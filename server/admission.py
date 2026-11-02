import threading, time, statistics
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from . import store
from .provider import provider_name

LIMIT=3
CEILING=100
_active=0
_lock=threading.Lock()
_stats={}
class Busy(Exception): pass
class Ceiling(Exception): pass


def reserve_session_cost(sid, operation_id, amount_usd, cap_usd, *, policy_revision=None, translation_choice=None, speech_choice=None):
    """Conservatively reserve an operation against its session's monetary cap.

    Reservations are permanent, including unknown effects.  This is separate
    from, and does not replace, the provider's global budget reservation.
    The caller must recheck the current policy and source before dispatch.
    """
    import json, re
    if (not isinstance(sid, str) or not sid or not isinstance(operation_id, str)
            or not re.fullmatch(r'[0-9a-f]{64}', operation_id)):
        raise ValueError('invalid reservation identity')
    try:
        amount, cap = Decimal(str(amount_usd)), Decimal(str(cap_usd))
        if not amount.is_finite() or not cap.is_finite() or amount <= 0 or cap < 0 or cap > 75:
            raise ValueError('invalid reservation amount')
    except (InvalidOperation, TypeError):
        raise ValueError('invalid reservation amount')
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        session = db.execute("SELECT owner_id,data FROM objects WHERE kind='session' AND id=? AND session_id=?", (sid, sid)).fetchone()
        if not session:
            raise KeyError(sid)
        if policy_revision is not None or translation_choice is not None or speech_choice is not None:
            from . import lifecycle, waves20_modes
            if (type(policy_revision) is not int or policy_revision < 1 or
                    ((translation_choice is None) == (speech_choice is None)) or
                    (translation_choice is not None and translation_choice not in ('local', 'hosted')) or
                    (speech_choice is not None and speech_choice not in ('local', 'hosted')) or not session['owner_id'] or
                    not lifecycle.active(json.loads(session['data']))):
                raise ValueError('invalid policy binding')
            _, policy = waves20_modes._current(db, sid, session['owner_id'])
            selected = policy['operations']['speech'] if policy and speech_choice is not None else None
            if (not policy or policy['revision'] != policy_revision or
                    (translation_choice is not None and policy['operations']['translation']['primary'] != translation_choice) or
                    (speech_choice is not None and speech_choice not in [selected['primary'], *selected['alternatives']]) or
                    Decimal(policy['sessionCapUsd']) != cap):
                raise ValueError('policy changed')
        rows = db.execute("SELECT id,data FROM objects WHERE kind='w20costreservation' AND session_id=?", (sid,)).fetchall()
        total = Decimal('0')
        for row in rows:
            item = json.loads(row['data'])
            value = Decimal(item['amountUsd'])
            if not value.is_finite() or value <= 0:
                raise ValueError('invalid existing reservation')
            if row['id'] == operation_id:
                raise ValueError('operation already reserved')
            total += value
        if total + amount > cap:
            raise Ceiling()
        db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w20costreservation',?,?,NULL,1,?,?)",
                   (operation_id, sid, json.dumps({'amountUsd': str(amount)}, separators=(',', ':')), store.now()))
        db.commit()

def reserve(sid):
    import json
    with store.LOCK, store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM objects WHERE kind='session' AND id=?",(sid,)).fetchone():db.rollback();raise KeyError(sid)
        row=db.execute("SELECT data FROM objects WHERE kind='admission' AND id=?",(sid,)).fetchone()
        n=json.loads(row['data']).get('calls',0) if row else 0
        if n>=CEILING:db.rollback();raise Ceiling()
        data=json.dumps({'id':sid,'calls':n+1})
        db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('admission',?,?,NULL,1,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data,revision=objects.revision+1",(sid,sid,data,store.now()));db.commit()

def effective_limit():return 1 if provider_name()=="claude" else LIMIT

def stats(sid):
    with _lock:
        x=_stats.get(sid,{}); lat=list(x.get('latencies',[])); result={'limit':effective_limit(),'inFlight':x.get('inFlight',0),'sessionCallLimit':CEILING,'completed':x.get('completed',0),'busy':x.get('busy',0),'errors':x.get('errors',0),'medianMs':round(statistics.median(lat),2) if lat else None,'worstMs':round(max(lat),2) if lat else None}
    row=store.get('admission',sid,sid)
    result['sessionCalls']=row.get('calls',0) if row else 0
    return result

@contextmanager
def lease(sid):
    global _active
    with _lock:
        x=_stats.setdefault(sid,{})
        if _active>=effective_limit():
            x['busy']=x.get('busy',0)+1
            raise Busy()
        _active+=1;x['inFlight']=x.get('inFlight',0)+1
    try:yield
    finally:
        with _lock:
            _active-=1;_stats[sid]['inFlight']-=1

@contextmanager
def operation(sid):
    reserve(sid)
    started=time.monotonic();failed=False
    try:yield
    except BaseException:
        failed=True;raise
    finally:
        with _lock:
            x=_stats.setdefault(sid,{});key='errors' if failed else 'completed';x[key]=x.get(key,0)+1
            x.setdefault('latencies',[]).append((time.monotonic()-started)*1000);x['latencies']=x['latencies'][-256:]

@contextmanager
def admitted(sid):
    with lease(sid):
        with operation(sid):yield
