"""Current-rights feed of received, audience-authorized ASR segments."""
import hashlib,json,re
from urllib.parse import parse_qs,urlparse
from . import store,phase10_timeline,phase10_common

MAX_ROWS=2048

def verified_moment_language(source,moment):
    """Derive one language from this exact server-verified ASR interval."""
    try:
        ref=phase10_common.parse_ref(moment['ref'])
        proof=source.get('p10Provenance') or {}
        if (proof.get('type')!='received_asr_v1' or proof.get('sessionId')!=ref['sessionId']
                or source.get('id')!=ref['sourceId'] or source.get('_revision')!=ref['sourceRevision']):return None
        top=source.get('language');parts=source.get('segments')
        if top not in ('en','es','mixed') or not isinstance(parts,list) or not 1<=len(parts)<=1000:return None
        spans=[];languages=set()
        for part in parts:
            if not isinstance(part,dict):return None
            # Older single-language ASR records have no per-segment field. Their
            # server-created aggregate result is the only allowed fallback.
            language=part.get('language')
            if language is None and top in ('en','es'):language=top
            if language not in ('en','es'):return None
            start=phase10_timeline._ms(part.get('sessionStartSeconds'))
            end=phase10_timeline._ms(part.get('sessionEndSeconds'))
            if end<=start or (spans and start<spans[-1][1]):return None
            spans.append((start,end,language));languages.add(language)
        if ((top=='mixed' and languages!={'en','es'})
                or (top in ('en','es') and languages!={top})):return None
        selected=[part for part in spans if part[0]>=ref['startMs'] and part[1]<=ref['endMs']]
        overlapping=[part for part in spans if part[0]<ref['endMs'] and part[1]>ref['startMs']]
        if (not selected or selected!=overlapping or selected[0][0]!=ref['startMs']
                or selected[-1][1]!=ref['endMs']):return None
        selected_languages={part[2] for part in selected}
        if len(selected_languages)!=1:return None
        language=selected[0][2]
        if moment.get('language',language)!=language:return None
        return language
    except (phase10_common.Phase10Error,KeyError,TypeError,ValueError,OverflowError):
        return None


def index_source(sid,source_id):
    with store.LOCK:
        from .http import expired
        source=store.get('source',source_id,sid)
        if not source or expired(source) or not source.get('audienceVisible') or source.get('status')!='active' or source.get('language') not in ('en','es','mixed') or source.get('p10Provenance',{}).get('type')!='received_asr_v1':return False
        with store.connect() as db:
            prior=db.execute('SELECT revision FROM phase12_feed_sources WHERE session_id=? AND source_id=?',(sid,source_id)).fetchone()
        if prior and prior['revision']==source['_revision']:return True
        parts=source.get('segments',[])
        if not parts:return False
        corrected=hashlib.sha256(source['text'].encode()).hexdigest()!=source['p10Provenance'].get('textSha256')
        spans=[{'startMs':phase10_timeline._ms(p['sessionStartSeconds']),'endMs':phase10_timeline._ms(p['sessionEndSeconds']),'kind':'other'} for p in parts]
        if corrected:spans=[{'startMs':spans[0]['startMs'],'endMs':spans[-1]['endMs'],'kind':'correction'}]
        moments=[]
        for span in spans:
            for moment in phase10_timeline.build_moments(source,[span]):
                language=verified_moment_language(source,moment)
                if language is None:return False
                moment['language']=language
                moments.append(moment)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT revision FROM phase12_feed_sources WHERE session_id=? AND source_id=?',(sid,source_id)).fetchone()
            if prior and prior['revision']==source['_revision']:
                db.commit();return True
            for moment in moments:
                mid=moment['ref']['momentId'];existing=db.execute("SELECT data FROM objects WHERE kind='p10moment' AND id=? AND session_id=?",(mid,sid)).fetchone()
                if existing:
                    prior=json.loads(existing['data'])
                    if (prior.get('ref')!=moment['ref'] or prior.get('text')!=moment['text']
                            or prior.get('language',moment['language'])!=moment['language']):raise phase10_common.Phase10Error('index_conflict','Indexed segment conflicts.',409)
                    if 'language' not in prior:
                        prior['language']=moment['language']
                        db.execute("UPDATE objects SET data=? WHERE kind='p10moment' AND id=? AND session_id=?",(json.dumps(prior,ensure_ascii=False),mid,sid))
                else:
                    value={**moment,'id':mid}
                    db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('p10moment',?,?,NULL,1,?,?)",(mid,sid,json.dumps(value,ensure_ascii=False),store.now()))
                if not db.execute('SELECT 1 FROM phase12_caption_feed WHERE moment_id=?',(mid,)).fetchone():
                    db.execute('INSERT INTO phase12_feed_counter VALUES(?,1) ON CONFLICT(session_id) DO UPDATE SET seq=seq+1',(sid,))
                    seq=db.execute('SELECT seq FROM phase12_feed_counter WHERE session_id=?',(sid,)).fetchone()['seq']
                    db.execute('INSERT INTO phase12_caption_feed(session_id,seq,source_id,moment_id,ref,language,run_id) VALUES(?,?,?,?,?,?,?)',(sid,seq,source_id,mid,json.dumps(moment['ref'],sort_keys=True),moment['language'],moment.get('captureRunId')))
            db.execute('INSERT INTO phase12_feed_sources VALUES(?,?,?) ON CONFLICT(session_id,source_id) DO UPDATE SET revision=excluded.revision',(sid,source_id,source['_revision']))
            cutoff=db.execute('SELECT seq FROM phase12_caption_feed WHERE session_id=? ORDER BY seq DESC LIMIT 1 OFFSET ?',(sid,MAX_ROWS-1)).fetchone()
            if cutoff:
                discarded=db.execute('SELECT MAX(seq) FROM phase12_caption_feed WHERE session_id=? AND seq<?',(sid,cutoff['seq'])).fetchone()[0]
                if discarded is not None:
                    db.execute('DELETE FROM phase12_caption_feed WHERE session_id=? AND seq<=?',(sid,discarded))
                    db.execute('INSERT INTO phase12_feed_floor VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET seq=MAX(seq,excluded.seq)',(sid,discarded))
            db.commit()
        return True

def feed(handler,sid,actor):
    q=parse_qs(urlparse(handler.path).query,keep_blank_values=True)
    if set(q)-{'after','limit','runId'} or any(len(v)!=1 for v in q.values()):raise phase10_common.Phase10Error('invalid_query','Invalid caption feed query.',422)
    def integer(name,default,maximum):
        v=q.get(name,[str(default)])[0]
        if not v.isascii() or not v.isdigit() or len(v)>16 or not 0<=int(v)<=maximum:raise phase10_common.Phase10Error('invalid_query','Invalid caption feed cursor or limit.',422)
        return int(v)
    after=integer('after',0,2**53-1);limit=integer('limit',50,100)
    if limit<1:raise phase10_common.Phase10Error('invalid_query','Limit must be between 1 and 100.',422)
    run=q.get('runId',[None])[0]
    if run is not None and not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',run):raise phase10_common.Phase10Error('invalid_query','Invalid capture run.',422)
    with store.LOCK,store.connect() as db:
        floorrow=db.execute('SELECT seq FROM phase12_feed_floor WHERE session_id=?',(sid,)).fetchone();floor=floorrow['seq'] if floorrow else 0
        if after and after<floor:raise phase10_common.Phase10Error('cursor_expired','The caption cursor expired; restart with after=0.',410)
        rows=db.execute('SELECT * FROM phase12_caption_feed WHERE session_id=? AND seq>? ORDER BY seq LIMIT 200',(sid,after)).fetchall()
        from .phase12_jobs import capture_time_metadata
        context=phase10_common.Context(handler,sid,actor); items=[];cursor=after
        for row in rows:
            cursor=row['seq']
            if run is not None and row['run_id']!=run:continue
            ref=json.loads(row['ref'])
            try:resolved=context.resolve([ref])[0]
            except phase10_common.Phase10Error:continue
            src=resolved['source'];moment=resolved['moment']
            if not src.get('audienceVisible') or verified_moment_language(src,moment)!=row['language']:continue
            items.append({'sequence':row['seq'],'ref':ref,'original':moment['text'],'sourceLanguage':row['language'],'alignment':moment['alignment'],'captureRunId':moment.get('captureRunId'),'speaker':None,'captureId':src.get('captureId'),'chunkId':src.get('chunkId'),'capturedAtISO':src.get('capturedAtISO'),'offsetSeconds':src.get('offsetSeconds'),**capture_time_metadata(src)})
            if len(items)>=limit:break
        has_more=bool(db.execute('SELECT 1 FROM phase12_caption_feed WHERE session_id=? AND seq>? LIMIT 1',(sid,cursor)).fetchone())
        handler._p10_refs=[x['ref'] for x in items]
        handler._p12_feed_binding=(sid,actor,[x['ref'] for x in items])
        return 200,{'items':items,'nextCursor':cursor,'hasMore':has_more,'truncatedBefore':floor}


def bootstrap():
    """Backfill existing eligible sources once per revision before serving requests."""
    with store.connect() as db:
        rows=db.execute("SELECT id,session_id FROM objects WHERE kind='source' ORDER BY rowid").fetchall()
    for row in rows:
        try:index_source(row['session_id'],row['id'])
        except (phase10_common.Phase10Error,KeyError,TypeError,ValueError):continue
