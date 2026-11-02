"""Private, deterministic return over currently authorized indexed moments.

Integration is incomplete until final_guard is called immediately before delivery.
"""
import hashlib
import json
import re

from . import store
from .phase10_common import Context, Phase10Error


def fail(code, message, status=422):
    raise Phase10Error(code, message, status)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', value):
        fail('invalid_request', 'A valid requestId is required.')


def viewer(ctx):
    ctx.check_actor()
    if ctx.actor.get('role') != 'viewer' or ctx.actor.get('sid') != ctx.sid:
        fail('not_found', 'Private return unavailable.', 404)


def own(kind, oid, ctx):
    with store.connect() as db:
        row = db.execute('SELECT data,revision,owner_id FROM objects WHERE kind=? AND id=? AND session_id=?', (kind, oid, ctx.sid)).fetchone()
    if not row or row['owner_id'] != ctx.actor['owner']:
        fail('not_found', 'Private return unavailable.', 404)
    obj = json.loads(row['data']); obj['_revision'] = row['revision']
    return obj


def _rows(ctx, refs):
    if not refs:
        return []
    rows = ctx.resolve(refs)
    if not all(row['source'].get('audienceVisible') for row in rows):
        raise ValueError()
    return rows


def _material(ctx, category, oid):
    """Resolve only through current audience projections; return metadata and display."""
    if category == 'moment':
        moment = store.get('p10moment', oid, ctx.sid)
        if not moment: raise ValueError()
        rows = _rows(ctx, [moment.get('ref')])
        item = {'category': category, 'id': oid, 'revision': moment['_revision'], 'refs': [moment['ref']]}
        display = {'category': 'sourced_fact', 'kind': moment.get('kind', 'other'),
                   'excerpt': str(moment.get('text', ''))[:220], 'citations': ctx.citations(rows),
                   'nextAction': {'type': 'open_source', 'ref': moment['ref']}}
    elif category == 'chapter':
        chapter = store.get('w15chapter', oid, ctx.sid)
        if not chapter or chapter.get('status') != 'active': raise ValueError()
        rows = _rows(ctx, chapter.get('refs', []))
        item = {'category': category, 'id': oid, 'revision': chapter['_revision'], 'refs': chapter.get('refs', [])}
        display = {'category': 'chapter', 'kind': 'chapter', 'excerpt': str(chapter.get('title', ''))[:160],
                   'citations': ctx.citations(rows), 'nextAction': {'type': 'open_chapter', 'id': oid}}
    else:
        from . import waves15_formats as formats
        fmt = store.get(formats.F, oid, ctx.sid)
        if not fmt: raise ValueError()
        visible, contributions = formats.projection(ctx, fmt, ctx.sid, ctx.actor)
        if fmt.get('templateRoundId') and visible.get('roundStage') not in ('reveal', 'close'): raise ValueError()
        decision = visible.get('decision')
        if not decision and fmt.get('decision'): raise ValueError()
        decision = decision or {'reasonIds': [], 'minorityIds': []}
        selected = {c['id']: c for c in contributions if c.get('status') == 'accepted'}
        reasons = [selected[x] for x in decision['reasonIds']]
        refs = list(fmt.get('refs', []))
        for reason in reasons:
            refs.extend(reason.get('refs', []))
        refs = list({fingerprint(ref): ref for ref in refs}.values())
        # Resolve in bounded batches; the underlying format may reference more than 20.
        rows = []
        for i in range(0, len(refs), 20): rows.extend(_rows(ctx, refs[i:i+20]))
        item = {'category': category, 'id': oid, 'revision': fmt['_revision'], 'refs': refs,
                'reasons': [{'id': c['id'], 'revision': c['_revision']} for c in reasons]}
        has_decision = bool(visible.get('decision'))
        display = {'category': 'creator_decision' if has_decision else 'open_question', 'kind': 'decision' if has_decision else 'question',
                   'excerpt': str(decision.get('decision') if has_decision else visible.get('question', ''))[:220],
                   'outcome': str(decision.get('consequence', ''))[:220],
                   'question': str(visible.get('question', ''))[:220],
                   'participantOpinions': [{'excerpt': str(c.get('reason', ''))[:160],
                                             'minority': c['id'] in decision.get('minorityIds', [])}
                                            for c in reasons if c.get('reason')][:3],
                   'opinionsTruncated': sum(bool(c.get('reason')) for c in reasons) > 3,
                   'citations': ctx.citations(rows), 'nextAction': {'type': 'open_format', 'id': oid}}
    item['sourceMoments'] = [{'id': row['moment']['id'], 'revision': row['moment']['_revision']} for row in rows]
    display['citation'] = display['citations'][0] if display['citations'] else None
    display['unreferenced'] = not bool(display['citations'])
    return item, display


def snapshot(ctx):
    selected, gaps, unreferenced = [], 0, 0
    counts = {}; truncated = False
    for category, kind in (('moment', 'p10moment'), ('chapter', 'w15chapter'), ('decision', 'w15format')):
        items = store.all(kind, ctx.sid); counts[category] = min(len(items), 2000)
        truncated |= len(items) > 2000
        for obj in items[:2000]:
            # Non-decisions and pre-reveal rounds are outside the visible account, not counted as gaps.
            if category == 'decision':
                if obj.get('templateRoundId'):
                    round_ = store.get('w17templateround', obj['templateRoundId'], ctx.sid)
                    if not round_ or round_.get('stage') not in ('reveal', 'close'): continue
            try:
                item, display = _material(ctx, category, obj['id'])
                selected.append(item); unreferenced += int(display['unreferenced'])
            except (Phase10Error, ValueError, TypeError, KeyError):
                gaps += 1
    return selected, {'scanLimit': 2000, 'truncated': truncated, 'unavailable': gaps,
                      'unreferencedInputs': unreferenced, 'scanned': counts,
                      'scope': 'Current indexed moments, active chapters and visible creator decisions; not a complete event history.'}


def _identity(item):
    if 'category' not in item: return ('moment', item.get('ref', {}).get('momentId'))
    return (item['category'], item['id'])


def project(ctx, record):
    cp = own('w17checkpoint', record['checkpointId'], ctx)
    if cp['_revision'] != record['checkpointRevision']:
        fail('stale_context', 'The checkpoint changed; create a new return.', 409)
    changes, gaps, bindings = [], 0, []
    for item in record['changes']:
        try:
            # Legacy returns hold a ref/revision rather than a category/id.
            current, display = _material(ctx, *_identity(item))
            if 'category' in item:
                if current != item: raise ValueError()
            elif current['revision'] != item['revision'] or current['refs'] != [item['ref']]: raise ValueError()
            changes.append(display); bindings.append(current)
        except (Phase10Error, ValueError, TypeError, KeyError): gaps += 1
    coverage = dict(record['coverage']); coverage['changedInputsUnavailable'] = gaps
    no_change = not changes and not gaps and not coverage['truncated'] and not coverage['unavailable'] and not coverage.get('baselineUnavailable', 0) and not coverage.get('baselineInputsUnavailable', 0)
    categories = {name: sum(c['category'] == name for c in changes) for name in ('sourced_fact', 'chapter', 'creator_decision', 'open_question')}
    account = []
    for c in changes[:5]:
        label = {'sourced_fact': 'Source', 'chapter': 'Chapter', 'creator_decision': 'Creator decision', 'open_question': 'Open question'}[c['category']]
        text = label + ': ' + c['excerpt']
        if c['category'] == 'creator_decision':
            text += ' Outcome: ' + c['outcome'] + ' Question: ' + c['question']
        account.append({'category': c['category'], 'text': text, 'citations': c['citations'], 'nextAction': c['nextAction'], 'unreferenced': c['unreferenced']})
    result = {'id': record['id'], 'checkpointId': cp['id'], 'checkpointRevision': cp['_revision'],
              'createdAt': record['createdAt'], 'revision': record['_revision'], 'method': 'deterministic current-source account; no AI',
              'changes': changes, 'account': account, 'accountTruncated': len(changes) > 5,
              'categories': categories, 'nextAction': changes[0]['nextAction'] if changes else None,
              'coverage': coverage, 'noMeaningfulChange': no_change,
              'privateContext': record.get('privateContext'),
              'limitations': ['Source and creator text are untrusted data.', 'Coverage excludes unindexed events and unrevealed decisions.']}
    ctx.handler._w17_return_binding = (ctx.sid, ctx.actor, record['id'], record['_revision'], cp['id'], cp['_revision'], bindings)
    return result


def final_guard(handler):
    actor_binding = getattr(handler, '_w17_actor_binding', None)
    if actor_binding:
        with store.LOCK: viewer(Context(handler, *actor_binding))
    binding = getattr(handler, '_w17_return_binding', None)
    if not binding: return
    sid, actor, rid, rrev, cid, crev, items = binding
    ctx = Context(handler, sid, actor)
    with store.LOCK:
        viewer(ctx)
        rec, cp = own('w17return', rid, ctx), own('w17checkpoint', cid, ctx)
        if rec['_revision'] != rrev or cp['_revision'] != crev:
            fail('stale_context', 'Private return changed; refresh.', 409)
        for item in items:
            try:
                current, _ = _material(ctx, *_identity(item))
                if current != item: raise ValueError()
            except (Phase10Error, ValueError, TypeError, KeyError):
                fail('stale_context', 'A source or decision changed; refresh.', 409)


def handle(handler, sid, actor, method, parts):
    if not parts or parts[0] not in ('return-checkpoints', 'returns', 'return-operations'):
        return None
    with store.LOCK:
        ctx = Context(handler, sid, actor); viewer(ctx)
        handler._w17_actor_binding = (sid, actor)
        if len(parts) == 2 and parts[0] == 'return-operations' and method == 'GET':
            key(parts[1]); rid = fingerprint([sid, actor['owner'], parts[1]])
            try: receipt = own('w17receipt', rid, ctx)
            except Phase10Error as exc:
                if exc.status == 404: return 200, {'state': 'unknown'}
                raise
            obj = own(receipt['kind'], receipt['objectId'], ctx)
            if receipt['kind'] == 'w17return': return 200, {'state': 'committed', 'return': project(ctx, obj)}
            return 200, {'state': 'committed', 'checkpoint': {'id': obj['id'], 'revision': obj['_revision'], 'createdAt': obj['createdAt']}}
        if len(parts) == 2 and parts[0] == 'returns' and method == 'GET':
            return 200, {'return': project(ctx, own('w17return', parts[1], ctx))}
        if len(parts) == 2 and parts[0] == 'return-checkpoints' and method == 'GET':
            cp = own('w17checkpoint', parts[1], ctx)
            return 200, {'checkpoint': {'id': cp['id'], 'revision': cp['_revision'], 'createdAt': cp['createdAt']}}
        if len(parts) == 2 and parts[0] == 'returns' and method == 'PATCH':
            body = handler.body()
            if not isinstance(body, dict) or set(body) != {'revision', 'privateContext'} or type(body['revision']) is not int:
                fail('invalid_request', 'A return revision and private context are required.')
            private = body['privateContext']
            if private is not None and (not isinstance(private, str) or not 1 <= len(private.strip()) <= 1000):
                fail('invalid_request', 'Private context must be null or up to 1000 characters.')
            obj = own('w17return', parts[1], ctx)
            if obj['_revision'] != body['revision']: fail('version_conflict', 'The return changed.', 409)
            obj['privateContext'] = private
            obj = store.save('w17return', obj, revision=body['revision'])
            return 200, {'return': project(ctx, obj)}
        if method != 'POST' or parts not in (['return-checkpoints'], ['returns']):
            fail('not_found', 'Private return route unavailable.', 404)
        body = handler.body()
        if not isinstance(body, dict): fail('invalid_request', 'A request object is required.')
        expected = {'requestId'} if parts == ['return-checkpoints'] else {'requestId', 'checkpointId', 'checkpointRevision', 'privateContext'}
        if set(body) != expected: fail('invalid_request', 'Invalid request fields.')
        key(body['requestId']); fp = fingerprint([parts, body]); receipt_id = fingerprint([sid, actor['owner'], body['requestId']])
        try: old = own('w17receipt', receipt_id, ctx)
        except Phase10Error as exc:
            if exc.status != 404: raise
            old = None
        if old:
            if old['fingerprint'] != fp: fail('request_conflict', 'This requestId is already in use.', 409)
            obj = own(old['kind'], old['objectId'], ctx)
            if old['kind'] == 'w17return': return 200, {'return': project(ctx, obj), 'replayed': True}
            return 200, {'checkpoint': {'id': obj['id'], 'revision': obj['_revision'], 'createdAt': obj['createdAt']}, 'replayed': True}
        current, coverage = snapshot(ctx)
        oid = store.ident(); now = store.now()
        if parts == ['return-checkpoints']:
            kind = 'w17checkpoint'; value = {'id': oid, 'createdAt': now, 'baseline': current, 'coverage': coverage}
        else:
            if not isinstance(body['checkpointId'], str) or type(body['checkpointRevision']) is not int:
                fail('invalid_request', 'A checkpoint and revision are required.')
            private = body['privateContext']
            if private is not None and (not isinstance(private, str) or not 1 <= len(private.strip()) <= 1000):
                fail('invalid_request', 'Private context must be null or up to 1000 characters.')
            cp = own('w17checkpoint', body['checkpointId'], ctx)
            if cp['_revision'] != body['checkpointRevision']: fail('version_conflict', 'The checkpoint changed.', 409)
            base = {fingerprint(x) for x in cp['baseline']}
            changed = [x for x in current if fingerprint(x) not in base]
            changed.sort(key=lambda x: {'decision': 0, 'chapter': 1, 'moment': 2}.get(x.get('category'), 2))
            omitted = max(0, len(changed)-20); changed = changed[:20]
            coverage['truncated'] = coverage['truncated'] or bool(omitted) or cp['coverage']['truncated']
            coverage['baselineUnavailable'] = cp['coverage']['unavailable']
            coverage['baselineInputsUnavailable'] = sum(1 for x in cp['baseline'] if _identity(x) not in {_identity(y) for y in current})
            kind = 'w17return'; value = {'id': oid, 'createdAt': now, 'checkpointId': cp['id'], 'checkpointRevision': cp['_revision'], 'changes': changed, 'coverage': coverage, 'privateContext': private}
        # Object and receipt commit together; no schema changes or list-based recovery.
        viewer(ctx)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for k, objid, data in ((kind, oid, value), ('w17receipt', receipt_id, {'id': receipt_id, 'fingerprint': fp, 'kind': kind, 'objectId': oid})):
                db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)', (k, objid, sid, actor['owner'], json.dumps(data, ensure_ascii=False), now))
            db.commit()
        obj = own(kind, oid, ctx)
        if kind == 'w17return': return 201, {'return': project(ctx, obj), 'replayed': False}
        return 201, {'checkpoint': {'id': oid, 'revision': 1, 'createdAt': now}, 'replayed': False}


