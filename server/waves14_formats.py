"""Bounded counter formats and explicit creator-to-creator transfer."""
from . import store, lifecycle
from .phase10_common import Context, Phase10Error

def fail(message,status=400): raise Phase10Error('not_found' if status==404 else 'invalid_format',message,status)
def title(v):
    if not isinstance(v,str) or not 1<=len(v.strip())<=160:fail('Enter a format title.')
    return v.strip()
def integer(v):
    if type(v) is not int or abs(v)>1000000:fail('Use a bounded integer.')
    return v

def handle(handler,sid,actor,method,parts):
    with store.LOCK:
        Context(handler,sid,actor).check_actor()
        if parts==['formats'] and method=='GET':return 200,{'formats':store.all('w14format',sid),'contributions':store.all('w14formatcontribution',sid)}
        if parts==['formats'] and method=='POST':
            if actor['role']!='creator':raise Phase10Error('forbidden','Only the creator can create a format.',403)
            b=handler.body()
            if not isinstance(b,dict) or set(b)!={'title','min','max','step','value'}:fail('Title, bounds, step and initial value are required.')
            low,high,step,value=[integer(b[k]) for k in ('min','max','step','value')]
            if low>=high or step<=0 or step>high-low or not low<=value<=high or (value-low)%step:fail('Invalid counter bounds or value.')
            item=store.put('w14format',sid,{'title':title(b['title']),'min':low,'max':high,'step':step,'value':value},owner=actor['owner']);return 201,{'format':item}
        if len(parts)==2 and parts[0]=='formats' and method=='PATCH':
            if actor['role']!='creator':raise Phase10Error('forbidden','Only the creator can adapt a format.',403)
            fmt=store.get('w14format',parts[1],sid); b=handler.body()
            if not fmt:fail('Format unavailable.',404)
            if not isinstance(b,dict) or set(b)!={'title','min','max','step','value','revision'} or type(b['revision']) is not int:fail('Rules, state and revision are required.')
            if fmt['_revision']!=b['revision']:raise Phase10Error('version_conflict','The format changed.',409)
            low,high,step,value=[integer(b[k]) for k in ('min','max','step','value')]
            if low>=high or step<=0 or step>high-low or not low<=value<=high or (value-low)%step:fail('Invalid counter bounds or value.')
            fmt.update(title=title(b['title']),min=low,max=high,step=step,value=value)
            store.save('w14format',fmt,revision=b['revision'])
            return 200,{'format':store.get('w14format',parts[1],sid)}
        if len(parts)==3 and parts[0]=='formats' and parts[2]=='contributions' and method=='POST':
            fmt=store.get('w14format',parts[1],sid)
            if not fmt:fail('Format unavailable.',404)
            b=handler.body()
            if not isinstance(b,dict) or set(b)!={'delta','consent'} or b['consent'] is not True:fail('Explicit consent and a delta are required.')
            delta=integer(b['delta'])
            if not delta or delta%fmt['step'] or abs(delta)>fmt['max']-fmt['min']:fail('Delta must be a nonzero step within the bounds.')
            item=store.put('w14formatcontribution',sid,{'formatId':fmt['id'],'delta':delta,'status':'pending'},owner=actor['owner']);return 201,{'contribution':item}
        if len(parts)==3 and parts[0]=='format-contributions' and parts[2]=='accept' and method=='POST':
            if actor['role']!='creator':raise Phase10Error('forbidden','Only the creator can accept a contribution.',403)
            c=store.get('w14formatcontribution',parts[1],sid)
            if not c or c['status']!='pending':fail('Contribution unavailable.',404)
            fmt=store.get('w14format',c['formatId'],sid);b=handler.body()
            if not isinstance(b,dict) or set(b)!={'formatRevision'} or type(b['formatRevision']) is not int:fail('Format revision required.')
            if not fmt or fmt['_revision']!=b['formatRevision']:raise Phase10Error('version_conflict','The format changed.',409)
            value=fmt['value']+c['delta']
            if not fmt['min']<=value<=fmt['max'] or (value-fmt['min'])%fmt['step']:fail('Contribution no longer matches the current rules.',409)
            # Both writes commit together: acceptance cannot be replayed or applied twice.
            import json
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE');fmt['value']=value;c['status']='accepted';c['resultValue']=value
                for kind,obj in [('w14format',fmt),('w14formatcontribution',c)]:
                    rev=obj.pop('_revision'); changed=db.execute('UPDATE objects SET data=?, revision=? WHERE kind=? AND id=? AND session_id=? AND revision=?',(json.dumps(obj,ensure_ascii=False),rev+1,kind,obj['id'],sid,rev)).rowcount
                    if changed!=1: db.rollback(); raise Phase10Error('version_conflict','The contribution or format changed.',409)
                db.commit()
            return 200,{'format':store.get('w14format',fmt['id'],sid),'contribution':store.get('w14formatcontribution',c['id'],sid)}
        if parts==['format-transfers'] and method=='GET':
            if actor['role']!='creator':raise Phase10Error('forbidden','Only the creator can review transfers.',403)
            with store.connect() as db:
                import json
                rows=db.execute("SELECT data,revision FROM objects WHERE kind='w14transfer'").fetchall()
                offers=[dict(json.loads(r['data']),_revision=r['revision']) for r in rows]
            return 200,{'transfers':[o for o in offers if o['targetSessionId']==sid and o['status']=='offered'], 'sentTransfers':[o for o in offers if o['sourceSessionId']==sid and o['status']=='offered']}
        if len(parts)==3 and parts[0]=='formats' and parts[2]=='transfer' and method=='POST':
            if actor['role']!='creator':raise Phase10Error('forbidden','Only the creator can offer a format.',403)
            fmt=store.get('w14format',parts[1],sid);b=handler.body()
            if not fmt:fail('Format unavailable.',404)
            if not isinstance(b,dict) or set(b)!={'targetSessionId','revision'} or not isinstance(b['targetSessionId'],str) or type(b['revision']) is not int:fail('Target session and revision are required.')
            if b['revision']!=fmt['_revision']:raise Phase10Error('version_conflict','The format changed.',409)
            target=store.get('session',b['targetSessionId'])
            if not target or not lifecycle.active(target) or b['targetSessionId']==sid:fail('Target session unavailable.',404)
            snapshot={k:fmt[k] for k in ('title','min','max','step','value')}
            offer=store.put('w14transfer',sid,{'targetSessionId':b['targetSessionId'],'sourceSessionId':sid,'sourceFormatId':fmt['id'],'sourceRevision':fmt['_revision'],'snapshot':snapshot,'status':'offered'},owner=actor['owner'])
            return 201,{'transfer':offer}
        if len(parts)==3 and parts[0]=='format-transfers' and parts[2] in ('decline','withdraw') and method=='POST':
            if actor['role']!='creator':raise Phase10Error('forbidden','Only the creator can manage a transfer.',403)
            action=parts[2]; offer=store.get('w14transfer',parts[1]); b=handler.body()
            party='targetSessionId' if action=='decline' else 'sourceSessionId'
            if not offer or offer.get(party)!=sid or offer.get('status')!='offered':fail('Transfer unavailable.',404)
            if not isinstance(b,dict) or set(b)!={'revision'} or type(b['revision']) is not int:fail('Transfer revision required.')
            if b['revision']!=offer['_revision']:raise Phase10Error('version_conflict','The transfer changed.',409)
            # Check source availability and update the exact offer together under the write lock.
            import json
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                source=db.execute("SELECT data FROM objects WHERE kind='session' AND id=?",(offer['sourceSessionId'],)).fetchone()
                fmt=db.execute("SELECT revision FROM objects WHERE kind='w14format' AND id=? AND session_id=?",(offer['sourceFormatId'],offer['sourceSessionId'])).fetchone()
                if not source or not lifecycle.active(json.loads(source['data'])) or not fmt or fmt['revision']!=offer['sourceRevision']:
                    db.rollback(); fail('The source format changed or became unavailable.',409)
                offer['status']='declined' if action=='decline' else 'withdrawn'; rev=offer.pop('_revision')
                changed=db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w14transfer' AND id=? AND session_id=? AND revision=?",(json.dumps(offer,ensure_ascii=False),rev+1,offer['id'],offer['sourceSessionId'],rev)).rowcount
                if changed!=1: db.rollback(); raise Phase10Error('version_conflict','The transfer changed.',409)
                db.commit()
            return 200,{'transfer':store.get('w14transfer',offer['id'],offer['sourceSessionId'])}
        if len(parts)==3 and parts[0]=='format-transfers' and parts[2]=='accept' and method=='POST':
            if actor['role']!='creator':raise Phase10Error('forbidden','Only the recipient creator can accept a transfer.',403)
            offer=store.get('w14transfer',parts[1]);b=handler.body()
            if not offer or offer['targetSessionId']!=sid or offer['status']!='offered':fail('Transfer unavailable.',404)
            if not isinstance(b,dict) or set(b)!={'revision'} or type(b['revision']) is not int:fail('Transfer revision required.')
            if b['revision']!=offer['_revision']:raise Phase10Error('version_conflict','The transfer changed.',409)
            source=store.get('session',offer['sourceSessionId']);fmt=store.get('w14format',offer['sourceFormatId'],offer['sourceSessionId'])
            if not source or not lifecycle.active(source) or not fmt or fmt['_revision']!=offer['sourceRevision']:fail('The source format changed or became unavailable.',409)
            import json
            new_id=store.ident(); value=dict(offer['snapshot'],id=new_id,provenance={'sourceSessionId':offer['sourceSessionId'],'sourceFormatId':offer['sourceFormatId'],'sourceRevision':offer['sourceRevision'],'transferId':offer['id']}); offer['status']='accepted';offer['recipientFormatId']=new_id;rev=offer.pop('_revision')
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current=db.execute("SELECT revision FROM objects WHERE kind='w14format' AND id=? AND session_id=?",(offer['sourceFormatId'],offer['sourceSessionId'])).fetchone()
                if not current or current['revision']!=offer['sourceRevision']: db.rollback(); raise Phase10Error('version_conflict','The source format changed.',409)
                changed=db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w14transfer' AND id=? AND revision=?",(json.dumps(offer,ensure_ascii=False),rev+1,offer['id'],rev)).rowcount
                if changed!=1: db.rollback(); raise Phase10Error('version_conflict','The transfer changed.',409)
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)',('w14format',new_id,sid,actor['owner'],1,json.dumps(value,ensure_ascii=False),store.now()));db.commit()
            return 201,{'format':store.get('w14format',new_id,sid)}
        raise Phase10Error('not_found','Format route unavailable.',404)
