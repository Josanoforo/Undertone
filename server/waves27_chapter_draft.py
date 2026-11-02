"""Deterministic source-bound chapter assembly for Studio drafts.

Preparation only: the integrating authority must hold the store lock and
atomically commit the returned draft with its own durable request receipt.
"""
import copy
import json

from . import phase10_studio as studio
from .phase10_common import Phase10Error
from .waves16_continuation import material_data


def assemble(ctx, title, chapters):
    """Resolve a creator's ordered selection and prepare Studio material data.

    Caller holds ctx.lock until the dependent commit or response serialization.
    No persistence, approval, generation or delivery is performed here.
    """
    ctx.check_actor()
    if ctx.actor.get('role') != 'creator':
        raise Phase10Error('not_found', 'Material unavailable.', 404)
    title = studio.text(title, 200)
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= 20:
        raise Phase10Error('invalid_field', 'Select between one and twenty chapters.', 400)
    refs, labels = [], []
    for chapter in chapters:
        if not isinstance(chapter, dict) or set(chapter) != {'ref', 'label'}:
            raise Phase10Error('invalid_field', 'Invalid chapter.', 400)
        ref = chapter['ref']
        if not isinstance(ref, dict) or ref.get('sessionId') != ctx.sid or ref in refs:
            raise Phase10Error('invalid_field', 'Select distinct current session references.', 400)
        refs.append(copy.deepcopy(ref))
        labels.append(studio.text(chapter['label'], 200))
    rows = studio.resolve_material_refs(ctx, refs)
    # JSON escaping preserves labels and original attribution without permitting
    # embedded newlines to forge additional chapter/source headings.
    lines = []
    for index, (ref, label, row) in enumerate(zip(refs, labels, rows), 1):
        source = row['source']
        item = {'label': label, 'sourceTitle': str(source.get('title') or 'Source')[:200],
                'sourceId': ref['sourceId'], 'sourceRevision': ref['sourceRevision']}
        if 'momentId' in ref:
            item['momentId'] = ref['momentId']
            item['excerpt'] = str(row['moment'].get('text', ''))[:1500]
        lines.append(str(index) + '. ' + json.dumps(item, ensure_ascii=False, separators=(',', ':')))
    body = studio.text('\n'.join(lines), 12000)
    material = material_data(title, body, refs)
    material['format'] = 'chapter'
    return material


def replacement(ctx, material, version, title, chapters):
    """Prepare a new, unapproved exact Studio version; never commit it."""
    draft = assemble(ctx, title, chapters)
    return studio.replacement_material(ctx, material, version, draft['title'], draft['body'], draft['refs'])
