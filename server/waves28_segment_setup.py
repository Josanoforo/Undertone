"""Reviewed segment setup adapter over existing session pack receipts.

The target is an editable pack, never an activation or a capability grant.
"""
from . import store, waves24_channel_pack as pack, waves23_speech_profiles, waves21_pronunciation
from .phase10_common import Phase10Error

_SUPPORTED = frozenset(('activity', 'approvedActivity', 'approvedPackActivity',
                        'approvedProfile', 'approvedPackProfile', 'sharedGlossary')) | frozenset(pack._SETUP_DEFINITION_FIELDS)

def _source(ctx, source_id, revision):
    if type(revision) is not int or revision < 1:
        pack._fail('invalid_request', 'Invalid source revision.', 422)
    with store.connect() as db:
        pack._creator(ctx)
        source, current, owner = pack._load(db, ctx, source_id)
        if owner != ctx.actor['owner'] or source['withdrawn'] or not pack._live(source['expiresAt']):
            pack._fail('not_found', 'Source setup unavailable.', 404)
        if current != revision:
            pack._fail('stale_revision', 'Source setup changed.', 409)
        return source


def _entries(ctx, source):
    entries = []
    for index, item in enumerate(source['items']):
        if not isinstance(item, dict) or set(item) != {'kind', 'ref', 'revision'}:
            pack._fail('invalid_item', 'Invalid setup reference.', 422)
        if item['kind'] not in _SUPPORTED:
            entries.append({'index': index, 'kind': item['kind'], 'state': 'unsupported'})
            continue
        try:
            resolved = pack.validate_item(ctx, item)
            entries.append({'index': index, 'kind': item['kind'], 'state': 'ready', 'item': resolved})
        except Phase10Error as exc:
            if exc.code not in ('not_found', 'stale_context', 'stale_revision'):
                raise
            # Existing authority intentionally does not disclose whether an
            # inaccessible reference is missing or revoked to this actor.
            entries.append({'index': index, 'kind': item['kind'], 'state': 'missing_or_revoked'})
    return entries


def preview(ctx, body):
    fields = {'packId', 'expectedRevision', 'sourcePackId', 'sourceRevision'}
    if not isinstance(body, dict) or set(body) != fields:
        pack._fail('invalid_request', 'Invalid setup preview.', 422)
    if body['packId'] == body['sourcePackId']:
        pack._fail('invalid_request', 'Choose a different target.', 422)
    with ctx.lock:
        source = _source(ctx, body['sourcePackId'], body['sourceRevision'])
        entries = _entries(ctx, source)
        # This verifies creator, target revision, target status and conflict IDs.
        raw = pack.preview(ctx, body)
        conflicts = {x['index']: x['conflictId'] for x in raw['items'] if x['status'] == 'conflict'}
        for entry in entries:
            if entry['index'] in conflicts and entry['state'] == 'ready':
                entry['conflictId'] = conflicts[entry['index']]
        needs_review = any(item['kind'] in pack._SETUP_DEFINITION_FIELDS or item['kind'] == 'sharedGlossary' for item in source['items'])
        reviewed = source.get('setupReview') == {'revision': body['sourceRevision'], 'itemsHash': pack._fingerprint(source['items'])}
        checks = []
        profiles = [e for e in entries if e['state'] == 'ready' and e['kind'] == 'profileDefinition']
        voices = waves23_speech_profiles.installed_voices(ctx) if any(e['item']['ref']['definition']['engine'] == 'local_neural' for e in profiles) else None
        for entry in profiles:
            profile = entry['item']['ref']['definition']; engine = profile['engine']
            status, reason = 'unknown', 'engine_not_covered_by_local_inventory'
            if engine == 'local_neural':
                keys = ('language','engine','model','modelVersion','voiceId','voiceVersion','adapterVersion')
                matching = any(all(voice.get(k) == profile[k] for k in keys) for voice in voices['voices'])
                unavailable = next((x['reason'] for x in voices['unavailable'] if x['language'] == profile['language']), None)
                status, reason = ('available', None) if matching else ('unavailable', unavailable or 'installed_identity_mismatch')
            checks.append({'index': entry['index'], 'voiceAvailability': status, 'reason': reason,
                           'controls': waves21_pronunciation.capabilities(engine, profile['model'], profile['voiceId']),
                           'requiresFreshRuleBinding': True})
        return {'sourcePackId': body['sourcePackId'], 'sourceRevision': body['sourceRevision'],
                'packId': body['packId'], 'targetRevision': raw['revision'], 'items': entries,
                'requiresSourceReview': needs_review, 'sourceReviewed': reviewed, 'profileChecks': checks,
                'glossaryChecks': [{'index': e['index'], 'forms': pack.glossary_projection(ctx, e['item']['ref'], e['item']['revision']), 'freshReviewRequired': True}
                                   for e in entries if e['state'] == 'ready' and e['kind'] == 'sharedGlossary'],
                'cueRequirements': [{'index': e['index'], 'materialFormat': e['item']['ref']['definition']['materialFormat'],
                                     'requiresCurrentApprovedMaterial': True, 'destinationAvailability': 'unknown'}
                                    for e in entries if e['state'] == 'ready' and e['kind'] == 'cueDefinition'],
                'target': {'sessionId': ctx.sid, 'creatorCanEdit': True,
                           'adapterCanActivate': False, 'activationAvailability': 'unknown',
                           'freshReviewRequired': True},
                'canImport': bool(entries) and all(x['state'] == 'ready' for x in entries) and (not needs_review or reviewed)}


def import_setup(ctx, body):
    fields = {'requestId', 'packId', 'expectedRevision', 'sourcePackId', 'sourceRevision', 'choices'}
    if not isinstance(body, dict) or set(body) != fields:
        pack._fail('invalid_request', 'Invalid setup import.', 422)
    original = {'action': 'import', **body}
    with ctx.lock:
        # Replays need the original pack receipt before the old target revision
        # check; mutate compares the entire original body and creates no new intent.
        try:
            pack.receipt(ctx, body['requestId'])
            replay = True
        except Phase10Error as exc:
            if exc.code != 'not_found':
                raise
            replay = False
        # Check replay fingerprint before inspecting a possibly changed source.
        result = pack.mutate(ctx, original) if replay else None
        source = _source(ctx, body['sourcePackId'], body['sourceRevision'])
        entries = _entries(ctx, source)
        if not entries or any(x['state'] != 'ready' for x in entries):
            pack._fail('unavailable_setup', 'Setup contains unavailable or unsupported items.', 409)
        if not replay:
            candidate = preview(ctx, {k: body[k] for k in ('packId', 'expectedRevision', 'sourcePackId', 'sourceRevision')})
            if not candidate['canImport']:
                pack._fail('unavailable_setup', 'Setup unavailable.', 409)
        if not replay:
            result = pack.mutate(ctx, original)
        return {**result, 'freshReviewRequired': True, 'activated': False}


def handle(handler, sid, actor, method, parts):
    ctx = pack.session_authority(handler, sid, actor)
    if method == 'POST' and parts == ['segment-setup', 'preview']:
        body = handler.body()
        with ctx.lock:
            result = preview(ctx, body)
        handler._w28_setup_final = lambda: pack._same(preview(ctx, body), result)
        return 200, result
    if method == 'POST' and parts == ['segment-setup', 'import']:
        body = handler.body()
        with ctx.lock:
            result = import_setup(ctx, body)
            expected_source = _entries(ctx, _source(ctx, body['sourcePackId'], body['sourceRevision']))
        def guard():
            pack._same(pack.receipt(ctx, body['requestId']), {k: result[k] for k in ('operation', 'packId', 'revision', 'currentRevision')})
            pack._same(_entries(ctx, _source(ctx, body['sourcePackId'], body['sourceRevision'])), expected_source)
        handler._w28_setup_final = guard
        return 200, result
    pack._fail('not_found', 'Route unavailable.', 404)


def final_guard(handler):
    guard = getattr(handler, '_w28_setup_final', None)
    if not callable(guard):
        pack._fail('not_found', 'Setup response unavailable.', 404)
    guard()
