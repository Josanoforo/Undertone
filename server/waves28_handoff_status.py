"""Revision-bound handoff metadata over the existing coedit authority.

Not mounted: the shared router must hold store.LOCK through final_guard and send.
"""
from . import store, waves22_coedit as coedit, waves22_coedit_auth as auth
from .phase10_common import Phase10Error, parse_ref

STATUS = 'w28handoffstatus'
RECEIPT = 'w28handoffreceipt'


def _fail(code='not_found', message='Handoff unavailable.', status=404):
    raise Phase10Error(code, message, status)


def _refs(refs):
    if not isinstance(refs, list) or len(refs) > 20:
        _fail('invalid_request', 'Invalid reason references.', 422)
    result = []
    for ref in refs:
        coedit._fields(ref, ('id', 'revision', 'sourceRef'))
        result.append({'id': coedit._id(ref['id']), 'revision': coedit._revision(ref['revision']),
                       'sourceRef': parse_ref(ref['sourceRef'])})
        if ref['revision'] < 1: _fail('invalid_request', 'Invalid reason revision.', 422)
    if len({ref['id'] for ref in result}) != len(result):
        _fail('invalid_request', 'Duplicate reason references.', 422)
    return result


def _binding(ctx, db, draft, refs, submitting=False):
    grant = coedit._read(db, auth.GRANT, ctx.sid, draft['id'])
    material = coedit._read(db, 'p10material', ctx.sid, draft['materialId'])
    if not grant or not material:
        _fail()
    sources = material[0].get('refs', [])
    if any(ref['sourceRef'] not in sources for ref in refs):
        _fail('stale_context', 'Reason is not a current draft source.', 409)
    authors = []
    for ref in refs:
        reason = coedit._read(db, 'w14reason', ctx.sid, ref['id'])
        if (not reason or reason[1] != ref['revision'] or reason[2] not in (draft['creatorId'], draft['collaboratorId'])
                or reason[0].get('status') == 'withdrawn' or not isinstance(reason[0].get('text'), str)):
            _fail('stale_context', 'Reason unavailable.', 409)
        if submitting and reason[2] != ctx.actor['owner']:
            _fail()
        authors.append(reason[2])
    if refs:
        unique = {coedit._json(ref['sourceRef']): ref['sourceRef'] for ref in refs}
        ctx.resolve(list(unique.values()))
    return {'revision': draft['revision'], 'creatorId': draft['creatorId'],
            'collaboratorId': draft['collaboratorId'], 'grantRevision': grant[1],
            'materialVersion': draft['baseMaterialVersion'], 'sourceRefs': sources, 'reasonAuthors': authors}


def _current(ctx, db, draft_id):
    draft, _ = coedit._get(db, ctx, draft_id, 'read')
    row = coedit._read(db, STATUS, ctx.sid, draft_id)
    if not row or row[2] != draft['creatorId']:
        _fail()
    value = row[0]
    if value['binding'] != _binding(ctx, db, draft, value['reasonRefs']):
        _fail('stale_context', 'Handoff context changed.', 409)
    return draft, row


def _view(draft_id, value):
    return {key: value[key] for key in ('revision', 'owner', 'dueNext', 'status', 'reasonRefs')} | {'draftId': draft_id}


def _status_version(ctx, db, draft, row):
    reason_state = []
    if row:
        for ref in row[0]['reasonRefs']:
            reason = coedit._read(db, 'w14reason', ctx.sid, ref['id'])
            reason_state.append([ref['id'], reason[1], reason[2], reason[0].get('status')] if reason else [ref['id'], None])
        try:
            _binding(ctx, db, draft, row[0]['reasonRefs'])
            reason_state.append('available')
        except Phase10Error as exc:
            if exc.code != 'stale_context': raise
            reason_state.append('stale')
    return coedit._hash([STATUS, ctx.sid, draft['id'], row[1] if row else 0,
                         _binding(ctx, db, draft, []), reason_state])


def view(ctx, draft_id):
    with store.LOCK, store.connect() as db:
        draft, _ = coedit._get(db, ctx, draft_id, 'read')
        sources = _binding(ctx, db, draft, [])['sourceRefs']
        if sources:
            ctx.resolve(sources)
        own = []
        for item in db.execute("SELECT id FROM objects WHERE kind=? AND session_id=? AND owner_id=? ORDER BY id", ('w14reason', ctx.sid, ctx.actor['owner'])):
            reason = coedit._read(db, 'w14reason', ctx.sid, item['id'])
            if reason and reason[0].get('status') != 'withdrawn' and isinstance(reason[0].get('text'), str):
                own.append({'id': item['id'], 'revision': reason[1]})
        candidates = {'ownReasons': own, 'draftSources': sources}
        row = coedit._read(db, STATUS, ctx.sid, draft_id)
        if not row:
            return {'draftId': draft_id, 'status': None, 'statusVersion': _status_version(ctx, db, draft, row)} | candidates
        if row[2] != draft['creatorId']:
            _fail()
        try:
            current = row[0]['binding'] == _binding(ctx, db, draft, row[0]['reasonRefs'])
        except Phase10Error as exc:
            if exc.code != 'stale_context': raise
            current = False
        if not current:
            return {'draftId': draft_id, 'status': 'stale', 'statusVersion': _status_version(ctx, db, draft, row)} | candidates
        # Only previously associated references can be projected: Wave 14
        # reasons do not themselves record a source association.
        own = [ref for ref, author in zip(row[0]['reasonRefs'], row[0]['binding']['reasonAuthors'])
               if author == ctx.actor['owner']]
        return _view(draft_id, row[0]) | {'statusVersion': _status_version(ctx, db, draft, row),
                                          'selectableReasonRefs': own} | candidates


def connected_scope(ctx, draft_id):
    """Project current authenticated handoff scope without draft or reason text."""
    with store.LOCK, store.connect() as db:
        draft, _ = coedit._get(db, ctx, draft_id, 'read')
        binding = _binding(ctx, db, draft, [])
        sources = binding['sourceRefs']
        identities = {(ref['sessionId'], ref['sourceId'], ref['sourceRevision']) for ref in sources}
        if len(identities) != 1:
            _fail('stale_context', 'A single current source is required for connected handoff.', 409)
        source_session, source_id, source_revision = next(iter(identities))
        ctx.resolve(sources)
        scope = {'sessionId': ctx.sid, 'actorId': ctx.actor['owner'], 'role': ctx.actor['role'],
                 'creatorId': draft['creatorId'], 'collaboratorId': draft['collaboratorId'],
                 'collaborationId': draft['id'], 'sourceId': source_id,
                 'sourceRevision': source_revision, 'draftId': draft['id'],
                 'revision': draft['revision'], 'grantGeneration': binding['grantRevision'],
                 'eligible': True}
        scope['scopeId'] = coedit._hash(['w28scope', scope, source_session, binding])
        return scope


def connected_scope_guard(ctx, draft_id, result):
    """Caller holds store.LOCK through this check, serialization and send."""
    if connected_scope(ctx, draft_id) != result:
        _fail('stale_context', 'Handoff scope changed.', 409)


def _rid(ctx, request):
    return coedit._hash([RECEIPT, ctx.sid, ctx.actor['owner'], coedit._id(request)])


def _old(db, ctx, rid, fp, draft_id, draft):
    row = coedit._read(db, RECEIPT, ctx.sid, rid)
    if row and (row[2] != ctx.actor['owner'] or row[0]['fingerprint'] != fp or row[0]['draftId'] != draft_id):
        _fail('request_conflict', 'Request ID already used.', 409)
    if row:
        _receipt_binding(ctx, db, draft, row[0])
        return row[0]['result']
    return None


def _receipt_binding(ctx, db, draft, value):
    if value['binding'] != _binding(ctx, db, draft, value['reasonRefs']):
        _fail('stale_context', 'Handoff context changed.', 409)


def _record(db, ctx, rid, fp, draft_id, result, binding, refs):
    coedit._insert(db, RECEIPT, ctx.sid, rid, ctx.actor['owner'],
                   {'fingerprint': fp, 'draftId': draft_id, 'result': result,
                    'binding': binding, 'reasonRefs': refs})


def offer(ctx, draft_id, body):
    """Creator offers/reoffers a current draft to one of its named actors."""
    coedit._fields(body, ('requestId', 'expectedRevision', 'expectedStatusVersion', 'owner', 'dueNext', 'reasonRefs'))
    coedit._id(draft_id); coedit._revision(body['expectedRevision'])
    coedit._id(body['expectedStatusVersion'])
    owner = coedit._id(body['owner']); refs = _refs(body['reasonRefs'])
    due = body['dueNext']
    if due is not None and (not isinstance(due, str) or not due.strip() or len(due) > 80 or any(ord(c) < 32 for c in due)):
        _fail('invalid_request', 'Invalid due-next label.', 422)
    fp = coedit._hash(['offer', draft_id, body]); rid = _rid(ctx, body['requestId'])
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        draft, _ = coedit._get(db, ctx, draft_id, 'read')
        if ctx.actor['owner'] != draft['creatorId'] or owner not in (draft['creatorId'], draft['collaboratorId']):
            _fail()
        old = _old(db, ctx, rid, fp, draft_id, draft)
        if old:
            return old
        if draft['revision'] != body['expectedRevision']:
            _fail('stale_revision', 'Draft changed.', 409)
        row = coedit._read(db, STATUS, ctx.sid, draft_id)
        if row and row[2] != draft['creatorId']: _fail()
        if _status_version(ctx, db, draft, row) != body['expectedStatusVersion']:
            _fail('status_conflict', 'Handoff status changed.', 409)
        binding = _binding(ctx, db, draft, refs, submitting=True)
        value = {'revision': draft['revision'], 'owner': owner, 'dueNext': due,
                 'status': 'offered', 'reasonRefs': refs, 'binding': binding}
        if row:
            db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=?',
                       (coedit._json(value), STATUS, draft_id, ctx.sid))
        else:
            coedit._insert(db, STATUS, ctx.sid, draft_id, draft['creatorId'], value)
        result = {'operation': {'requestId': body['requestId'], 'state': 'committed', 'action': 'offer', 'revision': draft['revision']}}
        _record(db, ctx, rid, fp, draft_id, result, binding, refs); db.commit(); return result


def decide(ctx, draft_id, body):
    coedit._fields(body, ('requestId', 'expectedRevision', 'expectedStatusVersion', 'action', 'reasonRefs'))
    coedit._id(draft_id); coedit._revision(body['expectedRevision']); refs = _refs(body['reasonRefs'])
    coedit._id(body['expectedStatusVersion'])
    action = body['action']
    if action not in ('accept', 'return', 'complete'):
        _fail('invalid_request', 'Invalid action.', 422)
    fp = coedit._hash(['decide', draft_id, body]); rid = _rid(ctx, body['requestId'])
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); draft, row = _current(ctx, db, draft_id)
        old = _old(db, ctx, rid, fp, draft_id, draft)
        if old: return old
        value = row[0]
        if body['expectedRevision'] != draft['revision']:
            _fail('stale_revision', 'Draft changed.', 409)
        if _status_version(ctx, db, draft, row) != body['expectedStatusVersion']:
            _fail('status_conflict', 'Handoff status changed.', 409)
        if (action == 'complete' and ctx.actor['owner'] != draft['creatorId']) or (action != 'complete' and ctx.actor['owner'] != value['owner']):
            _fail()
        allowed = {'accept': ('offered',), 'return': ('offered', 'accepted'), 'complete': ('accepted',)}
        if value['status'] not in allowed[action]:
            _fail('request_conflict', 'Handoff status changed.', 409)
        binding = _binding(ctx, db, draft, refs, submitting=True)
        value.update(status={'accept': 'accepted', 'return': 'returned', 'complete': 'completed'}[action], reasonRefs=refs, binding=binding)
        db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=?',
                   (coedit._json(value), STATUS, draft_id, ctx.sid))
        result = {'operation': {'requestId': body['requestId'], 'state': 'committed', 'action': action, 'revision': draft['revision']}}
        _record(db, ctx, rid, fp, draft_id, result, binding, refs); db.commit(); return result


def receipt(ctx, draft_id, request_id):
    with store.LOCK, store.connect() as db:
        draft, _ = coedit._get(db, ctx, draft_id, 'read')
        row = coedit._read(db, RECEIPT, ctx.sid, _rid(ctx, request_id))
        if not row or row[2] != ctx.actor['owner'] or row[0]['draftId'] != draft_id: _fail()
        _receipt_binding(ctx, db, draft, row[0])
        return row[0]['result']


def final_guard(ctx, draft_id, result, request_id=None):
    """Caller holds store.LOCK through this check, serialization and send."""
    actual = receipt(ctx, draft_id, request_id) if request_id is not None else view(ctx, draft_id)
    if actual != result: _fail('stale_context', 'Handoff changed.', 409)


def cleanup_db(db, sid, owner=None):
    if not db.in_transaction: raise ValueError('cleanup requires caller transaction')
    for kind in (STATUS, RECEIPT):
        if owner is None:
            db.execute('DELETE FROM objects WHERE kind=? AND session_id=?', (kind, sid))
        else:
            db.execute('DELETE FROM objects WHERE kind=? AND session_id=? AND owner_id=?', (kind, sid, owner))
