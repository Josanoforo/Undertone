"""Production session visual-grounding handler using Phase 10 receipts and rights."""
import base64
import hashlib
import json
from .phase10_common import Context, Phase10Error
from . import phase10_vision, waves21_visual_grounding as grounding

OPERATION = 'w21.visual.ground'

def _vision(row, box):
    scaled = {k: round(v * 10000) for k, v in box.items()}
    instruction = ('Describe visible evidence in the selected normalized region ' +
                   json.dumps(scaled, sort_keys=True) +
                   ' of the supplied full image. Distinguish description from inference; the cause is unknown when unsupported.')
    return phase10_vision.call([row], instruction, [row['source']['image']])

def _vision_batch(regions):
    """Use one admitted provider call for all selected regions, with strict mapping."""
    results = None
    position = 0
    def describe(row, box):
        nonlocal results, position
        if results is None:
            selections = [{'regionId': r['regionId'],
                           'box': {k: round(v * 10000) for k, v in r['box'].items()}}
                          for r in regions]
            instruction = ('For each selected normalized region of the supplied full image, '
                           'describe visible evidence separately. Return the text field as a JSON '
                           'array of objects with exactly regionId, text and uncertain, one for '
                           'each selection in the given order. Distinguish description from '
                           'inference; unsupported causes are unknown. Selections: ' +
                           json.dumps(selections, ensure_ascii=False))
            data, provider, model = phase10_vision.call([row], instruction, [row['source']['image']])
            try:
                values = json.loads(data['text'])
                if not isinstance(values, list) or len(values) != len(regions):
                    raise ValueError()
                for expected, value in zip(regions, values):
                    if (not isinstance(value, dict) or set(value) != {'regionId', 'text', 'uncertain'}
                            or value['regionId'] != expected['regionId']
                            or not isinstance(value['text'], str) or not 1 <= len(value['text'].strip()) <= 6000
                            or type(value['uncertain']) is not bool):
                        raise ValueError()
                results = [({'text': v['text'], 'uncertain': v['uncertain']}, provider, model) for v in values]
            except (ValueError, TypeError, KeyError):
                raise Phase10Error('invalid_vision', 'Visual descriptions unavailable.', 503)
        if position >= len(regions) or box != regions[position]['box']:
            raise Phase10Error('invalid_vision', 'Visual descriptions unavailable.', 503)
        result = results[position]
        position += 1
        return result
    return describe

def _hash(image):
    return hashlib.sha256(base64.b64decode(image['data'], validate=True)).hexdigest()

def _project(ctx, result):
    safe = grounding.project(ctx, result, grounding.png_metadata)
    if safe.get('status') == 'unavailable':
        raise Phase10Error('stale_context', 'The selected frame is unavailable.', 409)
    row = ctx.resolve([safe['frame']['ref']])[0]
    if _hash(row['source']['image']) != safe.get('imageSha256'):
        raise Phase10Error('stale_context', 'The selected frame changed.', 409)
    return safe

def final_projection(handler, sid, actor, result):
    """PRIMARY must call under store.LOCK immediately through final serialization."""
    ctx = Context(handler, sid, actor)
    with ctx.lock:
        ctx.check_actor()
        return _project(ctx, result)

def _recover(ctx, request_id):
    with ctx.lock, ctx.store.connect() as db:
        ctx.check_actor()
        row = db.execute('SELECT state,status,result,refs FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?', (ctx.sid, ctx.actor['owner'], OPERATION, request_id)).fetchone()
        if not row:
            raise Phase10Error('not_found', 'Operation unavailable.', 404)
        if row['state'] != 'complete':
            return 200, {'operation': {'requestId': request_id, 'state': row['state']}}
        result = _project(ctx, json.loads(row['result']))
        ctx.handler._w21_visual_binding = (ctx.sid, dict(ctx.actor), request_id)
        ctx.handler._p10_refs = json.loads(row['refs'])
        return 200, {'operation': {'requestId': request_id, 'state': 'complete'}, 'grounding': result}

def handle(handler, sid, actor, method, parts):
    ctx = Context(handler, sid, actor)
    if method == 'GET' and len(parts) == 2 and parts[0] == 'requests':
        return _recover(ctx, parts[1])
    if method == 'POST' and parts == ['ground']:
        body = handler.body()
        if not isinstance(body, dict) or set(body) != {'requestId', 'frame', 'regions'}:
            raise Phase10Error('invalid_request', 'A request ID, indexed frame and selected regions are required.', 422)
        frame = body['frame']
        if not isinstance(frame, dict):
            raise Phase10Error('invalid_frame', 'An indexed frame is required.', 422)
        ref = frame.get('ref')
        # Validate all client-controlled geometry and source rights before admission.
        # This preflight performs no provider call.
        grounding.ground(ctx, frame, body['regions'], grounding.png_metadata)
        payload = {'frame': frame, 'regions': body['regions']}
        def invoke(rows):
            vision = _vision if len(body['regions']) == 1 else _vision_batch(body['regions'])
            result = grounding.ground(ctx, frame, body['regions'], grounding.png_metadata, vision)
            result['imageSha256'] = _hash(rows[0]['source']['image'])
            return result
        status, result = ctx.generate(OPERATION, body['requestId'], payload, [ref], invoke)
        with ctx.lock:
            ctx.check_actor(); safe = _project(ctx, result)
            handler._w21_visual_binding = (sid, dict(actor), body['requestId'])
            return status, {'grounding': safe, 'requestId': body['requestId']}
    raise Phase10Error('not_found', 'Visual operation unavailable.', 404)



def edition_metadata(ctx, record_projection):
    """Read this actor's current grounding metadata for an exact approved record.

    PRIMARY must keep store.LOCK through the final response. A correction is
    disclosed only for this actor's current source-change fence. Description
    assets are unavailable until persisted; model text is not an asset.
    """
    from . import waves18_records
    if not isinstance(record_projection, dict):
        raise Phase10Error('invalid_request', 'An approved record is required.', 422)
    with ctx.lock:
        ctx.check_actor()
        record = waves18_records.fetch(ctx.sid, record_projection.get('id'))
        current = waves18_records.projection(ctx.sid, record, record_projection.get('language'))
        if current != record_projection:
            raise Phase10Error('stale_context', 'The approved record changed.', 409)
        refs = list(current['refs'])
        for chapter in current.get('chapters', []):
            for ref in chapter.get('refs', []):
                if ref not in refs:
                    refs.append(ref)
        with ctx.store.connect() as db:
            rows = db.execute("SELECT result FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND state='complete'", (ctx.sid, ctx.actor['owner'], OPERATION)).fetchall()
            from . import waves21_correction_impact as impact
            corrections = {}
            for ref in refs:
                source_id, revision = ref.get('sourceId'), ref.get('sourceRevision')
                if not isinstance(source_id, str) or type(revision) is not int:
                    continue
                fence = impact._get(db, 'w21sourcefence', impact._key(ctx.sid, source_id), ctx.sid)
                if not fence or fence.get('revision') != revision:
                    continue
                intent = impact._get(db, 'w21sourcechange', fence.get('intentId'), ctx.sid)
                owner = db.execute("SELECT owner_id FROM objects WHERE kind='w21sourcechange' AND id=? AND session_id=?", (fence.get('intentId'), ctx.sid)).fetchone()
                if intent and owner and owner['owner_id'] == ctx.actor['owner'] and intent.get('sourceId') == source_id and intent.get('revision') == revision and intent.get('fence') == fence.get('fence'):
                    corrections[(source_id, revision)] = {'status': 'available', 'changeId': intent['id'], 'sourceRevision': revision}
        entries = []
        for row in rows:
            try:
                result = json.loads(row['result'])
                safe = _project(ctx, result)
                if safe['frame']['ref'] not in refs:
                    continue
                entries.append({'frame': safe['frame'], 'imageSha256': safe['imageSha256'],
                                'regions': [{'regionId': r['regionId'], 'box': r['box'],
                                             'ocrStatus': r['ocrStatus']} for r in safe['regions']],
                                'descriptionAsset': {'status': 'unavailable'},
                                'correction': corrections.get((safe['frame']['ref']['sourceId'], safe['frame']['ref']['sourceRevision']), {'status': 'unavailable'})})
            except (Phase10Error, ValueError, TypeError, KeyError):
                continue
        return {'recordId': current['id'], 'recordVersion': current['version'], 'visual': entries}
