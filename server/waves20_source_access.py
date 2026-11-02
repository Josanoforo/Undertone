"""Current-rights check for a private Wave 20 ASR subscriber.

This is one part of the delivery binding, not a public-source approval or a
configured scheduler. Authority is a credential digest, never a bearer token.
"""
import hashlib
import json
from . import lifecycle, phase12_jobs, store
from .phase10_common import Phase10Error, parse_ref
from .waves20_delivery import Identity, Subscriber


def private_asr_source(identity, subscriber, ref=None):
    """Return the currently authorized source and moment, or None.

    Source is the indexed moment ID; source_revision is its decimal source
    revision. Callers using the returned content must hold store.LOCK through
    their own authority decision or serialization. Public delivery requires
    separate creator authorization and is deliberately outside this function.
    """
    try:
        if not isinstance(identity, Identity) or not isinstance(subscriber, Subscriber):
            return None
        with store.LOCK:
            if ref is None:
                moment = store.get('p10moment', identity.source, identity.session)
                ref = moment.get('ref') if moment else None
            ref = parse_ref(ref)
            return _private_asr_source_locked(identity, subscriber, ref)
    except (Phase10Error, ValueError, TypeError, KeyError, UnicodeError):
        return None


def _private_asr_source_locked(identity, subscriber, ref):
    try:
        if (not identity.private_actor or identity.private_actor != subscriber.actor or
            ref['sessionId'] != identity.session or ref['momentId'] != identity.source or
            str(ref['sourceRevision']) != identity.source_revision or
            len(subscriber.authority) != 64 or
            any(c not in '0123456789abcdef' for c in subscriber.authority)):
            return None
        with store.LOCK, store.connect() as db:
            credential = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?',
                                    (subscriber.authority,)).fetchone()
            owner = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?",
                               (identity.session, identity.session)).fetchone()
            session = store.get('session', identity.session, identity.session)
            if (not credential or credential['session_id'] != identity.session or
                credential['owner_id'] != subscriber.actor or
                credential['role'] not in ('creator', 'viewer') or
                not owner or not owner['owner_id'] or
                (credential['role'] == 'creator' and credential['owner_id'] != owner['owner_id']) or
                not session or not lifecycle.active(session)):
                return None
            row = {'credential_hash': subscriber.authority, 'role': credential['role'],
                   'session_id': identity.session, 'actor_id': subscriber.actor,
                   'ref': json.dumps(ref)}
            source, moment, _ = phase12_jobs.rights(row)
            text = moment.get('text')
            if (isinstance(text, str) and bool(text.strip()) and
                    hashlib.sha256(text.encode('utf-8')).hexdigest() == identity.text_digest):
                return source, moment, ref
            return None
    except (Phase10Error, ValueError, TypeError, KeyError, UnicodeError):
        return None


def private_asr_access(identity, subscriber, ref):
    """Boolean current-rights check; no source content leaves this boundary."""
    return bool(private_asr_source(identity, subscriber, ref))


def approved_record_source(identity, subscriber=None):
    """Re-read an approved public interpretation and, when given, subscriber rights.

    The caller must hold store.LOCK across its authority decision or response
    serialization. Without a subscriber this checks global record authority only;
    it must never be used as authorization to send a result to a viewer.
    """
    from . import waves18_records
    try:
        if (not isinstance(identity, Identity) or identity.private_actor or
                not identity.source.startswith('record:') or
                not identity.source[7:] or identity.language not in ('en', 'es')):
            return None
        with store.LOCK:
            session = store.get('session', identity.session, identity.session)
            if not session or not lifecycle.active(session):
                return None
            with store.connect() as db:
                owner = db.execute("SELECT owner_id FROM objects WHERE kind='session' AND id=? AND session_id=?",
                                   (identity.session, identity.session)).fetchone()
                record_owner = db.execute("SELECT owner_id FROM objects WHERE kind='w18record' AND id=? AND session_id=?",
                                          (identity.source[7:], identity.session)).fetchone()
            if not owner or not owner['owner_id'] or not record_owner or record_owner['owner_id'] != owner['owner_id']:
                return None
            if subscriber is not None:
                if (not isinstance(subscriber, Subscriber) or
                        len(subscriber.authority) != 64 or
                        any(c not in '0123456789abcdef' for c in subscriber.authority)):
                    return None
                with store.connect() as db:
                    credential = db.execute(
                        'SELECT role,session_id,owner_id FROM credentials WHERE hash=?',
                        (subscriber.authority,)).fetchone()
                if (not credential or credential['session_id'] != identity.session or
                        credential['owner_id'] != subscriber.actor or
                        credential['role'] not in ('creator', 'viewer')):
                    return None
                if credential['role'] == 'creator' and owner['owner_id'] != subscriber.actor:
                    return None
            record = waves18_records.fetch(identity.session, identity.source[7:])
            if str(record['version']) != identity.source_revision:
                return None
            projection = waves18_records.projection(identity.session, record, identity.language)
            if subscriber is not None:
                # Global record currency does not replace the requesting actor's
                # rights, especially for references carried across sessions.
                from .phase10_common import Context
                actor = {'sid': identity.session, 'owner': subscriber.actor,
                         'role': credential['role']}
                ctx = Context(None, identity.session, actor,
                              credential_digest=subscriber.authority)
                refs = list(projection['refs'])
                for entry in projection['chapters'] + projection['contributions']:
                    refs.extend(entry.get('refs', []))
                fmt = store.get('w15format', record['snapshot']['format']['id'], identity.session)
                if not fmt:
                    return None
                refs.extend(fmt.get('refs', []))
                for ref in refs:
                    ctx.resolve([ref])
            text = projection['interpretation']
            if (projection['fallback'] or not isinstance(text, str) or
                    not 1 <= len(text.strip()) <= 600 or len(text) > 600 or
                    hashlib.sha256(text.encode('utf-8')).hexdigest() != identity.text_digest):
                return None
            return projection
    except (Phase10Error, ValueError, TypeError, KeyError, UnicodeError):
        return None
