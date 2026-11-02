"""Read-only current Wave 25 listening and completed-media authorities."""
from dataclasses import dataclass
import hashlib
import math
from email.parser import BytesParser
import time

from . import waves17_tts_local as local, waves20_modes, waves20_policy_access
from . import waves23_speech_profiles as profiles
from .phase10_common import Phase10Error


def installed_voice_descriptor(language):
    """Read the fixed local installation only; the identity is not publisher semver."""
    if language not in local.VOICES:
        return {'ok': False, 'reason': 'unsupported_language'}
    try:
        voice, folder = local.VOICES[language]
        base = local.ROOT / 'models' / folder
        model = base / (voice + '.onnx')
        tokens = base / 'tokens.txt'
        data = base / 'espeak-ng-data'
        if not local.PYTHON.is_file() or not data.is_dir():
            raise OSError('missing installation')
        def sha(path):
            if path.is_symlink() or not path.is_file():
                raise OSError('missing or linked asset')
            with path.open('rb') as stream:
                return hashlib.file_digest(stream, 'sha256').hexdigest()
        model_hash = sha(model)
        if model_hash != local.WEIGHT_SHA256[language]:
            return {'ok': False, 'reason': 'model_integrity'}
        token_hash = sha(tokens)
        if data.is_symlink():
            raise OSError('linked asset directory')
        files = []
        for path in sorted(data.rglob('*')):
            if path.is_symlink():
                raise OSError('linked asset')
            if path.is_file():
                files.append([path.relative_to(data).as_posix(), sha(path)])
        if not files:
            raise OSError('empty phonemizer data')
        versions = {}
        for package, directory in (('sherpa_onnx', 'sherpa_onnx-1.12.40.dist-info'),
                                   ('sherpa_onnx_core', 'sherpa_onnx_core-1.12.40.dist-info')):
            metadata = local.ROOT / 'venv' / 'Lib' / 'site-packages' / directory / 'METADATA'
            if metadata.is_symlink():
                raise OSError('linked metadata')
            record = BytesParser().parsebytes(metadata.read_bytes(), headersonly=True)
            if record.get('Version') != '1.12.40' or record.get('Name', '').replace('-', '_').lower() != package:
                return {'ok': False, 'reason': 'runtime_metadata_mismatch'}
            versions[package] = record['Version']
        facts = {'language': language, 'voiceId': voice, 'model': 'piper-vits',
                 'modelVersion': local.MODEL_REV, 'adapterVersion': local.ADAPTER_REV,
                 'modelSha256': model_hash, 'tokensSha256': token_hash,
                 'phonemizerSha256': profiles.digest(files), 'runtimeVersions': versions}
        return {'ok': True, **facts, 'voiceVersion': 'asset-sha256:' + profiles.digest(facts)}
    except (OSError, ValueError, KeyError):
        return {'ok': False, 'reason': 'local_metadata_unavailable'}


def bind_installed_voice(ctx, selection, projection, *, lifetime=120):
    """Bind a verified installed identity to the current authorized selection."""
    if type(lifetime) not in (int, float) or not math.isfinite(lifetime) or not 0 < lifetime <= 300:
        raise ValueError('invalid observation lifetime')
    try:
        with ctx.lock:
            selected, obj = profiles.current_selection(ctx)
            p = obj['profile']
            current = {'profileId': obj['id'], 'profileRevision': obj['_revision'],
                       'configDigest': profiles.digest(p), 'ref': selected['ref'], 'language': p['language']}
            if current != selection or profiles.projection(obj) != projection:
                return {'ok': False, 'reason': 'selection_changed'}
            if ctx.resolve([selected['ref']])[0]['source'].get('language') != p['language']:
                from .waves25_listening_recovery import prepared_translation
                if prepared_translation(ctx, selection, obj)['state'] != 'ready':
                    return {'ok': False, 'reason': 'translated_audio_unavailable'}
            descriptor = installed_voice_descriptor(p['language'])
            if not descriptor['ok']:
                return descriptor
            if any(p[k] != value for k, value in (
                ('engine', 'local_neural'), ('model', descriptor['model']),
                ('modelVersion', descriptor['modelVersion']), ('voiceId', descriptor['voiceId']),
                ('adapterVersion', descriptor['adapterVersion']), ('voiceVersion', descriptor['voiceVersion']))):
                return {'ok': False, 'reason': 'profile_incompatible', 'installed': descriptor,
                        'remedy': 'Create or update a creator profile with the installed identity, approve it and reselect it.'}
            now = time.time()
            observation = VoiceObservation(ctx.sid, ctx.actor['owner'], profiles.digest(selection),
                                           profiles.digest(p), descriptor['voiceVersion'], now + lifetime, now)
            return {'ok': True, 'observation': observation, 'installed': descriptor}
    except (Phase10Error, KeyError, TypeError, ValueError):
        return {'ok': False, 'reason': 'current_authority_unavailable'}


@dataclass(frozen=True)
class VoiceObservation:
    """Operator-observed voice version for one actor, source and profile revision."""
    session: str
    actor: str
    selection_digest: str
    profile_digest: str
    voice_version: str
    expires_at: float
    observed_at: float


class ListeningAuthorities:
    def __init__(self, voice_observation, delivery, edition_id=None):
        from .source_translation_delivery import SourceTranslationBinding
        if not isinstance(voice_observation, VoiceObservation):
            raise TypeError('A bound voice observation is required')
        if not isinstance(delivery, SourceTranslationBinding):
            raise TypeError('The current delivery binding is required')
        self.voice_observation = voice_observation
        self.delivery = delivery
        self.edition_id = edition_id

    def capabilities(self, ctx, selection, projection, mode):
        """Check exact selection, current local policy and local adapter assets."""
        try:
            with ctx.lock:
                selected, obj = profiles.current_selection(ctx)
                current = {'profileId': obj['id'], 'profileRevision': obj['_revision'],
                           'configDigest': profiles.digest(obj['profile']),
                           'ref': selected['ref'], 'language': obj['profile']['language']}
                if selection != current or projection != profiles.projection(obj) or mode != 'listen':
                    return False
                obs = self.voice_observation
                if (obs.session != ctx.sid or obs.actor != ctx.actor['owner'] or
                    obs.selection_digest != profiles.digest(selection) or
                    obs.profile_digest != profiles.digest(obj['profile']) or
                    obs.voice_version != obj['profile']['voiceVersion'] or
                    type(obs.expires_at) not in (int, float) or not math.isfinite(obs.expires_at) or
                    type(obs.observed_at) not in (int, float) or not math.isfinite(obs.observed_at) or
                    not obs.observed_at <= time.time() < obs.expires_at or
                    not 0 < obs.expires_at - obs.observed_at <= 300):
                    return False
                p = obj['profile']
                descriptor = installed_voice_descriptor(p['language'])
                if not descriptor.get('ok') or descriptor['voiceVersion'] != obs.voice_version:
                    return False
                if (p['engine'] != 'local_neural' or p['model'] != 'piper-vits' or
                    p['language'] not in local.VOICES or p['voiceId'] != local.VOICES[p['language']][0] or
                    p['modelVersion'] != local.MODEL_REV or p['adapterVersion'] != local.ADAPTER_REV):
                    return False
                if ctx.resolve([selected['ref']])[0]['source'].get('language') != p['language']:
                    from .waves25_listening_recovery import prepared_translation
                    if prepared_translation(ctx, selection, obj)['state'] != 'ready':
                        return False
                with ctx.store.connect() as db:
                    row = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?",
                                     (ctx.sid, ctx.sid)).fetchone()
                    _, policy = waves20_modes._current(db, ctx.sid, row['owner_id']) if row else (None, None)
                return bool(policy and waves20_policy_access.current_local_policy(ctx.sid, policy['revision']))
        except (Phase10Error, KeyError, TypeError, ValueError):
            return False

    def accessibility_capabilities(self, ctx, selection, projection, feature, value):
        """Inspect current edition tracks or a completed exact description receipt."""
        import hashlib
        import json
        from . import waves22_edition as edition, waves21_speech_runtime as speech
        from .waves20_delivery import Identity, Subscriber
        from .waves20_job_bridge import validate_plan
        try:
            with ctx.lock:
                selected, obj = profiles.current_selection(ctx)
                current = {'profileId': obj['id'], 'profileRevision': obj['_revision'],
                    'configDigest': profiles.digest(obj['profile']), 'ref': selected['ref'],
                    'language': obj['profile']['language']}
                if current != selection or profiles.projection(obj) != projection or not self.edition_id:
                    return False
                manifest = edition.project_edition(ctx, self.edition_id, selection['language'],
                    released=edition.released_metadata)['manifest']
                if selection['ref'] not in [x['ref'] for x in manifest['provenance']['sources']]:
                    return False
                if feature == 'captionMode' and value in ('original', 'translated', 'both'):
                    kinds = {'original', 'translation'} if value == 'both' else {
                        'original' if value == 'original' else 'translation'}
                    available = {track['kind'] for track in manifest['tracks']
                        if track['kind'] in kinds and
                        track['language'] == (manifest['sourceLanguage'] if track['kind'] == 'original' else selection['language']) and
                        any(cue.get('sourceRef') == selection['ref']
                                                          for cue in track['cues'])}
                    return available == kinds
                if feature != 'descriptionEnabled' or value is not True:
                    return False
                description = manifest['descriptionAudio']
                if (description.get('state') != 'available' or description.get('sourceRef') != selection['ref'] or
                    not self.capabilities(ctx, selection, projection, 'listen')):
                    return False
                with ctx.store.connect() as db:
                    rows = db.execute("SELECT request_id,fingerprint,payload,result,media FROM phase12_jobs "
                        "WHERE session_id=? AND actor_id=? AND kind='w20_speech' AND source_id=? AND state='w20_complete'",
                        (ctx.sid, '\x00wave20-internal', 'edition:' + self.edition_id)).fetchall()
                for row in rows:
                    try:
                        identity = Identity(**json.loads(row['payload'])['identity'])
                        subscriber = Subscriber(ctx.actor['owner'], identity.source,
                            int(identity.source_revision), speech._credential(ctx))
                        plan = self.delivery.reading._plan(identity, subscriber)
                        if (identity.engine != obj['profile']['engine'] or identity.model != obj['profile']['model'] or
                            identity.voice != obj['profile']['voiceId'] or identity.language != selection['language'] or
                            self.delivery.eligible(identity, subscriber, 'final') is not True or
                            not plan or validate_plan(identity, plan) != plan or
                            plan['settings']['speed'] != obj['profile']['rate'] or
                            row['request_id'] != profiles.digest(vars(identity)) or
                            row['fingerprint'] != profiles.digest(plan) or not row['media'] or
                            json.loads(row['result'])['audioSha256'] != hashlib.sha256(row['media']).hexdigest()):
                            continue
                        return True
                    except (Phase10Error, KeyError, TypeError, ValueError):
                        continue
                return False
        except (Phase10Error, KeyError, TypeError, ValueError):
            return False

    def receipt_authority(self, ctx, identity_dict, binding):
        """Recheck real subscriber, plan and existing delivery policy, without effects."""
        from . import waves21_speech_runtime as speech
        from .waves20_job_bridge import validate_plan
        try:
            with ctx.lock:
                profiles.check_generation_binding(ctx, binding)
                marker = ctx.store.get(profiles.BINDING,
                    profiles.digest([ctx.sid, ctx.actor['owner'], binding['requestId']]), ctx.sid)
                if not marker:
                    return False
                if marker.get('approvedRequest') is not None:
                    identity, subscriber, plan = profiles.approved_generation_subscriber(
                        ctx, binding['runId'], binding['requestId'])
                else:
                    identity, subscriber, plan = speech.generation_subscriber(
                        ctx, binding['runId'], binding['requestId'])
                if vars(identity) != identity_dict or profiles.digest(identity_dict) != binding['identityDigest']:
                    return False
                selected, obj = profiles.current_selection(ctx)
                selection = {'profileId': obj['id'], 'profileRevision': obj['_revision'],
                    'configDigest': profiles.digest(obj['profile']), 'ref': selected['ref'],
                    'language': obj['profile']['language']}
                if not self.capabilities(ctx, selection, profiles.projection(obj), 'listen'):
                    return False
                validate_plan(identity, plan)
                return self.delivery.eligible(identity, subscriber, 'final') is True
        except (Phase10Error, KeyError, TypeError, ValueError):
            return False
