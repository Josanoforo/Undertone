"""Finite, consented creator formats. No provider or executable content."""
import hashlib, json, re
from . import store as _store, lifecycle
import threading
from .phase10_common import Context, Phase10Error

F='w15format'; C='w15formatcontribution'; T='w15formattransfer'

class _TransactionalStore:
    """Module-local transaction; never patches the shared store or its connections."""
    def __init__(self): self.local=threading.local()
    def __getattr__(self, name): return getattr(_store,name)
    def get(self, kind, oid, sid=None):
        db=getattr(self.local,'db',None)
        if db is None: return _store.get(kind,oid,sid)
        sql='SELECT data,revision FROM objects WHERE kind=? AND id=?'; args=[kind,oid]
        if sid is not None: sql+=' AND session_id=?'; args.append(sid)
        row=db.execute(sql,args).fetchone()
        return dict(json.loads(row['data']),_revision=row['revision']) if row else None
    def all(self,kind,sid):
        db=getattr(self.local,'db',None)
        if db is None: return _store.all(kind,sid)
        rows=db.execute('SELECT data,revision FROM objects WHERE kind=? AND session_id=? ORDER BY created_at',(kind,sid)).fetchall()
        return [dict(json.loads(r['data']),_revision=r['revision']) for r in rows]
    def put(self,kind,sid,data,owner=None,oid=None,revision=1):
        db=getattr(self.local,'db',None)
        if db is None: return _store.put(kind,sid,data,owner=owner,oid=oid,revision=revision)
        oid=oid or _store.ident(); value=dict(data); value.setdefault('id',oid)
        if kind!='session' and not db.execute("SELECT 1 FROM objects WHERE kind='session' AND id=?",(sid,)).fetchone(): raise KeyError(sid)
        db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',(kind,oid,sid,owner,revision,json.dumps(value,ensure_ascii=False),_store.now()))
        return value
    def save(self,kind,value,revision=None):
        db=getattr(self.local,'db',None)
        if db is None: return _store.save(kind,value,revision=revision)
        value=dict(value); oid=value['id']; expected=revision if revision is not None else value.get('_revision'); value.pop('_revision',None)
        row=db.execute('SELECT revision FROM objects WHERE kind=? AND id=?',(kind,oid)).fetchone()
        if not row: raise KeyError(oid)
        if expected is not None and row['revision']!=expected: raise RuntimeError('stale')
        db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=?',(json.dumps(value,ensure_ascii=False),row['revision']+1,kind,oid))
        return dict(value,_revision=row['revision']+1)
store=_TransactionalStore()
RECEIPT='w15formatreceipt'

def _receipt_id(sid,actor,key):
    return hashlib.sha256(json.dumps([sid,actor['owner'],key],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def _key(key):
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',key): error('Invalid mutation request ID.')
    return key

def _safe_replay(ctx,sid,actor,receipt):
    # Snapshots are returned only while every affected item is still exactly current.
    for dep in receipt['dependencies']:
        obj=store.get(dep['kind'],dep['id'],dep['sid'])
        if not obj or obj['_revision']!=dep['revision']: error('The committed result is no longer available.',409)
        if dep['kind']==F:
            visible,_=projection(ctx,obj,sid,actor)
            if visible.get('decision')!=obj.get('decision'): error('The committed result is no longer available.',409)
        elif dep['kind']==C:
            if obj.get('status')=='withdrawn' and dep.get('status')!='withdrawn': error('The committed result is no longer available.',409)
            current(ctx,obj)
            fmt=find(F,obj['formatId'],dep['sid']); current(ctx,fmt)
        elif dep['kind']==T:
            from . import waves16_continuation as continuation
            if obj.get('status') in ('withdrawn','declined'):
                if sid not in (obj.get('sourceSessionId'),obj.get('targetSessionId')): error('The committed result is no longer available.',409)
            else: continuation.guard_offer(ctx,obj)
        elif dep['kind']=='w16work':
            from . import waves16_continuation as continuation
            if obj['snapshot'].get('sourceSessionId')!=sid: error('The committed result is no longer available.',409)
            continuation.validate_snapshot(obj['snapshot'])
        elif dep['kind']=='p10material':
            from . import waves16_continuation as continuation
            continuation.guard_material(ctx,obj)
        elif dep['kind']=='w16sourcegrant':
            from . import waves16_continuation as continuation
            if obj.get('status')!='active': error('The committed result is no longer available.',409)
            continuation.valid_ref(obj['ref'])
            continuation.active_session(obj['targetSessionId'])
            current(ctx,find(F,obj['formatId'],sid))
        elif dep['kind']=='w15continuationconsent':
            c=find(C,obj['contributionId'],sid); current(ctx,c); current(ctx,find(F,c['formatId'],sid))
    return receipt['status'],receipt['result']

def _dependencies(result,sid):
    found=[]
    kinds={'format':F,'contribution':C,'consent':'w15continuationconsent','transfer':T,'grant':'w16sourcegrant','work':'w16work','material':'p10material'}
    for name,kind in kinds.items():
        obj=result.get(name)
        if isinstance(obj,dict) and isinstance(obj.get('id'),str) and type(obj.get('_revision')) is int:
            found.append(dict(kind=kind,id=obj['id'],sid=sid if kind!=T else obj.get('sourceSessionId',sid),revision=obj['_revision'],status=obj.get('status')))
    transfer=result.get('transfer')
    if isinstance(transfer,dict) and transfer.get('status')=='accepted':
        target=transfer.get('targetSessionId')
        for oid in transfer.get('contributionMapping',{}).values():
            obj=store.get(C,oid,target)
            if not obj: error('The committed result is no longer available.',409)
            found.append(dict(kind=C,id=oid,sid=target,revision=obj['_revision'],status=obj.get('status')))
    return found

class _Body:
    def __init__(self,handler,body): self._handler=handler; self._body=body
    def body(self): return self._body
    def __getattr__(self,name): return getattr(self._handler,name)

def handle(handler,sid,actor,method,parts):
    with store.LOCK:
        ctx=Context(handler,sid,actor); ctx.check_actor()
        if len(parts)==3 and parts[0]=='formats' and parts[1]=='receipts' and method=='GET':
            key=_key(parts[2]); rec=store.get(RECEIPT,_receipt_id(sid,actor,key),sid)
            if not rec: return 200,{'receipt':{'requestId':key,'state':'unknown'}}
            return 200,{'receipt':{'requestId':key,'state':'committed','operation':rec['operation'],'status':rec['status']}}
        if method not in ('POST','PATCH','DELETE'): return _handle(handler,sid,actor,method,parts)
        body=handler.body()
        if not isinstance(body,dict) or 'mutationRequestId' not in body: return _handle(_Body(handler,body),sid,actor,method,parts)
        body=dict(body); key=_key(body.pop('mutationRequestId'))
        operation=method+' /'+'/'.join(parts)
        fingerprint=hashlib.sha256(json.dumps([operation,body],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        with _store.connect() as db:
            db.execute('BEGIN IMMEDIATE'); store.local.db=db
            try:
                ctx.check_actor()
                oid=_receipt_id(sid,actor,key); rec=store.get(RECEIPT,oid,sid)
                if rec:
                    if rec['fingerprint']!=fingerprint or rec['role']!=actor['role']: error('Mutation request ID already used.',409)
                    result=_safe_replay(ctx,sid,actor,rec); db.commit(); return result
                status,result=_handle(_Body(handler,body),sid,actor,method,parts)
                rec=dict(operation=operation,role=actor['role'],fingerprint=fingerprint,status=status,result=result,dependencies=_dependencies(result,sid))
                store.put(RECEIPT,sid,rec,owner=actor['owner'],oid=oid)
                db.commit(); return status,result
            except BaseException:
                db.rollback(); raise
            finally: del store.local.db

def error(msg, status=400): raise Phase10Error('version_conflict' if status==409 else 'forbidden' if status==403 else 'not_found' if status==404 else 'invalid_format',msg,status)
def text(v, limit=1000, optional=False):
    if not isinstance(v,str) or len(v)>limit or (not optional and not v.strip()) or '\x00' in v: error('Invalid text.')
    return v.strip()
def fields(b, keys):
    if not isinstance(b,dict) or set(b)!=set(keys): error('Invalid fields.')
def rev(item,b):
    if type(b.get('revision')) is not int: error('Revision required.')
    if item['_revision']!=b['revision']: error('The item changed.',409)
def creator(a):
    if a['role']!='creator': error('Creator access required.',403)
def owner(kind, oid, sid, actor):
    with store.connect() as db: row=db.execute('SELECT owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',(kind,oid,sid)).fetchone()
    if not row or row['owner_id']!=actor['owner']: error('Only the author can change this contribution.',403)
def references(ctx, refs):
    if not isinstance(refs,list) or len(refs)>20: error('Invalid source references.')
    if refs:
        rows=ctx.resolve(refs)
        if any(not x['source'].get('audienceVisible') for x in rows): error('Source unavailable.',409)
def definition(b):
    fields(b,('type','title','question','options','cards','refs'))
    typ=b['type']; title=text(b['title'],160); question=text(b['question'],500)
    if typ not in ('choice','structured_board'): error('Unknown format type.')
    if not isinstance(b['options'],list) or not isinstance(b['cards'],list): error('Invalid finite items.')
    options=b['options']; cards=b['cards']
    if typ=='choice':
        if not 2<=len(options)<=20 or cards: error('Choice requires 2 to 20 options.')
        options=[text(x,160) for x in options]
        if len(set(options))!=len(options): error('Options must be distinct.')
    else:
        if options or not 1<=len(cards)<=30: error('Board requires 1 to 30 proposal cards.')
        cards=[text(x,300) for x in cards]
        if len(set(cards))!=len(cards): error('Cards must be distinct.')
    return dict(type=typ,title=title,question=question,options=options,cards=cards,refs=b['refs'])
def contribution(b,fmt,ctx):
    fields(b,('selection','reason','alternative','refs','consent','formatRevision','idempotencyKey'))
    if b['consent'] is not True: error('Explicit sharing consent required.')
    if type(b['formatRevision']) is not int or b['formatRevision']!=fmt['_revision']: error('The format changed.',409)
    selected=text(b['selection'],300); allowed=fmt['options'] if fmt['type']=='choice' else fmt['cards']
    if selected not in allowed: error('Select a current finite item.')
    reason=text(b['reason'],2000,True); alternative=text(b['alternative'],1000,True)
    if fmt['type']=='choice' and alternative: error('Alternative applies to boards.')
    references(ctx,b['refs'])
    key=b['idempotencyKey']
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',key): error('Invalid idempotency key.')
    return dict(selection=selected,reason=reason,alternative=alternative,refs=b['refs'])
def current(ctx,item):
    if item.get('templateRoundId') and item.get('templateImportTransferId'):
        from . import waves17_templates
        waves17_templates.validate_import(item['templateImportTransferId'])
    from . import waves16_continuation as continuation
    if item.get('type') in ('choice','structured_board'):
        continuation.guard_format(ctx,item)
    elif item.get('formatId'):
        continuation.guard_contribution(ctx,item)
    references(ctx,item.get('refs',[]))
def find(kind,oid,sid):
    item=store.get(kind,oid,sid)
    if not item: error('Item unavailable.',404)
    return item
def contribution_view(c, actor):
    # Identity is evaluated for each caller, never persisted as an actor-relative flag.
    result = {k:v for k,v in c.items() if k not in ('requestKey', 'fingerprint')}
    result['isMine'] = c.get('authorId') == actor['owner']
    result['canEdit'] = result['isMine'] and c.get('status') != 'withdrawn'
    return result

def projection(ctx, fmt, sid, actor):
    current(ctx,fmt); contributions=[]
    for c in store.all(C,sid):
        if c['formatId']!=fmt['id'] or c['status']=='withdrawn': continue
        try: current(ctx,c)
        except Phase10Error: continue
        if actor['role']=='creator' or c['status']=='accepted' or c['authorId']==actor['owner']: contributions.append(contribution_view(c,actor))
    active={c['id'] for c in contributions if c['status']=='accepted'}
    decision=fmt.get('decision')
    if decision:
        # A decision must never silently lose a cited reason or minority.
        if not set(decision['reasonIds']) <= active or not set(decision['minorityIds']) <= active:
            decision=None
    result=dict(fmt,decision=decision)
    if fmt.get('templateRoundId'):
        from . import waves17_templates
        result,contributions=waves17_templates.project(ctx,result,contributions,actor)
    return result,contributions

def stage_guard(fmt,action):
    if fmt.get('templateRoundId'):
        from . import waves17_templates
        waves17_templates.guard(fmt,action)

def _continuation_route(method,parts):
    return (len(parts)>=3 and parts[0]=='formats' and parts[2] in ('work','source-grants','transfer')) or (len(parts)==3 and parts[0]=='format-transfers' and parts[2] in ('preview','accept','decline','withdraw'))

def _handle(handler,sid,actor,method,parts):
  with store.LOCK:
    ctx=Context(handler,sid,actor);ctx.check_actor()
    if _continuation_route(method,parts):
        from . import waves16_continuation as continuation
        result=continuation.handle(ctx,method,parts,handler.body() if method in ('POST','PATCH','DELETE') else None)
        if result is not None: return result
    if len(parts)==3 and parts[0]=='format-contributions' and parts[2]=='continuation-consent' and method=='GET':
        c=find(C,parts[1],sid); owner(C,c['id'],sid,actor); current(ctx,c)
        grants=[{'id':g['id'],'revision':g['_revision'],'targetSessionId':g['targetSessionId'],'contributionRevision':g['contributionRevision'],'status':g['status']} for g in store.all('w15continuationconsent',sid) if g.get('contributionId')==c['id']]
        return 200,{'consents':grants}
    if parts==['formats'] and method=='GET':
        formats=[]; contributions=[]
        for fmt in store.all(F,sid):
            try: f,cs=projection(ctx,fmt,sid,actor)
            except Phase10Error: continue
            formats.append(f);contributions.extend(cs)
        return 200,{'formats':formats,'contributions':contributions}
    if parts==['formats'] and method=='POST':
        creator(actor); b=handler.body(); d=definition(b);references(ctx,d['refs']);d['decision']=None
        obj=store.put(F,sid,d,owner=actor['owner']);return 201,{'format':find(F,obj['id'],sid)}
    if len(parts)==2 and parts[0]=='formats' and method=='PATCH':
        creator(actor);fmt=find(F,parts[1],sid);current(ctx,fmt);stage_guard(fmt,'edit');b=handler.body();
        if not isinstance(b,dict) or 'revision' not in b: error('Revision required.')
        rev(fmt,b);d=definition({k:v for k,v in b.items() if k!='revision'});references(ctx,d['refs'])
        if d['type']!=fmt['type']: error('Format type cannot change.')
        fmt.update(d);fmt['decision']=None;return 200,{'format':store.save(F,fmt,revision=b['revision'])}
    if len(parts)==3 and parts[0]=='formats' and parts[2]=='contributions' and method=='POST':
        fmt=find(F,parts[1],sid);current(ctx,fmt);stage_guard(fmt,'contribute');b=handler.body();d=contribution(b,fmt,ctx)
        fp=hashlib.sha256(json.dumps(b,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        for old in store.all(C,sid):
            if old.get('authorId')==actor['owner'] and old.get('requestKey')==b['idempotencyKey']:
                if old['fingerprint']!=fp: error('Request key already used.',409)
                if old['status']=='withdrawn': error('Contribution withdrawn.',409)
                current(ctx,old)
                return 200,{'contribution':contribution_view(old,actor)}
        d.update(formatId=fmt['id'],authorId=actor['owner'],status='pending',requestKey=b['idempotencyKey'],fingerprint=fp)
        obj=store.put(C,sid,d,owner=actor['owner']);return 201,{'contribution':contribution_view(find(C,obj['id'],sid),actor)}
    if len(parts)==2 and parts[0]=='format-contributions' and method in ('PATCH','DELETE'):
        c=find(C,parts[1],sid);owner(C,c['id'],sid,actor);fmt=find(F,c['formatId'],sid)
        if method!='DELETE' or not fmt.get('templateRoundId'):
            current(ctx,c);stage_guard(fmt,'contribute')
        b=handler.body();rev(c,b)
        if c['status']=='withdrawn': error('Contribution unavailable.',404)
        if method=='DELETE':
            fields(b,('revision',));c.update(status='withdrawn',selection=None,reason=None,alternative=None,refs=[])
        else:
            fields(b,('revision','selection','reason','alternative','refs','consent','formatRevision','idempotencyKey'))
            fmt=find(F,c['formatId'],sid);current(ctx,fmt);d=contribution({k:v for k,v in b.items() if k!='revision'},fmt,ctx);c.update(d,status='pending')
        return 200,{'contribution':contribution_view(store.save(C,c,revision=b['revision']),actor)}
    if len(parts)==3 and parts[0]=='format-contributions' and parts[2]=='continuation-consent' and method=='POST':
        c=find(C,parts[1],sid);owner(C,c['id'],sid,actor);b=handler.body()
        fields(b,('revision','targetSessionId','allow'));rev(c,b)
        if type(b['allow']) is not bool: error('An explicit consent choice is required.')
        target=store.get('session',b['targetSessionId']) if isinstance(b['targetSessionId'],str) else None
        if not target or not lifecycle.active(target) or target['id']==sid: error('Target unavailable.',404)
        if c['status']=='withdrawn': error('Contribution unavailable.',404)
        current(ctx,c)
        grants=[g for g in store.all('w15continuationconsent',sid) if g.get('contributionId')==c['id'] and g.get('targetSessionId')==target['id'] and g.get('status')=='active']
        for grant in grants:
            grant['status']='revoked';store.save('w15continuationconsent',grant)
        grant=store.put('w15continuationconsent',sid,{'contributionId':c['id'],'contributionRevision':c['_revision'],'targetSessionId':target['id'],'status':'active' if b['allow'] else 'revoked'},owner=actor['owner'])
        return 200,{'consent':find('w15continuationconsent',grant['id'],sid)}
    if len(parts)==3 and parts[0]=='format-contributions' and parts[2]=='accept' and method=='POST':
        creator(actor);c=find(C,parts[1],sid);b=handler.body();fields(b,('revision','formatRevision'));rev(c,b);fmt=find(F,c['formatId'],sid);current(ctx,fmt);current(ctx,c)
        stage_guard(fmt,'accept')
        if type(b['formatRevision']) is not int or b['formatRevision']!=fmt['_revision']: error('The format changed.',409)
        if c['status']!='pending' or c['selection'] not in (fmt['options'] if fmt['type']=='choice' else fmt['cards']): error('Contribution unavailable.',409)
        c['status']='accepted';return 200,{'contribution':contribution_view(store.save(C,c,revision=b['revision']),actor)}
    if len(parts)==3 and parts[0]=='formats' and parts[2]=='decision' and method=='POST':
        creator(actor);fmt=find(F,parts[1],sid);b=handler.body();fields(b,('revision','reasonIds','minorityIds','decision','consequence'));rev(fmt,b);current(ctx,fmt);stage_guard(fmt,'decide')
        for k in ('reasonIds','minorityIds'):
            if not isinstance(b[k],list) or len(b[k])>50 or any(not isinstance(i,str) for i in b[k]) or len(set(b[k]))!=len(b[k]): error('Invalid contribution references.')
        if not set(b['minorityIds'])<=set(b['reasonIds']): error('Minorities must reference selected reasons.')
        for oid in b['reasonIds']:
            c=find(C,oid,sid)
            if c['formatId']!=fmt['id'] or c['status']!='accepted': error('Accepted contribution required.',409)
            current(ctx,c)
        fmt['decision']={'reasonIds':b['reasonIds'],'minorityIds':b['minorityIds'],'decision':text(b['decision'],2000),'consequence':text(b['consequence'],2000)}
        return 200,{'format':store.save(F,fmt,revision=b['revision'])}
    if parts==['format-transfers'] and method=='GET':
        creator(actor)
        with store.connect() as db: rows=db.execute('SELECT data,revision FROM objects WHERE kind=?',(T,)).fetchall()
        offers=[dict(json.loads(row['data']),_revision=row['revision']) for row in rows]
        visible=[]
        from . import waves16_continuation as continuation
        for o in offers:
            if sid not in (o.get('targetSessionId'),o.get('sourceSessionId')): continue
            try: continuation.validate_offer(o)
            except Phase10Error: continue
            visible.append(o)
        return 200,{'transfers':visible}
    if len(parts)==3 and parts[0]=='formats' and parts[2]=='transfer' and method=='POST':
        creator(actor);fmt=find(F,parts[1],sid);b=handler.body();fields(b,('revision','targetSessionId'));rev(fmt,b);current(ctx,fmt)
        error('Reviewed and consented continuation is not available yet.',409)
    if len(parts)==3 and parts[0]=='format-transfers' and parts[2] in ('accept','decline','withdraw') and method=='POST':
        creator(actor);offer=store.get(T,parts[1]); action=parts[2];b=handler.body();fields(b,('revision',))
        if not offer or offer['status']!='offered' or offer['sourceSessionId' if action=='withdraw' else 'targetSessionId']!=sid: error('Transfer unavailable.',404)
        rev(offer,b)
        if action!='accept': offer['status']='declined' if action=='decline' else 'withdrawn';return 200,{'transfer':store.save(T,offer,revision=b['revision'])}
        error('This transfer does not contain reviewed, consented continuation.',409)
    raise Phase10Error('not_found','Format route unavailable.',404)
