"""Authoritative local speech policy lookup for Wave 20 delivery.

The caller must hold store.LOCK through any decision that relies on the result.
This is one resolver building block; it does not configure or authorize delivery.
"""
import json
from decimal import Decimal, InvalidOperation
from . import lifecycle, store, waves20_modes, waves17_tts_local


def current_hosted_speech_policy(sid, revision):
    """Return the current explicit hosted speech policy, without admitting spend.

    The caller must independently verify the hosted profile, source rights and
    reserve both session and global budgets at the actual dispatch boundary.
    A configured profile alone does not establish synthesis availability.
    """
    if type(revision) is not int or revision < 1:
        return None
    with store.LOCK, store.connect() as db:
        row = db.execute("SELECT owner_id,data FROM objects WHERE kind='session' AND id=? AND session_id=?",
                         (sid, sid)).fetchone()
        try:
            if not row or not row['owner_id'] or not lifecycle.active(json.loads(row['data'])):
                return None
            _, policy = waves20_modes._current(db, sid, row['owner_id'])
            if not policy or policy['revision'] != revision:
                return None
            selected = policy['operations']['speech']
            cap = Decimal(policy['sessionCapUsd'])
            if ('hosted' not in [selected['primary'], *selected['alternatives']] or
                    not cap.is_finite() or cap <= 0 or cap > 75):
                return None
            return policy
        except (ValueError, TypeError, KeyError, InvalidOperation, waves20_modes.Phase10Error):
            return None


def current_local_policy(sid, revision):
    """Resolve current creator policy for shared work without subscriber authority.

    Callers must hold store.LOCK through their authority decision. Subscriber
    access is checked independently; this function alone cannot authorize output.
    """
    if type(revision) is not int or revision < 1:
        return None
    with store.LOCK, store.connect() as db:
        row = db.execute("SELECT owner_id,data FROM objects WHERE kind='session' AND id=? AND session_id=?",
                         (sid, sid)).fetchone()
        try:
            if not row or not row['owner_id'] or not lifecycle.active(json.loads(row['data'])):
                return None
            _, policy = waves20_modes._current(db, sid, row['owner_id'])
            if not policy or policy['revision'] != revision:
                return None
            selected = policy['operations']['speech']
            if 'local' not in [selected['primary'], *selected['alternatives']]:
                return None
            facts = waves17_tts_local.availability()
            if facts.get('configured') is not True or facts.get('available') is not True:
                return None
            return policy
        except (ValueError, TypeError, KeyError, waves20_modes.Phase10Error):
            return None


def translation_binding(policy, provider_status):
    """Bind a selected translation provider to verified runtime facts.

    This does not reserve funds or authorize a call. The caller must separately
    enforce the session cap and existing durable provider admission at dispatch.
    A configured but untested provider is deliberately not treated as available.
    """
    try:
        selected = policy['operations']['translation']['primary']
        name = provider_status['name']
        expected = {'local': 'ollama', 'hosted': 'claude'}.get(selected)
        model = provider_status['model']
        cap = Decimal(policy['sessionCapUsd'])
        if (expected is None or name != expected or
                provider_status['configured'] is not True or
                provider_status['available'] is not True or
                not isinstance(model, str) or not model or len(model) > 128 or
                not cap.is_finite() or cap < 0 or cap > 75 or
                (selected == 'hosted' and cap <= 0)):
            return None
        return {'choice': selected, 'provider': name, 'model': model,
                'sessionCapUsd': policy['sessionCapUsd']}
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


def current_translation_policy(sid, revision, provider_status):
    """Resolve the current speech and translation choices together.

    The caller holds store.LOCK through the authority decision. This is a
    policy snapshot only: durable admission and spending limits are separate.
    """
    policy = current_local_policy(sid, revision)
    if policy is None:
        return None
    binding = translation_binding(policy, provider_status)
    return (policy, binding) if binding is not None else None


def local_policy(sid, actor, credential_hash, revision):
    """Return the current explicit local speech policy, or None on any mismatch."""
    if (not isinstance(actor, dict) or actor.get('sid') != sid or
            actor.get('role') not in ('creator', 'viewer') or
            not isinstance(actor.get('owner'), str) or not actor['owner'] or
            not isinstance(credential_hash, str) or len(credential_hash) != 64 or
            any(c not in '0123456789abcdef' for c in credential_hash) or
            type(revision) is not int or revision < 1):
        return None
    with store.LOCK, store.connect() as db:
        credential = db.execute('SELECT role,session_id,owner_id FROM credentials WHERE hash=?',
                                (credential_hash,)).fetchone()
        row = db.execute("SELECT owner_id,data FROM objects WHERE kind='session' AND id=? AND session_id=?",
                         (sid, sid)).fetchone()
        if (not credential or (credential['role'], credential['session_id'], credential['owner_id']) !=
                (actor['role'], sid, actor['owner']) or not row or not row['owner_id'] or
                (actor['role'] == 'creator' and actor['owner'] != row['owner_id'])):
            return None
        try:
            if not lifecycle.active(json.loads(row['data'])):
                return None
            _, policy = waves20_modes._current(db, sid, row['owner_id'])
            if not policy or policy['revision'] != revision:
                return None
            selected = policy['operations']['speech']
            if 'local' not in [selected['primary'], *selected['alternatives']]:
                return None
            facts = waves17_tts_local.availability()
            if facts.get('configured') is not True or facts.get('available') is not True:
                return None
            return policy
        except (ValueError, TypeError, KeyError, waves20_modes.Phase10Error):
            return None

