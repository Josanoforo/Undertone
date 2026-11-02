"""Optional installed Windows OCR over selected PNG crops; no provider or storage."""
import base64
import functools
import json
import math
from pathlib import Path
import subprocess

from .phase10_common import Phase10Error


def _worker(request):
    executable = Path('C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe')
    if not executable.is_file():
        raise ValueError('windows_ocr_unavailable')
    # Use the normal command interface; no execution-policy setting is changed.
    # The static worker contains no image data, credential, or source capability.
    command = Path(__file__).with_name('waves21_ocr_worker.ps1').read_text(encoding='utf-8')
    result = subprocess.run([str(executable), '-NoProfile', '-NonInteractive', '-Command', command],
                            input=json.dumps(request).encode('utf-8'), capture_output=True, timeout=25,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or len(result.stdout) > 256000:
        raise ValueError('windows_ocr_unavailable')
    value = json.loads(result.stdout.decode('utf-8-sig'))
    if not isinstance(value, dict) or value.get('status') != 'ok':
        raise ValueError('windows_ocr_unavailable')
    return value


@functools.lru_cache(maxsize=1)
def capabilities():
    try:
        result = _worker({'operation': 'capabilities'})
        languages = result['languages']
        if not isinstance(languages, list) or not languages or any(not isinstance(x, str) for x in languages):
            raise ValueError()
        return {'available': True, 'engine': 'Windows.Media.Ocr', 'languages': languages,
                'maxImageDimension': result['maxImageDimension'], 'confidence': 'unavailable'}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return {'available': False, 'engine': 'Windows.Media.Ocr', 'languages': [],
                'reason': 'installed_recognizer_unavailable'}


def recognize(row, box):
    """Recognize actual cropped pixels and map word boxes to the selected frame.

    The grounding owner checks source/capture/revision before and after this call.
    Only a crop contained in the normalized selected region reaches the OCR engine.
    Empty results mean no recognized words, never invented caption-derived text.
    """
    from .waves21_visual_grounding import png_metadata, rectangle
    image = row['source']['image']
    meta = png_metadata(image)
    box = rectangle(box)
    width, height = meta['width'], meta['height']
    left, top = math.ceil(box['x'] * width), math.ceil(box['y'] * height)
    right = math.floor((box['x'] + box['width']) * width)
    bottom = math.floor((box['y'] + box['height']) * height)
    if right <= left or bottom <= top:
        return []
    caps = capabilities()
    if not caps['available']:
        raise Phase10Error('ocr_unavailable', 'The installed OCR recognizer is unavailable.', 503)
    try:
        result = _worker({'operation': 'recognize', 'image': image['data'],
                          'language': caps['languages'][0],
                          'crop': {'x': left, 'y': top, 'width': right-left, 'height': bottom-top}})
        words = result['words']
        if not isinstance(words, list) or len(words) > 100:
            raise ValueError()
        angle = result.get('textAngle')
        if words and (type(angle) not in (int, float) or not math.isfinite(angle) or abs(angle) > .01):
            raise ValueError('rotated_text_boxes_unsupported')
        out = []
        for word in words:
            if (not isinstance(word, dict) or not isinstance(word.get('text'), str)
                    or not 1 <= len(word['text']) <= 1000):
                raise ValueError()
            values = [word[k] for k in ('x', 'y', 'width', 'height')]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError()
            x, y, w, h = values
            x1, y1 = max(left, left+x), max(top, top+y)
            x2, y2 = min(right, left+x+w), min(bottom, top+y+h)
            if x2 <= x1 or y2 <= y1:
                continue
            # Clip in normalized space too, avoiding float-boundary drift.
            nx, ny = max(box['x'], x1/width), max(box['y'], y1/height)
            ex, ey = min(box['x']+box['width'], x2/width), min(box['y']+box['height'], y2/height)
            out.append({'text': word['text'], 'box': {'x': nx, 'y': ny, 'width': ex-nx, 'height': ey-ny},
                        'confidence': None})
        return out
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        raise Phase10Error('ocr_unavailable', 'Regional OCR did not complete; no automatic retry.', 503) from None


def callback():
    return recognize if capabilities()['available'] else None
