"""Current approved edition export. Host must call finalize immediately before send."""
import copy
import hashlib
import json
from html import escape
from . import waves22_edition as edition
from . import waves18_records as records


def _fail(message, status=409):
    edition._fail('export_unavailable', message, status)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _stamp(ms):
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02}.{ms:03}'


def prepare(ctx, request, *, released=edition.released_metadata):
    """Prepare ephemeral data; it is not authorized for delivery until finalize."""
    if (not isinstance(request, dict) or set(request) != {'editionId','revision','format','languages'}
        or type(request['revision']) is not int or request['revision'] < 1
        or request['format'] not in ('text','vtt') or not isinstance(request['languages'], list)
        or not 1 <= len(request['languages']) <= 2
        or any(x not in ('en','es') for x in request['languages'])
        or len(set(request['languages'])) != len(request['languages'])):
        _fail('Choose an edition, revision, format and explicit languages.', 422)
    records.key(request['editionId'])
    with ctx.lock:
        if ctx.actor.get('role') not in ('creator', 'viewer'):
            _fail('Export unavailable.', 404)
        prepared = edition.project_edition(ctx, request['editionId'], request['languages'][0], released=released)
        manifest = prepared['manifest']
        if manifest['revision'] != request['revision']:
            _fail('Edition revision changed.')
        record, view, _ = edition._read(ctx, request['editionId'], request['languages'][0])
        refs = copy.deepcopy(view['refs'] + view.get('sourceRefs', []))
        # Source-only references are checked by the same current record authority and
        # actor resolver; include their current data only in the private fence.
        source_rows = [ctx.resolve_source(ref) for ref in view.get('sourceRefs', [])]
        limitations = ['Downloaded copies cannot be recalled; hosted access can be revoked.']
        attribution = []
        if request['format'] == 'text':
            chunks=[]
            for lang in request['languages']:
                tracks=[t for t in manifest['tracks'] if t['kind']=='approved_text' and t['language']==lang]
                if len(tracks)!=1 or not tracks[0]['cues']:
                    _fail('Requested approved language unavailable.')
                attribution.append(f"{lang}: {tracks[0]['provenance']}")
                value='\n\n'.join(c['text'] for c in tracks[0]['cues'])
                chunks.append(f'[{lang}]\n{value}' if len(request['languages']) > 1 else value)
            content='\n\n'.join(chunks)
            mime='text/plain; charset=utf-8'
        else:
            cues=[]; omitted=0
            for lang in request['languages']:
                tracks=[t for t in manifest['tracks'] if t['kind'] in ('original','translation') and t['language']==lang]
                for track in tracks:
                    for cue in track['cues']:
                        if cue['startMs'] is None:
                            omitted += 1
                        else:
                            cues.append((cue['startMs'], cue['endMs'], lang, track['kind'], cue['text']))
                if not any(c[2] == lang for c in cues):
                    _fail('Timed captions unavailable for a requested language.')
                for kind in sorted({c[3] for c in cues if c[2] == lang}):
                    attribution.append(f'{lang}: {kind} source captions')
            if omitted:
                limitations.append('Untimed captions were omitted; timing was not inferred.')
            lines=['WEBVTT','']
            for start,end,lang,kind,value in sorted(cues, key=lambda c:(c[0],c[1],c[2],c[3])):
                safe=escape(value, quote=False).replace('\r',' ').replace('\n',' ')
                if len(request['languages']) > 1: safe=f'[{lang}] {safe}'
                lines.extend([_stamp(start)+' --> '+_stamp(end), safe, ''])
            content='\n'.join(lines); mime='text/vtt; charset=utf-8'
        # Keep provenance in the downloaded bytes as well as in the DTO. JSON
        # encoding makes source identifiers safe in plain text and VTT NOTE lines.
        metadata = json.dumps({'sourceRefs': refs, 'attribution': attribution,
                               'limitations': limitations}, ensure_ascii=False,
                              sort_keys=True, separators=(',', ':'))
        if request['format'] == 'text':
            content += '\n\nSource and attribution metadata:\n' + metadata + '\n'
        else:
            content = 'WEBVTT\n\nNOTE source and attribution metadata\n' + metadata + '\n\n' + content[len('WEBVTT\n\n'):]
        result={'mimeType':mime,'content':content,'sourceRefs':refs,
                'attribution':attribution,'limitations':limitations}
        # Revalidate after resolving all data, including source-only references.
        edition.finalize(ctx, prepared, released=released)
        return {'result':result, '_binding':{'request':copy.deepcopy(request),
                'edition':prepared, 'sourceDigest':_digest(source_rows), 'resultDigest':_digest(result)}}


def finalize(ctx, prepared, *, released=edition.released_metadata):
    """Rebuild and compare under the host's delivery lock, immediately before bytes."""
    if not isinstance(prepared, dict) or not isinstance(prepared.get('_binding'), dict):
        _fail('Export unavailable.')
    with ctx.lock:
        binding=prepared['_binding']
        try:
            fresh=prepare(ctx, binding['request'], released=released)
            if fresh['_binding'] != binding or fresh['result'] != prepared.get('result'):
                _fail('Export changed before delivery.')
        except (KeyError, TypeError):
            _fail('Export unavailable.')
        return fresh['result']
