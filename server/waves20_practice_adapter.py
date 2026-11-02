"""SQLite-backed private practice. Handler owns source/objective eligibility and delivery lock."""
import hashlib
import json
from . import lifecycle, store, waves20_practice as core


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Adapter:
    """credential_hash is the authenticated target digest; callbacks use the supplied DB.

    source(db, actor, sid, id) returns an eligible {id, revision, title, at, ...};
    objective(db, actor, sid, id, source) returns an approved objective or None.
    Both callbacks must use this transaction, perform no writes or network calls.
    """
    def __init__(self, credential_hash, source, objective, wire_fingerprint=None):
        if wire_fingerprint is not None and (not isinstance(wire_fingerprint, str) or len(wire_fingerprint) != 64 or any(c not in '0123456789abcdef' for c in wire_fingerprint)):
            raise ValueError('Invalid request wire fingerprint')
        self.credential_hash, self.source, self.objective = credential_hash, source, objective
        self.wire_fingerprint = wire_fingerprint

    def atomic(self, actor, sid, request_id, operation, fingerprint, callback):
        with store.LOCK, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                tx = Transaction(self, db)
                tx.actor_active(actor, sid)
                key = hashlib.sha256(_dump([sid, actor['owner'], request_id]).encode()).hexdigest()
                receipt = tx.get('w20practicereceipt', sid, key)
                if receipt and (receipt['operation'] != operation or receipt['fingerprint'] != fingerprint or receipt.get('wireFingerprint') != self.wire_fingerprint):
                    core.fail('request_conflict', 'Request ID already used.')
                result = callback(tx, receipt['result'] if receipt else None)
                continuation = tx.get_continuation(sid, result.get('continuationId'))
                if not continuation or continuation.get('owner') != actor['owner'] or (not operation.startswith('revoke_share:') and tx.project(actor, sid, continuation)['state'] != 'current'): core.fail('objective_unavailable', 'Practice context changed.')
                if not receipt:
                    tx.put('w20practicereceipt', sid, actor['owner'], {'operation': operation, 'fingerprint': fingerprint, 'wireFingerprint': self.wire_fingerprint, 'result': result}, key)
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise

    def deliver_share(self, sid, share_id, deliver):
        """Call only after handler authenticates creator; deliver while holding the lock."""
        core.ident(share_id)
        with store.LOCK, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                tx = Transaction(self, db)
                sh = tx.get('w20practiceshare', sid, share_id)
                c = tx.get_continuation(sid, sh.get('w20ContinuationId')) if sh else None
                if not c: core.fail('not_found', 'Share unavailable.', 404)
                actor = {'sid': sid, 'role': 'viewer', 'owner': c['owner']}
                value = tx.share_current(actor, sid, share_id)
                result = deliver(value)
                db.commit()
                return result
            except BaseException:
                db.rollback()
                raise
    def list_current(self, actor, sid):
        core._actor(actor, sid)
        with store.LOCK, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                tx = Transaction(self, db); tx.actor_active(actor, sid)
                rows = db.execute("SELECT data FROM objects WHERE kind='w20practice' AND session_id=? AND owner_id=? ORDER BY created_at,id", (sid, actor['owner'])).fetchall()
                result = [tx.project(actor, sid, json.loads(row['data'])) for row in rows]
                db.commit(); return result
            except BaseException:
                db.rollback(); raise

    def current(self, actor, sid, continuation_id):
        core._actor(actor, sid); core.ident(continuation_id)
        with store.LOCK, store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                tx = Transaction(self, db); tx.actor_active(actor, sid)
                c = tx.get_continuation(sid, continuation_id)
                if not c or c.get('owner') != actor['owner']: core.fail('not_found', 'Practice unavailable.', 404)
                result = tx.project(actor, sid, c)
                db.commit(); return result
            except BaseException:
                db.rollback(); raise


class Transaction:
    def __init__(self, adapter, db): self.adapter, self.db = adapter, db
    def get(self, kind, sid, oid):
        r = self.db.execute('SELECT data FROM objects WHERE kind=? AND session_id=? AND id=?', (kind, sid, oid)).fetchone()
        return json.loads(r['data']) if r else None
    def put(self, kind, sid, owner, value, oid=None):
        oid = oid or store.ident(); value = dict(value, id=oid)
        self.db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)', (kind, oid, sid, owner, _dump(value), store.now()))
        return oid
    def actor_active(self, actor, sid):
        core._actor(actor, sid)
        row = self.db.execute('SELECT 1 FROM credentials WHERE hash=? AND session_id=? AND owner_id=? AND role=?', (self.adapter.credential_hash, sid, actor['owner'], actor['role'])).fetchone()
        session = self.get('session', sid, sid)
        if actor['role'] != 'viewer' or not row or not session or not lifecycle.active(session): core.fail('not_found', 'Practice unavailable.', 404)
    def bridge_active(self, actor, sid, prior_sid, prior_id, bridge_id):
        self.actor_active(actor, sid)
        b = self.get('w20bridge', sid, bridge_id)
        if not b or b.get('status') != 'active' or b.get('targetOwnerId') != actor['owner'] or b.get('targetCredentialHash') != self.adapter.credential_hash or b.get('sourceSessionId') != prior_sid or b.get('priorAttemptId') != prior_id: return False
        if b.get('expiresAt') is not None and lifecycle.past(b['expiresAt']): return False
        source_session = self.get('session', prior_sid, prior_sid)
        if not source_session or not lifecycle.active(source_session): return False
        if not self.db.execute("SELECT 1 FROM credentials WHERE hash=? AND role='viewer' AND session_id=? AND owner_id=?", (b.get('sourceCredentialHash'), prior_sid, b.get('sourceOwnerId'))).fetchone(): return False
        return self.private_attempt(actor, prior_sid, prior_id, bridge_id) is not None
    def private_attempt(self, actor, prior_sid, prior_id, bridge_id):
        b = self.get('w20bridge', actor['sid'], bridge_id)
        if not b: return None
        rows = self.db.execute("SELECT data FROM objects WHERE kind='conversation' AND session_id=? AND owner_id=?", (prior_sid, b.get('sourceOwnerId'))).fetchall()
        for row in rows:
            conversation = json.loads(row['data'])
            # A Wave 20 attempt needs its own live bridge and objective; do not
            # turn it into an unguarded prior attempt through a second bridge.
            if conversation.get('w20ContinuationId'): continue
            for attempt in conversation.get('attempts', []):
                if attempt.get('id') == prior_id: return attempt
        return None
    def current_source(self, actor, sid, source_id): return self.adapter.source(self.db, actor, sid, source_id)
    def approved_objective(self, actor, sid, objective_id, source):
        objective = self.adapter.objective(self.db, actor, sid, objective_id, source)
        bound = getattr(self, '_objective_version', None)
        return objective if not bound or (objective and objective.get('version') == bound) else None
    def create_continuation(self, record):
        source = self.current_source({'sid': record['sessionId'], 'role': 'viewer', 'owner': record['owner']}, record['sessionId'], record['sourceId'])
        objective = self.approved_objective({'sid': record['sessionId'], 'role': 'viewer', 'owner': record['owner']}, record['sessionId'], record['objectiveId'], source)
        if not objective or type(objective.get('version')) is not int: core.fail('objective_unavailable', 'Supported objective unavailable.')
        return self.put('w20practice', record['sessionId'], record['owner'], dict(record, objectiveVersion=objective['version']))
    def get_continuation(self, sid, cid):
        value = self.get('w20practice', sid, cid)
        self._objective_version = value.get('objectiveVersion') if value else None
        return value
    def change_state(self, previous, source):
        revs = previous.get('sourceRevisions') or {}
        return 'unchanged' if revs.get(source['id']) == source['revision'] else 'changed_or_unavailable'
    def private_summary(self, previous):
        return {'id': previous['id'], 'text': previous.get('text', ''),
                'goal': previous.get('goal', ''),
                'sourceIds': previous.get('sourceIds', []),
                'sourceRevisions': previous.get('sourceRevisions', {})}
    def source_projection(self, source): return {k: source[k] for k in ('id', 'revision', 'title', 'at') if k in source}
    def create_private_attempt(self, actor, sid, c, text, source, objective):
        aid = store.ident(); cid = c['id']; conversation_id = store.ident()
        attempt = {'id': aid, 'goal': objective.get('prompt', ''), 'difficulty': '', 'text': text, 'image': None, 'previousAttemptId': None, 'createdAt': store.now(), 'sourceIds': [source['id']], 'sourceRevisions': {source['id']: source['revision']}, 'revision': 1, 'processingStatus': 'review_not_started'}
        conversation = {'id': conversation_id, 'ownerId': actor['owner'], 'title': 'Private practice', 'mode': 'practice', 'messages': [], 'attempts': [attempt], 'createdAt': store.now(), 'w20ContinuationId': cid}
        self.put('conversation', sid, actor['owner'], conversation, conversation_id)
        return attempt
    def get_private_attempt(self, actor, sid, cid, aid):
        rows = self.db.execute("SELECT data FROM objects WHERE kind='conversation' AND session_id=? AND owner_id=?", (sid, actor['owner'])).fetchall()
        for row in rows:
            c = json.loads(row['data'])
            if c.get('w20ContinuationId') == cid:
                for a in c.get('attempts', []):
                    if a.get('id') == aid: return dict(a, _conversationId=c['id'], _continuationId=cid)
        return None
    def attempt_projection(self, attempt, source, objective):
        answer = attempt.get('answer') if attempt.get('processingStatus') == 'complete' else None
        return {'id': attempt['id'], 'text': attempt['text'], 'goal': attempt.get('goal', ''), 'sourceIds': attempt.get('sourceIds', []), 'sourceRevisions': attempt.get('sourceRevisions', {}), 'createdAt': attempt['createdAt'], 'feedbackStatus': attempt.get('processingStatus', 'review_not_started'), 'feedback': answer.get('text') if isinstance(answer, dict) else None, 'citations': answer.get('citations', []) if isinstance(answer, dict) else []}
    def share_selected_attempt(self, actor, sid, attempt, source, objective, include_identity=False):
        value = {'ownerId': actor['owner'], 'conversationId': attempt['_conversationId'], 'summary': attempt['text'], 'citations': [], 'allowPublicDerivative': False, 'includeImage': False, 'image': None, 'messageId': None, 'attemptId': attempt['id'], 'messageRevision': None, 'attemptRevision': attempt['revision'], 'sourceIds': [source['id']], 'sourceRevisions': {source['id']: source['revision']}, 'active': True, 'createdAt': store.now(), 'w20ContinuationId': attempt['_continuationId']}
        if include_identity is True: value['includeIdentity'] = True
        return self.put('w20practiceshare', sid, actor['owner'], value)
    def check_share(self, actor, sid, share_id, attempt, source):
        sh = self.get('w20practiceshare', sid, share_id)
        if not sh or not sh.get('active') or sh.get('ownerId') != actor['owner'] or sh.get('attemptId') != attempt['id'] or sh.get('w20ContinuationId') != attempt['_continuationId']: core.fail('not_found', 'Share unavailable.', 404)
    def project(self, actor, sid, c):
        result = {'continuationId': c['id'], 'state': 'unavailable', 'attempts': [], 'activeShares': []}
        rows = self.db.execute("SELECT data FROM objects WHERE kind='w20practiceshare' AND session_id=? AND owner_id=? ORDER BY created_at,id", (sid, actor['owner'])).fetchall()
        for row in rows:
            share = json.loads(row['data'])
            if share.get('active') and share.get('ownerId') == actor['owner'] and share.get('w20ContinuationId') == c['id']:
                result['activeShares'].append({'shareId': share['id'], 'attemptId': share.get('attemptId'), 'sourceRevision': c['sourceRevision']})
        if not self.bridge_active(actor, sid, c['priorSessionId'], c['priorAttemptId'], c['bridgeId']): return result
        previous = self.private_attempt(actor, c['priorSessionId'], c['priorAttemptId'], c['bridgeId'])
        if not previous: return result
        result['previousAttemptSummary'] = self.private_summary(previous)
        # Owner-only history remains readable after a source or objective changes.
        # Never project feedback without the current-context fingerprint check below.
        rows = self.db.execute("SELECT data FROM objects WHERE kind='conversation' AND session_id=? AND owner_id=?", (sid, actor['owner'])).fetchall()
        history = []
        for row in rows:
            conversation = json.loads(row['data'])
            if conversation.get('w20ContinuationId') == c['id']:
                for attempt in conversation.get('attempts', []):
                    history.append(self.attempt_projection(dict(attempt, processingStatus='review_unavailable', answer=None), None, None))
        result['attempts'] = history
        result['newAttempts'] = history
        source = self.current_source(actor, sid, c['sourceId'])
        if not source or source.get('id') != c['sourceId'] or source.get('revision') != c['sourceRevision']:
            result['state'] = 'source_changed_or_unavailable'
            result['changeDescription'] = 'The source changed or is unavailable. Choose a current approved objective to continue.'
            return result
        objective = self.approved_objective(actor, sid, c['objectiveId'], source)
        if not isinstance(objective, dict) or objective.get('version') != c.get('objectiveVersion'): result['state'] = 'objective_unavailable'; return result
        result.update(id=c['id'], state='current', sourceVersion=c['sourceRevision'], source=self.source_projection(source), objective=objective)
        result['changeState'] = self.change_state(previous, source)
        result['attempts'] = []
        rows = self.db.execute("SELECT data FROM objects WHERE kind='conversation' AND session_id=? AND owner_id=?", (sid, actor['owner'])).fetchall()
        for row in rows:
            conversation = json.loads(row['data'])
            if conversation.get('w20ContinuationId') == c['id']:
                for attempt in conversation.get('attempts', []):
                    if attempt.get('processingStatus') == 'complete':
                        # A later mutation must not attach old feedback to different inputs.
                        from .waves20_practice_http import _review_fingerprint
                        private = self.get_private_attempt(actor, sid, c['id'], attempt['id'])
                        try:
                            current = _review_fingerprint(self, actor, sid, c, private)
                        except Exception:
                            current = None
                        if not attempt.get('_reviewFingerprint') or current != attempt['_reviewFingerprint']:
                            attempt = dict(attempt, processingStatus='review_unavailable', answer=None)
                    result['attempts'].append(self.attempt_projection(attempt, source, objective))
        result['newAttempts'] = result['attempts']
        return result

    def share_current(self, actor, sid, share_id):
        """Owner-side check only; creator delivery requires the integration guard below."""
        sh = self.get('w20practiceshare', sid, share_id)
        if not sh or sh.get('ownerId') != actor['owner'] or not sh.get('active'): core.fail('not_found', 'Share unavailable.', 404)
        c = self.get_continuation(sid, sh.get('w20ContinuationId'))
        if not c or self.project(actor, sid, c)['state'] != 'current': core.fail('not_found', 'Share unavailable.', 404)
        attempt = self.get_private_attempt(actor, sid, c['id'], sh.get('attemptId'))
        if not attempt: core.fail('not_found', 'Share unavailable.', 404)
        self.check_share(actor, sid, share_id, attempt, None)
        return sh


