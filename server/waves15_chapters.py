"""Creator-authored source chapters and authorized moment search."""
import hashlib
import json
import re
from urllib.parse import parse_qs, urlparse
from . import store, phase10_timeline
from .phase10_common import Context, Phase10Error


def invalid(message):
    raise Phase10Error('invalid_request', message, 422)


def valid_key(key):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', key):
        invalid('Enter a valid idempotency key.')


def project_receipt(context, sid, receipt):
    if not receipt:
        return {'state': 'unknown'}
    chapter = store.get('w15chapter', receipt['chapter_id'], sid)
    eligible = False
    if chapter and chapter.get('status') == 'active':
        try:
            rows = context.resolve(chapter['refs'])
            eligible = all(row['source'].get('audienceVisible') for row in rows)
        except Phase10Error:
            pass
    return {'state': 'committed', 'kind': receipt['operation'], 'chapterId': receipt['chapter_id'],
            'committedRevision': receipt['committed_revision'],
            'currentRevision': chapter['_revision'] if chapter else None, 'eligible': eligible}


def handle(handler, sid, actor, method, parts):
    with store.LOCK:
        context = Context(handler, sid, actor)
        context.check_actor()
        if len(parts) == 2 and parts[0] == 'operations' and method == 'GET':
            if actor['role'] != 'creator':
                raise Phase10Error('forbidden', 'Only the original creator can read this receipt.', 403)
            key = parts[1]
            valid_key(key)
            with store.connect() as db:
                receipt = db.execute('SELECT * FROM w15_chapter_receipts WHERE session_id=? AND actor_id=? AND request_key=?', (sid, actor['owner'], key)).fetchone()
            return 200, {'operation': project_receipt(context, sid, receipt)}
        if (parts == ['chapters'] and method == 'POST') or (len(parts) == 2 and parts[0] == 'chapters' and method == 'PATCH'):
            if actor['role'] != 'creator':
                raise Phase10Error('forbidden', 'Only the creator can change chapters.', 403)
            creating = method == 'POST'
            body = handler.body()
            required = {'title', 'refs', 'idempotencyKey'} if creating else {'title', 'refs', 'revision'}
            if not isinstance(body, dict) or (set(body) != required and (creating or set(body) != required | {'idempotencyKey'})):
                invalid('Title, moment references, revision and a recovery key are required as applicable.')
            if not isinstance(body['title'], str) or not 1 <= len(body['title'].strip()) <= 160:
                invalid('Enter a chapter title.')
            if not creating and type(body['revision']) is not int:
                invalid('Enter a chapter revision.')
            key = body.get('idempotencyKey')
            if 'idempotencyKey' in body: valid_key(key)
            operation = 'create' if creating else 'patch'
            # Preserve fingerprints of receipts produced by the previous create implementation.
            payload = body if creating else {'operation': operation, 'chapterId': parts[1], 'body': body}
            fp = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            old_replay = False
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                old = db.execute('SELECT * FROM w15_chapter_receipts WHERE session_id=? AND actor_id=? AND request_key=?', (sid, actor['owner'], key)).fetchone() if key else None
                if old:
                    old_replay = True
                    if old['fingerprint'] != fp or old['operation'] != operation:
                        raise Phase10Error('request_conflict', 'This request key is bound to another operation.', 409)
                    db.commit()
                else:
                    rows = context.resolve(body['refs'])
                    if not all(row['source'].get('audienceVisible') for row in rows):
                        raise Phase10Error('stale_context', 'A selected moment is unavailable.', 409)
                    if creating:
                        chapter_id = store.ident(); revision = 1
                        value = {'id': chapter_id, 'title': body['title'].strip(), 'refs': body['refs'], 'status': 'active'}
                        db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,?,?,?)', ('w15chapter', chapter_id, sid, actor['owner'], revision, json.dumps(value, ensure_ascii=False), store.now()))
                    else:
                        chapter_id = parts[1]
                        row = db.execute("SELECT data,revision FROM objects WHERE kind='w15chapter' AND id=? AND session_id=?", (chapter_id, sid)).fetchone()
                        if not row or json.loads(row['data']).get('status') != 'active':
                            raise Phase10Error('not_found', 'Chapter unavailable.', 404)
                        if row['revision'] != body['revision']:
                            raise Phase10Error('version_conflict', 'The chapter changed.', 409)
                        value = json.loads(row['data']); value.update(title=body['title'].strip(), refs=body['refs'])
                        revision = row['revision'] + 1
                        db.execute("UPDATE objects SET data=?,revision=? WHERE kind='w15chapter' AND id=? AND session_id=? AND revision=?", (json.dumps(value, ensure_ascii=False), revision, chapter_id, sid, body['revision']))
                    if key:
                        db.execute('INSERT INTO w15_chapter_receipts(session_id,actor_id,request_key,fingerprint,chapter_id,operation,committed_revision) VALUES(?,?,?,?,?,?,?)', (sid, actor['owner'], key, fp, chapter_id, operation, revision))
                    db.commit()
                    old = db.execute('SELECT * FROM w15_chapter_receipts WHERE session_id=? AND actor_id=? AND request_key=?', (sid, actor['owner'], key)).fetchone() if key else None
            projection = project_receipt(context, sid, old) if old else {'state': 'committed', 'chapterId': chapter_id, 'currentRevision': revision, 'eligible': True}
            result = {'operation': projection}
            if projection.get('eligible'):
                chapter = store.get('w15chapter', projection['chapterId'], sid)
                handler._p10_refs = chapter['refs']
                result['chapter'] = chapter
            return (201 if creating and not old_replay else 200), result
        if parts == ['chapters'] and method == 'GET':
            items, refs = [], []
            for chapter in store.all('w15chapter', sid):
                if chapter.get('status') != 'active' or len(refs) + len(chapter.get('refs', [])) > 20:
                    continue
                try:
                    rows = context.resolve(chapter['refs'])
                    if not all(row['source'].get('audienceVisible') for row in rows):
                        continue
                except Phase10Error:
                    continue
                items.append(chapter)
                refs.extend(chapter['refs'])
            if refs:
                # The response guard rejects repeated refs; chapters may share moments.
                handler._p10_refs = list({json.dumps(r, sort_keys=True): r for r in refs}.values())
            return 200, {'chapters': items}
        if parts == ['search'] and method == 'GET':
            query = parse_qs(urlparse(handler.path).query, keep_blank_values=True)
            if set(query) != {'q'} or len(query['q']) != 1 or not 1 <= len(query['q'][0].strip()) <= 200:
                invalid('Enter one search query of up to 200 characters.')
            candidates = []
            for moment in store.all('p10moment', sid):
                try:
                    rows = context.resolve([moment.get('ref')])
                    if rows[0]['source'].get('audienceVisible'):
                        candidates.append(rows[0]['moment'])
                except Phase10Error:
                    continue
                if len(candidates) == 2000:
                    break
            matches = phase10_timeline.rank_moments(query['q'][0], candidates)
            refs = [item['ref'] for item in matches]
            if refs:
                handler._p10_refs = refs
            return 200, {'moments': matches}
        raise Phase10Error('not_found', 'Chapter route unavailable.', 404)
