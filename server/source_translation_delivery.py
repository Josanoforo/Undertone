"""Authoritative private indexed-ASR reconstruction for translation delivery.

This is a component, not an admission, generation or public-delivery interface.
Callers retain store.LOCK through decisions based on the returned content.
"""
import hashlib
import json
import math
import threading
import time
from dataclasses import asdict
from . import phase12_jobs, store, waves17_terminology
from .phase10_common import Context, Phase10Error
from .waves20_delivery import Identity, Subscriber
from .waves20_job_bridge import canonical, settings_digest, validate_plan
from . import waves20_policy_access, waves20_runtime


def inspect_translation_receipt(identity):
    """Inspect the existing bridge receipt for an exact private identity.

    Operator-only diagnostic; it does not authorize output, reconcile a provider
    effect, or permit a retry. Never expose this result to an unauthenticated
    client. No source text, output or credential is returned.
    """
    if (not isinstance(identity, Identity) or not identity.private_actor or
            identity.rights_partition != 'private:' + identity.private_actor or
            not identity.translation_revision.startswith('translation:')):
        raise ValueError('private translation identity required')
    operation_id = hashlib.sha256(canonical(asdict(identity)).encode('utf-8')).hexdigest()
    with store.LOCK, store.connect() as db:
        row = db.execute(
            "SELECT kind,state,transport FROM phase12_jobs WHERE session_id=? AND actor_id=? AND request_id=?",
            (identity.session, '\x00wave20-internal', operation_id)).fetchone()
    if row is None:
        return None
    if row['kind'] != 'w20_speech':
        raise ValueError('unexpected bridge receipt')
    return {'operationId': operation_id, 'state': row['state'], 'transport': row['transport']}


def private_source(ctx, moment_id, source_revision, target_language, terminology_revision=None):
    """Rebuild a source using the requesting actor's current credential and rights.

    The language is the requested delivery target, never a claim about the source.
    Terminology is explicitly opted in and checked with the same actor's rights.
    Returned text is private and must not be treated as public approval.
    """
    if (not isinstance(ctx, Context) or not isinstance(moment_id, str) or
        type(source_revision) is not int or source_revision < 1 or
        target_language not in ('en', 'es') or
        (terminology_revision is not None and
         (type(terminology_revision) is not int or terminology_revision < 1))):
        raise Phase10Error('invalid_request', 'Invalid source selection.', 422)
    with store.LOCK:
        ctx.check_actor()
        digest = ctx._credential_digest
        if digest is None:
            digest = store.digest(getattr(ctx.handler, '_auth_token', ''))
        moment = store.get('p10moment', moment_id, ctx.sid)
        ref = moment.get('ref') if moment else None
        if (not isinstance(ref, dict) or ref.get('sessionId') != ctx.sid or
            ref.get('momentId') != moment_id or ref.get('sourceRevision') != source_revision):
            raise Phase10Error('stale_context', 'Source unavailable.', 409)
        row = {'session_id': ctx.sid, 'actor_id': ctx.actor['owner'],
               'role': ctx.actor['role'], 'credential_hash': digest,
               'ref': json.dumps(ref)}
        source, moment, ref = phase12_jobs.rights(row)
        language, text = source.get('language'), moment.get('text')
        if (language not in ('en', 'es') or not isinstance(text, str) or
            not 1 <= len(text.strip()) <= 600 or len(text) > 600):
            raise Phase10Error('stale_context', 'Source unavailable.', 409)
        terms = None if terminology_revision is None else waves17_terminology.snapshot(
            ctx.sid, ctx.actor, digest, terminology_revision)
        return {'source': moment_id, 'sourceRevision': source_revision,
                'sourceLanguage': language, 'targetLanguage': target_language,
                'text': text, 'textDigest': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                'ref': ref, 'scope': 'private', 'privateActor': ctx.actor['owner'],
                'terminology': terms}


def private_translation(ctx, moment_id, source_revision, target_language,
                        policy_revision, provider_status, terminology_revision=None, preparation_id=None):
    """Build a private cross-language identity and plan from current store data.

    Provider facts must be observed by the trusted operator outside store.LOCK;
    they are not client input and do not constitute monetary admission. This
    constructor performs no effect and is not a complete scheduler resolver.
    The caller holds store.LOCK through its authority decision.
    """
    with store.LOCK:
        prepared = None
        if preparation_id is not None:
            from . import waves25_listening_preparation as preparation
            prepared = preparation.resolve(ctx, preparation_id, moment_id, source_revision, target_language)
            chosen_revision = prepared[0]['choice']['terminologyRevision']
            if terminology_revision is not None and terminology_revision != chosen_revision:
                raise Phase10Error('stale_preparation', 'Preparation revisions do not match.', 409)
            terminology_revision = chosen_revision
        source = private_source(ctx, moment_id, source_revision, target_language,
                                terminology_revision)
        current = waves20_policy_access.current_translation_policy(
            ctx.sid, policy_revision, provider_status)
        if current is None or source['sourceLanguage'] == target_language:
            raise Phase10Error('unavailable', 'Translation unavailable.', 409)
        _, binding = current
        settings = waves20_runtime.LocalSourceReading._settings(target_language)
        settings['terminology'] = source['terminology']
        if prepared is not None:
            settings = preparation.settings(*prepared)
        term_revision = ('none' if terminology_revision is None else
                         'terms:' + str(terminology_revision))
        translation_revision = 'translation:' + str(policy_revision) + ':' + settings_digest({
            'policyRevision': policy_revision, 'binding': binding})
        if preparation_id is not None:
            translation_revision += ':' + preparation_id
        identity = Identity(session=ctx.sid, rights_partition='private:' + ctx.actor['owner'],
            source=moment_id, source_revision=str(source_revision),
            translation_revision=translation_revision, terminology_revision=term_revision,
            text_digest=source['textDigest'], language=target_language,
            engine=settings['engine'], model=settings['model'], voice=settings['voice'],
            settings_digest=settings_digest(settings), output_format=settings['outputFormat'],
            private_actor=ctx.actor['owner'])
        digest = ctx._credential_digest
        if digest is None:
            digest = store.digest(getattr(ctx.handler, '_auth_token', ''))
        subscriber = Subscriber(ctx.actor['owner'], moment_id, source_revision, digest)
        plan = {'session': ctx.sid, 'rightsPartition': identity.rights_partition,
                'source': moment_id, 'sourceRevision': identity.source_revision,
                'translationRevision': translation_revision,
                'terminologyRevision': term_revision, 'scope': 'private',
                'privateActor': identity.private_actor, 'text': source['text'],
                'sourceLanguage': source['sourceLanguage'], 'settings': settings}
        return identity, subscriber, validate_plan(identity, plan)


def private_translation_plan(identity, subscriber, provider_status):
    """Reconstruct one subscriber's exact plan, or fail closed.

    This helper does not enumerate active subscribers or obtain provider facts;
    the integration must do both without holding a scheduler lock over store
    reads or doing network work while holding store.LOCK.
    """
    try:
        if not isinstance(identity, Identity) or not isinstance(subscriber, Subscriber):
            return None
        parts = identity.translation_revision.split(':')
        if len(parts) not in (3, 4) or parts[0] != 'translation' or not parts[1].isdigit():
            return None
        revision = int(parts[1])
        if revision < 1 or str(revision) != parts[1]:
            return None
        term = identity.terminology_revision
        if term == 'none':
            term_revision = None
        elif term.startswith('terms:') and term[6:].isdigit() and str(int(term[6:])) == term[6:] and int(term[6:]) > 0:
            term_revision = int(term[6:])
        else:
            return None
        with store.LOCK, store.connect() as db:
            credential = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?',
                                    (subscriber.authority,)).fetchone()
            if (not credential or credential['session_id'] != identity.session or
                    credential['owner_id'] != subscriber.actor or
                    subscriber.actor != identity.private_actor or
                    subscriber.stream != identity.source or
                    str(subscriber.sequence) != identity.source_revision):
                return None
            actor = {'sid': identity.session, 'owner': credential['owner_id'],
                     'role': credential['role']}
            ctx = Context(None, identity.session, actor, credential_digest=subscriber.authority)
            fresh, _, plan = private_translation(ctx, identity.source, subscriber.sequence,
                identity.language, revision, provider_status, term_revision, parts[3] if len(parts) == 4 else None)
            return plan if fresh == identity else None
    except (Phase10Error, ValueError, TypeError, KeyError, UnicodeError):
        return None


class SourceTranslationBinding:
    """Compose private cross-language delivery with the existing reading resolver.

    PRIMARY owns observation, effect admission and the scheduler. Observations are
    published as short-lived local snapshots, never fetched by a store callback.
    The JobBridge must receive resolve_translation_binding as its second
    argument to enforce current policy at the translation effect boundary.
    """
    def __init__(self, *, max_observation_age=30, clock=time.monotonic):
        if (isinstance(max_observation_age, bool) or
                not isinstance(max_observation_age, (int, float)) or
                not math.isfinite(max_observation_age) or
                not 0 < max_observation_age <= 30):
            raise ValueError('invalid observation age')
        self.reading = waves20_runtime.LocalSourceReading()
        self._clock = clock
        self._max_age = max_observation_age
        self._facts_lock = threading.Lock()
        self._facts = None
        self._observed_at = None

    @property
    def scheduler(self):
        return self.reading.scheduler

    @scheduler.setter
    def scheduler(self, value):
        self.reading.scheduler = value

    def publish_observation(self, facts):
        """Publish PRIMARY's fresh trusted observation; None revokes it.

        Observe outside store.LOCK. Never pass client input or cached configured
        state as availability. No provider operation happens in this method.
        """
        if facts is not None:
            if (not isinstance(facts, dict) or set(facts) != {'name', 'model', 'configured', 'available'} or
                    facts['name'] not in ('ollama', 'claude') or
                    not isinstance(facts['model'], str) or not 1 <= len(facts['model']) <= 128 or
                    type(facts['configured']) is not bool or type(facts['available']) is not bool):
                raise ValueError('invalid provider observation')
            facts = dict(facts)
        with self._facts_lock:
            self._facts = facts
            self._observed_at = self._clock() if facts is not None else None

    def _observation(self):
        with self._facts_lock:
            age = None if self._observed_at is None else self._clock() - self._observed_at
            if self._facts is None or age is None or not 0 <= age <= self._max_age:
                return None
            return dict(self._facts)

    def authorize(self, handler, sid, actor):
        return self.reading.authorize(handler, sid, actor)

    def prepare_request(self, handler, sid, actor, body):
        if 'preparation' not in body:
            return
        if not self.authorize(handler, sid, actor):
            raise Phase10Error('forbidden', 'Delivery access required.', 403)
        from . import waves25_listening_preparation as preparation
        preparation.prepare(Context(handler, sid, actor), body['preparation'], body)

    def resolve_request(self, handler, sid, actor, body):
        """Use existing request fields; browser text and provider facts are absent."""
        with store.LOCK:
            if not self.authorize(handler, sid, actor):
                raise Phase10Error('forbidden', 'Delivery access required.', 403)
            source_id = body['source']
            if source_id.startswith(('record:', 'edition:', 'speech:')):
                return self.reading.resolve_request(handler, sid, actor, body)
            ctx = Context(handler, sid, actor)
            preparation_id = None
            if 'preparation' in body:
                from . import waves25_listening_preparation as preparation
                preparation_id = preparation.lookup(ctx, body['preparation'])
            source = private_source(ctx, source_id, body['sourceRevision'], body['language'])
            if source['sourceLanguage'] == body['language']:
                if preparation_id is not None:
                    raise Phase10Error('invalid_request', 'This preparation path requires an explicit translated-language choice.', 422)
                return self.reading.resolve_request(handler, sid, actor, body)
            facts = self._observation()
            if (facts is None or body['choice'] != 'local' or
                    body['language'] not in waves20_runtime.waves17_tts_local.VOICES or
                    body['voice'] != waves20_runtime.waves17_tts_local.VOICES[body['language']][0]):
                raise Phase10Error('unavailable', 'Translation unavailable.', 409)
            identity, subscriber, _ = private_translation(ctx, source_id, body['sourceRevision'],
                body['language'], body['policyRevision'], facts, preparation_id=preparation_id)
            return identity, subscriber

    def eligible(self, identity, subscriber, phase):
        if not identity.translation_revision.startswith('translation:'):
            return self.reading.eligible(identity, subscriber, phase)
        facts = self._observation()
        return facts is not None and private_translation_plan(identity, subscriber, facts) is not None

    def resolve_plan(self, identity, phase):
        if not identity.translation_revision.startswith('translation:'):
            return self.reading.resolve_plan(identity, phase)
        if self.scheduler is None:
            return None
        # Release scheduler lock before resolving store-backed authority.
        subscribers = self.scheduler.active_subscribers(identity)
        facts = self._observation()
        if facts is None:
            return None
        for subscriber in subscribers:
            plan = private_translation_plan(identity, subscriber, facts)
            if plan is not None:
                return plan
        return None

    def resolve_translation_binding(self, identity, phase):
        """Return the exact current policy binding for an active private job.

        This is a read-only input to PRIMARY's effect-boundary admission, not
        admission itself. Recheck at the effect boundary and enforce the
        returned provider, model and session cap in the existing accounting
        path. Never perform an effect while holding store.LOCK.
        """
        if (not isinstance(identity, Identity) or self.scheduler is None or
                not identity.translation_revision.startswith('translation:')):
            return None
        subscribers = self.scheduler.active_subscribers(identity)
        facts = self._observation()
        if facts is None:
            return None
        try:
            revision = int(identity.translation_revision.split(':')[1])
            with store.LOCK:
                for subscriber in subscribers:
                    if private_translation_plan(identity, subscriber, facts) is None:
                        continue
                    current = waves20_policy_access.current_translation_policy(
                        identity.session, revision, facts)
                    if current is not None:
                        return dict(current[1])
        except (ValueError, TypeError, IndexError, Phase10Error):
            return None
        return None

