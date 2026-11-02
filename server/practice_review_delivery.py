"""Trusted entry point for an already admitted Wave 20 practice review."""
import hashlib
import re
from .phase10_common import Context, Phase10Error
from . import waves20_review


class _ReviewHandler:
    """Bind the existing HTTP admission to the existing review factory."""
    def __init__(self, handler, ops):
        self._handler, self._ops = handler, ops

    def __getattr__(self, name):
        return getattr(self._handler, name)

    def w20_review_existing_attempt(self, sid, actor, continuation_id, attempt_id, guard):
        return review_existing(self._handler, self._ops, sid, actor,
                               continuation_id, attempt_id, guard)


def review_request(handler, ops, sid, actor, continuation_id, attempt_id, body, digest):
    """Use the real Wave 20 admission, authority guards and persisted receipt.

    Called outside store.LOCK. The HTTP seam owns request idempotency, snapshots,
    guarded persistence and its unknown state; this wrapper never retries effects.
    The admitted guard carries the existing provider's durable stage identity.
    """
    from . import waves20_practice_http
    waves20_practice_http._authenticate(handler, sid, actor, 'viewer')
    Context(handler, sid, actor).check_actor()
    return waves20_practice_http.review(_ReviewHandler(handler, ops), sid, actor,
                                        continuation_id, attempt_id, body, digest)


def review_existing(handler, ops, sid, actor, continuation_id, attempt_id, guard):
    """Run the shared review stage with fresh actor and admitted-input checks.

    The caller owns durable admission, guarded commit and response; this function
    must be called outside the store lock.  It does not retry provider effects.
    """
    context = Context(handler, sid, actor)
    if actor.get('sid') != sid or actor.get('role') != 'viewer':
        raise Phase10Error('not_found', 'Practice unavailable.', 404)

    def checked():
        context.check_actor()
        snapshot = guard()
        if (snapshot['continuation'].get('id') != continuation_id or
                snapshot['continuation'].get('owner') != actor.get('owner') or
                snapshot['attempt'].get('id') != attempt_id or
                snapshot['attempt'].get('_continuationId') != continuation_id):
            raise Phase10Error('stale_context', 'Practice context changed.', 409)
        return snapshot

    # The factory reads the correlation from its guard immediately before each
    # provider call. Preserve the admitted operation across this authority wrapper.
    checked.effect_id = getattr(guard, 'effect_id', None)
    if not isinstance(checked.effect_id, str) or not re.fullmatch(r'[0-9a-f]{64}', checked.effect_id):
        raise ValueError('Admitted review effect identity required')
    return waves20_review.review_existing(handler, ops, sid, checked)


def recover_effects(sid, owner, request_id):
    """Operator-only ledger lookup; absence or unknown never authorizes retry.

    Inputs must come from the original authenticated admission, not a browser
    asserting ownership. Call outside store.LOCK; this takes the provider lock.
    """
    from . import claude_provider
    from .waves20_practice_adapter import _dump
    if any(not isinstance(value, str) or not value for value in (sid, owner, request_id)):
        raise ValueError('Original admission identity required')
    operation = hashlib.sha256(_dump(['w20PracticeReview', sid, owner, request_id]).encode()).hexdigest()
    return {stage: claude_provider.lookup_effect({'operation': operation, 'stage': stage})
            for stage in ('draft', 'review')}
