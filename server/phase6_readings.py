"""Explicit viewer readings and creator-reviewed exact presentations."""
from __future__ import annotations
import json
from urllib.parse import urlparse
from . import store, phase6 as p

def tomb(v):return {'id':v['id'],'revision':v['revision'],'available':False,'reason':'unavailable'}
def reading_ok(db,h,sid,v):return bool(v and v['status']=='submitted' and p.source_ok(db,h,sid,v['sourceRef']))
def reading_dto(db,h,sid,v):
    if v['status']=='withdrawn' or not p.source_ok(db,h,sid,v['sourceRef']):return tomb(v)
    return {k:x for k,x in v.items() if not k.startswith('_')}
def getref(h,r):
    p.keys(h,r,('id','revision'));p.text(h,r['id'],128)
    if type(r['revision']) is not int or r['revision']<1:p.fail(h)
def eligible(db,h,sid,r,public=False):
    v=p.load(db,'p6_reading',r['id'],sid)
    return v if reading_ok(db,h,sid,v) and v['revision']==r['revision'] and (not public or v['consent']['publicQuotation']) else None

def version_ok(db,h,sid,version):
    for item in version['items']:
        v=eligible(db,h,sid,item['reading'],True)
        if not v or v['consent']['attribution']!=item['attribution']:return False
    return True

def presentation(db,h,sid,v):
    result={k:v[k] for k in ('id','revision','status','currentVersion','approvedVersion','presentedVersion')}
    result['versions']=[{**x,'eligible':True} if version_ok(db,h,sid,x) else {'number':x['number'],'eligible':False} for x in v['versions']]
    return result

def grouping(db,h,sid,v):
    current=all(eligible(db,h,sid,r) for r in v['inputRefs'])
    if current:return {k:v[k] for k in ('id','revision','groups','ungrouped')} | {'reasoningStatus':'current'}
    groups=[{'readings':[r for r in g['readings'] if eligible(db,h,sid,r)]} for g in v['groups']]
    return {'id':v['id'],'revision':v['revision'],'groups':groups,'ungrouped':[r for r in v['ungrouped'] if eligible(db,h,sid,r)],'reasoningStatus':'pending'}

def version_input(db,h,sid,d):
    p.text(h,d['title'],200);items=d['items']
    if not isinstance(items,list) or not 1<=len(items)<=100:p.fail(h)
    seen=set()
    for item in items:
        p.keys(h,item,('reading','attribution'));getref(h,item['reading']);v=eligible(db,h,sid,item['reading'],True)
        if not v:p.fail(h,'reference_unavailable',409)
        if item['attribution']!=v['consent']['attribution']:p.fail(h,'forbidden',403)
        if item['reading']['id'] in seen:p.fail(h)
        seen.add(item['reading']['id'])
    return {'title':d['title'],'items':items,'createdAt':store.now()}

def replay(db,h,sid,owner,prev):
    result=json.loads(prev['result']);typ=result['type'];v=p.load(db,{'reading':'p6_reading','grouping':'p6_grouping','presentation':'p6_reading_presentation'}[typ],result['id'],sid)
    if not v:p.fail(h,'not_found',404)
    if typ=='reading':p.own(h,v,owner);return {'reading':reading_dto(db,h,sid,v)}
    if typ=='grouping':return {'grouping':grouping(db,h,sid,v)}
    return {'presentation':presentation(db,h,sid,v)}

def public(handler,h,sid):
    with store.LOCK,store.connect() as db:
        values=[v for v in p.rows(db,'p6_reading_presentation',sid) if v['status']=='presented']
        values.sort(key=lambda x:(x.get('presentedAt',''),x['id']),reverse=True)
        result=None
        if values:
            v=values[0];ver=next((x for x in v['versions'] if x['number']==v['presentedVersion']),None)
            if ver and v['approvedVersion']==v['presentedVersion']==v['currentVersion'] and version_ok(db,h,sid,ver):
                entries=[]
                for item in ver['items']:
                    r=eligible(db,h,sid,item['reading'],True)
                    entries.append({'text':r['text'],'reason':r['reason'],'attribution':item['attribution'],'sourceRef':r['sourceRef']})
                result={'id':v['id'],'version':ver['number'],'title':ver['title'],'items':entries}
        handler.send(200,{'presentation':result})

def route(handler,h,sid,a,parts,method):
    name=parts[0];owner=a['owner'];viewer=name=='readings'
    p.role(h,a,'viewer' if viewer else 'creator')
    if method=='GET':
        with store.LOCK,store.connect() as db:
            if name=='readings' and len(parts)==1:
                handler.send(200,p.page(handler,h,[reading_dto(db,h,sid,v) for v in p.rows(db,'p6_reading',sid) if v['_owner']==owner]));return
            if name=='reading-review' and len(parts)==1:
                handler.send(200,p.page(handler,h,[reading_dto(db,h,sid,v) for v in p.rows(db,'p6_reading',sid) if v['status'] in ('submitted','withdrawn')]));return
            if name=='reading-groups' and len(parts)==2:
                v=p.load(db,'p6_grouping',parts[1],sid)
                if not v:p.fail(h,'not_found',404)
                handler.send(200,{'grouping':grouping(db,h,sid,v)});return
            if name=='reading-presentations' and len(parts)==1:
                handler.send(200,p.page(handler,h,[presentation(db,h,sid,v) for v in p.rows(db,'p6_reading_presentation',sid)]));return
        p.fail(h,'not_found',404)
    if method not in ('POST','PATCH'):p.fail(h,'not_found',404)
    d=handler.body();p.rid(h,d.get('requestId'));fp=p.fingerprint(method,urlparse(handler.path).path,d)
    with store.LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            prev=p.check_receipt(db,h,sid,owner,d['requestId'],fp)
            if prev:
                out=replay(db,h,sid,owner,prev);status=prev['status'];db.commit();handler.send(status,out);return
            if not db.execute('SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role=?',(sid,owner,a['role'])).fetchone():p.fail(h,'unauthorized',401)
            now=store.now();status=200
            if name=='readings' and len(parts)==1 and method=='POST':
                p.keys(h,d,('requestId','sourceRef','text','reason'));p.ref(h,d['sourceRef']);p.text(h,d['text']);p.text(h,d['reason'])
                if d['sourceRef'] is None:p.fail(h)
                if not p.source_ok(db,h,sid,d['sourceRef']):p.fail(h,'reference_unavailable',409)
                v=p.insert(db,'p6_reading',sid,owner,{'status':'draft','sourceRef':d['sourceRef'],'text':d['text'],'reason':d['reason'],'consent':None,'createdAt':now,'updatedAt':now});status=201
                typ='reading';out={'reading':reading_dto(db,h,sid,v)}
            elif name=='readings' and len(parts)>=2:
                v=p.own(h,p.load(db,'p6_reading',parts[1],sid),owner);p.expect(h,v,d)
                if len(parts)==2 and method=='PATCH':
                    p.keys(h,d,('requestId','expectedRevision','sourceRef','text','reason'))
                    if v['status']!='draft':p.fail(h,'invalid_transition',409)
                    p.ref(h,d['sourceRef']);p.text(h,d['text']);p.text(h,d['reason'])
                    if d['sourceRef'] is None:p.fail(h)
                    if not p.source_ok(db,h,sid,d['sourceRef']):p.fail(h,'reference_unavailable',409)
                    for k in ('sourceRef','text','reason'):v[k]=d[k]
                elif len(parts)==3 and parts[2]=='submit' and method=='POST':
                    p.keys(h,d,('requestId','expectedRevision','consent'));c=d['consent'];p.keys(h,c,('review','publicQuotation','crossSession','attribution'))
                    if c['review'] is not True or type(c['publicQuotation']) is not bool or type(c['crossSession']) is not bool:p.fail(h)
                    attr=c['attribution'];p.keys(h,attr,('mode','label'))
                    if attr['mode'] not in ('name','pseudonym','unattributed'):p.fail(h)
                    if attr['mode']=='unattributed':
                        if attr['label'] is not None:p.fail(h)
                    else:p.text(h,attr['label'],100)
                    if v['status']!='draft':p.fail(h,'invalid_transition',409)
                    if not p.source_ok(db,h,sid,v['sourceRef']):p.fail(h,'reference_unavailable',409)
                    v['consent']=c;v['status']='submitted'
                elif len(parts)==3 and parts[2]=='withdraw' and method=='POST':
                    p.keys(h,d,('requestId','expectedRevision'))
                    if v['status']!='submitted':p.fail(h,'invalid_transition',409)
                    v['status']='withdrawn'
                else:p.fail(h,'not_found',404)
                v['updatedAt']=now;v=p.save(db,'p6_reading',sid,v);typ='reading';out={'reading':reading_dto(db,h,sid,v)}
            elif name=='reading-groups' and len(parts)==1 and method=='POST':
                p.keys(h,d,('requestId','groups'));groups=d['groups']
                if not isinstance(groups,list) or len(groups)>100:p.fail(h)
                current=[v for v in p.rows(db,'p6_reading',sid) if reading_ok(db,h,sid,v)]
                if len(current)>1000:p.fail(h,'limit_reached',409)
                allrefs=[{'id':v['id'],'revision':v['revision']} for v in current];seen=set()
                for group in groups:
                    p.keys(h,group,('label','rationale','disagreement','readings'))
                    for k in ('label','rationale','disagreement'):p.text(h,group[k],100 if k=='label' else 4000,empty=k=='disagreement')
                    if not isinstance(group['readings'],list) or not 1<=len(group['readings'])<=100:p.fail(h)
                    for r in group['readings']:
                        getref(h,r)
                        if r['id'] in seen:p.fail(h)
                        if not eligible(db,h,sid,r):p.fail(h,'reference_unavailable',409)
                        seen.add(r['id'])
                v=p.insert(db,'p6_grouping',sid,owner,{'groups':groups,'ungrouped':[r for r in allrefs if r['id'] not in seen],'inputRefs':allrefs});status=201;typ='grouping';out={'grouping':grouping(db,h,sid,v)}
            elif name=='reading-presentations' and len(parts)==1 and method=='POST':
                p.keys(h,d,('requestId','title','items'));ver=version_input(db,h,sid,d);ver['number']=1
                v=p.insert(db,'p6_reading_presentation',sid,owner,{'status':'draft','currentVersion':1,'approvedVersion':None,'presentedVersion':None,'versions':[ver]});status=201;typ='presentation';out={'presentation':presentation(db,h,sid,v)}
            elif name=='reading-presentations' and len(parts)==3 and method=='POST':
                v=p.load(db,'p6_reading_presentation',parts[1],sid)
                if not v:p.fail(h,'not_found',404)
                p.expect(h,v,d);action=parts[2]
                if action=='versions':
                    p.keys(h,d,('requestId','expectedRevision','title','items'));ver=version_input(db,h,sid,d);ver['number']=v['currentVersion']+1;v['versions'].append(ver);v.update(currentVersion=ver['number'],status='draft',approvedVersion=None,presentedVersion=None)
                elif action in ('approve','present','withdraw'):
                    p.keys(h,d,('requestId','expectedRevision','version'))
                    if type(d['version']) is not int or d['version']!=v['currentVersion']:p.fail(h,'stale_revision',409)
                    ver=next(x for x in v['versions'] if x['number']==d['version'])
                    if action=='withdraw':
                        if v['status']!='presented' or v['presentedVersion']!=d['version']:p.fail(h,'invalid_transition',409)
                        v.update(status='withdrawn',presentedVersion=None)
                    else:
                        if not version_ok(db,h,sid,ver):p.fail(h,'reference_unavailable',409)
                        if action=='approve':v.update(status='approved',approvedVersion=d['version'],presentedVersion=None)
                        else:
                            if v['status']!='approved' or v['approvedVersion']!=d['version']:p.fail(h,'invalid_transition',409)
                            v.update(status='presented',presentedVersion=d['version'],presentedAt=now)
                else:p.fail(h,'not_found',404)
                v=p.save(db,'p6_reading_presentation',sid,v);typ='presentation';out={'presentation':presentation(db,h,sid,v)}
            else:p.fail(h,'not_found',404)
            p.complete(db,sid,owner,d['requestId'],fp,status,{'type':typ,'id':v['id']});db.commit();handler.send(status,out)
        except BaseException:db.rollback();raise
