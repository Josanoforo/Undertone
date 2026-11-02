// The host supplies a finalized approved manifest and a current-scope snapshot.
// verifyCurrent must freshly reauthorize that exact actor, source, rights and
// manifest; requestExport uses the existing authenticated session transport.
// The supplied read callback must reauthorize the exact Studio material each
// time. No independent edition or copied approval is created.
export async function downloadApprovedChapter({readCurrent, expected, isCurrent}) {
  if (typeof readCurrent !== 'function' || typeof isCurrent !== 'function' || !expected) throw Error('Chapter unavailable');
  const canonical = x => Array.isArray(x) ? x.map(canonical) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canonical(x[k])])) : x;
  const same = (a,b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  const valid = m => m && m.id === expected.materialId && m.format === 'chapter' && m.status === 'approved' && m.currentVersion === expected.version && m.approvedVersion === expected.version && m.dependencyState === 'current' && m.requiresReview === false && typeof m.title === 'string' && typeof m.body === 'string' && same(m.refs,expected.refs) && Number.isSafeInteger(m.revision);
  if (!isCurrent()) throw Error('Chapter unavailable');
  const first = await readCurrent(); if (!isCurrent() || !valid(first)) throw Error('Chapter unavailable');
  const second = await readCurrent(); if (!isCurrent() || !valid(second) || !same(first,second)) throw Error('Chapter changed');
  const metadata = JSON.stringify({materialId:first.id,version:first.currentVersion,sourceRefs:first.refs,attribution:'Source titles and excerpts are retained in the approved chapter body.',limitations:['Downloaded copies cannot be recalled; hosted access can be revoked.']});
  const content = `${first.title}\n\n${first.body}\n\nSource and attribution metadata:\n${metadata}\n`;
  const url = URL.createObjectURL(new Blob([content], {type:'text/plain; charset=utf-8'}));
  const a = document.createElement('a');
  try { a.href=url; a.download=`approved-chapter-v${first.currentVersion}.txt`; a.hidden=true; document.body.append(a); a.click(); }
  finally { a.remove(); URL.revokeObjectURL(url); }
}

export function mountApprovedExport(root, {requestExport, verifyCurrent} = {}) {
  if (typeof requestExport !== 'function' || typeof verifyCurrent !== 'function') throw new TypeError('Export host callbacks are required');
  const box = document.createElement('section'); box.className = 'w27-export';
  const node = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
  const status = node('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const content = node('div'); box.append(node('h2', 'Export approved edition'), node('p', 'Downloaded copies cannot be recalled. Hosted access can still be revoked.'), status, content); root.append(box);
  let generation = 0, alive = true, state = null, busy = false, urls = new Set();
  const canonical = x => Array.isArray(x) ? x.map(canonical) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canonical(x[k])])) : x;
  const fingerprint = x => JSON.stringify(canonical(x));
  const revoke = () => { for (const url of urls) URL.revokeObjectURL(url); urls.clear(); };
  function reset() { generation++; state = null; busy = false; revoke(); content.replaceChildren(); status.textContent = 'Refresh the approved edition and current access to export.'; }
  const active = (g, s) => alive && generation === g && state === s;
  const validCue = c => Number.isSafeInteger(c?.startMs) && Number.isSafeInteger(c?.endMs) && c.startMs >= 0 && c.endMs > c.startMs;
  function available(manifest, format) {
    return ['en','es'].filter(lang => manifest.tracks.some(t => t?.language === lang && Array.isArray(t.cues) && (format === 'text' ? t.kind === 'approved_text' && t.cues.some(c => typeof c?.text === 'string' && c.text.length > 0) : ['original','translation'].includes(t.kind) && t.cues.some(validCue))));
  }
  function validResult(result, format) {
    if (!result || typeof result !== 'object' || Array.isArray(result) || Object.keys(result).sort().join(',') !== 'attribution,content,limitations,mimeType,sourceRefs') return false;
    if (result.mimeType !== (format === 'text' ? 'text/plain; charset=utf-8' : 'text/vtt; charset=utf-8') || typeof result.content !== 'string' || !result.content.length || result.content.length > 8388608 || (format === 'vtt' && !result.content.startsWith('WEBVTT\n'))) return false;
    const strings = a => Array.isArray(a) && a.length > 0 && a.length <= 100 && a.every(x => typeof x === 'string' && x.length > 0 && x.length <= 4096);
    if (!strings(result.attribution) || !strings(result.limitations) || !Array.isArray(result.sourceRefs) || result.sourceRefs.length > 1000 || !result.sourceRefs.every(x => x && typeof x === 'object' && !Array.isArray(x))) return false;
    try { return JSON.stringify(result.sourceRefs).length <= 1048576; } catch { return false; }
  }
  async function download(s, g, format, languages) {
    if (!active(g,s) || busy) return;
    busy = true; status.textContent = 'Checking current export access…';
    try {
      if (await verifyCurrent({scope:s.scope, manifest:s.manifest}) !== true || !active(g,s) || fingerprint(s.scope) !== s.scopeKey || fingerprint(s.manifest) !== s.manifestKey) throw Error('stale');
      const body = {editionId:s.manifest.editionId, revision:s.manifest.revision, format, languages};
      const result = await requestExport({scope:s.scope, body});
      if (!active(g,s) || fingerprint(s.scope) !== s.scopeKey || fingerprint(s.manifest) !== s.manifestKey || !validResult(result, format)) throw Error('stale');
      if (await verifyCurrent({scope:s.scope, manifest:s.manifest}) !== true || !active(g,s) || fingerprint(s.scope) !== s.scopeKey || fingerprint(s.manifest) !== s.manifestKey) throw Error('stale');
      const blob = new Blob([result.content], {type:result.mimeType});
      const url = URL.createObjectURL(blob); urls.add(url);
      const a = node('a');
      try { a.href = url; a.download = `approved-edition-${format}.${format === 'vtt' ? 'vtt' : 'txt'}`; a.hidden = true; box.append(a); a.click(); }
      finally { a.remove(); URL.revokeObjectURL(url); urls.delete(url); }
      status.textContent = 'Export downloaded. Hosted access can be revoked, but downloaded copies cannot be recalled.';
    } catch { if (active(g,s)) status.textContent = 'Export unavailable or access changed. Refresh the approved edition and try again.'; }
    finally { if (active(g,s)) busy = false; }
  }
  function render(s, g) {
    const formatLabel = node('label', 'Format '), format = node('select');
    for (const [value,label] of [['text','Text'],['vtt','Timed WebVTT']]) { const option = node('option',label); option.value = value; format.append(option); }
    formatLabel.append(format); const choices = node('fieldset'), legend = node('legend','Available languages'); choices.append(legend);
    const controls = new Map();
    for (const lang of ['en','es']) { const label = node('label'); const input = node('input'); input.type = 'checkbox'; label.append(input, document.createTextNode(` ${lang}`)); choices.append(label); controls.set(lang,{input,label}); }
    const note = node('p', 'WebVTT includes only supplied timed captions; untimed captions are omitted.');
    const button = node('button','Download selected export'); button.type = 'button';
    const updateChoices = () => { const offered = available(s.manifest,format.value); for (const [lang,c] of controls) { c.input.disabled = !offered.includes(lang); c.label.hidden = c.input.disabled; if (c.input.disabled) c.input.checked = false; } button.disabled = !offered.length; };
    format.addEventListener('change',updateChoices); button.addEventListener('click',() => { if (!active(g,s)) return; const langs = [...controls].filter(([,c]) => !c.input.disabled && c.input.checked).map(([lang])=>lang); if (!langs.length) { status.textContent = 'Select at least one available language.'; return; } download(s,g,format.value,langs); });
    content.append(formatLabel, choices, note, button); updateChoices();
  }
  // Called only with a finalized current approved edition. Host resets on every
  // actor, session, source, edition, rights or authorization change.
  function update(manifest, scope) {
    reset(); if (!alive) return false;
    try {
      if (!scope || typeof scope !== 'object' || !manifest || manifest.approval !== 'approved' || !/^[A-Za-z0-9._:-]{1,128}$/.test(manifest.editionId) || !Number.isSafeInteger(manifest.revision) || manifest.revision < 1 || !Array.isArray(manifest.tracks)) throw Error('invalid');
      const m = JSON.parse(JSON.stringify(manifest)), s = JSON.parse(JSON.stringify(scope));
      state = {manifest:m, scope:s, manifestKey:fingerprint(m), scopeKey:fingerprint(s)}; render(state,generation); status.textContent = 'Select a format and available language, then download.'; return true;
    } catch { reset(); status.textContent = 'Approved edition or current access is unavailable.'; return false; }
  }
  function destroy() { if (!alive) return; reset(); alive = false; box.remove(); }
  reset(); return {update, reset, destroy};
}
