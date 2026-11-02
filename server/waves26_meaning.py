"""Private, source-bound meaning inspection; no generation or delivery effects."""
import copy
import hashlib
import json
import re

from . import phase12_jobs, source_translation_delivery, store, waves17_terminology, waves23_moment_index, waves26_visual_association
from .phase10_common import Context, Phase10Error, parse_ref


def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        _fail('invalid_request', 'Invalid request identifier.', 422)
    return value


def _visual_origin(ctx, evidence):
    """Keep receipt attribution lost by the search excerpt projection.

    Never infer an actual observation, creator authorship or quality from text.
    The same current-rights projector used by visual search guards each receipt.
    """
    from . import waves21_visual_runtime as visual
    origins = set()
    with ctx.store.connect() as db:
        rows = db.execute("SELECT result FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND state='complete' LIMIT 201",
                          (ctx.sid, ctx.actor['owner'], visual.OPERATION)).fetchall()
    if len(rows) > 200:
        return 'unknown'
    key = {'inference': 'inferences', 'observation': 'observations', 'ocr': 'ocr'}.get(evidence.get('evidenceKind'))
    if key is None:
        return 'unknown'
    for row in rows:
        try:
            receipt = visual._project(ctx, json.loads(row['result']))
            if receipt['frame']['ref'] != evidence['ref']:
                continue
            for region in receipt['regions']:
                if region['regionId'] != evidence['regionId']:
                    continue
                for entry in region.get(key, []):
                    if entry.get('text', '').strip()[:2000] != evidence.get('explanation'):
                        continue
                    provider = entry.get('provider')
                    origins.add('fixture' if provider == 'fixture' else 'provider_output' if provider and provider != 'user' else 'unknown')
        except (Phase10Error, TypeError, ValueError, KeyError):
            continue
    return next(iter(origins)) if len(origins) == 1 else 'unknown'


def inspect(ctx, ref, target_language, translation_request_id=None, region_id=None, association_id=None):
    """Read a selected ASR moment and optional exact completed actor receipt.

    Caller holds ctx.lock through final serialization; call guard_final immediately
    before sending. Cross-source evidence requires an explicit association ID.
    """
    if not isinstance(ctx, Context):
        raise TypeError('production Context required')
    ref = parse_ref(ref)
    if target_language not in ('en', 'es'):
        _fail('invalid_request', 'Invalid target language.', 422)
    if translation_request_id is not None:
        _id(translation_request_id)
    if association_id is not None and region_id is not None:
        _fail('invalid_request', 'Select one visual evidence source.', 422)
    with ctx.lock:
        source = source_translation_delivery.private_source(ctx, ref['momentId'], ref['sourceRevision'], target_language)
        if source['ref'] != ref:
            _fail('stale_context', 'Source unavailable.')
        row = ctx.resolve([ref])[0]
        result = {'source': {'ref': copy.deepcopy(ref), 'text': source['text'],
                             'language': source['sourceLanguage'], 'certainty': 'unknown',
                             'provenance': 'received_asr', 'humanReview': 'unassessed',
                             'alignment': copy.deepcopy(row['moment'].get('alignment'))},
                  'translation': {'state': 'unavailable'}, 'visual': {'state': 'unavailable'},
                  'destination': {'kind': 'moment', 'ref': copy.deepcopy(ref)}}
        if translation_request_id is not None:
            job = phase12_jobs.check_job(ctx.handler, ctx.sid, ctx.actor, translation_request_id)
            if job['kind'] == 'translation' and job['state'] == 'complete':
                payload = json.loads(job['payload']); saved_ref = json.loads(job['ref'])
                data = json.loads(job['result']) if job['result'] else None
                if (saved_ref != ref or payload.get('targetLanguage') != target_language or
                    payload.get('sourceLanguage') != source['sourceLanguage'] or
                    not isinstance(data, dict) or data.get('original') != source['text'] or
                    data.get('targetLanguage') != target_language or
                    not isinstance(data.get('translation'), str)):
                    _fail('stale_context', 'Translation unavailable.')
                waves17_terminology.guard(job)
                result['translation'] = {'state': 'available', 'requestId': translation_request_id,
                                         'text': data['translation'], 'language': target_language,
                                         'certainty': 'unknown', 'sourceCertainty': 'unknown',
                                         'provenance': ('fixture' if job['transport'] == 'fixture' or data.get('provider') == 'fixture' else
                                                        ('creator_text' if job['role'] == 'creator' else 'user_text') if job['transport'] == 'local_user_correction' else 'provider_output'),
                                         'humanReview': 'unassessed',
                                         'uncertainty': copy.deepcopy(data.get('uncertainty'))}
        if association_id is not None:
            _id(association_id)
            association = waves26_visual_association.read(ctx, association_id)
            if association['asrRef'] != ref:
                _fail('stale_context', 'Visual association unavailable.')
            result['visual'] = {'state': 'available', 'associationId': association['id'],
                                'revision': association['revision'],
                                'association': copy.deepcopy(association['association']),
                                'frameRef': copy.deepcopy(association['frameRef']),
                                'regionId': association['regionId'],
                                'evidence': copy.deepcopy(association['visual']['evidence']),
                                'certainty': association['visual']['certainty']}
        elif region_id is not None:
            _id(region_id)
            try:
                visual = waves23_moment_index.resolve_destination(ctx, ref, region_id)
                result['visual'] = {'state': 'available', 'evidence': visual}
            except Phase10Error as exc:
                if exc.code not in ('not_found', 'stale_context'):
                    raise
        if result['visual']['state'] == 'available':
            result['visual']['descriptionProvenance'] = _visual_origin(ctx, result['visual']['evidence'])
            result['visual']['humanReview'] = 'unassessed'
            result['visual']['certainty'] = 'unknown'
        return result


def guard_final(ctx, request, response):
    current = inspect(ctx, request['ref'], request['targetLanguage'],
                      request.get('translationRequestId'), request.get('regionId'), request.get('associationId'))
    if current != response:
        _fail('stale_context', 'Inspection changed or is unavailable.')
    return current


def _key(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def flag(ctx, ref, field, note, request_id):
    """Create an actor-owned notebook item and atomic idempotency receipt."""
    ref = parse_ref(ref); _id(request_id)
    if field not in ('source', 'translation', 'visual') or not isinstance(note, str) or not note.strip() or len(note) > 1000 or '\x00' in note:
        _fail('invalid_request', 'Select a field and enter a bounded note.', 422)
    payload = {'ref': ref, 'field': field, 'note': note}
    fingerprint = _key(payload)
    rid = _key(ctx.sid, ctx.actor['owner'], request_id)
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'viewer':
            _fail('forbidden', 'Viewer access required.', 403)
        ctx.resolve([ref])
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            receipt = db.execute("SELECT data FROM objects WHERE kind='w26meaningreceipt' AND id=? AND session_id=? AND owner_id=?", (rid, ctx.sid, ctx.actor['owner'])).fetchone()
            if receipt:
                saved = json.loads(receipt['data'])
                if saved['fingerprint'] != fingerprint:
                    _fail('request_conflict', 'Request ID already used.')
                oid = saved['itemId']
                existing = db.execute("SELECT revision FROM objects WHERE kind='notebook' AND id=? AND session_id=? AND owner_id=?", (oid, ctx.sid, ctx.actor['owner'])).fetchone()
                if not existing or existing['revision'] != saved['itemRevision']:
                    _fail('request_conflict', 'The committed result is no longer available.')
            else:
                oid = store.ident()
                value = {'id': oid, 'ownerId': ctx.actor['owner'], 'kind': 'reference', 'text': note,
                         'reference': {'type': 'source', 'id': ref['sourceId'], 'revision': ref['sourceRevision']},
                         'meaningFlag': {'ref': ref, 'field': field}}
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',
                           ('notebook', oid, ctx.sid, ctx.actor['owner'], 1, json.dumps(value, ensure_ascii=False), store.now()))
                rec = {'fingerprint': fingerprint, 'itemId': oid, 'itemRevision': 1}
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',
                           ('w26meaningreceipt', rid, ctx.sid, ctx.actor['owner'], 1, json.dumps(rec), store.now()))
            db.commit()
        return get_flag(ctx, oid)


def get_flag(ctx, flag_id):
    _id(flag_id)
    with ctx.lock:
        ctx.check_actor()
        with store.connect() as db:
            row = db.execute("SELECT data,revision FROM objects WHERE kind='notebook' AND id=? AND session_id=? AND owner_id=?", (flag_id, ctx.sid, ctx.actor['owner'])).fetchone()
        if not row:
            _fail('not_found', 'Flag unavailable.', 404)
        item = json.loads(row['data']); metadata = item.get('meaningFlag')
        if not isinstance(metadata, dict):
            _fail('not_found', 'Flag unavailable.', 404)
        ctx.resolve([parse_ref(metadata['ref'])])
        return {'id': flag_id, 'revision': row['revision'], 'ref': metadata['ref'],
                'field': metadata['field'], 'note': item['text'], 'visibility': 'private'}


def revise_flag(ctx, flag_id, revision, field, note, request_id):
    _id(flag_id); _id(request_id)
    if type(revision) is not int or revision < 1 or field not in ('source', 'translation', 'visual') or not isinstance(note, str) or not note.strip() or len(note) > 1000 or '\x00' in note:
        _fail('invalid_request', 'Invalid flag revision.', 422)
    fingerprint = _key('revise', flag_id, revision, field, note)
    rid = _key(ctx.sid, ctx.actor['owner'], request_id)
    with ctx.lock:
        current = get_flag(ctx, flag_id)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            receipt = db.execute("SELECT data FROM objects WHERE kind='w26meaningreceipt' AND id=? AND session_id=? AND owner_id=?", (rid, ctx.sid, ctx.actor['owner'])).fetchone()
            if receipt:
                saved = json.loads(receipt['data'])
                if saved['fingerprint'] != fingerprint or saved.get('itemRevision') != current['revision']:
                    _fail('request_conflict', 'Request ID already used or result changed.')
            else:
                if current['revision'] != revision:
                    _fail('version_conflict', 'Flag changed.')
                row = db.execute("SELECT data FROM objects WHERE kind='notebook' AND id=? AND session_id=? AND owner_id=? AND revision=?", (flag_id, ctx.sid, ctx.actor['owner'], revision)).fetchone()
                if not row:
                    _fail('version_conflict', 'Flag changed.')
                item = json.loads(row['data']); item['text'] = note; item['meaningFlag']['field'] = field
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='notebook' AND id=?", (json.dumps(item, ensure_ascii=False), flag_id))
                rec = {'fingerprint': fingerprint, 'itemId': flag_id, 'itemRevision': revision + 1}
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',
                           ('w26meaningreceipt', rid, ctx.sid, ctx.actor['owner'], 1, json.dumps(rec), store.now()))
            db.commit()
        return get_flag(ctx, flag_id)


# Import lazily: the contribution authority reads get_flag from this module.
# PRIMARY must install all common-reader guards documented by that authority
# before exposing these operations to a served application.
def share_flag(ctx, selection):
    from . import waves26_flag_contribution
    return waves26_flag_contribution.share(ctx, selection)


def share_receipt(ctx, request_id):
    from . import waves26_flag_contribution
    return waves26_flag_contribution.receipt(ctx, request_id)


def revoke_flag_share(ctx, share_id):
    from . import waves26_flag_contribution
    return waves26_flag_contribution.revoke(ctx, share_id)


def guard_flag_share(ctx, share_id, projection):
    from . import waves26_flag_contribution
    return waves26_flag_contribution.final_guard(ctx, share_id, projection)
