// Displays the authenticated, actor-filtered correction preview.
function materialSegmentBinding(item) {
  if (item?.segmentReplacementUnavailable === true) throw Error('Segment binding unavailable');
  if (!Object.hasOwn(item ?? {}, 'segmentReplacement')) return null;
  const binding = item.segmentReplacement;
  if (typeof binding.segmentId !== 'string' || !binding.segmentId || !Number.isSafeInteger(binding.revision) || binding.revision < 1) throw Error('Invalid segment binding');
  return {segmentId:binding.segmentId, revision:binding.revision};
}
function sameMaterialSegment(item, expected) {
  try { return JSON.stringify(materialSegmentBinding(item)) === JSON.stringify(expected); } catch { return false; }
}
// Whole-source candidates come from an authenticated source listing/search, not
// from moment indexes. Keep source revisions and audience eligibility explicit.
export function impactSourceChoices(data, sessionId, query = '') {
  const rows = Array.isArray(data?.sources) ? data.sources : [];
  const term = query.trim().toLocaleLowerCase();
  return rows.flatMap(item => {
    const ref = item?.ref;
    const sourceId = ref?.sourceId ?? item?.id;
    const revision = ref?.sourceRevision ?? item?.revision;
    const sid = ref?.sessionId ?? item?.sessionId ?? sessionId;
    if (sid !== sessionId || typeof sourceId !== 'string' || !sourceId || !Number.isSafeInteger(revision) || revision < 1 || item?.stale === true) return [];
    if (item?.status !== 'active' || item?.audienceVisible !== true) return [];
    if (term && !`${item.title || ''} ${item.text || ''}`.toLocaleLowerCase().includes(term)) return [];
    return [{sourceId, sourceRevision:revision, title:item.title || 'Source', text:item.text || ''}];
  });
}
export function impactMomentChoices(data, sessionId) {
  return (Array.isArray(data?.moments) ? data.moments : []).flatMap(item => {
    const ref = item?.ref;
    if (ref?.sessionId !== sessionId || typeof ref.sourceId !== 'string' || !ref.sourceId || !Number.isSafeInteger(ref.sourceRevision) || ref.sourceRevision < 1 || item?.stale === true) return [];
    return [{ref, text:item.text || 'Source moment'}];
  });
}
export function mountImpactPreview(root, {identity, assertIdentity, assertReadIdentity = assertIdentity, search, sourceSearch, materialSearch, preview, change, request, getChange, recoverSource, listSpeech, replaceSpeech, replaceCaption, replaceMaterial, openMaterial, recordOptions, replaceRecord, openRecord}) {
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
  const box = el('section'), title = el('h2', 'Review source correction impact');
  const searchLabel = el('label', 'Search sources and moments '), query = el('input'); searchLabel.append(query);
  const find = el('button', 'Search'), results = el('div'), selected = el('p');
  const reasonLabel = el('label', 'Reason for correction '), reason = el('input'); reason.maxLength = 500; reasonLabel.append(reason);
  const check = el('button', 'Preview impact'), status = el('p'), output = el('div');
  const correctionLabel = el('label', 'Corrected source text '), correction = el('textarea'); correction.maxLength = 20000; correctionLabel.append(correction);
  const titleLabel = el('label', 'Corrected title (optional) '), correctedTitle = el('input'); correctedTitle.maxLength = 200; titleLabel.append(correctedTitle);
  const statusLabel = el('label', 'Source status '), correctedStatus = el('select');
  for (const [value, label] of [['', 'Keep current status'], ['active', 'Active'], ['retracted', 'Retracted']]) correctedStatus.append(new Option(label, value));
  statusLabel.append(correctedStatus);
  const visibilityLabel = el('label', 'Audience visibility '), visibility = el('select');
  for (const [value, label] of [['', 'Keep current visibility'], ['visible', 'Visible to audience'], ['private', 'Hidden from audience']]) visibility.append(new Option(label, value));
  visibilityLabel.append(visibility);
  const expiryLabel = el('label', 'Expiry '), expiryMode = el('select'), expiry = el('input'); expiry.type = 'datetime-local';
  for (const [value, label] of [['', 'Keep current expiry'], ['set', 'Set expiry'], ['clear', 'Remove expiry']]) expiryMode.append(new Option(label, value));
  expiryLabel.append(expiryMode, expiry);
  const submit = el('button', 'Apply correction'), recover = el('button', 'Check previous correction');
  const reopen = el('button', 'Reopen last correction'), history = el('select'), openHistory = el('button', 'Open selected correction');
  const lookupKindLabel = el('label', 'Reference type '), lookupKind = el('select');
  for (const [value, label] of [['source', 'Source'], ['change', 'Correction'], ['request', 'Correction request']]) lookupKind.append(new Option(label, value));
  lookupKindLabel.append(lookupKind);
  const lookupLabel = el('label', 'Correction reference '), lookup = el('input'), lookupButton = el('button', 'Read correction'), lookupResult = el('div');
  lookupLabel.append(lookup); lookupButton.type = 'button';
  history.setAttribute('aria-label', 'Previously confirmed corrections'); openHistory.type = 'button';
  submit.type = recover.type = reopen.type = 'button';
  find.type = check.type = 'button'; status.setAttribute('role', 'status');
  const lookupBox = el('section'); lookupBox.dataset.tabOnlyRead = ''; lookupBox.append(el('h2', 'Read a current correction'), lookupKindLabel, lookupLabel, lookupButton, lookupResult);
  box.append(title, searchLabel, find, results, selected, reasonLabel, check, correctionLabel, titleLabel, statusLabel, visibilityLabel, expiryLabel, submit, recover, reopen, history, openHistory, status, output); root.append(lookupBox, box);
  let generation = 0, resultsGeneration = 0, source = null, reviewed = false, historyScope = null;
  let lookupGeneration = 0;
  lookup.oninput = lookupKind.onchange = () => { lookupGeneration++; lookupResult.replaceChildren(); };
  lookupButton.onclick = async () => {
    const id = lookup.value.trim(), kind = lookupKind.value, scope = identity(), ticket = ++lookupGeneration;
    lookupResult.replaceChildren();
    if (!id) { lookupResult.textContent = 'Enter a correction reference.'; return; }
    lookupButton.disabled = true;
    try {
      assertReadIdentity(scope);
      const result = await (kind === 'source' ? recoverSource(id, scope) : kind === 'request' ? request(id, scope) : getChange(id, scope));
      assertReadIdentity(scope);
      if (ticket !== lookupGeneration || lookup.value.trim() !== id) return;
      if (typeof result?.change?.id !== 'string' || (kind === 'change' && result.change.id !== id) || (kind === 'source' && result.change.sourceId !== id) || !Array.isArray(result.change.affected)) throw Error('Unexpected correction receipt');
      lookupResult.append(el('p', 'Current correction found. Replacement outcomes without an authoritative receipt remain unknown.'));
      if (kind === 'source' && scope.role === 'creator') {
        const recoverProtected = el('button', 'Check protected replacement receipt');
        recoverProtected.type = 'button';
        recoverProtected.onclick = async () => {
          recoverProtected.disabled = true;
          let action;
          try {
            const current = () => { try { assertReadIdentity(scope); return ticket === lookupGeneration && lookup.value.trim() === id && lookupKind.value === 'source'; } catch { return false; } };
            action = createImpactReplacementAction({scope, isCurrent:current, recoverSource});
            const settled = await action.readback(id);
            if (current()) lookupResult.append(el('p', `Protected replacement receipt confirmed for ${settled.kind}; version ${settled.version}. Read the current correction again to review it.`));
          } catch { if (ticket === lookupGeneration) lookupResult.append(el('p', 'No matching confirmed protected replacement receipt is available. No request was repeated.')); }
          finally { action?.destroy(); recoverProtected.disabled = false; }
        };
        lookupResult.append(recoverProtected);
      }
      if (kind === 'source' && scope.role === 'creator' && result.change.correctionReceipt === 'confirmed') {
        const optLabel = el('label', ' Enable protected replacement for this correction '), opt = el('input'); opt.type = 'checkbox'; optLabel.prepend(opt);
        const editor = el('div'), editorStatus = el('p'); editorStatus.setAttribute('role', 'status');
        opt.onchange = () => {
          editor.replaceChildren(); editorStatus.textContent = '';
          if (!opt.checked) return;
          try {
            assertReadIdentity(scope);
            if (ticket !== lookupGeneration || lookup.value.trim() !== id || lookupKind.value !== 'source') throw Error('View changed');
            showChange(result, {protectedScope:scope, protectedCurrent:() => opt.checked && ticket === lookupGeneration && lookup.value.trim() === id && lookupKind.value === 'source', targetOutput:editor, targetStatus:editorStatus});
          } catch { editorStatus.textContent = 'Current creator access is required.'; }
        };
        lookupResult.append(optLabel, editorStatus, editor);
      }
      const list = el('ul');
      if (kind === 'source') lookupResult.append(el('p', result.change.correctionReceipt === 'confirmed' ? 'Correction receipt confirmed.' : 'Correction receipt unresolved. The original outcome remains unknown.'));
      for (const item of result.change.affected) {
        const row = el('li', `${item.kind || 'Output'}: ${item.state || 'unknown'} — receipt ${item.replacementReceipt === 'confirmed' ? 'confirmed' : 'unresolved'}`);
        if (kind === 'source' && result.change.correctionReceipt === 'confirmed' && item.state === 'applied' && item.replacementReceipt === 'confirmed' && ['material', 'record'].includes(item.kind) && typeof item.id === 'string' && item.replacement && Number.isInteger(item.replacement.version)) {
          const button = el('button', 'Open confirmed replacement for review'); button.type = 'button';
          button.onclick = async () => {
            button.disabled = true;
            try {
              assertReadIdentity(scope);
              const fresh = await recoverSource(id, scope);
              assertReadIdentity(scope);
              if (ticket !== lookupGeneration || lookup.value.trim() !== id || lookupKind.value !== 'source') return;
              const current = fresh?.change;
              const match = current?.affected?.find(x => x.kind === item.kind && x.id === item.id && x.replacementId === item.replacementId && x.state === 'applied' && x.replacementReceipt === 'confirmed' && x.replacement?.version === item.replacement.version && x.replacement?.status === item.replacement.status);
              if (current?.id !== result.change.id || current?.sourceId !== id || current?.revision !== result.change.revision || current?.fence !== result.change.fence || current?.correctionReceipt !== 'confirmed' || !match) throw Error('Current replacement changed');
              if (item.kind === 'material') await openMaterial(button, item.id, scope, item.replacement.version); else await openRecord(item.id, scope, item.replacement.version, button);
              assertReadIdentity(scope);
            } catch { if (ticket === lookupGeneration) lookupResult.textContent = 'Replacement unavailable or changed. Refresh before review; no action was repeated.'; }
            finally { button.disabled = false; }
          };
          row.append(button);
        }
        list.append(row);
      }
      lookupResult.append(list);
    } catch { if (ticket === lookupGeneration) lookupResult.textContent = 'Correction unavailable or no longer current. The request outcome remains unknown; no request was repeated.'; }
    finally { lookupButton.disabled = false; }
  };
  function reset() { generation++; resultsGeneration++; lookupGeneration++; lookup.value = ''; lookupResult.replaceChildren(); source = null; reviewed = false; historyScope = null; history.replaceChildren(); correction.value = ''; correctedTitle.value = ''; correctedStatus.value = ''; visibility.value = ''; expiryMode.value = ''; expiry.value = ''; results.replaceChildren(); selected.textContent = ''; output.replaceChildren(); status.textContent = 'Select a current source.'; }
  query.addEventListener('input', reset);
  reason.addEventListener('input', () => { generation++; reviewed = false; output.replaceChildren(); });
  find.onclick = async () => {
    reset(); const ticket = generation, resultsTicket = resultsGeneration, scope = identity();
    try {
      const data = await search(query.value.trim(), scope); assertIdentity(scope); if (ticket !== generation) return;
      let sourceData = null;
      if (sourceSearch) {
        try { sourceData = await sourceSearch(query.value.trim(), scope); assertIdentity(scope); }
        catch { /* Keep indexed-moment selection available if whole-source search fails. */ }
      }
      if (ticket !== generation || resultsTicket !== resultsGeneration) return;
      const chooseSource = (sourceId, revision, label) => {
        const row = el('p', label), choose = el('button', 'Select source'); choose.type = 'button';
        choose.onclick = () => { try { assertIdentity(scope); } catch { return; } if (resultsTicket !== resultsGeneration) return; generation++; reviewed = false; source = {sourceRef:sourceId, expectedRevision:revision}; selected.textContent = `Source ${sourceId}, revision ${revision}.`; output.replaceChildren(); status.textContent = 'Enter a reason and preview the impact.'; };
        row.append(choose); results.append(row);
      };
      // Some authenticated search implementations return eligible sources on
      // the same DTO; otherwise the caller may provide its session source search.
      const wholeSources = impactSourceChoices(sourceData ?? data, scope.sessionId, query.value);
      for (const item of wholeSources) chooseSource(item.sourceId, item.sourceRevision, `${item.title}: Whole source`);
      for (const item of impactMomentChoices(data, scope.sessionId)) {
        const ref = item.ref;
        const row = el('p', item.text), choose = el('button', 'Select source'); choose.type = 'button';
        choose.onclick = () => { try { assertIdentity(scope); } catch { return; } if (resultsTicket !== resultsGeneration) return; generation++; reviewed = false; source = {sourceRef: ref.sourceId, expectedRevision: ref.sourceRevision}; selected.textContent = `Source ${ref.sourceId}, revision ${ref.sourceRevision}.`; output.replaceChildren(); status.textContent = 'Enter a reason and preview the impact.'; };
        row.append(choose); results.append(row);
      }
      status.textContent = 'Select a current source or source moment from the results.';
    } catch { if (ticket === generation) status.textContent = 'Source search is unavailable.'; }
  };
  check.onclick = async () => {
    const chosen = source, why = reason.value.trim(), ticket = ++generation, scope = identity(); reviewed = false; output.replaceChildren();
    if (!chosen || !why) { status.textContent = 'Select a source and enter a reason.'; return; }
    check.disabled = true;
    try {
      const data = await preview({...chosen, reason: why}, scope); assertIdentity(scope); if (ticket !== generation) return;
      if (data.source !== chosen.sourceRef || data.revision !== chosen.expectedRevision || !Array.isArray(data.affected)) throw Error('Unexpected projection');
      output.append(el('p', 'Audio already heard cannot be recalled. Public replacements require fresh approval.'));
      const list = el('ul'); for (const item of data.affected) list.append(el('li', `${item.kind || 'Output'}: ${item.state || 'unknown'}`)); output.append(list);
      reviewed = true;
      status.textContent = 'Impact preview loaded. No source change was submitted.';
    } catch { if (ticket === generation) status.textContent = 'Impact is unavailable or the source changed. Refresh before continuing.'; }
    finally { check.disabled = false; }
  };
  const keyFor = scope => `entrelineas.w21.impact.v1:${scope.sessionId}:${scope.actorBinding}`;
  const intentKeyFor = scope => `entrelineas.w21.impact.last.v1:${scope.sessionId}:${scope.actorBinding}`;
  const historyKeyFor = scope => `entrelineas.w21.impact.history.v1:${scope.sessionId}:${scope.actorBinding}`;
  function remember(scope, id) {
    const key = historyKeyFor(scope); let ids = [];
    try { const stored = JSON.parse(localStorage.getItem(key) || '[]'); if (Array.isArray(stored)) ids = stored.filter(x => typeof x === 'string'); } catch { throw Error('Correction history unavailable'); }
    localStorage.setItem(key, JSON.stringify([id, ...ids.filter(x => x !== id)]));
    localStorage.setItem(intentKeyFor(scope), id);
  }
  function showHistory(scope) {
    let ids = []; const stored = localStorage.getItem(historyKeyFor(scope));
    if (stored) { ids = JSON.parse(stored); if (!Array.isArray(ids) || ids.some(x => typeof x !== 'string')) throw Error('Invalid correction history'); }
    const last = localStorage.getItem(intentKeyFor(scope)); if (last && !ids.includes(last)) ids.unshift(last);
    history.replaceChildren(); for (const id of ids) { const option = el('option', `Correction ${id}`); option.value = id; history.append(option); } historyScope = `${scope.sessionId}:${scope.actorBinding}`;
  }
  history.onfocus = () => { try { const scope = identity(); assertIdentity(scope); showHistory(scope); } catch { status.textContent = 'Correction history is unavailable.'; } };
  openHistory.onclick = async () => {
    const scope = identity(), ticket = generation, id = history.value;
    if (!id || historyScope !== `${scope.sessionId}:${scope.actorBinding}`) { status.textContent = 'Select a confirmed correction for this identity.'; return; }
    openHistory.disabled = true;
    try { assertIdentity(scope); const result = await getChange(id, scope); assertIdentity(scope); if (ticket !== generation) return; showChange(result); status.textContent = 'Current correction loaded.'; }
    catch { if (ticket === generation) status.textContent = 'Correction unavailable or no longer current.'; }
    finally { openHistory.disabled = false; }
  };
  const lockFor = scope => `entrelineas.w21.impact:${scope.sessionId}:${scope.actorBinding}`;
  function available(scope) {
    if (!scope.sessionId || !scope.actorBinding || !navigator.locks || !crypto?.subtle || !crypto?.randomUUID) throw Error('Safe recovery unavailable');
  }
  function showChange(result, {protectedScope = null, protectedCurrent = null, targetOutput = null, targetStatus = null} = {}) {
    const displayOutput = targetOutput || output, displayStatus = targetStatus || status;
    const checkScope = scope => {
      if (!protectedScope) return assertIdentity(scope);
      assertReadIdentity(scope); assertReadIdentity(protectedScope);
      if (scope.epoch !== protectedScope.epoch || scope.token !== protectedScope.token || scope.actorBinding !== protectedScope.actorBinding || scope.sessionId !== protectedScope.sessionId || scope.role !== 'creator' || !protectedCurrent()) throw Error('View changed');
    };
    const protectedSubmit = async (scope, pending, sameForm) => {
      const isCurrent = () => { try { checkScope(scope); return sameForm(); } catch { return false; } };
      const action = createImpactReplacementAction({scope, isCurrent, recoverSource, dispatch:(kind, intent, payload, actor) => kind === 'material' ? replaceMaterial(intent, payload, actor) : replaceRecord(intent, payload, actor)});
      try {
        if (!navigator.locks?.request) throw Error('Safe recovery unavailable');
        return await navigator.locks.request(lockFor(scope), async () => {
          checkScope(scope);
          if (localStorage.getItem(`${keyFor(scope)}:replacement`) !== null) throw Error('Previous replacement remains unconfirmed');
          return action.submit(pending);
        });
      } finally { action.destroy(); }
    };
    if (!result?.change?.id || !Array.isArray(result.change.affected)) throw Error('Unexpected correction receipt');
    displayOutput.replaceChildren(el('p', 'Correction saved. Replacements require explicit action and fresh public approval.'));
    const list = el('ul');
    for (const item of result.change.affected) {
      const row = el('li', `${item.kind || 'Output'}: ${item.state || 'unknown'}`);
      if (!protectedScope && item.kind === 'caption' && ['pending_replacement', 'applied'].includes(item.state) && typeof item.replacementId === 'string' && typeof result.change.fence === 'string') {
        const label = el('label', ' Search current captions '), input = el('input'), findCaption = el('button', 'Find caption'), matches = el('div');
        label.append(input); findCaption.type = 'button'; row.append(label, findCaption, matches);
        input.oninput = () => matches.replaceChildren();
        findCaption.onclick = async () => {
          const scope = identity(), ticket = generation, queryText = input.value.trim(); matches.replaceChildren();
          try {
            const data = await search(queryText, scope); checkScope(scope);
            if (ticket !== generation || input.value.trim() !== queryText) return;
            for (const moment of data.moments || []) {
              const ref = moment.ref;
              if (!ref || ref.sessionId !== scope.sessionId || ref.sourceId !== result.change.sourceId || ref.sourceRevision !== result.change.revision) continue;
              const button = el('button', 'Associate this caption'); button.type = 'button';
              const choice = el('p', moment.text || 'Current caption'); choice.append(button); matches.append(choice);
              button.onclick = async () => {
                button.disabled = true;
                try {
                  available(scope);
                  const payload = {replacementId: item.replacementId, fence: result.change.fence, ref};
                  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify({intentId: result.change.id, payload})));
                  const fingerprint = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
                  await navigator.locks.request(lockFor(scope), async () => {
                    checkScope(scope); if (ticket !== generation || input.value.trim() !== queryText) throw Error('View changed');
                    const key = `${keyFor(scope)}:replacement`, saved = localStorage.getItem(key);
                    if (saved && saved !== fingerprint) throw Error('Previous replacement remains unconfirmed');
                    if (!saved) localStorage.setItem(key, fingerprint);
                    const response = await replaceCaption(result.change.id, payload, scope); checkScope(scope);
                    if (response?.replacement?.replacementId !== item.replacementId || JSON.stringify(response.replacement.ref) !== JSON.stringify(ref)) throw Error('Unexpected receipt');
                    if (localStorage.getItem(key) === fingerprint) localStorage.removeItem(key);
                    if (ticket === generation) displayStatus.textContent = 'Caption replacement associated.';
                  });
                } catch { if (ticket === generation) displayStatus.textContent = 'Caption replacement not confirmed. Reopen and select the exact same caption to retry.'; }
                finally { button.disabled = false; }
              };
            }
          } catch { if (ticket === generation) displayStatus.textContent = 'Current captions are unavailable.'; }
        };
      }
      if (!protectedScope && item.kind === 'speech' && ['pending_replacement', 'applied'].includes(item.state) && typeof item.replacementId === 'string' && typeof result.change.fence === 'string') {
        const label = el('label', ' Existing speech job ID '), job = el('input'), associate = el('button', 'Associate speech replacement');
        const loadJobs = el('button', 'Find existing speech jobs'), jobs = el('div'); let cursor = 0;
        job.type = 'number'; job.min = '1'; job.step = '1'; label.append(job); associate.type = loadJobs.type = 'button'; row.append(loadJobs, jobs, label, associate);
        loadJobs.onclick = async () => {
          const scope = identity(), ticket = generation, requested = cursor; loadJobs.disabled = true; if (requested === 0) jobs.replaceChildren();
          try {
            const page = await listSpeech(requested, scope); checkScope(scope);
            if (ticket !== generation) return;
            if (!Array.isArray(page.operations) || !Number.isSafeInteger(page.nextCursor) || page.nextCursor < requested || typeof page.hasMore !== 'boolean' || (page.hasMore && page.nextCursor === requested)) throw Error('Invalid operations page');
            for (const operation of page.operations) {
              if (operation.kind !== 'speech' || !['queued','running','complete'].includes(operation.state) || !Number.isSafeInteger(operation.sequence) || operation.sequence < 1) continue;
              const choice = el('p', `Speech ${operation.sequence}: ${operation.state}, ${operation.language || 'language unknown'}. `), choose = el('button', 'Select speech job'); choose.type = 'button';
              choose.onclick = () => { try { checkScope(scope); if (ticket === generation) job.value = String(operation.sequence); } catch { displayStatus.textContent = 'Access changed. Refresh jobs.'; } };
              choice.append(choose); jobs.append(choice);
            }
            cursor = page.nextCursor; loadJobs.textContent = page.hasMore ? 'Find more speech jobs' : 'Refresh speech jobs';
            if (!page.hasMore) cursor = 0;
            displayStatus.textContent = 'Select a current job for the corrected source. The server checks its exact eligibility.';
          } catch { if (ticket === generation) displayStatus.textContent = 'Speech jobs are unavailable. No job was submitted.'; }
          finally { loadJobs.disabled = false; }
        };
        associate.onclick = async () => {
          const scope = identity(), ticket = generation, value = Number(job.value);
          if (!Number.isSafeInteger(value) || value < 1) { displayStatus.textContent = 'Enter an existing speech job ID.'; return; }
          associate.disabled = true;
          try {
            available(scope);
            const payload = {replacementId: item.replacementId, fence: result.change.fence, jobId: value};
            const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify({intentId: result.change.id, payload})));
            const fingerprint = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
            await navigator.locks.request(lockFor(scope), async () => {
              checkScope(scope); if (ticket !== generation) throw Error('View changed');
              const key = `${keyFor(scope)}:replacement`, saved = localStorage.getItem(key);
              if (saved && saved !== fingerprint) throw Error('Previous replacement remains unconfirmed');
              if (!saved) localStorage.setItem(key, fingerprint);
              const response = await replaceSpeech(result.change.id, payload, scope);
              checkScope(scope);
              if (response?.replacement?.replacementId !== item.replacementId || response.replacement.jobId !== value) throw Error('Unexpected receipt');
              if (localStorage.getItem(key) === fingerprint) localStorage.removeItem(key);
              if (ticket === generation) displayStatus.textContent = 'Speech replacement associated. No job was submitted.';
            });
          } catch { if (ticket === generation) displayStatus.textContent = 'Speech replacement not confirmed. Reopen this correction and retry the exact same job ID.'; }
          finally { associate.disabled = false; }
        };
      }
      if (item.kind === 'material' && item.state === 'pending_replacement' && typeof item.replacementId === 'string' && typeof result.change.fence === 'string') {
        let segmentBinding;
        try { segmentBinding = materialSegmentBinding(item); } catch { row.append(el('p', 'Segment binding unavailable. Refresh this correction before replacing the material.')); list.append(row); continue; }
        const titleLabel = el('label', ' Replacement title '), titleInput = el('input'); titleInput.maxLength = 200; titleLabel.append(titleInput);
        const bodyLabel = el('label', ' Replacement text '), bodyInput = el('textarea'); bodyInput.maxLength = 12000; bodyLabel.append(bodyInput);
        const searchLabel = el('label', ' Search current sources '), input = el('input'); searchLabel.append(input);
        const find = el('button', 'Find source'), matches = el('div'), selected = el('p'); find.type = 'button';
        let refs = []; input.oninput = () => { matches.replaceChildren(); };
        const renderSelected = () => {
          selected.replaceChildren();
          for (const entry of refs) {
            const row = el('span', `${entry.label} `), remove = el('button', 'Remove source'); remove.type = 'button';
            remove.onclick = () => { refs = refs.filter(x => x !== entry); renderSelected(); };
            row.append(remove); selected.append(row);
          }
        };
        find.onclick = async () => {
          const scope = identity(), ticket = generation, queryText = input.value.trim(); matches.replaceChildren();
          try {
            const data = await materialSearch(queryText, scope); checkScope(scope);
            // The current creator options also expose valid untimed sources. A
            // text search need not index a corrected source, so retain the
            // exact current source as an explicit selectable result.
            const options = await recordOptions(scope); checkScope(scope);
            const corrected = (options.sources || []).find(s => s.ref?.sessionId === scope.sessionId && s.ref?.sourceId === result.change.sourceId && s.ref?.sourceRevision === result.change.revision);
            const candidates = [...(data.results || [])];
            if (corrected && !candidates.some(m => JSON.stringify(m.ref) === JSON.stringify(corrected.ref))) candidates.push({ref: corrected.ref, time:null, destination:{kind:'source'}, explanation:corrected.sourceTitle || 'Current source'});
            if (ticket !== generation || input.value.trim() !== queryText) return;
            let correctedFound = false;
            for (const moment of candidates) {
              const candidate = moment.ref;
              if (!candidate || candidate.sessionId !== scope.sessionId || typeof candidate.sourceId !== 'string' || !Number.isInteger(candidate.sourceRevision) || (candidate.sourceId === result.change.sourceId && candidate.sourceRevision !== result.change.revision)) continue;
              const untimed = moment.time === null && moment.destination?.kind === 'source';
              if (untimed && (Object.keys(candidate).length !== 3 || !['sessionId', 'sourceId', 'sourceRevision'].every(k => Object.hasOwn(candidate, k)))) continue;
              if (!untimed && (!moment.time || typeof candidate.momentId !== 'string')) continue;
              if (candidate.sourceId === result.change.sourceId && candidate.sourceRevision === result.change.revision) correctedFound = true;
              const label = `${untimed ? 'Source without timing' : 'Source moment'}: ${moment.explanation || 'Current source'}`;
              const choice = el('p', label), choose = el('button', 'Add source'); choose.type = 'button';
              choose.onclick = () => { if (ticket !== generation) return; try { checkScope(scope); } catch { return; } if (!refs.some(x => JSON.stringify(x.ref) === JSON.stringify(candidate))) refs = [...refs, {ref:candidate, label}]; renderSelected(); };
              choice.append(choose); matches.append(choice);
            }
            displayStatus.textContent = correctedFound ? 'Select the corrected source for this replacement.' : 'The corrected source is not available for this search. Refresh or resolve its source availability before saving.';
          } catch { if (ticket === generation) displayStatus.textContent = 'Current sources are unavailable.'; }
        };
        const save = el('button', 'Save material replacement draft'); save.type = 'button';
        save.onclick = async () => {
          const scope = identity(), ticket = generation, chosen = refs, title = titleInput.value.trim(), body = bodyInput.value.trim();
          if (!chosen.some(x => x.ref.sourceId === result.change.sourceId && x.ref.sourceRevision === result.change.revision && (!segmentBinding || typeof x.ref.momentId === 'string')) || !title || !body) { displayStatus.textContent = 'Select the corrected source and enter a title and text.'; return; }
          save.disabled = true;
          try {
            const payload = {replacementId:item.replacementId, fence:result.change.fence, title, body, refs:chosen.map(x => x.ref), ...(segmentBinding ? {segmentRevision:segmentBinding.revision} : {})};
            if (protectedScope) {
              const settled = await protectedSubmit(scope, {kind:'material', intentId:result.change.id, targetId:item.id, sourceId:result.change.sourceId, sourceRevision:result.change.revision, segmentBinding, payload}, () => ticket === generation && refs === chosen && titleInput.value.trim() === title && bodyInput.value.trim() === body);
              if (protectedCurrent()) displayStatus.textContent = `Replacement receipt confirmed at version ${settled.version}. Read the current correction again before review.`;
              return;
            }
            available(scope);
            const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify({intentId:result.change.id, payload})));
            const fingerprint = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
            await navigator.locks.request(lockFor(scope), async () => {
              checkScope(scope); if (ticket !== generation || refs !== chosen || titleInput.value.trim() !== title || bodyInput.value.trim() !== body) throw Error('View changed');
              const fresh = await getChange(result.change.id, scope); checkScope(scope);
              const current = fresh?.change, target = current?.affected?.find(x => x.kind === 'material' && x.id === item.id && x.replacementId === item.replacementId);
              if (ticket !== generation || refs !== chosen || titleInput.value.trim() !== title || bodyInput.value.trim() !== body || current?.id !== result.change.id || current?.sourceId !== result.change.sourceId || current?.revision !== result.change.revision || current?.fence !== result.change.fence || target?.state !== 'pending_replacement' || !sameMaterialSegment(target, segmentBinding)) throw Error('Current material binding changed');
              const key = `${keyFor(scope)}:replacement`, saved = localStorage.getItem(key);
              if (saved !== null) throw Error('Previous replacement remains unconfirmed; check its current receipt');
              if (!saved) localStorage.setItem(key, fingerprint);
              const response = await replaceMaterial(result.change.id, payload, scope); checkScope(scope);
              if (response?.replacement?.replacementId !== item.replacementId || response.replacement.status !== 'draft' || response.replacement.materialId !== item.id || !Number.isInteger(response.replacement.version)) throw Error('Unexpected receipt');
              if (localStorage.getItem(key) === fingerprint) localStorage.removeItem(key);
              if (ticket === generation) { displayStatus.textContent = 'Replacement saved as a draft. Review and approve it again before presenting.'; const review = el('button', 'Open replacement for review'); review.type = 'button'; review.onclick = async () => { review.disabled = true; try { checkScope(scope); if (ticket === generation) await openMaterial(review, response.replacement.materialId, scope, response.replacement.version); } catch { if (ticket === generation) displayStatus.textContent = 'This replacement could not be opened for exact review. Refresh or open it from the Studio collection.'; } finally { if (ticket === generation) review.disabled = false; } }; row.append(review); }
            });
          } catch { if (ticket === generation) displayStatus.textContent = 'Material replacement not confirmed. Check the current correction receipt before any further action.'; }
          finally { save.disabled = false; }
        };
        row.append(titleLabel, bodyLabel, searchLabel, find, matches, selected, save);
      }
      if (item.kind === 'record' && item.state === 'pending_replacement' && typeof item.replacementId === 'string' && typeof result.change.fence === 'string') {
        const load = el('button', 'Choose current record contents'), editor = el('div'); load.type = 'button'; row.append(load, editor);
        load.onclick = async () => {
          const scope = identity(), ticket = generation; load.disabled = true; editor.replaceChildren();
          try {
            const options = await recordOptions(scope); checkScope(scope); if (ticket !== generation) return;
            if (!Array.isArray(options.moments) || !Array.isArray(options.chapters) || !Array.isArray(options.formats)) throw Error('Invalid options');
            const addChecks = (items, label) => items.map(value => { const l = el('label', label(value)), c = el('input'); c.type = 'checkbox'; l.prepend(c); editor.append(l); return {value, c}; });
            editor.append(el('p', 'Select current sources, chapters, outcome and its required contributions.'));
            const moments = addChecks(options.moments.filter(m => m.ref?.sessionId === scope.sessionId), m => `${m.sourceTitle || 'Source'}: ${m.text || ''}`);
            const sources = addChecks((options.sources || []).filter(s => s.ref?.sessionId === scope.sessionId), s => `Source without timing: ${s.title || s.sourceTitle || 'Source'}`);
            const chapters = addChecks(options.chapters, c => `Chapter: ${c.title || c.id}`);
            const formatLabel = el('label', 'Outcome '), format = el('select'); format.append(new Option('Choose an outcome', ''));
            for (const f of options.formats.filter(f => f.decision)) format.append(new Option(f.title || f.question || 'Outcome', f.id));
            formatLabel.append(format); editor.append(formatLabel); const contributionsBox = el('div'); editor.append(contributionsBox); let contributions = [];
            format.onchange = () => { contributionsBox.replaceChildren(); const f = options.formats.find(x => x.id === format.value); contributions = (f?.contributions || []).map(value => { const l = el('label', `${value.selection || 'Contribution'}: ${value.reason || ''}`), c = el('input'); c.type = 'checkbox'; l.prepend(c); contributionsBox.append(l); return {value, c}; }); };
            const languageLabel = el('label', 'Original language '), language = el('select'); language.append(new Option('English', 'en'), new Option('Spanish', 'es')); languageLabel.append(language);
            const enLabel = el('label', 'English interpretation '), en = el('textarea'); enLabel.append(en); const esLabel = el('label', 'Spanish interpretation '), es = el('textarea'); esLabel.append(es);
            const save = el('button', 'Save record replacement draft'); save.type = 'button'; editor.append(languageLabel, enLabel, esLabel, save);
            save.onclick = async () => {
              const f = options.formats.find(x => x.id === format.value), refs = moments.filter(x => x.c.checked).map(x => x.value.ref), sourceRefs = sources.filter(x => x.c.checked).map(x => x.value.ref), selected = contributions.filter(x => x.c.checked).map(x => ({id:x.value.id, revision:x.value.revision})), ids = new Set(selected.map(x => x.id)), interpretations = {};
              if (en.value.trim()) interpretations.en = en.value.trim(); if (es.value.trim()) interpretations.es = es.value.trim();
              if (!f || ![...refs, ...sourceRefs].some(r => r.sourceId === result.change.sourceId && r.sourceRevision === result.change.revision) || !interpretations[language.value] || [...(f.decision.reasonIds || []), ...(f.decision.minorityIds || [])].some(id => !ids.has(id))) { displayStatus.textContent = 'Select the corrected source, an outcome, its required contributions and an original-language interpretation.'; return; }
              const payload = {replacementId:item.replacementId, fence:result.change.fence, refs, ...(sourceRefs.length ? {sourceRefs} : {}), chapters:chapters.filter(x => x.c.checked).map(x => ({id:x.value.id, revision:x.value.revision})), format:{id:f.id, revision:f.revision}, contributions:selected, sourceLanguage:language.value, interpretations};
              save.disabled = true;
              try {
                if (protectedScope) {
                  const settled = await protectedSubmit(scope, {kind:'record', intentId:result.change.id, targetId:item.id, sourceId:result.change.sourceId, sourceRevision:result.change.revision, payload}, () => ticket === generation && JSON.stringify(refs) === JSON.stringify(moments.filter(x => x.c.checked).map(x => x.value.ref)) && JSON.stringify(sourceRefs) === JSON.stringify(sources.filter(x => x.c.checked).map(x => x.value.ref)) && JSON.stringify(payload.chapters) === JSON.stringify(chapters.filter(x => x.c.checked).map(x => ({id:x.value.id, revision:x.value.revision}))) && format.value === f.id && JSON.stringify(selected) === JSON.stringify(contributions.filter(x => x.c.checked).map(x => ({id:x.value.id, revision:x.value.revision}))) && language.value === payload.sourceLanguage && (en.value.trim() || undefined) === interpretations.en && (es.value.trim() || undefined) === interpretations.es);
                  if (protectedCurrent()) displayStatus.textContent = `Replacement receipt confirmed at version ${settled.version}. Read the current correction again before review.`;
                  return;
                }
                available(scope); const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify({intentId:result.change.id, payload}))), fingerprint = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
                await navigator.locks.request(lockFor(scope), async () => { checkScope(scope); if (ticket !== generation || JSON.stringify(refs) !== JSON.stringify(moments.filter(x => x.c.checked).map(x => x.value.ref)) || JSON.stringify(sourceRefs) !== JSON.stringify(sources.filter(x => x.c.checked).map(x => x.value.ref)) || JSON.stringify(payload.chapters) !== JSON.stringify(chapters.filter(x => x.c.checked).map(x => ({id:x.value.id, revision:x.value.revision}))) || format.value !== f.id || JSON.stringify(selected) !== JSON.stringify(contributions.filter(x => x.c.checked).map(x => ({id:x.value.id, revision:x.value.revision}))) || language.value !== payload.sourceLanguage || (en.value.trim() || undefined) !== interpretations.en || (es.value.trim() || undefined) !== interpretations.es) throw Error('View changed'); const key = `${keyFor(scope)}:replacement`, saved = localStorage.getItem(key); if (saved !== null) throw Error('Previous replacement remains unconfirmed; check its current receipt'); if (!saved) localStorage.setItem(key, fingerprint); const response = await replaceRecord(result.change.id, payload, scope); checkScope(scope); if (response?.replacement?.replacementId !== item.replacementId || response.replacement.status !== 'draft' || response.replacement.recordId !== item.id || !Number.isInteger(response.replacement.version)) throw Error('Unexpected receipt'); if (localStorage.getItem(key) === fingerprint) localStorage.removeItem(key); if (ticket === generation) { displayStatus.textContent = 'Record replacement saved as a draft. Review and approve the new version.'; const review = el('button', 'Review replacement record'); review.type = 'button'; review.onclick = async () => { try { checkScope(scope); if (ticket === generation) await openRecord(response.replacement.recordId, scope, response.replacement.version, review); } catch { if (ticket === generation) displayStatus.textContent = 'Record access changed. Refresh before review.'; } }; editor.append(review); } });
              } catch { if (ticket === generation) displayStatus.textContent = 'Record replacement not confirmed. Check the current correction receipt before any further action.'; } finally { save.disabled = false; }
            };
          } catch { if (ticket === generation) displayStatus.textContent = 'Current record options are unavailable.'; } finally { load.disabled = false; }
        };
      }
      list.append(row);
    }
    displayOutput.append(list);
  }
  submit.onclick = async () => {
    const scope = identity(), chosen = source, text = correction.value.trim(), title = correctedTitle.value.trim(), sourceStatus = correctedStatus.value, audience = visibility.value, expiryChoice = expiryMode.value, expiryValue = expiry.value, ticket = generation;
    if (!chosen || !reviewed || (!text && !title && !sourceStatus && !audience && !expiryChoice)) { status.textContent = 'Preview the selected source and enter a correction.'; return; }
    if (expiryChoice === 'set' && (!expiryValue || !Number.isFinite(new Date(expiryValue).getTime()))) { status.textContent = 'Enter a valid local expiry date and time.'; return; }
    submit.disabled = true;
    try {
      available(scope);
      const changes = {}; if (text) changes.text = text; if (title) changes.title = title; if (sourceStatus) changes.status = sourceStatus; if (audience) changes.audienceVisible = audience === 'visible'; if (expiryChoice) changes.expiresAt = expiryChoice === 'clear' ? null : new Date(expiryValue).toISOString();
      const payload = {...chosen, change: changes};
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(payload)));
      const fingerprint = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
      await navigator.locks.request(lockFor(scope), async () => {
        assertIdentity(scope); if (ticket !== generation || source !== chosen || !reviewed || correction.value.trim() !== text || correctedTitle.value.trim() !== title || correctedStatus.value !== sourceStatus || visibility.value !== audience || expiryMode.value !== expiryChoice || expiry.value !== expiryValue) throw Error('Selection changed');
        const key = keyFor(scope), saved = localStorage.getItem(key); let marker;
        if (saved) { marker = JSON.parse(saved); if (marker.fingerprint !== fingerprint || typeof marker.requestId !== 'string') throw Error('Previous correction remains unconfirmed'); }
        else { marker = {fingerprint, requestId: crypto.randomUUID()}; localStorage.setItem(key, JSON.stringify(marker)); }
        const result = await change({...payload, requestId: marker.requestId}, scope);
        assertIdentity(scope); if (!result?.change?.id || !Array.isArray(result.change.affected)) throw Error('Unexpected correction receipt');
        remember(scope, result.change.id);
        if (localStorage.getItem(key) === JSON.stringify(marker)) localStorage.removeItem(key);
        if (ticket === generation) { showChange(result); reviewed = false; status.textContent = 'Correction saved.'; }
      });
    } catch { if (ticket === generation) status.textContent = 'Correction was not confirmed. Check the previous correction or re-enter the exact original text and source to retry.'; }
    finally { submit.disabled = false; }
  };
  recover.onclick = async () => {
    const scope = identity(), ticket = generation; recover.disabled = true;
    try {
      available(scope);
      await navigator.locks.request(lockFor(scope), async () => {
        assertIdentity(scope); const key = keyFor(scope), saved = localStorage.getItem(key);
        if (!saved) { if (ticket === generation) status.textContent = 'No unconfirmed correction for this identity.'; return; }
        const marker = JSON.parse(saved); if (typeof marker.requestId !== 'string') throw Error('Invalid recovery marker');
        const result = await request(marker.requestId, scope); assertIdentity(scope);
        if (ticket !== generation) return;
        showChange(result); remember(scope, result.change.id);
        if (localStorage.getItem(key) === saved) localStorage.removeItem(key);
        reviewed = false; status.textContent = 'Previous correction confirmed.';
      });
    } catch { if (ticket === generation) status.textContent = 'Previous correction remains unconfirmed. Its request is preserved.'; }
    finally { recover.disabled = false; }
  };
  reopen.onclick = async () => {
    const scope = identity(), ticket = generation; reopen.disabled = true;
    try {
      available(scope); assertIdentity(scope);
      const id = localStorage.getItem(intentKeyFor(scope));
      if (!id) { status.textContent = 'No saved correction for this identity.'; return; }
      const result = await getChange(id, scope); assertIdentity(scope);
      if (ticket !== generation) return;
      showChange(result); status.textContent = 'Current correction loaded.';
    } catch { if (ticket === generation) status.textContent = 'Correction unavailable or no longer current.'; }
    finally { reopen.disabled = false; }
  };
  reset(); return {reset};
}


// The opted-in replacement journal derives its key from the re-entered capability.
// Callers must hold an exclusive navigator lock for the whole save/dispatch cycle.
export function createImpactReplacementJournal({scope, isCurrent, storage = globalThis.localStorage, cryptoProvider = globalThis.crypto}) {
  const captured = {...scope};
  const enc = new TextEncoder(), dec = new TextDecoder('utf-8', {fatal:true});
  let destroyed = false;
  function guard() {
    if (destroyed || isCurrent() !== true || captured.role !== 'creator' || !captured.sessionId || !captured.actorBinding || !captured.token || !storage || !cryptoProvider?.subtle) throw Error('Protected recovery unavailable');
  }
  const context = JSON.stringify(['w21-replacement', 1, captured.sessionId, captured.actorBinding]);
  async function nameAndKey() {
    guard();
    const nameHash = await cryptoProvider.subtle.digest('SHA-256', enc.encode(context)); guard();
    const raw = await cryptoProvider.subtle.digest('SHA-256', enc.encode(JSON.stringify([context, captured.token]))); guard();
    const key = await cryptoProvider.subtle.importKey('raw', raw, {name:'AES-GCM'}, false, ['encrypt','decrypt']); guard();
    return {name:'entrelineas.w21.protected.v1:' + Array.from(new Uint8Array(nameHash), b => b.toString(16).padStart(2,'0')).join(''), key};
  }
  async function load() {
    const {name,key} = await nameAndKey(); guard(); const raw = storage.getItem(name); if (raw === null) return null;
    const envelope = JSON.parse(raw);
    if (envelope?.v !== 1 || !Array.isArray(envelope.iv) || envelope.iv.length !== 12 || !Array.isArray(envelope.cipher) || envelope.cipher.length < 16 || envelope.cipher.length > 100000 || ![...envelope.iv,...envelope.cipher].every(x => Number.isInteger(x) && x >= 0 && x <= 255)) throw Error('Invalid protected recovery');
    const bytes = await cryptoProvider.subtle.decrypt({name:'AES-GCM',iv:new Uint8Array(envelope.iv),additionalData:enc.encode(context)},key,new Uint8Array(envelope.cipher)); guard();
    const pending = JSON.parse(dec.decode(bytes));
    if (!validPending(pending) || storage.getItem(name) !== raw) throw Error('Invalid protected recovery');
    return pending;
  }
  async function save(pending) {
    guard(); const snapshot = JSON.parse(JSON.stringify(pending));
    if (!validPending(snapshot)) throw Error('Invalid protected request');
    const {name,key} = await nameAndKey(); guard(); if (storage.getItem(name) !== null) throw Error('Prior operation pending');
    const iv = cryptoProvider.getRandomValues(new Uint8Array(12));
    const cipher = await cryptoProvider.subtle.encrypt({name:'AES-GCM',iv,additionalData:enc.encode(context)},key,enc.encode(JSON.stringify(snapshot))); guard();
    if (storage.getItem(name) !== null) throw Error('Prior operation pending');
    const envelope = JSON.stringify({v:1,iv:Array.from(iv),cipher:Array.from(new Uint8Array(cipher))});
    storage.setItem(name,envelope); guard();
    if (storage.getItem(name) !== envelope) throw Error('Protected recovery was not stored');
  }
  function validPending(p) {
    return !!p && ['material','record'].includes(p.kind) && typeof p.intentId === 'string' && !!p.intentId && typeof p.targetId === 'string' && !!p.targetId && typeof p.sourceId === 'string' && !!p.sourceId && Number.isSafeInteger(p.sourceRevision) && p.sourceRevision > 0 && typeof p.payload?.replacementId === 'string' && !!p.payload.replacementId && typeof p.payload.fence === 'string' && !!p.payload.fence;
  }
  // A current server receipt settles the registered target, not which payload
  // won a race. Call only while holding the same lock used for dispatch.
  async function settle(result) {
    const {name} = await nameAndKey(); guard();
    const before = storage.getItem(name);
    if (before === null) return null;
    const pending = await load(); guard();
    const change = result?.change;
    const target = change?.affected?.find(x => x.kind === pending.kind && x.id === pending.targetId && x.replacementId === pending.payload.replacementId);
    if (change?.id !== pending.intentId || change?.sourceId !== pending.sourceId || change?.revision !== pending.sourceRevision || change?.fence !== pending.payload.fence || change?.correctionReceipt !== 'confirmed' || target?.state !== 'applied' || target?.replacementReceipt !== 'confirmed' || !Number.isSafeInteger(target?.replacement?.version) || target.replacement.version < 1) throw Error('Replacement remains unconfirmed');
    guard(); if (storage.getItem(name) !== before) throw Error('Protected request changed');
    storage.removeItem(name); guard();
    if (storage.getItem(name) !== null) throw Error('Protected request not cleared');
    return {kind:pending.kind, targetId:pending.targetId, version:target.replacement.version};
  }
  return {load, save, settle, destroy() { destroyed = true; captured.token = null; }};
}

// This adapter never retries a request. The caller must invoke submit only in
// response to a creator action, and may use readback after an unknown result.
export function createImpactReplacementAction({scope, isCurrent, recoverSource, dispatch, storage, cryptoProvider = globalThis.crypto, locks = globalThis.navigator?.locks}) {
  const journal = createImpactReplacementJournal({scope, isCurrent, storage, cryptoProvider});
  const lock = `entrelineas.w21.protected-action:${scope.sessionId}:${scope.actorBinding}`;
  function guard() {
    if (isCurrent() !== true || !locks?.request) throw Error('Current creator access required');
  }
  async function readback(sourceId) {
    guard();
    return locks.request(lock, async () => {
      guard(); const pending = await journal.load(); guard();
      if (!pending || pending.sourceId !== sourceId) throw Error('No matching protected request');
      const receipt = await recoverSource(sourceId, scope); guard();
      return journal.settle(receipt);
    });
  }
  async function submit(pending) {
    guard();
    const snapshot = JSON.parse(JSON.stringify(pending));
    return locks.request(lock, async () => {
      guard(); if (await journal.load()) throw Error('Previous request remains unconfirmed');
      guard(); const fresh = await recoverSource(snapshot.sourceId, scope); guard();
      const change = fresh?.change;
      const target = change?.affected?.find(x => x.kind === snapshot.kind && x.id === snapshot.targetId && x.replacementId === snapshot.payload?.replacementId);
      if (change?.id !== snapshot.intentId || change?.sourceId !== snapshot.sourceId || change?.revision !== snapshot.sourceRevision || change?.fence !== snapshot.payload?.fence || change?.correctionReceipt !== 'confirmed' || target?.state !== 'pending_replacement') throw Error('Current target unavailable');
      if (snapshot.kind === 'material' && (!sameMaterialSegment(target, snapshot.segmentBinding ?? null) || (snapshot.segmentBinding ? snapshot.payload.segmentRevision !== snapshot.segmentBinding.revision : Object.hasOwn(snapshot.payload, 'segmentRevision')))) throw Error('Current material binding changed');
      await journal.save(snapshot); guard();
      await dispatch(snapshot.kind, snapshot.intentId, snapshot.payload, scope); guard();
      const receipt = await recoverSource(snapshot.sourceId, scope); guard();
      return journal.settle(receipt);
    });
  }
  return {submit, readback, destroy:journal.destroy};
}

// Explicit exact-version approval; an unresolved request is read back only.
export function createImpactApprovalAction({scope, isCurrent, assertClear, beforeDispatch = () => {}, readCurrent, readReceipt, dispatch, storage = globalThis.localStorage, cryptoProvider = globalThis.crypto, locks = globalThis.navigator?.locks}) {
  const captured = {...scope}, encoder = new TextEncoder(), decoder = new TextDecoder('utf-8', {fatal:true});
  let destroyed = false;
  const context = JSON.stringify(['w21-approval', 1, captured.sessionId, captured.actorBinding]);
  function guard() {
    if (destroyed || isCurrent() !== true || captured.role !== 'creator' || !captured.sessionId || !captured.actorBinding || !captured.token || !locks?.request || !storage || !cryptoProvider?.subtle) throw Error('Protected approval unavailable');
  }
  async function keyAndName() {
    guard(); const hash = await cryptoProvider.subtle.digest('SHA-256', encoder.encode(context)); guard();
    const raw = await cryptoProvider.subtle.digest('SHA-256', encoder.encode(JSON.stringify([context,captured.token]))); guard();
    const key = await cryptoProvider.subtle.importKey('raw',raw,{name:'AES-GCM'},false,['encrypt','decrypt']); guard();
    return {key, name:'entrelineas.w21.approval.v1:' + Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2,'0')).join('')};
  }
  function valid(p) {
    return p && ['material','record'].includes(p.kind) && typeof p.id === 'string' && !!p.id && Number.isSafeInteger(p.version) && p.version > 0 && typeof p.requestId === 'string' && !!p.requestId && (p.kind !== 'record' || Number.isSafeInteger(p.revision) && p.revision > 0);
  }
  async function load() {
    const {key,name} = await keyAndName(); guard(); const raw = storage.getItem(name); if (raw === null) return null;
    const e = JSON.parse(raw); if (e?.v !== 1 || !Array.isArray(e.iv) || e.iv.length !== 12 || !Array.isArray(e.cipher) || e.cipher.length < 16 || e.cipher.length > 10000 || ![...e.iv,...e.cipher].every(n => Number.isInteger(n) && n >= 0 && n <= 255)) throw Error('Invalid approval recovery');
    const bytes = await cryptoProvider.subtle.decrypt({name:'AES-GCM',iv:new Uint8Array(e.iv),additionalData:encoder.encode(context)},key,new Uint8Array(e.cipher)); guard();
    const pending = JSON.parse(decoder.decode(bytes)); if (!valid(pending) || storage.getItem(name) !== raw) throw Error('Approval recovery changed'); return {pending,raw,name};
  }
  async function save(pending) {
    if (!valid(pending)) throw Error('Invalid approval'); const {key,name} = await keyAndName(); guard(); if (storage.getItem(name) !== null) throw Error('Earlier approval unresolved');
    const iv = cryptoProvider.getRandomValues(new Uint8Array(12)); const cipher = await cryptoProvider.subtle.encrypt({name:'AES-GCM',iv,additionalData:encoder.encode(context)},key,encoder.encode(JSON.stringify(pending))); guard();
    if (storage.getItem(name) !== null) throw Error('Earlier approval unresolved'); const raw=JSON.stringify({v:1,iv:Array.from(iv),cipher:Array.from(new Uint8Array(cipher))}); storage.setItem(name,raw); guard(); if (storage.getItem(name)!==raw) throw Error('Approval recovery was not stored');
  }
  async function settle(entry) {
    guard(); const p=entry.pending;
    let receipt; if (p.kind === 'record') { receipt=await readReceipt(p.requestId,captured); guard(); if (receipt?.operation?.requestId !== p.requestId || receipt.operation.state !== 'committed' || receipt.operation.recordId !== p.id || !Number.isSafeInteger(receipt.operation.revision)) throw Error('Approval remains unconfirmed'); }
    const result=await readCurrent(p.kind,p.id,captured); guard(); const obj=p.kind === 'record' ? result?.record : result?.material || result;
    if (p.kind === 'record' ? result?.stale || obj?.stale || obj?.id !== p.id || obj?.version !== p.version || obj?._revision !== receipt.operation.revision || obj?.state !== 'approved' : obj?.redacted || obj?.id !== p.id || obj?.currentVersion !== p.version || obj?.approvedVersion !== p.version || !['approved','published'].includes(obj?.status)) throw Error('Approval remains unconfirmed');
    if (storage.getItem(entry.name)!==entry.raw) throw Error('Approval recovery changed'); storage.removeItem(entry.name); guard(); if (storage.getItem(entry.name)!==null) throw Error('Approval recovery not cleared'); return {kind:p.kind,id:p.id,version:p.version};
  }
  const lock=`entrelineas.w21.approval:${captured.sessionId}:${captured.actorBinding}`;
  async function readback(expected) { guard(); return locks.request('entrelineas.w21.impact:' + captured.sessionId + ':' + captured.actorBinding,()=>locks.request(lock,async()=>{ guard(); const entry=await load(); guard(); if (!entry || expected && (entry.pending.kind !== expected.kind || entry.pending.id !== expected.id || entry.pending.version !== expected.version)) throw Error('No matching pending approval'); return settle(entry); })); }
  async function submit(input) {
    guard(); const p=JSON.parse(JSON.stringify(input)); if (!valid(p)) throw Error('Invalid approval');
    return locks.request('entrelineas.w21.impact:' + captured.sessionId + ':' + captured.actorBinding,()=>locks.request(lock,async()=>{ guard(); if (await load()) throw Error('Earlier approval unresolved'); guard(); await assertClear(p,captured); guard();
      const result=await readCurrent(p.kind,p.id,captured); guard(); const obj=p.kind==='record' ? result?.record : result?.material || result;
      if (p.kind==='record' ? result?.stale || obj?.stale || obj?.id!==p.id || obj?.version!==p.version || obj?._revision!==p.revision || obj?.state!=='draft' : obj?.redacted || obj?.id!==p.id || obj?.currentVersion!==p.version || obj?.status!=='draft') throw Error('Review changed');
      await save(p); guard(); await beforeDispatch(p,captured); guard(); await dispatch(p,captured); guard(); const entry=await load(); guard(); if (!entry || JSON.stringify(entry.pending)!==JSON.stringify(p)) throw Error('Approval recovery changed'); return settle(entry);
    }));
  }
  return {submit,readback,destroy(){destroyed=true;captured.token=null;}};
}

// Tab-only format actions use a separate encrypted, receipt-only journal.
export function createProtectedFormatAction({scope, isCurrent, call, storage=globalThis.localStorage, cryptoProvider=globalThis.crypto, locks=globalThis.navigator?.locks}) {
  const captured={...scope}, enc=new TextEncoder(), dec=new TextDecoder();
  const context=JSON.stringify(['w15-protected',1,captured.sessionId,captured.actorBinding]);
  let destroyed=false;
  const guard=()=>{if(destroyed || !isCurrent() || captured.role!=='creator' || !captured.token || !captured.sessionId || !captured.actorBinding || !storage || !locks?.request || !cryptoProvider?.subtle) throw Error('Current creator access required');};
  async function keyName(){guard(); const digest=await cryptoProvider.subtle.digest('SHA-256',enc.encode(context)); guard(); const raw=await cryptoProvider.subtle.digest('SHA-256',enc.encode(JSON.stringify([context,captured.token]))); guard(); const key=await cryptoProvider.subtle.importKey('raw',raw,'AES-GCM',false,['encrypt','decrypt']); guard(); return {key,name:'entrelineas.w15.protected.v1:'+Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('')};}
  async function load(){const {key,name}=await keyName();guard();const raw=storage.getItem(name);if(raw===null)return null;const e=JSON.parse(raw);if(e?.v!==1 || !Array.isArray(e.iv) || e.iv.length!==12 || !Array.isArray(e.cipher) || e.cipher.length<16 || e.cipher.length>100000 || ![...e.iv,...e.cipher].every(x=>Number.isInteger(x)&&x>=0&&x<=255))throw Error('Invalid recovery');const bytes=await cryptoProvider.subtle.decrypt({name:'AES-GCM',iv:new Uint8Array(e.iv),additionalData:enc.encode(context)},key,new Uint8Array(e.cipher));guard();const pending=JSON.parse(dec.decode(bytes));if(!['w15CreateFormat','w15FormatDecision'].includes(pending.route)||!pending.requestId||storage.getItem(name)!==raw)throw Error('Invalid recovery');return {pending,raw,name};}
  async function save(p){const {key,name}=await keyName();guard();if(storage.getItem(name)!==null)throw Error('Prior action unresolved');const iv=cryptoProvider.getRandomValues(new Uint8Array(12));const cipher=await cryptoProvider.subtle.encrypt({name:'AES-GCM',iv,additionalData:enc.encode(context)},key,enc.encode(JSON.stringify(p)));guard();if(storage.getItem(name)!==null)throw Error('Prior action unresolved');const raw=JSON.stringify({v:1,iv:Array.from(iv),cipher:Array.from(new Uint8Array(cipher))});storage.setItem(name,raw);guard();if(storage.getItem(name)!==raw)throw Error('Recovery not stored');}
  async function settle(entry){guard();const p=entry.pending;const response=await call('w15FormatReceipt',null,p.requestId,{scope:captured});guard();const operation=p.route==='w15CreateFormat'?'POST /formats':`POST /formats/${p.id}/decision`;if(response?.receipt?.requestId!==p.requestId || response.receipt.state!=='committed' || response.receipt.operation!==operation || response.receipt.status<200 || response.receipt.status>=300)throw Error('Action remains unconfirmed');if(storage.getItem(entry.name)!==entry.raw)throw Error('Recovery changed');storage.removeItem(entry.name);guard();if(storage.getItem(entry.name)!==null)throw Error('Recovery not cleared');return true;}
  const lock='entrelineas.w15.protected:'+captured.sessionId+':'+captured.actorBinding;
  async function submit(route,body,id=null){guard();if(!['w15CreateFormat','w15FormatDecision'].includes(route) || (route==='w15FormatDecision' && !id))throw Error('Invalid action');return locks.request(lock,async()=>{guard();if(await load())throw Error('Prior action unresolved');const p={route,id,requestId:cryptoProvider.randomUUID(),body:JSON.parse(JSON.stringify(body))};await save(p);guard();const args=id?[id]:[];await call(route,{...p.body,mutationRequestId:p.requestId},...args,{scope:captured});guard();const entry=await load();guard();if(!entry || entry.pending.requestId!==p.requestId)throw Error('Recovery changed');return settle(entry);});}
  async function readback(){guard();return locks.request(lock,async()=>{guard();const entry=await load();if(!entry)throw Error('No pending action');return settle(entry);});}
  return {submit,readback,destroy(){destroyed=true;captured.token=null;}};
}
