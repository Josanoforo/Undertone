"""Versioned speech profiles and private selections; no provider operations.

Creator-approved shared spoken forms are separate from private dictionaries.
"""
import hashlib
import json
import math
import re

from .phase10_common import Context, Phase10Error, parse_ref
from . import waves21_pronunciation as pronunciation
from . import waves21_speech_runtime as speech

PROFILE = 'w23speechprofile'
SELECTION = 'w23speechselection'
RECEIPT = 'w23speechreceipt'
BINDING = 'w23speechbinding'
FIELDS = {'language', 'engine', 'model', 'modelVersion', 'voiceId', 'voiceVersion',
          'adapterVersion', 'ruleSetId', 'ruleSetRevision', 'rate', 'qualityPreference', 'audienceVisible'}

def fail(code, message, status=409):
    raise Phase10Error(code, message, status)

def token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        fail('invalid_request', 'Invalid identifier.', 422)
    return value

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def validate(profile):
    if not isinstance(profile, dict) or set(profile) != FIELDS:
        fail('invalid_profile', 'A complete speech profile is required.', 422)
    for key in ('model', 'modelVersion', 'voiceId', 'voiceVersion', 'adapterVersion', 'ruleSetId'):
        token(profile[key])
    if profile['language'] not in ('en', 'es') or profile['engine'] not in ('local_neural', 'sapi', 'elevenlabs'):
        fail('invalid_profile', 'The language or engine is unsupported.', 422)
    if type(profile['ruleSetRevision']) is not int or profile['ruleSetRevision'] < 0:
        fail('invalid_profile', 'The rules revision is invalid.', 422)
    rate = profile['rate']
    if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not .5 <= rate <= 2:
        fail('invalid_profile', 'The rate is invalid.', 422)
    if profile['engine'] != 'local_neural' and rate != 1:
        fail('unsupported_controls', 'The selected engine does not support this rate.', 422)
    if profile['qualityPreference'] not in ('local_neural', 'explicit_selection'):
        fail('invalid_profile', 'The quality preference is invalid.', 422)
    if type(profile['audienceVisible']) is not bool:
        fail('invalid_profile', 'Audience visibility must be explicit.', 422)
    return dict(profile)

def load(ctx, profile_id):
    ctx.check_actor()
    obj = ctx.store.get(PROFILE, token(profile_id), ctx.sid)
    if not obj:
        fail('not_found', 'Speech profile unavailable.', 404)
    return obj

def check_access(ctx, obj):
    if ctx.actor.get('role') != 'creator' and not obj['profile']['audienceVisible']:
        fail('not_found', 'Speech profile unavailable.', 404)
    if ctx.actor.get('role') != 'creator' and not obj.get('approval'):
        fail('not_found', 'Speech profile unavailable.', 404)
    if ctx.actor.get('role') == 'creator' and ctx.actor.get('owner') != obj['owner']:
        fail('not_found', 'Speech profile unavailable.', 404)
    if ctx.actor.get('role') == 'creator':
        speech._rule_load(ctx, obj['profile']['ruleSetId'])
    rules = ctx.store.get(speech.RULE_KIND, obj['profile']['ruleSetId'], ctx.sid)
    if not rules or rules.get('owner') != obj['owner'] or rules.get('ruleset', {}).get('revision') != obj['profile']['ruleSetRevision']:
        fail('stale_profile', 'The pronunciation rules have changed.')
    with ctx.store.connect() as db:
        credential = db.execute("SELECT 1 FROM credentials WHERE hash=? AND role='creator' AND session_id=? AND owner_id=?",
                                (rules.get('credentialHash'), ctx.sid, obj['owner'])).fetchone()
    if not credential:
        fail('stale_profile', 'The profile owner is unavailable.')
    approval = obj.get('approval')
    if approval and (approval.get('ruleSetRevision') != rules['ruleset']['revision'] or
                     approval.get('ruleSetId') != obj['profile']['ruleSetId']):
        fail('stale_profile', 'The approved pronunciation forms have changed.')


def approve_profile(ctx, profile_id, body):
    """Publish exactly selected already-approved rules, never a private dictionary."""
    if not isinstance(body, dict) or set(body) != {'requestId', 'expectedRevision', 'ruleIds'}:
        fail('invalid_request', 'A revision and selected rule IDs are required.', 422)
    token(profile_id)
    ids = body['ruleIds']
    if (type(body['expectedRevision']) is not int or body['expectedRevision'] < 1 or
        not isinstance(ids, list) or len(ids) > 100):
        fail('invalid_request', 'The approval is invalid.', 422)
    for item in ids:
        token(item)
    if len(set(ids)) != len(ids):
        fail('invalid_request', 'The approval is invalid.', 422)
    if ctx.actor.get('role') != 'creator':
        fail('not_found', 'Speech profile unavailable.', 404)
    def apply(db):
        obj = load(ctx, profile_id)
        if obj['owner'] != ctx.actor.get('owner') or obj['_revision'] != body['expectedRevision']:
            fail('stale_profile', 'The profile has changed or is unavailable.')
        rules = speech._rule_load(ctx, obj['profile']['ruleSetId'])['ruleset']
        if rules['revision'] != obj['profile']['ruleSetRevision']:
            fail('stale_profile', 'The pronunciation rules have changed.')
        selected = {r['id']: r for r in rules['rules'] if r['approved']}
        if any(i not in selected for i in ids):
            fail('invalid_approval', 'Only current approved pronunciation forms may be selected.', 422)
        obj.pop('_revision')
        obj['approval'] = {'ruleSetId': rules['ruleSetId'], 'ruleSetRevision': rules['revision'],
                           'rules': [dict(selected[i]) for i in ids]}
        revision = body['expectedRevision'] + 1
        changed = db.execute('UPDATE objects SET revision=?,data=? WHERE kind=? AND id=? AND session_id=? AND owner_id=? AND revision=?',
                             (revision, json.dumps(obj, ensure_ascii=False), PROFILE, profile_id,
                              ctx.sid, ctx.actor['owner'], body['expectedRevision'])).rowcount
        if changed != 1:
            fail('stale_profile', 'The profile has changed.')
        return {'profileId': profile_id, 'revision': revision}
    return write(ctx, 'profile.approve', body['requestId'], {'id': profile_id, **body}, apply)

def projection(obj):
    p = obj['profile']
    return {'profileId': obj['id'], 'revision': obj['_revision'], **p,
            'capabilities': pronunciation.capabilities(p['engine'], p['model'], p['voiceId']),
            'availability': 'unknown', 'deliveryMode': 'buffered',
            'costMode': 'hosted_unknown' if p['engine'] == 'elevenlabs' else 'local'}

def visible_profiles(ctx):
    """Return only profiles the current actor may select, rechecking each rule."""
    ctx.check_actor()
    with ctx.store.connect() as db:
        rows = db.execute('SELECT id FROM objects WHERE kind=? AND session_id=?',
                          (PROFILE, ctx.sid)).fetchall()
    result = []
    for row in rows:
        try:
            obj = load(ctx, row['id'])
            check_access(ctx, obj)
        except Phase10Error:
            continue
        result.append(projection(obj))
    return sorted(result, key=lambda item: item['profileId'])

def installed_voices(ctx):
    """Expose only identities verified by the existing local installation authority."""
    ctx.check_actor()
    if ctx.actor.get('role') != 'creator':
        fail('not_found', 'Speech profile unavailable.', 404)
    from . import waves25_listening_authorities as authorities
    voices, unavailable = [], []
    for language in ('en', 'es'):
        descriptor = authorities.installed_voice_descriptor(language)
        if descriptor.get('ok') is True:
            voices.append({'language': language, 'engine': 'local_neural', **{
                key: descriptor[key] for key in ('model', 'modelVersion', 'voiceId',
                                                   'voiceVersion', 'adapterVersion')}})
        else:
            unavailable.append({'language': language, 'reason': descriptor['reason']})
    return {'voices': voices, 'unavailable': unavailable}

def write(ctx, operation, request_id, payload, apply):
    token(request_id)
    fp = digest({'operation': operation, 'payload': payload})
    rid = digest([ctx.sid, ctx.actor['owner'], request_id])
    with ctx.lock, ctx.store.connect() as db:
        ctx.check_actor()
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND session_id=? AND owner_id=?',
                           (RECEIPT, rid, ctx.sid, ctx.actor['owner'])).fetchone()
        if prior:
            receipt = json.loads(prior['data'])
            if receipt['fingerprint'] != fp:
                fail('request_conflict', 'The request ID belongs to another operation.')
            db.commit()
            return recover_result(ctx, receipt)
        result = apply(db)
        receipt = {'id': rid, 'requestId': request_id, 'operation': operation,
                   'fingerprint': fp, 'result': result}
        db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                   (RECEIPT, rid, ctx.sid, ctx.actor['owner'], json.dumps(receipt), ctx.store.now()))
        db.commit()
        return result

def save_profile(ctx, profile_id, body):
    if not isinstance(body, dict) or set(body) != {'requestId', 'expectedRevision', 'profile'}:
        fail('invalid_request', 'A profile, expected revision and request ID are required.', 422)
    profile = validate(body['profile'])
    if ctx.actor.get('role') != 'creator':
        fail('not_found', 'Speech profile unavailable.', 404)
    token(profile_id)
    if type(body['expectedRevision']) is not int or body['expectedRevision'] < 0:
        fail('invalid_request', 'The expected revision is invalid.', 422)
    def apply(db):
        rules = speech._rule_load(ctx, profile['ruleSetId'])['ruleset']
        if rules['revision'] != profile['ruleSetRevision']:
            fail('stale_profile', 'The pronunciation rules have changed.')
        row = db.execute('SELECT revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                         (PROFILE, profile_id, ctx.sid)).fetchone()
        if row is None and db.execute('SELECT 1 FROM objects WHERE kind=? AND id=?', (PROFILE, profile_id)).fetchone():
            fail('profile_unavailable', 'The profile ID is unavailable.', 409)
        expected = body['expectedRevision']
        obj = {'id': profile_id, 'owner': ctx.actor['owner'], 'profile': profile}
        if row is None and expected == 0:
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                       (PROFILE, profile_id, ctx.sid, ctx.actor['owner'], json.dumps(obj), ctx.store.now()))
            revision = 1
        elif row and row['owner_id'] == ctx.actor['owner'] and row['revision'] == expected:
            revision = expected + 1
            db.execute('UPDATE objects SET revision=?,data=? WHERE kind=? AND id=? AND session_id=?',
                       (revision, json.dumps(obj), PROFILE, profile_id, ctx.sid))
        else:
            fail('stale_profile', 'The profile has changed or is unavailable.')
        return {'profileId': profile_id, 'revision': revision}
    return write(ctx, 'profile.save', body['requestId'], {'id': profile_id, **body}, apply)

def select_profile(ctx, body):
    if not isinstance(body, dict) or set(body) != {'requestId', 'profileId', 'revision', 'ref'}:
        fail('invalid_request', 'Select a profile and current source.', 422)
    pid, ref = token(body['profileId']), parse_ref(body['ref'])
    if type(body['revision']) is not int or body['revision'] < 1:
        fail('invalid_request', 'The profile revision is invalid.', 422)
    def apply(db):
        ctx.resolve([ref])
        obj = load(ctx, pid)
        check_access(ctx, obj)
        if obj['_revision'] != body['revision']:
            fail('stale_profile', 'The profile has changed.')
        oid = digest([ctx.sid, ctx.actor['owner']])
        selection = {'id': oid, 'profileId': pid, 'revision': body['revision'], 'ref': ref}
        db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?) '
                   'ON CONFLICT(kind,id) DO UPDATE SET revision=objects.revision+1,data=excluded.data',
                   (SELECTION, oid, ctx.sid, ctx.actor['owner'], json.dumps(selection), ctx.store.now()))
        return selection
    return write(ctx, 'profile.select', body['requestId'], body, apply)

def current_selection(ctx):
    ctx.check_actor()
    obj = ctx.store.get(SELECTION, digest([ctx.sid, ctx.actor['owner']]), ctx.sid)
    if not obj:
        fail('not_found', 'Speech selection unavailable.', 404)
    ctx.resolve([obj['ref']])
    profile = load(ctx, obj['profileId'])
    check_access(ctx, profile)
    if profile['_revision'] != obj['revision']:
        fail('stale_profile', 'The selected profile has changed.')
    return obj, profile


def _approved_plan(ctx, body, selection, obj, require_intent):
    from .waves20_delivery import Identity
    from .waves20_job_bridge import settings_digest, validate_plan, SPOKEN_FORM_REVISION
    from . import waves21_speech_stream as stream
    run = speech._load(ctx, token(body['runId']))
    if run['ref'] != selection['ref']:
        fail('stale_context', 'The selected source does not match the speech run.')
    p, approval = obj['profile'], obj.get('approval')
    if not approval or p['engine'] not in ('local_neural', 'sapi'):
        fail('unavailable', 'The approved voice is unavailable.', 409)
    if SPOKEN_FORM_REVISION != pronunciation.SPOKEN_FORM_REVISION:
        fail('unavailable', 'Spoken-form execution is unavailable.')
    history = run['state']['segments'].get(body['segmentId']) if isinstance(body['segmentId'], str) else None
    event = history[-1] if history else None
    if (not event or event['state'] != 'final' or type(body['expectedRevision']) is not int or
        event['revision'] != body['expectedRevision']):
        fail('not_current_final', 'A current final segment is required.')
    if require_intent:
        intent = run['state'].get('intents', {}).get(body['requestId'])
        if (not intent or intent.get('segmentId') != body['segmentId'] or
            intent.get('revision') != body['expectedRevision'] or intent.get('eventDigest') != stream._digest(event)):
            fail('stale_context', 'The speech intent has changed.')
    ruleset = {'ruleSetId': approval['ruleSetId'], 'ownerId': obj['owner'], 'scope': 'shared',
               'revision': approval['ruleSetRevision'], 'rules': approval['rules']}
    request = {key: p[key] for key in ('engine', 'model', 'modelVersion', 'voiceId', 'voiceVersion', 'adapterVersion', 'rate')}
    request.update({'requestId': token(body['requestId']), 'outputFormat': body['outputFormat'], 'controls': [],
                    'ruleSetRevision': ruleset['revision'], 'scope': 'shared', 'text': event['text'],
                    'language': event['language'], 'sourceId': run['ref']['sourceId'],
                    'sourceRevision': run['ref']['sourceRevision']})
    try:
        result = pronunciation.resolve_rules(ruleset, request, ctx.actor, lambda *_: True)
    except pronunciation.PronunciationError:
        fail('invalid_request', 'The speech request is invalid.', 422)
    if not result['ready']:
        fail('unsupported_controls', 'The requested pronunciation controls are unavailable.', 422)
    rules = approval['rules']
    settings = {'engine': p['engine'], 'model': p['model'], 'voice': p['voiceId'],
                'outputFormat': body['outputFormat'], 'adapterVersion': p['adapterVersion'],
                'modelVersion': p['modelVersion'], 'speed': p['rate'], 'ruleSetId': approval['ruleSetId'],
                'ruleRevision': str(approval['ruleSetRevision']), 'ruleDigest': settings_digest(rules),
                'approvedRules': rules, 'controls': [], 'glossary': [], 'terminology': None, 'hostedBinding': None}
    partition = stream._digest(['w23-approved-private', ctx.sid, ctx.actor['owner'], speech._credential(ctx)])
    identity = Identity(session=ctx.sid, rights_partition=partition, source=run['ref']['sourceId'],
                        source_revision=str(run['ref']['sourceRevision']), translation_revision=result['generationKey'],
                        terminology_revision='none', text_digest=hashlib.sha256(result['originalText'].encode()).hexdigest(),
                        language=p['language'], engine=p['engine'], model=p['model'], voice=p['voiceId'],
                        settings_digest=settings_digest(settings), output_format=body['outputFormat'], private_actor=ctx.actor['owner'])
    plan = {'session': ctx.sid, 'rightsPartition': partition, 'source': identity.source,
            'sourceRevision': identity.source_revision, 'translationRevision': identity.translation_revision,
            'terminologyRevision': identity.terminology_revision, 'scope': 'private', 'privateActor': ctx.actor['owner'],
            'text': result['originalText'], 'sourceLanguage': event['language'], 'settings': settings}
    return identity, validate_plan(identity, plan), run


def prepare_approved_generation(ctx, body, selection, obj):
    from . import waves21_speech_stream as stream
    identity, _, run = _approved_plan(ctx, body, selection, obj, False)
    request_id = token(body['requestId'])
    binding_id = digest([ctx.sid, ctx.actor['owner'], request_id])
    intent = {'id': binding_id, 'runId': body['runId'], 'requestId': request_id,
              'profileId': obj['id'], 'profileRevision': obj['_revision'], 'selectionRef': selection['ref'],
              'fingerprint': digest(body), 'approvedRequest': dict(body)}
    try:
        state = stream.prepare_intent(run['state'], body['segmentId'], body['expectedRevision'],
                                      'audio', request_id, lambda *_: True)
    except stream.SpeechStreamError:
        fail('stale_context', 'The speech intent cannot be prepared.')
    with ctx.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        prior = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                           (BINDING, binding_id, ctx.sid)).fetchone()
        if db.execute('SELECT 1 FROM objects WHERE kind=? AND id=? AND session_id=?',
                      ('w24profilebinding', binding_id, ctx.sid)).fetchone():
            fail('request_conflict', 'An archived speech request already uses this request ID.')
        if prior:
            if prior['owner_id'] != ctx.actor['owner'] or json.loads(prior['data']) != intent:
                fail('request_conflict', 'Request ID already has different profile content.')
        else:
            if request_id in run['state'].get('intents', {}):
                fail('request_conflict', 'An existing speech intent cannot be adopted.')
            marker_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id], separators=(',', ':')).encode()).hexdigest()
            if db.execute('SELECT 1 FROM objects WHERE kind=? AND id=? AND session_id=?',
                          (speech.GENERATION_KIND, marker_id, ctx.sid)).fetchone():
                fail('request_conflict', 'An existing speech request cannot be adopted.')
            run['state'] = state
            rev = run.pop('_revision')
            changed = db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?',
                                 (json.dumps(run, ensure_ascii=False), speech.KIND, body['runId'], ctx.sid, rev)).rowcount
            if changed != 1:
                fail('stale_context', 'Speech changed before preparation.')
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                       (BINDING, binding_id, ctx.sid, ctx.actor['owner'], json.dumps(intent), ctx.store.now()))
        db.commit()
    return generation_binding(ctx, body['runId'], request_id)


def approved_generation_plan(ctx, run_id, request_id):
    with ctx.lock:
        selection, obj = current_selection(ctx)
        record = ctx.store.get(BINDING, digest([ctx.sid, ctx.actor['owner'], token(request_id)]), ctx.sid)
        if (not record or record.get('runId') != run_id or record.get('profileId') != obj['id'] or
            record.get('profileRevision') != obj['_revision'] or record.get('selectionRef') != selection['ref'] or
            not isinstance(record.get('approvedRequest'), dict)):
            fail('stale_profile', 'The approved speech request is unavailable.')
        marker_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id], separators=(',', ':')).encode()).hexdigest()
        if ctx.store.get(speech.GENERATION_KIND, marker_id, ctx.sid):
            fail('request_conflict', 'Another speech request uses this request ID.')
        identity, plan, _ = _approved_plan(ctx, record['approvedRequest'], selection, obj, True)
        return identity, plan


def approved_generation_subscriber(ctx, run_id, request_id):
    """Create the existing private subscriber from a current approved intent."""
    from .waves20_delivery import Subscriber
    with ctx.lock:
        identity, plan = approved_generation_plan(ctx, run_id, request_id)
        record = ctx.store.get(BINDING, digest([ctx.sid, ctx.actor['owner'], token(request_id)]), ctx.sid)
        subscriber = Subscriber(actor=ctx.actor['owner'], stream=run_id,
                                sequence=record['approvedRequest']['expectedRevision'], authority=record['id'])
        return identity, subscriber, plan


def _stored_approved_context(sid, owner, run_id):
    from . import store
    run = store.get(speech.KIND, run_id, sid)
    if not run or run.get('owner') != owner:
        fail('not_found', 'Speech run unavailable.', 404)
    return speech._StoredContext(sid, {'role': 'viewer', 'sid': sid, 'owner': owner}, run['credentialHash'])


def resolve_approved_generation(identity):
    """Reconstruct a worker plan using persisted viewer authority, without a token."""
    from . import store
    from .waves20_delivery import Identity
    if not isinstance(identity, Identity) or not identity.private_actor:
        return None
    matches = []
    with store.LOCK, store.connect() as db:
        rows = db.execute('SELECT data FROM objects WHERE kind=? AND session_id=? AND owner_id=?',
                          (BINDING, identity.session, identity.private_actor)).fetchall()
        for row in rows:
            try:
                record = json.loads(row['data'])
                if not isinstance(record.get('approvedRequest'), dict):
                    continue
                ctx = _stored_approved_context(identity.session, identity.private_actor, record['runId'])
                current, plan = approved_generation_plan(ctx, record['runId'], record['requestId'])
                if current == identity:
                    matches.append(plan)
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
    return matches[0] if matches and all(plan == matches[0] for plan in matches) else None


def eligible_approved_subscriber(identity, subscriber):
    """Recheck subscriber and exact persisted viewer capability at delivery fences."""
    from . import store
    from .waves20_delivery import Identity, Subscriber
    if (not isinstance(identity, Identity) or not isinstance(subscriber, Subscriber) or
        not identity.private_actor or subscriber.actor != identity.private_actor):
        return False
    try:
        with store.LOCK:
            record = store.get(BINDING, subscriber.authority, identity.session)
            if not record or record.get('runId') != subscriber.stream:
                return False
            ctx = _stored_approved_context(identity.session, subscriber.actor, subscriber.stream)
            current, expected, _ = approved_generation_subscriber(ctx, subscriber.stream, record['requestId'])
            return current == identity and expected == subscriber
    except (Phase10Error, KeyError, TypeError, ValueError):
        return False

def prepare_selected_generation(ctx, body):
    if not isinstance(body, dict) or set(body) != {'runId', 'segmentId', 'expectedRevision', 'requestId', 'outputFormat', 'profileId', 'profileRevision'}:
        fail('invalid_request', 'A speech run and current segment are required.', 422)
    for key in ('runId', 'segmentId', 'requestId', 'profileId'):
        token(body[key])
    if (type(body['expectedRevision']) is not int or body['expectedRevision'] < 1 or
        type(body['profileRevision']) is not int or body['profileRevision'] < 1 or
        not isinstance(body['outputFormat'], str) or len(body['outputFormat']) > 100):
        fail('invalid_request', 'A current segment, profile revision and audio format are required.', 422)
    with ctx.lock:
        selection, obj = current_selection(ctx)
        if body['profileId'] != obj['id'] or type(body['profileRevision']) is not int or body['profileRevision'] != obj['_revision']:
            fail('stale_profile', 'The selected profile has changed.')
        if ctx.actor.get('role') != 'creator':
            return prepare_approved_generation(ctx, body, selection, obj)
        run_id = token(body['runId'])
        run = speech._load(ctx, run_id)
        if run['ref'] != selection['ref']:
            fail('stale_context', 'The selected source does not match the speech run.')
        p = obj['profile']
        if p['engine'] not in ('local_neural', 'sapi'):
            fail('unavailable', 'The selected voice is unavailable for this speech request.', 409)
        request = {key: p[key] for key in ('ruleSetId', 'engine', 'model', 'modelVersion',
                   'voiceId', 'voiceVersion', 'adapterVersion', 'rate')}
        request.update({key: body[key] for key in ('segmentId', 'expectedRevision', 'requestId', 'outputFormat')})
        request.update({'targetLanguage': p['language'], 'controls': []})
        request_id = token(body['requestId'])
        binding_id = digest([ctx.sid, ctx.actor['owner'], request_id])
        intent = {'id': binding_id, 'runId': run_id, 'requestId': request_id,
                  'profileId': obj['id'], 'profileRevision': obj['_revision'],
                  'selectionRef': selection['ref'], 'fingerprint': digest(body)}
        # Commit the profile association before Wave 21 creates its own durable
        # marker. A crash between the two is recovered only with the same input.
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                             (BINDING, binding_id, ctx.sid)).fetchone()
            if db.execute('SELECT 1 FROM objects WHERE kind=? AND id=? AND session_id=?',
                          ('w24profilebinding', binding_id, ctx.sid)).fetchone():
                fail('request_conflict', 'An archived speech request already uses this request ID.')
            if row:
                if row['owner_id'] != ctx.actor['owner'] or json.loads(row['data']) != intent:
                    fail('request_conflict', 'Request ID already has different profile content.')
            else:
                if request_id in run['state'].get('intents', {}):
                    fail('request_conflict', 'An existing speech intent cannot be adopted.')
                speech_marker = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id],
                                               separators=(',', ':')).encode()).hexdigest()
                if db.execute('SELECT 1 FROM objects WHERE kind=? AND id=? AND session_id=?',
                              (speech.GENERATION_KIND, speech_marker, ctx.sid)).fetchone():
                    fail('request_conflict', 'An existing speech request has no profile association.')
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                           (BINDING, binding_id, ctx.sid, ctx.actor['owner'], json.dumps(intent), ctx.store.now()))
            db.commit()
        speech.prepare_generation(ctx, run_id, request)
        return generation_binding(ctx, run_id, request_id)


def generation_binding(ctx, run_id, request_id):
    """Reconstruct the existing private identity and bind current selection."""
    with ctx.lock:
        selection, obj = current_selection(ctx)
        request_id = token(request_id)
        binding_id = digest([ctx.sid, ctx.actor['owner'], request_id])
        intent = ctx.store.get(BINDING, binding_id, ctx.sid)
        if (not intent or intent.get('runId') != run_id or intent.get('requestId') != request_id or
            intent.get('profileId') != obj['id'] or intent.get('profileRevision') != obj['_revision'] or
            intent.get('selectionRef') != selection['ref']):
            fail('stale_profile', 'The prepared request has a different profile or source.')
        if intent.get('approvedRequest') is not None:
            identity, _ = approved_generation_plan(ctx, run_id, request_id)
            return {'profileId': obj['id'], 'profileRevision': obj['_revision'],
                    'selectionRef': selection['ref'], 'runId': run_id,
                    'requestId': request_id, 'identityDigest': digest(vars(identity))}
        run = speech._load(ctx, token(run_id))
        if run['ref'] != selection['ref']:
            fail('stale_context', 'The selected source does not match the speech run.')
        identity, plan = speech.generation_plan(ctx, run_id, request_id)
        marker_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id],
                                  separators=(',', ':')).encode()).hexdigest()
        marker = ctx.store.get(speech.GENERATION_KIND, marker_id, ctx.sid)
        p, settings = obj['profile'], plan['settings']
        if (not marker or identity.language != p['language'] or identity.engine != p['engine'] or
            identity.model != p['model'] or identity.voice != p['voiceId'] or
            marker['preview']['voiceVersion'] != p['voiceVersion'] or
            settings['modelVersion'] != p['modelVersion'] or
            settings['adapterVersion'] != p['adapterVersion'] or
            settings['ruleSetId'] != p['ruleSetId'] or
            settings['ruleRevision'] != str(p['ruleSetRevision']) or settings['speed'] != p['rate']):
            fail('stale_profile', 'The prepared speech request does not match the selected profile.')
        return {'profileId': obj['id'], 'profileRevision': obj['_revision'],
                'selectionRef': selection['ref'], 'runId': run_id,
                'requestId': request_id, 'identityDigest': digest(vars(identity))}


def check_generation_binding(ctx, binding):
    if not isinstance(binding, dict) or set(binding) != {'profileId', 'profileRevision',
            'selectionRef', 'runId', 'requestId', 'identityDigest'}:
        fail('invalid_request', 'A complete profile binding is required.', 422)
    if generation_binding(ctx, binding['runId'], binding['requestId']) != binding:
        fail('stale_profile', 'The selected profile or speech request has changed.')


def final_guard(handler):
    guard = getattr(handler, '_w23_profile_final', None)
    if guard is None:
        fail('stale_context', 'Profile authorization unavailable.')
    guard()

def recover_result(ctx, obj):
    ctx.check_actor()
    result = obj['result']
    if obj['operation'] == 'profile.select':
        ctx.resolve([result['ref']])
        profile = load(ctx, result['profileId'])
        check_access(ctx, profile)
        if profile['_revision'] != result['revision']:
            fail('stale_profile', 'The selected profile has changed.')
        current, _ = current_selection(ctx)
        if any(current[k] != result[k] for k in ('profileId', 'revision', 'ref')):
            fail('stale_profile', 'The selection has changed.')
    elif obj['operation'] in ('profile.save', 'profile.approve'):
        profile = load(ctx, result['profileId'])
        if ctx.actor.get('role') != 'creator' or profile['owner'] != ctx.actor.get('owner'):
            fail('not_found', 'Operation unavailable.', 404)
        check_access(ctx, profile)
        if profile['_revision'] != result['revision']:
            fail('stale_profile', 'The profile has changed.')
    else:
        fail('not_found', 'Operation unavailable.', 404)
    return result


def receipt(ctx, request_id):
    ctx.check_actor()
    rid = digest([ctx.sid, ctx.actor['owner'], token(request_id)])
    obj = ctx.store.get(RECEIPT, rid, ctx.sid)
    if not obj:
        fail('not_found', 'Operation unavailable.', 404)
    result = recover_result(ctx, obj)
    return {'requestId': obj['requestId'], 'operation': obj['operation'], 'state': 'complete', 'result': result}

def cleanup_db(db, sid, owner=None):
    if owner is None:
        db.execute('DELETE FROM objects WHERE session_id=? AND kind IN (?,?,?,?)', (sid, PROFILE, SELECTION, RECEIPT, BINDING))
    else:
        db.execute('DELETE FROM objects WHERE session_id=? AND owner_id=? AND kind IN (?,?,?,?)', (sid, owner, PROFILE, SELECTION, RECEIPT, BINDING))

def handle(handler, sid, actor, method, parts):
    ctx = Context(handler, sid, actor)
    if actor.get('sid') != sid:
        fail('not_found', 'Speech profile unavailable.', 404)
    with ctx.lock:
        ctx.check_actor()
        if parts == ['installed-voices'] and method == 'GET':
            result = installed_voices(ctx)
            def installed_voices_fence():
                if installed_voices(ctx) != result:
                    fail('stale_context', 'Installed voices have changed.')
            handler._w23_profile_final = installed_voices_fence
            return 200, result
        if parts == ['profiles'] and method == 'GET':
            result = visible_profiles(ctx)
            def profiles_fence():
                if visible_profiles(ctx) != result:
                    fail('stale_context', 'Available speech profiles have changed.')
            handler._w23_profile_final = profiles_fence
            return 200, {'profiles': result}
        if len(parts) == 2 and parts[0] == 'operations' and method == 'GET':
            result = receipt(ctx, parts[1])
            handler._w23_profile_final = lambda: receipt(ctx, parts[1])
            return 200, {'operation': result}
        if parts == ['generation', 'prepare'] and method == 'POST':
            binding = prepare_selected_generation(ctx, handler.body())
            handler._w23_profile_final = lambda: check_generation_binding(ctx, binding)
            return 200, {'binding': binding}
        if len(parts) == 3 and parts[0] == 'generation' and method == 'GET':
            binding = generation_binding(ctx, parts[1], parts[2])
            handler._w23_profile_final = lambda: check_generation_binding(ctx, binding)
            return 200, {'binding': binding}
        if len(parts) == 2 and parts[0] == 'profiles' and method == 'PUT':
            result = save_profile(ctx, parts[1], handler.body())
            pid, rev = result['profileId'], result['revision']
            def fence():
                obj = load(ctx, pid)
                if obj['_revision'] != rev:
                    fail('stale_profile', 'The profile has changed.')
                rules = speech._rule_load(ctx, obj['profile']['ruleSetId'])['ruleset']
                if rules['revision'] != obj['profile']['ruleSetRevision']:
                    fail('stale_profile', 'The pronunciation rules have changed.')
            handler._w23_profile_final = fence
            return 200, result
        if len(parts) == 3 and parts[0] == 'profiles' and parts[2] == 'approval' and method == 'PUT':
            result = approve_profile(ctx, parts[1], handler.body())
            handler._w23_profile_final = lambda: recover_result(ctx, {'operation': 'profile.approve', 'result': result})
            return 200, result
        if parts == ['selection'] and method == 'PUT':
            result = select_profile(ctx, handler.body())
            def selection_fence():
                current, _ = current_selection(ctx)
                if any(current[k] != result[k] for k in ('profileId', 'revision', 'ref')):
                    fail('stale_profile', 'The selection has changed.')
            handler._w23_profile_final = selection_fence
            return 200, {'selection': result}
        if parts == ['selection'] and method == 'GET':
            selection, obj = current_selection(ctx)
            def selection_fence():
                current, _ = current_selection(ctx)
                if any(current[k] != selection[k] for k in ('profileId', 'revision', 'ref')):
                    fail('stale_profile', 'The selection has changed.')
            handler._w23_profile_final = selection_fence
            return 200, {'selection': selection, 'profile': projection(obj)}
        if len(parts) == 2 and parts[0] == 'profiles' and method == 'GET':
            obj = load(ctx, parts[1])
            if actor.get('role') != 'creator' or obj['owner'] != actor.get('owner'):
                fail('not_found', 'Speech profile unavailable.', 404)
            rev = obj['_revision']
            def profile_fence():
                current = load(ctx, parts[1])
                if current['_revision'] != rev:
                    fail('stale_profile', 'The profile has changed.')
                rules = speech._rule_load(ctx, current['profile']['ruleSetId'])['ruleset']
                if rules['revision'] != current['profile']['ruleSetRevision']:
                    fail('stale_profile', 'The pronunciation rules have changed.')
            profile_fence()
            handler._w23_profile_final = profile_fence
            return 200, {'profile': projection(obj)}
        fail('not_found', 'Speech profile unavailable.', 404)
