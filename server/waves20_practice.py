"""Private source-current practice operations over a primary-owned atomic adapter.

No global identity, store, router, provider or feedback engine is supplied here.
"""
import copy
import hashlib
import json
import re
from .phase10_common import Phase10Error

ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')


def fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def ident(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        fail('invalid_request', 'Invalid identifier.', 422)
    return value


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        fail('invalid_request', 'Invalid fields.', 422)


def revision(value):
    if type(value) is not int or value < 1: fail('invalid_request', 'Invalid source revision.', 422)
    return value


def _actor(actor, sid):
    if not isinstance(actor, dict) or actor.get('sid') != sid or actor.get('role') not in ('viewer', 'creator') or not actor.get('owner'):
        fail('not_found', 'Practice unavailable.', 404)


def _source(tx, actor, sid, source_id, source_revision):
    # tx.current_source must check current authorization and return only an eligible source.
    source = tx.current_source(actor, sid, source_id)
    if not isinstance(source, dict) or source.get('id') != source_id or source.get('revision') != source_revision:
        fail('stale_context', 'Source changed or is unavailable. Refresh to continue.')
    return source


def _authorized(tx, actor, sid, continuation):
    if not isinstance(continuation, dict) or continuation.get('owner') != actor['owner'] or continuation.get('sessionId') != sid:
        fail('not_found', 'Practice unavailable.', 404)
    # Every use, including replay and delivery, rechecks the explicit bridge.
    if not tx.bridge_active(actor, sid, continuation['priorSessionId'], continuation['priorAttemptId'], continuation['bridgeId']):
        fail('bridge_unavailable', 'Reconnect your private history to continue.')
    return continuation


def _mutate(adapter, actor, sid, request_id, operation, body, fn):
    _actor(actor, sid); ident(request_id)
    fingerprint = hashlib.sha256(json.dumps([operation, body], sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    # Must call fn(tx, prior_result) inside one transaction for both first execution
    # and replay; conflicting fingerprints must fail without running fn.
    return adapter.atomic(actor, sid, request_id, operation, fingerprint, fn)


def create_continuation(adapter, actor, sid, request_id, body):
    fields(body, ('priorSessionId', 'priorAttemptId', 'bridgeId', 'sourceId', 'sourceRevision', 'objectiveId'))
    for k in ('priorSessionId', 'priorAttemptId', 'bridgeId', 'sourceId', 'objectiveId'): ident(body[k])
    revision(body['sourceRevision'])
    def apply(tx, prior):
        if not tx.bridge_active(actor, sid, body['priorSessionId'], body['priorAttemptId'], body['bridgeId']):
            fail('bridge_unavailable', 'Reconnect your private history to continue.')
        previous = tx.private_attempt(actor, body['priorSessionId'], body['priorAttemptId'], body['bridgeId'])
        if not isinstance(previous, dict): fail('not_found', 'Private attempt unavailable.', 404)
        source = _source(tx, actor, sid, body['sourceId'], body['sourceRevision'])
        objective = tx.approved_objective(actor, sid, body['objectiveId'], source)
        if not isinstance(objective, dict): fail('objective_unavailable', 'Supported objective unavailable.')
        if prior is None:
            record = {'owner': actor['owner'], 'sessionId': sid, 'priorSessionId': body['priorSessionId'], 'priorAttemptId': body['priorAttemptId'], 'bridgeId': body['bridgeId'], 'sourceId': body['sourceId'], 'sourceRevision': body['sourceRevision'], 'objectiveId': body['objectiveId']}
            cid = tx.create_continuation(record)
        else:
            cid = prior['continuationId']
            _authorized(tx, actor, sid, tx.get_continuation(sid, cid))
        # Summary and source presentation are adapter-controlled owner-only projections.
        return {'continuationId': cid, 'sourceVersion': body['sourceRevision'], 'changeState': tx.change_state(previous, source), 'objective': copy.deepcopy(objective), 'previousAttemptSummary': tx.private_summary(previous), 'source': tx.source_projection(source)}
    return _mutate(adapter, actor, sid, request_id, 'create_continuation', body, apply)


def create_attempt(adapter, actor, sid, continuation_id, request_id, body):
    ident(continuation_id); fields(body, ('sourceRevision', 'text'))
    revision(body['sourceRevision'])
    if not isinstance(body['text'], str) or not body['text'].strip() or len(body['text']) > 4000 or any(ord(c) < 32 and c not in '\n\r\t' for c in body['text']):
        fail('invalid_request', 'Enter a bounded text attempt.', 422)
    def apply(tx, prior):
        c = _authorized(tx, actor, sid, tx.get_continuation(sid, continuation_id))
        if body['sourceRevision'] != c['sourceRevision']: fail('stale_context', 'Source changed. Create a continuation for its current revision.')
        source = _source(tx, actor, sid, c['sourceId'], c['sourceRevision'])
        objective = tx.approved_objective(actor, sid, c['objectiveId'], source)
        if not isinstance(objective, dict): fail('objective_unavailable', 'Supported objective unavailable.')
        if prior is None:
            # Existing practice adapter creates a private new attempt; never auto-shares.
            attempt = tx.create_private_attempt(actor, sid, c, body['text'], source, objective)
        else:
            attempt = tx.get_private_attempt(actor, sid, continuation_id, prior['attemptId'])
        if not isinstance(attempt, dict) or not isinstance(attempt.get('id'), str): fail('not_found', 'Private attempt unavailable.', 404)
        # No grading is asserted here. Adapter must suppress stale/unsupported feedback.
        return {'continuationId': continuation_id, 'attemptId': attempt['id'], 'attempt': tx.attempt_projection(attempt, source, objective)}
    return _mutate(adapter, actor, sid, request_id, 'create_attempt:' + continuation_id, body, apply)


def share_attempt(adapter, actor, sid, continuation_id, request_id, body):
    ident(continuation_id)
    required = {'attemptId', 'sourceRevision', 'scope', 'consent'}
    if not isinstance(body, dict) or set(body) not in (required, required | {'includeIdentity'}):
        fail('invalid_request', 'Invalid fields.', 422)
    if 'includeIdentity' in body and type(body['includeIdentity']) is not bool:
        fail('invalid_request', 'Invalid identity choice.', 422)
    ident(body['attemptId']); revision(body['sourceRevision'])
    if body['consent'] is not True or body['scope'] != 'creator': fail('invalid_request', 'Explicit creator sharing consent is required.', 422)
    def apply(tx, prior):
        c = _authorized(tx, actor, sid, tx.get_continuation(sid, continuation_id))
        if body['sourceRevision'] != c['sourceRevision']: fail('stale_context', 'Source changed. Refresh before sharing.')
        source = _source(tx, actor, sid, c['sourceId'], c['sourceRevision'])
        objective = tx.approved_objective(actor, sid, c['objectiveId'], source)
        if not isinstance(objective, dict): fail('objective_unavailable', 'Supported objective unavailable.')
        attempt = tx.get_private_attempt(actor, sid, continuation_id, body['attemptId'])
        if not isinstance(attempt, dict): fail('not_found', 'Selected attempt unavailable.', 404)
        if prior is None:
            share_id = tx.share_selected_attempt(actor, sid, attempt, source, objective, include_identity=True) if body.get('includeIdentity') else tx.share_selected_attempt(actor, sid, attempt, source, objective)
        else:
            share_id = prior['shareId']
        if prior is not None: tx.check_share(actor, sid, share_id, attempt, source)
        return {'continuationId': continuation_id, 'attemptId': body['attemptId'], 'shareId': share_id, 'scope': 'creator'}
    return _mutate(adapter, actor, sid, request_id, 'share_attempt:' + continuation_id, body, apply)
