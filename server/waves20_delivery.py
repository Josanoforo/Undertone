"""Bounded, in-process delivery coordination; no provider or persistence authority."""
from dataclasses import dataclass, field
from collections import defaultdict
from threading import RLock
from typing import Callable, Any
import hashlib
import json
import math
import time
import uuid


@dataclass(frozen=True)
class Identity:
    session: str
    rights_partition: str
    source: str
    source_revision: str
    translation_revision: str
    terminology_revision: str
    text_digest: str
    language: str
    engine: str
    model: str
    voice: str
    settings_digest: str
    output_format: str
    private_actor: str = ''

    def __post_init__(self):
        for name, value in self.__dict__.items():
            if not isinstance(value, str) or len(value) > 512 or (name != 'private_actor' and not value):
                raise ValueError('invalid identity field: ' + name)
        for name in ('text_digest', 'settings_digest'):
            value = getattr(self, name)
            if len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('identity digests must be lowercase SHA-256')


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class Subscriber:
    actor: str
    stream: str
    sequence: int
    # Opaque, bounded capability reference, never a bearer or raw private text.
    authority: str

    def __post_init__(self):
        if any(not isinstance(v, str) or not v or len(v) > 512 for v in (self.actor, self.stream, self.authority)):
            raise ValueError('invalid subscriber')
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError('invalid sequence')


@dataclass
class _Subscription:
    subscriber: Subscriber
    state: str = 'queued'


@dataclass
class _Work:
    identity: Identity
    created: float
    ordinal: int
    subscribers: dict = field(default_factory=dict)
    state: str = 'queued'
    started: float = 0
    result: Any = None
    invalid: bool = False
    # An ambiguous dispatched operation remains blocked until external reconciliation.
    unknown: bool = False


class Scheduler:
    """Call dispatch_one concurrently from a bounded primary-owned worker pool.

    eligible(identity, subscriber, phase) must fail closed and consult current rights.
    generate(identity) invokes primary's durable, at-most-once authority and returns
    ('ready', value), ('unavailable', None), or ('unknown', None). Exceptions are unknown.
    """
    def __init__(self, *, total: int, per_session: int, per_viewer: int,
                 concurrency: int, max_age: float, timeout: float,
                 eligible: Callable, generate: Callable, clock: Callable = time.monotonic):
        values = (total, per_session, per_viewer, concurrency)
        if any(type(v) is not int or v < 1 for v in values) or concurrency > total:
            raise ValueError('invalid limits')
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in (max_age, timeout)):
            raise ValueError('invalid time limits')
        self.total, self.per_session, self.per_viewer, self.concurrency = values
        self.max_age, self.timeout = max_age, timeout
        self.eligible, self.generate, self.clock = eligible, generate, clock
        self._lock = RLock()
        self._works = {}
        self._tickets = {}
        self._ordinal = 0
        self._turn = 0
        self._sessions = defaultdict(int)
        self._viewers = defaultdict(int)
        self._running = 0

    def _allowed(self, identity, subscriber, phase):
        try:
            return self.eligible(identity, subscriber, phase) is True
        except Exception:
            return False

    def _expire(self, now):
        for work in self._works.values():
            if work.state == 'queued' and now - work.created >= self.max_age:
                work.state = 'stale'
                for sub in work.subscribers.values():
                    if sub.state == 'queued': sub.state = 'stale'
            elif work.state == 'running' and now - work.started >= self.timeout:
                work.state, work.unknown = 'unknown', True
                for sub in work.subscribers.values():
                    if sub.state == 'running': sub.state = 'unavailable'

    def admit(self, identity: Identity, subscriber: Subscriber):
        if not isinstance(identity, Identity) or not isinstance(subscriber, Subscriber):
            raise ValueError('typed identity and subscriber required')
        if identity.private_actor and identity.private_actor != subscriber.actor:
            return {'state': 'unavailable', 'text_fallback': True}
        if not self._allowed(identity, subscriber, 'admission'):
            return {'state': 'unavailable', 'text_fallback': True}
        # Late subscribers must also pass the dispatch guard before joining in-flight work.
        dispatch_allowed = self._allowed(identity, subscriber, 'dispatch')
        with self._lock:
            now = self.clock()
            self._expire(now)
            # Limits count retained tickets, including terminal tickets, until forgotten.
            session_count = sum(1 for w, s in self._tickets.values() if w.identity.session == identity.session)
            viewer_count = sum(1 for w, s in self._tickets.values() if w.identity.session == identity.session and s.subscriber.actor == subscriber.actor)
            if len(self._tickets) >= self.total or session_count >= self.per_session or viewer_count >= self.per_viewer:
                return {'state': 'full', 'text_fallback': True}
            work = self._works.get(identity)
            if work and work.state in ('unknown', 'stale', 'unavailable'):
                return {'state': work.state, 'text_fallback': True}
            if work and work.state in ('checking', 'running') and not dispatch_allowed:
                return {'state': 'unavailable', 'text_fallback': True}
            # Never enqueue an older stream update behind a newer retained update.
            if any(old.identity.session == identity.session and sub.subscriber.actor == subscriber.actor
                   and sub.subscriber.stream == subscriber.stream and sub.subscriber.sequence > subscriber.sequence
                   and sub.state in ('queued', 'running', 'ready') for old, sub in self._tickets.values()):
                return {'state': 'stale', 'text_fallback': True}
            # Only queued older stream entries are coalesced; checkpoints are external.
            for old, sub in self._tickets.values():
                if (old.identity.session == identity.session and sub.subscriber.actor == subscriber.actor
                    and sub.subscriber.stream == subscriber.stream and sub.state == 'queued'
                    and sub.subscriber.sequence < subscriber.sequence):
                    sub.state = 'stale'
            if work is None:
                self._ordinal += 1
                work = _Work(identity, now, self._ordinal)
                self._works[identity] = work
            ticket = uuid.uuid4().hex
            # A subscriber joining while dispatch checks the initial snapshot
            # already passed its own dispatch check above. Keep it queued so the
            # dispatcher transitions it together with the existing subscribers.
            state = 'queued' if work.state == 'checking' else work.state
            sub = _Subscription(subscriber, state)
            work.subscribers[ticket] = sub
            self._tickets[ticket] = (work, sub)
            return {'state': state, 'ticket': ticket, 'text_fallback': False}

    def dispatch_one(self):
        with self._lock:
            self._expire(self.clock())
            if self._running >= self.concurrency: return False
            candidates = []
            for work in self._works.values():
                active = [s for s in work.subscribers.values() if s.state == 'queued']
                if work.state == 'queued' and active:
                    viewer = min(active, key=lambda s: (self._viewers[(work.identity.session, s.subscriber.actor)], s.subscriber.actor)).subscriber.actor
                    candidates.append((self._sessions[work.identity.session], self._viewers[(work.identity.session, viewer)], work.ordinal, viewer, work))
            if not candidates: return False
            _, _, _, viewer, work = min(candidates, key=lambda x: x[:3])
            self._turn += 1
            self._sessions[work.identity.session] = self._turn
            self._viewers[(work.identity.session, viewer)] = self._turn
            work.state, work.started = 'checking', self.clock()
            snapshot = list(work.subscribers.items())
            self._running += 1
        checks = {ticket: self._allowed(work.identity, sub.subscriber, 'dispatch') for ticket, sub in snapshot if sub.state == 'queued'}
        with self._lock:
            for ticket, allowed in checks.items():
                sub = work.subscribers.get(ticket)
                if sub and sub.state == 'queued' and not allowed: sub.state = 'unavailable'
            expired = self.clock() - work.created >= self.max_age
            if work.invalid or expired or not any(s.state == 'queued' for s in work.subscribers.values()):
                work.state = 'stale' if work.invalid or expired else 'unavailable'
                if expired:
                    for sub in work.subscribers.values():
                        if sub.state == 'queued': sub.state = 'stale'
                self._running -= 1
                return True
            work.state, work.started = 'running', self.clock()
            work._callback_active = True
            for sub in work.subscribers.values():
                if sub.state == 'queued': sub.state = 'running'
        try:
            outcome, result = self.generate(work.identity)
            if outcome not in ('ready', 'unavailable', 'unknown') or (outcome != 'ready' and result is not None):
                outcome, result = 'unknown', None
        except Exception:
            outcome, result = 'unknown', None
        with self._lock:
            self._expire(self.clock())
            self._running -= 1
            work._callback_active = False
            # Timeout/cancellation/invalidation suppresses late output. Unknown stays held.
            if work.unknown:
                return True
            if work.invalid:
                work.state = 'stale'
                return True
            if outcome == 'ready' and not any(s.state == 'running' for s in work.subscribers.values()):
                outcome, result = 'unavailable', None
            work.state, work.result = outcome, result if outcome == 'ready' else None
            work.unknown = outcome == 'unknown'
            for sub in work.subscribers.values():
                if sub.state == 'running': sub.state = 'ready' if outcome == 'ready' else 'unavailable'
        return True

    def view(self, ticket):
        with self._lock:
            self._expire(self.clock())
            pair = self._tickets.get(ticket)
            if not pair: return {'state': 'unavailable', 'text_fallback': True}
            work, sub = pair
            state = sub.state
            age = max(0, self.clock() - work.created)
        if state == 'ready' and not self._allowed(work.identity, sub.subscriber, 'delivery'):
            with self._lock:
                if sub.state == 'ready': sub.state = 'unavailable'
        with self._lock:
            self._expire(self.clock())
            state = sub.state
            response = {'state': state, 'age': age, 'sequence': sub.subscriber.sequence,
                        'text_fallback': state in ('stale', 'cancelled', 'unavailable')}
            if state == 'ready' and not work.invalid: response['result'] = work.result
            return response

    def cancel(self, ticket):
        with self._lock:
            pair = self._tickets.get(ticket)
            if not pair: return False
            work, sub = pair
            sub.state = 'cancelled'
            return True

    def active_subscribers(self, identity):
        """Snapshot active subscribers without holding the lock during authority reads."""
        with self._lock:
            self._expire(self.clock())
            work = self._works.get(identity)
            if not work or work.invalid or work.state not in ('checking', 'running'):
                return ()
            return tuple(s.subscriber for s in work.subscribers.values()
                         if s.state in ('queued', 'running'))

    def registered_terminology_work(self, session, actor, authority):
        """Snapshot this capability's live terminology-bound registrations.

        Internal metadata only: callers must recheck current source, target and
        grant rights and must not treat this snapshot as delivery authority.
        No store callback runs while the scheduler lock is held.
        """
        if any(not isinstance(v, str) or not v for v in (session, actor, authority)):
            raise ValueError('session, actor and authority required')
        with self._lock:
            self._expire(self.clock())
            return tuple((work.identity, sub.subscriber, sub.state)
                for work, sub in self._tickets.values()
                if work.identity.session == session
                and work.identity.private_actor == actor
                and work.identity.rights_partition == 'private:' + actor
                and work.identity.terminology_revision.startswith('terms:')
                and not work.invalid
                and work.state in ('queued', 'checking', 'running', 'ready')
                and sub.subscriber.actor == actor
                and sub.subscriber.authority == authority
                and sub.state in ('queued', 'running', 'ready'))

    def invalidate_source(self, session, source, current_revision):
        with self._lock:
            for work in self._works.values():
                ident = work.identity
                if ident.session == session and ident.source == source and ident.source_revision != current_revision:
                    work.invalid = True
                    if work.state not in ('running', 'unknown', 'checking'): work.state = 'stale'
                    for sub in work.subscribers.values():
                        if sub.state not in ('cancelled', 'unavailable'): sub.state = 'stale'
                    work.result = None

    def reconcile(self, identity, *, settled):
        """External durable authority confirms an unknown has been reconciled; no retry here."""
        if settled is not True: return False
        with self._lock:
            work = self._works.get(identity)
            if not work or not work.unknown or self._running_for(work): return False
            work.unknown = False
            work.state = 'stale' if work.invalid else 'unavailable'
            return True

    def _running_for(self, work):
        return getattr(work, '_callback_active', False)

    def forget(self, ticket):
        with self._lock:
            pair = self._tickets.get(ticket)
            if not pair: return False
            work, sub = pair
            if sub.state in ('queued', 'running') or work.state in ('checking', 'running', 'unknown') or work.unknown or self._running_for(work): return False
            del self._tickets[ticket]
            del work.subscribers[ticket]
            if not work.subscribers and work.state not in ('running', 'checking', 'unknown') and not work.unknown:
                self._works.pop(work.identity, None)
            if not any(w.identity.session == work.identity.session for w in self._works.values()):
                self._sessions.pop(work.identity.session, None)
            if not any(w.identity.session == work.identity.session and any(s.subscriber.actor == sub.subscriber.actor for s in w.subscribers.values()) for w in self._works.values()):
                self._viewers.pop((work.identity.session, sub.subscriber.actor), None)
            return True
