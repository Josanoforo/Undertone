"""Source-linked explicit claim history; PRIMARY mounts and supplies Context."""
import hashlib, json, re
from datetime import datetime, timezone
from . import store
from .phase10_common import Phase10Error, parse_ref

KIND='w22claim'; RECEIPT='w22claimreceipt'
def fail(code, message, status=422): raise Phase10Error(code,message,status)
def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def key(x):
    if not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',x): fail('invalid_request','Invalid identifier.')
    return x
def stamp(x):
    if not isinstance(x,str) or len(x)>40: fail('invalid_request','An ISO timestamp with timezone is required.')
    try:
        d=datetime.fromisoformat(x.replace('Z','+00:00'))
        if d.tzinfo is None: raise ValueError()
        return d.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except ValueError: fail('invalid_request','An ISO timestamp with timezone is required.')
def text(x,limit):
    if not isinstance(x,str) or not x.strip() or len(x)>limit or any(ord(c)<32 and c not in '\n\r\t' for c in x): fail('invalid_request','Invalid text.')
    try: x.encode('utf-8')
    except UnicodeError: fail('invalid_request','Invalid text.')
    return x.strip()
def _id(*args): return hashlib.sha256(canon(args).encode()).hexdigest()
def _load(db,sid,oid):
    row=db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?',(KIND,oid,sid)).fetchone()
    if not row: fail('not_found','Claim unavailable.',404)
    return dict(json.loads(row['data']),revision=row['revision'],owner=row['owner_id'])
def _visible(ctx,item):
    return (item['scope']=='creator' and ctx.actor.get('role')=='creator') or (item['scope']=='private' and item['owner']==ctx.actor['owner'])
def _guard(ctx,item):
    if not _visible(ctx,item) or item.get('forgotten'): fail('not_found','Claim unavailable.',404)
    ctx.resolve(item['sourceRefs'])
def _insert(db,kind,oid,sid,owner,value,revision=1):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',(kind,oid,sid,owner,revision,canon(value),store.now()))
def mutate(ctx, body):
    """Create, correct or forget; actor and source authorization come from ctx."""
    if not isinstance(body,dict): fail('invalid_request','Invalid request.')
    action=body.get('action'); req=key(body.get('requestId')); owner=key(ctx.actor.get('owner')); sid=key(ctx.sid)
    if action not in ('create','correct','forget'): fail('invalid_request','Invalid action.')
    fields={'action','requestId','expectedRevision','scope','topic','claim','sourceRefs','validFrom','validUntil','eventTime','relations'} if action=='create' else ({'action','requestId','expectedRevision','claimId','claim','sourceRefs','validFrom','validUntil','eventTime'} if action=='correct' else {'action','requestId','expectedRevision','claimId'})
    if set(body)!=fields or type(body.get('expectedRevision')) is not int or body['expectedRevision']<0: fail('invalid_request','Invalid fields.')
    rid=_id(sid,owner,req); fp=_id(body)
    with ctx.lock, store.connect() as db:
        ctx.check_actor(); db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT data FROM objects WHERE kind=? AND id=? AND session_id=?',(RECEIPT,rid,sid)).fetchone()
        if old:
            receipt=json.loads(old['data'])
            if receipt['fingerprint']!=fp: fail('request_conflict','Request ID already used.',409)
            item=_load(db,sid,receipt['claimId'])
            if action=='forget': return {'operation':{'requestId':req,'state':'committed'},'forgotten':True}
            if item['revision']!=receipt['revision']: fail('stale_revision','Claim has changed.',409)
            _guard(ctx,item); return {'claim':_project(item),'operation':{'requestId':req,'state':'committed'}}
        if action=='create':
            if body['expectedRevision']!=0 or body['scope'] not in ('private','creator') or (body['scope']=='creator' and ctx.actor.get('role')!='creator'): fail('not_found','Claim unavailable.',404)
            oid=store.ident(); scope=body['scope']; topic=text(body['topic'],200); revision=1
        else:
            oid=key(body['claimId']); item=_load(db,sid,oid)
            if action!='forget': _guard(ctx,item)
            if item['owner']!=owner or item['scope']!='private': fail('not_found','Claim unavailable.',404)
            if item['revision']!=body['expectedRevision']: fail('stale_revision','Claim has changed.',409)
            scope=item['scope']; topic=item['topic']; revision=item['revision']+1
        if action=='forget':
            # Erase private text and references, including old versions; receipts carry no content.
            value={'id':oid,'scope':'private','forgotten':True}; db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=?',(canon(value),revision,KIND,oid,sid))
        else:
            refs=body['sourceRefs']
            if not isinstance(refs,list) or not 1<=len(refs)<=8: fail('invalid_request','Select source moments.')
            refs=[parse_ref(r) for r in refs]
            if any(r['sessionId']!=sid for r in refs) or len({canon(r) for r in refs})!=len(refs): fail('invalid_request','Invalid source moments.')
            ctx.resolve(refs)
            start=stamp(body['validFrom']); end=stamp(body['validUntil']) if body['validUntil'] is not None else None; event=stamp(body['eventTime'])
            if end is not None and end<=start: fail('invalid_request','Invalid validity interval.')
            relations=body['relations'] if action=='create' else item['relations']
            if not isinstance(relations,list) or len(relations)>8: fail('invalid_request','Invalid relations.')
            for rel in relations if action=='create' else []:
                if not isinstance(rel,dict) or set(rel)!={'type','claimId','revision'} or rel['type'] not in ('supersedes','disputes') or type(rel['revision']) is not int: fail('invalid_request','Invalid relation.')
                target=_load(db,sid,key(rel['claimId'])); _guard(ctx,target)
                if target['revision']!=rel['revision'] or target['topic']!=topic or (scope=='creator' and target['scope']!='creator'): fail('stale_revision','Relation unavailable or changed.',409)
            recorded=stamp(datetime.now(timezone.utc).isoformat()); value={'id':oid,'scope':scope,'topic':topic,'claim':text(body['claim'],4000),'sourceRefs':refs,'validFrom':start,'validUntil':end,'eventTime':event,'recordedAt':recorded,'relations':relations}
            if action=='correct':
                # Preserve old version for known-at queries; private forgetting removes it below.
                value['previous']=item.get('previous',[])+[{k:v for k,v in item.items() if k not in ('owner','revision','previous')} | {'revision':item['revision']}]
                if len(value['previous'])>20: fail('capacity','Private history is full.',409)
                db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND session_id=?',(canon(value),revision,KIND,oid,sid))
            else: _insert(db,KIND,oid,sid,owner,value)
        _insert(db,RECEIPT,rid,sid,owner,{'fingerprint':fp,'claimId':oid,'revision':revision})
        db.commit()
        if action=='forget': return {'operation':{'requestId':req,'state':'committed'},'forgotten':True}
        return {'claim':_project(dict(value,owner=owner,revision=revision)),'operation':{'requestId':req,'state':'committed'}}
def _project(item): return {k:item[k] for k in ('id','revision','scope','topic','claim','sourceRefs','validFrom','validUntil','eventTime','recordedAt','relations')}
def query(ctx,topic,asOfEventTime,knownAt):
    topic=text(topic,200); event=stamp(asOfEventTime); known=stamp(knownAt)
    candidates=[]; histories=[]; recorded=[]
    with ctx.lock, store.connect() as db:
        ctx.check_actor()
        rows=db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND session_id=? ORDER BY id LIMIT 1001',(KIND,ctx.sid)).fetchall()
        if len(rows)>1000: fail('capacity','Too many claims to query.',409)
        for row in rows:
            item=dict(json.loads(row['data']),revision=row['revision'],owner=row['owner_id'])
            if item.get('forgotten') or not _visible(ctx,item) or item.get('topic')!=topic: continue
            versions=item.get('previous',[])+[{k:v for k,v in item.items() if k!='previous'}]
            versions=[dict(v,owner=item['owner']) for v in versions if v['recordedAt']<=known]
            if not versions: continue
            selected=max(versions,key=lambda v:(v['recordedAt'],v['revision']))
            # Explicit replacement remains a replacement when its source expires
            # or is withdrawn. Keep only its relation internally, never its text
            # in the response. Current rights still guard every projected version.
            recorded.append(selected)
            try: _guard(ctx,selected)
            except Phase10Error: continue
            candidates.append(selected)
            for version in versions:
                if version['revision']==selected['revision']: continue
                try: _guard(ctx,version)
                except Phase10Error: continue
                histories.append((version,selected))
        if len(candidates)>1000: fail('capacity','Too many claims to query.',409)
        active=[x for x in candidates if x['validFrom']<=event and (x['validUntil'] is None or event<x['validUntil']) and x['eventTime']<=event]
        ids={(x['id'],x['revision']) for x in active}; superseded=set(); disputes=set()
        for x in recorded:
            if x['eventTime']>event or x['validFrom']>event: continue
            for rel in x['relations']:
                target=(rel['claimId'],rel['revision'])
                if target in ids:
                    if rel['type']=='supersedes': superseded.add(target)
                    elif x['validUntil'] is None or event<x['validUntil']:
                        disputes.update((target,(x['id'],x['revision'])))
        current=[x for x in active if (x['id'],x['revision']) not in superseded]
        # Known-at controls which version was recorded; it must not turn a
        # future event or a not-yet-valid claim into prior history.
        prior=[x for x in candidates if x not in current and x['eventTime']<=event and x['validFrom']<=event]
        projections=[]
        for x in prior:
            replaced_by=[{'claimId':other['id'],'revision':other['revision']} for other in candidates
                         if other['eventTime']<=event and other['validFrom']<=event
                         and any(r['type']=='supersedes' and (r['claimId'],r['revision'])==(x['id'],x['revision']) for r in other['relations'])]
            projections.append(dict(_project(x),priorReason='superseded' if (x['id'],x['revision']) in superseded else 'expired',replacedBy=replaced_by))
        for old,new in histories:
            if old['eventTime']<=event and old['validFrom']<=event:
                prior.append(old)
                projections.append(dict(_project(old),priorReason='corrected',replacedBy=[{'claimId':new['id'],'revision':new['revision']}]))
        result={'current':[_project(x) for x in current],'prior':projections,'disputed':[x['id'] for x in current if (x['id'],x['revision']) in disputes], 'unknown':not bool(current) or bool(disputes) or len(current)>1}
        # A final guard is required at the transport boundary under the same source lock.
        ctx.check_actor()
        for x in current+prior: _guard(ctx,x)
        return result


