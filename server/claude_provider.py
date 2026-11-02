"""Bounded Anthropic Messages adapter; no health inference or automatic retry."""
import json, os, time, uuid, math, urllib.request, urllib.error, ssl, hashlib, re, base64, binascii, struct
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from .provider import ProviderUnavailable

ENDPOINT = 'https://api.anthropic.com/v1/messages'
MODEL = os.environ.get('APP_CLAUDE_MODEL', 'claude-sonnet-5-5')
if MODEL not in ('claude-sonnet-5-5', 'claude-opus-5'):
    raise ValueError('unsupported explicit Claude model')
INPUT_RATE, OUTPUT_RATE = (5, 25) if MODEL == 'claude-opus-5' else (2, 10)
THINKING = {'type': 'disabled'} if MODEL == 'claude-opus-5' else {'type': 'between_tools'}
MAX_INPUT = 60000
MAX_RESPONSE = 200000
MAX_OUTPUT = 1600
_tested = False
_vision_tested = False

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def status():
    configured = bool(os.environ.get('ANTHROPIC_API_KEY') or (os.environ.get('APP_CLAUDE_PROFILE_PATH') and os.environ.get('APP_CLAUDE_PROFILE_SHA256')))
    available = False if not configured else (True if _tested else None)
    return {'name':'claude','model':MODEL,'configured':configured,'available':available,'tested':_tested,'capabilities':{'text':available,'vision':(True if _vision_tested else (None if configured else False))},'visionConfigured':configured,'visionAvailable':(True if _vision_tested else (None if configured else False)),'visionTested':_vision_tested}

def _profile_key():
    """Consume only the configured CurrentUser protected profile, in-process."""
    selected=os.environ.get('APP_CLAUDE_PROFILE_PATH')
    digest=os.environ.get('APP_CLAUDE_PROFILE_SHA256')
    if not selected and not digest:
        return os.environ.get('ANTHROPIC_API_KEY')
    if not selected or not re.fullmatch(r'[0-9a-f]{64}', digest or ''):
        raise ValueError('profile configuration')
    root=Path(__file__).resolve().parents[1]
    path=Path(selected).resolve()
    if path != (root/'.runtime/mesa04/credentials/anthropic.dpapi').resolve():
        raise ValueError('profile path')
    data=path.read_bytes()
    if len(data)>65536 or hashlib.sha256(data).hexdigest()!=digest:
        raise ValueError('profile integrity')
    # ConvertFrom-SecureString (without -Key) serializes a hex DPAPI blob.
    encrypted=bytes.fromhex(data.decode('utf-8-sig').strip())
    if os.name != 'nt' or not encrypted: raise ValueError('profile codec')
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buf=(ctypes.c_ubyte*len(encrypted)).from_buffer_copy(encrypted)
    source=Blob(len(encrypted),buf); plain=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype=wintypes.BOOL
    kernel.LocalFree.argtypes=[ctypes.c_void_p]; kernel.LocalFree.restype=ctypes.c_void_p
    if not crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(plain)):
        raise ValueError('profile decrypt')
    try:
        key=ctypes.string_at(plain.data,plain.size).decode('utf-16-le')
        if not key or '\x00' in key or '\r' in key or '\n' in key: raise ValueError('profile content')
        return key
    finally:
        if plain.data:
            ctypes.memset(plain.data,0,plain.size)
            kernel.LocalFree(ctypes.cast(plain.data,ctypes.c_void_p))

ERROR_TYPES={'invalid_request_error','authentication_error','permission_error','not_found_error','rate_limit_error','api_error','overloaded_error','request_too_large'}
ERROR_FIELDS=('thinking','output_config','json_schema','schema','max_tokens','model','messages','parameter')
def safe_request_id(value, key):
    return value if isinstance(value,str) and re.fullmatch(r'req_[A-Za-z0-9_-]{1,124}',value) and key not in value else None

def error_diagnostic(exc, phase, key):
    result={'error_phase':phase,'error_class':'OtherError','http_status':None,'provider_error_type':None,'parameter_hints':[],'reason_class':None,'tls_verify_code':None,'tls_category':None,'error_request_id':None}
    for cls,name in ((urllib.error.HTTPError,'HTTPError'),(ssl.SSLCertVerificationError,'SSLCertVerificationError'),(urllib.error.URLError,'URLError'),(TimeoutError,'TimeoutError'),(json.JSONDecodeError,'JSONDecodeError'),(UnicodeDecodeError,'UnicodeDecodeError'),(ValueError,'ValueError'),(OSError,'OSError')):
        if isinstance(exc,cls): result['error_class']=name;break
    if isinstance(exc,urllib.error.HTTPError):
        if type(exc.code) is int and 100<=exc.code<=599: result['http_status']=exc.code
        try:
            result['error_request_id']=safe_request_id(exc.headers.get('request-id'),key) if exc.headers else None
            raw=exc.read(4097)
            if len(raw)<=4096:
                obj=json.loads(raw); detail=obj.get('error',{}) if isinstance(obj,dict) else {}
                if isinstance(detail,dict):
                    kind=detail.get('type'); result['provider_error_type']=kind if kind in ERROR_TYPES else None
                    message=detail.get('message')
                    if kind=='invalid_request_error' and isinstance(message,str):
                        result['parameter_hints']=[word for word in ERROR_FIELDS if re.search(r'(?<![A-Za-z0-9_])'+word+r'(?![A-Za-z0-9_])',message)]
                if isinstance(obj,dict) and not result['error_request_id']: result['error_request_id']=safe_request_id(obj.get('request_id'),key)
        except Exception: pass
    reason=exc.reason if isinstance(exc,urllib.error.URLError) and not isinstance(exc,urllib.error.HTTPError) else exc
    if isinstance(reason,ssl.SSLCertVerificationError):
        result['reason_class']='SSLCertVerificationError'
        code=getattr(reason,'verify_code',None)
        if type(code) is int and 0<=code<=999: result['tls_verify_code']=code
        if code in (9,10): result['tls_category']='certificate_time'
        elif code in (18,19,20,21,27): result['tls_category']='certificate_trust'
        elif code==62: result['tls_category']='hostname_mismatch'
        else: result['tls_category']='certificate_other'
    elif isinstance(reason,TimeoutError): result['reason_class']='TimeoutError'
    elif isinstance(reason,ssl.SSLError): result['reason_class']='SSLError'
    elif isinstance(reason,ConnectionRefusedError): result['reason_class']='ConnectionRefusedError'
    elif isinstance(reason,ConnectionResetError): result['reason_class']='ConnectionResetError'
    elif isinstance(reason,OSError): result['reason_class']='OSError'
    return result

def normalize(schema):
    allowed={'type','properties','required','additionalProperties','items','enum','description','anyOf'}
    if not isinstance(schema,dict): raise ValueError('schema')
    out={}
    for k,v in schema.items():
        if k not in allowed: continue
        if k=='properties': out[k]={name:normalize(child) for name,child in v.items()}
        elif k=='items': out[k]=normalize(v)
        elif k=='anyOf': out[k]=[normalize(x) for x in v]
        else: out[k]=v
    if out.get('type')=='object': out['additionalProperties']=False
    return out

def validate(value, schema):
    if 'anyOf' in schema:
        if not any(validate(value,x) for x in schema['anyOf']): return False
    typ=schema.get('type')
    types={'object':dict,'array':list,'string':str,'integer':int,'number':(int,float),'boolean':bool,'null':type(None)}
    if typ and (typ not in types or not isinstance(value,types[typ]) or (typ in ('integer','number') and isinstance(value,bool))): return False
    if 'enum' in schema and value not in schema['enum']: return False
    if isinstance(value,dict):
        props=schema.get('properties',{})
        if any(k not in value for k in schema.get('required',[])): return False
        if schema.get('additionalProperties') is False and any(k not in props for k in value): return False
        if any(k in props and not validate(v,props[k]) for k,v in value.items()): return False
    if isinstance(value,list):
        if len(value)<schema.get('minItems',0) or len(value)>schema.get('maxItems',float('inf')): return False
        if schema.get('uniqueItems') and len({json.dumps(x,sort_keys=True) for x in value})!=len(value): return False
        if 'items' in schema and any(not validate(x,schema['items']) for x in value): return False
    if isinstance(value,str) and (len(value)<schema.get('minLength',0) or len(value)>schema.get('maxLength',float('inf'))): return False
    return True

def _ledger_path():
    root=Path(__file__).resolve().parents[1]
    p=Path(os.environ.get('APP_CLAUDE_LEDGER', str(root/'.runtime/mesa02/claude-ledger.jsonl'))).resolve()
    if not p.is_relative_to((root/'.runtime').resolve()): raise ValueError('ledger path')
    return p

def _append(path,row):
    with open(path,'a',encoding='utf-8') as f:
        f.write(json.dumps(row,separators=(',',':'))+'\n'); f.flush(); os.fsync(f.fileno())

def utcnow():
    return datetime.now(timezone.utc).isoformat()

class JournalFailure(Exception):
    pass

@contextmanager
def ledger_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock=path.with_suffix(path.suffix+'.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    identity=os.fstat(fd)
    retain=False
    try:
        yield
    except JournalFailure:
        retain=True
        raise
    finally:
        os.close(fd)
        if not retain:
            try:
                current=lock.stat()
                if (current.st_dev,current.st_ino)==(identity.st_dev,identity.st_ino): lock.unlink()
            except FileNotFoundError: pass

def canonical_sha(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()

def validate_ledger(rows, require_review=True):
    root=Path(__file__).resolve().parents[1]
    def ishash(value):return isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value) is not None
    def number(value):return type(value) in (int,float) and math.isfinite(value) and value>=0
    if any(not isinstance(r,dict) or r.get('event') not in ('reserved','finished','preflight','operator_review','provider_revision') for r in rows):raise ValueError('ledger malformed')
    reserved=[r for r in rows if r['event']=='reserved'];finished=[r for r in rows if r['event']=='finished'];reviews=[r for r in rows if r['event']=='operator_review']
    if any(not isinstance(r.get('id'),str) or re.fullmatch(r'[0-9a-f]{32}',r['id']) is None or not number(r.get('amount')) or not ishash(r.get('request_sha256')) for r in reserved):raise ValueError('reservation malformed')
    ids=[r['id'] for r in reserved];finish_ids=[r.get('id') for r in finished]
    if len(ids)!=len(set(ids)) or len(finish_ids)!=len(set(finish_ids)) or set(ids)!=set(finish_ids):raise ValueError('unfinished reservation')
    if any(r.get('cost_certainty') not in ('bounded','unknown') for r in finished):raise ValueError('finished malformed')
    for r in finished:
        if r.get('cost_certainty')=='bounded':
            usage=r.get('usage')
            if not isinstance(usage,dict) or any(type(usage.get(k)) is not int or usage[k]<0 for k in ('input_tokens','output_tokens')) or not number(r.get('estimated_usd')) or r.get('response_model')!=MODEL:raise ValueError('bounded cost malformed')
    reserve_map={r['id']:r for r in reserved};finish_map={r['id']:r for r in finished};seen=set()
    revisions=[r for r in rows if r['event']=='provider_revision']
    used_revisions=set()
    def reviewed_successor(review):
        current=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        source=review['fixed_provider_sha256']
        if source==current: return
        # The runtime operator must pin the final canonical record independently
        # of the mutable ledger. A ledger row alone cannot authorize a revision.
        pin=os.environ.get('APP_CLAUDE_REVISION_SHA256','')
        if not ishash(pin): raise ValueError('provider revision not pinned')
        prior=canonical_sha(review); visited=set(); last_index=rows.index(review)
        while source!=current:
            options=[x for x in revisions if x.get('review_sha256')==canonical_sha(review) and x.get('previous_sha256')==prior]
            if len(options)!=1: raise ValueError('provider revision chain')
            item=options[0]
            index=rows.index(item)
            if index<=last_index: raise ValueError('provider revision order')
            last_index=index
            keys={'event','review_sha256','previous_sha256','old_provider_sha256','new_provider_sha256','old_source_path','new_source_path','evidence_path','evidence_sha256','timestamp_utc'}
            if set(item)!=keys or item.get('old_provider_sha256')!=source or not ishash(item.get('new_provider_sha256')) or not ishash(item.get('evidence_sha256')) or not isinstance(item.get('timestamp_utc'),str): raise ValueError('provider revision schema')
            for path_key,hash_key in (('old_source_path','old_provider_sha256'),('new_source_path','new_provider_sha256'),('evidence_path','evidence_sha256')):
                if not isinstance(item.get(path_key),str): raise ValueError('provider revision path')
                file=(root/item[path_key]).resolve()
                if not file.is_relative_to((root/'sessions').resolve()) or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=item[hash_key]: raise ValueError('provider revision evidence')
            digest=canonical_sha(item)
            if digest in visited or item['new_provider_sha256'] in visited: raise ValueError('provider revision cycle')
            visited.update((digest,source)); used_revisions.add(digest)
            source=item['new_provider_sha256']; prior=digest
        if prior!=pin: raise ValueError('provider revision pin')

    for r in reviews:
        keys={'event','target_id','finished_sha256','request_sha256','reservation_amount','cost_status','timestamp_utc','evidence_path','evidence_sha256','fixed_provider_sha256','reason_code'}
        if set(r)!=keys:raise ValueError('review schema')
        ident=r.get('target_id')
        if not isinstance(ident,str) or ident not in reserve_map or ident in seen:raise ValueError('review target')
        original=reserve_map[ident];finish=finish_map[ident]
        if finish.get('cost_certainty')!='unknown' or r.get('cost_status')!='unknown' or r.get('reason_code')!='sonnet55_thinking_parameter_fixed':raise ValueError('review state')
        if not number(r.get('reservation_amount')) or r['reservation_amount']!=original['amount'] or r.get('finished_sha256')!=canonical_sha(finish) or r.get('request_sha256')!=original['request_sha256']:raise ValueError('review reference')
        if not all(ishash(r.get(k)) for k in ('finished_sha256','request_sha256','evidence_sha256','fixed_provider_sha256')) or not isinstance(r.get('timestamp_utc'),str):raise ValueError('review metadata')
        reviewed_successor(r)
        if not isinstance(r.get('evidence_path'),str):raise ValueError('evidence path')
        path=(root/r['evidence_path']).resolve()
        if not any(path.is_relative_to((root/folder).resolve()) for folder in ('.runtime','sessions')) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=r['evidence_sha256']:raise ValueError('evidence changed')
        seen.add(ident)
    if len(used_revisions)!=len(revisions):raise ValueError('unused provider revision')
    if require_review and any(r['id'] not in seen for r in finished if r.get('cost_certainty')=='unknown'):raise ValueError('cost requires review')
    return reserved,finish_map,seen

def _check_reservation(path, amount, effect=None):
    cap=float(os.environ.get('APP_CLAUDE_CAP_USD','0.50')); calls=int(os.environ.get('APP_CLAUDE_MAX_CALLS','8'))
    if not math.isfinite(cap) or cap<=0 or cap>1.5 or calls<1 or calls>64: raise ValueError('budget configuration')
    rows=[]
    if path.exists():
        with open(path,encoding='utf-8') as f:
            for line in f: rows.append(json.loads(line))
    reserved,_,_=validate_ledger(rows)
    if effect is not None:
        if (not isinstance(effect,dict) or set(effect)!={'operation','stage'} or
            not isinstance(effect['operation'],str) or not re.fullmatch(r'[0-9a-f]{64}',effect['operation']) or
            effect['stage'] not in ('draft','review')): raise ValueError('effect identity')
        if any(r.get('effect') == effect for r in reserved): raise ValueError('effect already reserved')
    if len(reserved)>=calls or sum(r['amount'] for r in reserved)+amount>cap: raise ValueError('budget exceeded')

def _reserve(path, amount, request_hash, effect=None):
    _check_reservation(path, amount, effect)
    ident=uuid.uuid4().hex
    row={'event':'reserved','id':ident,'amount':amount,'model':MODEL,'request_sha256':request_hash,'timestamp_utc':utcnow()}
    if effect is not None: row['effect']=dict(effect)
    try: _append(path,row)
    except Exception: raise JournalFailure() from None
    return ident

def lookup_effect(effect, path=None):
    """Recover a review-stage reservation without authorizing a retry.

    The provider ledger lock serializes this read with reservation and finish.
    An unfinished reservation is returned as unknown. This is an operator-side
    accounting primitive, not an actor authorization or a public endpoint.
    """
    if (not isinstance(effect,dict) or set(effect)!={'operation','stage'} or
        not isinstance(effect['operation'],str) or not re.fullmatch(r'[0-9a-f]{64}',effect['operation']) or
        effect['stage'] not in ('draft','review')): raise ValueError('effect identity')
    path = _ledger_path() if path is None else Path(path)
    with ledger_lock(path):
        rows=[]
        if path.exists():
            with open(path,encoding='utf-8') as f:
                for line in f: rows.append(json.loads(line))
        if any(not isinstance(row,dict) for row in rows): raise ValueError('ledger malformed')
        matches=[row for row in rows if row.get('event')=='reserved' and row.get('effect')==effect]
        if len(matches)>1: raise ValueError('duplicate effect')
        if not matches: return None
        reservation=matches[0]; ident=reservation.get('id')
        if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f]{32}',ident): raise ValueError('reservation malformed')
        finishes=[row for row in rows if row.get('event')=='finished' and row.get('id')==ident]
        if len(finishes)>1: raise ValueError('duplicate finish')
        finish=finishes[0] if finishes else None
        if finish and finish.get('cost_certainty') not in ('bounded','unknown'): raise ValueError('finish malformed')
        return {'reservationId':ident, 'state':finish.get('state','unknown') if finish else 'unknown',
                'costCertainty':finish['cost_certainty'] if finish else 'unknown'}


MAX_IMAGE = 4 * 1024 * 1024
MAX_IMAGE_EDGE = 2576

def image_block(image):
    if not isinstance(image,dict) or set(image)!={'mimeType','data'} or image['mimeType'] not in ('image/png','image/jpeg','image/webp') or not isinstance(image['data'],str) or len(image['data']) > 4*((MAX_IMAGE+2)//3): raise ValueError('image')
    raw=base64.b64decode(image['data'],validate=True)
    if not raw or len(raw)>MAX_IMAGE or base64.b64encode(raw).decode('ascii')!=image['data']: raise ValueError('image size')
    mime=image['mimeType']; width=height=0
    if mime=='image/png' and len(raw)>=24 and raw[:8]==b'\x89PNG\r\n\x1a\n' and raw[12:16]==b'IHDR' and raw[8:12]==b'\x00\x00\x00\r': width,height=struct.unpack('>II',raw[16:24])
    elif mime=='image/jpeg' and raw[:2]==b'\xff\xd8':
        pos=2
        while pos+4<=len(raw):
            if raw[pos]!=255: break
            while pos<len(raw) and raw[pos]==255: pos+=1
            if pos>=len(raw): break
            marker=raw[pos]; pos+=1
            if marker in (0xd8,0xd9) or 0xd0<=marker<=0xd7: continue
            if pos+2>len(raw): break
            size=int.from_bytes(raw[pos:pos+2],'big')
            if size<2 or pos+size>len(raw): break
            if marker in (0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf) and size>=8:
                height=int.from_bytes(raw[pos+3:pos+5],'big'); width=int.from_bytes(raw[pos+5:pos+7],'big'); break
            pos+=size
    elif mime=='image/webp' and len(raw)>=30 and raw[:4]==b'RIFF' and raw[8:12]==b'WEBP' and int.from_bytes(raw[4:8],'little')+8==len(raw):
        kind=raw[12:16]
        if kind==b'VP8X': width=1+int.from_bytes(raw[24:27],'little'); height=1+int.from_bytes(raw[27:30],'little')
        elif kind==b'VP8 ' and raw[23:26]==b'\x9d\x01\x2a': width=int.from_bytes(raw[26:28],'little')&16383; height=int.from_bytes(raw[28:30],'little')&16383
        elif kind==b'VP8L' and raw[20]==47:
            bits=int.from_bytes(raw[21:25],'little'); width=(bits&16383)+1; height=((bits>>14)&16383)+1
    if not 0<width<=MAX_IMAGE_EDGE or not 0<height<=MAX_IMAGE_EDGE: raise ValueError('image dimensions or format')
    return {'type':'image','source':{'type':'base64','media_type':mime,'data':image['data']}}

def chat(messages, image=None, timeout=120, schema=None, repair=True, opener=None, effect=None):
    global _tested, _vision_tested
    try:
        if not isinstance(messages,list) or not messages: raise ValueError('messages')
        system=[]; wire=[]
        for m in messages:
            role=m.get('role'); content=m.get('content')
            if role not in ('system','user','assistant') or not isinstance(content,str): raise ValueError('message')
            if role=='system':
                if wire: raise ValueError('system order')
                system.append(content)
            else:
                if wire and wire[-1]['role']==role: wire[-1]['content']+='\n'+content
                else: wire.append({'role':role,'content':content})
        if not wire or wire[0]['role']!='user': raise ValueError('message order')
        target=schema or {'type':'object','properties':{'text':{'type':'string'}},'required':['text'],'additionalProperties':False}
        body={'model':MODEL,'max_tokens':MAX_OUTPUT,'thinking':THINKING,'messages':wire,'output_config':{'format':{'type':'json_schema','schema':normalize(target)}}}
        if system: body['system']='\n'.join(system)
        text_data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(text_data)>MAX_INPUT: raise ValueError('input limit')
        images=[] if image is None else (image if isinstance(image,list) else [image])
        if len(images)>2: raise ValueError('image count')
        if images:
            if wire[-1]['role']!='user': raise ValueError('image message order')
            blocks=[image_block(item) for item in images]
            wire[-1]['content']=[{'type':'text','text':wire[-1]['content']}]+blocks
        data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        if len(data)>MAX_INPUT+2*(4*((MAX_IMAGE+2)//3)+256): raise ValueError('payload limit')
        input_bound=len(text_data)+512+4784*len(images)
        path=_ledger_path(); amount=(input_bound*INPUT_RATE+MAX_OUTPUT*OUTPUT_RATE)/1000000
        with ledger_lock(path):
            # Reject accounting and duplicate effects before opening protected
            # credentials. The lock preserves that decision until reservation.
            _check_reservation(path,amount,effect)
            key=_profile_key()
            if not key: raise ProviderUnavailable('provider_unavailable')
            req=urllib.request.Request(ENDPOINT,data=data,method='POST',headers={'content-type':'application/json','x-api-key':key,'anthropic-version':'2023-06-01'})
            ident=_reserve(path,amount,hashlib.sha256(data).hexdigest(),effect)
            started=time.monotonic(); state='uncertain'; usage=None; cost=None; response_model=None; request_id=None; valid=None; error='provider_unavailable'; cost_certainty='unknown'; phase='HTTPopen'; diagnostic={}
            try:
                with (opener or urllib.request.build_opener(urllib.request.HTTPSHandler(),NoRedirect())).open(req,timeout=min(max(float(timeout),1),120)) as response:
                    headers=getattr(response,'headers',None)
                    rid=headers.get('request-id') if headers is not None else None
                    if isinstance(rid,str) and re.fullmatch(r'req_[A-Za-z0-9_-]{1,124}',rid) and key not in rid: request_id=rid
                    phase='read'; raw=response.read(MAX_RESPONSE+1)
                    if len(raw)>MAX_RESPONSE: raise ValueError('response limit')
                    phase='JSONdecode'; payload=json.loads(raw.decode('utf-8', errors='strict'))
                if not isinstance(payload,dict): raise ValueError('response')
                phase='model'; model=payload.get('model')
                if isinstance(model,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',model) and key not in model: response_model=model
                phase='usage'; u=payload.get('usage')
                if isinstance(u,dict) and all(type(u.get(k)) is int and u[k]>=0 for k in ('input_tokens','output_tokens')):
                    usage={'input_tokens':u['input_tokens'],'output_tokens':u['output_tokens']}
                    cost=(u['input_tokens']*INPUT_RATE+u['output_tokens']*OUTPUT_RATE)/1000000
                if usage is None or u.get('cache_creation_input_tokens',0) or u.get('cache_read_input_tokens',0) or u['input_tokens']>input_bound or u['output_tokens']>MAX_OUTPUT: raise ValueError('usage')
                phase='model'
                if model!=MODEL: raise ValueError('model')
                cost_certainty='bounded'
                error='provider_invalid_output'
                phase='stop'
                if payload.get('stop_reason')!='end_turn': raise ValueError('stop')
                phase='schema'; blocks=payload.get('content')
                if not isinstance(blocks,list) or len(blocks)!=1 or not isinstance(blocks[0],dict) or blocks[0].get('type')!='text' or not isinstance(blocks[0].get('text'),str): raise ValueError('content')
                parsed=json.loads(blocks[0]['text'])
                if not isinstance(parsed,dict) or not validate(parsed,target): raise ValueError('schema')
                valid={'text':str(parsed.get('text',blocks[0]['text'])),'json':parsed,'done_reason':'stop'};state='complete'
            except Exception as exc: diagnostic=error_diagnostic(exc,phase,key)
            # Durable finish precedes success; any failure leaves an unfinished reservation and blocks future calls.
            try: _append(path,{'event':'finished','id':ident,'state':state,'cost_certainty':cost_certainty,'usage':usage,'estimated_usd':cost if cost_certainty=='bounded' else None,'cost_kind':'estimate_not_billing','response_model':response_model,'request_id':request_id or diagnostic.get('error_request_id'),'diagnostic':diagnostic or None,'timestamp_utc':utcnow(),'latency_ms':round((time.monotonic()-started)*1000)})
            except Exception: raise JournalFailure() from None
            if valid is None: raise ProviderUnavailable(error)
            _tested=True
            if images and opener is None: _vision_tested=True
            return valid
    except ProviderUnavailable: raise
    except Exception: raise ProviderUnavailable('provider_unavailable') from None
