"""Atomic creator-owned Studio chapter commits and original-request receipts.

The integrator holds ctx.lock through call, guard, serialization and send.
"""
import copy
import json
from . import store, phase10_studio as studio, waves27_chapter_draft as chapter
from . import waves22_coedit as common, waves22_coedit_auth as auth
from .phase10_common import Phase10Error

KIND = 'w22chapterreceipt'

def _unavailable():
    raise Phase10Error('stale_context', 'The chapter draft is unavailable.', 409)

def _identity(ctx):
    with store.connect() as db:
        auth._creator(ctx, db)

def _receipt_id(ctx, request_id):
    return common._hash([KIND, ctx.sid, ctx.actor['owner'], common._id(request_id)])

def _current(ctx, result):
    _identity(ctx)
    with store.connect() as db:
        row = common._read(db, 'p10material', ctx.sid, result['materialId'])
    if (not row or row[2] != ctx.actor['owner'] or row[1] != result['objectRevision']
            or row[0].get('currentVersion') != result['version']
            or row[0].get('refs') != result['refs'] or row[0].get('status') == 'withdrawn'):
        _unavailable()
    studio._guard_material(ctx, row[0])
    studio.resolve_material_refs(ctx, result['refs'])

def commit(ctx, body):
    """Commit exact chapter intent; baseRevision='create' or positive object revision.

    Edit requires materialId and version. Creation requires both to be None.
    No caller-provided prepared data is trusted; it is rebuilt under the lock.
    """
    common._fields(body, ('requestId', 'baseRevision', 'materialId', 'version', 'title', 'chapters'))
    rid = _receipt_id(ctx, body['requestId'])
    create = body['baseRevision'] == 'create'
    if create:
        if body['materialId'] is not None or body['version'] is not None:
            common._fail('invalid_request', 'Invalid creation target.', 422)
    else:
        common._id(body['materialId'])
        for name in ('baseRevision', 'version'):
            common._revision(body[name])
            if body[name] < 1: common._fail('invalid_request', 'Invalid revision.', 422)
    fingerprint = common._hash(body)
    with ctx.lock:
        _identity(ctx)
        with store.connect() as db:
            old = common._read(db, KIND, ctx.sid, rid)
        if old:
            if old[2] != ctx.actor['owner'] or old[0].get('fingerprint') != fingerprint:
                common._fail('request_conflict', 'Request ID already used.')
            result = copy.deepcopy(old[0]['result'])
            _current(ctx, result)
            return result
        if create:
            material = chapter.assemble(ctx, body['title'], body['chapters'])
            material_id = common._hash(['w22chaptermaterial', ctx.sid, ctx.actor['owner'], body['requestId']])
            material['id'] = material_id
            revision, version = 1, 1
        else:
            material_id = body['materialId']
            with store.connect() as db:
                row = common._read(db, 'p10material', ctx.sid, material_id)
            if not row or row[2] != ctx.actor['owner'] or row[1] != body['baseRevision']:
                common._fail('version_conflict', 'The material changed.')
            if row[0].get('status') == 'withdrawn' or row[0].get('format') != 'chapter': _unavailable()
            material = chapter.replacement(ctx, row[0], body['version'], body['title'], body['chapters'])
            revision, version = row[1] + 1, body['version'] + 1
        result = {'requestId': body['requestId'], 'state':'committed', 'materialId':material_id,
                  'objectRevision':revision, 'version':version, 'refs':copy.deepcopy(material['refs'])}
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if create:
                if db.execute("SELECT 1 FROM objects WHERE kind='p10material' AND id=?", (material_id,)).fetchone():
                    common._fail('version_conflict', 'The material already exists.')
                common._insert(db, 'p10material', ctx.sid, material_id, ctx.actor['owner'], material)
            else:
                n = db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='p10material' AND id=? AND session_id=? AND owner_id=? AND revision=?",
                    (common._json(material), material_id, ctx.sid, ctx.actor['owner'], body['baseRevision'])).rowcount
                if n != 1: common._fail('version_conflict', 'The material changed.')
            common._insert(db, KIND, ctx.sid, rid, ctx.actor['owner'], {'fingerprint':fingerprint, 'result':result})
            db.commit()
        return result

def receipt(ctx, request_id):
    """Read the original committed metadata, or honestly report unknown."""
    with ctx.lock:
        _identity(ctx)
        with store.connect() as db:
            row = common._read(db, KIND, ctx.sid, _receipt_id(ctx, request_id))
        if not row:
            return {'requestId':request_id, 'state':'unknown'}
        if row[2] != ctx.actor['owner']: _unavailable()
        result = copy.deepcopy(row[0]['result'])
        _current(ctx, result)
        return result

def recover(ctx, material_id, revision, version):
    """Read a unique original receipt for an exact, currently accessible material."""
    common._id(material_id)
    for number in (revision, version):
        common._revision(number)
        if number < 1: common._fail('invalid_request', 'Invalid revision.', 422)
    with ctx.lock:
        _identity(ctx)
        with store.connect() as db:
            material = common._read(db, 'p10material', ctx.sid, material_id)
            if (not material or material[2] != ctx.actor['owner'] or
                    material[1] != revision or material[0].get('currentVersion') != version or
                    material[0].get('format') != 'chapter'):
                _unavailable()
            target = {'materialId': material_id, 'objectRevision': revision,
                      'version': version, 'refs': material[0].get('refs')}
            _current(ctx, target)
            rows = db.execute('SELECT id,data FROM objects WHERE kind=? AND session_id=? AND owner_id=?',
                              (KIND, ctx.sid, ctx.actor['owner'])).fetchall()
        matches = []
        for row in rows:
            try:
                result = json.loads(row['data'])['result']
                if (not isinstance(result, dict) or result.get('materialId') != material_id or
                        type(result.get('objectRevision')) is not int or result['objectRevision'] != revision or
                        type(result.get('version')) is not int or result['version'] != version):
                    continue
                if (set(result) != {'requestId', 'state', 'materialId', 'objectRevision', 'version', 'refs'} or
                        result['state'] != 'committed' or row['id'] != _receipt_id(ctx, result['requestId']) or
                        result['refs'] != target['refs']):
                    _unavailable()
                matches.append(result)
            except (KeyError, TypeError, ValueError):
                _unavailable()
        if not matches: return {'state': 'unknown'}
        if len(matches) != 1: return {'state': 'ambiguous'}
        _current(ctx, matches[0])
        return copy.deepcopy(matches[0])

def guard_recovery(ctx, material_id, revision, version, result):
    """Repeat the complete uniqueness and rights fence before final send."""
    with ctx.lock:
        if recover(ctx, material_id, revision, version) != result:
            _unavailable()

def guard(ctx, result):
    """Repeat current-rights and exact committed result fence before final send."""
    with ctx.lock:
        if result.get('state') == 'unknown':
            if receipt(ctx, result.get('requestId')) != result: _unavailable()
        elif receipt(ctx, result.get('requestId')) != result:
            _unavailable()
