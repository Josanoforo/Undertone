const FIELDS = ['title', 'body'];

function validVersion(version) {
  return version && Number.isSafeInteger(version.revision) && version.revision >= 0 &&
    version.fields && typeof version.fields.title === 'string' &&
    typeof version.fields.body === 'string' && version.fields.title.length <= 200 &&
    version.fields.body.length <= 12000;
}

/** Pure view model. Every version must come from the authorized live conflict response. */
export function diffConflict({base, current, proposed} = {}) {
  if (!validVersion(base) || !validVersion(current) || !proposed?.fields ||
      typeof proposed.fields.title !== 'string' || typeof proposed.fields.body !== 'string' ||
      proposed.fields.title.length > 200 || proposed.fields.body.length > 12000 ||
      current.revision < base.revision) return null;
  return {
    baseRevision: base.revision,
    currentRevision: current.revision,
    fields: FIELDS.map(field => ({
      field,
      base: base.fields[field],
      current: current.fields[field],
      proposed: proposed.fields[field],
      changed: {
        current: current.fields[field] !== base.fields[field],
        proposed: proposed.fields[field] !== base.fields[field]
      }
    }))
  };
}

/**
 * Render a live, currently authorized conflict. `onResolve` receives chosen fields
 * and the current revision only after an explicit submit; it must use the host's
 * existing fresh-base/request/rights patch path. This component never saves or approves.
 */
export function mountConflictResolution(root, {scope, assertScope, conflict, onResolve} = {}) {
  const section = document.createElement('section'); section.className = 'w28-conflict';
  section.setAttribute('aria-labelledby', 'w28-conflict-heading');
  const heading = document.createElement('h2'); heading.id = 'w28-conflict-heading';
  heading.textContent = 'Resolve draft changes';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.tabIndex = -1;
  const content = document.createElement('div');
  section.append(heading, status, content); root.append(section);
  let generation = 0, activeScope = scope && {...scope}, model = null, selections = null, destroyed = false, submitted = false;
  const sameScope = (a,b) => !!a && !!b && a.sourceId === b.sourceId && a.sessionId === b.sessionId && a.actorId === b.actorId && a.role === b.role && a.revocationGeneration === b.revocationGeneration && a.draftId === b.draftId;
  const text = (tag, value) => { const el = document.createElement(tag); el.textContent = String(value); return el; };
  function clear(message) { generation++; model = null; selections = null; submitted = false; content.replaceChildren(); status.textContent = message; }
  function update(response, nextScope, ticket) {
    if (destroyed || ticket !== generation) return false;
    if (!sameScope(activeScope, nextScope) || nextScope?.role !== 'creator') { activeScope = nextScope && {...nextScope}; clear('Access or source changed. Conflict details are unavailable.'); return false; }
    if (typeof assertScope !== 'function') { clear('Conflict details unavailable until the host can verify current access.'); return false; }
    try { assertScope(nextScope); } catch (_) { clear('Access or source changed. Conflict details are unavailable.'); return false; }
    // A content-free receipt is deliberately insufficient; the host must pass both live versions.
    const next = diffConflict(response?.conflict);
    if (!next || response?.operation?.state !== 'conflict') {
      clear(response?.operation?.state === 'conflict' ? 'Conflict details unavailable. Refresh the draft.' : 'No live conflict details are available.');
      return false;
    }
    model = next; selections = {title: null, body: null}; submitted = false; render(); return true;
  }
  function render() {
    content.replaceChildren();
    if (!model || !selections) return;
    content.append(text('p', `Base revision ${model.baseRevision}; current revision ${model.currentRevision}. Choose a value for each field.`));
    for (const row of model.fields) {
      const group = document.createElement('fieldset');
      const legend = text('legend', row.field === 'title' ? 'Title' : 'Body'); group.append(legend);
      const base = document.createElement('p'); base.append(text('strong', 'Base version: '), text('span', row.base)); group.append(base);
      for (const choice of ['current', 'proposed']) {
        const id = `w28-${row.field}-${choice}`;
        const label = document.createElement('label'); label.htmlFor = id;
        const input = document.createElement('input'); input.type = 'radio'; input.name = `w28-${row.field}`; input.id = id; input.value = choice; input.checked = selections[row.field] === choice;
        input.addEventListener('change', () => { selections[row.field] = choice; submit.disabled = !FIELDS.every(field => selections[field]); });
        const value = text('span', row[choice]);
        label.append(input, text('strong', choice === 'current' ? 'Current version: ' : 'Proposed version: '), value);
        group.append(label);
      }
      content.append(group);
    }
    const submit = document.createElement('button'); submit.type = 'button'; submit.textContent = 'Use selected fields'; submit.disabled = submitted || !FIELDS.every(field => selections[field]);
    submit.addEventListener('click', () => {
      const epoch = generation, captured = activeScope;
      if (!model || submitted || !FIELDS.every(field => selections[field]) || typeof onResolve !== 'function') return;
      try { assertScope(captured); } catch (_) { clear('Access or source changed. Conflict details are unavailable.'); return; }
      if (epoch !== generation || !sameScope(captured, activeScope)) return;
      const selected = Object.fromEntries(FIELDS.map(field => [field, model.fields.find(row => row.field === field)[selections[field]]]));
      submitted = true; submit.disabled = true;
      try { onResolve({baseRevision: model.currentRevision, fields: selected}, captured); }
      catch (_) { submitted = false; submit.disabled = false; status.textContent = 'Selection was not submitted. Refresh the draft and choose again.'; return; }
      status.textContent = 'Selected values submitted for fresh revision and rights checks. Creator approval remains separate.';
    });
    content.append(submit);
    status.textContent = 'No changes have been submitted. Compare both versions and choose each field explicitly.';
  }
  return {
    update,
    getGeneration: () => generation,
    reset() { clear('Conflict details unavailable.'); },
    destroy() { clear('Conflict details unavailable.'); destroyed = true; section.remove(); }
  };
}
