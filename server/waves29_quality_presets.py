"""Explicit profile choices; no generation, admission, or provider operation.

The policy reader is supplied by PRIMARY and must project current Wave 20 policy
and facts for the authenticated actor without side effects, under the store lock.
"""
import json

from .phase10_common import Context, parse_ref
from . import waves23_speech_profiles as profiles
from . import waves25_listening_authorities as listening


def _fail(code, message, status=409):
    profiles.fail(code, message, status)


def _preset_label(language, engine, ordinal):
    """Readable creator label; profile, voice and model IDs stay out of the UI."""
    language_name = {'en': 'English', 'es': 'Spanish'}.get(language, 'Supported-language')
    engine_name = {'local_neural': 'local neural speech', 'sapi': 'system speech',
                   'elevenlabs': 'hosted speech'}.get(engine, 'speech')
    suffix = '' if ordinal == 1 else f' option {ordinal}'
    return f'{language_name} {engine_name}{suffix}'


def _creator_only(ctx):
    if ctx.actor.get('role') != 'creator':
        _fail('not_found', 'Quality choices are unavailable.', 404)


class Presets:
    def __init__(self, policy_reader):
        if not callable(policy_reader):
            raise TypeError('A current policy projection reader is required')
        self.policy_reader = policy_reader

    def _policy(self, ctx):
        ctx.check_actor()
        state = self.policy_reader(ctx)
        try:
            policy, choices = state['policy'], state['choices']['speech']
            revision = policy['revision']
            selected = policy['operations']['speech']
            if (type(revision) is not int or revision < 1 or
                not isinstance(selected['alternatives'], list) or
                selected['primary'] not in ('local', 'hosted', 'text') or
                any(x not in ('local', 'hosted', 'text') for x in selected['alternatives'])):
                raise ValueError()
            # Only public, bounded facts participate in the condition identity.
            result = {'revision': revision, 'primary': selected['primary'],
                      'alternatives': list(selected['alternatives']),
                      'sessionCapUsd': policy['sessionCapUsd'], 'choices': {}}
            for choice in ('local', 'hosted'):
                item = choices[choice]
                if item['availability'] not in ('available', 'unavailable', 'unknown'):
                    raise ValueError()
                result['choices'][choice] = {key: item.get(key) for key in (
                    'availability', 'estimatedUsd', 'estimateBasis', 'reservationsUsd',
                    'unknownHoldsUsd', 'unknownHoldsPresent', 'unknownAfterDispatch')}
            return result
        except (KeyError, TypeError, ValueError):
            _fail('policy_unavailable', 'Current speech policy is unavailable.')

    def list(self, ctx, ref):
        ref = parse_ref(ref)
        with ctx.lock:
            _creator_only(ctx)
            ctx.check_actor()
            source = ctx.resolve([ref])[0]['source']
            source_language = source.get('language')
            policy = self._policy(ctx)
            result = []
            descriptors = {}
            label_counts = {}
            for p in profiles.visible_profiles(ctx):
                choice = 'hosted' if p['engine'] == 'elevenlabs' else 'local'
                fact = policy['choices'][choice]
                configured = choice in [policy['primary'], *policy['alternatives']]
                language_matches = p['language'] == source_language
                if p['language'] not in descriptors:
                    descriptors[p['language']] = listening.installed_voice_descriptor(p['language'])
                descriptor = descriptors[p['language']]
                supported_identity = (p['engine'] == 'local_neural' and descriptor.get('ok') and
                    all(p.get(key) == descriptor.get(key) for key in
                        ('model', 'modelVersion', 'voiceId', 'voiceVersion', 'adapterVersion')))
                if not language_matches:
                    unavailable_reason = 'This profile language does not match the current source; this route does not switch languages.'
                elif not supported_identity:
                    unavailable_reason = 'This profile identity is not supported by the current local source-reading route.'
                elif not configured:
                    unavailable_reason = 'This profile path is not configured by current policy.'
                elif fact['availability'] == 'unknown':
                    unavailable_reason = 'Current policy availability is unknown.'
                elif fact['availability'] == 'unavailable':
                    unavailable_reason = 'Current policy reports this path unavailable.'
                else:
                    unavailable_reason = None
                availability = (fact['availability'] if supported_identity and language_matches and configured
                                else 'unavailable')
                label_key = (p['language'], p['engine'])
                label_counts[label_key] = label_counts.get(label_key, 0) + 1
                conditions = {'policyRevision': policy['revision'], 'policyChoice': choice,
                    'role': 'primary' if choice == policy['primary'] else 'alternative',
                    'configured': configured, 'deliveryPathSupported': bool(supported_identity),
                    'sourceLanguage': source_language, 'profileLanguageMatches': language_matches,
                    'availabilityReason': unavailable_reason,
                    'policyAvailability': fact['availability'], 'facts': fact,
                    'sessionCapUsd': policy['sessionCapUsd'],
                    'costMode': 'hosted_unknown' if choice == 'hosted' else 'local',
                    'deliveryMode': p['deliveryMode']}
                item = {'id': p['profileId'], 'label': _preset_label(p['language'], p['engine'], label_counts[label_key]),
                    'profileId': p['profileId'], 'profileRevision': p['revision'],
                    'language': p['language'], 'engine': p['engine'], 'model': p['model'],
                    'modelVersion': p['modelVersion'], 'voiceId': p['voiceId'],
                    'voiceVersion': p['voiceVersion'], 'adapterVersion': p['adapterVersion'],
                    'rate': p['rate'], 'qualityPreference': p['qualityPreference'],
                    'availability': availability, 'conditions': conditions}
                item['conditionsDigest'] = profiles.digest({'ref': ref, 'preset': item})
                result.append(item)
            return {'ref': ref, 'presets': result}

    def choose(self, ctx, body):
        _creator_only(ctx)
        required = {'requestId', 'presetId', 'expectedRevision', 'ref',
                    'policyRevision', 'conditionsDigest', 'acceptConditions'}
        if not isinstance(body, dict) or set(body) != required:
            _fail('invalid_request', 'A preset and its current conditions are required.', 422)
        profiles.token(body['requestId']); profiles.token(body['presetId'])
        if (type(body['expectedRevision']) is not int or body['expectedRevision'] < 1 or
            type(body['policyRevision']) is not int or body['policyRevision'] < 1 or
            body['acceptConditions'] is not True or
            not isinstance(body['conditionsDigest'], str)):
            _fail('invalid_request', 'Explicit acceptance of current conditions is required.', 422)
        ref = parse_ref(body['ref'])
        with ctx.lock:
            listing = self.list(ctx, ref)
            preset = next((x for x in listing['presets'] if x['id'] == body['presetId']), None)
            if not preset:
                _fail('preset_unavailable', 'The preset is unavailable; choose a listed alternative.')
            if (preset['profileRevision'] != body['expectedRevision'] or
                preset['conditions']['policyRevision'] != body['policyRevision'] or
                preset['conditionsDigest'] != body['conditionsDigest']):
                _fail('stale_conditions', 'Conditions changed; review the available choices.')
            if preset['availability'] != 'available':
                _fail('preset_unavailable', 'The preset is unavailable; choose a listed alternative.')
            selection_body = {'requestId': body['requestId'], 'profileId': body['presetId'],
                              'revision': body['expectedRevision'], 'ref': ref}
            # Use the existing receipt namespace and recovery authority, but
            # fingerprint the accepted policy and conditions as well.
            def apply(db):
                ctx.resolve([ref])
                obj = profiles.load(ctx, body['presetId'])
                profiles.check_access(ctx, obj)
                if obj['_revision'] != body['expectedRevision']:
                    _fail('stale_profile', 'The profile has changed.')
                oid = profiles.digest([ctx.sid, ctx.actor['owner']])
                value = {'id': oid, 'profileId': body['presetId'],
                         'revision': body['expectedRevision'], 'ref': ref}
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?) '
                    'ON CONFLICT(kind,id) DO UPDATE SET revision=objects.revision+1,data=excluded.data',
                    (profiles.SELECTION, oid, ctx.sid, ctx.actor['owner'], json.dumps(value), ctx.store.now()))
                # Keep the exact accepted conditions beside the existing
                # profile.select receipt so recovery is read-only and verifiable.
                return {**value, 'requestId': body['requestId'],
                        'policyRevision': body['policyRevision'],
                        'conditionsDigest': body['conditionsDigest']}
            selection = profiles.write(ctx, 'profile.select', body['requestId'],
                                       {'selection': selection_body, 'conditions': body}, apply)
            return {'selection': selection, 'conditionsDigest': preset['conditionsDigest'],
                    'policyRevision': body['policyRevision']}

    def handle(self, handler, sid, actor, method, parts):
        if actor.get('sid') != sid or actor.get('role') != 'creator':
            _fail('not_found', 'Preset unavailable.', 404)
        ctx = Context(handler, sid, actor)
        with ctx.lock:
            body = handler.body()
            if parts == ['list'] and method == 'POST' and isinstance(body, dict) and set(body) == {'ref'}:
                result = self.list(ctx, body['ref'])
                def fence():
                    if self.list(ctx, body['ref']) != result:
                        _fail('stale_context', 'Preset conditions changed.')
            elif parts == ['choose'] and method == 'POST':
                result = self.choose(ctx, body)
                def fence():
                    current = self.list(ctx, body['ref'])
                    item = next((p for p in current['presets'] if p['id'] == body['presetId']), None)
                    if not item or item['conditionsDigest'] != result['conditionsDigest'] or item['availability'] != 'available':
                        _fail('stale_context', 'Preset conditions changed.')
                    selection, _ = profiles.current_selection(ctx)
                    if any(selection[k] != result['selection'][k] for k in ('id', 'profileId', 'revision', 'ref')):
                        _fail('stale_context', 'The selection changed.')
            else:
                _fail('not_found', 'Preset route unavailable.', 404)
            handler._w29_quality_final = fence
            return 200, result


def final_guard(handler):
    guard = getattr(handler, '_w29_quality_final', None)
    if not callable(guard):
        _fail('stale_context', 'Preset authorization unavailable.')
    guard()


def configure(policy_reader):
    return Presets(policy_reader)


def configure_wave20(authorize, facts):
    """Bind the actual creator-authorized Wave 20 projection and its fact reader."""
    if not callable(authorize) or not callable(facts):
        raise TypeError('Wave 20 authority and facts are required')
    from . import waves20_modes
    def read(ctx):
        return waves20_modes.get_policy(ctx.sid, ctx.actor,
            getattr(ctx.handler, '_auth_token', ''), authorize, facts)
    return Presets(read)
