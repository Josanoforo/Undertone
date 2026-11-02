"""Typed translation projections and explicit participant-to-creator grants."""
import hashlib, hmac, json, re, sys
from . import store, phase11
from .phase10_common import Phase10Error

def fail(code='stale_context', message='The selected source or grant is unavailable.', status=409):
    raise Phase10Error(code,message,status)
def key(v): return isinstance(v,str) and bool(re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',v))
def canon(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS phase12_grants(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,activity_id TEXT NOT NULL,contribution_id TEXT NOT NULL,contribution_revision INTEGER NOT NULL,participant_id TEXT NOT NULL,author_owner TEXT NOT NULL,recipient_owner TEXT NOT NULL,owner_hash TEXT NOT NULL,language TEXT NOT NULL,attribution INTEGER NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS phase12_grant_receipts(session_id TEXT NOT NULL,actor_id TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,grant_id TEXT NOT NULL,PRIMARY KEY(session_id,actor_id,request_id))')
    db.execute('CREATE TABLE IF NOT EXISTS phase12_recaps(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,activity_id TEXT NOT NULL,version INTEGER NOT NULL,fragment_ids TEXT NOT NULL,language TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS phase12_recap_receipts(session_id TEXT NOT NULL,actor_id TEXT NOT NULL,request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,recap_id TEXT NOT NULL,PRIMARY KEY(session_id,actor_id,request_id))')

def valid_selection(ref):
    if not isinstance(ref,dict):fail('invalid_request','Invalid typed selection.',422)
    t=ref.get('type')
    fields={'audience_handoff':{'type','projectId','handoffId','version','projectVersion'},'handoff':{'type','projectId','handoffId','version'},'contribution':{'type','activityId','contributionId','revision','grantId','grantRevision'},'studio':{'type','materialId','version'},'activity_fragment':{'type','activityId','version','fragmentId'},'activity_stage':{'type','activityId','version','stageRevision'},'activity_recap':{'type','activityId','recapId','revision'},'exchange_question':{'type','questionId','revision'},'exchange_answer':{'type','questionId','revision'}}
    if t not in fields or set(ref)!=fields[t]:fail('invalid_request','Invalid typed selection.',422)
    for k,v in ref.items():
        if k in ('revision','grantRevision','version','stageRevision','projectVersion'):
            if type(v) is not int or v<(0 if k in ('version','stageRevision') else 1):fail('invalid_request','Invalid version.',422)
        elif k!='type' and not key(v):fail('invalid_request','Invalid source identity.',422)
    return dict(ref)

def resolve(row,selection):
    from .http import p10_public_material
    sid=row['session_id']; t=selection['type']
    with store.connect() as db:
        if t in ('exchange_question','exchange_answer'):
            from . import phase12_jobs
            q=store.get('w13question',selection['questionId'],sid)
            own=db.execute("SELECT owner_id FROM objects WHERE kind='w13question' AND id=? AND session_id=?",(selection['questionId'],sid)).fetchone()
            if not q or not own or q.get('_revision')!=selection['revision'] or q.get('status')=='withdrawn':fail()
            public=q.get('status')=='selected' and (q.get('answer') or {}).get('approved') is True
            if row['role']!='creator' and row['actor_id']!=own['owner_id'] and not public:fail()
            if t=='exchange_answer' and not public:fail()
            if q.get('ref'):
                nested=dict(row);nested['ref']=canon(q['ref']);phase12_jobs.rights(nested)
            value=q if t=='exchange_question' else q['answer']
            text=value['text'];meta={'type':t,'questionId':q['id'],'revision':q['_revision'],'language':value['language'],'ref':q.get('ref'),'purpose':'exchange'}
        elif t=='audience_handoff':
            from . import phase12_collab_audience
            if row['role']!='viewer':fail()
            item=phase12_collab_audience.publication(db,selection['projectId'],sid,row['actor_id'])
            if item['handoffId']!=selection['handoffId'] or item['handoffVersion']!=selection['version'] or item['version']!=selection['projectVersion']:fail()
            text='\n\n'.join([item['body']]+[v['text'] for v in item['contributions']]);meta={'type':'audience_handoff','projectId':selection['projectId'],'handoffId':selection['handoffId'],'version':selection['version'],'projectVersion':selection['projectVersion'],'purpose':'audience'}
        elif t=='handoff':
            from . import phase12_collaboration
            if row['role']!='creator':fail()
            actor={'owner':row['actor_id'],'role':row['role']}
            item=phase12_collaboration.handoff(db,selection['projectId'],selection['handoffId'],sid,actor)
            if item['status']!='accepted' or item['version']!=selection['version']:fail()
            text='\n\n'.join([item['material']['body']]+[v['text'] for v in item['contributions']]);meta={'type':'handoff','projectId':selection['projectId'],'handoffId':selection['handoffId'],'version':selection['version'],'purpose':'creator_collaboration'}
        elif t=='studio':
            session=store.get('session',sid); m=store.get('p10material',selection['materialId'],sid)
            public=p10_public_material(session.get('joinCode',''),selection['materialId']) if session else None
            if not m or not public or public['version']!=selection['version']:fail()
            text=public['body']; meta={'type':'studio','materialId':m['id'],'version':public['version'],'purpose':'audience','refs':public['refs']}
        else:
            a=phase11.load(db,selection['activityId'])
            if not a or a['sessionId']!=sid or not phase11.basis_available(db,a) or not phase11.active_session(db,a['basisSessionId']) or not phase11.valid_config(a['config']):fail()
            if t=='contribution':
                g=db.execute('SELECT * FROM phase12_grants WHERE id=?',(selection['grantId'],)).fetchone()
                if not g or g['status']!='active' or g['session_id']!=sid or g['activity_id']!=a['id'] or g['contribution_id']!=selection['contributionId'] or g['contribution_revision']!=selection['revision'] or g['revision']!=selection['grantRevision'] or row['role']!='creator' or row['actor_id']!=g['recipient_owner'] or not hmac.compare_digest(g['owner_hash'],a['_owner_hash']):fail()
                c=next((v for v in a['contributions'] if v['id']==g['contribution_id'] and v['revision']==g['contribution_revision']),None)
                if not c or c['participant']!=g['participant_id'] or not phase11.eligible(db,a,{'id':c['id'],'revision':c['revision']}):fail()
                participant=db.execute('SELECT origin_owner,origin_session FROM phase11_participants WHERE id=? AND activity_id=?',(c['participant'],a['id'])).fetchone()
                if not participant or participant['origin_owner']!=g['author_owner'] or participant['origin_session']!=sid or not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='viewer'",(sid,g['author_owner'])).fetchone():fail()
                text=c['text']; meta={'type':'contribution','activityId':a['id'],'contributionId':c['id'],'revision':c['revision'],'grantId':g['id'],'grantRevision':g['revision'],'purpose':'creator_review','speaker':c.get('attribution') if g['attribution'] and c.get('attributionAllowed') else None,'language':g['language']}
            elif t=='activity_recap':
                recap=db.execute('SELECT * FROM phase12_recaps WHERE id=? AND activity_id=? AND session_id=?',(selection['recapId'],a['id'],sid)).fetchone()
                if not recap or recap['status']!='active' or recap['revision']!=selection['revision'] or a['status']!='closed' or a['currentVersion']!=recap['version'] or a.get('publishedVersion')!=recap['version']:fail()
                version=next((v for v in a['versions'] if v['version']==recap['version']),None)
                if not version:fail()
                available={v['id']:v for v in phase11.project_version(db,a,version)['fragments']}
                ids=json.loads(recap['fragment_ids'])
                if not ids or any(i not in available for i in ids):fail()
                text='\n\n'.join(available[i]['text'] for i in ids)
                meta={'type':t,'activityId':a['id'],'recapId':recap['id'],'revision':recap['revision'],'version':recap['version'],'fragmentIds':ids,'purpose':'audience','language':recap['language']}
            else:
                if a['status']!='active' or not a['published'] or a.get('publishedVersion')!=selection['version'] or a['currentVersion']!=selection['version']:fail()
                version=next((v for v in a['versions'] if v['version']==selection['version']),None)
                if not version:fail()
                projected=phase11.project_version(db,a,version)
                if t=='activity_fragment':
                    fragment=next((v for v in projected['fragments'] if v['id']==selection['fragmentId']),None)
                    if not fragment:fail()
                    text=fragment['text'];meta={'type':t,'activityId':a['id'],'version':selection['version'],'fragmentId':fragment['id'],'purpose':'audience','contributionRefs':fragment['contributionRefs']}
                else:
                    if a.get('stageRevision',0)!=selection['stageRevision']:fail()
                    text=a['config']['stages'][a.get('stageIndex',0)];meta={'type':t,'activityId':a['id'],'version':selection['version'],'stageRevision':selection['stageRevision'],'purpose':'audience'}
    if not isinstance(text,str) or not 1<=len(text.strip())<=6000:fail('source_size','Source text is unavailable or too long.',422)
    return {'language':meta.get('language'),'projection':meta},{'text':text,'alignment':None,'captureRunId':None},selection

def grant(handler,sid,actor,method,parts):
    from . import http
    if method=='GET' and actor['role']=='creator' and len(parts)==1 and key(parts[0]):
        with store.LOCK,store.connect() as db:
            if not phase11.current_credential(db,sid,actor['role'],actor['owner'],handler._auth_token):fail('unauthorized','Capability unavailable.',401)
            a=phase11.load(db,parts[0])
            if not a or a['sessionId']!=sid or not phase11.basis_available(db,a) or not phase11.active_session(db,a['basisSessionId']):fail()
            phase11._owner(handler,http,a)
            values=[]
            for g in db.execute("SELECT * FROM phase12_grants WHERE activity_id=? AND session_id=? AND recipient_owner=? AND status='active'",(a['id'],sid,actor['owner'])).fetchall():
                c=next((v for v in a['contributions'] if v['id']==g['contribution_id'] and v['revision']==g['contribution_revision']),None)
                if c and phase11.eligible(db,a,{'id':c['id'],'revision':c['revision']}) and db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='viewer'",(sid,g['author_owner'])).fetchone():
                    values.append({'id':g['id'],'revision':g['revision'],'activityId':a['id'],'contributionId':c['id'],'contributionRevision':c['revision'],'sourceLanguage':g['language'],'recipient':'session_creator','purpose':'creator_review','allowAttribution':bool(g['attribution'] and c.get('attributionAllowed'))})
            return 200,{'grants':values}
    if actor['role']!='viewer':fail('forbidden','Only the author may grant or revoke.',403)
    if method!='POST':fail('not_found','Grant route unavailable.',404)
    body=handler.body()
    if not isinstance(body,dict) or not key(body.get('requestId')):fail('invalid_request','Valid requestId required.',422)
    creating=not parts
    fields={'requestId','activityId','contributionId','revision','sourceLanguage','allowAttribution'} if creating else {'requestId'}
    if set(body)!=fields or (not creating and (len(parts)!=2 or parts[1]!='revoke' or not key(parts[0]))):fail('invalid_request','Invalid grant request.',422)
    fp=hashlib.sha256(canon([parts,body]).encode()).hexdigest()
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not phase11.current_credential(db,sid,actor['role'],actor['owner'],handler._auth_token):fail('unauthorized','Capability unavailable.',401)
        old=db.execute('SELECT * FROM phase12_grant_receipts WHERE session_id=? AND actor_id=? AND request_id=?',(sid,actor['owner'],body['requestId'])).fetchone()
        if old:
            if old['fingerprint']!=fp:fail('request_conflict','Request ID already used.',409)
            g=db.execute('SELECT * FROM phase12_grants WHERE id=?',(old['grant_id'],)).fetchone()
            if not g:fail()
            a=phase11.load(db,g['activity_id'])
            if not a or a['sessionId']!=sid or not phase11.basis_available(db,a) or not phase11.active_session(db,a['basisSessionId']) or phase11._participant(handler,http,db,a,actor)!=g['participant_id']:fail()
            if g['author_owner']!=actor['owner']:fail('forbidden','Author capability required.',403)
            if g['status']=='active' and not phase11.eligible(db,a,{'id':g['contribution_id'],'revision':g['contribution_revision']}):fail()
        elif creating:
            if not key(body['activityId']) or not key(body['contributionId']) or type(body['revision']) is not int or body['revision']<1 or body['sourceLanguage'] not in ('en','es') or type(body['allowAttribution']) is not bool:fail('invalid_request','Invalid grant fields.',422)
            a=phase11.load(db,body['activityId'])
            if not a or a['sessionId']!=sid or not phase11.basis_available(db,a) or not phase11.active_session(db,a['basisSessionId']):fail()
            participant=phase11._participant(handler,http,db,a,actor)
            owner=db.execute('SELECT origin_session,origin_owner FROM phase11_participants WHERE id=? AND activity_id=?',(participant,a['id'])).fetchone()
            if not owner or owner['origin_session']!=sid or owner['origin_owner']!=actor['owner']:fail('forbidden','Only the original author may grant.',403)
            c=next((x for x in a['contributions'] if x['id']==body['contributionId'] and x['revision']==body['revision'] and x['participant']==participant),None)
            if not c or not phase11.eligible(db,a,{'id':c['id'],'revision':c['revision']}):fail()
            creators=db.execute("SELECT DISTINCT owner_id FROM credentials WHERE session_id=? AND role='creator'",(sid,)).fetchall()
            if len(creators)!=1:fail()
            ident=store.ident();db.execute('INSERT INTO phase12_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,sid,a['id'],c['id'],c['revision'],participant,actor['owner'],creators[0]['owner_id'],a['_owner_hash'],body['sourceLanguage'],int(body['allowAttribution']),1,'active'))
            db.execute('INSERT INTO phase12_grant_receipts VALUES(?,?,?,?,?)',(sid,actor['owner'],body['requestId'],fp,ident));g=db.execute('SELECT * FROM phase12_grants WHERE id=?',(ident,)).fetchone()
        else:
            g=db.execute('SELECT * FROM phase12_grants WHERE id=? AND session_id=? AND author_owner=?',(parts[0],sid,actor['owner'])).fetchone()
            if not g:fail('not_found','Grant unavailable.',404)
            a=phase11.load(db,g['activity_id'])
            if not a or phase11._participant(handler,http,db,a,actor)!=g['participant_id']:fail('forbidden','Author capability required.',403)
            db.execute("UPDATE phase12_grants SET status='revoked',revision=revision+1 WHERE id=? AND status='active'",(g['id'],))
            db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE json_extract(ref,'$.grantId')=? AND state IN ('queued','running','complete')",(g['id'],))
            db.execute('INSERT INTO phase12_grant_receipts VALUES(?,?,?,?,?)',(sid,actor['owner'],body['requestId'],fp,g['id']));g=db.execute('SELECT * FROM phase12_grants WHERE id=?',(g['id'],)).fetchone()
        db.commit()
        return 200,{'grant':{'id':g['id'],'revision':g['revision'],'status':g['status'],'activityId':g['activity_id'],'contributionId':g['contribution_id'],'contributionRevision':g['contribution_revision'],'sourceLanguage':g['language'],'recipient':'session_creator','purpose':'creator_review','allowAttribution':bool(g['attribution'])}}


def recaps(handler,sid,actor,method,parts):
    from . import http
    if method=='GET' and len(parts)==1 and key(parts[0]):
        with store.LOCK,store.connect() as db:
            if not phase11.current_credential(db,sid,actor['role'],actor['owner'],handler._auth_token):fail('unauthorized','Capability unavailable.',401)
            values=[]
            for r in db.execute("SELECT * FROM phase12_recaps WHERE session_id=? AND activity_id=? AND status='active'",(sid,parts[0])).fetchall():
                selection={'type':'activity_recap','activityId':r['activity_id'],'recapId':r['id'],'revision':r['revision']}
                try:resolve({'session_id':sid,'role':actor['role'],'actor_id':actor['owner']},selection)
                except Phase10Error:continue
                values.append({'id':r['id'],'revision':r['revision'],'activityId':r['activity_id'],'version':r['version'],'sourceLanguage':r['language'],'fragmentIds':json.loads(r['fragment_ids']),'purpose':'audience'})
            return 200,{'recaps':values}
    if method!='POST' or actor['role']!='creator':fail('forbidden','Creator review is required.',403)
    body=handler.body()
    if not isinstance(body,dict) or not key(body.get('requestId')):fail('invalid_request','Valid requestId required.',422)
    create=not parts
    fields={'requestId','activityId','version','fragmentIds','sourceLanguage','confirmAudience'} if create else {'requestId'}
    if set(body)!=fields or (not create and (len(parts)!=2 or parts[1]!='withdraw' or not key(parts[0]))):fail('invalid_request','Invalid recap request.',422)
    fp=hashlib.sha256(canon([parts,body]).encode()).hexdigest()
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not phase11.current_credential(db,sid,actor['role'],actor['owner'],handler._auth_token):fail('unauthorized','Capability unavailable.',401)
        old=db.execute('SELECT * FROM phase12_recap_receipts WHERE session_id=? AND actor_id=? AND request_id=?',(sid,actor['owner'],body['requestId'])).fetchone()
        if old:
            if old['fingerprint']!=fp:fail('request_conflict','Request ID already used.',409)
            recap=db.execute('SELECT * FROM phase12_recaps WHERE id=?',(old['recap_id'],)).fetchone()
            if not recap:fail()
            activity=phase11.load(db,recap['activity_id'])
            if not activity or activity['sessionId']!=sid:fail()
            phase11._owner(handler,http,activity)
        elif create:
            if not key(body['activityId']) or type(body['version']) is not int or body['version']<0 or body['sourceLanguage'] not in ('en','es') or body['confirmAudience'] is not True or not isinstance(body['fragmentIds'],list) or not 1<=len(body['fragmentIds'])<=20 or any(not key(i) for i in body['fragmentIds']) or len(set(body['fragmentIds']))!=len(body['fragmentIds']):fail('invalid_request','Invalid recap review.',422)
            activity=phase11.load(db,body['activityId'])
            if not activity or activity['sessionId']!=sid or not phase11.basis_available(db,activity) or not phase11.active_session(db,activity['basisSessionId']):fail()
            phase11._owner(handler,http,activity)
            if activity['status']!='closed' or activity['currentVersion']!=body['version'] or activity.get('publishedVersion')!=body['version']:fail()
            v=next((v for v in activity['versions'] if v['version']==body['version']),None)
            available={f['id']:f for f in phase11.project_version(db,activity,v)['fragments']} if v else {}
            if any(i not in available for i in body['fragmentIds']):fail()
            if len('\n\n'.join(available[i]['text'] for i in body['fragmentIds']))>6000:fail('source_size','Recap exceeds translation limit.',422)
            ident=store.ident();db.execute('INSERT INTO phase12_recaps VALUES(?,?,?,?,?,?,1,?)',(ident,sid,activity['id'],body['version'],canon(body['fragmentIds']),body['sourceLanguage'],'active'))
            db.execute('INSERT INTO phase12_recap_receipts VALUES(?,?,?,?,?)',(sid,actor['owner'],body['requestId'],fp,ident));recap=db.execute('SELECT * FROM phase12_recaps WHERE id=?',(ident,)).fetchone()
        else:
            recap=db.execute('SELECT * FROM phase12_recaps WHERE id=? AND session_id=?',(parts[0],sid)).fetchone()
            activity=phase11.load(db,recap['activity_id']) if recap else None
            if not activity or activity['sessionId']!=sid:fail()
            phase11._owner(handler,http,activity)
            db.execute("UPDATE phase12_recaps SET status='withdrawn',revision=revision+1 WHERE id=? AND status='active'",(recap['id'],))
            db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE source_id=? AND state IN ('queued','running','complete')",(recap['id'],))
            db.execute('INSERT INTO phase12_recap_receipts VALUES(?,?,?,?,?)',(sid,actor['owner'],body['requestId'],fp,recap['id']));recap=db.execute('SELECT * FROM phase12_recaps WHERE id=?',(recap['id'],)).fetchone()
        db.commit()
        return 200,{'recap':{'id':recap['id'],'revision':recap['revision'],'status':recap['status'],'activityId':recap['activity_id'],'version':recap['version'],'sourceLanguage':recap['language'],'fragmentIds':json.loads(recap['fragment_ids']),'purpose':'audience'}}
