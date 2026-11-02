"""Fixed-origin ElevenLabs transport. Not a provider availability or budget gate."""
import ctypes
from ctypes import wintypes
import http.client
import re
import socket
import time
from pathlib import Path
from . import waves17_tts_elevenlabs as adapter

KEY_FILE = Path(__file__).resolve().parent.parent / '.runtime/credentials/elevenlabs-key.dpapi'
class _Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def _validated_key_file(path):
    """Reject reparse aliases in the fixed private credential path before reading."""
    for item in (path.parent.parent, path.parent, path):
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('private credential reparse path')
    if not path.is_file():
        raise ValueError('private credential unavailable')
    return path

def load_key():
    """Decrypt only the current Windows user's DPAPI blob; never log its contents."""
    raw = _validated_key_file(KEY_FILE).read_bytes()
    if not 1 <= len(raw) <= 4096: raise ValueError('Invalid encrypted configuration')
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    src, dst = _Blob(len(raw), buf), _Blob()
    crypt, kernel = ctypes.windll.crypt32, ctypes.windll.kernel32
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]; kernel.LocalFree.restype = ctypes.c_void_p
    if not crypt.CryptUnprotectData(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)): raise ValueError('Encrypted configuration unavailable')
    try:
        key = ctypes.string_at(dst.data, dst.size).decode('ascii')
        if not 8 <= len(key) <= 512 or any(ord(c)<33 or ord(c)>126 for c in key): raise ValueError('Invalid encrypted configuration')
        return key
    finally:
        ctypes.memset(dst.data, 0, dst.size); kernel.LocalFree(dst.data)

def transport(*, path, body, timeout_seconds, max_bytes, cancelled):
    """Exactly one fixed-origin POST; no redirect following or automatic retry."""
    if (not isinstance(path,str) or not re.fullmatch(r'/v1/text-to-speech/[A-Za-z0-9]{20}\?output_format=pcm_16000',path)
        or not isinstance(body,bytes) or not 1<=len(body)<=8192 or timeout_seconds != 30 or max_bytes != adapter.MAX_PCM):
        raise adapter.TransportFailure('transport')
    if cancelled(): raise adapter.TransportFailure('cancelled')
    try: key=load_key()
    except Exception: raise adapter.TransportFailure('transport') from None
    conn=None; start=time.monotonic()
    try:
        # http.client does not follow redirects; the adapter refuses all non-200 responses.
        conn=http.client.HTTPSConnection('api.elevenlabs.io',443,timeout=5)
        conn.request('POST',path,body=body,headers={'xi-api-key':key,'Content-Type':'application/json','Accept':'audio/pcm','Connection':'close'})
        if cancelled(): raise adapter.TransportFailure('cancelled')
        response=conn.getresponse()
        length=response.getheader('Content-Length')
        if length is not None and (not length.isascii() or not length.isdigit() or int(length)>max_bytes): raise adapter.TransportFailure('truncated')
        parts=[]; total=0
        while True:
            if cancelled(): raise adapter.TransportFailure('cancelled')
            if time.monotonic()-start>timeout_seconds: raise adapter.TransportFailure('timeout')
            chunk=response.read(min(16384,max_bytes+1-total))
            if not chunk: break
            total+=len(chunk)
            if total>max_bytes: raise adapter.TransportFailure('truncated')
            parts.append(chunk)
        if length is not None and total!=int(length): raise adapter.TransportFailure('truncated')
        headers={k:v for k,v in response.getheaders() if k.lower() in ('content-type','content-length','request-id','character-cost')}
        return adapter.Response(response.status,headers,b''.join(parts),True)
    except adapter.TransportFailure: raise
    except (socket.timeout,TimeoutError): raise adapter.TransportFailure('timeout') from None
    except http.client.IncompleteRead: raise adapter.TransportFailure('truncated') from None
    except Exception: raise adapter.TransportFailure('transport') from None
    finally:
        if conn is not None: conn.close()
