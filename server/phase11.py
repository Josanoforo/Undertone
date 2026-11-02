"""Phase 11 manual activity persistence primitives. No writes on import."""
from __future__ import annotations
import hashlib, json, re
from . import store, lifecycle, phase6

REQUEST = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
FORMATS = {
    'collective_workshop': {'stages':['Prepare','Invite proposals','Review and incorporate','Compare','Close and continue'], 'contributionTypes':['constraint','design proposal']},
    'participatory_story': {'stages':['Prepare','Invite elements and actions','Review and incorporate','Compare','Close and continue'], 'contributionTypes':['story element','character action']},
}
ACTIONS = {'creator_edit','append_contribution'}

def migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS phase11_activities(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,owner_hash TEXT NOT NULL,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS phase11_participants(id TEXT PRIMARY KEY,activity_id TEXT NOT NULL,secret_hash TEXT NOT NULL,origin_session TEXT NOT NULL,origin_owner TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS phase11_receipts(activity_id TEXT NOT NULL,actor TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(activity_id,actor,request_id))')

def capability(token,purpose,ident):
    import hmac,base64
    raw=hmac.new(token.encode(),('phase11:'+purpose+':'+ident).encode(),hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))

def fingerprint(method,path,data):
    return hashlib.sha256(canonical([method,path,data]).encode()).hexdigest()

def valid_config(config):
    if not isinstance(config,dict) or set(config)!={'objective','basis','stages','contributionTypes','allowedActions'}:return False
    if any(not isinstance(config[k],str) or not config[k].strip() or len(config[k])>4000 for k in ('objective','basis')):return False
    for k in ('stages','contributionTypes'):
        vals=config[k]
        if not isinstance(vals,list) or not 1<=len(vals)<=20 or any(not isinstance(x,str) or not x.strip() or len(x)>120 for x in vals) or len(set(vals))!=len(vals):return False
    acts=config['allowedActions']
    return isinstance(acts,list) and len(acts)<=2 and all(isinstance(x,str) and x in ACTIONS for x in acts) and len(set(acts))==len(acts)

def active_session(db,sid):
    value=phase6.load(db,'session',sid,sid)
    return bool(value and lifecycle.active(value))

def current_credential(db,sid,role,owner,token):
    return bool(active_session(db,sid) and db.execute('SELECT 1 FROM credentials WHERE session_id=? AND role=? AND owner_id=? AND hash=?',(sid,role,owner,store.digest(token))).fetchone())

def load(db,aid):
    row=db.execute('SELECT data,owner_hash FROM phase11_activities WHERE id=?',(aid,)).fetchone()
    if not row:return None
    value=json.loads(row['data']);value['_owner_hash']=row['owner_hash'];return value

def phase12_invalidate_contribution(db, activity, contribution_id):
    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.projectId') IN (SELECT p.project_id FROM phase12_collab_proposals p JOIN phase12_collab_proposal_grants pg ON pg.proposal_id=p.id JOIN phase12_collab_grants g ON g.id=pg.grant_id WHERE g.activity_id=? AND g.contribution_id=?) AND state IN ('queued','running','complete')",(activity['id'],contribution_id))
    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.handoffId') IN (SELECT hg.handoff_id FROM phase12_collab_handoff_grants hg JOIN phase12_collab_grants g ON g.id=hg.grant_id WHERE g.activity_id=? AND g.contribution_id=?) AND state IN ('queued','running','complete')",(activity['id'],contribution_id))
    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE source_id=? AND state IN ('queued','running','complete')",(contribution_id,))
    for version in activity.get('versions',[]):
        for fragment in version.get('fragments',[]):
            if any(ref.get('id')==contribution_id for ref in fragment.get('contributionRefs',[])):
                db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.activityId')=? AND json_extract(ref,'$.fragmentId')=? AND state IN ('queued','running','complete')",(activity['id'],fragment['id']))
                for recap in db.execute('SELECT id,fragment_ids FROM phase12_recaps WHERE activity_id=?',(activity['id'],)).fetchall():
                    if fragment['id'] in json.loads(recap['fragment_ids']):db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE source_id=? AND state IN ('queued','running','complete')",(recap['id'],))

def save(db,activity):
    previous=load(db,activity['id'])
    if previous:
        old={c['id']:c for c in previous['contributions']}
        for contribution in activity['contributions']:
            before=old.get(contribution['id'])
            if before and before.get('contentAllowed') and not contribution.get('contentAllowed'):
                phase12_invalidate_contribution(db,previous,contribution['id'])
            if before and before.get('revision')!=contribution.get('revision'):
                phase12_invalidate_contribution(db,previous,contribution['id'])
            if before and before.get('attributionAllowed') and not contribution.get('attributionAllowed'):
                db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.projectId') IN (SELECT p.project_id FROM phase12_collab_proposals p JOIN phase12_collab_proposal_grants pg ON pg.proposal_id=p.id JOIN phase12_collab_grants g ON g.id=pg.grant_id WHERE g.activity_id=? AND g.contribution_id=?) AND state IN ('queued','running','complete')",(activity['id'],contribution['id']))
                db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.handoffId') IN (SELECT hg.handoff_id FROM phase12_collab_handoff_grants hg JOIN phase12_collab_grants g ON g.id=hg.grant_id WHERE g.activity_id=? AND g.contribution_id=?) AND state IN ('queued','running','complete')",(activity['id'],contribution['id']))
        if any(previous.get(k)!=activity.get(k) for k in ('sessionId','basisAllowed','status','published','publishedVersion','currentVersion','stageRevision')):
            db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.activityId')=? AND (json_extract(ref,'$.type') IN ('activity_fragment','activity_stage','activity_recap') OR ?=0) AND state IN ('queued','running','complete')",(activity['id'],int(activity.get('basisAllowed',False))))
    data={k:v for k,v in activity.items() if k!='_owner_hash'}
    db.execute('UPDATE phase11_activities SET session_id=?,data=? WHERE id=?',(activity['sessionId'],canonical(data),activity['id']))

def basis_available(db,a):
    return a.get('basisAllowed',False) and bool(db.execute("SELECT 1 FROM objects WHERE kind='session' AND id=?",(a.get('basisSessionId'),)).fetchone())

def eligible(db,a,ref):
    c=next((x for x in a['contributions'] if x['id']==ref.get('id') and x['revision']==ref.get('revision')),None)
    if not c or not c['contentAllowed']:return False
    participant=db.execute('SELECT origin_session,origin_owner FROM phase11_participants WHERE id=? AND activity_id=?',(c['participant'],a['id'])).fetchone()
    if not participant or not db.execute("SELECT 1 FROM objects WHERE kind='viewer' AND id=? AND session_id=?",(participant['origin_owner'],participant['origin_session'])).fetchone():return False
    return c['originSession']==a['sessionId'] or c['retainAcrossSessions']

def project_version(db,a,v):
    out={'version':v['version'],'fragments':[],'world':[],'reason':None,'physicalUndo':False}
    out['world']=[entry for entry in v.get('world',[]) if all(eligible(db,a,r) for r in entry['refs'])]
    for frag in v['fragments']:
        if all(eligible(db,a,r) for r in frag['contributionRefs']):out['fragments'].append(frag)
    if all(eligible(db,a,r) for r in v['reasonRefs']):out['reason']=v['reason']
    return out

def project_contribution(db,a,c):
    allowed=eligible(db,a,{'id':c['id'],'revision':c['revision']})
    derived=allowed and all(eligible(db,a,r) for r in c.get('reasonRefs',[]))
    state=c['status'] if derived else ('pending' if allowed else 'withdrawn')
    return {'id':c['id'],'revision':c['revision'],'type':c['type'],'text':c['text'] if allowed else None,'status':state,'reason':c.get('reason') if derived else None,'outputVersion':c.get('outputVersion') if derived else None,'attribution':c.get('attribution') if allowed and c.get('attributionAllowed') else None,'stageIndex':c.get('stageIndex',0),'stageRevision':c.get('stageRevision',0)}

def activity_dto(db,a):
    out={k:a[k] for k in ('id','sessionId','format','status','config','currentVersion','published')}
    out['configRevision']=a.get('configRevision',0)
    out['stage']={'index':a.get('stageIndex',0),'revision':a.get('stageRevision',0),'label':a['config']['stages'][a.get('stageIndex',0)]}
    out['openQuestions']=[q for q in a['openQuestions'] if isinstance(q,str) or all(eligible(db,a,r) for r in q['refs'])]
    out['physicalFacts']=[f for f in a.get('physicalFacts',[]) if all(eligible(db,a,r) for r in f['refs'])]
    return out

def _fail(h,code='invalid_field',status=422):
    h.err(code,'Invalid or unavailable activity request.',status)

def _keys(h,d,names):
    if not isinstance(d,dict) or set(d)!=set(names):_fail(h)

def _text(h,value,limit=4000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit:_fail(h)
    return value

def _refs(h,value):
    if not isinstance(value,list) or len(value)>50:_fail(h)
    for r in value:
        _keys(h,r,('id','revision'))
        if not isinstance(r['id'],str) or type(r['revision']) is not int or r['revision']<1:_fail(h)
    if len({(r['id'],r['revision']) for r in value})!=len(value):_fail(h)
    return value

def _owner(handler,h,a):
    import hmac
    token=handler.headers.get('X-Activity-Owner','')
    if not token or not hmac.compare_digest(store.digest(token),a['_owner_hash']):_fail(h,'unauthorized',401)

def _participant(handler,h,db,a,actor):
    import hmac
    token=handler.headers.get('X-Activity-Participant','')
    if not token:_fail(h,'unauthorized',401)
    rows=db.execute('SELECT * FROM phase11_participants WHERE activity_id=?',(a['id'],)).fetchall()
    for row in rows:
        if hmac.compare_digest(store.digest(token),row['secret_hash']):
            if row['origin_session']==actor['sid'] and row['origin_owner']!=actor['owner']:_fail(h,'forbidden',403)
            return row['id']
    _fail(h,'unauthorized',401)

def _receipt(db,h,aid,actor,d,method,path):
    rid=d.get('requestId')
    if not isinstance(rid,str) or not REQUEST.fullmatch(rid):_fail(h)
    fp=fingerprint(method,path,d)
    row=db.execute('SELECT fingerprint,result FROM phase11_receipts WHERE activity_id=? AND actor=? AND request_id=?',(aid,actor,rid)).fetchone()
    if row and row['fingerprint']!=fp:_fail(h,'request_id_conflict',409)
    return fp, json.loads(row['result']) if row else None

def _record(db,aid,actor,d,fp,result):
    db.execute('INSERT INTO phase11_receipts VALUES(?,?,?,?,?)',(aid,actor,d['requestId'],fp,canonical(result)))

def _result(db,a,result):
    kind=result.get('kind')
    if kind=='activity':return {'activity':activity_dto(db,a)}
    if kind=='version':
        version=next(v for v in a['versions'] if v['version']==result['version'])
        return {'version':project_version(db,a,version)}
    if kind=='contribution':
        c=next(c for c in a['contributions'] if c['id']==result['id'])
        return {'contribution':project_contribution(db,a,c)}
    if kind=='correction':
        c=next(c for c in a['contributions'] if c['id']==result['id'])
        return {'correction':{'contributionId':result['id'],'revision':result['revision'],'previousRevision':result['previousRevision']},'contribution':project_contribution(db,a,c)}
    if kind=='group':
        g=next(g for g in a['groups'] if g['id']==result['id'])
        return {'group':g if all(eligible(db,a,r) for r in g.get('reasonRefs',g['refs'])) else None}
    if kind=='assistance':
        from . import phase11_assist
        row=phase11_assist.load_row(db,a['id'],result['id'])
        return {'assistance':phase11_assist.projection(db,a,row)} if row else {}
    if kind=='participant':return {'participant':{'id':result['id']}}
    if kind=='publish':return {'stageUrl':'/public/activities/'+a['id']}
    if kind=='unpublish':return {'published':False}
    return {}

def route(handler,h,sid,actor,parts,method):
    import secrets
    from urllib.parse import urlparse
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if not current_credential(db,sid,actor['role'],actor['owner'],handler._auth_token):_fail(h,'unauthorized',401)
            if not parts:
                if actor['role']!='creator':_fail(h,'forbidden',403)
                if method=='GET':
                    vals=[{'id':r['id']} for r in db.execute('SELECT id FROM phase11_activities WHERE session_id=?',(sid,)).fetchall()]
                    db.commit();handler.send(200,{'activities':vals});return
                if method!='POST':_fail(h,'not_found',404)
                d=handler.body();_keys(h,d,('requestId','format','basis','objective'))
                if not isinstance(d['format'],str) or d['format'] not in FORMATS:_fail(h)
                _text(h,d['basis']);_text(h,d['objective'])
                actorkey='creator:'+sid+':'+actor['owner'];fp,prev=_receipt(db,h,'creation',actorkey,d,method,urlparse(handler.path).path)
                if prev:
                    a=load(db,prev['id'])
                    if not a or not basis_available(db,a):_fail(h,'not_found',404)
                    secret=capability(handler._auth_token,'owner',a['id']);db.commit();handler._phase11_header=('X-Activity-Owner',secret);handler.send(201,{'activity':activity_dto(db,a)});return
                aid=store.ident();secret=capability(handler._auth_token,'owner',aid);defaults=FORMATS[d['format']]
                config={'objective':d['objective'],'basis':d['basis'],'stages':defaults['stages'][:],'contributionTypes':defaults['contributionTypes'][:],'allowedActions':['creator_edit','append_contribution']}
                a={'id':aid,'sessionId':sid,'format':d['format'],'status':'draft','config':config,'currentVersion':0,'published':False,'publishedVersion':None,'openQuestions':[],'basisSessionId':sid,'basisAllowed':True,'configRevision':0,'stageIndex':0,'stageRevision':0,'physicalFacts':[],'contributions':[],'groups':[],'versions':[{'version':0,'fragments':[],'reason':'Activity prepared','reasonRefs':[]}]}
                db.execute('INSERT INTO phase11_activities VALUES(?,?,?,?)',(aid,sid,store.digest(secret),canonical(a)))
                _record(db,'creation',actorkey,d,fp,{'id':aid});db.commit();handler._phase11_header=('X-Activity-Owner',secret);handler.send(201,{'activity':activity_dto(db,a)});return
            aid=parts[0];a=load(db,aid)
            if not a or not basis_available(db,a):_fail(h,'not_found',404)
            if not valid_config(a['config']):_fail(h,'invalid_config',409)
            is_reopen=len(parts)==2 and parts[1]=='reopen' and method=='POST'
            if a['sessionId']!=sid and not is_reopen:_fail(h,'not_found',404)
            if actor['role']=='creator':
                _owner(handler,h,a);actorkey='owner:'+aid
            elif actor['role']=='viewer':
                if len(parts)==2 and parts[1]=='participants' and method=='POST':actorkey='join:'+sid+':'+actor['owner']
                else:actorkey='participant:'+_participant(handler,h,db,a,actor)
            else:_fail(h,'forbidden',403)
            if method=='GET':
                if len(parts)==1:
                    view=activity_dto(db,a)
                    if actor['role']=='viewer':
                        view['config']={k:v for k,v in view['config'].items() if k!='basis'};view.pop('physicalFacts',None);view.pop('openQuestions',None)
                    out={'activity':view}
                elif parts[1]=='contributions' and len(parts)==2:
                    out={'contributions':[project_contribution(db,a,c) for c in a['contributions'] if actor['role']=='creator' or actorkey=='participant:'+c['participant']]}
                elif len(parts)==4 and parts[1]=='contributions' and parts[3]=='history' and actor['role']=='viewer':
                    c=next((x for x in a['contributions'] if x['id']==parts[2] and actorkey=='participant:'+x['participant']),None)
                    identity=db.execute('SELECT origin_session,origin_owner FROM phase11_participants WHERE id=?',(c['participant'],)).fetchone() if c else None
                    if not c or not identity or identity['origin_session']!=sid or identity['origin_owner']!=actor['owner']:_fail(h,'not_found',404)
                    allowed=eligible(db,a,{'id':c['id'],'revision':c['revision']})
                    lineage=c.get('lineage') or [{'revision':c['revision'],'previousRevision':None,'text':c['text']}]
                    out={'history':{'contributionId':c['id'],'currentRevision':c['revision'],'revisions':[{'revision':v['revision'],'previousRevision':v['previousRevision'],'text':v['text'] if allowed else None} for v in lineage]}}
                elif parts[1]=='versions' and len(parts)==2 and actor['role']=='creator':out={'versions':[project_version(db,a,v) for v in a['versions']]}
                elif parts[1]=='groups' and len(parts)==2 and actor['role']=='creator':out={'groups':[g for g in a['groups'] if all(eligible(db,a,r) for r in g.get('reasonRefs',g['refs']))]}
                elif parts[1]=='operations' and len(parts)==3:
                    row=db.execute('SELECT result FROM phase11_receipts WHERE activity_id=? AND actor=? AND request_id=?',(aid,actorkey,parts[2])).fetchone()
                    if not row:_fail(h,'not_found',404)
                    receipt_result=json.loads(row['result'])
                    if receipt_result.get('kind')=='assistance':
                        from . import phase11_assist
                        assist=phase11_assist.load_row(db,a['id'],receipt_result['id'])
                        if not assist or assist['actor']!=actor['owner']:_fail(h,'not_found',404)
                    out=_result(db,a,receipt_result)
                else:_fail(h,'not_found',404)
                db.commit();handler.send(200,out);return
            if method!='POST':_fail(h,'not_found',404)
            d=handler.body();path=urlparse(handler.path).path;fp,prev=_receipt(db,h,aid,actorkey,d,method,path)
            if prev:
                if prev.get('kind')=='participant':handler._phase11_header=('X-Activity-Participant',capability(handler._auth_token,'participant',prev['id']))
                out=_result(db,a,prev);db.commit();handler.send(200,out);return
            op=parts[1:] ;result={'kind':'activity'};status=200
            if op==['participants'] and actor['role']=='viewer':
                _keys(h,d,('requestId',))
                if a['status']!='active':_fail(h,'invalid_transition',409)
                pid=store.ident();secret=capability(handler._auth_token,'participant',pid)
                db.execute('INSERT INTO phase11_participants VALUES(?,?,?,?,?)',(pid,aid,store.digest(secret),sid,actor['owner']))
                handler._phase11_header=('X-Activity-Participant',secret);result={'kind':'participant','id':pid};status=201
            elif op==['config'] and actor['role']=='creator':
                _keys(h,d,('requestId','config'))
                if a['status']!='draft' or not valid_config(d['config']):_fail(h,'invalid_config',422)
                if a['config']['stages']!=d['config']['stages']:
                    a['stageIndex']=0;a['stageRevision']=a.get('stageRevision',0)+1
                a['config']=d['config'];a['configRevision']=a.get('configRevision',0)+1
            elif op==['activate'] and actor['role']=='creator':
                _keys(h,d,('requestId','confirmBasis'))
                if a['status']!='draft' or d['confirmBasis'] is not True or not valid_config(a['config']):_fail(h,'invalid_transition',409)
                a['status']='active'
            elif op==['stage'] and actor['role']=='creator':
                _keys(h,d,('requestId','expectedStageRevision','stageIndex'))
                if a['status']!='active':_fail(h,'invalid_transition',409)
                if type(d['expectedStageRevision']) is not int or d['expectedStageRevision']!=a.get('stageRevision',0):_fail(h,'stale_stage',409)
                if type(d['stageIndex']) is not int or not 0<=d['stageIndex']<len(a['config']['stages']):_fail(h)
                a['stageIndex']=d['stageIndex'];a['stageRevision']=a.get('stageRevision',0)+1
            elif op==['contributions'] and actor['role']=='viewer':
                legacy=('requestId','type','text','share','attribution','retainAcrossSessions')
                if set(d)==set(legacy):target=a.get('stageIndex',0);stage_revision=a.get('stageRevision',0)
                else:
                    _keys(h,d,(*legacy,'stageIndex','expectedStageRevision'))
                    target=d['stageIndex'];stage_revision=d['expectedStageRevision']
                    if type(target) is not int or type(stage_revision) is not int or target!=a.get('stageIndex',0) or stage_revision!=a.get('stageRevision',0):_fail(h,'stale_stage',409)
                if a['status']!='active' or d['share'] is not True or d['type'] not in a['config']['contributionTypes'] or type(d['retainAcrossSessions']) is not bool:_fail(h)
                _text(h,d['text']);name=d['attribution']
                if name is not None:_text(h,name,100)
                c={'id':store.ident(),'revision':1,'participant':actorkey.split(':',1)[1],'originSession':sid,'stageIndex':target,'stageRevision':stage_revision,'type':d['type'],'text':d['text'],'contentAllowed':True,'attribution':name,'attributionAllowed':name is not None,'retainAcrossSessions':d['retainAcrossSessions'],'status':'pending','reason':None,'outputVersion':None}
                a['contributions'].append(c);result={'kind':'contribution','id':c['id']};status=201
            elif len(op)==3 and op[0]=='contributions' and op[2]=='correct' and actor['role']=='viewer':
                _keys(h,d,('requestId','expectedRevision','text'));_text(h,d['text'])
                c=next((x for x in a['contributions'] if x['id']==op[1] and actorkey=='participant:'+x['participant']),None)
                identity=db.execute('SELECT origin_session,origin_owner FROM phase11_participants WHERE id=?',(c['participant'],)).fetchone() if c else None
                if not c or not identity or identity['origin_session']!=sid or identity['origin_owner']!=actor['owner']:_fail(h,'not_found',404)
                if a['status']!='active' or not eligible(db,a,{'id':c['id'],'revision':c['revision']}):_fail(h,'reference_unavailable',409)
                if type(d['expectedRevision']) is not int or d['expectedRevision']!=c['revision']:_fail(h,'stale_revision',409)
                if d['text']==c['text']:_fail(h,'unchanged_content',409)
                old=c['revision'];lineage=c.setdefault('lineage',[{'revision':old,'previousRevision':None,'text':c['text']}])
                c['revision']=old+1;c['text']=d['text'];lineage.append({'revision':c['revision'],'previousRevision':old,'text':d['text']})
                c['status']='pending';c['reason']=None;c['reasonRefs']=[];c['outputVersion']=None
                result={'kind':'correction','id':c['id'],'revision':c['revision'],'previousRevision':old}
            elif len(op)==3 and op[0]=='contributions' and op[2]=='withdraw' and actor['role']=='viewer':
                _keys(h,d,('requestId','kind'));c=next((x for x in a['contributions'] if x['id']==op[1] and actorkey=='participant:'+x['participant']),None)
                if not c:_fail(h,'not_found',404)
                if d['kind']=='content':c['contentAllowed']=False
                elif d['kind']=='attribution':c['attributionAllowed']=False
                else:_fail(h)
                result={'kind':'contribution','id':c['id']}
            elif len(op)==3 and op[0]=='contributions' and op[2]=='disposition' and actor['role']=='creator':
                _keys(h,d,('requestId','status','reason'));_text(h,d['reason'])
                c=next((x for x in a['contributions'] if x['id']==op[1]),None)
                if not c or not eligible(db,a,{'id':c['id'],'revision':c['revision']}):_fail(h,'not_found',404)
                if d['status']!='not_used' or c['status']=='incorporated':_fail(h,'invalid_transition',409)
                c['status']='not_used';c['reason']=d['reason'];c['reasonRefs']=[{'id':c['id'],'revision':c['revision']}];result={'kind':'contribution','id':c['id']}
            elif op==['groups'] and actor['role']=='creator':
                _keys(h,d,('requestId','label','refs','reason'));_text(h,d['label'],120);_text(h,d['reason']);refs=_refs(h,d['refs'])
                if not refs or not all(eligible(db,a,r) for r in refs):_fail(h,'reference_unavailable',409)
                g={'id':store.ident(),'label':d['label'],'refs':refs,'reason':d['reason']};a['groups'].append(g);result={'kind':'group','id':g['id']}
            elif op==['actions'] and actor['role']=='creator':
                _keys(h,d,('requestId','expectedVersion','action','text','reason','refs'))
                if a['status']!='active' or type(d['expectedVersion']) is not int or d['expectedVersion']!=a['currentVersion']:_fail(h,'stale_version',409)
                if d['action'] not in a['config']['allowedActions']:_fail(h,'forbidden',403)
                _text(h,d['text']);_text(h,d['reason']);refs=_refs(h,d['refs'])
                if d['action']=='append_contribution' and not refs:_fail(h)
                if not all(eligible(db,a,r) for r in refs):_fail(h,'reference_unavailable',409)
                prevv=a['versions'][-1];number=a['currentVersion']+1
                frag={'id':store.ident(),'text':d['text'],'contributionRefs':refs}
                fragments=prevv['fragments']+[frag] if d['action']=='append_contribution' else [frag]
                v={'version':number,'fragments':fragments,'world':prevv.get('world',[]),'reason':d['reason'],'reasonRefs':refs}
                a['versions'].append(v);a['currentVersion']=number
                if a['published']:a['publishedVersion']=number
                for ref in refs:
                    c=next(x for x in a['contributions'] if x['id']==ref['id'])
                    c['status']='incorporated';c['reason']=d['reason'];c['reasonRefs']=refs;c['outputVersion']=number
                result={'kind':'version','version':number}
            elif op==['story-world'] and actor['role']=='creator':
                _keys(h,d,('requestId','expectedVersion','entries','reason'));_text(h,d['reason'])
                if a['format']!='participatory_story' or a['status']!='active':_fail(h,'invalid_transition',409)
                if type(d['expectedVersion']) is not int or d['expectedVersion']!=a['currentVersion']:_fail(h,'stale_version',409)
                if not isinstance(d['entries'],list) or len(d['entries'])>50:_fail(h)
                refs=[]
                for entry in d['entries']:
                    _keys(h,entry,('kind','text','refs'));_text(h,entry['text']);_refs(h,entry['refs'])
                    if entry['kind'] not in ('character','fact','boundary'):_fail(h)
                    if not all(eligible(db,a,r) for r in entry['refs']):_fail(h,'reference_unavailable',409)
                    refs.extend(entry['refs'])
                old=a['versions'][-1];number=a['currentVersion']+1
                a['versions'].append({'version':number,'fragments':old['fragments'],'world':d['entries'],'reason':d['reason'],'reasonRefs':refs});a['currentVersion']=number
                if a['published']:a['publishedVersion']=number
                result={'kind':'version','version':number}
            elif op==['restore'] and actor['role']=='creator':
                _keys(h,d,('requestId','expectedVersion','version','reason'));_text(h,d['reason'])
                if a['status']!='active' or type(d['expectedVersion']) is not int or d['expectedVersion']!=a['currentVersion']:_fail(h,'stale_version',409)
                old=next((x for x in a['versions'] if x['version']==d['version']),None)
                if not old:_fail(h,'not_found',404)
                fragments=[f for f in old['fragments'] if all(eligible(db,a,r) for r in f['contributionRefs'])]
                number=a['currentVersion']+1;a['versions'].append({'version':number,'fragments':fragments,'world':[e for e in old.get('world',[]) if all(eligible(db,a,r) for r in e['refs'])],'reason':d['reason'],'reasonRefs':[]});a['currentVersion']=number
                if a['published']:a['publishedVersion']=number
                result={'kind':'version','version':number}
            elif op==['publish'] and actor['role']=='creator':
                _keys(h,d,('requestId','expectedVersion'))
                if a['status']!='active' or d['expectedVersion']!=a['currentVersion']:_fail(h,'stale_version',409)
                a['published']=True;a['publishedVersion']=a['currentVersion'];result={'kind':'publish'}
            elif op==['physical-facts'] and actor['role']=='creator':
                _keys(h,d,('requestId','text','refs'));_text(h,d['text']);refs=_refs(h,d['refs'])
                if not all(eligible(db,a,r) for r in refs):_fail(h,'reference_unavailable',409)
                a['physicalFacts'].append({'text':d['text'],'refs':refs,'confirmation':'creator_confirmed'})
            elif op==['source-withdraw'] and actor['role']=='creator':
                _keys(h,d,('requestId',));a['basisAllowed']=False;a['published']=False;result={'kind':'unpublish'}
            elif op==['unpublish'] and actor['role']=='creator':
                _keys(h,d,('requestId',));a['published']=False;result={'kind':'unpublish'}
            elif op==['close'] and actor['role']=='creator':
                _keys(h,d,('requestId','expectedVersion','openQuestions'))
                if a['status']!='active' or d['expectedVersion']!=a['currentVersion']:_fail(h,'stale_version',409)
                if not isinstance(d['openQuestions'],list) or len(d['openQuestions'])>20:_fail(h)
                for q in d['openQuestions']:
                    if isinstance(q,str):_text(h,q)
                    else:
                        _keys(h,q,('text','refs'));_text(h,q['text']);refs=_refs(h,q['refs'])
                        if not all(eligible(db,a,r) for r in refs):_fail(h,'reference_unavailable',409)
                a['openQuestions']=d['openQuestions'];a['status']='closed';a['published']=False
            elif op==['reopen'] and actor['role']=='creator':
                _keys(h,d,('requestId','version','openQuestions'))
                if a['status']!='closed' or sid==a['sessionId']:_fail(h,'invalid_transition',409)
                if not isinstance(d['openQuestions'],list) or len(d['openQuestions'])>20:_fail(h)
                for q in d['openQuestions']:
                    if isinstance(q,str):_text(h,q)
                    else:
                        _keys(h,q,('text','refs'));_text(h,q['text']);refs=_refs(h,q['refs'])
                        if not all(eligible(db,a,r) for r in refs):_fail(h,'reference_unavailable',409)
                old=next((x for x in a['versions'] if x['version']==d['version']),None)
                if not old:_fail(h,'not_found',404)
                a['sessionId']=sid
                fragments=[f for f in old['fragments'] if all(eligible(db,a,r) for r in f['contributionRefs'])]
                number=a['currentVersion']+1;a['versions'].append({'version':number,'fragments':fragments,'world':[e for e in old.get('world',[]) if all(eligible(db,a,r) for r in e['refs'])],'reason':'Continued by creator','reasonRefs':[]});a['currentVersion']=number
                a['openQuestions']=d['openQuestions'];a['status']='active';a['published']=False
            else:_fail(h,'not_found',404)
            save(db,a);_record(db,aid,actorkey,d,fp,result);out=_result(db,a,result);db.commit();handler.send(status,out)
        except BaseException:
            db.rollback();raise

def public(handler,h,aid,html=False):
    with store.LOCK,store.connect() as db:
        a=load(db,aid)
        if not a or not basis_available(db,a) or not valid_config(a['config']) or a['status']!='active' or not a['published'] or not active_session(db,a['sessionId']):_fail(h,'not_found',404)
        handler._sid=a['sessionId']
        if html:
            import secrets
            nonce=secrets.token_urlsafe(18)
            page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>Live activity</title><style nonce="%s">body{font:18px sans-serif;background:#171824;color:white;padding:2rem}pre{white-space:pre-wrap}</style><h1 id="objective"></h1><p id="stage"></p><pre id="result"></pre><p id="reason"></p><p>Watching is optional and requires no submission.</p><script nonce="%s">let generation=0;async function refresh(){let n=++generation;try{let r=await fetch('/api/public/activities/'+encodeURIComponent(location.pathname.split('/').pop()),{cache:'no-store'});if(!r.ok)throw Error();let d=(await r.json()).stage;if(n!==generation)return;document.getElementById('objective').textContent=d.objective;document.getElementById('stage').textContent=d.currentStage.label;document.getElementById('result').textContent=d.fragments.map(x=>x.text).concat(d.world.map(x=>x.kind+': '+x.text)).join('\\n\\n');document.getElementById('reason').textContent=d.reason||''}catch(e){if(n!==generation)return;for(const id of ['objective','stage','result','reason'])document.getElementById(id).textContent=''} }refresh();setInterval(refresh,2000)</script></html>'''%(nonce,nonce)
            csp="default-src 'none'; script-src 'nonce-%s'; style-src 'nonce-%s'; connect-src 'self'; base-uri 'none'; frame-ancestors *"%(nonce,nonce)
            handler.send(200,page,'text/html; charset=utf-8',csp);return
        published=next((v for v in a['versions'] if v['version']==a.get('publishedVersion')),None)
        if not published:_fail(h,'not_found',404)
        v=project_version(db,a,published);stage={'objective':a['config']['objective'],'format':a['format'],'currentStage':{'index':a.get('stageIndex',0),'revision':a.get('stageRevision',0),'label':a['config']['stages'][a.get('stageIndex',0)]},'version':v['version'],'fragments':v['fragments'],'world':v['world'],'reason':v['reason'],'context':'Current activity; participation is optional.'}
        handler.send(200,{'stage':stage})
