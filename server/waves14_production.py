"""Creator-only scheduled breaks and approved-material preparation."""
from datetime import datetime, timezone
from . import store, phase10_studio
from .phase10_common import Context, Phase10Error

def fail(message, status=400): raise Phase10Error('not_found' if status==404 else 'invalid_break',message,status)
def label(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=160: fail('Enter a break title.')
    return value.strip()
def instant(value):
    if not isinstance(value,str) or not value.endswith('Z'): fail('Use a UTC time ending in Z.')
    try: parsed=datetime.fromisoformat(value[:-1]+'+00:00')
    except ValueError: fail('Invalid UTC time.')
    return parsed

def eligible_material(context,sid,material_id,version):
    material=store.get('p10material',material_id,sid)
    if not material or material.get('status')!='approved' or material.get('approvedVersion')!=version or material.get('currentVersion')!=version:
        fail('An approved current material is required.',409)
    phase10_studio._guard_material(context, material)
    rows=context.resolve(material.get('refs'))
    if not rows or not all(row['source'].get('audienceVisible') for row in rows):
        fail('The material sources are no longer eligible.',409)
    return material

def handle(handler,sid,actor,method,parts):
    with store.LOCK:
        context=Context(handler,sid,actor); context.check_actor()
        if actor['role']!='creator': raise Phase10Error('forbidden','Only the creator can manage production breaks.',403)
        if parts==['breaks'] and method=='GET':
            breaks=store.all('w14break',sid)
            for b in breaks: b['due']=instant(b['at'])<=datetime.now(timezone.utc)
            return 200,{'breaks':breaks,'interventions':store.all('w14intervention',sid)}
        if parts==['breaks'] and method=='POST':
            body=handler.body()
            if not isinstance(body,dict) or set(body)!={'title','at'}: fail('Title and time are required.')
            instant(body['at']); item=store.put('w14break',sid,{'title':label(body['title']),'at':body['at']},owner=actor['owner'])
            return 201,{'break':item}
        if parts==['interventions'] and method=='POST':
            body=handler.body()
            if not isinstance(body,dict) or set(body)!={'breakId','materialId','version'} or not isinstance(body['breakId'],str) or not isinstance(body['materialId'],str) or type(body['version']) is not int: fail('Break and material version are required.')
            if not store.get('w14break',body['breakId'],sid): fail('Break unavailable.',404)
            eligible_material(context,sid,body['materialId'],body['version'])
            item=store.put('w14intervention',sid,{**body,'status':'prepared'},owner=actor['owner'])
            return 201,{'intervention':item}
        if len(parts)==3 and parts[0]=='interventions' and parts[2]=='action' and method=='POST':
            item=store.get('w14intervention',parts[1],sid)
            if not item: fail('Intervention unavailable.',404)
            body=handler.body()
            if not isinstance(body,dict) or set(body) not in ({'action','revision'},{'action','revision','breakId'}) or body['action'] not in ('accept','defer','ignore') or type(body['revision']) is not int: fail('Action and revision are required.')
            if item['_revision']!=body['revision']: raise Phase10Error('version_conflict','The intervention changed.',409)
            if item['status'] not in ('prepared','deferred'): fail('This intervention is no longer pending.',409)
            if 'breakId' in body:
                target=store.get('w14break',body['breakId'],sid) if isinstance(body['breakId'],str) else None
                current=store.get('w14break',item['breakId'],sid)
                if body['action']!='defer' or not target or not current or instant(target['at'])<=instant(current['at']):
                    fail('Choose an available later break for deferral.',409)
            if body['action']=='accept':
                eligible_material(context,sid,item['materialId'],item['version'])
            if 'breakId' in body: item['breakId']=body['breakId']
            item['status']={'accept':'accepted','defer':'deferred','ignore':'ignored'}[body['action']]
            store.save('w14intervention',item,revision=body['revision'])
            return 200,{'intervention':store.get('w14intervention',parts[1],sid)}
        raise Phase10Error('not_found','Production route unavailable.',404)
