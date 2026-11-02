"""Participant-controlled grants for exact collaboration handoff purposes."""
import json
from . import store,phase11,phase12_collaboration as collab

def migrate(db):
 db.execute("CREATE TABLE IF NOT EXISTS phase12_collab_grants (id TEXT PRIMARY KEY,project_id TEXT NOT NULL,session_id TEXT NOT NULL,recipient_session TEXT NOT NULL,activity_id TEXT NOT NULL,contribution_id TEXT NOT NULL,revision INTEGER NOT NULL,participant_id TEXT NOT NULL,author_id TEXT NOT NULL,purpose TEXT NOT NULL,attribution INTEGER NOT NULL,status TEXT NOT NULL)")
 db.execute("CREATE TABLE IF NOT EXISTS phase12_collab_handoff_grants (handoff_id TEXT NOT NULL,grant_id TEXT NOT NULL,PRIMARY KEY(handoff_id,grant_id))")

def projection(db,gid,pid,sid,recipient,audience=False):
 g=db.execute("SELECT * FROM phase12_collab_grants WHERE id=?",(gid,)).fetchone()
 if not g or g['status']!='active' or (g['project_id'],g['session_id'],g['recipient_session'])!=(pid,sid,recipient) or (audience and g['purpose']!='handoff_and_audience'):collab.bad('source_unavailable','Contribution grant unavailable.')
 activity=phase11.load(db,g['activity_id'])
 if not activity or activity['sessionId']!=sid or not phase11.basis_available(db,activity) or not phase11.active_session(db,activity['basisSessionId']) or not phase11.eligible(db,activity,{'id':g['contribution_id'],'revision':g['revision']}):collab.bad('source_unavailable','Contribution unavailable.')
 participant=db.execute("SELECT * FROM phase11_participants WHERE id=? AND activity_id=?",(g['participant_id'],g['activity_id'])).fetchone()
 if not participant or participant['origin_session']!=sid or participant['origin_owner']!=g['author_id'] or not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='viewer'",(sid,g['author_id'])).fetchone():collab.bad('source_unavailable','Author unavailable.')
 c=next((x for x in activity['contributions'] if x['id']==g['contribution_id'] and x['revision']==g['revision'] and x['participant']==g['participant_id']),None)
 if not c:collab.bad('source_unavailable','Contribution unavailable.')
 return {'grantId':gid,'activityId':g['activity_id'],'contributionId':g['contribution_id'],'revision':g['revision'],'text':c['text'],'attribution':c.get('attribution') if g['attribution'] and c.get('attributionAllowed') else None,'purpose':g['purpose']}

def handle(handler,sid,actor,method,parts):
 from . import http
 from urllib.parse import urlparse
 if actor['role']!='viewer' or method!='POST':collab.bad('forbidden','Participant capability required.',403)
 data=handler.body();collab.reqid(data);path=urlparse(handler.path).path
 with store.LOCK,store.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  if not phase11.current_credential(db,sid,'viewer',actor['owner'],handler._auth_token):collab.bad('not_found','Viewer unavailable.',404)
  fp,old=collab.receipt(db,sid,actor,data,method,path)
  if old:
   if old['kind']!='collab_grant':collab.bad('request_conflict','Request ID already used.')
   g=db.execute('SELECT * FROM phase12_collab_grants WHERE id=? AND author_id=? AND session_id=?',(old['id'],actor['owner'],sid)).fetchone()
   if not g:collab.bad('not_found','Grant unavailable.',404)
   activity=phase11.load(db,g['activity_id'])
   if not activity or phase11._participant(handler,http,db,activity,actor)!=g['participant_id']:collab.bad('forbidden','Author capability required.',403)
  elif not parts:
   fields={'requestId','projectId','recipientSessionId','activityId','contributionId','revision','purpose','allowAttribution'}
   if set(data)!=fields or any(not isinstance(data[k],str) or not collab.REQUEST.fullmatch(data[k]) for k in ('projectId','recipientSessionId','activityId','contributionId')) or type(data['revision']) is not int or data['revision']<1 or data['purpose'] not in ('handoff','handoff_and_audience') or type(data['allowAttribution']) is not bool:collab.bad('invalid_request','Invalid contribution grant.',422)
   members=db.execute("SELECT m.session_id FROM phase12_collab_members m JOIN credentials c ON c.session_id=m.session_id AND c.owner_id=m.actor_id AND c.role='creator' WHERE m.project_id=? AND m.status='active'",(data['projectId'],)).fetchall()
   if {x['session_id'] for x in members}!={sid,data['recipientSessionId']} or sid==data['recipientSessionId']:collab.bad('recipient_unavailable','Project recipient unavailable.')
   a=phase11.load(db,data['activityId'])
   if not a or a['sessionId']!=sid or not phase11.basis_available(db,a) or not phase11.active_session(db,a['basisSessionId']):collab.bad('source_unavailable','Activity unavailable.')
   participant=phase11._participant(handler,http,db,a,actor)
   identity=db.execute('SELECT * FROM phase11_participants WHERE id=?',(participant,)).fetchone()
   if not identity or identity['origin_session']!=sid or identity['origin_owner']!=actor['owner']:collab.bad('forbidden','Original author required.',403)
   c=next((x for x in a['contributions'] if x['id']==data['contributionId'] and x['revision']==data['revision'] and x['participant']==participant),None)
   if not c or not phase11.eligible(db,a,{'id':c['id'],'revision':c['revision']}):collab.bad('source_unavailable','Contribution unavailable.')
   ident=store.ident();db.execute("INSERT INTO phase12_collab_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,'active')",(ident,data['projectId'],sid,data['recipientSessionId'],a['id'],c['id'],c['revision'],participant,actor['owner'],data['purpose'],int(data['allowAttribution'])))
   collab.save_receipt(db,sid,actor,data,fp,{'kind':'collab_grant','id':ident});g=db.execute('SELECT * FROM phase12_collab_grants WHERE id=?',(ident,)).fetchone()
  else:
   if len(parts)!=2 or parts[1] not in ('revoke','withdraw-attribution') or set(data)!={'requestId'}:collab.bad('invalid_request','Invalid grant action.',422)
   g=db.execute('SELECT * FROM phase12_collab_grants WHERE id=? AND session_id=? AND author_id=?',(parts[0],sid,actor['owner'])).fetchone()
   a=phase11.load(db,g['activity_id']) if g else None
   if not g or not a or phase11._participant(handler,http,db,a,actor)!=g['participant_id']:collab.bad('not_found','Grant unavailable.',404)
   if parts[1]=='revoke':
    db.execute("UPDATE phase12_collab_grants SET status='revoked' WHERE id=?",(g['id'],))
    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.handoffId') IN (SELECT handoff_id FROM phase12_collab_handoff_grants WHERE grant_id=?) AND state IN ('queued','running','complete')",(g['id'],))
   else:
    db.execute('UPDATE phase12_collab_grants SET attribution=0 WHERE id=?',(g['id'],))
    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.handoffId') IN (SELECT handoff_id FROM phase12_collab_handoff_grants WHERE grant_id=?) AND state IN ('queued','running','complete')",(g['id'],))
   db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.projectId') IN (SELECT p.project_id FROM phase12_collab_proposals p JOIN phase12_collab_proposal_grants pg ON pg.proposal_id=p.id WHERE pg.grant_id=?) AND state IN ('queued','running','complete')",(g['id'],))
   collab.save_receipt(db,sid,actor,data,fp,{'kind':'collab_grant','id':g['id']});g=db.execute('SELECT * FROM phase12_collab_grants WHERE id=?',(g['id'],)).fetchone()
  result={'grant':{'id':g['id'],'projectId':g['project_id'],'recipientSessionId':g['recipient_session'],'activityId':g['activity_id'],'contributionId':g['contribution_id'],'revision':g['revision'],'purpose':g['purpose'],'allowAttribution':bool(g['attribution']),'status':g['status']}}
  handler._p12_collab_grant_binding=(sid,actor,g['id'])
  db.commit();return 200,result
