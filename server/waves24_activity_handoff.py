"""Wave 24 activity configuration primitives; not mounted by the shared router."""
import json

from . import store, waves22_models as models, waves22_model_auth as model_auth
from . import waves22_adoption as adoption, waves22_coedit_auth as coedit_auth
from .phase10_common import Context, Phase10Error

ACTIVITY = 'w24activity'
RECEIPT = 'w24activityreceipt'
VERSION = 'w24activityversion'
EDITORIAL_TEMPLATE = 'w24editorialtemplate'
EDITORIAL_VERSION = 'w24editorialversion'
EDITORIAL_RECEIPT = 'w24editorialreceipt'
REVIEWED_RECORD = 'w24reviewedrecord'
RECORD_RECEIPT = 'w24recordreceipt'
COEDIT_TEMPLATE = 'w24drafttemplate'
COEDIT_VERSION = 'w24drafttemplateversion'
COEDIT_RECEIPT = 'w24drafttemplatereceipt'
REASON_LINK = 'w24activityreason'
CROSS_INTENT = 'w24crossintent'


def link_reason(ctx, body):
    """The reason's author explicitly opts its current revision into an activity."""
    models._fields(body, ('activityId', 'activityRevision', 'reasonId', 'reasonRevision', 'consent'))
    if body['consent'] is not True:
        raise Phase10Error('invalid_request', 'Explicit consent is required.', 422)
    reason_id = models._id(body['reasonId'])
    revision = models._integer(body['reasonRevision'], 1, 2147483647)
    activity_id = models._id(body['activityId'])
    activity_revision = models._integer(body['activityRevision'], 1, 2147483647)
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        db.execute('BEGIN IMMEDIATE')
        read_version(ctx, activity_id, activity_revision)
        row = db.execute('SELECT owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         ('w14reason', reason_id, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor.get('owner'):
            _unavailable()
        _reasons(db, ctx, [{'id': reason_id, 'revision': revision}])
        oid = models._hash([ctx.sid, activity_id, activity_revision, reason_id])
        existing = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                              (REASON_LINK, oid, ctx.sid)).fetchone()
        value = {'activityId': activity_id, 'activityRevision': activity_revision,
                 'reasonId': reason_id, 'reasonRevision': revision}
        if existing:
            if existing['owner_id'] != ctx.actor['owner']:
                raise Phase10Error('request_conflict', 'Reason link changed.', 409)
            previous = json.loads(existing['data'])
            if any(previous.get(k) != v for k, v in value.items()) or not previous.get('consentId'):
                value['consentId'] = store.ident()
                db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=?',
                           (models._json(value), REASON_LINK, oid, ctx.sid))
        else:
            value['consentId'] = store.ident()
            models._insert(db, REASON_LINK, ctx.sid, ctx.actor['owner'], oid, value)
        db.commit()
        return {'linked': True, 'reasonId': reason_id, 'reasonRevision': revision}


def _eligible_reason_refs(db, ctx, activity_id, activity_revision):
    refs = []
    rows = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND session_id=?',
                      (REASON_LINK, ctx.sid)).fetchall()
    for row in rows:
        link = json.loads(row['data'])
        if link['activityId'] != activity_id or link['activityRevision'] != activity_revision:
            continue
        reason = db.execute('SELECT owner_id,revision,data FROM objects WHERE kind=? AND id=? AND session_id=?',
                            ('w14reason', link['reasonId'], ctx.sid)).fetchone()
        if (reason and reason['owner_id'] == row['owner_id'] and reason['revision'] == link['reasonRevision']
                and json.loads(reason['data']).get('status') != 'withdrawn'):
            refs.append({'id': link['reasonId'], 'revision': link['reasonRevision']})
    return sorted(refs, key=lambda ref: ref['id'])


def _reason_consents(db, ctx, activity_id, activity_revision, references):
    """Bind review to each explicit grant, so re-consent cannot revive it."""
    result = []
    for ref in references:
        oid = models._hash([ctx.sid, activity_id, activity_revision, ref['id']])
        row = db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (REASON_LINK, oid, ctx.sid)).fetchone()
        value = json.loads(row['data']) if row else {}
        if not value.get('consentId') or value.get('reasonRevision') != ref['revision']:
            raise Phase10Error('stale_context', 'Reason consent changed.', 409)
        result.append(value['consentId'])
    return result


def unlink_reason(ctx, body):
    models._fields(body, ('activityId', 'activityRevision', 'reasonId'))
    activity_id = models._id(body['activityId'])
    revision = models._integer(body['activityRevision'], 1, 2147483647)
    reason_id = models._id(body['reasonId'])
    oid = models._hash([ctx.sid, activity_id, revision, reason_id])
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (REASON_LINK, oid, ctx.sid)).fetchone()
        if row and row['owner_id'] != ctx.actor.get('owner'):
            _unavailable()
        if row:
            db.execute('DELETE FROM objects WHERE kind=? AND id=? AND session_id=?', (REASON_LINK, oid, ctx.sid))
        db.commit()
        return {'linked': False, 'reasonId': reason_id}


def activity_reasons(ctx, activity_id, revision):
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        read_version(ctx, activity_id, revision)
        refs = _eligible_reason_refs(db, ctx, activity_id, revision)
        return {'activityId': activity_id, 'activityRevision': revision, 'reasons': _reasons(db, ctx, refs)}


def draft_template(ctx, template_id, version):
    """Resolve an exact approved draft snapshot under current coedit rights."""
    from . import waves22_coedit as coedit
    models._id(template_id)
    models._integer(version, 1, 2147483647)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        head = coedit._read(db, COEDIT_TEMPLATE, ctx.sid, template_id)
        selected = coedit._read(db, COEDIT_VERSION, ctx.sid, models._hash([template_id, version]))
        if not head or not selected or head[2] != ctx.actor['owner'] or selected[2] != ctx.actor['owner'] or head[0].get('withdrawn'):
            _unavailable()
        value = selected[0]
        if value.get('templateId') != template_id or value.get('version') != version:
            _unavailable()
        snapshot = coedit.approved_in_transaction(ctx, db, value['draftId'], value['approvedRevision'])
        if snapshot != value['snapshot']:
            _unavailable()
        return value


def draft_template_receipt(ctx, request_id):
    models._id(request_id)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        rid = models._hash([ctx.sid, ctx.actor['owner'], request_id])
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (COEDIT_RECEIPT, rid, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _unavailable()
        value = json.loads(row['data'])
        return {'operation': {'requestId': request_id, 'state': 'committed'},
                'templateId': value['templateId'], 'version': value['version']}


def mutate_draft_template(ctx, body):
    from . import waves22_coedit as coedit
    if not isinstance(body, dict) or body.get('action') not in ('create', 'update', 'withdraw'):
        raise Phase10Error('invalid_request', 'Invalid template action.', 422)
    action = body['action']
    fields = {'action', 'requestId', 'expectedRevision'}
    if action != 'create': fields.add('templateId')
    if action != 'withdraw': fields.update(('draftId', 'approvedRevision'))
    models._fields(body, fields)
    req = models._id(body['requestId'])
    expected = models._integer(body['expectedRevision'], 0, 2147483647)
    fingerprint = models._hash(body)
    rid = models._hash([ctx.sid, ctx.actor.get('owner'), req])
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        db.execute('BEGIN IMMEDIATE')
        old = coedit._read(db, COEDIT_RECEIPT, ctx.sid, rid)
        if old:
            if old[2] != ctx.actor['owner'] or old[0]['fingerprint'] != fingerprint:
                raise Phase10Error('request_conflict', 'Request ID already used.', 409)
            return draft_template_receipt(ctx, req)
        if action == 'create':
            if expected != 0: raise Phase10Error('stale_revision', 'Template changed.', 409)
            tid, revision = store.ident(), 1
        else:
            tid = models._id(body['templateId'])
            head = coedit._read(db, COEDIT_TEMPLATE, ctx.sid, tid)
            if not head or head[2] != ctx.actor['owner']: _unavailable()
            if head[0].get('withdrawn') or head[1] != expected:
                raise Phase10Error('stale_revision', 'Template changed.', 409)
            revision = expected + 1
        if action != 'withdraw':
            snapshot = coedit.approved_in_transaction(ctx, db, body['draftId'], body['approvedRevision'])
            value = {'templateId': tid, 'version': revision, 'draftId': body['draftId'],
                     'approvedRevision': body['approvedRevision'], 'snapshot': snapshot}
            models._insert(db, COEDIT_VERSION, ctx.sid, ctx.actor['owner'], models._hash([tid, revision]), value)
        if action == 'create':
            models._insert(db, COEDIT_TEMPLATE, ctx.sid, ctx.actor['owner'], tid, {'withdrawn': False})
        else:
            db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=?',
                       (models._json({'withdrawn': action == 'withdraw'}), revision, COEDIT_TEMPLATE, tid, ctx.sid))
        models._insert(db, COEDIT_RECEIPT, ctx.sid, ctx.actor['owner'], rid,
                       {'fingerprint': fingerprint, 'templateId': tid, 'version': revision})
        db.commit()
        return {'operation': {'requestId': req, 'state': 'committed'}, 'templateId': tid, 'version': revision}


def apply_draft_template(ctx, template_id, version, draft_id, body):
    """Apply via coedit's durable patch receipt; never carry approval to the target."""
    from . import waves22_coedit as coedit
    models._fields(body, ('requestId', 'baseRevision'))
    with ctx.lock:
        value = draft_template(ctx, template_id, version)
        content = value['snapshot']['content']
        return coedit.apply_patch(ctx, draft_id, {'requestId': body['requestId'],
            'baseRevision': body['baseRevision'], 'operations': [
                {'field': 'title', 'value': content['title']}, {'field': 'body', 'value': content['body']}]})


def source_context(handler, source_sid):
    """Authenticate the separately supplied source-session capability on every use."""
    models._id(source_sid)
    token = handler.headers.get('X-Source-Capability', '')
    actor = store.auth(token) if token else None
    if not actor or actor.get('sid') != source_sid or actor.get('role') != 'creator':
        _unavailable()
    # The source credential is never substituted for the target credential.
    class SourceHandler:
        _auth_token = token
    ctx = coedit_auth.CoeditContext(SourceHandler(), source_sid, actor)
    ctx.check_actor()
    return ctx


def apply_cross_session_template(target_ctx, source_ctx, template_id, version, draft_id, body):
    """Apply an approved source template with two current session capabilities."""
    from . import waves22_coedit as coedit
    models._fields(body, ('requestId', 'baseRevision'))
    if target_ctx.sid == source_ctx.sid:
        raise Phase10Error('invalid_request', 'Choose a different source session.', 422)
    with target_ctx.lock:
        models._id(body['requestId']); models._integer(body['baseRevision'], 0, 2147483647)
        models._id(draft_id)
        with store.connect() as db:
            _creator(target_ctx, db)
        value = draft_template(source_ctx, template_id, version)
        content = value['snapshot']['content']
        binding = {'sourceSid': source_ctx.sid, 'sourceOwner': source_ctx.actor['owner'],
                   'templateId': template_id, 'version': version, 'draftId': draft_id,
                   'baseRevision': body['baseRevision']}
        rid = models._hash([target_ctx.sid, target_ctx.actor['owner'], body['requestId']])
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            coedit._get(db, target_ctx, draft_id, 'edit')
            existing = coedit._read(db, CROSS_INTENT, target_ctx.sid, rid)
            if existing:
                if existing[2] != target_ctx.actor['owner'] or {k: v for k, v in existing[0].items() if k != 'effectId'} != binding:
                    raise Phase10Error('request_conflict', 'Request ID already used.', 409)
                effect_id = existing[0]['effectId']
            else:
                effect_id = store.ident()
                models._insert(db, CROSS_INTENT, target_ctx.sid, target_ctx.actor['owner'], rid, dict(binding, effectId=effect_id))
            db.commit()
        return coedit.apply_patch(target_ctx, draft_id, {'requestId': effect_id,
            'baseRevision': body['baseRevision'], 'operations': [
                {'field': 'title', 'value': content['title']}, {'field': 'body', 'value': content['body']}]})


def recover_cross_session_application(target_ctx, source_ctx, template_id, version, draft_id, body):
    """Recover only the exact target receipt, without requiring current source approval."""
    from . import waves22_coedit as coedit
    models._fields(body, ('requestId', 'baseRevision'))
    models._id(template_id); models._integer(version, 1, 2147483647)
    models._id(draft_id); models._id(body['requestId'])
    models._integer(body['baseRevision'], 0, 2147483647)
    if target_ctx.sid == source_ctx.sid:
        raise Phase10Error('invalid_request', 'Choose a different source session.', 422)
    with target_ctx.lock, store.connect() as db:
        _creator(target_ctx, db)
        _creator(source_ctx, db)
        coedit._get(db, target_ctx, draft_id, 'read')
        rid = models._hash([target_ctx.sid, target_ctx.actor['owner'], body['requestId']])
        intent = coedit._read(db, CROSS_INTENT, target_ctx.sid, rid)
        expected = {'sourceSid': source_ctx.sid, 'sourceOwner': source_ctx.actor['owner'],
                    'templateId': template_id, 'version': version, 'draftId': draft_id,
                    'baseRevision': body['baseRevision']}
        if not intent or intent[2] != target_ctx.actor['owner'] or {k: v for k, v in intent[0].items() if k != 'effectId'} != expected:
            _unavailable()
        row = coedit._read(db, COEDIT_VERSION, source_ctx.sid, models._hash([template_id, version]))
        if not row or row[2] != source_ctx.actor['owner'] or row[0].get('templateId') != template_id or row[0].get('version') != version:
            _unavailable()
        content = row[0]['snapshot']['content']
        patch = {'requestId': intent[0]['effectId'], 'baseRevision': body['baseRevision'], 'operations': [
            {'field': 'title', 'value': content['title']}, {'field': 'body', 'value': content['body']}]}
        _, old = coedit._receipt(db, target_ctx, intent[0]['effectId'], coedit._hash(['patch', draft_id, patch]))
        if not old:
            return {'operation': {'state': 'not_committed'}}
        result = old['result']
        return {'operation': {'state': result['state'], **({'revision': result['revision']} if result['state'] == 'committed' else {'currentRevision': result['currentRevision']})}}


def recover_template_application(ctx, template_id, version, draft_id, body):
    """Match the original patch fingerprint without relying on current source approval."""
    from . import waves22_coedit as coedit
    models._fields(body, ('requestId', 'baseRevision'))
    models._id(template_id); models._integer(version, 1, 2147483647)
    models._id(draft_id); models._id(body['requestId'])
    models._integer(body['baseRevision'], 0, 2147483647)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        coedit._get(db, ctx, draft_id, 'read')
        row = coedit._read(db, COEDIT_VERSION, ctx.sid, models._hash([template_id, version]))
        if not row or row[2] != ctx.actor['owner'] or row[0].get('templateId') != template_id or row[0].get('version') != version:
            _unavailable()
        content = row[0]['snapshot']['content']
        patch = {'requestId': body['requestId'], 'baseRevision': body['baseRevision'], 'operations': [
            {'field': 'title', 'value': content['title']}, {'field': 'body', 'value': content['body']}]}
        _, old = coedit._receipt(db, ctx, body['requestId'], coedit._hash(['patch', draft_id, patch]))
        if not old:
            _unavailable()
        # Conflict receipts contain submitted text, so never disclose them after source loss.
        result = old['result']
        return {'operation': {'state': result['state'], **({'revision': result['revision']} if result['state'] == 'committed' else {'currentRevision': result['currentRevision']})}}


def _reasons(db, ctx, references):
    if not isinstance(references, list) or len(references) > 50:
        raise Phase10Error('invalid_request', 'Invalid reasons.', 422)
    seen, result = set(), []
    for ref in references:
        models._fields(ref, ('id', 'revision'))
        oid = models._id(ref['id'])
        revision = models._integer(ref['revision'], 1, 2147483647)
        if oid in seen:
            raise Phase10Error('invalid_request', 'Duplicate reason.', 422)
        seen.add(oid)
        row = db.execute('SELECT data,revision FROM objects WHERE kind=? AND id=? AND session_id=?',
                         ('w14reason', oid, ctx.sid)).fetchone()
        if not row or row['revision'] != revision:
            raise Phase10Error('stale_context', 'Reason changed.', 409)
        value = json.loads(row['data'])
        if value.get('status') == 'withdrawn' or not isinstance(value.get('text'), str):
            raise Phase10Error('stale_context', 'Reason unavailable.', 409)
        result.append({'id': oid, 'revision': revision, 'text': value['text'],
                       'corrections': value.get('corrections', [])})
    return result


def reviewed_record(ctx, record_id):
    models._id(record_id)
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') not in ('creator', 'viewer'):
            _unavailable()
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (REVIEWED_RECORD, record_id, ctx.sid)).fetchone()
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
        if not row or not session or row['owner_id'] != session['owner_id']:
            _unavailable()
        value = json.loads(row['data'])
        if value.get('withdrawn') or value.get('reasonBinding') != 2: _unavailable()
        activity = read_version(ctx, value['activityId'], value['activityRevision'])
        if activity['definition'] != value['definition'] or activity['approvalId'] != value['approvalId']:
            _unavailable()
        reasons = _reasons(db, ctx, value['reasonRefs'])
        eligible = _eligible_reason_refs(db, ctx, value['activityId'], value['activityRevision'])
        if any(ref not in eligible for ref in value['reasonRefs']):
            raise Phase10Error('stale_context', 'Reason consent changed.', 409)
        if _reason_consents(db, ctx, value['activityId'], value['activityRevision'], value['reasonRefs']) != value.get('reasonConsents'):
            raise Phase10Error('stale_context', 'Reason consent changed.', 409)
        return {'recordId': record_id, 'activityId': value['activityId'], 'activityRevision': value['activityRevision'],
                'definition': value['definition'], 'reasons': reasons, 'review': value['review']}


def reviewed_record_reference(ctx, record_id, revision):
    """Resolve a reviewed record for a consumer, with live rights and consent.

    Record content is immutable at revision 1; withdrawal invalidates it rather
    than producing a new readable revision. Consumers must repeat this reader
    at their own final-delivery boundary while holding the shared store lock.
    """
    models._integer(revision, 1, 2147483647)
    if revision != 1:
        _unavailable()
    return reviewed_record(ctx, record_id)


def record_receipt(ctx, request_id):
    models._id(request_id)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        rid = models._hash([ctx.sid, ctx.actor['owner'], request_id])
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (RECORD_RECEIPT, rid, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']: _unavailable()
        value = json.loads(row['data'])
        return {'operation': {'requestId': request_id, 'state': 'committed'}, 'recordId': value['recordId']}


def save_reviewed_record(ctx, body):
    models._fields(body, ('requestId', 'activityId', 'activityRevision', 'reasonRefs', 'review'))
    req = models._id(body['requestId'])
    if not isinstance(body['review'], str) or not 1 <= len(body['review'].strip()) <= 4000:
        raise Phase10Error('invalid_request', 'Enter a review.', 422)
    fingerprint = models._hash(body)
    rid = models._hash([ctx.sid, ctx.actor.get('owner'), req])
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (RECORD_RECEIPT, rid, ctx.sid)).fetchone()
        if row:
            value = json.loads(row['data'])
            if row['owner_id'] != ctx.actor['owner'] or value['fingerprint'] != fingerprint:
                raise Phase10Error('request_conflict', 'Request ID already used.', 409)
            return record_receipt(ctx, req)
        activity = read_version(ctx, body['activityId'], body['activityRevision'])
        _reasons(db, ctx, body['reasonRefs'])
        if sorted(body['reasonRefs'], key=lambda ref: ref['id']) != _eligible_reason_refs(db, ctx, body['activityId'], body['activityRevision']):
            raise Phase10Error('stale_context', 'Review all currently linked reasons.', 409)
        oid = store.ident()
        value = {'withdrawn': False, 'activityId': activity['activityId'], 'activityRevision': activity['revision'],
                 'approvalId': activity['approvalId'], 'definition': activity['definition'],
                 'reasonRefs': body['reasonRefs'], 'reasonBinding': 2,
                 'reasonConsents': _reason_consents(db, ctx, body['activityId'], body['activityRevision'], body['reasonRefs']),
                 'review': body['review'].strip()}
        models._insert(db, REVIEWED_RECORD, ctx.sid, ctx.actor['owner'], oid, value)
        models._insert(db, RECORD_RECEIPT, ctx.sid, ctx.actor['owner'], rid, {'fingerprint': fingerprint, 'recordId': oid})
        db.commit()
        return {'operation': {'requestId': req, 'state': 'committed'}, 'recordId': oid}


def withdraw_record(ctx, record_id, body):
    models._fields(body, ('requestId', 'expectedRevision'))
    req = models._id(body['requestId']); models._id(record_id)
    expected = models._integer(body['expectedRevision'], 1, 2147483647)
    fingerprint = models._hash(['withdraw', record_id, body])
    rid = models._hash([ctx.sid, ctx.actor.get('owner'), req])
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (RECORD_RECEIPT, rid, ctx.sid)).fetchone()
        if old:
            value = json.loads(old['data'])
            if old['owner_id'] != ctx.actor['owner'] or value['fingerprint'] != fingerprint:
                raise Phase10Error('request_conflict', 'Request ID already used.', 409)
            return record_receipt(ctx, req)
        row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (REVIEWED_RECORD, record_id, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']: _unavailable()
        if row['revision'] != expected or json.loads(row['data']).get('withdrawn'):
            raise Phase10Error('stale_revision', 'Record changed.', 409)
        db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=?',
                   (models._json({'withdrawn': True}), expected + 1, REVIEWED_RECORD, record_id, ctx.sid))
        models._insert(db, RECORD_RECEIPT, ctx.sid, ctx.actor['owner'], rid,
                       {'fingerprint': fingerprint, 'recordId': record_id})
        db.commit()
        return {'operation': {'requestId': req, 'state': 'committed'}, 'recordId': record_id}


def editorial_template(ctx, template_id, version):
    """Resolve a saved exact activity definition and its live source rights."""
    models._id(template_id)
    models._integer(version, 1, 2147483647)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (EDITORIAL_TEMPLATE, template_id, ctx.sid)).fetchone()
        selected = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                              (EDITORIAL_VERSION, models._hash([template_id, version]), ctx.sid)).fetchone()
        if not row or not selected or row['owner_id'] != ctx.actor['owner'] or selected['owner_id'] != ctx.actor['owner']:
            _unavailable()
        head, value = json.loads(row['data']), json.loads(selected['data'])
        if head.get('withdrawn') or value.get('templateId') != template_id or value.get('version') != version:
            _unavailable()
        activity = read_version(ctx, value['activityId'], value['activityRevision'])
        if activity['definition'] != value['definition'] or activity['approvalId'] != value['approvalId']:
            _unavailable()
        return value


def editorial_receipt(ctx, request_id):
    models._id(request_id)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        rid = models._hash([ctx.sid, ctx.actor['owner'], request_id])
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (EDITORIAL_RECEIPT, rid, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _unavailable()
        value = json.loads(row['data'])
        head = db.execute('SELECT revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                          (EDITORIAL_TEMPLATE, value['templateId'], ctx.sid)).fetchone()
        if not head or head['owner_id'] != ctx.actor['owner']:
            _unavailable()
        return {'operation': {'requestId': request_id, 'state': 'committed'},
                'templateId': value['templateId'], 'version': value['version'], 'currentRevision': head['revision']}


def mutate_editorial_template(ctx, body):
    """Save a versioned exact approved activity reference with idempotent recovery."""
    if not isinstance(body, dict) or body.get('action') not in ('create', 'update', 'withdraw'):
        raise Phase10Error('invalid_request', 'Invalid template action.', 422)
    action = body['action']
    fields = {'action', 'requestId', 'expectedRevision'}
    if action != 'create': fields.add('templateId')
    if action != 'withdraw': fields.update(('activityId', 'activityRevision'))
    models._fields(body, fields)
    req = models._id(body['requestId'])
    expected = models._integer(body['expectedRevision'], 0, 2147483647)
    fingerprint = models._hash(body)
    rid = models._hash([ctx.sid, ctx.actor.get('owner'), req])
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (EDITORIAL_RECEIPT, rid, ctx.sid)).fetchone()
        if old:
            saved = json.loads(old['data'])
            if old['owner_id'] != ctx.actor['owner'] or saved['fingerprint'] != fingerprint:
                raise Phase10Error('request_conflict', 'Request ID already used.', 409)
            return editorial_receipt(ctx, req)
        if action == 'create':
            if expected != 0: raise Phase10Error('stale_revision', 'Template changed.', 409)
            tid, revision = store.ident(), 1
        else:
            tid = models._id(body['templateId'])
            row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                             (EDITORIAL_TEMPLATE, tid, ctx.sid)).fetchone()
            if not row or row['owner_id'] != ctx.actor['owner']: _unavailable()
            if json.loads(row['data']).get('withdrawn') or row['revision'] != expected:
                raise Phase10Error('stale_revision', 'Template changed.', 409)
            revision = expected + 1
        if action != 'withdraw':
            activity = read_version(ctx, body['activityId'], body['activityRevision'])
            value = {'templateId': tid, 'version': revision, 'activityId': activity['activityId'],
                     'activityRevision': activity['revision'], 'approvalId': activity['approvalId'],
                     'definition': activity['definition']}
            models._insert(db, EDITORIAL_VERSION, ctx.sid, ctx.actor['owner'], models._hash([tid, revision]), value)
        head = {'withdrawn': action == 'withdraw'}
        if action == 'create':
            models._insert(db, EDITORIAL_TEMPLATE, ctx.sid, ctx.actor['owner'], tid, head)
        else:
            db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=?',
                       (models._json(head), revision, EDITORIAL_TEMPLATE, tid, ctx.sid))
        models._insert(db, EDITORIAL_RECEIPT, ctx.sid, ctx.actor['owner'], rid,
                       {'fingerprint': fingerprint, 'templateId': tid, 'version': revision})
        db.commit()
        return {'operation': {'requestId': req, 'state': 'committed'}, 'templateId': tid,
                'version': revision, 'currentRevision': revision}


def _unavailable():
    raise Phase10Error('not_found', 'Activity unavailable.', 404)


def _creator(ctx, db):
    ctx.check_actor()
    row = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
    if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') != 'creator' or not row or row['owner_id'] != ctx.actor.get('owner'):
        _unavailable()


def _approval(ctx, approval_id):
    models._id(approval_id)
    matches = [a for a in model_auth.list_approvals(ctx)['approvals'] if a['approvalId'] == approval_id]
    if len(matches) != 1:
        _unavailable()
    return matches[0]['definition']


def _load(db, ctx, activity_id):
    row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (ACTIVITY, models._id(activity_id), ctx.sid)).fetchone()
    if not row:
        _unavailable()
    return json.loads(row['data']), row['revision'], row['owner_id']


def read(ctx, activity_id):
    """Return only a current, source-authorized creator-approved definition."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') not in ('creator', 'viewer'):
            _unavailable()
        value, revision, owner = _load(db, ctx, activity_id)
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
        if not session or owner != session['owner_id'] or value.get('withdrawn'):
            _unavailable()
        definition = _approval(ctx, value['approvalId'])
        if definition != value['definition']:
            _unavailable()
        return {'activityId': activity_id, 'revision': revision, 'approvalId': value['approvalId'], 'definition': definition, 'units': definition['spec']['units']}


def read_version(ctx, activity_id, revision):
    """Read an immutable version while the activity and exact approval remain live."""
    models._id(activity_id)
    models._integer(revision, 1, 2147483647)
    with ctx.lock, store.connect() as db:
        read(ctx, activity_id)
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (VERSION, models._hash([activity_id, revision]), ctx.sid)).fetchone()
        if not row:
            _unavailable()
        value = json.loads(row['data'])
        current, _, owner = _load(db, ctx, activity_id)
        if row['owner_id'] != owner or value.get('activityId') != activity_id or value.get('revision') != revision:
            _unavailable()
        definition = _approval(ctx, value['approvalId'])
        if definition != value['definition']:
            _unavailable()
        return {'activityId': activity_id, 'revision': revision, 'approvalId': value['approvalId'], 'definition': definition, 'units': definition['spec']['units']}


def activity_reference(ctx, activity_id, revision):
    """Resolve an exact activity reference with current source and approval rights.

    Consumers must repeat this read under the common lock at their delivery
    boundary; the returned projection is not an independent grant.
    """
    return read_version(ctx, activity_id, revision)


def template_reference(ctx, template_id, version):
    """Resolve an existing creator-owned template version under current rights."""
    from . import waves17_templates as templates
    models._id(template_id)
    models._integer(version, 1, 2147483647)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        row = db.execute('SELECT owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (templates.T, template_id, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _unavailable()
        version_row = db.execute('SELECT owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                                 (templates.V, template_id + ':' + str(version), ctx.sid)).fetchone()
        if not version_row or version_row['owner_id'] != ctx.actor['owner']:
            _unavailable()
        template = templates.template(template_id, ctx.actor)
        selected = templates.version(template, version)
        if selected.get('templateId') != template_id or selected.get('version') != version:
            _unavailable()
        return selected


def mutate(ctx, body):
    """Creator configuration and exact actor-scoped committed request receipt."""
    if not isinstance(body, dict) or body.get('action') not in ('create', 'update', 'withdraw'):
        raise Phase10Error('invalid_request', 'Invalid action.', 422)
    action = body['action']
    fields = {'action', 'requestId', 'expectedRevision'}
    if action != 'create': fields.add('activityId')
    if action != 'withdraw': fields.add('approvalId')
    models._fields(body, fields)
    req = models._id(body['requestId'])
    expected = models._integer(body['expectedRevision'], 0, 2147483647)
    fingerprint = models._hash(body)
    rid = models._hash([ctx.sid, ctx.actor.get('owner'), req])
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (RECEIPT, rid, ctx.sid)).fetchone()
        if row:
            receipt = json.loads(row['data'])
            if row['owner_id'] != ctx.actor['owner'] or receipt['fingerprint'] != fingerprint:
                raise Phase10Error('request_conflict', 'Request ID already used.', 409)
            return _receipt(ctx, db, req, receipt)
        if action == 'create':
            if expected != 0:
                raise Phase10Error('stale_revision', 'Activity changed.', 409)
            activity_id, revision = store.ident(), 1
        else:
            activity_id = models._id(body['activityId'])
            previous, old_revision, owner = _load(db, ctx, activity_id)
            if owner != ctx.actor['owner']:
                _unavailable()
            if previous['withdrawn'] or old_revision != expected:
                raise Phase10Error('stale_revision', 'Activity changed.', 409)
            revision = old_revision + 1
        if action == 'withdraw':
            value = {'withdrawn': True}
        else:
            definition = _approval(ctx, body['approvalId'])
            value = {'withdrawn': False, 'approvalId': body['approvalId'], 'definition': definition}
        if action == 'create':
            models._insert(db, ACTIVITY, ctx.sid, ctx.actor['owner'], activity_id, value)
        else:
            db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=?', (models._json(value), revision, ACTIVITY, activity_id, ctx.sid))
        if action != 'withdraw':
            models._insert(db, VERSION, ctx.sid, ctx.actor['owner'], models._hash([activity_id, revision]), {'activityId': activity_id, 'revision': revision, 'approvalId': value['approvalId'], 'definition': value['definition']})
        models._insert(db, RECEIPT, ctx.sid, ctx.actor['owner'], rid, {'fingerprint': fingerprint, 'activityId': activity_id, 'revision': revision})
        db.commit()
        return {'operation': {'requestId': req, 'state': 'committed'}, 'activityId': activity_id, 'revision': revision, 'currentRevision': revision}


def _receipt(ctx, db, request_id, receipt):
    _, revision, owner = _load(db, ctx, receipt['activityId'])
    if owner != ctx.actor['owner']:
        _unavailable()
    return {'operation': {'requestId': request_id, 'state': 'committed'}, 'activityId': receipt['activityId'], 'revision': receipt['revision'], 'currentRevision': revision}


def receipt(ctx, request_id):
    models._id(request_id)
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        rid = models._hash([ctx.sid, ctx.actor['owner'], request_id])
        row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (RECEIPT, rid, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _unavailable()
        return _receipt(ctx, db, request_id, json.loads(row['data']))


def demonstrate(ctx, activity_id, revision, parameters):
    """Evaluate the fixed rule without creating or publishing a private attempt."""
    activity = read(ctx, activity_id)
    if type(revision) is not int or revision != activity['revision']:
        raise Phase10Error('stale_revision', 'Activity changed.', 409)
    return {'activityId': activity_id, 'revision': revision,
            'result': models.evaluate(activity['definition'], parameters), 'units': activity['units']}


def shared_results(ctx, activity_id, revision):
    """Creator review of currently consented results matching the exact definition.

    This is a model-definition match, not proof that an attempt belongs to a
    particular activity. The model service controls disclosure and identity.
    """
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        activity = read_version(ctx, activity_id, revision)
        model_ctx = model_auth.ModelContext(ctx.handler, ctx.sid, ctx.actor,
                                            credential_digest=ctx._credential_digest)
        shares = models.list_shares(model_ctx)['shares']
        return {'activityId': activity_id, 'revision': revision,
                'shares': [item for item in shares if item['definition'] == activity['definition']]}


def handoff(ctx, draft_id, body):
    """Use the existing durable adoption intent and exact current approval checks."""
    models._fields(body, ('requestId', 'approvedRevision', 'segmentId'))
    models._id(body['segmentId'])
    # Verify the approved segment before invoking the existing side-effecting adoption.
    from . import waves22_coedit as coedit
    with ctx.lock:
        models._id(body['requestId'])
        rid = coedit._hash(['w22adoption', ctx.sid, ctx.actor.get('owner'), body['requestId']])
        with store.connect() as db:
            existing = coedit._read(db, adoption.KIND, ctx.sid, rid)
        snapshot = existing[0]['snapshot'] if existing else coedit.approved_for_adoption(ctx, draft_id, body['approvedRevision'])
        if snapshot['segmentId'] != body['segmentId']:
            raise Phase10Error('stale_context', 'Approved segment changed.', 409)
        result, rid = adoption.adopt(ctx, draft_id, {'requestId': body['requestId'], 'expectedRevision': body['approvedRevision']})
        result['operatorReference'] = {'segmentId': snapshot['segmentId'],
                                       'materialId': result['operation']['materialId'],
                                       'materialVersion': result['operation']['materialVersion']}
        return result, rid


def recover_handoff(ctx, draft_id, body):
    """Inspect the exact adoption intent without invoking Studio or disclosing its snapshot."""
    from . import waves22_coedit as coedit
    models._fields(body, ('requestId', 'approvedRevision', 'segmentId'))
    coedit._id(draft_id); coedit._id(body['requestId']); coedit._revision(body['approvedRevision'])
    models._id(body['segmentId'])
    rid = coedit._hash(['w22adoption', ctx.sid, ctx.actor.get('owner'), body['requestId']])
    with ctx.lock, store.connect() as db:
        _creator(ctx, db)
        row = coedit._read(db, adoption.KIND, ctx.sid, rid)
        if not row:
            _unavailable()
        rec, _, owner = row
        snapshot = rec['snapshot']
        if (owner != ctx.actor['owner'] or rec.get('draftId') != draft_id
                or rec.get('revision') != body['approvedRevision']
                or snapshot.get('segmentId') != body['segmentId']):
            raise Phase10Error('request_conflict', 'Request ID already used.', 409)
        material = coedit._read(db, 'p10material', ctx.sid, snapshot['materialId'])
        state = 'indeterminate'
        if material and material[2] == owner and material[0].get('w22Adoption') == rid:
            value = material[0]
            if value.get('currentVersion') == snapshot['baseMaterialVersion']:
                state = 'pending'
            elif (value.get('currentVersion') == snapshot['baseMaterialVersion'] + 1
                  and value.get('title') == snapshot['content']['title'].strip()
                  and value.get('body') == snapshot['content']['body'].strip()):
                state = 'committed'
        return {'operation': {'requestId': body['requestId'], 'state': state}}


def _same(actual, expected):
    if actual != expected:
        raise Phase10Error('stale_context', 'Activity changed before delivery.', 409)


def handle(handler, sid, actor, method, parts):
    """Route seam; PRIMARY must mount it and fence final delivery."""
    ctx = Context(handler, sid, actor)
    if actor.get('sid') != sid:
        _unavailable()
    if parts == ['activity-reasons'] and method == 'POST':
        body = handler.body(); result = link_reason(ctx, body)
        def guard_reason_link():
            with ctx.lock, store.connect() as db:
                ctx.check_actor()
                read_version(ctx, body['activityId'], body['activityRevision'])
                if {'id': body['reasonId'], 'revision': body['reasonRevision']} not in _eligible_reason_refs(db, ctx, body['activityId'], body['activityRevision']):
                    _unavailable()
        handler._w24_activity_final = guard_reason_link
        return 200, result
    if parts == ['activity-reasons', 'withdraw'] and method == 'POST':
        body = handler.body(); result = unlink_reason(ctx, body)
        def guard_reason_unlink():
            with ctx.lock, store.connect() as db:
                ctx.check_actor()
                oid = models._hash([ctx.sid, body['activityId'], body['activityRevision'], body['reasonId']])
                if db.execute('SELECT 1 FROM objects WHERE kind=? AND id=? AND session_id=?',
                              (REASON_LINK, oid, ctx.sid)).fetchone():
                    raise Phase10Error('stale_context', 'Reason consent changed.', 409)
        handler._w24_activity_final = guard_reason_unlink
        return 200, result
    if len(parts) == 5 and parts[0] == 'activities' and parts[2] == 'versions' and parts[4] == 'reasons' and method == 'GET':
        raw = parts[3]
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        result = activity_reasons(ctx, parts[1], int(raw))
        handler._w24_activity_final = lambda: _same(activity_reasons(ctx, parts[1], int(raw)), result)
        return 200, result
    if (len(parts) == 8 and parts[0] == 'source-sessions' and parts[2] == 'draft-templates'
            and parts[4] == 'versions' and parts[6] in ('apply', 'recover-apply') and method == 'POST'):
        raw = parts[5]
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        cctx = coedit_auth.CoeditContext(handler, sid, actor)
        sctx = source_context(handler, parts[1])
        body = handler.body()
        if parts[6] == 'apply':
            result = apply_cross_session_template(cctx, sctx, parts[3], int(raw), parts[7], body)
            def guard_cross_apply():
                from . import waves22_coedit as coedit
                current_source = source_context(handler, parts[1])
                draft_template(current_source, parts[3], int(raw))
                current = coedit.open_draft(cctx, parts[7])['draft']
                _same((current['revision'], current['content']), (result['draft']['revision'], result['draft']['content']))
            handler._w24_activity_final = guard_cross_apply
        else:
            result = recover_cross_session_application(cctx, sctx, parts[3], int(raw), parts[7], body)
            handler._w24_activity_final = lambda: _same(recover_cross_session_application(
                cctx, source_context(handler, parts[1]), parts[3], int(raw), parts[7], body), result)
        return 200, result
    if parts == ['draft-templates'] and method == 'POST':
        cctx = coedit_auth.CoeditContext(handler, sid, actor)
        body = handler.body(); result = mutate_draft_template(cctx, body)
        handler._w24_activity_final = lambda: _same(draft_template_receipt(cctx, body['requestId']), result)
        return 200, result
    if len(parts) == 3 and parts[:2] == ['draft-templates', 'operations'] and method == 'GET':
        result = draft_template_receipt(ctx, parts[2])
        handler._w24_activity_final = lambda: _same(draft_template_receipt(ctx, parts[2]), result)
        return 200, result
    if len(parts) == 4 and parts[0] == 'draft-templates' and parts[2] == 'versions' and method == 'GET':
        raw = parts[3]
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        cctx = coedit_auth.CoeditContext(handler, sid, actor)
        result = draft_template(cctx, parts[1], int(raw))
        handler._w24_activity_final = lambda: _same(draft_template(cctx, parts[1], int(raw)), result)
        return 200, result
    if len(parts) == 6 and parts[0] == 'draft-templates' and parts[2] == 'versions' and parts[4] == 'apply' and method == 'POST':
        raw = parts[3]
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        cctx = coedit_auth.CoeditContext(handler, sid, actor)
        body = handler.body(); result = apply_draft_template(cctx, parts[1], int(raw), parts[5], body)
        def guard_apply():
            from . import waves22_coedit as coedit
            draft_template(cctx, parts[1], int(raw))
            current = coedit.open_draft(cctx, parts[5])['draft']
            _same((current['revision'], current['content']), (result['draft']['revision'], result['draft']['content']))
        handler._w24_activity_final = guard_apply
        return 200, result
    if len(parts) == 6 and parts[0] == 'draft-templates' and parts[2] == 'versions' and parts[4] == 'recover-apply' and method == 'POST':
        raw = parts[3]
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        cctx = coedit_auth.CoeditContext(handler, sid, actor)
        body = handler.body(); result = recover_template_application(cctx, parts[1], int(raw), parts[5], body)
        handler._w24_activity_final = lambda: _same(recover_template_application(cctx, parts[1], int(raw), parts[5], body), result)
        return 200, result
    if parts == ['activity-records'] and method == 'POST':
        body = handler.body(); result = save_reviewed_record(ctx, body)
        handler._w24_activity_final = lambda: _same(record_receipt(ctx, body['requestId']), result)
        return 200, result
    if len(parts) == 3 and parts[:2] == ['activity-records', 'operations'] and method == 'GET':
        result = record_receipt(ctx, parts[2])
        handler._w24_activity_final = lambda: _same(record_receipt(ctx, parts[2]), result)
        return 200, result
    if len(parts) == 2 and parts[0] == 'activity-records' and method == 'GET':
        result = reviewed_record(ctx, parts[1])
        handler._w24_activity_final = lambda: _same(reviewed_record(ctx, parts[1]), result)
        return 200, result
    if len(parts) == 3 and parts[0] == 'activity-records' and parts[2] == 'withdraw' and method == 'POST':
        body = handler.body(); result = withdraw_record(ctx, parts[1], body)
        handler._w24_activity_final = lambda: _same(record_receipt(ctx, body['requestId']), result)
        return 200, result
    if parts == ['editorial-templates'] and method == 'POST':
        body = handler.body(); result = mutate_editorial_template(ctx, body)
        handler._w24_activity_final = lambda: _same(editorial_receipt(ctx, body['requestId']), result)
        return 200, result
    if len(parts) == 3 and parts[:2] == ['editorial-templates', 'operations'] and method == 'GET':
        result = editorial_receipt(ctx, parts[2])
        handler._w24_activity_final = lambda: _same(editorial_receipt(ctx, parts[2]), result)
        return 200, result
    if len(parts) == 4 and parts[0] == 'editorial-templates' and parts[2] == 'versions' and method == 'GET':
        version = parts[3]
        if not isinstance(version, str) or not version.isascii() or not version.isdecimal() or len(version) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        result = editorial_template(ctx, parts[1], int(version))
        handler._w24_activity_final = lambda: _same(editorial_template(ctx, parts[1], int(version)), result)
        return 200, result
    if parts == ['activities'] and method == 'POST':
        body = handler.body(); result = mutate(ctx, body)
        handler._w24_activity_final = lambda: _same(receipt(ctx, body['requestId']), result)
        return 200, result
    if len(parts) == 2 and parts[0] == 'activities' and method == 'GET':
        result = read(ctx, parts[1])
        handler._w24_activity_final = lambda: _same(read(ctx, parts[1]), result)
        return 200, result
    if len(parts) == 3 and parts[:2] == ['activities', 'operations'] and method == 'GET':
        result = receipt(ctx, parts[2])
        handler._w24_activity_final = lambda: _same(receipt(ctx, parts[2]), result)
        return 200, result
    if len(parts) == 4 and parts[0] == 'activities' and parts[2] == 'versions' and method == 'GET':
        version = parts[3]
        if not isinstance(version, str) or not version.isascii() or not version.isdecimal() or len(version) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        result = read_version(ctx, parts[1], int(version))
        handler._w24_activity_final = lambda: _same(read_version(ctx, parts[1], int(version)), result)
        return 200, result
    if len(parts) == 3 and parts[0] == 'activities' and parts[2] == 'demonstrate' and method == 'POST':
        body = handler.body(); models._fields(body, ('revision', 'parameters'))
        result = demonstrate(ctx, parts[1], body['revision'], body['parameters'])
        handler._w24_activity_final = lambda: _same(demonstrate(ctx, parts[1], body['revision'], body['parameters']), result)
        return 200, result
    if len(parts) == 5 and parts[0] == 'activities' and parts[2] == 'versions' and parts[4] == 'shares' and method == 'GET':
        version = parts[3]
        if not isinstance(version, str) or not version.isascii() or not version.isdecimal() or len(version) > 10:
            raise Phase10Error('invalid_request', 'Invalid revision.', 422)
        result = shared_results(ctx, parts[1], int(version))
        handler._w24_activity_final = lambda: _same(shared_results(ctx, parts[1], int(version)), result)
        return 200, result
    if len(parts) == 3 and parts[0] == 'handoffs' and parts[2] == 'adopt' and method == 'POST':
        cctx = coedit_auth.CoeditContext(handler, sid, actor)
        result, rid = handoff(cctx, parts[1], handler.body())
        handler._w24_activity_final = lambda: adoption.guard(cctx, result, rid)
        return 200, result
    if len(parts) == 3 and parts[0] == 'handoffs' and parts[2] == 'recover' and method == 'POST':
        body = handler.body(); result = recover_handoff(ctx, parts[1], body)
        handler._w24_activity_final = lambda: _same(recover_handoff(ctx, parts[1], body), result)
        return 200, result
    _unavailable()


def final_guard(handler):
    """PRIMARY holds store.LOCK from this call through serialization and send."""
    guard = getattr(handler, '_w24_activity_final', None)
    if not callable(guard):
        _unavailable()
    guard()


def cleanup_db(db, sid, owner=None):
    if not db.in_transaction:
        raise ValueError('cleanup requires caller transaction')
    for kind in (ACTIVITY, VERSION, RECEIPT, EDITORIAL_TEMPLATE, EDITORIAL_VERSION, EDITORIAL_RECEIPT, REVIEWED_RECORD, RECORD_RECEIPT, COEDIT_TEMPLATE, COEDIT_VERSION, COEDIT_RECEIPT, REASON_LINK, CROSS_INTENT):
        if owner is None:
            db.execute('DELETE FROM objects WHERE kind=? AND session_id=?', (kind, sid))
        else:
            db.execute('DELETE FROM objects WHERE kind=? AND session_id=? AND owner_id=?', (kind, sid, owner))
