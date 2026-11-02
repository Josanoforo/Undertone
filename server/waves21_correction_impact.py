"""Bounded correction lineage and durable replacement coordination.

All callbacks are supplied by the integration owner and execute on the supplied
SQLite connection. No provider, queue, network or shared runtime is operated here.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

_ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
_KINDS = {'caption', 'speech', 'material', 'record'}
_STATES = {'current', 'superseded', 'pending_replacement', 'already_consumed'}
_MAX = 128

class ImpactError(Exception):
    def __init__(self, code, status=409):
        super().__init__(code); self.code, self.status = code, status

def _fail(code, status=409): raise ImpactError(code, status)
def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value): _fail('invalid_request', 422)
    return value

def _rev(value):
    if type(value) is not int or not 0 <= value <= 9007199254740991: _fail('invalid_request', 422)
    return value

def _json(value):
    try: result = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError): _fail('invalid_request', 422)
    if len(result.encode('utf-8')) > 16384: _fail('invalid_request', 422)
    return result

def _hash(value): return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()
def _key(*values): return _hash(list(values))
def _now(): return datetime.now(timezone.utc).isoformat()

def _get(db, kind, key, sid):
    row = db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND session_id=?', (kind, key, sid)).fetchone()
    return json.loads(row[0]) if row else None

def _put(db, kind, key, sid, owner, data):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?) ON CONFLICT(kind,id) DO UPDATE SET revision=objects.revision+1,data=excluded.data', (kind,key,sid,owner,_json(data),_now()))

def _begin(db):
    if db.in_transaction: raise ValueError('a connection without an open transaction is required')
    db.execute('BEGIN IMMEDIATE')

def _source(auth, db, sid, actor, source, action):
    # Must return current {revision, scope, owner} or None; do not distinguish absence/denial.
    value = auth(db, sid, actor, source, action)
    if not isinstance(value, dict) or value.get('scope') not in ('public','private'): _fail('unavailable',404)
    _rev(value.get('revision'))
    if value['scope'] == 'private' and value.get('owner') != actor['owner']: _fail('unavailable',404)
    if action == 'correct' and value['scope'] == 'public' and actor.get('role') != 'creator': _fail('unavailable',404)
    return value

def _actor(sid, actor):
    _id(sid)
    if not isinstance(actor,dict) or actor.get('sid') != sid or actor.get('role') not in ('creator','viewer'): _fail('unavailable',404)
    _id(actor.get('owner'))

def _links(db, sid, source):
    # One bounded aggregate per source, indexed by the existing objects primary key.
    return _get(db,'w21impactlinks',_key(sid,source),sid) or {'items':[]}

def register_relation(db, sid, source, source_revision, target):
    """Call inside PRIMARY's target-creation transaction, after authorization.

    target: kind,id,revision,state,scope,owner. Replace only the exact target
    identity; sourceRevision binds its actual derivation. Never index content.
    """
    if not db.in_transaction: raise ValueError('registration requires caller transaction')
    _id(sid); _id(source); _rev(source_revision)
    if not isinstance(target,dict) or set(target) != {'kind','id','revision','state','scope','owner'}: _fail('invalid_request',422)
    if target['kind'] not in _KINDS or target['state'] not in _STATES or target['scope'] not in ('public','private'): _fail('invalid_request',422)
    _id(target['id']); _id(target['owner']); _rev(target['revision'])
    links = _links(db,sid,source); items = links['items']
    item = dict(target, sourceRevision=source_revision)
    existing = next((i for i,x in enumerate(items) if (x['kind'],x['id']) == (item['kind'],item['id'])),None)
    if existing is None:
        if len(items) >= _MAX: _fail('capacity',409)
        items.append(item)
    else: items[existing] = item
    _put(db,'w21impactlinks',_key(sid,source),sid,None,links)

def _visible(db, sid, actor, source, item, target_access):
    if item['scope'] == 'private' and item['owner'] != actor['owner']: return False
    return target_access(db,sid,actor,source,dict(item)) is True

def _view(item, reason):
    state = item['state']
    action = 'choose_correction_audio' if state == 'already_consumed' and item['kind'] == 'speech' else ('none' if state == 'already_consumed' else 'prepare_replacement')
    return {'kind':item['kind'],'id':item['id'],'revision':item['revision'],'state':state,'reason':reason,'eligibleActions':[action] if action != 'none' else [],'freshApprovalRequired':item['scope']=='public' and item['kind'] in ('material','record')}

def preview_correction(db, sid, actor, source, expected_revision, reason, *, source_access, target_access):
    _actor(sid,actor); _id(source); _rev(expected_revision)
    if not isinstance(reason,str) or not reason.strip() or len(reason)>500: _fail('invalid_request',422)
    _begin(db)
    try:
        src = _source(source_access,db,sid,actor,source,'correct')
        if src['revision'] != expected_revision: _fail('stale_revision')
        affected = [_view(i,reason) for i in _links(db,sid,source)['items'] if i['sourceRevision']==expected_revision and _visible(db,sid,actor,source,i,target_access)]
        db.commit(); return {'source':source,'revision':expected_revision,'reason':reason,'affected':affected}
    except BaseException:
        db.rollback(); raise

def commit_correction(db, sid, actor, body, *, source_access, target_access, update_source):
    """Atomic source update, fence, intent and idempotency receipt; callbacks must be DB-only."""
    _actor(sid,actor)
    if not isinstance(body,dict) or set(body)!={'requestId','sourceRef','expectedRevision','reason','change'}: _fail('invalid_request',422)
    request, source = _id(body['requestId']), _id(body['sourceRef']); expected = _rev(body['expectedRevision'])
    reason = body['reason']
    if not isinstance(reason,str) or not reason.strip() or len(reason)>500: _fail('invalid_request',422)
    fp = _hash(body); receipt_id = _key(sid,actor['owner'],request); fence_id = _key(sid,source)
    _begin(db)
    try:
        src = _source(source_access,db,sid,actor,source,'correct')
        receipt = _get(db,'w21impactreceipt',receipt_id,sid)
        if receipt:
            if receipt['fingerprint'] != fp: _fail('request_conflict')
            intent = _get(db,'w21impactintent',receipt['intentId'],sid)
            if src['revision'] != intent['revision']: _fail('stale_revision')
            result = _project(db,sid,actor,intent,target_access)
            db.commit(); return result
        if src['revision'] != expected: _fail('stale_revision')
        # Retain every affected derivative in the private durable intent. Projection
        # filters current rights; hidden targets must not escape invalidation.
        items = [dict(i) for i in _links(db,sid,source)['items'] if i['sourceRevision']==expected]
        new_revision = update_source(db,sid,actor,source,expected,body['change'])
        if type(new_revision) is not int or new_revision <= expected: _fail('invalid_source_update')
        intent_id = _key('intent',sid,actor['owner'],request)
        fence = _key('fence',sid,source,new_revision,intent_id)
        targets=[]
        for i in items:
            i['replacementId'] = _key('replacement',intent_id,i['kind'],i['id'],i['revision'])
            i['status'] = 'consumed' if i['state']=='already_consumed' else 'pending'
            targets.append(i)
        intent={'id':intent_id,'source':source,'revision':new_revision,'previousRevision':expected,'fence':fence,'reason':reason,'owner':actor['owner'],'targets':targets}
        _put(db,'w21impactfence',fence_id,sid,actor['owner'],{'fence':fence,'revision':new_revision,'intentId':intent_id})
        _put(db,'w21impactintent',intent_id,sid,actor['owner'],intent)
        _put(db,'w21impactreceipt',receipt_id,sid,actor['owner'],{'fingerprint':fp,'intentId':intent_id})
        result=_project(db,sid,actor,intent,target_access); db.commit(); return result
    except BaseException:
        db.rollback(); raise

def _project(db,sid,actor,intent,target_access):
    targets=[]
    for i in intent['targets']:
        if _visible(db,sid,actor,intent['source'],i,target_access):
            v=_view(i,intent['reason']); v.update({'replacementId':i['replacementId'],'status':i['status']}); targets.append(v)
    return {'intentId':intent['id'],'source':intent['source'],'revision':intent['revision'],'fence':intent['fence'],'affected':targets}

def _guard(db,sid,actor,intent,source_access):
    src=_source(source_access,db,sid,actor,intent['source'],'correct')
    fence=_get(db,'w21impactfence',_key(sid,intent['source']),sid)
    if src['revision'] != intent['revision'] or not fence or fence['fence'] != intent['fence']: _fail('stale_fence')

def apply_replacement(db, sid, actor, intent_id, expected_fence, replacement_id, *, source_access, target_access, target_current, apply):
    """Atomically guard and apply a prepared result; apply must be a local DB-only mutation.

    The caller performs costly work outside this call using replacement_id as its
    idempotency key. target_current verifies exact old version and generation.
    """
    _actor(sid,actor); _id(intent_id); _id(expected_fence); _id(replacement_id)
    _begin(db)
    try:
        intent=_get(db,'w21impactintent',intent_id,sid)
        if not intent or intent['owner'] != actor['owner']: _fail('unavailable',404)
        _guard(db,sid,actor,intent,source_access)
        if intent['fence'] != expected_fence: _fail('stale_fence')
        item=next((x for x in intent['targets'] if x['replacementId']==replacement_id),None)
        if not item or not _visible(db,sid,actor,intent['source'],item,target_access): _fail('unavailable',404)
        if item['status']=='consumed': _fail('already_consumed')
        if item['status']=='applied':
            result={'id':item['id'],'oldRevision':item['revision'],'newRevision':item['newRevision'],'status':'applied','replacementId':replacement_id}
            db.commit(); return result
        if target_current(db,sid,actor,dict(item)) is not True: _fail('stale_target')
        newrev=apply(db,sid,actor,dict(item),intent['revision'],replacement_id, item['scope']=='public')
        if type(newrev) is not int or newrev <= item['revision']: _fail('invalid_target_update')
        item['newRevision']=newrev; item['status']='applied'
        _put(db,'w21impactintent',intent_id,sid,intent['owner'],intent)
        result={'id':item['id'],'oldRevision':item['revision'],'newRevision':newrev,'status':'applied','replacementId':replacement_id}
        db.commit(); return result
    except BaseException:
        db.rollback(); raise

def guard_delivery(db, sid, actor, intent_id, fence, replacement_id, *, source_access, target_access, delivery_current):
    """Recheck current source/rights/fence and exact replacement at delivery time."""
    _actor(sid,actor); _id(intent_id); _id(fence); _id(replacement_id); _begin(db)
    try:
        intent=_get(db,'w21impactintent',intent_id,sid)
        if not intent: _fail('unavailable',404)
        # Reading actors need current source read rights; creator ownership is not assumed.
        src=_source(source_access,db,sid,actor,intent['source'],'read')
        current=_get(db,'w21impactfence',_key(sid,intent['source']),sid)
        if src['revision']!=intent['revision'] or not current or current['fence']!=fence or intent['fence']!=fence: _fail('stale_fence')
        item=next ( (x for x in intent['targets'] if x['replacementId']==replacement_id), None)
        if not item or item['status']!='applied' or not _visible(db,sid,actor,intent['source'],item,target_access): _fail('unavailable',404)
        if delivery_current(db,sid,actor,dict(item)) is not True: _fail('unavailable',404)
        db.commit(); return True
    except BaseException:
        db.rollback(); raise

