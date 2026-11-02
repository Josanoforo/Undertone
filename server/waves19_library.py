"""Bounded definition-only catalog. Integration owns persistence and authorization."""
import copy
import hashlib
import json
import re
from pathlib import Path
from .phase10_common import Phase10Error
from .waves17_templates import clean_definition

SCHEMA_VERSION = 1
MAX_BYTES = 16384
_ID = re.compile(r'^[A-Za-z0-9._:-]{1,128}$')


def fail(message, status=422):
    raise Phase10Error('invalid_library' if status == 422 else 'library_unavailable', message, status)


def validate(envelope):
    """Return canonical definition; reject every unknown field, including nested payloads."""
    try:
        encoded = json.dumps(envelope, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        fail('Invalid definition encoding.')
    if len(encoded) > MAX_BYTES or not isinstance(envelope, dict) or set(envelope) != {'schemaVersion', 'definition'}:
        fail('Use a bounded definition-only envelope.')
    if type(envelope['schemaVersion']) is not int or envelope['schemaVersion'] != SCHEMA_VERSION:
        fail('Unsupported schema version; export version 1 or recreate the definition.')
    d = envelope['definition']
    if not isinstance(d, dict) or set(d) != {'type', 'title', 'question', 'options', 'cards'}:
        fail('Only type, title, question, options and cards are supported; remove other fields.')
    if any(not isinstance(d.get(k), str) for k in ('type', 'title', 'question')):
        fail('Definition text is required.')
    for name in ('options', 'cards'):
        if not isinstance(d[name], list) or any(not isinstance(x, str) for x in d[name]):
            fail('Items must be plain text.')
    if any(any(ord(c) < 32 and c not in '\n\r\t' for c in s) for s in [d['title'], d['question'], *d['options'], *d['cards']]):
        fail('Remove control characters from text.')
    return clean_definition(copy.deepcopy(d))


def export_definition(definition):
    envelope = {'schemaVersion': SCHEMA_VERSION, 'definition': copy.deepcopy(definition)}
    return {'schemaVersion': SCHEMA_VERSION, 'definition': validate(envelope)}


def catalog():
    path = Path(__file__).with_name('waves19_library_examples.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list) or len(data) > 20:
        fail('Catalog unavailable.', 503)
    result = []
    for entry in data:
        if not isinstance(entry, dict) or set(entry) != {'id', 'version', 'intent', 'steps', 'definition'} or not _ID.fullmatch(entry['id']) or type(entry['version']) is not int or entry['version'] != 1:
            fail('Catalog unavailable.', 503)
        if not isinstance(entry['intent'], str) or not 1 <= len(entry['intent']) <= 500 or not isinstance(entry['steps'], list) or not 1 <= len(entry['steps']) <= 8 or any(not isinstance(s, str) or not 1 <= len(s) <= 300 for s in entry['steps']):
            fail('Catalog unavailable.', 503)
        definition = validate({'schemaVersion': 1, 'definition': entry['definition']})
        result.append({'id': entry['id'], 'version': 1, 'title': definition['title'], 'intent': entry['intent'], 'steps': copy.deepcopy(entry['steps']), 'compatibility': 'compatible', 'definition': definition})
    if len({e['id'] for e in result}) != len(result): fail('Catalog unavailable.', 503)
    return result


def get_example(example_id):
    for entry in catalog():
        if entry['id'] == example_id: return entry
    fail('Library item unavailable.', 404)


def import_definition(adapter, actor, session_id, request_id, envelope):
    """Adapter atomically creates fresh template + receipt or replays after rights checks."""
    if not isinstance(actor, dict) or actor.get('role') != 'creator' or actor.get('sid') != session_id or not actor.get('owner'):
        fail('Creator access required.', 403)
    if not isinstance(request_id, str) or not _ID.fullmatch(request_id): fail('Invalid request ID.')
    definition = validate(envelope)
    canonical = json.dumps({'schemaVersion': 1, 'definition': definition}, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    fingerprint = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return adapter.import_template(actor, session_id, request_id, fingerprint, copy.deepcopy(definition), {'kind': 'definition-library', 'schemaVersion': 1})
