"""Bounded, local, generic SAPI speech. No playback or external provider."""
import base64, io, json, os, subprocess, tempfile, time, wave
from pathlib import Path
from . import store

VOICES = {'en':'TTS_MS_EN-US_ZIRA_11.0', 'es':'TTS_MS_ES-MX_SABINA_11.0'}

def synthesize(text, language):
    if language not in VOICES or not isinstance(text,str) or not 1 <= len(text.strip()) <= 600:
        raise ValueError('Invalid speech input.')
    store.DATA.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix='p12speech-', suffix='.wav', dir=store.DATA)
    os.close(fd)
    try:
        payload=json.dumps({'textUtf8Base64':base64.b64encode(text.encode('utf-8')).decode('ascii'), 'language':language,'output':path})
        begin=time.monotonic()
        p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('phase12_sapi.ps1'))],input=payload,text=True,encoding='utf-8',capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if p.returncode: raise RuntimeError('Local speech unavailable.')
        meta=json.loads(p.stdout.strip().splitlines()[-1])
        if not meta.get('voiceId','').endswith(VOICES[language]): raise RuntimeError('Voice unavailable.')
        if os.path.getsize(path)>8*1024*1024: raise RuntimeError('Speech size exceeded.')
        data=Path(path).read_bytes()
        with wave.open(io.BytesIO(data),'rb') as w:
            if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype()) != (1,2,16000,'NONE'): raise RuntimeError('Invalid speech format.')
            duration=w.getnframes()/w.getframerate()
            if not 0<duration<=30: raise RuntimeError('Speech duration exceeded.')
            if len(w.readframes(w.getnframes())) != w.getnframes()*2: raise RuntimeError('Truncated speech.')
        return data, {'voice':meta['voiceName'],'language':language,'durationSeconds':duration,'synthesisMs':round((time.monotonic()-begin)*1000,2),'providerRequests':0}
    finally:
        try: os.unlink(path)
        except FileNotFoundError: pass
