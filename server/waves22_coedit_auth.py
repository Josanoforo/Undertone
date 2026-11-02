"""Wave 22 coedit authority over real session credentials and stored objects.

Callers must hold store.LOCK through response serialization and invoke the
appropriate coedit read again before sending. No provider or native work here.
"""
import json
import math
import time
from . import store, waves18_segments as segments, waves22_coedit as coedit
from .phase10_common import Context, Phase10Error

GRANT = 'w22coeditgrant'


def _missing():
    raise Phase10Error('not_found', 'Coediting is unavailable.', 404)


def _row(db, kind, sid, ident):
    row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND session_id=? AND id=?', (kind, sid, ident)).fetchone()
    if not row:
        return None
    return dict(json.loads(row['data']), id=ident, _revision=row['revision'], _owner=row['owner_id'])


def _creator(ctx, db):
    ctx.check_actor()
    if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') != 'creator':
        _missing()
    row = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
    if not row or row['owner_id'] != ctx.actor['owner']:
        _missing()


def _binding(ctx, db, draft):
    segment = _row(db, segments.SEG, ctx.sid, draft['segmentId'])
    material = _row(db, 'p10material', ctx.sid, draft['materialId'])
    if (not segment or not material or segment.get('creatorId') != draft['creatorId']
            or segment['_owner'] != draft['creatorId'] or material['_owner'] != draft['creatorId']
            or segment.get('state') == 'closed' or segment.get('materialId') != draft['materialId']
            or material.get('currentVersion') != draft['baseMaterialVersion']
            or material.get('status') == 'withdrawn'):
        _missing()
    # The stored marker binds segment, source revisions and selected signals.
    live = store.get('p10material', draft['materialId'], ctx.sid)
    if not live or not live.get('w18Segment'):
        _missing()
    segments.guard_delivery(ctx.sid, live)
    ctx.resolve(live.get('refs', []))


class CoeditContext(Context):
    def authorize(self, db, draft, action):
        self.check_actor()
        if self.actor.get('sid') != self.sid:
            _missing()
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (self.sid, self.sid)).fetchone()
        if not session or session['owner_id'] != draft['creatorId']:
            _missing()
        if not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='viewer'", (self.sid, draft['collaboratorId'])).fetchone():
            _missing()
        grant = _row(db, GRANT, self.sid, draft['id'])
        if (not grant or grant['_owner'] != draft['creatorId'] or grant.get('active') is not True
                or grant.get('creatorId') != draft['creatorId']
                or grant.get('collaboratorId') != draft['collaboratorId']
                or grant.get('segmentId') != draft['segmentId']
                or grant.get('materialId') != draft['materialId']
                or grant.get('baseMaterialVersion') != draft['baseMaterialVersion']
                or type(grant.get('expiresAt')) not in (int, float) or grant['expiresAt'] <= time.time()):
            _missing()
        if self.actor['owner'] == draft['creatorId']:
            if self.actor.get('role') != 'creator': _missing()
        elif self.actor['owner'] == draft['collaboratorId']:
            if self.actor.get('role') != 'viewer': _missing()
        else:
            _missing()
        _binding(self, db, draft)
        return True


def issue(ctx, body):
    """Create one grant for a specific draft and exact current segment/material."""
    coedit._fields(body, ('draftId', 'segmentId', 'materialId', 'baseMaterialVersion', 'collaboratorId', 'expiresAt'))
    for key in ('draftId', 'segmentId', 'materialId', 'collaboratorId'): coedit._id(body[key])
    coedit._revision(body['baseMaterialVersion'])
    expiry = body['expiresAt']
    if type(expiry) not in (int, float) or not math.isfinite(expiry) or expiry <= time.time():
        raise Phase10Error('invalid_request', 'Choose a future expiry.', 422)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _creator(ctx, db)
        if body['collaboratorId'] == ctx.actor['owner'] or not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='viewer'", (ctx.sid, body['collaboratorId'])).fetchone():
            _missing()
        draft = dict(body, id=body['draftId'], creatorId=ctx.actor['owner'])
        _binding(ctx, db, draft)
        value = dict(body, creatorId=ctx.actor['owner'], active=True)
        existing = _row(db, GRANT, ctx.sid, body['draftId'])
        if existing:
            revision = existing.pop('_revision')
            owner = existing.pop('_owner')
            existing.pop('id')
            if owner != ctx.actor['owner'] or existing != value:
                raise Phase10Error('version_conflict', 'Grant already exists.', 409)
            return {'grant': dict(existing, revision=revision)}
        coedit._insert(db, GRANT, ctx.sid, body['draftId'], ctx.actor['owner'], value)
        db.commit()
        return {'grant': dict(value, revision=1)}


def guard_issued(ctx, result):
    """Recheck the exact grant and its current source rights before sending."""
    grant = result['grant']
    with store.LOCK, store.connect() as db:
        _creator(ctx, db)
        current = _row(db, GRANT, ctx.sid, grant['draftId'])
        if not current:
            _missing()
        owner = current.pop('_owner')
        revision = current.pop('_revision')
        current.pop('id')
        if owner != ctx.actor['owner'] or dict(current, revision=revision) != grant:
            _missing()
        draft = dict(current, id=grant['draftId'])
        ctx.authorize(db, draft, 'read')


def list_grants(ctx):
    with store.LOCK, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('sid') != ctx.sid: _missing()
        rows = db.execute('SELECT id,data,revision,owner_id FROM objects WHERE kind=? AND session_id=?', (GRANT, ctx.sid)).fetchall()
        result = []
        for row in rows:
            value = json.loads(row['data'])
            if ctx.actor['owner'] not in (row['owner_id'], value.get('collaboratorId')): continue
            if ctx.actor['owner'] != row['owner_id'] and (value.get('active') is not True or value.get('expiresAt', 0) <= time.time()): continue
            result.append(dict(value, revision=row['revision']))
        return {'grants': result}


def revoke(ctx, draft_id, revision):
    coedit._id(draft_id); coedit._revision(revision)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); _creator(ctx, db)
        grant = _row(db, GRANT, ctx.sid, draft_id)
        if not grant or grant['_owner'] != ctx.actor['owner']: _missing()
        if grant['_revision'] != revision: raise Phase10Error('version_conflict', 'Grant changed.', 409)
        grant.pop('_owner'); grant.pop('_revision'); grant.pop('id'); grant['active'] = False
        db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND session_id=? AND id=? AND revision=?', (coedit._json(grant), GRANT, ctx.sid, draft_id, revision))
        db.commit()
        return {'revoked': True, 'revision': revision + 1}


