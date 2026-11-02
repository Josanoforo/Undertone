"""Phase 6 project provenance and typed, durable operations."""
from __future__ import annotations
import copy,json
from urllib.parse import urlparse
from . import store,lifecycle,phase6 as p,phase6_project as core,phase6_readings as readings,phase6_inquiry as inquiry

def schema(db):
    core.schema(db)
    for name in ('grants','imports','proposals','events'):
        db.execute(f'CREATE TABLE IF NOT EXISTS phase6_project_{name}(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,session_id TEXT NOT NULL,revision INTEGER NOT NULL,data TEXT NOT NULL)')

def get(db,name,oid):
    row=db.execute(f'SELECT data,revision FROM phase6_project_{name} WHERE id=?',(oid,)).fetchone()
    if not row:return None
    v=json.loads(row['data']);v['revision']=row['revision'];return v

def all_(db,name,pid=None,sid=None):
    q=f'SELECT id FROM phase6_project_{name} WHERE 1=1';args=[]
    if pid is not None:q+=' AND project_id=?';args.append(pid)
    if sid is not None:q+=' AND session_id=?';args.append(sid)
    q+=' ORDER BY rowid'
    return [get(db,name,r['id']) for r in db.execute(q,args).fetchall()]

def insert(db,name,pid,sid,v):
    v=dict(v);v['id']=store.ident();v['revision']=1
    db.execute(f'INSERT INTO phase6_project_{name} VALUES(?,?,?,?,?)',(v['id'],pid,sid,1,json.dumps(v,ensure_ascii=False)));return v

def save(db,name,v):
    v=copy.deepcopy(v);old=v['revision'];v['revision']+=1
    if db.execute(f'UPDATE phase6_project_{name} SET revision=?,data=? WHERE id=? AND revision=?',(v['revision'],json.dumps(v,ensure_ascii=False),v['id'],old)).rowcount!=1:raise RuntimeError('stale')
    return v

def session_active(db,sid):
    s=p.load(db,'session',sid,sid)
    return bool(s and lifecycle.active(s))

def links(db,pid,sid):
    return [core.get_link(db,r['id']) for r in db.execute('SELECT id FROM phase6_project_links WHERE project_id=? AND session_id=?',(pid,sid))]

def authorized(db,pid,sid,role,scope):
    return session_active(db,sid) and any(l['status']=='active' and l['ownerApproved'] and l['creatorApproved'] and l['scopes'][role].get(scope,False) for l in links(db,pid,sid))

def exact(h,r):
    p.keys(h,r,('originSessionId','kind','id','revision','grantId'))
    for k in ('originSessionId','id','grantId'):p.rid(h,r[k])
    if r['kind'] not in ('reading','observation') or type(r['revision']) is not int or r['revision']<1:p.fail(h)

def origin(db,h,pid,r):
    grant=get(db,'grants',r['grantId'])
    if not grant or grant['status']!='active' or grant['destinationProjectId']!=pid or grant['originSessionId']!=r['originSessionId'] or grant['kind']!=r['kind'] or grant['object']!={'id':r['id'],'revision':r['revision']} or not session_active(db,r['originSessionId']):return None
    sid=r['originSessionId']
    if r['kind']=='reading':
        x=readings.eligible(db,h,sid,{'id':r['id'],'revision':r['revision']},True)
        if not x or not x['consent']['crossSession']:return None
        return {'kind':'reading','text':x['text'],'reason':x['reason'],'attribution':x['consent']['attribution']}
    x=inquiry.obs_ref(db,h,sid,{'id':r['id'],'revision':r['revision']})
    if not x or not x['consent']['project'] or not x['consent']['crossSession']:return None
    return {'kind':'observation',**{k:x[k] for k in ('text','origin','observedAt','method','uncertainty','limitations')}}

def available(db,h,pid,r,sid=None):
    if not origin(db,h,pid,r):return False
    for imp in all_(db,'imports',pid):
        if imp['status']=='active' and imp['ref']==r and (sid is None or imp['sessionId']==sid) and authorized(db,pid,imp['sessionId'],'creator','read'):return True
    return False

def public_grant(v):return {k:v[k] for k in ('id','revision','kind','originSessionId','object','destinationProjectId','status')}
def public_import(v):return {k:v[k] for k in ('id','revision','ref','status')}

def session_route(handler,h,sid,a,parts,method):
    owner=a['owner'];name=parts[0]
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        try:
            if not session_active(db,sid) or not db.execute('SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role=? AND hash=?',(sid,owner,a['role'],store.digest(handler._auth_token))).fetchone():p.fail(h,'unauthorized',401)
            if method=='GET' and name=='export-grants' and len(parts)==1:
                vals=[public_grant(x) for x in all_(db,'grants',sid=sid) if a['role']=='creator' or x['_actor']==owner];out=p.page(handler,h,vals);db.commit();handler.send(200,out);return
            if method=='GET' and name=='projects' and len(parts)==1:
                vals=[]
                for row in db.execute('SELECT DISTINCT project_id FROM phase6_project_links WHERE session_id=?',(sid,)):
                    pid=row['project_id']
                    if authorized(db,pid,sid,a['role'],'read'):
                        l=next(l for l in links(db,pid,sid) if l['status']=='active' and l['scopes'][a['role']]['read']);vals.append({'projectId':pid,'linkId':l['id'],'scopes':l['scopes']})
                out=p.page(handler,h,vals);db.commit();handler.send(200,out);return
            if name=='projects' and len(parts)>=2:
                pid=parts[1];proj=core.get_project(db,pid)
                if not proj or not authorized(db,pid,sid,a['role'],'read'):p.fail(h,'not_found',404)
                if method=='GET' and len(parts)==2:out={'project':project_dto(db,h,proj)};db.commit();handler.send(200,out);return
                if method=='GET' and len(parts)==3 and parts[2]=='proposals':
                    vals=[proposal_dto(db,h,x) for x in all_(db,'proposals',pid)];out=p.page(handler,h,vals);db.commit();handler.send(200,out);return
                if method=='GET' and len(parts)==3 and parts[2]=='imports':
                    p.role(h,a,'creator');vals=[public_import(x) for x in all_(db,'imports',pid,sid)];out=p.page(handler,h,vals);db.commit();handler.send(200,out);return
            if method!='POST':p.fail(h,'not_found',404)
            d=handler.body();p.rid(h,d.get('requestId'));fp=p.fingerprint(method,urlparse(handler.path).path,d);actor='session:'+sid+':'+owner
            if name=='projects' and len(parts)==3 and parts[2]=='resolve-reference':
                p.keys(h,d,('requestId','ref'));exact(h,d['ref']);content=origin(db,h,pid,d['ref']) if available(db,h,pid,d['ref']) else None
                db.commit();handler.send(200,{'reference':{'ref':d['ref'],'available':bool(content),'content':content}});return
            prev=core.check(db,h,actor,d['requestId'],fp)
            if prev:
                out=receipt(db,h,json.loads(prev['result']));db.commit();handler.send(prev['status'],out);return
            status=200
            if name in ('reading-export-grants','observation-export-grants') and len(parts)==1:
                kind='reading' if name.startswith('reading') else 'observation';p.role(h,a,'viewer' if kind=='reading' else 'creator')
                p.keys(h,d,('requestId',kind,'destinationProjectId'));ref=d[kind];readings.getref(h,ref);pid=d['destinationProjectId'];p.rid(h,pid)
                if not core.get_project(db,pid):p.fail(h,'not_found',404)
                if kind=='reading':
                    x=readings.eligible(db,h,sid,ref,True)
                    if not x or x['_owner']!=owner or not x['consent']['crossSession']:p.fail(h,'reference_unavailable',409)
                    state='pending_creator'
                else:
                    x=inquiry.obs_ref(db,h,sid,ref)
                    if not x or not x['consent']['project'] or not x['consent']['crossSession']:p.fail(h,'reference_unavailable',409)
                    state='active'
                v=insert(db,'grants',pid,sid,{'kind':kind,'originSessionId':sid,'object':ref,'destinationProjectId':pid,'status':state,'_actor':owner});status=201;result={'type':'grant','id':v['id']};out={'grant':public_grant(v)}
            elif name=='export-grants' and len(parts)==3 and parts[2] in ('approve','revoke'):
                p.keys(h,d,('requestId','expectedRevision'));v=get(db,'grants',parts[1])
                if not v or v['originSessionId']!=sid:p.fail(h,'not_found',404)
                p.expect(h,v,d)
                if parts[2]=='approve':
                    p.role(h,a,'creator')
                    if v['kind']!='reading' or v['status']!='pending_creator':p.fail(h,'invalid_transition',409)
                    x=readings.eligible(db,h,sid,v['object'],True)
                    if not x or not x['consent']['crossSession']:p.fail(h,'reference_unavailable',409)
                    v['status']='active'
                else:
                    if a['role']!='creator' and not (v['kind']=='reading' and v['_actor']==owner):p.fail(h,'forbidden',403)
                    if v['status']=='revoked':p.fail(h,'invalid_transition',409)
                    v['status']='revoked'
                v=save(db,'grants',v);result={'type':'grant','id':v['id']};out={'grant':public_grant(v)}
            elif name=='projects' and len(parts)==3 and parts[2]=='imports':
                p.role(h,a,'creator');p.keys(h,d,('requestId','ref'));exact(h,d['ref'])
                if not origin(db,h,pid,d['ref']):p.fail(h,'reference_unavailable',409)
                v=insert(db,'imports',pid,sid,{'sessionId':sid,'ref':d['ref'],'status':'active'});status=201;result={'type':'import','id':v['id']};out={'import':public_import(v)}
            elif name=='projects' and len(parts)==5 and parts[2]=='imports' and parts[4]=='revoke':
                p.role(h,a,'creator');p.keys(h,d,('requestId','expectedRevision'));v=get(db,'imports',parts[3])
                if not v or v['sessionId']!=sid or v['ref'] is None or not any(x['id']==v['id'] for x in all_(db,'imports',pid,sid)):p.fail(h,'not_found',404)
                p.expect(h,v,d)
                if v['status']!='active':p.fail(h,'invalid_transition',409)
                v['status']='revoked';v=save(db,'imports',v);result={'type':'import','id':v['id']};out={'import':public_import(v)}
            elif name=='projects' and len(parts)==3 and parts[2]=='proposals':
                if not authorized(db,pid,sid,a['role'],'propose'):p.fail(h,'forbidden',403)
                p.keys(h,d,('requestId','expectedProjectRevision','operation','reason'));p.text(h,d['reason']);project_expect(h,proj,d)
                refs=validate_operation(h,d['operation'])
                refs=dependency_refs(h,proj,d['operation'],refs)
                if len(refs)>20 or any(not available(db,h,pid,r,sid) for r in refs):p.fail(h,'reference_unavailable',409)
                if len(all_(db,'proposals',pid))>=1000:p.fail(h,'limit_reached',409)
                v=insert(db,'proposals',pid,sid,{'projectId':pid,'originSessionId':sid,'actor':a['role'],'_actor':owner,'status':'proposed','operation':d['operation'],'reason':d['reason'],'refs':refs,'createdAt':store.now(),'appliedProjectRevision':None});status=201;result={'type':'proposal-create','id':v['id']};out={'proposal':proposal_dto(db,h,v),'projectRevision':proj['revision']}
            elif name=='projects' and len(parts)==5 and parts[2]=='proposals' and parts[4]=='withdraw':
                p.keys(h,d,('requestId','expectedProposalRevision'));v=get(db,'proposals',parts[3])
                if not v or v['projectId']!=pid or v['originSessionId']!=sid or v['_actor']!=owner:p.fail(h,'not_found',404)
                if type(d['expectedProposalRevision']) is not int or d['expectedProposalRevision']!=v['revision']:p.fail(h,'stale_revision',409)
                if v['status'] not in ('proposed','blocked') and not (v['status']=='accepted' and not refs_ok(db,h,pid,v['refs'])):p.fail(h,'invalid_transition',409)
                v['status']='withdrawn';v=save(db,'proposals',v);result={'type':'proposal','id':v['id']};out={'proposal':proposal_dto(db,h,v)}
            else:p.fail(h,'not_found',404)
            core.record(db,actor,d['requestId'],fp,status,result);db.commit();handler.send(status,out)
        except BaseException:db.rollback();raise

def project_expect(h,v,d):
    n=d.get('expectedProjectRevision')
    if type(n) is not int or n!=v['revision']:p.fail(h,'stale_revision',409)

def validate_operation(h,op):
    if not isinstance(op,dict):p.fail(h)
    t=op.get('type');spec={'select_plan':('type','planId','text','refs'),'supersede_plan':('type','planId','text','refs'),'attach_observation':('type','ref'),'record_decision':('type','decisionId','text','qualification','refs','nextAction'),'open_action':('type','actionId','text','decisionId'),'complete_action':('type','actionId'),'reopen_action':('type','actionId')}
    if not isinstance(t,str) or t not in spec:p.fail(h)
    p.keys(h,op,spec[t])
    for k in ('planId','decisionId','actionId'):
        if k in op and op[k] is not None:p.rid(h,op[k])
    for k in ('text','qualification'):
        if k in op:p.text(h,op[k])
    if t=='record_decision':
        p.keys(h,op['nextAction'],('id','text'));p.rid(h,op['nextAction']['id']);p.text(h,op['nextAction']['text'])
    refs=op.get('refs',[]) if t!='attach_observation' else [op['ref']]
    if not isinstance(refs,list) or len(refs)>20:p.fail(h)
    for r in refs:exact(h,r)
    if len({json.dumps(r,sort_keys=True) for r in refs})!=len(refs):p.fail(h)
    if t=='attach_observation' and op['ref']['kind']!='observation':p.fail(h)
    return refs

def dependency_refs(h,project,op,refs):
    result=list(refs);decision_id=op.get('decisionId') if op['type']=='open_action' else None
    if op['type'] in ('complete_action','reopen_action'):
        action=next((x for x in project['state']['actions'] if x['id']==op['actionId']),None)
        if not action:p.fail(h,'invalid_transition',409)
        decision_id=action['decisionId']
    if decision_id:
        decision=next((x for x in project['state']['decisions'] if x['id']==decision_id and not x['reversed']),None)
        if not decision:p.fail(h,'invalid_transition',409)
        for ref in decision['refs']:
            if ref not in result:result.append(ref)
    return result

def refs_ok(db,h,pid,refs,sid=None):return all(available(db,h,pid,r,sid) for r in refs)

def project_dto(db,h,project):
    v=copy.deepcopy(core.project_dto(project));st=v['state'];pid=v['id']
    plan=st['selectedPlan']
    if plan and not refs_ok(db,h,pid,plan['sourceRefs']):plan['text']=None;plan['available']=False
    for observation in st['observations']:observation['available']=available(db,h,pid,observation['ref'])
    st['reviewAvailable']=any(x['available'] for x in st['observations'])
    decisions={}
    for d in st['decisions']:
        invalid=not refs_ok(db,h,pid,d['refs']);d['provenanceStatus']='invalidated' if invalid else 'valid'
        if invalid:d['text']=None;d['qualification']=None
        decisions[d['id']]=d
    for action in st['actions']:
        parent=decisions.get(action['decisionId']) if action['decisionId'] else None
        if parent and parent['provenanceStatus']=='invalidated':action.update(text=None,status='suspended',provenanceStatus='invalidated')
        else:action['provenanceStatus']='valid'
    return v

def proposal_dto(db,h,v):
    out={k:x for k,x in v.items() if not k.startswith('_')};valid=refs_ok(db,h,v['projectId'],v['refs'])
    if not valid:
        out['operation']=None;out['reason']=None
        if out['status'] in ('proposed','accepted'):out['status']='blocked'
    return out

def event_dto(db,h,v):
    valid=refs_ok(db,h,v['projectId'],v['refs'])
    return {'id':v['id'],'projectRevision':v['projectRevision'],'proposalId':v['proposalId'],'action':v['action'],'actor':'project_owner','at':v['at'],'reason':v['reason'] if valid else None,'provenanceStatus':'valid' if valid else 'invalidated'}

def receipt(db,h,result):
    typ=result['type'];v=get(db,{'grant':'grants','import':'imports','proposal':'proposals','proposal-create':'proposals','proposal-transition':'proposals'}[typ],result['id'])
    if not v:p.fail(h,'not_found',404)
    if typ=='grant':return {'grant':public_grant(v)}
    if typ=='import':return {'import':public_import(v)}
    proj=core.get_project(db,v['projectId']);out={'proposal':proposal_dto(db,h,v)}
    if typ=='proposal-create':out['projectRevision']=proj['revision']
    if typ=='proposal-transition':out['project']=project_dto(db,h,proj)
    return out

def update_project(db,v):
    old=v['revision'];v=copy.deepcopy(v);v['revision']+=1;raw=core.project_dto(v)
    if db.execute('UPDATE phase6_projects SET revision=?,data=? WHERE id=? AND revision=?',(v['revision'],json.dumps(raw,ensure_ascii=False),v['id'],old)).rowcount!=1:raise RuntimeError('stale')
    return v

def apply_operation(db,h,project,proposal):
    st=project['state'];op=proposal['operation'];t=op['type'];undo={}
    if any(len(st[k])>=1000 for k in ('observations','decisions','actions')):p.fail(h,'limit_reached',409)
    # IDs remain reserved after reversal, including prior applications.
    def created_ids(operation):
        kind=operation['type'];ids=[]
        if kind in ('select_plan','supersede_plan'):ids.append(operation['planId'])
        if kind=='record_decision':ids.extend((operation['decisionId'],operation['nextAction']['id']))
        if kind=='open_action':ids.append(operation['actionId'])
        return ids
    new_ids=created_ids(op)
    if len(new_ids)!=len(set(new_ids)):p.fail(h,'invalid_transition',409)
    for prior in all_(db,'proposals',project['id']):
        if prior['id']!=proposal['id'] and prior['status'] in ('applied','reversed') and set(new_ids).intersection(created_ids(prior['operation'])):p.fail(h,'invalid_transition',409)
    if t in ('select_plan','supersede_plan'):
        if (t=='select_plan') != (st['selectedPlan'] is None):p.fail(h,'invalid_transition',409)
        undo={'previous':copy.deepcopy(st['selectedPlan'])};st['selectedPlan']={'id':op['planId'],'text':op['text'],'sourceRefs':op['refs']}
    elif t=='attach_observation':
        if any(x['ref']==op['ref'] for x in st['observations']):p.fail(h,'invalid_transition',409)
        st['observations'].append({'ref':op['ref'],'available':True});undo={'ref':op['ref']}
    elif t=='record_decision':
        if any(x['id']==op['decisionId'] for x in st['decisions']) or any(x['id']==op['nextAction']['id'] for x in st['actions']):p.fail(h,'invalid_transition',409)
        undo={'changedActions':[{ 'id':x['id'],'status':x['status']} for x in st['actions'] if x['status']=='open'],'decisionId':op['decisionId'],'actionId':op['nextAction']['id']}
        for x in st['actions']:
            if x['status']=='open':x['status']='completed'
        st['decisions'].append({'id':op['decisionId'],'text':op['text'],'qualification':op['qualification'],'refs':op['refs'],'provenanceStatus':'valid','reversed':False})
        st['actions'].append({'id':op['nextAction']['id'],'text':op['nextAction']['text'],'status':'open','decisionId':op['decisionId'],'provenanceStatus':'valid'})
    elif t=='open_action':
        if any(x['id']==op['actionId'] for x in st['actions']):p.fail(h,'invalid_transition',409)
        if op['decisionId'] is not None:
            decision=next((d for d in st['decisions'] if d['id']==op['decisionId'] and not d['reversed']),None)
            if not decision or not refs_ok(db,h,project['id'],decision['refs']):p.fail(h,'reference_unavailable',409)
        st['actions'].append({'id':op['actionId'],'text':op['text'],'status':'open','decisionId':op['decisionId'],'provenanceStatus':'valid'});undo={'actionId':op['actionId']}
    else:
        action=next((x for x in st['actions'] if x['id']==op['actionId']),None)
        projected=next((x for x in project_dto(db,h,project)['state']['actions'] if x['id']==op['actionId']),None)
        expected='open' if t=='complete_action' else 'completed'
        if not action or not projected or projected['status']!=expected:p.fail(h,'invalid_transition',409)
        undo={'actionId':action['id'],'status':action['status']};action['status']='completed' if t=='complete_action' else 'open'
    return undo

def reverse_operation(h,project,proposal):
    st=project['state'];op=proposal['operation'];t=op['type'];u=proposal['_undo']
    if t in ('select_plan','supersede_plan'):st['selectedPlan']=u['previous']
    elif t=='attach_observation':st['observations']=[x for x in st['observations'] if x['ref']!=u['ref']]
    elif t=='record_decision':
        for d in st['decisions']:
            if d['id']==u['decisionId']:d['reversed']=True
        st['actions']=[x for x in st['actions'] if x['id']!=u['actionId']]
        for before in u['changedActions']:
            x=next((x for x in st['actions'] if x['id']==before['id']),None)
            if x:x['status']=before['status']
    elif t=='open_action':st['actions']=[x for x in st['actions'] if x['id']!=u['actionId']]
    else:
        x=next((x for x in st['actions'] if x['id']==u['actionId']),None)
        if not x:p.fail(h,'invalid_transition',409)
        x['status']=u['status']

def owner_route(handler,h,parts,method):
    pid=parts[0]
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE');schema(db)
        try:
            project=core.auth_owner(handler,h,db,pid)
            if len(parts)==1 and method=='GET':out={'project':project_dto(db,h,project)};db.commit();handler.send(200,out);return
            if len(parts)==2 and parts[1] in ('history','proposals') and method=='GET':
                typ='events' if parts[1]=='history' else 'proposals';vals=all_(db,typ,pid);out=p.page(handler,h,[event_dto(db,h,x) if typ=='events' else proposal_dto(db,h,x) for x in vals]);db.commit();handler.send(200,out);return
            if method!='POST':p.fail(h,'not_found',404)
            d=handler.body();p.rid(h,d.get('requestId'))
            if len(parts)==2 and parts[1]=='resolve-reference':
                p.keys(h,d,('requestId','ref'));exact(h,d['ref']);content=origin(db,h,pid,d['ref']) if available(db,h,pid,d['ref']) else None
                db.commit();handler.send(200,{'reference':{'ref':d['ref'],'available':bool(content),'content':content}});return
            if len(parts)!=4 or parts[1]!='proposals' or parts[3] not in ('accept','apply','reject','reverse'):p.fail(h,'not_found',404)
            p.keys(h,d,('requestId','expectedProjectRevision','expectedProposalRevision','reason'));p.text(h,d['reason']);fp=p.fingerprint(method,urlparse(handler.path).path,d);actor='owner:'+pid;prev=core.check(db,h,actor,d['requestId'],fp)
            if prev:out=receipt(db,h,json.loads(prev['result']));db.commit();handler.send(prev['status'],out);return
            proposal=get(db,'proposals',parts[2])
            if not proposal or proposal['projectId']!=pid:p.fail(h,'not_found',404)
            project_expect(h,project,d)
            if type(d['expectedProposalRevision']) is not int or d['expectedProposalRevision']!=proposal['revision']:p.fail(h,'stale_revision',409)
            action=parts[3]
            if action in ('accept','apply'):
                if not authorized(db,pid,proposal['originSessionId'],proposal['actor'],'propose') or not refs_ok(db,h,pid,proposal['refs'],proposal['originSessionId']):p.fail(h,'reference_unavailable',409)
                if action=='accept':
                    if proposal['status']!='proposed':p.fail(h,'invalid_transition',409)
                    proposal['status']='accepted'
                else:
                    if proposal['status']!='accepted':p.fail(h,'invalid_transition',409)
                    proposal['_undo']=apply_operation(db,h,project,proposal);project=update_project(db,project);proposal['status']='applied';proposal['appliedProjectRevision']=project['revision']
            elif action=='reject':
                if proposal['status'] not in ('proposed','accepted','blocked'):p.fail(h,'invalid_transition',409)
                proposal['status']='rejected'
            else:
                applied=[x for x in all_(db,'proposals',pid) if x['status']=='applied']
                if proposal['status']!='applied' or not applied or max(x['appliedProjectRevision'] for x in applied)!=proposal['appliedProjectRevision']:p.fail(h,'invalid_transition',409)
                reverse_operation(h,project,proposal);project=update_project(db,project);proposal['status']='reversed'
            proposal=save(db,'proposals',proposal)
            insert(db,'events',pid,proposal['originSessionId'],{'projectId':pid,'projectRevision':project['revision'],'proposalId':proposal['id'],'action':action,'at':store.now(),'reason':d['reason'],'refs':proposal['refs']})
            result={'type':'proposal-transition','id':proposal['id']};core.record(db,actor,d['requestId'],fp,200,result);out={'proposal':proposal_dto(db,h,proposal),'project':project_dto(db,h,project)};db.commit();handler.send(200,out)
        except BaseException:db.rollback();raise
