"""Private session listening continuity without generation or dispatch."""
import hashlib
import io
import json
import wave

from .phase10_common import Phase10Error
from . import waves23_speech_profiles as profiles

KIND = 'w25listening'
RECEIPT = 'w25listeningreceipt'


def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def _key(ctx):
    return profiles.digest([ctx.sid, ctx.actor['owner']])


def _selection(ctx):
    selection, obj = profiles.current_selection(ctx)
    return {'profileId': obj['id'], 'profileRevision': obj['_revision'],
            'configDigest': profiles.digest(obj['profile']), 'ref': selection['ref'],
            'language': obj['profile']['language']}, obj


def _load(ctx):
    return ctx.store.get(KIND, _key(ctx), ctx.sid)


def timed_original_audio(ctx, selected, position):
    """Authorize offsets in retained, digest-bound PCM WAV for this source.

    Offsets are milliseconds from the beginning of the retained audio, not
    the moment's timeline or an inferred offset for untimed text.
    """
    try:
        ref = selected['ref']
        if position['bindingId'] != ref['sourceId']:
            return False
        row = ctx.resolve([ref])[0]
        source = row['source']
        with ctx.store.connect() as db:
            audio = db.execute('SELECT mime,digest,data FROM phase12_original_audio WHERE source_id=? AND session_id=?',
                               (ref['sourceId'], ctx.sid)).fetchone()
        if (not audio or audio['mime'] not in ('audio/wav', 'audio/wave', 'audio/x-wav') or
                not isinstance(audio['data'], bytes) or len(audio['data']) > 12 * 1024 * 1024 or
                audio['digest'] != source.get('audioDigest') or
                hashlib.sha256(audio['data']).hexdigest() != audio['digest']):
            return False
        with wave.open(io.BytesIO(audio['data']), 'rb') as wav:
            if wav.getcomptype() != 'NONE' or not wav.getframerate() or not wav.getnframes():
                return False
            frame_size = wav.getnchannels() * wav.getsampwidth()
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * frame_size:
                return False
            return position['offsetMs'] * wav.getframerate() <= wav.getnframes() * 1000
    except (Phase10Error, KeyError, TypeError, ValueError, EOFError, wave.Error):
        return False


def _position(ctx, selected, value, authority):
    if value is None:
        return
    if (not isinstance(value, dict) or set(value) != {'bindingId', 'offsetMs'} or
            not isinstance(value['bindingId'], str) or not 1 <= len(value['bindingId']) <= 128 or
            type(value['offsetMs']) is not int or not 0 <= value['offsetMs'] <= 864000000):
        _fail('invalid_request', 'The playback position is invalid.', 422)
    if not callable(authority) or authority(ctx, selected, dict(value)) is not True:
        _fail('position_unavailable', 'This source has no current timed playback binding.')


def _supported(ctx, selected, obj, mode, authority):
    return mode == 'read' or (callable(authority) and
                              authority(ctx, selected, profiles.projection(obj), mode) is True)


def _access_supported(ctx, selected, obj, feature, value, authority):
    if (feature == 'descriptionEnabled' and value is False) or (feature == 'captionMode' and value == 'off'):
        return True
    return callable(authority) and authority(ctx, selected, profiles.projection(obj), feature, value) is True


def save(ctx, body, *, capabilities, timed_binding, accessibility_capabilities=None):
    """Atomically persist private preference and idempotency receipt."""
    required = {'requestId', 'expectedRevision', 'mode', 'position'}
    if not isinstance(body, dict) or not required <= set(body) or set(body) - required - {'descriptionEnabled', 'captionMode'}:
        _fail('invalid_request', 'A request ID, revision, mode and position are required.', 422)
    profiles.token(body['requestId'])
    if type(body['expectedRevision']) is not int or body['expectedRevision'] < 0 or body['mode'] not in ('read', 'listen'):
        _fail('invalid_request', 'The listening preference is invalid.', 422)
    if (('descriptionEnabled' in body and type(body['descriptionEnabled']) is not bool) or
            ('captionMode' in body and body['captionMode'] not in ('off', 'original', 'translated', 'both'))):
        _fail('invalid_request', 'The accessibility preference is invalid.', 422)
    fingerprint = profiles.digest(body)
    rid = profiles.digest([ctx.sid, ctx.actor['owner'], body['requestId']])
    with ctx.lock:
        ctx.check_actor()
        selected, obj = _selection(ctx)
        if not _supported(ctx, selected, obj, body['mode'], capabilities):
            _fail('choice_unavailable', 'This listening choice is unavailable. Reading is available.')
        for feature in ('descriptionEnabled', 'captionMode'):
            if feature in body and not _access_supported(ctx, selected, obj, feature, body[feature], accessibility_capabilities):
                _fail('choice_unavailable', 'This accessibility choice is unavailable.')
        _position(ctx, selected, body['position'], timed_binding)
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            prior = db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND session_id=? AND owner_id=?',
                               (RECEIPT, rid, ctx.sid, ctx.actor['owner'])).fetchone()
            if prior:
                receipt = json.loads(prior['data'])
                if receipt['fingerprint'] != fingerprint:
                    _fail('request_conflict', 'The request ID belongs to another preference.')
                current = _load(ctx)
                if not current or current['_revision'] != receipt['revision'] or current['selection'] != selected:
                    _fail('stale_context', 'The saved preference has changed.')
                db.commit()
                return reconcile(ctx, capabilities=capabilities, timed_binding=timed_binding, accessibility_capabilities=accessibility_capabilities)
            row = db.execute('SELECT revision,data FROM objects WHERE kind=? AND id=? AND session_id=? AND owner_id=?',
                             (KIND, _key(ctx), ctx.sid, ctx.actor['owner'])).fetchone()
            actual = row['revision'] if row else 0
            if actual != body['expectedRevision']:
                _fail('stale_revision', 'The listening preference has changed.')
            revision = actual + 1
            previous = json.loads(row['data']) if row else {}
            data = {'id': _key(ctx), 'selection': selected, 'mode': body['mode'], 'position': body['position'],
                    'descriptionEnabled': body.get('descriptionEnabled', previous.get('descriptionEnabled', False)),
                    'captionMode': body.get('captionMode', previous.get('captionMode', 'off'))}
            if row:
                changed = db.execute('UPDATE objects SET revision=?,data=? WHERE kind=? AND id=? AND session_id=? AND owner_id=? AND revision=?',
                                     (revision, json.dumps(data), KIND, _key(ctx), ctx.sid, ctx.actor['owner'], actual)).rowcount
                if changed != 1:
                    _fail('stale_revision', 'The listening preference has changed.')
            else:
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',
                           (KIND, _key(ctx), ctx.sid, ctx.actor['owner'], revision, json.dumps(data), ctx.store.now()))
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                       (RECEIPT, rid, ctx.sid, ctx.actor['owner'], json.dumps({'fingerprint': fingerprint, 'revision': revision}), ctx.store.now()))
            db.commit()
        return reconcile(ctx, capabilities=capabilities, timed_binding=timed_binding, accessibility_capabilities=accessibility_capabilities)


def reconcile(ctx, *, capabilities, timed_binding, accessibility_capabilities=None):
    with ctx.lock:
        result = _reconcile(ctx, capabilities=capabilities, timed_binding=timed_binding,
                            accessibility_capabilities=accessibility_capabilities)
        from .waves25_listening_preparation import approved_for_selection
        result['approvedPreparation'] = approved_for_selection(ctx)
        return result


def _reconcile(ctx, *, capabilities, timed_binding, accessibility_capabilities=None):
    """Revalidate saved choice without changing it or starting work."""
    with ctx.lock:
        ctx.check_actor()
        saved = _load(ctx)
        if not saved:
            result = {'state': 'unset', 'revision': 0, 'descriptionEnabled': False, 'captionMode': 'off',
                      'descriptionAvailable': True, 'captionAvailable': True}
            try:
                selected, obj = _selection(ctx)
                from .waves25_listening_recovery import continuity
                result['continuity'] = continuity(ctx, selected, obj)
            except Phase10Error:
                pass
            return result
        try:
            selected, obj = _selection(ctx)
            if selected != saved['selection']:
                _fail('stale_context', 'The selected source or profile has changed.')
            available = _supported(ctx, selected, obj, saved['mode'], capabilities)
            description = saved.get('descriptionEnabled', False)
            captions = saved.get('captionMode', 'off')
            position = saved['position']
            position_available = True
            try:
                _position(ctx, selected, position, timed_binding)
            except Phase10Error:
                position_available = False
            from .waves25_listening_recovery import continuity
            return {'state': 'available' if available else 'unavailable', 'revision': saved['_revision'],
                    'selection': selected, 'mode': saved['mode'],
                    'descriptionEnabled': description, 'captionMode': captions,
                    'descriptionAvailable': _access_supported(ctx, selected, obj, 'descriptionEnabled', description, accessibility_capabilities),
                    'captionAvailable': _access_supported(ctx, selected, obj, 'captionMode', captions, accessibility_capabilities),
                    'position': position if position_available else None, 'positionAvailable': position_available,
                    'alternative': None if available else {'mode': 'read', 'language': selected['language']},
                    'message': None if available else 'This listening choice is unavailable. You can choose reading.',
                    'continuity': continuity(ctx, selected, obj)}
        except Phase10Error:
            return {'state': 'unavailable', 'revision': saved['_revision'],
                    'message': 'The saved source or profile is unavailable. Choose a current source and profile.',
                    'alternative': None, 'position': None}


def _current_plan(ctx, run_id, request_id):
    """Reconstruct the existing intent and its exact bridge plan without writes."""
    from . import waves21_speech_runtime as speech
    record = ctx.store.get(profiles.BINDING,
                           profiles.digest([ctx.sid, ctx.actor['owner'], request_id]), ctx.sid)
    if not record:
        _fail('stale_context', 'The speech binding is unavailable.')
    if record.get('approvedRequest') is not None:
        identity, subscriber, plan = profiles.approved_generation_subscriber(ctx, run_id, request_id)
        if not profiles.eligible_approved_subscriber(identity, subscriber):
            _fail('stale_context', 'The speech subscriber is unavailable.')
        return identity, plan
    return speech.generation_plan(ctx, run_id, request_id)


def preload(ctx, run_id, request_id, *, receipt_authority):
    """Inspect an existing exact completed bridge receipt, never create one."""
    with ctx.lock:
        ctx.check_actor()
        binding = profiles.generation_binding(ctx, run_id, request_id)
        with ctx.store.connect() as db:
            row = db.execute('SELECT state,fingerprint,payload,result,media FROM phase12_jobs WHERE session_id=? AND actor_id=? AND request_id=? AND kind=?',
                             (ctx.sid, '\x00wave20-internal', binding['identityDigest'], 'w20_speech')).fetchone()
        if not row:
            return {'state': 'unavailable'}
        if row['state'] != 'w20_complete':
            from .waves25_listening_recovery import receipt_state
            return {'state': receipt_state(row['state'])}
        try:
            identity = json.loads(row['payload'])['identity']
            result = json.loads(row['result'])
            current, plan = _current_plan(ctx, run_id, request_id)
            if (profiles.digest(identity) != binding['identityDigest'] or identity['session'] != ctx.sid or
                    identity['private_actor'] != ctx.actor['owner'] or not row['media'] or
                    vars(current) != identity or row['fingerprint'] != profiles.digest(plan) or
                    result['audioSha256'] != hashlib.sha256(row['media']).hexdigest() or
                    not callable(receipt_authority) or receipt_authority(ctx, identity, binding) is not True):
                return {'state': 'unavailable'}
        except (Phase10Error, KeyError, TypeError, ValueError):
            return {'state': 'unavailable'}
        return {'state': 'ready', 'binding': binding, 'audioSha256': result['audioSha256']}


def final_guard(ctx, binding, *, receipt_authority):
    """Run under the host's final-send lock immediately before audio delivery."""
    checked = preload(ctx, binding['runId'], binding['requestId'], receipt_authority=receipt_authority)
    if checked.get('state') != 'ready' or checked.get('binding') != binding:
        _fail('stale_context', 'The audio is unavailable or has changed.')


def cleanup_db(db, sid, owner=None):
    """Compose with the host's existing session/revocation transaction."""
    if owner is None:
        db.execute('DELETE FROM objects WHERE session_id=? AND kind IN (?,?,?)', (sid, KIND, RECEIPT, 'w25preparation'))
    else:
        db.execute('DELETE FROM objects WHERE session_id=? AND owner_id=? AND kind IN (?,?,?)',
                   (sid, owner, KIND, RECEIPT, 'w25preparation'))
