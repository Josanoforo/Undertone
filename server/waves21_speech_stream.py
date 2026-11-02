"""Revisioned speech state. Store mutation and downstream dispatch belong to PRIMARY."""
import copy
import hashlib
import json
import math
import re

class SpeechStreamError(ValueError):
    pass

def _token(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        raise SpeechStreamError('invalid_id')
    return value

def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise SpeechStreamError('invalid_number')
    return value

def _text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 4000:
        raise SpeechStreamError('invalid_text')
    return value

def _language(value):
    if value not in ('en', 'es', 'mixed', 'unknown'):
        raise SpeechStreamError('invalid_language')
    return value

def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def new_run(run_id, source_ref, scope, input_kind='unknown'):
    _token(run_id); _token(source_ref)
    if scope not in ('private', 'shared'):
        raise SpeechStreamError('invalid_scope')
    if input_kind not in ('live_program_audio', 'file_replay', 'unknown'):
        raise SpeechStreamError('invalid_input_kind')
    return {'captureRunId': run_id, 'sourceRef': source_ref, 'scope': scope, 'inputKind': input_kind,
            'clock': 'run-relative-milliseconds', 'chunks': {}, 'segments': {}, 'intents': {}, 'receipts': {}}

def _authorize(run, authorize, action):
    if not callable(authorize) or authorize(action, copy.deepcopy(run)) is not True:
        raise SpeechStreamError('forbidden_or_revoked')

def _interval(start, end):
    _integer(start, 0, 864000000); _integer(end, 1, 864000000)
    if end <= start or end-start > 120000: raise SpeechStreamError('invalid_interval')
    return {'startMs': start, 'endMs': end}

def faster_whisper(audio, mime_type, language=None):
    """Buffered real ASR: returned segments are final, never invented partials."""
    from . import asr
    if language is not None:
        return dict(asr.transcribe(audio, mime_type, language), resultMode='final_only')
    # The installed adapter removes silence by concatenating VAD regions, then
    # chooses ONE language for that entire buffer. Preserve the existing VAD
    # regions so an unhinted EN/ES change across a pause is detected separately.
    # Keep the shared adapter/configuration untouched, including its loader.
    import base64
    import os
    from pathlib import Path
    import subprocess
    import sys
    mime = asr._check_audio(audio, mime_type)
    interpreter = asr._external_python() or sys.executable
    env = dict(os.environ, ASR_LANGUAGE='', HF_HUB_OFFLINE='1',
               TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    env.pop('ASR_PYTHON', None)
    try:
        completed = subprocess.run([interpreter, '-I', str(Path(__file__).resolve()), '--auto-vad-worker'],
            input=json.dumps({'audio':base64.b64encode(audio).decode('ascii'), 'mime':mime}),
            capture_output=True, text=True, encoding='utf-8', env=env, timeout=180,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if completed.returncode or len(completed.stdout) > 1024 * 1024:
            raise asr.ASRUnavailable('The local speech-region worker did not complete.')
        result = json.loads(completed.stdout)
        if not isinstance(result, dict) or 'error' in result:
            raise asr.ASRUnavailable('The local speech-region worker returned no usable result.')
        return result
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise asr.ASRUnavailable('The local speech-region worker failed; no automatic retry.') from exc


def _vad_transcribe_local(audio, mime_type):
    """Pause-delimited automatic language detection, not speaker separation.

    Invoked only in the bounded worker. Uses the existing ASR decoder/model,
    default installed Silero regions and cached model. No language hint,
    expected transcript, known splice offset or new model is supplied.
    """
    import io
    import wave
    import numpy as np
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    from . import asr
    values = asr._decode(audio, asr._check_audio(audio, mime_type))
    regions = get_speech_timestamps(values, VadOptions())
    if len(regions) > 32:
        raise asr.ASRUnavailable('Too many speech regions for one bounded chunk.')
    output, trace, languages = [], [], set()
    for region in regions:
        start, end = region['start'], region['end']
        if not 0 <= start < end <= len(values):
            raise asr.ASRUnavailable('Invalid detected speech region.')
        target = io.BytesIO()
        with wave.open(target, 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(asr.RATE)
            samples = np.clip(np.rint(values[start:end] * 32768), -32768, 32767).astype('<i2')
            f.writeframes(samples.tobytes())
        # The worker has no external interpreter setting or forced language;
        # call the original adapter, reusing its same cached CPU/int8 model.
        decoded = asr.transcribe(target.getvalue(), 'audio/wav', None)
        language = decoded.get('language')
        language = language if language in ('en', 'es') else 'unknown'
        languages.add(language)
        trace.append({'startSample':start, 'endSample':end, 'sampleRate':asr.RATE,
                      'language':language, 'languageHint':None})
        for item in decoded['segments']:
            output.append(dict(item, start=item['start'] + start/asr.RATE,
                               end=item['end'] + start/asr.RATE, language=language))
    language = ('mixed' if languages == {'en', 'es'} else next(iter(languages)) if len(languages) == 1 else 'unknown')
    return {'text':' '.join(s['text'] for s in output), 'segments':output, 'language':language,
            'provider':'faster-whisper-local', 'resultMode':'final_only',
            'recognitionStrategy':'automatic_language_per_vad_region', 'recognitionIntervals':trace,
            'limitations':['Completed fragments only; no incremental ASR events.',
                            'Language changes without a detected pause may remain incorrect.',
                            'No overlap detection or voice separation; simultaneous speech may be omitted.']}

def ingest(run, chunk, audio, adapter, authorize):
    """Return a new run; caller commits it atomically with compare-and-swap."""
    _authorize(run, authorize, 'ingest')
    run = copy.deepcopy(run); cid = _token(chunk['chunkId'])
    start = chunk['startMs']; end = chunk['endMs']; interval = _interval(start, end)
    if not isinstance(audio, bytes) or not 0 < len(audio) <= 12*1024*1024: raise SpeechStreamError('invalid_audio')
    mime = chunk['mimeType']; requested = chunk.get('language')
    if not isinstance(mime, str) or len(mime) > 128 or requested not in (None, 'en', 'es'): raise SpeechStreamError('invalid_chunk')
    fingerprint = _digest({'interval': interval, 'mime': mime, 'language': requested, 'audioSha256': hashlib.sha256(audio).hexdigest()})
    old = run['chunks'].get(cid)
    if old:
        if old['fingerprint'] != fingerprint: raise SpeechStreamError('duplicate_conflict')
        return run
    if len(run['chunks']) >= 1000: raise SpeechStreamError('run_full')
    for other in run['chunks'].values():
        iv = other['interval']
        if start < iv['endMs'] and end > iv['startMs']: raise SpeechStreamError('chunk_overlap')
    response = adapter(audio, mime, requested)
    if not isinstance(response, dict) or not isinstance(response.get('segments'), list) or len(response['segments']) > 200: raise SpeechStreamError('invalid_adapter_result')
    lang = response.get('language'); lang = lang if lang in ('en', 'es', 'mixed') else 'unknown'
    produced = []
    for index, item in enumerate(response['segments']):
        a = item.get('start'); b = item.get('end')
        if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int,float)) or not isinstance(b, (int,float)) or not math.isfinite(a) or not math.isfinite(b): raise SpeechStreamError('invalid_adapter_interval')
        s, e = start + round(a*1000), start + round(b*1000)
        if s < start or e > end: raise SpeechStreamError('invalid_adapter_interval')
        iv = _interval(s,e); text = _text(item.get('text')); sid = cid + ':' + str(index)
        if len(sid) > 128: raise SpeechStreamError('invalid_id')
        # This adapter consumes a complete chunk and has no partial-result API.
        # Human corrections remain separately revisioned; do not relabel a
        # completed decode as provisional to imply streaming recognition.
        item_language = item.get('language', lang)
        item_language = item_language if item_language in ('en', 'es', 'mixed') else 'unknown'
        event = {'captureRunId':run['captureRunId'], 'sourceRef':run['sourceRef'], 'inputKind':run.get('inputKind', 'unknown'), 'interval':iv, 'segmentId':sid, 'revision':1, 'language':item_language, 'originalLanguage':item_language, 'state':'final', 'text':text, 'originalText':text, 'recognitionMode':'final_only', 'speaker':'unknown'}
        run['segments'][sid] = [event]; produced.append(sid)
    run['chunks'][cid] = {'fingerprint':fingerprint,'interval':interval,'segmentIds':produced, 'recognitionMode':'final_only'}
    if response.get('recognitionStrategy') == 'automatic_language_per_vad_region':
        run['chunks'][cid].update(recognitionStrategy=response['recognitionStrategy'], recognitionIntervals=copy.deepcopy(response['recognitionIntervals']))
    return run

def prefix_result(run, chunk, response, authorize):
    """Revision of one open utterance from real, growing-prefix recognition.

    The decoder still buffers each prefix. Its words are hypotheses about the
    open utterance, not native engine partials or a semantic turn boundary.
    Runtime owns provenance, sequencing, durable claims and the side effect.
    """
    _authorize(run, authorize, 'ingest')
    run = copy.deepcopy(run)
    cid = _token(chunk['chunkId'])
    sid = _token(cid + ':prefix')
    iv = _interval(chunk['startMs'], chunk['endMs'])
    previous = run.get('prefix')
    sequence = _integer(chunk['sequence'], 1, 64)
    if type(chunk['final']) is not bool:
        raise SpeechStreamError('invalid_final')
    if previous:
        if (previous['final'] or previous['chunkId'] != cid or
                sequence != previous['sequence'] + 1 or
                iv['startMs'] != previous['startMs'] or iv['endMs'] <= previous['endMs']):
            raise SpeechStreamError('stale_prefix')
    elif sequence != 1 or run['chunks']:
        raise SpeechStreamError('stale_prefix')
    history = run['segments'].get(sid, [])
    current_revision = history[-1]['revision'] if history else 0
    if type(chunk['expectedRevision']) is not int or chunk['expectedRevision'] != current_revision:
        raise SpeechStreamError('stale_revision')
    if not isinstance(response, dict) or not isinstance(response.get('segments'), list) or len(response['segments']) > 200:
        raise SpeechStreamError('invalid_adapter_result')
    texts, languages, decoder_intervals = [], set(), []
    for item in response['segments']:
        a, b = item.get('start'), item.get('end')
        if (type(a) not in (int, float) or type(b) not in (int, float) or
                not math.isfinite(a) or not math.isfinite(b) or a < 0 or
                b <= a or b > 120):
            raise SpeechStreamError('invalid_adapter_interval')
        # Whisper may timestamp the padded decoder window beyond a received
        # prefix. Preserve that evidence; do not trim audio, invent word timing
        # or mistake decoder timestamps for a received utterance boundary.
        decoder_intervals.append({'startSeconds':a, 'endSeconds':b})
        texts.append(_text(item.get('text')))
        languages.add(_language(item.get('language', response.get('language', 'unknown'))))
    text = _text(' '.join(texts)) if texts else ''
    language = ('mixed' if languages == {'en', 'es'} else
                next(iter(languages)) if len(languages) == 1 else 'unknown')
    event = {'captureRunId':run['captureRunId'], 'sourceRef':run['sourceRef'],
             'inputKind':run['inputKind'], 'interval':iv, 'segmentId':sid,
             'revision':current_revision + 1, 'language':language,
             'originalLanguage':language, 'text':text, 'originalText':text,
             'state':('final' if chunk['final'] else 'provisional') if text else 'gap',
             'recognitionMode':'incremental_prefix', 'speaker':'unknown',
             'sequence':sequence, 'decoderIntervals':decoder_intervals,
             'timingSupport':'received_prefix_only',
             'finalization':'explicit' if chunk['final'] else 'open_utterance'}
    history.append(event)
    run['segments'][sid] = history
    run['prefix'] = {**iv, 'chunkId':cid, 'sequence':sequence, 'final':chunk['final']}
    run['chunks'][cid] = {'interval':iv, 'segmentIds':[sid] if text else [],
                          'recognitionMode':'incremental_prefix'}
    run['recognitionMode'] = 'incremental_prefix'
    return run


def revise(run, segment_id, expected_revision, text, language, authorize):
    _authorize(run, authorize, 'revise'); run = copy.deepcopy(run); _token(segment_id)
    history = run['segments'].get(segment_id)
    if not history: raise SpeechStreamError('segment_missing')
    current = history[-1]; _integer(expected_revision, 1, 1000000)
    if current['revision'] != expected_revision: raise SpeechStreamError('stale_revision')
    if len(history) >= 1000: raise SpeechStreamError('revision_limit')
    event = dict(current, revision=expected_revision+1, text=_text(text), language=_language(language), state='correction' if current['state'] in ('final','correction') else 'provisional', correctionOf=expected_revision)
    history.append(event); return run

def finalize(run, segment_id, expected_revision, authorize):
    _authorize(run, authorize, 'finalize'); run = copy.deepcopy(run); _token(segment_id)
    history = run['segments'].get(segment_id)
    if not history: raise SpeechStreamError('segment_missing')
    current = history[-1]
    if type(expected_revision) is not int or current['revision'] != expected_revision: raise SpeechStreamError('stale_revision')
    if current['state'] == 'final': return run
    if len(history) >= 1000: raise SpeechStreamError('revision_limit')
    history.append(dict(current, revision=expected_revision+1, state='final', correctionOf=current.get('correctionOf')))
    return run

def gaps(run):
    issues = list(run.get('recognitionIssues', {}).values())
    spans = sorted((x['interval']['startMs'], x['interval']['endMs']) for x in list(run['chunks'].values()) + issues)
    bounds = run.get('interval', {})
    cursor = bounds.get('startMs', 0); result = []
    for start,end in spans:
        if start > cursor: result.append({'state':'gap','interval':{'startMs':cursor,'endMs':start}})
        cursor = max(cursor,end)
    if bounds.get('endMs', cursor) > cursor:
        result.append({'state':'gap', 'interval':{'startMs':cursor,'endMs':bounds['endMs']}})
    for chunk in run['chunks'].values():
        if not chunk['segmentIds']:
            result.append({'state':'gap', 'interval':dict(chunk['interval']), 'reason':'no_speech_detected'})
    result.extend(copy.deepcopy(issues))
    result.sort(key=lambda item: (item['interval']['startMs'], item['interval']['endMs']))
    return result

def prepare_intent(run, segment_id, revision, purpose, request_id, authorize):
    _authorize(run, authorize, 'dispatch'); run = copy.deepcopy(run); _token(request_id)
    if purpose not in ('translation','audio'): raise SpeechStreamError('invalid_purpose')
    history = run['segments'].get(_token(segment_id)); current = history[-1] if history else None
    if not current or current['state'] != 'final' or current['revision'] != revision: raise SpeechStreamError('not_current_final')
    intent = {'requestId':request_id,'segmentId':segment_id,'revision':revision,'purpose':purpose,'scope':run['scope'],'eventDigest':_digest(current)}
    prior = run['intents'].get(request_id)
    if prior and prior != intent: raise SpeechStreamError('duplicate_conflict')
    run['intents'][request_id] = intent
    return run

def record_receipt(run, request_id, receipt, authorize):
    _authorize(run, authorize, 'receipt'); run = copy.deepcopy(run); _token(request_id)
    if request_id not in run['intents']: raise SpeechStreamError('intent_missing')
    if not isinstance(receipt, dict) or set(receipt) != {'status','externalId'} or receipt['status'] not in ('accepted','failed','unknown') or not isinstance(receipt['externalId'], str) or len(receipt['externalId']) > 128: raise SpeechStreamError('invalid_receipt')
    old = run['receipts'].get(request_id)
    if old and old != receipt: raise SpeechStreamError('duplicate_conflict')
    run['receipts'][request_id] = copy.deepcopy(receipt); return run

def transaction(transact, run_id, transition):
    """Execute one state transition in PRIMARY's atomic load/commit callback.

    transact(run_id, transition) must serialize transitions, commit the returned
    state and return it, or raise without committing. It must not replay a
    transition that invokes ASR or any external side effect.
    """
    _token(run_id)
    if not callable(transact) or not callable(transition): raise SpeechStreamError('invalid_transaction')
    def checked(state):
        if not isinstance(state,dict) or state.get('captureRunId') != run_id: raise SpeechStreamError('run_missing')
        updated=transition(copy.deepcopy(state))
        if not isinstance(updated,dict) or updated.get('captureRunId') != run_id: raise SpeechStreamError('invalid_transition')
        return updated
    return transact(run_id,checked)

def eligible_event(run, request_id, authorize):
    """Revalidate a durable intent immediately before dispatch or delivery."""
    _authorize(run,authorize,'dispatch'); _token(request_id)
    intent=run['intents'].get(request_id)
    if not intent or intent['scope'] != run['scope']: raise SpeechStreamError('intent_missing')
    history=run['segments'].get(intent['segmentId']); event=history[-1] if history else None
    if not event or event['state'] != 'final' or event['revision'] != intent['revision'] or _digest(event) != intent['eventDigest']: raise SpeechStreamError('not_current_final')
    return copy.deepcopy(event)


if __name__ == '__main__':
    import base64
    from pathlib import Path
    import sys
    if sys.argv[1:] != ['--auto-vad-worker']:
        raise SystemExit(2)
    # -I deliberately omits the working directory; resolve only this project.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from server.waves21_speech_stream import _vad_transcribe_local
    try:
        request = json.load(sys.stdin)
        result = _vad_transcribe_local(base64.b64decode(request['audio'], validate=True), request['mime'])
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    except Exception:
        print(json.dumps({'error':'asr_unavailable'}))
        raise SystemExit(1)
