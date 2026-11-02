"""Current-rights, bounded navigation over the existing moment index."""
import copy
import json

from .phase10_common import Context, Phase10Error, parse_ref, parse_source_ref
from . import waves23_moment_index as index

MAX_CANDIDATES = 2000
MAX_SIDE = 10


def _error(code, message, status=400):
    raise Phase10Error(code, message, status)


def _request(body):
    if not isinstance(body, dict) or set(body) - {'ref', 'archive', 'before', 'after'} or 'ref' not in body:
        _error('invalid_request', 'Select one exact source or moment.')
    before, after = body.get('before', 1), body.get('after', 1)
    if type(before) is not int or type(after) is not int or not 0 <= before <= MAX_SIDE or not 0 <= after <= MAX_SIDE:
        _error('invalid_request', 'The trail bounds are invalid.')
    raw = body['ref']
    ref = parse_source_ref(raw) if isinstance(raw, dict) and set(raw) == {'sessionId', 'sourceId', 'sourceRevision'} else parse_ref(raw)
    archive = body.get('archive')
    if archive is not None and (not isinstance(archive, dict) or set(archive) != {'channelId', 'grantId', 'revision'}):
        _error('invalid_request', 'The archive grant is invalid.')
    return ref, archive, before, after


def _label(ctx, item):
    item = copy.deepcopy(item)
    ref = item['ref']
    row = ctx.store.get('p10moment', ref['momentId'], ref['sessionId']) if 'momentId' in ref else None
    item['trailState'] = 'corrected' if row and row.get('ref') == ref and row.get('kind') == 'correction' else 'current'
    return item


def trail(ctx, body):
    """Project one explicit selection and its current, separately authorized neighbors."""
    ref, archive, before, after = _request(body)
    with ctx.lock:
        # This also validates actor, source revision, exact grant and selected destination.
        try:
            selected = index.resolve_destination(ctx, ref, archive=archive)
        except Phase10Error:
            # A creator may see a content-free retirement marker for an exact
            # own-session current identity. Others and all archive failures stay
            # indistinguishable, preserving withdrawal and membership privacy.
            index._check_actor(ctx)
            source = ctx.store.get('source', ref['sourceId'], ctx.sid) if ref['sessionId'] == ctx.sid else None
            moment = ctx.store.get('p10moment', ref['momentId'], ctx.sid) if 'momentId' in ref else None
            if (archive is None and ctx.actor.get('role') == 'creator' and source
                    and source.get('_revision') == ref['sourceRevision']
                    and source.get('status') in ('retired', 'withdrawn', 'retracted')
                    and ('momentId' not in ref or (moment and moment.get('ref') == ref))):
                return {'state': 'retired', 'selected': None, 'previous': [], 'next': [],
                        'context': 'unavailable', 'labels': ['retired', 'unavailable'], 'truncated': False}
            raise
        if 'momentId' not in ref:
            return {'state': 'current', 'selected': _label(ctx, selected), 'previous': [], 'next': [],
                    'context': 'whole_source', 'labels': ['current'], 'truncated': False}
        candidates = []
        if archive is None:
            rows = ctx.store.all('p10moment', ctx.sid)
            if len(rows) > MAX_CANDIDATES:
                _error('index_capacity', 'The moment set exceeds its supported limit.', 409)
            for row in rows:
                try:
                    other = parse_ref(row.get('ref'))
                    if (other['sessionId'], other['sourceId'], other['sourceRevision']) != (ref['sessionId'], ref['sourceId'], ref['sourceRevision']):
                        continue
                    item = index.resolve_destination(ctx, other)
                    candidates.append(item)
                except (Phase10Error, KeyError, TypeError, ValueError):
                    continue
        else:
            from . import channel_authority
            channel_authority.require_member(ctx, archive['channelId'])
            with ctx.store.connect() as db:
                rows = db.execute("SELECT id,revision,data FROM objects WHERE kind='w24archivegrant' LIMIT ?", (MAX_CANDIDATES + 1,)).fetchall()
            if len(rows) > MAX_CANDIDATES:
                _error('index_capacity', 'The archive exceeds its supported limit.', 409)
            for row in rows:
                try:
                    data = json.loads(row['data'])
                    if data.get('channelId') != archive['channelId'] or data.get('kind') is not None or not data.get('active'):
                        continue
                    grant = {'channelId': archive['channelId'], 'grantId': row['id'], 'revision': row['revision']}
                    projected = channel_authority.project_source(ctx, grant['channelId'], grant['grantId'], grant['revision'])
                    other = parse_ref(projected['ref'])
                    if (other['sessionId'], other['sourceId'], other['sourceRevision']) != (ref['sessionId'], ref['sourceId'], ref['sourceRevision']):
                        continue
                    candidates.append(index.resolve_destination(ctx, other, archive=grant))
                except (Phase10Error, KeyError, TypeError, ValueError):
                    continue
        def key(item):
            r = item['ref']
            return (r['startMs'], r['endMs'], r['momentId'])
        candidates.sort(key=key)
        # Duplicate archive grants for the selected ref remain explicit, never guessed.
        matches = [i for i, item in enumerate(candidates) if item['ref'] == ref and item['destination'].get('archive') == archive]
        if len(matches) != 1:
            _error('stale_context', 'The selected moment is unavailable or ambiguous.', 409)
        pos = matches[0]
        # A revision number alone is not evidence of a correction.
        selected = _label(ctx, selected)
        state = selected['trailState']
        return {'state': state, 'selected': selected,
                'previous': [_label(ctx, item) for item in candidates[max(0, pos-before):pos]],
                'next': [_label(ctx, item) for item in candidates[pos+1:pos+1+after]], 'context': 'timed',
                'labels': [state], 'truncated': pos > before or len(candidates)-pos-1 > after}


def guard_final(ctx, request, response):
    current = trail(ctx, request)
    if current != response:
        _error('stale_context', 'The trail changed or is unavailable.', 409)
    return current


def handle(handler, sid, actor, method, parts):
    if method != 'POST' or parts != ['trail']:
        _error('not_found', 'Moment trail is unavailable.', 404)
    body = handler.body()
    response = trail(Context(handler, sid, actor), body)
    handler._w27_moment_trail_binding = (sid, dict(actor), copy.deepcopy(body), copy.deepcopy(response))
    return 200, response
