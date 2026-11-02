"""Wave 22 session routes. PRIMARY must invoke final_guard under store.LOCK
and retain that lock through serialization/send; never send prepared content directly.
"""
from . import store, waves22_claims as claims, waves22_coedit as coedit
from . import waves22_coedit_auth as authority, waves22_edition as edition
from . import waves22_models as models, waves22_model_auth as model_auth
from . import waves22_adoption as adoption
from .phase10_common import Context, Phase10Error
from urllib.parse import parse_qs, urlparse


def _missing():
    raise Phase10Error('not_found', 'Route unavailable.', 404)


def handle(handler, sid, actor, method, parts):
    ctx = Context(handler, sid, actor)
    if actor.get('sid') != sid: _missing()
    # The final hook is server-owned, never supplied by the caller.
    if parts == ['claims'] and method == 'POST':
        body = handler.body()
        if not isinstance(body, dict): _missing()
        with store.LOCK:
            ctx.check_actor()
            if set(body) == {'query'}:
                query = body['query']
                if not isinstance(query, dict) or set(query) != {'topic', 'asOfEventTime', 'knownAt'}:
                    raise Phase10Error('invalid_request', 'Invalid query.', 422)
                invoke = lambda: claims.query(ctx, query['topic'], query['asOfEventTime'], query['knownAt'])
            else:
                # Replaying the same request ID is the established mutation receipt path.
                invoke = lambda: claims.mutate(ctx, body)
            result = invoke()
            handler._w22_final = lambda: _same(invoke(), result)
            return 200, result
    if parts and parts[0] == 'models':
        mctx = model_auth.ModelContext(handler, sid, actor)
        if parts == ['models', 'approvals'] and method == 'GET':
            result = model_auth.list_approvals(mctx)
            handler._w22_final = lambda: _same(model_auth.list_approvals(mctx), result)
            return 200, result
        if parts == ['models', 'owned-shares'] and method == 'GET':
            result = models.list_owned_shares(mctx)
            handler._w22_final = lambda: _same(models.list_owned_shares(mctx), result)
            return 200, result
        if parts == ['models', 'shares'] and method == 'GET':
            result = models.list_shares(mctx)
            handler._w22_final = lambda: _same(models.list_shares(mctx), result)
            return 200, result
        if parts in (['models'], ['models', 'receipts']) and method == 'GET':
            invoke = models.list_models if parts == ['models'] else models.list_receipts
            result = invoke(mctx)
            handler._w22_final = lambda: _same(invoke(mctx), result)
            return 200, result
        if parts == ['models', 'approvals'] and method == 'POST':
            body = handler.body()
            models._fields(body, ('definition',))
            result = model_auth.approve(mctx, body['definition'])
            handler._w22_final = lambda: model_auth.guard_approval(mctx, result)
            return 200, result
        if len(parts) == 4 and parts[1] == 'approvals' and parts[3] == 'revoke' and method == 'POST':
            models._fields(handler.body(), ())
            result = model_auth.revoke_approval(mctx, parts[2])
            handler._w22_final = mctx.check_actor
            return 200, result
        if parts == ['models'] and method == 'POST':
            body = handler.body()
            result = models.mutate(mctx, body)
            if body['action'] == 'revoke':
                handler._w22_final = mctx.check_actor
            else:
                mid = result['model']['id']
                def guard_model_mutation():
                    _same(models.read(mctx, mid), result['model'])
                    if body['action'] == 'share':
                        model_auth.guard_share_owner(mctx, result['shareId'], mid)
                handler._w22_final = guard_model_mutation
            return 200, result
        if len(parts) == 3 and parts[2] == 'forget' and method == 'POST':
            body = handler.body(); models._fields(body, ('requestId',))
            result = models.forget(mctx, parts[1], body['requestId'])
            handler._w22_final = mctx.check_actor
            return 200, result
        if len(parts) == 2 and method == 'GET':
            result = models.read(mctx, parts[1])
            handler._w22_final = lambda: _same(models.read(mctx, parts[1]), result)
            return 200, {'model': result}
        if len(parts) == 3 and parts[1] == 'shares' and method == 'GET':
            result = models.read_share(mctx, parts[2])
            handler._w22_final = lambda: _same(models.read_share(mctx, parts[2]), result)
            return 200, {'share': result}
        _missing()
    if parts and parts[0] == 'coedit':
        cctx = authority.CoeditContext(handler, sid, actor)
        if parts == ['coedit', 'grants'] and method == 'GET':
            result = authority.list_grants(cctx)
            handler._w22_final = lambda: _same(authority.list_grants(cctx), result)
            return 200, result
        if parts == ['coedit', 'grants'] and method == 'POST':
            result = authority.issue(cctx, handler.body())
            handler._w22_final = lambda: authority.guard_issued(cctx, result)
            return 201, result
        if len(parts) == 4 and parts[1] == 'grants' and parts[3] == 'revoke' and method == 'POST':
            body = handler.body()
            coedit._fields(body, ('revision',))
            result = authority.revoke(cctx, parts[2], body['revision'])
            handler._w22_final = cctx.check_actor
            return 200, result
        if parts == ['coedit', 'drafts'] and method == 'POST':
            result = coedit.create(cctx, handler.body())
            draft_id = result['draft']['draftId']
        elif len(parts) >= 3 and parts[1] == 'drafts':
            draft_id = parts[2]
            if len(parts) == 6 and parts[3:5] == ['adoption', 'operations'] and method == 'GET':
                result = adoption.recovery_receipt(cctx, draft_id, parts[5])
                handler._w22_final = lambda: _same(adoption.recovery_receipt(cctx, draft_id, parts[5]), result)
                return 200, result
            if len(parts) == 5 and parts[3] == 'operations' and method == 'GET':
                result = coedit.operation_receipt(cctx, draft_id, parts[4])
                handler._w22_final = lambda: _same(coedit.operation_receipt(cctx, draft_id, parts[4]), result)
                return 200, result
            if len(parts) == 3 and method == 'GET':
                params = parse_qs(urlparse(handler.path).query, keep_blank_values=True)
                if set(params) - {'cursor', 'schemaVersion'} or any(len(v) != 1 for v in params.values()):
                    raise Phase10Error('invalid_request', 'Invalid reconnect parameters.', 422)
                def number(name, default):
                    value = params.get(name, [str(default)])[0]
                    if not value.isascii() or not value.isdecimal() or len(value) > 10:
                        raise Phase10Error('invalid_request', 'Invalid reconnect parameters.', 422)
                    return int(value)
                cursor, schema_version = number('cursor', 0), number('schemaVersion', 1)
                result = coedit.open_draft(cctx, draft_id, cursor, schema_version)
                if cctx.actor.get('role') == 'creator':
                    result['capabilities'] = {'adoptionRecovery': 1}
            elif len(parts) == 4 and method == 'POST' and parts[3] == 'patch':
                result = coedit.apply_patch(cctx, draft_id, handler.body())
            elif len(parts) == 4 and method == 'POST' and parts[3] == 'adopt':
                result, rid = adoption.adopt(cctx, draft_id, handler.body())
                handler._w22_final = lambda: adoption.guard(cctx, result, rid)
                return 200, result
            elif len(parts) == 4 and method == 'POST' and parts[3] == 'presence':
                body = handler.body(); coedit._fields(body, ('seconds',))
                result = {'draft': coedit.presence(cctx, draft_id, body['seconds'])}
            elif len(parts) == 4 and method == 'POST' and parts[3] in ('approve', 'withdraw'):
                action = parts[3]
                body = handler.body()
                result = coedit.decide(cctx, draft_id, action, body)
                if action == 'withdraw':
                    handler._w22_final = cctx.check_actor
                    return 200, result
                approved = coedit.approved_for_adoption(cctx, draft_id, body['expectedRevision'])
                handler._w22_final = lambda: _same(coedit.approved_for_adoption(cctx, draft_id, body['expectedRevision']), approved)
                return 200, result
            else: _missing()
        else: _missing()
        def guard_draft():
            fresh = (coedit.open_draft(cctx, draft_id, cursor, schema_version)
                     if len(parts) == 3 and method == 'GET' else coedit.open_draft(cctx, draft_id))
            if 'draft' in result and fresh['draft'] != result['draft']:
                raise Phase10Error('stale_context', 'Draft changed before delivery.', 409)
            if 'events' in result and fresh['events'] != result['events']:
                raise Phase10Error('stale_context', 'Draft changed before delivery.', 409)
        handler._w22_final = guard_draft
        return (409 if result.get('operation', {}).get('state') == 'conflict' else 200), result
    if len(parts) == 3 and parts[0] == 'edition' and parts[2] == 'regions' and method == 'POST':
        body = handler.body()
        result = edition.approve_regions(ctx, parts[1], body)
        handler._w22_final = lambda: _same(edition.region_receipt(ctx, parts[1], body['requestId']), result)
        return 200, result
    if len(parts) == 3 and parts[0] == 'edition' and parts[2] == 'description' and method == 'POST':
        body = handler.body()
        if not isinstance(body, dict) or 'requestId' not in body:
            raise Phase10Error('invalid_request', 'A request ID is required.', 422)
        selection = dict(body); request_id = selection.pop('requestId')
        result = edition.select_description(ctx, parts[1], selection, request_id)
        handler._w22_final = lambda: _same(edition.description_receipt(ctx, parts[1], request_id), result)
        return 200, result
    if len(parts) == 3 and parts[0] == 'edition' and parts[2] == 'description' and method == 'DELETE':
        body = handler.body(); models._fields(body, ('requestId',))
        request_id = body['requestId']
        result = edition.revoke_description(ctx, parts[1], request_id)
        handler._w22_final = lambda: _same(edition.description_receipt(ctx, parts[1], request_id), result)
        return 200, result
    if len(parts) == 5 and parts[0] == 'edition' and parts[2:4] == ['description', 'operations'] and method == 'GET':
        result = edition.description_receipt(ctx, parts[1], parts[4])
        handler._w22_final = lambda: _same(edition.description_receipt(ctx, parts[1], parts[4]), result)
        return 200, result
    if len(parts) == 5 and parts[0] == 'edition' and parts[3] == 'assets' and method == 'GET':
        result = edition.read_frame_asset(ctx, parts[1], parts[2], parts[4])
        handler._w22_final = lambda: _same(edition.read_frame_asset(ctx, parts[1], parts[2], parts[4]), result)
        return 200, {'asset': result}
    if len(parts) == 3 and parts[0] == 'edition' and method == 'GET':
        prepared = edition.project_edition(ctx, parts[1], parts[2], released=edition.released_metadata)
        manifest = prepared['manifest']
        handler._w22_final = lambda: _same(edition.finalize(ctx, prepared, released=edition.released_metadata), manifest)
        return 200, {'edition': manifest}
    _missing()


def _same(current, expected):
    if current != expected:
        raise Phase10Error('stale_context', 'The content changed before delivery.', 409)


def final_guard(handler):
    """Call with store.LOCK held immediately before response serialization."""
    guard = getattr(handler, '_w22_final', None)
    if guard is None:
        raise Phase10Error('stale_context', 'Delivery authorization unavailable.', 409)
    guard()


