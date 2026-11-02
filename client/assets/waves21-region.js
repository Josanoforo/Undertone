// The caller supplies a current-rights projection and owns navigation and audio.
export function mountRegion(root, {scope, api = {}, actions = {}}) {
  const box = document.createElement('section'); box.className = 'w21-region';
  const heading = document.createElement('h2'); heading.textContent = 'Inspect this moment';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.setAttribute('tabindex', '-1');
  const content = document.createElement('div'); box.append(heading, status, content); root.append(box);
  let generation = 0, destroyed = false, currentScope = scope;
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); return n; };
  const button = (parent, label, fn) => { const b = el('button', label); b.type = 'button'; b.addEventListener('click', fn); parent.append(b); return b; };
  const clear = () => content.replaceChildren();
  function reset() { generation++; clear(); status.textContent = ''; }
  function update(projection, nextScope = currentScope, ticket) {
    if (ticket !== generation) return false;
    generation++; const epoch = generation; currentScope = nextScope; clear();
    if (destroyed) return;
    if (!projection || projection.rightsState !== 'available') {
      const reason = projection?.rightsState;
      status.textContent = reason === 'withdrawn' ? 'This source was withdrawn.' : reason === 'ambiguous' ? 'This moment is ambiguous or cannot be identified.' : 'This moment is unavailable or access cannot be confirmed.';
      return;
    }
    status.textContent = 'Moment available. Choose a named region to inspect.';
    const info = el('p', `Moment: ${projection.momentId ?? 'unknown'}; source revision: ${projection.sourceRevision ?? 'unknown'}.`); content.append(info);
    if (projection.interval) content.append(el('p', `Source interval: ${projection.interval.startMs ?? '?'}–${projection.interval.endMs ?? '?'} ms.`));
    const regions = Array.isArray(projection.regions) ? projection.regions : projection.region ? [projection] : [];
    const list = el('ol'); list.setAttribute('aria-label', 'Named regions'); const details = el('div'); details.className = 'w21-region-details';
    let overlay;
    if (typeof projection.frameRef === 'string' && projection.frameRef) {
      const frame = el('div'); frame.className = 'w21-region-frame';
      const img = el('img'); img.alt = projection.frameAlt || 'Authorized frame. Choose a named region below for a text alternative.'; img.src = projection.frameRef;
      img.addEventListener('error', () => { if (epoch === generation) status.textContent = 'The authorized frame could not be displayed. Use the region list.'; });
      overlay = el('div'); overlay.className = 'w21-region-overlay'; overlay.setAttribute('aria-hidden', 'true'); frame.append(img, overlay); content.append(frame);
    }
    function select(item, i) {
      if (epoch !== generation) return;
      details.replaceChildren();
      details.append(el('h3', item.name || item.label || `Region ${i + 1}`));
      const add = (label, value) => details.append(el('p', `${label}: ${value || 'Not available'}`));
      add('Original evidence', item.observedText); add('OCR text', item.ocrText); add('Interpretation (inference)', item.interpretation); add('Uncertainty', item.uncertainty);
      if (item.cause || item.ambiguousCause) add('Cause', item.cause || 'Ambiguous; the cause is not established.');
      if (overlay) { overlay.replaceChildren(); const r = item.region || item; if ([r.x,r.y,r.width,r.height].every(Number.isFinite) && r.x >= 0 && r.y >= 0 && r.width > 0 && r.height > 0 && r.x + r.width <= 1 && r.y + r.height <= 1) { const marker = el('div'); marker.className = 'w21-region-marker'; Object.assign(marker.style, {left:`${r.x*100}%`,top:`${r.y*100}%`,width:`${r.width*100}%`,height:`${r.height*100}%`}); overlay.append(marker); } }
      if (typeof actions.describe === 'function') button(details, 'Play available description', async () => { try { await actions.describe({scope:currentScope, projection, region:item}); if(epoch === generation) status.textContent = 'Description requested.'; } catch { if(epoch === generation) status.textContent = 'Description is unavailable.'; } });
      status.textContent = `${item.name || item.label || `Region ${i + 1}`} selected.`;
    }
    regions.forEach((item, i) => { const li = el('li'); button(li, item.name || item.label || `Region ${i + 1}`, () => select(item, i)); list.append(li); });
    if (!regions.length) content.append(el('p', 'No named regions are available.'));
    content.append(list, details);
    if (typeof actions.returnToLive === 'function') button(content, 'Return to live', () => actions.returnToLive({scope:currentScope}));
  }
  function destroy() { reset(); destroyed = true; box.remove(); }
  return {update, reset, destroy, getGeneration: () => generation};
}

