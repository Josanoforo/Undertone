// Read only the authenticated owner's current model records; the server checks
// the source, approval and private attempt binding again for each refresh.
export function mountModelHistory(root, {identity, assertIdentity, list, openSource}) {
  const details = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = 'Your model history';
  const refresh = document.createElement('button'); refresh.type = 'button'; refresh.textContent = 'Refresh model history';
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  const content = document.createElement('div');
  details.append(summary, refresh, status, content); root.append(details);
  let generation = 0;
  const element = (tag, value) => { const node = document.createElement(tag); node.textContent = String(value); return node; };
  function reset() { generation++; content.replaceChildren(); status.textContent = ''; }
  refresh.onclick = async () => {
    const scope = identity(), ticket = ++generation;
    content.replaceChildren(); status.textContent = 'Checking your current model history…';
    try {
      if (scope.role !== 'viewer' || !scope.sessionId || !scope.token) throw Error('access');
      const response = await list(scope); assertIdentity(scope);
      if (ticket !== generation) return;
      if (!Array.isArray(response.models)) throw Error('projection');
      if (!response.models.length) content.append(element('p', 'No current accessible model history.'));
      for (const model of response.models) {
        const kind = model.definition?.kind;
        if (!['RGB_LINEAR_MEAN_V1', 'RESOURCE_BUDGET_12_V1'].includes(kind) || !Array.isArray(model.events)) continue;
        const card = element('article', '');
        card.append(element('h3', kind === 'RGB_LINEAR_MEAN_V1' ? 'Digital RGB weighted mean' : 'Allocate twelve resource tokens'));
        card.append(element('p', `Approved rule: ${kind}; definition version ${model.definition.version}; operation ${model.definition.spec?.operation || 'unavailable'}. Template ${model.definition.templateId}, version ${model.definition.templateVersion}.`));
        card.append(element('p', `Your prediction: ${model.prediction}`));
        for (const event of model.events) {
          const values = event.result?.values;
          if (!values || event.ruleVersion !== kind || event.definitionVersion !== model.definition.version) continue;
          const row = element('p', `Result ${event.sequence}: ${Object.entries(values).map(([key, value]) => `${key}: ${value}`).join(', ')}. ${event.result.explanation || ''}`);
          card.append(element('p', `Event ${event.sequence} parameters: ${JSON.stringify(event.parameters)}. Rule ${event.ruleVersion}; definition version ${event.definitionVersion}.`), row);
        }
        const refs = model.definition.sourceRefs;
        if (Array.isArray(refs)) for (const ref of refs) card.append(element('p', `Source ${ref.sourceId}, revision ${ref.sourceRevision}; moment ${ref.momentId}; interval ${ref.startMs}–${ref.endMs} ms; session ${ref.sessionId}.`));
        if (typeof openSource === 'function' && Array.isArray(refs)) for (const ref of refs) {
          const button = element('button', 'Open source moment'); button.type = 'button';
          button.onclick = async () => { try { assertIdentity(scope); if (ticket !== generation) return; await openSource(ref, scope); assertIdentity(scope); } catch { if (ticket === generation) status.textContent = 'Current source access is unavailable.'; } };
          card.append(button);
        }
        content.append(card);
      }
      status.textContent = 'Showing your currently accessible model history.';
    } catch { if (ticket === generation) { content.replaceChildren(); status.textContent = 'Model history or current access is unavailable. Reconnect and refresh.'; } }
  };
  return {reset};
}

// Creator sees only currently authorized, explicitly shared model events.
export function mountModelShares(root, {identity, assertIdentity, list, openSource}) {
  const details = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = 'Shared model results';
  const refresh = document.createElement('button'); refresh.type = 'button'; refresh.textContent = 'Refresh shared results';
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  const content = document.createElement('div'); details.append(summary, refresh, status, content); root.append(details);
  let generation = 0;
  const el = (tag, value) => { const node = document.createElement(tag); node.textContent = String(value); return node; };
  function reset() { generation++; content.replaceChildren(); status.textContent = ''; }
  refresh.onclick = async () => {
    const scope = identity(), ticket = ++generation; content.replaceChildren(); status.textContent = 'Checking shared results…';
    try {
      if (scope.role !== 'creator' || !scope.sessionId || !scope.token) throw Error('access');
      const response = await list(scope); assertIdentity(scope); if (ticket !== generation) return;
      if (!Array.isArray(response.shares)) throw Error('projection');
      if (!response.shares.length) content.append(el('p', 'No currently accessible shared results.'));
      for (const share of response.shares) {
        const def = share.definition, event = share.event, values = event?.result?.values;
        if (!['RGB_LINEAR_MEAN_V1', 'RESOURCE_BUDGET_12_V1'].includes(def?.kind) || event?.ruleVersion !== def.kind || event?.definitionVersion !== def.version || !values || typeof values !== 'object') continue;
        const card = el('article', '');
        card.append(el('h3', def.kind === 'RGB_LINEAR_MEAN_V1' ? 'Digital RGB weighted mean' : 'Allocate twelve resource tokens'));
        card.append(el('p', `Selected result: ${Object.entries(values).map(([key, value]) => `${key}: ${value}`).join(', ')}. ${event.result.explanation || ''}`));
        if (share.ownerId) card.append(el('p', `Shared by: ${share.ownerId}`));
        else card.append(el('p', 'Shared without identity.'));
        if (typeof openSource === 'function' && Array.isArray(def.sourceRefs)) for (const ref of def.sourceRefs) {
          const button = el('button', 'Open source moment'); button.type = 'button';
          button.onclick = async () => { try { assertIdentity(scope); if (ticket !== generation) return; await openSource(ref, scope); assertIdentity(scope); } catch { if (ticket === generation) status.textContent = 'Current source access is unavailable.'; } };
          card.append(button);
        }
        content.append(card);
      }
      status.textContent = 'Showing currently accessible shared results.';
    } catch { if (ticket === generation) { content.replaceChildren(); status.textContent = 'Shared results or current access are unavailable. Reconnect and refresh.'; } }
  };
  return {reset};
}
