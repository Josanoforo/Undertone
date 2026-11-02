"""Durable project authority and link storage; independent of session cleanup."""
from __future__ import annotations
import base64, hashlib, hmac, json, re
from urllib.parse import urlparse
from . import store, phase6 as p, lifecycle

SECRET=re.compile(r'^[A-Za-z0-9_-]{43}$')

def secret_hash(h,token):
    if not isinstance(token,str) or not SECRET.fullmatch(token):p.fail(h,'unauthorized',401)
    try:
        raw=base64.urlsafe_b64decode(token+'=')
        if len(raw)!=32 or base64.urlsafe_b64encode(raw).decode().rstrip('=')!=token:raise ValueError()
    except (ValueError,TypeError):p.fail(h,'unauthorized',401)
    return hashlib.sha256(token.encode()).hexdigest()

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS phase6_projects(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, owner_hash TEXT NOT NULL, data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS phase6_project_links(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,session_id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS phase6_project_receipts(actor TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,status INTEGER NOT NULL,result TEXT NOT NULL,PRIMARY KEY(actor,request_id))')

def get_project(db,pid):
    row=db.execute('SELECT * FROM phase6_projects WHERE id=?',(pid,)).fetchone()
    if not row:return None
    data=json.loads(row['data']);data['revision']=row['revision'];data['_ownerHash']=row['owner_hash'];return data

def project_dto(v):return {k:x for k,x in v.items() if not k.startswith('_')}

def auth_owner(handler,h,db,pid):
    if getattr(handler,'_gateway',False) or not h.is_loopback(handler.client_address[0]):p.fail(h,'forbidden',403)
    handler.require_same_site();header=handler.headers.get('Authorization','');token=header[7:] if header.startswith('Bearer ') else ''
    digest=secret_hash(h,token);v=get_project(db,pid)
    if not v or not hmac.compare_digest(digest,v['_ownerHash']):p.fail(h,'unauthorized',401)
    return v

def check(db,h,actor,key,fp):
    row=db.execute('SELECT * FROM phase6_project_receipts WHERE actor=? AND request_id=?',(actor,key)).fetchone()
    if row and row['fingerprint']!=fp:p.fail(h,'request_id_conflict',409)
    return row

def record(db,actor,key,fp,status,result):db.execute('INSERT INTO phase6_project_receipts VALUES(?,?,?,?,?)',(actor,key,fp,status,json.dumps(result)))
def get_link(db,lid):
    row=db.execute('SELECT * FROM phase6_project_links WHERE id=?',(lid,)).fetchone()
    if not row:return None
    v=json.loads(row['data']);v['revision']=row['revision'];return v

def save_link(db,v):
    old=v['revision'];v=dict(v);v['revision']=old+1
    if db.execute('UPDATE phase6_project_links SET revision=?,data=? WHERE id=? AND revision=?',(v['revision'],json.dumps(v),v['id'],old)).rowcount!=1:raise RuntimeError('stale')
    return v

def valid_scopes(h,scopes):
    p.keys(h,scopes,('creator','viewer'));p.keys(h,scopes['creator'],('read','propose','decide'));p.keys(h,scopes['viewer'],('read','propose'))
    if any(type(x) is not bool for x in list(scopes['creator'].values())+list(scopes['viewer'].values())):p.fail(h)
    if any(v['propose'] and not v['read'] for v in scopes.values()) or (scopes['creator']['decide'] and not scopes['creator']['read']) or not (scopes['creator']['read'] or scopes['viewer']['read']):p.fail(h)

def create(handler,h,sid,a,method):
    p.role(h,a,'creator')
    if method!='POST' or getattr(handler,'_gateway',False) or not h.is_loopback(handler.client_address[0]):p.fail(h,'forbidden',403)
    d=handler.body();p.keys(h,d,('requestId','title','question'));p.rid(h,d['requestId']);p.text(h,d['title'],200);p.text(h,d['question'])
    digest=secret_hash(h,handler.headers.get('X-Project-Owner'));fp=p.fingerprint(method,urlparse(handler.path).path,{**d,'ownerHash':digest});actor='create:'+sid+':'+a['owner']
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        try:
            session=p.load(db,'session',sid,sid)
            if not session or not lifecycle.active(session) or not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='creator' AND hash=?",(sid,a['owner'],store.digest(handler._auth_token))).fetchone():p.fail(h,'unauthorized',401)
            prev=check(db,h,actor,d['requestId'],fp)
            if prev:v=get_project(db,json.loads(prev['result'])['id'])
            else:
                v={'id':store.ident(),'revision':1,'title':d['title'],'question':d['question'],'state':{'reviewAvailable':False,'selectedPlan':None,'observations':[],'decisions':[],'actions':[]}}
                db.execute('INSERT INTO phase6_projects VALUES(?,?,?,?)',(v['id'],1,digest,json.dumps(v,ensure_ascii=False)));record(db,actor,d['requestId'],fp,201,{'id':v['id']})
            from . import phase6_project_work as work
            work.schema(db);out=work.project_dto(db,h,v)
            db.commit();handler.send(201,{'project':out})
        except BaseException:db.rollback();raise

def owner_route(handler,h,parts,method):
    if len(parts)<1:p.fail(h,'not_found',404)
    pid=parts[0]
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        try:
            v=auth_owner(handler,h,db,pid)
            if len(parts)==1 and method=='GET':db.commit();handler.send(200,{'project':project_dto(v)});return
            if len(parts)==2 and parts[1]=='links' and method=='GET':
                rows=db.execute('SELECT id FROM phase6_project_links WHERE project_id=? ORDER BY rowid',(pid,)).fetchall();out=p.page(handler,h,[get_link(db,r['id']) for r in rows]);db.commit();handler.send(200,out);return
            if method!='POST':p.fail(h,'not_found',404)
            d=handler.body();p.rid(h,d.get('requestId'));fp=p.fingerprint(method,urlparse(handler.path).path,d);actor='owner:'+pid
            prev=check(db,h,actor,d['requestId'],fp)
            if prev:
                link=get_link(db,json.loads(prev['result'])['id']);db.commit();handler.send(prev['status'],{'link':link});return
            status=200
            if len(parts)==2 and parts[1]=='links':
                p.keys(h,d,('requestId','sessionId','scopes'));p.text(h,d['sessionId'],128);valid_scopes(h,d['scopes']);s=p.load(db,'session',d['sessionId'],d['sessionId'])
                if not s or not lifecycle.active(s):p.fail(h,'reference_unavailable',409)
                link={'id':store.ident(),'revision':1,'projectId':pid,'sessionId':d['sessionId'],'scopes':d['scopes'],'status':'pending','ownerApproved':True,'creatorApproved':False}
                db.execute('INSERT INTO phase6_project_links VALUES(?,?,?,?,?)',(link['id'],pid,d['sessionId'],1,json.dumps(link)));status=201
            elif len(parts)==4 and parts[1]=='links' and parts[3]=='revoke':
                p.keys(h,d,('requestId','expectedRevision'));link=get_link(db,parts[2])
                if not link or link['projectId']!=pid:p.fail(h,'not_found',404)
                p.expect(h,link,d)
                if link['status']=='revoked':p.fail(h,'invalid_transition',409)
                link['status']='revoked';link=save_link(db,link)
            else:p.fail(h,'not_found',404)
            record(db,actor,d['requestId'],fp,status,{'id':link['id']});db.commit();handler.send(status,{'link':link})
        except BaseException:db.rollback();raise

def session_link_route(handler,h,sid,a,parts,method):
    p.role(h,a,'creator')
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        try:
            session=p.load(db,'session',sid,sid)
            if not session or not lifecycle.active(session) or not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='creator' AND hash=?",(sid,a['owner'],store.digest(handler._auth_token))).fetchone():p.fail(h,'unauthorized',401)
            if parts==['project-link-requests'] and method=='GET':
                rows=db.execute('SELECT id FROM phase6_project_links WHERE session_id=? ORDER BY rowid',(sid,)).fetchall();links=[get_link(db,x['id']) for x in rows];out=p.page(handler,h,[x for x in links if x['status']!='revoked']);db.commit();handler.send(200,out);return
            if len(parts)!=3 or parts[0]!='project-links' or method!='POST' or parts[2] not in ('approve','revoke'):p.fail(h,'not_found',404)
            d=handler.body();p.keys(h,d,('requestId','expectedRevision'));p.rid(h,d['requestId']);fp=p.fingerprint(method,urlparse(handler.path).path,d);actor='session:'+sid+':'+a['owner'];prev=check(db,h,actor,d['requestId'],fp)
            if prev:link=get_link(db,json.loads(prev['result'])['id']);db.commit();handler.send(prev['status'],{'link':link});return
            link=get_link(db,parts[1])
            if not link or link['sessionId']!=sid:p.fail(h,'not_found',404)
            p.expect(h,link,d)
            if parts[2]=='approve':
                if link['status']!='pending' or not link['ownerApproved']:p.fail(h,'invalid_transition',409)
                link['creatorApproved']=True;link['status']='active'
            else:
                if link['status']=='revoked':p.fail(h,'invalid_transition',409)
                link['status']='revoked'
            link=save_link(db,link);record(db,actor,d['requestId'],fp,200,{'id':link['id']});db.commit();handler.send(200,{'link':link})
        except BaseException:db.rollback();raise
