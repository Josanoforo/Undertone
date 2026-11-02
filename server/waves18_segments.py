"""Creator segment workspace over existing editorial and cue handlers.

Delivery remains disabled until the host wires guard_delivery at every documented
boundary and explicitly enables DELIVERY_GUARDS_WIRED in its integration.
"""
import hashlib, json, os, re
from . import store, waves13_exchange, waves15_formats, waves15_cues, phase10_studio, waves16_continuation
from .phase10_common import Context, Phase10Error

SEG='w18segment'; REC='w18segmentreceipt'; DELIVERY_GUARDS_WIRED=False
ACTIONS=('select','compose','edit','approve','prepare_cue','present','defer','withdraw_cue','close')
def fail(code,msg,status=409): raise Phase10Error(code,msg,status)
def canon(x): return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(x): return hashlib.sha256(canon(x).encode()).hexdigest()
def key(x):
    if not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',x): fail('invalid_request','Invalid request ID.',422)
    return x
def text(x,n):
    if not isinstance(x,str) or not x.strip() or len(x)>n or '\x00' in x: fail('invalid_request','Invalid text.',422)
    return x.strip()
def read(db,kind,oid,sid):
    row=db.execute('SELECT data,revision FROM objects WHERE kind=? AND id=? AND session_id=?',(kind,oid,sid)).fetchone()
    return dict(json.loads(row['data']),_revision=row['revision']) if row else None
def put(db,kind,oid,sid,owner,value,revision=1):
    value=dict(value); value.pop('_revision',None); value['id']=oid
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',(kind,oid,sid,owner,revision,canon(value),store.now()))
    return dict(value,_revision=revision)
def save(db,kind,obj,sid):
    obj=dict(obj); rev=obj.pop('_revision'); oid=obj['id']
    changed=db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=? AND revision=?',(canon(obj),rev+1,kind,oid,sid,rev)).rowcount
    if changed!=1: fail('version_conflict','The item changed.')
    return dict(obj,_revision=rev+1)
def authority(ctx):
    ctx.check_actor()
    if ctx.actor.get('sid')!=ctx.sid or ctx.actor.get('role')!='creator': fail('forbidden','Creator access required.',403)
def refs_current(sid,refs):
    if not isinstance(refs,list) or not refs or len(refs)>20: fail('invalid_request','Select one or more source moments.',422)
    for ref in refs:
        if not isinstance(ref,dict) or ref.get('sessionId')!=sid: fail('stale_context','Source unavailable.')
        waves16_continuation.valid_ref(ref)
def signals_current(sid,signals):
    if not isinstance(signals,list) or len(signals)>20: fail('invalid_request','Invalid selections.',422)
    seen=set()
    for item in signals:
        if not isinstance(item,dict) or set(item)!={'kind','id','revision'} or item['kind'] not in ('question','contribution') or not isinstance(item['id'],str) or type(item['revision']) is not int: fail('invalid_request','Invalid selection.',422)
        tag=(item['kind'],item['id'])
        if tag in seen: fail('invalid_request','Duplicate selection.',422)
        seen.add(tag)
        kind='w13question' if item['kind']=='question' else waves15_formats.C
        obj=store.get(kind,item['id'],sid)
        if not obj or obj['_revision']!=item['revision']: fail('stale_context','Selected contribution unavailable.')
        if item['kind']=='question':
            if obj.get('status') not in ('shared','selected'): fail('stale_context','Selected question unavailable.')
            if obj.get('ref'):
                row=waves16_continuation.valid_ref(obj['ref'])
                if row['source'].get('p10Provenance',{}).get('type')!='received_asr_v1': fail('stale_context','Selected question unavailable.')
        else:
            if obj.get('status')!='accepted': fail('stale_context','Selected contribution unavailable.')
            fmt=store.get(waves15_formats.F,obj.get('formatId'),sid)
            if not fmt: fail('stale_context','Format unavailable.')
            # Existing continuation guards are actor independent at the lineage boundary.
            if fmt.get('continuationTransferId'):
                offer=store.get(waves16_continuation.T,fmt['continuationTransferId'])
                if not offer or offer.get('targetSessionId')!=sid: fail('stale_context','Format unavailable.')
                waves16_continuation.validate_offer(offer,('accepted',))
            if obj.get('continuationTransferId') != fmt.get('continuationTransferId'): fail('stale_context','Contribution lineage changed.')
            for ref in fmt.get('refs',[])+obj.get('refs',[]): waves16_continuation.valid_ref(ref)
            if fmt.get('templateRoundId') and fmt.get('templateImportTransferId'):
                from . import waves17_templates
                waves17_templates.validate_import(fmt['templateImportTransferId'])
def guard_delivery(sid,material):
    """Fail closed for marked segment material; no fabricated actor."""
    with store.LOCK:
        if 'w18Segment' not in material: return True
        b=material.get('w18Segment')
        if not isinstance(b,dict) or b.get('sessionId')!=sid: fail('stale_context','Segment material unavailable.')
        live=store.get('p10material',material.get('id'),sid)
        segment=store.get(SEG,b.get('segmentId'),sid)
        if live!=material or not segment or segment.get('materialId')!=material.get('id') or segment.get('binding')!=b or material.get('refs')!=b.get('refs'): fail('stale_context','Segment material unavailable.')
        refs_current(sid,b['refs']); signals_current(sid,b['signals'])
        for dep in b.get('formats',[]):
            fmt=store.get(waves15_formats.F,dep['id'],sid)
            if not fmt or fmt['_revision']!=dep['revision']: fail('stale_context','Participation changed.')
        return True
def guard_material(ctx,material):
    ctx.check_actor(); return guard_delivery(ctx.sid,material)

def prepare_bound_replacement(ctx, db, material, object_revision, segment_revision,
                              version, title, body, refs):
    """Prepare a W21 draft and update its segment in the caller's transaction.

    Caller holds store.LOCK and an IMMEDIATE transaction, and owns validation
    and CAS of the W21 intent, fence, material and receipt. Any subsequent
    failure must roll back this transaction. This function never commits.
    """
    import copy
    authority(ctx)
    if not db.in_transaction:
        fail('invalid_transition','A replacement transaction is required.')
    if any(k in material for k in ('continuationWorkId','continuationTransferId','w18Assistance')):
        fail('stale_context','Bound material requires its own editor.')
    binding=material.get('w18Segment')
    if not isinstance(binding,dict) or binding.get('sessionId')!=ctx.sid:
        fail('stale_context','Segment material unavailable.')
    row=db.execute("SELECT owner_id,revision,data FROM objects WHERE kind='p10material' AND id=? AND session_id=?",(material.get('id'),ctx.sid)).fetchone()
    if (not row or row['owner_id']!=ctx.actor['owner'] or type(object_revision) is not int
            or row['revision']!=object_revision or json.loads(row['data'])!=material
            or type(version) is not int or material.get('currentVersion')!=version):
        fail('version_conflict','The material changed.')
    s=read(db,SEG,binding.get('segmentId'),ctx.sid)
    if (not s or s.get('creatorId')!=ctx.actor['owner'] or type(segment_revision) is not int
            or s['_revision']!=segment_revision or s.get('state')!='open'
            or s.get('materialId')!=material.get('id') or s.get('binding')!=binding
            or s.get('refs')!=binding.get('refs') or s.get('signals')!=binding.get('signals')
            or material.get('refs')!=binding.get('refs')):
        fail('stale_context','Segment material unavailable.')
    for pending in store.all(REC,ctx.sid):
        if pending.get('segmentId')==s['id'] and pending.get('state') in ('pending','unknown'):
            fail('operation_unresolved','A previous operation needs reconciliation.')
    # A cue binds the old material version and can have independent native state.
    if s.get('cueId'):
        fail('operation_unresolved','The segment has an existing cue.')
    refs_current(ctx.sid,refs)
    phase10_studio.resolve_material_refs(ctx,refs)
    signals_current(ctx.sid,binding.get('signals'))
    for dep in binding.get('formats',[]):
        fmt=store.get(waves15_formats.F,dep.get('id'),ctx.sid)
        if not fmt or fmt['_revision']!=dep.get('revision'):
            fail('stale_context','Participation changed.')
    title=phase10_studio.text(title,200); body=phase10_studio.text(body,12000)
    updated=copy.deepcopy(material); new_binding=copy.deepcopy(binding)
    new_binding['refs']=copy.deepcopy(refs)
    updated.setdefault('versions',[]).append({'number':version+1,'title':title,'body':body,'refs':copy.deepcopy(refs)})
    updated.update(title=title,body=body,refs=copy.deepcopy(refs),currentVersion=version+1,
                   approvedVersion=None,status='draft',w18Segment=new_binding)
    s.update(refs=copy.deepcopy(refs),binding=new_binding)
    save(db,SEG,s,ctx.sid)
    return updated
def get_segment(sid,actor,oid):
    s=store.get(SEG,oid,sid)
    if not s or s.get('creatorId')!=actor['owner']: fail('not_found','Segment unavailable.',404)
    return s
def presentation_configuration(sid,actor):
    cfg=waves15_cues.configuration(sid,actor)
    if str(cfg['httpPort']) != os.environ.get('APP_PORT','8765'):
        fail('destination_unbound','The local destination is bound to a different runtime port.',503)
    # A creator/session match alone is not a usable connector configuration.
    # Reject incomplete local bindings before recording a Wave 18 intent; a
    # failure after dispatch still retains the existing unknown-effect guard.
    if (type(cfg.get('port')) is not int or not 1 <= cfg['port'] <= 65535
            or type(cfg.get('itemId')) is not int or cfg['itemId'] < 0
            or any(not isinstance(cfg.get(k), str) or not cfg[k].strip()
                   for k in ('scene','sceneUuid','profile','collection','input'))):
        fail('transport_unavailable','The local OBS destination configuration is incomplete.',503)
    try:
        from .obs_adapter import cue_password
        cue_password(cfg)
    except (OSError, KeyError, ValueError, TypeError):
        fail('transport_unavailable','The local OBS destination credential is unavailable.',503)
    return cfg
def project(ctx,s):
    out=dict(s); out.pop('binding',None)
    try:
        if s.get('refs'): refs_current(ctx.sid,s['refs']); signals_current(ctx.sid,s['signals'])
        m=store.get('p10material',s.get('materialId'),ctx.sid) if s.get('materialId') else None
        if m: guard_material(ctx,m)
        out['material']=phase10_studio._summary(ctx,m,True) if m else None
        cue=store.get('w15cue',s.get('cueId'),ctx.sid) if s.get('cueId') else None
        out['cue']=waves15_cues.projection(ctx,ctx.sid,cue) if cue else None
        out['dependencyState']='current' if s.get('refs') else 'unselected'
    except Phase10Error:
        out.update(refs=[],signals=[],material=None,cue=None,dependencyState='unavailable')
    out['deliveryGuardsWired']=DELIVERY_GUARDS_WIRED
    try:
        presentation_configuration(ctx.sid,ctx.actor)
        out['presentationTransport']={'state':'bound'}
    except Phase10Error as exc:
        out['presentationTransport']={'state':'unavailable','code':exc.code,'message':exc.message}
    return out
class Body:
    def __init__(self,handler,body): self.handler=handler; self.value=body
    def body(self): return self.value
    def __getattr__(self,name): return getattr(self.handler,name)
def options(ctx):
    # Existing projections enforce caller rights; only eligible shared content is offered.
    _,formats=waves15_formats.handle(ctx.handler,ctx.sid,ctx.actor,'GET',['formats'])
    _,questions=waves13_exchange.handle(ctx.handler,ctx.sid,ctx.actor,'GET',['questions'])
    moments=[]
    for m in store.all('p10moment',ctx.sid):
        try:
            r=waves16_continuation.valid_ref(m['ref']); moments.append({'ref':m['ref'],'title':r['source'].get('title','Source'),'text':m.get('text','')})
        except (Phase10Error,KeyError): pass
    return {'moments':moments,'questions':questions['questions'],'formats':formats['formats'],'contributions':[c for c in formats['contributions'] if c.get('status')=='accepted']}
def receipt_id(sid,actor,request): return digest([sid,actor['owner'],request])
def pending_operations(ctx,s):
    """Bounded metadata only; legacy digest-only receipts stay unresolved."""
    authority(ctx)
    rows=[]; legacy=False
    for rec in store.all(REC,ctx.sid):
        if rec.get('creatorId')!=ctx.actor['owner'] or rec.get('segmentId')!=s['id'] or rec.get('state') not in ('pending','unknown'):
            continue
        request=rec.get('requestId')
        if not isinstance(request,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',request) or receipt_id(ctx.sid,ctx.actor,request)!=rec.get('id'):
            legacy=True
            continue
        rows.append({'requestId':request,'state':rec['state'],'action':rec['action']})
    rows.sort(key=lambda x:x['requestId'])
    return {'operations':rows[:50],'incomplete':legacy or len(rows)>50}
def _handle_locked(handler,sid,actor,method,parts):
    ctx=Context(handler,sid,actor); authority(ctx)
    with store.LOCK:
        if method=='GET':
            if parts==['segments','options']: return 200,options(ctx)
            if parts==['segments']: return 200,{'segments':[project(ctx,s) for s in store.all(SEG,sid) if s.get('creatorId')==actor['owner']]}
            if len(parts)==3 and parts[0]=='segments' and parts[2]=='pending-operations':
                return 200,pending_operations(ctx,get_segment(sid,actor,parts[1]))
            if len(parts)==2 and parts[0]=='segments': return 200,{'segment':project(ctx,get_segment(sid,actor,parts[1]))}
            if len(parts)==2 and parts[0]=='segment-operations':
                rec=store.get(REC,receipt_id(sid,actor,key(parts[1])),sid)
                if rec and rec.get('creatorId')==actor['owner'] and rec.get('state') in ('pending','unknown') and rec.get('action') in ('prepare_cue','present','defer','withdraw_cue'):
                    get_segment(sid,actor,rec['segmentId'])
                    return ('reconcile',ctx,rec['id'],parts[1],rec)
                return 200,{'operation':{'requestId':parts[1],'state':rec['state'],'action':rec['action'],'segmentId':rec.get('segmentId'),'underlyingRequestId':rec.get('underlyingRequestId')} if rec and rec.get('creatorId')==actor['owner'] else {'requestId':parts[1],'state':'unknown'}}
            fail('not_found','Route unavailable.',404)
        if method!='POST': fail('not_found','Route unavailable.',404)
        body=handler.body()
        if not isinstance(body,dict): fail('invalid_request','Invalid request.',422)
        request=key(body.get('requestId')); rid=receipt_id(sid,actor,request)
        create=parts==['segments']; is_action=len(parts)==3 and parts[0]=='segments' and parts[2]=='actions'
        if not (create or is_action): fail('not_found','Route unavailable.',404)
        action='create' if create else body.get('action')
        schemas={'create':{'requestId','title'},'select':{'requestId','revision','action','refs','signals'},'compose':{'requestId','revision','action'},'edit':{'requestId','revision','action','version','title','body'},'approve':{'requestId','revision','action','version'},'prepare_cue':{'requestId','revision','action'},'present':{'requestId','revision','action'},'defer':{'requestId','revision','action'},'withdraw_cue':{'requestId','revision','action'},'close':{'requestId','revision','action'}}
        if action not in schemas or set(body)!=schemas[action]: fail('invalid_request','Invalid action fields.',422)
        fp=digest([parts,body]); old=store.get(REC,rid,sid)
        if old:
            if old['fingerprint']!=fp or old['creatorId']!=actor['owner']: fail('request_conflict','Request ID already used.')
            s=get_segment(sid,actor,old['segmentId'])
            # Readback runs after leaving the global lock, like dispatch.
            if old['state'] in ('pending','unknown') and old['action'] in ('prepare_cue','present','defer','withdraw_cue'):
                return ('reconcile',ctx,rid,request,old)
            return 200,{'operation':{'requestId':request,'state':old['state'],'action':action,'underlyingRequestId':old.get('underlyingRequestId')},'segment':project(ctx,s)}
        if create:
            title=text(body['title'],160); oid=store.ident()
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE'); authority(ctx)
                s=put(db,SEG,oid,sid,actor['owner'],{'creatorId':actor['owner'],'title':title,'state':'open','refs':[],'signals':[],'materialId':None,'cueId':None,'binding':None})
                put(db,REC,rid,sid,actor['owner'],{'creatorId':actor['owner'],'fingerprint':fp,'action':action,'state':'committed','segmentId':oid,'underlyingRequestId':None}); db.commit()
            return 201,{'operation':{'requestId':request,'state':'committed','action':action},'segment':project(ctx,s)}
        s=get_segment(sid,actor,parts[1])
        if type(body['revision']) is not int or body['revision']!=s['_revision']: fail('version_conflict','The segment changed.')
        if s['state']=='closed': fail('invalid_transition','Segment is closed.')
        for pending in store.all(REC,sid):
            if pending.get('segmentId')==s['id'] and pending.get('state') in ('pending','unknown'):
                if action=='withdraw_cue' and pending.get('action')=='present': continue
                fail('operation_unresolved','A previous operation needs reconciliation.')
        if action=='select':
            if s.get('materialId'): fail('invalid_transition','Create a new segment to change bound selections.')
            refs_current(sid,body['refs']); signals_current(sid,body['signals']); s.update(refs=body['refs'],signals=body['signals'])
        elif action=='compose':
            if s.get('materialId'): fail('invalid_transition','Material already exists.')
            refs_current(sid,s['refs']); signals_current(sid,s['signals'])
        elif action=='close': s['state']='closed'
        else:
            m=store.get('p10material',s.get('materialId'),sid)
            if not m: fail('invalid_transition','Compose material first.')
            if action!='withdraw_cue': guard_material(ctx,m)
            if action=='present' and not DELIVERY_GUARDS_WIRED: fail('integration_required','Delivery guard wiring is required before presentation.',503)
            # Reject a known configuration failure before recording a dispatch
            # intent. The cue handler repeats this check at the native boundary.
            if action=='present': presentation_configuration(sid,actor)
        underlying='w18-'+digest([sid,actor['owner'],request])[:48]
        if action in ('select','compose','close'):
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE'); authority(ctx)
                if action=='compose':
                    formats=[]
                    for item in s['signals']:
                        if item['kind']=='contribution':
                            c=store.get(waves15_formats.C,item['id'],sid); f=store.get(waves15_formats.F,c['formatId'],sid)
                            formats.append({'id':f['id'],'revision':f['_revision']})
                    binding={'sessionId':sid,'segmentId':s['id'],'refs':s['refs'],'signals':s['signals'],'formats':formats}; mid=store.ident()
                    lines=[]
                    for ref in s['refs']:
                        row=waves16_continuation.valid_ref(ref); lines.append('Source: '+str(row['moment'].get('text',''))[:1500])
                    for item in s['signals']:
                        obj=store.get('w13question' if item['kind']=='question' else waves15_formats.C,item['id'],sid)
                        lines.append(('Question: '+obj['text']) if item['kind']=='question' else ('Contribution: '+obj['selection']+' — '+obj.get('reason','')))
                    content='\n\n'.join(lines)[:12000] or 'Review the selected sources.'
                    mat={'format':'explanation','currentVersion':1,'title':s['title'],'body':content,'refs':s['refs'],'status':'draft','approvedVersion':None,'provider':'deterministic','model':None,'versions':[{'number':1,'title':s['title'],'body':content,'refs':s['refs']}],'w18Segment':binding}
                    put(db,'p10material',mid,sid,actor['owner'],mat); s.update(materialId=mid,binding=binding)
                s=save(db,SEG,s,sid); put(db,REC,rid,sid,actor['owner'],{'creatorId':actor['owner'],'fingerprint':fp,'action':action,'state':'committed','segmentId':s['id'],'underlyingRequestId':None}); db.commit()
            return 200,{'operation':{'requestId':request,'state':'committed','action':action},'segment':project(ctx,s)}
        # Durable intent is committed before crossing the independent handler boundary.
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE'); authority(ctx)
            put(db,REC,rid,sid,actor['owner'],{'creatorId':actor['owner'],'requestId':request,'fingerprint':fp,'action':action,'state':'pending','segmentId':s['id'],'underlyingRequestId':underlying,'segmentRevision':s['_revision']}); db.commit()
        # Return the committed intent and immutable input snapshot to the wrapper.
        return ('dispatch',ctx,rid,request,action,s,m,body,underlying)

def handle(handler,sid,actor,method,parts):
    # Never enter a delegated handler while owning store.LOCK: cue mutations
    # take the native lock first and release store.LOCK for network/OBS I/O.
    outcome=_handle_locked(handler,sid,actor,method,parts)
    if not isinstance(outcome,tuple) or not outcome or outcome[0] not in ('dispatch','reconcile'):
        return outcome
    if outcome[0]=='reconcile':
        _,ctx,rid,request,snapshot=outcome
        _,check=waves15_cues.handle(handler,sid,actor,'GET',['cue-operations',snapshot['underlyingRequestId']])
        return _reconcile(ctx,rid,request,check)
    _,ctx,rid,request,action,s,m,body,underlying=outcome
    try:
        if action=='edit':
            result=phase10_studio.handle('PATCH',['studio','materials',m['id']],{'version':body['version'],'title':body['title'],'body':body['body'],'refs':m['refs']},ctx)
        elif action=='approve':
            result=phase10_studio.handle('POST',['studio','materials',m['id'],'approve'],{'version':body['version']},ctx)
        elif action=='prepare_cue':
            if s.get('cueId'): fail('invalid_transition','Cue already prepared.')
            result=waves15_cues.handle(Body(handler,{'materialId':m['id'],'materialVersion':m['currentVersion'],'idempotencyKey':underlying}),sid,actor,'POST',['cues'])
        else:
            cue=store.get('w15cue',s.get('cueId'),sid)
            if not cue: fail('invalid_transition','Prepare a cue first.')
            cue_action={'present':'present','defer':'defer','withdraw_cue':'withdraw'}[action]
            result=waves15_cues.handle(Body(handler,{'action':cue_action,'revision':cue['_revision'],'idempotencyKey':underlying}),sid,actor,'POST',['cues',cue['id'],'action'])
        return _reconcile(ctx,rid,request,result[1],dispatched=True)
    except BaseException:
        with store.LOCK:
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE'); rec=read(db,REC,rid,sid)
                if rec and rec['state']=='pending': rec['state']='unknown'; save(db,REC,rec,sid)
                db.commit()
        raise

def _reconcile(ctx,rid,request,result,dispatched=False):
    sid=ctx.sid
    with store.LOCK:
        authority(ctx)
        rec=store.get(REC,rid,sid)
        if not rec or rec['creatorId']!=ctx.actor['owner'] or rec['underlyingRequestId']!=('w18-'+digest([sid,ctx.actor['owner'],request])[:48]): fail('operation_unresolved','Operation receipt unavailable.')
        s=get_segment(sid,ctx.actor,rec['segmentId']); action=rec['action']
        op=result.get('operation',{})
        # Studio has no operation receipt: only the direct return can resolve it.
        committed=dispatched if action in ('edit','approve') else op.get('state')=='committed'
        cue=result.get('cue') or op.get('cue')
        if rec['state'] in ('pending','unknown') and committed:
            if s['_revision']!=rec['segmentRevision']: fail('operation_unresolved','Segment changed during operation.')
            if action!='withdraw_cue':
                m=store.get('p10material',s.get('materialId'),sid)
                if not m: fail('stale_context','Segment material unavailable.')
                guard_material(ctx,m)
            if action=='prepare_cue':
                if not cue or s.get('cueId') or cue.get('materialId')!=m['id'] or cue.get('materialVersion')!=m.get('currentVersion') or not cue.get('eligible'): fail('operation_unresolved','Cue cannot be associated.')
                s['cueId']=cue['id']
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE'); s=save(db,SEG,s,sid)
                rec=read(db,REC,rid,sid); rec['state']='committed'; rec=save(db,REC,rec,sid)
                if action=='withdraw_cue':
                    for prior in store.all(REC,sid):
                        if prior.get('segmentId')==s['id'] and prior.get('action')=='present' and prior.get('state') in ('pending','unknown'):
                            prior['state']='resolved'; save(db,REC,prior,sid)
                db.commit()
        elif rec['state']=='pending' and not committed:
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE'); rec=read(db,REC,rid,sid); rec['state']='unknown'; rec=save(db,REC,rec,sid); db.commit()
        return 200,{'operation':{'requestId':request,'state':rec['state'],'action':action,'underlyingRequestId':rec.get('underlyingRequestId')},'segment':project(ctx,s)}
