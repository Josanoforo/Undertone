"""Approved-record edition projection and creator selection operations.

The host must re-run ``finalize`` at the actual response boundary and must not
cache its returned representation. Optional metadata is supplied exclusively by
trusted, rights-aware host code; this module does not infer assets or alignment.
"""
import copy
import hashlib
import json
import math
import re
from html import escape
from urllib.parse import quote
from . import waves18_records as records
from .phase10_common import Phase10Error


def _fail(code, message, status=409):
    raise Phase10Error(code, message, status)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _read(ctx, record_id, language):
    records.key(record_id)
    if language not in ('en', 'es'):
        _fail('invalid_request', 'Choose English or Spanish.', 422)
    ctx.check_actor()
    if ctx.actor.get('sid') != ctx.sid:
        _fail('not_found', 'Record unavailable.', 404)
    record = records.fetch(ctx.sid, record_id)
    view = records.projection(ctx.sid, record, language)
    rows = ctx.resolve(view['refs']) if view['refs'] else []
    # Internal digest includes the actual current rows, never their private fields in output.
    return record, view, rows


def project_edition(ctx, record_id, language, *, released=None):
    """Return an ephemeral edition; ``released`` is a trusted host callback.

    Callback returns only already-authorized current metadata, or None. Its
    result is validated and compared again by finalize. It must enforce every
    component's rights, revision, and actor, including any media endpoint.
    """
    with ctx.lock:
        record, view, rows = _read(ctx, record_id, language)
        row_digest = _digest(rows)
        actor_digest = _digest(ctx.actor)
        supplemental = released(ctx, copy.deepcopy(record), copy.deepcopy(view)) if released else None
        extra = _supplement(supplemental, view['refs'])
        # Recheck after callback, which may have yielded to another writer.
        latest, current, current_rows = _read(ctx, record_id, language)
        if (latest['_revision'] != record['_revision'] or _digest(current) != _digest(view)
                or _digest(current_rows) != row_digest or _digest(ctx.actor) != actor_digest):
            _fail('stale_context', 'Record changed during projection.')
        snap = record['snapshot']
        tracks = []
        # A still has an exact instant, not an invented speech duration. Bind
        # the approved captions to that same current frame when it is released.
        anchor = (view['refs'][0] if len(rows) == 1 and len(view['refs']) == 1
                  and rows[0]['moment'].get('alignment', {}).get('origin') == 'capture'
                  and view['refs'][0]['startMs'] == view['refs'][0]['endMs']
                  and extra['media']['state'] == 'available' else None)
        for lang, value in snap['interpretations'].items():
            tracks.append({'kind':'approved_text', 'language':lang, 'provenance':
                           'creator_reviewed_translation' if lang in snap.get('translationBindings', {}) else 'creator_authored',
                           'role':'original' if lang == view['sourceLanguage'] else 'translation',
                           'originalLanguage':view['sourceLanguage'],
                           'cues':[{'startMs':anchor['startMs'] if anchor else None,
                                    'endMs':anchor['endMs'] if anchor else None, 'text':value,
                                    'sourceRef':copy.deepcopy(anchor),
                                    'timingProvenance':'approved_still_instant' if anchor else 'untimed_approved_text',
                                    'sourceRefs':copy.deepcopy(view['refs']), 'revision':record['version']}]})
        manifest = {'editionId':record['id'], 'revision':record['_revision'], 'recordVersion':record['version'],
                    'interval':({'startMs':view['refs'][0]['startMs'], 'endMs':view['refs'][0]['endMs']} if len(view['refs']) == 1 else None),
                    'timeBasis':'Source-relative supplied interval; a still frame has a single instant, not a playback duration.',
                    'approval':'approved', 'sourceLanguage':view['sourceLanguage'],
                    'provenance':{'format':copy.deepcopy(snap['format']),
                                  'sources':[{'ref':copy.deepcopy(row['ref']),
                                              'momentRevision':row['moment']['_revision']} for row in rows]},
                    'language':view['language'], 'fallback':view['fallback'],
                    'tracks':tracks + extra['tracks'], 'regions':extra['regions'],
                    'timedPlayback':_timed_playback(ctx, record, view, rows, extra),
                    'materials':_reviewed_materials(ctx, record),
                    'descriptionAudio':_description(ctx, record, view, extra),
                    'corrections':extra['corrections'], 'decision':copy.deepcopy(view['decision']),
                    'recordHistory':[{'version':h['version'], 'replacedByVersion':record['version']}
                                     for h in record.get('history', []) if h.get('state') == 'approved'],
                    'media':extra['media'], 'returnToLive':{'sessionId':ctx.sid}}
        return {'manifest':manifest, '_binding':{'recordId':record_id, 'language':language,
                 'recordRevision':record['_revision'], 'viewDigest':_digest(view), 'extraDigest':_digest(extra),
                 'actorDigest':actor_digest, 'sourceDigest':row_digest}}


def _timed_playback(ctx, record, view, rows, extra):
    """Bind one complete, approved utterance to its retained original clock.

    Timing comes exclusively from an exact, rebuilt ASR feed interval. An
    approved translation of that one utterance inherits the whole interval,
    never word timings inferred from its text. Edited summaries and multi-ref
    records remain untimed until an explicit alignment contract exists.
    """
    from .waves25_listening_preferences import timed_original_audio
    unavailable = {'state': 'unavailable'}
    if len(rows) != 1 or len(view['refs']) != 1:
        return unavailable
    row = rows[0]
    ref, source, moment = row['ref'], row['source'], row['moment']
    if (not source.get('audienceVisible') or source.get('language') != view['sourceLanguage']
            or moment.get('alignment', {}).get('origin') != 'asr'):
        return unavailable
    candidates = [c for t in extra['tracks'] if t['kind'] == 'original'
                  and t['language'] == view['sourceLanguage'] for c in t['cues']
                  if c['sourceRef'] == ref and c['startMs'] == ref['startMs']
                  and c['endMs'] == ref['endMs']]
    if len(candidates) != 1:
        return unavailable
    cue = candidates[0]
    offset = source.get('offsetSeconds')
    digest = source.get('audioDigest')
    if (type(offset) not in (int, float) or not math.isfinite(offset) or offset < 0
            or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)):
        return unavailable
    origin = round(offset * 1000)
    if not 0 <= origin <= ref['startMs'] < ref['endMs']:
        return unavailable
    if not timed_original_audio(ctx, {'ref': ref},
                                {'bindingId': ref['sourceId'], 'offsetMs': ref['endMs'] - origin}):
        return unavailable
    tracks = [{'kind': 'original', 'language': view['sourceLanguage'],
               'provenance': 'received_asr', 'cues': [copy.deepcopy(cue)]}]
    snap = record['snapshot']
    # Approval covers this exact ref and this complete original utterance.
    if snap['interpretations'].get(view['sourceLanguage']) == cue['text']:
        for lang, text in snap['interpretations'].items():
            if lang == view['sourceLanguage']:
                continue
            translated = dict(copy.deepcopy(cue), text=text, revision=record['version'])
            tracks.append({'kind': 'translation', 'language': lang,
                           'provenance': 'creator_reviewed_translation' if lang in snap.get('translationBindings', {}) else 'creator_authored',
                           'recordVersion': record['version'], 'cues': [translated]})
    return {'state': 'available', 'binding': {'sourceRef': copy.deepcopy(ref),
            'audioSha256': digest, 'originMs': origin},
            'authorizedRef': '/api/sessions/{}/p12/sources/{}/original-audio'.format(
                quote(ctx.sid, safe=''), quote(ref['sourceId'], safe='')),
            'alignment': 'whole_verified_source_interval', 'tracks': tracks}


def _reviewed_materials(ctx, record):
    """Return only currently approved material explicitly bound to this record."""
    from . import phase10_studio
    out = []
    for material in ctx.store.all('p10material', ctx.sid):
        binding = material.get('w18Record')
        if not isinstance(binding, dict) or binding.get('sessionId') != ctx.sid or binding.get('recordId') != record['id'] or binding.get('version') != record['version']:
            continue
        if material.get('approvedVersion') != material.get('currentVersion') or material.get('status') not in ('approved', 'published'):
            continue
        if ctx.actor.get('role') != 'creator' and material.get('status') != 'published':
            continue
        try:
            state, rows = phase10_studio._state(ctx, material)
            if state != 'current' or not all(row['source'].get('audienceVisible') for row in rows):
                continue
            records.text(material['title'], 200)
            records.text(material['body'], 12000)
        except (Phase10Error, KeyError, TypeError):
            continue
        out.append({'id':material['id'], 'revision':material['_revision'],
                    'version':material['currentVersion'], 'title':material['title'],
                    'body':material['body'], 'refs':copy.deepcopy(material['refs'])})
    return out


def _description_creator(ctx):
    ctx.check_actor()
    with ctx.store.connect() as db:
        owner = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
    if ctx.actor.get('sid') != ctx.sid or ctx.actor.get('role') != 'creator' or not owner or owner['owner_id'] != ctx.actor.get('owner'):
        _fail('not_found', 'Selection unavailable.', 404)


def _description_receipt(ctx, edition_id, request_id):
    records.key(edition_id); records.key(request_id)
    _description_creator(ctx)
    oid = _digest([ctx.sid, ctx.actor['owner'], request_id])
    row = ctx.store.get('w22descriptionreceipt', oid, ctx.sid)
    if not row or row.get('editionId') != edition_id or row.get('owner') != ctx.actor['owner']:
        _fail('not_found', 'Operation unavailable.', 404)
    return row


def description_receipt(ctx, edition_id, request_id):
    with ctx.lock:
        row = _description_receipt(ctx, edition_id, request_id)
        return {'operation': {'requestId': request_id, 'action': row['action'], 'state': 'committed'}}


def _description_commit(ctx, edition_id, action, request_id, fingerprint, value=None):
    """Atomically change the selection and persist a content-free receipt."""
    from . import store
    oid = _digest([ctx.sid, edition_id])
    rid = _digest([ctx.sid, ctx.actor['owner'], request_id])
    with ctx.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute("SELECT data FROM objects WHERE kind='w22descriptionreceipt' AND id=? AND session_id=?", (rid, ctx.sid)).fetchone()
        if old:
            receipt = json.loads(old['data'])
            if receipt.get('fingerprint') != fingerprint:
                _fail('request_conflict', 'Request ID already used.', 409)
        else:
            selected = db.execute("SELECT data,revision FROM objects WHERE kind='w22description' AND id=? AND session_id=?", (oid, ctx.sid)).fetchone()
            if action == 'select':
                data = dict(value, id=oid)
                if selected:
                    previous = json.loads(selected['data'])
                    if previous != data:
                        db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w22description' AND id=? AND session_id=?", (json.dumps(data, ensure_ascii=False), oid, ctx.sid))
                else:
                    db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w22description',?,?,?,1,?,?)", (oid, ctx.sid, ctx.actor['owner'], json.dumps(data, ensure_ascii=False), store.now()))
            elif selected:
                data = json.loads(selected['data'])
                if data.get('active') is not False:
                    data['active'] = False
                    db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w22description' AND id=? AND session_id=?", (json.dumps(data, ensure_ascii=False), oid, ctx.sid))
            receipt = {'id':rid, 'editionId':edition_id, 'owner':ctx.actor['owner'], 'action':action, 'fingerprint':fingerprint}
            db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w22descriptionreceipt',?,?,?,1,?,?)", (rid, ctx.sid, ctx.actor['owner'], json.dumps(receipt), store.now()))
        db.commit()
    return {'operation': {'requestId':request_id, 'action':action, 'state':'committed'}}


def select_description(ctx, edition_id, body, request_id=None):
    """Persist the creator's exact approved narration and grounded region selection."""
    if not isinstance(body, dict) or set(body) != {'recordId', 'recordVersion', 'language', 'sourceRef', 'regionId'}:
        _fail('invalid_request', 'Select an approved description and region.', 422)
    records.key(body['recordId']); records.key(body['regionId'])
    if type(body['recordVersion']) is not int or body['recordVersion'] < 1 or body['language'] not in ('en', 'es'):
        _fail('invalid_request', 'Select an approved description and language.', 422)
    with ctx.lock:
        _description_creator(ctx)
        if request_id is not None:
            records.key(edition_id); records.key(request_id)
            fingerprint = _digest(['select', edition_id, body])
            existing = ctx.store.get('w22descriptionreceipt', _digest([ctx.sid, ctx.actor['owner'], request_id]), ctx.sid)
            if existing:
                if existing.get('fingerprint') != fingerprint: _fail('request_conflict', 'Request ID already used.', 409)
                return description_receipt(ctx, edition_id, request_id)
        edition, view, _ = _read(ctx, edition_id, body['language'])
        narration, narration_view, _ = _read(ctx, body['recordId'], body['language'])
        if (narration['version'] != body['recordVersion'] or narration_view['language'] != body['language']
                or body['sourceRef'] not in view['refs'] or body['sourceRef'] not in narration_view['refs']):
            _fail('stale_context', 'Description source changed.')
        proof = _description_proof(ctx, ctx.actor['owner'], body['sourceRef'], body['regionId'], edition_id=edition_id)
        if not proof:
            _fail('stale_context', 'Selected region unavailable.')
        oid = _digest([ctx.sid, edition_id])
        value = {'editionId': edition_id, 'editionVersion': edition['version'], 'editionRevision': edition['_revision'],
                 'recordId': narration['id'], 'recordVersion': narration['version'], 'recordRevision': narration['_revision'],
                 'language': body['language'], 'sourceRef': copy.deepcopy(body['sourceRef']), 'regionId': body['regionId'],
                 'creatorOwner': ctx.actor['owner'], 'visualRequestId': proof[0], 'visualDigest': proof[1], 'active': True}
        if request_id is not None:
            return _description_commit(ctx, edition_id, 'select', request_id, fingerprint, value)
        old = ctx.store.get('w22description', oid, ctx.sid)
        if old:
            if {k:v for k,v in old.items() if k not in ('id', '_revision')} != value:
                ctx.store.save('w22description', dict(value, id=oid, _revision=old['_revision']))
        else:
            ctx.store.put('w22description', ctx.sid, value, ctx.actor['owner'], oid)
        return {'selection': value}


def revoke_description(ctx, edition_id, request_id=None):
    records.key(edition_id)
    with ctx.lock:
        _description_creator(ctx)
        if request_id is not None:
            records.key(request_id)
            return _description_commit(ctx, edition_id, 'withdraw', request_id, _digest(['withdraw', edition_id]))
        oid = _digest([ctx.sid, edition_id])
        value = ctx.store.get('w22description', oid, ctx.sid)
        if value and value.get('active') is not False:
            value['active'] = False
            ctx.store.save('w22description', value)
        return {'revoked': True}


def _description_proof(ctx, owner, ref, region_id, request_id=None, digest=None, edition_id=None):
    """Recheck the creator's selected receipt using the requesting actor's rights."""
    from . import waves21_visual_runtime as visual
    with ctx.store.connect() as db:
        rows = db.execute("SELECT request_id,result FROM phase10_receipts WHERE session_id=? AND actor_id=? AND operation=? AND state='complete'", (ctx.sid, owner, visual.OPERATION)).fetchall()
    for row in rows:
        if request_id is not None and row['request_id'] != request_id:
            continue
        try:
            result = json.loads(row['result'])
            if digest is not None and _digest(result) != digest:
                continue
            safe = visual._project(ctx, result)
            if safe['frame']['ref'] == ref and any(r['regionId'] == region_id for r in safe['regions']):
                return row['request_id'], _digest(result)
        except (Phase10Error, ValueError, KeyError, TypeError):
            continue
    if edition_id:
        record, view, _ = _read(ctx, edition_id, 'en')
        selected = _approved_regions(ctx, record, view)
        if (selected and selected['creatorOwner'] == owner and selected['sourceRef'] == ref
                and any(r['regionId'] == region_id for r in selected['regions'])):
            proof_id, proof_digest = 'edition-regions:' + edition_id, _digest(selected)
            if (request_id is None or request_id == proof_id) and (digest is None or digest == proof_digest):
                return proof_id, proof_digest
    return None


def _description(ctx, edition, view, extra):
    missing = {'state':'missing', 'authorizedRef':None}
    value = ctx.store.get('w22description', _digest([ctx.sid, edition['id']]), ctx.sid)
    if not value or value.get('active') is not True or value.get('editionVersion') != edition['version'] or value.get('editionRevision') != edition['_revision']:
        return missing
    ref = value.get('sourceRef')
    with ctx.store.connect() as db:
        owner = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
    if (not owner or owner['owner_id'] != value.get('creatorOwner') or ref not in view['refs']
            or not isinstance(value.get('visualRequestId'), str) or not isinstance(value.get('visualDigest'), str)
            or not _description_proof(ctx, owner['owner_id'], ref, value.get('regionId'), value['visualRequestId'], value['visualDigest'], edition['id'])):
        return missing
    try:
        record, narration, _ = _read(ctx, value['recordId'], value['language'])
        if (record['version'] != value['recordVersion'] or record['_revision'] != value['recordRevision']
                or narration['language'] != value['language'] or ref not in narration['refs']):
            return missing
    except (Phase10Error, KeyError, TypeError):
        return missing
    return {'state':'available', 'authorizedRef':None, 'delivery':'on_demand_approved_record',
            'recordId':record['id'], 'recordVersion':record['version'], 'recordRevision':record['_revision'],
            'language':narration['language'], 'text':narration['interpretation'], 'provenance':narration['provenance'],
            'sourceRef':copy.deepcopy(ref), 'regionId':value['regionId'], 'selectionRevision':value['_revision']}


def guard_description(ctx, edition_id, language, expected):
    """Reauthorize an exact on-demand selection at admission and delivery."""
    with ctx.lock:
        actual = project_edition(ctx, edition_id, language, released=released_metadata)['manifest']['descriptionAudio']
        if actual.get('state') != 'available' or actual != expected:
            _fail('stale_context', 'Description changed or is unavailable.')
        return actual


def phase12_feed_metadata(ctx, record, view):
    """Project exact approved refs retained in the current Phase 12 feed.

    This is received ASR feed metadata, not Wave 21 stream or media. A missing
    or unverifiable feed row supplies no cue; it never manufactures alignment.
    """
    from . import waves17_listening, phase10_timeline
    grouped = {}
    ctx.check_actor()
    for row in (ctx.resolve(view['refs']) if view['refs'] else []):
        ref, source, moment = row['ref'], row['source'], row['moment']
        if not source.get('audienceVisible') or source.get('language') not in ('en', 'es'):
            continue
        seq, run = waves17_listening.sequence(ctx.sid, ref)
        point = waves17_listening.feed_point(ctx.handler, ctx.sid, ctx.actor, seq)
        if not point or point['ref'] != ref or point['captureRunId'] != run:
            continue
        try:
            rebuilt = phase10_timeline.build_moments(source, [{'startMs':ref['startMs'],
                'endMs':ref['endMs'], 'kind':moment.get('kind')}])[0]
            if (rebuilt['ref'] != ref or rebuilt['alignment'] != moment.get('alignment')
                    or rebuilt['text'] != moment.get('text')):
                continue
            text = records.text(moment['text'], 4000)
        except (Phase10Error, KeyError, TypeError, ValueError):
            continue
        grouped.setdefault(source['language'], []).append({'startMs':ref['startMs'],
            'endMs':ref['endMs'], 'text':text, 'sourceRef':copy.deepcopy(ref),
            'revision':moment['_revision']})
    return {'tracks':[{'kind':'original', 'language':lang, 'cues':cues}
                      for lang, cues in sorted(grouped.items())], 'regions':[],
            'corrections':[], 'media':{'state':'missing', 'authorizedRef':None}}


def _correction_history(ctx, refs):
    """Follow the actor's persisted correction chain from the current fence.

    Historical intents are never independently public: only the creator who
    owns them can see revision pairs, anchored to an authorized current source.
    No derivative identities, counts, or historical source text are projected.
    """
    from . import waves21_correction_impact as impact, waves21_impact_runtime
    if ctx.actor.get('role') != 'creator':
        return []
    out = []
    with ctx.store.connect() as db:
        for ref in refs:
            fence = impact._get(db, 'w21sourcefence',
                                impact._key(ctx.sid, ref['sourceId']), ctx.sid)
            if not fence or fence.get('revision') != ref['sourceRevision']:
                continue
            current = waves21_impact_runtime.project_change(ctx, fence['intentId'])
            if current.get('sourceId') != ref['sourceId'] or current.get('revision') != ref['sourceRevision']:
                _fail('invalid_metadata', 'Correction metadata unavailable.')
            rows = db.execute("SELECT id,owner_id,data FROM objects WHERE kind='w21sourcechange' AND session_id=?", (ctx.sid,)).fetchall()
            by_revision = {}
            for row in rows:
                if row['owner_id'] != ctx.actor.get('owner'):
                    continue
                value = json.loads(row['data'])
                if value.get('sourceId') != ref['sourceId']:
                    continue
                revision, previous = value.get('revision'), value.get('previousRevision')
                if type(revision) is not int or type(previous) is not int or previous != revision - 1:
                    _fail('invalid_metadata', 'Correction metadata unavailable.')
                if revision in by_revision:
                    _fail('invalid_metadata', 'Correction metadata unavailable.')
                by_revision[revision] = (row['id'], previous)
            revision = ref['sourceRevision']
            if by_revision.get(revision, (None,))[0] != fence['intentId']:
                _fail('invalid_metadata', 'Correction metadata unavailable.')
            while revision in by_revision:
                previous = by_revision[revision][1]
                out.append({'sourceRef': copy.deepcopy(ref), 'revision': revision,
                            'correctsRevision': previous, 'recordedAt': None, 'text': None})
                revision = previous
    return out


def released_metadata(ctx, record, view):
    """Compose current released readers without promoting private speech to public."""
    from . import waves21_speech_runtime, waves21_visual_runtime
    speech = waves21_speech_runtime.edition_metadata(ctx, view)
    if not isinstance(speech, dict) or speech.get('scope') != 'private':
        _fail('invalid_metadata', 'Speech metadata unavailable.')
    visual = waves21_visual_runtime.edition_metadata(ctx, view)
    if (not isinstance(visual, dict) or visual.get('recordId') != record['id']
            or visual.get('recordVersion') != record['version']
            or not isinstance(visual.get('visual'), list)):
        _fail('invalid_metadata', 'Visual metadata unavailable.')
    result = phase12_feed_metadata(ctx, record, view)
    result['corrections'] = _correction_history(ctx, view['refs'])
    for entry in visual['visual']:
        frame = entry.get('frame') if isinstance(entry, dict) else None
        ref = frame.get('ref') if isinstance(frame, dict) else None
        if ref not in view['refs']:
            continue
        if result['media']['state'] == 'missing':
            # The reader has verified the persisted receipt and frame digest.
            # Opening the reference independently repeats all authorization.
            asset_id = _digest({'session': ctx.sid, 'record': record['id'],
                                'recordRevision': record['_revision'], 'ref': ref,
                                'sha256': entry.get('imageSha256')})
            try:
                read_frame_asset(ctx, record['id'], view['language'], asset_id)
            except Phase10Error:
                pass
            else:
                path = '/api/sessions/{}/w22/edition/{}/{}/assets/{}'.format(
                    quote(ctx.sid, safe=''), quote(record['id'], safe=''), view['language'], asset_id)
                result['media'] = {'state': 'available', 'authorizedRef': path}
        for region in entry.get('regions', []):
            result['regions'].append({'regionId': region['regionId'],
                'frameId': ref['momentId'], 'sourceRef': copy.deepcopy(ref),
                'box': copy.deepcopy(region['box']), 'description': None})
    # An indexed speech interval may already have a trusted derived frame.
    # Consume that released reader instead of pretending it is a capture instant
    # or requiring a second source/reference for the same authorized material.
    if result['media']['state'] == 'missing' and len(view['refs']) == 1:
        asset = _indexed_frame(ctx, record, view['refs'][0])
        if asset:
            result['media'] = {'state': 'available', 'authorizedRef':
                '/api/sessions/{}/w22/edition/{}/{}/assets/{}'.format(
                    quote(ctx.sid, safe=''), quote(record['id'], safe=''),
                    view['language'], asset['id'])}
    selected = _approved_regions(ctx, record, view)
    if selected:
        for region in selected['regions']:
            result['regions'].append({'regionId': region['regionId'],
                'frameId': selected['sourceRef']['momentId'],
                'sourceRef': copy.deepcopy(selected['sourceRef']),
                'box': copy.deepcopy(region['box']),
                'description': 'Creator-approved authored region: ' + region['description']})
    return result


def _approved_regions(ctx, record, view):
    """Current creator-reviewed geometry for an already registered interval image."""
    selected = ctx.store.get('w22regions', _digest([ctx.sid, record['id']]), ctx.sid)
    if (not selected or selected.get('recordVersion') != record['version']
            or selected.get('recordRevision') != record['_revision']
            or view['refs'] != [selected.get('sourceRef')]):
        return None
    with ctx.store.connect() as db:
        owner = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?", (ctx.sid, ctx.sid)).fetchone()
    if not owner or owner['owner_id'] != selected.get('creatorOwner'):
        return None
    asset = _indexed_frame(ctx, record, selected['sourceRef'])
    if not asset or asset['id'] != selected.get('frameAssetId'):
        return None
    return selected


def region_receipt(ctx, edition_id, request_id):
    _description_creator(ctx)
    records.key(edition_id); records.key(request_id)
    row = ctx.store.get('w22regionsreceipt', _digest([ctx.sid, ctx.actor['owner'], request_id]), ctx.sid)
    if not row or row.get('editionId') != edition_id:
        _fail('not_found', 'Region approval unavailable.', 404)
    return {'operation': {'requestId': request_id, 'action': 'approve_regions', 'state': 'committed'}}


def approve_regions(ctx, edition_id, body):
    """Explicitly approve authored boxes; never create a vision/OCR receipt."""
    from .waves21_visual_grounding import rectangle
    fields = {'requestId', 'recordVersion', 'recordRevision', 'sourceRef', 'frameAssetId', 'regions', 'approve'}
    if not isinstance(body, dict) or set(body) != fields or body['approve'] is not True:
        _fail('invalid_request', 'Explicit region approval is required.', 422)
    records.key(edition_id); records.key(body['requestId'])
    if (type(body['recordVersion']) is not int or type(body['recordRevision']) is not int
            or not isinstance(body['regions'], list) or not 1 <= len(body['regions']) <= 8):
        _fail('invalid_request', 'Select an exact edition and one to eight regions.', 422)
    regions, ids = [], set()
    for region in body['regions']:
        if not isinstance(region, dict) or set(region) != {'regionId', 'box', 'description'}:
            _fail('invalid_request', 'Select labelled authored regions.', 422)
        records.key(region['regionId']); records.text(region['description'], 1000)
        if region['regionId'] in ids:
            _fail('invalid_request', 'Select each region once.', 422)
        ids.add(region['regionId'])
        regions.append(dict(region, box=rectangle(region['box'])))
    with ctx.lock:
        _description_creator(ctx)
        fingerprint = _digest([edition_id, body])
        rid = _digest([ctx.sid, ctx.actor['owner'], body['requestId']])
        old = ctx.store.get('w22regionsreceipt', rid, ctx.sid)
        if old:
            if old.get('fingerprint') != fingerprint:
                _fail('request_conflict', 'Request ID already used.', 409)
            return region_receipt(ctx, edition_id, body['requestId'])
        record, view, _ = _read(ctx, edition_id, 'en')
        if (record['version'] != body['recordVersion'] or record['_revision'] != body['recordRevision']
                or view['refs'] != [body['sourceRef']]):
            _fail('stale_context', 'Edition changed before region approval.')
        asset = _indexed_frame(ctx, record, body['sourceRef'])
        if not asset or asset['id'] != body['frameAssetId']:
            _fail('stale_context', 'The selected source image changed.')
        oid = _digest([ctx.sid, edition_id])
        value = {'id': oid, 'editionId': edition_id, 'recordVersion': record['version'],
                 'recordRevision': record['_revision'], 'sourceRef': copy.deepcopy(body['sourceRef']),
                 'creatorOwner': ctx.actor['owner'], 'frameAssetId': asset['id'], 'regions': regions}
        receipt = {'id': rid, 'editionId': edition_id, 'fingerprint': fingerprint}
        with ctx.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute("SELECT 1 FROM objects WHERE kind='w22regions' AND id=? AND session_id=?", (oid, ctx.sid)).fetchone()
            if existing:
                db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w22regions' AND id=? AND session_id=?", (json.dumps(value), oid, ctx.sid))
            else:
                db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w22regions',?,?,?,1,?,?)", (oid, ctx.sid, ctx.actor['owner'], json.dumps(value), ctx.store.now()))
            db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w22regionsreceipt',?,?,?,1,?,?)", (rid, ctx.sid, ctx.actor['owner'], json.dumps(receipt), ctx.store.now()))
            db.commit()
        return region_receipt(ctx, edition_id, body['requestId'])


def _indexed_frame(ctx, record, ref):
    """Read a previously registered derived frame under the exact current ref.

    Registration belongs to the trusted moment-media owner. No client URL,
    bytes, timing or claimed source relationship is admitted by this reader.
    """
    from . import waves23_moment_media as media
    import base64
    try:
        meta = media.inspect(ctx, ref)
        if meta['provenance'] != 'derived_frame' or meta['mimeType'] not in ('image/png', 'image/jpeg'):
            return None
        current, raw = media.bytes_for(ctx, ref, meta['assetId'])
        if current != meta:
            return None
        key = _digest({'session': ctx.sid, 'record': record['id'],
                       'recordRevision': record['_revision'], 'ref': ref,
                       'momentAsset': meta['assetId'], 'sha256': meta['digest']})
        return {'id': key, 'mimeType': meta['mimeType'],
                'data': base64.b64encode(raw).decode('ascii')}
    except Phase10Error:
        return None


def read_frame_asset(ctx, record_id, language, asset_id):
    """Read only an actual frame referenced by the current approved edition.

    The identifier is a lookup key, never an authorization capability. The
    record, credential, visual receipt and frame bytes are revalidated on
    every read and again by the host at the response boundary.
    """
    from . import waves21_visual_runtime, phase10_timeline
    import base64
    if not isinstance(asset_id, str) or not re.fullmatch(r'[0-9a-f]{64}', asset_id):
        _fail('not_found', 'Asset unavailable.', 404)
    with ctx.lock:
        record, view, _ = _read(ctx, record_id, language)
        visual = waves21_visual_runtime.edition_metadata(ctx, view)
        if visual.get('recordId') != record['id'] or visual.get('recordVersion') != record['version']:
            _fail('stale_context', 'Asset unavailable.')
        for entry in visual.get('visual', []):
            ref = entry.get('frame', {}).get('ref')
            if ref not in view['refs']:
                continue
            row = ctx.resolve([ref])[0]
            image = row['source'].get('image')
            try:
                rebuilt = phase10_timeline.frame_moment(row['source'])
                raw = base64.b64decode(image['data'], validate=True)
                digest = hashlib.sha256(raw).hexdigest()
            except (Phase10Error, KeyError, TypeError, ValueError):
                continue
            if rebuilt['ref'] != ref or digest != entry.get('imageSha256'):
                continue
            key = _digest({'session': ctx.sid, 'record': record['id'],
                           'recordRevision': record['_revision'], 'ref': ref, 'sha256': digest})
            if key == asset_id:
                return {'id': key, 'mimeType': image['mimeType'], 'data': image['data']}
        if len(view['refs']) == 1:
            asset = _indexed_frame(ctx, record, view['refs'][0])
            if asset and asset['id'] == asset_id:
                return asset
        _fail('not_found', 'Asset unavailable.', 404)


def _supplement(value, refs):
    empty = {'tracks':[], 'regions':[], 'corrections':[], 'media':{'state':'missing', 'authorizedRef':None}}
    if value is None:
        return empty
    if not isinstance(value, dict) or set(value) != set(empty):
        _fail('invalid_metadata', 'Edition metadata unavailable.')
    # Prevent arbitrary fields, private notes or credentials reaching the client.
    out = copy.deepcopy(empty)
    tracks = value['tracks']
    if not isinstance(tracks, list) or len(tracks) > 8:
        _fail('invalid_metadata', 'Caption metadata unavailable.')
    for track in tracks:
        if not isinstance(track, dict) or set(track) != {'kind','language','cues'} or track['kind'] not in ('original','translation') or track['language'] not in ('en','es') or not isinstance(track['cues'], list) or len(track['cues']) > 500:
            _fail('invalid_metadata', 'Caption metadata unavailable.')
        cues=[]
        for c in track['cues']:
            if not isinstance(c, dict) or set(c) != {'startMs','endMs','text','sourceRef','revision'} or c['sourceRef'] not in refs or type(c['revision']) is not int or c['revision'] < 1:
                _fail('invalid_metadata', 'Caption metadata unavailable.')
            a,b=c['startMs'],c['endMs']
            if not ((a is None and b is None) or (type(a) is int and type(b) is int and 0 <= a < b <= 864000000)):
                _fail('invalid_metadata', 'Caption timing unavailable.')
            # A cue cannot claim event time outside its exact approved source interval.
            if a is not None and not (c['sourceRef']['startMs'] <= a < b <= c['sourceRef']['endMs']):
                _fail('invalid_metadata', 'Caption timing is outside the approved source.')
            records.text(c['text'], 4000); cues.append(c)
        out['tracks'].append({'kind':track['kind'],'language':track['language'],'cues':cues})
    from .waves21_visual_grounding import rectangle
    if not isinstance(value['regions'], list) or len(value['regions']) > 20:
        _fail('invalid_metadata', 'Region metadata unavailable.')
    for r in value['regions']:
        if not isinstance(r,dict) or set(r) != {'regionId','frameId','sourceRef','box','description'} or r['sourceRef'] not in refs or r['frameId'] != r['sourceRef']['momentId']:
            _fail('invalid_metadata', 'Region metadata unavailable.')
        records.key(r['regionId']); rectangle(r['box'])
        if r['description'] is not None: records.text(r['description'], 4000)
        out['regions'].append(r)
    if not isinstance(value['corrections'],list) or len(value['corrections'])>100:
        _fail('invalid_metadata', 'Correction metadata unavailable.')
    for c in value['corrections']:
        if not isinstance(c,dict) or set(c)!={'sourceRef','revision','correctsRevision','recordedAt','text'} or c['sourceRef'] not in refs or type(c['revision']) is not int or type(c['correctsRevision']) is not int or not 0 < c['correctsRevision'] < c['revision']:
            _fail('invalid_metadata', 'Correction metadata unavailable.')
        if c['recordedAt'] is not None: records.text(c['recordedAt'],64)
        if c['text'] is not None: records.text(c['text'],4000)
        out['corrections'].append(c)
    media=value['media']
    if not isinstance(media,dict) or set(media)!={'state','authorizedRef'} or media['state'] not in ('available','missing','revoked'):
        _fail('invalid_metadata', 'Media metadata unavailable.')
    # A same-origin, opaque host route only; never a guessed storage path or URL token.
    ref=media['authorizedRef']
    if media['state']=='available':
        if not isinstance(ref,str) or not re.fullmatch(r'/api/sessions/[A-Za-z0-9._%~-]+/w22/edition/[A-Za-z0-9._%~-]+/(?:en|es)/assets/[0-9a-f]{64}',ref):
            _fail('invalid_metadata', 'Media reference unavailable.')
    elif ref is not None:
        _fail('invalid_metadata', 'Media reference unavailable.')
    out['media']=media
    return out


def finalize(ctx, prepared, *, released=None):
    """Rebuild and compare at response boundary, rejecting late changes."""
    binding=prepared.get('_binding') if isinstance(prepared,dict) else None
    if not isinstance(binding,dict): _fail('stale_context','Edition unavailable.')
    fresh=project_edition(ctx,binding['recordId'],binding['language'],released=released)
    if fresh['_binding'] != binding or fresh['manifest'] != prepared.get('manifest'):
        _fail('stale_context','Edition changed before delivery.')
    return fresh['manifest']


def render_text(manifest):
    return '\n\n'.join(c['text'] for t in manifest['tracks'] if t['kind']=='approved_text' and t['language']==manifest['language'] for c in t['cues'])


def render_vtt(manifest, language):
    def timestamp(ms):
        hours, ms = divmod(ms, 3600000); minutes, ms = divmod(ms, 60000); seconds, ms = divmod(ms, 1000)
        return f'{hours:02}:{minutes:02}:{seconds:02}.{ms:03}'
    cues=[c for t in manifest['tracks'] if t['kind'] in ('original','translation') and t['language']==language for c in t['cues'] if c['startMs'] is not None]
    lines=['WEBVTT','']
    for cue in cues:
        lines.extend([timestamp(cue['startMs'])+' --> '+timestamp(cue['endMs']), escape(cue['text']).replace('\r',' ').replace('\n',' '), ''])
    return '\n'.join(lines)
