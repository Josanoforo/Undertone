"""Creator-controlled, source-bound assistance. No provider, scheduler or router."""
import hashlib, json, re, time
from . import store
from .phase10_common import Context, Phase10Error

KIND='w18assist'; RECEIPT='w18assistreceipt'
def canonical(v): return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(v): return hashlib.sha256(canonical(v).encode('utf-8')).hexdigest()
def fail(code,msg,status=409): raise Phase10Error(code,msg,status)
def ident(v): return isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',v) is not None
def txt(v,limit):
    if not isinstance(v,str) or not v.strip() or len(v)>limit or any(ord(c)<32 and c not in '\n\r\t' for c in v): fail('invalid_request','Invalid text.',422)
    try: v.encode('utf-8')
    except UnicodeEncodeError: fail('invalid_request','Invalid text.',422)
    return v.strip()
def read(db,kind,oid,sid):
    row=db.execute('SELECT data,revision FROM objects WHERE kind=? AND id=? AND session_id=?',(kind,oid,sid)).fetchone()
    return dict(json.loads(row['data']),_revision=row['revision']) if row else None
def write(db,kind,oid,sid,owner,value,revision):
    value=dict(value); value.pop('_revision',None); value['id']=oid
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data,revision=excluded.revision',(kind,oid,sid,owner,revision,canonical(value),store.now()))
    return dict(value,_revision=revision)
def authority(ctx):
    ctx.check_actor()
    if ctx.actor.get('sid')!=ctx.sid: fail('not_found','Session unavailable.',404)
    if ctx.actor.get('role')!='creator': fail('forbidden','Creator capability required.',403)
def rows(ctx,refs):
    if not isinstance(refs,list) or not refs or any(not isinstance(r,dict) or r.get('sessionId')!=ctx.sid for r in refs): fail('invalid_refs','Select local source moments.',422)
    result=ctx.resolve(refs)
    if any(not r['source'].get('audienceVisible',False) for r in result): fail('stale_context','Source is not shared.',409)
    return result

def signals(ctx,items):
    if not isinstance(items,list) or len(items)>5: fail('invalid_request','Invalid shared signals.',422)
    texts=[]; seen=set()
    for item in items:
        if not isinstance(item,dict) or set(item)!={'kind','id','revision'} or item['kind'] not in ('question','contribution') or not ident(item['id']) or type(item['revision']) is not int or item['revision']<1: fail('invalid_request','Invalid shared signal.',422)
        key=(item['kind'],item['id'])
        if key in seen: fail('invalid_request','Duplicate signal.',422)
        seen.add(key)
        kind='w13question' if item['kind']=='question' else 'w15formatcontribution'
        obj=store.get(kind,item['id'],ctx.sid)
        if not obj or obj['_revision']!=item['revision'] or obj.get('status')=='withdrawn': fail('stale_context','Shared signal unavailable.')
        if item['kind']=='question':
            from . import waves13_exchange
            if obj.get('status') not in ('shared','selected') or not waves13_exchange.eligible(ctx.handler,ctx.sid,ctx.actor,obj): fail('stale_context','Shared question unavailable.')
            if obj.get('ref'): rows(ctx,[obj['ref']])
            texts.append('Shared question: '+str(obj.get('text',''))[:1000])
        else:
            from . import waves15_formats as f
            if obj.get('status') not in ('pending','accepted'): fail('stale_context','Contribution unavailable.')
            f.current(ctx,obj); fmt=store.get(f.F,obj.get('formatId'),ctx.sid)
            if not fmt: fail('stale_context','Contribution format unavailable.')
            f.current(ctx,fmt)
            texts.append('Consented contribution: '+str(obj.get('selection',''))[:300]+' '+str(obj.get('reason',''))[:1000])
    return texts

def check_candidate(ctx,c):
    rows(ctx,c['refs']); signals(ctx,c.get('signals',[]))
def guard_material(ctx,material):
    """Call before every material projection, edit, approval and current delivery."""
    binding=material.get('w18Assistance')
    if binding is None: return
    if not isinstance(binding,dict) or binding.get('sessionId')!=ctx.sid or material.get('refs')!=binding.get('refs'): fail('stale_context','Assistance dependencies changed.')
    rows(ctx,binding['refs']); signals(ctx,binding.get('signals',[]))

def guard_delivery(sid, material):
    """Recheck persisted assistance lineage without assuming a caller capability."""
    with store.LOCK:
        if 'w18Assistance' not in material: return True
        from . import waves16_continuation as continuation, waves15_formats as formats
        b=material.get('w18Assistance')
        if not isinstance(b,dict) or set(b)!={'sessionId','candidateId','refs','signals'} or b.get('sessionId')!=sid or material.get('refs')!=b.get('refs') or store.get('p10material',material.get('id'),sid)!=material:
            fail('stale_context','Assistance dependencies changed.')
        continuation.active_session(sid)
        matches=[c for state in store.all(KIND,sid) for c in state.get('candidates',[]) if c.get('id')==b['candidateId'] and c.get('state')=='accepted' and c.get('materialId')==material.get('id') and c.get('refs')==b['refs'] and c.get('signals',[])==b['signals']]
        if len(matches)!=1 or not isinstance(b['refs'],list) or not b['refs'] or not isinstance(b['signals'],list) or len(b['signals'])>5: fail('stale_context','Assistance dependencies changed.')
        for ref in b['refs']:
            if not isinstance(ref,dict) or ref.get('sessionId')!=sid: fail('stale_context','Source unavailable.')
            continuation.valid_ref(ref)
        seen=set()
        for item in b['signals']:
            if not isinstance(item,dict) or set(item)!={'kind','id','revision'} or item.get('kind') not in ('question','contribution') or not ident(item.get('id')) or type(item.get('revision')) is not int or item['revision']<1: fail('stale_context','Signal unavailable.')
            key=(item['kind'],item['id'])
            if key in seen: fail('stale_context','Signal unavailable.')
            seen.add(key)
            obj=store.get('w13question' if item['kind']=='question' else formats.C,item['id'],sid)
            if not obj or obj['_revision']!=item['revision']: fail('stale_context','Signal unavailable.')
            if item['kind']=='question':
                if obj.get('status') not in ('shared','selected'): fail('stale_context','Question unavailable.')
                if obj.get('ref'):
                    ref=obj['ref']
                    if not isinstance(ref,dict) or ref.get('sessionId')!=sid or continuation.valid_ref(ref)['source'].get('p10Provenance',{}).get('type')!='received_asr_v1': fail('stale_context','Question unavailable.')
            else:
                if obj.get('status') not in ('pending','accepted'): fail('stale_context','Contribution unavailable.')
                fmt=store.get(formats.F,obj.get('formatId'),sid)
                if not fmt: fail('stale_context','Format unavailable.')
                tid=fmt.get('continuationTransferId'); permitted=[]
                if tid:
                    offer=store.get(continuation.T,tid)
                    if not offer or offer.get('targetSessionId')!=sid or offer.get('recipientFormatId')!=fmt.get('id'): fail('stale_context','Format unavailable.')
                    snap=continuation.validate_offer(offer,('accepted',)); permitted=[x['ref'] for x in snap['refs']]
                if obj.get('continuationTransferId') and obj.get('continuationTransferId')!=tid: fail('stale_context','Contribution unavailable.')
                for ref in fmt.get('refs',[])+obj.get('refs',[]):
                    if not isinstance(ref,dict) or (ref.get('sessionId')!=sid and ref not in permitted): fail('stale_context','Source unavailable.')
                    continuation.valid_ref(ref)
                if fmt.get('templateRoundId') and fmt.get('templateImportTransferId'):
                    from . import waves17_templates
                    waves17_templates.validate_import(fmt['templateImportTransferId'])
        return True


def policy_identity(p): return digest([p['objective'],p['allowedKinds']])

def project(ctx,state):
    result=dict(state); result['candidates']=[]
    for original in state.get('candidates',[]):
        item=dict(original)
        try:
            if item['state'] in ('pending','deferred') and item['policyIdentity']!=policy_identity(state['policy']): fail('stale_context','Policy changed.')
            check_candidate(ctx,item)
        except Phase10Error:
            item={k:item[k] for k in ('id','state','createdAt') if k in item}; item['state']='stale'
        result['candidates'].append(item)
    return result

def policy(v):
    keys={'objective','allowedKinds','cooldownSeconds','maxPerHour','queueLimit','quiet'}
    if not isinstance(v,dict) or set(v)!=keys: fail('invalid_request','Invalid assistance policy.',422)
    objective=txt(v['objective'],1000); kinds=v['allowedKinds']
    if not isinstance(kinds,list) or len(kinds)>1 or any(k!='source_excerpt' for k in kinds): fail('invalid_request','Invalid intervention kinds.',422)
    for key,lo,hi in [('cooldownSeconds',0,86400),('maxPerHour',1,60),('queueLimit',1,20)]:
        if type(v[key]) is not int or not lo<=v[key]<=hi: fail('invalid_request','Invalid policy limit.',422)
    if type(v['quiet']) is not bool: fail('invalid_request','Invalid quiet setting.',422)
    return dict(v,objective=objective)

def handle(handler,sid,actor,method,parts):
    ctx=Context(handler,sid,actor); authority(ctx)
    if len(parts)<2 or parts[0]!='assistance' or not ident(parts[1]): fail('not_found','Assistance route unavailable.',404)
    context_id=parts[1]; oid=digest([sid,context_id]); path=parts[2:]
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE'); authority(ctx)
        state=read(db,KIND,oid,sid)
        if state and state['creatorId']!=actor['owner']: fail('not_found','Assistance unavailable.',404)
        if method=='GET' and not path:
            db.commit(); return 200,{'assistance':project(ctx,state) if state else None}
        if method!='POST': fail('not_found','Assistance route unavailable.',404)
        b=handler.body()
        if not isinstance(b,dict) or not ident(b.get('requestId')) or type(b.get('expectedRevision')) is not int or b['expectedRevision']<0: fail('invalid_request','Request ID and revision required.',422)
        rid=digest([sid,actor['owner'],b['requestId']]); fp=digest([parts,b]); receipt=read(db,RECEIPT,rid,sid)
        if receipt:
            if receipt['fingerprint']!=fp: fail('request_conflict','Request ID already used.')
            current=read(db,KIND,oid,sid)
            if not current or current['_revision']!=receipt['revision']: fail('stale_receipt','Committed result has changed.')
            # Never replay a draft after its source has changed or disappeared.
            for c in current['candidates']:
                if c['id'] in receipt.get('candidateIds',[]): check_candidate(ctx,c)
            material_id=receipt.get('extra',{}).get('materialId')
            if material_id:
                material=read(db,'p10material',material_id,sid)
                if not material or material['_revision']!=1: fail('stale_receipt','Committed material changed.')
                guard_material(ctx,material)
            result=project(ctx,current); db.commit(); return receipt['status'],{'assistance':result,**receipt.get('extra',{})}
        revision=state['_revision'] if state else 0
        if b['expectedRevision']!=revision: fail('stale_revision','Assistance changed.')
        if db.execute('SELECT COUNT(*) FROM objects WHERE kind=? AND session_id=?',(RECEIPT,sid)).fetchone()[0]>=4096: fail('receipt_capacity','Assistance receipt capacity reached.',429)
        now=int(time.time()); extra={}; touched=[]; status=200
        if path==['policy']:
            if set(b)!={'requestId','expectedRevision','policy'}: fail('invalid_request','Invalid fields.',422)
            p=policy(b['policy'])
            if not state: state={'creatorId':actor['owner'],'contextId':context_id,'candidates':[],'emissions':[]}
            state['policy']=p
        elif path==['candidates']:
            if set(b) not in ({'requestId','expectedRevision','kind','refs'},{'requestId','expectedRevision','kind','refs','signals'}) or not state: fail('invalid_request','Policy and candidate fields required.',422)
            p=state['policy']
            if p['quiet']: fail('quiet','Assistance is quiet.')
            if b['kind'] not in p['allowedKinds']: fail('not_allowed','Intervention is not enabled.')
            selected=rows(ctx,b['refs']); signal_items=b.get('signals',[]); signal_text=signals(ctx,signal_items); identity=digest([policy_identity(p),b['kind'],b['refs'],signal_items])
            if any(c['identity']==identity for c in state['candidates']): fail('duplicate','This context already has a candidate.')
            active=[]
            for c in state['candidates']:
                if c['state'] in ('pending','deferred'):
                    try:
                        if c['policyIdentity']!=policy_identity(p): fail('stale_context','Policy changed.')
                        check_candidate(ctx,c); active.append(c)
                    except Phase10Error: pass
            if len(active)>=p['queueLimit']: fail('queue_full','Assistance queue is full.')
            emissions=[t for t in state['emissions'] if now-t<3600 and t<=now]
            if state['emissions'] and now-state['emissions'][-1]<p['cooldownSeconds']: fail('cooldown','Assistance is cooling down.')
            if len(emissions)>=p['maxPerHour']: fail('frequency_limit','Assistance frequency limit reached.')
            if len(state['candidates'])>=200: fail('candidate_capacity','Assistance history is full.',429)
            excerpt=str(selected[0]['moment'].get('text','')).strip()
            if not excerpt: fail('no_signal','Selected moment has no text.')
            candidate={'id':store.ident(),'identity':identity,'policyIdentity':policy_identity(p),'kind':b['kind'],'refs':b['refs'],'signals':signal_items,'state':'pending','createdAt':now,'rationale':'Selected source moment for the creator objective.','draft':{'title':'Source excerpt for review','body':excerpt[:4000]+(('\n\n'+'\n'.join(signal_text)) if signal_text else '')},'feedback':None}
            state['candidates'].append(candidate); state['emissions']=emissions+[now]; touched=[candidate['id']]; status=201
        elif len(path)==3 and path[0]=='candidates' and path[2]=='feedback':
            if set(b)!={'requestId','expectedRevision','action','title','body'} or not state: fail('invalid_request','Invalid feedback.',422)
            c=next((x for x in state['candidates'] if x['id']==path[1]),None)
            if not c or c['state'] not in ('pending','deferred'): fail('not_found','Candidate unavailable.',404)
            action=b['action']
            if action not in ('dismiss','defer','accept'): fail('invalid_request','Invalid feedback action.',422)
            if action!='accept' and (b['title'] is not None or b['body'] is not None): fail('invalid_request','Unexpected draft fields.',422)
            if action=='accept':
                if c['policyIdentity']!=policy_identity(state['policy']): fail('stale_context','Policy changed.')
                check_candidate(ctx,c); title=txt(b['title'],200); body=txt(b['body'],12000)
                mid=store.ident(); binding={'sessionId':sid,'candidateId':c['id'],'refs':c['refs'],'signals':c.get('signals',[])}
                material={'format':'explanation','currentVersion':1,'title':title,'body':body,'refs':c['refs'],'status':'draft','approvedVersion':None,'provider':'deterministic','model':None,'versions':[{'number':1,'title':title,'body':body,'refs':c['refs']}],'w18Assistance':binding}
                write(db,'p10material',mid,sid,actor['owner'],material,1); c['materialId']=mid; touched=[c['id']]; extra={'materialId':mid}
            c['state']={'dismiss':'dismissed','defer':'deferred','accept':'accepted'}[action]; c['feedback']=action
        else: fail('not_found','Assistance route unavailable.',404)
        state=write(db,KIND,oid,sid,actor['owner'],state,revision+1)
        write(db,RECEIPT,rid,sid,actor['owner'],{'fingerprint':fp,'revision':revision+1,'status':status,'candidateIds':touched,'extra':extra},1)
        result=project(ctx,state); db.commit(); return status,{'assistance':result,**extra}



