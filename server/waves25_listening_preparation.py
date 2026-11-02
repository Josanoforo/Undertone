"""Explicit approved preparation bindings. These records are consent metadata,
not generation/admission receipts; only the existing Wave20 pipeline creates audio.
"""
import json
import re

from . import store, waves17_terminology as terminology, waves23_speech_profiles as profiles
from .phase10_common import Phase10Error, parse_ref

KIND = 'w25preparation'


def approved_for_selection(ctx):
    """Read only approved content accessible to the selected viewer; never a draft or opt-in."""
    ctx.check_actor()
    if ctx.actor['role'] != 'viewer':
        return None
    try:
        selected, _ = profiles.current_selection(ctx)
        ctx.resolve([selected['ref']])
        record = terminology.load(ctx.sid)
        if not record or not record.get('approved'):
            return None
        credential = ctx._credential_digest or store.digest(getattr(ctx.handler, '_auth_token', ''))
        return terminology.snapshot(ctx.sid, ctx.actor, credential, record['approved']['revision'])
    except Phase10Error:
        return None


def fail(message='The chosen preparation changed or is unavailable.'):
    raise Phase10Error('stale_preparation', message, 409)


def validate_choice(choice):
    if not isinstance(choice, dict) or set(choice) != {'profileId', 'profileRevision', 'terminologyRevision', 'ref'}:
        raise Phase10Error('invalid_request', 'Choose an exact approved profile and glossary/context revision.', 422)
    profiles.token(choice['profileId'])
    if any(type(choice[k]) is not int or choice[k] < 1 for k in ('profileRevision', 'terminologyRevision')):
        raise Phase10Error('invalid_request', 'Choose exact approved revisions.', 422)
    parse_ref(choice['ref'])


def _current(ctx, choice):
    validate_choice(choice)
    ctx.check_actor()
    ref = choice['ref']
    if ref['sessionId'] != ctx.sid:
        fail()
    ctx.resolve([ref])
    selected, obj = profiles.current_selection(ctx)
    if (selected['ref'] != ref or obj['id'] != choice['profileId']
            or obj['_revision'] != choice['profileRevision'] or not obj.get('approval')):
        fail('Select this exact current approved profile for the source before preparing.')
    approval, p = obj['approval'], obj['profile']
    # This is the actually supported local adapter, not a silent engine fallback.
    from .waves25_listening_authorities import installed_voice_descriptor
    installed = installed_voice_descriptor(p['language'])
    if p['engine'] != 'local_neural' or not installed.get('ok') or any(
            p[key] != installed[key] for key in ('model', 'modelVersion', 'voiceId', 'voiceVersion', 'adapterVersion')):
        fail('The chosen profile is not supported by the current installed voice.')
    credential = ctx._credential_digest or store.digest(getattr(ctx.handler, '_auth_token', ''))
    terms = terminology.snapshot(ctx.sid, ctx.actor, credential, choice['terminologyRevision'])
    if not terms['document']['terms'] and not terms['document']['context']:
        fail('Choose nonempty approved glossary or source-bound context.')
    bound = {'choice': choice, 'sessionId': ctx.sid, 'actorId': ctx.actor['owner'],
             'credentialHash': credential, 'language': p['language'], 'voice': p['voiceId'],
             'profileDigest': profiles.digest(p), 'approvalDigest': profiles.digest(approval),
             'terminologyDigest': profiles.digest(terms)}
    return bound, obj, terms


def prepare(ctx, choice, body):
    """Admission-only hook: record this explicit request's immutable choice."""
    with ctx.lock:
        bound, _, _ = _current(ctx, choice)
        ref = choice['ref']
        if (body['source'] != ref['momentId'] or body['sourceRevision'] != ref['sourceRevision']
                or body['language'] != bound['language'] or body['voice'] != bound['voice'] or body['choice'] != 'local'):
            fail('Preparation must match the exact source, language and selected voice.')
        binding_id = profiles.digest(bound)
        prior = ctx.store.get(KIND, binding_id, ctx.sid)
        if prior:
            prior = {k: v for k, v in prior.items() if k not in ('id', '_revision')}
            if prior != bound:
                fail()
        else:
            ctx.store.put(KIND, ctx.sid, bound, owner=ctx.actor['owner'], oid=binding_id)
        return binding_id


def lookup(ctx, choice):
    """Read-only resolution. Missing metadata is never recreated on recovery."""
    with ctx.lock:
        bound, _, _ = _current(ctx, choice)
        binding_id = profiles.digest(bound)
        if ctx.store.get(KIND, binding_id, ctx.sid) is None:
            fail('No admitted preparation binding exists for this explicit choice.')
        return binding_id


def resolve(ctx, binding_id, moment_id, revision, language):
    with ctx.lock:
        if not isinstance(binding_id, str) or not re.fullmatch('[a-f0-9]{64}', binding_id):
            fail()
        record = ctx.store.get(KIND, binding_id, ctx.sid)
        if not record:
            fail()
        bound, obj, terms = _current(ctx, record['choice'])
        if (profiles.digest(bound) != binding_id or record['actorId'] != ctx.actor['owner']
                or bound['choice']['ref']['momentId'] != moment_id
                or bound['choice']['ref']['sourceRevision'] != revision or bound['language'] != language):
            fail()
        return bound, obj, terms


def settings(bound, obj, terms):
    """Trusted exact profile/rule settings for the existing JobBridge validator."""
    from .waves20_job_bridge import settings_digest
    p, approval = obj['profile'], obj['approval']
    rules = approval['rules']
    return {'engine': p['engine'], 'model': p['model'], 'voice': p['voiceId'],
            'outputFormat': 'audio/wav', 'adapterVersion': p['adapterVersion'],
            'modelVersion': p['modelVersion'], 'speed': p['rate'],
            'ruleSetId': approval['ruleSetId'], 'ruleRevision': str(approval['ruleSetRevision']),
            'ruleDigest': settings_digest(rules), 'approvedRules': rules, 'controls': [],
            'glossary': [], 'terminology': terms, 'hostedBinding': None}


def projection(ctx, selection):
    """Project authentic live Wave20 receipts, never relabel a Phase12 receipt."""
    from . import waves20_scheduler
    service = waves20_scheduler._service
    if service is None:
        return None
    credential = ctx._credential_digest or store.digest(getattr(ctx.handler, '_auth_token', ''))
    results = []
    with ctx.lock, service.lock:
        for ticket, (_, identity, subscriber) in list(service.live.items()):
            parts = identity.translation_revision.split(':')
            if (len(parts) != 4 or parts[0] != 'translation' or identity.session != ctx.sid
                    or identity.private_actor != ctx.actor['owner'] or subscriber.authority != credential):
                continue
            try:
                bound, _, terms = resolve(ctx, parts[3], identity.source, int(identity.source_revision), identity.language)
                if (bound['choice']['ref'] != selection['ref'] or bound['choice']['profileId'] != selection['profileId']
                        or bound['choice']['profileRevision'] != selection['profileRevision']
                        or bound['profileDigest'] != selection['configDigest']):
                    continue
                view = service.view(ctx.handler, ctx.sid, ctx.actor, ticket)
                status = view['state']
                mapped = 'ready' if status == 'ready' else 'unknown' if status == 'unknown' else 'pending' if status in ('queued','running','generating','waiting') else 'failed'
                item = {'state': mapped, 'ticket': ticket, 'kind': 'wave20_prepared',
                        'preparationId': parts[3], 'terminologyRevision': terms['revision'],
                        'profileId': selection['profileId'], 'profileRevision': selection['profileRevision'],
                        'message': 'Existing approved preparation and Wave20 audio are recoverable; playback remains explicit.' if mapped == 'ready' else 'Check the original Wave20 receipt; no new admission was started.'}
                if mapped == 'ready':
                    item['audioSha256'] = view['result']['audioSha256']
                results.append(item)
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
    if not results:
        return None
    return {**next((item for item in results if item['state'] == 'ready'), results[0]), 'outcomes': results}
