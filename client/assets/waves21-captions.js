// Incoming projections must already be authorized by the owner. No transport or playback is started here.
export function mountCaptions(root, {actions = {}} = {}) {
  const box = document.createElement('section'); box.className = 'w21-captions';
  const title = document.createElement('h2'); title.textContent = 'Captions';
  const status = document.createElement('p'); status.setAttribute('role','status');
  const list = document.createElement('ol'); list.setAttribute('aria-label','Caption moments');
  box.append(title,status,list); root.append(box);
  let generation = 0, scope = null, rows = new Map(), connection = 'connected', destroyed = false;
  const key = x => JSON.stringify([x.captureRunId,x.sourceId,x.segmentId]);
  function render() {
    list.replaceChildren();
    status.textContent = connection === 'connected' ? 'Captions available.' : connection === 'reconnecting' ? 'Reconnecting. Captions are hidden until access is confirmed.' : 'Disconnected. Captions are hidden until access is confirmed.';
    const ordered = [...rows.values()].sort((a,b) => (a.startMs ?? 0)-(b.startMs ?? 0) || key(a).localeCompare(key(b)));
    if (connection === 'connected' && !ordered.some(row => row.status !== 'gap')) status.textContent = ordered.length ? 'Caption gaps shown below.' : 'No captions yet.';
    for (const row of ordered) {
      const li = document.createElement('li'); li.className = `w21-caption-${row.status}`;
      li.dataset.segmentId = row.segmentId; li.dataset.revision = String(row.revision);
      const label = document.createElement('strong'); label.textContent = row.status === 'gap' ? 'Missing caption' : `${row.status === 'provisional' ? 'Provisional — may change' : row.status === 'correction' ? 'Correction awaiting finalization' : 'Final'} (${row.language || 'language unknown'}) · revision ${row.revision}`;
      li.append(label);
      const reasons = {recognition_pending:'Recognition pending.', recognition_error:'Recognition failed; the outcome is unknown and will not be retried automatically.', no_speech_detected:'No speech was recognized; silence and missed speech cannot be distinguished here.'};
      const original = document.createElement('p'); original.textContent = row.status === 'gap' ? `${row.startMs}–${row.endMs} ms: ${reasons[row.reason] || 'Audio has not been received for this interval.'}` : String(row.text || ''); li.append(original);
      if (row.status !== 'gap') {
        const meta = document.createElement('p'); meta.textContent = `${row.segmentId} · source revision ${row.sourceRevision} · ${row.startMs}–${row.endMs} ms · Speaker unknown${Number.isInteger(row.correctionOf) ? ` · corrects revision ${row.correctionOf}` : ''}`; li.append(meta);
        if (typeof row.originalText === 'string' && (row.text !== row.originalText || row.language !== row.originalLanguage)) {
          const initial = document.createElement('p'); initial.textContent = `Original recognition (${row.originalLanguage || 'unknown'}): ${row.originalText}`; li.append(initial);
        }
      }
      if (row.overlap === true) { const note=document.createElement('p'); note.textContent='Overlapping speech; speaker identity is unknown.'; li.append(note); }
      if (row.status === 'final' && row.translation && row.translation.approved === true && row.translation.captionRevision === row.revision && row.translation.sourceRevision === row.sourceRevision && typeof row.translation.text === 'string') { const t=document.createElement('p'); t.textContent=`Translation (${row.translation.language || 'language unknown'}): ${row.translation.text}`; li.append(t); }
      if (row.status === 'final' && typeof actions.select === 'function') { const b=document.createElement('button'); b.type='button'; b.textContent='Choose this moment'; b.onclick=()=>actions.select({...row}); li.append(b); }
      list.append(li);
    }
  }
  function reset() { generation++; rows.clear(); scope=null; list.replaceChildren(); status.textContent='Captions cleared.'; }
  function update(projection, ticket) {
    if (destroyed || ticket !== generation) return false;
    if (!projection || projection.rightsState !== 'available' || !projection.scopeKey) { reset(); status.textContent='Captions unavailable or access changed.'; return false; }
    if (scope !== null && scope !== projection.scopeKey) { reset(); status.textContent='Captions unavailable or access changed.'; return false; }
    scope=projection.scopeKey;
    connection=['connected','reconnecting','disconnected'].includes(projection.connection) ? projection.connection : 'disconnected';
    if (connection !== 'connected') { generation++; rows.clear(); render(); return true; }
    for (const row of Array.isArray(projection.revisions) ? projection.revisions : []) {
      if (!row || !row.captureRunId || !row.sourceId || !row.segmentId || !Number.isInteger(row.revision) || !Number.isInteger(row.sourceRevision) || !['provisional','correction','final','gap'].includes(row.status)) continue;
      const id=key(row), previous=rows.get(id);
      if (previous && (row.sourceRevision < previous.sourceRevision || (row.sourceRevision === previous.sourceRevision && row.revision <= previous.revision))) continue;
      if (previous && row.sourceRevision === previous.sourceRevision && (row.originalText !== previous.originalText || row.originalLanguage !== previous.originalLanguage || row.startMs !== previous.startMs || row.endMs !== previous.endMs)) continue;
      rows.set(id, {...row, translation:row.translation ? {...row.translation} : null});
    }
    render(); return true;
  }
  return {update, reset, destroy(){reset();destroyed=true;box.remove();}, getGeneration:()=>generation};
}
