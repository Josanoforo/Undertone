// APIs are injected; this component never constructs routes or changes creator truth.
export function mountClaims(root, {scope, api = {}, actions = {}, pending: initialPending = null}) {
  const box = document.createElement('section'); box.className = 'w22-claims';
  const title = document.createElement('h2'); title.textContent = 'Changed and disputed claims';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.setAttribute('tabindex', '-1');
  const content = document.createElement('div'); box.append(title, status, content); root.append(box);
  let currentScope = scope, epoch = 0, destroyed = false, pending = initialPending, busy = false;
  const el = (tag, value) => { const n = document.createElement(tag); if (value != null) n.textContent = String(value); return n; };
  const button = (parent, label, handler) => { const b = el('button', label); b.type = 'button'; b.addEventListener('click', handler); parent.append(b); return b; };
  const scopeKey = s => JSON.stringify([s?.sessionId, s?.actorId, s?.generation]);
  const clear = () => content.replaceChildren();
  function reset() { epoch++; busy = false; clear(); status.textContent = ''; }
  function recoveryControl() {
    if (!pending) return;
    content.append(el('p', 'A private action is unconfirmed. Check its authoritative result before another change.'));
    button(content, 'Check previous action', async () => {
      if (busy || typeof api.recover !== 'function' || scopeKey(currentScope) !== pending.scopeKey) { status.textContent = 'Authoritative recovery is unavailable for this session.'; return; }
      const g = epoch, operation = pending; busy = true; clear(); status.textContent = 'Checking the previous action…';
      try {
        const result = await api.recover({scope:currentScope, requestId:operation.requestId, claimId:operation.claimId, kind:operation.kind});
        if (g !== epoch || operation !== pending) return;
        if (result?.status === 'committed' || result?.status === 'rejected') {
          await actions.clearPending({...operation, scope:currentScope});
          if (g !== epoch || operation !== pending) return;
          pending = null; status.textContent = result.status === 'committed' ? 'Private action confirmed. Refresh current claims.' : 'Private action was rejected. Refresh current claims.';
          if (typeof actions.refresh === 'function') actions.refresh({scope:currentScope});
        } else { status.textContent = 'The action is still unconfirmed.'; recoveryControl(); }
      } catch { if (g === epoch) { status.textContent = 'Recovery is unavailable. The action remains unconfirmed.'; recoveryControl(); } }
      finally { if (g === epoch) busy = false; }
    });
  }
  async function mutate(kind, claim, text) {
    if (busy || pending || typeof api[kind] !== 'function' || typeof api.recover !== 'function' || typeof actions.rememberPending !== 'function' || typeof actions.clearPending !== 'function') { status.textContent = 'Private changes are unavailable until safe recovery is connected.'; return; }
    if (!globalThis.crypto?.randomUUID) { status.textContent = 'A safe request identifier is unavailable. No change was sent.'; return; }
    const g = ++epoch, s = currentScope;
    pending = {kind, claimId:claim.id, requestId:globalThis.crypto.randomUUID(), scopeKey:scopeKey(s)};
    const operation = pending; busy = true; clear(); status.textContent = 'Saving private change…'; status.focus();
    try {
      try { await actions.rememberPending({...operation, scope:s}); } catch { if (g === epoch && operation === pending) { pending = null; status.textContent = 'Recovery could not be prepared. No change was sent.'; } return; }
      if (g !== epoch || operation !== pending) return;
      const result = await api[kind]({scope:s, claimId:claim.id, expectedRevision:claim.revision, requestId:operation.requestId, ...(kind === 'correctPrivate' ? {text} : {})});
      if (g !== epoch || operation !== pending) return;
      if (result?.status !== 'committed' && result?.status !== 'rejected') throw new Error('unconfirmed');
      await actions.clearPending({...operation, scope:s});
      if (g !== epoch || operation !== pending) return;
      pending = null; status.textContent = result.status === 'committed' ? 'Private change confirmed. Refresh current claims.' : 'Private change was rejected or conflicted. Refresh current claims.';
      if (typeof actions.refresh === 'function') actions.refresh({scope:s});
    } catch { if (g === epoch && operation === pending) { status.textContent = 'The result is unconfirmed. Check the previous action before retrying.'; recoveryControl(); } }
    finally { if (g === epoch) busy = false; }
  }
  function update(projection, nextScope = currentScope, ticket) {
    if (ticket !== epoch) return false;
    epoch++; busy = false; currentScope = nextScope; clear();
    if (destroyed) return;
    if (pending) { status.textContent = 'A private action needs authoritative recovery.'; recoveryControl(); return; }
    if (!projection || projection.rightsState !== 'available' || !Array.isArray(projection.claims)) { status.textContent = projection?.rightsState === 'withdrawn' ? 'This source was withdrawn.' : 'Claims or current access are unavailable.'; return; }
    status.textContent = 'Claims loaded. Dates and source access are shown separately.';
    if (!projection.claims.length) content.append(el('p', 'No claims are available.'));
    for (const claim of projection.claims) {
      const card = el('article'); card.className = 'w22-claim';
      if (claim.available === false || claim.rightsState && claim.rightsState !== 'available') { card.append(el('p', 'Claim unavailable or withdrawn.')); content.append(card); continue; }
      card.append(el('h3', claim.text || 'Claim text unavailable'));
      const states = ['current','prior','superseded','disputed','unknown'];
      card.append(el('p', `Status: ${states.includes(claim.status) ? claim.status : 'unknown'}.`));
      card.append(el('p', `${claim.scope === 'private' ? 'Your private interpretation' : 'Creator account'}; revision ${claim.revision}.`));
      if (claim.explanation) card.append(el('p', claim.explanation));
      card.append(el('p', `Event time: ${claim.eventTime || 'unknown'}.`));
      card.append(el('p', `Valid from: ${claim.validFrom || 'unknown'}${claim.validUntil ? ` until ${claim.validUntil}` : ''}.`));
      card.append(el('p', `Recorded time: ${claim.recordedAt || 'unknown'}.`));
      if (claim.author) card.append(el('p', `Author: ${claim.author}.`));
      for (const relation of claim.relations || []) card.append(el('p', `Relationship: ${relation.kind || 'unknown'}${relation.reviewed === true ? '' : ' (proposed, not reviewed)'}${relation.targetId ? `; target ${relation.targetId}` : ''}.`));
      const sources = el('ul'); sources.setAttribute('aria-label', 'Sources');
      for (const source of claim.sources || []) {
        const item = el('li', source.available === true ? `${source.title || 'Source'}${source.revision != null ? ` (revision ${source.revision})` : ''}` : 'Source unavailable or withdrawn.');
        if (source.available === true && source.ref && typeof actions.openSource === 'function') {
          const generation = epoch, scope = currentScope;
          button(item, 'Open source moment', async () => {
            if (generation !== epoch) return;
            try { await actions.openSource({scope, ref:source.ref}); }
            catch { if (generation === epoch) { reset(); status.textContent = 'This source is unavailable. Search again with current access.'; } }
          });
        }
        sources.append(item);
      }
      if (sources.childNodes.length) card.append(sources); else card.append(el('p', 'No eligible citations available.'));
      if (claim.scope === 'private' && claim.canEdit === true && claim.id != null && claim.revision != null) {
        card.append(el('p', 'Changes apply only to your private note; creator history is unchanged.'));
        const label = el('label', 'Correct your private note'); const input = el('textarea'); input.value = claim.text || ''; label.append(input); card.append(label);
        if (typeof api.correctPrivate === 'function') button(card, 'Save private correction', () => { const value = input.value.trim(); if (!value) { status.textContent = 'Enter a private correction first.'; input.focus(); return; } mutate('correctPrivate', claim, value); });
        if (typeof api.forgetPrivate === 'function') { let confirm = false; const forget = button(card, 'Forget private note', () => { if (!confirm) { confirm = true; forget.textContent = 'Confirm forgetting private note'; status.textContent = 'Confirm to forget this private note.'; return; } mutate('forgetPrivate', claim); }); }
      }
      content.append(card);
    }
  }
  function destroy() { reset(); destroyed = true; box.remove(); }
  return {update, reset, destroy, getGeneration: () => epoch};
}



