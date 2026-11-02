"""Revisioned explicit session choices. PRIMARY owns rights, facts and all spending."""
import hashlib
import json
import re
import sqlite3
from decimal import Decimal, InvalidOperation

from . import store
from .phase10_common import Phase10Error

POLICY = "w20modespolicy"
RECEIPT = "w20modesreceipt"
OPERATIONS = ("speech", "translation")
CHOICES = ("local", "hosted", "text")
_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)
_MONEY = re.compile(r"^(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,6})?$", re.ASCII)
_BASIS = re.compile(r"^[A-Za-z0-9._:-]{1,128}$", re.ASCII)


def _fail(code, message, status=422):
    raise Phase10Error(code, message, status)


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _fail("invalid_request", "Invalid identifier.")
    return value


def _money(value):
    if not isinstance(value, str) or not _MONEY.fullmatch(value):
        return None
    try:
        n = Decimal(value)
        return format(n, "f") if n.is_finite() and n <= Decimal("999999") else None
    except InvalidOperation:
        return None


def _body(body):
    if not isinstance(body, dict) or set(body) != {"requestId", "expectedRevision", "operations", "sessionCapUsd"}:
        _fail("invalid_request", "Invalid policy fields.")
    _id(body["requestId"])
    if type(body["expectedRevision"]) is not int or not 0 <= body["expectedRevision"] <= 2147483646:
        _fail("invalid_request", "Invalid policy revision.")
    cap = _money(body["sessionCapUsd"])
    if cap is None or Decimal(cap) > 75:
        _fail("invalid_request", "Invalid session cap.")
    operations = body["operations"]
    if not isinstance(operations, dict) or set(operations) != set(OPERATIONS):
        _fail("invalid_request", "Both operations require an explicit choice.")
    normalized = {}
    for op in OPERATIONS:
        item = operations[op]
        if not isinstance(item, dict) or set(item) != {"primary", "alternatives"}:
            _fail("invalid_request", "Invalid operation choice.")
        primary, alternatives = item["primary"], item["alternatives"]
        if not isinstance(primary, str) or primary not in CHOICES or not isinstance(alternatives, list) or len(alternatives) > 2:
            _fail("invalid_request", "Invalid operation choice.")
        if any(not isinstance(x, str) or x not in CHOICES for x in alternatives) or len(set(alternatives + [primary])) != len(alternatives) + 1:
            _fail("invalid_request", "Invalid alternatives.")
        normalized[op] = {"primary": primary, "alternatives": list(alternatives)}
    return {"operations": normalized, "sessionCapUsd": cap}


def _authority(db, sid, actor, capability, authorize):
    if not isinstance(actor, dict) or actor.get("sid") != sid or actor.get("role") != "creator" or not isinstance(actor.get("owner"), str) or not actor["owner"]:
        _fail("forbidden", "Creator access required.", 403)
    creator = authorize(db, sid, actor, capability, "policy")
    if not isinstance(creator, str) or not creator or creator != actor["owner"]:
        _fail("forbidden", "Creator access required.", 403)
    return creator


def _read(db, kind, oid, sid):
    return db.execute("SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?", (kind, oid, sid)).fetchone()


def _insert(db, kind, oid, sid, owner, value):
    db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)",
               (kind, oid, sid, owner, _json(value), store.now()))


def _current(db, sid, creator):
    oid = _hash(["w20policy", sid])
    row = _read(db, POLICY, oid, sid)
    if row and row["owner_id"] != creator:
        _fail("not_found", "Policy unavailable.", 404)
    if not row:
        return oid, None
    value = json.loads(row["data"])
    return oid, {"revision": row["revision"], "operations": value["operations"], "sessionCapUsd": value["sessionCapUsd"]}


def save_policy(sid, actor, capability, authorize, body, *, wire_metadata=None):
    """Atomic policy and receipt; callback must check current rights in this transaction."""
    _id(sid)
    value = _body(body)
    fingerprint = _hash([body["expectedRevision"], value])
    if wire_metadata is not None:
        expected = {"operation": "w20PolicySave", "requestId": body["requestId"], "target": sid, "revision": body["expectedRevision"]}
        if not isinstance(wire_metadata, dict) or set(wire_metadata) != set(expected) | {"fingerprint"} or any(wire_metadata[k] != v for k, v in expected.items()) or not isinstance(wire_metadata["fingerprint"], str) or not re.fullmatch(r"[a-f0-9]{64}", wire_metadata["fingerprint"]):
            _fail("invalid_request", "Invalid trusted wire metadata.")
    with store.LOCK, store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        creator = _authority(db, sid, actor, capability, authorize)
        oid, current = _current(db, sid, creator)
        rid = _hash(["w20receipt", sid, creator, body["requestId"]])
        receipt = _read(db, RECEIPT, rid, sid)
        if receipt:
            prior = json.loads(receipt["data"])
            if receipt["owner_id"] != creator or prior["fingerprint"] != fingerprint or prior.get("wire") != wire_metadata:
                _fail("request_conflict", "Request ID already used.", 409)
            db.commit()
            return 200, {"policy": prior["policy"], "replayed": True}
        revision = current["revision"] if current else 0
        if revision != body["expectedRevision"]:
            _fail("version_conflict", "The policy changed; refresh.", 409)
        result = {"revision": revision + 1, **value}
        if current:
            changed = db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND owner_id=? AND revision=?",
                                 (_json(value), POLICY, oid, sid, creator, revision)).rowcount
            if changed != 1:
                _fail("version_conflict", "The policy changed; refresh.", 409)
        else:
            _insert(db, POLICY, oid, sid, creator, value)
        _insert(db, RECEIPT, rid, sid, creator, {"fingerprint": fingerprint, "policy": result, "wire": wire_metadata})
        db.commit()
        return 200, {"policy": result, "replayed": False}


def _tri(value):
    return value if type(value) is bool else None


def _safe_facts(raw, choice):
    # Whitelist only; never propagate arbitrary provider/account or private payload.
    raw = raw if isinstance(raw, dict) else {}
    checks = ("configured", "available") if choice == "local" else (
        "configured", "accountVerified", "quotaVerified", "rateVerified",
        "authorizationVerified", "reserveWithinBoundary", "envelopeAvailable")
    if choice == "text":
        checks = ()
    states = {key: _tri(raw.get(key)) for key in checks}
    availability = "unavailable" if False in states.values() else ("unknown" if None in states.values() else "available")
    basis = raw.get("estimateBasis")
    if not isinstance(basis, str) or not _BASIS.fullmatch(basis):
        basis = None
    return {
        "availability": availability, "checks": states,
        "confirmedUsageUsd": _money(raw.get("confirmedUsageUsd")),
        "estimatedUsd": _money(raw.get("estimatedUsd")),
        "estimateBasis": basis,
        "reservationsUsd": _money(raw.get("reservationsUsd")),
        "unknownHoldsUsd": _money(raw.get("unknownHoldsUsd")),
        "unknownHoldsPresent": _tri(raw.get("unknownHoldsPresent")),
        "unknownAfterDispatch": _tri(raw.get("unknownAfterDispatch")),
    }


def _facts(db, sid, creator, op, choice, policy, facts):
    # Callback computes a fresh conservative decision from the existing ledger,
    # including unknown holds, cap, actual configuration and current envelope.
    return _safe_facts(facts(db, sid, creator, op, choice, policy), choice)


def _session_reservations(db, sid):
    """Read the durable admission reservations, not billing or settlement."""
    try:
        rows = db.execute("SELECT data FROM objects WHERE kind='w20costreservation' AND session_id=?", (sid,)).fetchall()
        total = Decimal('0')
        for row in rows:
            item = json.loads(row['data'])
            value = item['amountUsd']
            if _money(value) is None:
                return None
            amount = Decimal(value)
            if not amount.is_finite() or amount <= 0 or amount > 75:
                return None
            total += amount
            if total > 75:
                return None
        return format(total, 'f')
    except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError, sqlite3.Error):
        return None


def get_policy(sid, actor, capability, authorize, facts):
    _id(sid)
    with store.LOCK, store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        creator = _authority(db, sid, actor, capability, authorize)
        _, policy = _current(db, sid, creator)
        projections = {op: {choice: _facts(db, sid, creator, op, choice, policy, facts)
                            for choice in CHOICES} for op in OPERATIONS}
        reservations = _session_reservations(db, sid)
        db.commit()
        return {"policy": policy, "choices": projections,
                "sessionBudget": {"reservationsUsd": reservations}}


def admit(sid, actor, capability, authorize, facts, operation, choice, expected_revision, automatic_retry=False):
    """Predicate only; PRIMARY must recheck rights/facts and reserve durably at dispatch."""
    _id(sid)
    if operation not in OPERATIONS or choice not in CHOICES or type(expected_revision) is not int or expected_revision < 1 or type(automatic_retry) is not bool:
        _fail("invalid_request", "Invalid admission request.")
    with store.LOCK, store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        creator = _authority(db, sid, actor, capability, authorize)
        _, policy = _current(db, sid, creator)
        if not policy or policy["revision"] != expected_revision:
            _fail("version_conflict", "The policy changed; refresh.", 409)
        selected = policy["operations"][operation]
        if choice not in [selected["primary"], *selected["alternatives"]]:
            _fail("choice_not_selected", "This choice is not selected in the policy.", 409)
        projection = _facts(db, sid, creator, operation, choice, policy, facts)
        # Every alternative requires a new explicit user action. Never auto-transition
        # to hosted or automatically retry an unknown paid dispatch.
        if automatic_retry and (choice != selected["primary"] or choice == "hosted" or projection["unknownAfterDispatch"] is not False):
            _fail("retry_unavailable", "Automatic retry is unavailable.", 409)
        allowed = projection["availability"] == "available"
        db.commit()
        return {"allowed": allowed, "choice": choice, "policyRevision": policy["revision"],
                "projection": projection, "requiresDurableReservation": choice == "hosted" and allowed}



def lookup_wire_receipt(sid, actor, capability, authorize, query):
    """Only an exact committed binding can be confirmed; all other outcomes remain unknown."""
    _id(sid)
    if not isinstance(query, dict) or set(query) != {"operation", "requestId", "fingerprint", "target", "revision"}:
        _fail("invalid_request", "Invalid receipt query.")
    _id(query["requestId"])
    if query["operation"] != "w20PolicySave" or query["target"] != sid or type(query["revision"]) is not int or query["revision"] < 0 or not isinstance(query["fingerprint"], str) or not re.fullmatch(r"[a-f0-9]{64}", query["fingerprint"]):
        _fail("invalid_request", "Invalid receipt query.")
    with store.LOCK, store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        creator = _authority(db, sid, actor, capability, authorize)
        rid = _hash(["w20receipt", sid, creator, query["requestId"]])
        row = _read(db, RECEIPT, rid, sid)
        prior = json.loads(row["data"]) if row and row["owner_id"] == creator else None
        if not prior or prior.get("wire") != query:
            db.commit()
            return {"status": "unknown"}
        result = {"status": "committed", **prior["wire"], "result": {"policy": prior["policy"]}}
        db.commit()
        return result


def check_authority(sid, actor, capability, authorize):
    with store.LOCK, store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        _authority(db, sid, actor, capability, authorize)
        db.commit()
