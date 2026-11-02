"""Resolve explicitly shared invitations without issuing credentials."""
import re, secrets
from urllib.parse import urlsplit, parse_qs
from . import store, lifecycle
from .phase10_common import Phase10Error

def resolve(payload, origin):
    def unavailable():
        raise Phase10Error("not_found", "Invitation unavailable. Ask the creator for a current invitation.", 404)
    if not isinstance(payload, dict) or set(payload) != {"invitation"}: unavailable()
    invitation = payload["invitation"]
    if not isinstance(invitation, str) or len(invitation) > 2048 or not origin: unavailable()
    try:
        url = urlsplit(invitation)
        base = urlsplit(origin)
        if (url.scheme, url.netloc) != (base.scheme, base.netloc) or url.path != "/" or url.fragment or url.username or url.password: unavailable()
        query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
        if set(query) != {"sessionId", "joinCode"} or any(len(v) != 1 for v in query.values()): unavailable()
        sid, code = query["sessionId"][0], query["joinCode"][0]
        if not re.fullmatch(r"[0-9a-f]{32}", sid) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", code): unavailable()
    except (ValueError, UnicodeError): unavailable()
    with store.LOCK:
        session = store.get("session", sid)
        if not session or not lifecycle.active(session) or lifecycle.past(session.get("lifecycle", {}).get("invitationExpiresAt")) or not secrets.compare_digest(session.get("joinCode", ""), code): unavailable()
        return {"sessionId": sid, "joinCode": code}

def readiness(sid, session, origin, source_visible):
    from . import waves17_tts_local, waves17_hosted_facade
    sources = [x for x in store.all("source", sid) if source_visible(x)]
    invitation_current = lifecycle.active(session) and not lifecycle.past(session.get("lifecycle", {}).get("invitationExpiresAt"))
    return {"source": {"state": "available" if sources else "unavailable", "reason": None if sources else "no_visible_source"},
            "invitation": {"state": "available" if invitation_current and origin else ("configured" if invitation_current else "unavailable"), "expiresAt": session.get("lifecycle", {}).get("invitationExpiresAt"), "linkConfigured": bool(origin)},
            "languages": ["en", "es"],
            "engines": [{"id": "local_neural", **waves17_tts_local.availability()}, {"id": "sapi", "available": None, "reason": "attempt_on_request", "languages": ["en", "es"], "emergency": True}, waves17_hosted_facade.options()],
            "textFallback": True, "automaticFallback": False}
