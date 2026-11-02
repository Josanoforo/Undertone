"""Conservative punctuation units over explicit final text, never ASR simulation."""
import hashlib
import re

REVISION = 'punctuation-sentences-v1'
_ABBREVIATIONS = {'dr', 'mr', 'mrs', 'ms', 'sr', 'sra', 'srta', 'prof', 'st', 'etc', 'e.g', 'i.e'}


def split(text):
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000:
        raise ValueError('invalid_sentence_text')
    units, start = [], 0
    # Keep punctuation/whitespace verbatim. A final tail is an explicit final
    # utterance tail, not a claim that punctuation implies semantic turn end.
    for match in re.finditer(r'[.!?]+[\"\'\u201d\u2019)]*(?=\s|$)', text):
        end = match.end()
        prefix = text[:match.start()]
        token = re.search(r'([\w.]+)$', prefix)
        token = token.group(1) if token else ''
        if match.group(0).startswith('.') and (token.lower() in _ABBREVIATIONS or
                (len(token) == 1 and token.isalpha()) or re.fullmatch(r'(?:[A-Za-z]\.)+[A-Za-z]?', token)):
            continue
        while end < len(text) and text[end].isspace():
            end += 1
        if text[start:end].strip():
            units.append({'start': start, 'end': end, 'boundary': 'punctuation'})
            start = end
    if text[start:].strip():
        units.append({'start': start, 'end': len(text), 'boundary': 'explicit_final_tail'})
    if not units or len(units) > 32 or any(len(text[u['start']:u['end']]) > 600 for u in units):
        raise ValueError('sentence_unit_too_large')
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return [{'index': i, **u, 'text': text[u['start']:u['end']], 'segmentTextSha256': digest,
             'segmentationRevision': REVISION, 'delivery': 'buffered_sentence', 'alignment': 'unavailable'}
            for i, u in enumerate(units)]
