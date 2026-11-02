"""Versioned finite definitions and stageful rounds; no runtime/router ownership."""
import copy, hashlib, json
from . import store as base
from . import waves15_formats as f
from .phase10_common import Context, Phase10Error

S=f.store
T='w17template'; V='w17templateversion'; R='w17templateround'; Q='w17templatereceipt'
STAGES=('open','contribute','review','decide','reveal','close')
RESET={'responses':'reset','identities':'reset','consents':'reset','decision':'reset','sources':'explicit'}

def fail(message,status=400): f.error(message,status)
def clean_definition(value):
    if not isinstance(value,dict) or set(value)!={'type','title','question','options','cards'}: fail('Invalid definition.')
    d=f.definition(dict(value,refs=[])); d.pop('refs'); return d

def template(oid,actor):
    obj=S.get(T,oid)
    if not obj or obj.get('creatorId')!=actor['owner']: fail('Template unavailable.',404)
    if obj.get('importedFrom'): validate_import(obj['importedFrom']['transferId'])
    return obj

def validate_import(transfer_id):
    from . import waves16_continuation as c
    offer=S.get(f.T,transfer_id)
    if not offer: fail('Imported definition unavailable.',409)
    c.validate_offer(offer,('accepted',))

def version(t,number):
    if type(number) is not int or number<1: fail('Version required.')
    obj=S.get(V,t['id']+':'+str(number))
    if not obj: fail('Template version unavailable.',404)
    return obj

def material(ctx,link):
    from . import waves16_continuation as c
    from . import waves18_delivery
    if not isinstance(link,dict) or set(link)!={'id','version'} or not isinstance(link['id'],str) or type(link['version']) is not int: fail('Invalid material link.')
    m=S.get('p10material',link['id'],ctx.sid)
    if not m or m.get('currentVersion')!=link['version'] or m.get('approvedVersion')!=link['version'] or m.get('status') not in ('approved','published'): fail('Approved current material unavailable.',409)
    c.guard_material(ctx,m)
    waves18_delivery.guard_delivery(ctx.sid,m)
    f.references(ctx,m.get('refs',[]))
    return {'id':m['id'],'version':link['version'],'title':m.get('title',''),'body':m.get('body',''),'refs':m.get('refs',[])}

def guard(fmt,action):
    r=S.get(R,fmt['templateRoundId'])
    if not r or r.get('formatId')!=fmt.get('id'): fail('Round unavailable.',409)
    allowed={'contribute':'contribute','accept':'review','decide':'decide'}
    if action not in allowed or r['stage']!=allowed[action]: fail('Action unavailable in this round stage.',409)

def project(ctx,fmt,contributions,actor):
    r=S.get(R,fmt['templateRoundId'],ctx.sid)
    if not r or r.get('formatId')!=fmt['id']: fail('Round unavailable.',409)
    fmt['roundStage']=r['stage']
    if actor['role']!='creator' and r['stage'] not in ('reveal','close'):
        fmt['decision']=None
        contributions=[c for c in contributions if c.get('authorId')==actor['owner']]
    return fmt,contributions

def round_view(ctx,r,actor):
    fmt=f.find(f.F,r['formatId'],ctx.sid); projected,cs=f.projection(ctx,fmt,ctx.sid,actor)
    links=[]
    for link in r['materialLinks']:
        try: links.append(material(ctx,link))
        except Phase10Error: pass
    return {'round':r,'format':projected,'contributions':cs,'carriedMaterial':links}

def inner(ctx,method,parts,body):
    sid=ctx.sid; actor=ctx.actor
    if parts==['templates','import-continuation'] and method=='POST':
        from . import waves16_continuation as c
        f.creator(actor); f.fields(body,('transferId',))
        if not isinstance(body['transferId'],str): fail('Invalid continuation ID.')
        offer=S.get(f.T,body['transferId'])
        if not offer or offer.get('targetSessionId')!=sid: fail('Accepted continuation unavailable.',404)
        snap=c.validate_offer(offer,('accepted',))
        source=S.get(f.F,snap['formatId'],snap['sourceSessionId'])
        prior=S.get(R,source.get('templateRoundId'),snap['sourceSessionId']) if source and source.get('templateRoundId') else None
        if not prior or prior.get('formatId')!=source['id']: fail('Continuation has no template version.',409)
        original=S.get(V,prior['templateId']+':'+str(prior['templateVersion']))
        keys=('type','title','question','options','cards')
        if not original or any(original['definition'].get(k)!=offer['formatSnapshot'].get(k) for k in keys): fail('Template definition changed.',409)
        oid=S.ident(); d=clean_definition(original['definition'])
        S.put(T,sid,{'creatorId':actor['owner'],'latestVersion':1,'importedFrom':{'transferId':offer['id'],'templateId':prior['templateId'],'version':prior['templateVersion']}},owner=actor['owner'],oid=oid)
        S.put(V,sid,{'templateId':oid,'version':1,'definition':d},owner=actor['owner'],oid=oid+':1')
        return 201,{'template':template(oid,actor),'version':version(template(oid,actor),1)}
    if parts==['templates'] and method=='GET':
        f.creator(actor)
        with S.connect() as db: rows=db.execute('SELECT data,revision FROM objects WHERE kind=? AND owner_id=?',(T,actor['owner'])).fetchall()
        visible=[]
        for row in rows:
            candidate=json.loads(row['data'])
            try:
                visible.append(template(candidate['id'],actor))
            except Phase10Error:
                # An invalid imported continuation must not hide other owned templates.
                continue
        return 200,{'templates':visible}
    if parts==['templates'] and method=='POST':
        f.creator(actor); f.fields(body,('definition',)); d=clean_definition(body['definition']); oid=S.ident()
        S.put(T,sid,{'creatorId':actor['owner'],'latestVersion':1},owner=actor['owner'],oid=oid)
        S.put(V,sid,{'templateId':oid,'version':1,'definition':d},owner=actor['owner'],oid=oid+':1')
        return 201,{'template':template(oid,actor),'version':version(template(oid,actor),1)}
    if len(parts)==2 and parts[0]=='templates' and method=='GET':
        f.creator(actor); t=template(parts[1],actor)
        return 200,{'template':t,'versions':[version(t,i) for i in range(1,t['latestVersion']+1)]}
    if len(parts)==3 and parts[0]=='templates' and parts[2]=='versions' and method=='POST':
        f.creator(actor); t=template(parts[1],actor); f.fields(body,('expectedRevision','definition'))
        if body['expectedRevision']!=t['_revision'] or type(body['expectedRevision']) is not int: fail('Template changed.',409)
        d=clean_definition(body['definition']); n=t['latestVersion']+1
        if d['type']!=version(t,1)['definition']['type']: fail('Template type cannot change.')
        S.put(V,sid,{'templateId':t['id'],'version':n,'definition':d},owner=actor['owner'],oid=t['id']+':'+str(n)); t['latestVersion']=n
        return 201,{'template':S.save(T,t,revision=body['expectedRevision']),'version':version(t,n)}
    if len(parts)==3 and parts[0]=='templates' and parts[2] in ('preview','instantiate') and method=='POST':
        f.creator(actor); t=template(parts[1],actor); f.fields(body,('version','resetPolicy','refs','materialLinks'))
        v=version(t,body['version'])
        if body['resetPolicy']!=RESET: fail('Explicit reset policy required.')
        f.references(ctx,body['refs'])
        if not isinstance(body['materialLinks'],list) or len(body['materialLinks'])>20: fail('Invalid material links.')
        carried=[material(ctx,x) for x in body['materialLinks']]
        preview={'definition':v['definition'],'version':v['version'],'resetPolicy':RESET,'refs':body['refs'],'carriedMaterial':carried}
        if parts[2]=='preview': return 200,{'preview':preview}
        rid=S.ident(); fid=S.ident()
        fmt=dict(copy.deepcopy(v['definition']),refs=copy.deepcopy(body['refs']),decision=None,templateRoundId=rid)
        if t.get('importedFrom'): fmt['templateImportTransferId']=t['importedFrom']['transferId']
        S.put(f.F,sid,fmt,owner=actor['owner'],oid=fid)
        S.put(R,sid,{'templateId':t['id'],'templateVersion':v['version'],'formatId':fid,'stage':'open','resetPolicy':RESET,'materialLinks':copy.deepcopy(body['materialLinks'])},owner=actor['owner'],oid=rid)
        return 201,round_view(ctx,f.find(R,rid,sid),actor)
    if len(parts)==2 and parts[0]=='template-rounds' and method=='GET':
        return 200,round_view(ctx,f.find(R,parts[1],sid),actor)
    if len(parts)==3 and parts[0]=='template-rounds' and parts[2]=='transition' and method=='POST':
        f.creator(actor); r=f.find(R,parts[1],sid); f.fields(body,('expectedRevision','stage'))
        if type(body['expectedRevision']) is not int or r['_revision']!=body['expectedRevision']: fail('Round changed.',409)
        target=body['stage']; i=STAGES.index(r['stage'])
        active=[x for x in S.all(f.C,sid) if x.get('formatId')==r['formatId'] and x.get('status')!='withdrawn']
        zero_close=target=='close' and not active and r['stage']!='close'
        if not zero_close and (i==len(STAGES)-1 or target!=STAGES[i+1]): fail('Invalid stage transition.',409)
        fmt=f.find(f.F,r['formatId'],sid); f.current(ctx,fmt)
        if target=='reveal' and not fmt.get('decision'): fail('A decision is required before reveal.',409)
        r['stage']=target; r=S.save(R,r,revision=body['expectedRevision'])
        return 200,round_view(ctx,r,actor)
    fail('Template route unavailable.',404)

def handle(handler,sid,actor,method,parts):
    with S.LOCK:
        ctx=Context(handler,sid,actor); ctx.check_actor()
        if actor.get('sid')!=sid: fail('Session unavailable.',404)
        if method!='POST': return inner(ctx,method,parts,None)
        b=handler.body()
        if not isinstance(b,dict): fail('Invalid body.')
        b=dict(b); key=f._key(b.pop('requestId',None))
        operation=method+' /'+'/'.join(parts)
        fingerprint=hashlib.sha256(json.dumps([operation,b],sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        oid=hashlib.sha256(json.dumps([sid,actor['owner'],key],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        with base.connect() as db:
            db.execute('BEGIN IMMEDIATE'); S.local.db=db
            try:
                ctx.check_actor(); rec=S.get(Q,oid,sid)
                if rec:
                    if rec['fingerprint']!=fingerprint or rec['role']!=actor['role']: fail('Request ID already used.',409)
                    # Recompute sensitive projections and validate current rights on replay.
                    if rec.get('roundId'):
                        current=round_view(ctx,f.find(R,rec['roundId'],sid),actor)
                        if current['round']['_revision']!=rec['roundRevision'] or current['format']['_revision']!=rec['formatRevision']: fail('Committed round changed.',409)
                        result=(rec['status'],current)
                    elif rec.get('templateId'):
                        t=template(rec['templateId'],actor)
                        if t['_revision']!=rec['templateRevision']: fail('Committed template changed.',409)
                        result=(rec['status'],{'template':t,'version':version(t,rec['version'])})
                    else: result=inner(ctx,method,parts,b)
                    db.commit(); return result
                status,result=inner(ctx,method,parts,b)
                rec={'fingerprint':fingerprint,'role':actor['role'],'status':status}
                if 'round' in result: rec.update(roundId=result['round']['id'],roundRevision=result['round']['_revision'],formatRevision=result['format']['_revision'])
                elif 'template' in result: rec.update(templateId=result['template']['id'],version=result['version']['version'],templateRevision=result['template']['_revision'])
                else: rec['preview']=True
                S.put(Q,sid,rec,owner=actor['owner'],oid=oid); db.commit(); return status,result
            except BaseException:
                db.rollback(); raise
            finally: del S.local.db
