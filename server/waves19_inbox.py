"""Creator-reviewed inbox over the voluntary Wave 13 exchange.

The integrating HTTP send path must invoke guard_delivery under store.LOCK.
"""
import hashlib
import json
import re

from . import store, waves13_exchange as exchange
from .phase10_common import Context, Phase10Error

_ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')


def fail(message, status=400):
    raise Phase10Error('not_found' if status == 404 else 'inbox_conflict' if status == 409 else 'invalid_inbox', message, status)


def _ids(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 50 or any(not isinstance(i, str) or not _ID.fullmatch(i) for i in value) or len(set(value)) != len(value):
        fail('Select one to fifty distinct questions.')
    return value


def _text(value, limit):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        fail('Enter bounded descriptive text.')
    return value.strip()


def _question(handler, sid, actor, qid):
    q = store.get('w13question', qid, sid)
    return q if q and exchange.eligible(handler, sid, actor, q) else None


def _answer(handler, sid, actor, link):
    target = _question(handler, sid, actor, link['questionId'])
    origin = _question(handler, sid, actor, link['answerQuestionId'])
    if not target or target['_revision'] != link['questionRevision'] or not origin or origin['_revision'] != link['answerRevision']:
        return None
    answer = origin.get('answer') or {}
    if origin.get('status') != 'selected' or answer.get('approved') is not True:
        return None
    return {'question': target, 'answer': dict(answer), 'answerSource': {'questionId': origin['id'], 'revision': origin['_revision'], 'ref': origin.get('ref')}}


def _projection(handler, sid, actor, view):
    Context(handler, sid, actor).check_actor()
    if view == 'creator':
        if actor['role'] != 'creator': fail('Creator capability required.', 403)
        questions = [q for q in store.all('w13question', sid) if exchange.eligible(handler, sid, actor, q)]
        current = {q['id']: q['_revision'] for q in questions}
        groups = []
        for g in store.all('w19inboxgroup', sid):
            members = [i for i in g['questionIds'] if current.get(i) == g['questionRevisions'].get(i)]
            if not members: continue
            complete = len(members) == len(g['questionIds'])
            groups.append({'id': g['id'], 'revision': g['_revision'], 'questionIds': members, 'state': g['state'], 'theme': g['theme'] if complete else None, 'reason': g['reason'] if complete else None, 'distinct': g['distinct'] if complete else None, 'needsReview': not complete})
        return {'questions': questions, 'groups': groups}
    if actor['role'] != 'viewer': fail('Viewer capability required.', 403)
    answers = []
    for link in store.all('w19inboxlink', sid):
        if exchange.owner(sid, link['questionId']) != actor['owner']: continue
        row = _answer(handler, sid, actor, link)
        if row:
            # The source question's raw text and owner never leave the creator inbox.
            answers.append(row)
    return {'answers': answers}


def guard_delivery(handler):
    """Revalidate a protected read at the send boundary; caller holds store.LOCK."""
    binding = getattr(handler, '_w19_inbox_binding', None)
    if binding is None: return
    sid, actor, view, before = binding
    if _projection(handler, sid, actor, view) != before:
        raise Phase10Error('stale_context', 'Inbox access or content changed; refresh.', 409)


def _insert(db, kind, sid, oid, owner, obj):
    db.execute('INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES(?,?,?,?,1,?,?)', (kind, oid, sid, owner, json.dumps(obj, ensure_ascii=False), store.now()))


def handle(handler, sid, actor, method, parts):
    with store.LOCK:
        Context(handler, sid, actor).check_actor()
        if method == 'GET' and parts in (['inbox'], ['inbox', 'answers']):
            view = 'creator' if parts == ['inbox'] else 'viewer'
            result = _projection(handler, sid, actor, view)
            handler._w19_inbox_binding = (sid, dict(actor), view, result)
            return 200, result
        if actor['role'] != 'creator': fail('Creator capability required.', 403)
        creating = method == 'POST' and parts == ['inbox', 'groups']
        editing = method == 'PATCH' and len(parts) == 3 and parts[:2] == ['inbox', 'groups']
        answering = method == 'POST' and len(parts) == 4 and parts[:2] == ['inbox', 'groups'] and parts[3] == 'answer'
        if not (creating or editing or answering): fail('Inbox route unavailable.', 404)
        b = handler.body()
        fields = {'requestId', 'questionIds', 'action', 'theme', 'reason', 'distinct'} if creating else ({'requestId', 'expectedRevision', 'questionIds', 'action', 'theme', 'reason', 'distinct'} if editing else {'requestId', 'expectedRevision', 'questionIds', 'answerQuestionId', 'answerRevision'})
        if not isinstance(b, dict) or set(b) != fields: fail('Invalid inbox fields.')
        if not isinstance(b['requestId'], str) or not _ID.fullmatch(b['requestId']): fail('A valid request ID is required.')
        ids = _ids(b['questionIds'])
        if not creating and (type(b['expectedRevision']) is not int or b['expectedRevision'] < 1): fail('A valid revision is required.')
        if answering:
            if not isinstance(b['answerQuestionId'], str) or not _ID.fullmatch(b['answerQuestionId']) or type(b['answerRevision']) is not int or b['answerRevision'] < 1: fail('An exact reviewed answer revision is required.')
        else:
            if b['action'] not in ('group', 'split', 'defer') or type(b['distinct']) is not bool: fail('Use an explicit group, split or defer action.')
            if creating and b['action'] == 'split': fail('Split requires an existing group.')
            _text(b['theme'], 160); _text(b['reason'], 500)
        fingerprint = hashlib.sha256(json.dumps([method, parts, b], sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        receipt_id = hashlib.sha256((sid + '\0' + actor['owner'] + '\0' + b['requestId']).encode()).hexdigest()
        old = store.get('w19inboxreceipt', receipt_id, sid)
        if old and old['fingerprint'] != fingerprint: fail('Request ID already used for a different action.', 409)
        group = store.get('w19inboxgroup', old['groupId'] if old else parts[2], sid) if not creating or old else None
        if old:
            if not group or group['_revision'] != old['groupRevision']: fail('The previous result changed; refresh.', 409)
        elif not creating:
            if not group: fail('Group unavailable.', 404)
            if group['_revision'] != b['expectedRevision']: fail('Group changed; refresh.', 409)
        questions = {}
        for qid in ids:
            q = _question(handler, sid, actor, qid)
            if not q: fail('A selected question is unavailable.', 409)
            questions[qid] = q
        if answering:
            if any(i not in group['questionIds'] or group['questionRevisions'].get(i) != questions[i]['_revision'] for i in ids): fail('Group membership changed; refresh.', 409)
            origin = _question(handler, sid, actor, b['answerQuestionId'])
            if not origin or origin['_revision'] != b['answerRevision'] or origin.get('status') != 'selected' or (origin.get('answer') or {}).get('approved') is not True: fail('The reviewed answer changed or is unavailable.', 409)
        if old:
            if any(old['questionRevisions'].get(i) != questions[i]['_revision'] for i in ids): fail('A question changed; refresh.', 409)
            if answering:
                for qid in ids:
                    link_id = hashlib.sha256((sid + '\0' + qid).encode()).hexdigest()
                    link = store.get('w19inboxlink', link_id, sid)
                    if not link or link.get('questionRevision') != questions[qid]['_revision'] or link.get('answerQuestionId') != origin['id'] or link.get('answerRevision') != origin['_revision']:
                        fail('The previous answer link changed; refresh.', 409)
            return 200, {'groupId': group['id'], 'revision': group['_revision'], 'replayed': True}
        if editing and b['action'] == 'split' and (not set(ids) < set(group['questionIds'])): fail('Split keeps a nonempty proper subset.', 409)
        if not answering:
            group_id = store.ident() if creating else group['id']
            value = {'id': group_id, 'questionIds': ids, 'questionRevisions': {i: questions[i]['_revision'] for i in ids}, 'theme': _text(b['theme'],160), 'reason': _text(b['reason'],500), 'distinct': b['distinct'], 'state': 'deferred' if b['action'] == 'defer' else 'grouped'}
            new_revision = 1 if creating else group['_revision'] + 1
        else:
            group_id, new_revision = group['id'], group['_revision']
        receipt = {'id': receipt_id, 'fingerprint': fingerprint, 'groupId': group_id, 'groupRevision': new_revision, 'questionRevisions': {i: questions[i]['_revision'] for i in ids}}
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Guard every selected revision inside the transaction as well as source rights above.
            for q in list(questions.values()) + ([origin] if answering else []):
                row = db.execute("SELECT revision FROM objects WHERE kind='w13question' AND id=? AND session_id=?", (q['id'], sid)).fetchone()
                if not row or row['revision'] != q['_revision']: fail('A question changed; refresh.', 409)
            if creating:
                _insert(db, 'w19inboxgroup', sid, group_id, actor['owner'], value)
            elif editing:
                changed = db.execute("UPDATE objects SET data=?,revision=revision+1 WHERE kind='w19inboxgroup' AND id=? AND session_id=? AND revision=?", (json.dumps(value,ensure_ascii=False),group_id,sid,group['_revision'])).rowcount
                if changed != 1: fail('Group changed; refresh.', 409)
            else:
                row = db.execute("SELECT revision FROM objects WHERE kind='w19inboxgroup' AND id=? AND session_id=?", (group_id,sid)).fetchone()
                if not row or row['revision'] != group['_revision']: fail('Group changed; refresh.', 409)
                for qid in ids:
                    link_id = hashlib.sha256((sid + '\0' + qid).encode()).hexdigest()
                    link = {'id':link_id, 'questionId':qid, 'questionRevision':questions[qid]['_revision'], 'answerQuestionId':origin['id'], 'answerRevision':origin['_revision']}
                    db.execute("INSERT INTO objects(kind,id,session_id,owner_id,revision,data,created_at) VALUES('w19inboxlink',?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data,revision=objects.revision+1", (link_id,sid,actor['owner'],1,json.dumps(link,ensure_ascii=False),store.now()))
            _insert(db, 'w19inboxreceipt', sid, receipt_id, actor['owner'], receipt)
            db.commit()
        return (201 if creating else 200), {'groupId': group_id, 'revision': new_revision, 'replayed': False}

