"""Phase 10 private vault and retention grants; staged integration candidate."""
import json, secrets
from .phase10_common import Phase10Error, VaultContext, parse_ref
from .phase10_timeline import _provider_call, _query_ref


def fail(message='The requested item is unavailable.', status=404):
    raise Phase10Error('not_found' if status == 404 else 'invalid_field', message, status)


def text(value, maximum):
    if not isinstance(value,str) or not 1 <= len(value.strip()) <= maximum: fail('Invalid text.',400)
    return value.strip()


def entry_view(ctx, entry):
    dep={'entryId':entry['id'],'entryRevision':entry['_revision'],'grantId':entry['grantId'],'ref':entry['ref']}
    try:
        # Inactive entries are visible to their owner but cannot be used for generation.
        if entry['active']: ctx.resolve_entries([dep])
        elif entry['ref'] is not None:
            probe=dict(entry); probe['active']=True
            # Do not expose source content when an inactive reference is stale.
            from .http import expired
            src=ctx.store.get('source',entry['ref']['sourceId'],entry['ref']['sessionId'])
            grant=ctx.store.get('p10grant',entry['grantId'],entry['ref']['sessionId'])
            moment=ctx.store.get('p10moment',entry['ref']['momentId'],entry['ref']['sessionId'])
            if not src or src.get('_revision')!=entry['ref']['sourceRevision'] or src.get('status')!='active' or expired(src) or not src.get('audienceVisible') or not grant or grant.get('status')!='active' or grant.get('ref')!=entry['ref'] or not moment or moment.get('ref')!=entry['ref']: raise Phase10Error('stale_context','Unavailable.',409)
        status='available'
    except Phase10Error: status='unavailable'
    current_correction=None
    ref=entry.get('ref')
    if ref is not None:
        from .http import expired
        src=ctx.store.get('source',ref['sourceId'],ref['sessionId'])
        original_grant=ctx.store.get('p10grant',entry['grantId'],ref['sessionId'])
        marker=src.get('creatorCorrection') if src else None
        if (src and src.get('status')=='active' and not expired(src) and src.get('audienceVisible')
                and original_grant and original_grant.get('status')=='active' and original_grant.get('ref')==ref
                and isinstance(marker,dict) and marker.get('sourceRevision')==src.get('_revision')
                and marker.get('sourceRevision',0)>ref['sourceRevision']):
            # A fresh retention grant for the exact newly indexed correction is required.
            for moment in ctx.store.all('p10moment',ref['sessionId']):
                newref=moment.get('ref',{})
                if (moment.get('kind')=='correction' and newref.get('sourceId')==ref['sourceId']
                        and newref.get('sourceRevision')==src['_revision']
                        and newref.get('startMs')==ref['startMs'] and newref.get('endMs')==ref['endMs']
                        and any(g.get('status')=='active' and g.get('ref')==newref for g in ctx.store.all('p10grant',ref['sessionId']))):
                    current_correction={'text':marker['text'],'correctedAt':marker['at'],'ref':newref}
                    break
    return {'id':entry['id'],'revision':entry['_revision'],'ref':entry['ref'],'interpretation':entry['interpretation'] if status=='available' else None,'pastStatement':entry.get('pastStatement') if status=='available' else None,'correction':entry.get('correction') if status=='available' else None,'creatorCorrection':current_correction,'active':entry['active'],'status':status}


def handle(method, parts, body, context):
    store=context.store
    if not isinstance(context,VaultContext):
        if not parts or parts[0]!='retention-grants': return None
        context.check_actor()
        if parts==['retention-grants'] and method=='GET':
            ref=_query_ref(context.handler,context.sid); rows=context.resolve([ref])
            if not rows[0]['source'].get('audienceVisible'): fail()
            return 200,{'grants':[{'id':g['id'],'ref':g['ref'],'status':'active'} for g in store.all('p10grant',context.sid) if g.get('status')=='active' and g.get('ref')==ref]}
        if context.actor.get('role')!='creator': raise Phase10Error('forbidden','Only the creator can manage retention grants.',403)
        if parts==['retention-grants'] and method=='POST':
            if not isinstance(body,dict) or set(body)!={'ref','consent'} or body['consent'] is not True: fail('Explicit consent and a reference are required.',400)
            with context.lock:
                ref=parse_ref(body['ref']); rows=context.resolve([ref])
                if not rows[0]['source'].get('audienceVisible'): fail()
                grant=store.put('p10grant',context.sid,{'ref':ref,'status':'active'},owner=context.actor['owner'])
            return 201,{'grant':{'id':grant['id'],'ref':ref,'status':'active'}}
        if len(parts)==2 and method=='DELETE':
            with context.lock,store.connect() as db:
                context.check_actor(); db.execute('BEGIN IMMEDIATE')
                row=db.execute("SELECT data FROM objects WHERE kind='p10grant' AND id=? AND session_id=?",(parts[1],context.sid)).fetchone()
                if not row: fail()
                grant=json.loads(row['data']); grant['status']='revoked'
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='p10grant' AND id=?",(json.dumps(grant,ensure_ascii=False),parts[1]))
                for item in db.execute("SELECT id,data FROM objects WHERE kind='p10vaultentry'").fetchall():
                    entry=json.loads(item['data'])
                    if entry.get('grantId')==parts[1] and entry.get('ref',{}).get('sessionId')==context.sid:
                        store.phase10_forget_entry_db(db,entry['vaultId'],item['id'])
                db.commit()
            return 200,{'revoked':True}
        return None
    if parts==['vaults'] and method=='POST':
        hook=getattr(context.handler,'p10_set_response_header',None)
        if not callable(hook): raise Phase10Error('integration_unavailable','Vault capability response headers are unavailable.',503)
        remote_sid=getattr(context.handler,'_p10_create_viewer_sid',None)
        if body != ( {'sessionId':remote_sid} if remote_sid is not None else {} ): fail('Invalid vault request.',400)
        capability=secrets.token_urlsafe(32); vault_id=store.ident()
        with context.lock,store.connect() as db:
            if remote_sid is not None: context.verify_viewer_header(remote_sid)
            db.execute('BEGIN IMMEDIATE')
            db.execute("INSERT INTO phase10_vaults(id,token_hash,status,calls) VALUES(?,?,'active',0)",(vault_id,store.digest(capability)))
            hook('X-Vault-Capability',capability)
            context.handler._p10_new_vault_id=vault_id
            db.commit()
        return 201,{'vault':{'id':vault_id}}
    if parts==['vault','resume'] and method=='POST':
        if not isinstance(body,dict) or set(body)!={'entryId','revision'} or not isinstance(body['entryId'],str) or type(body['revision']) is not int:
            raise Phase10Error('invalid_request','An entry and revision are required.',422)
        with context.lock:
            context.check_actor()
            entry=store.get('p10vaultentry',body['entryId'])
            if not entry or entry.get('vaultId')!=context.vault_id:
                fail()
            if entry.get('_revision')!=body['revision']:
                raise Phase10Error('version_conflict','The entry changed; refresh.',409)
            dep={'entryId':entry['id'],'entryRevision':entry['_revision'],'grantId':entry.get('grantId'),'ref':entry.get('ref')}
            rows=context.resolve_entries([dep])
            if rows[0]['moment'] is None:
                raise Phase10Error('stale_context','This entry has no retained source moment.',409)
            context.handler._p10_vault_deps=[dep]
            return 200,{'entry':entry_view(context,entry),'moment':{'ref':rows[0]['ref'],'text':rows[0]['moment'].get('text','')}}
    if parts==['vault','entries'] and method=='POST':
        if not isinstance(body,dict) or not {'sessionId','ref','interpretation','retainSourceGrantId'} <= set(body) or set(body)-{'sessionId','ref','interpretation','retainSourceGrantId','pastStatement','correction'}: fail('Invalid entry.',400)
        interpretation=text(body['interpretation'],4000); sid=body['sessionId']
        past=text(body['pastStatement'],4000) if body.get('pastStatement') is not None else None
        correction=text(body['correction'],4000) if body.get('correction') is not None else None
        if not isinstance(sid,str): fail('Invalid session.',400)
        with context.lock:
            context.check_actor(); viewer=context.verify_viewer_header(sid)
            ref=body['ref']; grant_id=body['retainSourceGrantId']
            if ref is None:
                if grant_id is not None: fail('A note cannot have a grant.',400)
            else:
                ref=parse_ref(ref)
                if ref['sessionId']!=sid or not isinstance(grant_id,str): fail('Invalid retained reference.',400)
                # Session bearer differs from vault bearer; verify viewer directly and validate source/grant.
                src=store.get('source',ref['sourceId'],sid); moment=store.get('p10moment',ref['momentId'],sid); grant=store.get('p10grant',grant_id,sid)
                from .http import expired
                if not src or src.get('_revision')!=ref['sourceRevision'] or src.get('status')!='active' or expired(src) or not src.get('audienceVisible') or not moment or moment.get('ref')!=ref or not grant or grant.get('ref')!=ref or grant.get('status')!='active': fail()
            item=store.put('p10vaultentry','vault:'+context.vault_id,{'vaultId':context.vault_id,'originSessionId':sid,'originViewerOwner':viewer['owner'],'ref':ref,'grantId':grant_id,'interpretation':interpretation,'pastStatement':past,'correction':correction,'active':True,'status':'active'},owner=context.vault_id)
            item=store.get('p10vaultentry',item['id'])
            return 201,{'entry':entry_view(context,item)}
    if parts==['vault','entries'] and method=='GET':
        with context.lock:
            context.check_actor(); return 200,{'entries':[entry_view(context,e) for e in store.all('p10vaultentry','vault:'+context.vault_id) if e.get('vaultId')==context.vault_id and e.get('status')=='active']}
    if len(parts)==3 and parts[:2]==['vault','entries'] and method in ('PATCH','DELETE'):
        with context.lock,store.connect() as db:
            context.check_actor(); db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT data,revision FROM objects WHERE kind='p10vaultentry' AND id=? AND session_id=?",(parts[2],'vault:'+context.vault_id)).fetchone()
            if not row: fail()
            entry=json.loads(row['data'])
            if entry.get('vaultId')!=context.vault_id or entry.get('status')!='active': fail()
            if method=='PATCH':
                if not isinstance(body,dict) or not {'revision','interpretation','active'} <= set(body) or set(body)-{'revision','interpretation','active','pastStatement','correction'} or type(body['revision']) is not int or type(body['active']) is not bool: fail('Invalid entry update.',400)
                if body['revision']!=row['revision']: raise Phase10Error('version_conflict','The entry changed.',409)
                entry['interpretation']=text(body['interpretation'],4000);entry['active']=body['active']
                for field in ('pastStatement','correction'):
                    if field in body: entry[field]=text(body[field],4000) if body[field] is not None else None
                store.phase10_forget_entry_db(db,context.vault_id,parts[2])
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='p10vaultentry' AND id=?",(json.dumps(entry,ensure_ascii=False),parts[2]));db.commit()
                return 200,{'entry':entry_view(context,store.get('p10vaultentry',parts[2]))}
            store.phase10_forget_entry_db(db,context.vault_id,parts[2]);db.execute("DELETE FROM objects WHERE kind='p10vaultentry' AND id=?",(parts[2],));db.commit()
            return 200,{'forgotten':True}
    if parts==['vault','query'] and method=='POST':
        if not isinstance(body,dict) or set(body)!={'entryIds','query','clientRequestId'}: fail('Invalid query.',400)
        query=text(body['query'],2000); ids=body['entryIds']
        if not isinstance(ids,list) or not 1<=len(ids)<=20 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids): fail('Select distinct entries.',400)
        with context.lock:
            context.check_actor(); entries=[store.get('p10vaultentry',i) for i in ids]
            if any(not e or e.get('vaultId')!=context.vault_id for e in entries): fail()
            deps=[{'entryId':e['id'],'entryRevision':e['_revision'],'grantId':e['grantId'],'ref':e['ref']} for e in entries]
        def invoke(rows):
            inputs=[{'moment':{'text':json.dumps({'interpretation':r['entry']['interpretation'],'source':r['moment'].get('text','') if r['moment'] else None},ensure_ascii=False)}} for r in rows]
            answer,handles,provider,model=_provider_call(inputs,query)
            citations=[]
            for i in handles:
                row=rows[i]; citation={'entryId':row['entry']['id'],'entryRevision':row['entry']['_revision'],'ref':row['entry']['ref']}
                if row.get('ref') is not None: citation.update(context.citations([row])[0])
                citations.append(citation)
            return {'answer':answer,'citations':citations,'provider':provider,'model':model,'limitations':['Private notes are viewer-authored interpretations.']}
        return context.generate('vault.query',body['clientRequestId'],body,deps,invoke)
    return None
