"""Finite reviewed continuation. All entry points require an authenticated Context."""
import copy
import json
from . import lifecycle
from .waves15_formats import store
from contextlib import contextmanager
from .phase10_common import Phase10Error, parse_ref

F, C, T = 'w15format', 'w15formatcontribution', 'w15formattransfer'
G, A, W = 'w16sourcegrant', 'w15continuationconsent', 'w16work'

def fail(message='Continuation unavailable.', status=409):
    raise Phase10Error('not_found' if status == 404 else 'forbidden' if status == 403 else 'stale_context' if status == 409 else 'invalid_field', message, status)

def require_fields(body, names):
    if not isinstance(body, dict) or set(body) != set(names): fail('Invalid continuation fields.', 400)

def creator(ctx):
    ctx.check_actor()
    if ctx.actor.get('role') != 'creator': fail('Creator access required.', 403)

def get(kind, oid, sid=None):
    obj = store.get(kind, oid, sid)
    if not obj: fail(status=404)
    return obj

def check_revision(obj, rev):
    if type(rev) is not int or rev != obj.get('_revision'): fail('The item changed.')

def active_session(sid):
    obj = store.get('session', sid, sid)
    if not obj or not lifecycle.active(obj): fail()

def valid_ref(ref):
    ref = parse_ref(ref)
    active_session(ref['sessionId'])
    src = store.get('source', ref['sourceId'], ref['sessionId'])
    moment = store.get('p10moment', ref['momentId'], ref['sessionId'])
    from .http import expired
    if not src or src.get('status') != 'active' or expired(src) or not src.get('audienceVisible') or src.get('_revision') != ref['sourceRevision'] or not moment or moment.get('ref') != ref: fail()
    if moment.get('alignment', {}).get('origin') == 'capture' or src.get('p10Frame'):
        from .phase10_timeline import frame_moment
        frame = frame_moment(src)
        if any(frame.get(k) != moment.get(k) for k in ('ref', 'alignment', 'captureRunId')): fail()
    return {'eligible': True, 'ref': ref, 'source': src, 'moment': moment}

def validate_snapshot(snap, require_approved=False):
    sid, target = snap['sourceSessionId'], snap['targetSessionId']
    active_session(sid); active_session(target)
    fmt = get(F, snap['formatId'], sid)
    if fmt['_revision'] != snap['formatRevision'] or fmt.get('decision') != snap['decision']: fail()
    for entry in snap['refs']:
        ref = entry['ref']; valid_ref(ref)
        grant = get(G, entry['grantId'], sid)
        if grant.get('status') != 'active' or grant.get('formatId') != fmt['id'] or grant.get('targetSessionId') != target or grant.get('ref') != ref: fail()
    for entry in snap['contributions']:
        c = get(C, entry['id'], sid)
        if c['_revision'] != entry['revision'] or c.get('status') != 'accepted' or c.get('formatId') != fmt['id']: fail()
        consent = get(A, entry['consentId'], sid)
        if consent.get('status') != 'active' or consent.get('contributionId') != c['id'] or consent.get('contributionRevision') != c['_revision'] or consent.get('targetSessionId') != target: fail()
    if require_approved:
        m = get('p10material', snap['materialId'], sid)
        if m.get('currentVersion') != snap['materialVersion'] or m.get('approvedVersion') != snap['materialVersion'] or m.get('status') not in ('approved','published') or m.get('continuationWorkId') != snap['workId'] or m.get('refs') != [entry['ref'] for entry in snap['refs']]: fail()
    return fmt

def validate_offer(offer, allowed=('offered','accepted')):
    if offer.get('kind') != 'reviewed-continuation-v1' or offer.get('status') not in allowed or not isinstance(offer.get('snapshot'), dict): fail()
    snap = offer['snapshot']
    if offer.get('sourceSessionId') != snap.get('sourceSessionId') or offer.get('targetSessionId') != snap.get('targetSessionId'): fail()
    validate_snapshot(snap, True)
    if offer.get('w18Record'):
        from . import waves18_records
        waves18_records.guard_offer(offer)
    return snap

def guard_delivery(session_id, material):
    """Validate continuation lineage at delivery, without inventing an actor."""
    with store.LOCK:
        work_id = material.get('continuationWorkId')
        transfer_id = material.get('continuationTransferId')
        if not work_id and not transfer_id:
            if 'continuationWorkId' in material or 'continuationTransferId' in material: fail()
            return True
        live = get('p10material', material.get('id'), session_id)
        if live != material: fail()
        if work_id:
            work = get(W, work_id, session_id)
            if work.get('materialId') != material.get('id') or work['snapshot'].get('sourceSessionId') != session_id: fail()
            validate_snapshot(work['snapshot'])
        if transfer_id:
            offer = get(T, transfer_id)
            if offer.get('targetSessionId') != session_id or offer.get('recipientMaterialId') != material.get('id'): fail()
            validate_offer(offer, ('accepted',))
        return True

def guard_material(ctx, material):
    with store.LOCK:
        ctx.check_actor()
        return guard_delivery(ctx.sid, material)

def guard_format(ctx, fmt):
    with store.LOCK:
        ctx.check_actor()
        transfer_id = fmt.get('continuationTransferId')
        if transfer_id:
            offer = get(T, transfer_id)
            if offer.get('targetSessionId') != ctx.sid or offer.get('recipientFormatId') != fmt.get('id'): fail()
            validate_offer(offer, ('accepted',))
        return True

def guard_offer(ctx, offer):
    with store.LOCK:
        ctx.check_actor()
        if ctx.sid not in (offer.get('sourceSessionId'), offer.get('targetSessionId')): fail(status=404)
        validate_offer(offer)
        return True

def guard_contribution(ctx, contribution):
    with store.LOCK:
        ctx.check_actor()
        fmt = get(F, contribution['formatId'], ctx.sid)
        guard_format(ctx, fmt)
        if contribution.get('continuationTransferId') != fmt.get('continuationTransferId'):
            if contribution.get('continuationTransferId'): fail()
        return True

def resolve_ref(ctx, ref):
    with store.LOCK:
        ctx.check_actor(); ref = parse_ref(ref)
        if ref['sessionId'] == ctx.sid: fail('Foreign continuation reference required.', 403)
        for fmt in store.all(F, ctx.sid):
            tid = fmt.get('continuationTransferId')
            if not tid: continue
            offer = store.get(T, tid)
            if not offer or offer.get('recipientFormatId') != fmt.get('id') or offer.get('targetSessionId') != ctx.sid: continue
            try:
                snap = validate_offer(offer, ('accepted',))
                if any(x['ref'] == ref for x in snap['refs']): return valid_ref(ref)
            except Phase10Error: continue
        fail()

def snapshot(ctx, fmt, body, extra_refs=()):
    target = body['targetSessionId']
    if not isinstance(target, str) or target == ctx.sid: fail('Invalid target.', 400)
    active_session(target); check_revision(fmt, body['revision'])
    guard_format(ctx, fmt)
    decision = fmt.get('decision')
    if not isinstance(decision, dict): fail('A current decision is required.')
    selected = body['contributions']
    if not isinstance(selected, list) or len(selected) > 50 or any(not isinstance(x, dict) or set(x) != {'id','revision','consentId'} for x in selected): fail('Invalid contribution selection.', 400)
    ids = [x['id'] for x in selected]
    if len(set(ids)) != len(ids) or not set(decision['reasonIds']) <= set(ids) or not set(decision['minorityIds']) <= set(ids): fail('Include every decision reason and minority.')
    refs = list(fmt.get('refs', [])); entries=[]
    for item in selected:
        c = get(C, item['id'], ctx.sid); check_revision(c,item['revision'])
        if c.get('formatId') != fmt['id'] or c.get('status') != 'accepted': fail()
        entries.append({'id': c['id'], 'revision': c['_revision'], 'consentId': item['consentId']})
        for ref in c.get('refs', []):
            if ref not in refs: refs.append(ref)
    for ref in extra_refs:
        if ref not in refs: refs.append(ref)
    if not refs or len(refs) > 20: fail('Select current source references.', 400)
    grants = body['sourceGrantIds']
    if not isinstance(grants,list) or len(grants) != len(refs) or len(set(grants)) != len(grants): fail('One source grant per reference is required.', 400)
    snap = {'sourceSessionId':ctx.sid,'targetSessionId':target,'formatId':fmt['id'],'formatRevision':fmt['_revision'],'decision':copy.deepcopy(decision),'refs':[{'ref':ref,'grantId':gid} for ref,gid in zip(refs,grants)],'contributions':entries}
    validate_snapshot(snap)
    return snap

def material_data(title, content, refs, **extra):
    version = {'number':1,'title':title,'body':content,'refs':refs}
    return dict(format='explanation',currentVersion=1,title=title,body=content,refs=refs,status='draft',approvedVersion=None,provider='deterministic',model=None,versions=[version],**extra)

def compose(ctx, fmt, snap):
    lines = ['Format: '+fmt['title'], 'Question: '+fmt['question']]
    for e in snap['refs']:
        row = valid_ref(e['ref']); lines.append('Source: '+str(row['source'].get('title','Source'))+' — '+str(row['moment'].get('text','')))
    for e in snap['contributions']:
        c = get(C,e['id'],ctx.sid)
        lines.append(('Minority contribution: ' if c['id'] in snap['decision']['minorityIds'] else 'Contribution: ')+c['selection']+' | Reason: '+c.get('reason','')+' | Alternative: '+c.get('alternative',''))
    lines.extend(['Decision: '+snap['decision']['decision'],'Consequence: '+snap['decision']['consequence']])
    content='\n'.join(lines)
    if len(content)>12000: fail('Selected content exceeds the material limit.',400)
    return content

def insert(db, kind, sid, owner, oid, data):
    value = dict(data,id=oid)
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)',(kind,oid,sid,owner,json.dumps(value,ensure_ascii=False),store.now()))

def db_get(db, kind, oid, sid=None):
    row=db.execute('SELECT data,revision FROM objects WHERE kind=? AND id=?' + (' AND session_id=?' if sid is not None else ''), (kind,oid,sid) if sid is not None else (kind,oid)).fetchone()
    if not row: fail(status=404)
    return dict(json.loads(row['data']),_revision=row['revision'])

def prepare_work(ctx, fmt, body, extra_refs=(), content=None, marker=None):
    snap=snapshot(ctx,fmt,body,extra_refs)
    content=compose(ctx,fmt,snap) if content is None else content
    if len(content)>12000: fail('Selected content exceeds the material limit.',400)
    wid=store.ident(); mid=store.ident(); refs=[e['ref'] for e in snap['refs']]
    work={'snapshot':snap,'materialId':mid}
    extra={'continuationWorkId':wid}
    if marker is not None:
        marker=dict(marker,workId=wid); work['w18Record']=marker; extra['w18Record']=marker
    return wid,mid,work,material_data(fmt['title'],content,refs,**extra)

def write_work(db, sid, actor, prepared):
    wid,mid,work,material=prepared
    insert(db,W,sid,actor,wid,work); insert(db,'p10material',sid,actor,mid,material)

def prepare_offer(sid, fmt, body):
    check_revision(fmt,body['revision']); work=get(W,body['workId'],sid)
    if work.get('materialId')!=body['materialId'] or work['snapshot']['formatId']!=fmt['id']: fail()
    snap=copy.deepcopy(work['snapshot']); snap.update(workId=work['id'],materialId=body['materialId'],materialVersion=body['materialVersion'])
    validate_snapshot(snap,True)
    m=get('p10material',body['materialId'],sid)
    if work.get('w18Record') != m.get('w18Record'): fail()
    offer={'kind':'reviewed-continuation-v1','sourceSessionId':sid,'targetSessionId':snap['targetSessionId'],'sourceFormatId':fmt['id'],'sourceRevision':fmt['_revision'],'snapshot':snap,'formatSnapshot':{k:copy.deepcopy(fmt[k]) for k in ('type','title','question','options','cards','refs','decision')},'contributionSnapshot':[{k:copy.deepcopy(get(C,e['id'],sid).get(k)) for k in ('id','selection','reason','alternative','refs')} for e in snap['contributions']],'materialSnapshot':{'title':m['title'],'body':m['body'],'refs':m['refs']},'status':'offered'}
    oid=store.ident()
    if work.get('w18Record'):
        marker=dict(work['w18Record'],transferId=oid)
        offer['w18Record']=marker; offer['materialSnapshot']['w18Record']=marker
    return oid,offer

def write_offer(db,sid,actor,prepared):
    oid,offer=prepared; insert(db,T,sid,actor,oid,offer)

@contextmanager
def participating_db():
    db = getattr(store.local, 'db', None)
    if db is not None:
        yield db
    else:
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

def handle(ctx, method, parts, body=None):
    with store.LOCK:
        ctx.check_actor(); sid=ctx.sid; actor=ctx.actor['owner']
        if len(parts)==3 and parts[0]=='format-contributions' and parts[2]=='continuation-consent' and method=='GET':
            contribution=get(C,parts[1],sid)
            if ctx.actor.get('role') != 'creator' and contribution.get('authorId') != actor: fail(status=404)
            guard_contribution(ctx,contribution)
            return 200, {'consents':[g for g in store.all(A,sid) if g.get('contributionId')==contribution['id']]}
        creator(ctx)
        if len(parts)>=3 and parts[0]=='formats' and parts[2]=='source-grants':
            fmt=get(F,parts[1],sid); guard_format(ctx,fmt)
            if len(parts)==3 and method=='GET':
                return 200, {'grants':[g for g in store.all(G,sid) if g.get('formatId')==fmt['id']]}
            if len(parts)==3 and method=='POST':
                require_fields(body,('revision','targetSessionId','ref')); check_revision(fmt,body['revision'])
                ref=parse_ref(body['ref']); target=body['targetSessionId']
                if ref['sessionId']!=sid or not isinstance(target,str) or target==sid: fail('Invalid target or source.',400)
                active_session(target); valid_ref(ref); ctx.resolve([ref])
                grant=store.put(G,sid,{'formatId':fmt['id'],'targetSessionId':target,'ref':ref,'status':'active'},owner=actor)
                return 201, {'grant':get(G,grant['id'],sid)}
            if len(parts)==5 and parts[4]=='revoke' and method=='POST':
                require_fields(body,('revision',)); grant=get(G,parts[3],sid)
                if grant.get('formatId')!=fmt['id']: fail(status=404)
                check_revision(grant,body['revision']); grant['status']='revoked'
                return 200, {'grant':store.save(G,grant,revision=body['revision'])}
        if len(parts)==3 and parts[0]=='formats' and parts[2]=='work' and method=='POST':
            require_fields(body,('revision','targetSessionId','contributions','sourceGrantIds'))
            fmt=get(F,parts[1],sid); prepared=prepare_work(ctx,fmt,body)
            with participating_db() as db: write_work(db,sid,actor,prepared)
            return 201, {'work':get(W,prepared[0],sid),'material':get('p10material',prepared[1],sid)}
        if len(parts)==3 and parts[0]=='formats' and parts[2]=='transfer' and method=='POST':
            require_fields(body,('revision','workId','materialId','materialVersion'))
            fmt=get(F,parts[1],sid); prepared=prepare_offer(sid,fmt,body)
            if prepared[1].get('w18Record'): fail('Use the record reuse offer operation.')
            with participating_db() as db: write_offer(db,sid,actor,prepared)
            return 201,{'transfer':get(T,prepared[0],sid)}
        if len(parts)==3 and parts[0]=='format-transfers':
            action=parts[2]; offer=get(T,parts[1]); party='sourceSessionId' if action=='withdraw' else 'targetSessionId'
            if offer.get(party)!=sid: fail(status=404)
            if action=='preview' and method=='GET':
                validate_offer(offer,('offered',)); return 200,{'transfer':offer}
            if method=='POST' and action in ('accept','decline','withdraw'):
                require_fields(body,('revision',)); check_revision(offer,body['revision'])
                if action in ('decline','withdraw'):
                    if offer.get('kind')!='reviewed-continuation-v1' or offer.get('status') not in (('offered','accepted') if action=='withdraw' else ('offered',)): fail()
                    offer['status']='withdrawn' if action=='withdraw' else 'declined'
                    saved=store.save(T,offer,revision=body['revision'])
                    return 200,{'transfer':{k:saved[k] for k in ('id','kind','sourceSessionId','targetSessionId','status','_revision')}}
                snap=validate_offer(offer,('offered',)); fid=store.ident(); mid=store.ident(); mapping={c['id']:store.ident() for c in offer['contributionSnapshot']}
                data=copy.deepcopy(offer['formatSnapshot']); decision=data['decision']; decision['reasonIds']=[mapping[x] for x in decision['reasonIds']]; decision['minorityIds']=[mapping[x] for x in decision['minorityIds']]; data['continuationTransferId']=offer['id']
                material=offer['materialSnapshot']; md=material_data(material['title'],material['body'],material['refs'],continuationTransferId=offer['id'])
                if offer.get('w18Record'):
                    if material.get('w18Record') != offer['w18Record']: fail()
                    md['w18Record']=copy.deepcopy(offer['w18Record'])
                offer.update(status='accepted',recipientFormatId=fid,recipientMaterialId=mid,contributionMapping=mapping)
                revision=offer.pop('_revision')
                with participating_db() as db:
                    changed=db.execute('UPDATE objects SET data=?,revision=? WHERE kind=? AND id=? AND revision=?',(json.dumps(offer,ensure_ascii=False),revision+1,T,offer['id'],revision)).rowcount
                    if changed!=1: fail()
                    insert(db,F,sid,actor,fid,data)
                    for c in offer['contributionSnapshot']:
                        cd={k:copy.deepcopy(c[k]) for k in ('selection','reason','alternative','refs')}; cd.update(formatId=fid,status='accepted',authorId=None,continuationTransferId=offer['id'],sourceContributionId=c['id'])
                        insert(db,C,sid,actor,mapping[c['id']],cd)
                    insert(db,'p10material',sid,actor,mid,md)
                return 201,{'transfer':get(T,offer['id']),'format':get(F,fid,sid),'material':get('p10material',mid,sid)}
        return None
