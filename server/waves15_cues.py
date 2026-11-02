"""Creator-reviewed, durable cues and bounded local OBS presentation."""
import hashlib, json, os, re, threading, urllib.request
from . import store, phase10_studio
from .phase10_common import Context, Phase10Error
from .obs_adapter import cue_effect

_NATIVE_LOCK = threading.Lock()

def fail(code, message, status=409):
    raise Phase10Error(code, message, status)

def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        fail('invalid_request', 'A valid operation key is required.', 422)

def eligible_material(context, sid, mid, version):
    m = store.get('p10material', mid, sid)
    if not m or m.get('status') not in ('approved', 'published') or m.get('approvedVersion') != version or m.get('currentVersion') != version:
        fail('not_eligible', 'An approved current material is required.')
    phase10_studio._guard_material(context, m)
    rows = context.resolve(m.get('refs'))
    if not rows or not all(r['source'].get('audienceVisible') for r in rows):
        fail('not_eligible', 'The material sources are no longer eligible.')
    return m

def projection(context, sid, cue):
    try:
        eligible_material(context, sid, cue['materialId'], cue['materialVersion']); eligible = True
    except Phase10Error:
        eligible = False
    return {k: cue[k] for k in ('id','materialId','materialVersion','status','_revision')} | {'eligible': eligible}

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS w15_cue_receipts (session_id TEXT NOT NULL, actor_id TEXT NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, cue_id TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(session_id,actor_id,request_key))')
    db.execute('CREATE TABLE IF NOT EXISTS w15_native_operations (session_id TEXT NOT NULL, actor_id TEXT NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, cue_id TEXT NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL, url TEXT, result TEXT, PRIMARY KEY(session_id,actor_id,request_key))')

def configuration(sid, actor):
    try:
        with open(os.environ['APP_OBS_CUE_CONFIG'], encoding='utf-8') as f: cfg = json.load(f)
        if cfg['allowedSessionId'] != sid or cfg['allowedCreatorId'] != actor['owner']:
            fail('destination_unbound', 'The local destination is not bound to this creator and session.', 403)
        if type(cfg['httpPort']) is not int or not 1 <= cfg['httpPort'] <= 65535:
            raise ValueError()
        return cfg
    except Phase10Error:
        raise
    except (OSError, KeyError, ValueError, TypeError):
        fail('transport_unavailable', 'The local OBS destination is unavailable.', 503)

def native_read(db, sid, owner, request_key):
    return db.execute('SELECT * FROM w15_native_operations WHERE session_id=? AND actor_id=? AND request_key=?', (sid, owner, request_key)).fetchone()

def native_result(row, context, sid):
    cue = store.get('w15cue', row['cue_id'], sid)
    operation = {'state': 'committed' if row['state'] == 'committed' else 'unknown', 'cueId': row['cue_id']}
    if row['state'] == 'committed':
        result = json.loads(row['result']); operation['committedRevision'] = result['revision']
        projected = projection(context, sid, cue) if cue else None
        transport = result['transport']
        if row['action'] == 'present' and (not projected or not projected['eligible'] or (store.get('p10material', cue['materialId'], sid) or {}).get('status') != 'published'):
            transport = {'state': 'suppressed'}
        return {'cue': projected, 'operation': operation, 'transport': transport}
    return {'cue': projection(context, sid, cue) if cue else None, 'operation': operation, 'transport': {'state':'unknown'}}

def handle(handler, sid, actor, method, parts):
    context = Context(handler, sid, actor)
    context.check_actor()
    if actor['role'] != 'creator': fail('forbidden', 'Only the creator can manage cues.', 403)
    if parts == ['cues'] and method == 'GET':
        return 200, {'cues':[projection(context,sid,c) for c in store.all('w15cue',sid)], 'transport':{'state':'configured' if os.environ.get('APP_OBS_CUE_CONFIG') else 'unavailable'}}
    if len(parts)==2 and parts[0]=='cue-operations' and method=='GET':
        key(parts[1])
        with store.connect() as db:
            schema(db); row = native_read(db,sid,actor['owner'],parts[1])
            old = db.execute('SELECT cue_id,revision FROM w15_cue_receipts WHERE session_id=? AND actor_id=? AND request_key=?',(sid,actor['owner'],parts[1])).fetchone()
        if row:
            result = native_result(row,context,sid); return 200, {'operation': result['operation'], 'cue': result['cue'], 'transport': result['transport']}
        if not old: return 200, {'operation':{'state':'unknown'}}
        cue=store.get('w15cue',old['cue_id'],sid)
        return 200, {'operation':{'state':'committed','cueId':old['cue_id'],'committedRevision':old['revision'],'cue':projection(context,sid,cue) if cue else None}}
    creating=parts==['cues'] and method=='POST'
    action=len(parts)==3 and parts[0]=='cues' and parts[2]=='action' and method=='POST'
    if not (creating or action): fail('not_found','Cue route unavailable.',404)
    body=handler.body(); expected={'materialId','materialVersion','idempotencyKey'} if creating else {'action','revision','idempotencyKey'}
    if not isinstance(body,dict) or set(body)!=expected: fail('invalid_request','Invalid cue request.',422)
    key(body['idempotencyKey'])
    if creating and (not isinstance(body['materialId'],str) or type(body['materialVersion']) is not int or body['materialVersion']<1): fail('invalid_request','A material and version are required.',422)
    if action and (body['action'] not in ('present','defer','withdraw') or type(body['revision']) is not int): fail('invalid_request','An action and revision are required.',422)
    fingerprint=hashlib.sha256(json.dumps({'parts':parts,'body':body},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    # The native lock serializes only this owned destination, never the store lock.
    with _NATIVE_LOCK:
        with store.LOCK:
            context.check_actor()
            with store.connect() as db:
                schema(db)
                old=db.execute('SELECT * FROM w15_cue_receipts WHERE session_id=? AND actor_id=? AND request_key=?',(sid,actor['owner'],body['idempotencyKey'])).fetchone()
                native=native_read(db,sid,actor['owner'],body['idempotencyKey'])
            previous=old or native
            if previous:
                if previous['fingerprint']!=fingerprint: fail('request_conflict','The operation key is already in use.')
                if native: return 200,native_result(native,context,sid)
                cue=store.get('w15cue',old['cue_id'],sid)
                return 200,{'cue':projection(context,sid,cue),'operation':{'state':'committed','committedRevision':old['revision']},'transport':{'state':'unavailable'}}
            if creating:
                eligible_material(context,sid,body['materialId'],body['materialVersion'])
                oid=store.ident(); revision=1; value={'id':oid,'materialId':body['materialId'],'materialVersion':body['materialVersion'],'status':'prepared'}
            else:
                oid=parts[1]; value=store.get('w15cue',oid,sid)
                if not value: fail('not_found','Cue unavailable.',404)
                with store.connect() as db:
                    owner=db.execute("SELECT owner_id FROM objects WHERE kind='w15cue' AND id=? AND session_id=?",(oid,sid)).fetchone()
                if not owner or owner['owner_id']!=actor['owner']: fail('not_found','Cue unavailable.',404)
                if value['_revision']!=body['revision']: fail('version_conflict','The cue changed.')
                if value['status']=='withdrawn': fail('invalid_transition','The cue is withdrawn.')
                if body['action'] in ('present','defer'):
                    material=eligible_material(context,sid,value['materialId'],value['materialVersion'])
                    if body['action']=='present' and any(k in material for k in ('w18Segment','w18Assistance')):
                        from . import waves18_segments
                        if not waves18_segments.DELIVERY_GUARDS_WIRED:
                            fail('integration_required','Delivery guard integration is not yet available.',503)
                revision=value['_revision']+1
            with store.connect() as db:
                unresolved = db.execute("SELECT url FROM w15_native_operations WHERE session_id=? AND actor_id=? AND cue_id=? AND action='present' AND state IN ('intent','unknown') ORDER BY rowid DESC LIMIT 1", (sid,actor['owner'],oid)).fetchone() if action else None
            needs_native=action and (body['action']=='present' or (body['action']=='withdraw' and (value['status']=='presented' or unresolved)))
            if not needs_native:
                if action: value['status']={'defer':'deferred','withdraw':'withdrawn'}[body['action']]; value.pop('_revision',None)
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    if creating: db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',('w15cue',oid,sid,actor['owner'],revision,json.dumps(value),store.now()))
                    else: db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w15cue' AND id=? AND session_id=? AND revision=?",(json.dumps(value),revision,oid,sid,body['revision']))
                    db.execute('INSERT INTO w15_cue_receipts VALUES(?,?,?,?,?,?)',(sid,actor['owner'],body['idempotencyKey'],fingerprint,oid,revision)); db.commit()
                cue=store.get('w15cue',oid,sid)
                return (201 if creating else 200),{'cue':projection(context,sid,cue),'operation':{'state':'committed','committedRevision':revision},'transport':{'state':'unavailable'}}
            cfg=configuration(sid,actor)
            with store.connect() as db:
                blocked=db.execute("SELECT session_id,actor_id,cue_id,action,state,url FROM w15_native_operations WHERE state IN ('intent','unknown') LIMIT 1").fetchone()
                if blocked and not (body['action']=='withdraw' and blocked['session_id']==sid and blocked['actor_id']==actor['owner'] and blocked['cue_id']==oid and blocked['action']=='present' and blocked['url']):
                    fail('operation_unknown','A local OBS operation requires reconciliation.',409)
                if body['action']=='present':
                    active=db.execute("SELECT cue_id FROM w15_native_operations WHERE state='committed' AND action='present' AND NOT EXISTS (SELECT 1 FROM w15_native_operations w WHERE w.cue_id=w15_native_operations.cue_id AND w.action='withdraw' AND w.state='committed') LIMIT 1").fetchone()
                    if active: fail('destination_busy','The local OBS destination already has a cue.',409)
                else:
                    active=db.execute("SELECT url FROM w15_native_operations WHERE session_id=? AND actor_id=? AND cue_id=? AND action='present' AND state='committed' ORDER BY rowid DESC LIMIT 1",(sid,actor['owner'],oid)).fetchone()
                    if not active and unresolved and unresolved['url']: active=unresolved
                    if not active: fail('operation_unknown','The owned presentation cannot be identified.',409)
                db.execute('INSERT INTO w15_native_operations VALUES(?,?,?,?,?,?,?,?,?)',(sid,actor['owner'],body['idempotencyKey'],fingerprint,oid,body['action'],'intent',active['url'] if body['action']=='withdraw' else None,None))
            if body['action']=='present':
                try:
                    _,published=phase10_studio.handle('POST',['studio','materials',value['materialId'],'publish'],{'version':value['materialVersion']},context)
                    url='http://127.0.0.1:'+str(cfg['httpPort'])+published['publicUrl']+'?expectedVersion='+str(value['materialVersion'])
                    with store.connect() as db: db.execute('UPDATE w15_native_operations SET url=? WHERE session_id=? AND actor_id=? AND request_key=?',(url,sid,actor['owner'],body['idempotencyKey']))
                except Exception:
                    with store.connect() as db: db.execute('UPDATE w15_native_operations SET state=? WHERE session_id=? AND actor_id=? AND request_key=?',('unknown',sid,actor['owner'],body['idempotencyKey']))
                    raise
            else: url=active['url']
        # No global lock or SQLite transaction is held during HTTP or OBS I/O.
        try:
            public_hash=None
            if body['action']=='present':
                api=url.replace('/p10/public/','/api/p10/public/',1)
                with urllib.request.urlopen(api,timeout=10) as response: public_hash=hashlib.sha256(response.read()).hexdigest()
            if body['action']=='present':
                with store.LOCK:
                    eligible_material(context,sid,value['materialId'],value['materialVersion'])
            proof=cue_effect(cfg,url,body['action'])
            with store.LOCK:
                context.check_actor()
                if body['action']=='present':
                    m=eligible_material(context,sid,value['materialId'],value['materialVersion'])
                    if m['status']!='published': fail('not_eligible','Publication changed during presentation.')
                current=store.get('w15cue',oid,sid)
                if not current or current['_revision']!=body['revision']: fail('version_conflict','The cue changed during presentation.')
                current.pop('_revision',None); current['status']='presented' if body['action']=='present' else 'withdrawn'
                transport={'state':'presented' if body['action']=='present' else 'withdrawn','proof':proof,'publicJsonSha256':public_hash,'materialId':value['materialId'],'materialVersion':value['materialVersion'],'cueId':oid}
                result={'revision':revision,'transport':transport}
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w15cue' AND id=? AND session_id=? AND revision=?",(json.dumps(current),revision,oid,sid,body['revision']))
                    db.execute("UPDATE w15_native_operations SET state='committed',result=? WHERE session_id=? AND actor_id=? AND request_key=?",(json.dumps(result),sid,actor['owner'],body['idempotencyKey']))
                    if body['action']=='withdraw': db.execute("UPDATE w15_native_operations SET state='resolved' WHERE session_id=? AND actor_id=? AND cue_id=? AND action='present' AND state IN ('intent','unknown')",(sid,actor['owner'],oid))
                    db.commit()
                cue=store.get('w15cue',oid,sid)
                return 200,{'cue':projection(context,sid,cue),'operation':{'state':'committed','committedRevision':revision},'transport':transport}
        except Exception:
            # Native effects may have occurred even if the response was lost.
            # An uncertain present is removed only if the configured input still matches.
            if body['action']=='present':
                try: cue_effect(cfg,url,'withdraw')
                except Exception: pass
            with store.connect() as db: db.execute("UPDATE w15_native_operations SET state='unknown' WHERE session_id=? AND actor_id=? AND request_key=?",(sid,actor['owner'],body['idempotencyKey']))
            fail('operation_unknown','The local OBS operation requires reconciliation.',503)
