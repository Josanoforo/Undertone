"""Store-backed local source-reading plans for the Wave 20 delivery bridge.

No bearer token is retained here.
"""
import hashlib
import json
import threading
from dataclasses import asdict, replace

from . import store, waves17_tts_local, waves18_records, waves20_modes
from . import waves20_policy_access, waves20_source_access
from .phase10_common import Context, Phase10Error
from .waves20_delivery import Identity, Subscriber
from .waves20_job_bridge import settings_digest


class LocalSourceReading:
    """Resolve explicit local neural source-reading with fresh authority checks."""
    def __init__(self):
        self.scheduler = None

    @staticmethod
    def _speech_binding(identity, subscriber, revision=None):
        """Persist and recheck the policy selected for this exact speech intent."""
        from . import waves21_speech_runtime as speech
        from . import waves23_speech_profiles as profiles, waves24_channel_pack as pack
        from .waves20_job_bridge import validate_plan
        with store.LOCK:
            # A stored archive binding is authoritative; never reinterpret a
            # revoked or mismatched archive request as another speech intent.
            if store.get('w24profilebinding', subscriber.authority, identity.session):
                if not pack.eligible_archived_subscriber(identity, subscriber):
                    return None
                plan = pack.resolve_archived_generation(identity)
            elif profiles.eligible_approved_subscriber(identity, subscriber):
                plan = profiles.resolve_approved_generation(identity)
            elif speech.eligible_generation_subscriber(identity, subscriber):
                plan = speech.resolve_generation(identity)
            else:
                return None
            try:
                validate_plan(identity, plan)
                settings = plan['settings']
                # Translation has a separate paid admission path; do not silently
                # turn a source-reading request into a provider call.
                if (plan['sourceLanguage'] != identity.language or
                    identity.engine != 'local_neural' or identity.model != 'piper-vits' or
                    identity.language not in waves17_tts_local.VOICES or
                    identity.voice != waves17_tts_local.VOICES[identity.language][0] or
                    settings['adapterVersion'] != waves17_tts_local.ADAPTER_REV or
                    settings['modelVersion'] != waves17_tts_local.MODEL_REV):
                    return None
            except (ValueError, TypeError, KeyError):
                return None
            fingerprint = hashlib.sha256(json.dumps(asdict(identity), sort_keys=True,
                separators=(',', ':')).encode()).hexdigest()
            # A credential can submit more than one speech identity.  Binding
            # only the credential made the first request permanently exclude
            # every later source or revision for that subscriber.
            key = hashlib.sha256(('w21-policy:' + subscriber.authority + ':' + fingerprint).encode()).hexdigest()
            legacy_key = hashlib.sha256(('w21-policy:' + subscriber.authority).encode()).hexdigest()
            with store.connect() as db:
                identity_key = hashlib.sha256(('w21-identity-policy:' + fingerprint).encode()).hexdigest()
                identity_row = db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND session_id=?',
                    ('w20speechidentitypolicy', identity_key, identity.session)).fetchone()
                row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                                 ('w20speechpolicybinding', key, identity.session)).fetchone()
                if not row:
                    legacy = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                                        ('w20speechpolicybinding', legacy_key, identity.session)).fetchone()
                    if legacy and json.loads(legacy['data']).get('identity') == fingerprint:
                        row = legacy
                if row:
                    binding = json.loads(row['data'])
                    if row['owner_id'] != subscriber.actor or binding.get('identity') != fingerprint:
                        return None
                    if revision is not None and binding.get('revision') != revision:
                        return None
                    revision = binding.get('revision')
                elif revision is not None:
                    if not waves20_policy_access.current_local_policy(identity.session, revision):
                        return None
                    if identity_row and json.loads(identity_row['data']).get('revision') != revision:
                        return None
                    if not identity_row:
                        db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                            ('w20speechidentitypolicy', identity_key, identity.session, subscriber.actor,
                             json.dumps({'revision': revision}), store.now()))
                    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                        ('w20speechpolicybinding', key, identity.session, subscriber.actor,
                         json.dumps({'identity': fingerprint, 'revision': revision}), store.now()))
                else:
                    return None
                if not identity_row and row:
                    return None
                if identity_row and json.loads(identity_row['data']).get('revision') != revision:
                    return None
            return plan if waves20_policy_access.current_local_policy(identity.session, revision) else None

    @staticmethod
    def authorize(handler, sid, actor):
        try:
            return Context(handler, sid, actor).check_actor() == actor
        except (Phase10Error, ValueError, TypeError):
            return False

    @staticmethod
    def _settings(language):
        rules = []
        return {'engine': 'local_neural', 'model': 'piper-vits',
                'voice': waves17_tts_local.VOICES[language][0],
                'outputFormat': 'audio/wav',
                'adapterVersion': waves17_tts_local.ADAPTER_REV,
                'modelVersion': waves17_tts_local.MODEL_REV,
                'speed': 1.0, 'ruleSetId': 'none', 'ruleRevision': '0',
                'ruleDigest': settings_digest(rules), 'approvedRules': rules,
                'controls': [], 'glossary': [], 'terminology': None,
                'hostedBinding': None}

    @staticmethod
    def _hosted_settings(language):
        from . import waves17_hosted_facade as hosted
        account, _, _ = hosted.current(1)
        if language not in account.config.languages:
            raise ValueError('Hosted language unavailable')
        binding = hosted.binding(account)
        rules = []
        return {'engine': 'elevenlabs', 'model': binding['model'],
                'voice': binding['voice'], 'outputFormat': 'audio/wav',
                'adapterVersion': binding['adapterVersion'], 'modelVersion': binding['modelVersion'],
                'speed': 1.0, 'ruleSetId': 'none', 'ruleRevision': '0',
                'ruleDigest': settings_digest(rules), 'approvedRules': rules,
                'controls': [], 'glossary': [], 'terminology': None,
                'hostedBinding': binding}

    @staticmethod
    def _policy_revision(identity):
        value = identity.translation_revision
        if not value.startswith('policy:') or not value[7:].isdigit():
            return None
        number = int(value[7:])
        return number if str(number) == value[7:] and number > 0 else None

    @staticmethod
    def _edition_description(sid, edition_id, language, subscriber):
        """Rebuild the selected description with the subscriber's current credential."""
        from . import waves22_edition
        if subscriber is None:
            return None
        with store.LOCK, store.connect() as db:
            row = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?',
                             (subscriber.authority,)).fetchone()
        if not row or row['session_id'] != sid or row['owner_id'] != subscriber.actor or row['role'] not in ('creator', 'viewer'):
            return None
        actor = {'sid': sid, 'owner': row['owner_id'], 'role': row['role']}
        ctx = Context(None, sid, actor, credential_digest=subscriber.authority)
        ctx.check_actor()
        description = waves22_edition.project_edition(ctx, edition_id, language,
            released=waves22_edition.released_metadata)['manifest']['descriptionAudio']
        if description.get('state') != 'available' or description.get('language') != language:
            return None
        return waves22_edition.guard_description(ctx, edition_id, language, description)

    def _plan(self, identity, subscriber):
        try:
            with store.LOCK:
                revision = self._policy_revision(identity)
                if revision is None or identity.language not in waves17_tts_local.VOICES:
                    return None
                if identity.engine == 'elevenlabs':
                    if not waves20_policy_access.current_hosted_speech_policy(identity.session, revision):
                        return None
                    settings = self._hosted_settings(identity.language)
                else:
                    if not waves20_policy_access.current_local_policy(identity.session, revision):
                        return None
                    settings = self._settings(identity.language)
                if (identity.engine != settings['engine'] or identity.model != settings['model'] or
                        identity.voice != settings['voice'] or identity.output_format != settings['outputFormat'] or
                        identity.settings_digest != settings_digest(settings) or (not identity.source.startswith('edition:') and identity.terminology_revision != 'none')):
                    return None
                if identity.private_actor:
                    if identity.rights_partition != 'private:' + identity.private_actor or subscriber is None:
                        return None
                    result = waves20_source_access.private_asr_source(identity, subscriber)
                    if not result:
                        return None
                    source, moment, _ = result
                    text, language = moment.get('text'), source.get('language')
                else:
                    if identity.rights_partition != 'approved-record':
                        return None
                    if identity.source.startswith('edition:'):
                        description = self._edition_description(identity.session, identity.source[8:], identity.language, subscriber)
                        if (not description or str(description['selectionRevision']) != identity.source_revision or
                                identity.terminology_revision != 'edition:' + settings_digest(description)):
                            return None
                        record_identity = replace(identity, source='record:' + description['recordId'],
                                                  source_revision=str(description['recordVersion']))
                        projection = waves20_source_access.approved_record_source(record_identity, subscriber)
                        if not projection or projection['interpretation'] != description['text']:
                            return None
                    else:
                        projection = waves20_source_access.approved_record_source(identity, subscriber)
                        if not projection:
                            return None
                    text, language = projection['interpretation'], projection['language']
                if (language != identity.language or not isinstance(text, str) or
                        not 1 <= len(text.strip()) <= 600 or len(text) > 600):
                    return None
                return {'session': identity.session, 'rightsPartition': identity.rights_partition,
                        'source': identity.source, 'sourceRevision': identity.source_revision,
                        'translationRevision': identity.translation_revision,
                        'terminologyRevision': identity.terminology_revision,
                        'scope': 'private' if identity.private_actor else 'public',
                        'privateActor': identity.private_actor, 'text': text,
                        'sourceLanguage': language, 'settings': settings}
        except (Phase10Error, ValueError, TypeError, KeyError, UnicodeError):
            return None

    def resolve_request(self, handler, sid, actor, body):
        with store.LOCK:
            if not self.authorize(handler, sid, actor) or body['choice'] not in ('local', 'hosted'):
                raise Phase10Error('unavailable', 'Delivery context unavailable.', 409)
            if body['source'].startswith('speech:'):
                if body['choice'] != 'local':
                    raise Phase10Error('unavailable', 'Speech delivery context unavailable.', 409)
                from . import waves21_speech_runtime as speech
                if actor.get('role') == 'viewer':
                    from . import waves23_speech_profiles as profiles, waves24_channel_pack as pack
                    ctx = Context(handler, sid, actor)
                    run_id = body['source'][len('speech:'):]
                    binding_id = profiles.digest([sid, actor['owner'], body['requestId']])
                    if store.get('w24profilebinding', binding_id, sid):
                        identity, subscriber, _ = pack.archived_generation_subscriber(ctx, run_id, body['requestId'])
                    else:
                        identity, subscriber, _ = profiles.approved_generation_subscriber(ctx, run_id, body['requestId'])
                    if (body['sourceRevision'] != int(identity.source_revision) or
                            body['language'] != identity.language or body['voice'] != identity.voice):
                        raise Phase10Error('stale_context', 'Speech delivery selection changed.', 409)
                else:
                    identity, subscriber = speech.resolve_delivery_request(handler, sid, actor, body)
                if self._speech_binding(identity, subscriber, body['policyRevision']) is None:
                    raise Phase10Error('unavailable', 'Speech delivery context unavailable.', 409)
                return identity, subscriber
            language, source_id = body['language'], body['source']
            try:
                settings = (self._hosted_settings(language) if body['choice'] == 'hosted'
                            else self._settings(language))
            except (ValueError, KeyError, TypeError):
                raise Phase10Error('unavailable', 'Voice unavailable.', 409) from None
            if language not in waves17_tts_local.VOICES or body['voice'] != settings['voice']:
                raise Phase10Error('unavailable', 'Voice unavailable.', 409)
            edition = source_id.startswith('edition:')
            public = source_id.startswith('record:') or edition
            if edition:
                provisional = Subscriber(actor['owner'], source_id, body['sourceRevision'], store.digest(handler._auth_token))
                description = self._edition_description(sid, source_id[8:], language, provisional)
                if not description or description['selectionRevision'] != body['sourceRevision']:
                    raise Phase10Error('unavailable', 'Description unavailable.', 409)
                text = description['text']
            elif public:
                record = waves18_records.fetch(sid, source_id[7:])
                projection = waves18_records.projection(sid, record, language)
                text = projection['interpretation']
            else:
                moment = store.get('p10moment', source_id, sid)
                text = moment.get('text') if moment else None
            if not isinstance(text, str):
                raise Phase10Error('unavailable', 'Delivery source unavailable.', 409)
            subscriber = Subscriber(actor['owner'], source_id, body['sourceRevision'],
                                    store.digest(handler._auth_token))
            identity = Identity(session=sid, rights_partition='approved-record' if public else 'private:' + actor['owner'],
                source=source_id, source_revision=str(body['sourceRevision']),
                translation_revision='policy:' + str(body['policyRevision']), terminology_revision=('edition:' + settings_digest(description) if edition else 'none'),
                text_digest=hashlib.sha256(text.encode('utf-8')).hexdigest(), language=language,
                engine=settings['engine'], model=settings['model'], voice=settings['voice'],
                settings_digest=settings_digest(settings), output_format=settings['outputFormat'],
                private_actor='' if public else actor['owner'])
            if self._plan(identity, subscriber) is None:
                raise Phase10Error('unavailable', 'Delivery context unavailable.', 409)
            return identity, subscriber

    def eligible(self, identity, subscriber, phase):
        if not identity.translation_revision.startswith('policy:'):
            return self._speech_binding(identity, subscriber) is not None
        return self._plan(identity, subscriber) is not None

    def resolve_plan(self, identity, phase):
        if self.scheduler is None:
            return None
        # An approved record is shared creator-reviewed work.  Its generation
        # authority is the current record and its sources, not the credential
        # of whichever viewer happened to request it first.  Each subscriber
        # is still independently checked by eligible() and the final guard.
        if identity.translation_revision.startswith('policy:') and not identity.private_actor and not identity.source.startswith('edition:'):
            # Never acquire the scheduler lock while holding the store lock.
            # The snapshot does not itself grant rights: every subscriber and
            # the record are revalidated under the store lock below.
            subscribers = self.scheduler.active_subscribers(identity)
            with store.LOCK:
                if not any(self._plan(identity, subscriber) is not None for subscriber in subscribers):
                    return None
                return self._plan(identity, None)
        # Snapshot under the scheduler lock, then release it before store reads.
        for subscriber in self.scheduler.active_subscribers(identity):
            plan = (self._speech_binding(identity, subscriber) if not identity.translation_revision.startswith('policy:')
                    else self._plan(identity, subscriber))
            if plan is not None:
                return plan
        return None


class ProviderObservation:
    """Refresh provider facts outside the store lock without running inference."""
    def __init__(self, binding):
        self.binding = binding
        self.stop_event = threading.Event()
        self.publish_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name='w20-provider-status', daemon=True)

    @staticmethod
    def _peer_status(local):
        """Consume an operator-pinned loopback runtime's actual provider status.

        The operator must configure an exact port, boot ID and matching protected
        profile digest. An unverified, replaced or unreachable peer grants no
        availability. No credential or provider request crosses this boundary.
        """
        import os, re, urllib.request
        from pathlib import Path
        port=os.environ.get('APP_W20_OBSERVATION_PEER_PORT','')
        boot=os.environ.get('APP_W20_OBSERVATION_PEER_BOOT','')
        profile=os.environ.get('APP_W20_OBSERVATION_PEER_PROFILE_SHA256','')
        if (not re.fullmatch(r'[1-9][0-9]{0,4}',port) or int(port)>65535 or
            not re.fullmatch(r'[0-9a-f]{32}',boot) or
            not re.fullmatch(r'[0-9a-f]{64}',profile) or
            profile != os.environ.get('APP_CLAUDE_PROFILE_SHA256') or
            local.get('name')!='claude' or local.get('configured') is not True):
            return None
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,req,fp,code,msg,headers,newurl): return None
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open('http://127.0.0.1:'+port+'/api/health',timeout=2) as response:
            raw=response.read(131073)
        if len(raw)>131072: return None
        data=json.loads(raw); runtime=data.get('runtime',{})
        expected=hashlib.sha256(Path(__file__).with_name('claude_provider.py').read_bytes()).hexdigest()
        if runtime.get('bootId')!=boot or runtime.get('bootSourceSha256',{}).get('claude_provider.py')!=expected:
            return None
        matches=[item for item in data.get('providers',[]) if item.get('name')=='claude']
        if (len(matches)!=1 or matches[0].get('model')!=local.get('model') or
            matches[0].get('configured') is not True or matches[0].get('tested') is not True or
            matches[0].get('available') is not True): return None
        return {key:matches[0].get(key) for key in ('name','model','configured','available')}

    def _run(self):
        from . import provider
        while not self.stop_event.is_set():
            try:
                status = provider.status()
                facts = {key: status.get(key) for key in ('name', 'model', 'configured', 'available')}
                # Unknown availability is not positive evidence of availability.
                if facts['available'] is not True:
                    facts = self._peer_status(status) or facts
                facts['available'] = facts['available'] is True
                with self.publish_lock:
                    if not self.stop_event.is_set():
                        self.binding.publish_observation(facts)
            except Exception:
                self.binding.publish_observation(None)
            self.stop_event.wait(10)
        with self.publish_lock:
            self.binding.publish_observation(None)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(6)
        with self.publish_lock:
            self.binding.publish_observation(None)


def configure_local_delivery():
    """Construct the real bridge and bounded dispatcher; caller controls startup."""
    from . import waves20_scheduler, source_translation_delivery
    from .waves20_job_bridge import JobBridge
    from .waves20_worker_pool import WorkerPool
    if waves20_scheduler._service is not None:
        raise RuntimeError('delivery already configured')
    # Translation observations start absent. Only the runtime operator may
    # publish a fresh verified provider observation; until then cross-language
    # admission fails closed while same-language source reading remains usable.
    resolver = source_translation_delivery.SourceTranslationBinding()
    bridge = JobBridge(resolver.resolve_plan, resolver.resolve_translation_binding)
    service = waves20_scheduler.configure(
        authorize=resolver.authorize, resolve=resolver.resolve_request,
        prepare=resolver.prepare_request,
        eligible=resolver.eligible, generate=bridge.generate,
        limits={'total': 128, 'per_session': 48, 'per_viewer': 12,
                'concurrency': 2, 'max_age': 120, 'timeout': 120},
        max_result_bytes=10 * 1024 * 1024)
    resolver.scheduler = service.scheduler
    service.translation_binding = resolver
    service.provider_observation = ProviderObservation(resolver)
    return service, WorkerPool(service.scheduler, workers=2)


def delivery_sources(handler, sid, actor):
    """Project currently admissible source identities; caller holds store.LOCK through send."""
    runtime = LocalSourceReading()
    from . import waves20_scheduler
    binding = getattr(waves20_scheduler._service, 'translation_binding', None)
    if not runtime.authorize(handler, sid, actor):
        raise Phase10Error('forbidden', 'Delivery access required.', 403)
    with store.LOCK, store.connect() as db:
        owner = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (sid, sid)).fetchone()
        _, policy = waves20_modes._current(db, sid, owner['owner_id']) if owner and owner['owner_id'] else (None, None)
        revision = policy['revision'] if policy else None
    local_available = revision is not None and bool(waves20_policy_access.current_local_policy(sid, revision))
    hosted_available = revision is not None and bool(waves20_policy_access.current_hosted_speech_policy(sid, revision))
    if not local_available and not hosted_available:
        return {'policyRevision': revision, 'sources': []}
    candidates = []
    for moment in store.all('p10moment', sid):
        ref = moment.get('ref') or {}
        source = store.get('source', ref.get('sourceId'), sid)
        if source:
            kind = (source.get('p10Provenance') or {}).get('inputKind')
            if kind not in ('file_replay', 'live_program_audio'):
                kind = 'unknown'
            candidates.append((ref.get('momentId'), ref.get('sourceRevision'), source.get('language'), 'private_asr', kind))
    for record in store.all('w18record', sid):
        for language in ('en', 'es'):
            try:
                projection = waves18_records.projection(sid, record, language)
                if not projection['fallback']:
                    candidates.append(('record:' + record['id'], record['version'], language, 'approved_record', projection['provenance']))
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
            # A selected edition description is a separate, revision-bound
            # source. Resolve it with this subscriber's current credential;
            # neither a record projection nor a creator role grants access.
            try:
                subscriber = Subscriber(actor['owner'], 'edition:' + record['id'], 0,
                                        store.digest(handler._auth_token))
                description = runtime._edition_description(sid, record['id'], language, subscriber)
                if description:
                    candidates.append(('edition:' + record['id'], description['selectionRevision'],
                                       language, 'edition_description', 'creator_selected'))
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
    result = []
    for source_id, source_revision, language, kind, provenance in candidates:
        if not isinstance(source_id, str) or len(source_id) > 128 or type(source_revision) is not int or language not in waves17_tts_local.VOICES:
            continue
        choices = []
        for choice in ('local', 'hosted'):
            if not (local_available if choice == 'local' else hosted_available):
                continue
            try:
                settings = runtime._settings(language) if choice == 'local' else runtime._hosted_settings(language)
                body = {'source': source_id, 'sourceRevision': source_revision, 'policyRevision': revision,
                        'language': language, 'voice': settings['voice'], 'choice': choice}
                runtime.resolve_request(handler, sid, actor, body)
                choices.append({'choice': choice, 'voices': [settings['voice']]})
            except (Phase10Error, ValueError, TypeError, KeyError):
                continue
        if not choices:
            continue
        # Keep the existing local voices field for older clients. Hosted is an
        # explicit selection, never an automatic fallback from a local request.
        local_voices = next((item['voices'] for item in choices if item['choice'] == 'local'), [])
        result.append({'source': source_id, 'sourceRevision': source_revision, 'language': language,
                       'kind': kind, 'provenance': provenance, 'voices': local_voices, 'choices': choices})
        if len(result) >= 100:
            break
        if kind == 'private_asr' and binding is not None and local_available:
            target = 'es' if language == 'en' else 'en'
            translated = {'source': source_id, 'sourceRevision': source_revision, 'policyRevision': revision,
                          'language': target, 'voice': waves17_tts_local.VOICES[target][0], 'choice': 'local'}
            try:
                binding.resolve_request(handler, sid, actor, translated)
            except (Phase10Error, ValueError, TypeError, KeyError):
                continue
            result.append({'source': source_id, 'sourceRevision': source_revision,
                           'language': target, 'kind': 'private_translation',
                           'provenance': provenance, 'voices': [translated['voice']]})
            if len(result) >= 100:
                break
    return {'policyRevision': revision, 'sources': result}
