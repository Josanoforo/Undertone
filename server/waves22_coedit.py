"""Bounded optimistic coediting; trusted integration supplies current rights guards."""
import hashlib
import json
import re
import time
from . import store
from .phase10_common import Phase10Error

DRAFT = 'w22coedit'
RECEIPT = 'w22coeditreceipt'
MAX_EVENTS = 200

def _base_content(draft, revision):
    """Reconstruct only when the entire retained event prefix proves the base."""
    if revision > draft['revision']:
        return None
    if revision == draft['revision']:
        return dict(draft['content'])
    events = draft['events']
    if revision == 0:
        return {'title': '', 'body': ''}
    if not events or events[0]['revision'] != 1:
        return None
    content = {'title': '', 'body': ''}
    for event in events:
        if event['revision'] > revision:
            break
        for op in event['operations']:
            content[op['field']] = op['value']
        if event['revision'] == revision:
            return content
    return None

def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)

def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        _fail('invalid_request', 'Invalid identifier.', 422)
    return value

def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()

def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        _fail('invalid_request', 'Invalid fields.', 422)

def _revision(value):
    if type(value) is not int or value < 0 or value > 2147483647:
        _fail('invalid_request', 'Invalid revision.', 422)
    return value

def _content(value):
    _fields(value, ('title', 'body'))
    for key, limit in (('title', 200), ('body', 12000)):
        if not isinstance(value[key], str) or len(value[key]) > limit or '\x00' in value[key]:
            _fail('invalid_request', 'Invalid draft text.', 422)
    return dict(value)

def _read(db, kind, sid, ident):
    row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (kind, ident, sid)).fetchone()
    if not row: return None
    return json.loads(row['data']), row['revision'], row['owner_id']

def _insert(db, kind, sid, ident, owner, value):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)', (kind, ident, sid, owner, _json(value), store.now()))

def _save(db, sid, ident, rev, value):
    n = db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?', (_json(value), DRAFT, ident, sid, rev)).rowcount
    if n != 1: _fail('version_conflict', 'Draft changed.')

def _guard(ctx, db, draft, action):
    # The callback is trusted code supplied by PRIMARY, not a request parameter.
    # It must check current credential, explicit coedit grant, source/session rights,
    # segment/material binding and captured base material version in this transaction.
    if ctx.authorize(db, draft, action) is not True:
        _fail('not_found', 'Draft unavailable.', 404)
    if ctx.actor.get('owner') not in (draft['creatorId'], draft['collaboratorId']):
        _fail('not_found', 'Draft unavailable.', 404)
    if action in ('approve', 'withdraw') and ctx.actor.get('owner') != draft['creatorId']:
        _fail('not_found', 'Draft unavailable.', 404)
    if draft['withdrawn'] and action != 'withdraw':
        _fail('not_found', 'Draft unavailable.', 404)

def _get(db, ctx, draft_id, action):
    row = _read(db, DRAFT, ctx.sid, _id(draft_id))
    if not row or row[2] != row[0].get('creatorId'): _fail('not_found', 'Draft unavailable.', 404)
    _guard(ctx, db, row[0], action)
    return row[0], row[1]

def _receipt(db, ctx, request, fingerprint):
    rid = _hash(['w22coeditreceipt', ctx.sid, ctx.actor['owner'], _id(request)])
    row = _read(db, RECEIPT, ctx.sid, rid)
    if row and (row[2] != ctx.actor['owner'] or row[0]['fingerprint'] != fingerprint):
        _fail('request_conflict', 'Request ID already used.')
    return rid, row[0] if row else None

def _record(db, ctx, rid, fingerprint, result, draft_id, action):
    _insert(db, RECEIPT, ctx.sid, rid, ctx.actor['owner'], {'fingerprint':fingerprint, 'result':result, 'draftId':draft_id, 'action':action})

def create(ctx, body):
    _fields(body, ('requestId','draftId','segmentId','materialId','baseMaterialVersion','collaboratorId'))
    for key in ('requestId','draftId','segmentId','materialId','collaboratorId'): _id(body[key])
    _revision(body['baseMaterialVersion'])
    if ctx.actor.get('role') != 'creator' or ctx.actor.get('owner') == body['collaboratorId']:
        _fail('not_found', 'Draft unavailable.', 404)
    draft = {'id':body['draftId'], 'segmentId':body['segmentId'], 'materialId':body['materialId'], 'baseMaterialVersion':body['baseMaterialVersion'], 'creatorId':ctx.actor['owner'], 'collaboratorId':body['collaboratorId'], 'schemaVersion':1, 'revision':0, 'content':{'title':'','body':''}, 'events':[], 'cursor':0, 'presence':{}, 'approval':None, 'withdrawn':False}
    fp = _hash(['create',body])
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _guard(ctx, db, draft, 'create')
        rid, old = _receipt(db, ctx, body['requestId'], fp)
        if old:
            current, _ = _get(db, ctx, body['draftId'], 'read')
            return {'operation':old['result'], 'draft':_projection(current)}
        if db.execute('SELECT 1 FROM objects WHERE kind=? AND id=?', (DRAFT, body['draftId'])).fetchone():
            _fail('version_conflict','Draft already exists.')
        existing = db.execute('SELECT data FROM objects WHERE kind=? AND session_id=? AND owner_id=?', (DRAFT,ctx.sid,ctx.actor['owner'])).fetchall()
        if any(json.loads(row['data']).get('segmentId') == body['segmentId'] for row in existing):
            _fail('version_conflict','Segment already has a draft.')
        _insert(db, DRAFT, ctx.sid, body['draftId'], ctx.actor['owner'], draft)
        result={'state':'committed','revision':0}
        _record(db, ctx, rid, fp, result, body['draftId'], 'create'); db.commit()
        return {'operation':result, 'draft':_projection(draft)}

def _projection(draft):
    now=time.time()
    return {'draftId':draft['id'], 'schemaVersion':1, 'revision':draft['revision'], 'content':dict(draft['content']), 'cursor':draft['cursor'], 'presence':[{'actorId':actor,'expiresAt':expiry} for actor,expiry in draft['presence'].items() if expiry > now], 'approvedRevision':draft['approval']['revision'] if draft['approval'] else None}

def open_draft(ctx, draft_id, cursor=0, schema_version=1):
    _revision(cursor)
    if type(schema_version) is not int or schema_version != 1: _fail('unsupported_schema','Unsupported draft schema.',409)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); draft,_ = _get(db,ctx,draft_id,'read')
        if cursor > draft['cursor']: _fail('version_conflict','Invalid event cursor.')
        events=draft['events']
        reset=bool(events and cursor < events[0]['cursor']-1)
        out={'draft':_projection(draft), 'reset':reset, 'events':[] if reset else [event for event in events if event['cursor']>cursor]}
        db.commit(); return out

def apply_patch(ctx, draft_id, body):
    _fields(body, ('requestId','baseRevision','operations'))
    _id(body['requestId']); _revision(body['baseRevision'])
    ops=body['operations']
    if not isinstance(ops,list) or not 1 <= len(ops) <= 2: _fail('invalid_request','Invalid operations.',422)
    patch={}
    for op in ops:
        _fields(op, ('field','value'))
        if op['field'] not in ('title','body') or op['field'] in patch: _fail('invalid_request','Invalid operation.',422)
        patch[op['field']]=op['value']
    _content({'title':patch.get('title',''), 'body':patch.get('body','')})
    fp=_hash(['patch',draft_id,body])
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); draft,rev=_get(db,ctx,draft_id,'edit'); rid,old=_receipt(db,ctx,body['requestId'],fp)
        if old: return {'operation':old['result'],'draft':_projection(draft)}
        if body['baseRevision'] != draft['revision']:
            result={'state':'conflict','baseRevision':body['baseRevision'],'submitted':patch,'currentRevision':draft['revision']}
            base = _base_content(draft, body['baseRevision'])
            conflict = None
            if base is not None:
                proposed = dict(base)
                proposed.update(patch)
                conflict = {'base': {'revision': body['baseRevision'], 'fields': base},
                            'current': {'revision': draft['revision'], 'fields': dict(draft['content'])},
                            'proposed': {'fields': proposed}}
        else:
            draft['content'].update(patch); draft['revision']+=1; draft['cursor']+=1; draft['approval']=None
            draft['events'].append({'cursor':draft['cursor'],'revision':draft['revision'],'actorId':ctx.actor['owner'],'operations':ops})
            draft['events']=draft['events'][-MAX_EVENTS:]; _save(db,ctx.sid,draft_id,rev,draft)
            result={'state':'committed','revision':draft['revision']}
        _record(db,ctx,rid,fp,result,draft_id,'patch'); db.commit()
        response = {'operation':result,'draft':_projection(draft)}
        if result['state'] == 'conflict' and conflict is not None:
            response['conflict'] = conflict
        return response

def presence(ctx,draft_id,seconds):
    if type(seconds) is not int or not 1 <= seconds <= 60: _fail('invalid_request','Invalid presence expiry.',422)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); draft,rev=_get(db,ctx,draft_id,'read')
        draft['presence'][ctx.actor['owner']]=time.time()+seconds; _save(db,ctx.sid,draft_id,rev,draft); db.commit()
        return _projection(draft)

def decide(ctx,draft_id,action,body):
    if action not in ('approve','withdraw'): _fail('invalid_request','Invalid action.',422)
    _fields(body,('requestId','expectedRevision')); _id(body['requestId']); _revision(body['expectedRevision'])
    fp=_hash([action,draft_id,body])
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); draft,rev=_get(db,ctx,draft_id,action); rid,old=_receipt(db,ctx,body['requestId'],fp)
        if old: return {'operation':old['result']}
        if draft['revision'] != body['expectedRevision']: _fail('version_conflict','Draft changed.')
        if action == 'approve':
            if not draft['content']['title'].strip() or not draft['content']['body'].strip(): _fail('invalid_request','Draft text is required.',422)
            draft['approval']={'revision':draft['revision'],'content':dict(draft['content'])}
        else:
            draft['withdrawn']=True; draft['approval']=None; draft['presence']={}
        _save(db,ctx.sid,draft_id,rev,draft); result={'state':'committed','revision':draft['revision'],'action':action}
        _record(db,ctx,rid,fp,result,draft_id,action); db.commit(); return {'operation':result}

def operation_receipt(ctx, draft_id, request_id):
    """Read an actor-bound durable receipt without admitting a mutation."""
    _id(draft_id); _id(request_id)
    rid = _hash(['w22coeditreceipt', ctx.sid, ctx.actor['owner'], request_id])
    with store.LOCK, store.connect() as db:
        row = _read(db, DRAFT, ctx.sid, draft_id)
        if not row or row[2] != row[0].get('creatorId'):
            _fail('not_found', 'Draft unavailable.', 404)
        draft = row[0]
        # Withdrawal remains recoverable only while all underlying rights hold.
        _guard(ctx, db, draft, 'withdraw' if draft['withdrawn'] else 'read')
        receipt = _read(db, RECEIPT, ctx.sid, rid)
        if (not receipt or receipt[2] != ctx.actor['owner'] or receipt[0].get('draftId') != draft_id
                or receipt[0].get('action') not in ('create', 'patch', 'approve', 'withdraw')):
            _fail('not_found', 'Operation unavailable.', 404)
        value = receipt[0]
        if draft['withdrawn'] and value.get('action') != 'withdraw':
            _fail('not_found', 'Operation unavailable.', 404)
        result = value['result']
        metadata = {key: result[key] for key in ('state', 'revision', 'action', 'baseRevision', 'currentRevision') if key in result}
        metadata['action'] = value['action']
        return {'operation': metadata, 'draft': None if draft['withdrawn'] else _projection(draft)}

def approved_for_adoption(ctx,draft_id,revision):
    """Return exact immutable approval for creator; caller must recheck atomically at adoption."""
    _revision(revision)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); draft,_=_get(db,ctx,draft_id,'approve')
        approval=draft['approval']
        if not approval or approval['revision'] != revision or draft['revision'] != revision: _fail('version_conflict','Fresh approval required.')
        result={'draftId':draft_id,'revision':revision,'segmentId':draft['segmentId'],'materialId':draft['materialId'],'baseMaterialVersion':draft['baseMaterialVersion'],'content':dict(approval['content'])}
        db.commit(); return result

def approved_in_transaction(ctx, db, draft_id, revision):
    """PRIMARY invokes inside the same serialized transaction as material adoption."""
    _revision(revision)
    draft,_ = _get(db,ctx,draft_id,'approve')
    approval=draft['approval']
    if not approval or approval['revision'] != revision or draft['revision'] != revision:
        _fail('version_conflict','Fresh approval required.')
    return {'draftId':draft_id,'revision':revision,'segmentId':draft['segmentId'],'materialId':draft['materialId'],'baseMaterialVersion':draft['baseMaterialVersion'],'content':dict(approval['content'])}

