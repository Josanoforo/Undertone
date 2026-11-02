"""Real-store correction impact, mutation, and replacement primitives."""
import json
import hashlib
from .phase10_common import Context, Phase10Error
from . import waves21_correction_impact as impact


def _change_fingerprint(source_id, previous_revision, change):
    """Hash the validated source change without truncating valid source text.

    The generic impact serializer limits metadata objects to 16 KiB, while a
    source correction permits 20,000 characters. The canonical encoding is
    otherwise identical, preserving fingerprints of existing receipts.
    """
    value = {'sourceId': source_id, 'previousRevision': previous_revision,
             'change': change}
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _invalidate_session_receipts(db, store, sid, source_id):
    """Redact only dependencies belonging to this session's source."""
    for row in db.execute("SELECT id,data FROM objects WHERE kind='p10vaultentry'").fetchall():
        try:
            entry = json.loads(row['data'])
        except (TypeError, ValueError):
            continue
        ref = entry.get('ref')
        if (isinstance(ref, dict) and ref.get('sessionId') == sid
                and ref.get('sourceId') == source_id
                and isinstance(entry.get('vaultId'), str)):
            store.phase10_forget_entry_db(db, entry['vaultId'], row['id'])
    for row in db.execute('SELECT actor_id,operation,request_id,refs FROM phase10_receipts WHERE session_id=?', (sid,)).fetchall():
        try:
            refs = json.loads(row['refs'])
        except (TypeError, ValueError):
            refs = []
        if any(isinstance(ref, dict) and ref.get('sessionId') == sid and
               ref.get('sourceId') == source_id for ref in refs):
            db.execute("UPDATE phase10_receipts SET state=CASE WHEN state IN ('pending','unknown') THEN 'unknown' ELSE 'failed' END,status=409,result=NULL WHERE session_id=? AND actor_id=? AND operation=? AND request_id=?", (sid, row['actor_id'], row['operation'], row['request_id']))


def _refs(value):
    """Return exact source refs from supported persisted snapshot shapes."""
    if isinstance(value, dict):
        if set(value) in ({'sessionId', 'sourceId', 'sourceRevision'},
                          {'sessionId', 'sourceId', 'sourceRevision', 'momentId', 'startMs', 'endMs'}):
            yield value
        else:
            for item in value.values():
                yield from _refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _refs(item)


def discover(db, sid, source_id, source_revision):
    """Discover actual current persisted derivatives; do not project content.

    Must run in the source transaction or under the shared store lock. Existing
    rows are not presumed to be public merely because their source is public.
    """
    impact._id(sid); impact._id(source_id); impact._rev(source_revision)
    found = []
    def matches(value):
        return any(r.get('sessionId') == sid and r.get('sourceId') == source_id and
                   r.get('sourceRevision') == source_revision for r in _refs(value))
    for row in db.execute('SELECT seq,moment_id,ref FROM phase12_caption_feed WHERE session_id=? AND source_id=?', (sid, source_id)):
        ref = json.loads(row['ref'])
        if matches(ref):
            found.append({'kind':'caption','id':row['moment_id'],'revision':source_revision,
                          'state':'current','scope':'public','owner':None})
    for row in db.execute("SELECT seq,actor_id,ref,state FROM phase12_jobs WHERE session_id=? AND kind IN ('speech','w20_speech')", (sid,)):
        ref = json.loads(row['ref'])
        linked = matches(ref)
        # Studio selections point to a specific material version rather than
        # embedding the underlying moment references in the job itself.
        if not linked and ref.get('type') == 'studio':
            material = db.execute("SELECT data FROM objects WHERE kind='p10material' AND id=? AND session_id=?", (ref.get('materialId'), sid)).fetchone()
            if material:
                value = json.loads(material['data'])
                linked = value.get('currentVersion') == ref.get('version') and matches(value.get('refs', []))
        if linked:
            # Completion is not evidence that a listener consumed audio.
            state = 'current'
            found.append({'kind':'speech','id':str(row['seq']),'revision':source_revision,
                          'state':state,'scope':'private','owner':row['actor_id']})
    for row in db.execute("SELECT kind,id,owner_id,data FROM objects WHERE session_id=? AND kind IN ('p10material','w18record')", (sid,)):
        value = json.loads(row['data'])
        refs = value.get('refs', []) if row['kind'] == 'p10material' else value.get('snapshot', {})
        if not matches(refs):
            continue
        kind = 'material' if row['kind'] == 'p10material' else 'record'
        version = value.get('currentVersion') if kind == 'material' else value.get('version')
        if type(version) is not int or version < 1:
            continue
        # Records and studio materials are creator editorial work; never infer
        # viewer access from the linked source alone.
        found.append({'kind':kind,'id':row['id'],'revision':version,'state':'current',
                      'scope':'private','owner':row['owner_id']})
    return found



def register_discovered(db, sid, source_id, source_revision):
    """Persist actual derivative identities in the caller's source transaction.

    This index contains no derivative content. Object revisions and job
    fingerprints are retained so a subsequent mutation cannot silently treat
    a newer target as the one that was inspected. The caller holds store.LOCK
    and must own the transaction; this function performs no external effects.
    """
    if not db.in_transaction:
        raise ValueError('registration requires caller transaction')
    items = discover(db, sid, source_id, source_revision)
    for item in items:
        kind, oid = item['kind'], item['id']
        if kind == 'caption':
            row = db.execute('SELECT seq,ref FROM phase12_caption_feed WHERE session_id=? AND moment_id=?', (sid, oid)).fetchone()
            identity = {'sequence': row['seq'], 'refHash': impact._hash(json.loads(row['ref']))}
        elif kind == 'speech':
            row = db.execute('SELECT fingerprint,credential_hash,state,transport FROM phase12_jobs WHERE session_id=? AND seq=?', (sid, int(oid))).fetchone()
            identity = {'fingerprint': row['fingerprint'], 'credentialHash': row['credential_hash'],
                        'state': row['state'], 'transport': row['transport']}
        else:
            object_kind = 'p10material' if kind == 'material' else 'w18record'
            row = db.execute('SELECT revision FROM objects WHERE session_id=? AND kind=? AND id=?', (sid, object_kind, oid)).fetchone()
            identity = {'objectRevision': row['revision']}
        key = impact._key('derivative', sid, source_id, source_revision, kind, oid)
        value = {'sourceId': source_id, 'sourceRevision': source_revision,
                 'kind': kind, 'targetId': oid, 'targetVersion': item['revision'],
                 'scope': item['scope'], 'owner': item['owner'], 'identity': identity}
        impact._put(db, 'w21derivative', key, sid, item['owner'], value)
    return len(items)


def handle(handler, sid, actor, method, parts):
    """Authenticated correction, recovery and permission-filtered preview."""
    ctx = Context(handler, sid, actor)
    if method == 'POST' and len(parts) == 3 and parts[0] == 'changes' and parts[2] == 'speech-replacement':
        try:
            return 200, {'replacement': replace_speech(ctx, parts[1], handler.body())}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Replacement unavailable.', exc.status) from exc
    if method == 'POST' and len(parts) == 3 and parts[0] == 'changes' and parts[2] == 'caption-replacement':
        try:
            return 200, {'replacement': replace_caption(ctx, parts[1], handler.body())}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Replacement unavailable.', exc.status) from exc
    if method == 'POST' and len(parts) == 3 and parts[0] == 'changes' and parts[2] == 'record-replacement':
        try:
            return 200, {'replacement': replace_record(ctx, parts[1], handler.body())}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Replacement unavailable.', exc.status) from exc
    if method == 'POST' and len(parts) == 3 and parts[0] == 'changes' and parts[2] == 'material-replacement':
        try:
            return 200, {'replacement': replace_material(ctx, parts[1], handler.body())}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Replacement unavailable.', exc.status) from exc
    if method == 'POST' and parts == ['changes']:
        body = handler.body()
        if not isinstance(body, dict) or set(body) != {'sourceRef', 'expectedRevision', 'requestId', 'change'}:
            raise Phase10Error('invalid_request', 'A source, revision, request ID and change are required.', 422)
        try:
            result = mutate_source(ctx, body['sourceRef'], body['expectedRevision'], body['requestId'], body['change'])
            with ctx.lock:
                return 200, {'change': project_change(ctx, result['id'])}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Correction unavailable.', exc.status) from exc
    if method == 'GET' and len(parts) == 2 and parts[0] == 'recovery':
        try:
            return 200, {'change': recover_source_change(ctx, parts[1])}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Correction unavailable.', exc.status) from exc
    if method == 'GET' and len(parts) == 2 and parts[0] == 'requests':
        try:
            impact._id(parts[1])
            with ctx.lock, ctx.store.connect() as db:
                ctx.check_actor()
                receipt = impact._get(db, 'w21sourcechangereceipt',
                                      impact._key(sid, actor['owner'], parts[1]), sid)
                if not receipt:
                    raise Phase10Error('not_found', 'Correction unavailable.', 404)
                return 200, {'change': project_change(ctx, receipt['intentId'])}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Correction unavailable.', exc.status) from exc
    if method == 'GET' and len(parts) == 2 and parts[0] == 'changes':
        try:
            return 200, {'change': project_change(ctx, parts[1])}
        except impact.ImpactError as exc:
            raise Phase10Error(exc.code, 'Correction unavailable.', exc.status) from exc
    if method != 'POST' or parts != ['preview']:
        raise Phase10Error('not_found', 'Correction operation unavailable.', 404)
    body = handler.body()
    if not isinstance(body, dict) or set(body) != {'sourceRef','expectedRevision','reason'}:
        raise Phase10Error('invalid_request', 'A source, revision and reason are required.', 422)
    try:
        source = impact._id(body['sourceRef']); revision = impact._rev(body['expectedRevision'])
    except impact.ImpactError as exc:
        raise Phase10Error(exc.code, 'Invalid correction request.', exc.status) from exc
    reason = body['reason']
    if not isinstance(reason,str) or not reason.strip() or len(reason)>500:
        raise Phase10Error('invalid_request', 'A correction reason is required.', 422)
    with ctx.lock, ctx.store.connect() as db:
        ctx.check_actor()
        if actor.get('role') != 'creator':
            raise Phase10Error('not_found', 'Correction operation unavailable.', 404)
        src = ctx.store.get('source', source, sid)
        from .http import expired
        if not src or src.get('status') != 'active' or expired(src):
            raise Phase10Error('not_found', 'Source unavailable.', 404)
        if src.get('_revision') != revision:
            raise Phase10Error('stale_revision', 'Source changed.', 409)
        visible = []
        for target in discover(db, sid, source, revision):
            if target['scope'] == 'private' and target['owner'] != actor['owner']:
                continue
            visible.append(impact._view(target, reason))
        return 200, {'source':source,'revision':revision,'reason':reason,'affected':visible}




def mutate_source(ctx, source_id, previous_revision, request_id, change):
    """Authenticate and atomically update a source and its derivative fences.

    No external effects occur here. PRIMARY must mount the route and hold the
    lock through final response serialization, including project_change.
    """
    from datetime import datetime
    from .http import expired
    for value in (ctx.sid, source_id, request_id, ctx.actor.get('owner')):
        impact._id(value)
    impact._rev(previous_revision)
    allowed = {'text', 'title', 'status', 'audienceVisible', 'expiresAt'}
    if not isinstance(change, dict) or not change or set(change) - allowed:
        raise Phase10Error('invalid_request', 'Invalid source change.', 422)
    change = dict(change)
    for field, limit in (('text', 20000), ('title', 200)):
        if field in change:
            value = change[field]
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise Phase10Error('invalid_field', 'Invalid source field.', 422)
            change[field] = value.strip()
    if 'status' in change and change['status'] not in ('active', 'retracted'):
        raise Phase10Error('invalid_status', 'Invalid source status.', 422)
    if 'audienceVisible' in change and type(change['audienceVisible']) is not bool:
        raise Phase10Error('invalid_field', 'Invalid source visibility.', 422)
    if change.get('expiresAt') is not None:
        try:
            dt = datetime.fromisoformat(change['expiresAt'].replace('Z', '+00:00'))
            if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Phase10Error('invalid_expiry', 'Expiry must be ISO UTC.', 422)
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            raise Phase10Error('not_found', 'Correction unavailable.', 404)
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            replay = check_change_request(db, ctx.sid, ctx.actor['owner'], request_id, source_id, previous_revision, change)
            if replay:
                db.commit()
                return replay
            row = db.execute("SELECT revision,data FROM objects WHERE kind='source' AND id=? AND session_id=?", (source_id, ctx.sid)).fetchone()
            if not row:
                raise Phase10Error('not_found', 'Source unavailable.', 404)
            value = json.loads(row['data'])
            if row['revision'] != previous_revision:
                raise Phase10Error('stale_revision', 'Source changed.', 409)
            if value.get('status') != 'active' or expired(value):
                raise Phase10Error('not_found', 'Source unavailable.', 404)
            value.update(change)
            if 'text' in change:
                value['creatorCorrection'] = {'text': value['text'], 'at': ctx.store.now(), 'sourceRevision': previous_revision + 1}
            else:
                value.pop('creatorCorrection', None)
            updated = db.execute("UPDATE objects SET revision=revision+1,data=? WHERE kind='source' AND id=? AND session_id=? AND revision=?", (json.dumps(value, ensure_ascii=False), source_id, ctx.sid, previous_revision)).rowcount
            if updated != 1:
                raise Phase10Error('stale_revision', 'Source changed.', 409)
            # Capture target identities and their pre-invalidation states before
            # the ordinary source-save effects cancel jobs or redact receipts.
            # Both steps remain in this same transaction.
            result = source_changed(db, ctx.sid, source_id, previous_revision, ctx.actor['owner'], request_id, change)
            from . import waves23_moment_index
            waves23_moment_index.source_changed_db(db, ctx.sid, source_id, previous_revision)
            # Preserve store.save(source)'s withdrawal, receipt/vault and job effects.
            if value.get('status') != 'active':
                db.execute('DELETE FROM phase12_original_audio WHERE session_id=? AND source_id=?', (ctx.sid, source_id))
            for material in db.execute("SELECT id,data FROM objects WHERE kind='p10material' AND session_id=?", (ctx.sid,)).fetchall():
                if any(ref.get('sourceId') == source_id for ref in json.loads(material['data']).get('refs', []) if isinstance(ref, dict)):
                    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE session_id=? AND source_id=? AND state IN ('queued','running','complete')", (ctx.sid, material['id']))
            _invalidate_session_receipts(db, ctx.store, ctx.sid, source_id)
            from . import waves21_speech_runtime
            waves21_speech_runtime.invalidate_source_db(db, ctx.sid, source_id)
            db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE session_id=? AND source_id=? AND state IN ('queued','running','complete')", (ctx.sid, source_id))
            db.commit()
            return result


def replace_speech(ctx, intent_id, body):
    """Associate an explicitly submitted existing speech job; never submit work."""
    from .http import expired
    from . import phase12_jobs
    impact._id(intent_id)
    if not isinstance(body, dict) or set(body) != {'replacementId', 'fence', 'jobId'}:
        raise Phase10Error('invalid_request', 'Invalid replacement.', 422)
    replacement_id = impact._id(body['replacementId'])
    impact._id(body['fence'])
    job_id = body['jobId']
    if type(job_id) is not int or job_id < 1:
        raise Phase10Error('invalid_request', 'Invalid speech job.', 422)
    fingerprint = _change_fingerprint(intent_id, 0, body)
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            raise impact.ImpactError('unavailable', 404)
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT owner_id,data FROM objects WHERE kind='w21sourcechange' AND id=? AND session_id=?", (intent_id, ctx.sid)).fetchone()
            if not row or row['owner_id'] != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            intent = json.loads(row['data'])
            source = ctx.store.get('source', intent['sourceId'], ctx.sid)
            fence = impact._get(db, 'w21sourcefence', impact._key(ctx.sid, intent['sourceId']), ctx.sid)
            if (not source or source.get('_revision') != intent['revision'] or source.get('status') != 'active'
                    or expired(source) or not source.get('audienceVisible') or not fence
                    or fence.get('intentId') != intent_id or fence.get('revision') != intent['revision']
                    or fence.get('fence') != body['fence'] or intent.get('fence') != body['fence']):
                raise impact.ImpactError('stale_context')
            target = next((x for x in intent['targets'] if x['kind'] == 'speech' and x['replacementId'] == replacement_id), None)
            if not target:
                raise impact.ImpactError('unavailable', 404)
            registration = impact._get(db, 'w21derivative', impact._key('derivative', ctx.sid, intent['sourceId'], intent['previousRevision'], 'speech', target['id']), ctx.sid)
            if not registration or registration.get('owner') != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            job = db.execute("SELECT * FROM phase12_jobs WHERE session_id=? AND seq=? AND kind='speech'", (ctx.sid, job_id)).fetchone()
            if (not job or job['actor_id'] != ctx.actor['owner'] or job['role'] != ctx.actor['role']
                    or job['credential_hash'] != ctx.store.digest(getattr(ctx.handler, '_auth_token', ''))
                    or job['state'] not in ('queued', 'running', 'complete')
                    or not any(x['kind'] == 'speech' and x['id'] == str(job_id)
                               for x in discover(db, ctx.sid, intent['sourceId'], intent['revision']))):
                raise impact.ImpactError('stale_context')
            phase12_jobs.rights(job)
            if target.get('state') == 'applied':
                if target.get('replacementFingerprint') != fingerprint or target.get('jobFingerprint') != job['fingerprint']:
                    raise impact.ImpactError('request_conflict')
            elif target.get('state') == 'pending_replacement':
                target.update(state='applied', replacementFingerprint=fingerprint,
                              replacementJobId=job_id, jobFingerprint=job['fingerprint'])
                impact._put(db, 'w21sourcechange', intent_id, ctx.sid, ctx.actor['owner'], intent)
            else:
                raise impact.ImpactError('stale_target')
            db.commit()
            return {'replacementId': replacement_id, 'jobId': job_id, 'state': job['state']}


def replace_caption(ctx, intent_id, body):
    """Associate an existing current indexed caption with its invalidated target.

    Indexing remains the ordinary feed lifecycle; this operation never invents
    text, invokes a provider, or changes the index. The caller holds the shared
    lock through response serialization.
    """
    from .http import expired
    impact._id(intent_id)
    if not isinstance(body, dict) or set(body) != {'replacementId', 'fence', 'ref'}:
        raise Phase10Error('invalid_request', 'Invalid replacement.', 422)
    replacement_id = impact._id(body['replacementId'])
    impact._id(body['fence'])
    ref = body['ref']
    if not isinstance(ref, dict):
        raise Phase10Error('invalid_request', 'An indexed reference is required.', 422)
    fingerprint = _change_fingerprint(intent_id, 0, body)
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            raise impact.ImpactError('unavailable', 404)
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT owner_id,data FROM objects WHERE kind='w21sourcechange' AND id=? AND session_id=?", (intent_id, ctx.sid)).fetchone()
            if not row or row['owner_id'] != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            intent = json.loads(row['data'])
            source = ctx.store.get('source', intent['sourceId'], ctx.sid)
            fence = impact._get(db, 'w21sourcefence', impact._key(ctx.sid, intent['sourceId']), ctx.sid)
            if (not source or source.get('_revision') != intent['revision'] or source.get('status') != 'active'
                    or expired(source) or not source.get('audienceVisible') or not fence
                    or fence.get('intentId') != intent_id or fence.get('revision') != intent['revision']
                    or fence.get('fence') != body['fence'] or intent.get('fence') != body['fence']):
                raise impact.ImpactError('stale_context')
            target = next((x for x in intent['targets'] if x['kind'] == 'caption' and x['replacementId'] == replacement_id), None)
            if not target:
                raise impact.ImpactError('unavailable', 404)
            if (ref.get('sessionId') != ctx.sid or ref.get('sourceId') != intent['sourceId']
                    or ref.get('sourceRevision') != intent['revision']):
                raise impact.ImpactError('stale_context')
            rows = db.execute('SELECT ref FROM phase12_caption_feed WHERE session_id=? AND source_id=? AND moment_id=?',
                              (ctx.sid, intent['sourceId'], ref.get('momentId'))).fetchall()
            if not any(json.loads(item['ref']) == ref for item in rows):
                raise impact.ImpactError('stale_context')
            ctx.resolve([ref])
            if target.get('state') == 'applied':
                if target.get('replacementFingerprint') != fingerprint:
                    raise impact.ImpactError('request_conflict')
            elif target.get('state') == 'pending_replacement':
                target.update(state='applied', replacementFingerprint=fingerprint, replacementRef=ref)
                impact._put(db, 'w21sourcechange', intent_id, ctx.sid, ctx.actor['owner'], intent)
            else:
                raise impact.ImpactError('stale_target')
            db.commit()
            return {'replacementId': replacement_id, 'ref': ref}


def replace_material(ctx, intent_id, body):
    """Save a creator-authored replacement draft and its receipt atomically.

    This performs no generation. The caller must keep the store lock through
    final response serialization. Other derivative types have separate flows.
    """
    from . import phase10_studio as studio
    from .http import expired
    impact._id(intent_id)
    fields = {'replacementId', 'fence', 'title', 'body', 'refs'}
    if not isinstance(body, dict) or set(body) not in (fields, fields | {'segmentRevision'}):
        raise Phase10Error('invalid_request', 'Invalid replacement.', 422)
    if 'segmentRevision' in body and (type(body['segmentRevision']) is not int or body['segmentRevision'] < 1):
        raise Phase10Error('invalid_request', 'Invalid segment revision.', 422)
    replacement_id = impact._id(body['replacementId'])
    impact._id(body['fence'])
    title = studio.text(body['title'], 200)
    content = studio.text(body['body'], 12000)
    refs = body['refs']
    if not isinstance(refs, list) or not refs or any(not isinstance(x, dict) or x.get('sessionId') != ctx.sid for x in refs):
        raise Phase10Error('invalid_request', 'Current session references are required.', 422)
    fingerprint_body = {'replacementId': replacement_id,
        'fence': body['fence'], 'title': title, 'body': content, 'refs': refs}
    if 'segmentRevision' in body:
        fingerprint_body['segmentRevision'] = body['segmentRevision']
    fingerprint = _change_fingerprint(intent_id, 0, fingerprint_body)
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            raise Phase10Error('not_found', 'Replacement unavailable.', 404)
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT owner_id,data FROM objects WHERE kind='w21sourcechange' AND id=? AND session_id=?", (intent_id, ctx.sid)).fetchone()
            if not row or row['owner_id'] != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            intent = json.loads(row['data'])
            fence = impact._get(db, 'w21sourcefence', impact._key(ctx.sid, intent['sourceId']), ctx.sid)
            source = ctx.store.get('source', intent['sourceId'], ctx.sid)
            if (not source or source.get('_revision') != intent['revision'] or source.get('status') != 'active'
                    or expired(source) or not fence or fence.get('intentId') != intent_id
                    or fence.get('revision') != intent['revision'] or fence.get('fence') != body['fence']
                    or intent.get('fence') != body['fence']):
                raise impact.ImpactError('stale_context')
            target = next((x for x in intent['targets'] if x['kind'] == 'material' and x['replacementId'] == replacement_id), None)
            if not target:
                raise impact.ImpactError('unavailable', 404)
            current = db.execute("SELECT owner_id,revision,data FROM objects WHERE kind='p10material' AND id=? AND session_id=?", (target['id'], ctx.sid)).fetchone()
            if not current or current['owner_id'] != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            material = json.loads(current['data'])
            bound = 'w18Segment' in material
            if bound != ('segmentRevision' in body):
                raise Phase10Error('invalid_request', 'Segment revision required only for segment material.', 422)
            if bound and not isinstance(material['w18Segment'], dict):
                raise impact.ImpactError('stale_target')
            if target.get('state') == 'applied':
                if target.get('replacementFingerprint') != fingerprint:
                    raise impact.ImpactError('request_conflict')
                if current['revision'] != target.get('replacementObjectRevision') or material.get('currentVersion') != target.get('newVersion'):
                    raise impact.ImpactError('stale_target')
                if bound:
                    from . import waves18_segments as segments
                    segment = segments.read(db, segments.SEG, material['w18Segment'].get('segmentId'), ctx.sid)
                    if (not segment or segment.get('creatorId') != ctx.actor['owner']
                            or segment.get('state') != 'open' or segment.get('cueId')
                            or segment['_revision'] != target.get('replacementSegmentRevision')
                            or target.get('replacementSegmentRevision') != body['segmentRevision'] + 1):
                        raise impact.ImpactError('stale_target')
                    if any(p.get('segmentId') == segment['id'] and p.get('state') in ('pending', 'unknown')
                           for p in ctx.store.all(segments.REC, ctx.sid)):
                        raise impact.ImpactError('stale_target')
                    # Segment delivery compares the complete current store projection.
                    studio._guard_material(ctx, dict(material, _revision=current['revision']))
                else:
                    studio._guard_material(ctx, material)
                studio.resolve_material_refs(ctx, refs)
                return {'replacementId': replacement_id, 'materialId': target['id'], 'version': target['newVersion'], 'status': 'draft'}
            if (target.get('state') != 'pending_replacement' or current['revision'] != target.get('invalidatedObjectRevision')
                    or material.get('currentVersion') != target['version'] or material.get('status') != 'draft'):
                raise impact.ImpactError('stale_target')
            if not any(r.get('sourceId') == intent['sourceId'] and r.get('sourceRevision') == intent['revision'] for r in refs):
                raise impact.ImpactError('stale_context')
            version = target['version'] + 1
            if bound:
                material = studio.replacement_material(ctx, material, target['version'], title, content, refs,
                    transaction=db, object_revision=current['revision'], segment_revision=body['segmentRevision'])
            else:
                material = studio.replacement_material(ctx, material, target['version'], title, content, refs)
            changed = db.execute("UPDATE objects SET revision=revision+1,data=? WHERE kind='p10material' AND id=? AND session_id=? AND revision=?", (json.dumps(material, ensure_ascii=False), target['id'], ctx.sid, current['revision'])).rowcount
            if changed != 1:
                raise impact.ImpactError('stale_target')
            target.update(state='applied', newVersion=version, replacementFingerprint=fingerprint, replacementObjectRevision=current['revision'] + 1)
            if bound:
                target['replacementSegmentRevision'] = body['segmentRevision'] + 1
            impact._put(db, 'w21sourcechange', intent_id, ctx.sid, ctx.actor['owner'], intent)
            db.commit()
            return {'replacementId': replacement_id, 'materialId': target['id'], 'version': version, 'status': 'draft'}


def replace_record(ctx, intent_id, body):
    """Save a validated record replacement as an unapproved version."""
    import copy
    from . import waves18_records as records
    from .http import expired
    impact._id(intent_id)
    fields = {'replacementId', 'fence', 'refs', 'chapters', 'format',
              'contributions', 'sourceLanguage', 'interpretations'}
    if not isinstance(body, dict) or set(body) not in (fields, fields | {'sourceRefs'}):
        raise Phase10Error('invalid_request', 'Invalid replacement.', 422)
    replacement_id = impact._id(body['replacementId'])
    impact._id(body['fence'])
    fingerprint = _change_fingerprint(intent_id, 0, body)
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            raise Phase10Error('not_found', 'Replacement unavailable.', 404)
        # Existing record validation checks all referenced decisions, chapters,
        # translations and current source rights under the same store lock.
        snap = records.snapshot(ctx, body)
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT owner_id,data FROM objects WHERE kind='w21sourcechange' AND id=? AND session_id=?", (intent_id, ctx.sid)).fetchone()
            if not row or row['owner_id'] != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            intent = json.loads(row['data'])
            fence = impact._get(db, 'w21sourcefence', impact._key(ctx.sid, intent['sourceId']), ctx.sid)
            source = ctx.store.get('source', intent['sourceId'], ctx.sid)
            if (not source or source.get('_revision') != intent['revision'] or source.get('status') != 'active'
                    or expired(source) or not fence or fence.get('intentId') != intent_id
                    or fence.get('revision') != intent['revision'] or fence.get('fence') != body['fence']
                    or intent.get('fence') != body['fence']):
                raise impact.ImpactError('stale_context')
            target = next ( (x for x in intent['targets'] if x['kind'] == 'record' and x['replacementId'] == replacement_id), None)
            if not target:
                raise impact.ImpactError('unavailable', 404)
            current = db.execute("SELECT owner_id,revision,data FROM objects WHERE kind='w18record' AND id=? AND session_id=?", (target['id'], ctx.sid)).fetchone()
            if not current or current['owner_id'] != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            record = json.loads(current['data'])
            if record.get('creatorId') != ctx.actor['owner']:
                raise impact.ImpactError('unavailable', 404)
            if target.get('state') == 'applied':
                if target.get('replacementFingerprint') != fingerprint:
                    raise impact.ImpactError('request_conflict')
                if current['revision'] != target.get('replacementObjectRevision') or record.get('version') != target.get('newVersion'):
                    raise impact.ImpactError('stale_target')
                records.current(ctx.sid, record['snapshot'])
                return {'replacementId': replacement_id, 'recordId': target['id'], 'version': target['newVersion'], 'status': record['state']}
            if (target.get('state') != 'pending_replacement' or current['revision'] != target.get('invalidatedObjectRevision')
                    or record.get('version') != target['version'] or record.get('state') != 'draft'):
                raise impact.ImpactError('stale_target')
            if not any(r.get('sourceId') == intent['sourceId'] and r.get('sourceRevision') == intent['revision'] for r in _refs(snap)):
                raise impact.ImpactError('stale_context')
            record.setdefault('history', []).append({'version': record['version'], 'state': record['state'], 'snapshot': copy.deepcopy(record['snapshot'])})
            record.update(version=record['version'] + 1, state='draft', snapshot=snap)
            changed = db.execute("UPDATE objects SET revision=revision+1,data=? WHERE kind='w18record' AND id=? AND session_id=? AND revision=?", (json.dumps(record, ensure_ascii=False), target['id'], ctx.sid, current['revision'])).rowcount
            if changed != 1:
                raise impact.ImpactError('stale_target')
            target.update(state='applied', newVersion=record['version'], replacementFingerprint=fingerprint, replacementObjectRevision=current['revision'] + 1)
            impact._put(db, 'w21sourcechange', intent_id, ctx.sid, ctx.actor['owner'], intent)
            db.commit()
            return {'replacementId': replacement_id, 'recordId': target['id'], 'version': record['version'], 'status': 'draft'}


def check_change_request(db, sid, actor_id, request_id, source_id, previous_revision, change):
    """Check payload-bound replay before changing a source, in the same transaction.

    The caller must authenticate the actor and validate the change before calling.
    A returned intent is a replay; None means the caller may perform the change
    and must pass the same payload to source_changed before committing.
    """
    if not db.in_transaction:
        raise ValueError('source change requires caller transaction')
    for value in (sid, actor_id, request_id, source_id):
        impact._id(value)
    impact._rev(previous_revision)
    fingerprint = _change_fingerprint(source_id, previous_revision, change)
    receipt = impact._get(db, 'w21sourcechangereceipt', impact._key(sid, actor_id, request_id), sid)
    if not receipt:
        return None
    if receipt.get('fingerprint') != fingerprint:
        raise impact.ImpactError('request_conflict')
    intent = impact._get(db, 'w21sourcechange', receipt['intentId'], sid)
    if not intent:
        raise impact.ImpactError('stale_context')
    return intent


def source_changed(db, sid, source_id, previous_revision, actor_id, request_id, change):
    """Record and invalidate actual derivatives in the caller's source transaction.

    Call only after updating the source row, with store.LOCK held and before
    commit. The caller retains the ordinary source-save side effects. No content
    or external effect is put in the intent. This is an integration primitive,
    not a complete correction endpoint or a replacement implementation.
    """
    if not db.in_transaction:
        raise ValueError('source change requires caller transaction')
    for value in (sid, source_id, actor_id, request_id):
        impact._id(value)
    impact._rev(previous_revision)
    row = db.execute("SELECT revision FROM objects WHERE kind='source' AND id=? AND session_id=?", (source_id, sid)).fetchone()
    if not row or row['revision'] != previous_revision + 1:
        raise impact.ImpactError('stale_revision')
    revision = row['revision']
    intent_id = impact._key('source-change', sid, source_id, revision, actor_id, request_id)
    fingerprint = _change_fingerprint(source_id, previous_revision, change)
    receipt_id = impact._key(sid, actor_id, request_id)
    receipt = impact._get(db, 'w21sourcechangereceipt', receipt_id, sid)
    if receipt:
        if (receipt['sourceId'], receipt['previousRevision'], receipt['intentId'], receipt.get('fingerprint')) != (source_id, previous_revision, intent_id, fingerprint):
            raise impact.ImpactError('request_conflict')
        existing = impact._get(db, 'w21sourcechange', intent_id, sid)
        if not existing:
            raise impact.ImpactError('stale_context')
        return existing
    existing = impact._get(db, 'w21sourcechange', intent_id, sid)
    if existing:
        raise impact.ImpactError('stale_context')
    items = discover(db, sid, source_id, previous_revision)
    register_discovered(db, sid, source_id, previous_revision)
    targets = []
    for item in items:
        kind, oid = item['kind'], item['id']
        registration = impact._get(db, 'w21derivative', impact._key('derivative', sid, source_id, previous_revision, kind, oid), sid)
        replacement = impact._key('replacement', intent_id, kind, oid, item['revision'])
        target = {'kind': kind, 'id': oid, 'version': item['revision'],
                  'identity': registration['identity'], 'replacementId': replacement,
                  'state': 'pending_replacement'}
        if kind == 'speech':
            db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE session_id=? AND seq=? AND state IN ('queued','running','complete')", (sid, int(oid)))
            # Generated or delivered is not proof of actual listening.
            target['historicalLimit'] = 'Audio already heard cannot be recalled.'
        elif kind in ('material', 'record'):
            object_kind = 'p10material' if kind == 'material' else 'w18record'
            current = db.execute('SELECT revision,data FROM objects WHERE kind=? AND id=? AND session_id=?', (object_kind, oid, sid)).fetchone()
            if not current or current['revision'] != registration['identity']['objectRevision']:
                raise impact.ImpactError('stale_target')
            data = json.loads(current['data'])
            if kind == 'material':
                # A source correction must never revive an explicitly withdrawn
                # editorial object. Other versions need fresh creator review.
                if data.get('status') != 'withdrawn':
                    data['status'] = 'draft'
                data['approvedVersion'] = None
            elif data.get('state') == 'approved':
                data['state'] = 'draft'
            changed = db.execute('UPDATE objects SET data=?,revision=revision+1 WHERE kind=? AND id=? AND session_id=? AND revision=?', (json.dumps(data, ensure_ascii=False), object_kind, oid, sid, current['revision'])).rowcount
            if changed != 1:
                raise impact.ImpactError('stale_target')
            target['invalidatedObjectRevision'] = current['revision'] + 1
        targets.append(target)
    fence = impact._key('source-fence', sid, source_id, revision, intent_id)
    result = {'id': intent_id, 'sourceId': source_id, 'previousRevision': previous_revision,
              'revision': revision, 'fence': fence, 'targets': targets}
    impact._put(db, 'w21sourcechange', intent_id, sid, actor_id, result)
    impact._put(db, 'w21sourcechangereceipt', receipt_id, sid, actor_id,
                {'intentId': intent_id, 'sourceId': source_id, 'previousRevision': previous_revision, 'fingerprint': fingerprint})
    impact._put(db, 'w21sourcefence', impact._key(sid, source_id), sid, actor_id,
                {'intentId': intent_id, 'revision': revision, 'fence': fence})
    return result


def project_change(ctx, intent_id):
    """Project current correction metadata, filtering every hidden derivative.

    Caller must hold store.LOCK through final response serialization.
    """
    impact._id(intent_id)
    with ctx.lock, ctx.store.connect() as db:
        ctx.check_actor()
        intent = impact._get(db, 'w21sourcechange', intent_id, ctx.sid)
        row = db.execute("SELECT owner_id FROM objects WHERE kind='w21sourcechange' AND id=? AND session_id=?", (intent_id, ctx.sid)).fetchone()
        if not intent or not row or ctx.actor.get('role') != 'creator' or row['owner_id'] != ctx.actor.get('owner'):
            raise Phase10Error('not_found', 'Correction unavailable.', 404)
        source = ctx.store.get('source', intent['sourceId'], ctx.sid)
        fence = impact._get(db, 'w21sourcefence', impact._key(ctx.sid, intent['sourceId']), ctx.sid)
        from .http import expired
        if (not source or source.get('status') != 'active' or expired(source)
                or source.get('_revision') != intent['revision'] or not fence
                or fence.get('intentId') != intent_id or fence.get('revision') != intent['revision']
                or fence.get('fence') != intent.get('fence')):
            raise Phase10Error('stale_context', 'Correction is no longer current.', 409)
        visible = []
        for target in intent['targets']:
            registration = impact._get(db, 'w21derivative', impact._key('derivative', ctx.sid, intent['sourceId'], intent['previousRevision'], target['kind'], target['id']), ctx.sid)
            if not registration or (registration['scope'] == 'private' and registration['owner'] != ctx.actor['owner']):
                continue
            # Stored ownership is historical lineage, not current access. A
            # transferred or removed private target must not leak its identity.
            if target['kind'] == 'speech':
                current = db.execute('SELECT actor_id FROM phase12_jobs WHERE session_id=? AND seq=?', (ctx.sid, int(target['id']))).fetchone()
                if not current or current['actor_id'] != ctx.actor['owner']:
                    continue
            elif target['kind'] in ('material', 'record'):
                object_kind = 'p10material' if target['kind'] == 'material' else 'w18record'
                current = db.execute('SELECT owner_id,data FROM objects WHERE kind=? AND id=? AND session_id=?', (object_kind, target['id'], ctx.sid)).fetchone()
                if not current or current['owner_id'] != ctx.actor['owner']:
                    continue
            elif target['kind'] == 'caption':
                current = db.execute('SELECT 1 FROM phase12_caption_feed WHERE session_id=? AND moment_id=? AND source_id=?', (ctx.sid, target['id'], intent['sourceId'])).fetchone()
                if not current:
                    continue
            else:
                continue
            projected = {k: target[k] for k in ('kind', 'id', 'version', 'replacementId', 'state')}
            if target['kind'] == 'material' and target['state'] == 'pending_replacement':
                material = json.loads(current['data'])
                if 'w18Segment' in material:
                    binding = material['w18Segment']
                    segment = None
                    if isinstance(binding, dict) and binding.get('sessionId') == ctx.sid:
                        from . import waves18_segments as segments
                        segment = segments.read(db, segments.SEG, binding.get('segmentId'), ctx.sid)
                    if (segment and segment.get('creatorId') == ctx.actor['owner']
                            and segment.get('state') == 'open' and segment.get('materialId') == target['id']
                            and segment.get('binding') == binding):
                        projected['segmentReplacement'] = {'segmentId': segment['id'], 'revision': segment['_revision']}
                    else:
                        projected['segmentReplacementUnavailable'] = True
            if target.get('historicalLimit'):
                projected['historicalLimit'] = target['historicalLimit']
            visible.append(projected)
        return {'id': intent_id, 'sourceId': intent['sourceId'], 'revision': intent['revision'],
                'fence': intent['fence'], 'affected': visible}


def recover_source_change(ctx, source_id):
    """Read current actor-owned correction and verified replacement metadata.

    The caller holds ctx.lock through final serialization and send and invokes
    this again at that boundary. Absence never establishes an operation failed.
    """
    impact._id(source_id)
    with ctx.lock, ctx.store.connect() as db:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator':
            raise Phase10Error('not_found', 'Correction unavailable.', 404)
        fence = impact._get(db, 'w21sourcefence', impact._key(ctx.sid, source_id), ctx.sid)
        if not fence or not isinstance(fence.get('intentId'), str):
            raise Phase10Error('not_found', 'Correction unavailable.', 404)
        result = project_change(ctx, fence['intentId'])
        if result['sourceId'] != source_id:
            raise Phase10Error('not_found', 'Correction unavailable.', 404)
        intent = impact._get(db, 'w21sourcechange', result['id'], ctx.sid)
        receipts = db.execute("SELECT data FROM objects WHERE kind='w21sourcechangereceipt' AND session_id=? AND owner_id=?", (ctx.sid, ctx.actor['owner'])).fetchall()
        receipt_found = any((lambda x: x.get('intentId') == result['id'] and x.get('sourceId') == source_id and x.get('previousRevision') == intent.get('previousRevision'))(json.loads(row['data'])) for row in receipts)
        result['correctionReceipt'] = 'confirmed' if receipt_found else 'unresolved'
        by_id = {t['replacementId']: t for t in intent['targets']}
        visible = []
        for item in result['affected']:
            target = by_id[item['replacementId']]
            state, kind = target.get('state'), target['kind']
            if state not in ('pending_replacement', 'applied'):
                continue
            replacement = None
            if kind == 'speech':
                original = db.execute('SELECT actor_id,role,credential_hash,fingerprint,state FROM phase12_jobs WHERE session_id=? AND seq=?', (ctx.sid, int(target['id']))).fetchone()
                identity = target.get('identity', {})
                if (not original or original['actor_id'] != ctx.actor['owner'] or original['role'] != ctx.actor['role']
                        or original['credential_hash'] != ctx.store.digest(getattr(ctx.handler, '_auth_token', ''))
                        or original['fingerprint'] != identity.get('fingerprint') or original['state'] != 'canceled'):
                    continue
            elif kind == 'caption':
                rows = db.execute('SELECT seq,ref FROM phase12_caption_feed WHERE session_id=? AND source_id=? AND moment_id=?', (ctx.sid, source_id, target['id'])).fetchall()
                identity = target.get('identity', {})
                if not any(row['seq'] == identity.get('sequence') and impact._hash(json.loads(row['ref'])) == identity.get('refHash') for row in rows):
                    continue
            if kind in ('material', 'record'):
                objkind = 'p10material' if kind == 'material' else 'w18record'
                row = db.execute('SELECT owner_id,revision,data FROM objects WHERE kind=? AND id=? AND session_id=?', (objkind, target['id'], ctx.sid)).fetchone()
                if not row or row['owner_id'] != ctx.actor['owner']:
                    continue
                value = json.loads(row['data'])
                version = value.get('currentVersion') if kind == 'material' else value.get('version')
                status = value.get('status') if kind == 'material' else value.get('state')
                expected_revision = target.get('replacementObjectRevision') if state == 'applied' else target.get('invalidatedObjectRevision')
                expected_version = target.get('newVersion') if state == 'applied' else target.get('version')
                if (row['revision'] != expected_revision or version != expected_version or status in ('withdrawn', 'deleted', 'retracted')
                        or (kind == 'record' and value.get('creatorId') != ctx.actor['owner'])):
                    continue
                if state == 'pending_replacement' and status != 'draft':
                    continue
                if state == 'applied':
                    try:
                        if kind == 'material':
                            from . import phase10_studio
                            if 'w18Segment' in value:
                                from . import waves18_segments as segments
                                if not isinstance(value['w18Segment'], dict):
                                    continue
                                segment = segments.read(db, segments.SEG, value['w18Segment'].get('segmentId'), ctx.sid)
                                if not segment or segment['_revision'] != target.get('replacementSegmentRevision'):
                                    continue
                                phase10_studio._guard_material(ctx, dict(value, _revision=row['revision']))
                            else:
                                phase10_studio._guard_material(ctx, value)
                            phase10_studio.resolve_material_refs(ctx, value.get('refs', []))
                        else:
                            from . import waves18_records
                            waves18_records.current(ctx.sid, value['snapshot'])
                    except (Phase10Error, KeyError):
                        continue
                    replacement = {'version': version, 'status': status}
            elif kind == 'caption' and state == 'applied':
                ref = target.get('replacementRef')
                if not isinstance(ref, dict) or not result.get('sourceId') == ref.get('sourceId') or ref.get('sourceRevision') != result['revision'] or ref.get('sessionId') != ctx.sid:
                    continue
                rows = db.execute('SELECT ref FROM phase12_caption_feed WHERE session_id=? AND source_id=? AND moment_id=?', (ctx.sid, source_id, ref.get('momentId'))).fetchall()
                try:
                    if not any(json.loads(row['ref']) == ref for row in rows):
                        continue
                    ctx.resolve([ref])
                except Phase10Error:
                    continue
                replacement = {'ref': ref}
            elif kind == 'speech' and state == 'applied':
                job = db.execute("SELECT * FROM phase12_jobs WHERE session_id=? AND seq=? AND kind='speech'", (ctx.sid, target.get('replacementJobId'))).fetchone()
                if (not job or job['actor_id'] != ctx.actor['owner'] or job['role'] != ctx.actor['role']
                        or job['credential_hash'] != ctx.store.digest(getattr(ctx.handler, '_auth_token', ''))
                        or job['fingerprint'] != target.get('jobFingerprint') or job['state'] not in ('queued', 'running', 'complete')
                        or not any(x['kind'] == 'speech' and x['id'] == str(job['seq']) for x in discover(db, ctx.sid, source_id, result['revision']))):
                    continue
                try:
                    from . import phase12_jobs
                    phase12_jobs.rights(job)
                except Phase10Error:
                    continue
                replacement = {'jobId': job['seq'], 'state': job['state']}
            if state == 'applied':
                if replacement is None or not target.get('replacementFingerprint'):
                    continue
                item['replacement'] = replacement
                item['replacementReceipt'] = 'confirmed'
            else:
                item['replacementReceipt'] = 'unresolved'
            visible.append(item)
        result['affected'] = visible
        return result


def guard_target(ctx, source_id, source_revision, kind, target_id, target_version):
    """Guard real current storage; hold store.LOCK through final delivery."""
    from .http import expired
    impact._id(source_id); impact._id(target_id); impact._rev(source_revision); impact._rev(target_version)
    with ctx.lock, ctx.store.connect() as db:
        ctx.check_actor()
        src = ctx.store.get('source', source_id, ctx.sid)
        if (not src or src.get('_revision') != source_revision or src.get('status') != 'active'
                or expired(src) or (ctx.actor.get('role') != 'creator' and not src.get('audienceVisible', False))):
            raise Phase10Error('stale_context', 'Derivative source is unavailable.', 409)
        if kind == 'caption':
            rows = db.execute('SELECT ref FROM phase12_caption_feed WHERE session_id=? AND source_id=? AND moment_id=?', (ctx.sid, source_id, target_id)).fetchall()
            valid = False
            if target_version == source_revision:
                for row in rows:
                    ref = json.loads(row['ref'])
                    if not any(r.get('sourceRevision') == source_revision and r.get('sourceId') == source_id and r.get('sessionId') == ctx.sid for r in _refs(ref)):
                        continue
                    try:
                        ctx.resolve([ref])
                    except Phase10Error:
                        continue
                    valid = True
                    break
        elif kind == 'speech':
            row = db.execute('SELECT * FROM phase12_jobs WHERE session_id=? AND seq=? AND kind=?', (ctx.sid, int(target_id), 'speech')).fetchone() if target_id.isdecimal() else None
            token = getattr(ctx.handler, '_auth_token', '')
            valid = bool(row and row['actor_id'] == ctx.actor['owner'] and row['credential_hash'] == ctx.store.digest(token) and row['state'] == 'complete' and target_version == source_revision)
            if valid:
                valid = any(x['kind'] == 'speech' and x['id'] == target_id for x in discover(db, ctx.sid, source_id, source_revision))
            if valid:
                from . import phase12_jobs
                try:
                    phase12_jobs.rights(row)
                except Phase10Error:
                    valid = False
        elif kind in ('material', 'record'):
            object_kind = 'p10material' if kind == 'material' else 'w18record'
            row = db.execute('SELECT owner_id,data FROM objects WHERE kind=? AND id=? AND session_id=?', (object_kind, target_id, ctx.sid)).fetchone()
            valid = False
            if row and row['owner_id'] == ctx.actor['owner']:
                data = json.loads(row['data'])
                refs = data.get('refs', []) if kind == 'material' else data.get('snapshot', {})
                version = data.get('currentVersion') if kind == 'material' else data.get('version')
                approved = (data.get('status') in ('approved', 'published') and data.get('approvedVersion') == version) if kind == 'material' else data.get('state') == 'approved'
                valid = version == target_version and approved and any(r.get('sessionId') == ctx.sid and r.get('sourceId') == source_id and r.get('sourceRevision') == source_revision for r in _refs(refs))
                if valid:
                    try:
                        if kind == 'record':
                            from . import waves18_records
                            waves18_records.current(ctx.sid, refs)
                        else:
                            ctx.resolve(refs)
                    except Phase10Error:
                        valid = False
        else:
            valid = False
        if not valid:
            raise Phase10Error('stale_context', 'Derivative is unavailable or has changed.', 409)
        return True


def guard_speech_completion(db, sid, source_id, source_revision, job_id, fingerprint, credential_hash):
    """Fence a pending speech result inside the caller's locked transaction.

    PRIMARY calls immediately before its conditional completion update. This
    function does not execute a job or replace the worker's other rights checks.
    """
    from .http import expired
    if not db.in_transaction:
        raise ValueError('completion guard requires caller transaction')
    impact._id(sid); impact._id(source_id); impact._rev(source_revision)
    if type(job_id) is not int or job_id < 1:
        raise impact.ImpactError('invalid_request', 422)
    row = db.execute("SELECT * FROM phase12_jobs WHERE session_id=? AND seq=? AND kind IN ('speech','w20_speech')", (sid, job_id)).fetchone()
    source = db.execute("SELECT revision,data FROM objects WHERE kind='source' AND id=? AND session_id=?", (source_id, sid)).fetchone()
    if not row or not source or row['state'] != 'running' or row['fingerprint'] != fingerprint or row['credential_hash'] != credential_hash:
        raise impact.ImpactError('stale_context')
    credential = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?', (credential_hash,)).fetchone()
    value = json.loads(source['data'])
    if (not credential or credential['role'] != row['role'] or credential['session_id'] != sid
            or credential['owner_id'] != row['actor_id'] or source['revision'] != source_revision
            or value.get('status') != 'active' or expired(value)
            or (row['role'] != 'creator' and not value.get('audienceVisible', False))
            or not any(x['kind'] == 'speech' and x['id'] == str(job_id)
                       for x in discover(db, sid, source_id, source_revision))):
        raise impact.ImpactError('stale_context')
    from . import phase12_jobs
    try:
        phase12_jobs.rights(row)
    except Phase10Error:
        raise impact.ImpactError('stale_context')
    return True
