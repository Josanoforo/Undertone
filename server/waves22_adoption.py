"""Creator adoption and recovery of an exact coedit approval."""
import json
import time
from . import store, phase10_studio, waves18_segments, waves22_coedit as coedit
from . import waves22_coedit_auth as authority
from .phase10_common import Phase10Error

KIND = 'w22adoption'


def _fail():
    raise Phase10Error('stale_context', 'The approved draft or material is unavailable.', 409)


def _current(ctx, snapshot, request_id, after=False):
    """Revalidate actual actor, grant, approved snapshot, material and source lineage."""
    ctx.check_actor()
    if ctx.actor.get('role') != 'creator': _fail()
    with store.connect() as db:
        authority._creator(ctx, db)
        draft_row = coedit._read(db, coedit.DRAFT, ctx.sid, snapshot['draftId'])
        grant = authority._row(db, authority.GRANT, ctx.sid, snapshot['draftId'])
        if not draft_row or not grant: _fail()
        draft = draft_row[0]
        if (draft_row[2] != ctx.actor['owner'] or draft.get('creatorId') != ctx.actor['owner']
            or draft.get('withdrawn') or draft.get('revision') != snapshot['revision']
            or draft.get('approval') != {'revision': snapshot['revision'], 'content': snapshot['content']}
            or draft.get('segmentId') != snapshot['segmentId'] or draft.get('materialId') != snapshot['materialId']
            or draft.get('baseMaterialVersion') != snapshot['baseMaterialVersion']
            or grant.get('_owner') != ctx.actor['owner'] or grant.get('active') is not True
            or grant.get('creatorId') != ctx.actor['owner'] or grant.get('collaboratorId') != draft.get('collaboratorId')
            or grant.get('segmentId') != snapshot['segmentId'] or grant.get('materialId') != snapshot['materialId']
            or grant.get('baseMaterialVersion') != snapshot['baseMaterialVersion']
            or type(grant.get('expiresAt')) not in (int, float) or grant['expiresAt'] <= time.time()
            or not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='viewer'", (ctx.sid, draft.get('collaboratorId'))).fetchone()): _fail()
        segment = authority._row(db, waves18_segments.SEG, ctx.sid, snapshot['segmentId'])
        material_row = authority._row(db, 'p10material', ctx.sid, snapshot['materialId'])
        if (not segment or segment.get('_owner') != ctx.actor['owner'] or segment.get('creatorId') != ctx.actor['owner']
            or segment.get('state') == 'closed' or segment.get('materialId') != snapshot['materialId']
            or not material_row or material_row.get('_owner') != ctx.actor['owner']): _fail()
    material = store.get('p10material', snapshot['materialId'], ctx.sid)
    if not material or material.get('status') == 'withdrawn': _fail()
    expected = snapshot['baseMaterialVersion'] + (1 if after else 0)
    if material.get('currentVersion') != expected: _fail()
    if after and (material.get('w22Adoption') != request_id or material.get('title') != snapshot['content']['title'].strip()
                  or material.get('body') != snapshot['content']['body'].strip()): _fail()
    waves18_segments.guard_delivery(ctx.sid, material)
    ctx.resolve(material.get('refs', []))
    return material


def adopt(ctx, draft_id, body):
    coedit._fields(body, ('requestId', 'expectedRevision'))
    coedit._id(body['requestId']); coedit._revision(body['expectedRevision']); coedit._id(draft_id)
    rid = coedit._hash(['w22adoption', ctx.sid, ctx.actor.get('owner'), body['requestId']])
    with store.LOCK:
        with store.connect() as db:
            row = coedit._read(db, KIND, ctx.sid, rid)
        if row:
            rec = row[0]
            if row[2] != ctx.actor.get('owner') or rec.get('draftId') != draft_id or rec.get('revision') != body['expectedRevision']:
                raise Phase10Error('request_conflict', 'Request ID already used.', 409)
            snapshot = rec['snapshot']
        else:
            snapshot = coedit.approved_for_adoption(ctx, draft_id, body['expectedRevision'])
            if any(value != value.strip() for value in snapshot['content'].values()):
                raise Phase10Error('invalid_request', 'Remove leading or trailing whitespace before adoption.', 422)
            _current(ctx, snapshot, rid)
            # Mark the exact material and durable intent in one local SQLite transaction.
            # The marker survives Studio's versioned write and distinguishes replay.
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                material = coedit._read(db, 'p10material', ctx.sid, snapshot['materialId'])
                if not material or material[2] != ctx.actor['owner'] or material[0].get('currentVersion') != snapshot['baseMaterialVersion']: _fail()
                value = material[0]; value['w22Adoption'] = rid
                count = db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='p10material' AND id=? AND session_id=? AND revision=?", (coedit._json(value), snapshot['materialId'], ctx.sid, material[1])).rowcount
                if count != 1: _fail()
                coedit._insert(db, KIND, ctx.sid, rid, ctx.actor['owner'], {'draftId':draft_id, 'revision':body['expectedRevision'], 'snapshot':snapshot, 'recoveryBinding': {'sessionId': ctx.sid, 'actorId': ctx.actor['owner'], 'draftId': draft_id, 'requestId': body['requestId']}, 'recoveryState': 'pending'})
                db.commit()
        material = store.get('p10material', snapshot['materialId'], ctx.sid)
        if not material or material.get('w22Adoption') != rid: _fail()
        record_completion = False
        if material.get('currentVersion') == snapshot['baseMaterialVersion']:
            _current(ctx, snapshot, rid)
            # Persist uncertainty before entering Studio: a crash cannot turn an
            # attempted write into a falsely reported pending operation.
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                intent = coedit._read(db, KIND, ctx.sid, rid)
                value = intent[0]
                record_completion = value.get('recoveryState') == 'pending'
                if value.get('recoveryBinding'):
                    value['recoveryState'] = 'unknown'
                    db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?', (coedit._json(value), KIND, rid, ctx.sid, intent[1]))
                db.commit()
            phase10_studio.handle('PATCH', ['studio','materials',snapshot['materialId']], {'version':snapshot['baseMaterialVersion'], 'title':snapshot['content']['title'], 'body':snapshot['content']['body'], 'refs':material['refs']}, ctx)
        _current(ctx, snapshot, rid, after=True)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            intent = coedit._read(db, KIND, ctx.sid, rid)
            value = intent[0]
            if record_completion and value.get('recoveryBinding') and value.get('recoveryState') == 'unknown':
                value['recoveryState'] = 'committed'
                db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?', (coedit._json(value), KIND, rid, ctx.sid, intent[1]))
            db.commit()
        return {'operation': {'requestId':body['requestId'], 'state':'committed', 'materialId':snapshot['materialId'], 'materialVersion':snapshot['baseMaterialVersion']+1}, 'snapshot':snapshot}, rid


def guard(ctx, result, rid):
    _current(ctx, result['snapshot'], rid, after=True)


def recovery_receipt(ctx, draft_id, request_id):
    """Read recorded metadata only; never reconcile or invoke an effect."""
    coedit._id(draft_id); coedit._id(request_id)
    rid = coedit._hash(['w22adoption', ctx.sid, ctx.actor.get('owner'), request_id])
    with store.LOCK:
        with store.connect() as db:
            authority._creator(ctx, db)
            row = coedit._read(db, KIND, ctx.sid, rid)
            if not row:
                coedit._get(db, ctx, draft_id, 'read')
                return {'operation': {'requestId': request_id, 'state': 'missing'}}
            rec = row[0]
            if row[2] != ctx.actor.get('owner') or rec.get('draftId') != draft_id:
                coedit._fail('not_found', 'Operation unavailable.', 404)
        snapshot = rec.get('snapshot')
        if not isinstance(snapshot, dict) or snapshot.get('draftId') != draft_id:
            coedit._fail('not_found', 'Operation unavailable.', 404)
        binding = {'sessionId': ctx.sid, 'actorId': ctx.actor['owner'], 'draftId': draft_id, 'requestId': request_id}
        state = rec.get('recoveryState') if rec.get('recoveryBinding') == binding else 'unknown'
        if state not in ('pending', 'unknown', 'committed'): state = 'unknown'
        # Check rights against the recorded state's exact version; unknown can
        # use either version for authorization, never for determining its state.
        if state == 'pending':
            _current(ctx, snapshot, rid)
        elif state == 'committed':
            _current(ctx, snapshot, rid, after=True)
        else:
            try:
                _current(ctx, snapshot, rid)
            except Phase10Error:
                _current(ctx, snapshot, rid, after=True)
        operation = {'requestId': request_id, 'state': state}
        if state == 'committed':
            operation.update(materialId=snapshot['materialId'], materialVersion=snapshot['baseMaterialVersion'] + 1)
        return {'operation': operation}

