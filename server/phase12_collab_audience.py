"""Explicit collaboration presentation, audience admission and private references."""
from urllib.parse import urlparse,parse_qs
import re
from . import store,phase11,phase12_collaboration as c,phase12_collab_grants as grants

def migrate(db):
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_agreements(project_id TEXT NOT NULL,session_id TEXT NOT NULL,version INTEGER NOT NULL,PRIMARY KEY(project_id,session_id))')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_publications(project_id TEXT NOT NULL,session_id TEXT NOT NULL,version INTEGER NOT NULL,destination TEXT NOT NULL,status TEXT NOT NULL,PRIMARY KEY(project_id,session_id))')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_admissions(project_id TEXT NOT NULL,session_id TEXT NOT NULL,actor_id TEXT NOT NULL,version INTEGER NOT NULL,PRIMARY KEY(project_id,session_id,actor_id))')
 db.execute('CREATE TABLE IF NOT EXISTS phase12_collab_refs(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,session_id TEXT NOT NULL,actor_id TEXT NOT NULL,version INTEGER NOT NULL)')

def safe_destination(value,pid,db):
 if not isinstance(value,dict):c.bad('invalid_request','Invalid destination.',422)
 if set(value)=={'kind','sessionId'} and value['kind']=='session' and isinstance(value['sessionId'],str):
  if not db.execute("SELECT 1 FROM phase12_collab_members WHERE project_id=? AND session_id=? AND status='active'",(pid,value['sessionId'])).fetchone():c.bad('invalid_request','Destination is not a project creator session.',422)
  return value
 if set(value)=={'kind','url'} and value['kind']=='recorded' and isinstance(value['url'],str) and len(value['url'])<=2048:
  try:u=urlparse(value['url']);host=(u.hostname or '').lower();port=u.port
  except ValueError:c.bad('invalid_request','Invalid recording URL.',422)
  base=u.scheme=='https' and not u.username and not u.password and port in (None,443) and not u.fragment and not any(ord(x)<32 for x in value['url'])
  query=parse_qs(u.query,keep_blank_values=True)
  if host in ('youtube.com','www.youtube.com'):valid=u.path=='/watch' and set(query)=={'v'} and len(query['v'])==1 and bool(re.fullmatch(r'[A-Za-z0-9_-]{11}',query['v'][0]))
  elif host=='youtu.be':valid=not u.query and bool(re.fullmatch(r'/[A-Za-z0-9_-]{11}',u.path))
  elif host in ('twitch.tv','www.twitch.tv'):valid=not u.query and bool(re.fullmatch(r'/videos/[0-9]{1,20}',u.path))
  elif host=='clips.twitch.tv':valid=not u.query and bool(re.fullmatch(r'/[A-Za-z0-9_-]{1,128}',u.path))
  else:valid=False
  if base and valid:return value
 c.bad('invalid_request','Destination must be an approved HTTPS recording or an active project session.',422)

def current(db,pid,sid):
 member=db.execute("SELECT actor_id FROM phase12_collab_members WHERE project_id=? AND session_id=? AND status='active'",(pid,sid)).fetchone()
 if not member:c.bad('source_unavailable','Project membership unavailable.')
 actor={'owner':member['actor_id'],'role':'creator'}
 return c.current_version(db,pid,sid,actor)

def publication(db,pid,sid,actor_id=None,require_admission=True):
 import json
 row=db.execute("SELECT * FROM phase12_collab_publications WHERE project_id=? AND session_id=? AND status='published'",(pid,sid)).fetchone()
 if not row:c.bad('source_unavailable','Audience presentation unavailable.')
 v=current(db,pid,sid)
 if v['version']!=row['version']:c.bad('source_unavailable','Accepted project version changed.')
 members=db.execute("SELECT session_id FROM phase12_collab_members WHERE project_id=? AND status='active'",(pid,)).fetchall()
 if len(members)!=2 or any(not db.execute('SELECT 1 FROM phase12_collab_agreements WHERE project_id=? AND session_id=? AND version=?',(pid,m['session_id'],v['version'])).fetchone() for m in members):c.bad('source_unavailable','Creator agreement unavailable.')
 hand=db.execute('SELECT * FROM phase12_collab_handoffs WHERE id=?',(v['handoffId'],)).fetchone()
 if not hand:c.bad('source_unavailable','Handoff unavailable.')
 values=[grants.projection(db,g['grant_id'],pid,hand['sender_session'],hand['recipient_session'],True) for g in db.execute('SELECT grant_id FROM phase12_collab_handoff_grants WHERE handoff_id=? ORDER BY rowid',(hand['id'],)).fetchall()]
 if v['proposalId']:values+=c.proposal_contributions(db,pid,v['proposalId'],True)
 if require_admission and not db.execute('SELECT 1 FROM phase12_collab_admissions WHERE project_id=? AND session_id=? AND actor_id=? AND version=?',(pid,sid,actor_id,v['version'])).fetchone():c.bad('forbidden','Explicit audience admission required.',403)
 destination=safe_destination(json.loads(row['destination']),pid,db)
 return {'projectId':pid,'version':v['version'],'handoffId':hand['id'],'handoffVersion':hand['version'],'body':v['body'],'contributions':values,'creators':[{'sessionId':m['session_id']} for m in members],'stages':[{'kind':'accepted_version','version':v['version'],'handoffId':hand['id']}],'destination':destination,'availability':'unknown'}

def handle(handler,sid,actor,method,parts):
 from urllib.parse import urlparse
 path=urlparse(handler.path).path
 with store.LOCK,store.connect() as db:
  db.execute('BEGIN IMMEDIATE')
  if not phase11.current_credential(db,sid,actor['role'],actor['owner'],handler._auth_token):c.bad('not_found','Session capability unavailable.',404)
  if actor['role']=='creator':
   c.auth(db,handler,sid,actor)
   if method!='POST' or len(parts)!=3 or parts[0]!='projects' or parts[2] not in ('agree','publish','unpublish'):c.bad('not_found','Route unavailable.',404)
   pid=parts[1];c.project(db,pid,sid,actor);data=handler.body();fp,old=c.receipt(db,sid,actor,data,method,path)
   if old:
    if old['kind']!='audience_action':c.bad('request_conflict','Request ID already used.')
    if old['action']=='publish':value=publication(db,pid,sid,require_admission=False);handler._p12_audience_binding=(sid,actor,pid,False);db.commit();return 200,{'publication':value}
    db.commit();return 200,{'action':{'projectId':pid,'status':old['action']}}
   action=parts[2]
   if action=='unpublish':
    if set(data)!={'requestId'}:c.bad('invalid_request','Invalid action.',422)
    db.execute("UPDATE phase12_collab_publications SET status='withdrawn' WHERE project_id=? AND session_id=?",(pid,sid))
    db.execute('DELETE FROM phase12_collab_admissions WHERE project_id=? AND session_id=?',(pid,sid))
    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE session_id=? AND json_extract(ref,'$.type')='audience_handoff' AND json_extract(ref,'$.projectId')=? AND state IN ('queued','running','complete')",(sid,pid))
   else:
    expected={'requestId','version'} if action=='agree' else {'requestId','version','destination'}
    if set(data)!=expected or type(data['version']) is not int:c.bad('invalid_request','Invalid version action.',422)
    v=c.current_version(db,pid,sid,actor)
    if v['version']!=data['version']:c.bad('version_conflict','Accepted project version changed.')
    if action=='agree':db.execute('INSERT INTO phase12_collab_agreements VALUES(?,?,?) ON CONFLICT(project_id,session_id) DO UPDATE SET version=excluded.version',(pid,sid,v['version']))
    else:
     destination=safe_destination(data['destination'],pid,db)
     db.execute("INSERT INTO phase12_collab_publications VALUES(?,?,?,?,'published') ON CONFLICT(project_id,session_id) DO UPDATE SET version=excluded.version,destination=excluded.destination,status='published'",(pid,sid,v['version'],c.canonical(destination)))
     value=publication(db,pid,sid,require_admission=False);db.execute('DELETE FROM phase12_collab_admissions WHERE project_id=? AND session_id=?',(pid,sid));handler._p12_audience_binding=(sid,actor,pid,False)
   c.save_receipt(db,sid,actor,data,fp,{'kind':'audience_action','id':pid,'action':action});db.commit();return 200,{'publication':value} if action=='publish' else {'action':{'projectId':pid,'status':action}}
  if actor['role']!='viewer':c.bad('forbidden','Viewer capability required.',403)
  if method=='GET' and len(parts)==2 and parts[0]=='receipts':
   c.reqid({'requestId':parts[1]})
   row=db.execute('SELECT result FROM phase12_collab_receipts WHERE session_id=? AND actor_id=? AND request_id=?',(sid,actor['owner'],parts[1])).fetchone()
   # The empty reference binding rechecks the current credential at final send.
   handler._p12_reference_binding=(sid,actor,[])
   db.commit();return 200,{'receipt':{'requestId':parts[1],'state':'committed' if row else 'unknown','result':c.receipt_metadata(row)}}
  if method=='GET' and parts==['routes']:
   values=[]
   for row in db.execute("SELECT project_id FROM phase12_collab_publications WHERE session_id=? AND status='published'",(sid,)).fetchall():
    try:
     v=publication(db,row['project_id'],sid,require_admission=False);values.append({'projectId':v['projectId'],'version':v['version'],'creators':v['creators'],'stages':v['stages'],'destination':v['destination'],'availability':'unknown'})
    except c.Phase10Error:continue
   handler._p12_audience_list=(sid,actor,[v['projectId'] for v in values]);db.commit();return 200,{'routes':values}
  if len(parts)==2 and parts[0]=='routes' and method=='GET':
   value=publication(db,parts[1],sid,actor['owner']);handler._p12_audience_binding=(sid,actor,parts[1],True);db.commit();return 200,{'publication':value}
  if method=='GET' and parts==['references']:
   refs=[]
   for row in db.execute('SELECT * FROM phase12_collab_refs WHERE session_id=? AND actor_id=? ORDER BY rowid',(sid,actor['owner'])).fetchall():
    try:
     v=publication(db,row['project_id'],sid,actor['owner'])
     if v['version']==row['version']:refs.append({'id':row['id'],'projectId':row['project_id'],'version':row['version']})
    except c.Phase10Error:continue
   handler._p12_reference_binding=(sid,actor,refs);db.commit();return 200,{'references':refs}
  if method=='GET' and len(parts)==2 and parts[0]=='references':
   row=db.execute('SELECT * FROM phase12_collab_refs WHERE id=? AND session_id=? AND actor_id=?',(parts[1],sid,actor['owner'])).fetchone()
   if not row:c.bad('not_found','Reference unavailable.',404)
   value=publication(db,row['project_id'],sid,actor['owner'])
   if value['version']!=row['version']:c.bad('source_unavailable','Reference version unavailable.')
   handler._p12_audience_binding=(sid,actor,row['project_id'],True);db.commit();return 200,{'publication':value}
  if method!='POST':c.bad('not_found','Route unavailable.',404)
  data=handler.body();fp,old=c.receipt(db,sid,actor,data,method,path)
  if old:
   if old['kind']=='audience_admit':
    value=publication(db,old['id'],sid,actor['owner']);handler._p12_audience_binding=(sid,actor,old['id'],True);db.commit();return 200,{'publication':value}
   if old['kind']=='audience_reference':
    row=db.execute('SELECT * FROM phase12_collab_refs WHERE id=? AND session_id=? AND actor_id=?',(old['id'],sid,actor['owner'])).fetchone()
    if not row:c.bad('not_found','Reference unavailable.',404)
    v=publication(db,row['project_id'],sid,actor['owner'])
    if v['version']!=row['version']:c.bad('source_unavailable','Reference version unavailable.')
    handler._p12_reference_binding=(sid,actor,[{'id':row['id'],'projectId':row['project_id'],'version':row['version']}]);db.commit();return 200,{'reference':{'id':row['id'],'projectId':row['project_id'],'version':row['version']}}
   c.bad('request_conflict','Request ID already used.')
  if len(parts)==3 and parts[0]=='routes' and parts[2]=='admit':
   if set(data)!={'requestId','version'} or type(data['version']) is not int:c.bad('invalid_request','Invalid admission.',422)
   value=publication(db,parts[1],sid,require_admission=False)
   if data['version']!=value['version']:c.bad('version_conflict','Presentation changed.')
   db.execute('INSERT INTO phase12_collab_admissions VALUES(?,?,?,?) ON CONFLICT(project_id,session_id,actor_id) DO UPDATE SET version=excluded.version',(parts[1],sid,actor['owner'],data['version']))
   c.save_receipt(db,sid,actor,data,fp,{'kind':'audience_admit','id':parts[1]});handler._p12_audience_binding=(sid,actor,parts[1],True);db.commit();return 200,{'publication':value}
  if parts==['references']:
   if set(data)!={'requestId','projectId','version'} or not isinstance(data['projectId'],str) or type(data['version']) is not int:c.bad('invalid_request','Invalid reference.',422)
   value=publication(db,data['projectId'],sid,actor['owner'])
   if value['version']!=data['version']:c.bad('version_conflict','Presentation changed.')
   ident=store.ident();db.execute('INSERT INTO phase12_collab_refs VALUES(?,?,?,?,?)',(ident,data['projectId'],sid,actor['owner'],data['version']))
   c.save_receipt(db,sid,actor,data,fp,{'kind':'audience_reference','id':ident});ref={'id':ident,'projectId':data['projectId'],'version':data['version']};handler._p12_reference_binding=(sid,actor,[ref]);db.commit();return 201,{'reference':ref}
  c.bad('not_found','Route unavailable.',404)
