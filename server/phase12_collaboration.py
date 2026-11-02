"""Scoped two-creator project membership; no source data is shared by invitation."""
import hashlib,json,re
from . import store,lifecycle
from .phase10_common import Phase10Error

REQUEST=re.compile(r'^[A-Za-z0-9._:-]{1,128}$')
def bad(code,message,status=409):raise Phase10Error(code,message,status)
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def migrate(db):
 from . import phase12_collab_grants,phase12_collab_audience
 phase12_collab_grants.migrate(db)
 phase12_collab_audience.migrate(db)
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_projects (id TEXT PRIMARY KEY, owner_session TEXT NOT NULL, owner_id TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_members (project_id TEXT NOT NULL, session_id TEXT NOT NULL, actor_id TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL, PRIMARY KEY(project_id,session_id,actor_id))')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_invites (id TEXT PRIMARY KEY,project_id TEXT NOT NULL,sender_session TEXT NOT NULL,recipient_session TEXT NOT NULL,recipient_id TEXT NOT NULL,status TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_handoffs (id TEXT PRIMARY KEY,project_id TEXT NOT NULL,sender_session TEXT NOT NULL,recipient_session TEXT NOT NULL,material_id TEXT NOT NULL,version INTEGER NOT NULL,content TEXT NOT NULL,questions TEXT NOT NULL,state TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_versions (project_id TEXT NOT NULL,version INTEGER NOT NULL,handoff_id TEXT NOT NULL,body TEXT NOT NULL,proposal_id TEXT,PRIMARY KEY(project_id,version))')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_proposals (id TEXT PRIMARY KEY,project_id TEXT NOT NULL,handoff_id TEXT NOT NULL,author_session TEXT NOT NULL,base_version INTEGER NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL,reason TEXT)')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_activity_links (activity_id TEXT PRIMARY KEY,project_id TEXT NOT NULL,handoff_id TEXT NOT NULL,session_id TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_proposal_grants (proposal_id TEXT NOT NULL,grant_id TEXT NOT NULL,PRIMARY KEY(proposal_id,grant_id))')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_replacements (handoff_id TEXT PRIMARY KEY, previous_id TEXT NOT NULL)')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_receipts (session_id TEXT NOT NULL,actor_id TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(session_id,actor_id,request_id))')
def auth(db,handler,sid,actor):
 current=db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='creator' AND hash=?",(sid,actor['owner'],store.digest(handler._auth_token))).fetchone()
 session=store.get('session',sid)
 if actor['role']!='creator':bad('forbidden','Creator capability required.',403)
 if not current or not session or not lifecycle.active(session):bad('not_found','Session or capability unavailable.',404)
def reqid(data):
 if not isinstance(data,dict) or not isinstance(data.get('requestId'),str) or not REQUEST.fullmatch(data['requestId']):bad('invalid_request','A valid requestId is required.',422)
def receipt(db,sid,actor,data,method,path):
 reqid(data);fp=hashlib.sha256(canonical([method,path,data]).encode()).hexdigest()
 row=db.execute('SELECT fingerprint,result FROM phase12_collab_receipts WHERE session_id=? AND actor_id=? AND request_id=?',(sid,actor['owner'],data['requestId'])).fetchone()
 if row and row['fingerprint']!=fp:bad('request_conflict','Request ID already used for another payload.')
 return fp,json.loads(row['result']) if row else None
def save_receipt(db,sid,actor,data,fp,result):db.execute('INSERT INTO phase12_collab_receipts VALUES(?,?,?,?,?)',(sid,actor['owner'],data['requestId'],fp,canonical(result)))
def receipt_metadata(row):
 if not row:return None
 result=json.loads(row['result'])
 return {key:result[key] for key in ('kind','id','project','handoff','version','action') if key in result}
def project(db,pid,sid,actor):
 p=db.execute('SELECT * FROM phase12_collab_projects WHERE id=?',(pid,)).fetchone()
 member=db.execute("SELECT * FROM phase12_collab_members WHERE project_id=? AND session_id=? AND actor_id=? AND status='active'",(pid,sid,actor['owner'])).fetchone()
 if not p or not member or p['status']!='active':bad('not_found','Project unavailable.',404)
 members=[{'sessionId':x['session_id'],'role':x['role'],'status':x['status']} for x in db.execute("SELECT * FROM phase12_collab_members WHERE project_id=? ORDER BY rowid",(pid,)).fetchall()]
 return {'id':p['id'],'title':p['title'],'role':member['role'],'members':members}
def eligible_material(sid,material_id,version):
 from .http import p10_public_material
 session=store.get('session',sid)
 value=p10_public_material(session.get('joinCode',''),material_id) if session else None
 if not value or value['version']!=version:bad('source_unavailable','Published material or exact version is unavailable.')
 return value

def handoff(db,pid,hid,sid,actor):
 project(db,pid,sid,actor)
 row=db.execute('SELECT * FROM phase12_collab_handoffs WHERE id=? AND project_id=?',(hid,pid)).fetchone()
 if not row or sid not in (row['sender_session'],row['recipient_session']):bad('not_found','Handoff unavailable.',404)
 if row['state']=='withdrawn':bad('source_unavailable','Handoff was withdrawn.')
 for member_sid in (row['sender_session'],row['recipient_session']):
  session=store.get('session',member_sid)
  if not session or not lifecycle.active(session) or not db.execute("SELECT 1 FROM phase12_collab_members m JOIN credentials c ON c.session_id=m.session_id AND c.owner_id=m.actor_id AND c.role='creator' WHERE m.project_id=? AND m.session_id=? AND m.status='active'",(pid,member_sid)).fetchone():bad('source_unavailable','Handoff membership or session unavailable.')
 current=eligible_material(row['sender_session'],row['material_id'],row['version'])
 stored=json.loads(row['content'])
 if current!=stored:bad('source_unavailable','Published source changed or was withdrawn.')
 from . import phase12_collab_grants
 grants=db.execute('SELECT grant_id FROM phase12_collab_handoff_grants WHERE handoff_id=? ORDER BY rowid',(hid,)).fetchall()
 contributions=[phase12_collab_grants.projection(db,g['grant_id'],pid,row['sender_session'],row['recipient_session']) for g in grants]
 replacement=db.execute('SELECT previous_id FROM phase12_collab_replacements WHERE handoff_id=?',(hid,)).fetchone()
 return {'id':row['id'],'projectId':pid,'senderSessionId':row['sender_session'],'recipientSessionId':row['recipient_session'],'version':row['version'],'status':row['state'],'material':stored,'questions':json.loads(row['questions']),'contributions':contributions,'replacesHandoffId':replacement['previous_id'] if replacement else None}

def proposal_attribution_rights(db,handoff_id):
 # Free-form editor text cannot be safely stripped of a withdrawn contributor name.
 from . import phase11
 for g in db.execute('SELECT g.* FROM phase12_collab_handoff_grants hg JOIN phase12_collab_grants g ON g.id=hg.grant_id WHERE hg.handoff_id=?',(handoff_id,)).fetchall():
  activity=phase11.load(db,g['activity_id'])
  contributor=next((x for x in activity.get('contributions',[]) if x['id']==g['contribution_id'] and x['revision']==g['revision']),None) if activity else None
  if contributor and contributor.get('attribution') and (not g['attribution'] or not contributor.get('attributionAllowed')):bad('source_unavailable','Attribution withdrawal makes free-form proposal text unavailable.')

def proposal_contributions(db,pid,propid,audience=False):
 from . import phase12_collab_grants
 row=db.execute('SELECT * FROM phase12_collab_proposals WHERE id=? AND project_id=?',(propid,pid)).fetchone()
 if not row:bad('source_unavailable','Proposal unavailable.')
 project_row=db.execute('SELECT owner_session FROM phase12_collab_projects WHERE id=?',(pid,)).fetchone()
 return [phase12_collab_grants.projection(db,g['grant_id'],pid,row['author_session'],project_row['owner_session'],audience) for g in db.execute('SELECT grant_id FROM phase12_collab_proposal_grants WHERE proposal_id=? ORDER BY rowid',(propid,)).fetchall()]

def proposal_grant_attribution_rights(db,propid):
 from . import phase11
 for g in db.execute('SELECT g.* FROM phase12_collab_proposal_grants pg JOIN phase12_collab_grants g ON g.id=pg.grant_id WHERE pg.proposal_id=?',(propid,)).fetchall():
  activity=phase11.load(db,g['activity_id'])
  contributor=next((x for x in activity.get('contributions',[]) if x['id']==g['contribution_id'] and x['revision']==g['revision']),None) if activity else None
  if contributor and contributor.get('attribution') and (not g['attribution'] or not contributor.get('attributionAllowed')):bad('source_unavailable','Attribution withdrawal makes free-form proposal text unavailable.')

def current_version(db,pid,sid,actor):
 project(db,pid,sid,actor)
 row=db.execute('SELECT * FROM phase12_collab_versions WHERE project_id=? ORDER BY version DESC LIMIT 1',(pid,)).fetchone()
 if not row:bad('not_found','No accepted project version.',404)
 source=handoff(db,pid,row['handoff_id'],sid,actor)
 if source['status']!='accepted':bad('source_unavailable','Accepted handoff unavailable.')
 if row['proposal_id']:
  proposal_attribution_rights(db,row['handoff_id']);proposal_grant_attribution_rights(db,row['proposal_id']);proposal_contributions(db,pid,row['proposal_id'])
 return {'projectId':pid,'version':row['version'],'handoffId':row['handoff_id'],'body':row['body'],'proposalId':row['proposal_id']}
def versions(db,pid,sid,actor):
 project(db,pid,sid,actor)
 values=[]
 for row in db.execute('SELECT * FROM phase12_collab_versions WHERE project_id=? ORDER BY version',(pid,)).fetchall():
  try:
   source=handoff(db,pid,row['handoff_id'],sid,actor)
   if row['proposal_id']:
    proposal_attribution_rights(db,row['handoff_id']);proposal_grant_attribution_rights(db,row['proposal_id']);proposal_contributions(db,pid,row['proposal_id'])
   if source['status']=='accepted':values.append({'projectId':pid,'version':row['version'],'handoffId':row['handoff_id'],'body':row['body'],'proposalId':row['proposal_id']})
  except Phase10Error:continue
 return values
def activity_link(db,handler,pid,hid,sid,actor):
 from . import phase11,http
 value=handoff(db,pid,hid,sid,actor)
 if value['status']!='accepted' or value['recipientSessionId']!=sid:bad('not_found','Activity link unavailable.',404)
 row=db.execute('SELECT * FROM phase12_collab_activity_links WHERE project_id=? AND handoff_id=? AND session_id=?',(pid,hid,sid)).fetchone()
 if not row:bad('not_found','Activity link unavailable.',404)
 a=phase11.load(db,row['activity_id'])
 if not a or a['sessionId']!=sid or not phase11.basis_available(db,a) or not phase11.active_session(db,a['basisSessionId']):bad('source_unavailable','Activity unavailable.')
 phase11._owner(handler,http,a)
 return {'projectId':pid,'handoffId':hid,'activityId':a['id'],'activityVersion':a['currentVersion'],'stageIndex':a.get('stageIndex',0),'stageRevision':a.get('stageRevision',0)}

def proposal(db,pid,propid,sid,actor):
 project(db,pid,sid,actor)
 row=db.execute('SELECT * FROM phase12_collab_proposals WHERE project_id=? AND id=?',(pid,propid)).fetchone()
 if not row:bad('not_found','Proposal unavailable.',404)
 source=handoff(db,pid,row['handoff_id'],sid,actor)
 if source['status']!='accepted':bad('source_unavailable','Accepted handoff unavailable.')
 proposal_attribution_rights(db,row['handoff_id']);proposal_grant_attribution_rights(db,propid)
 contributions=proposal_contributions(db,pid,propid)
 return {'id':row['id'],'projectId':pid,'handoffId':row['handoff_id'],'authorSessionId':row['author_session'],'baseVersion':row['base_version'],'body':row['body'],'status':row['state'],'returnReason':row['reason'],'contributions':contributions}

def selection(data):
 if not {'requestId','materialId','version','questions','confirmAuthor'}<=set(data) or set(data)-{'requestId','materialId','version','questions','confirmAuthor','replacesHandoffId','contributionGrantIds'} or not isinstance(data['materialId'],str) or type(data['version']) is not int or data['version']<1 or data['confirmAuthor'] is not True or not isinstance(data['questions'],list) or len(data['questions'])>10 or any(not isinstance(x,str) or not 1<=len(x.strip())<=500 for x in data['questions']):bad('invalid_request','Select a published version and confirm your authored questions.',422)

def handle(handler,sid,actor,method,parts):
 from urllib.parse import urlparse
 path=urlparse(handler.path).path
 with store.LOCK,store.connect() as db:
  db.execute('BEGIN IMMEDIATE');auth(db,handler,sid,actor)
  if len(parts)==3 and parts[:2]==['projects','receipts'] and method=='GET':
   reqid({'requestId':parts[2]})
   row=db.execute('SELECT result FROM phase12_collab_receipts WHERE session_id=? AND actor_id=? AND request_id=?',(sid,actor['owner'],parts[2])).fetchone()
   # Absence cannot prove that an earlier in-flight action will not commit.
   handler._p12_collab_binding=(sid,actor,[])
   db.commit();return 200,{'receipt':{'requestId':parts[2],'state':'committed' if row else 'unknown','result':receipt_metadata(row)}}
  if parts==['projects'] and method=='GET':
   rows=db.execute("SELECT project_id FROM phase12_collab_members WHERE session_id=? AND actor_id=? AND status='active'",(sid,actor['owner'])).fetchall();values=[project(db,r['project_id'],sid,actor) for r in rows];handler._p12_collab_binding=(sid,actor,[v['id'] for v in values]);db.commit();return 200,{'projects':values}
  if len(parts)==2 and parts[0]=='projects' and method=='GET':
   value=project(db,parts[1],sid,actor);handler._p12_collab_binding=(sid,actor,[parts[1]]);db.commit();return 200,{'project':value}
  if len(parts)==5 and parts[0]=='projects' and parts[2]=='handoffs' and parts[4]=='activity' and method=='GET':
   value=activity_link(db,handler,parts[1],parts[3],sid,actor);handler._p12_activity_link=(sid,actor,parts[1],parts[3]);db.commit();return 200,{'activityLink':value}
  if len(parts)==4 and parts[0]=='projects' and parts[2]=='handoffs' and method=='GET':
   value=handoff(db,parts[1],parts[3],sid,actor);handler._p12_handoff_binding=(sid,actor,parts[1],parts[3]);db.commit();return 200,{'handoff':value}
  if len(parts)==3 and parts[0]=='projects' and parts[2]=='versions' and method=='GET':
   value=versions(db,parts[1],sid,actor);handler._p12_versions_binding=(sid,actor,parts[1],value);db.commit();return 200,{'versions':value}
  if len(parts)==3 and parts[0]=='projects' and parts[2]=='current' and method=='GET':
   value=current_version(db,parts[1],sid,actor);handler._p12_version_binding=(sid,actor,parts[1]);db.commit();return 200,{'current':value}
  if len(parts)==4 and parts[0]=='projects' and parts[2]=='proposals' and method=='GET':
   value=proposal(db,parts[1],parts[3],sid,actor);handler._p12_proposal_binding=(sid,actor,parts[1],parts[3]);db.commit();return 200,{'proposal':value}
  if parts==['invitations'] and method=='GET':
   rows=db.execute("SELECT id,project_id,sender_session,status FROM phase12_collab_invites WHERE recipient_session=? AND recipient_id=? ORDER BY rowid",(sid,actor['owner'])).fetchall();db.commit();return 200,{'invitations':[{'id':r['id'],'projectId':r['project_id'],'senderSessionId':r['sender_session'],'status':r['status']} for r in rows]}
  if method!='POST':bad('not_found','Collaboration route unavailable.',404)
  data=handler.body()
  if len(parts)==4 and parts[0]=='projects' and parts[2:]==['handoffs','preview']:
   reqid(data);selection(data);project(db,parts[1],sid,actor)
   recipients=db.execute("SELECT session_id FROM phase12_collab_members WHERE project_id=? AND status='active' AND session_id!=?",(parts[1],sid)).fetchall()
   if len(recipients)!=1:bad('recipient_unavailable','An active second creator is required.')
   value=eligible_material(sid,data['materialId'],data['version'])
   from . import phase12_collab_grants
   ids=data.get('contributionGrantIds',[])
   if not isinstance(ids,list) or len(ids)>20 or any(not isinstance(i,str) or not REQUEST.fullmatch(i) for i in ids) or len(set(ids))!=len(ids):bad('invalid_request','Invalid grant selection.',422)
   contributions=[phase12_collab_grants.projection(db,i,parts[1],sid,recipients[0]['session_id']) for i in ids]
   handler._p12_preview_grants=(sid,actor,parts[1],recipients[0]['session_id'],ids)
   handler._p12_handoff_preview=(sid,actor,parts[1],data['materialId'],data['version'],recipients[0]['session_id'])
   db.commit();return 200,{'preview':{'material':value,'questions':data['questions'],'recipientSessionId':recipients[0]['session_id'],'contributions':contributions}}
  fp,old=receipt(db,sid,actor,data,method,path)
  if old:
   if old['kind']=='project':result={'project':project(db,old['id'],sid,actor)};handler._p12_collab_binding=(sid,actor,[old['id']])
   elif old['kind']=='handoff':
    result={'handoff':handoff(db,old['project'],old['id'],sid,actor)};handler._p12_handoff_binding=(sid,actor,old['project'],old['id'])
   elif old['kind']=='activity_link':
    result={'activityLink':activity_link(db,handler,old['project'],old['handoff'],sid,actor)};handler._p12_activity_link=(sid,actor,old['project'],old['handoff'])
   elif old['kind']=='version':
    value=current_version(db,old['project'],sid,actor)
    if value['version']!=old['version']:bad('version_conflict','The selected version is no longer current.')
    result={'current':value};handler._p12_version_binding=(sid,actor,old['project'])
   elif old['kind']=='withdrawal':
    project(db,old['project'],sid,actor);result={'withdrawal':{'handoffId':old['id'],'status':'withdrawn'}};handler._p12_collab_binding=(sid,actor,[old['project']])
   elif old['kind']=='proposal':
    result={'proposal':proposal(db,old['project'],old['id'],sid,actor)};handler._p12_proposal_binding=(sid,actor,old['project'],old['id'])
   else:
    r=db.execute('SELECT * FROM phase12_collab_invites WHERE id=?',(old['id'],)).fetchone()
    if not r or (r['recipient_session']!=sid and r['sender_session']!=sid):bad('not_found','Invitation unavailable.',404)
    result={'invitation':{'id':r['id'],'projectId':r['project_id'],'recipientSessionId':r['recipient_session'],'status':r['status']}}
   db.commit();return 200,result
  if parts==['projects']:
   if set(data)!={'requestId','title'} or not isinstance(data['title'],str) or not 1<=len(data['title'].strip())<=160:bad('invalid_request','Invalid project.',422)
   pid=store.ident();db.execute("INSERT INTO phase12_collab_projects VALUES(?,?,?,?,'active')",(pid,sid,actor['owner'],data['title'].strip()));db.execute("INSERT INTO phase12_collab_members VALUES(?,?,?,'owner','active')",(pid,sid,actor['owner']));save_receipt(db,sid,actor,data,fp,{'kind':'project','id':pid});result={'project':project(db,pid,sid,actor)};status=201
  elif len(parts)==3 and parts[0]=='projects' and parts[2]=='invitations':
   if set(data)!={'requestId','recipientSessionId'} or not isinstance(data['recipientSessionId'],str):bad('invalid_request','Invalid recipient.',422)
   p=project(db,parts[1],sid,actor)
   if p['role']!='owner':bad('forbidden','Only the project owner can invite.',403)
   target=data['recipientSessionId'];session=store.get('session',target)
   recipients=db.execute("SELECT DISTINCT owner_id FROM credentials WHERE session_id=? AND role='creator'",(target,)).fetchall()
   if target==sid or not session or not lifecycle.active(session) or len(recipients)!=1 or recipients[0]['owner_id']==actor['owner']:bad('recipient_unavailable','Recipient unavailable.')
   if db.execute("SELECT 1 FROM phase12_collab_members WHERE project_id=? AND status='active' AND role='member'",(parts[1],)).fetchone():bad('membership_full','The project already has another creator.')
   if db.execute("SELECT 1 FROM phase12_collab_invites WHERE project_id=? AND recipient_session=? AND status='pending'",(parts[1],target)).fetchone():bad('invitation_pending','An invitation is already pending.')
   iid=store.ident();db.execute("INSERT INTO phase12_collab_invites VALUES(?,?,?,?,?,'pending')",(iid,parts[1],sid,target,recipients[0]['owner_id']));save_receipt(db,sid,actor,data,fp,{'kind':'invitation','id':iid});result={'invitation':{'id':iid,'projectId':parts[1],'recipientSessionId':target,'status':'pending'}};status=201
  elif len(parts)==3 and parts[0]=='invitations' and parts[2] in ('accept','decline'):
   if set(data)!={'requestId'}:bad('invalid_request','Invalid invitation action.',422)
   row=db.execute('SELECT * FROM phase12_collab_invites WHERE id=?',(parts[1],)).fetchone()
   if not row or row['recipient_session']!=sid or row['recipient_id']!=actor['owner']:bad('not_found','Invitation unavailable.',404)
   if row['status']!='pending':bad('invalid_transition','Invitation is no longer pending.')
   if parts[2]=='accept':
    if db.execute("SELECT 1 FROM phase12_collab_members WHERE project_id=? AND status='active' AND role='member'",(row['project_id'],)).fetchone():bad('membership_full','The project already has another creator.')
    owner=store.get('session',row['sender_session'])
    if not owner or not lifecycle.active(owner):bad('recipient_unavailable','Sender session unavailable.')
    db.execute("INSERT INTO phase12_collab_members VALUES(?,?,?,'member','active') ON CONFLICT(project_id,session_id,actor_id) DO UPDATE SET status='active'",(row['project_id'],sid,actor['owner']))
   status_text='accepted' if parts[2]=='accept' else 'declined';db.execute('UPDATE phase12_collab_invites SET status=? WHERE id=?',(status_text,row['id']));save_receipt(db,sid,actor,data,fp,{'kind':'invitation','id':row['id']});result={'invitation':{'id':row['id'],'projectId':row['project_id'],'recipientSessionId':sid,'status':status_text}};status=200
  elif len(parts)==3 and parts[0]=='projects' and parts[2]=='handoffs':
   selection(data);p=project(db,parts[1],sid,actor)
   recipients=db.execute("SELECT session_id FROM phase12_collab_members WHERE project_id=? AND status='active' AND session_id!=?",(parts[1],sid)).fetchall()
   if len(recipients)!=1:bad('recipient_unavailable','An active second creator is required.')
   if 'replacesHandoffId' in data:
    if not isinstance(data['replacesHandoffId'],str):bad('invalid_request','Invalid replacement.',422)
    previous=handoff(db,parts[1],data['replacesHandoffId'],sid,actor)
    if previous['senderSessionId']!=sid:bad('forbidden','Only the original sender can offer an update.',403)
   current=eligible_material(sid,data['materialId'],data['version']);ident=store.ident()
   from . import phase12_collab_grants
   ids=data.get('contributionGrantIds',[])
   if not isinstance(ids,list) or len(ids)>20 or any(not isinstance(i,str) or not REQUEST.fullmatch(i) for i in ids) or len(set(ids))!=len(ids):bad('invalid_request','Invalid grant selection.',422)
   for gid in ids:
    phase12_collab_grants.projection(db,gid,parts[1],sid,recipients[0]['session_id']);db.execute('INSERT INTO phase12_collab_handoff_grants VALUES(?,?)',(ident,gid))
   if 'replacesHandoffId' in data:db.execute('INSERT INTO phase12_collab_replacements VALUES(?,?)',(ident,data['replacesHandoffId']))
   db.execute("INSERT INTO phase12_collab_handoffs VALUES(?,?,?,?,?,?,?,?, 'offered')",(ident,parts[1],sid,recipients[0]['session_id'],data['materialId'],data['version'],canonical(current),canonical(data['questions'])))
   save_receipt(db,sid,actor,data,fp,{'kind':'handoff','id':ident,'project':parts[1]});result={'handoff':handoff(db,parts[1],ident,sid,actor)};handler._p12_handoff_binding=(sid,actor,parts[1],ident);status=201
  elif len(parts)==5 and parts[0]=='projects' and parts[2]=='handoffs' and parts[4]=='accept':
   if set(data)!={'requestId'}:bad('invalid_request','Invalid handoff action.',422)
   value=handoff(db,parts[1],parts[3],sid,actor)
   if value['recipientSessionId']!=sid:bad('forbidden','Only the recipient can accept.',403)
   if value['status']!='offered':bad('invalid_transition','Handoff is not awaiting acceptance.')
   db.execute("UPDATE phase12_collab_handoffs SET state='accepted' WHERE id=?",(parts[3],))
   if not db.execute('SELECT 1 FROM phase12_collab_versions WHERE project_id=?',(parts[1],)).fetchone():db.execute('INSERT INTO phase12_collab_versions VALUES(?,?,?,?,NULL)',(parts[1],1,parts[3],value['material']['body']))
   save_receipt(db,sid,actor,data,fp,{'kind':'handoff','id':parts[3],'project':parts[1]});result={'handoff':handoff(db,parts[1],parts[3],sid,actor)};handler._p12_handoff_binding=(sid,actor,parts[1],parts[3]);status=200
  elif len(parts)==5 and parts[0]=='projects' and parts[2]=='handoffs' and parts[4]=='activity':
   if set(data)!={'requestId','activityId'} or not isinstance(data['activityId'],str) or not REQUEST.fullmatch(data['activityId']):bad('invalid_request','An existing activity ID is required.',422)
   value=handoff(db,parts[1],parts[3],sid,actor)
   if value['status']!='accepted' or value['recipientSessionId']!=sid:bad('forbidden','Only the recipient can link an accepted handoff.',403)
   from . import phase11,http
   a=phase11.load(db,data['activityId'])
   if not a or a['sessionId']!=sid or not phase11.basis_available(db,a) or not phase11.active_session(db,a['basisSessionId']):bad('source_unavailable','Activity unavailable.')
   phase11._owner(handler,http,a)
   if db.execute('SELECT 1 FROM phase12_collab_activity_links WHERE activity_id=? OR (project_id=? AND handoff_id=? AND session_id=?)',(a['id'],parts[1],parts[3],sid)).fetchone():bad('link_exists','Activity or handoff already linked.')
   db.execute('INSERT INTO phase12_collab_activity_links VALUES(?,?,?,?)',(a['id'],parts[1],parts[3],sid))
   save_receipt(db,sid,actor,data,fp,{'kind':'activity_link','project':parts[1],'handoff':parts[3]});result={'activityLink':activity_link(db,handler,parts[1],parts[3],sid,actor)};handler._p12_activity_link=(sid,actor,parts[1],parts[3]);status=201
  elif len(parts)==5 and parts[0]=='projects' and parts[2]=='handoffs' and parts[4]=='select':
   if set(data)!={'requestId','expectedProjectVersion'} or type(data['expectedProjectVersion']) is not int:bad('invalid_request','Expected project version required.',422)
   p=project(db,parts[1],sid,actor)
   if p['role']!='owner':bad('forbidden','Only the responsible editor can select an update.',403)
   value=handoff(db,parts[1],parts[3],sid,actor);current=current_version(db,parts[1],sid,actor)
   if value['status']!='accepted' or value['replacesHandoffId']!=current['handoffId']:bad('invalid_transition','An accepted update of the current handoff is required.')
   if current['version']!=data['expectedProjectVersion']:bad('version_conflict','Accepted project version changed.')
   number=current['version']+1;db.execute('INSERT INTO phase12_collab_versions VALUES(?,?,?,?,NULL)',(parts[1],number,parts[3],value['material']['body']))
   db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.type')='audience_handoff' AND json_extract(ref,'$.projectId')=? AND state IN ('queued','running','complete')",(parts[1],))
   save_receipt(db,sid,actor,data,fp,{'kind':'version','project':parts[1],'version':number});result={'current':current_version(db,parts[1],sid,actor)};handler._p12_version_binding=(sid,actor,parts[1]);status=200
  elif len(parts)==5 and parts[0]=='projects' and parts[2]=='handoffs' and parts[4]=='withdraw':
   if set(data)!={'requestId'}:bad('invalid_request','Invalid handoff action.',422)
   project(db,parts[1],sid,actor)
   row=db.execute('SELECT * FROM phase12_collab_handoffs WHERE id=? AND project_id=?',(parts[3],parts[1])).fetchone()
   if not row or row['sender_session']!=sid:bad('not_found','Handoff unavailable.',404)
   if row['state']=='withdrawn':bad('invalid_transition','Handoff already withdrawn.')
   db.execute("UPDATE phase12_collab_handoffs SET state='withdrawn' WHERE id=?",(parts[3],))
   db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.type') IN ('handoff','audience_handoff') AND json_extract(ref,'$.handoffId')=? AND state IN ('queued','running','complete')",(parts[3],))
   save_receipt(db,sid,actor,data,fp,{'kind':'withdrawal','id':parts[3],'project':parts[1]});result={'withdrawal':{'handoffId':parts[3],'status':'withdrawn'}};handler._p12_collab_binding=(sid,actor,[parts[1]]);status=200
  elif len(parts)==3 and parts[0]=='projects' and parts[2]=='proposals':
   if not {'requestId','handoffId','baseVersion','body'}<=set(data) or set(data)-{'requestId','handoffId','baseVersion','body','contributionGrantIds'} or not isinstance(data['handoffId'],str) or type(data['baseVersion']) is not int or not isinstance(data['body'],str) or not 1<=len(data['body'].strip())<=12000:bad('invalid_request','Invalid proposal.',422)
   source=handoff(db,parts[1],data['handoffId'],sid,actor);current=current_version(db,parts[1],sid,actor)
   if source['status']!='accepted' or source['recipientSessionId']!=sid:bad('forbidden','Only the accepted handoff recipient can propose.',403)
   proposal_attribution_rights(db,data['handoffId'])
   if current['handoffId']!=data['handoffId'] or current['version']!=data['baseVersion']:bad('version_conflict','The accepted version changed.')
   ident=store.ident();db.execute("INSERT INTO phase12_collab_proposals VALUES(?,?,?,?,?,?,'pending',NULL)",(ident,parts[1],data['handoffId'],sid,data['baseVersion'],data['body']))
   ids=data.get('contributionGrantIds',[])
   if not isinstance(ids,list) or len(ids)>20 or any(not isinstance(i,str) or not REQUEST.fullmatch(i) for i in ids) or len(set(ids))!=len(ids):bad('invalid_request','Invalid grant selection.',422)
   from . import phase12_collab_grants
   owner_session=db.execute('SELECT owner_session FROM phase12_collab_projects WHERE id=?',(parts[1],)).fetchone()['owner_session']
   for gid in ids:
    phase12_collab_grants.projection(db,gid,parts[1],sid,owner_session);db.execute('INSERT INTO phase12_collab_proposal_grants VALUES(?,?)',(ident,gid))
   proposal_grant_attribution_rights(db,ident)
   save_receipt(db,sid,actor,data,fp,{'kind':'proposal','id':ident,'project':parts[1]});result={'proposal':proposal(db,parts[1],ident,sid,actor)};handler._p12_proposal_binding=(sid,actor,parts[1],ident);status=201
  elif len(parts)==5 and parts[0]=='projects' and parts[2]=='proposals' and parts[4] in ('preview','incorporate','return'):
   action=parts[4];p=project(db,parts[1],sid,actor)
   if p['role']!='owner':bad('forbidden','Only the responsible editor can review.',403)
   value=proposal(db,parts[1],parts[3],sid,actor);current=current_version(db,parts[1],sid,actor)
   if value['status']!='pending':bad('invalid_transition','Proposal is no longer pending.')
   if action=='preview':
    if set(data)!={'requestId'}:bad('invalid_request','Invalid preview.',422)
    handler._p12_proposal_binding=(sid,actor,parts[1],parts[3]);handler._p12_version_binding=(sid,actor,parts[1]);db.commit();return 200,{'proposal':value,'current':current,'conflict':value['baseVersion']!=current['version']}
   if action=='return':
    if set(data)!={'requestId','reason'} or not isinstance(data['reason'],str) or not 1<=len(data['reason'].strip())<=1000:bad('invalid_request','A return reason is required.',422)
    db.execute("UPDATE phase12_collab_proposals SET state='returned',reason=? WHERE id=?",(data['reason'],parts[3]))
   else:
    if set(data)!={'requestId','expectedVersion'} or type(data['expectedVersion']) is not int:bad('invalid_request','Expected version is required.',422)
    if current['version']!=data['expectedVersion'] or value['baseVersion']!=current['version'] or value['handoffId']!=current['handoffId']:bad('version_conflict','The accepted version changed.')
    db.execute('INSERT INTO phase12_collab_versions VALUES(?,?,?,?,?)',(parts[1],current['version']+1,value['handoffId'],value['body'],parts[3]));db.execute("UPDATE phase12_collab_proposals SET state='incorporated' WHERE id=?",(parts[3],))
    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.type')='audience_handoff' AND json_extract(ref,'$.projectId')=? AND state IN ('queued','running','complete')",(parts[1],))
   save_receipt(db,sid,actor,data,fp,{'kind':'proposal','id':parts[3],'project':parts[1]});result={'proposal':proposal(db,parts[1],parts[3],sid,actor)};handler._p12_proposal_binding=(sid,actor,parts[1],parts[3]);status=200
  elif len(parts)==4 and parts[0]=='projects' and parts[2]=='members' and parts[3]=='revoke':
   if set(data)!={'requestId','sessionId'} or not isinstance(data['sessionId'],str):bad('invalid_request','Invalid member.',422)
   p=project(db,parts[1],sid,actor)
   if p['role']!='owner':bad('forbidden','Only the owner can revoke membership.',403)
   result_row=db.execute("SELECT * FROM phase12_collab_members WHERE project_id=? AND session_id=? AND role='member' AND status='active'",(parts[1],data['sessionId'])).fetchone()
   if not result_row:bad('not_found','Member unavailable.',404)
   db.execute("UPDATE phase12_collab_members SET status='revoked' WHERE project_id=? AND session_id=? AND actor_id=?",(parts[1],data['sessionId'],result_row['actor_id']))
   db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.type') IN ('handoff','audience_handoff') AND json_extract(ref,'$.projectId')=? AND state IN ('queued','running','complete')",(parts[1],))
   # Receipt reprojects owner access; published history is not deleted.
   save_receipt(db,sid,actor,data,fp,{'kind':'project','id':parts[1]});result={'project':project(db,parts[1],sid,actor)};status=200
  else:bad('not_found','Collaboration route unavailable.',404)
  if 'project' in result:handler._p12_collab_binding=(sid,actor,[result['project']['id']])
  db.commit();return status,result
