"""Two source-bound declarative models. No executable user rules or provider calls."""
import copy
import hashlib
import json
import re
from . import store
from .phase10_common import Phase10Error, parse_ref

MODEL = 'w22model'
RECEIPT = 'w22modelreceipt'
SHARE = 'w22modelshare'
RGB = 'RGB_LINEAR_MEAN_V1'
BUDGET = 'RESOURCE_BUDGET_12_V1'


def fail(code, message, status=422):
    raise Phase10Error(code, message, status)


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        fail('invalid_request', 'Invalid identifier.')
    return value


def _fields(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        fail('invalid_request', 'Invalid fields.')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        fail('invalid_parameter', 'A bounded integer is required.')
    return value


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        fail('invalid_request', 'Invalid JSON value.')


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def definition(kind, sourceRefs, templateId, templateVersion):
    """Build the only supported definitions; approval is checked by the trusted context."""
    if kind not in (RGB, BUDGET): fail('unsupported_model', 'Unsupported model.')
    _id(templateId); _integer(templateVersion, 1, 2147483647)
    if not isinstance(sourceRefs, list) or not 1 <= len(sourceRefs) <= 8:
        fail('invalid_request', 'Select source moments.')
    sourceRefs = [parse_ref(ref) for ref in sourceRefs]
    if len({_json(ref) for ref in sourceRefs}) != len(sourceRefs): fail('invalid_request', 'Duplicate source moments.')
    # Current rights belong to the trusted context.
    if len(_json(sourceRefs)) > 8192: fail('invalid_request', 'Source references are too large.')
    if kind == RGB:
        spec = {'operation':'weighted_channel_mean_half_up', 'units':{'channels':'integer channel levels','weights':'weight units'}, 'ranges':{'channel':[0,255], 'weight':[0,100]}}
    else:
        spec = {'operation':'exact_fixed_sum', 'units':{'allocation':'resource tokens'}, 'ranges':{'allocation':[0,12]}, 'total':12}
    return {'kind':kind, 'version':1, 'sourceRefs':copy.deepcopy(sourceRefs), 'templateId':templateId, 'templateVersion':templateVersion, 'spec':spec}


def validate_definition(value):
    _fields(value, ('kind','version','sourceRefs','templateId','templateVersion','spec'))
    if type(value['version']) is not int or value['version'] != 1:
        fail('unsupported_version', 'Unsupported definition version.')
    expected = definition(value['kind'], value['sourceRefs'], value['templateId'], value['templateVersion'])
    if value != expected or _json(value) != _json(expected):
        fail('unsupported_definition', 'The fixed model definition cannot be changed.')
    return copy.deepcopy(expected)


def evaluate(model, parameters):
    model = validate_definition(model)
    if model['kind'] == RGB:
        _fields(parameters, ('c1','w1','c2','w2'))
        for name in ('c1','c2'):
            _fields(parameters[name], ('r','g','b'))
            for k in ('r','g','b'): _integer(parameters[name][k], 0, 255)
        w1 = _integer(parameters['w1'],0,100); w2 = _integer(parameters['w2'],0,100)
        total = w1+w2
        if not total: fail('invalid_parameter', 'At least one weight must be positive.')
        values = {k:(2*(w1*parameters['c1'][k]+w2*parameters['c2'][k])+total)//(2*total) for k in ('r','g','b')}
        explanation = 'Each channel is the weighted integer mean, rounded half upward. This is simplified digital arithmetic, not pigment mixing or a color-science prediction.'
    else:
        _fields(parameters, ('total','a','b'))
        total = _integer(parameters['total'],12,12)
        a = _integer(parameters['a'],0,12); b = _integer(parameters['b'],0,12)
        if a+b != total: fail('invalid_parameter', 'Allocations must add up to exactly 12.')
        values = {'a':a,'b':b,'unused':0}
        explanation = 'The two integer allocations use exactly 12 resource tokens. This toy rule provides no allocation or optimization advice.'
    return {'values':values, 'explanation':explanation, 'ruleVersion':model['kind'], 'definitionVersion':model['version']}


def replay(model, events):
    """Verify and reconstruct exact parameter/result events; authorization is caller-owned."""
    model = validate_definition(model)
    if not isinstance(events,list) or len(events)>200: fail('invalid_request', 'Invalid event history.')
    output=[]
    for index, event in enumerate(events):
        _fields(event, ('sequence','definitionVersion','ruleVersion','parameters','result'))
        if type(event['sequence']) is not int or event['sequence'] != index+1 or type(event['definitionVersion']) is not int or event['definitionVersion'] != model['version'] or event['ruleVersion'] != model['kind']:
            fail('version_conflict', 'Event version or sequence changed.',409)
        calculated = evaluate(model,event['parameters'])
        if event['result'] != calculated or _json(event['result']) != _json(calculated):
            fail('version_conflict', 'Recorded result does not match its rule.',409)
        output.append(copy.deepcopy(event))
    return output


def _load(db, kind, sid, oid):
    row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND session_id=? AND id=?',(kind,sid,oid)).fetchone()
    if not row: fail('not_found','Model unavailable.',404)
    return json.loads(row['data']), row['revision'], row['owner_id']


def _insert(db, kind, sid, owner, oid, value):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',(kind,oid,sid,owner,_json(value),store.now()))


def _guard(ctx, db, model, owner):
    # Trusted PRIMARY checks current actor, session, source rights, exact approved
    # template/version and private practice attempt ownership/binding atomically.
    ctx.check_actor()
    fingerprint = ctx.authorize(db, model['definition'], model['attemptId'], owner)
    if not isinstance(fingerprint, str) or model.get('attemptFingerprint') != fingerprint:
        fail('not_found','Model unavailable.',404)


def _private(ctx, db, model_id, authorize=True):
    model, revision, owner = _load(db,MODEL,ctx.sid,_id(model_id))
    if owner != ctx.actor['owner']: fail('not_found','Model unavailable.',404)
    if authorize: _guard(ctx,db,model,owner)
    return model,revision,owner


def _projection(model, revision):
    return {'id':model['id'],'revision':revision,'definition':copy.deepcopy(model['definition']), 'attemptId':model['attemptId'], 'prediction':copy.deepcopy(model['prediction']), 'events':replay(model['definition'],model['events'])}


def mutate(ctx, body):
    """Atomic create, evaluate, share or revoke. No client-supplied identity."""
    if not isinstance(body,dict): fail('invalid_request','Invalid request.')
    action=body.get('action'); req=_id(body.get('requestId')); sid=_id(ctx.sid); owner=_id(ctx.actor.get('owner'))
    common=('action','requestId','expectedRevision')
    names={'create':common+('definition','attemptId','prediction'), 'evaluate':common+('modelId','parameters'), 'share':common+('modelId','sequence','consent','identityConsent'), 'revoke':common+('modelId','shareId')}
    if action not in names: fail('invalid_request','Invalid action.')
    _fields(body,names[action]); expected=_integer(body['expectedRevision'],0,2147483647)
    fp=_hash(body); receipt_id=_hash([sid,owner,req])
    with ctx.lock, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            ctx.check_actor()
            row=db.execute('SELECT data FROM objects WHERE kind=? AND session_id=? AND id=?',(RECEIPT,sid,receipt_id)).fetchone()
            receipt=json.loads(row['data']) if row else None
            if receipt and receipt['fingerprint'] != fp: fail('request_conflict','Request ID already used.',409)
            if action=='create':
                if expected!=0: fail('version_conflict','Model revision changed.',409)
                definition_value=validate_definition(body['definition']); attempt=_id(body['attemptId'])
                # Prediction is a bounded text entered before any result exists.
                prediction=body['prediction']
                if not isinstance(prediction,str) or not prediction.strip() or len(prediction)>2000 or any(ord(c)<32 and c not in '\n\r\t' for c in prediction): fail('invalid_request','Enter a prediction.')
                if receipt:
                    model,rev,_=_private(ctx,db,receipt['modelId'])
                    if rev!=receipt['revision']: fail('version_conflict','Model revision changed.',409)
                else:
                    mid=store.ident(); model={'id':mid,'definition':definition_value,'attemptId':attempt,'prediction':prediction,'events':[]}
                    model['attemptFingerprint'] = ctx.authorize(db, definition_value, attempt, owner)
                    _guard(ctx,db,model,owner)
                    _insert(db,MODEL,sid,owner,mid,model); rev=1
            else:
                mid=_id(body['modelId']); model,rev,_=_private(ctx,db,mid,action!='revoke')
                if receipt:
                    if rev!=receipt['revision']: fail('version_conflict','Model revision changed.',409)
                    if action=='share':
                        sh,_,showner=_load(db,SHARE,sid,receipt['shareId'])
                        if showner!=owner or not sh['active']: fail('not_found','Share unavailable.',404)
                else:
                    if rev!=expected: fail('version_conflict','Model revision changed.',409)
                    if action=='evaluate':
                        result=evaluate(model['definition'],body['parameters'])
                        if len(model['events'])>=200: fail('capacity','Model history is full.',409)
                        model['events'].append({'sequence':len(model['events'])+1,'definitionVersion':model['definition']['version'],'ruleVersion':model['definition']['kind'],'parameters':copy.deepcopy(body['parameters']),'result':result})
                    elif action=='share':
                        seq=_integer(body['sequence'],1,len(model['events']))
                        if body['consent'] is not True or type(body['identityConsent']) is not bool: fail('invalid_request','Explicit sharing consent is required.')
                        share_id=store.ident(); _insert(db,SHARE,sid,owner,share_id,{'id':share_id,'modelId':mid,'sequence':seq,'active':True,'identityConsent':body['identityConsent']})
                    else:
                        share_id=_id(body['shareId']); sh,shrev,showner=_load(db,SHARE,sid,share_id)
                        if showner!=owner or sh['modelId']!=mid or not sh['active']: fail('not_found','Share unavailable.',404)
                        sh['active']=False; db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND session_id=? AND id=?',(_json(sh),shrev+1,SHARE,sid,share_id))
                    rev+=1
                    db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND session_id=? AND id=?',(_json(model),rev,MODEL,sid,mid))
            if not receipt:
                receipt={'fingerprint':fp,'modelId':model['id'],'revision':rev,'requestId':req,'action':action}
                if action in ('share','revoke'): receipt['shareId']=share_id
                _insert(db,RECEIPT,sid,owner,receipt_id,receipt)
            if action=='revoke':
                ctx.check_actor()
                output={'operation':{'requestId':req,'state':'committed'}}
            else:
                _guard(ctx,db,model,owner)
                output={'model':_projection(model,rev),'operation':{'requestId':req,'state':'committed'}}
            if action in ('share','revoke'): output['shareId']=receipt['shareId']
            db.commit(); return output
        except BaseException:
            db.rollback(); raise


def read(ctx, model_id):
    with ctx.lock, store.connect() as db:
        ctx.check_actor(); model,rev,owner=_private(ctx,db,model_id)
        result=_projection(model,rev); _guard(ctx,db,model,owner); return result


def read_share(ctx, share_id):
    """Creator-only selected event; ctx authorizes recipient and original owner's source rights."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('role')!='creator': fail('not_found','Share unavailable.',404)
        sh,_,owner=_load(db,SHARE,ctx.sid,_id(share_id))
        if not sh['active']: fail('not_found','Share unavailable.',404)
        model,_,model_owner=_load(db,MODEL,ctx.sid,sh['modelId'])
        if owner!=model_owner: fail('not_found','Share unavailable.',404)
        _guard(ctx,db,model,owner)
        events=replay(model['definition'],model['events']); event=events[sh['sequence']-1]
        result={'shareId':share_id,'definition':copy.deepcopy(model['definition']),'event':event}
        if sh['identityConsent']: result['ownerId']=owner
        _guard(ctx,db,model,owner)
        return result


def list_shares(ctx):
    """Discover only shares currently readable by the session creator."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            fail('not_found', 'Share unavailable.', 404)
        rows = db.execute("SELECT id FROM objects WHERE kind=? AND session_id=? ORDER BY created_at,id", (SHARE, ctx.sid)).fetchall()
        result = []
        for row in rows:
            try:
                result.append(read_share(ctx, row['id']))
            except Phase10Error as exc:
                if exc.code not in ('not_found', 'stale_context'):
                    raise
        return {'shares': result}



def list_models(ctx):
    """Enumerate only the caller's currently authorized private models."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        rows = db.execute("SELECT id FROM objects WHERE kind=? AND session_id=? AND owner_id=? ORDER BY created_at,id", (MODEL, ctx.sid, ctx.actor['owner'])).fetchall()
        result = []
        for row in rows:
            try:
                model, rev, owner = _private(ctx, db, row['id'])
                result.append(_projection(model, rev))
            except Phase10Error as exc:
                if exc.code not in ('not_found', 'stale_context'):
                    raise
        return {'models': result}


def list_receipts(ctx):
    """Enumerate committed operation identifiers without exposing fingerprints."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        rows = db.execute("SELECT data FROM objects WHERE kind=? AND session_id=? AND owner_id=? ORDER BY created_at,id", (RECEIPT, ctx.sid, ctx.actor['owner'])).fetchall()
        return {'receipts': [{k: value[k] for k in ('requestId', 'action', 'modelId', 'revision') if k in value} for value in (json.loads(row['data']) for row in rows)]}


def list_owned_shares(ctx):
    """Minimal withdrawal handles remain available when a source is withdrawn."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') not in ('creator', 'viewer'):
            fail('not_found', 'Share unavailable.', 404)
        owner = ctx.actor['owner']
        rows = db.execute('SELECT data FROM objects WHERE kind=? AND session_id=? AND owner_id=? ORDER BY created_at,id', (SHARE, ctx.sid, owner)).fetchall()
        result = []
        for row in rows:
            share = json.loads(row['data'])
            if share.get('active') is not True: continue
            try:
                _, revision, _ = _private(ctx, db, share['modelId'], authorize=False)
            except Phase10Error as exc:
                if exc.code == 'not_found': continue
                raise
            result.append({'shareId': share['id'], 'modelId': share['modelId'], 'revision': revision, 'sequence': share['sequence']})
        return {'shares': result}


def forget(ctx, model_id, request_id):
    """Erase a caller-owned model and deactivate its shares, even if sources expired."""
    model_id, request_id = _id(model_id), _id(request_id)
    owner = _id(ctx.actor.get('owner')); sid = _id(ctx.sid)
    fingerprint = _hash({'action': 'forget', 'modelId': model_id})
    receipt_id = _hash([sid, owner, request_id])
    with ctx.lock, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            ctx.check_actor()
            row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND session_id=? AND id=?', (RECEIPT, sid, receipt_id)).fetchone()
            if row:
                receipt = json.loads(row['data'])
                if row['owner_id'] != owner or receipt.get('fingerprint') != fingerprint:
                    fail('request_conflict', 'Request ID already used.', 409)
            else:
                _private(ctx, db, model_id, authorize=False)
                shares = db.execute('SELECT id,data,revision FROM objects WHERE kind=? AND session_id=? AND owner_id=?', (SHARE, sid, owner)).fetchall()
                for share in shares:
                    value = json.loads(share['data'])
                    if value.get('modelId') == model_id and value.get('active') is True:
                        value['active'] = False
                        db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND session_id=? AND id=?', (_json(value), share['revision'] + 1, SHARE, sid, share['id']))
                db.execute('DELETE FROM objects WHERE kind=? AND session_id=? AND id=? AND owner_id=?', (MODEL, sid, model_id, owner))
                _insert(db, RECEIPT, sid, owner, receipt_id, {'fingerprint': fingerprint, 'modelId': model_id, 'revision': 0, 'requestId': request_id, 'action': 'forget'})
            db.commit()
            return {'operation': {'requestId': request_id, 'state': 'committed'}}
        except BaseException:
            db.rollback()
            raise

