"""Voluntary, source-linked questions and creator-approved exchanges."""
from . import store
from .phase10_common import Context, Phase10Error

def fail(message,status=400):raise Phase10Error('not_found' if status==404 else 'invalid_exchange',message,status)
def content(v):
    if not isinstance(v,str) or not 1<=len(v.strip())<=4000:fail('Enter text between 1 and 4000 characters.')
    return v.strip()
def language(v):
    if v not in ('en','es'):fail('Choose English or Spanish.')
    return v

def owner(sid,qid):
    with store.connect() as db: row=db.execute("SELECT owner_id FROM objects WHERE kind='w13question' AND id=? AND session_id=?",(qid,sid)).fetchone()
    return row['owner_id'] if row else None

def eligible(handler,sid,actor,q):
    if q.get('status')=='withdrawn':return False
    if q.get('ref'):
        try:
            row=Context(handler,sid,actor).resolve([q['ref']])[0]
            if row['source'].get('p10Provenance',{}).get('type')!='received_asr_v1':return False
        except Phase10Error:return False
    return True

def handle(handler,sid,actor,method,parts):
    with store.LOCK:
        ctx=Context(handler,sid,actor);ctx.check_actor()
        if parts==['questions'] and method=='GET':
            visible=[]
            for q in store.all('w13question',sid):
                if not eligible(handler,sid,actor,q):continue
                if actor['role']=='creator' or owner(sid,q['id'])==actor['owner'] or (q.get('status')=='selected' and (q.get('answer') or {}).get('approved') is True):visible.append(q)
            handler._w13_question_binding=(sid,dict(actor),[(q['id'],q['_revision']) for q in visible])
            return 200,{'questions':visible}
        if parts==['questions'] and method=='POST':
            b=handler.body()
            if actor['role']!='viewer':raise Phase10Error('forbidden','Viewer capability required.',403)
            if not isinstance(b,dict) or set(b) not in ({'text','language','consent'},{'text','language','consent','ref'}) or b['consent'] is not True:fail('Explicit consent, text and language are required.')
            ref=b.get('ref')
            if ref is not None:
                row=ctx.resolve([ref])[0]
                if row['source'].get('p10Provenance',{}).get('type')!='received_asr_v1':fail('An authorized speech segment is required.')
            q=store.put('w13question',sid,{'text':content(b['text']),'language':language(b['language']),'status':'shared','answer':None,'ref':ref},owner=actor['owner'])
            return 201,{'question':store.get('w13question',q['id'],sid)}
        if len(parts)>=2 and parts[0]=='questions':
            q=store.get('w13question',parts[1],sid)
            if not q or q.get('status')=='withdrawn':fail('Question unavailable.',404)
            author=owner(sid,q['id'])==actor['owner']
            if not (author and len(parts)==2 and method=='DELETE') and not eligible(handler,sid,actor,q):fail('Question unavailable.',404)
            if len(parts)==2 and method in ('DELETE','PATCH'):
                if not author:raise Phase10Error('forbidden','Only the author can change this question.',403)
                b=handler.body()
                expected={'revision'} if method=='DELETE' else {'revision','text','language'}
                if not isinstance(b,dict) or set(b)!=expected or type(b['revision']) is not int:fail('A valid revision is required.')
                if b['revision']!=q['_revision']:raise Phase10Error('version_conflict','The question changed.',409)
                if method=='DELETE':q.update(text=None,answer=None,status='withdrawn')
                else:q.update(text=content(b['text']),language=language(b['language']),answer=None,status='shared')
                store.save('w13question',q,revision=b['revision'])
                return 200,{'withdrawn':True} if method=='DELETE' else {'question':store.get('w13question',q['id'],sid)}
            if len(parts)==3 and parts[2] in ('select','answer','unselect') and method=='POST':
                if actor['role']!='creator':raise Phase10Error('forbidden','Creator capability required.',403)
                b=handler.body(); action=parts[2]
                expected={'revision','text','language','approved'} if action=='answer' else {'revision'}
                if not isinstance(b,dict) or set(b)!=expected or type(b['revision']) is not int:fail('Invalid exchange fields.')
                if b['revision']!=q['_revision']:raise Phase10Error('version_conflict','The question changed.',409)
                if action=='answer':
                    if q.get('status')!='selected' or b['approved'] is not True:fail('Select the question and explicitly approve the answer.')
                    q['answer']={'text':content(b['text']),'language':language(b['language']),'approved':True}
                elif action=='select':q.update(status='selected',answer=None)
                else:q.update(status='shared',answer=None)
                store.save('w13question',q,revision=b['revision'])
                return 200,{'question':store.get('w13question',q['id'],sid)}
        raise Phase10Error('not_found','Question route unavailable.',404)
