"""Creator-selected, current-rights association of ASR and visual evidence."""

import copy
import hashlib
import json
import re

from . import source_translation_delivery, store, waves23_moment_index
from .phase10_common import Context, Phase10Error, parse_ref


def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        _fail('invalid_request', 'Invalid identifier.', 422)
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _current(ctx, asr_ref, frame_ref, region_id):
    if not isinstance(ctx, Context):
        raise TypeError('production Context required')
    ctx.check_actor()
    asr_ref, frame_ref = parse_ref(asr_ref), parse_ref(frame_ref)
    _id(region_id)
    if asr_ref['sessionId'] != ctx.sid or frame_ref['sessionId'] != ctx.sid:
        _fail('stale_context', 'Selection unavailable.')
    source = source_translation_delivery.private_source(ctx, asr_ref['momentId'], asr_ref['sourceRevision'], 'en')
    if source['ref'] != asr_ref:
        _fail('stale_context', 'Selection unavailable.')
    # The ordinary destination reader scopes receipts to the current actor.
    # Refuse multiple matching evidence entries instead of silently picking one.
    matches = [item for _, item in waves23_moment_index._visual_candidates(ctx, frame_ref['startMs'], frame_ref['endMs'])
               if item['ref'] == frame_ref and item['regionId'] == region_id]
    if len(matches) != 1:
        _fail('stale_context', 'Selected visual evidence unavailable or ambiguous.')
    return waves23_moment_index.resolve_destination(ctx, frame_ref, region_id)


def _load(db, sid, association_id):
    row = db.execute("SELECT owner_id,revision,data FROM objects WHERE kind='w26visualassociation' AND session_id=? AND id=?", (sid, association_id)).fetchone()
    if row is None:
        _fail('not_found', 'Association unavailable.', 404)
    return row, json.loads(row['data'])


def read(ctx, association_id):
    _id(association_id)
    with ctx.lock:
        ctx.check_actor()
        with store.connect() as db:
            row, value = _load(db, ctx.sid, association_id)
        if value['state'] != 'active':
            _fail('not_found', 'Association unavailable.', 404)
        evidence = _current(ctx, value['asrRef'], value['frameRef'], value['regionId'])
        if _hash(evidence) != value['evidenceHash']:
            _fail('stale_context', 'Selected visual evidence changed.')
        return {'id': association_id, 'revision': row['revision'], 'asrRef': copy.deepcopy(value['asrRef']),
                'frameRef': copy.deepcopy(value['frameRef']), 'regionId': value['regionId'],
                'association': {'kind': 'creator_selected', 'creatorId': row['owner_id']},
                'visual': {'state': 'available', 'evidence': evidence, 'certainty': 'unknown'}}


def bind(ctx, asr_ref, frame_ref, region_id, request_id, association_id=None, revision=None):
    """Create or revise an explicit selection; exact replay retains its result."""
    _id(request_id)
    if association_id is not None:
        _id(association_id)
        if type(revision) is not int or revision < 1:
            _fail('invalid_request', 'An exact revision is required.', 422)
    elif revision is not None:
        _fail('invalid_request', 'Unexpected revision.', 422)
    asr_ref, frame_ref = parse_ref(asr_ref), parse_ref(frame_ref)
    payload = {'asrRef': asr_ref, 'frameRef': frame_ref, 'regionId': _id(region_id),
               'associationId': association_id, 'revision': revision}
    fingerprint = _hash(payload)
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            _fail('forbidden', 'Creator selection required.', 403)
        receipt_id = _hash([ctx.sid, ctx.actor['owner'], request_id])
        with store.connect() as db:
            prior = db.execute("SELECT data FROM objects WHERE kind='w26visualassocreceipt' AND id=? AND session_id=? AND owner_id=?", (receipt_id, ctx.sid, ctx.actor['owner'])).fetchone()
        if prior and json.loads(prior['data'])['fingerprint'] != fingerprint:
            _fail('request_conflict', 'The request is bound to another selection.')
        evidence = _current(ctx, asr_ref, frame_ref, region_id)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            receipt = db.execute("SELECT data FROM objects WHERE kind='w26visualassocreceipt' AND id=? AND session_id=? AND owner_id=?", (receipt_id, ctx.sid, ctx.actor['owner'])).fetchone()
            if receipt:
                saved = json.loads(receipt['data'])
                row, value = _load(db, ctx.sid, saved['id'])
                if saved['fingerprint'] != fingerprint or row['revision'] != saved['revision'] or value['state'] != 'active':
                    _fail('request_conflict', 'The request or committed selection changed.')
                result_id = saved['id']
            else:
                value = {'asrRef': asr_ref, 'frameRef': frame_ref, 'regionId': region_id,
                         'evidenceHash': _hash(evidence), 'state': 'active'}
                if association_id is None:
                    result_id, next_revision = store.ident(), 1
                    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',
                               ('w26visualassociation', result_id, ctx.sid, ctx.actor['owner'], 1, json.dumps(value), store.now()))
                else:
                    row, old = _load(db, ctx.sid, association_id)
                    if row['owner_id'] != ctx.actor['owner'] or row['revision'] != revision or old['state'] != 'active':
                        _fail('version_conflict', 'Selection changed or unavailable.')
                    # Revisions are allowed only while the original selection remains current.
                    if _hash(_current(ctx, old['asrRef'], old['frameRef'], old['regionId'])) != old['evidenceHash']:
                        _fail('stale_context', 'Original selection changed.')
                    result_id, next_revision = association_id, revision + 1
                    db.execute("UPDATE objects SET revision=?,data=? WHERE kind='w26visualassociation' AND id=? AND session_id=? AND revision=?", (next_revision, json.dumps(value), result_id, ctx.sid, revision))
                rec = {'fingerprint': fingerprint, 'id': result_id, 'revision': next_revision}
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)', ('w26visualassocreceipt', receipt_id, ctx.sid, ctx.actor['owner'], 1, json.dumps(rec), store.now()))
            db.commit()
        return read(ctx, result_id)


def final_guard(ctx, association_id, response):
    current = read(ctx, association_id)
    if current != response:
        _fail('stale_context', 'Association changed or unavailable.')
    return current


def list_current(ctx, asr_ref):
    """Bounded current-rights discovery for one exact already-selected source.

    Read only: never creates an association, visual receipt or permission.
    Each candidate uses the same authority as an individually selected read.
    """
    asr_ref = parse_ref(asr_ref)
    with ctx.lock:
        source = source_translation_delivery.private_source(ctx, asr_ref['momentId'], asr_ref['sourceRevision'], 'en')
        if source['ref'] != asr_ref:
            _fail('stale_context', 'Selection unavailable.')
        with ctx.store.connect() as db:
            rows = db.execute("SELECT id,data FROM objects WHERE kind='w26visualassociation' AND session_id=? ORDER BY id LIMIT 200", (ctx.sid,)).fetchall()
        items = []
        for row in rows:
            try:
                saved = json.loads(row['data'])
                if saved.get('asrRef') != asr_ref:
                    continue
                current = read(ctx, row['id'])
                items.append({'associationId': current['id'], 'revision': current['revision'],
                              'asrRef': current['asrRef'], 'frameRef': current['frameRef'],
                              'regionId': current['regionId'],
                              'description': current['visual']['evidence']['explanation'],
                              'certainty': 'unknown'})
            except (Phase10Error, TypeError, ValueError, KeyError):
                continue
        return {'ref': copy.deepcopy(asr_ref), 'items': items, 'coverage': 'bounded_current_actor_readable_only'}


def final_guard_list(ctx, asr_ref, response):
    current = list_current(ctx, asr_ref)
    if current != response:
        _fail('stale_context', 'Visual references changed before delivery.')
    return current


def lifecycle(ctx, association_id, revision, request_id):
    """Withdraw a creator selection, with durable exact replay and no grant change."""
    _id(association_id); _id(request_id)
    if type(revision) is not int or revision < 1:
        _fail('invalid_request', 'An exact revision is required.', 422)
    fingerprint = _hash(['withdraw', association_id, revision])
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            _fail('forbidden', 'Creator selection required.', 403)
        rid = _hash([ctx.sid, ctx.actor['owner'], request_id])
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            receipt = db.execute("SELECT data FROM objects WHERE kind='w26visualassocreceipt' AND id=? AND session_id=? AND owner_id=?", (rid, ctx.sid, ctx.actor['owner'])).fetchone()
            row, value = _load(db, ctx.sid, association_id)
            if row['owner_id'] != ctx.actor['owner']:
                _fail('not_found', 'Association unavailable.', 404)
            if receipt:
                saved = json.loads(receipt['data'])
                if saved['fingerprint'] != fingerprint or row['revision'] != saved['revision'] or value['state'] != 'withdrawn':
                    _fail('request_conflict', 'The request or selection changed.')
            else:
                if row['revision'] != revision or value['state'] != 'active':
                    _fail('version_conflict', 'Selection changed or unavailable.')
                value['state'] = 'withdrawn'
                db.execute("UPDATE objects SET revision=?,data=? WHERE kind='w26visualassociation' AND id=? AND session_id=? AND revision=?", (revision + 1, json.dumps(value), association_id, ctx.sid, revision))
                saved = {'fingerprint': fingerprint, 'id': association_id, 'revision': revision + 1}
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)', ('w26visualassocreceipt', rid, ctx.sid, ctx.actor['owner'], 1, json.dumps(saved), store.now()))
            db.commit()
        return {'id': association_id, 'revision': saved['revision'], 'state': 'withdrawn'}


def handle(handler, sid, actor, method, parts):
    """Optional PRIMARY route binding; handler owns final lock and send."""
    ctx = Context(handler, sid, actor)
    if method == 'POST' and parts == ['list']:
        body = handler.body()
        if not isinstance(body, dict) or set(body) != {'ref'}:
            _fail('invalid_request', 'Select one exact source fragment.', 422)
        # The existing HTTP mount holds store.LOCK through this handler, the
        # re-projection below, serialization and send. No HTTP edit is needed.
        with ctx.lock:
            result = list_current(ctx, body['ref'])
            final_guard_list(ctx, body['ref'], result)
            return 200, result
    if method == 'POST' and parts == ['bind']:
        body = handler.body()
        if not isinstance(body, dict) or not {'asrRef', 'frameRef', 'regionId', 'requestId'} <= set(body) or set(body) - {'asrRef', 'frameRef', 'regionId', 'requestId', 'associationId', 'revision'}:
            _fail('invalid_request', 'An explicit selection is required.', 422)
        result = bind(ctx, body['asrRef'], body['frameRef'], body['regionId'], body['requestId'], body.get('associationId'), body.get('revision'))
    elif method == 'GET' and len(parts) == 1:
        result = read(ctx, parts[0])
    elif method == 'POST' and len(parts) == 2 and parts[1] == 'withdraw':
        body = handler.body()
        if not isinstance(body, dict) or set(body) != {'revision', 'requestId'}:
            _fail('invalid_request', 'An exact revision is required.', 422)
        return 200, lifecycle(ctx, parts[0], body['revision'], body['requestId'])
    else:
        _fail('not_found', 'Association operation unavailable.', 404)
    handler._w26_visual_association_binding = (sid, dict(actor), result['id'], copy.deepcopy(result))
    return 200, result
