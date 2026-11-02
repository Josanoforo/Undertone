const MAX_CHAPTERS = 20;
const CREATE_BASE = 'create';

const same = (left, right) => JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  return value;
}

function validRef(ref, scope) {
  return ref && typeof ref === 'object' && !Array.isArray(ref) &&
    ref.sessionId === scope.sessionId && typeof ref.sourceId === 'string' && !!ref.sourceId &&
    Number.isInteger(ref.sourceRevision) &&
    ((ref.momentId === undefined && ref.startMs === undefined && ref.endMs === undefined) ||
      (typeof ref.momentId === 'string' && !!ref.momentId && Number.isFinite(ref.startMs) &&
        Number.isFinite(ref.endMs) && ref.startMs >= 0 && ref.endMs > ref.startMs));
}

// Only the exact, lossless assembler representation can safely be reopened as
// structured chapters. An arbitrary Studio body remains editable in Studio.
export function chaptersFromMaterial(material, scope) {
  if (!material || material.format !== 'chapter' || typeof material.body !== 'string' || !Array.isArray(material.refs) || material.refs.length < 1 || material.refs.length > MAX_CHAPTERS || material.refs.some(ref => !validRef(ref, scope))) return null;
  if (new Set(material.refs.map(ref => JSON.stringify(canonical(ref)))).size !== material.refs.length) return null;
  const lines = material.body.split('\n');
  if (lines.length !== material.refs.length) return null;
  const chapters = [];
  for (let i = 0; i < lines.length; i++) {
    const prefix = `${i + 1}. `; if (!lines[i].startsWith(prefix)) return null;
    const encoded = lines[i].slice(prefix.length); let item;
    try { item = JSON.parse(encoded); } catch { return null; }
    const ref = material.refs[i], timed = ref.momentId !== undefined;
    if (!item || typeof item !== 'object' || Array.isArray(item) || JSON.stringify(item) !== encoded ||
        Object.keys(item).sort().join(',') !== (timed ? 'excerpt,label,momentId,sourceId,sourceRevision,sourceTitle' : 'label,sourceId,sourceRevision,sourceTitle') ||
        typeof item.label !== 'string' || !item.label.trim() || item.label !== item.label.trim() || item.label.length > 200 ||
        typeof item.sourceTitle !== 'string' || item.sourceTitle.length > 200 || item.sourceId !== ref.sourceId || item.sourceRevision !== ref.sourceRevision ||
        (timed && (item.momentId !== ref.momentId || typeof item.excerpt !== 'string' || item.excerpt.length > 1500))) return null;
    chapters.push({ref: structuredClone(ref), label: item.label});
  }
  return chapters;
}

function normalizeChoice(choice, scope) {
  if (!choice || !validRef(choice.ref, scope)) return null;
  if (choice.rightsState !== 'current' || choice.withdrawn === true || choice.eligible === false) {
    return { ref: choice.ref, eligible: false, reason: 'This reference is unavailable or no longer authorized.' };
  }
  const sourceTitle = typeof choice.sourceTitle === 'string' ? choice.sourceTitle : '';
  const excerpt = typeof choice.excerpt === 'string' ? choice.excerpt : '';
  return {
    ref: choice.ref,
    eligible: true,
    sourceTitle,
    excerpt,
    timing: choice.ref.momentId ? { startMs: choice.ref.startMs, endMs: choice.ref.endMs } : null,
    defaultLabel: typeof choice.label === 'string' ? choice.label : sourceTitle || 'Chapter'
  };
}

function validDraft(envelope, scope, request) {
  const result = envelope?.result;
  return result && result.requestId === request.requestId && result.state === 'committed' && typeof result.materialId === 'string' && !!result.materialId &&
    Number.isInteger(result.version) && result.version > 0 && Number.isInteger(result.objectRevision) && result.objectRevision >= 1 &&
    (request.version === null ? result.version === 1 : result.version === request.version + 1 && result.objectRevision > request.baseRevision) &&
    Array.isArray(result.refs) && same(result.refs, request.chapters.map(chapter => chapter.ref)) &&
    same(envelope.identity, request.identity) && same(envelope.identity, scope);
}

export function mountChapterDraft(root, host) {
  if (!(root instanceof Element) || !host || typeof host.getScope !== 'function') throw new TypeError('Chapter draft host is required.');
  let disposed = false, generation = 0, busy = false, currentDraft = null, pending = null;
  let scope = host.getScope(), choices = [], selected = [], operation = 0;

  const el = (tag, text) => { const node = document.createElement(tag); if (text != null) node.textContent = text; return node; };
  const heading = el('h2', 'Curate chapter draft');
  const notice = el('p', 'Choose authorized moments or source references, then arrange and label the chapters.');
  notice.setAttribute('role', 'status'); notice.setAttribute('aria-live', 'polite');
  const title = el('input'); title.maxLength = 200; title.required = true;
  const titleLabel = el('label', 'Edition title'); titleLabel.append(title);
  const sourceList = el('ul'); sourceList.className = 'w27-source-list';
  const selectedHeading = el('h3', 'Selected chapters');
  const selectedList = el('ol'); selectedList.className = 'w27-selected-list';
  const submit = el('button', 'Create Studio draft'); submit.type = 'button';
  const recover = el('button', 'Check original request'); recover.type = 'button';
  const open = el('button', 'Open existing Studio draft'); open.type = 'button';
  const actions = el('div'); actions.className = 'w27-actions'; actions.append(submit, recover, open);
  root.replaceChildren(heading, notice, titleLabel, el('h3', 'Available sources'), sourceList, selectedHeading, selectedList, actions);

  const scopeKey = value => JSON.stringify(canonical(value));
  let startingScope = scopeKey(scope);
  const active = ticket => !disposed && generation === ticket && scopeKey(host.getScope()) === startingScope && same(host.getScope(), scope);
  const setNotice = (text, alert = false) => { notice.textContent = text; notice.setAttribute('role', alert ? 'alert' : 'status'); };
  function currentSource(choice) {
    const fresh = choices.find(item => same(item.ref, choice.ref));
    return !!fresh && fresh.eligible && validRef(fresh.ref, scope);
  }
  function refreshButtons() {
    const creator = scope?.role === 'creator' && typeof scope.actorId === 'string' && !!scope.actorId;
    submit.textContent = currentDraft ? 'Save chapter as a new version' : 'Create Studio draft';
    submit.disabled = busy || !!pending || !creator || typeof host.createDraft !== 'function' || !title.value.trim() || selected.length < 1 || selected.length > MAX_CHAPTERS ||
      selected.some(item => !currentSource(item));
    recover.disabled = busy || !pending || typeof host.recover !== 'function';
    open.disabled = busy || !currentDraft || typeof host.openDraft !== 'function';
    title.disabled = busy;
    sourceList.querySelectorAll('button').forEach(button => { button.disabled = busy || button.textContent === 'Selected' || selected.length >= MAX_CHAPTERS; });
    selectedList.querySelectorAll('input').forEach(input => { input.disabled = busy; });
    selectedList.querySelectorAll('button').forEach(button => { button.disabled = busy || button.textContent === 'Move up' && Number(button.parentElement.dataset.index) === 0 || button.textContent === 'Move down' && Number(button.parentElement.dataset.index) === selected.length - 1; });
  }
  function selectedRefs() { return selected.map(item => item.ref); }

  function renderSources() {
    sourceList.replaceChildren();
    if (!choices.length) { sourceList.append(el('li', 'No source references are available.')); return; }
    for (const choice of choices) {
      const row = el('li');
      if (!choice.eligible) {
        row.append(el('span', 'Unavailable source. Its title and text are hidden.'), el('span', choice.reason));
      } else {
        const text = choice.ref.momentId
          ? `${choice.sourceTitle || 'Source'} · ${choice.timing.startMs}–${choice.timing.endMs} ms`
          : `${choice.sourceTitle || 'Source'} · untimed reference`;
        row.append(el('span', text));
        if (choice.excerpt) row.append(el('p', choice.excerpt));
        const add = el('button', selected.some(item => same(item.ref, choice.ref)) ? 'Selected' : 'Select');
        add.type = 'button'; add.disabled = busy || selected.some(item => same(item.ref, choice.ref)) || selected.length >= MAX_CHAPTERS;
        add.setAttribute('aria-label', `Select ${text}`);
        add.addEventListener('click', () => {
          if (add.disabled || !currentSource(choice)) return;
          selected.push({ ref: structuredClone(choice.ref), label: choice.defaultLabel, sourceDerivedLabel: true });
          renderSources(); renderSelected(); refreshButtons(); setNotice('Source selected. Review chapter order and labels before creating a draft.');
        });
        row.append(add);
      }
      sourceList.append(row);
    }
  }

  function renderSelected(focus = null) {
    selectedList.replaceChildren();
    selected.forEach((chapter, index) => {
      const row = el('li'); row.dataset.index = String(index);
      const source = choices.find(item => same(item.ref, chapter.ref));
      const sourceName = source?.eligible ? source.sourceTitle || 'Source' : 'Unavailable source';
      const timing = chapter.ref.momentId ? `${chapter.ref.startMs}–${chapter.ref.endMs} ms` : 'untimed';
      row.append(el('span', `${index + 1}. ${sourceName} · ${timing}`));
      if (!currentSource(chapter)) row.append(el('p', 'This source is unavailable or no longer authorized; remove it before continuing.'));
      const labelInput = el('input'); labelInput.value = chapter.label; labelInput.maxLength = 200; labelInput.required = true; labelInput.disabled = busy;
      labelInput.setAttribute('aria-label', `Chapter ${index + 1} label`);
      labelInput.addEventListener('input', () => { chapter.label = labelInput.value; chapter.sourceDerivedLabel = false; refreshButtons(); });
      row.append(labelInput);
      for (const [delta, text] of [[-1, 'Move up'], [1, 'Move down']]) {
        const button = el('button', text); button.type = 'button'; button.disabled = busy || index + delta < 0 || index + delta >= selected.length;
        button.setAttribute('aria-label', `${text} chapter ${index + 1}`); button.dataset.focus = `${index}:${delta}`;
        button.addEventListener('click', () => {
          if (button.disabled) return;
          const next = index + delta; [selected[index], selected[next]] = [selected[next], selected[index]];
          renderSelected(`${next}:${-delta}`); refreshButtons(); setNotice('Chapter order updated.');
        });
        row.append(button);
      }
      const remove = el('button', 'Remove'); remove.type = 'button'; remove.disabled = busy;
      remove.setAttribute('aria-label', `Remove chapter ${index + 1}`);
      remove.addEventListener('click', () => { selected.splice(index, 1); renderSelected(); renderSources(); refreshButtons(); });
      row.append(remove); selectedList.append(row);
    });
    if (focus) selectedList.querySelector(`[data-focus="${focus}"]`)?.focus();
  }

  function refreshChoices(nextChoices, nextScope = host.getScope()) {
    if (disposed) return false;
    generation++; operation++; busy = false;
    const identityChanged = !same(scope, nextScope);
    scope = structuredClone(nextScope); startingScope = scopeKey(scope);
    const normalized = Array.isArray(nextChoices) ? nextChoices.map(item => normalizeChoice(item, scope)).filter(Boolean) : [];
    choices = normalized;
    if (identityChanged) { selected = []; currentDraft = null; pending = null; title.value = ''; }
    else selected = selected.map(chapter => ({ ...chapter, ref: structuredClone(chapter.ref) }));
    for (const chapter of selected) {
      if (!currentSource(chapter) && chapter.sourceDerivedLabel) {
        // A source title is only a convenience default. Once its reference is
        // unavailable, remove that unauthorized text while preserving labels
        // the creator explicitly entered (including labels from an existing draft).
        chapter.label = 'Chapter';
        chapter.sourceDerivedLabel = false;
      }
    }
    renderSources(); renderSelected(); refreshButtons();
    if (identityChanged) setNotice('The active creator, session, source or grants changed. Review the available references again.');
    return true;
  }

  async function startCreate() {
    if (submit.disabled || typeof host.createRequestId !== 'function' || typeof host.createDraft !== 'function') return;
    const ticket = generation, selectedSnapshot = selected.map(chapter => ({ ref: structuredClone(chapter.ref), label: chapter.label.trim() }));
    if (!title.value.trim() || title.value.trim().length > 200 || selectedSnapshot.some(chapter => !chapter.label || chapter.label.length > 200) || selectedSnapshot.length > MAX_CHAPTERS) {
      setNotice('Each chapter needs a label of 1–200 characters.', true); return;
    }
    if (new Set(selectedSnapshot.map(chapter => JSON.stringify(canonical(chapter.ref)))).size !== selectedSnapshot.length) {
      setNotice('Each source can appear only once.', true); return;
    }
    const request = {
      requestId: host.createRequestId(), baseRevision: currentDraft ? currentDraft.revision : CREATE_BASE,
      materialId: currentDraft?.materialId ?? null, version: currentDraft?.version ?? null, title: title.value.trim(), chapters: selectedSnapshot,
      identity: structuredClone(scope)
    };
    if (typeof request.requestId !== 'string' || !request.requestId) { setNotice('A unique request could not be created.', true); return; }
    pending = structuredClone(request); currentDraft = null; busy = true; operation++; const op = operation; refreshButtons();
    setNotice('Requesting the Studio draft…');
    try {
      const envelope = await host.createDraft({ request: structuredClone({ requestId: request.requestId, baseRevision: request.baseRevision, materialId: request.materialId, version: request.version, title: request.title, chapters: request.chapters }), identity: structuredClone(request.identity) });
      if (!active(ticket) || operation !== op) return;
      const result = envelope?.result;
      if (result?.state === 'unknown') { setNotice('The original request result is unknown. Check that same request before trying again.', true); return; }
      if (result?.state === 'conflict') { setNotice('The Studio draft changed. Nothing was overwritten; reload its current version before editing.', true); return; }
      if (!validDraft(envelope, scope, request)) throw new Error('The Studio draft result did not match this request.');
      currentDraft = { materialId: result.materialId, version: result.version, revision: result.objectRevision, refs: structuredClone(result.refs) };
      pending = null; setNotice(`Studio draft saved at version ${result.version}. Approval and publication remain separate creator actions.`);
    } catch {
      if (active(ticket) && operation === op) setNotice('The Studio draft could not be confirmed. Check the original request before retrying.', true);
    } finally { if (active(ticket) && operation === op) { busy = false; refreshButtons(); } }
  }

  async function checkOriginal() {
    if (recover.disabled || !pending) return;
    const ticket = generation, original = structuredClone(pending); busy = true; operation++; const op = operation; refreshButtons();
    setNotice('Checking the original request…');
    try {
      const envelope = await host.recover({ requestId: original.requestId, identity: structuredClone(original.identity) });
      if (!active(ticket) || operation !== op || !pending || pending.requestId !== original.requestId) return;
      const result = envelope?.result;
      if (result?.state === 'unknown') { setNotice('The original request remains unknown. No new request was sent.', true); return; }
      if (result?.state === 'conflict') { setNotice('The original request conflicts with a different intent. Nothing was overwritten.', true); return; }
      if (!validDraft(envelope, scope, original)) throw new Error('Recovery result did not match original request.');
      currentDraft = { materialId: result.materialId, version: result.version, revision: result.objectRevision, refs: structuredClone(result.refs) };
      pending = null; setNotice(`Original request confirmed at Studio version ${result.version}.`);
    } catch { if (active(ticket) && operation === op) setNotice('The original request could not be confirmed. Its intent remains unchanged.', true); }
    finally { if (active(ticket) && operation === op) { busy = false; refreshButtons(); } }
  }

  async function openExisting() {
    if (open.disabled || !currentDraft) return;
    const ticket = generation, draft = structuredClone(currentDraft);
    try {
      const result = await host.openDraft({ materialId: draft.materialId, version: draft.version, revision: draft.revision, identity: structuredClone(scope) });
      if (!active(ticket)) return;
      if (!result || result.materialId !== draft.materialId || result.version !== draft.version || result.revision !== draft.revision || !same(result.identity, scope)) {
        setNotice('The exact Studio draft version is no longer available. Refresh its current state before opening.', true); return;
      }
      setNotice(`Opened existing Studio draft version ${draft.version}.`);
    } catch { if (active(ticket)) setNotice('The existing Studio draft is unavailable.'); }
  }

  title.addEventListener('input', refreshButtons);
  submit.addEventListener('click', startCreate); recover.addEventListener('click', checkOriginal); open.addEventListener('click', openExisting);
  renderSources(); renderSelected(); refreshButtons();
  return {
    update: refreshChoices,
    setDraft(draft, nextScope = host.getScope()) {
      if (disposed || !draft || typeof draft.materialId !== 'string' || !draft.materialId || !Number.isInteger(draft.version) || !Number.isInteger(draft.revision) || !same(nextScope, scope)) return false;
      if (!Array.isArray(draft.chapters) || draft.chapters.length < 1 || draft.chapters.length > MAX_CHAPTERS ||
          draft.chapters.some(chapter => !chapter || !validRef(chapter.ref, scope) || typeof chapter.label !== 'string' || !chapter.label.trim() || chapter.label.length > 200) ||
          new Set(draft.chapters.map(chapter => JSON.stringify(canonical(chapter.ref)))).size !== draft.chapters.length) return false;
      currentDraft = { materialId: draft.materialId, version: draft.version, revision: draft.revision, refs: Array.isArray(draft.refs) ? structuredClone(draft.refs) : [] };
      title.value = typeof draft.title === 'string' ? draft.title : '';
      selected = draft.chapters.map(chapter => ({ ref: structuredClone(chapter.ref), label: chapter.label, sourceDerivedLabel: false }));
      renderSources(); renderSelected();
      refreshButtons(); return true;
    },
    reset(nextScope = host.getScope()) { generation++; operation++; busy = false; scope = structuredClone(nextScope); startingScope = scopeKey(scope); selected = []; pending = null; currentDraft = null; title.value = ''; renderSources(); renderSelected(); refreshButtons(); },
    destroy() { if (disposed) return; disposed = true; generation++; operation++; root.replaceChildren(); },
    getSelection() { return selected.map(item => ({ ref: structuredClone(item.ref), label: item.label })); }
  };
}
