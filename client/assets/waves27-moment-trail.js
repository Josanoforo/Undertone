// B27.1 presentation adapter. Host supplies the released, final-guarded DTO.
export function mount(root, initialContext = {}) {
  let ctx = initialContext, generation = 0, sequence = 0, destroyed = false, rows = [], focusTarget = null;
  const identity = c => JSON.stringify([c.actorId, c.role, c.sessionId, c.sourceRef, c.sourceRevision, c.rightsGeneration, c.scope, c.scopeGeneration, c.channelId]);
  const make = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
  const heading = make('h2', 'Moment context'), status = make('p', 'Select a moment to see its context.');
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const list = make('ol'), previous = make('button', 'Previous moment'), next = make('button', 'Next moment'), live = make('button', 'Return to live');
  for (const b of [previous, next, live]) b.type = 'button';
  root.classList.add('moment-trail27'); root.replaceChildren(heading, status, list, previous, next, live);
  const valid = (g, key, seq) => !destroyed && g === generation && key === identity(ctx) && seq === sequence;
  const clear = message => { rows = []; focusTarget = null; list.replaceChildren(); status.textContent = message; previous.disabled = true; next.disabled = true; live.disabled = typeof ctx.returnLive !== 'function'; };
  function controls() {
    previous.disabled = !rows.some(x => x.position === 'previous' && x.destination != null) || typeof ctx.navigate !== 'function';
    next.disabled = !rows.some(x => x.position === 'next' && x.destination != null) || typeof ctx.navigate !== 'function';
    live.disabled = typeof ctx.returnLive !== 'function';
  }
  async function action(callback, value) {
    if (typeof callback !== 'function') return;
    const g = generation, key = identity(ctx), seq = sequence;
    try { await callback(value, () => valid(g, key, seq)); } catch (_) { if (valid(g, key, seq)) status.textContent = 'This destination is unavailable.'; }
  }
  const sameRef = (a, b) => !!a && !!b && ['sessionId', 'sourceId', 'sourceRevision', 'momentId', 'startMs', 'endMs'].every(k => a[k] === b[k]);
  const sameArchive = (a, b) => a == null && b == null || !!a && !!b && ['channelId', 'grantId', 'revision'].every(k => a[k] === b[k]);
  function render(model, selection) {
    if (!model || !['current', 'corrected', 'retired'].includes(model.state) || !Array.isArray(model.previous) || !Array.isArray(model.next) || model.previous.length > 10 || model.next.length > 10) throw Error('Invalid trail');
    if (model.state === 'retired') { clear('This source is retired or unavailable.'); return; }
    if (!['timed', 'whole_source'].includes(model.context) || !model.selected || !sameRef(model.selected.ref, selection.ref) || !sameArchive(model.selected.destination?.archive, selection.archive) || model.selected.sourceRef !== ctx.sourceRef || model.selected.sourceRevision !== ctx.sourceRevision || (model.context === 'whole_source' && (model.previous.length || model.next.length || model.selected.time !== null))) throw Error('Invalid selection');
    const item = (value, position) => {
      if (!value || !['current', 'corrected'].includes(value.trailState) || value.rightsState !== 'current' || !value.destination || !sameRef(value.ref, value.destination.ref) || value.sourceRef !== ctx.sourceRef || value.sourceRevision !== ctx.sourceRevision) throw Error('Invalid item');
      const ref = value.ref;
      const timed = ref.momentId != null;
      if (timed && (!Number.isSafeInteger(ref.startMs) || !Number.isSafeInteger(ref.endMs) || ref.startMs < 0 || ref.endMs <= ref.startMs)) throw Error('Invalid interval');
      return { position, state: value.trailState, destination: value.destination, interval: timed ? `${ref.startMs}–${ref.endMs} ms` : 'untimed source' };
    };
    if (model.selected.trailState !== model.state) throw Error('Invalid selected state');
    const safe = [...model.previous.map(x => item(x, 'previous')), item(model.selected, 'selected'), ...model.next.map(x => item(x, 'next'))];
    rows = safe; list.replaceChildren(); const renderGeneration = generation, renderKey = identity(ctx), renderSequence = sequence;
    status.textContent = `Current source · revision ${model.selected.sourceRevision}${model.context === 'whole_source' ? ' · whole-source context' : ''}${model.truncated ? ' · More context available' : ''}`;
    for (const item of rows) {
      const li = make('li'), label = { previous: 'Previous', selected: 'Selected', next: 'Next', context: 'Context' }[item.position];
      li.append(make('span', `${label} · ${item.state} · ${item.interval}`));
      if (item.destination != null) {
        const b = make('button', 'Inspect ' + label.toLowerCase()); b.type = 'button'; b.disabled = typeof ctx.inspect !== 'function';
        b.addEventListener('click', () => { if (valid(renderGeneration, renderKey, renderSequence)) action(ctx.inspect, item.destination); }); li.append(b);
      } else li.append(make('span', ' · Content unavailable'));
      list.append(li);
    }
    if (model.context === 'timed' && !model.previous.length) list.prepend(make('li', 'Previous · unavailable'));
    if (model.context === 'timed' && !model.next.length) list.append(make('li', 'Next · unavailable'));
    controls();
    if (focusTarget) { status.tabIndex = -1; status.focus(); focusTarget = null; }
  }
  async function load(selection) {
    const wasInside = root.contains(document.activeElement); ++sequence; clear('Loading context…'); if (wasInside) { status.tabIndex = -1; status.focus(); } const g = generation, key = identity(ctx), seq = sequence;
    if (!selection || !selection.ref || Array.isArray(selection.ref) || Array.isArray(selection)) { clear('Choose a specific moment before opening its context.'); return; }
    if (selection.ref.sourceId !== ctx.sourceRef || selection.ref.sourceRevision !== ctx.sourceRevision) { clear('Context is unavailable.'); return; }
    if (typeof ctx.loadTrail !== 'function') { clear('Context is unavailable.'); return; }
    try { const request = JSON.parse(JSON.stringify(selection)); const expected = JSON.parse(JSON.stringify(request)); const model = await ctx.loadTrail(request, () => valid(g, key, seq)); if (valid(g, key, seq)) render(model, expected); }
    catch (_) { if (valid(g, key, seq)) clear('Context is unavailable.'); }
  }
  function move(position) { const candidates = rows.filter(x => x.position === position && x.destination != null); const row = position === 'previous' ? candidates[candidates.length - 1] : candidates[0]; if (row) action(ctx.navigate, row.destination); }
  previous.addEventListener('click', () => move('previous')); next.addEventListener('click', () => move('next')); live.addEventListener('click', () => action(ctx.returnLive));
  clear('Select a moment to see its context.');
  return {
    load,
    update(nextContext) { const changed = identity(ctx) !== identity(nextContext); ctx = nextContext; if (changed) { generation++; sequence++; const wasInside = root.contains(document.activeElement); clear('Select a moment to see its context.'); if (wasInside) { status.tabIndex = -1; status.focus(); } } else controls(); },
    destroy() { destroyed = true; generation++; sequence++; rows = []; focusTarget = null; root.replaceChildren(); }
  };
}


