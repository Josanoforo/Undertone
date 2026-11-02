"""Session-bound channel pack primitives; shared mounting remains with PRIMARY."""

import hashlib
import json
import re
from datetime import datetime, timezone

from . import store, waves22_claims, waves22_edition, waves22_model_auth, waves24_activity_handoff, channel_authority
from .phase10_common import Context, Phase10Error, parse_ref


def session_authority(handler, sid, actor):
    """Authenticate against real session credentials; no cross-session inference."""
    ctx = Context(handler, sid, actor)
    ctx.check_actor()
    if ctx.actor.get('sid') != sid:
        raise Phase10Error('not_found', 'Session unavailable.', 404)
    return ctx


def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _fingerprint(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _creator(ctx):
    ctx.check_actor()
    # The owner is authoritative in the objects row; never use a display name.
    with ctx.store.connect() as db:
        row = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
    if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') != 'creator' or not row or row['owner_id'] != ctx.actor.get('owner'):
        _fail('not_found', 'Pack unavailable.', 404)


# Session-local, creator-authored setup data. These are not channel grants,
# runtime destinations, model approvals, or independently approved resources.
_SETUP_DEFINITION_FIELDS = {
    'roleDefinition': ('label',),
    'glossaryDefinition': ('term', 'meaning'),
    'profileDefinition': ('language', 'engine', 'model', 'modelVersion', 'voiceId', 'voiceVersion', 'adapterVersion', 'rate', 'qualityPreference'),
    'chapterDefinition': ('title', 'refs'),
    'activityDefinition': ('type', 'title', 'question', 'options', 'cards'),
    'cueDefinition': ('label', 'kind', 'materialFormat'),
}


def _setup_definition(ctx, kind, ref, revision):
    _creator(ctx)
    if not isinstance(ref, dict) or set(ref) != {'id', 'definition'}:
        _fail('invalid_item', 'Invalid setup definition.', 422)
    ident = _id(ref['id']); definition = ref['definition']
    fields = _SETUP_DEFINITION_FIELDS[kind]
    if not isinstance(definition, dict) or set(definition) != set(fields):
        _fail('invalid_item', 'Invalid setup definition fields.', 422)
    if kind == 'activityDefinition':
        from . import waves17_templates
        clean = waves17_templates.clean_definition(definition)
        if re.search(r'(?i)(bearer\s+\S+|(?:api[_ -]?key|password|secret|credential|access[_ -]?token)\s*[:=]|https?://)', _canonical(clean)):
            _fail('invalid_item', 'Credentials and destinations are not setup definitions.', 422)
        return {'kind': kind, 'ref': {'id': ident, 'definition': clean}, 'revision': revision}
    if kind == 'profileDefinition':
        from . import waves23_speech_profiles
        # Existing validator checks actual engine, voice and control shape. No
        # private rule set, old approval or audience grant is transferred.
        checked = waves23_speech_profiles.validate({**definition, 'ruleSetId':'unbound', 'ruleSetRevision':0, 'audienceVisible':False})
        return {'kind': kind, 'ref': {'id': ident, 'definition': {key: checked[key] for key in fields}}, 'revision': revision}
    clean = {}
    for key in fields:
        value = definition[key]
        if key == 'refs':
            if not isinstance(value, list) or not value or len(value) > 20:
                _fail('invalid_item', 'Select current chapter sources.', 422)
            refs = [parse_ref(ref) for ref in value]
            rows = ctx.resolve(refs)
            if not all(row['source'].get('audienceVisible') is True for row in rows):
                _fail('not_found', 'Chapter sources unavailable.', 404)
            clean[key] = refs
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > (1000 if key in ('meaning', 'instruction') else 160) or any(ord(c) < 32 for c in value):
            _fail('invalid_item', 'Invalid setup definition text.', 422)
        if re.search(r'(?i)(bearer\s+\S+|(?:api[_ -]?key|password|secret|credential|access[_ -]?token)\s*[:=]|https?://)', value):
            _fail('invalid_item', 'Credentials and destinations are not setup definitions.', 422)
        clean[key] = value.strip()
    if kind == 'cueDefinition' and clean['kind'] not in ('note', 'visual', 'audio'):
        _fail('invalid_item', 'Unsupported cue definition.', 422)
    if kind == 'cueDefinition' and clean['materialFormat'] not in ('guide', 'explanation', 'faq', 'exercise', 'highlight', 'chapter', 'export'):
        _fail('invalid_item', 'Unsupported material format.', 422)
    return {'kind': kind, 'ref': {'id': ident, 'definition': clean}, 'revision': revision}


def glossary_projection(ctx, ref, revision):
    """Resolve only forms explicitly selected into a current visible profile."""
    from . import waves21_speech_runtime as speech, waves23_speech_profiles as profiles
    _creator(ctx)
    if not isinstance(ref, dict) or set(ref) != {'profileId', 'ruleSetRevision', 'ruleIds'}:
        _fail('invalid_item', 'Invalid glossary reference.', 422)
    profile_id = _id(ref['profileId']); ids = ref['ruleIds']; rule_revision = ref['ruleSetRevision']
    if (type(rule_revision) is not int or rule_revision < 1 or not isinstance(ids, list)
            or not 1 <= len(ids) <= 100 or len(ids) != len(set(_id(i) for i in ids))):
        _fail('invalid_item', 'Invalid glossary selection.', 422)
    try:
        obj = profiles.load(ctx, profile_id)
        profiles.check_access(ctx, obj)
    except Phase10Error as exc:
        if exc.code == 'stale_profile':
            _fail('stale_context', 'Glossary unavailable or changed.', 409)
        raise
    approval = obj.get('approval')
    if (obj['_revision'] != revision or obj['profile'].get('audienceVisible') is not True
            or not isinstance(approval, dict) or approval.get('ruleSetRevision') != rule_revision
            or approval.get('ruleSetId') != obj['profile'].get('ruleSetId')):
        _fail('stale_context', 'Glossary unavailable or changed.', 409)
    rules = speech._rule_load(ctx, approval['ruleSetId'])['ruleset']
    if rules.get('revision') != rule_revision:
        _fail('stale_context', 'Glossary unavailable or changed.', 409)
    current = {r['id']: r for r in rules['rules'] if r.get('approved') is True}
    shared = {r['id']: r for r in approval.get('rules', []) if r.get('approved') is True}
    if any(i not in current or i not in shared or current[i] != shared[i] for i in ids):
        _fail('stale_context', 'Glossary unavailable or changed.', 409)
    return [{'id': i, 'language': shared[i]['language'], 'term': shared[i]['term'], 'spokenForm': shared[i]['alias']} for i in ids]


def validate_item(ctx, item):
    """Resolve an exact reference using released production readers.

    Creator claims retain their existing creator-only visibility; pronunciation
    rules lack a released persistent shared-rights reader and cannot be exported.
    """
    if not isinstance(item, dict) or set(item) != {'kind', 'ref', 'revision'}:
        _fail('invalid_item', 'A complete item reference is required.', 422)
    revision = item['revision']
    if type(revision) is not int or revision < 1:
        _fail('invalid_item', 'An exact revision is required.', 422)
    kind, ref = item['kind'], item['ref']
    if kind in _SETUP_DEFINITION_FIELDS:
        return _setup_definition(ctx, kind, ref, revision)
    if kind == 'sharedGlossary':
        glossary_projection(ctx, ref, revision)
        return {'kind': kind, 'ref': {'profileId': ref['profileId'], 'ruleSetRevision': ref['ruleSetRevision'], 'ruleIds': list(ref['ruleIds'])}, 'revision': revision}
    if kind in ('approvedPackSource', 'approvedPackProfile', 'approvedPackModel', 'approvedPackActivity', 'approvedPackClaim', 'approvedPackEdition'):
        if not isinstance(ref, dict) or set(ref) != {'channelId', 'grantId', 'sourceGrantId', 'sourceRevision'}:
            _fail('invalid_item', 'Invalid approved pack reference.', 422)
        with store.connect() as db:
            candidates = _approved_pack(ctx, db, ref['channelId'], ref['grantId'], revision, creator=False)
        expected_kind = {'approvedPackSource': 'approvedSource', 'approvedPackProfile': 'approvedProfile', 'approvedPackModel': 'approvedModel', 'approvedPackActivity': 'approvedActivity', 'approvedPackClaim': 'approvedClaim', 'approvedPackEdition': 'approvedEdition'}[kind]
        selected = next((candidate for candidate in candidates if candidate['kind'] == expected_kind and candidate['ref']['grantId'] == ref['sourceGrantId'] and candidate['revision'] == ref['sourceRevision']), None)
        if selected is None:
            _fail('not_found', 'Item unavailable.', 404)
        return {'kind': kind, 'ref': dict(ref), 'revision': revision}
    if kind in ('approvedSource', 'approvedProfile', 'approvedModel', 'approvedActivity', 'approvedClaim', 'approvedEdition'):
        if not isinstance(ref, dict) or set(ref) != {'channelId', 'grantId'}:
            _fail('invalid_item', 'Invalid approved source reference.', 422)
        _id(ref['channelId']); _id(ref['grantId'])
        projector = {'approvedSource': channel_authority.project_source, 'approvedProfile': channel_authority.project_profile, 'approvedModel': channel_authority.project_model, 'approvedActivity': channel_authority.project_activity, 'approvedClaim': channel_authority.project_claim, 'approvedEdition': channel_authority.project_edition}[kind]
        projector(ctx, ref['channelId'], ref['grantId'], revision)
        return {'kind': kind, 'ref': dict(ref), 'revision': revision}
    if kind == 'claim':
        if not isinstance(ref, dict) or set(ref) != {'claimId', 'topic'}:
            _fail('invalid_item', 'Invalid claim reference.', 422)
        _id(ref['claimId'])
        if ctx.actor.get('role') != 'creator':
            _fail('not_found', 'Item unavailable.', 404)
        now = datetime.now(timezone.utc).isoformat()
        result = waves22_claims.query(ctx, ref['topic'], now, now)
        matches = [claim for claim in result['current'] + result['prior']
                   if claim['id'] == ref['claimId'] and claim['revision'] == revision
                   and claim['scope'] == 'creator']
        if not matches:
            _fail('not_found', 'Item unavailable.', 404)
        return {'kind': kind, 'ref': dict(ref), 'revision': revision}
    if kind == 'source':
        ref = parse_ref(ref)
        if ref['sessionId'] != ctx.sid or ref['sourceRevision'] != revision:
            _fail('not_found', 'Item unavailable.', 404)
        row = ctx.resolve([ref])[0]
        if row['source'].get('audienceVisible') is not True:
            _fail('not_found', 'Item unavailable.', 404)
        return {'kind': kind, 'ref': ref, 'revision': revision}
    if kind == 'edition':
        if not isinstance(ref, dict) or set(ref) != {'recordId', 'language'}:
            _fail('invalid_item', 'Invalid edition reference.', 422)
        prepared = waves22_edition.project_edition(ctx, ref['recordId'], ref['language'], released=waves22_edition.released_metadata)
        manifest = waves22_edition.finalize(ctx, prepared, released=waves22_edition.released_metadata)
        if manifest['revision'] != revision:
            _fail('stale_revision', 'Item changed.', 409)
        for source in manifest['provenance']['sources']:
            row = ctx.resolve([source['ref']])[0]
            if row['source'].get('audienceVisible') is not True:
                _fail('not_found', 'Item unavailable.', 404)
        return {'kind': kind, 'ref': dict(ref), 'revision': revision}
    if kind == 'activity':
        if not isinstance(ref, str):
            _fail('invalid_item', 'Invalid activity reference.', 422)
        _id(ref)
        waves24_activity_handoff.activity_reference(ctx, ref, revision)
        return {'kind': kind, 'ref': ref, 'revision': revision}
    if kind == 'model':
        if not isinstance(ref, str):
            _fail('invalid_item', 'Invalid model approval reference.', 422)
        approvals = waves22_model_auth.list_approvals(ctx)['approvals']
        if revision != 1 or not any(a['approvalId'] == ref for a in approvals):
            _fail('not_found', 'Item unavailable.', 404)
        return {'kind': kind, 'ref': ref, 'revision': revision}
    _fail('unsupported_item', 'This item has no shared rights binding.', 422)


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        _fail('invalid_request', 'Invalid identifier.', 422)
    return value


def _expiry(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        _fail('invalid_request', 'Invalid expiry.', 422)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except ValueError:
        _fail('invalid_request', 'Invalid expiry.', 422)


def _live(value):
    return value is None or value > datetime.now(timezone.utc).isoformat(timespec='microseconds')


def _items(ctx, items):
    if not isinstance(items, list) or len(items) > 100:
        _fail('invalid_request', 'Select at most 100 items.', 422)
    resolved = [validate_item(ctx, item) for item in items]
    if len({_identity(item) for item in resolved}) != len(resolved):
        _fail('invalid_request', 'Duplicate items are not allowed.', 422)
    return resolved


def _identity(item):
    ref = item['ref']
    if item['kind'] == 'source':
        ref = {k: ref[k] for k in ('sessionId', 'sourceId', 'momentId')}
    elif item['kind'] in _SETUP_DEFINITION_FIELDS:
        ref = {'id': ref['id']}
    elif item['kind'] == 'sharedGlossary':
        ref = {'profileId': ref['profileId']}
    return _canonical([item['kind'], ref])


def _merge(existing, incoming, choices):
    """Require an explicit decision for each changed logical reference."""
    if not isinstance(choices, dict):
        _fail('invalid_request', 'Conflict choices are required.', 422)
    by_key = {_identity(item): item for item in existing}
    if len(by_key) != len(existing) or len({_identity(i) for i in incoming}) != len(incoming):
        _fail('invalid_request', 'Duplicate logical references are not allowed.', 422)
    conflicts = {_identity(item) for item in incoming if _identity(item) in by_key and by_key[_identity(item)] != item}
    if set(choices) != conflicts or any(v not in ('keep', 'replace') for v in choices.values()):
        _fail('conflict', 'Resolve each changed reference explicitly.', 409)
    for item in incoming:
        key = _identity(item)
        if key not in conflicts or choices[key] == 'replace':
            by_key[key] = item
    return list(by_key.values())


def _load(db, ctx, pack_id):
    row = db.execute("SELECT data,revision,owner_id FROM objects WHERE kind='w24pack' AND session_id=? AND id=?", (ctx.sid, _id(pack_id))).fetchone()
    if not row:
        _fail('not_found', 'Pack unavailable.', 404)
    return json.loads(row['data']), row['revision'], row['owner_id']


def approve_pack(ctx, channel_id, pack_id, revision):
    """Approve an exact pack version containing only individually approved sources."""
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        channel_authority.require_member(ctx, channel_id, creator=True)
        pack, current, owner = _load(db, ctx, pack_id)
        if owner != ctx.actor['owner'] or pack['withdrawn'] or not _live(pack['expiresAt']):
            _fail('not_found', 'Pack unavailable.', 404)
        if type(revision) is not int or current != revision:
            _fail('stale_revision', 'Pack changed; reload.', 409)
        if not pack['items'] or any(item.get('kind') not in ('approvedSource', 'approvedProfile', 'approvedModel', 'approvedActivity', 'approvedClaim', 'approvedEdition') or item.get('ref', {}).get('channelId') != channel_id for item in pack['items']):
            _fail('unsupported_item', 'Approve each source for this channel first.', 422)
        _items(ctx, pack['items'])
        grant_id = store.ident()
        db.execute('BEGIN IMMEDIATE')
        _insert(db, 'w24packgrant', grant_id, ctx, {'channelId': channel_id, 'packId': pack_id, 'packRevision': revision, 'active': True})
        db.commit()
        return {'grantId': grant_id, 'revision': 1}


def pack_grant_operation(ctx, body):
    """Commit a pack approval or withdrawal and its actor-bound receipt together."""
    if not isinstance(body, dict):
        _fail('invalid_request', 'Invalid operation.', 422)
    action = body.get('action')
    fields = {'action', 'requestId', 'channelId'}
    if action == 'approve':
        fields.update(('packId', 'expectedRevision'))
    elif action == 'withdraw':
        fields.update(('grantId', 'expectedRevision'))
    else:
        _fail('invalid_request', 'Invalid operation.', 422)
    request_id = body.get('requestId')
    if set(body) != fields or not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', request_id):
        _fail('invalid_request', 'Invalid operation.', 422)
    fingerprint = _fingerprint(body)
    receipt_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor.get('owner'), request_id], separators=(',', ':')).encode()).hexdigest()
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data,owner_id FROM objects WHERE kind='w24authorityreceipt' AND id=? AND session_id=?", (receipt_id, ctx.sid)).fetchone()
        if row:
            prior = json.loads(row['data'])
            if row['owner_id'] != ctx.actor['owner'] or prior['fingerprint'] != fingerprint:
                _fail('request_conflict', 'Request ID already used.', 409)
            return prior['result']
        channel_id = body['channelId']
        channel_authority._channel(db, channel_id)
        if not channel_authority._membership(db, channel_id, ctx.sid):
            _fail('not_found', 'Channel unavailable.', 404)
        revision = body['expectedRevision']
        if type(revision) is not int:
            _fail('invalid_request', 'Invalid revision.', 422)
        if action == 'approve':
            pack, current, owner = _load(db, ctx, body['packId'])
            if owner != ctx.actor['owner'] or pack['withdrawn'] or not _live(pack['expiresAt']):
                _fail('not_found', 'Pack unavailable.', 404)
            if current != revision:
                _fail('stale_revision', 'Pack changed; reload.', 409)
            if not pack['items'] or any(item.get('kind') not in ('approvedSource', 'approvedProfile', 'approvedModel', 'approvedActivity', 'approvedClaim', 'approvedEdition') or item.get('ref', {}).get('channelId') != channel_id for item in pack['items']):
                _fail('unsupported_item', 'Approve each source for this channel first.', 422)
            _items(ctx, pack['items'])
            grant_id = store.ident()
            _insert(db, 'w24packgrant', grant_id, ctx, {'channelId': channel_id, 'packId': body['packId'], 'packRevision': revision, 'active': True})
            result_revision = 1
        else:
            grant_id = _id(body['grantId'])
            grant = db.execute("SELECT data,revision,owner_id FROM objects WHERE kind='w24packgrant' AND id=? AND session_id=?", (grant_id, ctx.sid)).fetchone()
            if not grant or grant['owner_id'] != ctx.actor['owner']:
                _fail('not_found', 'Approval unavailable.', 404)
            value = json.loads(grant['data'])
            if value.get('channelId') != channel_id or value.get('active') is not True:
                _fail('not_found', 'Approval unavailable.', 404)
            if grant['revision'] != revision:
                _fail('stale_revision', 'Approval changed; reload.', 409)
            value['active'] = False
            result_revision = revision + 1
            db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w24packgrant' AND id=?", (_canonical(value), result_revision, grant_id))
        result = {'requestId': request_id, 'state': 'committed', 'channelId': channel_id, 'grantId': grant_id, 'revision': result_revision, 'withdrawn': action == 'withdraw'}
        _insert(db, 'w24authorityreceipt', receipt_id, ctx, {'fingerprint': fingerprint, 'result': result})
        db.commit()
        return result


def _approved_pack(ctx, db, channel_id, grant_id, grant_revision, creator=True):
    channel_authority.require_member(ctx, channel_id, creator=creator)
    row = db.execute("SELECT data,revision,session_id FROM objects WHERE kind='w24packgrant' AND id=?", (_id(grant_id),)).fetchone()
    if not row or type(grant_revision) is not int or row['revision'] != grant_revision:
        _fail('not_found', 'Approved pack unavailable.', 404)
    grant = json.loads(row['data'])
    if grant.get('active') is not True or grant.get('channelId') != channel_id or not channel_authority._membership(db, channel_id, row['session_id']):
        _fail('not_found', 'Approved pack unavailable.', 404)
    source = db.execute("SELECT data,revision FROM objects WHERE kind='w24pack' AND id=? AND session_id=?", (grant['packId'], row['session_id'])).fetchone()
    if not source or source['revision'] != grant['packRevision']:
        _fail('stale_revision', 'Approved pack changed; reload.', 409)
    pack = json.loads(source['data'])
    if pack['withdrawn'] or not _live(pack['expiresAt']):
        _fail('not_found', 'Approved pack unavailable.', 404)
    if any(item.get('kind') not in ('approvedSource', 'approvedProfile', 'approvedModel', 'approvedActivity', 'approvedClaim', 'approvedEdition') or item.get('ref', {}).get('channelId') != channel_id for item in pack['items']):
        _fail('not_found', 'Approved pack unavailable.', 404)
    # Each approved item retains its own authority. Revoking one grant must not
    # suppress independent still-current items in the same approved pack.
    available = []
    for item in pack['items']:
        try:
            available.append(validate_item(ctx, item))
        except Phase10Error as exc:
            if exc.code not in ('not_found', 'stale_context', 'stale_revision'):
                raise
    return available


def _pack_items(channel_id, grant_id, revision, items):
    return [{'kind': {'approvedSource': 'approvedPackSource', 'approvedProfile': 'approvedPackProfile', 'approvedModel': 'approvedPackModel', 'approvedActivity': 'approvedPackActivity', 'approvedClaim': 'approvedPackClaim', 'approvedEdition': 'approvedPackEdition'}[item['kind']],
             'ref': {'channelId': channel_id, 'grantId': grant_id,
                     'sourceGrantId': item['ref']['grantId'], 'sourceRevision': item['revision']},
             'revision': revision} for item in items]


def withdraw_pack_grant(ctx, channel_id, grant_id, revision):
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        channel_authority.require_member(ctx, channel_id, creator=True)
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT data,revision,owner_id FROM objects WHERE kind='w24packgrant' AND id=? AND session_id=?", (_id(grant_id), ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _fail('not_found', 'Approval unavailable.', 404)
        grant = json.loads(row['data'])
        if grant.get('channelId') != channel_id or grant.get('active') is not True:
            _fail('not_found', 'Approval unavailable.', 404)
        if type(revision) is not int or row['revision'] != revision:
            _fail('stale_revision', 'Approval changed; reload.', 409)
        grant['active'] = False
        db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w24packgrant' AND id=?", (_canonical(grant), grant_id))
        db.commit()
        return {'grantId': grant_id, 'revision': revision + 1, 'withdrawn': True}


def _insert(db, kind, oid, ctx, value):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
               (kind, oid, ctx.sid, ctx.actor['owner'], _canonical(value), store.now()))


def _claim_projection(ctx, item):
    # The upstream query also includes the creator's private claims. Recompute
    # relationships exclusively from creator-scoped claims so those private
    # records cannot affect even the status of a pack reference.
    now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    result = waves22_claims.query(ctx, item['ref']['topic'], now, now)
    claims = [c for c in result['current'] + result['prior'] if c['scope'] == 'creator']
    selected = next((c for c in claims if c['id'] == item['ref']['claimId']
                     and c['revision'] == item['revision']), None)
    if selected is None:
        _fail('not_found', 'Item unavailable.', 404)
    active = [c for c in claims if c['validFrom'] <= now and c['eventTime'] <= now
              and (c['validUntil'] is None or now < c['validUntil'])]
    ids = {(c['id'], c['revision']) for c in active}
    superseded, disputed = set(), set()
    for claim in active:
        for relation in claim['relations']:
            target = (relation['claimId'], relation['revision'])
            if target in ids:
                if relation['type'] == 'supersedes':
                    superseded.add(target)
                else:
                    disputed.update((target, (claim['id'], claim['revision'])))
    identity = (selected['id'], selected['revision'])
    status = ('retired' if identity not in ids or identity in superseded else
              'disputed' if identity in disputed else 'current')
    return {'status': status, 'claim': selected}


def preview(ctx, body):
    """Inspect candidate references against an exact current pack revision."""
    if not isinstance(body, dict) or set(body) not in ({'packId', 'expectedRevision', 'items'}, {'packId', 'expectedRevision', 'sourcePackId', 'sourceRevision'}, {'packId', 'expectedRevision', 'channelId', 'grantId', 'grantRevision'}):
        _fail('invalid_request', 'Invalid preview.', 422)
    if type(body['expectedRevision']) is not int or body['expectedRevision'] < 1:
        _fail('invalid_request', 'Invalid revision.', 422)
    if 'items' in body and (not isinstance(body['items'], list) or len(body['items']) > 100):
        _fail('invalid_request', 'Select at most 100 items.', 422)
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        pack, revision, owner = _load(db, ctx, body['packId'])
        if owner != ctx.actor['owner'] or pack['withdrawn'] or not _live(pack['expiresAt']):
            _fail('not_found', 'Pack unavailable.', 404)
        if revision != body['expectedRevision']:
            _fail('stale_revision', 'Pack changed; reload.', 409)
        if 'grantId' in body:
            candidates = _pack_items(body['channelId'], body['grantId'], body['grantRevision'],
                                     _approved_pack(ctx, db, body['channelId'], body['grantId'], body['grantRevision']))
        elif 'sourcePackId' in body:
            if type(body['sourceRevision']) is not int or body['sourceRevision'] < 1:
                _fail('invalid_request', 'Invalid source revision.', 422)
            source, source_revision, source_owner = _load(db, ctx, body['sourcePackId'])
            if source_owner != ctx.actor['owner'] or source['withdrawn'] or not _live(source['expiresAt']):
                _fail('not_found', 'Source pack unavailable.', 404)
            if source_revision != body['sourceRevision']:
                _fail('stale_revision', 'Source pack changed; reload.', 409)
            candidates = source['items']
        else:
            candidates = body['items']
        result = []
        for index, item in enumerate(candidates):
            try:
                resolved = validate_item(ctx, item)
                result.append({'index': index, 'status': 'eligible', 'item': resolved})
            except Phase10Error as exc:
                if exc.code not in ('not_found', 'stale_context', 'stale_revision', 'unsupported_item'):
                    raise
                result.append({'index': index, 'status': 'unavailable'})
        existing = {_identity(item): item for item in pack['items']}
        for entry in result:
            if entry['status'] == 'eligible':
                key = _identity(entry['item'])
                if key in existing and existing[key] != entry['item']:
                    entry['status'] = 'conflict'
                    entry['conflictId'] = key
        return {'packId': body['packId'], 'revision': revision, 'items': result,
                'crossSession': 'approved-grants'}


def read(ctx, pack_id):
    """Project current live references; inaccessible references never appear."""
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') not in ('creator', 'viewer'):
            _fail('not_found', 'Pack unavailable.', 404)
        if ctx.actor.get('role') == 'creator':
            _creator(ctx)
        pack, revision, owner = _load(db, ctx, pack_id)
        if pack['withdrawn'] or not _live(pack['expiresAt']):
            _fail('not_found', 'Pack unavailable.', 404)
        visible = []
        for item in pack['items']:
            try:
                resolved = validate_item(ctx, item)
                if resolved['kind'] == 'claim':
                    resolved['projection'] = _claim_projection(ctx, resolved)
                elif resolved['kind'] == 'approvedSource':
                    resolved['projection'] = channel_authority.project_source(ctx, resolved['ref']['channelId'], resolved['ref']['grantId'], resolved['revision'])
                elif resolved['kind'] == 'approvedPackSource':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_source(ctx, ref['channelId'], ref['sourceGrantId'], ref['sourceRevision'])
                elif resolved['kind'] == 'approvedProfile':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_profile(ctx, ref['channelId'], ref['grantId'], resolved['revision'])
                elif resolved['kind'] == 'approvedPackProfile':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_profile(ctx, ref['channelId'], ref['sourceGrantId'], ref['sourceRevision'])
                elif resolved['kind'] == 'approvedModel':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_model(ctx, ref['channelId'], ref['grantId'], resolved['revision'])
                elif resolved['kind'] == 'approvedPackModel':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_model(ctx, ref['channelId'], ref['sourceGrantId'], ref['sourceRevision'])
                elif resolved['kind'] == 'approvedActivity':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_activity(ctx, ref['channelId'], ref['grantId'], resolved['revision'])
                elif resolved['kind'] == 'approvedPackActivity':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_activity(ctx, ref['channelId'], ref['sourceGrantId'], ref['sourceRevision'])
                elif resolved['kind'] == 'approvedClaim':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_claim(ctx, ref['channelId'], ref['grantId'], resolved['revision'])
                elif resolved['kind'] == 'approvedPackClaim':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_claim(ctx, ref['channelId'], ref['sourceGrantId'], ref['sourceRevision'])
                elif resolved['kind'] == 'approvedEdition':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_edition(ctx, ref['channelId'], ref['grantId'], resolved['revision'])
                elif resolved['kind'] == 'approvedPackEdition':
                    ref = resolved['ref']
                    resolved['projection'] = channel_authority.project_edition(ctx, ref['channelId'], ref['sourceGrantId'], ref['sourceRevision'])
                visible.append(resolved)
            except Phase10Error as exc:
                if exc.code not in ('not_found', 'stale_context', 'stale_revision'):
                    raise
        result = {'packId': pack_id, 'revision': revision, 'expiresAt': pack['expiresAt'],
                  'items': visible, 'binding': 'session', 'crossSession': 'approved-grants'}
        if ctx.actor.get('role') == 'creator':
            result['setupReviewed'] = bool(pack.get('setupReview') == {'revision': revision, 'itemsHash': _fingerprint(pack['items'])})
        return result


def mutate(ctx, body):
    """Commit session-scoped create/update/withdraw and an exact actor receipt."""
    if not isinstance(body, dict) or body.get('action') not in ('create', 'update', 'withdraw', 'import', 'importApproved', 'reviewSetup'):
        _fail('invalid_request', 'Invalid action.', 422)
    action = body['action']
    fields = {'action', 'requestId', 'expectedRevision'}
    if action != 'create': fields.add('packId')
    if action in ('create', 'update'): fields.update(('items', 'expiresAt'))
    if action == 'update': fields.add('choices')
    if action == 'import': fields.update(('sourcePackId', 'sourceRevision', 'choices'))
    if action == 'importApproved': fields.update(('channelId', 'grantId', 'grantRevision', 'choices'))
    if set(body) != fields or type(body['expectedRevision']) is not int or body['expectedRevision'] < 0:
        _fail('invalid_request', 'Invalid fields.', 422)
    request_id = _id(body['requestId']); fingerprint = _fingerprint(body)
    receipt_id = _fingerprint([ctx.sid, ctx.actor['owner'], request_id])
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        db.execute('BEGIN IMMEDIATE')
        receipt = db.execute("SELECT data FROM objects WHERE kind='w24packreceipt' AND id=? AND session_id=?", (receipt_id, ctx.sid)).fetchone()
        if receipt:
            value = json.loads(receipt['data'])
            if value['fingerprint'] != fingerprint:
                _fail('request_conflict', 'Request ID already used.', 409)
            pack, revision, owner = _load(db, ctx, value['packId'])
            if owner != ctx.actor['owner']:
                _fail('not_found', 'Operation unavailable.', 404)
            return {'operation': {'requestId': request_id, 'state': 'committed'}, 'packId': value['packId'], 'revision': value['revision'], 'currentRevision': revision}
        if action == 'create':
            if body['expectedRevision'] != 0: _fail('stale_revision', 'Pack changed; reload.', 409)
            pack_id = store.ident(); revision = 1
        else:
            pack_id = _id(body['packId'])
            old, previous, owner = _load(db, ctx, pack_id)
            if owner != ctx.actor['owner']: _fail('not_found', 'Pack unavailable.', 404)
            if previous != body['expectedRevision'] or old['withdrawn']:
                _fail('stale_revision', 'Pack changed; reload.', 409)
            if action != 'withdraw' and not _live(old['expiresAt']):
                _fail('expired', 'Pack expired.', 409)
            revision = previous + 1
        if action == 'reviewSetup':
            items = _items(ctx, old['items'])
            if not items or not any(item['kind'] in _SETUP_DEFINITION_FIELDS or item['kind'] == 'sharedGlossary' for item in items):
                _fail('invalid_item', 'Choose setup definitions to review.', 422)
            value = {'withdrawn': False, 'expiresAt': old['expiresAt'], 'items': items,
                     'setupReview': {'revision': revision, 'itemsHash': _fingerprint(items)}}
        elif action == 'withdraw':
            value = {'withdrawn': True, 'expiresAt': None, 'items': []}
        elif action == 'importApproved':
            incoming = _pack_items(body['channelId'], body['grantId'], body['grantRevision'],
                                   _approved_pack(ctx, db, body['channelId'], body['grantId'], body['grantRevision']))
            value = {'withdrawn': False, 'expiresAt': old['expiresAt'],
                     'items': _items(ctx, _merge(old['items'], incoming, body['choices']))}
        elif action == 'import':
            if type(body['sourceRevision']) is not int or body['sourceRevision'] < 1:
                _fail('invalid_request', 'Invalid source revision.', 422)
            source, source_rev, source_owner = _load(db, ctx, body['sourcePackId'])
            if source_owner != ctx.actor['owner'] or source['withdrawn'] or not _live(source['expiresAt']):
                _fail('not_found', 'Source pack unavailable.', 404)
            if source_rev != body['sourceRevision']:
                _fail('stale_revision', 'Source pack changed; reload.', 409)
            if not _live(old['expiresAt']): _fail('expired', 'Pack expired.', 409)
            value = {'withdrawn': False, 'expiresAt': old['expiresAt'],
                     'items': _items(ctx, _merge(old['items'], source['items'], body['choices']))}
        else:
            expiry = _expiry(body['expiresAt'])
            if not _live(expiry): _fail('expired', 'Expiry must be in the future.', 422)
            items = _items(ctx, body['items'])
            if action == 'update':
                # Updates are complete replacement proposals: decisions guard changed identities.
                _merge(old['items'], items, body['choices'])
                for item in items:
                    key = _identity(item)
                    if body['choices'].get(key) == 'keep':
                        items[items.index(item)] = next(x for x in old['items'] if _identity(x) == key)
                items = _items(ctx, items)
            value = {'withdrawn': False, 'expiresAt': expiry, 'items': items}
        if action == 'create':
            _insert(db, 'w24pack', pack_id, ctx, value)
        else:
            db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w24pack' AND id=? AND session_id=?", (_canonical(value), revision, pack_id, ctx.sid))
        _insert(db, 'w24packreceipt', receipt_id, ctx, {'fingerprint': fingerprint, 'packId': pack_id, 'revision': revision})
        db.commit()
        return {'operation': {'requestId': request_id, 'state': 'committed'}, 'packId': pack_id, 'revision': revision, 'currentRevision': revision}


def receipt(ctx, request_id):
    """Recover only the authenticated creator's exact committed operation."""
    request_id = _id(request_id)
    with ctx.lock, store.connect() as db:
        _creator(ctx)
        rid = _fingerprint([ctx.sid, ctx.actor['owner'], request_id])
        row = db.execute("SELECT data,owner_id FROM objects WHERE kind='w24packreceipt' AND id=? AND session_id=?", (rid, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _fail('not_found', 'Operation unavailable.', 404)
        value = json.loads(row['data'])
        pack, revision, owner = _load(db, ctx, value['packId'])
        if owner != ctx.actor['owner']:
            _fail('not_found', 'Operation unavailable.', 404)
        return {'operation': {'requestId': request_id, 'state': 'committed'},
                'packId': value['packId'], 'revision': value['revision'],
                'currentRevision': revision}


def _same(actual, expected):
    if actual != expected:
        _fail('stale_context', 'Pack changed before delivery.', 409)


def select_archived_profile(ctx, body):
    """Select an exact accessible pack item and a receiving-session moment."""
    from . import waves23_speech_profiles as profiles
    if not isinstance(body, dict) or set(body) != {'requestId', 'packId', 'item', 'ref'}:
        _fail('invalid_request', 'A pack profile and source are required.', 422)
    profiles.token(body['requestId'])
    item = body['item']
    if not isinstance(item, dict) or item.get('kind') not in ('approvedProfile', 'approvedPackProfile'):
        _fail('invalid_item', 'An approved profile is required.', 422)
    ref = parse_ref(body['ref'])
    if ref['sessionId'] != ctx.sid:
        _fail('not_found', 'Source unavailable.', 404)
    with ctx.lock:
        ctx.resolve([ref])
        pack = read(ctx, body['packId'])
        if not any({k: entry[k] for k in ('kind', 'ref', 'revision')} == item for entry in pack['items']):
            _fail('not_found', 'Profile unavailable.', 404)
        oid = profiles.digest([ctx.sid, ctx.actor['owner']])
        rid = profiles.digest([ctx.sid, ctx.actor['owner'], body['requestId']])
        value = {'id': oid, 'packId': body['packId'], 'packRevision': pack['revision'], 'item': item, 'ref': ref}
        fingerprint = profiles.digest(body)
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute("SELECT data FROM objects WHERE kind='w24profilereceipt' AND id=? AND session_id=? AND owner_id=?", (rid, ctx.sid, ctx.actor['owner'])).fetchone()
            if previous:
                saved = json.loads(previous['data'])
                if saved['fingerprint'] != fingerprint:
                    _fail('request_conflict', 'Request ID belongs to another operation.')
                if current_archived_profile(ctx)[0] != saved['selection']:
                    _fail('stale_context', 'The selection changed.')
                return saved['selection']
            db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w24profileselection',?,?,?,1,?,?) ON CONFLICT(kind,id) DO UPDATE SET revision=objects.revision+1,data=excluded.data", (oid, ctx.sid, ctx.actor['owner'], _canonical(value), ctx.store.now()))
            db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w24profilereceipt',?,?,?,1,?,?)", (rid, ctx.sid, ctx.actor['owner'], _canonical({'fingerprint': fingerprint, 'selection': value}), ctx.store.now()))
            db.commit()
        return value


def _validate_archived_selection(ctx, selection):
    ctx.resolve([selection['ref']])
    pack = read(ctx, selection['packId'])
    if pack['revision'] != selection['packRevision'] or not any({k: entry[k] for k in ('kind', 'ref', 'revision')} == selection['item'] for entry in pack['items']):
        _fail('stale_context', 'The pack profile changed.')
    item = selection['item']; ref = item['ref']
    gid = ref['sourceGrantId'] if item['kind'] == 'approvedPackProfile' else ref['grantId']
    rev = ref['sourceRevision'] if item['kind'] == 'approvedPackProfile' else item['revision']
    obj = channel_authority.approved_profile_for_generation(ctx, ref['channelId'], gid, rev)
    return selection, obj


def current_archived_profile(ctx):
    from . import waves23_speech_profiles as profiles
    with ctx.lock:
        ctx.check_actor()
        oid = profiles.digest([ctx.sid, ctx.actor['owner']])
        selection = ctx.store.get('w24profileselection', oid, ctx.sid)
        if not selection:
            _fail('not_found', 'Profile selection unavailable.', 404)
        selection.pop('_revision', None)
        return _validate_archived_selection(ctx, selection)


def archived_profile_receipt(ctx, request_id):
    """Read the original actor-bound receipt without selecting again."""
    from . import waves23_speech_profiles as profiles
    profiles.token(request_id)
    with ctx.lock:
        ctx.check_actor()
        rid = profiles.digest([ctx.sid, ctx.actor['owner'], request_id])
        with ctx.store.connect() as db:
            row = db.execute("SELECT data FROM objects WHERE kind='w24profilereceipt' AND id=? AND session_id=? AND owner_id=?", (rid, ctx.sid, ctx.actor['owner'])).fetchone()
        if not row:
            _fail('not_found', 'Operation unavailable.', 404)
        selection = json.loads(row['data'])['selection']
        _validate_archived_selection(ctx, selection)
        oid = profiles.digest([ctx.sid, ctx.actor['owner']])
        current = ctx.store.get('w24profileselection', oid, ctx.sid)
        if current:
            current.pop('_revision', None)
        return {'operation': {'requestId': request_id, 'state': 'committed'},
                'selection': selection, 'current': current == selection}


def archived_generation_plan(ctx, run_id, request_id):
    from . import waves23_speech_profiles as profiles, waves21_speech_runtime as speech
    with ctx.lock:
        selection, obj = current_archived_profile(ctx)
        rid = profiles.digest([ctx.sid, ctx.actor['owner'], profiles.token(request_id)])
        binding = ctx.store.get('w24profilebinding', rid, ctx.sid)
        if not binding or binding.get('runId') != run_id or binding.get('selection') != selection:
            _fail('stale_context', 'Speech binding unavailable.')
        marker = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id], separators=(',', ':')).encode()).hexdigest()
        if ctx.store.get(speech.GENERATION_KIND, marker, ctx.sid) or ctx.store.get(profiles.BINDING, rid, ctx.sid):
            _fail('request_conflict', 'Another speech request uses this request ID.')
        identity, plan, _ = profiles._approved_plan(ctx, binding['request'], selection, obj, True)
        return identity, plan


def prepare_archived_generation(ctx, body):
    from . import waves23_speech_profiles as profiles, waves21_speech_runtime as speech, waves21_speech_stream as stream
    fields = {'runId', 'segmentId', 'expectedRevision', 'requestId', 'outputFormat', 'profileId', 'profileRevision'}
    if not isinstance(body, dict) or set(body) != fields:
        _fail('invalid_request', 'A speech run and selected profile are required.', 422)
    for key in ('runId', 'segmentId', 'requestId', 'profileId'):
        profiles.token(body[key])
    if (type(body['expectedRevision']) is not int or body['expectedRevision'] < 1 or
            type(body['profileRevision']) is not int or body['profileRevision'] < 1 or
            not isinstance(body['outputFormat'], str) or len(body['outputFormat']) > 100):
        _fail('invalid_request', 'Invalid speech request.', 422)
    with ctx.lock:
        selection, obj = current_archived_profile(ctx)
        if body['profileId'] != obj['id'] or body['profileRevision'] != obj['_revision']:
            _fail('stale_context', 'Selected profile changed.')
        _, _, run = profiles._approved_plan(ctx, body, selection, obj, False)
        rid = profiles.digest([ctx.sid, ctx.actor['owner'], body['requestId']])
        binding = {'id': rid, 'runId': body['runId'], 'requestId': body['requestId'],
                   'selection': selection, 'request': dict(body)}
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute("SELECT data,owner_id FROM objects WHERE kind='w24profilebinding' AND id=? AND session_id=?", (rid, ctx.sid)).fetchone()
            if previous:
                if previous['owner_id'] != ctx.actor['owner'] or json.loads(previous['data']) != binding:
                    _fail('request_conflict', 'Request ID belongs to another operation.')
            else:
                marker = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], body['requestId']], separators=(',', ':')).encode()).hexdigest()
                if (db.execute('SELECT 1 FROM objects WHERE kind=? AND id=? AND session_id=?', (speech.GENERATION_KIND, marker, ctx.sid)).fetchone() or
                        db.execute('SELECT 1 FROM objects WHERE kind=? AND id=? AND session_id=?', (profiles.BINDING, rid, ctx.sid)).fetchone()):
                    _fail('request_conflict', 'Another speech request uses this request ID.')
                if body['requestId'] in run['state'].get('intents', {}):
                    _fail('request_conflict', 'An existing speech intent cannot be adopted.')
                try:
                    run['state'] = stream.prepare_intent(run['state'], body['segmentId'], body['expectedRevision'], 'audio', body['requestId'], lambda *_: True)
                except stream.SpeechStreamError:
                    _fail('stale_context', 'Speech intent cannot be prepared.')
                revision = run.pop('_revision')
                changed = db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?', (_canonical(run), speech.KIND, body['runId'], ctx.sid, revision)).rowcount
                if changed != 1:
                    _fail('stale_context', 'Speech changed before preparation.')
                db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w24profilebinding',?,?,?,1,?,?)", (rid, ctx.sid, ctx.actor['owner'], _canonical(binding), ctx.store.now()))
            db.commit()
        return archived_generation_binding(ctx, body['runId'], body['requestId'])


def archived_generation_binding(ctx, run_id, request_id):
    from . import waves23_speech_profiles as profiles
    identity, _ = archived_generation_plan(ctx, run_id, request_id)
    return {'runId': run_id, 'requestId': request_id, 'identityDigest': profiles.digest(identity.__dict__)}


def archived_generation_subscriber(ctx, run_id, request_id):
    from . import waves23_speech_profiles as profiles
    from .waves20_delivery import Subscriber
    with ctx.lock:
        identity, plan = archived_generation_plan(ctx, run_id, request_id)
        rid = profiles.digest([ctx.sid, ctx.actor['owner'], request_id])
        binding = ctx.store.get('w24profilebinding', rid, ctx.sid)
        return identity, Subscriber(actor=ctx.actor['owner'], stream=run_id, sequence=binding['request']['expectedRevision'], authority=rid), plan


def _archived_context(sid, owner, run_id):
    from . import waves21_speech_runtime as speech
    run = store.get(speech.KIND, run_id, sid)
    if not run or run.get('owner') != owner:
        _fail('not_found', 'Speech run unavailable.', 404)
    with store.connect() as db:
        row = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?', (run['credentialHash'],)).fetchone()
    if not row or row['session_id'] != sid or row['owner_id'] != owner:
        _fail('not_found', 'Speech credential unavailable.', 404)
    return speech._StoredContext(sid, {'role': row['role'], 'sid': sid, 'owner': owner}, run['credentialHash'])


def resolve_archived_generation(identity):
    from .waves20_delivery import Identity
    if not isinstance(identity, Identity) or not identity.private_actor:
        return None
    matches = []
    with store.LOCK, store.connect() as db:
        rows = db.execute("SELECT data FROM objects WHERE kind='w24profilebinding' AND session_id=? AND owner_id=?", (identity.session, identity.private_actor)).fetchall()
        for row in rows:
            try:
                binding = json.loads(row['data'])
                ctx = _archived_context(identity.session, identity.private_actor, binding['runId'])
                current, plan = archived_generation_plan(ctx, binding['runId'], binding['requestId'])
                if current == identity:
                    matches.append(plan)
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
    return matches[0] if matches and all(plan == matches[0] for plan in matches) else None


def eligible_archived_subscriber(identity, subscriber):
    from .waves20_delivery import Identity, Subscriber
    if not isinstance(identity, Identity) or not isinstance(subscriber, Subscriber) or not identity.private_actor or subscriber.actor != identity.private_actor:
        return False
    try:
        with store.LOCK:
            binding = store.get('w24profilebinding', subscriber.authority, identity.session)
            if not binding or binding.get('runId') != subscriber.stream:
                return False
            ctx = _archived_context(identity.session, subscriber.actor, subscriber.stream)
            current, expected, _ = archived_generation_subscriber(ctx, subscriber.stream, binding['requestId'])
            return current == identity and expected == subscriber
    except (Phase10Error, KeyError, TypeError, ValueError):
        return False


def handle(handler, sid, actor, method, parts):
    """Unreleased route primitive; PRIMARY must mount and call final_guard."""
    ctx = session_authority(handler, sid, actor)
    if parts == ['packs', 'profile-generation'] and method == 'POST':
        body = handler.body()
        result = prepare_archived_generation(ctx, body)
        handler._w24_pack_final = lambda: _same(archived_generation_binding(ctx, result['runId'], result['requestId']), result)
        return 200, {'binding': result}
    if len(parts) == 4 and parts[:2] == ['packs', 'profile-generation'] and method == 'GET':
        result = archived_generation_binding(ctx, parts[2], parts[3])
        handler._w24_pack_final = lambda: _same(archived_generation_binding(ctx, parts[2], parts[3]), result)
        return 200, {'binding': result}
    if parts == ['packs', 'profile-selection'] and method == 'PUT':
        result = select_archived_profile(ctx, handler.body())
        handler._w24_pack_final = lambda: _same(current_archived_profile(ctx)[0], result)
        return 200, {'selection': result}
    if parts == ['packs', 'profile-selection'] and method == 'GET':
        from . import waves23_speech_profiles as profiles
        selection, obj = current_archived_profile(ctx)
        result = {'selection': selection, 'profile': profiles.projection(obj)}
        def profile_guard():
            current, profile = current_archived_profile(ctx)
            _same({'selection': current, 'profile': profiles.projection(profile)}, result)
        handler._w24_pack_final = profile_guard
        return 200, result
    if len(parts) == 3 and parts[:2] == ['packs', 'profile-selection-receipts'] and method == 'GET':
        result = archived_profile_receipt(ctx, parts[2])
        handler._w24_pack_final = lambda: _same(archived_profile_receipt(ctx, parts[2]), result)
        return 200, result
    if parts == ['channels', 'pack-grants'] and method == 'POST':
        body = handler.body()
        result = pack_grant_operation(ctx, body)
        if not result['withdrawn']:
            with ctx.lock, store.connect() as db:
                projection = _approved_pack(ctx, db, result['channelId'], result['grantId'], result['revision'])
            def pack_grant_guard():
                _same(channel_authority.capability_receipt(ctx, body['requestId']), result)
                with ctx.lock, store.connect() as db:
                    _same(_approved_pack(ctx, db, result['channelId'], result['grantId'], result['revision']), projection)
            handler._w24_pack_final = pack_grant_guard
        else:
            handler._w24_pack_final = lambda: _same(channel_authority.capability_receipt(ctx, body['requestId']), result)
        return 200, result
    if parts == ['channels', 'source-grants'] and method == 'POST':
        body = handler.body()
        result = channel_authority.source_operation(ctx, body)
        if not result['withdrawn']:
            projector = {'profile': channel_authority.project_profile, 'model': channel_authority.project_model, 'activity': channel_authority.project_activity, 'claim': channel_authority.project_claim, 'edition': channel_authority.project_edition}.get(body.get('kind'), channel_authority.project_source)
            projection = projector(ctx, result['channelId'], result['grantId'], result['revision'])
            def source_guard():
                _same(channel_authority.capability_receipt(ctx, body['requestId']), result)
                _same(projector(ctx, result['channelId'], result['grantId'], result['revision']), projection)
            handler._w24_pack_final = source_guard
        else:
            handler._w24_pack_final = lambda: _same(channel_authority.capability_receipt(ctx, body['requestId']), result)
        return 200, result
    if parts == ['channels', 'membership'] and method == 'POST':
        body = handler.body()
        result = channel_authority.membership_operation(ctx, body)
        if result.get('enrolled'):
            expected = {'channelId': result['channelId'], 'revision': result['revision'], 'enrolled': True}
            handler._w24_pack_final = lambda: _same(channel_authority.status(ctx, result['channelId']), expected)
        else:
            handler._w24_pack_final = lambda: _same(channel_authority.capability_receipt(ctx, body['requestId']), result)
        return 200, result
    if parts == ['channels', 'capabilities'] and method == 'POST':
        body = handler.body()
        if not isinstance(body, dict) or body.get('action') not in ('create', 'rotate'):
            _fail('invalid_request', 'Invalid operation.', 422)
        fields = {'action', 'requestId'}
        if body['action'] == 'rotate':
            fields.update(('channelId', 'expectedRevision'))
        if set(body) != fields:
            _fail('invalid_request', 'Invalid fields.', 422)
        result = channel_authority.capability_operation(ctx, body['requestId'], body['action'], body.get('channelId'), body.get('expectedRevision'))
        if result['capabilityAvailable']:
            expected = {'channelId': result['channelId'], 'revision': result['revision'], 'enrolled': True}
            handler._w24_pack_final = lambda: _same(channel_authority.status(ctx, result['channelId']), expected)
        else:
            handler._w24_pack_final = lambda: _same(channel_authority.capability_receipt(ctx, body['requestId']), result)
        return 200, result
    if len(parts) == 3 and parts[:2] == ['channels', 'operations'] and method == 'GET':
        result = channel_authority.capability_receipt(ctx, parts[2])
        handler._w24_pack_final = lambda: _same(channel_authority.capability_receipt(ctx, parts[2]), result)
        return 200, result
    if len(parts) == 2 and parts[0] == 'channels' and method == 'GET':
        result = channel_authority.status(ctx, parts[1])
        handler._w24_pack_final = lambda: _same(channel_authority.status(ctx, parts[1]), result)
        return 200, result
    if parts == ['packs', 'preview'] and method == 'POST':
        body = handler.body()
        result = preview(ctx, body)
        handler._w24_pack_final = lambda: _same(preview(ctx, body), result)
        return 200, result
    if parts == ['packs'] and method == 'POST':
        body = handler.body()
        result = mutate(ctx, body)
        handler._w24_pack_final = lambda: _same(receipt(ctx, body['requestId']), result)
        return 200, result
    if len(parts) == 2 and parts[0] == 'packs' and method == 'GET':
        result = read(ctx, parts[1])
        handler._w24_pack_final = lambda: _same(read(ctx, parts[1]), result)
        return 200, result
    if len(parts) == 3 and parts[:2] == ['packs', 'operations'] and method == 'GET':
        result = receipt(ctx, parts[2])
        handler._w24_pack_final = lambda: _same(receipt(ctx, parts[2]), result)
        return 200, result
    _fail('not_found', 'Route unavailable.', 404)


def final_guard(handler):
    """Caller holds store.LOCK continuously through guard, serialization and send."""
    guard = getattr(handler, '_w24_pack_final', None)
    if not callable(guard):
        _fail('not_found', 'Pack response unavailable.', 404)
    guard()


def cleanup_db(db, sid, owner=None):
    """Called by PRIMARY inside the existing session or owner deletion transaction."""
    if not db.in_transaction:
        raise ValueError('cleanup requires caller transaction')
    if owner is None:
        db.execute("DELETE FROM objects WHERE session_id=? AND kind IN ('w24pack','w24packreceipt','w24authorityreceipt','w24packgrant','w24archivegrant','w24channelmember','w24channel','w24profileselection','w24profilereceipt','w24profilebinding')", (sid,))
    else:
        db.execute("DELETE FROM objects WHERE session_id=? AND owner_id=? AND kind IN ('w24pack','w24packreceipt','w24authorityreceipt','w24packgrant','w24archivegrant','w24channelmember','w24channel','w24profileselection','w24profilereceipt','w24profilebinding')", (sid, owner))
