"""HTTP facade for the bounded delivery core; Primary owns all authority and workers."""
import hashlib
import json
import re
import threading
from contextlib import contextmanager
from dataclasses import asdict, replace
from . import store
from .phase10_common import Phase10Error
from .waves20_delivery import Identity, Subscriber, Scheduler

_ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
_RECEIPT = 'w20deliveryreceipt'
_IDENTITY = 'w20deliveryidentity'
_service = None

def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)

def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()

def _read(db, kind, key, sid):
    row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (kind,key,sid)).fetchone()
    return (json.loads(row['data']), row['owner_id']) if row else (None, None)

def _put(db, kind, key, sid, owner, value):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
               (kind,key,sid,owner,_json(value),store.now()))

def _validate(body):
    fields = {'requestId','source','sourceRevision','language','voice','policyRevision','choice'}
    if not isinstance(body, dict) or not fields <= set(body) or set(body)-fields-{'preparation'}:
        _fail('invalid_request','Invalid delivery fields.',422)
    if 'preparation' in body:
        from .waves25_listening_preparation import validate_choice
        validate_choice(body['preparation'])
    for key in ('requestId','source'):
        if not isinstance(body[key],str) or not _ID.fullmatch(body[key]): _fail('invalid_request','Invalid identifier.',422)
    for key in ('sourceRevision','policyRevision'):
        if type(body[key]) is not int or not 0 <= body[key] <= 9007199254740991: _fail('invalid_request','Invalid revision.',422)
    for key in ('language','voice'):
        if not isinstance(body[key],str) or not body[key].strip() or len(body[key]) > 128 or '\x00' in body[key]: _fail('invalid_request','Invalid selection.',422)
    if body['choice'] not in ('local','hosted'): _fail('invalid_request','Select a voice explicitly.',422)

class Facade:
    def __init__(self, *, authorize, resolve, eligible, generate, limits, max_result_bytes=1048576, max_receipts=10000, prepare=None):
        if not all(callable(x) for x in (authorize,resolve,eligible,generate)) or type(max_result_bytes) is not int or not 1 <= max_result_bytes <= 10485760 or type(max_receipts) is not int or max_receipts < 1:
            raise ValueError('invalid configuration')
        self.authorize, self.resolve, self.eligible = authorize, resolve, eligible
        if prepare is not None and not callable(prepare):
            raise ValueError('invalid preparation hook')
        self.prepare = prepare
        self.max_result_bytes, self.max_receipts = max_result_bytes, max_receipts
        self.live = {}  # durable receipt key -> process-local ticket, identity, subscriber
        self.lock = threading.RLock()
        def bounded_generate(identity):
            outcome, result = generate(identity)
            if outcome == 'ready':
                try:
                    if len(_json(result).encode('utf-8')) > self.max_result_bytes: return 'unavailable', None
                except (ValueError,TypeError,OverflowError): return 'unavailable', None
            return outcome, result
        self.scheduler = Scheduler(eligible=eligible,generate=bounded_generate,**limits)

    def _auth(self, handler, sid, actor):
        if not isinstance(sid,str) or not sid or not isinstance(actor,dict) or actor.get('sid') != sid or actor.get('role') not in ('creator','viewer') or not isinstance(actor.get('owner'),str) or not actor['owner']:
            _fail('forbidden','Delivery access required.',403)
        if self.authorize(handler,sid,actor) is not True: _fail('forbidden','Delivery access required.',403)

    def _resolved(self, handler, sid, actor, body):
        try: identity, subscriber = self.resolve(handler,sid,actor,dict(body))
        except Phase10Error: raise
        except Exception: _fail('unavailable','Delivery context unavailable.',409)
        if not isinstance(identity,Identity) or not isinstance(subscriber,Subscriber) or identity.session != sid or subscriber.actor != actor['owner'] or (identity.private_actor and identity.private_actor != actor['owner']):
            _fail('unavailable','Delivery context unavailable.',409)
        return identity, subscriber

    def _projection(self, key):
        ticket, identity, subscriber = self.live[key]
        result = self.scheduler.view(ticket)
        # A callback can reject after committing its bridge intent. Its durable
        # unknown must not be presented as a safely failed/no-effect request.
        if (result['state'] not in ('ready', 'cancelled') and identity.private_actor
                and identity.translation_revision.startswith('translation:')):
            from .source_translation_delivery import inspect_translation_receipt
            durable = inspect_translation_receipt(identity)
            if durable and durable['state'] in ('w20_unknown', 'w20_running') and result['state'] not in ('queued', 'running', 'generating', 'waiting'):
                result = {'state': 'unknown', 'age': result.get('age', 0),
                          'sequence': subscriber.sequence, 'text_fallback': True}
        with self.scheduler._lock:
            pair = self.scheduler._tickets.get(ticket)
            if pair and pair[0].unknown and result['state'] != 'cancelled':
                result = {'state':'unknown','age':result.get('age',0),'sequence':subscriber.sequence,'text_fallback':True}
        result['ticket'] = key
        result['gap'] = None
        return result

    def admit(self, handler, sid, actor, body):
        _validate(body)
        with store.LOCK, self.lock:
            self._auth(handler,sid,actor)
            if self.prepare is not None:
                self.prepare(handler,sid,actor,dict(body))
            identity, subscriber = self._resolved(handler,sid,actor,body)
            if self.eligible(identity,subscriber,'admission') is not True: _fail('unavailable','Delivery context unavailable.',409)
            key = _hash(['receipt',sid,actor['owner'],body['requestId']])
            fingerprint = _hash(body)
            identkey = _hash(['identity',asdict(identity)])
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                receipt, owner = _read(db,_RECEIPT,key,sid)
                if receipt:
                    if owner != actor['owner'] or receipt['fingerprint'] != fingerprint: _fail('request_conflict','Request ID already used.',409)
                    if receipt['identity'] != identkey: _fail('stale_context','Delivery context changed.',409)
                    db.commit()
                    if key not in self.live: return {'state':'unknown','ticket':key,'gap':None,'text_fallback':True}
                    result = self._projection(key)
                    handler._w20_delivery_binding = (self,sid,dict(actor),key,result)
                    return result
                marker, _ = _read(db,_IDENTITY,identkey,sid)
                live_identity = any(i == identity for _,i,_ in self.live.values())
                if marker and not live_identity:
                    db.commit(); return {'state':'unknown','gap':None,'text_fallback':True}
                count = db.execute('SELECT COUNT(*) FROM objects WHERE kind=?',(_RECEIPT,)).fetchone()[0]
                if count >= self.max_receipts:
                    db.commit(); return {'state':'full','gap':None,'text_fallback':True}
                if not marker: _put(db,_IDENTITY,identkey,sid,None,{'identity':identkey})
                # Persist before admission: a crash is conservatively unknown, never implicit retry.
                _put(db,_RECEIPT,key,sid,actor['owner'],{'fingerprint':fingerprint,'identity':identkey})
                db.commit()
            admitted = self.scheduler.admit(identity,subscriber)
            ticket = admitted.get('ticket')
            if ticket:
                self.live[key] = (ticket,identity,subscriber)
                result = self._projection(key)
                handler._w20_delivery_binding = (self,sid,dict(actor),key,result)
                return result
            # No dispatch occurred. Keep the receipt but release only a newly created marker.
            if not marker:
                with store.connect() as db:
                    db.execute('DELETE FROM objects WHERE kind=? AND id=? AND session_id=?',(_IDENTITY,identkey,sid))
            return dict(admitted, gap=None)

    def lookup(self, handler, sid, actor, body):
        """Recover an existing admission without creating or resuming work."""
        _validate(body)
        with store.LOCK, self.lock:
            self._auth(handler, sid, actor)
            key = _hash(['receipt', sid, actor['owner'], body['requestId']])
            with store.connect() as db:
                receipt, owner = _read(db, _RECEIPT, key, sid)
            if not receipt or owner != actor['owner']:
                _fail('not_found', 'Delivery unavailable.', 404)
            if receipt['fingerprint'] != _hash(body):
                _fail('request_conflict', 'Request ID already used.', 409)
            identity, subscriber = self._resolved(handler, sid, actor, body)
            if self.eligible(identity, subscriber, 'view') is not True:
                _fail('unavailable', 'Delivery context unavailable.', 409)
            if receipt['identity'] != _hash(['identity', asdict(identity)]):
                _fail('stale_context', 'Delivery context changed.', 409)
            if key in self.live:
                return self.view(handler, sid, actor, key)
            result = {'state':'unknown', 'ticket':key, 'gap':None, 'text_fallback':True}
            handler._w20_lookup_binding = (self, sid, dict(actor), identity, subscriber)
            return result

    def view(self, handler, sid, actor, key):
        with store.LOCK, self.lock:
            self._auth(handler,sid,actor)
            with store.connect() as db: receipt,owner = _read(db,_RECEIPT,key,sid)
            if not receipt or owner != actor['owner']: _fail('not_found','Delivery unavailable.',404)
            if key not in self.live: return {'state':'unknown','ticket':key,'gap':None,'text_fallback':True}
            _,identity,subscriber = self.live[key]
            if self.eligible(identity,subscriber,'view') is not True: _fail('unavailable','Delivery context unavailable.',409)
            result = self._projection(key)
            handler._w20_delivery_binding = (self,sid,dict(actor),key,result)
            return result

    def cancel(self, handler, sid, actor, key):
        with store.LOCK, self.lock:
            self._auth(handler,sid,actor)
            with store.connect() as db: receipt,owner = _read(db,_RECEIPT,key,sid)
            if not receipt or owner != actor['owner']: _fail('not_found','Delivery unavailable.',404)
            if key not in self.live: return {'state':'unknown','ticket':key,'gap':None,'text_fallback':True}
            self.scheduler.cancel(self.live[key][0])
            return self._projection(key)

    @contextmanager
    def terminology_registry_boundary(self, sid, actor, authority):
        """Hold current store and scheduler state through a metadata final send.

        The caller must validate all source and grant rights before sending.
        This boundary performs no generation, admission, or provider operation.
        """
        with store.LOCK, self.lock, self.scheduler._lock:
            yield self.scheduler.registered_terminology_work(sid, actor, authority)

    @contextmanager
    def terminology_observation_boundary(self):
        """Freeze the real local observation while a projection is sent."""
        from .source_translation_delivery import SourceTranslationBinding
        binding = getattr(self, 'translation_binding', None)
        if not isinstance(binding, SourceTranslationBinding):
            yield lambda: None
            return
        with binding._facts_lock:
            def current():
                age = None if binding._observed_at is None else binding._clock() - binding._observed_at
                if binding._facts is None or age is None or not 0 <= age <= binding._max_age:
                    return None
                return dict(binding._facts)
            yield current

    def terminology_projection(self, handler, sid, actor, registered, approved_revision, *, facts_override=None):
        """Project only this creator capability's currently authorized registrations.

        The caller holds terminology_registry_boundary through final response.
        Unknown provider facts or current authority suppress affected rows.
        """
        from . import source_translation_delivery as translation
        from . import waves17_terminology as terms
        from .waves20_job_bridge import settings_digest
        from .phase10_common import Context
        self._auth(handler, sid, actor)
        binding = getattr(self, 'translation_binding', None)
        if not isinstance(binding, translation.SourceTranslationBinding):
            return []
        facts = facts_override if facts_override is not None else binding._observation()
        if facts is None:
            return []
        ctx = Context(handler, sid, actor)
        result = []
        with store.connect() as db:
            receipts = db.execute(
                'SELECT data FROM objects WHERE kind=? AND session_id=? AND owner_id=?',
                (terms.RECEIPT, sid, actor['owner'])).fetchall()
        current_record = terms.load(sid)
        current_approved = current_record.get('approved') if current_record else None
        saved_approvals = [current_approved]
        for receipt in receipts:
            try:
                saved_approvals.append(json.loads(receipt['data'])['response']['terminology']['approved'])
            except (ValueError, TypeError, KeyError):
                continue
        for identity, subscriber, state in registered:
            try:
                term = identity.terminology_revision.split(':')
                policy = identity.translation_revision.split(':')
                if (len(term) != 2 or term[0] != 'terms' or not term[1].isdigit()
                        or str(int(term[1])) != term[1] or int(term[1]) < 1
                        or len(policy) != 3 or policy[0] != 'translation'
                        or not policy[1].isdigit() or str(int(policy[1])) != policy[1]
                        or int(policy[1]) < 1 or subscriber.authority != store.digest(handler._auth_token)):
                    continue
                fresh, current_subscriber, plan = translation.private_translation(
                    ctx, identity.source, subscriber.sequence, identity.language,
                    int(policy[1]), facts, None)
                # Resolve the original approved document from its existing
                # immutable terminology receipt, then recheck every old grant.
                # Older registrations without a matching receipt stay hidden.
                candidates = []
                for saved in saved_approvals:
                    try:
                        if not saved or saved['revision'] != int(term[1]):
                            continue
                        document = terms.validate(saved['document'])
                        snapshot = {'revision': int(term[1]), 'document': document}
                        settings = dict(plan['settings'], terminology=snapshot)
                        bound = replace(fresh, terminology_revision=identity.terminology_revision,
                                        settings_digest=settings_digest(settings))
                        if bound == identity:
                            terms.check_refs(sid, actor, subscriber.authority, document)
                            candidates.append(snapshot)
                    except (Phase10Error, ValueError, TypeError, KeyError, UnicodeError):
                        continue
                if not candidates or any(candidate != candidates[0] for candidate in candidates):
                    continue
                # The current source, target, policy and actor must also match.
                old_fields, new_fields = asdict(identity), asdict(fresh)
                for field in ('terminology_revision', 'settings_digest'):
                    old_fields.pop(field); new_fields.pop(field)
                if old_fields != new_fields or subscriber != current_subscriber:
                    continue
                revision = int(term[1])
                relation = ('current' if current_approved and current_approved['revision'] == revision
                            and current_approved['document'] == candidates[0]['document'] else 'stale')
                if relation == 'current' and translation.private_translation_plan(identity, subscriber, facts) is None:
                    continue
                result.append({'kind': 'wave20_private_delivery',
                    'reference': _hash(['identity', asdict(identity)]),
                    'source': identity.source, 'sourceRevision': subscriber.sequence,
                    'sourceLanguage': plan['sourceLanguage'], 'targetLanguage': identity.language, 'state': state,
                    'terminologyRevision': revision,
                    'bindingDigest': identity.settings_digest, 'relation': relation})
            except (Phase10Error, ValueError, TypeError, KeyError, UnicodeError):
                continue
        return sorted(result, key=lambda row: (row['reference'], row['state']))

    def invalidate_source(self, sid, source, revision):
        with store.LOCK, self.lock: self.scheduler.invalidate_source(sid,source,revision)

    def forget(self, key):
        """Forget only settled in-memory tickets; durable receipts/identity remain."""
        with store.LOCK, self.lock:
            item = self.live.get(key)
            if not item or not self.scheduler.forget(item[0]): return False
            del self.live[key]
            return True

    def reconcile_identity(self, identity, *, settled):
        """Primary invokes only after its durable authority establishes final settlement."""
        if settled is not True or not isinstance(identity,Identity): return False
        with store.LOCK, self.lock:
            if any(i == identity for _,i,_ in self.live.values()): return False
            with store.connect() as db:
                return bool(db.execute('DELETE FROM objects WHERE kind=? AND id=? AND session_id=?',(_IDENTITY,_hash(['identity',asdict(identity)]),identity.session)).rowcount)

def configure(**kwargs):
    global _service
    _service = Facade(**kwargs)
    return _service

def handle(handler, sid, actor, method, parts):
    if _service is None: _fail('unavailable','Delivery unavailable.',503)
    if method == 'POST' and parts == ['delivery', 'receipt']:
        return 200, _service.lookup(handler, sid, actor, handler.body())
    if method == 'POST' and parts == ['delivery']:
        result = _service.admit(handler,sid,actor,handler.body())
        # Admission may immediately return a cached result; protect it too.
        if result.get('ticket') in _service.live:
            result = _service.view(handler,sid,actor,result['ticket'])
        return 200,result
    if len(parts) == 2 and parts[0] == 'delivery' and re.fullmatch(r'[0-9a-f]{64}',parts[1]):
        if method == 'GET': return 200,_service.view(handler,sid,actor,parts[1])
        if method == 'DELETE': return 200,_service.cancel(handler,sid,actor,parts[1])
    _fail('not_found','Delivery route unavailable.',404)

def guard_delivery(handler):
    """Primary must hold store.LOCK from this check through response serialization."""
    lookup = getattr(handler, '_w20_lookup_binding', None)
    if lookup:
        service, sid, actor, identity, subscriber = lookup
        with service.lock:
            service._auth(handler, sid, actor)
            if service.eligible(identity, subscriber, 'final') is not True:
                _fail('stale_context', 'Delivery changed; refresh.', 409)
    binding = getattr(handler,'_w20_delivery_binding',None)
    if not binding: return
    service,sid,actor,key,before = binding
    with service.lock:
        service._auth(handler,sid,actor)
        item = service.live.get(key)
        current = service._projection(key) if item else None
        # Queue age advances naturally; protected state and result must still match.
        comparable = lambda value: {k:v for k,v in value.items() if k != 'age'}
        if not item or service.eligible(item[1],item[2],'final') is not True or comparable(current) != comparable(before):
            _fail('stale_context','Delivery changed; refresh.',409)

