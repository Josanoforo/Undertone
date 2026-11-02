"""Private, source-bound viewer speech segments; no audio or provider calls retained."""
import base64, binascii, hashlib, json
from . import asr, store
from .phase10_common import Context, Phase10Error
from . import phase12_jobs


def recover_interrupted():
    """Startup only: never re-run audio from an interrupted process."""
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute("SELECT id,data FROM objects WHERE kind='w15audio'").fetchall():
            value=json.loads(row['data'])
            if value.get('state')=='running':
                value.update(state='unknown', text=None, engine=None, generation=value['generation']+1)
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w15audio' AND id=?",(json.dumps(value,ensure_ascii=False),row['id']))
        for row in db.execute("SELECT id,data FROM objects WHERE kind='w15audiosession'").fetchall():
            value=json.loads(row['data'])
            if value.get('pending'):
                if value['state']=='canceled': value['pending']=None
                else: value.update(state='unknown',pending=None,generation=value['generation']+1)
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w15audiosession' AND id=?",(json.dumps(value,ensure_ascii=False),row['id']))
        db.commit()


def fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def question_id(ident, generation):
    return hashlib.sha256(('w15-question\0'+ident+'\0'+str(generation)).encode()).hexdigest()


def project(handler, sid, actor, ident):
    Context(handler, sid, actor).check_actor()
    segment = store.get('w15audio', ident, sid)
    if not segment or segment['actor'] != actor['owner'] or segment['credential'] != store.digest(handler._auth_token):
        fail('not_found', 'Audio segment unavailable.', 404)
    if segment['state'] != 'canceled':
        Context(handler, sid, actor).resolve([segment['ref']])
    return {k:segment[k] for k in ('id','requestId','ref','language','state','generation','text','engine')}


def handle(handler, sid, actor, method, parts):
    if actor['role'] != 'viewer':
        fail('forbidden', 'Viewer capability required for private speech.', 403)
    ctx = Context(handler, sid, actor); ctx.check_actor()
    if parts and parts[0]=='audio-sessions':
        return session_handle(handler,sid,actor,method,parts,ctx)
    if len(parts)==3 and parts[:2]==['audio-segments','by-request'] and method=='GET':
        request_id=parts[2]
        if not phase12_jobs.valid_id(request_id): fail('invalid_request','Invalid request ID.',422)
        ident=hashlib.sha256((sid+'\0'+actor['owner']+'\0'+request_id).encode()).hexdigest()
        with store.LOCK:
            segment=store.get('w15audio',ident,sid)
            if not segment or segment['actor']!=actor['owner'] or segment['credential']!=store.digest(handler._auth_token):
                return 200, {'segment':None,'state':'unknown'}
            return 200, {'segment':project(handler,sid,actor,ident),'state':'found'}
    if parts == ['audio-segments'] and method == 'POST':
        b = handler.body()
        if not isinstance(b, dict) or set(b) != {'requestId','ref','language','mimeType','audioBase64'} or not phase12_jobs.valid_id(b['requestId']) or b['language'] not in ('en','es') or b['mimeType'] not in asr.MIMES or not isinstance(b['audioBase64'],str) or len(b['audioBase64']) > ((asr.MAX_BYTES+2)//3)*4:
            fail('invalid_request', 'Invalid audio segment.', 422)
        try: raw = base64.b64decode(b['audioBase64'], validate=True); asr._check_audio(raw,b['mimeType'])
        except (binascii.Error, ValueError, asr.ASRUnavailable): fail('invalid_request','Invalid audio segment.',422)
        ctx.resolve([b['ref']])
        fingerprint=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        ident=hashlib.sha256((sid+'\0'+actor['owner']+'\0'+b['requestId']).encode()).hexdigest()
        with store.LOCK:
            old=store.get('w15audio',ident,sid)
            if old:
                if old['fingerprint'] != fingerprint: fail('request_conflict','Request ID is already bound to another segment.')
                return 200, {'segment':project(handler,sid,actor,ident)}
            segment={'actor':actor['owner'],'credential':store.digest(handler._auth_token),'requestId':b['requestId'],'fingerprint':fingerprint,'ref':b['ref'],'language':b['language'],'state':'running','generation':1,'text':None,'engine':None}
            store.put('w15audio',sid,segment,owner=actor['owner'],oid=ident)
        from .http import _asr_slots
        acquired=_asr_slots.acquire(blocking=False)
        try:
            if not acquired: raise asr.ASRUnavailable('ASR is busy.')
            result=asr.transcribe(raw,b['mimeType'],b['language'])
            text=result['text']; engine=result['provider']; state='complete'
        except Exception:
            text=None;engine=None;state='failed'
        finally:
            if acquired: _asr_slots.release()
        with store.LOCK:
            segment=store.get('w15audio',ident,sid)
            if segment and segment['state']=='running' and segment['generation']==1:
                try: ctx.resolve([segment['ref']])
                except Phase10Error: state='canceled';text=None;engine=None
                segment.update(state=state,text=text,engine=engine);store.save('w15audio',segment)
            return 200, {'segment':project(handler,sid,actor,ident)}
    if len(parts) in (2,3) and parts[0]=='audio-segments':
        ident=parts[1]
        with store.LOCK:
            segment=store.get('w15audio',ident,sid)
            if not segment or segment['actor']!=actor['owner'] or segment['credential']!=store.digest(handler._auth_token): fail('not_found','Audio segment unavailable.',404)
            if not (len(parts)==3 and parts[2]=='cancel' and method=='POST'): project(handler,sid,actor,ident)
            if len(parts)==2 and method=='GET': return 200,{'segment':project(handler,sid,actor,ident)}
            if len(parts)==3 and parts[2]=='share-question' and method=='POST':
                b=handler.body()
                if not isinstance(b,dict) or set(b)!={'generation','consent'} or b['consent'] is not True or type(b['generation']) is not int or b['generation']!=segment['generation'] or segment['state']!='complete' or not isinstance(segment['text'],str) or not 1<=len(segment['text'].strip())<=4000:
                    fail('invalid_request','A current completed segment and explicit consent are required.',422)
                row=ctx.resolve([segment['ref']])[0]
                if row['source'].get('p10Provenance',{}).get('type')!='received_asr_v1': fail('stale_context','An authorized speech source is required.')
                qid=question_id(ident,segment['generation'])
                question=store.get('w13question',qid,sid)
                if not question:
                    store.put('w13question',sid,{'text':segment['text'].strip(),'language':segment['language'],'status':'shared','answer':None,'ref':segment['ref']},owner=actor['owner'],oid=qid)
                    question=store.get('w13question',qid,sid)
                from . import waves13_exchange
                if not waves13_exchange.eligible(handler,sid,actor,question): fail('stale_context','Question unavailable.')
                handler._w13_question_binding=(sid,dict(actor),[(qid,question['_revision'])])
                return 200,{'question':question}
            if len(parts)==3 and parts[2] in ('cancel','correct') and method=='POST':
                b=handler.body()
                expected={'generation'} if parts[2]=='cancel' else {'generation','text'}
                if not isinstance(b,dict) or set(b)!=expected or type(b['generation']) is not int or b['generation']!=segment['generation']:
                    fail('generation_conflict','Segment generation changed.')
                if parts[2]=='correct':
                    if segment['state']!='complete' or not isinstance(b['text'],str) or not 1<=len(b['text'].strip())<=4000:fail('invalid_request','Completed segment and corrected text required.',422)
                    segment['text']=b['text'].strip()
                else: segment.update(state='canceled',text=None,engine=None)
                old_generation=segment['generation'];segment['generation']+=1
                # Invalidate any shared question and derived delivery atomically with the correction.
                qid=question_id(ident,old_generation)
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row=db.execute("SELECT revision,data FROM objects WHERE kind='w13question' AND id=? AND session_id=? AND owner_id=?",(qid,sid,actor['owner'])).fetchone()
                    if row:
                        question=json.loads(row['data']);question.update(text=None,answer=None,status='withdrawn')
                        db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w13question' AND id=?",(json.dumps(question,ensure_ascii=False),qid))
                        db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE source_id=? AND state IN ('queued','running','complete')",(qid,))
                    segment.pop('_revision',None)
                    db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w15audio' AND id=? AND session_id=?",(json.dumps(segment,ensure_ascii=False),ident,sid))
                    db.commit()
                return 200,{'segment':project(handler,sid,actor,ident)}
    fail('not_found','Audio route unavailable.',404)


def session_handle(handler,sid,actor,method,parts,ctx):
    """Ordered single-flight session; no audio retained and no implicit retry."""
    credential=store.digest(handler._auth_token)
    def projection(obj):
        if obj['state']!='canceled': ctx.resolve([obj['ref']])
        return {k:obj[k] for k in ('id','requestId','ref','sourceLanguage','targetLanguage','state','generation','confirmedSequence','pending')}
    def get(ident):
        obj=store.get('w15audiosession',ident,sid)
        if not obj or obj['actor']!=actor['owner'] or obj['credential']!=credential: fail('not_found','Audio session unavailable.',404)
        ctx.check_actor();return obj
    if parts==['audio-sessions'] and method=='POST':
        b=handler.body()
        if not isinstance(b,dict) or set(b)!={'requestId','ref','sourceLanguage','targetLanguage','consent'} or not phase12_jobs.valid_id(b['requestId']) or b['sourceLanguage'] not in ('en','es') or b['targetLanguage'] not in ('en','es') or b['consent'] is not True: fail('invalid_request','Explicit consent and valid languages are required.',422)
        ctx.resolve([b['ref']]);fingerprint=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        ident=hashlib.sha256(('session\0'+sid+'\0'+actor['owner']+'\0'+b['requestId']).encode()).hexdigest()
        with store.LOCK:
            old=store.get('w15audiosession',ident,sid)
            if old:
                old=get(ident)
                if old['fingerprint']!=fingerprint: fail('request_conflict','Request ID is already bound to another session.')
                return 200,{'audioSession':projection(old)}
            obj={'actor':actor['owner'],'credential':credential,'requestId':b['requestId'],'fingerprint':fingerprint,'ref':b['ref'],'sourceLanguage':b['sourceLanguage'],'targetLanguage':b['targetLanguage'],'state':'active','generation':1,'confirmedSequence':0,'pending':None,'receipts':{}}
            obj=store.put('w15audiosession',sid,obj,owner=actor['owner'],oid=ident)
            return 200,{'audioSession':projection(obj)}
    if len(parts)<2: fail('not_found','Audio session unavailable.',404)
    ident=parts[1]
    with store.LOCK:
        obj=get(ident)
        if len(parts)==5 and parts[2]=='chunks' and parts[4]=='receipt' and method in ('GET','POST'):
            request_id=parts[3]
            if not phase12_jobs.valid_id(request_id): fail('invalid_request','Invalid request ID.',422)
            if method=='POST':
                body=handler.body()
                if body != {'cancel':True}: fail('invalid_request','Explicit cancellation is required.',422)
            saved=obj['receipts'].get(request_id)
            if not saved or not saved['receipt'].get('segmentId'):
                return 200,{'receipt':None,'state':'unknown'}
            segment_id=saved['receipt']['segmentId']
            segment=store.get('w15audio',segment_id,sid)
            if not segment or segment['actor']!=actor['owner'] or segment['credential']!=credential:
                return 200,{'receipt':None,'state':'unknown'}
            if method=='POST' and segment['state']!='canceled':
                class CancelProxy:
                    def body(self): return {'generation':segment['generation']}
                    def __getattr__(self,name): return getattr(handler,name)
                handle(CancelProxy(),sid,actor,'POST',['audio-segments',segment_id,'cancel'])
                segment=store.get('w15audio',segment_id,sid)
            return 200,{'receipt':{'segmentId':segment_id,'state':segment['state'],'generation':segment['generation']},'state':'found'}
        if len(parts)==2 and method=='GET':return 200,{'audioSession':projection(obj)}
        if len(parts)==3 and parts[2]=='cancel' and method=='POST':
            b=handler.body()
            if not isinstance(b,dict) or set(b)!={'generation'} or type(b['generation']) is not int or b['generation']!=obj['generation']:fail('generation_conflict','Audio session generation changed.')
            obj.update(state='canceled',generation=obj['generation']+1);store.save('w15audiosession',obj)
            return 200,{'audioSession':projection(obj)}
        if len(parts)!=3 or parts[2]!='chunks' or method!='POST':fail('not_found','Audio session route unavailable.',404)
        b=handler.body()
        if not isinstance(b,dict) or set(b)!={'requestId','generation','sequence','mimeType','audioBase64'} or not phase12_jobs.valid_id(b['requestId']) or type(b['generation']) is not int or type(b['sequence']) is not int:fail('invalid_request','Invalid audio chunk.',422)
        digest=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest();old=obj['receipts'].get(b['requestId'])
        if old:
            if old['digest']!=digest:fail('request_conflict','Request ID is already bound to another chunk.')
            return 200,{'audioSession':projection(obj),'receipt':old['receipt']}
        if obj['state']!='active' or b['generation']!=obj['generation']:fail('generation_conflict','Audio session is no longer active.')
        ctx.resolve([obj['ref']])
        if obj['pending'] is not None:fail('audio_busy','One chunk is already pending.')
        if b['sequence']!=obj['confirmedSequence']+1 or b['sequence']>128:fail('sequence_conflict','Expected the next sequence within session capacity.')
        obj['pending']={'requestId':b['requestId'],'sequence':b['sequence']};store.save('w15audiosession',obj)
    class Proxy:
        def __init__(self, original, body):self.original=original;self.value=body
        def body(self):return self.value
        def __getattr__(self,name):return getattr(self.original,name)
    segment_request={'requestId':hashlib.sha256((ident+'\0'+b['requestId']).encode()).hexdigest(),'ref':obj['ref'],'language':obj['sourceLanguage'],'mimeType':b['mimeType'],'audioBase64':b['audioBase64']}
    try:
        _,result=handle(Proxy(handler,segment_request),sid,actor,'POST',['audio-segments']);segment=result['segment']
    except Exception:
        with store.LOCK:
            current=get(ident)
            if current.get('pending')==obj['pending']:
                current.update(state='unknown',pending=None,generation=current['generation']+1);store.save('w15audiosession',current)
        raise
    with store.LOCK:
        current=get(ident)
        if current['state']!='active' or current['generation']!=b['generation']:
            if segment['state'] not in ('canceled','unknown'):
                handle(Proxy(handler,{'generation':segment['generation']}),sid,actor,'POST',['audio-segments',segment['id'],'cancel'])
            receipt={'sequence':b['sequence'],'state':'canceled'}
            current['pending']=None;current['receipts'][b['requestId']]={'digest':digest,'receipt':receipt};store.save('w15audiosession',current)
            return 200,{'audioSession':projection(current),'receipt':receipt}
        ctx.resolve([current['ref']])
        receipt={'sequence':b['sequence'],'segmentId':segment['id'],'state':segment['state']}
        if segment['state']=='complete':current['confirmedSequence']=b['sequence']
        else:current['state']='unknown';current['generation']+=1
        current['pending']=None;current['receipts'][b['requestId']]={'digest':digest,'receipt':receipt};store.save('w15audiosession',current)
        return 200,{'audioSession':projection(current),'receipt':receipt}
