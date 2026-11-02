"""Current, actor-scoped operating metadata; never admits or starts work."""
from . import waves23_speech_profiles as profiles, waves25_listening_authorities as listening
from . import waves25_listening_preferences as preferences, waves20_scheduler, waves20_modes, waves20_policy_access
from .phase10_common import Phase10Error, parse_ref


def _supported_profile(ctx, obj, source, descriptors):
    """Use installed identity and current policy for this approved profile, without selecting it."""
    p = obj['profile']
    if not obj.get('approval') or p['engine'] != 'local_neural' or p['language'] != source.get('language'):
        return False
    language = p['language']
    if language not in descriptors:
        descriptors[language] = listening.installed_voice_descriptor(language)
    descriptor = descriptors[language]
    if not descriptor.get('ok') or any(p.get(key) != value for key, value in (
            ('model', descriptor['model']), ('modelVersion', descriptor['modelVersion']),
            ('voiceId', descriptor['voiceId']), ('adapterVersion', descriptor['adapterVersion']),
            ('voiceVersion', descriptor['voiceVersion']))):
        return False
    with ctx.store.connect() as db:
        row = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?",
                         (ctx.sid, ctx.sid)).fetchone()
        _, policy = waves20_modes._current(db, ctx.sid, row['owner_id']) if row else (None, None)
    return bool(policy and waves20_policy_access.current_local_policy(ctx.sid, policy['revision']))


def _profile_label(language, ordinal):
    """Safe user-facing label; provider voice/profile identifiers stay internal."""
    language_name = {'en': 'English', 'es': 'Spanish'}.get(language, 'Available')
    suffix = '' if ordinal == 1 else f' option {ordinal}'
    return f'{language_name} speech{suffix}'


def _delivery_projection(state):
    """Map current scheduler work without claiming that audio is buffered."""
    return {
        'queued': ('waiting', 'processing_waiting', 'none'),
        'running': ('running', 'processing', 'none'),
        'ready': ('ready', 'ready', 'none'),
        'unavailable': ('unavailable', 'failed', 'known_failure'),
        'stale': ('failed', 'failed', 'known_failure'),
        'cancelled': ('failed', 'failed', 'known_failure'),
        'unknown': ('unknown', 'unknown', 'unknown'),
    }.get(state)


def project(ctx, ref, *, ticket=None, run_id=None, request_id=None):
    """Read existing authorities under the host's store lock. No result/media leaves here."""
    ref = parse_ref(ref)
    with ctx.lock:
        ctx.check_actor()
        source = ctx.resolve([ref])[0]['source']
        scope = {'actorId': ctx.actor['owner'], 'sessionId': ctx.sid,
                 'role': 'operator' if ctx.actor['role'] == 'creator' else 'audience',
                 'sourceId': ref['sourceId'], 'sourceRevision': ref['sourceRevision'],
                 'scopeGeneration': profiles.digest([ctx.sid, ctx.actor]),
                 'rightsGeneration': profiles.digest([ref, source.get('status'), source.get('audienceVisible')])}
        result = {'scope': scope, 'access': 'current', 'stages': [],
                  'queue': {'state': 'unknown'}, 'admission': {'state': 'unknown'},
                  'effect': 'unknown',
                  'receipt': {'state': 'unavailable', 'canRead': False, 'canResume': False},
                  'source': {'label': str(source.get('title') or 'Source')[:120], 'available': True},
                  'profiles': []}
        selection = obj = authority = None
        try:
            selected, obj = profiles.current_selection(ctx)
            if selected['ref'] == ref:
                selection = {'profileId': obj['id'], 'profileRevision': obj['_revision'],
                             'configDigest': profiles.digest(obj['profile']), 'ref': ref,
                             'language': obj['profile']['language']}
                observation = listening.bind_installed_voice(ctx, selection, profiles.projection(obj))
                service = waves20_scheduler._service
                delivery = getattr(service, 'translation_binding', None)
                if observation.get('ok'):
                    authority = listening.ListeningAuthorities(observation['observation'], delivery)
        except (Phase10Error, ValueError, TypeError, KeyError):
            pass
        descriptors = {}
        profile_counts = {}
        for item in profiles.visible_profiles(ctx):
            try:
                current = profiles.load(ctx, item['profileId'])
                supported = _supported_profile(ctx, current, source, descriptors)
                if supported:
                    language = current['profile']['language']
                    profile_counts[language] = profile_counts.get(language, 0) + 1
                    result['profiles'].append({'profileId': item['profileId'],
                        'revision': item['revision'], 'label': _profile_label(language, profile_counts[language]),
                        'approved': True, 'supported': True})
            except (Phase10Error, ValueError, TypeError, KeyError):
                continue
        service = waves20_scheduler._service
        if ticket is not None and service is not None:
            with service.lock:
                live = service.live.get(ticket)
                if live:
                    _, identity, subscriber = live
                    if (identity.session == ctx.sid and subscriber.actor == ctx.actor['owner'] and
                            identity.private_actor == ctx.actor['owner'] and
                            identity.source == ref['momentId'] and
                            identity.source_revision == str(ref['sourceRevision'])):
                        try:
                            view = service.view(ctx.handler, ctx.sid, ctx.actor, ticket)
                            state = view.get('state')
                            projected = _delivery_projection(state)
                            if projected:
                                stage, queue, effect = projected
                                result['stages'] = [{'id': 'processing', 'label': 'Processing', 'state': stage}]
                                result['admission']['state'] = 'admitted'
                                result['queue']['state'] = queue
                                result['effect'] = effect
                        except Phase10Error:
                            pass
        if run_id is not None and request_id is not None and authority is not None and selection:
            try:
                receipt = preferences.preload(ctx, run_id, request_id, receipt_authority=authority.receipt_authority)
                state = receipt.get('state')
                if state == 'ready':
                    result['receipt'] = {'state': 'ready', 'canRead': True, 'canResume': False,
                                         'receiptId': request_id}
                elif state == 'unknown':
                    result['receipt']['state'] = 'unknown'
                    result['effect'] = 'unknown'
            except (Phase10Error, ValueError, TypeError, KeyError):
                pass
        return result


def final_guard(ctx, ref, snapshot, *, ticket=None, run_id=None, request_id=None):
    """Caller holds store.LOCK through this check and response serialization."""
    if project(ctx, ref, ticket=ticket, run_id=run_id, request_id=request_id) != snapshot:
        raise Phase10Error('stale_context', 'Operating status changed; refresh.', 409)
