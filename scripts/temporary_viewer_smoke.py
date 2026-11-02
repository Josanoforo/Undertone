"""Bounded synthetic Quick Tunnel smoke. Outputs only non-sensitive status."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlsplit
import stat
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler, Request
from setup_evaluator import no_reparse

ROOT = Path(__file__).resolve().parents[1]
RUNROOT = ROOT / '.runtime/mesa02/PHASE34-GATEWAY/quick-tunnel'
BINARY = RUNROOT / 'cloudflared-2026.10.6.exe'
DIGEST = 'd521b3bf68982165f0d06d76732f22d9a105ef057ff3ae4c0986f3a23190950f'
FILES = ['server/__init__.py','server/__main__.py','server/http.py','server/store.py','server/provider.py','server/claude_provider.py','server/asr.py','server/admission.py','server/lifecycle.py','server/gateway.py','client/index.html','client/overlay.html','client/assets/app.js','client/assets/app.css','client/assets/live-audio.js','client/assets/overlay.js','client/assets/overlay.css']
MAX = 1024 * 1024

class Adapter(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    target = None
    manual_only = False

def manual_allowed(method, target):
    path=urlsplit(target).path
    if '%' in path: return False
    ident=r'[A-Za-z0-9_-]+'
    prefix=r'/api/sessions/'+ident
    if method=='GET':
        return path in ('/', '/index.html') or bool(re.fullmatch(r'/assets/[A-Za-z0-9._/-]+',path) and '..' not in path) or bool(re.fullmatch(prefix+r'(?:/(?:sources|bookmarks|connection|capture-status|conversations(?:/'+ident+r')?))?',path))
    if method=='POST': return bool(re.fullmatch(prefix+r'/(?:join|bookmarks|conversations)',path))
    if method=='DELETE': return bool(re.fullmatch(prefix+r'/bookmarks/'+ident,path))
    return False

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'Companion'
    sys_version = ''
    def setup(self):
        super().setup(); self.connection.settimeout(15)
    def log_message(self, *args): pass
    def denied(self, status):
        self.close_connection = True
        body = b'{"error":{"code":"unavailable"}}'
        self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self): self.forward()
    def do_POST(self): self.forward()
    def do_PATCH(self): self.forward()
    def do_DELETE(self): self.forward()
    def forward(self):
        names = [n.lower() for n, _ in self.headers.raw_items()]
        if not self.server.target: return self.denied(503)
        if self.server.manual_only and not manual_allowed(self.command, self.path): return self.denied(404)
        if ('x-companion-gateway' in names or 'proxy-authorization' in names or 'transfer-encoding' in names or 'expect' in names or any(names.count(n)>1 for n in ('host','origin','authorization','content-type','content-length'))): return self.denied(403)
        try:
            n = self.headers.get('Content-Length', '0')
            if not re.fullmatch('[0-9]+',n) or int(n)>MAX: return self.denied(413)
            body = self.rfile.read(int(n))
            if len(body)!=int(n): return self.denied(400)
            # All forwarding and Cloudflare metadata are discarded, never trusted.
            headers = {name:self.headers[name] for name in ('Host','Origin','Authorization','Content-Type','Sec-Fetch-Site') if self.headers.get(name) is not None}
            headers['Connection']='close'
            c=http.client.HTTPConnection('127.0.0.1',self.server.target,timeout=130)
            try:
                c.request(self.command,self.path,body=body if body else None,headers=headers)
                r=c.getresponse(); data=r.read(20*1024*1024+1)
                if len(data)>20*1024*1024: return self.denied(502)
                self.send_response(r.status)
                for name in ('Content-Type','Content-Security-Policy','X-Content-Type-Options','Cache-Control'):
                    if r.getheader(name): self.send_header(name,r.getheader(name))
                self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
            finally: c.close()
        except (OSError,ValueError,http.client.HTTPException):
            try: self.denied(502)
            except OSError: pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

opener=build_opener(ProxyHandler({}),NoRedirect())
def request(base, method, path, payload=None, headers=None):
    data=json.dumps(payload).encode() if payload is not None else None
    h=dict(headers or {})
    if data is not None: h['Content-Type']='application/json'
    req=Request(base+path,data=data,headers=h,method=method)
    try: response=opener.open(req,timeout=20)
    except HTTPError as e: response=e
    with response:
        b=response.read(2*1024*1024)
        try: b=json.loads(b)
        except (ValueError,UnicodeDecodeError): pass
        return response.status,b

def dns_question(host):
    labels = host.split('.')
    return struct.pack('!HHHHHH', 0x4217, 0x0100, 1, 0, 0, 0) + b''.join(bytes([len(x)]) + x.encode('ascii') for x in labels) + b'\0' + struct.pack('!HH', 1, 1)

def dns_answer(data):
    if len(data) < 12: raise ValueError('Invalid DNS response')
    ident, flags, qd, an, _, _ = struct.unpack('!HHHHHH', data[:12])
    if ident != 0x4217 or not flags & 0x8000: raise ValueError('Invalid DNS response')
    def skip_name(pos):
        for _ in range(128):
            if pos >= len(data): raise ValueError('Invalid DNS name')
            n=data[pos]; pos+=1
            if n & 0xc0 == 0xc0: return pos+1
            if n & 0xc0: raise ValueError('Invalid DNS label')
            if not n: return pos
            pos+=n
        raise ValueError('Invalid DNS name')
    pos=12
    for _ in range(qd): pos=skip_name(pos)+4
    addresses=[]
    for _ in range(an):
        pos=skip_name(pos)
        if pos+10>len(data): raise ValueError('Invalid DNS answer')
        typ, cls, _, length=struct.unpack('!HHIH',data[pos:pos+10]); pos+=10
        if pos+length>len(data): raise ValueError('Invalid DNS answer')
        if typ==1 and cls==1 and length==4: addresses.append(socket.inet_ntoa(data[pos:pos+4]))
        pos+=length
    return flags & 15, addresses

def dns_probe(host):
    result={}; addresses=[]; packet=dns_question(host)
    try:
        socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        result['windows']='resolved'
    except socket.gaierror as e: result['windows']='gaierror:'+str(e.errno)
    try:
        req=Request('https://cloudflare-dns.com/dns-query',data=packet,headers={'Content-Type':'application/dns-message','Accept':'application/dns-message'},method='POST')
        with opener.open(req,timeout=8) as r: code,addresses=dns_answer(r.read(65535))
        result['cloudflare_doh']='rcode:'+str(code)+',a_count:'+str(len(addresses))
    except Exception as e: result['cloudflare_doh']='error:'+type(e).__name__
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(2); sock.sendto(packet,('1.1.1.1',53)); response,_=sock.recvfrom(65535)
        code,ips=dns_answer(response); result['directed_udp']='rcode:'+str(code)+',a_count:'+str(len(ips))
    except Exception as e: result['directed_udp']='error:'+type(e).__name__
    return result,addresses

def diagnostic_https(host, ip):
    # Diagnostic only: connect to an explicit DoH answer, retain original SNI and certificate validation.
    context=ssl.create_default_context()
    with socket.create_connection((ip,443),timeout=10) as raw:
        with context.wrap_socket(raw,server_hostname=host) as tls:
            tls.settimeout(10)
            tls.sendall(('GET / HTTP/1.1\r\nHost: '+host+'\r\nConnection: close\r\n\r\n').encode('ascii'))
            line=b''
            while b'\r\n' not in line and len(line)<512:
                part=tls.recv(1)
                if not part: break
                line+=part
            m=re.fullmatch(rb'HTTP/1\.[01] ([0-9]{3}) [^\r\n]*\r\n',line)
            if not m: raise ValueError('Invalid HTTP status')
            return int(m.group(1))

def snapshot(dest):
    if (ROOT/'client/dist').exists(): raise RuntimeError('Snapshot refuses an unlisted client distribution')
    no_reparse(ROOT); no_reparse(dest)
    data={}
    for f in FILES:
        p=ROOT/f
        no_reparse(p)
        if p.is_symlink() or not p.is_file(): raise RuntimeError('Snapshot source unavailable')
        data[f]=p.read_bytes()
    for f,b in data.items():
        if (ROOT/f).read_bytes()!=b: raise RuntimeError('Source changed during snapshot')
        p=dest/f; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b); p.chmod(stat.S_IREAD)
    if any((ROOT/f).read_bytes()!=b for f,b in data.items()): raise RuntimeError('Source changed during snapshot')
    manifest={f:hashlib.sha256(b).hexdigest() for f,b in data.items()}
    (dest/'snapshot-sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest

def freeport():
    with socket.socket() as s:
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'): s.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        s.bind(('127.0.0.1',0)); return s.getsockname()[1]

def childenv(home):
    env={k:os.environ[k] for k in ('SYSTEMROOT','WINDIR','PATH','COMSPEC','PATHEXT') if k in os.environ}
    env.update({k:str(home) for k in ('HOME','USERPROFILE','APPDATA','LOCALAPPDATA','TEMP','TMP')})
    env['PYTHONDONTWRITEBYTECODE']='1'
    return env

def main():
    result={'checks':{},'children':[],'network':'not_attempted'}
    processes=[]; adapter=None; run=None; manifest=None; snap=None
    def check(name,condition):
        result['checks'][name]=bool(condition)
        if not condition: raise RuntimeError('Check failed: '+name)
    try:
        no_reparse(BINARY)
        if not BINARY.is_file() or hashlib.sha256(BINARY.read_bytes()).hexdigest()!=DIGEST: raise RuntimeError('Official binary hash mismatch')
        RUNROOT.mkdir(parents=True,exist_ok=True)
        run=RUNROOT/('run-'+secrets.token_hex(8)); run.mkdir()
        snap=run/'candidate'; snap.mkdir(); manifest=snapshot(snap)
        data=run/'empty-data'; data.mkdir(); home=run/'child-home'; home.mkdir()
        adapter=Adapter(('127.0.0.1',0),Handler)
        threading.Thread(target=adapter.serve_forever,daemon=True).start()
        env=childenv(home)
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        t=subprocess.Popen([str(BINARY),'tunnel','--no-autoupdate','--url','http://127.0.0.1:'+str(adapter.server_port)],cwd=run,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=flags)
        processes.append(('tunnel',t)); result['children'].append({'name':'tunnel','pid':t.pid})
        q=queue.Queue(); registered=threading.Event()
        result['tunnel_log_classes']={'connection_error':0,'timeout':0,'quic':0,'registered':0}
        def consume():
            for line in iter(t.stdout.readline,b''):
                lower=line.lower()
                if b'registered tunnel connection' in lower:
                    result['tunnel_log_classes']['registered']+=1; registered.set()
                if b'error' in lower: result['tunnel_log_classes']['connection_error']+=1
                if b'timeout' in lower: result['tunnel_log_classes']['timeout']+=1
                if b'quic' in lower: result['tunnel_log_classes']['quic']+=1
                m=re.search(rb'https://[a-z0-9-]+\.trycloudflare\.com',line)
                if m: q.put(m.group().decode())
        threading.Thread(target=consume,daemon=True).start()
        try: origin=q.get(timeout=40)
        except queue.Empty: raise RuntimeError('Quick Tunnel did not supply a hostname within 40 seconds')
        if not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',origin): raise RuntimeError('Invalid tunnel origin')
        result['network']='tunnel_registration'
        if not registered.wait(20): raise RuntimeError('Quick Tunnel connector did not register within 20 seconds')
        secret=secrets.token_urlsafe(48); bp=freeport(); gp=freeport()
        if gp==bp: raise RuntimeError('Port allocation collision')
        env.update({'APP_HOST':'127.0.0.1','APP_PORT':str(bp),'APP_GATEWAY_PORT':str(gp),'APP_DATA_DIR':str(data),'APP_PUBLIC_ORIGIN':origin,'APP_GATEWAY_SECRET':secret,'APP_AI_PROVIDER':'ollama','OLLAMA_URL':'http://127.0.0.1:1','APP_ALLOWED_HOSTS':origin[8:]})
        for name,module in [('backend','server'),('gateway','server.gateway')]:
            p=subprocess.Popen([sys.executable,'-B','-m',module],cwd=snap,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            processes.append((name,p)); result['children'].append({'name':name,'pid':p.pid})
        local='http://127.0.0.1:'+str(bp)
        for _ in range(60):
            if any(p.poll() is not None for _,p in processes): raise RuntimeError('Owned process exited during startup')
            try:
                status,_=request(local,'GET','/');
                if status==200: break
            except OSError: pass
            time.sleep(.1)
        else: raise RuntimeError('Isolated backend did not start')
        status,created=request(local,'POST','/api/sessions',{'title':'Synthetic','channel':'synthetic','purpose':'synthetic'},{'Origin':local})
        check('local_synthetic_bootstrap',status==201)
        sid=created['session']['id']; creator=created['creatorToken']; code=created['joinCode']; sp='/api/sessions/'+sid
        auth={'Origin':local,'Authorization':'Bearer '+creator}
        status,_=request(local,'POST',sp+'/sources',{'kind':'note','title':'Visible','text':'visible fixture','audienceVisible':True},auth); check('local_visible_source',status==201)
        status,_=request(local,'POST',sp+'/sources',{'kind':'note','title':'Private','text':'private fixture','audienceVisible':False},auth); check('local_private_source',status==201)
        # Check the exact snapshotted core/gateway boundary before public traffic is enabled.
        def gateway_status(method,path,payload=None,headers=None):
            c=http.client.HTTPConnection('127.0.0.1',gp,timeout=3)
            h={'Host':origin[8:],'Origin':origin}; h.update(headers or {})
            raw=json.dumps(payload).encode() if payload is not None else None
            if raw is not None: h['Content-Type']='application/json'
            try:
                c.request(method,path,body=raw,headers=h); r=c.getresponse(); r.read(); return r.status
            finally: c.close()
        for _ in range(40):
            try:
                if gateway_status('GET','/')==200: break
            except OSError: pass
            time.sleep(.1)
        else: raise RuntimeError('Isolated gateway did not start')
        check('local_gateway_creator_denied',gateway_status('GET',sp,headers={'Authorization':'Bearer '+creator})==403)
        check('local_gateway_bootstrap_denied',gateway_status('POST','/api/sessions',{'title':'x'})==404)
        check('local_gateway_health_denied',gateway_status('GET','/api/health')==404)
        check('local_gateway_cross_origin_denied',gateway_status('POST',sp+'/join',{'joinCode':code},{'Origin':'https://attacker.invalid'})==403)
        # Keep one hostname while comparing Windows, directed UDP and Cloudflare DoH.
        # The public adapter remains closed during DNS propagation checks.
        host=origin[8:]; deadline=time.monotonic()+150; observations=[]; doh_addresses=[]
        while True:
            started=time.monotonic(); probe, addresses=dns_probe(host)
            observations.append({'elapsed_seconds':round(150-(deadline-started),1),**probe})
            if addresses: doh_addresses=addresses
            if probe['windows']=='resolved' or time.monotonic()>=deadline: break
            time.sleep(min(15,max(0,deadline-time.monotonic())))
        result['dns_observations']=observations
        if observations[-1]['windows']!='resolved':
            if doh_addresses:
                adapter.target=gp
                try: result['explicit_ip_diagnostic']={'https_status':diagnostic_https(host,doh_addresses[0]),'certificate_validation':'enabled','transport':'explicit_ip_diagnostic_only'}
                except Exception as e: result['explicit_ip_diagnostic']={'error_type':type(e).__name__,'certificate_validation':'enabled','transport':'explicit_ip_diagnostic_only'}
                finally: adapter.target=None
            result['network']='dns_unresolved'
            raise RuntimeError('Windows resolver did not resolve temporary hostname within bounded observation')
        adapter.target=gp
        result['network']='attempted'
        h={'Origin':origin}
        status,body=request(origin,'GET','/'); check('https_static',status==200 and isinstance(body,bytes) and b'<html' in body.lower())
        status,_=request(origin,'POST','/api/sessions',{'title':'x'},h); check('https_bootstrap_denied',status in (403,404))
        status,_=request(origin,'GET','/api/health'); check('https_health_denied',status in (403,404))
        status,_=request(origin,'POST',sp+'/join',{'joinCode':code},{'Origin':'https://attacker.invalid'}); check('https_cross_origin_denied',status==403)
        status,_=request(origin,'GET',sp,headers={'Authorization':'Bearer '+creator}); check('https_creator_role_denied',status==403)
        status,viewer=request(origin,'POST',sp+'/join',{'joinCode':code},h); check('https_join',status==200)
        status,other=request(origin,'POST',sp+'/join',{'joinCode':code},h); check('https_second_viewer_join',status==200)
        va={'Origin':origin,'Authorization':'Bearer '+viewer['viewerToken']}; vb={'Origin':origin,'Authorization':'Bearer '+other['viewerToken']}
        status,sources=request(origin,'GET',sp+'/sources',headers=va); check('https_source_visibility',status==200 and len(sources['sources'])==1 and 'private fixture' not in json.dumps(sources))
        status,conv=request(origin,'POST',sp+'/conversations',{'title':'synthetic private'},va); check('https_private_create',status==201)
        status,_=request(origin,'GET',sp+'/conversations/'+conv['conversation']['id'],headers=vb); check('https_foreign_viewer_denied',status==404)
        status,_=request(origin,'GET',sp,headers={'Authorization':'Bearer '+creator,'X-Forwarded-For':'127.0.0.1'}); check('https_forged_forwarding_no_creator_authority',status==403)
        status,_=request(origin,'GET','/',headers={'X-Companion-Gateway':'forged'}); check('https_forged_marker_denied',status==403)
        result['network']='https_smoke_passed'
    except Exception as exc:
        result['failure_type']=type(exc).__name__
        if isinstance(exc,RuntimeError): result['failure']=str(exc)
        reason=getattr(exc,'reason',None)
        if reason is not None:
            result['network_reason_type']=type(reason).__name__
            result['network_errno']=getattr(reason,'errno',None)
            result['network_winerror']=getattr(reason,'winerror',None)
    finally:
        if adapter: adapter.target=None
        for name,p in reversed(processes):
            # Popen retains the process handle; never look up or kill by PID alone.
            if p.poll() is None: p.terminate()
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if p.poll() is None: p.kill()
                p.wait(timeout=10)
            for item in result['children']:
                if item['name']==name: item['stopped']=p.poll() is not None; item['exit_code']=p.returncode
        if adapter: adapter.shutdown(); adapter.server_close()
        if manifest and snap:
            result['snapshot_hashes_match']=all(hashlib.sha256((snap/f).read_bytes()).hexdigest()==digest for f,digest in manifest.items())
        if run: (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,sort_keys=True))
    return 0 if result['network']=='https_smoke_passed' and result.get('snapshot_hashes_match') is True else 1

MANUAL_ROOT = ROOT / '.runtime/mesa02/PHASE34-GATEWAY'
RELEASE = MANUAL_ROOT / 'MANUAL-RELEASE.json'
READY = MANUAL_ROOT / 'MANUAL-READY.json'
ACTION = MANUAL_ROOT / 'MANUAL-ACTION.json'
BROWSER_ACCEPTED = MANUAL_ROOT / 'MANUAL-BROWSER-ACCEPTED.json'
BACKEND_MANIFEST = Path('.runtime/mesa02/PHASE34-CORE/release-r3/manifest.json')
BACKEND_MANIFEST_SHA256 = 'be45ae341fe6f1923164f5d92f71664285d4015943ae813cb9bc00102327d8e5'
CLIENT_FILES = {name for name in FILES if name.startswith('client/')}
COMPAT_CHECKS = ('health_404','providers_404','viewer_join','visible_source','private_source_absent','bookmark_save','reload','bookmark_retained')
LOCK = MANUAL_ROOT / 'MANUAL-LOCK'


def reference_bytes(ref, *, required_parent=None):
    if not isinstance(ref,dict) or not isinstance(ref.get('path'),str) or not isinstance(ref.get('sha256'),str) or not re.fullmatch(r'[0-9a-fA-F]{64}',ref['sha256']):
        raise ValueError('Invalid evidence reference')
    rel=Path(ref['path'])
    if rel.is_absolute() or rel.drive or '..' in rel.parts or rel.as_posix()!=ref['path']:
        raise ValueError('Invalid evidence path')
    target=(ROOT/rel).absolute(); parent=(ROOT/(required_parent or '.runtime')).absolute()
    if not target.is_relative_to(parent) or target==parent: raise ValueError('Evidence outside permitted runtime')
    no_reparse(target)
    data=target.read_bytes()
    if len(data)>1024*1024 or hashlib.sha256(data).hexdigest()!=ref['sha256'].lower(): raise ValueError('Evidence hash mismatch')
    return data


def load_release():
    no_reparse(RELEASE); raw=RELEASE.read_bytes()
    if len(raw)>1024*1024: raise ValueError('Release manifest too large')
    info=json.loads(raw)
    if not isinstance(info,dict) or not isinstance(info.get('sourceRoot'),str) or not isinstance(info.get('files'),list): raise ValueError('Invalid release manifest')
    rel=Path(info['sourceRoot'])
    if rel.is_absolute() or rel.drive or '..' in rel.parts or rel.as_posix()!=info['sourceRoot']: raise ValueError('Invalid release root')
    source=(ROOT/rel).absolute(); no_reparse(source)
    if not source.is_relative_to((ROOT/'.runtime').absolute()) or source==(ROOT/'.runtime').absolute(): raise ValueError('Release source must be an isolated repository runtime snapshot')
    files={}
    for entry in info['files']:
        if not isinstance(entry,dict) or not {'path','sha256'}.issubset(entry): raise ValueError('Invalid release file entry')
        name=entry['path']; digest=entry['sha256']
        if not isinstance(name,str) or not isinstance(digest,str) or not re.fullmatch('[a-fA-F0-9]{64}',digest): raise ValueError('Invalid release file entry')
        path=Path(name)
        if path.is_absolute() or path.drive or '..' in path.parts or path.as_posix()!=name or name in files: raise ValueError('Invalid release path')
        no_reparse(source/path); data=(source/path).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest.lower(): raise ValueError('Release hash mismatch')
        files[name]=(digest.lower(),data)
    if not set(FILES).issubset(files): raise ValueError('Release is missing runtime files')
    backend_raw=reference_bytes({'path':BACKEND_MANIFEST.as_posix(),'sha256':BACKEND_MANIFEST_SHA256})
    backend=json.loads(backend_raw)
    for name in (name for name in FILES if name.startswith('server/')):
        if backend.get(name)!=files[name][0]: raise ValueError('Release backend does not match R3')
    client_raw=reference_bytes(info.get('clientManifest'))
    client=json.loads(client_raw)
    entries=client.get('files') if isinstance(client,dict) else None
    if not isinstance(entries,list) or len(entries)!=len(CLIENT_FILES): raise ValueError('Invalid seven-file client manifest')
    client_files={}
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get('path'),str) or not isinstance(entry.get('sha256'),str): raise ValueError('Invalid client manifest entry')
        name=entry['path']; digest=entry['sha256'].lower()
        if name in client_files or name not in CLIENT_FILES or not re.fullmatch('[a-f0-9]{64}',digest): raise ValueError('Invalid client manifest entry')
        client_files[name]=digest
    if set(client_files)!=CLIENT_FILES or any(files[name][0]!=digest for name,digest in client_files.items()): raise ValueError('Release client does not match client manifest')
    proof_raw=reference_bytes(info.get('compatibilityProof'))
    proof=json.loads(proof_raw); checks=proof.get('checks') if isinstance(proof,dict) else None
    if (not isinstance(proof,dict) or proof.get('kind')!='viewer-client-compatibility' or proof.get('result')!='pass'
        or proof.get('clientManifestSha256')!=hashlib.sha256(client_raw).hexdigest() or not isinstance(checks,dict)
        or any(checks.get(name) is not True for name in COMPAT_CHECKS)):
        raise ValueError('Client compatibility proof is incomplete or mismatched')
    return raw,source,files,{'clientManifestSha256':hashlib.sha256(client_raw).hexdigest(),'compatibilityProofSha256':hashlib.sha256(proof_raw).hexdigest()}


def browser_acceptance(marker, ready, db):
    try:
        if not marker.is_file(): return None
        no_reparse(marker); raw=marker.read_bytes()
        if len(raw)>4096: return None
        descriptor=json.loads(raw); data=reference_bytes(descriptor,required_parent='.runtime/mesa04')
        proof=json.loads(data); checks=proof.get('checks') if isinstance(proof,dict) else None
        viewer=proof.get('viewerId') if isinstance(proof,dict) else None
        if (not isinstance(proof,dict) or proof.get('kind')!='m04-live-viewer' or proof.get('result')!='pass'
            or proof.get('hostInstanceId')!=ready['hostInstanceId'] or proof.get('releaseManifestSha256')!=ready['releaseManifestSha256']
            or proof.get('invitationRevision')!=ready['invitationRevision'] or not isinstance(checks,dict)
            or any(checks.get(name) is not True for name in COMPAT_CHECKS)
            or not isinstance(viewer,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',viewer)):
            return None
        with closing(sqlite3.connect('file:'+db.as_posix()+'?mode=ro',uri=True,timeout=5)) as con:
            if not con.execute("SELECT 1 FROM credentials WHERE session_id=? AND role='viewer' AND owner_id=?",(ready['sessionId'],viewer)).fetchone(): return None
        return viewer,hashlib.sha256(data).hexdigest()
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error): return None


def manual_snapshot(dest,raw,source,files):
    for name in FILES:
        digest,data=files[name]
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest: raise ValueError('Release changed during snapshot')
        out=dest/name; out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(data); out.chmod(stat.S_IREAD)
    if RELEASE.read_bytes()!=raw: raise ValueError('Release manifest changed during snapshot')
    for name in FILES:
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=files[name][0]: raise ValueError('Release changed during snapshot')
    manifest={name:files[name][0] for name in FILES}
    (dest/'snapshot-sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def atomic_json(path,value):
    no_reparse(path)
    tmp=path.with_name(path.name+'.'+secrets.token_hex(8)+'.tmp')
    with tmp.open('x',encoding='utf-8') as out: json.dump(value,out,indent=2)
    os.replace(tmp,path)


def manual_stats(db,sid,excluded,salt,visible_id,private_id):
    with closing(sqlite3.connect('file:'+db.as_posix()+'?mode=ro',uri=True,timeout=5)) as con:
        viewers=[r[0] for r in con.execute("SELECT owner_id FROM credentials WHERE role='viewer' AND session_id=?",(sid,)) if r[0] not in excluded]
        counts={v:0 for v in viewers}
        for owner,n in con.execute("SELECT owner_id,count(*) FROM objects WHERE kind='bookmark' AND session_id=? GROUP BY owner_id",(sid,)):
            if owner in counts: counts[owner]=n
        sources={r[0] for r in con.execute("SELECT id FROM objects WHERE kind='source' AND session_id=?",(sid,))}
    return {'activeUnclassifiedViewerCapabilities':len(viewers),'excludedAutomationCapabilities':len(excluded),'viewers':[{'identityHash':hashlib.sha256(salt+v.encode()).hexdigest(),'bookmarkCount':counts[v]} for v in sorted(viewers)],'visibleSourceConfigured':visible_id in sources,'privateSourceConfigured':private_id in sources}


def manual():
    processes=[]; adapter=None; run=None; manifest=None; snap=None; lock_owned=False; ready=None
    result={'state':'starting','children':[]}
    creator=origin=sid=code=None
    try:
        MANUAL_ROOT.mkdir(parents=True,exist_ok=True); no_reparse(MANUAL_ROOT)
        with LOCK.open('x',encoding='utf-8') as lock: lock.write('manual host owns this lock; inspect stale lock before removal')
        lock_owned=True
        if READY.exists(): raise RuntimeError('Existing readiness file requires operator inspection')
        raw,source,files,proof_identity=load_release()
        no_reparse(BINARY)
        if not BINARY.is_file() or hashlib.sha256(BINARY.read_bytes()).hexdigest()!=DIGEST: raise RuntimeError('Official binary hash mismatch')
        run=RUNROOT/('manual-'+secrets.token_hex(8)); run.mkdir(); snap=run/'candidate'; snap.mkdir()
        manifest=manual_snapshot(snap,raw,source,files)
        reread,_,_,proof_recheck=load_release()
        if reread!=raw or proof_recheck!=proof_identity: raise RuntimeError('Release evidence changed during snapshot')
        data=run/'empty-data'; data.mkdir(); home=run/'child-home'; home.mkdir()
        adapter=Adapter(('127.0.0.1',0),Handler); adapter.manual_only=True
        threading.Thread(target=adapter.serve_forever,daemon=True).start()
        env=childenv(home); flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        tunnel=subprocess.Popen([str(BINARY),'tunnel','--no-autoupdate','--url','http://127.0.0.1:'+str(adapter.server_port)],cwd=run,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=flags)
        processes.append(('tunnel',tunnel)); result['children'].append({'name':'tunnel','pid':tunnel.pid})
        q=queue.Queue(); registered=threading.Event()
        def consume():
            for line in iter(tunnel.stdout.readline,b''):
                if b'registered tunnel connection' in line.lower(): registered.set()
                match=re.search(rb'https://[a-z0-9-]+\.trycloudflare\.com',line)
                if match: q.put(match.group().decode())
        threading.Thread(target=consume,daemon=True).start()
        try: origin=q.get(timeout=40)
        except queue.Empty: raise RuntimeError('Tunnel hostname unavailable')
        if not re.fullmatch(r'https://[a-z0-9-]+\.trycloudflare\.com',origin) or not registered.wait(20): raise RuntimeError('Tunnel registration unavailable')
        bp=freeport(); gp=freeport()
        if bp==gp: raise RuntimeError('Port allocation collision')
        secret=secrets.token_urlsafe(48)
        env.update({'APP_HOST':'127.0.0.1','APP_PORT':str(bp),'APP_GATEWAY_PORT':str(gp),'APP_DATA_DIR':str(data),'APP_PUBLIC_ORIGIN':origin,'APP_GATEWAY_SECRET':secret,'APP_AI_PROVIDER':'ollama','OLLAMA_URL':'http://127.0.0.1:1','APP_ALLOWED_HOSTS':origin[8:]})
        for name,module in [('backend','server'),('gateway','server.gateway')]:
            p=subprocess.Popen([sys.executable,'-B','-m',module],cwd=snap,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            processes.append((name,p)); result['children'].append({'name':name,'pid':p.pid})
        local='http://127.0.0.1:'+str(bp)
        for _ in range(60):
            if any(p.poll() is not None for _,p in processes): raise RuntimeError('Owned process exited')
            try:
                if request(local,'GET','/')[0]==200: break
            except OSError: pass
            time.sleep(.1)
        else: raise RuntimeError('Backend unavailable')
        status,created=request(local,'POST','/api/sessions',{'title':'Device check','channel':'synthetic','purpose':'Synthetic device check'},{'Origin':local})
        if status!=201: raise RuntimeError('Synthetic bootstrap failed')
        sid=created['session']['id']; creator=created['creatorToken']; code=created['joinCode']
        auth={'Origin':local,'Authorization':'Bearer '+creator}; base='/api/sessions/'+sid
        ids=[]
        for title,visible in [('Visible device-check source',True),('Creator-only device-check source',False)]:
            status,obj=request(local,'POST',base+'/sources',{'kind':'note','title':title,'text':title,'audienceVisible':visible},auth)
            if status!=201: raise RuntimeError('Synthetic source failed')
            ids.append(obj['source']['id'])
        visible_id,private_id=ids
        # No external traffic until normal DNS resolves and core/gateway preconditions pass.
        def local_gate(method,path,payload=None,headers=None):
            c=http.client.HTTPConnection('127.0.0.1',gp,timeout=3); h={'Host':origin[8:],'Origin':origin}; h.update(headers or {})
            rawbody=json.dumps(payload).encode() if payload is not None else None
            if rawbody is not None: h['Content-Type']='application/json'
            try: c.request(method,path,body=rawbody,headers=h); r=c.getresponse(); r.read(); return r.status
            finally: c.close()
        for _ in range(40):
            try:
                if local_gate('GET','/')==200: break
            except OSError: pass
            time.sleep(.1)
        else: raise RuntimeError('Gateway unavailable')
        if local_gate('GET',base,headers={'Authorization':'Bearer '+creator})!=403 or local_gate('POST','/api/sessions',{'title':'x'})!=404 or local_gate('GET','/api/health')!=404: raise RuntimeError('Local gateway security check failed')
        deadline=time.monotonic()+150; observations=[]
        while True:
            start=time.monotonic(); probe,_=dns_probe(origin[8:]); observations.append({'elapsed_seconds':round(150-(deadline-start),1),**probe})
            if probe['windows']=='resolved': break
            if time.monotonic()>=deadline: raise RuntimeError('Windows DNS did not resolve within bounded wait')
            if any(p.poll() is not None for _,p in processes): raise RuntimeError('Owned process exited')
            time.sleep(min(15,max(0,deadline-time.monotonic())))
        result['dnsObservations']=observations
        adapter.target=gp
        def require(cond):
            if not cond: raise RuntimeError('Public boundary check failed')
        h={'Origin':origin}
        status,html=request(origin,'GET','/'); require(status==200 and isinstance(html,bytes) and b'<html' in html.lower())
        require(request(origin,'POST','/api/sessions',{'title':'x'},h)[0] in (403,404))
        require(request(origin,'GET','/api/health')[0] in (403,404))
        require(request(origin,'GET','/api/providers')[0] in (403,404))
        require(request(origin,'POST',base+'/join',{'joinCode':code},{'Origin':'https://attacker.invalid'})[0]==403)
        require(request(origin,'GET',base+'/workbench')[0] in (403,404))
        require(request(origin,'GET','/',headers={'X-Companion-Gateway':'forged'})[0]==403)
        status,viewer=request(origin,'POST',base+'/join',{'joinCode':code,'displayName':'Preflight'},h); require(status==200)
        probe_token=viewer['viewerToken']; probe_id=viewer['viewerId']; excluded={probe_id}
        vh={'Origin':origin,'Authorization':'Bearer '+probe_token}
        status,src=request(origin,'GET',base+'/sources',headers=vh)
        require(status==200 and len(src['sources'])==1 and src['sources'][0]['id']==visible_id and private_id not in json.dumps(src))
        require(request(origin,'POST',base+'/conversations/fixture/messages',{},vh)[0]==404)
        salt=secrets.token_bytes(32); end=time.monotonic()+1800; end_utc=(datetime.now(timezone.utc)+timedelta(seconds=1800)).isoformat()
        invitation=origin+'/?'+urlencode({'sessionId':sid,'joinCode':code})
        ready={'state':'api-ready-awaiting-browser','hostInstanceId':secrets.token_hex(16),'invitationRevision':0,'browserProofSha256':None,**proof_identity,'invitationUrl':invitation,'origin':origin,'sessionId':sid,'visibleSourceId':visible_id,'privateSourceId':private_id,'hostPid':os.getpid(),'children':result['children'],'releaseManifestSha256':hashlib.sha256(raw).hexdigest(),'snapshotSha256':manifest,'deadlineUtc':end_utc,'lastAction':None,'stats':manual_stats(data/'companion.sqlite3',sid,excluded,salt,visible_id,private_id)}
        seen=set(); started=time.time(); atomic_json(READY,ready); result['state']='api-ready-awaiting-browser'
        while time.monotonic()<end:
            if any(p.poll() is not None for _,p in processes): raise RuntimeError('Owned process exited during manual window')
            if ready['state']=='api-ready-awaiting-browser':
                accepted=browser_acceptance(BROWSER_ACCEPTED,ready,data/'companion.sqlite3')
                if accepted:
                    browser_viewer,browser_hash=accepted; excluded.add(browser_viewer)
                    ready['state']='human-ready'; ready['browserProofSha256']=browser_hash
                    ready['stats']=manual_stats(data/'companion.sqlite3',sid,excluded,salt,visible_id,private_id)
                    atomic_json(READY,ready)
            action=None
            try:
                no_reparse(ACTION)
                if ACTION.exists() and ACTION.stat().st_mtime >= started:
                    raw_action=ACTION.read_bytes()
                    if len(raw_action)<=4096:
                        candidate=json.loads(raw_action)
                        if isinstance(candidate,dict):
                            ident=candidate.get('id'); kind=candidate.get('action')
                            if isinstance(ident,str) and re.fullmatch(r'[A-Za-z0-9_-]{8,80}',ident) and kind in ('status','rotate','stop') and ident not in seen:
                                action=(ident,kind)
            except (ValueError,OSError): pass
            if action:
                ident,kind=action; seen.add(ident); outcome='ok'
                if kind=='rotate':
                    status,rotated=request(local,'POST',base+'/lifecycle',{'action':'rotate'},auth)
                    if status!=200: raise RuntimeError('Rotation failed')
                    code=rotated['joinCode']; ready['state']='api-ready-awaiting-browser'; ready['browserProofSha256']=None; ready['invitationRevision']+=1
                    old_status=request(origin,'GET',base,headers=vh)[0]
                    if old_status!=401: raise RuntimeError('Old viewer revocation not verified')
                    status,newprobe=request(origin,'POST',base+'/join',{'joinCode':code,'displayName':'Preflight'},h)
                    if status!=200: raise RuntimeError('Rotated invitation verification failed')
                    probe_token=newprobe['viewerToken']; probe_id=newprobe['viewerId']; excluded={probe_id}
                    vh={'Origin':origin,'Authorization':'Bearer '+probe_token}
                    ready['invitationUrl']=origin+'/?'+urlencode({'sessionId':sid,'joinCode':code})
                    outcome='old_preflight_capability_denied_401'
                ready['stats']=manual_stats(data/'companion.sqlite3',sid,excluded,salt,visible_id,private_id)
                ready['lastAction']={'id':ident,'action':kind,'result':outcome}
                if kind=='stop': ready['state']='STOPPING'
                atomic_json(READY,ready)
                if kind=='stop': break
            time.sleep(1)
        result['state']='stopped'
    except Exception as exc:
        result['state']='failed'; result['failure_type']=type(exc).__name__
        if isinstance(exc,(RuntimeError,ValueError)): result['failure']=str(exc)
    finally:
        if adapter: adapter.target=None
        for name,p in reversed(processes):
            if p.poll() is None: p.terminate()
            try: p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                if p.poll() is None: p.kill()
                p.wait(timeout=10)
            for item in result['children']:
                if item['name']==name: item['stopped']=p.poll() is not None; item['exit_code']=p.returncode
        if adapter: adapter.shutdown(); adapter.server_close()
        if manifest and snap: result['snapshotHashesMatch']=all(hashlib.sha256((snap/f).read_bytes()).hexdigest()==d for f,d in manifest.items())
        if ready:
            ready['state']='STOPPED' if result['state']=='stopped' else 'FAILED'; ready['children']=result['children']; ready['invitationUrl']=None
            ready['snapshotHashesMatch']=result.get('snapshotHashesMatch'); atomic_json(READY,ready)
        if run: (run/'manual-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        if lock_owned:
            try: LOCK.unlink()
            except OSError: pass
        print(json.dumps(result,sort_keys=True))
    return 0 if result['state']=='stopped' and result.get('snapshotHashesMatch') is True else 1

if __name__=='__main__': sys.exit(manual() if sys.argv[1:]==['--manual'] else main())
