"""Bounded, current-rights lexical projection of retained Phase 10 moments.

No content is copied into another store.  The retained moment table is the
index; each read resolves its source revision and actor afresh.
"""
import copy
import json
import re
import unicodedata

from .phase10_common import Context, Phase10Error, parse_ref, parse_source_ref
from .phase10_timeline import rank_moments, build_moments, _ms

MAX_CANDIDATES = 2000  # Bound the complete projection, including visual entries.

_QUERY_STOPWORDS = frozenset('a an and are as at be by did do does for from happen happened how in is it of on or scene show shown the time to was were what when where which who with'.split())

# Deliberately bounded lexical equivalences, not machine translation or a
# claim that a retrieved passage answers the question. The passage itself is
# returned unchanged, including any negation.
_EQUIVALENCES = (
    ('label', 'labels', 'etiqueta', 'etiquetas'),
    ('blue', 'azul'), ('green', 'verde'), ('line', 'lines', 'linea', 'lineas'),
    ('connect', 'connects', 'connected', 'connecting', 'conecta', 'conectan'),
    ('change', 'changed', 'changes', 'changing', 'cambio', 'cambia', 'cambiado'),
    ('stay', 'stays', 'remain', 'remains', 'permanece', 'igual'),
    ('unchanged', 'igual', 'permanece'), ('not', 'no'),
    ('mention', 'mentioned', 'mentions', 'mentioning', 'mencion', 'menciona'),
)


def _words(text):
    return set(re.findall(r'\w+', ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))))


def _matches_query(query, text):
    """Require evidence-bearing query terms, rather than function-word overlap."""
    terms = _words(query) - _QUERY_STOPWORDS
    if not terms:
        return False
    def matches(term, words):
        variants = {term, term + 'd', term + 'ed', term + 's', term + 'ing'}
        for group in _EQUIVALENCES:
            if term in group:
                variants.update(group)
        # Movement is a kind of change, so a broad change query can offer it
        # as a candidate without claiming which event the user intended.
        if term == 'change':
            variants.update(('move', 'moved', 'moves', 'moving'))
        return bool(variants & words)
    words = _words(text)
    # A generic change query must not treat a negated change as an event.
    if terms == {'change'} and words & {'no', 'not', 'never'}:
        return False
    return all(matches(term, words) for term in terms)


def _rank_relevant(query, moments, limit):
    terms = _words(query) - _QUERY_STOPWORDS
    candidates = [moment for moment in moments if _matches_query(query, moment['text'])]
    if not terms:
        return []
    expansion = []
    for term in sorted(terms):
        expansion.extend((term + 'd', term + 'ed', term + 's', term + 'ing'))
        for group in _EQUIVALENCES:
            if term in group:
                expansion.extend(group)
    if 'change' in terms:
        expansion.extend(('move', 'moved', 'moves', 'moving'))
    expanded = (' '.join(expansion) + ' ' + query)[:2000].strip()
    ranked = rank_moments(expanded, candidates, limit)
    # The shared ranker does not normalize accents and may not score a
    # cross-language match. Keep eligible unscored candidates as well.
    seen = {id(moment) for moment in ranked}
    remaining = sorted((m for m in candidates if id(m) not in seen),
                       key=lambda m: (m['ref']['startMs'], m['ref']['momentId']))
    return (ranked + remaining)[:limit]


def _error(code, message, status=400):
    raise Phase10Error(code, message, status)


def _check_actor(ctx):
    actor = ctx.check_actor()
    if actor.get('sid') != ctx.sid or actor.get('role') not in ('creator', 'viewer'):
        _error('not_found', 'The session or capability is unavailable.', 404)


def _request(body):
    if not isinstance(body, dict) or set(body) - {'query', 'scope', 'limit', 'startMs', 'endMs', 'channelId'}:
        _error('invalid_query', 'The search request is invalid.')
    query, scope, limit = body.get('query'), body.get('scope'), body.get('limit', 20)
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000 or not re.findall(r'\w+', query.casefold()):
        _error('invalid_query', 'Enter a search term.')
    if scope not in ('session', 'approved_archive') or type(limit) is not int or not 1 <= limit <= 20:
        _error('invalid_query', 'The search scope or limit is invalid.')
    if (scope == 'approved_archive' and (not isinstance(body.get('channelId'), str) or not re.fullmatch(r'[0-9a-f]{32}', body['channelId']))) or (scope == 'session' and 'channelId' in body):
        _error('invalid_query', 'A channel is required for archive search.')
    start, end = body.get('startMs', 0), body.get('endMs', 864000000)
    if type(start) is not int or type(end) is not int or not 0 <= start <= end <= 864000000:
        _error('invalid_query', 'The time range is invalid.')
    return {'query': query.strip(), 'scope': scope, 'limit': limit, 'startMs': start, 'endMs': end, 'channelId': body.get('channelId')}


def _projection(row):
    ref, moment = row['ref'], row['moment']
    text = moment.get('text', '')
    if not isinstance(text, str) or len(text) > 20000:
        return None
    return {'ref': copy.deepcopy(ref), 'sourceRef': ref['sourceId'],
            'sourceRevision': ref['sourceRevision'],
            'time': {'startMs': ref['startMs'], 'endMs': ref['endMs']},
            'regionId': None, 'explanation': text[:2000], 'rightsState': 'current',
            'destination': {'kind': 'moment', 'ref': copy.deepcopy(ref)},
            'limitations': ['Only retained indexed evidence is searched; image availability is checked at the destination.']}


def _source_projection(row):
    ref, source = row['ref'], row['source']
    text = source.get('text', '')
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        return None
    return {'ref': copy.deepcopy(ref), 'sourceRef': ref['sourceId'],
            'sourceRevision': ref['sourceRevision'], 'time': None, 'regionId': None,
            'explanation': text[:2000], 'rightsState': 'current',
            'destination': {'kind': 'source', 'ref': copy.deepcopy(ref)},
            'limitations': ['Source timing is unavailable; this is not a playable moment.']}


def _visual_candidates(ctx, start, end):
    """Read only this actor's completed existing visual receipts and reproject them."""
    from . import waves21_visual_runtime
    with ctx.store.connect() as db:
        receipts = db.execute("SELECT result FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND state='complete' LIMIT 201",
                              (ctx.sid, ctx.actor['owner'], waves21_visual_runtime.OPERATION)).fetchall()
    if len(receipts) > 200:
        _error('index_capacity', 'The searchable visual evidence exceeds its supported limit.', 409)
    candidates = []
    for receipt in receipts:
        try:
            grounding = waves21_visual_runtime._project(ctx, json.loads(receipt['result']))
            ref = parse_ref(grounding['frame']['ref'])
            if ref['sessionId'] != ctx.sid or ref['endMs'] < start or ref['startMs'] > end:
                continue
            for region in grounding['regions']:
                # Preserve the distinction between OCR, observation and inference.
                entries = []
                for kind, key in (('observation', 'observations'), ('ocr', 'ocr'), ('inference', 'inferences')):
                    for entry in region.get(key, []):
                        if isinstance(entry, dict) and isinstance(entry.get('text'), str) and entry['text'].strip():
                            entries.append((kind, entry['text'].strip()))
                for kind, text in entries:
                    if len(text) > 20000:
                        continue
                    item = _projection(ctx.resolve([ref])[0])
                    item.update(regionId=region['regionId'], regionBox=copy.deepcopy(region['box']), explanation=text[:2000], evidenceKind=kind,
                                destination={'kind': 'moment_region', 'ref': copy.deepcopy(ref), 'regionId': region['regionId']})
                    item['limitations'].append('Visual inference and OCR can be incorrect; inspect the underlying frame.')
                    candidates.append(({'ref': ref, 'text': text}, item))
        except (Phase10Error, KeyError, TypeError, ValueError):
            continue
    return candidates


def search(ctx, body):
    request = _request(body)
    with ctx.lock:
        _check_actor(ctx)
        if request['scope'] == 'approved_archive':
            from . import channel_authority
            channel = request['channelId']
            channel_authority.require_member(ctx, channel)
            with ctx.store.connect() as db:
                grants = db.execute("SELECT id,revision,data FROM objects WHERE kind='w24archivegrant' LIMIT ?", (MAX_CANDIDATES + 1,)).fetchall()
            if len(grants) > MAX_CANDIDATES:
                _error('index_capacity', 'The searchable archive exceeds its supported limit.', 409)
            eligible = []
            for grant in grants:
                try:
                    data = json.loads(grant['data'])
                    if data.get('channelId') != channel or data.get('kind') is not None or not data.get('active'):
                        continue
                    projected = channel_authority.project_source(ctx, channel, grant['id'], grant['revision'])
                    ref = projected['ref']
                    if ref['endMs'] < request['startMs'] or ref['startMs'] > request['endMs']: continue
                    moment = {'ref': ref, 'text': projected['excerpt']}
                    item = _projection({'ref': ref, 'moment': moment})
                    if item is None: continue
                    archive = {'channelId': channel, 'grantId': grant['id'], 'revision': grant['revision']}
                    item['destination']['archive'] = archive
                    eligible.append((moment, item))
                except (Phase10Error, KeyError, TypeError, ValueError):
                    continue
            ranked = _rank_relevant(request['query'], [x[0] for x in eligible], request['limit'])
            by_candidate = {id(x[0]): x[1] for x in eligible}
            results = [by_candidate[id(m)] for m in ranked]
            return {'scope': 'approved_archive', 'state': 'ambiguous' if len(results) > 1 else ('available' if results else 'unknown'), 'results': results, 'unknown': not bool(results)}
        moments = ctx.store.all('p10moment', ctx.sid)
        if len(moments) > MAX_CANDIDATES:
            _error('index_capacity', 'The searchable moment set exceeds its supported limit.', 409)
        eligible = []
        for moment in moments:
            try:
                ref = parse_ref(moment.get('ref'))
                if ref['sessionId'] != ctx.sid or ref['endMs'] < request['startMs'] or ref['startMs'] > request['endMs']:
                    continue
                row = ctx.resolve([ref])[0]
                item = _projection(row)
                if item is not None:
                    eligible.append((row['moment'], item))
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
        eligible.extend(_visual_candidates(ctx, request['startMs'], request['endMs']))
        # Untimed references are only candidates for an unconstrained search.
        # Never imply they overlap a user-specified time interval.
        untimed = []
        if 'startMs' not in body and 'endMs' not in body:
            sources = ctx.store.all('source', ctx.sid)
            if len(sources) > MAX_CANDIDATES:
                _error('index_capacity', 'The searchable source set exceeds its supported limit.', 409)
            timed_sources = {item['ref']['sourceId'] for _, item in eligible}
            for source in sources:
                try:
                    ref = parse_source_ref({'sessionId': ctx.sid, 'sourceId': source['id'], 'sourceRevision': source['_revision']})
                    if ref['sourceId'] in timed_sources:
                        continue
                    item = _source_projection(ctx.resolve_source(ref))
                    if item and _matches_query(request['query'], item['explanation']):
                        untimed.append(item)
                except (Phase10Error, KeyError, TypeError, ValueError):
                    continue
        if len(eligible) + len(untimed) > MAX_CANDIDATES:
            _error('index_capacity', 'The searchable moment set exceeds its supported limit.', 409)
        ranked = _rank_relevant(request['query'], [x[0] for x in eligible], request['limit'])
        by_candidate = {id(x[0]): x[1] for x in eligible}
        results = ([by_candidate[id(m)] for m in ranked] + sorted(untimed, key=lambda item: item['ref']['sourceId']))[:request['limit']]
        return {'scope': 'session', 'state': 'ambiguous' if len(results) > 1 else ('available' if results else 'unknown'),
                'results': results, 'unknown': not bool(results)}


def guard_final(ctx, request, response):
    """Recompute under the caller's held store lock through serialization/send."""
    current = search(ctx, request)
    if current != response:
        _error('stale_context', 'The search results changed or are unavailable.', 409)
    return current


def resolve_destination(ctx, ref, region_id=None, archive=None):
    if isinstance(ref, dict) and set(ref) == {'sessionId', 'sourceId', 'sourceRevision'}:
        ref = parse_source_ref(ref)
        if region_id is not None or archive is not None:
            _error('not_found', 'The source is unavailable.', 404)
        with ctx.lock:
            _check_actor(ctx)
            item = _source_projection(ctx.resolve_source(ref))
            if item is None:
                _error('not_found', 'The source is unavailable.', 404)
            return item
    ref = parse_ref(ref)
    with ctx.lock:
        _check_actor(ctx)
        if archive is not None:
            from . import channel_authority, waves23_moment_media
            if not isinstance(archive, dict) or set(archive) != {'channelId', 'grantId', 'revision'}:
                _error('not_found', 'The moment is unavailable.', 404)
            projected = channel_authority.project_source(ctx, archive['channelId'], archive['grantId'], archive['revision'])
            if projected['ref'] != ref or region_id is not None:
                _error('not_found', 'The moment is unavailable.', 404)
            moment = {'ref': ref, 'text': projected['excerpt']}
            item = _projection({'ref': ref, 'moment': moment})
            item['destination']['archive'] = copy.deepcopy(archive)
            try:
                item['destination']['image'] = waves23_moment_media.inspect(ctx, ref, None, archive)
            except Phase10Error:
                pass
            return item
        if ref['sessionId'] != ctx.sid:
            _error('not_found', 'The moment is unavailable.', 404)
        row = ctx.resolve([ref])[0]
        if region_id is None:
            item = _projection(row)
            from . import waves23_moment_media
            try:
                item['destination']['image'] = waves23_moment_media.inspect(ctx, ref)
            except Phase10Error:
                pass
            return item
        if not isinstance(region_id, str) or not 1 <= len(region_id) <= 128:
            _error('invalid_ref', 'The selected region is invalid.')
        for _, item in _visual_candidates(ctx, ref['startMs'], ref['endMs']):
            if item['ref'] == ref and item['regionId'] == region_id:
                from . import waves23_moment_media
                try:
                    item['destination']['image'] = waves23_moment_media.inspect(ctx, ref, region_id)
                except Phase10Error:
                    pass
                return item
        _error('not_found', 'The selected region is unavailable.', 404)


def guard_destination(ctx, request, response):
    current = resolve_destination(ctx, request['ref'], request.get('regionId'), request.get('archive'))
    if current != response:
        _error('stale_context', 'The selected moment changed or is unavailable.', 409)
    return current


def source_changed_db(db, sid, source_id, previous_revision):
    """Rebuild a corrected ASR moment inside the caller's source transaction.

    The caller authenticates the creator, holds store.LOCK, updates the source,
    invokes the impact fence and calls this before committing. Old moments need
    no mutation: Context.resolve rejects their source revision atomically.
    """
    from . import store
    from .http import expired
    if not db.in_transaction:
        raise ValueError('source change requires caller transaction')
    if not isinstance(sid, str) or not isinstance(source_id, str) or type(previous_revision) is not int or previous_revision < 1:
        _error('invalid_request', 'A source and revision are required.')
    row = db.execute("SELECT revision,data FROM objects WHERE kind='source' AND id=? AND session_id=?", (source_id, sid)).fetchone()
    if not row or row['revision'] != previous_revision + 1:
        _error('stale_context', 'The source is unavailable or changed.', 409)
    source = json.loads(row['data'])
    from . import waves23_moment_media
    waves23_moment_media.source_changed_db(db, sid, source_id)
    source.update(id=source_id, _revision=row['revision'])
    if source.get('status') != 'active' or expired(source):
        return {'state': 'unavailable', 'ref': None}
    segments = source.get('segments')
    if not isinstance(segments, list) or not segments or not isinstance(segments[0], dict) or not isinstance(segments[-1], dict):
        return {'state': 'unavailable', 'ref': None}
    try:
        selection = {'startMs': _ms(segments[0].get('sessionStartSeconds')),
                     'endMs': _ms(segments[-1].get('sessionEndSeconds')), 'kind': 'correction'}
        moment = build_moments(source, [selection])[0]
    except Phase10Error as exc:
        if exc.code == 'alignment_unavailable':
            return {'state': 'unavailable', 'ref': None}
        raise
    mid = moment['ref']['momentId']
    existing = db.execute("SELECT session_id,data FROM objects WHERE kind='p10moment' AND id=?", (mid,)).fetchone()
    value = dict(moment, id=mid)
    if existing:
        if existing['session_id'] != sid or json.loads(existing['data']) != value:
            _error('index_conflict', 'The indexed moment conflicts.', 409)
    else:
        db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)",
                   ('p10moment', mid, sid, None, 1, json.dumps(value, ensure_ascii=False), store.now()))
    return {'state': 'indexed', 'ref': copy.deepcopy(moment['ref'])}


def rebuild_correction(ctx, source_id, revision):
    """Idempotently index the corrected full aligned interval; never invoke a model."""
    from .http import expired
    if not isinstance(source_id, str) or type(revision) is not int or revision < 1:
        _error('invalid_request', 'A source and revision are required.')
    with ctx.lock:
        _check_actor(ctx)
        if ctx.actor['role'] != 'creator':
            _error('forbidden', 'Only the creator can index a correction.', 403)
        source = ctx.store.get('source', source_id, ctx.sid)
        if not source or source.get('_revision') != revision or source.get('status') != 'active' or expired(source):
            _error('stale_context', 'The source is unavailable or changed.', 409)
        segments = source.get('segments')
        if not isinstance(segments, list) or not segments or not isinstance(segments[0], dict) or not isinstance(segments[-1], dict):
            _error('alignment_unavailable', 'Source timing is unavailable.', 409)
        selection = {'startMs': _ms(segments[0].get('sessionStartSeconds')),
                     'endMs': _ms(segments[-1].get('sessionEndSeconds')), 'kind': 'correction'}
        moment = build_moments(source, [selection])[0]
        mid = moment['ref']['momentId']
        existing = ctx.store.get('p10moment', mid, ctx.sid)
        if existing is None:
            ctx.store.put('p10moment', ctx.sid, moment, oid=mid)
        elif any(existing.get(k) != v for k, v in moment.items()):
            _error('index_conflict', 'The indexed moment conflicts.', 409)
        return {'moment': _projection(ctx.resolve([moment['ref']])[0])}


def handle(handler, sid, actor, method, parts):
    ctx = Context(handler, sid, actor)
    if method == 'POST' and parts == ['rebuild-correction']:
        body = handler.body()
        if not isinstance(body, dict) or set(body) != {'sourceId', 'sourceRevision'}:
            _error('invalid_request', 'A source and revision are required.')
        result = rebuild_correction(ctx, body['sourceId'], body['sourceRevision'])
        handler._w23_moment_destination_binding = (sid, dict(actor), {'ref': result['moment']['ref']}, copy.deepcopy(result['moment']))
        handler._p10_refs = [copy.deepcopy(result['moment']['ref'])]
        return 200, result
    if method == 'POST' and parts == ['search']:
        body = handler.body()
        response = search(ctx, body)
        handler._w23_moment_search_binding = (sid, dict(actor), copy.deepcopy(body), copy.deepcopy(response))
        return 200, response
    if method == 'POST' and parts == ['destination']:
        body = handler.body()
        if not isinstance(body, dict) or 'ref' not in body or set(body) - {'ref', 'regionId', 'archive'}:
            _error('invalid_ref', 'An exact moment reference is required.')
        result = resolve_destination(ctx, body['ref'], body.get('regionId'), body.get('archive'))
        handler._w23_moment_destination_binding = (sid, dict(actor), copy.deepcopy(body), copy.deepcopy(result))
        if 'archive' not in body and result['destination']['kind'] != 'source': handler._p10_refs = [copy.deepcopy(result['ref'])]
        return 200, {'moment': result}
    if method == 'POST' and parts == ['image']:
        from . import waves23_moment_media
        body = handler.body()
        if not isinstance(body, dict) or not {'ref', 'assetId'} <= set(body) or set(body) - {'ref', 'assetId', 'regionId', 'archive'}:
            _error('invalid_request', 'An exact image reference is required.')
        metadata, raw = waves23_moment_media.bytes_for(ctx, body['ref'], body['assetId'], body.get('regionId'), body.get('archive'))
        handler._w23_moment_image_binding = (sid, dict(actor), copy.deepcopy(body), copy.deepcopy(metadata), raw)
        return 200, raw, metadata['mimeType']
    _error('not_found', 'Moment operation unavailable.', 404)
