"""Selected notebook flag snapshots in the existing share lifecycle.

All callers must hold Context.lock through the final serialization/send guard.
The common share readers must install the contract in WAVES26_FLAG_CONTRIBUTION
before this factory is mounted; their existing unfiltered list is insufficient.
"""
import copy
import hashlib
import json
import re

from . import store, waves26_meaning
from .phase10_common import Context, Phase10Error, parse_ref

OPERATION = 'w26_flag_share'
_ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')


def _error(code, message, status=409):
    raise Phase10Error(code, message, status)


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _error('invalid_request', 'Invalid identifier.', 422)
    return value


def _context(ctx, role=None):
    if not isinstance(ctx, Context):
        raise TypeError('production Context required')
    ctx.check_actor()
    if role and ctx.actor.get('role') != role:
        _error('forbidden', 'This action is unavailable.', 403)


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _current(ctx, share):
    """Recheck the shared snapshot, never fetch the current private note."""
    meta = share.get('meaningFlagContribution')
    if not isinstance(meta, dict) or share.get('active') is not True:
        _error('not_found', 'Contribution unavailable.', 404)
    ref = parse_ref(meta.get('ref'))
    if ref['sessionId'] != ctx.sid or meta.get('targetSessionId') != ctx.sid:
        _error('stale_context', 'Contribution unavailable.')
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND role='creator' LIMIT 1", (ctx.sid,)).fetchone():
            _error('stale_context', 'Contribution unavailable.')
    ctx.resolve([ref])
    return share


def share(ctx, selection):
    """Create exactly one snapshot and its atomic existing Phase 10 receipt.

    selection is the canonical DTO; owner and text are never caller supplied.
    """
    if not isinstance(selection, dict) or set(selection) != {'flagId', 'flagRevision', 'targetSessionId', 'consent', 'requestId'}:
        _error('invalid_request', 'Select a flag and target.', 422)
    fid = _id(selection['flagId']); request_id = _id(selection['requestId'])
    revision = selection['flagRevision']
    if type(revision) is not int or revision < 1 or selection['consent'] is not True:
        _error('consent_required', 'Select the current version and consent.', 422)
    if selection['targetSessionId'] != ctx.sid:
        _error('not_found', 'Target unavailable.', 404)
    fingerprint = _fingerprint(selection)
    with ctx.lock:
        _context(ctx, 'viewer')
        with store.connect() as db:
            old = db.execute('SELECT fingerprint,state,result FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?', (ctx.sid, ctx.actor['owner'], OPERATION, request_id)).fetchone()
        if old:
            if old['fingerprint'] != fingerprint:
                _error('request_conflict', 'Request ID already used.')
            if old['state'] != 'complete' or not old['result']:
                _error('operation_unresolved', 'The original outcome is unavailable.')
            return read_current(ctx, json.loads(old['result'])['shareId'])
        item = waves26_meaning.get_flag(ctx, fid)
        if item['revision'] != revision:
            _error('version_conflict', 'Flag changed; select it again.')
        ref = parse_ref(item['ref'])
        # Cross-session targets need their own current grant authority, which this
        # adapter intentionally does not create or infer.
        if ref['sessionId'] != ctx.sid:
            _error('stale_context', 'Target source unavailable.')
        rows = ctx.resolve([ref]); source = rows[0]['source']
        with store.connect() as db:
            if not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND role='creator' LIMIT 1", (ctx.sid,)).fetchone():
                _error('not_found', 'Target unavailable.', 404)
            oid = store.ident()
            citation = {'sourceId': ref['sourceId'], 'sourceRevision': ref['sourceRevision'], 'title': str(source.get('title', 'Source'))[:200], 'at': source.get('at'), 'excerpt': ''}
            value = {'id': oid, 'ownerId': ctx.actor['owner'], 'summary': item['note'], 'citations': [citation], 'allowPublicDerivative': False, 'includeImage': False, 'image': None, 'sourceIds': [ref['sourceId']], 'sourceRevisions': {ref['sourceId']: ref['sourceRevision']}, 'active': True, 'createdAt': store.now(), 'meaningFlagContribution': {'flagId': fid, 'flagRevision': revision, 'field': item['field'], 'ref': ref, 'targetSessionId': ctx.sid}}
            db.execute('BEGIN IMMEDIATE')
            # Protect the selected version inside the same transaction as receipt.
            selected = db.execute("SELECT revision FROM objects WHERE kind='notebook' AND id=? AND session_id=? AND owner_id=?", (fid, ctx.sid, ctx.actor['owner'])).fetchone()
            if not selected or selected['revision'] != revision:
                _error('version_conflict', 'Flag changed; select it again.')
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)', ('share', oid, ctx.sid, ctx.actor['owner'], 1, json.dumps(value, ensure_ascii=False), store.now()))
            db.execute('INSERT INTO phase10_receipts VALUES(?,?,?,?,?,?,?,?,?)', (ctx.sid, ctx.actor['owner'], OPERATION, request_id, fingerprint, 'complete', 201, json.dumps({'shareId': oid}), json.dumps([ref])))
            db.commit()
        return read_current(ctx, oid)


def read_current(ctx, share_id):
    from .http import public_share
    _id(share_id)
    with ctx.lock:
        _context(ctx)
        value = store.get('share', share_id, ctx.sid)
        if not value or (ctx.actor.get('role') != 'creator' and value.get('ownerId') != ctx.actor.get('owner')):
            _error('not_found', 'Contribution unavailable.', 404)
        _current(ctx, value)
        return public_share(value, creator=ctx.actor.get('role') == 'creator')


def receipt(ctx, request_id):
    _id(request_id)
    with ctx.lock:
        _context(ctx, 'viewer')
        with store.connect() as db:
            row = db.execute('SELECT state,result FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?', (ctx.sid, ctx.actor['owner'], OPERATION, request_id)).fetchone()
        if not row:
            return {'state': 'unknown', 'shareId': None}
        if row['state'] != 'complete' or not row['result']:
            return {'state': row['state'], 'shareId': None}
        oid = json.loads(row['result'])['shareId']
        read_current(ctx, oid)
        return {'state': 'complete', 'shareId': oid}


def revoke(ctx, share_id):
    from .http import withdraw_share
    _id(share_id)
    with ctx.lock:
        _context(ctx, 'viewer')
        value = store.get('share', share_id, ctx.sid)
        if not value or value.get('ownerId') != ctx.actor['owner'] or not isinstance(value.get('meaningFlagContribution'), dict):
            _error('not_found', 'Contribution unavailable.', 404)
        withdraw_share(ctx.sid, value)
        ctx.handler.invalidate_share(ctx.sid, share_id)
        return {'ok': True}


def final_guard(ctx, share_id, projected):
    current = read_current(ctx, share_id)
    if current != projected:
        _error('stale_context', 'Contribution changed or is unavailable.')
    return copy.deepcopy(current)
