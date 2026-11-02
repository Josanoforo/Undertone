"""Current creator terminology inspection over existing authorities; no writes."""
import json

from .phase10_common import Phase10Error
from . import phase12_jobs, waves17_terminology as terms
from . import waves21_speech_runtime as speech


def _unavailable():
    raise Phase10Error('not_found', 'Terminology inspection unavailable.', 404)


def inspect(ctx, *, rule_set_id=None):
    """Inspect the current creator record and own Phase 12 queued jobs only.

    Call under the host's shared store lock, including final serialization.
    The optional rule set is separately authorized by its existing authority.
    """
    with ctx.lock:
        ctx.check_actor()
        if ctx.actor.get('role') != 'creator' or getattr(ctx, '_credential_digest', None) is not None:
            _unavailable()
        credential = ctx.store.digest(getattr(ctx.handler, '_auth_token', ''))
        record = terms.load(ctx.sid)
        approved = record.get('approved') if record else None
        snapshot = terms.snapshot(ctx.sid, ctx.actor, credential, approved['revision']) if approved else None
        ruleset = speech._rule_load(ctx, rule_set_id)['ruleset'] if rule_set_id is not None else None
        rules = [dict(r) for r in ruleset['rules'] if r['approved']] if ruleset else []
        document = snapshot['document'] if snapshot else None
        projected = []
        if document:
            for item in document['terms']:
                matching = [dict(r) for r in rules if (r['language'] == 'en' and r['term'] == item['en']) or (r['language'] == 'es' and r['term'] == item['es'])]
                projected.append({'id': item['id'], 'original': item['en'], 'translated': item['es'],
                                  'alternatives': item['alternatives'], 'ambiguity': item['ambiguity'],
                                  'pronunciations': matching})
        applications, completed = [], []
        with ctx.store.connect() as db:
            rows = db.execute("SELECT * FROM phase12_jobs WHERE session_id=? AND actor_id=? AND credential_hash=? AND kind='translation' AND state IN ('queued','running','complete') ORDER BY seq", (ctx.sid, ctx.actor['owner'], credential)).fetchall()
        for row in rows:
            try:
                payload = json.loads(row['payload'])
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            bound = payload.get('terminologySnapshot')
            if row['transport'] == 'local_user_correction':
                try:
                    from . import waves15_translation_review
                    parent = waves15_translation_review.check_lineage(row)
                    bound = json.loads(parent['payload']).get('terminologySnapshot')
                except (Phase10Error, TypeError, ValueError, KeyError):
                    continue
            if (not isinstance(bound, dict) or type(bound.get('revision')) is not int
                    or bound['revision'] < 1 or not isinstance(bound.get('document'), dict)):
                continue
            try:
                terms.validate(bound['document'])
            except Phase10Error:
                continue
            # Suppressed targets are omitted entirely, including their identities.
            try:
                phase12_jobs.check_job(ctx.handler, ctx.sid, ctx.actor, row['request_id'])
                _, moment, source_ref = phase12_jobs.rights(row)
                # Historical context has its own rights; a current job source
                # does not authorize a revoked glossary context reference.
                terms.check_refs(ctx.sid, ctx.actor, credential, bound['document'])
            except (Phase10Error, TypeError, ValueError, KeyError):
                continue
            relation = 'current' if snapshot == bound else 'stale'
            if relation == 'current':
                try:
                    terms.guard(row)
                except Phase10Error:
                    continue
            previous = {item['id']: item for item in bound['document']['terms']}
            current = {item['id']: item for item in document['terms']} if document else {}
            changed = sorted(key for key in previous.keys() | current.keys() if previous.get(key) != current.get(key))
            source_text = moment.get('text', '')
            language = payload.get('sourceLanguage')
            # These are literal matches, not an invented semantic applicability
            # score. The complete document was supplied to each bound job.
            matched = [item['id'] for item in bound['document']['terms']
                       if language in ('en', 'es') and item[language].casefold() in source_text.casefold()]
            entry = {'kind': 'phase12_translation', 'requestId': row['request_id'],
                     'state': row['state'], 'terminologyRevision': bound['revision'],
                     'relation': relation, 'source': source_ref,
                     'termIds': sorted(previous), 'literalMatchTermIds': matched,
                     'changedTermIds': changed,
                     'contextChanged': snapshot is None or bound['document']['context'] != document['context'],
                     'refresh': ('review_completed_result' if row['state'] == 'complete' else 'review_pending_work') if relation == 'stale' else 'none'}
            (completed if row['state'] == 'complete' else applications).append(entry)
        state = 'approved' if snapshot else ('draft' if record and record.get('draft') else 'disabled' if record else 'absent')
        return {'state': state, 'recordRevision': record.get('_revision') if record else None,
                'approvedRevision': snapshot['revision'] if snapshot else None,
                'draftRevision': record['draft']['revision'] if record and record.get('draft') else None,
                'terms': projected, 'context': document['context'] if document else [],
                'pronunciation': {'ruleSetId': ruleset['ruleSetId'], 'revision': ruleset['revision']} if ruleset else None,
                'applications': applications,
                'completedResults': completed,
                'completedCoverage': 'actor_owned_phase12_translations_only',
                'coverage': 'partial_actor_owned_phase12_queued_running_only'}


def final_guard(ctx, expected, *, rule_set_id=None):
    """Recheck exactly the serialized projection under the host's send lock."""
    if inspect(ctx, rule_set_id=rule_set_id) != expected:
        raise Phase10Error('stale_context', 'Terminology inspection changed before delivery.', 409)
    return True
