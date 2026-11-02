"""Creator-approved, session-scoped terminology; all supplied content is data."""
import hashlib, json, re
from . import store, lifecycle
from .phase10_common import Phase10Error

KIND='w17terminology'
RECEIPT='w17termsreceipt'
def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def fail(code, message, status=409): raise Phase10Error(code,message,status)
def ident(v): return isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',v))
def text(v,n):
    if not isinstance(v,str) or not v.strip() or len(v)>n or any(ord(c)<32 and c not in '\n\r\t' for c in v): fail('invalid_request','Invalid terminology text.',422)
    try: v.encode('utf-8')
    except UnicodeEncodeError: fail('invalid_request','Invalid Unicode.',422)
    return v

def actor_check(handler,sid,actor,creator=False):
    if store.auth(getattr(handler,'_auth_token',''))!=actor or actor.get('sid')!=sid or not lifecycle.active(store.get('session',sid) or {}): fail('stale_context','Session or capability unavailable.')
    if creator and actor.get('role')!='creator': fail('forbidden','Creator capability required.',403)

def validate(data):
    if not isinstance(data,dict) or set(data)!={'terms','context'} or not isinstance(data['terms'],list) or not isinstance(data['context'],list) or len(data['terms'])>50 or len(data['context'])>10: fail('invalid_request','Invalid terminology document.',422)
    seen=set()
    for term in data['terms']:
        if not isinstance(term,dict) or set(term)!={'id','en','es','alternatives','ambiguity'} or not ident(term['id']) or term['id'] in seen: fail('invalid_request','Invalid term.',422)
        seen.add(term['id']); text(term['en'],120); text(term['es'],120)
        if not isinstance(term['alternatives'],list) or len(term['alternatives'])>5: fail('invalid_request','Invalid alternatives.',422)
        for alt in term['alternatives']:
            if not isinstance(alt,dict) or set(alt)!={'en','es'}: fail('invalid_request','Invalid alternative.',422)
            text(alt['en'],120); text(alt['es'],120)
        if not isinstance(term['ambiguity'],str) or len(term['ambiguity'])>500: fail('invalid_request','Invalid ambiguity.',422)
        if term['ambiguity']: text(term['ambiguity'],500)
    for item in data['context']:
        if not isinstance(item,dict) or set(item)!={'id','text','ref'} or not ident(item['id']) or item['id'] in seen: fail('invalid_request','Invalid context.',422)
        seen.add(item['id']); text(item['text'],1000)
        if not isinstance(item['ref'],dict): fail('invalid_request','A source reference is required.',422)
    if len(canon(data).encode('utf-8'))>32000: fail('invalid_request','Terminology document too large.',422)
    return data

def check_refs(sid,actor,credential_hash,doc):
    from . import phase12_jobs
    for item in doc['context']:
        candidate={'session_id':sid,'actor_id':actor['owner'],'role':actor['role'],'credential_hash':credential_hash,'ref':canon(item['ref'])}
        phase12_jobs.rights(candidate)

def check_record_refs(sid,actor,credential_hash,record):
    if record:
        for name in ('draft','approved'):
            if record.get(name): check_refs(sid,actor,credential_hash,record[name]['document'])

def load(sid):
    return store.get(KIND,sid,sid)

def snapshot(sid,actor,credential_hash,expected):
    """Resolve exact approved revision, checking source rights for this actor."""
    record=load(sid)
    if not record or not record.get('approved') or record['approved']['revision']!=expected: fail('stale_terminology','Approved terminology changed or is disabled.')
    approved=record['approved']; check_refs(sid,actor,credential_hash,approved['document'])
    return {'revision':approved['revision'],'document':approved['document']}

def guard(row):
    """Validate an opted-in job or correction against the currently approved snapshot."""
    try:
        payload=json.loads(row['payload'])
    except (TypeError, ValueError):
        fail('stale_terminology', 'Terminology binding unavailable.')
    if not isinstance(payload, dict):
        fail('stale_terminology', 'Terminology binding unavailable.')
    bound=payload.get('terminologySnapshot')
    if row['kind']=='translation' and row['transport']=='local_user_correction':
        from . import phase12_jobs
        parent_id=payload.get('originalRequestId')
        if not isinstance(parent_id, str) or not parent_id:
            fail('stale_terminology', 'Terminology binding unavailable.')
        parent=phase12_jobs.fetch(row['session_id'],row['actor_id'],parent_id)
        if not parent or parent['kind']!='translation' or parent['transport']=='local_user_correction':
            fail('stale_terminology', 'Terminology binding unavailable.')
        return guard(parent)
    if 'terminologySnapshot' in payload:
        if (not isinstance(bound, dict) or type(bound.get('revision')) is not int
                or bound['revision'] < 1 or not isinstance(bound.get('document'), dict)):
            fail('stale_terminology', 'Terminology binding unavailable.')
        try:
            validate(bound['document'])
        except Phase10Error:
            fail('stale_terminology', 'Terminology binding unavailable.')
        check_refs(row['session_id'],{'owner':row['actor_id'],'role':row['role']},row['credential_hash'],bound['document'])
        current=snapshot(row['session_id'],{'owner':row['actor_id'],'role':row['role']},row['credential_hash'],bound['revision'])
        if current!=bound: fail('stale_terminology','Approved terminology changed.')
    return bound

def handle(handler,sid,actor,method,parts):
    actor_check(handler,sid,actor,True)
    if parts not in ([],['approve'],['disable']): fail('not_found','Terminology route unavailable.',404)
    if method=='GET' and parts==[]:
        record=load(sid)
        check_record_refs(sid,actor,store.digest(handler._auth_token),record)
        return 200,{'terminology':record}
    if method!='POST': fail('method_not_allowed','Method unavailable.',405)
    body=handler.body()
    fields={'requestId','expectedRevision','document'} if not parts else {'requestId','expectedRevision'}
    if not isinstance(body,dict) or set(body)!=fields or not ident(body.get('requestId')) or type(body.get('expectedRevision')) is not int or body['expectedRevision']<0: fail('invalid_request','Invalid request.',422)
    if not parts: validate(body['document']); check_refs(sid,actor,store.digest(handler._auth_token),body['document'])
    fingerprint=hashlib.sha256(canon({'parts':parts,'body':body}).encode()).hexdigest()
    receipt_id=hashlib.sha256(canon([sid,actor['owner'],body['requestId']]).encode()).hexdigest()
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        receipt=db.execute('SELECT data FROM objects WHERE kind=? AND id=?',(RECEIPT,receipt_id)).fetchone()
        if receipt:
            saved=json.loads(receipt['data'])
            if saved['fingerprint']!=fingerprint: fail('request_conflict','Request ID is bound to another payload.')
            check_record_refs(sid,actor,store.digest(handler._auth_token),saved['response']['terminology'])
            db.commit(); return 200,saved['response']
        if db.execute('SELECT COUNT(*) FROM objects WHERE kind=? AND session_id=?',(RECEIPT,sid)).fetchone()[0]>=4096: fail('receipt_capacity','Terminology receipt storage is full.',429)
        row=db.execute('SELECT data,revision FROM objects WHERE kind=? AND id=? AND session_id=?',(KIND,sid,sid)).fetchone()
        old=json.loads(row['data']) if row else {'id':sid,'draft':None,'approved':None}
        revision=row['revision'] if row else 0
        if revision!=body['expectedRevision']: fail('stale_revision','Terminology revision changed.')
        new_revision=revision+1
        if not parts:
            old['draft']={'revision':new_revision,'document':body['document']}
            old['approved']=None
        elif parts==['approve']:
            if not old['draft'] or old['draft']['revision']!=revision: fail('stale_revision','Approve the exact current draft.')
            check_refs(sid,actor,store.digest(handler._auth_token),old['draft']['document'])
            old['approved']={'revision':new_revision,'draftRevision':revision,'document':old['draft']['document']}
            old['draft']=None
        else: old['approved']=None; old['draft']=None
        response={'terminology':dict(old,_revision=new_revision)}
        db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET revision=excluded.revision,data=excluded.data',(KIND,sid,sid,actor['owner'],new_revision,canon(old),store.now()))
        db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',(RECEIPT,receipt_id,sid,actor['owner'],canon({'fingerprint':fingerprint,'response':response}),store.now()))
        db.commit(); return 200,response
