from __future__ import annotations
import hashlib, json, os, secrets, sqlite3, threading, uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .recovery_startup import ensure_scoped_startup

DATA = Path(os.environ.get("APP_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
DB = DATA / "companion.sqlite3"
LOCK = threading.RLock()

def now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
def ident(): return uuid.uuid4().hex
def digest(token): return hashlib.sha256(token.encode()).hexdigest()

@contextmanager
def connect():
    ensure_scoped_startup(DB.parent)
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=20, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    try: yield db
    finally: db.close()

def migrate():
    with LOCK, connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
        INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
        CREATE TABLE IF NOT EXISTS objects(kind TEXT NOT NULL,id TEXT NOT NULL,session_id TEXT NOT NULL,
          owner_id TEXT,revision INTEGER NOT NULL DEFAULT 1,data TEXT NOT NULL,created_at TEXT NOT NULL,
          PRIMARY KEY(kind,id));
        CREATE INDEX IF NOT EXISTS objects_session ON objects(session_id,kind);
        CREATE TABLE IF NOT EXISTS phase6_receipts (session_id TEXT NOT NULL, actor_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, status INTEGER, result TEXT, PRIMARY KEY(session_id,actor_id,request_id));
        CREATE TABLE IF NOT EXISTS notebook_import_receipts (session_id TEXT NOT NULL, actor_id TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, item_ids TEXT NOT NULL, PRIMARY KEY(session_id,actor_id,request_id));
        CREATE TABLE IF NOT EXISTS w15_chapter_receipts (session_id TEXT NOT NULL, actor_id TEXT NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, chapter_id TEXT NOT NULL, PRIMARY KEY(session_id,actor_id,request_key));
        CREATE TABLE IF NOT EXISTS w15_cue_receipts (session_id TEXT NOT NULL, actor_id TEXT NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL, cue_id TEXT NOT NULL, revision INTEGER NOT NULL, PRIMARY KEY(session_id,actor_id,request_key));
        CREATE TABLE IF NOT EXISTS phase10_vaults (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, status TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS phase10_receipts (session_id TEXT NOT NULL, actor_id TEXT NOT NULL, operation TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, status INTEGER, result TEXT, refs TEXT NOT NULL, PRIMARY KEY(session_id,actor_id,operation,request_id));
        CREATE INDEX IF NOT EXISTS phase10_unresolved ON phase10_receipts(session_id,actor_id,operation,state);
        CREATE TABLE IF NOT EXISTS phase12_jobs (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, actor_id TEXT NOT NULL,
          credential_hash TEXT NOT NULL, role TEXT NOT NULL, request_id TEXT NOT NULL,
          kind TEXT NOT NULL, fingerprint TEXT NOT NULL, payload TEXT NOT NULL, ref TEXT NOT NULL,
          source_id TEXT NOT NULL, state TEXT NOT NULL, result TEXT, media BLOB, timing TEXT NOT NULL,
          transport TEXT NOT NULL DEFAULT 'not_started', UNIQUE(session_id,actor_id,request_id));
        CREATE INDEX IF NOT EXISTS phase12_queue ON phase12_jobs(state,seq);
        CREATE TABLE IF NOT EXISTS phase12_caption_feed (session_id TEXT NOT NULL, seq INTEGER NOT NULL, source_id TEXT NOT NULL, moment_id TEXT NOT NULL UNIQUE, ref TEXT NOT NULL, language TEXT NOT NULL, run_id TEXT, PRIMARY KEY(session_id,seq));
        CREATE INDEX IF NOT EXISTS phase12_feed_session ON phase12_caption_feed(session_id,seq);
        CREATE TABLE IF NOT EXISTS phase12_feed_floor (session_id TEXT PRIMARY KEY, seq INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS phase12_feed_counter (session_id TEXT PRIMARY KEY, seq INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS phase12_feed_sources (session_id TEXT NOT NULL,source_id TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(session_id,source_id));
        CREATE TABLE IF NOT EXISTS phase12_original_audio (source_id TEXT PRIMARY KEY,session_id TEXT NOT NULL,mime TEXT NOT NULL,digest TEXT NOT NULL,data BLOB NOT NULL);
        CREATE TABLE IF NOT EXISTS phase12_preferences (session_id TEXT NOT NULL, actor_id TEXT NOT NULL,
          language TEXT NOT NULL, show_original INTEGER NOT NULL, PRIMARY KEY(session_id,actor_id));
        CREATE TABLE IF NOT EXISTS credentials(hash TEXT PRIMARY KEY,role TEXT NOT NULL,session_id TEXT NOT NULL,
          owner_id TEXT NOT NULL,created_at TEXT NOT NULL);
        """)
        columns = {r[1] for r in db.execute("PRAGMA table_info(w15_chapter_receipts)")}
        if 'operation' not in columns: db.execute("ALTER TABLE w15_chapter_receipts ADD COLUMN operation TEXT NOT NULL DEFAULT 'create'")
        if 'committed_revision' not in columns: db.execute("ALTER TABLE w15_chapter_receipts ADD COLUMN committed_revision INTEGER NOT NULL DEFAULT 1")
        from . import phase11, phase11_assist, phase12_sources
        phase11.migrate(db)
        phase11_assist.migrate(db)
        phase12_sources.migrate(db)
        from . import phase12_collaboration
        phase12_collaboration.migrate(db)
        if "calls" not in {r[1] for r in db.execute("PRAGMA table_info(phase10_vaults)")}: db.execute("ALTER TABLE phase10_vaults ADD COLUMN calls INTEGER NOT NULL DEFAULT 0")
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='phase34_calls'").fetchone():
            for row in db.execute("SELECT session_id,calls FROM phase34_calls").fetchall():
                sid,n=row['session_id'],row['calls']
                if not db.execute("SELECT 1 FROM objects WHERE kind='session' AND id=?",(sid,)).fetchone(): continue
                old=db.execute("SELECT data FROM objects WHERE kind='admission' AND id=?",(sid,)).fetchone()
                count=max(n,json.loads(old['data']).get('calls',0) if old else 0)
                value=json.dumps({'id':sid,'calls':count})
                db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('admission',?,?,NULL,1,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data,revision=objects.revision+1",(sid,sid,value,now()))
            db.execute("DROP TABLE phase34_calls")
        db.commit()

def put(kind, sid, data, owner=None, oid=None, revision=1, *, original_audio=None):
    oid = oid or ident(); value = dict(data); value.setdefault("id", oid)
    with LOCK, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if kind=="p10vaultentry":
            if sid != "vault:"+str(owner) or not db.execute("SELECT 1 FROM phase10_vaults WHERE id=? AND status='active'",(owner,)).fetchone() or value.get("vaultId") != owner: db.rollback(); raise KeyError(owner)
        elif kind!="session" and not db.execute("SELECT 1 FROM objects WHERE kind='session' AND id=?",(sid,)).fetchone(): db.rollback(); raise KeyError(sid)
        if kind in ("viewer","conversation","bookmark","share") and owner and not db.execute("SELECT 1 FROM credentials WHERE session_id=? AND owner_id=? AND role='viewer'",(sid,owner)).fetchone():db.rollback();raise KeyError(owner)
        if original_audio is not None:
            if kind!='source' or not isinstance(original_audio,tuple) or len(original_audio)!=3: db.rollback();raise ValueError('Invalid original audio.')
            audio,mime,expected=original_audio
            if not isinstance(audio,bytes) or not audio or len(audio)>12*1024*1024 or hashlib.sha256(audio).hexdigest()!=expected:db.rollback();raise ValueError('Invalid original audio.')
            existing=db.execute('SELECT COUNT(*),COALESCE(SUM(length(data)),0) FROM phase12_original_audio WHERE session_id=?',(sid,)).fetchone()
            if existing[0]>=16 or existing[1]+len(audio)>64*1024*1024:db.rollback();raise OriginalAudioCapacity()
        db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)",
          (kind,oid,sid,owner,revision,json.dumps(value,ensure_ascii=False),now()))
        if original_audio is not None:db.execute('INSERT INTO phase12_original_audio VALUES(?,?,?,?,?)',(oid,sid,mime,expected,audio))
        db.commit()
    return value

def get(kind, oid, sid=None):
    with LOCK, connect() as db:
        if sid is None: row=db.execute("SELECT data,revision FROM objects WHERE kind=? AND id=?",(kind,oid)).fetchone()
        else: row=db.execute("SELECT data,revision FROM objects WHERE kind=? AND id=? AND session_id=?",(kind,oid,sid)).fetchone()
    if not row:return None
    value=json.loads(row["data"]); value["_revision"]=row["revision"]; return value

def all(kind, sid):
    with LOCK, connect() as db:
        rows=db.execute("SELECT data,revision FROM objects WHERE kind=? AND session_id=? ORDER BY created_at",(kind,sid)).fetchall()
    result=[]
    for r in rows:
        v=json.loads(r["data"]); v["_revision"]=r["revision"]; result.append(v)
    return result

class OriginalAudioCapacity(RuntimeError):
    pass

class StaleMaterialVersion(RuntimeError):
    pass

def save(kind, value, revision=None, *, expected_material_version=None, impact_change=None):
    if expected_material_version is not None and kind != "material":
        raise ValueError("Material version guard requires a material.")
    oid=value["id"]
    with LOCK, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT revision,data,session_id FROM objects WHERE kind=? AND id=?",(kind,oid)).fetchone()
        if not row: db.rollback(); raise KeyError(oid)
        if expected_material_version is not None and json.loads(row["data"]).get("currentVersion") != expected_material_version:
            db.rollback(); raise StaleMaterialVersion()
        expected = revision if revision is not None else value.get("_revision")
        if expected is not None and row[0]!=expected: db.rollback(); raise RuntimeError("stale")
        if impact_change is not None:
            if kind != 'source': raise ValueError('Impact change requires a source.')
            from . import waves21_impact_runtime
            actor_id, request_id, change = impact_change
            if waves21_impact_runtime.check_change_request(db, row['session_id'], actor_id, request_id, oid, row[0], change):
                raise RuntimeError('Unexpected source change replay')
        n=row[0]+1; value=dict(value); value.pop("_revision",None)
        db.execute("UPDATE objects SET data=?,revision=? WHERE kind=? AND id=?",(json.dumps(value,ensure_ascii=False),n,kind,oid))
        if impact_change is not None:
            waves21_impact_runtime.source_changed(db, row['session_id'], oid, row[0], actor_id, request_id, change)
            from . import waves23_moment_index
            waves23_moment_index.source_changed_db(db, row['session_id'], oid, row[0])
        if kind == "p10material":
            db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE source_id=? AND state IN ('queued','running','complete')",(oid,))
        if kind == "source":
            if impact_change is None:
                from . import waves23_moment_media
                waves23_moment_media.source_changed_db(db, row['session_id'], oid)
            if value.get('status')!='active':db.execute("DELETE FROM phase12_original_audio WHERE source_id=?",(oid,))
            for material in db.execute("SELECT id,data FROM objects WHERE kind='p10material'").fetchall():
                if any(ref.get('sourceId')==oid for ref in json.loads(material['data']).get('refs',[]) if isinstance(ref,dict)):
                    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE source_id=? AND state IN ('queued','running','complete')",(material['id'],))
            phase10_invalidate_source_db(db, row['session_id'], oid)
            from . import waves21_speech_runtime
            waves21_speech_runtime.invalidate_source_db(db, row['session_id'], oid)
            db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE source_id=? AND state IN ('queued','running','complete')",(oid,))
        db.commit()
        if kind == "source":
            from . import waves20_scheduler
            if waves20_scheduler._service is not None:
                waves20_scheduler._service.invalidate_source(row['session_id'], oid, str(n))
    return get(kind,oid)

def remove(kind, oid):
    with LOCK, connect() as db: db.execute("DELETE FROM objects WHERE kind=? AND id=?",(kind,oid))

def add_token(token, role, sid, owner):
    with LOCK, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM objects WHERE kind='session' AND id=?",(sid,)).fetchone():db.rollback();raise KeyError(sid)
        db.execute("INSERT INTO credentials VALUES(?,?,?, ?,?)",(digest(token),role,sid,owner,now()));db.commit()

def cleanup_session(sid, token_hash):
    with LOCK, connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM credentials WHERE hash=? AND session_id=? AND role='creator'",(token_hash,sid)).fetchone():db.rollback();raise KeyError(sid)
        phase10_cleanup_db(db,sid)
        from . import waves23_moment_media
        waves23_moment_media.cleanup_db(db,sid)
        db.execute("DELETE FROM w15_chapter_receipts WHERE session_id=?",(sid,))
        db.execute("DELETE FROM w15_cue_receipts WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_jobs WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_original_audio WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_caption_feed WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_feed_floor WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_feed_counter WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_feed_sources WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_preferences WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_grants WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_grant_receipts WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_recaps WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase12_recap_receipts WHERE session_id=?",(sid,))
        db.execute("DELETE FROM phase6_receipts WHERE session_id=?",(sid,))
        db.execute("DELETE FROM credentials WHERE session_id=?",(sid,))
        db.execute("DELETE FROM objects WHERE session_id=?",(sid,))
        db.commit()

def auth(token):
    if not token:return None
    with LOCK, connect() as db:
        r=db.execute("SELECT role,session_id,owner_id FROM credentials WHERE hash=?",(digest(token),)).fetchone()
    return dict(role=r[0],sid=r[1],owner=r[2]) if r else None

def revoke_owner(owner):
    with LOCK, connect() as db: db.execute("DELETE FROM credentials WHERE owner_id=?",(owner,))


def phase10_cleanup_db(db, sid, owner=None):
    """Called within caller's mutation transaction; lane-owned tables may add hooks here."""
    from . import waves21_speech_runtime, waves22_lifecycle, waves24_channel_pack, waves23_speech_profiles, waves24_activity_handoff, waves25_listening_preferences
    waves21_speech_runtime.cleanup_db(db, sid, owner)
    waves22_lifecycle.cleanup_db(db, sid, owner)
    waves24_channel_pack.cleanup_db(db, sid, owner)
    waves23_speech_profiles.cleanup_db(db, sid, owner)
    waves24_activity_handoff.cleanup_db(db, sid, owner)
    waves25_listening_preferences.cleanup_db(db, sid, owner)
    from . import waves28_handoff_status
    waves28_handoff_status.cleanup_db(db, sid, owner)
    for row in db.execute("SELECT id,data FROM objects WHERE kind='p10vaultentry'").fetchall():
        try: entry=json.loads(row["data"])
        except (ValueError,TypeError): continue
        ref=entry.get("ref")
        source_affected=owner is None and isinstance(ref,dict) and ref.get("sessionId")==sid
        viewer_deleted=owner is not None and entry.get("originSessionId")==sid and entry.get("originViewerOwner")==owner
        if source_affected or viewer_deleted:
            phase10_forget_entry_db(db,entry.get("vaultId"),row["id"])
            if viewer_deleted:
                db.execute("DELETE FROM objects WHERE kind='p10vaultentry' AND id=?",(row["id"],))
    if owner is None:
        db.execute("DELETE FROM phase10_receipts WHERE session_id=?", (sid,))
    else:
        from . import phase11
        for record in db.execute("SELECT id FROM phase11_activities").fetchall():
            activity=phase11.load(db,record['id'])
            participants={p['id'] for p in db.execute("SELECT id FROM phase11_participants WHERE activity_id=? AND origin_session=? AND origin_owner=?",(record['id'],sid,owner)).fetchall()}
            for contribution in activity.get('contributions',[]):
                if contribution['participant'] in participants:phase11.phase12_invalidate_contribution(db,activity,contribution['id'])
        db.execute("UPDATE phase12_grants SET status='revoked',revision=revision+1 WHERE session_id=? AND author_owner=? AND status='active'",(sid,owner))
        db.execute("DELETE FROM phase10_receipts WHERE session_id=? AND actor_id=?", (sid, owner))
        db.execute("DELETE FROM phase12_jobs WHERE session_id=? AND actor_id=?", (sid, owner))
        db.execute("DELETE FROM phase12_preferences WHERE session_id=? AND actor_id=?", (sid, owner))


def phase10_forget_entry_db(db, vault_id, entry_id):
    """Invalidate vault receipt content inside the same transaction as forgetting."""
    scope="vault:"+vault_id
    for row in db.execute("SELECT operation,request_id,refs FROM phase10_receipts WHERE session_id=? AND actor_id=?",(scope,vault_id)).fetchall():
        try: dependencies=json.loads(row["refs"])
        except (ValueError,TypeError): dependencies=[]
        if any(isinstance(d,dict) and d.get("entryId")==entry_id for d in dependencies):
            db.execute("UPDATE phase10_receipts SET state=CASE WHEN state IN ('pending','unknown') THEN 'unknown' ELSE 'failed' END,status=409,result=NULL WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?",(scope,vault_id,row["operation"],row["request_id"]))


def phase10_invalidate_source_db(db, session_id, source_id):
    """Redact matching receipt outputs in the same transaction as a source mutation."""
    for row in db.execute("SELECT id,data FROM objects WHERE kind='p10vaultentry'").fetchall():
        try: entry=json.loads(row['data'])
        except (TypeError,ValueError): continue
        ref=entry.get('ref')
        if isinstance(ref,dict) and ref.get('sessionId')==session_id and ref.get('sourceId')==source_id and isinstance(entry.get('vaultId'),str):
            phase10_forget_entry_db(db,entry['vaultId'],row['id'])
    for row in db.execute("SELECT session_id,actor_id,operation,request_id,refs FROM phase10_receipts WHERE session_id=?",(session_id,)).fetchall():
        try: refs=json.loads(row['refs'])
        except (TypeError,ValueError): refs=[]
        if any(isinstance(ref,dict) and ref.get('sourceId')==source_id for ref in refs):
            db.execute("UPDATE phase10_receipts SET state=CASE WHEN state IN ('pending','unknown') THEN 'unknown' ELSE 'failed' END,status=409,result=NULL WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?",(row['session_id'],row['actor_id'],row['operation'],row['request_id']))
