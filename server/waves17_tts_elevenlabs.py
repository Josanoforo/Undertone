"""Fixture-tested, explicitly selected ElevenLabs PCM adapter. No network client or key storage.

transport(*, path, body, timeout_seconds, max_bytes, cancelled) -> Response.
The injected transport MUST POST to the fixed official HTTPS origin, inject its secret
privately, reject redirects, bound both time and body, close on cancellation and signal
incomplete HTTP bodies with TransportFailure. It must never log request/response data.
"""
from dataclasses import dataclass, field
import hashlib
import io
import json
import math
import re
import time
import wave

MODEL = 'eleven_multilingual_v2'
FORMAT = 'pcm_16000'
ADAPTER_REVISION = 'elevenlabs-pcm-wav-1'
MAX_TEXT = 600
MAX_PCM = 960000  # 30 seconds of mono 16-bit 16 kHz

@dataclass(frozen=True)
class Config:
    available: bool
    model: str
    model_version: str
    voice_id: str
    voice_version: str
    languages: tuple
    stock_voice_verified: bool
    rights_verified: bool
    format_verified: bool

@dataclass(frozen=True)
class Request:
    text: str = field(repr=False)
    language: str
    voice_id: str
    model: str
    settings: dict = field(repr=False)
    revisions: dict = field(repr=False)
    request_id: str
    output_format: str = FORMAT

@dataclass(frozen=True)
class Response:
    status: int
    headers: dict = field(repr=False)
    body: bytes = field(repr=False)
    complete: bool = True

class TransportFailure(Exception):
    """Transport failure; kind is timeout, cancelled, truncated or transport."""
    def __init__(self, kind='transport'):
        self.kind = kind if kind in ('timeout', 'cancelled', 'truncated', 'transport') else 'transport'
        super().__init__(self.kind)

class SpeechError(Exception):
    def __init__(self, code, metadata):
        self.code = code
        self.metadata = metadata
        super().__init__(code)

_REQUIRED_REVISIONS = ('text_revision', 'source_id', 'source_revision', 'translation_id',
                       'translation_revision', 'terminology_revision')

def _valid_token(value):
    return isinstance(value, str) and 1 <= len(value) <= 160

def _settings(settings):
    if not isinstance(settings, dict) or set(settings) != {'stability', 'similarity_boost', 'style', 'use_speaker_boost'}:
        raise ValueError()
    for key in ('stability', 'similarity_boost', 'style'):
        value = settings[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError()
    if type(settings['use_speaker_boost']) is not bool:
        raise ValueError()
    return dict(settings)

def cache_identity(config, request):
    """Private deterministic digest only; equality is not a reuse authorization."""
    obj = {'text': request.text, 'language': request.language, 'voice_id': request.voice_id,
           'voice_version': config.voice_version, 'model': request.model,
           'model_version': config.model_version, 'settings': _settings(request.settings),
           'output_format': request.output_format, 'adapter_revision': ADAPTER_REVISION,
           'engine': 'elevenlabs', 'revisions': request.revisions}
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()

def _safe_metadata(headers, meta):
    if not isinstance(headers, dict):
        return
    h = {str(k).lower(): v for k, v in headers.items()}
    # Do not relay arbitrary provider text, headers, error bodies, or trace values.
    rid = h.get('request-id')
    if isinstance(rid, str) and re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', rid):
        meta['providerRequestId'] = rid
    cost = h.get('character-cost')
    if isinstance(cost, str) and re.fullmatch(r'[0-9]{1,9}', cost):
        meta['providerCharacterCost'] = int(cost)
        meta['characterCostCertainty'] = 'provider_reported'

def synthesize(config, request, transport, cancelled, eligible):
    """One bounded dispatch, no retries; caller owns final publication synchronization."""
    meta = {'engine': 'elevenlabs', 'providerRequests': 0, 'outcome': 'not_dispatched',
            'credits': None, 'cost': None, 'costCertainty': 'unknown',
            'providerCharacterCost': None, 'characterCostCertainty': 'unknown',
            'providerRequestId': None, 'firstAudioMs': None, 'cancelled': False}
    def fail(code):
        raise SpeechError(code, dict(meta)) from None
    try:
        if not isinstance(config, Config) or not isinstance(request, Request):
            fail('invalid_input')
        if not isinstance(request.request_id, str) or not re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', request.request_id):
            fail('invalid_request_id')
        meta['requestId'] = request.request_id
        if (config.available is not True or config.stock_voice_verified is not True or
            config.rights_verified is not True or config.format_verified is not True or
            not _valid_token(config.model_version) or not _valid_token(config.voice_version)):
            fail('unavailable')
        if config.model != MODEL or request.model != MODEL:
            fail('unsupported_model')
        if (not isinstance(config.voice_id, str) or not re.fullmatch(r'[A-Za-z0-9]{20}', config.voice_id)
            or request.voice_id != config.voice_id):
            fail('unsupported_voice')
        if request.language not in ('en', 'es') or request.language not in config.languages:
            fail('unsupported_language')
        if request.output_format != FORMAT:
            fail('unsupported_format')
        if not isinstance(request.text, str) or not request.text.strip() or len(request.text) > MAX_TEXT:
            fail('invalid_text')
        if (not isinstance(request.revisions, dict) or set(request.revisions) != set(_REQUIRED_REVISIONS)
            or any(not _valid_token(request.revisions[k]) for k in _REQUIRED_REVISIONS)):
            fail('invalid_revisions')
        try:
            settings = _settings(request.settings)
            request.text.encode('utf-8')
        except (ValueError, UnicodeError):
            fail('invalid_input')
        def current():
            try:
                if cancelled():
                    meta['cancelled'] = True
                    fail('cancelled')
                if eligible() is not True:
                    fail('ineligible')
            except SpeechError:
                raise
            except Exception:
                fail('eligibility_unavailable')
        current()
        payload = json.dumps({'text': request.text, 'model_id': MODEL, 'voice_settings': settings}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        started = time.monotonic()
        meta['providerRequests'] = 1
        meta['outcome'] = 'unknown'
        try:
            response = transport(path='/v1/text-to-speech/' + config.voice_id + '?output_format=' + FORMAT,
                                 body=payload, timeout_seconds=30, max_bytes=MAX_PCM, cancelled=cancelled)
        except TransportFailure as exc:
            if exc.kind == 'cancelled':
                meta['cancelled'] = True
            fail(exc.kind)
        except TimeoutError:
            fail('timeout')
        except Exception:
            fail('transport')
        meta['synthesisMs'] = round((time.monotonic() - started) * 1000, 2)
        if not isinstance(response, Response):
            fail('invalid_response')
        _safe_metadata(response.headers, meta)
        current()
        if not response.complete:
            fail('truncated')
        if response.status != 200:
            fail({401:'unauthorized', 403:'forbidden', 429:'rate_or_quota_limited'}.get(response.status, 'http_error'))
        headers = {str(k).lower(): v for k, v in response.headers.items()}
        content_type = headers.get('content-type', '')
        if not isinstance(content_type, str) or content_type.split(';', 1)[0].strip().lower() not in ('audio/pcm', 'audio/pcm_s16le', 'application/octet-stream'):
            fail('invalid_content_type')
        pcm = response.body
        if not isinstance(pcm, bytes) or not pcm or len(pcm) > MAX_PCM or len(pcm) % 2:
            fail('invalid_audio')
        length = headers.get('content-length')
        if length is not None and (not isinstance(length, str) or not re.fullmatch(r'[0-9]{1,10}', length) or int(length) != len(pcm)):
            fail('truncated')
        out = io.BytesIO()
        with wave.open(out, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)
        current()
        meta.update({'outcome': 'response_received', 'characters': len(request.text), 'mimeType': 'audio/wav',
                     'sampleRate': 16000, 'durationSeconds': len(pcm) / 32000,
                     'model': MODEL, 'modelVersion': config.model_version, 'voiceId': config.voice_id,
                     'voiceVersion': config.voice_version, 'language': request.language,
                     'adapterRevision': ADAPTER_REVISION})
        return out.getvalue(), meta
    except SpeechError:
        raise
    except Exception:
        fail('invalid_input')


