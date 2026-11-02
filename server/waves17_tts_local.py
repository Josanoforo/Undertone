"""Isolated, buffered CPU speech; primary owns eligibility and publication races."""
import base64, hashlib, io, json, math, os, subprocess, sys, threading, time, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / '.runtime' / 'mesa02' / 'w17-local-voice'
PYTHON = ROOT / 'venv' / 'Scripts' / 'python.exe'
MODEL_REV = 'sherpa-vits-piper-sha256-8ceba58a-6b7a54f5'
ADAPTER_REV = 'local-v2'
WEIGHT_SHA256 = {'en':'8ceba58a4b540d4e7e7e24ad079cf0d92762a4fd334e059f12940787c6c37b3d', 'es':'6b7a54f5fcc8c9ce3788cd308a26cfa429ad025cdff4a7a6c34d025d0d229341'}
VOICES = {'en': ('en_US-ljspeech-medium', 'vits-piper-en_US-ljspeech-medium'),
          'es': ('es_MX-claude-high', 'vits-piper-es_MX-claude-high')}

class SpeechError(Exception):
    pass

def availability():
    available = PYTHON.is_file() and all((ROOT/'models'/folder/(voice+'.onnx')).is_file() and (ROOT/'models'/folder/'tokens.txt').is_file() and (ROOT/'models'/folder/'espeak-ng-data').is_dir() for voice, folder in VOICES.values())
    return {'engine':'sherpa-onnx-cpu', 'configured':True, 'available':available, 'reason':None if available else 'local_assets_missing', 'voices':{k:v[0] for k,v in VOICES.items()}, 'modelVersion':MODEL_REV, 'runtimeVersion':'1.12.40', 'tested':False}

def synthesize(text, language, voice=None, *, cancelled=lambda:False, eligible=lambda:True, timeout=60, speed=1.0):
    if not isinstance(text,str) or not 1 <= len(text.strip()) <= 600 or language not in VOICES or (voice is not None and voice != VOICES[language][0]):
        raise SpeechError('invalid_input')
    if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0.5 <= speed <= 2.0:
        raise SpeechError('invalid_speed')
    if not availability()['available']:
        raise SpeechError('local_unavailable')
    if cancelled() or not eligible():
        raise SpeechError('cancelled_or_ineligible')
    model_path=ROOT/'models'/VOICES[language][1]/(VOICES[language][0]+'.onnx')
    with model_path.open('rb') as f:
        digest=hashlib.file_digest(f, 'sha256').hexdigest()
    if digest != WEIGHT_SHA256[language]: raise SpeechError('model_integrity')
    start=time.monotonic()
    env=os.environ.copy(); env['TEMP']=str(ROOT); env['TMP']=str(ROOT); env['PYTHONDONTWRITEBYTECODE']='1'
    p=subprocess.Popen([str(PYTHON), '-B', str(Path(__file__).resolve()), '--worker'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    result=[]
    def run():
        try: result.append(p.communicate(json.dumps({'text':text,'language':language,'speed':speed},ensure_ascii=False).encode('utf-8')))
        except Exception: result.append((b'',b''))
    t=threading.Thread(target=run,daemon=True); t.start()
    try:
        while t.is_alive():
            if cancelled() or not eligible() or time.monotonic()-start > timeout:
                p.kill(); t.join(); raise SpeechError('cancelled_or_ineligible' if time.monotonic()-start <= timeout else 'timeout')
            t.join(.025)
    except BaseException:
        if p.poll() is None: p.kill()
        t.join(); raise
    if cancelled() or not eligible(): raise SpeechError('cancelled_or_ineligible')
    if p.returncode != 0 or not result: raise SpeechError('local_failure')
    try:
        payload=json.loads(result[0][0]); audio=base64.b64decode(payload.pop('wav'),validate=True)
        with wave.open(io.BytesIO(audio),'rb') as w:
            if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype()) != (1,2,16000,'NONE'): raise ValueError()
            duration=w.getnframes()/16000
            if not 0 < duration <= 30 or len(audio)>8*1024*1024: raise ValueError()
    except Exception: raise SpeechError('invalid_audio') from None
    if cancelled() or not eligible(): raise SpeechError('cancelled_or_ineligible')
    return audio, {'engine':'sherpa-onnx-cpu','model':'piper-vits','modelVersion':MODEL_REV,'runtimeVersion':'1.12.40','adapterVersion':ADAPTER_REV,'voice':VOICES[language][0],'modelSha256':digest,'language':language,'settings':{'speed':speed,'threads':2,'sampleRate':16000},'mime':'audio/wav','sampleRate':16000,'durationSeconds':duration,'synthesisMs':round((time.monotonic()-start)*1000,2),'firstAudioMs':None,'providerRequests':0,'inputCharacters':len(text),'cost':0,'cancellation':'checked_before_and_after_buffered_generation',**payload}

def _worker():
    import audioop, array, ctypes
    import sherpa_onnx
    req=json.loads(sys.stdin.buffer.read()); voice, folder=VOICES[req['language']]; d=ROOT/'models'/folder
    begin=time.monotonic(); cpu=time.process_time()
    v=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(d/(voice+'.onnx')),tokens=str(d/'tokens.txt'),data_dir=str(d/'espeak-ng-data'))
    model=sherpa_onnx.OfflineTtsModelConfig(vits=v,num_threads=2,provider='cpu')
    tts=sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(model=model))
    setup=time.monotonic(); audio=tts.generate(req['text'],sid=0,speed=req['speed']); finish=time.monotonic()
    pcm=array.array('h',(int(max(-1,min(1,x))*32767) for x in audio.samples)).tobytes()
    pcm,_=audioop.ratecv(pcm,2,1,audio.sample_rate,16000,None)
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w: w.setparams((1,2,16000,0,'NONE','not compressed')); w.writeframes(pcm)
    class PMC(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('PageFaultCount',ctypes.c_ulong),('PeakWorkingSetSize',ctypes.c_size_t),('WorkingSetSize',ctypes.c_size_t),('QuotaPeakPagedPoolUsage',ctypes.c_size_t),('QuotaPagedPoolUsage',ctypes.c_size_t),('QuotaPeakNonPagedPoolUsage',ctypes.c_size_t),('QuotaNonPagedPoolUsage',ctypes.c_size_t),('PagefileUsage',ctypes.c_size_t),('PeakPagefileUsage',ctypes.c_size_t)]
    pmc=PMC(); pmc.cb=ctypes.sizeof(pmc); ctypes.windll.kernel32.GetCurrentProcess.restype=ctypes.c_void_p; ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]; ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(pmc),pmc.cb)
    print(json.dumps({'wav':base64.b64encode(buf.getvalue()).decode(),'modelSetupMs':round((setup-begin)*1000,2),'generationMs':round((finish-setup)*1000,2),'cpuSeconds':round(time.process_time()-cpu,3),'peakWorkingSetBytes':pmc.PeakWorkingSetSize,'nativeSampleRate':audio.sample_rate}))

if __name__ == '__main__' and sys.argv[1:] == ['--worker']:
    _worker()


