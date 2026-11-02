"""Local Ollama adapter. Never silently falls back after a provider error."""
from __future__ import annotations

import base64
import json
import ipaddress
import os
import threading
import urllib.error
import urllib.request
from urllib.parse import urlparse

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")
BASE_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
_lock = threading.Lock()
_tested = False
_vision_tested = False

def _local_endpoint():
    p=urlparse(BASE_URL)
    if p.scheme!="http" or not p.hostname:return False
    if p.hostname.lower()=="localhost":return True
    try:return ipaddress.ip_address(p.hostname).is_loopback
    except ValueError:return False


class ProviderUnavailable(Exception):
    def __init__(self, message: str = "provider_unavailable", raw_output: str | None = None):
        super().__init__(message)
        self.raw_output = raw_output


def _request(path: str, payload: dict | None = None, timeout: int = 120):
    if not _local_endpoint():raise ProviderUnavailable("Only local Ollama endpoints are allowed.")
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE_URL + path, data=data,
        headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())
    except (OSError, urllib.error.URLError, ValueError, TimeoutError) as exc:
        raise ProviderUnavailable("The local provider did not respond correctly.") from exc


def _ollama_status() -> dict:
    configured = bool(MODEL and BASE_URL and _local_endpoint())
    available = False
    if configured:
        try:
            available = any(m.get("name", "").split(":")[0] == MODEL.split(":")[0]
                            and m.get("name", "") == MODEL for m in _request("/api/tags", timeout=2).get("models", []))
        except ProviderUnavailable:
            pass
    capabilities = {"text": available, "vision": None}
    if available:
        try:
            shown = _request("/api/show", {"model": MODEL}, timeout=2)
            declared = shown.get("capabilities", [])
            capabilities["vision"] = "vision" in declared
        except ProviderUnavailable:
            pass
    return {"name": "ollama", "configured": configured, "available": available,
            "tested": _tested, "model": MODEL, "capabilities": capabilities,
            "visionTested": _vision_tested}


def _ollama_chat(messages: list[dict], image: bytes | None = None, timeout: int = 120,
         schema: dict | None = None, repair: bool = True, expected_model: str | None = None) -> dict:
    global _tested, _vision_tested
    user = next((m for m in reversed(messages) if m["role"] == "user"), None)
    if image and user:
        user["images"] = [base64.b64encode(image).decode("ascii")]
    with _lock:
        if expected_model is not None and MODEL != expected_model:
            raise ProviderUnavailable('provider_binding_changed')
        selected_model = expected_model if expected_model is not None else MODEL
        result = _request("/api/chat", {"model": selected_model, "messages": messages,
            "stream": False, "think": False, "format": schema or "json",
            "options": {"num_ctx": 8192, "num_predict": 1600}}, timeout)
    content = result.get("message", {}).get("content", "")
    if not isinstance(content,str) or not content.strip():
        raise ProviderUnavailable("The provider returned an empty response.")
    _tested = True
    if image:
        _vision_tested = True
    try:
        parsed = json.loads(content)
        text = parsed.get("text") if isinstance(parsed, dict) else None
        done = result.get("done_reason", "stop")
        if done in ("length", "max_tokens"):
            raise ValueError("truncated")
        if not isinstance(parsed, dict):
            raise ValueError("object required")
        return {"text": str(text) if text is not None else content, "json": parsed, "done_reason": done}
    except (ValueError, AttributeError):
        if schema is not None and repair:
            retry = list(messages) + [{"role":"assistant","content":content},
                {"role":"user","content":"Output does not match JSON/schema or is truncated. Retry once: return only the complete valid JSON object."}]
            return _ollama_chat(retry, image=image, timeout=timeout, schema=schema, repair=False, expected_model=expected_model)
        if schema is not None:
            raise ProviderUnavailable("provider_invalid_output", raw_output=content)
        return {"text": content, "json": None}


def provider_name():
    return os.environ.get("APP_AI_PROVIDER", "ollama").strip().lower()

def status():
    name=provider_name()
    if name=="ollama": return _ollama_status()
    if name=="claude":
        from . import claude_provider
        return claude_provider.status()
    return {"name":name,"configured":False,"available":False,"tested":False,"model":None,"capabilities":{"text":False,"vision":False},"visionTested":False}

def chat(messages, image=None, timeout=120, schema=None, repair=True, effect=None, expected_provider=None, expected_model=None):
    name=provider_name()
    # Optional internal dispatch fence: callers with an admitted policy must
    # bind its provider and model at this actual adapter boundary. Neither
    # value grants admission or replaces the durable provider ledger.
    if expected_provider is not None or expected_model is not None:
        if name == 'claude':
            from . import claude_provider
            model = claude_provider.MODEL
        elif name == 'ollama':
            model = MODEL
        else:
            model = None
        if (not isinstance(expected_provider, str) or not isinstance(expected_model, str)
                or name != expected_provider or model != expected_model):
            raise ProviderUnavailable('provider_binding_changed')
    if name=="ollama": return _ollama_chat(messages,image=image,timeout=timeout,schema=schema,repair=repair,expected_model=expected_model)
    if name=="claude":
        from . import claude_provider
        if isinstance(image,bytes):
            mime = 'image/png' if image.startswith(b'\x89PNG\r\n\x1a\n') else ('image/jpeg' if image.startswith(b'\xff\xd8') else 'image/webp')
            image = {'mimeType':mime,'data':base64.b64encode(image).decode('ascii')}
        return claude_provider.chat(messages,image=image,timeout=timeout,schema=schema,repair=repair,effect=effect)
    raise ProviderUnavailable("provider_unavailable")

def prove(text: str, image: bytes | None = None) -> dict:
    """Small explicit smoke inference used by the operator, not health probes."""
    prompt = "Describe only visible content in one sentence; return JSON with a text field." if image else "Respond briefly in English; return JSON with a text field."
    chosen_model = "claude-sonnet-5-5" if provider_name()=="claude" else MODEL
    try:
        out = chat([{"role": "user", "content": prompt if image else text}], image=image)
        return {"ok": True, "model": chosen_model, "text": out["text"][:240]}
    except ProviderUnavailable:
        return {"ok": False, "model": chosen_model, "error": "provider_unavailable"}
