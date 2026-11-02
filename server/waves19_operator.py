"""Preparation-only drafts over segment/material objects; no credential or delivery authority."""
import hashlib
import json
import re
from . import store
from .phase10_common import Phase10Error

CANDIDATE = 'w19operatorcandidate'
RECEIPT = 'w19operatorreceipt'


def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _read(db, kind, oid, sid):
    row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (kind, oid, sid)).fetchone()
    if not row:
        return None
    result = json.loads(row['data'])
    result['_revision'] = row['revision']
    result['_owner'] = row['owner_id']
    return result


def _insert(db, kind, oid, sid, owner, value):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
               (kind, oid, sid, owner, _json(value), store.now()))


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        _fail('invalid_request', 'Invalid identifier.', 422)
    return value


def _authority(db, sid, actor, capability, authorize):
    # The callback is the sole credential/grant authority. It must revalidate in
    # this transaction on every invocation, including receipt replay.
    if not isinstance(actor, dict) or actor.get('sid') != sid or actor.get('role') not in ('creator', 'prepare') or not isinstance(actor.get('owner'), str) or not actor['owner']:
        _fail('forbidden', 'Preparation access required.', 403)
    creator = authorize(db, sid, actor, capability, 'prepare')
    if not isinstance(creator, str) or not creator or (actor['role'] == 'creator' and creator != actor['owner']):
        _fail('forbidden', 'Preparation access required.', 403)
    return creator


def _segment(db, sid, creator, segment_id):
    seg = _read(db, 'w18segment', segment_id, sid)
    if not seg or seg.get('_owner') != creator or seg.get('creatorId') != creator or seg.get('state') == 'closed':
        _fail('not_found', 'Segment unavailable.', 404)
    material = _read(db, 'p10material', seg.get('materialId'), sid)
    if not material or material.get('_owner') != creator:
        _fail('not_found', 'Segment material unavailable.', 404)
    return seg, material


def _candidate_id(sid, segment_id):
    return _hash(['w19candidate', sid, segment_id])


def _project_candidate(candidate, material):
    if not candidate:
        return {'revision': 0, 'title': '', 'body': '', 'baseMaterialVersion': material.get('currentVersion')}
    return {key: candidate[key] for key in ('revision', 'title', 'body', 'baseMaterialVersion')}


def state(sid, actor, capability, authorize):
    """Return a safe preparation projection. authorize is supplied by primary."""
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        creator = _authority(db, sid, actor, capability, authorize)
        rows = db.execute("SELECT id FROM objects WHERE kind='w18segment' AND session_id=? AND owner_id=? ORDER BY created_at,id", (sid, creator)).fetchall()
        segments = []
        for row in rows:
            try:
                seg, material = _segment(db, sid, creator, row['id'])
            except Phase10Error:
                continue
            cue = _read(db, 'w15cue', seg.get('cueId'), sid) if seg.get('cueId') else None
            candidate = _read(db, CANDIDATE, _candidate_id(sid, seg['id']), sid)
            if candidate and (candidate.get('_owner') != creator or candidate.get('materialId') != material['id']):
                continue
            segments.append({'segmentId': seg['id'], 'segmentRevision': seg['_revision'],
                             'materialId': material['id'], 'materialVersion': material.get('currentVersion'),
                             'approvedVersion': material.get('approvedVersion'),
                             'cue': {'id': cue['id'], 'revision': cue['_revision'], 'state': cue.get('status', cue.get('state')),
                                     'materialVersion': cue.get('materialVersion')} if cue and cue.get('_owner') == creator else None,
                             'candidate': _project_candidate(candidate, material)})
        db.commit()
    return {'segments': segments, 'current': segments[0]['segmentId'] if segments else None,
            'next': segments[1]['segmentId'] if len(segments) > 1 else None,
            'ordering': 'creation_order'}


def edit(sid, actor, capability, authorize, segment_id, body):
    """Persist a candidate, never mutate editorial material or a cue."""
    _id(segment_id)
    if not isinstance(body, dict) or set(body) != {'requestId', 'revision', 'title', 'body'}:
        _fail('invalid_request', 'Invalid draft fields.', 422)
    request = _id(body['requestId'])
    if type(body['revision']) is not int or body['revision'] < 0:
        _fail('invalid_request', 'Invalid draft revision.', 422)
    for name, limit in (('title', 200), ('body', 12000)):
        value = body[name]
        if not isinstance(value, str) or not value.strip() or len(value) > limit or '\x00' in value:
            _fail('invalid_request', 'Invalid draft text.', 422)
    fingerprint = _hash([segment_id, body])
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        creator = _authority(db, sid, actor, capability, authorize)
        seg, material = _segment(db, sid, creator, segment_id)
        cid = _candidate_id(sid, segment_id)
        rid = _hash(['w19receipt', sid, actor['owner'], request])
        receipt = _read(db, RECEIPT, rid, sid)
        candidate = _read(db, CANDIDATE, cid, sid)
        if candidate and (candidate.get('_owner') != creator or candidate.get('materialId') != material['id']):
            _fail('not_found', 'Draft unavailable.', 404)
        if receipt:
            if receipt.get('fingerprint') != fingerprint or receipt.get('_owner') != actor['owner']:
                _fail('request_conflict', 'Request ID already used.', 409)
            db.commit()
            return 200, {'candidate': _project_candidate(candidate, material), 'replayed': True}
        revision = candidate['revision'] if candidate else 0
        if revision != body['revision']:
            current = _project_candidate(candidate, material)
            db.commit()
            return 409, {'error': {'code': 'version_conflict', 'message': 'The draft changed.'},
                         'candidate': current, 'submitted': {'title': body['title'], 'body': body['body']}}
        value = {'id': cid, 'segmentId': seg['id'], 'materialId': material['id'],
                 'baseMaterialVersion': candidate['baseMaterialVersion'] if candidate else material.get('currentVersion'),
                 'revision': revision + 1, 'title': body['title'], 'body': body['body']}
        if candidate:
            if candidate.get('_owner') != creator or candidate.get('materialId') != material['id']:
                _fail('not_found', 'Draft unavailable.', 404)
            changed = db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?',
                                 (_json(value), CANDIDATE, cid, sid, candidate['_revision'])).rowcount
            if changed != 1:
                _fail('version_conflict', 'The draft changed.', 409)
        else:
            _insert(db, CANDIDATE, cid, sid, creator, value)
        _insert(db, RECEIPT, rid, sid, actor['owner'], {'id': rid, 'fingerprint': fingerprint})
        db.commit()
        return 200, {'candidate': _project_candidate(value, material), 'replayed': False}
