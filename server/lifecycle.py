from datetime import datetime, timezone, timedelta
import uuid
from . import store
BOOT_ID=uuid.uuid4().hex

class StaleCaptureRun(Exception): pass
class CaptureRunLimit(Exception): pass

def future(seconds):
    return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat(timespec='seconds').replace('+00:00','Z')

def past(value):
    try: return datetime.fromisoformat(value.replace('Z','+00:00')) <= datetime.now(timezone.utc)
    except (ValueError, TypeError, AttributeError): return True

def ensure(s):
    with store.LOCK:
        s=store.get('session',s['id'])
        if 'lifecycle' not in s:
            s['lifecycle']={'status':'active','expiresAt':future(86400),'invitationExpiresAt':future(3600)}
            s=store.save('session',s)
        return s

def active(s): return s.get('lifecycle',{}).get('status')=='active' and not past(s['lifecycle'].get('expiresAt'))

def empty_capture(gaps=0):
    return {'state':'stopped','lastCompletedAt':None,'lastCapturedAt':None,'gaps':gaps,'updatedAt':None,'inputKind':None,'sourceLabel':None,'captureRunId':None,'runIds':[],'programVersion':3,'bootId':None}

def load_capture(sid):
    c=store.get('capture_status',sid,sid)
    if not c: return None
    if c.get('programVersion')!=3:
        # v2 had explicitly declared shared gaps; older provenance was untrusted.
        clean=empty_capture(c.get('gaps',0) if c.get('programVersion')==2 else 0)
        clean.update(id=c['id'],_revision=c['_revision']);return clean
    return c

def capture(sid):
    c=load_capture(sid) or empty_capture()
    same_boot=c.get('bootId')==BOOT_ID
    c={k:v for k,v in c.items() if k not in ('_revision','id','bootId','programVersion','runIds')}
    if not same_boot and c['state'] in ('current','delayed'): c['state']='stopped'
    if c['state']=='current' and (not c['lastCompletedAt'] or past_delay(c['lastCompletedAt']) or not c['lastCapturedAt'] or past_delay(c['lastCapturedAt'])): c['state']='delayed'
    return c

def past_delay(value):
    try: return (datetime.now(timezone.utc)-datetime.fromisoformat(value.replace('Z','+00:00'))).total_seconds()>30
    except (ValueError,TypeError,AttributeError): return True

def run_control(sid,action,program):
    with store.LOCK:
        c=load_capture(sid);existing=bool(c)
        if not c:c=empty_capture()
        rid=program['captureRunId'];same=c.get('captureRunId')==rid;running=c.get('bootId')==BOOT_ID and c.get('state') in ('current','delayed')
        if same and (c.get('inputKind')!=program['inputKind'] or c.get('sourceLabel')!=program['sourceLabel']):raise StaleCaptureRun()
        if action=='started':
            if same and running:return
            if rid in c['runIds']:raise StaleCaptureRun()
            if len(c['runIds'])>=256:raise CaptureRunLimit()
            c['runIds'].append(rid);c.update(state='delayed',captureRunId=rid,lastCompletedAt=None,lastCapturedAt=None,inputKind=program['inputKind'],sourceLabel=program['sourceLabel'],bootId=BOOT_ID,updatedAt=store.now())
        else:
            if same and c.get('bootId')==BOOT_ID and c.get('state')==action:return
            if not same or not running:raise StaleCaptureRun()
            c.update(state=action,updatedAt=store.now())
            if action=='gap':c['gaps']+=1
        if existing:store.save('capture_status',c)
        else:store.put('capture_status',sid,c,oid=sid)

def update_capture(sid,state,captured=None,program=None):
    # Completion/failure is conditional on the exact live run at commit time.
    with store.LOCK:
        c=load_capture(sid)
        if not c or not program or c.get('bootId')!=BOOT_ID or c.get('captureRunId')!=program['captureRunId'] or c.get('state') not in ('current','delayed'):return False
        if c.get('inputKind')!=program['inputKind'] or c.get('sourceLabel')!=program['sourceLabel']:return False
        c['state']=state;c['updatedAt']=store.now()
        if state=='gap':c['gaps']+=1
        if state=='current':
            c['lastCompletedAt']=store.now()
            if not c.get('lastCapturedAt') or datetime.fromisoformat(captured.replace('Z','+00:00'))>=datetime.fromisoformat(c['lastCapturedAt'].replace('Z','+00:00')):c['lastCapturedAt']=captured
        store.save('capture_status',c);return True


def require_live_program(sid, program):
    """Call under store.LOCK before accepting or committing a program chunk."""
    c=load_capture(sid)
    if not c or c.get('bootId')!=BOOT_ID or c.get('state') not in ('current','delayed') or any(c.get(k)!=program.get(k) for k in ('captureRunId','inputKind','sourceLabel')):
        raise StaleCaptureRun()
