"""Explicit local correction receipts for source-bound Phase 12 translations."""
import hashlib
import json
from . import store
from . import phase12_jobs as jobs

MAX_TEXT = 12000

def root_id(row):
    if row['transport'] == 'local_user_correction':
        return json.loads(row['payload'])['originalRequestId']
    return row['request_id']

def corrections(row):
    with store.connect() as db:
        rows = db.execute("SELECT * FROM phase12_jobs WHERE session_id=? AND actor_id=? AND kind='translation' AND transport='local_user_correction' ORDER BY seq", (row['session_id'], row['actor_id'])).fetchall()
    return [r for r in rows if json.loads(r['payload']).get('originalRequestId') == root_id(row)]

def check_lineage(row):
    parent = jobs.fetch(row['session_id'], row['actor_id'], root_id(row))
    if (not parent or parent['kind'] != 'translation' or parent['transport'] == 'local_user_correction'
            or parent['state'] != 'complete' or not parent['result']
            or parent['credential_hash'] != row['credential_hash'] or parent['ref'] != row['ref']):
        jobs.error('stale_context', 'Original translation unavailable.')
    jobs.rights(parent)
    return parent

def check_speech_parent(row):
    if row['kind'] != 'translation' or row['state'] != 'complete' or not row['result']:
        jobs.error('stale_context', 'Translation unavailable.')
    if row['transport'] == 'local_user_correction':
        check_lineage(row)
    versions = corrections(row)
    if versions and versions[-1]['request_id'] != row['request_id']:
        jobs.error('stale_context', 'Translation has been corrected; explicitly play its current version.')

def correct(handler, sid, actor, parent_id, body):
    if (not isinstance(body, dict) or set(body) != {'requestId', 'text'}
            or not jobs.valid_id(body.get('requestId')) or not isinstance(body.get('text'), str)):
        jobs.error('invalid_request', 'Valid requestId and text required.', 422)
    text = body['text']
    if not text.strip() or len(text) > MAX_TEXT or any(ord(c) < 32 and c not in '\n\r\t' for c in text):
        jobs.error('invalid_request', 'Correction text must contain 1 to 12000 characters.', 422)
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        jobs.error('invalid_request', 'Correction text must be valid Unicode.', 422)
    fingerprint = hashlib.sha256(jobs.canonical({'kind':'translation_correction','parent':parent_id,'body':body}).encode()).hexdigest()
    with store.LOCK, store.connect() as db:
        parent = jobs.check_job(handler, sid, actor, parent_id, 'complete')
        if parent['kind'] != 'translation' or parent['transport'] == 'local_user_correction' or not parent['result']:
            jobs.error('invalid_request', 'A completed original translation is required.', 422)
        old = jobs.fetch(sid, actor['owner'], body['requestId'])
        if old:
            if old['fingerprint'] != fingerprint:
                jobs.error('request_conflict', 'Request ID is bound to a different payload.')
            row = jobs.check_job(handler, sid, actor, body['requestId'], 'complete')
            handler._p12_binding = (sid, actor, body['requestId'], 'complete')
            return 200, {'operation': jobs.view(row)}
        if db.execute('SELECT COUNT(*) FROM phase12_jobs').fetchone()[0] >= jobs.MAX_RECEIPTS:
            jobs.error('receipt_capacity', 'Receipt storage is full.', 429)
        original = json.loads(parent['result'])
        result = dict(original)
        result.update(translation=text, uncertainty='', provider='user', model=None,
                      translationVersion='user-corrected-v1', provenance='user_corrected',
                      originalRequestId=parent_id, originalTranslationVersion=original.get('translationVersion'))
        payload = {'originalRequestId':parent_id, 'sourceLanguage':original['sourceLanguage'],
                   'targetLanguage':original['targetLanguage']}
        timing = {'request':jobs.stamp(), 'end':jobs.stamp()}
        # Lock and one SQLite transaction serialize the new version with speech suppression.
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute("INSERT INTO phase12_jobs(session_id,actor_id,credential_hash,role,request_id,kind,fingerprint,payload,ref,source_id,state,result,timing,transport) VALUES(?,?,?,?,?,'translation',?,?,?,?, 'complete',?,?, 'local_user_correction')",
                       (sid, actor['owner'], parent['credential_hash'], parent['role'], body['requestId'], fingerprint,
                        jobs.canonical(payload), parent['ref'], parent['source_id'], jobs.canonical(result), jobs.canonical(timing)))
            related = {parent_id} | {r['request_id'] for r in corrections(parent)}
            speeches = db.execute("SELECT seq,payload FROM phase12_jobs WHERE session_id=? AND actor_id=? AND kind='speech' AND state IN ('queued','running','complete')", (sid, actor['owner'])).fetchall()
            for speech in speeches:
                if json.loads(speech['payload']).get('translationRequestId') in related:
                    db.execute("UPDATE phase12_jobs SET state='canceled',result=NULL,media=NULL WHERE seq=?", (speech['seq'],))
            db.execute('COMMIT')
        except BaseException:
            db.execute('ROLLBACK')
            raise
        row = jobs.fetch(sid, actor['owner'], body['requestId'])
        handler._p12_binding = (sid, actor, body['requestId'], 'complete')
        return 201, {'operation':jobs.view(row)}
