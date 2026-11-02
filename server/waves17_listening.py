"""Private, bounded listening state over completed Phase 12 jobs."""
import hashlib
import json
from . import store, phase12_jobs as jobs, waves15_translation_review as review, waves17_terminology as terms
from .phase10_common import Phase10Error, Context

KIND = 'w17listening'
RECEIPT = 'w17listenreceipt'
MAX_SEGMENTS = 16
MAX_SPAN_MS = 120000
MAX_RECEIPTS = 4096


def fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def check_actor(handler, sid, actor):
    terms.actor_check(handler, sid, actor)
    if actor.get('role') != 'viewer':
        fail('forbidden', 'Viewer capability required.', 403)


def key(sid, actor, credential):
    return digest([sid, actor['owner'], credential])


def load(sid, oid):
    return store.get(KIND, oid, sid)


def feed_info(sid):
    with store.connect() as db:
        floor = db.execute('SELECT seq FROM phase12_feed_floor WHERE session_id=?', (sid,)).fetchone()
        latest = db.execute('SELECT seq FROM phase12_feed_counter WHERE session_id=?', (sid,)).fetchone()
    return (floor['seq'] if floor else 0, latest['seq'] if latest else 0)


def sequence(sid, ref):
    with store.connect() as db:
        rows = db.execute('SELECT seq,ref,run_id FROM phase12_caption_feed WHERE session_id=? AND moment_id=?', (sid, ref.get('momentId'))).fetchall() if isinstance(ref, dict) and ref.get('momentId') else []
    for row in rows:
        if json.loads(row['ref']) == ref:
            return row['seq'], row['run_id']
    return None, None


def resolve(handler, sid, actor, entry):
    row = jobs.check_job(handler, sid, actor, entry['translationRequestId'], 'complete')
    if row['kind'] != 'translation' or not row['result']:
        fail('stale_context', 'Translation unavailable.')
    review.check_speech_parent(row)
    binding = terms.guard(row)
    result = json.loads(row['result'])
    ref = json.loads(row['ref'])
    # Typed selections have no established comparable feed binding here.
    comparable = ref if 'momentId' in ref else None
    seq, run = sequence(sid, comparable)
    current = {'translationRequestId':row['request_id'], 'speechRequestId':entry.get('speechRequestId'),
               'ref':ref, 'sequence':seq, 'captureRunId':run, 'language':result.get('targetLanguage'),
               'text':result.get('translation'), 'translationVersion':result.get('translationVersion'),
               'terminologyRevision':binding['revision'] if binding else None}
    if not isinstance(current['text'], str) or len(current['text']) > 12000 or current['language'] not in ('en', 'es'):
        fail('stale_context', 'Translation result unavailable.')
    speech_id = entry.get('speechRequestId')
    if speech_id:
        speech = jobs.check_job(handler, sid, actor, speech_id, 'complete')
        if speech['kind'] != 'speech' or not speech['media'] or json.loads(speech['payload']).get('translationRequestId') != row['request_id']:
            fail('stale_context', 'Speech unavailable.')
    if entry.get('identity') and entry['identity'] != digest(current):
        fail('stale_context', 'Listening item changed.')
    current['identity'] = digest(current)
    return current


def feed_point(handler, sid, actor, seq):
    """Resolve the exact retained feed row with current source rights and alignment."""
    if not seq:
        return None
    with store.connect() as db:
        row = db.execute('SELECT seq,ref,run_id FROM phase12_caption_feed WHERE session_id=? AND seq=?', (sid, seq)).fetchone()
    if not row:
        return None
    try:
        ref = json.loads(row['ref'])
        resolved = Context(handler, sid, actor).resolve([ref])[0]
        source, moment = resolved['source'], resolved['moment']
        # The same validation used by jobs rebuilds alignment from current ASR evidence.
        from . import phase10_timeline
        rebuilt = phase10_timeline.build_moments(source, [{'startMs':ref['startMs'], 'endMs':ref['endMs'], 'kind':moment.get('kind')}])[0]
        if rebuilt['ref'] != ref or rebuilt['alignment'] != moment.get('alignment') or rebuilt.get('captureRunId') != row['run_id']:
            return None
        return {'sequence':seq, 'ref':ref, 'captureRunId':row['run_id'], 'endMs':ref['endMs'],
                'captureTimeProvenance':jobs.capture_time_metadata(source)['captureTimeProvenance']}
    except (Phase10Error, KeyError, TypeError, ValueError):
        return None


def source_offset(checkpoint, latest):
    reason = None
    if not checkpoint or not latest:
        reason = 'Checkpoint or latest retained source is unavailable.'
    elif not checkpoint['captureRunId'] or checkpoint['captureRunId'] != latest['captureRunId']:
        reason = 'Capture clocks are unavailable or differ.'
    elif latest['endMs'] < checkpoint['endMs']:
        reason = 'Source times are not ordered in the capture run.'
    provenance = {'status':'unknown' if reason else 'known', 'basis':'reported_capture_run_offset_ms',
                  'captureRunId':None if reason else latest['captureRunId'], 'reason':reason}
    return (None if reason else latest['endMs'] - checkpoint['endMs']), provenance


def projection(handler, sid, actor, state):
    floor, latest = feed_info(sid)
    entries, invalid = [], 0
    for item in state['queue']:
        try:
            entries.append(resolve(handler, sid, actor, item))
        except Phase10Error:
            invalid += 1
    if state['mode'] == 'live':
        entries = [e for e in entries if e['sequence'] == latest and latest != 0]
    entries.sort(key=lambda x: (x['sequence'] is None, x['sequence'] or 0, x['translationRequestId']))
    seqs = {e['sequence'] for e in entries if e['sequence'] is not None}
    checkpoint = state['checkpoint']
    with store.connect() as db:
        rows = db.execute('SELECT seq FROM phase12_caption_feed WHERE session_id=? AND seq>? ORDER BY seq LIMIT 2049', (sid, checkpoint)).fetchall()
    missing = [r['seq'] for r in rows if r['seq'] not in seqs]
    gaps = {'expired':bool(checkpoint < floor), 'missingSequences':missing[:32],
            'moreMissing':len(missing)>32, 'unknownSequence':any(e['sequence'] is None for e in entries),
            'invalidated':invalid, 'overflow':state['overflow']}
    current_point = feed_point(handler, sid, actor, checkpoint)
    latest_point = feed_point(handler, sid, actor, latest)
    offset_ms, clock = source_offset(current_point, latest_point)
    return {'sourceOffsetMs':offset_ms, 'clockProvenance':clock, 'currentCheckpoint':current_point,
            'latestAvailableSource':latest_point, 'generation':state['generation'], 'mode':state['mode'], 'preferences':state['preferences'],
            'checkpoint':checkpoint, 'feedFloor':floor, 'feedLatest':latest, 'queue':entries,
            'gaps':gaps, 'offset':{'status':clock['status'], 'reason':clock['reason'], 'sourceOffsetMs':offset_ms},
            'requiresChoice':state['mode']=='awaiting_choice'}


def final_guard(handler):
    sid, actor, credential, expected = handler._w17_listening_binding
    check_actor(handler, sid, actor)
    if store.digest(handler._auth_token) != credential:
        fail('stale_context', 'Capability changed.')
    state = load(sid, key(sid, actor, credential))
    if not state or projection(handler, sid, actor, state) != expected:
        fail('stale_context', 'Listening state or source eligibility changed.')


def handle(handler, sid, actor, method, parts):
    check_actor(handler, sid, actor)
    credential = store.digest(handler._auth_token)
    oid = key(sid, actor, credential)
    with store.LOCK:
        if method == 'GET':
            if parts == []:
                state = load(sid, oid)
                if not state: fail('not_found', 'Listening profile unavailable.', 404)
                result = projection(handler, sid, actor, state)
                handler._w17_listening_binding = (sid, actor, credential, result)
                return 200, {'listening':result}
            if len(parts)==2 and parts[0]=='receipts' and jobs.valid_id(parts[1]):
                receipt = store.get(RECEIPT, digest([oid, parts[1]]), sid)
                if not receipt: fail('not_found', 'Receipt unavailable.', 404)
                return 200, {'receipt':receipt['ack']}
            fail('not_found', 'Listening route unavailable.', 404)
        if method != 'POST' or parts not in ([], ['enqueue'], ['choose'], ['pause'], ['reconnect'], ['advance'], ['preferences']):
            fail('not_found', 'Listening route unavailable.', 404)
        body = handler.body()
        action = parts[0] if parts else 'create'
        fields = {'requestId','generation'} | {'enqueue':{'translationRequestId','speechRequestId'}, 'choose':{'mode'}, 'advance':{'translationRequestId'}, 'preferences':{'preferences'}}.get(action,set())
        if not isinstance(body,dict) or set(body)!=fields or not jobs.valid_id(body.get('requestId')) or type(body.get('generation')) is not int or body['generation']<0 or len(canonical(body).encode('utf-8'))>20000:
            fail('invalid_request', 'Invalid listening request.', 422)
        rid = digest([oid,body['requestId']])
        fingerprint = digest([action,body])
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND session_id=?',(RECEIPT,rid,sid)).fetchone()
            if old:
                receipt=json.loads(old['data'])
                if receipt['fingerprint'] != fingerprint: fail('request_conflict','Request ID is bound to a different payload.')
                db.commit()
                return 200, {'receipt':receipt['ack']}
            if db.execute('SELECT COUNT(*) FROM objects WHERE kind=? AND session_id=?',(RECEIPT,sid)).fetchone()[0]>=MAX_RECEIPTS:
                fail('receipt_capacity','Listening receipt storage is full.',429)
            raw=db.execute('SELECT data,revision FROM objects WHERE kind=? AND id=? AND session_id=?',(KIND,oid,sid)).fetchone()
            state=json.loads(raw['data']) if raw else None
            if action=='create':
                if state or body['generation'] != 0: fail('stale_generation','Listening profile already exists.')
                state={'id':oid,'generation':0,'mode':'awaiting_choice','preferences':{'pace':1.0,'textOnly':False},'checkpoint':0,'queue':[],'overflow':False}
            elif not state: fail('not_found','Listening profile unavailable.',404)
            if state['generation'] != body['generation']: fail('stale_generation','Listening state changed.')
            if action=='enqueue':
                if not jobs.valid_id(body['translationRequestId']) or (body['speechRequestId'] is not None and not jobs.valid_id(body['speechRequestId'])): fail('invalid_request','Invalid job reference.',422)
                entry=resolve(handler,sid,actor,body)
                if entry['sequence'] is not None and entry['sequence'] <= state['checkpoint']: fail('stale_context','The source precedes the confirmed checkpoint.')
                if state['mode']=='live':
                    _, latest = feed_info(sid)
                    if entry['sequence'] is None or entry['sequence'] != latest or not feed_point(handler, sid, actor, latest):
                        fail('stale_context','Live listening requires the current available feed item.')
                eligible=[]
                for q in state['queue']:
                    try: eligible.append(resolve(handler,sid,actor,q))
                    except Phase10Error: pass
                state['queue']=[q for q in eligible if state['mode'] != 'live' or q['sequence'] == entry['sequence']]
                if any(q['translationRequestId']==entry['translationRequestId'] or q['ref']==entry['ref'] or (entry['sequence'] is not None and q.get('sequence')==entry['sequence']) for q in state['queue']): fail('already_queued','Source already queued.')
                proposed=state['queue']+[entry]
                spans=[q['ref'] for q in proposed if isinstance(q.get('ref'),dict) and 'startMs' in q['ref'] and 'endMs' in q['ref']]
                # Sum durations conservatively; never combine unrelated capture clocks.
                span=sum(max(0,ref['endMs']-ref['startMs']) for ref in spans)
                if len(proposed)>MAX_SEGMENTS or span>MAX_SPAN_MS:
                    state['overflow']=True
                else: state['queue']=proposed
            elif action=='choose':
                if body['mode'] not in ('catch_up','live','text_only'): fail('invalid_request','Choose catch_up, live, or text_only.',422)
                state['mode']=body['mode']
                if body['mode']=='live':
                    valid=[]
                    for q in state['queue']:
                        try: valid.append(resolve(handler,sid,actor,q))
                        except Phase10Error: pass
                    ordered=[q for q in valid if q['sequence'] is not None]
                    _, feed_latest=feed_info(sid)
                    latest=next((q for q in ordered if q['sequence']==feed_latest),None) if feed_point(handler,sid,actor,feed_latest) else None
                    state['checkpoint']=max(state['checkpoint'],latest['sequence']-1) if latest else state['checkpoint']
                    state['queue']=[latest] if latest else []
                    state['overflow']=False
            elif action=='pause': state['mode']='paused'
            elif action=='reconnect': state['mode']='awaiting_choice'
            elif action=='preferences':
                pref=body['preferences']
                if not isinstance(pref,dict) or set(pref)!={'pace','textOnly'} or isinstance(pref['pace'],bool) or not isinstance(pref['pace'],(float,int)) or not 0.75<=pref['pace']<=1.5 or type(pref['textOnly']) is not bool: fail('invalid_request','Invalid listening preferences.',422)
                state['preferences']=pref
            elif action=='advance':
                if state['mode'] not in ('catch_up','live','text_only'): fail('choice_required','Choose a listening mode first.')
                view=projection(handler,sid,actor,state)
                if not view['queue'] or view['queue'][0]['translationRequestId']!=body['translationRequestId']: fail('out_of_order','Confirm the first eligible item.')
                first=view['queue'][0]; gaps=view['gaps']
                if state['mode']=='live' and (first['sequence'] != view['feedLatest'] or not view['latestAvailableSource']):
                    fail('stale_context','A newer source is available; choose or enqueue current work.')
                if first['sequence'] is None or gaps['expired'] or gaps['invalidated'] or gaps['overflow'] or any(s<first['sequence'] for s in gaps['missingSequences']): fail('coverage_gap','Choose recovery or live before advancing.')
                state['checkpoint']=first['sequence']
                state['queue']=[q for q in state['queue'] if q['translationRequestId']!=first['translationRequestId']]
            state['generation']+=1
            ack={'requestId':body['requestId'],'action':action,'generation':state['generation'],'overflow':state['overflow']}
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET revision=excluded.revision,data=excluded.data',(KIND,oid,sid,actor['owner'],state['generation'],canonical(state),store.now()))
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',(RECEIPT,rid,sid,actor['owner'],canonical({'fingerprint':fingerprint,'ack':ack}),store.now()))
            db.commit()
            return 200, {'receipt':ack}



