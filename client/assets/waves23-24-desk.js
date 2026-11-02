/* Editorial desk component; all service access is supplied by the host. */
export function mount(root, context) {
  let generation = 0, editGeneration = 0, current = context, draft = null, dirty = false, pending = null, reading = false, confirmed = false, reconciling = false, saveTimer = null, conflict = false, operatorReference = null;
  const scope = c => JSON.stringify([c?.scopeId, c?.sessionId, c?.actorId, c?.sourceId, c?.profileId, c?.draftId, c?.segmentId, c?.eligible]);
  let key = scope(context);
  // Synchronous host journal stores only request metadata, scoped to this context.
  const journalUnavailable = () => ({kind:'journal_unavailable'});
  function journalEntry(entry) {
    if (!entry || typeof entry !== 'object' || typeof entry.requestId !== 'string' || !entry.requestId) return null;
    if (['patch','approve','withdraw','template'].includes(entry.kind)) return {kind:entry.kind, requestId:entry.requestId};
    if (entry.kind === 'adopt' && Number.isSafeInteger(entry.approvedRevision) && typeof entry.segmentId === 'string' && entry.segmentId) return {kind:entry.kind, requestId:entry.requestId, approvedRevision:entry.approvedRevision, segmentId:entry.segmentId};
    if (entry.kind === 'applyTemplate') {
      const a = entry.args;
      if (!a || a.requestId !== entry.requestId || typeof a.templateId !== 'string' || !a.templateId || !Number.isSafeInteger(a.version) || typeof a.targetDraftId !== 'string' || !a.targetDraftId || !Number.isSafeInteger(a.baseRevision) || (a.sourceSessionId !== undefined && typeof a.sourceSessionId !== 'string')) return null;
      return {kind:entry.kind, requestId:entry.requestId, args:{templateId:a.templateId, version:a.version, targetDraftId:a.targetDraftId, requestId:a.requestId, baseRevision:a.baseRevision, ...(a.sourceSessionId !== undefined ? {sourceSessionId:a.sourceSessionId} : {})}};
    }
    return null;
  }
  function restoreJournal() {
    try {
      if (!valid(current)) return;
      if (!current.intentJournal || typeof current.intentJournal.read !== 'function' || typeof current.intentJournal.write !== 'function' || typeof current.intentJournal.remove !== 'function') throw Error('Journal unavailable');
      const entry = current.intentJournal.read(key);
      if (entry != null) pending = journalEntry(entry) || journalUnavailable();
    } catch (_) { pending = journalUnavailable(); }
    if (pending) status.textContent = 'An action or its journal is unconfirmed. Check the original request before another action.';
  }
  function recordIntent(intent) {
    const entry = journalEntry(intent);
    try {
      if (!entry || !current.intentJournal) throw Error('Journal unavailable');
      current.intentJournal.write(key, entry);
      if (JSON.stringify(journalEntry(current.intentJournal.read(key))) !== JSON.stringify(entry)) throw Error('Journal verification failed');
      pending = entry;
      return true;
    } catch (_) { pending = journalUnavailable(); status.textContent = 'Action not sent: durable request journal unavailable. Reopen after storage is restored.'; return false; }
  }
  function resolveIntent() {
    try {
      current.intentJournal.remove(key);
      if (current.intentJournal.read(key) != null) throw Error('Journal removal failed');
      pending = null;
      return true;
    } catch (_) { status.textContent = 'Action status found, but its journal could not be cleared. Check again before another action.'; return false; }
  }
  const valid = c => Boolean(c?.eligible && c?.sessionId && c?.actorId && c?.draftId);
  const signedIn = c => Boolean(c?.sessionId && c?.actorId);
  const el = (tag, text) => { const n = document.createElement(tag); if (text) n.textContent = text; return n; };
  const section = document.createElement('section');
  section.className = 'editorial-desk';
  const heading = document.createElement('h2');
  heading.textContent = 'Editorial desk';
  const note = document.createElement('p');
  note.textContent = 'Drafts and handoffs require current access and an available connection.';
  const status = document.createElement('p');
  status.setAttribute('role', 'status');
  status.textContent = 'Editorial handoff is unavailable.';
  const titleLabel = el('label', 'Title');
  const title = el('input'); title.maxLength = 200; titleLabel.append(title);
  const bodyLabel = el('label', 'Body');
  const body = el('textarea'); body.maxLength = 12000; bodyLabel.append(body);
  const comparison = el('div'); comparison.className = 'editorial-desk-comparison';
  const proposal = el('div'); proposal.append(el('h3', 'Your proposed edit'), titleLabel, bodyLabel);
  const saved = el('div');
  const remote = el('pre'); remote.setAttribute('aria-label', 'Current saved version');
  saved.append(el('h3', 'Current saved version'), remote);
  comparison.append(proposal, saved);
  const details = el('p');
  const templateIdLabel = el('label', 'Template ID');
  const templateId = el('input'); templateIdLabel.append(templateId);
  const templateVersionLabel = el('label', 'Template version');
  const templateVersion = el('input'); templateVersion.type = 'number'; templateVersion.min = '1'; templateVersionLabel.append(templateVersion);
  const sourceSessionLabel = el('label', 'Source session ID (for cross-session reuse)');
  const sourceSession = el('input'); sourceSessionLabel.append(sourceSession);
  const controls = el('div');
  function button(label, action) { const b = el('button', label); b.type = 'button'; b.addEventListener('click', action); controls.append(b); return b; }
  function clear() { clearTimeout(saveTimer); saveTimer = null; draft = null; dirty = false; pending = null; confirmed = false; reconciling = false; conflict = false; operatorReference = null; title.disabled = body.disabled = false; title.value = ''; body.value = ''; remote.textContent = ''; details.textContent = ''; templateId.value = ''; templateVersion.value = ''; sourceSession.value = ''; }
  function revoke() { generation++; reading = false; clear(); if (valid(current)) restoreJournal(); }
  function accessEnded(error) { return error?.rightsLost === true || [401, 403, 404, 410].includes(error?.status); }
  function rejected(error) { return [400, 422].includes(error?.status) || (error?.status === 409 && ['version_conflict', 'stale_revision', 'request_conflict', 'stale_context'].includes(error?.code)); }
  function show(d, preserve) {
    if (!d || d.draftId !== current.draftId || !Number.isSafeInteger(d.revision) || typeof d.content?.title !== 'string' || typeof d.content?.body !== 'string') throw Error('Invalid draft');
    draft = d; remote.textContent = `Title: ${d.content.title}\n\n${d.content.body}`;
    details.textContent = `Saved revision ${d.revision}; approval: ${d.approvedRevision === d.revision ? 'approved' : 'not approved'}. Present: ${(d.presence || []).map(p => p.actorId).join(', ') || 'none reported'}.`;
    if (!preserve) { title.value = d.content.title; body.value = d.content.body; dirty = false; }
  }
  async function read() {
    if (!valid(current) || typeof current.readDraft !== 'function') { clear(); status.textContent = 'Draft unavailable.'; return; }
    if (reading || pending) return;
    confirmed = false;
    remote.textContent = ''; details.textContent = '';
    reading = true;
    const epoch = generation, c = current, edits = editGeneration, previousRevision = draft?.revision;
    try { const result = await c.readDraft({draftId:c.draftId, cursor:0, schemaVersion:1}); if (epoch !== generation) return; show(result.draft, dirty || edits !== editGeneration); confirmed = true; conflict ||= dirty && previousRevision !== undefined && previousRevision !== draft.revision; if (conflict) { clearTimeout(saveTimer); saveTimer = null; } status.textContent = conflict ? 'Saved version changed. Compare your edit and save explicitly.' : dirty ? 'Current saved version loaded beside your unsaved edit.' : 'Draft loaded.'; if (dirty && !conflict && !saveTimer) scheduleSave(); }
    catch (error) { if (epoch === generation) { if (accessEnded(error)) { revoke(); status.textContent = 'Access ended; draft content cleared.'; } else status.textContent = 'Connection unavailable. Your unsaved edit remains in this window; reconnect to review current access.'; } }
    finally { if (epoch === generation) reading = false; }
  }
  function scheduleSave() { clearTimeout(saveTimer); saveTimer = null; if (conflict) return; const epoch = generation; saveTimer = setTimeout(() => { saveTimer = null; if (epoch === generation && dirty && confirmed && !pending && !reading) mutate('patch'); }, 1000); }
  function edited() { editGeneration++; dirty = true; status.textContent = 'Unsaved edit. Approval applies only to a saved revision.'; scheduleSave(); }
  title.addEventListener('input', edited); body.addEventListener('input', edited);
  async function mutate(kind) {
    clearTimeout(saveTimer); saveTimer = null;
    if (!valid(current) || !draft || !confirmed || pending || reading || typeof current[kind] !== 'function') { status.textContent = 'Refresh current access first, or reconcile the unconfirmed action.'; return; }
    if (kind !== 'patch' && (dirty || draft.approvedRevision !== draft.revision && kind === 'adopt')) { status.textContent = 'Save and review the exact revision first.'; return; }
    const epoch = generation, edits = editGeneration, c = current;
    const requestId = crypto.randomUUID();
    if (kind === 'adopt' && (typeof c.segmentId !== 'string' || !c.segmentId)) { status.textContent = 'The approved segment is unavailable; select it before handoff.'; return; }
    const payload = kind === 'patch' ? {requestId, baseRevision:draft.revision, operations:[{field:'title',value:title.value},{field:'body',value:body.value}]} : kind === 'adopt' ? {requestId, approvedRevision:draft.revision, segmentId:c.segmentId} : {requestId, expectedRevision:draft.revision};
    if (!recordIntent({kind, requestId, ...(kind === 'adopt' ? {approvedRevision:payload.approvedRevision, segmentId:payload.segmentId} : {})})) return;
    title.disabled = body.disabled = true;
    try {
      let result;
      try { result = await c[kind]({draftId:c.draftId, ...payload}); }
      catch (error) { if (error?.status === 409 && error?.result?.operation?.state === 'conflict') result = error.result; else throw error; }
      if (epoch !== generation) return;
      if (result?.operation?.state === 'conflict' && result.draft) { show(result.draft, true); if (!resolveIntent()) return; conflict = true; status.textContent = 'Conflict: compare your edit with the saved version. Edit your proposal, then save explicitly.'; return; }
      if (result?.operation?.state !== 'committed') throw Error('Unconfirmed');
      if (kind === 'adopt' && (result.operation.requestId !== requestId || result.snapshot?.draftId !== c.draftId || result.snapshot?.revision !== payload.approvedRevision || result.snapshot?.segmentId !== payload.segmentId)) throw Error('Unconfirmed handoff');
      if (kind === 'adopt') { const ref = result.operatorReference; operatorReference = ref && ref.segmentId === payload.segmentId && typeof ref.materialId === 'string' && Number.isSafeInteger(ref.materialVersion) ? {segmentId:ref.segmentId, materialId:ref.materialId, materialVersion:ref.materialVersion} : null; }
      else operatorReference = null;
      if (!resolveIntent()) return;
      if (kind === 'withdraw') { revoke(); status.textContent = 'Draft withdrawn.'; return; }
      if (kind === 'patch' && edits === editGeneration) { dirty = false; conflict = false; }
      await read();
      if (epoch === generation && confirmed) status.textContent = kind === 'adopt' ? 'Approved revision adopted. Continue in the operator queue.' : 'Action confirmed; review the current saved revision.';
    } catch (error) { if (epoch === generation) { confirmed = false; if (accessEnded(error)) { revoke(); status.textContent = 'Access ended; draft content cleared. The original action remains unconfirmed.'; } else if (rejected(error)) { if (!resolveIntent()) return; conflict = true; status.textContent = 'Action rejected. Refresh and review the saved revision before trying again.'; } else status.textContent = 'Action unconfirmed. Check its original request before another action.'; } }
    finally { if (epoch === generation) title.disabled = body.disabled = false; }
  }
  button('Refresh saved version', read);
  button('Show my presence', async () => {
    if (!valid(current) || typeof current.presence !== 'function') { status.textContent = 'Presence unavailable.'; return; }
    const epoch = generation, c = current;
    try { await c.presence({draftId:c.draftId, seconds:60}); if (epoch === generation) { status.textContent = 'Presence updated; refresh for current participants.'; } }
    catch (error) { if (epoch === generation) { if (accessEnded(error)) { revoke(); status.textContent = 'Access ended; draft content cleared.'; } else status.textContent = 'Presence unavailable.'; } }
  });
  button('Check unconfirmed action', async () => {
    if (!signedIn(current) || !pending || reconciling) { status.textContent = 'Action status is unavailable or already being checked.'; return; }
    const epoch = generation, c = current, intent = pending;
    reconciling = true;
    try {
      let result;
      if (intent.kind === 'adopt' && typeof c.recoverAdoption === 'function') result = await c.recoverAdoption({draftId:c.draftId, requestId:intent.requestId, approvedRevision:intent.approvedRevision, segmentId:intent.segmentId});
      else if (intent.kind === 'template' && typeof c.readTemplateOperation === 'function') result = await c.readTemplateOperation({requestId:intent.requestId});
      else if (intent.kind === 'applyTemplate' && typeof c.recoverTemplateApplication === 'function') result = await c.recoverTemplateApplication(intent.args);
      else if (['patch', 'approve', 'withdraw'].includes(intent.kind) && typeof c.readCoeditOperation === 'function') result = await c.readCoeditOperation({draftId:c.draftId, requestId:intent.requestId});
      else { status.textContent = 'No metadata-only recovery is available for this action. Keep this window open and consult the operator.'; return; }
      if (epoch !== generation || pending !== intent) return;
      const state = result?.operation?.state;
      if (['patch', 'approve', 'withdraw'].includes(intent.kind) && (result?.operation?.action !== intent.kind || !['committed', 'conflict'].includes(state))) { status.textContent = 'Action remains unconfirmed; no automatic retry was made.'; return; }
      if (!['committed', 'conflict', 'not_committed'].includes(state)) { status.textContent = 'Action remains unconfirmed; no automatic retry was made.'; return; }
      if (!resolveIntent()) return; if (state === 'conflict') conflict = true;
      if (intent.kind === 'withdraw' && state === 'committed') { revoke(); status.textContent = 'Draft withdrawn.'; return; }
      if (intent.kind === 'patch' && state === 'committed') { conflict = dirty; }
      if (intent.kind === 'template' && state === 'committed') { templateId.value = result.templateId; templateVersion.value = String(result.version); }
      await read();
      if (epoch === generation && confirmed) status.textContent = state === 'conflict' ? 'Conflict confirmed. Compare your edit with the saved version before saving.' : `Action ${state.replace('_', ' ')}. Review the saved version.`;
    } catch (error) { if (epoch === generation) { if (accessEnded(error)) { revoke(); pending = intent; status.textContent = 'Action status or access is unavailable; draft content cleared. The original action remains unconfirmed.'; } else status.textContent = 'Action remains unconfirmed.'; } }
    finally { if (epoch === generation) reconciling = false; }
  });
  button('Save edit', () => mutate('patch'));
  button('Approve saved revision', () => mutate('approve'));
  button('Adopt approved revision', () => mutate('adopt'));
  button('Open operator queue', async () => {
    if (!valid(current) || typeof current.openOperator !== 'function') { status.textContent = 'Operator queue unavailable.'; return; }
    const epoch = generation;
    try { await current.openOperator({draftId:current.draftId, ...(operatorReference ? {operatorReference:{...operatorReference}} : {})}); if (epoch === generation) status.textContent = 'Operator queue opened; use its current approval and presentation controls.'; }
    catch (_) { if (epoch === generation) status.textContent = 'Operator queue unavailable.'; }
  });
  button('Withdraw draft', () => mutate('withdraw'));
  async function templateAction(action) {
    if (!signedIn(current) || pending || reading || (action !== 'withdraw' && (!valid(current) || !draft || !confirmed || dirty))) { status.textContent = 'Save and refresh the current draft first.'; return; }
    const version = Number(templateVersion.value), id = templateId.value.trim(), source = sourceSession.value.trim();
    if (action !== 'create' && (!id || !Number.isSafeInteger(version) || version < 1)) { status.textContent = 'Enter a template ID and version.'; return; }
    if ((action === 'create' || action === 'update') && draft.approvedRevision !== draft.revision) { status.textContent = 'Approve the exact saved revision first.'; return; }
    const requestId = crypto.randomUUID(), epoch = generation, c = current;
    let args, callback;
    if (action === 'apply') {
      args = {templateId:id, version, targetDraftId:c.draftId, requestId, baseRevision:draft.revision, ...(source ? {sourceSessionId:source} : {})};
      callback = c.applyDraftTemplate;
    } else {
      args = action === 'create' ? {action, requestId, expectedRevision:0, draftId:c.draftId, approvedRevision:draft.revision} : action === 'update' ? {action, requestId, expectedRevision:version, templateId:id, draftId:c.draftId, approvedRevision:draft.revision} : {action, requestId, expectedRevision:version, templateId:id};
      callback = c.mutateDraftTemplate;
    }
    if (typeof callback !== 'function') { status.textContent = 'Template operation unavailable.'; return; }
    if (!recordIntent(action === 'apply' ? {kind:'applyTemplate', requestId, args} : {kind:'template', requestId})) return;
    title.disabled = body.disabled = true;
    try {
      let result;
      try { result = await callback(args); }
      catch (error) { if (error?.status === 409 && error?.result?.operation?.state === 'conflict') result = error.result; else throw error; }
      if (epoch !== generation) return;
      if (result?.operation?.state === 'conflict' && result.draft) { show(result.draft, true); if (!resolveIntent()) return; conflict = true; status.textContent = 'Template application conflicted. Compare the saved version before editing.'; return; }
      if (result?.operation?.state !== 'committed' || (action !== 'apply' && result.operation.requestId !== requestId)) throw Error('Unconfirmed');
      if (!resolveIntent()) return;
      if (action !== 'apply') { templateId.value = result.templateId; templateVersion.value = String(result.version); }
      if (action !== 'withdraw') await read();
      if (epoch === generation && (confirmed || action === 'withdraw')) status.textContent = action === 'apply' ? 'Template applied as an editable revision; approve it separately.' : action === 'withdraw' ? 'Template withdrawn.' : 'Template operation confirmed.';
    } catch (error) { if (epoch === generation) { confirmed = false; if (accessEnded(error)) { revoke(); status.textContent = 'Access ended; draft content cleared. The original action remains unconfirmed.'; } else if (rejected(error)) { if (!resolveIntent()) return; conflict = true; status.textContent = 'Template action rejected. Refresh and review before trying again.'; } else status.textContent = 'Template action unconfirmed. Check its original request before another action.'; } }
    finally { if (epoch === generation) title.disabled = body.disabled = false; }
  }
  button('Create template from approved revision', () => templateAction('create'));
  button('Update template from approved revision', () => templateAction('update'));
  button('Apply template to this draft', () => templateAction('apply'));
  button('Withdraw template', () => templateAction('withdraw'));
  section.append(heading, note, status, details, comparison, templateIdLabel, templateVersionLabel, sourceSessionLabel, controls);
  root.append(section);
  if (valid(context)) { restoreJournal(); read(); }
  return {
    update(next) { const nextKey = scope(next); current = next; if (key !== nextKey || !valid(next)) { generation++; reading = false; clear(); key = nextKey; if (valid(next)) restoreJournal(); } if (valid(next)) read(); else status.textContent = 'Draft unavailable.'; },
    destroy() { generation++; clear(); current = null; section.remove(); }
  };
}
