"""Creator policy HTTP adapter. PRIMARY supplies authenticated authority and facts."""
from . import waves20_modes as modes
from .phase10_common import Phase10Error


_UNREAD = object()


class Facade:
    def __init__(self, authorize, facts):
        if not callable(authorize) or not callable(facts):
            raise TypeError("authorize and facts callbacks are required")
        self.authorize, self.facts = authorize, facts

    def handle(self, handler, sid, actor, capability, method, parts, *, receipt_query=_UNREAD):
        # Called under the shared store lock by the router; handler.body hashes raw bytes.
        if parts == ["policy"] and method == "GET":
            result = modes.get_policy(sid, actor, capability, self.authorize, self.facts)
        elif parts == ["policy"] and method == "POST":
            body = handler.body()
            if not isinstance(body, dict):
                raise Phase10Error("invalid_request", "Invalid policy fields.", 422)
            wire = {"operation": "w20PolicySave", "requestId": body.get("requestId"),
                    "fingerprint": getattr(handler, "_body_sha256", None), "target": sid,
                    "revision": body.get("expectedRevision")}
            _, result = modes.save_policy(sid, actor, capability, self.authorize, body, wire_metadata=wire)
        elif parts == ["policy", "admit"] and method == "POST":
            body = handler.body()
            if not isinstance(body, dict) or set(body) != {"operation", "choice", "expectedRevision", "automaticRetry"}:
                raise Phase10Error("invalid_request", "Invalid admission request.", 422)
            result = modes.admit(sid, actor, capability, self.authorize, self.facts, body["operation"], body["choice"], body["expectedRevision"], body["automaticRetry"])
        elif parts == ["receipt"] and method == "POST":
            result = modes.lookup_wire_receipt(sid, actor, capability, self.authorize, handler.body() if receipt_query is _UNREAD else receipt_query)
        else:
            raise Phase10Error("not_found", "Policy route unavailable.", 404)
        handler._w20_policy_binding = (self, sid, dict(actor), capability)
        return 200, result

    def guard_delivery(self, handler):
        binding = getattr(handler, "_w20_policy_binding", None)
        if binding is not None:
            facade, sid, actor, capability = binding
            modes.check_authority(sid, actor, capability, facade.authorize)


def configure(authorize, facts):
    return Facade(authorize, facts)
