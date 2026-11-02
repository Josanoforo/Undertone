/* Explicit handoff status; authenticated authority and durable journal are host supplied. */
export function mount(root, context) {
  let c = context, generation = 0, pending = null, view = null, busy = false, destroyed = false;
  const scope = x => JSON.stringify([x?.scopeId,x?.sessionId,x?.actorId,x?.creatorId,x?.collaboratorId,x?.sourceId,x?.sourceRevision,x?.draftId,x?.revision,x?.grantGeneration,x?.eligible]);
  let key = scope(c);
  const valid = x => !!(x?.eligible && x.sessionId && x.actorId && x.draftId && Number.isSafeInteger(x.revision));
  const make = (tag, label) => { const e = document.createElement(tag); if (label) e.textContent = label; return e; };
  const section = make('section'); section.className = 'handoff28';
  const heading = make('h2','Handoff'); const details = make('p'); const reasons = make('ul');
  const notice = make('p'); notice.setAttribute('role','status');
  const dueLabel = make('label','Due next'); const due = make('input'); due.maxLength = 80; dueLabel.append(due);
  const ownerLabel = make('label','Offer to'); const owner = make('select'); ownerLabel.append(owner);
  const clearReasonsLabel = make('label','Send no reasons for this action (replaces displayed reasons)');
  const clearReasons = make('input'); clearReasons.type = 'checkbox'; clearReasonsLabel.append(clearReasons);
  const selection = make('fieldset'); const legend = make('legend','Choose a current draft source for each of your reasons'); selection.append(legend);
  let reasonSelectors = [];
  const controls = make('div');
  function button(label, fn) { const b = make('button',label); b.type = 'button'; b.addEventListener('click',fn); controls.append(b); return b; }
  const refresh = button('Refresh', load), offer = button('Offer', () => act('offer'));
  const accept = button('Accept', () => act('accept')), back = button('Return', () => act('return'));
  const complete = button('Complete handoff', () => act('complete')), recover = button('Check original request', reconcile);
  section.append(heading, details, reasons, dueLabel, ownerLabel, selection, clearReasonsLabel, controls, notice); root.append(section);
  function enabled() {
    const ready = valid(c) && !busy && !pending && view?.revision === c.revision && typeof view?.statusVersion === 'string' && !!view.statusVersion;
    const creator = c.actorId === c.creatorId, assigned = view?.owner === c.actorId;
    refresh.disabled = !valid(c) || busy || !!pending;
    offer.disabled = !valid(c) || busy || !!pending || !creator || !view || typeof view.statusVersion !== 'string' || !view.statusVersion || typeof c.offerHandoff !== 'function';
    accept.disabled = !ready || !assigned || view.status !== 'offered';
    back.disabled = !ready || !assigned || !['offered','accepted'].includes(view?.status);
    complete.disabled = !ready || !creator || view?.status !== 'accepted';
    recover.disabled = !valid(c) || busy || !pending || pending.kind !== 'handoff28';
    due.disabled = owner.disabled = !valid(c) || busy || !!pending || !creator;
    clearReasons.disabled = !valid(c) || busy || !!pending;
    selection.disabled = !valid(c) || busy || !!pending;
  }
  function restore() {
    pending = null;
    if (!valid(c)) return;
    try {
      if (!c.intentJournal || !['read','write','remove'].every(k => typeof c.intentJournal[k] === 'function')) throw Error();
      const p = c.intentJournal.read(key);
      if (p != null) pending = p.kind === 'handoff28' && typeof p.requestId === 'string' && p.requestId && Number.isSafeInteger(p.expectedRevision) && ['offer','accept','return','complete'].includes(p.action) ? {kind:p.kind,requestId:p.requestId,expectedRevision:p.expectedRevision,action:p.action} : {kind:'unavailable'};
    } catch (_) { pending = {kind:'unavailable'}; }
    if (pending) notice.textContent = 'An original request is unconfirmed. Check it before another action.';
  }
  function clearJournal() {
    try { c.intentJournal.remove(key); if (c.intentJournal.read(key) != null) throw Error(); pending = null; return true; }
    catch (_) { notice.textContent = 'The request was resolved but its journal could not be cleared.'; return false; }
  }
  function clear() { view = null; details.textContent = ''; reasons.replaceChildren(); selection.replaceChildren(legend); reasonSelectors = []; due.value = ''; owner.replaceChildren(); clearReasons.checked = false; }
  function choices() { owner.replaceChildren(); for (const id of [...new Set([c.creatorId,c.collaboratorId].filter(Boolean))]) { const o = make('option',id); o.value = id; owner.append(o); } }
  function render(v) {
    clearReasons.checked = false;
    selection.replaceChildren(legend);
    reasonSelectors = [];
    if (!v || v.draftId !== c.draftId || typeof v.statusVersion !== 'string' || !v.statusVersion) throw Error('Invalid handoff');
    if (v.ownReasons !== undefined || v.draftSources !== undefined) {
      if (!Array.isArray(v.ownReasons) || !Array.isArray(v.draftSources) || v.ownReasons.some(r => !r || typeof r.id !== 'string' || !Number.isSafeInteger(r.revision)) || v.draftSources.some(s => !s || typeof s !== 'object' || Array.isArray(s))) throw Error('Invalid candidates');
      for (const reason of v.ownReasons) {
        const label = make('label', `Reason ${reason.id}, revision ${reason.revision}: `), select = make('select');
        const blank = make('option','Do not include'); blank.value = ''; select.append(blank);
        v.draftSources.forEach((source, index) => { const option = make('option', JSON.stringify(source)); option.value = String(index + 1); select.append(option); });
        label.append(select); selection.append(label); reasonSelectors.push({reason, select});
      }
    }
    if (v.status === null || v.status === 'stale') {
      view = {...v};
      details.textContent = v.status === null ? 'No handoff has been offered.' : 'Previous handoff is stale; offer the current revision.';
      reasons.replaceChildren(); due.value = ''; choices(); return;
    }
    if (v.revision !== c.revision || !['offered','accepted','returned','completed'].includes(v.status) || typeof v.owner !== 'string' || !Array.isArray(v.reasonRefs)) throw Error('Invalid handoff');
    if (v.selectableReasonRefs !== undefined && !Array.isArray(v.selectableReasonRefs)) throw Error('Invalid reasons');
    view = {...v}; details.textContent = `Revision ${v.revision} · Current owner: ${v.owner} · Status: ${v.status} · Due next: ${v.dueNext || 'Not specified'}`;
    for (const [index, r] of (v.ownReasons ? [] : (v.selectableReasonRefs || [])).entries()) {
      const label = make('label', `Reason ${r.id}, revision ${r.revision}; source ${JSON.stringify(r.sourceRef)}`);
      const input = make('input'); input.type = 'checkbox'; input.value = String(index); label.append(input); selection.append(label);
    }
    reasons.replaceChildren(); for (const r of v.reasonRefs) reasons.append(make('li', `Reason ${r.id}, revision ${r.revision}; source ${JSON.stringify(r.sourceRef)}`));
    due.value = v.dueNext || ''; choices();
    if ([c.creatorId,c.collaboratorId].includes(v.owner)) owner.value = v.owner;
  }
  function lost(e) { return e?.rightsLost === true || [401,403,404,410].includes(e?.status); }
  function reject(e) { return [400,422].includes(e?.status) || (e?.status === 409 && ['version_conflict','status_conflict','stale_revision','request_conflict','stale_context'].includes(e?.code)); }
  function invalidate(message) { generation++; busy = false; clear(); choices(); restore(); notice.textContent = message; enabled(); }
  async function load() {
    if (!valid(c) || pending || busy || typeof c.viewHandoff !== 'function') return;
    busy = true; enabled(); const epoch = generation, host = c;
    try { const v = await host.viewHandoff({draftId:host.draftId}); if (epoch !== generation || destroyed) return; render(v); notice.textContent = 'Current handoff loaded. Approval and adoption are separate.'; }
    catch (e) { if (epoch === generation && !destroyed) { clear(); choices(); notice.textContent = lost(e) ? 'Handoff is unavailable or not yet offered; current access is required to offer.' : 'Handoff unavailable; refresh after reconnecting.'; } }
    finally { if (epoch === generation && !destroyed) { busy = false; enabled(); } }
  }
  async function act(action) {
    if (busy || pending || !valid(c) || !view || typeof view.statusVersion !== 'string' || !view.statusVersion || (action !== 'offer' && view.revision !== c.revision)) return;
    if ((action === 'offer' && (c.actorId !== c.creatorId || !owner.value)) || (['accept','return'].includes(action) && (view.owner !== c.actorId || !(action === 'accept' ? view.status === 'offered' : ['offered','accepted'].includes(view.status)))) || (action === 'complete' && (c.actorId !== c.creatorId || view.status !== 'accepted'))) return;
    const callback = action === 'offer' ? c.offerHandoff : c.decideHandoff;
    if (typeof callback !== 'function' || typeof c.newRequestId !== 'function') { notice.textContent = 'Handoff action is unavailable.'; return; }
    let refs;
    if (clearReasons.checked) refs = [];
    else if (Array.isArray(view.ownReasons) && Array.isArray(view.draftSources)) {
      refs = reasonSelectors.filter(x => x.select.value !== '').map(x => ({...x.reason,sourceRef:view.draftSources[Number(x.select.value)-1]}));
      if (!refs.length) { notice.textContent = 'Choose a source for your reasons or explicitly choose no reasons; either replaces displayed reasons.'; return; }
    }
    else if (Array.isArray(view.selectableReasonRefs)) {
      refs = [...selection.querySelectorAll('input:checked')].map(input => view.selectableReasonRefs[Number(input.value)]);
      if (!refs.length) { notice.textContent = 'Select your reasons or explicitly choose to send no reasons; either replaces displayed reasons.'; return; }
    } else refs = typeof c.currentReasonRefs === 'function' ? c.currentReasonRefs() : null;
    if (!Array.isArray(refs) || refs.length > 20 || refs.some(r => !r || typeof r.id !== 'string' || !Number.isSafeInteger(r.revision) || !r.sourceRef || typeof r.sourceRef !== 'object' || Array.isArray(r.sourceRef))) { notice.textContent = 'Select current source-backed reasons before acting.'; return; }
    const requestId = c.newRequestId(); if (typeof requestId !== 'string' || !requestId) return;
    const record = {kind:'handoff28',requestId,expectedRevision:c.revision,action};
    try { c.intentJournal.write(key,record); if (JSON.stringify(c.intentJournal.read(key)) !== JSON.stringify(record)) throw Error(); pending = record; }
    catch (_) { pending = {kind:'unavailable'}; notice.textContent = 'Action not sent: request journal unavailable.'; enabled(); return; }
    busy = true; enabled(); const epoch = generation, host = c;
    const args = {draftId:c.draftId,requestId,expectedRevision:c.revision,expectedStatusVersion:view.statusVersion,reasonRefs:refs.map(r => ({id:r.id,revision:r.revision,sourceRef:r.sourceRef})), ...(action === 'offer' ? {owner:owner.value,dueNext:due.value.trim() || null} : {action})};
    try { const result = await callback(args); if (epoch !== generation || destroyed) return; if (result?.operation?.requestId !== requestId || result.operation.state !== 'committed' || result.operation.action !== action || result.operation.revision !== record.expectedRevision) throw Error('Unconfirmed'); if (clearJournal()) { clearReasons.checked = false; notice.textContent = 'Handoff updated. Refresh to see current status.'; view = null; details.textContent = ''; reasons.replaceChildren(); } }
    catch (e) { if (epoch === generation && !destroyed) { if (reject(e)) { if (clearJournal()) { clear(); notice.textContent = 'Request rejected or conflicted; refresh current revision.'; } } else { if (lost(e)) clear(); notice.textContent = 'Result unknown or access ended. Check the original request; no action was retried.'; } } }
    finally { if (epoch === generation && !destroyed) { busy = false; enabled(); } }
  }
  async function reconcile() {
    if (!pending || pending.kind !== 'handoff28' || busy || typeof c.readHandoffReceipt !== 'function') return;
    const original = pending, host = c, epoch = generation; busy = true; enabled();
    try { const r = await host.readHandoffReceipt({draftId:host.draftId,requestId:original.requestId}); if (epoch !== generation || destroyed) return; const op = r?.operation; if (op?.requestId !== original.requestId || op.state !== 'committed' || op.action !== original.action || op.revision !== original.expectedRevision) throw Error('Unconfirmed'); if (clearJournal()) { clear(); notice.textContent = 'Original request confirmed. Refresh current handoff.'; } }
    catch (e) { if (epoch === generation && !destroyed) { if (lost(e)) clear(); notice.textContent = 'Original receipt is unavailable or access ended; the request remains unconfirmed.'; } }
    finally { if (epoch === generation && !destroyed) { busy = false; enabled(); } }
  }
  choices(); restore(); notice.textContent ||= 'Refresh to load the current handoff.'; enabled();
  return { update(next) { const nextKey = scope(next); c = next; if (nextKey !== key) { key = nextKey; invalidate('Context changed. Refresh current handoff.'); } else enabled(); }, destroy() { generation++; destroyed = true; section.remove(); } };
}


