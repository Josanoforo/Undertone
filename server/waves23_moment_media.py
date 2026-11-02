"""Guarded inspectable moment images; registration is trusted internal code only."""
import base64
import hashlib
import json
import re

from .phase10_common import Phase10Error, parse_ref


def _fail():
    raise Phase10Error('not_found', 'The moment image is unavailable.', 404)


def register(ctx, ref, image, timestamp_ms, region_id, caption, provenance, request_id):
    """Register already-produced bytes; never mount this internal function as a route."""
    from .claude_provider import image_block
    ref = parse_ref(ref)
    if (ref['sessionId'] != ctx.sid or type(timestamp_ms) is not int
            or not ref['startMs'] <= timestamp_ms <= ref['endMs']
            or (region_id is not None and (not isinstance(region_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', region_id)))
            or not isinstance(caption, str) or not 1 <= len(caption.strip()) <= 500
            or provenance not in ('authored', 'derived_frame')
            or not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request_id)):
        raise Phase10Error('invalid_request', 'Invalid moment image registration.', 422)
    if not isinstance(image, dict) or set(image) != {'mimeType', 'data'}:
        raise Phase10Error('invalid_request', 'Invalid image.', 422)
    try:
        image_block(image)
        raw = base64.b64decode(image['data'], validate=True)
    except (ValueError, TypeError, KeyError):
        raise Phase10Error('invalid_request', 'Invalid image.', 422)
    if not raw or len(raw) > 4 * 1024 * 1024:
        raise Phase10Error('invalid_request', 'Invalid image.', 422)
    digest = hashlib.sha256(raw).hexdigest()
    aid = hashlib.sha256(json.dumps([ctx.sid, request_id], separators=(',', ':')).encode()).hexdigest()
    value = {'id': aid, 'ref': ref, 'image': image, 'digest': digest, 'timestampMs': timestamp_ms,
             'regionId': region_id, 'caption': caption.strip(), 'provenance': provenance}
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator': _fail()
        ctx.resolve([ref])
        if region_id is not None:
            from .waves23_moment_index import _visual_candidates
            if not any(item['ref'] == ref and item['regionId'] == region_id for _, item in _visual_candidates(ctx, ref['startMs'], ref['endMs'])):
                _fail()
        old = ctx.store.get('w23momentimage', aid, ctx.sid)
        if old:
            old.pop('_revision', None)
            if old != value:
                raise Phase10Error('request_conflict', 'Registration ID is already used.', 409)
        else:
            existing = ctx.store.all('w23momentimage', ctx.sid)
            if any(v.get('ref') == ref and v.get('regionId') == region_id for v in existing):
                raise Phase10Error('image_conflict', 'This moment image is already registered.', 409)
            if len(existing) >= 32 or sum(len(v.get('image', {}).get('data', '')) for v in existing) + len(image['data']) > 24 * 1024 * 1024:
                raise Phase10Error('image_capacity', 'Moment image capacity reached.', 409)
            ctx.store.put('w23momentimage', ctx.sid, value, oid=aid)
    return {'assetId': aid, 'digest': digest}


def _authorized(ctx, ref, archive):
    if archive is None:
        if ref['sessionId'] != ctx.sid: _fail()
        return ctx.resolve([ref])[0]
    from . import channel_authority
    if not isinstance(archive, dict) or set(archive) != {'channelId', 'grantId', 'revision'}: _fail()
    projected = channel_authority.project_source(ctx, archive['channelId'], archive['grantId'], archive['revision'])
    if projected['ref'] != ref: _fail()
    return {'source': ctx.store.get('source', ref['sourceId'], ref['sessionId'])}


def inspect(ctx, ref, region_id=None, archive=None):
    ref = parse_ref(ref)
    with ctx.lock:
        ctx.check_actor()
        row = _authorized(ctx, ref, archive)
        if region_id is not None:
            if archive is not None: _fail()
            from .waves23_moment_index import _visual_candidates
            if not any(item['ref'] == ref and item['regionId'] == region_id for _, item in _visual_candidates(ctx, ref['startMs'], ref['endMs'])):
                _fail()
        images = ctx.store.all('w23momentimage', ref['sessionId'])
        matches = [v for v in images if v.get('ref') == ref and v.get('regionId') == region_id]
        if not matches and row['source'].get('p10Frame'):
            from .phase10_timeline import frame_moment
            source = row['source']
            if frame_moment(source)['ref'] != ref: _fail()
            image = source['image']
            return {'assetId': 'frame-' + ref['momentId'], 'ref': ref, 'regionId': region_id,
                    'timestampMs': ref['startMs'], 'digest': source['p10Frame']['imageSha256'],
                    'caption': 'Retained captured frame', 'provenance': 'received_capture',
                    'mimeType': image['mimeType']}
        if len(matches) != 1: _fail()
        value = matches[0]
        raw = base64.b64decode(value['image']['data'], validate=True)
        if hashlib.sha256(raw).hexdigest() != value['digest']: _fail()
        return {
            'assetId': value['id'], 'ref': ref, 'regionId': region_id, 'timestampMs': value['timestampMs'],
            'digest': value['digest'], 'caption': value['caption'], 'provenance': value['provenance'],
            'mimeType': value['image']['mimeType']}


def bytes_for(ctx, ref, asset_id, region_id=None, archive=None):
    with ctx.lock:
        metadata = inspect(ctx, ref, region_id, archive)
        if metadata['assetId'] != asset_id: _fail()
        if asset_id.startswith('frame-'):
            image = _authorized(ctx, metadata['ref'], archive)['source']['image']
        else:
            image = ctx.store.get('w23momentimage', asset_id, metadata['ref']['sessionId'])['image']
        raw = base64.b64decode(image['data'], validate=True)
        if hashlib.sha256(raw).hexdigest() != metadata['digest']: _fail()
        return metadata, raw


def guard_bytes(ctx, request, metadata, raw):
    current, data = bytes_for(ctx, request['ref'], request['assetId'], request.get('regionId'), request.get('archive'))
    if current != metadata or data != raw:
        raise Phase10Error('stale_context', 'The moment image changed or is unavailable.', 409)


def source_changed_db(db, sid, source_id):
    """Remove old derived image bytes as part of the source mutation transaction."""
    if not db.in_transaction: raise ValueError('source change requires caller transaction')
    rows = db.execute("SELECT id,data FROM objects WHERE kind='w23momentimage' AND session_id=?", (sid,)).fetchall()
    ids = [row['id'] for row in rows if json.loads(row['data']).get('ref', {}).get('sourceId') == source_id]
    db.executemany("DELETE FROM objects WHERE kind='w23momentimage' AND id=? AND session_id=?", [(oid, sid) for oid in ids])


def cleanup_db(db, sid):
    """Run inside the existing session cleanup transaction."""
    if not db.in_transaction: raise ValueError('cleanup requires caller transaction')
    db.execute("DELETE FROM objects WHERE kind='w23momentimage' AND session_id=?", (sid,))
