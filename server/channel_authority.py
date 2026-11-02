"""Persistent channel membership and explicitly approved archive primitives."""

import hashlib
import hmac
import json
import re
import secrets

from . import store
from .phase10_common import Phase10Error, parse_ref


def _error(code='not_found', message='Channel unavailable.', status=404):
    raise Phase10Error(code, message, status)


def _creator(ctx):
    ctx.check_actor()
    with store.connect() as db:
        row = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
    if (ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') != 'creator'
            or not row or row['owner_id'] != ctx.actor.get('owner')):
        _error()


def _member_id(channel_id, sid):
    return hashlib.sha256(json.dumps([channel_id, sid], separators=(',', ':')).encode()).hexdigest()


def _insert(db, kind, oid, sid, owner, value):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
               (kind, oid, sid, owner, json.dumps(value, sort_keys=True, separators=(',', ':')), store.now()))


def _channel(db, channel_id):
    if not isinstance(channel_id, str) or len(channel_id) != 32 or any(c not in '0123456789abcdef' for c in channel_id):
        _error()
    row = db.execute("SELECT data,revision FROM objects WHERE kind='w24channel' AND id=?", (channel_id,)).fetchone()
    if not row:
        _error()
    value = json.loads(row['data'])
    if value.get('revoked'):
        _error()
    return value, row['revision']


def _membership(db, channel_id, sid):
    row = db.execute("SELECT data FROM objects WHERE kind='w24channelmember' AND id=? AND session_id=?", (_member_id(channel_id, sid), sid)).fetchone()
    value = json.loads(row['data']) if row else None
    return bool(value and value.get('channelId') == channel_id and value.get('active') is True)


def require_member(ctx, channel_id, creator=False):
    """Recheck current credential, active target session, channel and membership."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') not in ('creator', 'viewer'):
            _error()
        if creator:
            _creator(ctx)
        _channel(db, channel_id)
        if not _membership(db, channel_id, ctx.sid):
            _error()


def status(ctx, channel_id):
    """Show current creator membership and channel revision without its verifier."""
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        _, revision = _channel(db, channel_id)
        if not _membership(db, channel_id, ctx.sid):
            _error()
        return {'channelId': channel_id, 'revision': revision, 'enrolled': True}


def capability_operation(ctx, request_id, action, channel_id=None, expected_revision=None):
    """Atomically create or rotate a capability with secret-free exact recovery.

    A replay returns committed metadata, never the once-disclosed capability.
    If disclosure was lost, a member creator can intentionally rotate it.
    """
    if (not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request_id)
            or action not in ('create', 'rotate')):
        _error('invalid_request', 'Invalid operation.', 422)
    if action == 'create' and (channel_id is not None or expected_revision is not None):
        _error('invalid_request', 'Invalid operation.', 422)
    if action == 'rotate' and (type(expected_revision) is not int or expected_revision < 1):
        _error('invalid_request', 'Invalid revision.', 422)
    request = [action, channel_id, expected_revision]
    fingerprint = hashlib.sha256(json.dumps(request, separators=(',', ':')).encode()).hexdigest()
    receipt_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor.get('owner'), request_id], separators=(',', ':')).encode()).hexdigest()
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data,owner_id FROM objects WHERE kind='w24authorityreceipt' AND id=? AND session_id=?", (receipt_id, ctx.sid)).fetchone()
        if row:
            receipt = json.loads(row['data'])
            if row['owner_id'] != ctx.actor['owner'] or receipt['fingerprint'] != fingerprint:
                _error('request_conflict', 'Request ID already used.', 409)
            return {'requestId': request_id, 'state': 'committed', 'channelId': receipt['channelId'],
                    'revision': receipt['revision'], 'capabilityAvailable': False}
        capability = secrets.token_urlsafe(32)
        if action == 'create':
            channel_id, revision = store.ident(), 1
            _insert(db, 'w24channel', channel_id, ctx.sid, ctx.actor['owner'],
                    {'verifier': store.digest(capability), 'revoked': False})
            _insert(db, 'w24channelmember', _member_id(channel_id, ctx.sid), ctx.sid, ctx.actor['owner'],
                    {'channelId': channel_id, 'active': True})
        else:
            channel, revision = _channel(db, channel_id)
            if not _membership(db, channel_id, ctx.sid):
                _error()
            if revision != expected_revision:
                _error('stale_revision', 'Channel changed; reload.', 409)
            channel['verifier'] = store.digest(capability)
            revision += 1
            db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w24channel' AND id=?",
                       (json.dumps(channel, sort_keys=True), revision, channel_id))
        _insert(db, 'w24authorityreceipt', receipt_id, ctx.sid, ctx.actor['owner'],
                {'fingerprint': fingerprint, 'channelId': channel_id, 'revision': revision})
        db.commit()
        return {'requestId': request_id, 'state': 'committed', 'channelId': channel_id,
                'revision': revision, 'capabilityAvailable': True, 'capability': capability}


def capability_receipt(ctx, request_id):
    """Recover committed metadata for the same authenticated creator only."""
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request_id):
        _error('invalid_request', 'Invalid operation.', 422)
    receipt_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor.get('owner'), request_id], separators=(',', ':')).encode()).hexdigest()
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        row = db.execute("SELECT data,owner_id FROM objects WHERE kind='w24authorityreceipt' AND id=? AND session_id=?", (receipt_id, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _error()
        receipt = json.loads(row['data'])
        if 'result' in receipt:
            return receipt['result']
        return {'requestId': request_id, 'state': 'committed', 'channelId': receipt['channelId'],
                'revision': receipt['revision'], 'capabilityAvailable': False}


def membership_operation(ctx, body):
    """Commit enrollment or revocation and its actor-bound receipt atomically."""
    if not isinstance(body, dict):
        _error('invalid_request', 'Invalid operation.', 422)
    action = body.get('action')
    fields = {'requestId', 'action', 'channelId'}
    if action == 'enroll':
        fields.add('capability')
    elif action == 'revoke':
        fields.update(('expectedRevision', 'sessionId'))
    else:
        _error('invalid_request', 'Invalid operation.', 422)
    request_id = body.get('requestId')
    if set(body) != fields or not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request_id):
        _error('invalid_request', 'Invalid operation.', 422)
    request = dict(body)
    if action == 'enroll':
        capability = body['capability']
        if not isinstance(capability, str) or not 32 <= len(capability) <= 256:
            _error()
        request['capability'] = store.digest(capability)
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    receipt_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor.get('owner'), request_id], separators=(',', ':')).encode()).hexdigest()
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data,owner_id FROM objects WHERE kind='w24authorityreceipt' AND id=? AND session_id=?", (receipt_id, ctx.sid)).fetchone()
        if row:
            prior = json.loads(row['data'])
            if row['owner_id'] != ctx.actor['owner'] or prior['fingerprint'] != fingerprint:
                _error('request_conflict', 'Request ID already used.', 409)
            return prior['result']
        channel_id = body['channelId']
        channel, revision = _channel(db, channel_id)
        if action == 'enroll':
            if not hmac.compare_digest(channel['verifier'], store.digest(capability)):
                _error()
            member_id = _member_id(channel_id, ctx.sid)
            member = db.execute("SELECT id FROM objects WHERE kind='w24channelmember' AND id=?", (member_id,)).fetchone()
            value = {'channelId': channel_id, 'active': True}
            if member:
                db.execute("UPDATE objects SET data=?,owner_id=?,revision=revision+1 WHERE kind='w24channelmember' AND id=?", (json.dumps(value, sort_keys=True), ctx.actor['owner'], member_id))
            else:
                _insert(db, 'w24channelmember', member_id, ctx.sid, ctx.actor['owner'], value)
            result = {'requestId': request_id, 'state': 'committed', 'channelId': channel_id, 'revision': revision, 'enrolled': True}
        else:
            if not _membership(db, channel_id, ctx.sid):
                _error()
            if type(body['expectedRevision']) is not int or body['expectedRevision'] != revision:
                _error('stale_revision', 'Channel changed; reload.', 409)
            target = body['sessionId']
            if target is None:
                channel['revoked'] = True
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w24channel' AND id=?", (json.dumps(channel, sort_keys=True), channel_id))
            else:
                if not isinstance(target, str) or not _membership(db, channel_id, target):
                    _error()
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w24channelmember' AND id=?", (json.dumps({'channelId': channel_id, 'active': False}), _member_id(channel_id, target)))
                db.execute("UPDATE objects SET revision=revision+1 WHERE kind='w24channel' AND id=?", (channel_id,))
            result = {'requestId': request_id, 'state': 'committed', 'channelId': channel_id, 'revision': revision + 1, 'revoked': True}
        _insert(db, 'w24authorityreceipt', receipt_id, ctx.sid, ctx.actor['owner'], {'fingerprint': fingerprint, 'result': result})
        db.commit()
        return result


def create(ctx):
    """Create a channel; return its capability once, never persist it in plaintext."""
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        channel_id, capability = store.ident(), secrets.token_urlsafe(32)
        db.execute('BEGIN IMMEDIATE')
        _insert(db, 'w24channel', channel_id, ctx.sid, ctx.actor['owner'],
                {'verifier': store.digest(capability), 'revoked': False})
        _insert(db, 'w24channelmember', _member_id(channel_id, ctx.sid), ctx.sid, ctx.actor['owner'],
                {'channelId': channel_id, 'active': True})
        db.commit()
        return {'channelId': channel_id, 'capability': capability, 'revision': 1}


def enroll(ctx, channel_id, capability):
    """Link another authenticated creator session by proof of the capability."""
    if not isinstance(capability, str) or not 32 <= len(capability) <= 256:
        _error()
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        channel, revision = _channel(db, channel_id)
        if not hmac.compare_digest(channel['verifier'], store.digest(capability)):
            _error()
        member_id = _member_id(channel_id, ctx.sid)
        row = db.execute("SELECT id FROM objects WHERE kind='w24channelmember' AND id=?", (member_id,)).fetchone()
        value = json.dumps({'channelId': channel_id, 'active': True}, sort_keys=True, separators=(',', ':'))
        if row:
            db.execute("UPDATE objects SET data=?,owner_id=?,revision=revision+1 WHERE kind='w24channelmember' AND id=?", (value, ctx.actor['owner'], member_id))
        else:
            _insert(db, 'w24channelmember', member_id, ctx.sid, ctx.actor['owner'], {'channelId': channel_id, 'active': True})
        db.commit()
        return {'channelId': channel_id, 'revision': revision, 'enrolled': True}


def rotate(ctx, channel_id, expected_revision):
    """Issue a replacement capability; existing memberships stay enrolled."""
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        channel, revision = _channel(db, channel_id)
        if not _membership(db, channel_id, ctx.sid):
            _error()
        if type(expected_revision) is not int or revision != expected_revision:
            _error('stale_revision', 'Channel changed; reload.', 409)
        capability = secrets.token_urlsafe(32)
        channel['verifier'] = store.digest(capability)
        db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w24channel' AND id=?", (json.dumps(channel, sort_keys=True), channel_id))
        db.commit()
        return {'channelId': channel_id, 'revision': revision + 1, 'capability': capability}


def revoke(ctx, channel_id, expected_revision, session_id=None):
    """Revoke the whole channel, or one enrolled session, under current authority."""
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        channel, revision = _channel(db, channel_id)
        if not _membership(db, channel_id, ctx.sid):
            _error()
        if type(expected_revision) is not int or expected_revision != revision:
            _error('stale_revision', 'Channel changed; reload.', 409)
        if session_id is None:
            channel['revoked'] = True
            db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w24channel' AND id=?", (json.dumps(channel, sort_keys=True), channel_id))
        else:
            if not isinstance(session_id, str) or not _membership(db, channel_id, session_id):
                _error()
            db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w24channelmember' AND id=?", (json.dumps({'channelId': channel_id, 'active': False}), _member_id(channel_id, session_id)))
            db.execute("UPDATE objects SET revision=revision+1 WHERE kind='w24channel' AND id=?", (channel_id,))
        db.commit()
        return {'channelId': channel_id, 'revision': revision + 1, 'revoked': True}


def approve_source(ctx, channel_id, ref):
    """Approve one exact visible moment; no private actor or payload is copied."""
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        ref = parse_ref(ref)
        if ref['sessionId'] != ctx.sid:
            _error()
        _channel(db, channel_id)
        if not _membership(db, channel_id, ctx.sid):
            _error()
        row = ctx.resolve([ref])[0]
        if row['source'].get('audienceVisible') is not True:
            _error()
        grant_id = store.ident()
        db.execute('BEGIN IMMEDIATE')
        _insert(db, 'w24archivegrant', grant_id, ctx.sid, ctx.actor['owner'],
                {'channelId': channel_id, 'ref': ref, 'active': True})
        db.commit()
        return {'grantId': grant_id, 'revision': 1}


def source_operation(ctx, body):
    """Approve or withdraw a source grant with an atomic secret-free receipt."""
    if not isinstance(body, dict):
        _error('invalid_request', 'Invalid operation.', 422)
    action = body.get('action')
    fields = {'requestId', 'action', 'channelId'}
    if action == 'approve':
        if body.get('kind') == 'profile':
            fields.update(('kind', 'profileId', 'profileRevision'))
        elif body.get('kind') == 'model':
            fields.update(('kind', 'approvalId'))
        elif body.get('kind') == 'activity':
            fields.update(('kind', 'activityId', 'activityRevision', 'modelGrantId', 'modelGrantRevision'))
        elif body.get('kind') == 'claim':
            fields.update(('kind', 'claimId', 'claimRevision', 'topic'))
        elif body.get('kind') == 'edition':
            fields.update(('kind', 'recordId', 'recordRevision', 'language'))
        else:
            fields.add('ref')
    elif action == 'withdraw':
        fields.update(('grantId', 'expectedRevision'))
    else:
        _error('invalid_request', 'Invalid operation.', 422)
    request_id = body.get('requestId')
    if set(body) != fields or not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request_id):
        _error('invalid_request', 'Invalid operation.', 422)
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    receipt_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor.get('owner'), request_id], separators=(',', ':')).encode()).hexdigest()
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data,owner_id FROM objects WHERE kind='w24authorityreceipt' AND id=? AND session_id=?", (receipt_id, ctx.sid)).fetchone()
        if row:
            prior = json.loads(row['data'])
            if row['owner_id'] != ctx.actor['owner'] or prior['fingerprint'] != fingerprint:
                _error('request_conflict', 'Request ID already used.', 409)
            return prior['result']
        channel_id = body['channelId']
        _channel(db, channel_id)
        if not _membership(db, channel_id, ctx.sid):
            _error()
        if action == 'approve':
            if body.get('kind') == 'profile':
                from . import waves23_speech_profiles as profiles
                obj = profiles.load(ctx, body['profileId'])
                profiles.check_access(ctx, obj)
                if (type(body['profileRevision']) is not int or obj['_revision'] != body['profileRevision']
                        or not obj.get('approval') or obj['profile'].get('audienceVisible') is not True):
                    _error()
                value = {'channelId': channel_id, 'kind': 'profile', 'profileId': body['profileId'],
                         'profileRevision': body['profileRevision'], 'active': True}
            elif body.get('kind') == 'model':
                from . import waves22_model_auth as model_auth
                matches = [a for a in model_auth.list_approvals(ctx)['approvals'] if a['approvalId'] == body['approvalId']]
                if len(matches) != 1:
                    _error()
                value = {'channelId': channel_id, 'kind': 'model', 'approvalId': body['approvalId'], 'active': True}
            elif body.get('kind') == 'activity':
                from . import waves24_activity_handoff as activities
                activity = activities.activity_reference(ctx, body['activityId'], body['activityRevision'])
                model = project_model(ctx, channel_id, body['modelGrantId'], body['modelGrantRevision'])
                model_row = db.execute("SELECT session_id,owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (body['modelGrantId'],)).fetchone()
                if (not model_row or model_row['session_id'] != ctx.sid or model_row['owner_id'] != ctx.actor['owner']
                        or activity['approvalId'] != model['approvalId'] or activity['definition'] != model['definition']):
                    _error()
                value = {'channelId': channel_id, 'kind': 'activity', 'activityId': body['activityId'],
                         'activityRevision': body['activityRevision'], 'modelGrantId': body['modelGrantId'],
                         'modelGrantRevision': body['modelGrantRevision'], 'active': True}
            elif body.get('kind') == 'claim':
                from . import waves22_claims as claims
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                found = claims.query(ctx, body['topic'], now, now)
                matches = [c for c in found['current'] + found['prior']
                           if c['id'] == body['claimId'] and c['revision'] == body['claimRevision']
                           and c['scope'] == 'creator']
                if type(body['claimRevision']) is not int or len(matches) != 1:
                    _error()
                for ref in matches[0]['sourceRefs']:
                    if ctx.resolve([ref])[0]['source'].get('audienceVisible') is not True:
                        _error()
                value = {'channelId': channel_id, 'kind': 'claim', 'claimId': body['claimId'],
                         'claimRevision': body['claimRevision'], 'topic': body['topic'], 'active': True}
            elif body.get('kind') == 'edition':
                from . import waves22_edition as edition
                prepared = edition.project_edition(ctx, body['recordId'], body['language'], released=edition.released_metadata)
                manifest = edition.finalize(ctx, prepared, released=edition.released_metadata)
                if type(body['recordRevision']) is not int or manifest['revision'] != body['recordRevision']:
                    _error()
                for source in manifest['provenance']['sources']:
                    if ctx.resolve([source['ref']])[0]['source'].get('audienceVisible') is not True:
                        _error()
                value = {'channelId': channel_id, 'kind': 'edition', 'recordId': body['recordId'],
                         'recordRevision': body['recordRevision'], 'language': body['language'], 'active': True}
            else:
                ref = parse_ref(body['ref'])
                if ref['sessionId'] != ctx.sid or ctx.resolve([ref])[0]['source'].get('audienceVisible') is not True:
                    _error()
                value = {'channelId': channel_id, 'ref': ref, 'active': True}
            grant_id = store.ident()
            _insert(db, 'w24archivegrant', grant_id, ctx.sid, ctx.actor['owner'], value)
            revision = 1
        else:
            grant_id = body['grantId']
            grant = db.execute("SELECT data,revision,owner_id FROM objects WHERE kind='w24archivegrant' AND id=? AND session_id=?", (grant_id, ctx.sid)).fetchone()
            if not grant or grant['owner_id'] != ctx.actor['owner']:
                _error()
            value = json.loads(grant['data'])
            if value.get('channelId') != channel_id or value.get('active') is not True:
                _error()
            if type(body['expectedRevision']) is not int or grant['revision'] != body['expectedRevision']:
                _error('stale_revision', 'Approval changed; reload.', 409)
            value['active'] = False
            revision = grant['revision'] + 1
            db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w24archivegrant' AND id=?", (json.dumps(value, sort_keys=True), revision, grant_id))
        result = {'requestId': request_id, 'state': 'committed', 'channelId': channel_id, 'grantId': grant_id, 'revision': revision, 'withdrawn': action == 'withdraw'}
        _insert(db, 'w24authorityreceipt', receipt_id, ctx.sid, ctx.actor['owner'], {'fingerprint': fingerprint, 'result': result})
        db.commit()
        return result


def withdraw_grant(ctx, channel_id, grant_id, expected_revision):
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        _channel(db, channel_id)
        if not _membership(db, channel_id, ctx.sid):
            _error()
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data,revision,owner_id FROM objects WHERE kind='w24archivegrant' AND id=? AND session_id=?", (grant_id, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _error()
        value = json.loads(row['data'])
        if value.get('channelId') != channel_id or not value.get('active'):
            _error()
        if type(expected_revision) is not int or expected_revision != row['revision']:
            _error('stale_revision', 'Approval changed; reload.', 409)
        value['active'] = False
        db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w24archivegrant' AND id=?", (json.dumps(value, sort_keys=True), grant_id))
        db.commit()
        return {'grantId': grant_id, 'revision': row['revision'] + 1, 'withdrawn': True}


def project_source(ctx, channel_id, grant_id, revision):
    """Project an approved source from current stored data, without impersonation."""
    from .http import expired
    with ctx.lock, store.connect() as db:
        require_member(ctx, channel_id)
        row = db.execute("SELECT data,revision,session_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant_id,)).fetchone()
        if not row or type(revision) is not int or row['revision'] != revision:
            _error()
        grant = json.loads(row['data'])
        if (grant.get('kind') is not None or 'ref' not in grant or grant.get('channelId') != channel_id
                or grant.get('active') is not True or not _membership(db, channel_id, row['session_id'])):
            _error()
        ref = parse_ref(grant['ref'])
        if ref['sessionId'] != row['session_id']:
            _error()
        source = store.get('source', ref['sourceId'], ref['sessionId'])
        moment = store.get('p10moment', ref['momentId'], ref['sessionId'])
        if (not source or not moment or moment.get('ref') != ref or source.get('_revision') != ref['sourceRevision']
                or source.get('status') != 'active' or source.get('audienceVisible') is not True or expired(source)):
            _error()
        if moment.get('alignment', {}).get('origin') == 'capture' or source.get('p10Frame'):
            from .phase10_timeline import frame_moment
            frame = frame_moment(source)
            if (frame.get('ref') != ref or frame.get('alignment') != moment.get('alignment')
                    or frame.get('captureRunId') != moment.get('captureRunId')):
                _error()
        return {'ref': ref, 'title': str(source.get('title', 'Source'))[:200],
                'excerpt': str(moment.get('text', ''))[:220]}


def _claim_data(ctx, channel_id, grant_id, revision):
    """Read exactly the approved creator claim and its currently public sources."""
    from . import waves22_claims as claims
    from .http import expired
    with ctx.lock, store.connect() as db:
        require_member(ctx, channel_id)
        row = db.execute("SELECT data,revision,session_id,owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant_id,)).fetchone()
        if not row or type(revision) is not int or row['revision'] != revision:
            _error()
        grant = json.loads(row['data'])
        sid, owner = row['session_id'], row['owner_id']
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (sid, sid)).fetchone()
        if (grant.get('kind') != 'claim' or grant.get('active') is not True or grant.get('channelId') != channel_id
                or not _membership(db, channel_id, sid) or not session or session['owner_id'] != owner):
            _error()
        record = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (claims.KIND, grant['claimId'], sid)).fetchone()
        if not record or record['revision'] != grant['claimRevision'] or record['owner_id'] != owner:
            _error()
        item = json.loads(record['data'])
        if item.get('scope') != 'creator' or item.get('forgotten') or item.get('topic') != grant['topic']:
            _error()
        for ref in item['sourceRefs']:
            ref = parse_ref(ref)
            source = store.get('source', ref['sourceId'], sid)
            moment = store.get('p10moment', ref['momentId'], sid)
            if (ref['sessionId'] != sid or not source or not moment or moment.get('ref') != ref
                    or source.get('_revision') != ref['sourceRevision'] or source.get('status') != 'active'
                    or source.get('audienceVisible') is not True or expired(source)):
                _error()
            if moment.get('alignment', {}).get('origin') == 'capture' or source.get('p10Frame'):
                from .phase10_timeline import frame_moment
                frame = frame_moment(source)
                if (frame.get('ref') != ref or frame.get('alignment') != moment.get('alignment')
                        or frame.get('captureRunId') != moment.get('captureRunId')):
                    _error()
        return claims._project(dict(item, revision=record['revision']))


def project_claim(ctx, channel_id, grant_id, revision):
    """Derive status only from currently authorized, explicitly exported claims."""
    from datetime import datetime, timezone
    with ctx.lock, store.connect() as db:
        selected = _claim_data(ctx, channel_id, grant_id, revision)
        rows = db.execute("SELECT id,revision,data FROM objects WHERE kind='w24archivegrant' LIMIT 1001").fetchall()
        if len(rows) > 1000:
            _error('capacity', 'Too many archive approvals.', 409)
        eligible = {}
        for row in rows:
            grant = json.loads(row['data'])
            if (grant.get('channelId') != channel_id or grant.get('kind') != 'claim'
                    or grant.get('active') is not True or grant.get('topic') != selected['topic']):
                continue
            try:
                claim = _claim_data(ctx, channel_id, row['id'], row['revision'])
            except Phase10Error:
                continue
            eligible[(claim['id'], claim['revision'])] = claim
        now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
        active = {key: claim for key, claim in eligible.items()
                  if claim['validFrom'] <= now and claim['eventTime'] <= now
                  and (claim['validUntil'] is None or now < claim['validUntil'])}
        superseded, disputed = set(), set()
        for key, claim in active.items():
            for relation in claim['relations']:
                target = (relation['claimId'], relation['revision'])
                if target in active:
                    if relation['type'] == 'supersedes':
                        superseded.add(target)
                    elif relation['type'] == 'disputes':
                        disputed.update((key, target))
        key = (selected['id'], selected['revision'])
        status = ('retired' if key not in active or key in superseded else
                  'disputed' if key in disputed else 'current')
        # Related records have separate grants; never reveal their identifiers here.
        selected['relations'] = []
        return {'claim': selected, 'status': status}


def _retained_edition(sid, record, language, _seen=None):
    """Revalidate the narrow creator-authored retained record without a session actor."""
    from . import waves15_formats as formats
    from .http import expired
    if record.get('state') != 'approved':
        _error()
    seen = set() if _seen is None else set(_seen)
    key = (sid, record.get('id'), record.get('version'))
    if key in seen or len(seen) >= 32:
        _error()
    seen.add(key)
    snap = record['snapshot']
    def live_ref(value, expected_sid=None):
        ref = parse_ref(value)
        origin = sid if expected_sid is None else expected_sid
        if ref['sessionId'] != origin:
            _error()
        source = store.get('source', ref['sourceId'], origin)
        moment = store.get('p10moment', ref['momentId'], origin)
        if (not source or source.get('status') != 'active' or source.get('audienceVisible') is not True
                or source.get('_revision') != ref['sourceRevision'] or expired(source)
                or not moment or moment.get('ref') != ref):
            _error()
        if moment.get('alignment', {}).get('origin') == 'capture' or source.get('p10Frame'):
            from .phase10_timeline import frame_moment
            frame = frame_moment(source)
            if any(frame.get(k) != moment.get(k) for k in ('ref', 'alignment', 'captureRunId')):
                _error()
        return source, moment, ref
    def retained_offer(offer, target):
        from . import waves16_continuation as continuation, waves18_records as records
        if (not offer or offer.get('kind') != 'reviewed-continuation-v1'
                or offer.get('status') != 'accepted' or offer.get('targetSessionId') != target
                or not isinstance(offer.get('snapshot'), dict)):
            _error()
        transfer = offer['snapshot']
        origin = transfer.get('sourceSessionId')
        if (not origin or offer.get('sourceSessionId') != origin
                or transfer.get('targetSessionId') != target
                or not store.get('session', origin, origin) or not store.get('session', target, target)):
            _error()
        original = store.get(continuation.F, transfer.get('formatId'), origin)
        if (not original or original['_revision'] != transfer.get('formatRevision')
                or original.get('decision') != transfer.get('decision')):
            _error()
        for entry in transfer['refs']:
            ref = entry['ref']
            live_ref(ref, ref['sessionId'])
            grant = store.get(continuation.G, entry['grantId'], origin)
            if (not grant or grant.get('status') != 'active' or grant.get('formatId') != original['id']
                    or grant.get('targetSessionId') != target or grant.get('ref') != ref):
                _error()
        for entry in transfer['contributions']:
            contribution = store.get(continuation.C, entry['id'], origin)
            consent = store.get(continuation.A, entry['consentId'], origin)
            if (not contribution or contribution['_revision'] != entry['revision']
                    or contribution.get('status') != 'accepted' or contribution.get('formatId') != original['id']
                    or not consent or consent.get('status') != 'active'
                    or consent.get('contributionId') != contribution['id']
                    or consent.get('contributionRevision') != contribution['_revision']
                    or consent.get('targetSessionId') != target):
                _error()
        material = store.get('p10material', transfer['materialId'], origin)
        if (not material or material.get('currentVersion') != transfer['materialVersion']
                or material.get('approvedVersion') != transfer['materialVersion']
                or material.get('status') not in ('approved', 'published')
                or material.get('continuationWorkId') != transfer['workId']
                or material.get('refs') != [entry['ref'] for entry in transfer['refs']]):
            _error()
        if offer.get('w18Record'):
            binding = offer['w18Record']
            if not records.RECORD_DELIVERY_INTEGRATED:
                _error()
            required = {'sessionId', 'recordId', 'version', 'language', 'targetSessionId', 'workId', 'transferId'}
            if (not isinstance(binding, dict) or set(binding) != required
                    or binding['sessionId'] != origin or binding['targetSessionId'] != target
                    or binding['transferId'] != offer.get('id')
                    or offer.get('materialSnapshot', {}).get('w18Record') != binding):
                _error()
            nested = records.fetch(origin, binding['recordId'])
            if (nested.get('version') != binding['version'] or nested.get('state') != 'approved'
                    or binding['language'] not in nested['snapshot']['interpretations']):
                _error()
            link = store.get('w18recordreuse', binding['transferId'], origin)
            work = store.get(continuation.W, binding['workId'], origin)
            marker = {k: v for k, v in binding.items() if k != 'transferId'}
            if (not link or link.get('binding') != binding or not work
                    or transfer.get('workId') != binding['workId']
                    or transfer.get('formatId') != nested['snapshot']['format']['id']
                    or transfer.get('formatRevision') != nested['snapshot']['format']['revision']
                    or work.get('w18Record') != marker or material.get('w18Record') != marker
                    or work.get('materialId') != material.get('id')):
                _error()
            _retained_edition(origin, nested, binding['language'], seen)
        return offer
    # Retained translations still depend on the original credential, ASR evidence,
    # correction lineage and current terminology, even after the session closes.
    from . import phase12_jobs as jobs, waves15_translation_review as review, waves17_terminology as terms, waves18_records as records
    from . import phase10_timeline as timeline
    for binding in snap.get('translationBindings', {}).values():
        row = jobs.fetch(sid, binding['owner'], binding['requestId'])
        if (not row or row['credential_hash'] != binding['credentialHash'] or
                row['kind'] != 'translation' or row['state'] != 'complete' or not row['result'] or
                records.digest([row['ref'], row['payload'], row['result'], row['transport']]) != binding['digest']):
            _error()
        with store.connect() as db:
            credential = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?', (row['credential_hash'],)).fetchone()
        if not credential or tuple(credential) != (row['role'], sid, row['actor_id']):
            _error()
        raw = json.loads(row['ref'])
        if not isinstance(raw, dict) or 'type' in raw:
            _error()
        source, moment, ref = live_ref(raw)
        proof = source.get('p10Provenance', {})
        if proof.get('type') != 'received_asr_v1' or proof.get('sessionId') != sid:
            _error()
        try:
            rebuilt = timeline.build_moments(source, [{'startMs': ref['startMs'], 'endMs': ref['endMs'], 'kind': moment.get('kind')}])[0]
        except (Phase10Error, KeyError, TypeError):
            _error()
        result = json.loads(row['result'])
        if (any(rebuilt.get(k) != moment.get(k) for k in ('ref', 'text', 'alignment')) or
                ref != binding['sourceRef'] or result.get('ref') != ref or result.get('original') != moment.get('text')):
            _error()
        if row['transport'] == 'local_user_correction':
            parent = jobs.fetch(sid, row['actor_id'], review.root_id(row))
            if (not parent or parent['kind'] != 'translation' or parent['transport'] == 'local_user_correction'
                    or parent['state'] != 'complete' or not parent['result']
                    or parent['credential_hash'] != row['credential_hash'] or parent['ref'] != row['ref']
                    or parent['role'] != row['role'] or parent['session_id'] != row['session_id']
                    or parent['actor_id'] != row['actor_id']):
                _error()
        versions = review.corrections(row)
        if versions and versions[-1]['request_id'] != row['request_id']:
            _error()
        term_row = parent if row['transport'] == 'local_user_correction' else row
        bound = json.loads(term_row['payload']).get('terminologySnapshot')
        if bound:
            approved = terms.load(sid)
            approved = approved.get('approved') if approved else None
            if (not approved or approved.get('revision') != bound.get('revision')
                    or approved.get('document') != bound.get('document')):
                _error()
            for item in bound['document']['context']:
                context_source, context_moment, context_ref = live_ref(item['ref'])
                proof = context_source.get('p10Provenance', {})
                if proof.get('type') != 'received_asr_v1' or proof.get('sessionId') != sid:
                    _error()
                try:
                    rebuilt = timeline.build_moments(context_source, [{'startMs': context_ref['startMs'],
                        'endMs': context_ref['endMs'], 'kind': context_moment.get('kind')}])[0]
                except (Phase10Error, KeyError, TypeError):
                    _error()
                if any(rebuilt.get(k) != context_moment.get(k) for k in ('ref', 'text', 'alignment')):
                    _error()
    for ref in snap['refs']:
        live_ref(ref)
    for chapter in snap['chapters']:
        current = store.get('w15chapter', chapter['id'], sid)
        if not current or current['_revision'] != chapter['revision'] or current.get('status') != 'active' or current.get('refs') != chapter['refs']:
            _error()
        for ref in chapter['refs']:
            live_ref(ref)
    fmt = store.get(formats.F, snap['format']['id'], sid)
    if (not fmt or fmt['_revision'] != snap['format']['revision'] or fmt.get('decision') != snap['decision']):
        _error()
    if fmt.get('continuationTransferId'):
        offer = retained_offer(store.get('w15formattransfer', fmt['continuationTransferId']), sid)
        if offer.get('recipientFormatId') != fmt['id']:
            _error()
    if fmt.get('templateRoundId'):
        from . import waves17_templates as templates
        round_ = store.get(templates.R, fmt['templateRoundId'], sid)
        if (not round_ or round_.get('formatId') != fmt['id']
                or round_.get('stage') not in ('reveal', 'close')
                or round_.get('_revision') != snap.get('roundRevision')
                or not store.get(templates.V, round_['templateId'] + ':' + str(round_['templateVersion']))):
            _error()
        if fmt.get('templateImportTransferId'):
            retained_offer(store.get('w15formattransfer', fmt['templateImportTransferId']), sid)
    elif fmt.get('templateImportTransferId'):
        _error()
    for ref in fmt.get('refs', []):
        live_ref(ref)
    ids = set()
    for entry in snap['contributions']:
        contribution = store.get(formats.C, entry['id'], sid)
        if (not contribution or contribution['_revision'] != entry['revision'] or contribution.get('status') != 'accepted'
                or contribution.get('formatId') != fmt['id']
                or contribution.get('continuationTransferId') != fmt.get('continuationTransferId')):
            _error()
        for ref in contribution.get('refs', []):
            live_ref(ref)
        ids.add(contribution['id'])
    if not set(snap['decision']['reasonIds']) <= ids or not set(snap['decision']['minorityIds']) <= ids:
        _error()
    lang = language if language in snap['interpretations'] else snap['sourceLanguage']
    return {'id': record['id'], 'version': record['version'], 'refs': snap['refs'],
            'sourceLanguage': snap['sourceLanguage'], 'language': lang, 'fallback': lang != language,
            'interpretation': snap['interpretations'][lang],
            'provenance': ('creator_reviewed_translation' if lang in snap.get('translationBindings', {}) else 'creator_authored'),
            'availableLanguages': list(snap['interpretations'])}


def project_edition(ctx, channel_id, grant_id, revision):
    """Project an explicitly exported approved record with current origin rights."""
    from . import waves18_records as records
    with ctx.lock, store.connect() as db:
        require_member(ctx, channel_id)
        row = db.execute("SELECT data,revision,session_id,owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant_id,)).fetchone()
        if not row or type(revision) is not int or row['revision'] != revision:
            _error()
        grant = json.loads(row['data'])
        sid, owner = row['session_id'], row['owner_id']
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (sid, sid)).fetchone()
        if (grant.get('kind') != 'edition' or grant.get('active') is not True or grant.get('channelId') != channel_id
                or not _membership(db, channel_id, sid) or not session or session['owner_id'] != owner):
            _error()
        record = records.fetch(sid, grant['recordId'])
        record_row = db.execute('SELECT owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (records.KIND, grant['recordId'], sid)).fetchone()
        if record.get('_revision') != grant['recordRevision'] or record.get('creatorId') != owner or not record_row or record_row['owner_id'] != owner:
            _error()
        from . import lifecycle
        origin = store.get('session', sid, sid)
        view = (records.projection(sid, record, grant['language']) if lifecycle.active(origin)
                else _retained_edition(sid, record, grant['language']))
        return {key: view[key] for key in ('id', 'version', 'refs', 'sourceLanguage', 'language',
                                           'fallback', 'interpretation', 'provenance', 'availableLanguages')}


def project_profile(ctx, channel_id, grant_id, revision):
    """Project only explicitly approved profile forms from current stored rights."""
    from . import waves23_speech_profiles as profiles, waves21_speech_runtime as speech
    with ctx.lock, store.connect() as db:
        require_member(ctx, channel_id)
        row = db.execute("SELECT data,revision,session_id,owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant_id,)).fetchone()
        if not row or type(revision) is not int or row['revision'] != revision:
            _error()
        grant = json.loads(row['data'])
        if (grant.get('kind') != 'profile' or grant.get('active') is not True
                or grant.get('channelId') != channel_id or not _membership(db, channel_id, row['session_id'])):
            _error()
        obj = store.get(profiles.PROFILE, grant['profileId'], row['session_id'])
        origin = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (row['session_id'], row['session_id'])).fetchone()
        if (not obj or obj.get('_revision') != grant['profileRevision'] or obj.get('owner') != row['owner_id']
                or not origin or origin['owner_id'] != row['owner_id']
                or not obj.get('approval') or obj.get('profile', {}).get('audienceVisible') is not True):
            _error()
        profile, approval = obj['profile'], obj['approval']
        rules = store.get(speech.RULE_KIND, profile['ruleSetId'], row['session_id'])
        if (not rules or rules.get('owner') != row['owner_id']
                or rules.get('ruleset', {}).get('revision') != profile['ruleSetRevision']
                or approval.get('ruleSetId') != profile['ruleSetId']
                or approval.get('ruleSetRevision') != profile['ruleSetRevision']):
            _error()
        credential = db.execute("SELECT 1 FROM credentials WHERE hash=? AND role='creator' AND session_id=? AND owner_id=?", (rules.get('credentialHash'), row['session_id'], row['owner_id'])).fetchone()
        if not credential:
            _error()
        return {'profile': profiles.projection(obj), 'approvedRules': approval['rules']}


def approved_profile_for_generation(ctx, channel_id, grant_id, revision):
    """Build the approved speech reader's input from a current archive grant."""
    from . import waves23_speech_profiles as profiles
    with ctx.lock, ctx.store.connect() as db:
        projected = project_profile(ctx, channel_id, grant_id, revision)
        row = db.execute("SELECT owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant_id,)).fetchone()
        if not row:
            _error('not_found', 'Approved profile unavailable.', 404)
        p = projected['profile']
        return {'id': p['profileId'], '_revision': p['revision'], 'owner': row['owner_id'],
                'profile': {key: p[key] for key in profiles.FIELDS},
                'approval': {'ruleSetId': p['ruleSetId'], 'ruleSetRevision': p['ruleSetRevision'],
                             'rules': projected['approvedRules']}}


def project_model(ctx, channel_id, grant_id, revision):
    """Resolve an explicitly exported model against its original current records."""
    from . import waves22_model_auth as auth, waves22_models as models
    from .http import expired
    with ctx.lock, store.connect() as db:
        require_member(ctx, channel_id)
        row = db.execute("SELECT data,revision,session_id,owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant_id,)).fetchone()
        if not row or type(revision) is not int or row['revision'] != revision:
            _error()
        grant = json.loads(row['data'])
        sid, owner = row['session_id'], row['owner_id']
        session = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (sid, sid)).fetchone()
        if (grant.get('kind') != 'model' or grant.get('active') is not True or grant.get('channelId') != channel_id
                or not _membership(db, channel_id, sid) or not session or session['owner_id'] != owner):
            _error()
        approval_id = grant['approvalId']
        record = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (auth.APPROVAL, approval_id, sid)).fetchone()
        if not record or record['owner_id'] != owner:
            _error()
        value = json.loads(record['data'])
        definition = models.validate_definition(value.get('definition'))
        if value != {'definition': definition, 'active': True, 'creatorId': owner} or models._hash(definition) != approval_id:
            _error()
        auth._template(db, sid, owner, definition)
        for ref in definition['sourceRefs']:
            ref = parse_ref(ref)
            source = store.get('source', ref['sourceId'], sid)
            moment = store.get('p10moment', ref['momentId'], sid)
            if (ref['sessionId'] != sid or not source or not moment or moment.get('ref') != ref
                    or source.get('_revision') != ref['sourceRevision'] or source.get('status') != 'active'
                    or source.get('audienceVisible') is not True or expired(source)):
                _error()
            if moment.get('alignment', {}).get('origin') == 'capture' or source.get('p10Frame'):
                from .phase10_timeline import frame_moment
                frame = frame_moment(source)
                if (frame.get('ref') != ref or frame.get('alignment') != moment.get('alignment')
                        or frame.get('captureRunId') != moment.get('captureRunId')):
                    _error()
        return {'approvalId': approval_id, 'definition': definition}


def project_activity(ctx, channel_id, grant_id, revision):
    """Read a retained activity version under both explicit archive grants."""
    from . import waves24_activity_handoff as activities, waves22_models as models
    with ctx.lock, store.connect() as db:
        require_member(ctx, channel_id)
        row = db.execute("SELECT data,revision,session_id,owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant_id,)).fetchone()
        if not row or type(revision) is not int or row['revision'] != revision:
            _error()
        grant = json.loads(row['data'])
        sid, owner = row['session_id'], row['owner_id']
        if grant.get('kind') != 'activity' or grant.get('active') is not True or grant.get('channelId') != channel_id or not _membership(db, channel_id, sid):
            _error()
        model_row = db.execute("SELECT session_id,owner_id FROM objects WHERE kind='w24archivegrant' AND id=?", (grant['modelGrantId'],)).fetchone()
        if not model_row or model_row['session_id'] != sid or model_row['owner_id'] != owner:
            _error()
        model = project_model(ctx, channel_id, grant['modelGrantId'], grant['modelGrantRevision'])
        activity = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (activities.ACTIVITY, grant['activityId'], sid)).fetchone()
        version = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (activities.VERSION, models._hash([grant['activityId'], grant['activityRevision']]), sid)).fetchone()
        if not activity or not version or activity['owner_id'] != owner or version['owner_id'] != owner:
            _error()
        head, value = json.loads(activity['data']), json.loads(version['data'])
        if (head.get('withdrawn') or head.get('approvalId') != model['approvalId'] or head.get('definition') != model['definition']
                or value.get('activityId') != grant['activityId'] or value.get('revision') != grant['activityRevision']
                or value.get('approvalId') != model['approvalId'] or value.get('definition') != model['definition']):
            _error()
        return {'activityId': grant['activityId'], 'revision': grant['activityRevision'], 'approvalId': model['approvalId'],
                'definition': model['definition'], 'units': model['definition']['spec']['units']}
