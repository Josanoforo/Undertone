"""Cooperative project API reservation ledger. No provider calls are made here."""
import argparse, contextlib, datetime as dt, decimal, hashlib, json, os, pathlib, re, stat, sys, time
D = decimal.Decimal
ROOT = pathlib.Path(__file__).absolute().parent.parent
DEFAULT = ROOT / '.runtime' / 'api-budget'
SOURCES = ['.runtime/mesa04/PHASE2_BUDGET_RESERVATION.json', '.runtime/mesa04/anthropic-qa-phase-ledger.jsonl', '.runtime/mesa04/claude-ledger.json', 'sessions/mesa-03/HANDOFF.md']
START = dt.date(2026, 10, 29)
END = dt.date(2026, 11, 2)
M02 = '.runtime/mesa02/claude-ledger.jsonl'
M04 = SOURCES[1]
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
class Refusal(Exception): pass

def money(value):
    try:
        if not isinstance(value, str) or len(value) > 32 or not re.fullmatch(r'\d+(?:\.\d{1,6})?', value): raise ValueError()
        n = D(value)
        if not n.is_finite() or n < 0 or n > 75: raise ValueError()
        return n
    except (ValueError, decimal.InvalidOperation): raise Refusal('invalid amount')

def cdmx_date():
    # Mexico City is UTC-6 throughout this specific 2026 authorization window.
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=-6))).date()

def ceiling(date):
    if not START <= date <= END: raise Refusal('outside authorized CDMX window')
    return D(15) * ((date - START).days + 1)

def safe(path, create=False):
    path = pathlib.Path(os.path.abspath(path))
    try: path.relative_to(ROOT)
    except ValueError: raise Refusal('path outside project')
    cur = pathlib.Path(path.anchor)
    for part in path.parts[1:]:
        cur = cur / part
        if cur.exists() or cur.is_symlink():
            s = cur.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s, 'st_file_attributes', 0) & 0x400: raise Refusal('reparse/symlink path')
        elif create:
            cur.mkdir()
    return path

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def checked_bytes(name):
    p=safe(ROOT / name)
    if name == M02 and safe(p.with_suffix(p.suffix+'.lock')).exists(): raise Refusal('M02 ledger locked')
    data=p.read_bytes()
    if len(data)>20_000_000 or (name in (M02,M04) and (not data or not data.endswith(b'\n'))): raise Refusal('invalid source size or partial ledger')
    if name == M02 and safe(p.with_suffix(p.suffix+'.lock')).exists(): raise Refusal('M02 ledger locked')
    return data

def parse_m04(data):
    try:
        rows=[json.loads(x, parse_float=D, parse_constant=lambda x: (_ for _ in ()).throw(ValueError())) for x in data.splitlines()]
        reserves=[r for r in rows if r.get('event')=='provider_reserve']
        ids=[r['request_id'] for r in reserves]
        if any(not isinstance(x,str) or not x for x in ids) or len(set(ids))!=len(ids): raise ValueError()
        return len(reserves), sum((money(str(r['reserved_usd'])) for r in reserves),D(0))
    except (ValueError,KeyError,TypeError,AttributeError,Refusal): raise Refusal('M04 ledger malformed')

def parse_m02(data):
    try:
        sys.path.insert(0,str(ROOT))
        from server.claude_provider import validate_ledger
        rows=[json.loads(x,parse_constant=lambda x: (_ for _ in ()).throw(ValueError())) for x in data.splitlines()]
        reserves,_,_=validate_ledger(rows)
        return len(reserves),sum((money(str(r['amount'])) for r in reserves),D(0))
    except (ValueError,KeyError,TypeError,Refusal,OverflowError): raise Refusal('M02 ledger invalid or incomplete') from None

def sha(data): return hashlib.sha256(data).hexdigest()

def initial_prefix_m04(data, expected):
    h=hashlib.sha256(); size=0
    for line in data.splitlines(keepends=True):
        h.update(line); size+=len(line)
        if h.hexdigest()==expected:
            if parse_m04(data[:size]) != (40,D('.930958')): raise Refusal('initial M04 aggregate mismatch')
            return size
    raise Refusal('initial M04 ledger prefix rewritten')

def initial_prefix_m02(data):
    # Original shared observation recorded 14 reservations / .309530 but no M02 hash.
    # Locate a validated matching prefix; this establishes a present proof, not a historical hash.
    lines=data.splitlines(keepends=True); partial=b''
    for line in lines:
        partial+=line
        try:
            if parse_m02(partial)==(14,D('.309530')): return len(partial)
        except Refusal: pass
    raise Refusal('no validated M02 prefix matches original shared observation')

def snapshot(rows):
    original=rows[0]; previous=next((r for r in reversed(rows) if r['type']=='reconcile'),None)
    names=SOURCES+[M02]; data={name:checked_bytes(name) for name in names}
    m04=data[M04]; m02=data[M02]
    if previous:
        old=previous['proof']
        for name,blob in ((M04,m04),(M02,m02)):
            saved=old['ledgers'][name]; n=saved['bytes']
            if len(blob)<n or sha(blob[:n])!=saved['sha256']: raise Refusal('ledger prefix rewritten')
        old04=old['ledgers'][M04]; old02=old['ledgers'][M02]
    else:
        n04=initial_prefix_m04(m04,original['sources'][M04]); n02=initial_prefix_m02(m02)
        old04={'bytes':n04,'sha256':sha(m04[:n04]),'count':40,'sum':'0.930958'}
        old02={'bytes':n02,'sha256':sha(m02[:n02]),'count':14,'sum':'0.309530'}
    if sha(data[SOURCES[2]])!=original['sources'][SOURCES[2]]: raise Refusal('historical ledger changed; manual reconciliation required')
    c04,v04=parse_m04(m04); c02,v02=parse_m02(m02)
    for count,value,old in ((c04,v04,old04),(c02,v02,old02)):
        if count<old['count'] or value<money(old['sum']) or (count==old['count'] and value!=money(old['sum'])): raise Refusal('ledger aggregate is not monotonic')
    previous_baseline=money(previous['baseline']) if previous else money(original['baseline'])
    baseline=previous_baseline+(v04-money(old04['sum']))+(v02-money(old02['sum']))
    money(str(baseline))
    proof={'ledgers':{M04:{'bytes':len(m04),'sha256':sha(m04),'count':c04,'sum':str(v04)}, M02:{'bytes':len(m02),'sha256':sha(m02),'count':c02,'sum':str(v02)}},'documents':{name:sha(data[name]) for name in (SOURCES[0],SOURCES[2],SOURCES[3])}}
    if not previous: proof['initial_prefixes']={M04:old04,M02:old02}
    if any(checked_bytes(name)!=data[name] for name in names): raise Refusal('source changed during read')
    return str(baseline),proof

def sources_current(rows):
    previous=next((r for r in reversed(rows) if r['type']=='reconcile'),None)
    if not previous: return False
    p=previous['proof']
    return all(sha(checked_bytes(name))==rec['sha256'] for name,rec in p['ledgers'].items()) and all(sha(checked_bytes(name))==h for name,h in p['documents'].items())

@contextlib.contextmanager
def locked(directory):
    directory = safe(directory, create=True)
    lock = safe(directory / 'lock')
    f = open(lock, 'a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0); f.write(b'0'); f.flush()
            for _ in range(300):
                try: f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1); break
                except OSError: time.sleep(.05)
            else: raise Refusal('lock timeout')
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX)
        yield directory
    finally:
        if os.name == 'nt':
            try: f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError: pass
        else:
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()

def read(directory):
    p = safe(directory / 'claims.jsonl')
    if not p.exists(): return []
    data = p.read_bytes()
    if len(data)>4_000_000 or not data.endswith(b'\n'): raise Refusal('invalid or oversized ledger')
    try:
        rows = [json.loads(x) for x in data.splitlines()]
        if len(rows)>10000: raise ValueError()
        claims = {}; counts = {}; settled = set(); baseline = False
        for row in rows:
            if not isinstance(row, dict): raise ValueError()
            typ = row['type']
            if typ == 'baseline_and_claim':
                if baseline or claims or row['baseline'] != '1.278208' or not isinstance(row['sources'],dict) or set(row['sources']) != set(SOURCES): raise ValueError()
                baseline=True; claim=row['claim']; cid=claim['id']; amount=money(claim['amount']); claims[cid]=amount
                if cid != 'M04-PHASE2-FORMATS-20261029' or amount != D('.60') or claim['max_posts'] != 10: raise ValueError()
                counts[cid]=claim['max_posts']
            elif typ == 'reconcile':
                if not baseline: raise ValueError()
                previous=next((r for r in reversed(rows[:rows.index(row)]) if r['type']=='reconcile'),None)
                oldbase=money(previous['baseline']) if previous else money(rows[0]['baseline'])
                newbase=money(row['baseline']); proof=row['proof']
                if newbase<oldbase or set(proof['ledgers'])!={M02,M04} or set(proof['documents'])!={SOURCES[0],SOURCES[2],SOURCES[3]}: raise ValueError()
                for item in proof['ledgers'].values():
                    if type(item['bytes']) is not int or item['bytes']<=0 or type(item['count']) is not int or item['count']<0 or not re.fullmatch(r'[0-9a-f]{64}',item['sha256']): raise ValueError()
                    money(item['sum'])
                if any(not re.fullmatch(r'[0-9a-f]{64}',x) for x in proof['documents'].values()): raise ValueError()
                oldproof=previous['proof']['ledgers'] if previous else proof['initial_prefixes']
                if not previous:
                    if oldproof[M04]['sha256']!=rows[0]['sources'][M04] or oldproof[M04]['count']!=40 or money(oldproof[M04]['sum'])!=D('.930958') or oldproof[M02]['count']!=14 or money(oldproof[M02]['sum'])!=D('.309530'): raise ValueError()
                delta=D(0)
                for name in (M02,M04):
                    old=oldproof[name]; new=proof['ledgers'][name]
                    if not re.fullmatch(r'[0-9a-f]{64}',old['sha256']) or type(old['count']) is not int or type(old['bytes']) is not int or old['bytes']<=0 or old['bytes']>new['bytes'] or old['count']>new['count'] or money(old['sum'])>money(new['sum']): raise ValueError()
                    delta+=money(new['sum'])-money(old['sum'])
                if newbase!=oldbase+delta: raise ValueError()
            elif typ == 'claim':
                cid=row['id']; amount=money(row['amount'])
                if not baseline or not isinstance(cid,str) or not ID.fullmatch(cid) or cid in claims or amount <= 0 or not isinstance(row['max_posts'],int) or isinstance(row['max_posts'],bool) or not 1<=row['max_posts']<=10000: raise ValueError()
                claims[cid]=amount
                counts[cid]=row['max_posts']
            elif typ == 'count_amendment':
                cid=row['id']
                if set(row)!={'type','id','amount','old_max_posts','new_max_posts','evidence_path','evidence_sha256','ledger_sha256','reason','date'} or cid!='M02-PHASE12-MANUAL-REAL-20261030-01' or cid not in claims or cid in settled or claims[cid]!=D('.75') or money(row['amount'])!=claims[cid] or type(row['old_max_posts']) is not int or type(row['new_max_posts']) is not int or counts[cid]!=6 or row['old_max_posts']!=6 or row['new_max_posts']!=7 or not re.fullmatch(r'[0-9a-f]{64}',row['evidence_sha256']) or not re.fullmatch(r'[0-9a-f]{64}',row['ledger_sha256']) or row['reason']!='duplicate_known_configuration' or not isinstance(row['evidence_path'],str) or not row['evidence_path'].startswith('sessions/mesa-02/PHASE12/collaboration-runtime/assist-reconciliation/'): raise ValueError()
                counts[cid]=7
            elif typ == 'settlement':
                cid=row['id']; amount=money(row['amount'])
                if cid not in claims or any(x.get('type')=='settlement' and x.get('id')==cid for x in rows[:rows.index(row)]) or amount>claims[cid] or not re.fullmatch(r'[0-9a-f]{64}',row['evidence_sha256']) or row['kind'] not in ('estimate','reconciled'): raise ValueError()
                claims[cid]=amount
                settled.add(cid)
            else: raise ValueError()
        return rows
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, Refusal): raise Refusal('malformed ledger; manual reconciliation required')

def total(rows):
    if not rows: raise Refusal('baseline missing')
    claims={rows[0]['claim']['id']:money(rows[0]['claim']['amount'])}
    for r in rows[1:]:
        if r['type'] in ('claim','settlement'): claims[r['id']]=money(r['amount'])
    baseline=next((money(r['baseline']) for r in reversed(rows) if r['type']=='reconcile'),money(rows[0]['baseline']))
    return baseline + sum(claims.values(),D(0))

def append(directory, row):
    p=safe(directory / 'claims.jsonl')
    payload=(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode()
    if len(payload)>16384: raise Refusal('record too large')
    with open(p,'ab', buffering=0) as f:
        if f.write(payload)!=len(payload): raise Refusal('partial append; reconcile')
        os.fsync(f.fileno())

def operate(directory, action, cid=None, amount=None, posts=None, evidence=None, kind=None, date=None, source_check=True, expected_sha=None, ledger_sha=None):
    date = date or cdmx_date()
    with locked(directory) as directory:
        rows=read(directory)
        if action=='init':
            if rows: raise Refusal('already initialized')
            if source_check: raise Refusal('initialization already completed; no reset supported')
            sources={x:'0'*64 for x in SOURCES}
            row={'type':'baseline_and_claim','date':str(date),'baseline':'1.278208','sources':sources,'claim':{'id':'M04-PHASE2-FORMATS-20261029','amount':'0.60','max_posts':10}}
            if D('1.878208')>ceiling(date): raise Refusal('ceiling exceeded')
            append(directory,row); return {'accounted_envelope':'1.878208','claim':row['claim']}
        if not rows: raise Refusal('baseline missing')
        if action=='status':
            try: current=sources_current(rows) if source_check else True; reason=None if current else 'reconciliation required'
            except (Refusal,OSError,ValueError,KeyError,TypeError): current=False; reason='source unavailable or invalid; reconciliation required'
            return {'accounted_envelope':str(total(rows)), 'claims':len([r for r in rows if r['type'] in ('claim','baseline_and_claim')]), 'date_cdmx':str(date),'reconciliation_required':not current,'reason':reason}
        ceiling(date)
        if action=='reconcile':
            baseline,proof=snapshot(rows)
            row={'type':'reconcile','date':str(date),'baseline':baseline,'proof':proof}
            append(directory,row); return {'baseline':baseline,'accounted_envelope':str(total(read(directory))),'reconciled':True}
        if source_check and not sources_current(rows): raise Refusal('reconciliation required before reserve or settlement')
        if not isinstance(cid,str) or not ID.fullmatch(cid): raise Refusal('invalid claim ID')
        existing={rows[0]['claim']['id']} | {r['id'] for r in rows[1:] if r['type']=='claim'}
        if action=='amend_count':
            p=directory/'claims.jsonl'
            if not isinstance(expected_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',expected_sha) or digest(p)!=expected_sha: raise Refusal('claim journal changed')
            if cid!='M02-PHASE12-MANUAL-REAL-20261030-01' or amount!='0.75' or type(posts) is not int or posts!=7 or kind!='duplicate_known_configuration' or any(r.get('id')==cid and r['type'] in ('settlement','count_amendment') for r in rows): raise Refusal('count amendment invalid')
            claim=next((r for r in rows if r.get('type')=='claim' and r.get('id')==cid),None)
            if not claim or claim['amount']!='0.75' or claim['max_posts']!=6: raise Refusal('claim count or amount mismatch')
            if evidence!='sessions/mesa-02/PHASE12/collaboration-runtime/assist-reconciliation/RECONCILIATION.json': raise Refusal('invalid amendment evidence')
            ep=safe(ROOT/evidence); ev=json.loads(ep.read_text(encoding='utf-8-sig'))
            if ledger_sha!='87d37a1749e50bdd49a91221cb26b20c43dad6080fd0c4c8e0c091df732d68f8' or ev.get('status')!='COUNT_LIMIT_BLOCKS_THIRD_UNFINISHED_CALL' or ev.get('ledger',{}).get('sha256')!=ledger_sha or ev['ledger'].get('reservedCount')!=4 or ev['ledger'].get('finishedCount')!=4 or ev['ledger'].get('unknownCostCount')!=0 or ev['ledger'].get('unfinishedReservationCount')!=0: raise Refusal('amendment evidence invalid')
            ledger=safe(ROOT/'.runtime/mesa02/PHASE12/collaboration-runtime/runs/41f90e44da6d4fa481b41406e0ba1674/candidate/.runtime/manual-real-44ac82261ab74c5095fbef3b48bd0877.jsonl')
            if ledger.with_suffix(ledger.suffix+'.lock').exists() or digest(ledger)!=ledger_sha or ledger.with_suffix(ledger.suffix+'.lock').exists(): raise Refusal('provider ledger changed or locked')
            row={'type':'count_amendment','id':cid,'amount':amount,'old_max_posts':6,'new_max_posts':7,'evidence_path':evidence,'evidence_sha256':digest(ep),'ledger_sha256':ledger_sha,'reason':kind,'date':str(date)}
        elif action=='reserve':
            n=money(amount)
            if cid in existing or n<=0 or not isinstance(posts,int) or isinstance(posts,bool) or not 1<=posts<=10000: raise Refusal('invalid or duplicate claim')
            if total(rows)+n>ceiling(date): raise Refusal('ceiling exceeded')
            row={'type':'claim','id':cid,'amount':str(n),'max_posts':posts,'date':str(date)}
        elif action=='settle':
            if cid not in existing or any(r.get('type')=='settlement' and r.get('id')==cid for r in rows) or kind not in ('estimate','reconciled') or not evidence: raise Refusal('settlement requires a pending claim, known amount and evidence')
            n=money(amount); current=next((money(r['amount']) for r in reversed(rows[1:]) if r.get('id')==cid),money(rows[0]['claim']['amount']))
            if n>current: raise Refusal('settlement exceeds held amount')
            ep=safe(ROOT / evidence)
            if not ep.is_file(): raise Refusal('evidence file missing')
            ev=json.loads(ep.read_text(encoding='utf-8'))
            if not isinstance(ev,dict) or ev.get('claim_id')!=cid or ev.get('kind')!=kind or ev.get('amount_usd')!=str(n) or ev.get('status')!='complete' or ev.get('unknown') is not False or ev.get('full_pending') is not False or not isinstance(ev.get('description'),str) or not 10<=len(ev['description'])<=1000: raise Refusal('settlement evidence incomplete or unknown')
            row={'type':'settlement','id':cid,'amount':str(n),'kind':kind,'evidence_sha256':digest(ep),'evidence_path':str(ep.relative_to(ROOT)),'date':str(date)}
        else: raise Refusal('unknown action')
        append(directory,row); return row

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('init'); sub.add_parser('status'); sub.add_parser('reconcile')
    r=sub.add_parser('reserve'); r.add_argument('id'); r.add_argument('amount'); r.add_argument('max_posts',type=int)
    a7=sub.add_parser('amend-count'); a7.add_argument('id'); a7.add_argument('amount'); a7.add_argument('max_posts',type=int); a7.add_argument('--evidence',required=True); a7.add_argument('--expected-sha',required=True); a7.add_argument('--ledger-sha',required=True)
    s=sub.add_parser('settle'); s.add_argument('id'); s.add_argument('amount'); s.add_argument('--kind',required=True,choices=['estimate','reconciled']); s.add_argument('--evidence',required=True)
    a=p.parse_args()
    try: print(json.dumps(operate(DEFAULT,'amend_count' if a.action=='amend-count' else a.action,getattr(a,'id',None),getattr(a,'amount',None),getattr(a,'max_posts',None),getattr(a,'evidence',None),'duplicate_known_configuration' if a.action=='amend-count' else getattr(a,'kind',None),expected_sha=getattr(a,'expected_sha',None),ledger_sha=getattr(a,'ledger_sha',None))))
    except (Refusal, OSError, ValueError, KeyError, json.JSONDecodeError) as e: print('REFUSED: '+str(e),file=sys.stderr); return 1
    return 0
if __name__=='__main__': sys.exit(main())
