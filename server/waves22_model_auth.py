"""Persisted creator approval and current practice authorization for Wave 22 models."""
import json
from . import store, waves22_models as models, waves20_practice_http as practice_http
from .waves20_practice_adapter import Adapter, Transaction
from .phase10_common import Context, Phase10Error

APPROVAL = 'w22modelapproval'


def unavailable():
    raise Phase10Error('not_found', 'Model context unavailable.', 404)


def _template(db, sid, creator, definition):
    tid = definition['templateId']; version = definition['templateVersion']
    rows = []
    for kind, oid in (('w17template', tid), ('w17templateversion', tid + ':' + str(version))):
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (kind, oid, sid)).fetchone()
        if not row or row['owner_id'] != creator: unavailable()
        rows.append(json.loads(row['data']))
    if rows[0].get('creatorId') != creator or rows[1].get('templateId') != tid or rows[1].get('version') != version: unavailable()
    if rows[0].get('importedFrom'):
        from .waves17_templates import validate_import
        validate_import(rows[0]['importedFrom']['transferId'])
    return rows


def approve(ctx, definition):
    definition = models.validate_definition(definition)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            ctx.check_actor()
            session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
            if ctx.actor.get('role') != 'creator' or not session or session['owner_id'] != ctx.actor.get('owner'): unavailable()
            _template(db, ctx.sid, ctx.actor['owner'], definition)
            ctx.resolve(definition['sourceRefs'])
            oid = models._hash(definition)
            row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND session_id=? AND id=?', (APPROVAL, ctx.sid, oid)).fetchone()
            value = {'definition': definition, 'active': True, 'creatorId': ctx.actor['owner']}
            if row:
                if row['owner_id'] != ctx.actor['owner'] or json.loads(row['data']) != value: unavailable()
            else:
                models._insert(db, APPROVAL, ctx.sid, ctx.actor['owner'], oid, value)
            db.commit()
            return {'approvalId': oid, 'definition': definition}
        except BaseException:
            db.rollback(); raise


def revoke_approval(ctx, approval_id):
    """Withdraw a creator approval even after its source or template expires."""
    models._id(approval_id)
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            ctx.check_actor()
            session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
            if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') != 'creator' or not session or session['owner_id'] != ctx.actor.get('owner'):
                unavailable()
            row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND session_id=? AND id=?', (APPROVAL, ctx.sid, approval_id)).fetchone()
            if not row or row['owner_id'] != ctx.actor['owner']:
                unavailable()
            value = json.loads(row['data'])
            if value.get('creatorId') != ctx.actor['owner'] or models._hash(models.validate_definition(value.get('definition'))) != approval_id:
                unavailable()
            if value.get('active') is True:
                value['active'] = False
                db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND session_id=? AND id=?', (models._json(value), row['revision'] + 1, APPROVAL, ctx.sid, approval_id))
            elif value.get('active') is not False:
                unavailable()
            db.commit()
            return {'approvalId': approval_id, 'state': 'withdrawn'}
        except BaseException:
            db.rollback()
            raise


class ModelContext(Context):
    def authorize(self, db, definition, attempt_id, owner):
        definition = models.validate_definition(definition)
        self.check_actor()
        if self.actor.get('sid') != self.sid or self.actor.get('role') not in ('creator', 'viewer'): unavailable()
        if self.actor['role'] == 'viewer' and self.actor.get('owner') != owner: unavailable()
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (self.sid, self.sid)).fetchone()
        if not session or (self.actor['role'] == 'creator' and self.actor['owner'] != session['owner_id']): unavailable()
        creator = session['owner_id']
        _template(db, self.sid, creator, definition)
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND session_id=? AND id=?', (APPROVAL, self.sid, models._hash(definition))).fetchone()
        if not row or row['owner_id'] != creator or json.loads(row['data']) != {'definition': definition, 'active': True, 'creatorId': creator}: unavailable()
        resolved = self.resolve(definition['sourceRefs'])
        if any(r['ref']['sessionId'] != self.sid or not r['source'].get('audienceVisible') for r in resolved): unavailable()
        rows = db.execute("SELECT data FROM objects WHERE kind='conversation' AND session_id=? AND owner_id=?", (self.sid, owner)).fetchall()
        matches = []
        for row in rows:
            conversation = json.loads(row['data'])
            for attempt in conversation.get('attempts', []):
                if attempt.get('id') == attempt_id and conversation.get('w20ContinuationId'):
                    matches.append((conversation['w20ContinuationId'], attempt))
        if len(matches) != 1: unavailable()
        cid, attempt = matches[0]
        row = db.execute("SELECT data FROM objects WHERE kind='w20practice' AND session_id=? AND id=? AND owner_id=?", (self.sid, cid, owner)).fetchone()
        if not row: unavailable()
        continuation = json.loads(row['data'])
        bridge_row = db.execute("SELECT data FROM objects WHERE kind='w20bridge' AND session_id=? AND id=?", (self.sid, continuation.get('bridgeId'))).fetchone()
        if not bridge_row: unavailable()
        bridge = json.loads(bridge_row['data']); credential = bridge.get('targetCredentialHash')
        if not isinstance(credential, str): unavailable()
        viewer = {'sid': self.sid, 'role': 'viewer', 'owner': owner}
        tx = Transaction(Adapter(credential, practice_http._source, practice_http._objective), db)
        current = tx.get_continuation(self.sid, cid)
        if not current or current.get('owner') != owner or tx.project(viewer, self.sid, current).get('state') != 'current': unavailable()
        source = tx.current_source(viewer, self.sid, current['sourceId'])
        objective = tx.approved_objective(viewer, self.sid, current['objectiveId'], source)
        if not objective or attempt.get('goal') != objective['prompt'] or attempt.get('sourceIds') != [source['id']] or attempt.get('sourceRevisions') != {source['id']: source['revision']}: unavailable()
        if any(ref['sourceId'] != source['id'] or ref['sourceRevision'] != source['revision'] for ref in definition['sourceRefs']): unavailable()
        # Bind private inputs, excluding asynchronously produced review output.
        stable_attempt = {k: v for k, v in attempt.items() if k not in ('processingStatus', 'answer', '_reviewFingerprint')}
        return models._hash(stable_attempt)


def list_approvals(ctx):
    """Current creator-approved definitions whose source remains audience-visible."""
    with store.LOCK, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') not in ('creator', 'viewer'): unavailable()
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
        if not session or (ctx.actor['role'] == 'creator' and ctx.actor.get('owner') != session['owner_id']): unavailable()
        creator = session['owner_id']
        rows = db.execute('SELECT id,data,owner_id FROM objects WHERE kind=? AND session_id=? ORDER BY created_at,id', (APPROVAL, ctx.sid)).fetchall()
        result = []
        for row in rows:
            try:
                value = json.loads(row['data'])
                definition = models.validate_definition(value.get('definition'))
                if row['owner_id'] != creator or value != {'definition': definition, 'active': True, 'creatorId': creator} or row['id'] != models._hash(definition): continue
                _template(db, ctx.sid, creator, definition)
                resolved = ctx.resolve(definition['sourceRefs'])
                if any(r['ref']['sessionId'] != ctx.sid or not r['source'].get('audienceVisible') for r in resolved): continue
                result.append({'approvalId': row['id'], 'definition': definition})
            except Phase10Error as exc:
                if exc.code not in ('not_found', 'stale_context'): raise
        return {'approvals': result}


def guard_approval(ctx, result):
    with store.LOCK, store.connect() as db:
        ctx.check_actor()
        definition = models.validate_definition(result['definition'])
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
        if not session or ctx.actor.get('role') != 'creator' or session['owner_id'] != ctx.actor.get('owner'): unavailable()
        _template(db, ctx.sid, session['owner_id'], definition)
        ctx.resolve(definition['sourceRefs'])
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND session_id=? AND id=?', (APPROVAL, ctx.sid, result['approvalId'])).fetchone()
        if not row or row['owner_id'] != session['owner_id'] or json.loads(row['data']) != {'definition': definition, 'active': True, 'creatorId': session['owner_id']}: unavailable()


def guard_share_owner(ctx, share_id, model_id):
    with store.LOCK, store.connect() as db:
        ctx.check_actor()
        share, _, owner = models._load(db, models.SHARE, ctx.sid, share_id)
        if owner != ctx.actor.get('owner') or share.get('modelId') != model_id or share.get('active') is not True: unavailable()

