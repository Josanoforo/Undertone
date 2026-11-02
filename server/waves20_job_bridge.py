"""Internal Wave 20 job bridge; trusted PRIMARY code supplies current authority.

Plan fields are data, never proof of public visibility.
"""
import hashlib
import json
import math
import re
from .waves20_delivery import Identity

# Included by the speech owner's generation key whenever approved rules exist.
SPOKEN_FORM_REVISION = 'approved-exact-terms-v1'

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def settings_digest(settings):
    return hashlib.sha256(canonical(settings).encode('utf-8')).hexdigest()


def validate_plan(identity, plan):
    """Validate a freshly resolved trusted plan, without conferring source rights.

    The caller must itself establish current source visibility, creator authority,
    actor rights, terminology and rule revisions; these fields are not certificates.
    The same resolver must be consulted again at dispatch, completion and delivery.
    """
    if not isinstance(identity, Identity) or not isinstance(plan, dict):
        raise ValueError('invalid plan')
    required = {'session', 'rightsPartition', 'source', 'sourceRevision', 'translationRevision',
                'terminologyRevision', 'scope', 'privateActor', 'text',
                'sourceLanguage', 'settings'}
    if set(plan) != required:
        raise ValueError('invalid plan fields')
    if any(plan[k] != v for k, v in (
        ('session', identity.session), ('rightsPartition', identity.rights_partition), ('source', identity.source),
        ('sourceRevision', identity.source_revision),
        ('translationRevision', identity.translation_revision),
        ('terminologyRevision', identity.terminology_revision),
        ('privateActor', identity.private_actor))):
        raise ValueError('identity mismatch')
    if plan['scope'] not in ('public', 'private') or (plan['scope'] == 'private') != bool(identity.private_actor):
        raise ValueError('invalid rights partition')
    text = plan['text']
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 6000:
        raise ValueError('invalid text')
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != identity.text_digest:
        raise ValueError('text mismatch')
    if plan['sourceLanguage'] not in ('en', 'es') or identity.language not in ('en', 'es'):
        raise ValueError('invalid language')
    settings = plan['settings']
    if not isinstance(settings, dict) or settings_digest(settings) != identity.settings_digest:
        raise ValueError('settings mismatch')
    required_settings = {'engine', 'model', 'voice', 'outputFormat', 'adapterVersion',
                         'modelVersion', 'speed', 'ruleSetId', 'ruleRevision',
                         'ruleDigest', 'approvedRules', 'controls', 'glossary', 'terminology', 'hostedBinding'}
    if set(settings) != required_settings:
        raise ValueError('invalid settings')
    if any(settings[k] != v for k, v in (('engine', identity.engine), ('model', identity.model),
                                         ('voice', identity.voice), ('outputFormat', identity.output_format))):
        raise ValueError('engine identity mismatch')
    if identity.engine not in ('sapi', 'local_neural', 'elevenlabs') or identity.output_format != 'audio/wav':
        raise ValueError('unsupported engine or format')
    for key in ('adapterVersion', 'modelVersion', 'ruleSetId', 'ruleRevision', 'ruleDigest'):
        if not isinstance(settings[key], str) or not settings[key] or len(settings[key]) > 512:
            raise ValueError('invalid revision')
    rules = settings['approvedRules']
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError('invalid rules')
    for rule in rules:
        if (not isinstance(rule, dict) or set(rule) != {'id','language','term','alias','approved'} or
            rule['language'] not in ('en','es') or type(rule['approved']) is not bool or
            not isinstance(rule['id'], str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,160}', rule['id']) or
            any(not isinstance(rule[k], str) or not 1 <= len(rule[k].strip()) <= 100 or
                any(c in rule[k] for c in '<>\r\n') for k in ('term','alias'))):
            raise ValueError('invalid rule')
    if settings['ruleDigest'] != settings_digest(rules):
        raise ValueError('rule digest mismatch')
    if any(rule['approved'] for rule in rules) and identity.translation_revision.startswith('policy:'):
        raise ValueError('spoken forms require a revision-bound speech identity')
    speed = settings['speed']
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not .5 <= speed <= 2:
        raise ValueError('invalid speed')
    if identity.engine == 'elevenlabs' and not isinstance(settings['hostedBinding'], dict):
        raise ValueError('missing hosted binding')
    if identity.engine != 'elevenlabs' and settings['hostedBinding'] is not None:
        raise ValueError('unexpected hosted binding')
    if identity.engine != 'local_neural' and speed != 1:
        raise ValueError('unsupported speed')
    # Current local adapters expose no aliases, phonemes or alignment; the
    # trusted planner must not silently replace the original words.
    if settings['controls'] != []:
        raise ValueError('unsupported controls')
    if not isinstance(settings['glossary'], list) or len(settings['glossary']) > 50:
        raise ValueError('invalid glossary')
    if settings['terminology'] is not None and not isinstance(settings['terminology'], dict):
        raise ValueError('invalid terminology')
    # Return a deep copy so later mutation cannot alter a validated snapshot.
    return json.loads(canonical(plan))

class JobBridge:
    """Internal job bridge. Resolver is trusted in-process PRIMARY code.

    A resolver returns the *current* complete plan for identity and phase, or
    None. It must check real source rights and creator authority itself. This
    class is not a public route or a subscriber authorization mechanism.
    """
    def __init__(self, resolve, resolve_translation_binding=None):
        if not callable(resolve):
            raise ValueError('resolver required')
        self.resolve = resolve
        self.resolve_translation_binding = resolve_translation_binding

    def _plan(self, identity, phase, expected=None):
        try:
            plan = validate_plan(identity, self.resolve(identity, phase))
            if expected is not None and plan != expected:
                return None
            return plan
        except Exception:
            return None

    def generate(self, identity):
        """Scheduler callback; only PRIMARY may configure and dispatch provider work."""
        import base64
        from dataclasses import asdict
        from . import store, admission, phase12_jobs, phase12_translation, phase12_tts, waves17_tts_local

        plan = self._plan(identity, 'dispatch')
        if plan is None:
            return 'unavailable', None
        # Cross-language effects require the trusted current policy resolver.
        if plan['sourceLanguage'] != identity.language and not callable(self.resolve_translation_binding):
            return 'unavailable', None
        settings = plan['settings']
        if identity.engine == 'sapi':
            if (identity.voice != phase12_tts.VOICES.get(identity.language) or
                settings['adapterVersion'] != phase12_jobs.sapi_revision() or
                settings['modelVersion'] != phase12_jobs.sapi_revision()):
                return 'unavailable', None
        elif identity.engine == 'local_neural' and (identity.model != 'piper-vits' or identity.language not in waves17_tts_local.VOICES or
              identity.voice != waves17_tts_local.VOICES[identity.language][0] or
              settings['adapterVersion'] != waves17_tts_local.ADAPTER_REV or
              settings['modelVersion'] != waves17_tts_local.MODEL_REV):
            return 'unavailable', None
        key = hashlib.sha256(canonical(asdict(identity)).encode('utf-8')).hexdigest()
        fingerprint = hashlib.sha256(canonical(plan).encode('utf-8')).hexdigest()
        actor = '\x00wave20-internal'
        # One committed intent per exact identity, prior to any native/model work.
        with store.LOCK, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM phase12_jobs WHERE session_id=? AND actor_id=? AND request_id=?',
                             (identity.session, actor, key)).fetchone()
            if row:
                db.commit()
            else:
                count = db.execute("SELECT COUNT(*) FROM phase12_jobs").fetchone()[0]
                if count >= phase12_jobs.MAX_RECEIPTS:
                    db.commit()
                    return 'unavailable', None
                used = db.execute("SELECT COALESCE(SUM(length(media)),0) FROM phase12_jobs WHERE (state='w20_complete' OR (kind='speech' AND state='complete'))").fetchone()[0]
                pending = db.execute("SELECT COUNT(*) FROM phase12_jobs WHERE state='w20_running' OR (kind='speech' AND state IN ('queued','running'))").fetchone()[0]
                if used + (pending + 1) * 8 * 1024 * 1024 > phase12_jobs.MAX_SPEECH_CACHE:
                    db.commit()
                    return 'unavailable', None
                db.execute("INSERT INTO phase12_jobs(session_id,actor_id,credential_hash,role,request_id,kind,fingerprint,payload,ref,source_id,state,result,media,timing,transport) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (identity.session,actor,'','w20_internal',key,'w20_speech',fingerprint,
                            canonical({'identity':asdict(identity),'sourceLanguage':plan['sourceLanguage']}),'{}',identity.source,'w20_running',None,None,'{}','w20_intent'))
                db.commit()
        if row:
            if row['fingerprint'] != fingerprint:
                return 'unavailable', None
            if row['state'] != 'w20_complete' or row['media'] is None or not row['result']:
                return 'unknown', None
            result = json.loads(row['result'])
            if result.get('audioSha256') != hashlib.sha256(row['media']).hexdigest():
                return 'unavailable', None
            if identity.engine == 'elevenlabs':
                from . import waves17_hosted_facade as hosted
                try:
                    account, _, _ = hosted.current(len(result.get('spokenText', result['text'])))
                    if hosted.binding(account) != settings['hostedBinding']:
                        return 'unavailable', None
                except Exception:
                    return 'unavailable', None
            # Recheck source and subscribers after any hosted observation.
            if self._plan(identity, 'reuse', plan) is None:
                return 'unavailable', None
            result['audioBase64'] = base64.b64encode(row['media']).decode('ascii')
            return 'ready', result
        try:
            def eligible():
                return self._plan(identity, 'effect', plan) is not None
            def mark(stage):
                with store.LOCK, store.connect() as db:
                    return db.execute("UPDATE phase12_jobs SET transport=? WHERE session_id=? AND actor_id=? AND request_id=? AND state='w20_running'",
                                      (stage,identity.session,actor,key)).rowcount == 1
            if not eligible():
                return 'unavailable', None
            text = plan['text']
            if plan['sourceLanguage'] != identity.language:
                parts = identity.translation_revision.split(':')
                if (len(parts) not in (3, 4) or parts[0] != 'translation'
                        or not parts[1].isdigit() or str(int(parts[1])) != parts[1] or int(parts[1]) < 1
                        or (len(parts) == 4 and not re.fullmatch('[a-f0-9]{64}', parts[3]))):
                    return 'unavailable', None
                revision = int(parts[1])
                binding = self.resolve_translation_binding(identity, 'effect')
                if (not isinstance(binding, dict) or set(binding) != {'choice', 'provider', 'model', 'sessionCapUsd'} or
                    (binding['choice'], binding['provider']) not in (('local', 'ollama'), ('hosted', 'claude')) or
                    not isinstance(binding['model'], str) or not binding['model'] or
                    parts[2] != settings_digest({'policyRevision': revision, 'binding': binding})):
                    return 'unavailable', None
                with admission.lease(identity.session):
                    with admission.operation(identity.session):
                        if not eligible() or self.resolve_translation_binding(identity, 'effect') != binding:
                            return 'unavailable', None
                        if not mark('w20_translation_attempting'):
                            return 'unknown', None
                        if binding['choice'] == 'hosted':
                            # The provider bounds its text input by MAX_INPUT bytes;
                            # reserve its maximum possible request, including its
                            # fixed overhead and output ceiling, in the session ledger.
                            from decimal import Decimal
                            from . import claude_provider
                            amount = (Decimal(claude_provider.MAX_INPUT + 512) * Decimal(claude_provider.INPUT_RATE) +
                                      Decimal(claude_provider.MAX_OUTPUT) * Decimal(claude_provider.OUTPUT_RATE)) / Decimal(1000000)
                            admission.reserve_session_cost(identity.session, key, amount, binding['sessionCapUsd'],
                                policy_revision=revision, translation_choice=binding['choice'])
                            if not mark('w20_translation_reserved'):
                                return 'unknown', None
                        if not eligible() or self.resolve_translation_binding(identity, 'effect') != binding:
                            return 'unavailable', None
                        if not mark('w20_translation_dispatching'):
                            return 'unknown', None
                        translated = phase12_translation.translate(text, plan['sourceLanguage'], identity.language,
                            settings['glossary'], terminology=settings['terminology'],
                            expected_provider=binding['provider'], expected_model=binding['model'])
                        if translated['provider'] != binding['provider'] or translated['model'] != binding['model']:
                            return 'unknown', None
                if not mark('w20_translation_returned'):
                    return 'unknown', None
                text = translated['text']
                mode = 'translated'
                translation = {'uncertainty': translated['uncertainty'], 'provider': translated['provider'], 'model': translated['model']}
            else:
                mode, translation = 'source_reading', None
            # Apply creator-approved literal forms only after translation. Keep
            # the display text intact and bind the preparation to the speech
            # identity; the resolver rechecks the exact rules at every fence.
            spoken = text
            preparation = None
            if any(rule['approved'] for rule in settings['approvedRules']):
                from . import waves21_pronunciation
                if waves21_pronunciation.SPOKEN_FORM_REVISION != SPOKEN_FORM_REVISION:
                    return 'unavailable', None
                preparation = waves21_pronunciation.prepare_spoken_text(text, identity.language, settings['approvedRules'])
                spoken = preparation['text']
            if not eligible() or not 1 <= len(spoken.strip()) <= 600 or len(spoken) > 600:
                return 'unavailable', None
            if identity.engine == 'local_neural':
                if not mark('w20_local_attempting'):
                    return 'unknown', None
                audio, meta = waves17_tts_local.synthesize(spoken, identity.language, identity.voice,
                                                          eligible=eligible, speed=settings['speed'])
            elif identity.engine == 'sapi':
                if not mark('w20_local_attempting'):
                    return 'unknown', None
                audio, meta = phase12_tts.synthesize(spoken, identity.language)
            else:
                from . import waves17_hosted_facade as hosted, waves17_tts_elevenlabs as adapter
                import uuid
                account, transport, amount = hosted.current(len(spoken))
                binding = hosted.binding(account)
                if (binding != settings['hostedBinding'] or binding['model'] != identity.model or
                    binding['voice'] != identity.voice or binding['adapterVersion'] != settings['adapterVersion'] or
                    binding['modelVersion'] != settings['modelVersion']):
                    return 'unavailable', None
                if not eligible():
                    return 'unavailable', None
                # Bind the speech charge to the current durable session policy.
                # The admission function validates this snapshot atomically.
                from . import lifecycle, waves20_modes
                def speech_policy():
                    with store.LOCK, store.connect() as db:
                        row = db.execute("SELECT owner_id,data FROM objects WHERE kind='session' AND id=? AND session_id=?",
                                         (identity.session, identity.session)).fetchone()
                        if not row or not row['owner_id'] or not lifecycle.active(json.loads(row['data'])):
                            return None
                        _, policy = waves20_modes._current(db, identity.session, row['owner_id'])
                        if not policy:
                            return None
                        selected = policy['operations']['speech']
                        if 'hosted' not in [selected['primary'], *selected['alternatives']]:
                            return None
                        return (policy['revision'], policy['sessionCapUsd'])
                policy = speech_policy()
                if policy is None or not eligible():
                    return 'unavailable', None
                # This exact durable journal claim is distinct from the Phase 12
                # receipt and is the existing shared spending authority.
                if not mark('w20_hosted_attempting'):
                    return 'unknown', None
                speech_key = hashlib.sha256(('w20-hosted-speech:' + key).encode('ascii')).hexdigest()
                admission.reserve_session_cost(identity.session, speech_key, amount, policy[1],
                    policy_revision=policy[0], speech_choice='hosted')
                hosted.reserve('tts-' + key, amount)
                if not mark('w20_hosted_reserved'):
                    return 'unknown', None
                if not eligible() or speech_policy() != policy:
                    return 'unavailable', None
                revisions = {'text_revision': hashlib.sha256(spoken.encode('utf-8')).hexdigest(),
                             'source_id': identity.source, 'source_revision': identity.source_revision,
                             'translation_id': key, 'translation_revision': identity.translation_revision,
                             'terminology_revision': identity.terminology_revision}
                request = adapter.Request(text=spoken, language=identity.language, voice_id=identity.voice,
                    model=identity.model, settings={'stability':0.5,'similarity_boost':0.75,'style':0.0,'use_speaker_boost':True},
                    revisions=revisions, request_id=str(uuid.UUID(key[:32])))
                if not mark('w20_hosted_dispatching'):
                    return 'unknown', None
                def speech_eligible():
                    return eligible() and speech_policy() == policy
                audio, meta = adapter.synthesize(account.config, request, transport, lambda: not speech_eligible(), speech_eligible)
                if not speech_eligible():
                    return 'unavailable', None
            if not eligible() or not isinstance(audio, bytes) or not audio or len(audio) > 6 * 1024 * 1024:
                return 'unavailable', None
            result = {'mode': mode, 'text': text, 'translation': translation,
                      'audio': meta, 'audioSha256': hashlib.sha256(audio).hexdigest(), 'alignment': None, 'operationId': key}
            if preparation is not None:
                result['sourceText'] = plan['text']
                result['spokenText'] = spoken
                result['spokenFormPreparation'] = preparation
            serialized = canonical(result)
            # Resolve subscribers before taking the store lock: the resolver
            # takes the scheduler lock before checking current source rights.
            # Delivery and receipt reuse independently recheck those rights.
            if not eligible():
                return 'unavailable', None
            with store.LOCK, store.connect() as db:
                n = db.execute("UPDATE phase12_jobs SET state='w20_complete',result=?,media=?,transport='w20_effect_complete' WHERE session_id=? AND actor_id=? AND request_id=? AND fingerprint=? AND state='w20_running'",
                               (serialized,audio,identity.session,actor,key,fingerprint)).rowcount
            if not n:
                return 'unknown', None
            result['audioBase64'] = base64.b64encode(audio).decode('ascii')
            return 'ready', result
        except Exception:
            # Dispatched work or its accounting may have taken effect. Never retry.
            return 'unknown', None
        finally:
            # A finished callback no longer needs an in-flight media allocation;
            # keep the identity permanently unknown and never clear provider holds.
            # A crash can leave w20_running, which remains conservatively reserved.
            try:
                with store.LOCK, store.connect() as db:
                    db.execute("UPDATE phase12_jobs SET state='w20_unknown' WHERE session_id=? AND actor_id=? AND request_id=? AND state='w20_running'",
                               (identity.session, actor, key))
            except Exception:
                pass

