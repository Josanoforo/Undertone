"""Phase 10 shared, side-effect-free reference validation. Interface v1."""
import re

_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$", re.ASCII)
_KEYS = {"sessionId", "sourceId", "sourceRevision", "momentId", "startMs", "endMs"}

class Phase10Error(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

def parse_ref(value):
    if not isinstance(value, dict) or set(value) != _KEYS:
        raise Phase10Error("invalid_ref", "A complete moment reference is required.")
    for key in ("sessionId", "sourceId", "momentId"):
        if not isinstance(value[key], str) or not _ID.fullmatch(value[key]):
            raise Phase10Error("invalid_ref", "The moment reference is invalid.")
    for key in ("sourceRevision", "startMs", "endMs"):
        if type(value[key]) is not int or value[key] < (1 if key == "sourceRevision" else 0) or value[key] > 864000000:
            raise Phase10Error("invalid_ref", "The moment reference is invalid.")
    if value["endMs"] < value["startMs"]:
        raise Phase10Error("invalid_ref", "The moment time range is invalid.")
    return dict(value)

def parse_source_ref(value):
    """Parse an untimed source identity; it is not a moment or playback range."""
    if not isinstance(value, dict) or set(value) != {"sessionId", "sourceId", "sourceRevision"}:
        raise Phase10Error("invalid_ref", "A complete source reference is required.")
    for key in ("sessionId", "sourceId"):
        if not isinstance(value[key], str) or not _ID.fullmatch(value[key]):
            raise Phase10Error("invalid_ref", "The source reference is invalid.")
    revision = value["sourceRevision"]
    if type(revision) is not int or not 1 <= revision <= 864000000:
        raise Phase10Error("invalid_ref", "The source reference is invalid.")
    return dict(value)


def resolve_refs(refs, lookup, actor, purpose):
    if not isinstance(refs, list) or not 1 <= len(refs) <= 20:
        raise Phase10Error("invalid_refs", "Select between one and twenty moments.")
    parsed = [parse_ref(ref) for ref in refs]
    if len({tuple(sorted(ref.items())) for ref in parsed}) != len(parsed):
        raise Phase10Error("invalid_refs", "Select each moment only once.")
    result = []
    for ref in parsed:
        row = lookup(actor, dict(ref), purpose)
        if not isinstance(row, dict) or row.get("eligible") is not True or row.get("ref") != ref or not isinstance(row.get("source"), dict) or not isinstance(row.get("moment"), dict):
            raise Phase10Error("stale_context", "A selected moment is unavailable or has changed.", 409)
        result.append(row)
    return result

def recheck_refs(refs, lookup, actor, purpose):
    return resolve_refs(refs, lookup, actor, purpose)


class Context:
    """Production session context; store import is deferred until construction."""
    def __init__(self, handler, sid, actor, *, credential_digest=None):
        from . import store
        self.handler, self.sid, self.actor = handler, sid, dict(actor)
        self.store, self.lock = store, store.LOCK
        self._credential_digest = credential_digest

    def check_actor(self):
        from . import lifecycle
        if self._credential_digest is None:
            current = self.store.auth(getattr(self.handler, "_auth_token", ""))
        else:
            digest = self._credential_digest
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise Phase10Error("not_found", "The session or capability is unavailable.", 404)
            with self.lock, self.store.connect() as db:
                row = db.execute("SELECT role,session_id,owner_id FROM credentials WHERE hash=?", (digest,)).fetchone()
            current = dict(role=row[0], sid=row[1], owner=row[2]) if row else None
        session = self.store.get("session", self.sid, self.sid)
        if current != self.actor or not session or not lifecycle.active(session):
            raise Phase10Error("not_found", "The session or capability is unavailable.", 404)
        return current

    def resolve(self, refs, purpose="session", grant_id=None):
        from .http import expired
        if purpose not in ("session", "retention"):
            raise Phase10Error("invalid_purpose", "The requested purpose is invalid.")
        if purpose == "retention" and not getattr(self, "vault_id", None):
            raise Phase10Error("not_found", "The retained moment is unavailable.", 404)
        def lookup(actor, ref, use):
            if use == "session":
                self.check_actor()
                if ref["sessionId"] != self.sid:
                    try:
                        from . import waves16_continuation
                    except ImportError:
                        return None
                    return waves16_continuation.resolve_ref(self, ref)
            elif not isinstance(grant_id, str) or not grant_id:
                return None
            sid = ref["sessionId"]
            src = self.store.get("source", ref["sourceId"], sid)
            moment = self.store.get("p10moment", ref["momentId"], sid)
            if not src or not moment or moment.get("ref") != ref or src.get("_revision") != ref["sourceRevision"] or src.get("status") != "active" or expired(src): return None
            if moment.get("alignment",{}).get("origin")=="capture" or src.get("p10Frame"):
                from .phase10_timeline import frame_moment
                try: frame=frame_moment(src)
                except Phase10Error:return None
                if frame.get("ref")!=ref or frame.get("alignment")!=moment.get("alignment") or frame.get("captureRunId")!=moment.get("captureRunId"):return None
            if use == "retention":
                grant = self.store.get("p10grant", grant_id, sid)
                if not grant or grant.get("status") != "active" or grant.get("ref") != ref or not src.get("audienceVisible", False): return None
            elif actor.get("role") != "creator" and not src.get("audienceVisible", False): return None
            return {"eligible":True, "ref":ref, "source":src, "moment":moment}
        with self.lock:
            return resolve_refs(refs, lookup, self.actor, purpose)

    def resolve_source(self, ref):
        """Resolve a same-session, current untimed source under live actor rights."""
        from .http import expired
        ref = parse_source_ref(ref)
        with self.lock:
            self.check_actor()
            if ref["sessionId"] != self.sid:
                raise Phase10Error("stale_context", "The source is unavailable or has changed.", 409)
            source = self.store.get("source", ref["sourceId"], self.sid)
            if (not source or source.get("_revision") != ref["sourceRevision"]
                    or source.get("status") != "active" or expired(source)
                    or (self.actor.get("role") != "creator" and not source.get("audienceVisible", False))):
                raise Phase10Error("stale_context", "The source is unavailable or has changed.", 409)
            return {"eligible": True, "ref": ref, "source": source}

    def citations(self, rows):
        return [{"ref":r["ref"], "title":str(r["source"].get("title", "Source"))[:200], "at":r["source"].get("capturedAtISO") or r["source"].get("at"), "excerpt":str(r["moment"].get("text", ""))[:220]} for r in rows]

    @staticmethod
    def parse_generated_refs(refs):
        import json
        if not isinstance(refs,list) or not 1<=len(refs)<=20:
            raise Phase10Error("invalid_refs", "Select between one and twenty references.")
        parsed=[parse_source_ref(ref) if isinstance(ref,dict) and set(ref)=={"sessionId","sourceId","sourceRevision"} else parse_ref(ref) for ref in refs]
        if len({json.dumps(ref,sort_keys=True,separators=(",",":")) for ref in parsed})!=len(parsed):
            raise Phase10Error("invalid_refs", "Select each reference only once.")
        return parsed

    def resolve_generated_refs(self, refs):
        rows=[]
        for ref in refs:
            rows.append(self.resolve_source(ref) if "momentId" not in ref else self.resolve([ref])[0])
        return rows

    def cleanup_hooks(self, db, owner=None):
        self.store.phase10_cleanup_db(db, self.sid, owner)

    def operation_status(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}",request_id):
            raise Phase10Error("invalid_request_id", "The request ID is invalid.")
        with self.lock, self.store.connect() as db:
            self.check_actor()
            rows=db.execute("SELECT operation,state,status FROM phase10_receipts WHERE session_id=? AND actor_id=? AND request_id=?",(self.sid,self.actor["owner"],request_id)).fetchall()
            if len(rows)!=1: raise Phase10Error("not_found", "Operation not found.",404)
            row=rows[0]
            return {"operation":{"requestId":request_id,"operation":row["operation"],"state":row["state"],"status":row["status"]}}

    def generate(self, operation, request_id, payload, refs, invoke):
        import hashlib, json
        from . import admission
        if not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}",request_id):
            raise Phase10Error("invalid_request_id", "The request ID is invalid.")
        if not isinstance(operation,str) or not re.fullmatch(r"[a-z0-9_.-]{1,80}",operation):
            raise Phase10Error("invalid_operation", "The operation is invalid.")
        fp=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        parsed=self.parse_generated_refs(refs)
        source_refs=[ref for ref in parsed if "momentId" not in ref]
        moment_refs=[ref for ref in parsed if "momentId" in ref]
        def bind_selected():
            if moment_refs:self.handler._p10_refs=moment_refs
            if source_refs:self.handler._p10_source_refs=source_refs
        owner=self.actor["owner"]
        with self.lock, self.store.connect() as db:
            self.check_actor(); db.execute("BEGIN IMMEDIATE")
            old=db.execute("SELECT * FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?",(self.sid,owner,operation,request_id)).fetchone()
            if old:
                if old["fingerprint"]!=fp: raise Phase10Error("request_conflict","This request ID is bound to another payload.",409)
                if old["state"] in ("pending","unknown"): raise Phase10Error("request_pending","The request outcome is unresolved.",409)
                if old["state"]=="failed": raise Phase10Error("known_failure","The request failed; use a new ID for a deliberate retry.",409)
                oldrefs=self.parse_generated_refs(json.loads(old["refs"])); self.resolve_generated_refs(oldrefs)
                self.handler._p10_refs=[ref for ref in oldrefs if "momentId" in ref]
                self.handler._p10_source_refs=[ref for ref in oldrefs if "momentId" not in ref]
                return old["status"],json.loads(old["result"])
            if db.execute("SELECT 1 FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND state IN ('pending','unknown')",(self.sid,owner,operation)).fetchone():
                raise Phase10Error("operation_unresolved","A prior operation has an unresolved outcome.",409)
            self.resolve_generated_refs(parsed)
            db.execute("INSERT INTO phase10_receipts VALUES(?,?,?,?,?,'pending',NULL,NULL,?)",(self.sid,owner,operation,request_id,fp,json.dumps(parsed)))
            db.commit()
        def finish(state,status,result=None):
            with self.lock,self.store.connect() as db:
                db.execute("UPDATE phase10_receipts SET state=?,status=?,result=? WHERE session_id=? AND actor_id=? AND operation=? AND request_id=? AND state='pending'",(state,status,json.dumps(result,ensure_ascii=False) if result is not None else None,self.sid,owner,operation,request_id))
        transport_started=False
        try:
            with admission.lease(self.sid):
                with self.lock:
                    rows=self.resolve_generated_refs(parsed)
                with admission.operation(self.sid):
                    transport_started=True
                    result=invoke(rows)
        except (admission.Busy,admission.Ceiling) as exc:
            finish("failed",503 if isinstance(exc,admission.Busy) else 429)
            raise Phase10Error("busy" if isinstance(exc,admission.Busy) else "session_call_limit", "Generation admission is unavailable.",503 if isinstance(exc,admission.Busy) else 429)
        except KnownUnavailable:
            finish("failed",503)
            raise Phase10Error("provider_unavailable","The provider is unavailable before transport.",503)
        except Phase10Error:
            finish("unknown" if transport_started else "failed",409)
            raise
        except Exception:
            finish("unknown" if transport_started else "failed",503)
            raise Phase10Error("provider_outcome_unknown" if transport_started else "provider_unavailable","The provider outcome is unknown; do not retry." if transport_started else "The provider is unavailable before transport.",503)
        with self.lock:
            try:
                self.resolve_generated_refs(parsed)
            except Phase10Error:
                with self.store.connect() as db:
                    db.execute("UPDATE phase10_receipts SET state='failed',status=409,result=NULL WHERE session_id=? AND actor_id=? AND operation=? AND request_id=? AND state IN ('pending','unknown')",(self.sid,owner,operation,request_id))
                raise Phase10Error("stale_context","A selected moment changed during generation.",409)
            finish("complete",200,result); bind_selected()
            return 200,result

class KnownUnavailable(Exception):
    """Provider is known unavailable before transport is attempted."""


class VaultContext(Context):
    """A distinct opaque vault credential; never accept a session bearer as a vault."""
    def __init__(self, handler, allow_create=False):
        from . import store
        self.handler=handler; self.sid=None; self.store=store; self.lock=store.LOCK; self.actor=None; self.vault_id=None
        header=handler.headers.get("Authorization","")
        token=header[7:] if header.startswith("Bearer ") else ""
        if not token:
            if allow_create:return
            raise Phase10Error("unauthorized","A vault capability is required.",401)
        with self.lock,store.connect() as db:
            row=db.execute("SELECT id FROM phase10_vaults WHERE token_hash=? AND status='active'",(store.digest(token),)).fetchone()
        if not row:raise Phase10Error("unauthorized","The vault capability is invalid.",401)
        self.vault_id=row["id"]
        self.actor={"role":"vault","owner":self.vault_id,"sid":None}

    def check_actor(self):
        header=self.handler.headers.get("Authorization","")
        token=header[7:] if header.startswith("Bearer ") else ""
        with self.lock,self.store.connect() as db:
            row=db.execute("SELECT id FROM phase10_vaults WHERE token_hash=? AND status='active'",(self.store.digest(token),)).fetchone() if token else None
        if not row or row["id"]!=self.vault_id:raise Phase10Error("unauthorized","The vault capability is unavailable.",401)
        return self.actor

    def resolve(self, refs, purpose="retention", grant_id=None, entry_id=None):
        with self.lock:
            self.check_actor()
            if purpose!="retention":raise Phase10Error("invalid_purpose","Vault references require retention authority.",403)
            entry=self.store.get("p10vaultentry",entry_id) if isinstance(entry_id,str) else None
            if not entry or entry.get("vaultId")!=self.vault_id or entry.get("active") is not True or entry.get("status")!="active" or entry.get("grantId")!=grant_id or len(refs)!=1 or entry.get("ref")!=refs[0]:
                raise Phase10Error("stale_context","The selected vault entry is unavailable.",409)
            return super().resolve(refs,purpose,grant_id)

    def verify_viewer(self, token, sid):
        from . import lifecycle
        actor=self.store.auth(token) if isinstance(token,str) else None
        session=self.store.get("session",sid,sid)
        if not actor or actor.get("role")!="viewer" or actor.get("sid")!=sid or not session or not lifecycle.active(session):
            raise Phase10Error("not_found","Viewer capability is unavailable.",404)
        return actor


    def verify_viewer_header(self, sid):
        value=self.handler.headers.get("X-Viewer-Capability", "")
        return self.verify_viewer(value,sid)

    def resolve_entries(self, dependencies):
        if not isinstance(dependencies,list) or not 1<=len(dependencies)<=20:
            raise Phase10Error("invalid_entries","Select between one and twenty entries.")
        result=[]
        with self.lock:
            self.check_actor()
            for dep in dependencies:
                if not isinstance(dep,dict) or set(dep)!={"entryId","entryRevision","grantId","ref"} or not isinstance(dep["entryId"],str) or type(dep["entryRevision"]) is not int or dep["entryRevision"]<1:
                    raise Phase10Error("invalid_entries","The entry selection is invalid.")
                entry=self.store.get("p10vaultentry",dep["entryId"])
                if not entry or entry.get("vaultId")!=self.vault_id or entry.get("active") is not True or entry.get("status")!="active" or entry.get("_revision")!=dep["entryRevision"] or entry.get("ref")!=dep["ref"] or entry.get("grantId")!=dep["grantId"]:
                    raise Phase10Error("stale_context","A selected vault entry is unavailable.",409)
                if dep["ref"] is None:
                    if dep["grantId"] is not None or not isinstance(entry.get("interpretation"),str):raise Phase10Error("stale_context","The note is unavailable.",409)
                    result.append({"entry":entry,"source":None,"moment":None})
                else:
                    row=self.resolve([dep["ref"]],grant_id=dep["grantId"],entry_id=dep["entryId"])[0]
                    result.append({"entry":entry,**row})
        return result

    def operation_status(self, request_id):
        if not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}",request_id):raise Phase10Error("invalid_request_id","The request ID is invalid.")
        with self.lock,self.store.connect() as db:
            self.check_actor()
            rows=db.execute("SELECT operation,state,status FROM phase10_receipts WHERE session_id=? AND actor_id=? AND request_id=?",("vault:"+self.vault_id,self.vault_id,request_id)).fetchall()
            if len(rows)!=1:raise Phase10Error("not_found","Operation not found.",404)
            return {"operation":{"requestId":request_id,"operation":rows[0]["operation"],"state":rows[0]["state"],"status":rows[0]["status"]}}

    def generate(self, operation, request_id, payload, dependencies, invoke):
        import hashlib,json
        from . import admission
        if not isinstance(operation,str) or not re.fullmatch(r"[a-z0-9_.-]{1,80}",operation) or not isinstance(request_id,str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}",request_id):raise Phase10Error("invalid_request_id","The request identity is invalid.")
        fp=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        scope="vault:"+self.vault_id;owner=self.vault_id
        with self.lock,self.store.connect() as db:
            self.check_actor();db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?",(scope,owner,operation,request_id)).fetchone()
            if row:
                if row["fingerprint"]!=fp:raise Phase10Error("request_conflict","This request ID is bound to another payload.",409)
                if row["state"] in ("pending","unknown"):raise Phase10Error("request_pending","The request outcome is unresolved.",409)
                if row["state"]=="failed":raise Phase10Error("known_failure","The request failed; use a new ID for a deliberate retry.",409)
                deps=json.loads(row["refs"]);self.resolve_entries(deps);self.handler._p10_vault_deps=deps
                return row["status"],json.loads(row["result"])
            if db.execute("SELECT 1 FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND state IN ('pending','unknown')",(scope,owner,operation)).fetchone():raise Phase10Error("operation_unresolved","A prior operation has an unresolved outcome.",409)
            self.resolve_entries(dependencies)
            db.execute("INSERT INTO phase10_receipts VALUES(?,?,?,?,?,'pending',NULL,NULL,?)",(scope,owner,operation,request_id,fp,json.dumps(dependencies,ensure_ascii=False)))
            db.commit()
        def finish(state,status,result=None):
            with self.lock,self.store.connect() as db:
                db.execute("UPDATE phase10_receipts SET state=?,status=?,result=? WHERE session_id=? AND actor_id=? AND operation=? AND request_id=? AND state='pending'",(state,status,json.dumps(result,ensure_ascii=False) if result is not None else None,scope,owner,operation,request_id))
        started=False
        try:
            with admission.lease(scope):
                with self.lock,self.store.connect() as db:
                    rows=self.resolve_entries(dependencies);db.execute("BEGIN IMMEDIATE")
                    vault=db.execute("SELECT calls FROM phase10_vaults WHERE id=? AND status='active'",(owner,)).fetchone()
                    if not vault or vault["calls"]>=admission.CEILING:raise admission.Ceiling()
                    db.execute("UPDATE phase10_vaults SET calls=calls+1 WHERE id=?",(owner,));db.commit()
                started=True;result=invoke(rows)
        except (admission.Busy,admission.Ceiling) as exc:
            finish("failed",503 if isinstance(exc,admission.Busy) else 429)
            raise Phase10Error("busy" if isinstance(exc,admission.Busy) else "vault_call_limit","Generation admission is unavailable.",503 if isinstance(exc,admission.Busy) else 429)
        except KnownUnavailable:
            finish("failed",503);raise Phase10Error("provider_unavailable","The provider is unavailable before transport.",503)
        except Phase10Error:
            finish("unknown" if started else "failed",409);raise
        except Exception:
            finish("unknown" if started else "failed",503);raise Phase10Error("provider_outcome_unknown" if started else "provider_unavailable","The provider outcome is unknown; do not retry." if started else "The provider is unavailable before transport.",503)
        with self.lock:
            try:self.resolve_entries(dependencies)
            except Phase10Error:
                with self.store.connect() as db:
                    db.execute("UPDATE phase10_receipts SET state='failed',status=409,result=NULL WHERE session_id=? AND actor_id=? AND operation=? AND request_id=? AND state IN ('pending','unknown')",(scope,owner,operation,request_id))
                raise Phase10Error("stale_context","A selected vault entry changed during generation.",409)
            finish("complete",200,result);self.handler._p10_vault_deps=dependencies
            return 200,result
