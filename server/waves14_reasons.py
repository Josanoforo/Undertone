"""Explicit shared reasons and creator decisions, scoped to a session."""
from . import store
from .phase10_common import Context, Phase10Error

def fail(message, status=400):
    raise Phase10Error('not_found' if status == 404 else 'invalid_reason', message, status)

def text(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 4000: fail('Enter between 1 and 4000 characters.')
    return value.strip()

def handle(handler, sid, actor, method, parts):
    ctx=Context(handler,sid,actor)
    with store.LOCK:
        ctx.check_actor()
        if parts == ['reasons'] and method == 'GET':
            return 200, {'reasons': [r if r.get('status') != 'withdrawn' else {'id':r['id'], '_revision':r['_revision'], 'status':'withdrawn'} for r in store.all('w14reason',sid)], 'decisions': store.all('w14decision',sid)}
        if parts == ['reasons'] and method == 'POST':
            body=handler.body()
            if not isinstance(body,dict) or set(body)!={'text','consent'} or body['consent'] is not True: fail('Explicit consent and a reason are required.')
            item=store.put('w14reason',sid,{'text':text(body['text']),'corrections':[]},owner=actor['owner'])
            return 201, {'reason':item}
        if len(parts)==2 and parts[0]=='reasons' and method=='DELETE':
            reason=store.get('w14reason',parts[1],sid)
            if not reason or reason.get('status')=='withdrawn': fail('Reason unavailable.',404)
            with store.connect() as db:
                row=db.execute("SELECT owner_id FROM objects WHERE kind='w14reason' AND id=? AND session_id=?",(parts[1],sid)).fetchone()
            if not row or row['owner_id']!=actor['owner']: raise Phase10Error('forbidden','Only the author can withdraw this reason.',403)
            body=handler.body()
            if not isinstance(body,dict) or set(body)!={'revision'} or type(body['revision']) is not int: fail('A revision is required.')
            if reason['_revision']!=body['revision']: raise Phase10Error('version_conflict','The reason changed.',409)
            reason.update(text=None,corrections=[],status='withdrawn');store.save('w14reason',reason,revision=body['revision'])
            return 200,{'withdrawn':True}
        if len(parts)==3 and parts[0]=='reasons' and parts[2]=='corrections' and method=='POST':
            reason=store.get('w14reason',parts[1],sid)
            if not reason or reason.get('status')=='withdrawn': fail('Reason unavailable.',404)
            with store.connect() as db:
                row=db.execute("SELECT owner_id FROM objects WHERE kind='w14reason' AND id=? AND session_id=?",(parts[1],sid)).fetchone()
            if not row or row['owner_id']!=actor['owner']: raise Phase10Error('forbidden','Only the author can correct this reason.',403)
            body=handler.body()
            if not isinstance(body,dict) or set(body)!={'text','revision'} or type(body['revision']) is not int: fail('Text and revision are required.')
            if body['revision']!=reason['_revision']: raise Phase10Error('version_conflict','The reason changed.',409)
            if len(reason['corrections'])>=50: fail('Correction limit reached.')
            reason['corrections'].append(text(body['text']));store.save('w14reason',reason,revision=body['revision'])
            return 200,{'reason':store.get('w14reason',parts[1],sid)}
        if parts==['decisions'] and method=='POST':
            if actor['role']!='creator': raise Phase10Error('forbidden','Only the creator can publish a decision.',403)
            body=handler.body()
            if not isinstance(body,dict) or set(body)!={'reasonIds','decision','consequence'}: fail('Reasons, decision and consequence are required.')
            ids=body['reasonIds']
            if not isinstance(ids,list) or not 1<=len(ids)<=50 or any(not isinstance(i,str) for i in ids) or len(set(ids))!=len(ids): fail('Select distinct reasons.')
            if any(not (r:=store.get('w14reason',i,sid)) or r.get('status')=='withdrawn' for i in ids): fail('Reason unavailable.',404)
            item=store.put('w14decision',sid,{'reasonIds':ids,'decision':text(body['decision']),'consequence':text(body['consequence'])},owner=actor['owner'])
            return 201,{'decision':item}
        raise Phase10Error('not_found','Reason route unavailable.',404)
