"""Read-only listening recovery over existing queue and private Phase12 receipts.

This module never admits, generates, cancels, retries, or changes a preference.
The normal Phase12 final-send guard remains the media delivery authority.
"""
import hashlib
import json

from . import phase12_jobs as jobs, store, waves17_listening as queue
from . import waves17_tts_local as local, waves20_modes, waves20_policy_access
from . import waves23_speech_profiles as profiles
from .phase10_common import Phase10Error


def receipt_state(state):
    if state in ('complete', 'w20_complete'):
        return 'ready'
    if state in ('unknown', 'w20_unknown', 'w20_running'):
        return 'unknown'
    if state in ('queued', 'running'):
        return 'pending'
    if state in ('failed', 'canceled', 'w20_failed', 'w20_canceled'):
        return 'failed'
    return 'unavailable'


def _local_policy(ctx):
    with ctx.store.connect() as db:
        row = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?",
                         (ctx.sid, ctx.sid)).fetchone()
        _, policy = waves20_modes._current(db, ctx.sid, row['owner_id']) if row else (None, None)
    return bool(policy and waves20_policy_access.current_local_policy(ctx.sid, policy['revision']))


def prepared_translation(ctx, selection, obj):
    """Inspect only this capability's exact selected-profile speech and parent.

    A Phase12 receipt does not prove application of Wave23 pronunciation rules;
    only the empty approved rule set can be equivalent to that execution path.
    """
    unavailable = {'state': 'unavailable', 'message': 'No current completed translated audio matches this voice profile.'}
    with ctx.lock:
        ctx.check_actor()
        from .waves25_listening_preparation import projection
        prepared = projection(ctx, selection)
        if prepared is not None:
            return prepared
        selected, current = profiles.current_selection(ctx)
        actual = {'profileId': current['id'], 'profileRevision': current['_revision'],
                  'configDigest': profiles.digest(current['profile']), 'ref': selected['ref'],
                  'language': current['profile']['language']}
        if actual != selection or profiles.projection(current) != profiles.projection(obj):
            return unavailable
        source = ctx.resolve([selection['ref']])[0]['source']
        p = current['profile']
        approval = current.get('approval')
        if (source.get('language') == p['language'] or p['engine'] != 'local_neural'
                or not approval or approval.get('rules') or not _local_policy(ctx)
                or not getattr(ctx.handler, '_auth_token', None)):
            return unavailable
        from .waves25_listening_authorities import installed_voice_descriptor
        installed = installed_voice_descriptor(p['language'])
        if not installed.get('ok') or any(p[key] != installed[key] for key in (
                'model', 'modelVersion', 'voiceId', 'voiceVersion', 'adapterVersion')):
            return unavailable
        with ctx.store.connect() as db:
            rows = db.execute("SELECT request_id FROM phase12_jobs WHERE session_id=? AND actor_id=? "
                              "AND credential_hash=? AND kind='speech' ORDER BY seq DESC LIMIT 200",
                              (ctx.sid, ctx.actor['owner'], store.digest(ctx.handler._auth_token))).fetchall()
        observed = []
        for entry in rows:
            try:
                row = jobs.check_job(ctx.handler, ctx.sid, ctx.actor, entry['request_id'])
                # Failed/unknown jobs still need a current source and parent fence.
                jobs.rights(row)
                payload = json.loads(row['payload'])
                if (json.loads(row['ref']) != selection['ref'] or payload.get('language') != p['language']
                        or payload.get('engine') != p['engine'] or payload.get('voice') != p['voiceId']
                        or payload.get('modelVersion') != p['modelVersion']
                        or payload.get('adapterVersion') != p['adapterVersion']
                        or payload.get('modelSha256') != local.WEIGHT_SHA256.get(p['language'])
                        or payload.get('speed', 1) != p['rate']):
                    continue
                parent = jobs.check_job(ctx.handler, ctx.sid, ctx.actor, payload['translationRequestId'], 'complete')
                if parent['kind'] != 'translation' or json.loads(parent['ref']) != selection['ref']:
                    continue
                from . import waves15_translation_review, waves17_terminology
                waves15_translation_review.check_speech_parent(parent)
                bound = waves17_terminology.guard(parent)
                translated = json.loads(parent['result'])
                if translated.get('targetLanguage') != p['language']:
                    continue
                state = receipt_state(row['state'])
                item = {'state': state, 'requestId': row['request_id'],
                        'translationRequestId': parent['request_id'], 'language': p['language'],
                        'profileId': selection['profileId'], 'profileRevision': selection['profileRevision'],
                        'terminologyRevision': bound['revision'] if bound else None,
                        'message': {'ready': 'Existing translated audio is recoverable with this exact voice. Start it explicitly in the player.',
                                    'pending': 'The original request is pending. Check that request; do not submit another.',
                                    'unknown': 'The original outcome is unknown. Check its receipt; no automatic retry is allowed.',
                                    'failed': 'The original request ended without recoverable audio. No replacement was started.'}.get(state, unavailable['message'])}
                if state == 'ready':
                    if not row['media'] or not row['result']:
                        continue
                    metadata = json.loads(row['result']).get('audio', {})
                    if (metadata.get('engine') != 'sherpa-onnx-cpu'
                            or metadata.get('voice') != p['voiceId']
                            or metadata.get('model') != p['model']
                            or metadata.get('modelVersion') != p['modelVersion']
                            or metadata.get('adapterVersion') != p['adapterVersion']
                            or metadata.get('modelSha256') != payload['modelSha256']):
                        continue
                    item['audioSha256'] = hashlib.sha256(row['media']).hexdigest()
                observed.append(item)
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
        if not observed:
            return unavailable
        # Prefer an existing usable receipt; preserve separate unknown outcomes.
        chosen = next((item for item in observed if item['state'] == 'ready'), observed[0])
        return {**chosen, 'outcomes': observed}


def prepared_original(ctx, selection, obj):
    """Keep the existing approved profile/glossary/context bridge recovery path."""
    from . import waves20_scheduler, waves25_listening_authorities as authorities
    from . import waves25_listening_preferences as preferences
    delivery = getattr(waves20_scheduler._service, 'translation_binding', None)
    if delivery is None:
        return None
    observed = authorities.bind_installed_voice(ctx, selection, profiles.projection(obj))
    if not observed.get('ok'):
        return None
    api = authorities.ListeningAuthorities(observed['observation'], delivery)
    with ctx.store.connect() as db:
        rows = db.execute('SELECT data FROM objects WHERE kind=? AND session_id=? AND owner_id=? ORDER BY rowid DESC LIMIT 200',
                          (profiles.BINDING, ctx.sid, ctx.actor['owner'])).fetchall()
    outcomes = []
    for row in rows:
        try:
            marker = json.loads(row['data'])
            if (marker.get('selectionRef') != selection['ref'] or marker.get('profileId') != selection['profileId']
                    or marker.get('profileRevision') != selection['profileRevision']):
                continue
            result = preferences.preload(ctx, marker['runId'], marker['requestId'], receipt_authority=api.receipt_authority)
            outcomes.append({'state': result['state'], 'runId': marker['runId'], 'requestId': marker['requestId'],
                             'audioSha256': result.get('audioSha256'),
                             'message': {'ready': 'Existing approved preparation and audio remain recoverable. Start playback explicitly.',
                                         'unknown': 'The original outcome is unknown. Check its receipt; do not submit a replacement.',
                                         'failed': 'The original request ended without recoverable audio. No replacement was started.'}.get(result['state'], 'This prepared audio is not currently recoverable.')})
        except (Phase10Error, KeyError, TypeError, ValueError):
            continue
    if not outcomes:
        return None
    chosen = next((item for item in outcomes if item['state'] == 'ready'), outcomes[0])
    return {**chosen, 'outcomes': outcomes}


def continuity(ctx, selection, obj):
    """Project the existing actor queue; offsets are reported source-clock gaps."""
    with ctx.lock:
        ctx.check_actor()
        currentness = {'state': 'unknown', 'message': 'No comparable source checkpoint is available.'}
        try:
            _, data = queue.handle(ctx.handler, ctx.sid, ctx.actor, 'GET', [])
            view = data['listening']
            offset = view.get('sourceOffsetMs')
            clock = view.get('clockProvenance', {})
            if clock.get('status') == 'known' and type(offset) is int and offset >= 0:
                currentness = {'state': 'live' if offset == 0 else 'delayed', 'delayMs': offset,
                               'basis': clock['basis'], 'message': 'Compared with the latest retained source on the same reported capture clock; not wall-clock stream latency.'}
            elif clock.get('reason'):
                currentness['message'] = clock['reason']
            currentness.update(generation=view['generation'], mode=view['mode'],
                               queueCount=len(view['queue']), checkpoint=view['checkpoint'],
                               latestSequence=view['feedLatest'], gaps=view['gaps'],
                               catchUpPolicy='preserve_order',
                               catchUpDescription='Catch up keeps queued captions in order. Go live explicitly discards older queued captions and skips their meaning; review the reported gaps before choosing.')
        except (Phase10Error, AttributeError):
            pass
        source_language = ctx.resolve([selection['ref']])[0]['source'].get('language')
        preparation = (prepared_original(ctx, selection, obj) if source_language == selection['language']
                       else prepared_translation(ctx, selection, obj))
        return {'selection': selection, 'currentness': currentness, 'preparation': preparation}
