"""Current-rights, moment-bounded playback of retained PCM WAV audio."""
import hashlib
import io
import wave

from . import channel_authority, lifecycle, phase10_common, phase10_timeline, store


def unavailable():
    raise phase10_common.Phase10Error('not_found', 'Moment audio is unavailable.', 404)


def audio(ctx, request):
    if not isinstance(request, dict) or set(request) != {'ref', 'archive'}:
        unavailable()
    ref = phase10_common.parse_ref(request['ref'])
    archive = request['archive']
    if not isinstance(archive, dict) or set(archive) != {'channelId', 'grantId', 'revision'}:
        unavailable()
    ctx.check_actor()
    projected = channel_authority.project_source(ctx, archive['channelId'], archive['grantId'], archive['revision'])
    if projected['ref'] != ref:
        unavailable()
    source = store.get('source', ref['sourceId'], ref['sessionId'])
    origin = store.get('session', ref['sessionId'], ref['sessionId'])
    if not origin or not lifecycle.active(origin) or not source or source.get('p10Provenance', {}).get('type') != 'received_asr_v1':
        unavailable()
    offset = phase10_timeline._ms(source.get('offsetSeconds', 0))
    start, end = ref['startMs'] - offset, ref['endMs'] - offset
    if start < 0 or end <= start:
        unavailable()
    with store.connect() as db:
        row = db.execute('SELECT mime,digest,data FROM phase12_original_audio WHERE source_id=? AND session_id=?', (ref['sourceId'], ref['sessionId'])).fetchone()
    if not row or row['mime'] not in ('audio/wav', 'audio/x-wav') or row['digest'] != source.get('audioDigest') or hashlib.sha256(row['data']).hexdigest() != row['digest']:
        unavailable()
    try:
        with wave.open(io.BytesIO(row['data']), 'rb') as src:
            channels, width, rate, count, compression, _ = src.getparams()
            if compression != 'NONE' or channels not in (1, 2) or width not in (1, 2, 3, 4) or not 1 <= rate <= 192000:
                unavailable()
            # Round inward so no sample outside the approved interval is sent.
            first = (start * rate + 999) // 1000
            last = min((end * rate) // 1000, count)
            if first >= last:
                unavailable()
            src.setpos(first)
            frames = src.readframes(last - first)
            if len(frames) != (last - first) * channels * width:
                unavailable()
            output = io.BytesIO()
            with wave.open(output, 'wb') as dst:
                dst.setnchannels(channels); dst.setsampwidth(width); dst.setframerate(rate)
                dst.writeframes(frames)
            return output.getvalue()
    except (wave.Error, EOFError, ValueError, OverflowError):
        unavailable()
