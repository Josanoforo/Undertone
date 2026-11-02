"""Wave 21 speech runtime: durable private runs and buffered chunk admission.

Common routing, policy, scheduler configuration and lifecycle invocation belong to PRIMARY.
Use the documented final-send and lifecycle hooks when mounting.
"""
import base64
import hashlib
import io
import json
import math
import wave

from .phase10_common import Context, Phase10Error, parse_ref
from . import waves21_speech_stream as stream
from . import waves21_pronunciation as pronunciation

KIND = 'w21speechrun'

def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)

def _source(ctx, ref):
    row = ctx.resolve([parse_ref(ref)])[0]
    source, moment = row['source'], row['moment']
    proof, alignment = source.get('p10Provenance') or {}, moment.get('alignment') or {}
    if (proof.get('type') != 'received_asr_v1' or proof.get('sessionId') != ctx.sid
        or not proof.get('captureRunId') or alignment.get('captureRunId') != proof['captureRunId']
        or alignment.get('origin') not in ('asr', 'manual')):
        _fail('source_unavailable', 'Indexed speech source unavailable.', 404)
    from .phase12_feed import verified_moment_language
    language = verified_moment_language(source, moment)
    with ctx.store.connect() as db:
        rows = db.execute('SELECT ref,run_id,language FROM phase12_caption_feed WHERE session_id=? AND moment_id=?',
                          (ctx.sid, ref['momentId'])).fetchall()
    if language is None or not any(json.loads(r['ref']) == ref and r['run_id'] == proof['captureRunId'] and r['language'] == language for r in rows):
        _fail('source_unavailable', 'Indexed speech source unavailable.', 404)
    kind = proof.get('inputKind')
    return proof['captureRunId'], kind if kind in ('file_replay', 'live_program_audio') else 'unknown'

def _credential(ctx):
    if isinstance(ctx, _StoredContext):
        return ctx.credential_hash
    return ctx.store.digest(getattr(ctx.handler, '_auth_token', ''))

def _load(ctx, run_id):
    stream._token(run_id)
    ctx.check_actor()
    obj = ctx.store.get(KIND, run_id, ctx.sid)
    if (not obj or obj.get('owner') != ctx.actor.get('owner') or
        obj.get('credentialHash') != _credential(ctx)):
        _fail('not_found', 'Speech run unavailable.', 404)
    if obj.get('invalidated') is True:
        _fail('stale_context', 'Speech source changed.')
    capture, kind = _source(ctx, obj['ref'])
    if capture != obj['state']['captureRunId'] or kind != obj['state']['inputKind']:
        _fail('stale_context', 'Speech source changed.')
    # Older stored runs predate explicit bounds/revision in the projection.
    # Derive them from the already verified source reference, never assume v1.
    obj['state'].setdefault('sourceRevision', obj['ref']['sourceRevision'])
    obj['state'].setdefault('interval', {'startMs':obj['ref']['startMs'], 'endMs':obj['ref']['endMs']})
    return obj

def create_run(ctx, ref, recognition_mode='final_only'):
    """Create a private, actor-and-credential-bound run for an indexed ASR moment."""
    with ctx.lock:
        if recognition_mode not in ('final_only', 'incremental_prefix'):
            _fail('invalid_mode', 'Speech recognition mode unavailable.', 422)
        ctx.check_actor()
        capture, kind = _source(ctx, ref)
        oid = ctx.store.ident()
        state = stream.new_run(capture, ref['sourceId'], 'private', kind)
        state.update(interval={'startMs':ref['startMs'], 'endMs':ref['endMs']},
                     sourceRevision=ref['sourceRevision'], recognitionMode=recognition_mode, recognitionIssues={})
        # The normal intake has already decoded and indexed this audio. Reuse
        # that authenticated result instead of requiring a second WAV upload
        # and inference just to open the revision-aware caption view.
        row = ctx.resolve([ref])[0]
        source, moment = row['source'], row['moment']
        proof = source.get('p10Provenance') or {}
        original = source.get('text')
        from .phase12_feed import verified_moment_language
        language = verified_moment_language(source, moment)
        if (recognition_mode == 'final_only' and moment.get('alignment', {}).get('origin') == 'asr'
                and isinstance(original, str) and isinstance(source.get('audioDigest'), str)
                and proof.get('textSha256') == hashlib.sha256(original.encode('utf-8')).hexdigest()
                and language in ('en', 'es') and isinstance(moment.get('text'), str)
                and 0 < len(moment['text'].strip()) <= 4000):
            segment_id = 'indexed:' + stream._digest(ref)[:32]
            event = {'captureRunId':capture, 'sourceRef':ref['sourceId'], 'inputKind':kind,
                     'interval':dict(state['interval']), 'segmentId':segment_id, 'revision':1,
                     'language':language, 'originalLanguage':language,
                     'state':'final', 'text':moment['text'], 'originalText':moment['text'],
                     'recognitionMode':'final_only', 'recognitionOrigin':'indexed_asr', 'speaker':'unknown'}
            state['segments'][segment_id] = [event]
            state['chunks']['indexed'] = {'fingerprint':stream._digest({'ref':ref, 'sourceAudioDigest':source['audioDigest']}),
                                         'interval':dict(state['interval']), 'segmentIds':[segment_id],
                                         'recognitionMode':'final_only', 'origin':'indexed_asr'}
            state['indexedAsr'] = True
        obj = {'id': oid, 'owner': ctx.actor['owner'], 'credentialHash': _credential(ctx),
               'ref': dict(ref), 'state': state, 'claims': {}}
        ctx.store.put(KIND, ctx.sid, obj, owner=ctx.actor['owner'], oid=oid)
        return oid

def _wav_duration_ms(audio):
    try:
        with wave.open(io.BytesIO(audio), 'rb') as f:
            if f.getcomptype() != 'NONE' or not f.getframerate() or not f.getnframes(): raise ValueError()
            return 1000 * f.getnframes() / f.getframerate()
    except (wave.Error, EOFError, ValueError):
        _fail('invalid_audio', 'A bounded PCM WAV chunk is required.', 422)

def _matches_source_audio(ctx, source, interval, audio):
    """Bind a WAV chunk to bytes of its indexed source, never caller metadata alone.

    Whole-source digest works even when original audio was not retained. Slices
    require retained PCM WAV with the source digest verified; sample boundaries
    must map exactly to the requested run-relative clock.
    """
    offset = source.get('offsetSeconds')
    digest = source.get('audioDigest')
    if (isinstance(offset, bool) or not isinstance(offset, (int, float))
            or not math.isfinite(offset) or not isinstance(digest, str)):
        return False
    start_ms = round(offset * 1000)
    if abs(offset * 1000 - start_ms) > 1e-6:
        return False
    if interval['startMs'] == start_ms and hashlib.sha256(audio).hexdigest() == digest:
        return True
    with ctx.store.connect() as db:
        row = db.execute('SELECT mime,digest,data FROM phase12_original_audio WHERE source_id=? AND session_id=?',
                         (source['id'], ctx.sid)).fetchone()
    if not row or row['mime'] not in ('audio/wav', 'audio/wave', 'audio/x-wav'):
        return False
    original = row['data']
    if not isinstance(original, bytes) or len(original) > 12 * 1024 * 1024 or row['digest'] != digest or hashlib.sha256(original).hexdigest() != digest:
        return False
    try:
        with wave.open(io.BytesIO(original), 'rb') as src, wave.open(io.BytesIO(audio), 'rb') as part:
            if src.getcomptype() != 'NONE' or part.getcomptype() != 'NONE': return False
            if (src.getnchannels(), src.getsampwidth(), src.getframerate()) != (part.getnchannels(), part.getsampwidth(), part.getframerate()): return False
            rate = src.getframerate()
            start = (interval['startMs'] - start_ms) * rate
            end = (interval['endMs'] - start_ms) * rate
            if start < 0 or start % 1000 or end % 1000: return False
            start //= 1000; end //= 1000
            if end > src.getnframes() or end <= start or part.getnframes() != end - start: return False
            src.setpos(start)
            return src.readframes(end - start) == part.readframes(end - start)
    except (wave.Error, EOFError, ValueError, OverflowError):
        return False


def ingest(ctx, run_id, chunk, audio):
    """Claim once durably, invoke actual ASR outside the lock, then fence and commit.

    A crash or exception after the claim leaves an unresolved claim, never an automatic retry.
    The caller must use the final serialization fence before sending a successful result.
    """
    if not isinstance(chunk, dict) or set(chunk) - {'chunkId','startMs','endMs','mimeType','language'} or not {'chunkId','startMs','endMs','mimeType'} <= set(chunk):
        _fail('invalid_chunk', 'Invalid chunk metadata.', 422)
    cid = stream._token(chunk['chunkId'])
    # Segment IDs append a colon and an index up to 199; reject IDs that
    # cannot represent every valid adapter result before claiming or inference.
    if len(cid) > 124:
        _fail('invalid_chunk', 'Chunk ID is too long.', 422)
    iv = stream._interval(chunk['startMs'], chunk['endMs'])
    if not isinstance(audio, bytes) or not 0 < len(audio) <= 12 * 1024 * 1024 or chunk['mimeType'] not in ('audio/wav', 'audio/wave', 'audio/x-wav') or chunk.get('language') not in (None, 'en', 'es'):
        _fail('invalid_chunk', 'Invalid audio chunk.', 422)
    if abs(_wav_duration_ms(audio) - (iv['endMs'] - iv['startMs'])) > 2:
        _fail('invalid_interval', 'Chunk duration does not match the WAV.', 422)
    fingerprint = stream._digest({'interval':iv,'mime':chunk['mimeType'],'language':chunk.get('language'),'audioSha256':hashlib.sha256(audio).hexdigest()})
    with ctx.lock:
        obj = _load(ctx, run_id)
        if obj['state'].get('recognitionMode') == 'incremental_prefix':
            _fail('invalid_mode', 'Use growing audio prefixes for this preview.')
        if obj['state'].get('indexedAsr'):
            _fail('already_indexed', 'This interval already has indexed recognition; revise its caption instead.', 409)
        if iv['startMs'] < obj['ref']['startMs'] or iv['endMs'] > obj['ref']['endMs']:
            _fail('audio_provenance_unavailable', 'Audio is outside the indexed moment.', 409)
        # Bind to the indexed recording and its exact sample clock.
        source = ctx.store.get('source', obj['ref']['sourceId'], ctx.sid)
        if not source or not _matches_source_audio(ctx, source, iv, audio):
            _fail('audio_provenance_unavailable', 'Audio does not match the indexed capture.', 409)
        claim = obj['claims'].get(cid)
        if claim:
            if claim['fingerprint'] != fingerprint: _fail('duplicate_conflict', 'Chunk ID already has different content.')
            if claim['status'] != 'complete': _fail('outcome_unknown', 'Chunk outcome is unresolved; do not retry.')
            return obj['state']
        if len(obj['claims']) >= 1000: _fail('run_full', 'Speech run is full.')
        for prior in obj['claims'].values():
            other = prior['interval']
            if iv['startMs'] < other['endMs'] and iv['endMs'] > other['startMs']:
                _fail('chunk_overlap', 'Speech chunks cannot overlap.')
        obj['claims'][cid] = {'fingerprint': fingerprint, 'interval': iv, 'status': 'in_flight'}
        obj['state'].setdefault('recognitionIssues', {})[cid] = {'state':'gap', 'interval':iv, 'chunkId':cid, 'reason':'recognition_pending'}
        ctx.store.save(KIND, obj)
    try:
        response = stream.faster_whisper(audio, chunk['mimeType'], chunk.get('language'))
        with ctx.lock:
            obj = _load(ctx, run_id)
            claim = obj['claims'].get(cid)
            if not claim or claim['status'] != 'in_flight' or claim['fingerprint'] != fingerprint:
                _fail('outcome_unknown', 'Chunk outcome is unresolved; do not retry.')
            updated = stream.ingest(obj['state'], chunk, audio, lambda *_: response, lambda *_: True)
            updated.setdefault('recognitionIssues', {}).pop(cid, None)
            claim['status'] = 'complete'
            obj['state'] = updated
            ctx.store.save(KIND, obj)
            return updated
    except Exception:
        # Unknown inference outcomes are never retried. Persist a safe, explicit
        # gap rather than losing the failure on the next authenticated GET.
        with ctx.lock:
            current = ctx.store.get(KIND, run_id, ctx.sid)
            failed = current.get('claims', {}).get(cid) if current else None
            if failed and failed['fingerprint'] == fingerprint and failed['status'] == 'in_flight':
                failed['status'] = 'unknown'
                current['state'].setdefault('recognitionIssues', {})[cid] = {'state':'gap', 'interval':iv, 'chunkId':cid, 'reason':'recognition_error', 'outcome':'unknown'}
                ctx.store.save(KIND, current)
        raise

def incremental_preview(ctx, run_id):
    """One explicit, idempotent replay preview; never discard indexed captions."""
    with ctx.lock:
        original = _load(ctx, run_id)
        preview_id = original.get('prefixPreviewRunId')
        if preview_id:
            return preview_id, _load(ctx, preview_id)['state']
        preview_id = create_run(ctx, original['ref'], 'incremental_prefix')
        original['prefixPreviewRunId'] = preview_id
        original['state']['incrementalPreviewRunId'] = preview_id
        ctx.store.save(KIND, original)
        return preview_id, _load(ctx, preview_id)['state']


def ingest_prefix(ctx, run_id, chunk, audio):
    """One growing source-bound WAV prefix per request; no automatic inference retry.

    HTTP responses/GET expose actual successive hypotheses while the utterance
    is open. This is a replay-capable incremental adapter over buffered ASR,
    not a native streaming decoder, live capture or an end-of-turn detector.
    """
    required = {'chunkId','startMs','endMs','mimeType','recognitionMode','sequence','expectedRevision','final'}
    if not isinstance(chunk, dict) or set(chunk) != required or chunk['recognitionMode'] != 'incremental_prefix':
        _fail('invalid_prefix', 'Invalid audio prefix.', 422)
    cid = stream._token(chunk['chunkId'])
    if len(cid) > 120 or chunk['mimeType'] != 'audio/wav' or not isinstance(audio, bytes) or not 0 < len(audio) <= 12 * 1024 * 1024:
        _fail('invalid_prefix', 'A bounded PCM WAV prefix is required.', 422)
    iv = stream._interval(chunk['startMs'], chunk['endMs'])
    if abs(_wav_duration_ms(audio) - (iv['endMs'] - iv['startMs'])) > 2:
        _fail('invalid_interval', 'Prefix duration does not match the WAV.', 422)
    stream._integer(chunk['sequence'], 1, 64)
    key = 'prefix:' + str(chunk['sequence'])
    fingerprint = stream._digest({'chunk':chunk, 'audioSha256':hashlib.sha256(audio).hexdigest()})
    with ctx.lock:
        obj = _load(ctx, run_id)
        if obj['state'].get('recognitionMode') != 'incremental_prefix':
            _fail('invalid_mode', 'Open an incremental preview first.')
        claim = obj['claims'].get(key)
        if claim:
            if claim['fingerprint'] != fingerprint:
                _fail('duplicate_conflict', 'Prefix sequence already has different content.')
            if claim['status'] != 'complete':
                _fail('outcome_unknown', 'Prefix outcome is unresolved; do not retry.')
            return obj['state']
        if any(c['status'] != 'complete' for c in obj['claims'].values()):
            _fail('outcome_unknown', 'A previous prefix is unresolved; no further recognition is admitted.')
        if iv['startMs'] != obj['ref']['startMs'] or iv['endMs'] > obj['ref']['endMs']:
            _fail('invalid_interval', 'Send a growing prefix from the start of the selected interval.', 422)
        # Validate sequencing/revision/finalization before the external effect.
        stream.prefix_result(obj['state'], chunk, {'segments':[]}, lambda *_: True)
        source = ctx.store.get('source', obj['ref']['sourceId'], ctx.sid)
        if not source or not _matches_source_audio(ctx, source, iv, audio):
            _fail('audio_provenance_unavailable', 'Audio does not match the indexed capture.')
        obj['claims'][key] = {'fingerprint':fingerprint, 'interval':iv, 'status':'in_flight'}
        obj['state'].setdefault('recognitionIssues', {})[key] = {'state':'gap','interval':iv,'reason':'recognition_pending'}
        ctx.store.save(KIND, obj)
    stage = 'adapter_call'
    try:
        response = stream.faster_whisper(audio, 'audio/wav', None)
        stage = 'result_validation'
        with ctx.lock:
            obj = _load(ctx, run_id)
            claim = obj['claims'].get(key)
            if not claim or claim['status'] != 'in_flight' or claim['fingerprint'] != fingerprint:
                _fail('outcome_unknown', 'Prefix outcome is unresolved; do not retry.')
            updated = stream.prefix_result(obj['state'], chunk, response, lambda *_: True)
            updated['recognitionIssues'].pop(key, None)
            obj['state'] = updated
            claim['status'] = 'complete'
            stage = 'commit'
            ctx.store.save(KIND, obj)
            return updated
    except Exception as exc:
        with ctx.lock:
            current = ctx.store.get(KIND, run_id, ctx.sid)
            claim = current.get('claims', {}).get(key) if current else None
            if claim and claim['fingerprint'] == fingerprint and claim['status'] == 'in_flight':
                claim['status'] = 'unknown'
                # Safe stage/code only, never decoder/source text or arbitrary
                # exception messages. Preserve unknown; diagnostics are not a
                # retry permission and do not retroactively classify old runs.
                code = (str(exc) if isinstance(exc, stream.SpeechStreamError) else
                        exc.code if isinstance(exc, Phase10Error) else 'adapter_unavailable' if stage == 'adapter_call' else 'operation_failed')
                if not isinstance(code, str) or not code.replace('_','').isalnum(): code='operation_failed'
                current['state'].setdefault('recognitionIssues', {})[key] = {'state':'gap','interval':iv,'reason':'recognition_error','outcome':'unknown','failureStage':stage,'code':code}
                ctx.store.save(KIND, current)
        raise


def mutate(ctx, run_id, action, body):
    with ctx.lock:
        obj = _load(ctx, run_id)
        if obj['state'].get('recognitionMode') == 'incremental_prefix' and not obj['state'].get('prefix', {}).get('final'):
            _fail('utterance_open', 'Finish audio recognition before editing or finalizing its caption.')
        if action == 'revise' and set(body) == {'segmentId','expectedRevision','text','language'}:
            updated = stream.revise(obj['state'], body['segmentId'], body['expectedRevision'], body['text'], body['language'], lambda *_: True)
        elif action == 'finalize' and set(body) == {'segmentId','expectedRevision'}:
            updated = stream.finalize(obj['state'], body['segmentId'], body['expectedRevision'], lambda *_: True)
        else:
            _fail('invalid_request', 'Invalid speech operation.', 422)
        obj['state'] = updated
        ctx.store.save(KIND, obj)
        return updated


def final_guard(handler):
    """PRIMARY calls under store.LOCK and holds it through response serialization."""
    guard = getattr(handler, '_w21_speech_final', None)
    if guard is None:
        _fail('stale_context', 'Speech delivery authorization unavailable.')
    guard()


def _fence_state(ctx, run_id, expected):
    current = _load(ctx, run_id)['state']
    if current != expected:
        _fail('stale_context', 'Speech changed before delivery.')


RULE_KIND = 'w21pronunciation'

def _rule_load(ctx, rule_id):
    pronunciation._id(rule_id)
    ctx.check_actor()
    obj = ctx.store.get(RULE_KIND, rule_id, ctx.sid)
    if (not obj or ctx.actor.get('role') != 'creator' or
        obj.get('owner') != ctx.actor.get('owner') or
        obj.get('credentialHash') != _credential(ctx)):
        _fail('not_found', 'Pronunciation rules unavailable.', 404)
    return obj

def _rule_fence(ctx, rule_id, expected):
    if _rule_load(ctx, rule_id)['ruleset'] != expected:
        _fail('stale_context', 'Pronunciation rules changed before delivery.')

def create_rules(ctx):
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            _fail('not_found', 'Pronunciation rules unavailable.', 404)
        oid = ctx.store.ident()
        ruleset = pronunciation.new_rule_set(oid, ctx.actor['owner'], 'private')
        obj = {'id':oid, 'owner':ctx.actor['owner'], 'credentialHash':_credential(ctx), 'ruleset':ruleset}
        ctx.store.put(RULE_KIND, ctx.sid, obj, owner=ctx.actor['owner'], oid=oid)
        return ruleset

def update_rules(ctx, rule_id, body, delete=False):
    fields = {'expectedRevision'} if delete else {'expectedRevision', 'rules'}
    if not isinstance(body, dict) or set(body) != fields:
        _fail('invalid_request', 'An expected revision and valid rules are required.', 422)
    with ctx.lock:
        obj = _rule_load(ctx, rule_id)
        obj['ruleset'] = pronunciation.update_rules(obj['ruleset'], body['expectedRevision'], [] if delete else body['rules'], ctx.actor, lambda *_: True)
        ctx.store.save(RULE_KIND, obj)
        return obj['ruleset']

def preview_rules(ctx, run_id, body):
    fields = {'ruleSetId', 'segmentId', 'expectedRevision', 'requestId', 'engine',
              'model', 'modelVersion', 'voiceId', 'voiceVersion', 'adapterVersion',
              'outputFormat', 'rate', 'controls'}
    if not isinstance(body, dict) or set(body) != fields:
        _fail('invalid_request', 'A complete pronunciation preview is required.', 422)
    with ctx.lock:
        obj = _load(ctx, run_id)
        ruleset = _rule_load(ctx, body['ruleSetId'])['ruleset']
        history = obj['state']['segments'].get(body['segmentId']) if isinstance(body['segmentId'], str) else None
        event = history[-1] if history else None
        if (not event or event['state'] != 'final' or type(body['expectedRevision']) is not int
                or event['revision'] != body['expectedRevision']):
            _fail('not_current_final', 'A current final segment is required.')
        request = {key: body[key] for key in ('requestId', 'engine', 'model', 'modelVersion',
                   'voiceId', 'voiceVersion', 'adapterVersion', 'outputFormat', 'rate', 'controls')}
        request.update({'ruleSetRevision':ruleset['revision'], 'scope':'private',
                        'text':event['text'], 'language':event['language'],
                        'sourceId':obj['ref']['sourceId'], 'sourceRevision':obj['ref']['sourceRevision']})
        result = pronunciation.resolve_rules(ruleset, request, ctx.actor, lambda *_: True)
        return result, obj['state'], ruleset


GENERATION_KIND = 'w21speechrequest'

def prepare_generation(ctx, run_id, body):
    """Persist a private current-final generation intent, without dispatch.

    A request ID is bound per session and actor across runs. The run transition
    and marker commit together; an existing marker is never silently replaced.
    This is preparation only, not a scheduler receipt or evidence of synthesis.
    """
    if not isinstance(body, dict) or body.get('targetLanguage') not in ('en', 'es'):
        _fail('invalid_request', 'A target language is required.', 422)
    preview_body = dict(body)
    target_language = preview_body.pop('targetLanguage')
    with ctx.lock:
        result, state, ruleset = preview_rules(ctx, run_id, preview_body)
        if not result['ready']:
            _fail('unsupported_controls', 'The requested pronunciation controls are unavailable.', 422)
        if any(rule['approved'] for rule in ruleset['rules']):
            from . import waves20_job_bridge
            if getattr(waves20_job_bridge, 'SPOKEN_FORM_REVISION', None) != pronunciation.SPOKEN_FORM_REVISION:
                _fail('unavailable', 'Spoken-form execution is not available.', 409)
        obj = _load(ctx, run_id)
        request_id = stream._token(preview_body['requestId'])
        intent_state = stream.prepare_intent(state, preview_body['segmentId'],
                                             preview_body['expectedRevision'], 'audio', request_id, lambda *_: True)
        fingerprint = stream._digest({'runId': run_id, 'preview': preview_body, 'targetLanguage': target_language,
                                      'generationKey': result['generationKey']})
        marker_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id],
                                               separators=(',', ':')).encode()).hexdigest()
        request = {'requestId': request_id, 'fingerprint': fingerprint, 'runId': run_id,
                   'targetLanguage': target_language, 'preview': preview_body,
                   'generationKey': result['generationKey'], 'status': 'prepared'}
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                             (GENERATION_KIND, marker_id, ctx.sid)).fetchone()
            if row:
                old = json.loads(row['data'])
                if row['owner_id'] != ctx.actor['owner'] or old.get('fingerprint') != fingerprint:
                    _fail('request_conflict', 'Request ID already has different content.')
                db.commit()
                return old
            intent_state.setdefault('generationRequests', {})[request_id] = request
            obj['state'] = intent_state
            revision = obj.pop('_revision')
            updated = db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?',
                                 (json.dumps(obj, ensure_ascii=False), KIND, run_id, ctx.sid, revision)).rowcount
            if updated != 1:
                _fail('stale_context', 'Speech changed before preparation.')
            db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',
                       (GENERATION_KIND, marker_id, ctx.sid, ctx.actor['owner'],
                        json.dumps(request, ensure_ascii=False), ctx.store.now()))
            db.commit()
        return request

def generation_plan(ctx, run_id, request_id):
    """Reconstruct the current private JobBridge identity and plan.

    The caller supplies the real authenticated Context and must re-run this
    under the store lock at every admission, effect and delivery fence. This
    function does not admit work or make an adapter call.
    """
    from .waves20_delivery import Identity
    from .waves20_job_bridge import settings_digest, validate_plan
    request_id = stream._token(request_id)
    marker_id = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id],
                                          separators=(',', ':')).encode()).hexdigest()
    with ctx.lock:
        ctx.check_actor()
        with ctx.store.connect() as db:
            row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                             (GENERATION_KIND, marker_id, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _fail('not_found', 'Speech request unavailable.', 404)
        request = json.loads(row['data'])
        if request.get('runId') != run_id or request.get('requestId') != request_id:
            _fail('request_conflict', 'Speech request does not match.')
        body = request['preview']
        result, state, ruleset = preview_rules(ctx, run_id, body)
        if not result['ready'] or result['generationKey'] != request['generationKey']:
            _fail('stale_context', 'Speech request changed.')
        if any(rule['approved'] for rule in ruleset['rules']):
            from . import waves20_job_bridge
            if getattr(waves20_job_bridge, 'SPOKEN_FORM_REVISION', None) != pronunciation.SPOKEN_FORM_REVISION:
                _fail('unavailable', 'Spoken-form execution is not available.', 409)
        obj = _load(ctx, run_id)
        intent = state.get('intents', {}).get(request_id)
        current = state['segments'][body['segmentId']][-1]
        if (not intent or intent.get('revision') != body['expectedRevision']
                or intent.get('segmentId') != body['segmentId']
                or intent.get('eventDigest') != stream._digest(current)):
            _fail('stale_context', 'Speech intent changed.')
        if body['engine'] not in ('sapi', 'local_neural'):
            _fail('unavailable', 'The selected voice is unavailable for this speech request.', 409)
        if result['identity']['language'] not in ('en', 'es'):
            _fail('unavailable', 'A known source language is required for speech delivery.', 409)
        rules = ruleset['rules']
        settings = {'engine': body['engine'], 'model': body['model'], 'voice': body['voiceId'],
                    'outputFormat': body['outputFormat'], 'adapterVersion': body['adapterVersion'],
                    'modelVersion': body['modelVersion'], 'speed': body['rate'],
                    'ruleSetId': ruleset['ruleSetId'], 'ruleRevision': str(ruleset['revision']),
                    'ruleDigest': settings_digest(rules), 'approvedRules': rules,
                    'controls': [], 'glossary': [], 'terminology': None, 'hostedBinding': None}
        partition = stream._digest(['w21-private', ctx.sid, ctx.actor['owner'], _credential(ctx)])
        identity = Identity(session=ctx.sid, rights_partition=partition,
                            source=obj['ref']['sourceId'], source_revision=str(obj['ref']['sourceRevision']),
                            translation_revision=request['generationKey'], terminology_revision='none',
                            text_digest=hashlib.sha256(result['originalText'].encode('utf-8')).hexdigest(),
                            language=request['targetLanguage'], engine=body['engine'], model=body['model'],
                            voice=body['voiceId'], settings_digest=settings_digest(settings),
                            output_format=body['outputFormat'], private_actor=ctx.actor['owner'])
        plan = {'session': ctx.sid, 'rightsPartition': partition, 'source': identity.source,
                'sourceRevision': identity.source_revision, 'translationRevision': identity.translation_revision,
                'terminologyRevision': identity.terminology_revision, 'scope': 'private',
                'privateActor': ctx.actor['owner'], 'text': result['originalText'],
                'sourceLanguage': result['identity']['language'], 'settings': settings}
        return identity, validate_plan(identity, plan)

def _preview_fence(ctx, run_id, state, rule_id, ruleset):
    _fence_state(ctx, run_id, state)
    _rule_fence(ctx, rule_id, ruleset)

def handle(handler, sid, actor, method, parts):
    """Private speech, pronunciation and scheduler admission routes."""
    ctx = Context(handler, sid, actor)
    if actor.get('sid') != sid:
        _fail('not_found', 'Speech route unavailable.', 404)
    try:
        if parts == ['rules'] and method == 'POST':
            if handler.body() != {}:
                _fail('invalid_request', 'An empty request is required.', 422)
            ruleset = create_rules(ctx)
            handler._w21_speech_final = lambda: _rule_fence(ctx, ruleset['ruleSetId'], ruleset)
            return 201, {'ruleSet': ruleset}
        if len(parts) == 2 and parts[0] == 'rules':
            rule_id = parts[1]
            if method == 'GET':
                with ctx.lock:
                    ruleset = _rule_load(ctx, rule_id)['ruleset']
            elif method in ('PUT', 'DELETE'):
                ruleset = update_rules(ctx, rule_id, handler.body(), delete=method == 'DELETE')
            else:
                _fail('not_found', 'Pronunciation rules unavailable.', 404)
            handler._w21_speech_final = lambda: _rule_fence(ctx, rule_id, ruleset)
            return 200, {'ruleSet': ruleset}
        if parts == ['runs'] and method == 'POST':
            body = handler.body()
            if not isinstance(body, dict) or 'ref' not in body or set(body) - {'ref','recognitionMode'}:
                _fail('invalid_request', 'A source reference is required.', 422)
            run_id = create_run(ctx, body['ref'], body.get('recognitionMode', 'final_only'))
            with ctx.lock:
                state = _load(ctx, run_id)['state']
            handler._w21_speech_final = lambda: _fence_state(ctx, run_id, state)
            return 201, {'runId': run_id, 'state': state}
        if len(parts) >= 2 and parts[0] == 'runs':
            run_id = parts[1]
            if len(parts) == 2 and method == 'GET':
                with ctx.lock:
                    state = _load(ctx, run_id)['state']
            elif len(parts) == 3 and parts[2] == 'generation' and method == 'POST':
                body = handler.body()
                if not isinstance(body, dict) or set(body) != {'request', 'policyRevision'}:
                    _fail('invalid_request', 'A speech request and policy revision are required.', 422)
                return 200, {'delivery': admit_generation(ctx, run_id, body['request'], body['policyRevision'])}
            elif len(parts) == 4 and parts[2] == 'generation' and method in ('GET', 'DELETE'):
                return 200, {'delivery': view_generation(ctx, run_id, parts[3], cancel=method == 'DELETE')}
            elif len(parts) == 3 and method == 'POST' and parts[2] == 'chunks':
                body = handler.body()
                if body == {'operation':'create_incremental_preview'}:
                    preview_id, state = incremental_preview(ctx, run_id)
                    handler._w21_speech_final = lambda: _fence_state(ctx, preview_id, state)
                    return 201, {'runId':preview_id, 'state':state}
                if not isinstance(body, dict) or set(body) != {'chunk', 'audioBase64'} or not isinstance(body['audioBase64'], str) or len(body['audioBase64']) > 16 * 1024 * 1024:
                    _fail('invalid_request', 'A bounded audio chunk is required.', 422)
                try:
                    audio = base64.b64decode(body['audioBase64'], validate=True)
                except (ValueError, TypeError):
                    _fail('invalid_audio', 'Invalid audio encoding.', 422)
                state = (ingest_prefix(ctx, run_id, body['chunk'], audio)
                         if isinstance(body['chunk'], dict) and body['chunk'].get('recognitionMode') == 'incremental_prefix'
                         else ingest(ctx, run_id, body['chunk'], audio))
            elif len(parts) == 3 and method == 'POST' and parts[2] == 'preview':
                body = handler.body()
                result, state, ruleset = preview_rules(ctx, run_id, body)
                handler._w21_speech_final = lambda: _preview_fence(ctx, run_id, state, ruleset['ruleSetId'], ruleset)
                return 200, {'preview': result}
            elif len(parts) == 3 and method == 'POST' and parts[2] in ('revise', 'finalize'):
                body = handler.body()
                if not isinstance(body, dict):
                    _fail('invalid_request', 'Invalid speech operation.', 422)
                state = mutate(ctx, run_id, parts[2], body)
            else:
                _fail('not_found', 'Speech route unavailable.', 404)
            handler._w21_speech_final = lambda: _fence_state(ctx, run_id, state)
            return 200, {'runId': run_id, 'state': state, 'gaps': stream.gaps(state)}
        _fail('not_found', 'Speech route unavailable.', 404)
    except pronunciation.PronunciationError as exc:
        _fail(str(exc), 'Pronunciation operation unavailable.', 422)
    except stream.SpeechStreamError as exc:
        _fail(str(exc), 'Speech operation unavailable.', 422)


def edition_metadata(ctx, record_projection):
    """Read current private speech cues associated with an approved record.

    This creator-only result is private and must never be added to a public
    edition. The caller must repeat this read under the final serialization
    lock. Missing, stale or unauthorized associations return explicit absence.
    """
    from . import waves18_records as records
    absent = {'state': 'absent', 'scope': 'private', 'cues': []}
    if not isinstance(record_projection, dict) or not isinstance(record_projection.get('id'), str):
        return absent
    with ctx.lock:
        try:
            ctx.check_actor()
            if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') != 'creator':
                return absent
            record = records.fetch(ctx.sid, record_projection['id'])
            if record.get('creatorId') != ctx.actor.get('owner'):
                return absent
            current = records.projection(ctx.sid, record, record_projection.get('language'))
            if current != record_projection:
                return absent
            refs = current['refs']
            ctx.resolve(refs)
            cues = []
            for candidate in ctx.store.all(KIND, ctx.sid):
                if candidate.get('ref') not in refs:
                    continue
                try:
                    obj = _load(ctx, candidate['id'])
                except (Phase10Error, stream.SpeechStreamError, KeyError, ValueError):
                    continue
                state, ref = obj['state'], obj['ref']
                if state.get('scope') != 'private' or state.get('clock') != 'run-relative-milliseconds':
                    continue
                for history in state.get('segments', {}).values():
                    if not isinstance(history, list) or not history or not isinstance(history[-1], dict):
                        continue
                    event = history[-1]
                    interval = event.get('interval')
                    if (event.get('state') != 'final' or event.get('captureRunId') != state.get('captureRunId')
                            or event.get('sourceRef') != ref['sourceId'] or not isinstance(interval, dict)
                            or type(interval.get('startMs')) is not int or type(interval.get('endMs')) is not int
                            or not ref['startMs'] <= interval['startMs'] < interval['endMs'] <= ref['endMs']
                            or type(event.get('revision')) is not int or event['revision'] < 1
                            or event.get('language') not in ('en', 'es', 'mixed', 'unknown')
                            or not isinstance(event.get('text'), str) or not 1 <= len(event['text'].strip()) <= 4000):
                        continue
                    cues.append({'sourceRef': dict(ref), 'captureRunId': state['captureRunId'],
                                 'inputKind': state['inputKind'], 'clock': state['clock'],
                                 'segmentId': event['segmentId'], 'revision': event['revision'],
                                 'startMs': interval['startMs'], 'endMs': interval['endMs'],
                                 'language': event['language'], 'text': event['text']})
            if not cues:
                return absent
            cues.sort(key=lambda c: (c['sourceRef']['sourceId'], c['startMs'], c['endMs'], c['segmentId']))
            return {'state': 'available', 'scope': 'private', 'recordId': record['id'],
                    'recordVersion': record['version'], 'recordRevision': record['_revision'], 'cues': cues}
        except (Phase10Error, KeyError, TypeError, ValueError):
            return absent


def invalidate_source_db(db, sid, source_id):
    """PRIMARY invokes in its source-change transaction under store.LOCK.

    Preserve claims and receipts, including unknown effects, while making every
    derived run permanently ineligible. This hook performs no model work and
    does not commit its caller's transaction. Scheduler invalidation remains
    PRIMARY's separate existing hook.
    """
    rows = db.execute("SELECT id,data FROM objects WHERE kind=? AND session_id=?",
                      (KIND, sid)).fetchall()
    changed = 0
    for row in rows:
        obj = json.loads(row['data'])
        if obj.get('ref', {}).get('sourceId') != source_id or obj.get('invalidated') is True:
            continue
        obj['invalidated'] = True
        changed += db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=?",
                              (json.dumps(obj, ensure_ascii=False), KIND, row['id'], sid)).rowcount
    return changed


def cleanup_db(db, sid, owner=None):
    """PRIMARY invokes in the existing session/owner cleanup transaction.

    This deletes only this module's private data. Other scheduler/provider
    receipts and unknown holds are outside its ownership and remain intact.
    """
    if owner is None:
        return db.execute("DELETE FROM objects WHERE session_id=? AND kind IN (?,?,?)",
                          (sid, KIND, RULE_KIND, GENERATION_KIND)).rowcount
    return db.execute("DELETE FROM objects WHERE session_id=? AND owner_id=? AND kind IN (?,?,?)",
                      (sid, owner, KIND, RULE_KIND, GENERATION_KIND)).rowcount


class _StoredContext(Context):
    """Internal worker context that rechecks a persisted credential hash, never a bearer."""
    def __init__(self, sid, actor, credential_hash):
        super().__init__(None, sid, actor)
        self.credential_hash = credential_hash

    def check_actor(self):
        from . import lifecycle
        with self.lock, self.store.connect() as db:
            row = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?',
                             (self.credential_hash,)).fetchone()
            current = dict(role=row[0], sid=row[1], owner=row[2]) if row else None
            session = self.store.get('session', self.sid, self.sid)
            if current != self.actor or not session or not lifecycle.active(session):
                _fail('not_found', 'The session or capability is unavailable.', 404)
            return current


def resolve_generation(identity):
    """Reconstruct a current private speech plan for a scheduler worker.

    No token is stored or recovered. Every call verifies the exact persisted
    credential, actor, session, source, final revision and rule set. Returns
    None when authority is absent, stale, ambiguous or inconsistent.
    PRIMARY must additionally enforce current policy and subscriber authority.
    """
    from . import store
    from .waves20_delivery import Identity
    if not isinstance(identity, Identity) or not identity.private_actor:
        return None
    with store.LOCK, store.connect() as db:
        rows = db.execute('SELECT data FROM objects WHERE kind=? AND session_id=? AND owner_id=?',
                          (KIND, identity.session, identity.private_actor)).fetchall()
        matches = []
        for row in rows:
            try:
                obj = json.loads(row['data'])
                credential = obj['credentialHash']
                actor = {'role': 'creator', 'sid': identity.session, 'owner': identity.private_actor}
                ctx = _StoredContext(identity.session, actor, credential)
                requests = obj['state'].get('generationRequests', {})
                if not isinstance(requests, dict):
                    continue
                for request_id in requests:
                    try:
                        current, plan = generation_plan(ctx, obj['id'], request_id)
                        if current == identity:
                            matches.append(plan)
                    except (Phase10Error, stream.SpeechStreamError, pronunciation.PronunciationError,
                            KeyError, TypeError, ValueError):
                        continue
            except (KeyError, TypeError, ValueError):
                continue
        if not matches or any(plan != matches[0] for plan in matches[1:]):
            return None
        return matches[0]


def generation_subscriber(ctx, run_id, request_id):
    """Build a private scheduler subscriber from a persisted, current intent.

    PRIMARY must also enforce its current delivery policy and adapter availability.
    The authority is an opaque request marker, never a bearer token.
    """
    from .waves20_delivery import Subscriber
    request_id = stream._token(request_id)
    with ctx.lock:
        identity, plan = generation_plan(ctx, run_id, request_id)
        marker = hashlib.sha256(json.dumps([ctx.sid, ctx.actor['owner'], request_id],
                                          separators=(',', ':')).encode()).hexdigest()
        with ctx.store.connect() as db:
            row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                             (GENERATION_KIND, marker, ctx.sid)).fetchone()
        if not row or row['owner_id'] != ctx.actor['owner']:
            _fail('not_found', 'Speech request unavailable.', 404)
        request = json.loads(row['data'])
        subscriber = Subscriber(actor=ctx.actor['owner'], stream=run_id,
                                sequence=request['preview']['expectedRevision'], authority=marker)
        return identity, subscriber, plan


def eligible_generation_subscriber(identity, subscriber):
    """Recheck exact private credential, request, source, segment and rules.

    This is only the speech-specific part of eligibility, not PRIMARY policy.
    """
    from . import store
    from .waves20_delivery import Identity, Subscriber
    if (not isinstance(identity, Identity) or not isinstance(subscriber, Subscriber)
            or not identity.private_actor or subscriber.actor != identity.private_actor):
        return False
    try:
        with store.LOCK, store.connect() as db:
            row = db.execute('SELECT data,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',
                             (GENERATION_KIND, subscriber.authority, identity.session)).fetchone()
            if not row or row['owner_id'] != subscriber.actor:
                return False
            request = json.loads(row['data'])
            if request.get('runId') != subscriber.stream:
                return False
            obj = store.get(KIND, subscriber.stream, identity.session)
            if not obj or obj.get('owner') != subscriber.actor:
                return False
            actor = {'role': 'creator', 'sid': identity.session, 'owner': subscriber.actor}
            ctx = _StoredContext(identity.session, actor, obj['credentialHash'])
            expected, current, _ = generation_subscriber(ctx, subscriber.stream, request['requestId'])
            return expected == identity and current == subscriber
    except (Phase10Error, stream.SpeechStreamError, pronunciation.PronunciationError,
            KeyError, TypeError, ValueError):
        return False


def resolve_delivery_request(handler, sid, actor, body):
    """Resolve a prepared speech request for PRIMARY's delivery resolver.

    PRIMARY must additionally check its current policy and adapter availability;
    this function does not confer either. A non-speech source returns None.
    """
    source = body.get('source') if isinstance(body, dict) else None
    if not isinstance(source, str) or not source.startswith('speech:'):
        return None
    run_id = stream._token(source[len('speech:'):])
    ctx = Context(handler, sid, actor)
    identity, subscriber, _ = generation_subscriber(ctx, run_id, body.get('requestId'))
    if (body.get('sourceRevision') != int(identity.source_revision)
            or body.get('language') != identity.language or body.get('voice') != identity.voice
            or body.get('choice') != 'local'):
        _fail('stale_context', 'Speech delivery selection changed.')
    return identity, subscriber


def _delivery_body(ctx, run_id, request_id, policy_revision):
    identity, subscriber, _ = generation_subscriber(ctx, run_id, request_id)
    if type(policy_revision) is not int or not 0 <= policy_revision <= 9007199254740991:
        _fail('invalid_request', 'Invalid policy revision.', 422)
    source = 'speech:' + run_id
    if len(source) > 128:
        _fail('invalid_request', 'Speech run identifier is too long.', 422)
    return identity, subscriber, {'requestId': request_id, 'source': source,
        'sourceRevision': int(identity.source_revision), 'language': identity.language,
        'voice': identity.voice, 'policyRevision': policy_revision, 'choice': 'local'}


def admit_generation(ctx, run_id, request, policy_revision):
    """Prepare then admit through the existing PRIMARY-owned scheduler facade."""
    from . import waves20_scheduler as delivery
    if type(policy_revision) is not int or not 0 <= policy_revision <= 9007199254740991:
        _fail('invalid_request', 'Invalid policy revision.', 422)
    if delivery._service is None:
        _fail('unavailable', 'Delivery unavailable.', 503)
    with ctx.lock, delivery._service.lock:
        marker = prepare_generation(ctx, run_id, request)
        identity, subscriber, body = _delivery_body(ctx, run_id, marker['requestId'], policy_revision)
        service = delivery._service
        service._auth(ctx.handler, ctx.sid, ctx.actor)
        resolved = service._resolved(ctx.handler, ctx.sid, ctx.actor, body)
        if resolved != (identity, subscriber):
            _fail('unavailable', 'Speech delivery binding unavailable.', 409)
        result = service.admit(ctx.handler, ctx.sid, ctx.actor, body)
        if result.get('ticket') in service.live:
            result = service.view(ctx.handler, ctx.sid, ctx.actor, result['ticket'])
        ctx.handler._w21_speech_final = lambda: _generation_fence(ctx, run_id, marker['requestId'], identity, subscriber)
        return result


def _generation_fence(ctx, run_id, request_id, identity, subscriber):
    current, actual, _ = generation_subscriber(ctx, run_id, request_id)
    if current != identity or actual != subscriber:
        _fail('stale_context', 'Speech delivery changed; refresh.')


def view_generation(ctx, run_id, request_id, *, cancel=False):
    """Read or cancel only the authenticated request's durable delivery receipt."""
    from . import waves20_scheduler as delivery
    if delivery._service is None:
        _fail('unavailable', 'Delivery unavailable.', 503)
    with ctx.lock, delivery._service.lock:
        identity, subscriber, _ = generation_subscriber(ctx, run_id, request_id)
        key = delivery._hash(['receipt', ctx.sid, ctx.actor['owner'], request_id])
        service = delivery._service
        item = service.live.get(key)
        if item and (item[1], item[2]) != (identity, subscriber):
            _fail('stale_context', 'Speech delivery changed; refresh.')
        result = (service.cancel if cancel else service.view)(ctx.handler, ctx.sid, ctx.actor, key)
        ctx.handler._w21_speech_final = lambda: _generation_fence(ctx, run_id, request_id, identity, subscriber)
        return result

