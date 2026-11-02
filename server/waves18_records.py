"""Reviewed session records. No private trail, provider, or external effects."""
import copy, hashlib, json, re
from . import store, waves15_formats as formats, waves16_continuation as continuation
from .phase10_common import Context, Phase10Error, parse_source_ref

KIND='w18record'; RECEIPT='w18recordreceipt'
# Primary may enable only after every delivery and reuse boundary is wired.
RECORD_DELIVERY_INTEGRATED = True
def fail(code,message,status=409): raise Phase10Error(code,message,status)
def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(x): return hashlib.sha256(canon(x).encode('utf-8')).hexdigest()
def key(x):
    if not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',x): fail('invalid_request','Invalid request ID.',422)
    return x
def text(x,limit):
    if not isinstance(x,str) or not x.strip() or len(x)>limit or any(ord(c)<32 and c not in '\n\r\t' for c in x): fail('invalid_request','Invalid text.',422)
    try: x.encode('utf-8')
    except UnicodeEncodeError: fail('invalid_request','Invalid text.',422)
    return x
def fetch(sid,oid):
    r=store.get(KIND,oid,sid)
    if not r: fail('not_found','Record unavailable.',404)
    return r

def current(sid,snap):
    """Actor-independent revalidation; never infers a viewer or reads private jobs."""
    continuation.active_session(sid)
    # Selected jobs are a continuing dependency, not a permanent copy of authority.
    from . import phase12_jobs as jobs, waves15_translation_review as review, waves17_terminology as terms
    for binding in snap.get('translationBindings', {}).values():
        row = jobs.fetch(sid, binding['owner'], binding['requestId'])
        if (not row or row['credential_hash'] != binding['credentialHash'] or
            row['kind'] != 'translation' or row['state'] != 'complete' or not row['result'] or
            digest([row['ref'], row['payload'], row['result'], row['transport']]) != binding['digest']):
            fail('stale_context', 'Translation unavailable or changed.')
        source, moment, ref = jobs.rights(row)
        result = json.loads(row['result'])
        if (ref != binding['sourceRef'] or result.get('ref') != ref or
            result.get('original') != moment.get('text') or not source.get('audienceVisible')):
            fail('stale_context', 'Translation source changed.')
        review.check_speech_parent(row)
        terms.guard(row)
    for ref in snap['refs']:
        if ref.get('sessionId')!=sid: fail('stale_context','Source unavailable.')
        continuation.valid_ref(ref)
    for ref in snap.get('sourceRefs', []):
        ref = parse_source_ref(ref)
        source = store.get('source', ref['sourceId'], sid)
        from .http import expired
        if (ref['sessionId'] != sid or not source or source.get('_revision') != ref['sourceRevision']
            or source.get('status') != 'active' or expired(source) or not source.get('audienceVisible')):
            fail('stale_context', 'Source unavailable or changed.')
    for chapter in snap['chapters']:
        c=store.get('w15chapter',chapter['id'],sid)
        if not c or c['_revision']!=chapter['revision'] or c.get('status')!='active' or c.get('refs')!=chapter['refs']: fail('stale_context','Chapter changed.')
        for ref in c['refs']: continuation.valid_ref(ref)
    fmt=store.get(formats.F,snap['format']['id'],sid)
    if not fmt or fmt['_revision']!=snap['format']['revision'] or fmt.get('decision')!=snap['decision']: fail('stale_context','Outcome changed.')
    if fmt.get('continuationTransferId'):
        offer=store.get(continuation.T,fmt['continuationTransferId'])
        if not offer or offer.get('targetSessionId')!=sid: fail('stale_context','Continuation unavailable.')
        continuation.validate_offer(offer,('accepted',))
    if fmt.get('templateRoundId'):
        from . import waves17_templates as templates
        rd=store.get(templates.R,fmt['templateRoundId'],sid)
        if not rd or rd.get('formatId')!=fmt['id'] or rd.get('stage') not in ('reveal','close'): fail('stale_context','Round is not revealed.')
        v=store.get(templates.V,rd['templateId']+':'+str(rd['templateVersion']))
        if not v or rd['_revision']!=snap['roundRevision']: fail('stale_context','Template round changed.')
        if fmt.get('templateImportTransferId'): templates.validate_import(fmt['templateImportTransferId'])
    for ref in fmt.get('refs',[]): continuation.valid_ref(ref)
    ids=set()
    for item in snap['contributions']:
        c=store.get(formats.C,item['id'],sid)
        if not c or c['_revision']!=item['revision'] or c.get('status')!='accepted' or c.get('formatId')!=fmt['id'] or c.get('continuationTransferId')!=fmt.get('continuationTransferId'): fail('stale_context','Contribution changed.')
        for ref in c.get('refs',[]): continuation.valid_ref(ref)
        ids.add(c['id'])
    if not set(snap['decision']['reasonIds']) <= ids or not set(snap['decision']['minorityIds']) <= ids: fail('stale_context','Decision reasons unavailable.')
    return fmt

def snapshot(ctx,b):
    refs=b['refs']; source_refs=b.get('sourceRefs', [])
    if (not isinstance(refs,list) or not isinstance(source_refs,list) or not 1<=len(refs)+len(source_refs)<=20
        or any(not isinstance(x,dict) for x in refs+source_refs)
        or len({canon(x) for x in refs+source_refs})!=len(refs)+len(source_refs)):
        fail('invalid_request','Select current sources or moments.',422)
    if refs: ctx.resolve(refs)
    for ref in source_refs: ctx.resolve_source(ref)
    f=b['format']
    if not isinstance(f,dict) or set(f)!={'id','revision'} or not isinstance(f['id'],str) or type(f['revision']) is not int: fail('invalid_request','Select a format revision.',422)
    fmt=store.get(formats.F,f['id'],ctx.sid)
    if not fmt or fmt['_revision']!=f['revision'] or not isinstance(fmt.get('decision'),dict): fail('stale_context','Current outcome required.')
    if not isinstance(b['contributions'],list) or len(b['contributions'])>50: fail('invalid_request','Invalid contributions.',422)
    cs=b['contributions']
    if any(not isinstance(x,dict) or set(x)!={'id','revision'} or not isinstance(x['id'],str) or type(x['revision']) is not int for x in cs) or len({x['id'] for x in cs})!=len(cs): fail('invalid_request','Invalid contributions.',422)
    if not isinstance(b['chapters'],list) or len(b['chapters'])>20: fail('invalid_request','Invalid chapters.',422)
    chapters=[]
    for x in b['chapters']:
        if not isinstance(x,dict) or set(x)!={'id','revision'} or not isinstance(x['id'],str) or type(x['revision']) is not int: fail('invalid_request','Invalid chapter.',422)
        c=store.get('w15chapter',x['id'],ctx.sid)
        if not c or c['_revision']!=x['revision'] or c.get('status')!='active': fail('stale_context','Chapter unavailable.')
        chapters.append({'id':c['id'],'revision':c['_revision'],'refs':c['refs'],'title':c['title']})
    langs=copy.deepcopy(b['interpretations'])
    if not isinstance(langs,dict) or not 1<=len(langs)<=2 or not set(langs)<= {'en','es'}: fail('invalid_request','Select English or Spanish interpretations.',422)
    bindings={}
    for lang,value in list(langs.items()):
        if isinstance(value,str):
            text(value,6000)
            continue
        if not isinstance(value,dict) or set(value)!={'translationRequestId'}: fail('invalid_request','Invalid interpretation.',422)
        from . import phase12_jobs as jobs, waves15_translation_review as review, waves17_terminology as terms
        row=jobs.check_job(ctx.handler,ctx.sid,ctx.actor,key(value['translationRequestId']),'complete')
        if row['kind']!='translation' or not row['result']: fail('stale_context','Translation unavailable.')
        review.check_speech_parent(row); terms.guard(row)
        result=json.loads(row['result']); ref=json.loads(row['ref'])
        eligible=continuation.valid_ref(ref) if ref in b['refs'] else None
        if (not eligible or result.get('ref') != ref or result.get('original') != eligible['moment'].get('text') or result.get('sourceLanguage')!=b['sourceLanguage'] or result.get('targetLanguage')!=lang): fail('stale_context','Translation source or language differs.')
        text(result.get('translation'),6000); text(result.get('original'),6000)
        langs[lang]=result['translation']
        bindings[lang]={'owner':ctx.actor['owner'],'credentialHash':row['credential_hash'],'requestId':row['request_id'],'digest':digest([row['ref'],row['payload'],row['result'],row['transport']]),'original':result['original'],'sourceRef':ref}
    if b['sourceLanguage'] not in langs: fail('invalid_request','Source-language account required.',422)
    if len(canon(b).encode('utf-8'))>40000: fail('invalid_request','Record too large.',422)
    rd=store.get('w17templateround',fmt.get('templateRoundId'),ctx.sid) if fmt.get('templateRoundId') else None
    snap={'refs':copy.deepcopy(b['refs']),'sourceRefs':copy.deepcopy(source_refs),'chapters':chapters,'format':copy.deepcopy(f),'decision':copy.deepcopy(fmt['decision']),'contributions':copy.deepcopy(cs),'sourceLanguage':b['sourceLanguage'],'interpretations':copy.deepcopy(langs),'roundRevision':rd['_revision'] if rd else None,'translationBindings':bindings}
    current(ctx.sid,snap)
    return snap

def projection(sid,record,language):
    if record['state']!='approved': fail('not_found','Record unavailable.',404)
    snap=record['snapshot']; current(sid,snap)
    lang=language if language in snap['interpretations'] else snap['sourceLanguage']
    rows=[]
    for entry in snap['contributions']:
        c=store.get(formats.C,entry['id'],sid)
        rows.append({k:c.get(k) for k in ('id','selection','reason','alternative','refs')})
    return {'id':record['id'],'version':record['version'],'refs':snap['refs'],'sourceRefs':snap.get('sourceRefs',[]),'chapters':snap['chapters'],'decision':snap['decision'],'contributions':rows,'sourceLanguage':snap['sourceLanguage'],'language':lang,'fallback':lang!=language,'interpretation':snap['interpretations'][lang],'provenance':('creator_reviewed_translation' if lang in snap.get('translationBindings',{}) else 'creator_authored'),'sourceInterpretation':snap['interpretations'][snap['sourceLanguage']],'translationOriginal':snap.get('translationBindings',{}).get(lang,{}).get('original'),'availableLanguages':list(snap['interpretations'])}

def creator_view(sid, record):
    out=copy.deepcopy(record)
    def safe_snapshot(item):
        if item.get('state') == 'withdrawn':
            item.pop('snapshot', None); item['stale']=True; return
        try:
            current(sid,item['snapshot']); item['stale']=False
        except Phase10Error:
            item.pop('snapshot', None); item['stale']=True
    safe_snapshot(out)
    for item in out.get('history', []): safe_snapshot(item)
    return out

def check_binding(binding):
    required={'sessionId','recordId','version','language','targetSessionId','workId'}
    if not isinstance(binding,dict) or set(binding) not in (required,required|{'transferId'}): fail('stale_context','Record lineage unavailable.')
    record=fetch(binding['sessionId'],binding['recordId'])
    if record['version']!=binding['version'] or record['state']!='approved' or binding['language'] not in record['snapshot']['interpretations']: fail('stale_context','Record version unavailable.')
    current(binding['sessionId'],record['snapshot'])
    return record

def guard_offer(offer):
    if not RECORD_DELIVERY_INTEGRATED: fail('integration_required','Record-derived material delivery is not wired.',503)
    binding=offer.get('w18Record'); record=check_binding(binding)
    if binding.get('transferId')!=offer.get('id') or offer.get('targetSessionId')!=binding['targetSessionId'] or offer.get('sourceSessionId')!=binding['sessionId'] or offer.get('materialSnapshot',{}).get('w18Record')!=binding: fail('stale_context','Record offer unavailable.')
    link=store.get('w18recordreuse',binding['transferId'],binding['sessionId'])
    if not link or link.get('binding')!=binding: fail('stale_context','Record reuse binding unavailable.')
    if offer['snapshot'].get('workId')!=binding['workId'] or offer['snapshot'].get('formatId')!=record['snapshot']['format']['id'] or offer['snapshot'].get('formatRevision')!=record['snapshot']['format']['revision']: fail('stale_context','Record lineage changed.')
    source_marker={k:v for k,v in binding.items() if k!='transferId'}
    work=continuation.get(continuation.W,binding['workId'],binding['sessionId'])
    source=continuation.get('p10material',offer['snapshot']['materialId'],binding['sessionId'])
    if work.get('w18Record')!=source_marker or source.get('w18Record')!=source_marker or work.get('materialId')!=source.get('id'): fail('stale_context','Record source lineage unavailable.')
    return True

def guard_delivery(sid,material):
    if 'w18Record' not in material: return True
    if not RECORD_DELIVERY_INTEGRATED: fail('integration_required','Record-derived material delivery is not wired.',503)
    binding=material['w18Record']; record=check_binding(binding)
    live=store.get('p10material',material.get('id'),sid)
    if live!=material: fail('stale_context','Record material unavailable.')
    if 'transferId' not in binding:
        if sid!=binding['sessionId'] or material.get('continuationWorkId')!=binding['workId']: fail('stale_context','Record source work unavailable.')
        work=continuation.get(continuation.W,binding['workId'],sid)
        if work.get('materialId')!=material['id'] or work.get('w18Record')!=binding or work['snapshot']['targetSessionId']!=binding['targetSessionId']: fail('stale_context','Record source work unavailable.')
        continuation.validate_snapshot(work['snapshot'])
    else:
        if sid!=binding['targetSessionId'] or material.get('continuationTransferId')!=binding['transferId']: fail('stale_context','Record recipient unavailable.')
        offer=continuation.get(continuation.T,binding['transferId'])
        if offer.get('recipientMaterialId')!=material['id'] or offer.get('w18Record')!=binding: fail('stale_context','Record recipient unavailable.')
        continuation.validate_offer(offer,('accepted',))
    return True

def guard_material(ctx,material):
    with store.LOCK:
        ctx.check_actor()
        return guard_delivery(ctx.sid,material)


def options(ctx):
    """Current creator selections, without private jobs or private source material."""
    from . import phase12_jobs as jobs, waves15_translation_review as review, waves17_terminology as terms
    moments=[]
    for m in store.all('p10moment',ctx.sid):
        try:
            row=continuation.valid_ref(m.get('ref'))
            if row['ref']['sessionId'] != ctx.sid: continue
            moments.append({'ref':row['ref'],'sourceTitle':row['source'].get('title') or 'Source', 'text':row['moment'].get('text','')})
        except (Phase10Error, KeyError, TypeError): continue
    sources=[]
    for source in store.all('source',ctx.sid):
        try:
            ref={'sessionId':ctx.sid,'sourceId':source['id'],'sourceRevision':source['_revision']}
            row=ctx.resolve_source(ref)
            if not row['source'].get('audienceVisible'): continue
            sources.append({'ref':ref,'sourceTitle':source.get('title') or 'Source'})
        except (Phase10Error, KeyError, TypeError): continue
    chapters=[]
    for c in store.all('w15chapter',ctx.sid):
        try:
            if c.get('status')!='active' or not c.get('refs'): continue
            for ref in c['refs']:
                if ref.get('sessionId')!=ctx.sid: fail('stale_context','Source unavailable.')
                continuation.valid_ref(ref)
            chapters.append({'id':c['id'],'revision':c['_revision'],'title':c.get('title',''), 'refs':c['refs']})
        except (Phase10Error, KeyError, TypeError): continue
    choices=[]
    for f in store.all(formats.F,ctx.sid):
        try:
            projected, cs=formats.projection(ctx,f,ctx.sid,ctx.actor)
            if not projected.get('decision'): continue
            if f.get('templateRoundId'):
                rd=store.get('w17templateround',f['templateRoundId'],ctx.sid)
                if not rd or rd.get('stage') not in ('reveal','close'): continue
            entries=[]
            for c in cs:
                if c.get('status')!='accepted': continue
                entries.append({k:c.get(k) for k in ('id','selection','reason','alternative','refs')} | {'revision':c['_revision']})
            ids={c['id'] for c in entries}
            if not set(projected['decision']['reasonIds']+projected['decision']['minorityIds']) <= ids: continue
            choices.append({'id':f['id'],'revision':f['_revision'],'title':f.get('title',''), 'type':f.get('type'),'refs':f.get('refs',[]),'decision':projected['decision'],'contributions':entries})
        except (Phase10Error, KeyError, TypeError): continue
    translations=[]
    with store.connect() as db:
        ids=[r['request_id'] for r in db.execute("SELECT request_id FROM phase12_jobs WHERE session_id=? AND actor_id=? AND role='creator' AND kind='translation' AND state='complete' ORDER BY seq",(ctx.sid,ctx.actor['owner'])).fetchall()]
    for rid in ids:
        try:
            row=jobs.check_job(ctx.handler,ctx.sid,ctx.actor,rid,'complete')
            review.check_speech_parent(row); terms.guard(row)
            result=json.loads(row['result']); ref=json.loads(row['ref'])
            source=continuation.valid_ref(ref)
            if ref['sessionId']!=ctx.sid or result.get('ref')!=ref or result.get('original')!=source['moment'].get('text'): continue
            if result.get('sourceLanguage') not in ('en','es') or result.get('targetLanguage') not in ('en','es'): continue
            text(result.get('original'),6000); text(result.get('translation'),6000)
            translations.append({'requestId':rid,'sourceTitle':source['source'].get('title') or 'Source','ref':ref,'original':result['original'],'translation':result['translation'],'sourceLanguage':result['sourceLanguage'],'targetLanguage':result['targetLanguage'],'provenance':row['transport']})
        except (Phase10Error, KeyError, TypeError, ValueError): continue
    return {'moments':moments,'sources':sources,'chapters':chapters,'formats':choices,'translations':translations}

def recipient(code):
    # Same invitation checks as public_session, without lifecycle.ensure's legacy write on GET.
    import secrets
    from . import lifecycle
    if not isinstance(code,str) or not 1<=len(code)<=128: fail('not_found','Invitation unavailable.',404)
    with store.connect() as db:
        rows=db.execute("SELECT data FROM objects WHERE kind='session'").fetchall()
    for row in rows:
        session=json.loads(row['data'])
        if secrets.compare_digest(str(session.get('joinCode','')),code) and lifecycle.active(session) and not lifecycle.past(session.get('lifecycle',{}).get('invitationExpiresAt')):
            return {'sessionId':session['id'],'title':session.get('title') or 'Session'}
    fail('not_found','Invitation unavailable.',404)

def reuse_options(ctx, record_id, target):
    if not RECORD_DELIVERY_INTEGRATED: fail('integration_required','Record-derived material delivery is not wired.',503)
    record=fetch(ctx.sid,record_id)
    if record.get('creatorId')!=ctx.actor['owner'] or record.get('state')!='approved': fail('not_found','Record unavailable.',404)
    fmt=current(ctx.sid,record['snapshot']); continuation.active_session(target)
    if record['snapshot'].get('sourceRefs'): fail('unsupported_source_transfer','Untimed source transfer is not available.',409)
    if target==ctx.sid: fail('invalid_request','Select another session.',422)
    snap=record['snapshot']; refs=list(fmt.get('refs',[]))
    for entry in snap['contributions']:
        c=store.get(formats.C,entry['id'],ctx.sid)
        for ref in c.get('refs',[]):
            if ref not in refs: refs.append(ref)
    for ref in snap['refs']+[r for c in snap['chapters'] for r in c['refs']]:
        if ref not in refs: refs.append(ref)
    grants=store.all(continuation.G,ctx.sid); consents=store.all(continuation.A,ctx.sid)
    refrows=[]
    for ref in refs:
        source=continuation.valid_ref(ref)
        refrows.append({'ref':ref,'sourceTitle':source['source'].get('title') or 'Source','text':source['moment'].get('text',''),'grantIds':[g['id'] for g in grants if g.get('status')=='active' and g.get('formatId')==fmt['id'] and g.get('targetSessionId')==target and g.get('ref')==ref]})
    contributions=[]
    for entry in snap['contributions']:
        c=store.get(formats.C,entry['id'],ctx.sid)
        contributions.append({'id':c['id'],'revision':c['_revision'],'selection':c.get('selection'),'reason':c.get('reason'),'alternative':c.get('alternative'),'consentIds':[g['id'] for g in consents if g.get('status')=='active' and g.get('targetSessionId')==target and g.get('contributionId')==c['id'] and g.get('contributionRevision')==c['_revision']]})
    return {'recordId':record_id,'version':record['version'],'revision':record['_revision'],'targetSessionId':target,'formatId':fmt['id'],'languages':list(snap['interpretations']),'refs':refrows,'contributions':contributions}

def incoming(ctx):
    if not RECORD_DELIVERY_INTEGRATED: return {'offers':[],'materials':[],'works':[]}
    with store.connect() as db:
        rows=db.execute('SELECT data,revision FROM objects WHERE kind=?',(continuation.T,)).fetchall()
    offers=[]
    for row in rows:
        offer=dict(json.loads(row['data']),_revision=row['revision'])
        if offer.get('targetSessionId')!=ctx.sid or not offer.get('w18Record'): continue
        try:
            continuation.validate_offer(offer)
            binding=offer['w18Record']; record=fetch(binding['sessionId'],binding['recordId'])
            offers.append({'id':offer['id'],'revision':offer['_revision'],'status':offer['status'],'sourceSessionId':offer['sourceSessionId'],'sourceTitle':(store.get('session',offer['sourceSessionId']) or {}).get('title') or 'Session','recordId':record['id'],'recordVersion':record['version'],'language':binding['language'],'format':offer['formatSnapshot'],'contributions':offer['contributionSnapshot'],'material':offer['materialSnapshot'],'rights':{'sourceGrantIds':[x['grantId'] for x in offer['snapshot']['refs']],'consentIds':[x['consentId'] for x in offer['snapshot']['contributions']]},'recipientFormatId':offer.get('recipientFormatId'),'recipientMaterialId':offer.get('recipientMaterialId')})
        except (Phase10Error, KeyError, TypeError): continue
    materials=[]
    for material in store.all('p10material',ctx.sid):
        if not material.get('w18Record'): continue
        try:
            guard_delivery(ctx.sid,material)
            materials.append({k:material.get(k) for k in ('id','title','status','currentVersion','approvedVersion','continuationWorkId','continuationTransferId','w18Record')})
        except (Phase10Error, KeyError, TypeError): continue
    works=[]
    for work in store.all(continuation.W,ctx.sid):
        if not work.get('w18Record'): continue
        try:
            material=continuation.get('p10material',work['materialId'],ctx.sid); guard_delivery(ctx.sid,material)
            works.append({'id':work['id'],'materialId':material['id'],'targetSessionId':work['snapshot']['targetSessionId'],'recordId':work['w18Record']['recordId'],'recordVersion':work['w18Record']['version'],'language':work['w18Record']['language']})
        except (Phase10Error, KeyError, TypeError): continue
    return {'offers':offers,'materials':materials,'works':works}

def handle(handler,sid,actor,method,parts):
    ctx=Context(handler,sid,actor)
    with store.LOCK:
        ctx.check_actor()
        if actor.get('sid')!=sid: fail('not_found','Session unavailable.',404)
        if actor.get('role')=='creator' and method=='GET':
            if parts==['records','options']: return 200,options(ctx)
            if len(parts)==3 and parts[:2]==['records','recipient']: return 200,{'recipient':recipient(parts[2])}
            if len(parts)==4 and parts[0]=='records' and parts[2]=='reuse-options': return 200,reuse_options(ctx,parts[1],parts[3])
            if parts==['records','incoming']: return 200,incoming(ctx)
        if method=='GET' and parts==['records']:
            result=[]
            for record in store.all(KIND,sid):
                if actor.get('role')=='creator':
                    if record.get('creatorId')!=actor['owner']: continue
                    try:
                        current(sid,record['snapshot']); stale=False
                    except Phase10Error:
                        stale=True
                    result.append({'id':record['id'],'version':record['version'],
                                   'revision':record['_revision'],'state':record['state'],'stale':stale})
                else:
                    try:
                        result.append(projection(sid,record,record['snapshot']['sourceLanguage']))
                    except Phase10Error:
                        continue
            return 200,{'records':result}
        if method=='GET' and len(parts)==3 and parts[0]=='records' and parts[2] in ('en','es'):
            return 200,{'record':projection(sid,fetch(sid,parts[1]),parts[2])}
        if actor.get('role')!='creator': fail('forbidden','Creator access required.',403)
        if method=='GET' and len(parts)==2 and parts[0]=='record-operations':
            rid=digest([sid,actor['owner'],key(parts[1])]); rec=store.get(RECEIPT,rid,sid)
            if not rec: return 200,{'operation':{'requestId':parts[1],'state':'unknown'}}
            if rec.get('action') in ('prepare-reuse','reuse-offers'):
                record=fetch(sid,rec['recordId'])
                if record.get('creatorId')!=actor['owner'] or record.get('_revision')!=rec['revision'] or record.get('state')!='approved': fail('stale_context','Record operation unavailable.')
                current(sid,record['snapshot'])
                if rec['action']=='prepare-reuse':
                    work=continuation.get(continuation.W,rec['workId'],sid)
                    material=continuation.get('p10material',rec['materialId'],sid)
                    if work.get('materialId')!=material['id']: fail('stale_context','Record operation unavailable.')
                    guard_material(ctx,material)
                else:
                    continuation.guard_offer(ctx,continuation.get(continuation.T,rec['transferId'],sid))
            op={'requestId':parts[1],'state':'committed','recordId':rec['recordId'],'revision':rec['revision']}
            for field in ('action','workId','materialId','transferId'):
                if field in rec: op[field]=rec[field]
            return 200,{'operation':op}
        if method=='GET' and len(parts)==2 and parts[0]=='records':
            r=fetch(sid,parts[1]);
            if r.get('creatorId')!=actor['owner']: fail('not_found','Record unavailable.',404)
            view=creator_view(sid,r)
            return 200,{'record':view,'stale':view['stale']}
        if method!='POST': fail('not_found','Route unavailable.',404)
        b=handler.body()
        if not isinstance(b,dict): fail('invalid_request','Invalid body.',422)
        request=key(b.get('requestId')); rid=digest([sid,actor['owner'],request]); fp=digest([parts,b])
        old=store.get(RECEIPT,rid,sid)
        action=parts[2] if len(parts)==3 and parts[0]=='records' else None
        if action in ('prepare-reuse','reuse-offers'):
            record=fetch(sid,parts[1])
            if record.get('creatorId')!=actor['owner']: fail('not_found','Record unavailable.',404)
            if old:
                if old['fingerprint']!=fp: fail('request_conflict','Request ID already used.')
                if record['_revision']!=old['revision'] or record['state']!='approved': fail('stale_revision','Record changed.')
                current(sid,record['snapshot'])
                if old.get('action')=='prepare-reuse':
                    work=continuation.get(continuation.W,old['workId'],sid); material=continuation.get('p10material',old['materialId'],sid)
                    guard_delivery(sid,material)
                    return old['status'],{'work':work,'material':material,'operation':{'requestId':request,'state':'committed'}}
                offer=continuation.get(continuation.T,old['transferId'],sid); continuation.validate_offer(offer)
                return old['status'],{'transfer':offer,'operation':{'requestId':request,'state':'committed'}}
            if type(b.get('revision')) is not int or type(b.get('version')) is not int or record['_revision']!=b['revision'] or record['version']!=b['version'] or record['state']!='approved': fail('stale_revision','Current approved record required.')
            snap=record['snapshot']; fmt=current(sid,snap)
            if action=='prepare-reuse':
                if snap.get('sourceRefs'): fail('unsupported_source_transfer','Untimed source transfer is not available.',409)
                if set(b)!={'requestId','revision','version','targetSessionId','contributions','sourceGrantIds','language'} or b['language'] not in snap['interpretations']: fail('invalid_request','Select a record language, target and grants.',422)
                chosen=b['contributions']
                if (not isinstance(chosen,list) or any(not isinstance(x,dict) or set(x)!={'id','revision','consentId'} or not isinstance(x['id'],str) or type(x['revision']) is not int or not isinstance(x['consentId'],str) for x in chosen) or sorted((x['id'],x['revision']) for x in chosen)!=sorted((x['id'],x['revision']) for x in snap['contributions'])): fail('invalid_request','Select consent for every record contribution.',422)
                extra=list(snap['refs'])
                for chapter in snap['chapters']:
                    for ref in chapter['refs']:
                        if ref not in extra: extra.append(ref)
                base={'revision':fmt['_revision'],'targetSessionId':b['targetSessionId'],'contributions':chosen,'sourceGrantIds':b['sourceGrantIds']}
                cs=continuation.snapshot(ctx,fmt,base,extra)
                content='Reviewed record ('+b['language']+'):\n'+snap['interpretations'][b['language']]+'\n\n'+continuation.compose(ctx,fmt,cs)
                marker={'sessionId':sid,'recordId':record['id'],'version':record['version'],'language':b['language'],'targetSessionId':b['targetSessionId']}
                prepared=continuation.prepare_work(ctx,fmt,base,extra,content,marker)
                receipt={'fingerprint':fp,'recordId':record['id'],'revision':record['_revision'],'status':201,'action':action,'workId':prepared[0],'materialId':prepared[1]}
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE'); continuation.write_work(db,sid,actor['owner'],prepared); continuation.insert(db,RECEIPT,sid,actor['owner'],rid,receipt); db.commit()
                return 201,{'work':continuation.get(continuation.W,prepared[0],sid),'material':continuation.get('p10material',prepared[1],sid),'operation':{'requestId':request,'state':'committed'}}
            if set(b)!={'requestId','revision','version','workId','materialId','materialVersion'}: fail('invalid_request','Select approved source material.',422)
            work=continuation.get(continuation.W,b['workId'],sid); marker=work.get('w18Record')
            if not marker or marker.get('recordId')!=record['id'] or marker.get('version')!=record['version'] or marker.get('sessionId')!=sid: fail('stale_context','Record work unavailable.')
            material=continuation.get('p10material',b['materialId'],sid); guard_delivery(sid,material)
            prepared=continuation.prepare_offer(sid,fmt,{'revision':fmt['_revision'],'workId':b['workId'],'materialId':b['materialId'],'materialVersion':b['materialVersion']})
            binding=prepared[1]['w18Record']; receipt={'fingerprint':fp,'recordId':record['id'],'revision':record['_revision'],'status':201,'action':action,'transferId':prepared[0]}
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE'); continuation.write_offer(db,sid,actor['owner'],prepared); continuation.insert(db,'w18recordreuse',sid,actor['owner'],prepared[0],{'binding':binding}); continuation.insert(db,RECEIPT,sid,actor['owner'],rid,receipt); db.commit()
            return 201,{'transfer':continuation.get(continuation.T,prepared[0],sid),'operation':{'requestId':request,'state':'committed'}}
        if old:
            if old['fingerprint']!=fp: fail('request_conflict','Request ID already used.')
            r=fetch(sid,old['recordId']); current(sid,r['snapshot'])
            if r['_revision']!=old['revision']: fail('stale_revision','Committed record has changed.')
            return old['status'],{'record':creator_view(sid,r),'operation':{'requestId':request,'state':'committed'}}
        create=parts==['records']; action=parts[2] if len(parts)==3 and parts[0]=='records' else None
        if create:
            fields={'requestId','refs','chapters','format','contributions','sourceLanguage','interpretations'}
            if set(b) not in (fields,fields|{'sourceRefs'}): fail('invalid_request','Invalid fields.',422)
            snap=snapshot(ctx,b); oid=store.ident(); r={'id':oid,'creatorId':actor['owner'],'version':1,'state':'draft','snapshot':snap,'history':[]}; rev=1; status=201
        elif action == 'versions':
            fields={'requestId','revision','version','refs','chapters','format','contributions','sourceLanguage','interpretations'}
            if set(b) not in (fields,fields|{'sourceRefs'}) or type(b['revision']) is not int or type(b['version']) is not int: fail('invalid_request','Invalid fields.',422)
            r=fetch(sid,parts[1]); oid=r['id']
            if r.get('creatorId')!=actor['owner']: fail('not_found','Record unavailable.',404)
            if r['_revision']!=b['revision'] or r['version']!=b['version']: fail('stale_revision','Record changed.')
            if r['state']=='withdrawn': fail('stale_revision','Record withdrawn.')
            snap=snapshot(ctx,b)
            history=r.setdefault('history',[])
            history.append({'version':r['version'],'state':r['state'],'snapshot':copy.deepcopy(r['snapshot'])})
            r['version']+=1; r['state']='draft'; r['snapshot']=snap
            rev=r.pop('_revision')+1; status=201
        elif action in ('approve','withdraw'):
            if set(b)!={'requestId','revision','version'} or type(b['revision']) is not int or type(b['version']) is not int: fail('invalid_request','Invalid fields.',422)
            r=fetch(sid,parts[1]); oid=r['id']
            if r.get('creatorId')!=actor['owner']: fail('not_found','Record unavailable.',404)
            if r['_revision']!=b['revision'] or r['version']!=b['version']: fail('stale_revision','Record changed.')
            if action=='approve':
                if r['state']!='draft': fail('stale_revision','Only a draft can be approved.')
                current(sid,r['snapshot']); r['state']='approved'
            else:
                if r['state'] not in ('draft','approved'): fail('stale_revision','Record already withdrawn.')
                r['state']='withdrawn'
            rev=r.pop('_revision')+1; status=200
        else: fail('not_found','Route unavailable.',404)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if create:
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',(KIND,oid,sid,actor['owner'],rev,canon(r),store.now()))
            else:
                n=db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=? AND revision=?',(canon(r),rev,KIND,oid,sid,rev-1)).rowcount
                if n!=1: fail('stale_revision','Record changed.')
            receipt={'id':rid,'fingerprint':fp,'recordId':oid,'revision':rev,'status':status}
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',(RECEIPT,rid,sid,actor['owner'],canon(receipt),store.now()))
            db.commit()
        return status,{'record':creator_view(sid,dict(r,_revision=rev)),'operation':{'requestId':request,'state':'committed'}}

