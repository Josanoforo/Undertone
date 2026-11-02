"""Local-only faster-whisper adapter; audio is never retained or downloaded.

Optional separate interpreter: ASR_PYTHON. ASR_MODEL_PATH must be a complete
local CT2 directory. Configuration and dependency presence are not ASR proof.
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import struct
import sys
import threading
import wave


class ASRUnavailable(Exception):
    """No usable local transcription was produced; no synthetic fallback."""


MAX_BYTES = 12 * 1024 * 1024
MAX_SECONDS = 120
RATE = 16000
MIMES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/webm",
         "audio/ogg", "audio/mp4", "audio/mpeg"}
_lock = threading.Lock()
_model = None
_model_key = None


def _model_path() -> Path | None:
    value = os.environ.get("ASR_MODEL_PATH", "").strip()
    if not value:
        return None
    root = Path(value)
    # A repository id such as Systran/faster-whisper-small is never accepted.
    if not root.is_absolute() or not root.is_dir():
        return None
    required = ["model.bin", "config.json", "tokenizer.json"]
    try:
        return root if all((root / f).is_file() and (root / f).stat().st_size > 0
                           for f in required) and any((root / f).is_file()
                           for f in ("vocabulary.txt", "vocabulary.json")) else None
    except OSError:
        return None


def _local_status() -> dict:
    configured = bool(os.environ.get("ASR_MODEL_PATH", "").strip())
    root = _model_path()
    try:
        dependency = importlib.util.find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        dependency = False
    limitations = ["Static availability does not establish inference or quality.",
                   "Audio is chunked; capture and session timing belong to the caller."]
    if not root:
        limitations.append("ASR_MODEL_PATH lacks a complete local CT2 directory.")
    if not dependency:
        limitations.append("faster-whisper is not installed in the ASR interpreter.")
    with _lock:
        languages = list(getattr(_model, "supported_languages", [])) if _model is not None else []
    if not languages:
        limitations.append("Languages are unverified until the model is loaded; small.en is English only.")
    return {"configured": configured, "available": bool(root and dependency),
            "model": root.name if root else None, "languages": languages,
            "limitations": limitations}


def _external_python() -> str | None:
    configured = os.environ.get("ASR_PYTHON", "").strip()
    if not configured:
        return None
    if not Path(configured).is_absolute() or not Path(configured).is_file():
        raise ASRUnavailable("ASR_PYTHON does not identify an available local interpreter.")
    return configured


def _invoke_worker(action: str, audio: bytes = b"", mime_type: str = "", language: str | None = None) -> dict:
    interpreter = _external_python()
    payload = {"action": action, "audio": base64.b64encode(audio).decode("ascii"),
               "mime_type": mime_type, "language": language}
    env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
               HF_HUB_DISABLE_TELEMETRY="1")
    env.pop("ASR_PYTHON", None)  # A worker never spawns another worker.
    try:
        result = subprocess.run([interpreter, "-I", str(Path(__file__).resolve()), "--worker"],
                                input=json.dumps(payload), capture_output=True,
                                text=True, encoding="utf-8", env=env,
                                timeout=15 if action == "status" else 180,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode != 0 or len(result.stdout) > 1024 * 1024:
            raise ASRUnavailable("The local ASR process did not complete the operation.")
        response = json.loads(result.stdout)
        if not isinstance(response, dict) or "error" in response:
            raise ASRUnavailable("The local ASR process did not produce a valid transcript.")
        return response
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise ASRUnavailable("The local ASR interpreter failed or timed out.") from exc


def status() -> dict:
    try:
        return _invoke_worker("status") if _external_python() else _local_status()
    except ASRUnavailable as exc:
        return {"configured": bool(os.environ.get("ASR_MODEL_PATH")), "available": False,
                "model": None, "languages": [], "limitations": [str(exc)]}


def _check_audio(audio: bytes, mime_type: str) -> str:
    mime = mime_type.split(";", 1)[0].strip().lower() if isinstance(mime_type, str) else ""
    if not isinstance(audio, bytes) or not audio or len(audio) > MAX_BYTES:
        raise ASRUnavailable("Audio is empty or exceeds the 12 MiB limit.")
    if mime not in MIMES:
        raise ASRUnavailable("Audio format is not supported by ASR.")
    return mime


def _decode(audio: bytes, mime: str):
    import numpy as np
    if mime in {"audio/wav", "audio/x-wav", "audio/wave"}:
        # IEEE float WAV is not supported by Python 3.12's wave module.
        # Parse only the bounded uncompressed float32 form; retain wave's PCM
        # handling below and reject malformed, non-finite or oversized input.
        if len(audio) >= 12 and audio[:4] == b"RIFF" and audio[8:12] == b"WAVE":
            end = struct.unpack_from("<I", audio, 4)[0] + 8
            if end > len(audio) or end < 12:
                raise ASRUnavailable("Truncated WAV.")
            pos, fmt, data = 12, None, None
            while pos + 8 <= end:
                kind, size = struct.unpack_from("<4sI", audio, pos)
                start = pos + 8
                if start + size > end:
                    raise ASRUnavailable("Truncated WAV chunk.")
                if kind == b"fmt " and fmt is None:
                    fmt = audio[start:start + size]
                elif kind == b"data" and data is None:
                    data = audio[start:start + size]
                pos = start + size + (size & 1)
            if fmt is not None and len(fmt) >= 16 and struct.unpack_from("<H", fmt)[0] == 3:
                tag, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
                if (channels not in (1, 2) or not 8000 <= rate <= 192000 or
                        bits != 32 or align != channels * 4 or byte_rate != rate * align or
                        data is None or not data or len(data) % align or
                        len(data) // align > rate * MAX_SECONDS):
                    raise ASRUnavailable("WAV requires bounded float32 mono/stereo audio.")
                values = np.frombuffer(data, dtype="<f4")
                if not np.isfinite(values).all():
                    raise ASRUnavailable("WAV contains non-finite audio.")
                values = np.clip(values, -1.0, 1.0).reshape(-1, channels).mean(axis=1)
                if rate != RATE:
                    positions = np.arange(max(1, round(len(values) * RATE / rate))) * rate / RATE
                    values = np.interp(positions, np.arange(len(values)), values).astype(np.float32)
                return values.astype(np.float32, copy=False)
        # Bypass the historical PyAV metadata_errors incompatibility for PCM WAV.
        with wave.open(io.BytesIO(audio), "rb") as source:
            channels, width, rate, count = (source.getnchannels(), source.getsampwidth(),
                                           source.getframerate(), source.getnframes())
            if width not in (2, 4) or channels not in (1, 2) or not 8000 <= rate <= 192000:
                raise ASRUnavailable("WAV requires PCM16/32, mono/stereo and 8–192 kHz.")
            if not 0 < count <= rate * MAX_SECONDS:
                raise ASRUnavailable("The chunk must be between 0 and 120 seconds long.")
            raw = source.readframes(count)
            if len(raw) != count * channels * width:
                raise ASRUnavailable("Truncated WAV.")
        values = np.frombuffer(raw, dtype="<i2" if width == 2 else "<i4")
        values = (values.astype(np.float32).reshape(-1, channels).mean(axis=1)
                  / float(2 ** (8 * width - 1)))
        if rate != RATE:
            positions = np.arange(max(1, round(len(values) * RATE / rate))) * rate / RATE
            values = np.interp(positions, np.arange(len(values)), values).astype(np.float32)
        return values
    import av
    chunks, samples = [], 0
    formats = {"audio/webm": "matroska", "audio/ogg": "ogg", "audio/mp4": "mov", "audio/mpeg": "mp3"}
    with av.open(io.BytesIO(audio), format=formats[mime],
                 options={"protocol_whitelist": "pipe", "enable_drefs": "0"}) as container:
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=RATE)
        for frame in container.decode(audio=0):
            for normalized in resampler.resample(frame):
                values = normalized.to_ndarray().reshape(-1)
                samples += len(values)
                if samples > MAX_SECONDS * RATE:
                    raise ASRUnavailable("The chunk exceeds 120 seconds.")
                chunks.append(values)
        for normalized in resampler.resample(None):
            values = normalized.to_ndarray().reshape(-1)
            samples += len(values)
            if samples > MAX_SECONDS * RATE:
                raise ASRUnavailable("The chunk exceeds 120 seconds.")
            chunks.append(values)
    if not chunks:
        raise ASRUnavailable("The file contains no decodable audio.")
    return np.concatenate(chunks).astype(np.float32)


def _local_transcribe(audio: bytes, mime: str, requested_language: str | None = None) -> dict:
    global _model, _model_key
    root = _model_path()
    if root is None:
        raise ASRUnavailable("ASR requires ASR_MODEL_PATH with a complete local CT2 model.")
    try:
        from faster_whisper import WhisperModel
        values = _decode(audio, mime)
        with _lock:
            key = str(root.resolve())
            if _model is None or _model_key != key:
                _model = WhisperModel(key, device="cpu", compute_type="int8", cpu_threads=2,
                                      num_workers=1, local_files_only=True)
                _model_key = key
            language = requested_language or os.environ.get("ASR_LANGUAGE", "").strip() or None
            if language and language not in _model.supported_languages:
                raise ASRUnavailable("The local model does not support the requested language.")
            segments, info = _model.transcribe(values, language=language, beam_size=1,
                                               temperature=0.0, condition_on_previous_text=False,
                                               vad_filter=True)
            output = []
            for segment in segments:
                start, end, text = float(segment.start), float(segment.end), segment.text.strip()
                if not all(math.isfinite(x) for x in (start, end)) or start < 0 or end <= start:
                    raise ASRUnavailable("ASR returned invalid timestamps.")
                if text:
                    output.append({"start": start, "end": end, "text": text})
        limits = ["Automatic transcription is correctable and does not establish facts about the stream.",
                  "Times are relative to the chunk; the caller adds the session offset."]
        if not output:
            limits.append("No speech was detected; no transcript was invented.")
        return {"text": " ".join(s["text"] for s in output), "segments": output,
                "language": info.language, "provider": "faster-whisper-local", "limitations": limits}
    except ASRUnavailable:
        raise
    except Exception as exc:
        raise ASRUnavailable("Local ASR unavailable or audio undecodable; audio was not saved.") from exc


def transcribe(audio: bytes, mime_type: str, language: str | None = None) -> dict:
    if language is not None and language not in ("es", "en"):
        raise ASRUnavailable("The requested language must be es or en.")
    mime = _check_audio(audio, mime_type)
    return (_invoke_worker("transcribe", audio, mime, language) if _external_python()
            else _local_transcribe(audio, mime, language))


if __name__ == "__main__" and sys.argv[1:] == ["--worker"]:
    try:
        request = json.load(sys.stdin)
        if request["action"] == "status":
            response = _local_status()
        elif request["action"] == "transcribe":
            data = base64.b64decode(request["audio"], validate=True)
            response = transcribe(data, request["mime_type"], request.get("language"))
        else:
            raise ASRUnavailable("Invalid ASR operation.")
        print(json.dumps(response, ensure_ascii=True))
    except Exception:
        print(json.dumps({"error": "asr_unavailable"}))
        sys.exit(1)
