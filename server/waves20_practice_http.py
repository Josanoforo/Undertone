"""Wave 20 practice HTTP seam. Mount only behind the session router."""
import hashlib
import json
import re
import sys
from . import store, lifecycle, phase5, waves20_practice as core
from .waves20_practice_adapter import Adapter, Transaction, _dump


def _source(db, actor, sid, source_id):
    from .http import expired
    row = db.execute("SELECT data,revision FROM objects WHERE kind='source' AND session_id=? AND id=?", (sid, source_id)).fetchone()
    if not row: return None
    value = json.loads(row['data'])
    if value.get('status') != 'active' or not value.get('audienceVisible') or expired(value): return None
    return dict(value, id=source_id, revision=row['revision'])


def _objective(db, actor, sid, objective_id, source):
    # Existing published activity is creator-approved persisted content, including its source versions.
    from . import http
    activity = phase5.presented(http, sid, objective_id)
    if not activity or source['id'] not in activity['sourceIds']: return None
    material = db.execute("SELECT data FROM objects WHERE kind='material' AND session_id=? AND id=?", (sid, objective_id)).fetchone()
    if not material: return None
    material = json.loads(material['data'])
    versions = material.get('versions', [])
    version = next((v for v in versions if v.get('number') == activity['version']), None)
    if not version or version.get('sourceRevisions', {}).get(source['id']) != source['revision']: return None
    exercise = activity['activity'].get('optionalAttempt')
    if not exercise: return None
    return {'id': objective_id, 'version': activity['version'], 'prompt': exercise['goal'], 'description': exercise['prompt']}


def _adapter(handler, digest=None):
    token = getattr(handler, '_auth_token', '')
    return Adapter(store.digest(token), _source, _objective, digest)


def _authenticate(handler, sid, actor, role):
    current = handler.auth(sid, [role])
    if current != actor: core.fail('not_found', 'Practice unavailable.', 404)
    return current


def _receipt(adapter, actor, sid, query):
    required = {'operation', 'requestId', 'fingerprint', 'target', 'revision'}
    if set(query) != required: core.fail('invalid_request', 'Invalid receipt lookup.', 422)
    core.ident(query['requestId'])
    if not isinstance(query['fingerprint'], str) or not re.fullmatch('[0-9a-f]{64}', query['fingerprint']): core.fail('invalid_request', 'Invalid receipt fingerprint.', 422)
    operations = {'w20PracticeCreate':'create_continuation', 'w20PracticeAttempt':'create_attempt:', 'w20PracticeShare':'share_attempt:', 'w20PracticeRevoke':'revoke_share:', 'w20PracticeReview':'review:'}
    operation = operations.get(query['operation'])
    if operation is None: core.fail('invalid_request', 'Invalid practice operation.', 422)
    if operation.endswith(':'):
        core.ident(query['target']); operation += query['target']
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            tx = Transaction(adapter, db); tx.actor_active(actor, sid)
            key = hashlib.sha256(_dump([sid, actor['owner'], query['requestId']]).encode()).hexdigest()
            rec = tx.get('w20practicereceipt', sid, key)
            if not rec:
                db.commit(); return dict(query, status='pending')
            if rec['operation'] != operation or rec.get('wireFingerprint') != query['fingerprint']:
                core.fail('request_conflict', 'Receipt does not match.', 409)
            result = dict(rec['result']); bound_fingerprint = result.pop('_reviewFingerprint', None); cid = result.get('continuationId')
            c = tx.get_continuation(sid, cid)
            if not c or c.get('owner') != actor['owner'] or (query['operation'] != 'w20PracticeRevoke' and tx.project(actor, sid, c)['state'] != 'current'): core.fail('not_found', 'Practice unavailable.', 404)
            if query['operation'] != 'w20PracticeCreate' and (cid != query['target'] or query['revision'] != c['sourceRevision']): core.fail('request_conflict', 'Receipt does not match.', 409)
            if 'shareId' in result and not result.get('revoked'): tx.share_current(actor, sid, result['shareId'])
            if 'attemptId' in result:
                attempt = tx.get_private_attempt(actor, sid, cid, result['attemptId'])
                if not attempt: core.fail('not_found', 'Practice unavailable.', 404)
                source = tx.current_source(actor, sid, c['sourceId']); objective = tx.approved_objective(actor, sid, c['objectiveId'], source)
                result = dict(result, attempt=tx.attempt_projection(attempt, source, objective)) if 'attempt' in result else result
                if query['operation'] == 'w20PracticeReview':
                    if not bound_fingerprint or _review_fingerprint(tx, actor, sid, c, attempt) != bound_fingerprint: core.fail('stale_context', 'Practice context changed.', 409)
                    result = dict(result, reviewStatus='complete' if attempt.get('processingStatus') == 'complete' else 'unknown')
            db.commit(); return dict(query, status='committed', result=result)
        except BaseException:
            db.rollback(); raise


def receipt(handler, sid, actor, query):
    _authenticate(handler, sid, actor, 'viewer')
    with store.LOCK: return _receipt(_adapter(handler), actor, sid, query)


def _review_fingerprint(tx, actor, sid, continuation, attempt):
    """Bind review to exact persisted inputs; status/answer are output fields."""
    if not attempt: core.fail('not_found', 'Attempt unavailable.', 404)
    source = tx.current_source(actor, sid, continuation['sourceId'])
    objective = tx.approved_objective(actor, sid, continuation['objectiveId'], source) if source else None
    previous = tx.private_attempt(actor, continuation['priorSessionId'], continuation['priorAttemptId'], continuation['bridgeId'])
    if not source or not objective or not previous: core.fail('not_found', 'Practice unavailable.', 404)
    if (attempt.get('goal') != objective.get('prompt') or
        attempt.get('sourceIds') != [source['id']] or
        attempt.get('sourceRevisions') != {source['id']: source['revision']}):
        core.fail('stale_context', 'Attempt no longer matches the approved context.', 409)
    stable_attempt = {k: v for k, v in attempt.items() if k not in ('processingStatus', 'answer', '_reviewFingerprint')}
    bridge = tx.get('w20bridge', sid, continuation['bridgeId'])
    return hashlib.sha256(_dump([continuation, bridge, previous, source, objective, stable_attempt]).encode()).hexdigest()


def review(handler, sid, actor, continuation_id, attempt_id, body, digest):
    """Admit once; invoke PRIMARY's extracted bounded review outside the store lock."""
    binding = getattr(handler, 'w20_review_existing_attempt', None)
    if not callable(binding): core.fail('review_unavailable', 'Practice review is not configured.', 503)
    core.fields(body, ('requestId', 'sourceRevision')); core.ident(attempt_id)
    adapter = _adapter(handler, digest); fresh = [False]; admitted = [None]
    def admit(tx, prior):
        c = core._authorized(tx, actor, sid, tx.get_continuation(sid, continuation_id))
        if body['sourceRevision'] != c['sourceRevision']: core.fail('stale_context', 'Source changed.')
        source = core._source(tx, actor, sid, c['sourceId'], c['sourceRevision'])
        objective = tx.approved_objective(actor, sid, c['objectiveId'], source)
        if not objective: core.fail('objective_unavailable', 'Objective unavailable.')
        attempt = tx.get_private_attempt(actor, sid, continuation_id, attempt_id)
        if not attempt: core.fail('not_found', 'Attempt unavailable.', 404)
        if prior is None:
            if attempt.get('processingStatus') != 'review_not_started': core.fail('review_unavailable', 'Review already started or completed.')
            row = tx.get('conversation', sid, attempt['_conversationId'])
            for item in row['attempts']:
                if item['id'] == attempt_id: item['processingStatus'] = 'review_unknown'
            tx.db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='conversation' AND session_id=? AND id=?", (_dump(row), sid, row['id']))
            fresh[0] = True
            attempt = tx.get_private_attempt(actor, sid, continuation_id, attempt_id)
            admitted[0] = _review_fingerprint(tx, actor, sid, c, attempt)
        fingerprint = admitted[0] if prior is None else prior.get('_reviewFingerprint')
        if not fingerprint or _review_fingerprint(tx, actor, sid, c, attempt) != fingerprint:
            core.fail('stale_context', 'Practice context changed.', 409)
        return {'continuationId':continuation_id, 'attemptId':attempt_id, 'reviewStatus': 'complete' if attempt.get('processingStatus') == 'complete' else 'unknown', '_reviewFingerprint': fingerprint}
    result = core._mutate(adapter, actor, sid, body['requestId'], 'review:' + continuation_id, {'attemptId':attempt_id, 'sourceRevision':body['sourceRevision']}, admit)
    if not fresh[0]: return result
    # No lock is held during model work. A crash or exception leaves unknown, never retries.
    def guard():
        with store.LOCK, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                tx = Transaction(adapter, db); tx.actor_active(actor, sid)
                c = tx.get_continuation(sid, continuation_id)
                if not c or c.get('owner') != actor['owner'] or tx.project(actor, sid, c)['state'] != 'current':
                    core.fail('not_found', 'Practice unavailable.', 404)
                a = tx.get_private_attempt(actor, sid, continuation_id, attempt_id)
                if not a or a.get('processingStatus') != 'review_unknown' or _review_fingerprint(tx, actor, sid, c, a) != admitted[0]:
                    core.fail('stale_context', 'Practice context changed.', 409)
                source = tx.current_source(actor, sid, c['sourceId'])
                objective = tx.approved_objective(actor, sid, c['objectiveId'], source)
                previous = tx.private_attempt(actor, c['priorSessionId'], c['priorAttemptId'], c['bridgeId'])
                snapshot = {'attempt': a, 'previous': previous, 'source': source, 'objective': objective, 'continuation': c}
                db.commit()
                return snapshot
            except BaseException:
                db.rollback(); raise
    # Opaque, stable correlation only; neither actor nor request ID enters the ledger.
    guard.effect_id = hashlib.sha256(_dump(['w20PracticeReview', sid, actor['owner'], body['requestId']]).encode()).hexdigest()
    try:
        guard()
        answer = binding(sid, dict(actor), continuation_id, attempt_id, guard)
    except Exception:
        return result
    if not isinstance(answer, dict) or not isinstance(answer.get('text'), str) or not isinstance(answer.get('citations'), list): return result
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            tx=Transaction(adapter, db); tx.actor_active(actor, sid)
            c=tx.get_continuation(sid, continuation_id)
            if not c or tx.project(actor, sid, c)['state'] != 'current': db.rollback(); return result
            a=tx.get_private_attempt(actor, sid, continuation_id, attempt_id)
            if not a or a.get('processingStatus') != 'review_unknown' or _review_fingerprint(tx, actor, sid, c, a) != admitted[0]: db.rollback(); return result
            row=tx.get('conversation', sid, a['_conversationId'])
            for item in row['attempts']:
                if item['id'] == attempt_id: item.update(answer=answer, processingStatus='complete', _reviewFingerprint=admitted[0])
            db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='conversation' AND session_id=? AND id=?", (_dump(row), sid, row['id']))
            db.commit(); result = dict(result, reviewStatus='complete')
        except BaseException:
            db.rollback(); raise
    return result




def prior_attempts(handler, sid, actor, body):
    """List only the history authorized by the supplied source capability."""
    core.fields(body, ('priorSessionId', 'sourceCapability'))
    prior_sid = core.ident(body['priorSessionId'])
    capability = body['sourceCapability']
    if not isinstance(capability, str) or not 1 <= len(capability) <= 512:
        core.fail('invalid_request', 'Source capability required.', 422)
    adapter = _adapter(handler)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            tx = Transaction(adapter, db); tx.actor_active(actor, sid)
            cred = db.execute("SELECT owner_id FROM credentials WHERE hash=? AND session_id=? AND role='viewer'", (store.digest(capability), prior_sid)).fetchone()
            session = tx.get('session', prior_sid, prior_sid)
            if not cred or not session or not lifecycle.active(session): core.fail('not_found', 'Prior capability unavailable.', 404)
            rows = db.execute("SELECT data FROM objects WHERE kind='conversation' AND session_id=? AND owner_id=? ORDER BY created_at,id", (prior_sid, cred['owner_id'])).fetchall()
            attempts = []
            for row in rows:
                conversation = json.loads(row['data'])
                if conversation.get('w20ContinuationId'): continue
                for attempt in conversation.get('attempts', []):
                    attempts.append(tx.private_summary(attempt))
            db.commit(); return {'priorSessionId': prior_sid, 'attempts': attempts}
        except BaseException:
            db.rollback(); raise


def discover(handler, sid, actor):
    """Project only explicit live bridges and current approved objectives."""
    adapter = _adapter(handler)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            tx = Transaction(adapter, db); tx.actor_active(actor, sid)
            bridges = []
            rows = db.execute("SELECT data FROM objects WHERE kind='w20bridge' AND session_id=? AND owner_id=? ORDER BY created_at,id", (sid, actor['owner'])).fetchall()
            for row in rows:
                b = json.loads(row['data'])
                if tx.bridge_active(actor, sid, b.get('sourceSessionId'), b.get('priorAttemptId'), b.get('id')):
                    attempt = tx.private_attempt(actor, b['sourceSessionId'], b['priorAttemptId'], b['id'])
                    bridges.append({'bridgeId': b['id'], 'priorSessionId': b['sourceSessionId'], 'priorAttemptId': b['priorAttemptId'], 'previousAttemptSummary': tx.private_summary(attempt)})
            sources = []
            rows = db.execute("SELECT id FROM objects WHERE kind='source' AND session_id=? ORDER BY created_at,id", (sid,)).fetchall()
            materials = db.execute("SELECT id FROM objects WHERE kind='material' AND session_id=? ORDER BY created_at,id", (sid,)).fetchall()
            for row in rows:
                source = tx.current_source(actor, sid, row['id'])
                if not source: continue
                objectives = []
                for material in materials:
                    obj = tx.approved_objective(actor, sid, material['id'], source)
                    if obj: objectives.append(obj)
                if objectives: sources.append({'source': tx.source_projection(source), 'objectives': objectives})
            db.commit(); return {'bridges': bridges, 'sources': sources}
        except BaseException:
            db.rollback(); raise


def handle(handler, sid, actor, method, parts):
    """parts after /w20/practice; handler.body computes digest of actual wire bytes."""
    _authenticate(handler, sid, actor, 'viewer')
    body = handler.body() if method == 'POST' else None
    digest = getattr(handler, '_body_sha256', None) if body is not None else None
    if body is not None and not digest: core.fail('invalid_request', 'Request body required.', 422)
    adapter = _adapter(handler, digest)
    if method == 'POST' and len(parts) == 5 and parts[0] == 'continuations' and parts[2] == 'attempts' and parts[4] == 'review':
        result = review(handler, sid, actor, parts[1], parts[3], body, digest)
        with store.LOCK, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                tx = Transaction(adapter, db); tx.actor_active(actor, sid)
                c = tx.get_continuation(sid, parts[1])
                if not c or c.get('owner') != actor['owner'] or tx.project(actor, sid, c)['state'] != 'current':
                    core.fail('not_found', 'Practice unavailable.', 404)
                a = tx.get_private_attempt(actor, sid, parts[1], parts[3])
                if not a or _review_fingerprint(tx, actor, sid, c, a) != result.get('_reviewFingerprint'):
                    core.fail('stale_context', 'Practice context changed.', 409)
                result = dict(result); result.pop('_reviewFingerprint', None)
                handler.send(200, result)
                db.commit()
            except BaseException:
                db.rollback(); raise
        return
    with store.LOCK:
        if parts == ['prior-attempts'] and method == 'POST':
            handler.send(200, prior_attempts(handler, sid, actor, body)); return
        if parts == ['discovery'] and method == 'GET':
            handler.send(200, discover(handler, sid, actor)); return
        if parts == ['continuations'] and method == 'GET':
            handler.send(200, {'continuations': adapter.list_current(actor, sid)}); return
        if len(parts) == 2 and parts[0] == 'continuations' and method == 'GET':
            handler.send(200, adapter.current(actor, sid, parts[1])); return
        if method == 'POST' and parts == ['receipt']:
            handler.send(200, _receipt(adapter, actor, sid, body)); return
        if method == 'POST' and isinstance(body, dict):
            request_id = body.get('requestId'); payload = dict(body); payload.pop('requestId', None)
            if parts == ['continuations']:
                result = core.create_continuation(adapter, actor, sid, request_id, payload)
            elif len(parts) == 3 and parts[0] == 'continuations' and parts[2] == 'attempts':
                result = core.create_attempt(adapter, actor, sid, parts[1], request_id, payload)
            elif len(parts) == 3 and parts[0] == 'continuations' and parts[2] == 'shares':
                result = core.share_attempt(adapter, actor, sid, parts[1], request_id, payload)
            elif len(parts) == 5 and parts[0] == 'continuations' and parts[2] == 'shares' and parts[4] == 'revoke':
                cid, share_id = core.ident(parts[1]), core.ident(parts[3]); core.fields(payload, ('sourceRevision',)); core.revision(payload['sourceRevision'])
                def revoke(tx, prior):
                    c = tx.get_continuation(sid, cid)
                    if not c or c.get('owner') != actor['owner']: core.fail('not_found', 'Practice unavailable.', 404)
                    if payload['sourceRevision'] != c['sourceRevision']: core.fail('stale_context', 'Source changed.')
                    sh = tx.get('w20practiceshare', sid, share_id)
                    if not sh or sh.get('ownerId') != actor['owner'] or sh.get('w20ContinuationId') != cid: core.fail('not_found', 'Share unavailable.', 404)
                    if prior is None:
                        sh['active'] = False
                        tx.db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w20practiceshare' AND session_id=? AND id=?", (_dump(sh), sid, share_id))
                    return {'continuationId':cid, 'shareId':share_id, 'revoked':True}
                result = core._mutate(adapter, actor, sid, request_id, 'revoke_share:' + cid, payload, revoke)
            else: core.fail('not_found', 'Practice route unavailable.', 404)
            # Protect serialization against source/bridge withdrawal following commit.
            current = adapter.current(actor, sid, result['continuationId'])
            if not result.get('revoked') and current['state'] != 'current': core.fail('not_found', 'Practice unavailable.', 404)
            handler.send(201, result); return
    core.fail('not_found', 'Practice route unavailable.', 404)


def deliver_creator_share(handler, sid, actor, share_id):
    _authenticate(handler, sid, actor, 'creator'); core.ident(share_id)
    with store.LOCK, store.connect() as db:
        if not db.execute("SELECT 1 FROM credentials WHERE hash=? AND session_id=? AND owner_id=? AND role='creator'", (store.digest(handler._auth_token), sid, actor['owner'])).fetchone(): core.fail('not_found', 'Share unavailable.', 404)
        session = db.execute("SELECT data FROM objects WHERE kind='session' AND session_id=? AND id=?", (sid, sid)).fetchone()
        if not session or not lifecycle.active(json.loads(session['data'])): core.fail('not_found', 'Share unavailable.', 404)
        row = db.execute("SELECT data FROM objects WHERE kind='w20practiceshare' AND session_id=? AND id=?", (sid, share_id)).fetchone()
        sh = json.loads(row['data']) if row else None
        row = db.execute("SELECT data FROM objects WHERE kind='w20practice' AND session_id=? AND id=?", (sid, sh.get('w20ContinuationId') if sh else '')).fetchone()
        c = json.loads(row['data']) if row else None
        row = db.execute("SELECT data FROM objects WHERE kind='w20bridge' AND session_id=? AND id=?", (sid, c.get('bridgeId') if c else '')).fetchone()
        bridge = json.loads(row['data']) if row else None
        if not bridge: core.fail('not_found', 'Share unavailable.', 404)
        adapter = Adapter(bridge.get('targetCredentialHash'), _source, _objective)
        def send(value):
            projection = {k:value[k] for k in ('id','attemptId','summary','createdAt') if k in value}
            if value.get('includeIdentity') is True:
                row = db.execute("SELECT data FROM objects WHERE kind='viewer' AND session_id=? AND id=?", (sid, value.get('ownerId'))).fetchone()
                viewer = json.loads(row['data']) if row else None
                if viewer and isinstance(viewer.get('displayName'), str): projection['displayName'] = viewer['displayName']
            handler.send(200, {'share': projection})
        return adapter.deliver_share(sid, share_id, send)
