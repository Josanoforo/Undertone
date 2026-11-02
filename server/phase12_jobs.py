"""Phase 12 source-bound translation and user-started local speech jobs."""
import hashlib, json, os, re, threading, time, uuid
from . import store, lifecycle, admission, phase10_timeline, phase12_translation, phase12_tts, phase12_sources
from . import waves17_terminology
from . import phase10_common
from .phase10_common import Phase10Error, KnownUnavailable, parse_ref

MAX_PENDING=16
MAX_RECEIPTS=4096
MAX_SPEECH_CACHE=64*1024*1024
PROCESS_DOMAIN=uuid.uuid4().hex
_worker_lock=threading.Lock()
_worker_active=False
_initialized=False

def error(code, message, status=409): raise Phase10Error(code,message,status)
def stamp(): return {'utc':store.now(),'monotonicMs':round(time.monotonic()*1000,2),'domain':PROCESS_DOMAIN}
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def valid_id(v): return isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',v))

def sapi_revision():
    # Bind reuse and queued work to both wrapper and the actual SAPI implementation.
    from pathlib import Path
    root=Path(__file__).parent
    h=hashlib.sha256()
    for name in ('phase12_tts.py','phase12_sapi.ps1'):
        h.update(name.encode('ascii'));h.update((root/name).read_bytes())
    return h.hexdigest()

def capture_time_metadata(source):
    provenance=source.get('captureTimeProvenance')
    if provenance not in ('client_reported','receipt_fallback_recording_unknown','recording_time_unverified'):
        return {'receivedAtISO':None,'captureTimeProvenance':'recording_time_unverified'}
    received=source.get('receivedAtISO')
    if not isinstance(received,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',received):received=None
    return {'receivedAtISO':received,'captureTimeProvenance':provenance}

def provider_configured():
    provider=phase12_translation.provider
    name=provider.provider_name()
    if name=='ollama':return bool(provider.MODEL and provider._local_endpoint())
    if name=='claude':return bool(os.environ.get('ANTHROPIC_API_KEY'))
    return False

def init():
    global _initialized
    with _worker_lock:
        if _initialized:return
        with store.LOCK,store.connect() as db:
            # Process restart cannot determine whether a dispatched provider call completed.
            db.execute("UPDATE phase12_jobs SET state='unknown',result=NULL,media=NULL WHERE state IN ('queued','running')")
        _initialized=True

def rights(row):
    from .http import expired
    with store.connect() as db:
        c=db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?',(row['credential_hash'],)).fetchone()
    if not c or (c['role'],c['session_id'],c['owner_id'])!=(row['role'],row['session_id'],row['actor_id']):error('stale_context','Capability unavailable.')
    session=store.get('session',row['session_id'])
    if not session or not lifecycle.active(session):error('stale_context','Session unavailable.')
    raw=json.loads(row['ref'])
    if isinstance(raw,dict) and 'type' in raw:return phase12_sources.resolve(row,phase12_sources.valid_selection(raw))
    ref=parse_ref(raw)
    source=store.get('source',ref['sourceId'],row['session_id'])
    moment=store.get('p10moment',ref['momentId'],row['session_id'])
    if (not source or source.get('_revision')!=ref['sourceRevision'] or source.get('status')!='active' or expired(source)
        or (row['role']!='creator' and not source.get('audienceVisible',False)) or not moment or moment.get('ref')!=ref):
        error('stale_context','The source is unavailable or changed.')
    proof=source.get('p10Provenance',{})
    if proof.get('type')!='received_asr_v1' or proof.get('sessionId')!=row['session_id']:
        error('stale_context','An authorized ASR source is required.')
    # Rebuild the exact interval from immutable ASR segment evidence, including correction semantics.
    try:
        rebuilt=phase10_timeline.build_moments(source,[{'startMs':ref['startMs'],'endMs':ref['endMs'],'kind':moment.get('kind')}])[0]
    except (Phase10Error,KeyError,TypeError): error('stale_context','Segment alignment unavailable.')
    if rebuilt['ref']!=ref or rebuilt['text']!=moment.get('text') or rebuilt['alignment']!=moment.get('alignment'):
        error('stale_context','Segment alignment changed.')
    return source,moment,ref

def fetch(sid,actor,rid):
    with store.connect() as db: return db.execute('SELECT * FROM phase12_jobs WHERE session_id=? AND actor_id=? AND request_id=?',(sid,actor,rid)).fetchone()

def view(row):
    obj={'requestId':row['request_id'],'kind':row['kind'],'state':row['state'],'transport':row['transport'],
         'timing':json.loads(row['timing']),'providerCost':('unestablished' if (row['transport'].startswith('hosted_') or (row['kind']=='speech' and json.loads(row['payload']).get('engine')=='elevenlabs')) else ('unestablished' if row['kind']=='translation' and row['transport']!='local_user_correction' else 'zero_provider_requests'))}
    if row['kind']=='speech':
        payload=json.loads(row['payload'])
        obj['binding']={'ref':json.loads(row['ref']),'translationRequestId':payload.get('translationRequestId'),
                        'language':payload.get('language'),'engine':payload.get('engine'),'voice':payload.get('voice')}
    if row['state']=='complete' and row['result']:
        obj['result']=json.loads(row['result'])
        if row['kind']=='translation':
            try: waves17_terminology.guard(row)
            except Phase10Error as exc:
                if exc.code != 'stale_terminology': raise
                obj['superseded']=True
        ref=json.loads(row['ref'])
        if row['kind']=='translation' and 'sourceId' in ref:
            source,_,_=rights(row)
            obj['result']['sourceProvenance'].update(capture_time_metadata(source))
        if ref.get('type')=='contribution':
            source,_,_=rights(row)
            obj['result']['speaker']=source['projection']['speaker']
            obj['result']['sourceProvenance']=source['projection']
    return obj

def check_job(handler, sid, actor, rid, expected=None):
    row=fetch(sid,actor['owner'],rid)
    if not row or row['credential_hash']!=store.digest(handler._auth_token): error('not_found','Request unavailable.',404)
    if json.loads(row['ref']).get('type')=='contribution':
        import hmac
        from . import phase11
        with store.connect() as db: activity=phase11.load(db,json.loads(row['ref'])['activityId'])
        supplied=handler.headers.get('X-Activity-Owner','')
        if not activity or not supplied or not hmac.compare_digest(store.digest(supplied),activity['_owner_hash']):error('unauthorized','Activity owner capability required.',401)
    if row['state'] in ('queued','running','complete'):
        rights(row)
    if row['kind']=='speech' and row['state'] in ('queued','running','complete'):
        parent=fetch(sid,actor['owner'],json.loads(row['payload'])['translationRequestId'])
        if not parent: error('stale_context','Translation unavailable.')
        rights(parent)
        from . import waves15_translation_review
        waves15_translation_review.check_speech_parent(parent)
        waves17_terminology.guard(parent)
    if row['kind']=='translation' and row['transport']=='local_user_correction' and row['state']=='complete':
        from . import waves15_translation_review
        waves15_translation_review.check_lineage(row)
    if expected and row['state']!=expected:error('stale_context','Request is no longer available.')
    return row

def terminology_reference(handler, sid, actor, rid):
    """Project an authorized live translation's exact source and term binding.

    Caller holds store.LOCK through the final response and compares a fresh
    projection before sending. This is metadata, never authority to generate.
    """
    row = check_job(handler, sid, actor, rid)
    if row['kind'] != 'translation' or row['state'] not in ('queued', 'running'):
        error('stale_context', 'Translation is no longer queued.')
    rights(row)
    try:
        payload = json.loads(row['payload'])
    except (TypeError, ValueError):
        error('stale_context', 'Terminology binding unavailable.')
    if not isinstance(payload, dict):
        error('stale_context', 'Terminology binding unavailable.')
    bound = payload.get('terminologySnapshot')
    if (not isinstance(bound, dict) or type(bound.get('revision')) is not int
            or bound['revision'] < 1 or not isinstance(bound.get('document'), dict)):
        error('stale_context', 'Terminology binding unavailable.')
    try:
        waves17_terminology.validate(bound['document'])
    except Phase10Error:
        error('stale_context', 'Terminology binding unavailable.')
    # A stale binding can still cite separately revocable context.  Source
    # rights alone do not authorize exposing the historical binding metadata.
    waves17_terminology.check_refs(sid, actor, row['credential_hash'], bound['document'])
    return {'requestId': rid, 'state': row['state'], 'source': json.loads(row['ref']),
            'sourceLanguage': payload.get('sourceLanguage'),
            'targetLanguage': payload.get('targetLanguage'),
            'terminologyRevision': bound.get('revision'),
            'terminologyDigest': hashlib.sha256(canonical(bound).encode('utf-8')).hexdigest()}

def final_guard(handler):
    sid,actor,rid,expected=handler._p12_binding
    row=check_job(handler,sid,actor,rid,expected)
    if row['kind']=='translation' and row['state']=='complete':
        try: waves17_terminology.guard(row)
        except Phase10Error as exc:
            if exc.code != 'stale_terminology': raise
    if row['kind']=='speech' and row['state']=='complete':
        parent=fetch(sid,actor['owner'],json.loads(row['payload'])['translationRequestId'])
        if not parent or parent['state']!='complete':error('stale_context','Translation unavailable.')
        rights(parent)
        from . import waves15_translation_review
        waves15_translation_review.check_speech_parent(parent)
        waves17_terminology.guard(parent)
        # Indexed ASR speech is an impact target. Recheck its current target
        # and source under the caller's final-send lock, in addition to the
        # ordinary job, credential, parent and terminology checks above.
        ref=json.loads(row['ref'])
        if isinstance(ref,dict) and 'sourceId' in ref and 'sourceRevision' in ref:
            from . import waves21_impact_runtime
            ctx=phase10_common.Context(handler,sid,actor)
            waves21_impact_runtime.guard_target(ctx,ref['sourceId'],ref['sourceRevision'],
                                                'speech',str(row['seq']),ref['sourceRevision'])
    return row

def start():
    global _worker_active
    init()
    with _worker_lock:
        if _worker_active:return
        _worker_active=True
        threading.Thread(target=run,daemon=True,name='phase12-queue').start()

def run():
    global _worker_active
    try:
        while True:
            with store.LOCK,store.connect() as db:
                row=db.execute("SELECT * FROM phase12_jobs WHERE state='queued' ORDER BY seq LIMIT 1").fetchone()
                if not row:break
                try: source,moment,ref=rights(row)
                except Phase10Error:
                    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE seq=?",(row['seq'],));continue
                timing=json.loads(row['timing']);timing['start']=stamp()
                db.execute("UPDATE phase12_jobs SET state='running',timing=? WHERE seq=? AND state='queued'",(canonical(timing),row['seq']))
            payload=json.loads(row['payload']); transport='not_started'; data=None; result=None
            try:
                if row['kind']=='translation':
                    with admission.lease(row['session_id']):
                        with store.LOCK:
                            current=fetch(row['session_id'],row['actor_id'],row['request_id'])
                            if not current or current['state']!='running':continue
                            source,moment,ref=rights(current)
                        with admission.operation(row['session_id']):
                            with store.LOCK,store.connect() as db:
                                current=fetch(row['session_id'],row['actor_id'],row['request_id'])
                                if not current or current['state']!='running':continue
                                rights(current)
                                waves17_terminology.guard(current)
                                db.execute("UPDATE phase12_jobs SET transport='reserved' WHERE seq=? AND state='running'",(row['seq'],))
                            transport='reserved'
                            args=(moment['text'],payload['sourceLanguage'],payload['targetLanguage'],payload['glossary'])
                            bound=payload.get('terminologySnapshot')
                            out=phase12_translation.translate(*args, terminology=bound['document']) if bound else phase12_translation.translate(*args)
                    result={'original':moment['text'],'translation':out['text'],'uncertainty':out['uncertainty'],
                            'sourceLanguage':payload['sourceLanguage'],'targetLanguage':payload['targetLanguage'],
                            'ref':ref,'alignment':moment['alignment'],'captureRunId':moment.get('captureRunId'),
                            'speaker':None,'sourceProvenance':source.get('projection') or {'captureId':source.get('captureId'),'chunkId':source.get('chunkId'),'offsetSeconds':source.get('offsetSeconds'),'capturedAtISO':source.get('capturedAtISO'),'asrTiming':source.get('asrTiming'),**capture_time_metadata(source)},'provider':out['provider'],'model':out['model'],'translationVersion':'p12-v1'}
                    if payload.get('terminologySnapshot'):
                        result['terminology']=payload['terminologySnapshot']
                    transport='completed_cost_unestablished'
                else:
                    with store.LOCK:
                        parent=fetch(row['session_id'],row['actor_id'],payload['translationRequestId'])
                        if not parent or parent['state']!='complete':raise Phase10Error('stale_context','Translation unavailable.',409)
                        rights(parent)
                        from . import waves15_translation_review
                        waves15_translation_review.check_speech_parent(parent)
                        waves17_terminology.guard(parent)
                        text=json.loads(parent['result'])['translation']
                    if payload.get('engine') == 'elevenlabs':
                        from . import waves17_hosted_facade as hosted
                        from . import waves17_tts_elevenlabs as adapter
                        try: account,hosted_transport,amount=hosted.current(len(text))
                        except ValueError: raise KnownUnavailable('Hosted configuration unavailable')
                        if any(payload.get(k)!=v for k,v in hosted.binding(account).items()):
                            raise Phase10Error('stale_speech_engine','Hosted configuration changed.',409)
                        def eligible():
                            try:
                                with store.LOCK:
                                    current=fetch(row['session_id'],row['actor_id'],row['request_id'])
                                    if not current or current['state']!='running': return False
                                    rights(current)
                                    parent_now=fetch(row['session_id'],row['actor_id'],payload['translationRequestId'])
                                    if not parent_now or parent_now['state']!='complete': return False
                                    rights(parent_now)
                                    waves15_translation_review.check_speech_parent(parent_now)
                                    waves17_terminology.guard(parent_now)
                                    return True
                            except Exception: return False
                        if not eligible(): raise Phase10Error('stale_context','Speech unavailable.',409)
                        with store.LOCK,store.connect() as db:
                            marked=db.execute("UPDATE phase12_jobs SET transport='hosted_attempting' WHERE seq=? AND state='running' AND transport='not_started'",(row['seq'],)).rowcount
                        if not marked: continue
                        transport='hosted_attempting'
                        # The committed marker precedes the fsynced journal. Never replay it.
                        try: hosted.reserve(hosted.claim_id(row),amount)
                        except hosted.budget.Refusal:
                            transport='hosted_refused'
                            raise KnownUnavailable('Hosted reservation unavailable')
                        with store.LOCK,store.connect() as db:
                            marked=db.execute("UPDATE phase12_jobs SET transport='hosted_reserved' WHERE seq=? AND state='running' AND transport='hosted_attempting'",(row['seq'],)).rowcount
                        transport='hosted_reserved'
                        if not marked: continue
                        if not eligible(): raise Phase10Error('stale_context','Speech unavailable.',409)
                        request=hosted.request(row,parent,text,payload)
                        data,meta=adapter.synthesize(account.config,request,hosted_transport,lambda:not eligible(),eligible)
                    elif payload.get('engine','sapi') == 'local_neural':
                        from . import waves17_tts_local
                        # A queued request is bound to the exact selected engine assets.
                        # Reject a changed deployment before starting inference.
                        language=payload['language']
                        if (payload.get('modelVersion') != waves17_tts_local.MODEL_REV or
                            payload.get('modelSha256') != waves17_tts_local.WEIGHT_SHA256.get(language) or
                            payload.get('adapterVersion') != waves17_tts_local.ADAPTER_REV or
                            language not in waves17_tts_local.VOICES or
                            payload.get('voice') != waves17_tts_local.VOICES[language][0]):
                            raise Phase10Error('stale_speech_engine','Speech engine changed while queued.',409)
                        def eligible():
                            try:
                                with store.LOCK:
                                    current=fetch(row['session_id'],row['actor_id'],row['request_id'])
                                    if not current or current['state']!='running': return False
                                    rights(current)
                                    parent_now=fetch(row['session_id'],row['actor_id'],payload['translationRequestId'])
                                    if not parent_now or parent_now['state']!='complete': return False
                                    rights(parent_now)
                                    waves15_translation_review.check_speech_parent(parent_now)
                                    waves17_terminology.guard(parent_now)
                                    return True
                            except Phase10Error: return False
                        data,meta=waves17_tts_local.synthesize(text,payload['language'],payload.get('voice'),eligible=eligible,speed=payload.get('speed',1.0))
                    else:
                        if payload.get('adapterVersion') != sapi_revision():
                            raise Phase10Error('stale_speech_engine','Speech engine changed while queued.',409)
                        data,meta=phase12_tts.synthesize(text,payload['language'])
                    result={'label':'Generic synthetic voice','language':payload['language'],'audio':meta,'translationRequestId':payload['translationRequestId']}
                    bound=waves17_terminology.guard(parent)
                    if bound: result['terminology']={'revision':bound['revision']}
                    transport='hosted_response_unknown_cost' if payload.get('engine')=='elevenlabs' else 'local_no_provider'
                with store.LOCK,store.connect() as db:
                    current=fetch(row['session_id'],row['actor_id'],row['request_id'])
                    if not current or current['state']!='running':continue
                    _,_,current_ref=rights(current)
                    if row['kind']=='translation': waves17_terminology.guard(current)
                    if row['kind']=='speech':
                        parent=fetch(row['session_id'],row['actor_id'],payload['translationRequestId'])
                        if not parent or parent['state']!='complete':raise Phase10Error('stale_context','Translation unavailable.',409)
                        rights(parent)
                        from . import waves15_translation_review
                        waves15_translation_review.check_speech_parent(parent)
                        waves17_terminology.guard(parent)
                        if isinstance(current_ref,dict) and 'sourceId' in current_ref and 'sourceRevision' in current_ref:
                            from . import waves21_impact_runtime
                            db.execute('BEGIN IMMEDIATE')
                            try:
                                waves21_impact_runtime.guard_speech_completion(db,current['session_id'],current_ref['sourceId'],current_ref['sourceRevision'],current['seq'],current['fingerprint'],current['credential_hash'])
                            except waves21_impact_runtime.impact.ImpactError as exc:
                                raise Phase10Error('stale_context','Speech source changed.',409) from exc
                    timing=json.loads(current['timing']);timing['end']=stamp()
                    db.execute("UPDATE phase12_jobs SET state='complete',result=?,media=?,timing=?,transport=? WHERE seq=? AND state='running'",(canonical(result),data,canonical(timing),transport,row['seq']))
                    while db.execute("SELECT COALESCE(SUM(length(media)),0) FROM phase12_jobs WHERE (kind='speech' AND state='complete') OR (kind='w20_speech' AND state='w20_complete')").fetchone()[0]>MAX_SPEECH_CACHE:
                        victim=db.execute("SELECT seq FROM phase12_jobs WHERE kind='speech' AND state='complete' AND media IS NOT NULL ORDER BY seq LIMIT 1").fetchone()
                        if not victim:break
                        db.execute("UPDATE phase12_jobs SET state='expired',result=NULL,media=NULL WHERE seq=?",(victim['seq'],))
                    if db.in_transaction:db.commit()
            except Exception as exc:
                with store.LOCK,store.connect() as db:
                    current=fetch(row['session_id'],row['actor_id'],row['request_id'])
                    if not current or current['state']!='running':continue
                    timing=json.loads(current['timing']);timing['end']=stamp()
                    state='unknown' if (transport.startswith('hosted_') and transport!='hosted_refused') or (transport=='reserved' and not isinstance(exc,(Phase10Error,KnownUnavailable))) else ('canceled' if isinstance(exc,Phase10Error) else 'failed')
                    if isinstance(exc,KnownUnavailable): transport='hosted_refused' if transport=='hosted_refused' else 'not_dispatched'
                    db.execute('UPDATE phase12_jobs SET state=?,result=NULL,media=NULL,timing=?,transport=? WHERE seq=? AND state=\'running\'',(state,canonical(timing),transport,row['seq']))
    finally:
        with _worker_lock:_worker_active=False
        # A submit can race with the worker going idle.
        with store.connect() as db: pending=db.execute("SELECT 1 FROM phase12_jobs WHERE state='queued' LIMIT 1").fetchone()
        if pending:start()

def submit(handler,sid,actor,kind,body):
    init()
    if not isinstance(body,dict) or not valid_id(body.get('requestId')):error('invalid_request','Valid requestId required.',422)
    if kind=='translation':
        if set(body)-{'terminologyRevision'} not in ({'requestId','ref','sourceLanguage','targetLanguage','glossary'},{'requestId','selection','sourceLanguage','targetLanguage','glossary'}):error('invalid_request','Invalid translation fields.',422)
        if 'terminologyRevision' in body and (type(body['terminologyRevision']) is not int or body['terminologyRevision']<1): error('invalid_request','Invalid terminology revision.',422)
        ref=parse_ref(body['ref']) if 'ref' in body else phase12_sources.valid_selection(body['selection']); gloss=body['glossary']
        if ('sessionId' in ref and ref['sessionId']!=sid) or body['sourceLanguage'] not in ('en','es') or body['targetLanguage'] not in ('en','es') or body['sourceLanguage']==body['targetLanguage'] or not isinstance(gloss,list) or len(gloss)>50: error('invalid_request','Invalid translation selection.',422)
        for term in gloss:
            if not isinstance(term,dict) or set(term)!={'source','target'} or any(not isinstance(term[k],str) or not 1<=len(term[k])<=120 for k in ('source','target')):error('invalid_request','Invalid glossary.',422)
    else:
        if set(body)-{'engine','voice','speed'}!={'requestId','translationRequestId'} or not valid_id(body.get('translationRequestId')):error('invalid_request','Invalid speech fields.',422)
        if 'speed' in body:
            import math
            speed=body['speed']
            if body.get('engine')!='local_neural' or isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or not .5<=speed<=2: error('invalid_request','Invalid local speech speed.',422)
        if body.get('engine','sapi') not in ('sapi','local_neural','elevenlabs'):error('engine_unavailable','Selected speech engine is unavailable.',422)
        if 'voice' in body and (body.get('engine') not in ('local_neural','elevenlabs') or not isinstance(body['voice'],str)):error('invalid_request','Invalid voice.',422)
    fingerprint=hashlib.sha256(canonical({'kind':kind,'body':body}).encode()).hexdigest()
    with store.LOCK,store.connect() as db:
        old=fetch(sid,actor['owner'],body['requestId'])
        if old:
            old_payload=json.loads(old['payload'])
            old_bound=old_payload.get('terminologySnapshot')
            replay_fingerprint=hashlib.sha256(canonical({'kind':kind,'body':body,'terminologySnapshot':old_bound}).encode()).hexdigest() if old_bound else fingerprint
            if old['fingerprint']!=replay_fingerprint: error('request_conflict','Request ID is bound to a different payload.')
            row=check_job(handler,sid,actor,body['requestId']);handler._p12_binding=(sid,actor,body['requestId'],None);return 200,{'operation':view(row)}
        if db.execute("SELECT COUNT(*) FROM phase12_jobs").fetchone()[0]>=MAX_RECEIPTS:error('receipt_capacity','Receipt storage is full.',429)
        if db.execute("SELECT COUNT(*) FROM phase12_jobs WHERE state IN ('queued','running')").fetchone()[0]>=MAX_PENDING:error('queue_full','The queue is full.',429)
        if kind=='speech':
            parent=check_job(handler,sid,actor,body['translationRequestId'],'complete')
            if parent['kind']!='translation':error('invalid_request','A completed translation is required.',422)
            from . import waves15_translation_review
            waves15_translation_review.check_speech_parent(parent)
            waves17_terminology.guard(parent)
            ref=json.loads(parent['ref']); translated=json.loads(parent['result'])
            if len(translated['translation'])>600:error('speech_too_long','Translation exceeds speech limit.',422)
            payload={'translationRequestId':body['translationRequestId'],'language':translated['targetLanguage']}
            if body.get('engine','sapi')=='sapi':
                payload.update(engine='sapi',voice=phase12_tts.VOICES[payload['language']],adapterVersion=sapi_revision())
            if body.get('engine')=='local_neural':
                from . import waves17_tts_local
                voice=body.get('voice',waves17_tts_local.VOICES[payload['language']][0])
                if voice!=waves17_tts_local.VOICES[payload['language']][0]:error('invalid_request','Voice does not support this language.',422)
                if not waves17_tts_local.availability()['available']:error('engine_unavailable','Local neural speech is unavailable.',503)
                payload.update(engine='local_neural',voice=voice,modelVersion=waves17_tts_local.MODEL_REV,modelSha256=waves17_tts_local.WEIGHT_SHA256[payload['language']],adapterVersion=waves17_tts_local.ADAPTER_REV,speed=body.get('speed',1.0))
            if body.get('engine')=='elevenlabs':
                from . import waves17_hosted_facade as hosted
                try: account,_,_=hosted.current(len(translated['translation']))
                except ValueError: error('engine_unavailable','Hosted speech account or pricing is unavailable.',503)
                if payload['language'] not in account.config.languages or body.get('voice')!=account.config.voice_id: error('invalid_request','Explicit verified hosted voice required.',422)
                payload.update(hosted.binding(account))
        else:
            payload=dict(body)
            if 'terminologyRevision' in body:
                bound=waves17_terminology.snapshot(sid,actor,store.digest(handler._auth_token),body['terminologyRevision'])
                if len(bound['document']['terms'])+len(body['glossary'])>50: error('terminology_capacity','Combined terminology and glossary exceed 50 terms.',422)
                source_key=body['sourceLanguage']; target_key=body['targetLanguage']
                approved={t[source_key].casefold():t[target_key].casefold() for t in bound['document']['terms']}
                if len(approved)!=len(bound['document']['terms']): error('terminology_conflict','Approved source terms conflict.',422)
                if any(t['source'].casefold() in approved and t['target'].casefold()!=approved[t['source'].casefold()] for t in body['glossary']): error('terminology_conflict','Glossary conflicts with approved terminology.',422)
                payload['terminologySnapshot']=bound
                fingerprint=hashlib.sha256(canonical({'kind':kind,'body':body,'terminologySnapshot':bound}).encode()).hexdigest()
        candidate={'credential_hash':store.digest(handler._auth_token),'role':actor['role'],'session_id':sid,'actor_id':actor['owner'],'ref':canonical(ref)}
        source,moment,_=rights(candidate)
        if kind=='translation' and source.get('language') is not None and source['language']!=body['sourceLanguage']:error('language_mismatch','Language does not match the source.',409)
        if kind=='translation' and ref.get('type')=='contribution':
            import hmac
            from . import phase11
            with store.connect() as authority_db: activity=phase11.load(authority_db,ref['activityId'])
            supplied=handler.headers.get('X-Activity-Owner','')
            if not activity or not supplied or not hmac.compare_digest(store.digest(supplied),activity['_owner_hash']):error('unauthorized','Activity owner capability required.',401)
        cache_hit=None
        # A new ID cannot bypass a running or ambiguous operation on the same exact source.
        # Explicit cancellation after a dispatched call also leaves its billing outcome unresolved.
        for previous in db.execute("SELECT * FROM phase12_jobs WHERE session_id=? AND actor_id=? AND kind=?",(sid,actor['owner'],kind)).fetchall():
            earlier=json.loads(previous['payload'])
            if previous['ref']==canonical(ref) and (previous['state'] in ('queued','running','unknown') or (previous['state']=='canceled' and (previous['transport']=='reserved' or previous['transport'].startswith('hosted_')))):
                # A different, explicitly chosen local engine can proceed after
                # a terminal hosted outcome. Keep the hosted receipt/hold intact;
                # never permit another hosted attempt, same-ID retry, or a live job.
                local_after_hosted_terminal = (
                    kind=='speech' and payload.get('engine')=='local_neural'
                    and earlier.get('engine')=='elevenlabs'
                    and previous['state'] in ('unknown','canceled')
                    and previous['transport'].startswith('hosted_')
                )
                if not local_after_hosted_terminal:
                    error('operation_unresolved','A prior request for this source remains unresolved.',409)
            prior_key={k:v for k,v in earlier.items() if k!='requestId'}
            current_key={k:v for k,v in payload.items() if k!='requestId'}
            if previous['state']=='complete' and previous['ref']==canonical(ref) and prior_key==current_key:
                if kind!='speech':
                    error('request_exists','A completed request already exists for this selection; use its original ID.',409)
                # Same actor, exact capability, exact translation and asset versions only.
                # Re-check the original job and its parent, including current rights/terms.
                if previous['credential_hash']==candidate['credential_hash'] and previous['media'] and previous['result']:
                    check_job(handler,sid,actor,previous['request_id'],'complete')
                    cache_hit=previous

        timing={'request':stamp(),'queue':stamp()}
        if cache_hit is not None:
            used=db.execute("SELECT COALESCE(SUM(length(media)),0) FROM phase12_jobs WHERE (kind='speech' AND state='complete') OR (kind='w20_speech' AND state='w20_complete')").fetchone()[0]
            # Bridge jobs reserve space before doing work; a cache copy must not
            # consume that space while a bridge effect is in flight.
            bridge_pending=db.execute("SELECT COUNT(*) FROM phase12_jobs WHERE kind='w20_speech' AND state='w20_running'").fetchone()[0]
            if used+bridge_pending*8*1024*1024+len(cache_hit['media'])>MAX_SPEECH_CACHE:
                error('speech_cache_capacity','Speech cache is full; use the original request.',429)
            timing['start']=stamp(); timing['end']=stamp()
            db.execute("INSERT INTO phase12_jobs(session_id,actor_id,credential_hash,role,request_id,kind,fingerprint,payload,ref,source_id,state,result,timing,transport,media) VALUES(?,?,?,?,?,?,?,?,?,?,'complete',?,?,'local_cache',?)",(sid,actor['owner'],candidate['credential_hash'],actor['role'],body['requestId'],kind,fingerprint,canonical(payload),canonical(ref),cache_hit['source_id'],cache_hit['result'],canonical(timing),cache_hit['media']))
            row=fetch(sid,actor['owner'],body['requestId'])
            handler._p12_binding=(sid,actor,body['requestId'],'complete')
            return 200,{'operation':view(row)}
        db.execute("INSERT INTO phase12_jobs(session_id,actor_id,credential_hash,role,request_id,kind,fingerprint,payload,ref,source_id,state,timing) VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?)",(sid,actor['owner'],candidate['credential_hash'],actor['role'],body['requestId'],kind,fingerprint,canonical(payload),canonical(ref),ref.get('sourceId') or ref.get('contributionId') or ref.get('materialId') or ref.get('recapId') or ref.get('activityId') or ref.get('handoffId') or ref.get('questionId') or (source.get('id') if ref.get('type')=='speech_sentence' else None),canonical(timing)))
        row=fetch(sid,actor['owner'],body['requestId'])
    start()
    return 202,{'operation':view(row)}

def list_operations(handler,sid,actor):
    from urllib.parse import parse_qs,urlparse
    q=parse_qs(urlparse(handler.path).query,keep_blank_values=True)
    if set(q)-{'after','limit'} or any(len(v)!=1 for v in q.values()):error('invalid_query','Invalid operation query.',422)
    def integer(k,default,maxval):
        v=q.get(k,[str(default)])[0]
        if not v.isascii() or not v.isdigit() or len(v)>16 or int(v)>maxval:error('invalid_query','Invalid operation cursor.',422)
        return int(v)
    after=integer('after',0,2**53-1);limit=integer('limit',50,100)
    if not limit:error('invalid_query','Invalid operation limit.',422)
    with store.LOCK,store.connect() as db:
        rows=db.execute('SELECT * FROM phase12_jobs WHERE session_id=? AND actor_id=? AND credential_hash=? AND seq>? ORDER BY seq LIMIT 200',(sid,actor['owner'],store.digest(handler._auth_token),after)).fetchall()
        values=[];cursor=after
        for row in rows:
            cursor=row['seq']
            try:
                check_job(handler,sid,actor,row['request_id']);rights(row)
            except phase10_common.Phase10Error:continue
            payload=json.loads(row['payload']);ref=json.loads(row['ref'])
            value={'sequence':row['seq'],'requestId':row['request_id'],'kind':row['kind'],'state':row['state'],'ref':ref}
            if row['kind']=='translation':value.update(sourceLanguage=payload['sourceLanguage'],targetLanguage=payload['targetLanguage'])
            else:value.update(translationRequestId=payload['translationRequestId'],language=payload['language'],
                              engine=payload.get('engine'),voice=payload.get('voice'))
            values.append(value)
            if len(values)>=limit:break
        more=bool(db.execute('SELECT 1 FROM phase12_jobs WHERE session_id=? AND actor_id=? AND credential_hash=? AND seq>? LIMIT 1',(sid,actor['owner'],store.digest(handler._auth_token),cursor)).fetchone())
        handler._p12_list_binding=(sid,actor,[v['requestId'] for v in values])
        return 200,{'operations':values,'nextCursor':cursor,'hasMore':more}

def original_audio(handler,sid,actor,source_id):
    from .http import expired
    current=store.auth(getattr(handler,'_auth_token',''))
    if current!=actor or actor['sid']!=sid:error('stale_context','Capability unavailable.')
    session=store.get('session',sid);source=store.get('source',source_id,sid)
    if not session or not lifecycle.active(session) or not source or source.get('status')!='active' or expired(source) or (actor['role']!='creator' and not source.get('audienceVisible',False)) or source.get('p10Provenance',{}).get('type')!='received_asr_v1':error('stale_context','Original audio is unavailable.')
    with store.connect() as db:row=db.execute('SELECT mime,digest,data FROM phase12_original_audio WHERE source_id=? AND session_id=?',(source_id,sid)).fetchone()
    if not row or hashlib.sha256(row['data']).hexdigest()!=row['digest'] or row['digest']!=source.get('audioDigest'):error('stale_context','Original audio is unavailable.')
    return row['data'],row['mime']

def handle(handler,sid,actor,method,sub):
    if method != 'GET': init()
    if len(sub)==3 and sub[0]=='sources' and sub[2]=='original-audio' and method=='GET' and valid_id(sub[1]):
        with store.LOCK:
            data,mime=original_audio(handler,sid,actor,sub[1]);handler._p12_original_audio=(sid,actor,sub[1]);return 200,data,mime
    if sub and sub[0]=='collaboration':
        from . import phase12_collab_audience
        return phase12_collab_audience.handle(handler,sid,actor,method,sub[1:])
    if sub and sub[0]=='collaboration-grants':
        from . import phase12_collab_grants
        return phase12_collab_grants.handle(handler,sid,actor,method,sub[1:])
    if sub and sub[0] in ('projects','invitations'):
        from . import phase12_collaboration
        return phase12_collaboration.handle(handler,sid,actor,method,sub)
    if sub==['caption-feed'] and method=='GET':
        from . import phase12_feed
        return phase12_feed.feed(handler,sid,actor)
    if sub==['operations'] and method=='GET':return list_operations(handler,sid,actor)
    if sub==['capabilities'] and method=='GET':
        provider=phase12_translation.provider
        if provider.provider_name()=='claude':
            from . import claude_provider
            tested=claude_provider._tested
        else:tested=provider._tested if provider.provider_name()=='ollama' else False
        configured=provider_configured()
        return 200,{'translation':{'directions':['es-en','en-es'],'providerConfigured':configured,'available':False if not configured else (True if tested else None),'tested':tested},'speech':{'engine':'Windows SAPI','languages':['en','es'],'availability':'attempt_on_request','automaticPlayback':False},'queue':{'maxPending':MAX_PENDING,'workers':1}}
    if sub==['speech-options'] and method=='GET':
        from . import waves17_tts_local
        from . import waves17_hosted_facade as hosted
        return 200,{'engines':[{'id':'local_neural',**waves17_tts_local.availability()},{'id':'sapi','engine':'Windows SAPI','available':None,'reason':'attempt_on_request','languages':['en','es'],'emergency':True},hosted.options()], 'automaticFallback':False}
    if sub==['preferences']:
        if actor['role']!='viewer':error('forbidden','Viewer capability required.',403)
        if method=='PUT':error('method_not_allowed','Use POST.',405)
        if method=='POST':
            body=handler.body()
            if set(body)!={'language','showOriginal'} or body['language'] not in ('en','es') or type(body['showOriginal']) is not bool:error('invalid_request','Invalid preference.',422)
            with store.LOCK,store.connect() as db: db.execute('INSERT INTO phase12_preferences VALUES(?,?,?,?) ON CONFLICT(session_id,actor_id) DO UPDATE SET language=excluded.language,show_original=excluded.show_original',(sid,actor['owner'],body['language'],int(body['showOriginal'])))
            return 200,{'preference':body}
        if method=='GET':
            with store.connect() as db: row=db.execute('SELECT language,show_original FROM phase12_preferences WHERE session_id=? AND actor_id=?',(sid,actor['owner'])).fetchone()
            return 200,{'preference':{'language':row['language'],'showOriginal':bool(row['show_original'])} if row else None}
    if sub and sub[0]=='recaps':return phase12_sources.recaps(handler,sid,actor,method,sub[1:])
    if sub and sub[0]=='contribution-grants':return phase12_sources.grant(handler,sid,actor,method,sub[1:])
    if sub==['translations'] and method=='POST':return submit(handler,sid,actor,'translation',handler.body())
    if sub==['speech'] and method=='POST':return submit(handler,sid,actor,'speech',handler.body())
    if len(sub)==3 and sub[0]=='operations' and valid_id(sub[1]) and sub[2]=='corrections' and method=='POST':
        from . import waves15_translation_review
        return waves15_translation_review.correct(handler,sid,actor,sub[1],handler.body())
    if len(sub)>=2 and sub[0]=='operations' and valid_id(sub[1]):
        rid=sub[1]
        with store.LOCK:
            row=check_job(handler,sid,actor,rid)
            if len(sub)==2 and method=='GET':
                handler._p12_binding=(sid,actor,rid,None);return 200,{'operation':view(row)}
            if len(sub)==3 and sub[2]=='cancel' and method=='POST':
                if handler.body()!={}:error('invalid_request','Cancel body must be empty.',422)
                with store.connect() as db:db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE seq=? AND state IN ('queued','running','complete')",(row['seq'],))
                row=fetch(sid,actor['owner'],rid);return 200,{'operation':view(row)}
            if len(sub)==3 and sub[2]=='audio' and method=='GET':
                if row['kind']!='speech' or row['state']!='complete' or not row['media']:error('not_found','Audio unavailable.',404)
                parent=fetch(sid,actor['owner'],json.loads(row['payload'])['translationRequestId'])
                if not parent or parent['state']!='complete':error('stale_context','Translation unavailable.')
                rights(parent)
                from . import waves15_translation_review
                waves15_translation_review.check_speech_parent(parent)
                waves17_terminology.guard(parent)
                handler._p12_binding=(sid,actor,rid,'complete');return 200,row['media'],'audio/wav'
    error('not_found','Phase 12 route unavailable.',404)

