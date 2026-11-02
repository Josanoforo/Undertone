/* Coauthor draft controls and recovery; see owner HANDOFF.md. */
import { diffConflict } from './waves28-conflict.js';
export function mountCoeditSetup(root, {identity, assertIdentity, grant, create, openCreated}) {
  const details = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = 'Create a coauthor draft';
  const form = document.createElement('form');
  const inputs = {};
  for (const [name, label, type] of [['draftId','New draft ID','text'],['segmentId','Segment ID','text'],['materialId','Studio material ID','text'],['baseMaterialVersion','Current material version','number'],['collaboratorId','Collaborator ID','text'],['expiresAt','Grant expiry','datetime-local']]) {
    const wrapper = document.createElement('label'), input = document.createElement('input');
    wrapper.textContent = label; input.type = type; input.required = true;
    if (type === 'text') input.maxLength = 128;
    if (type === 'number') { input.min = '0'; input.step = '1'; }
    wrapper.append(input); form.append(wrapper); inputs[name] = input;
  }
  const button = document.createElement('button'); button.type = 'submit'; button.textContent = 'Grant access and create draft';
  const status = document.createElement('p'); status.setAttribute('role','status');
  const help = document.createElement('p'); help.textContent = 'Use the current segment and material version and the collaborator’s actor ID. If the result is unconfirmed, re-enter exactly the same values to recover it.';
  form.append(button); details.append(summary,help,form,status); root.append(details);
  let generation = 0;
  form.addEventListener('input', () => {
    generation++;
    button.disabled = false;
    status.textContent = 'Details changed. If a previous setup was sent, re-enter its exact values to recover it.';
  });
  const digest = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)))), b => b.toString(16).padStart(2,'0')).join('');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const scope = identity(), epoch = ++generation;
    if (scope.role !== 'creator' || !scope.sessionId || !scope.token) { status.textContent = 'Join as the creator to create a draft.'; return; }
    const body = {draftId:inputs.draftId.value.trim(), segmentId:inputs.segmentId.value.trim(), materialId:inputs.materialId.value.trim(), baseMaterialVersion:Number(inputs.baseMaterialVersion.value), collaboratorId:inputs.collaboratorId.value.trim(), expiresAt:Date.parse(inputs.expiresAt.value)/1000};
    if (!['draftId','segmentId','materialId','collaboratorId'].every(k => /^[A-Za-z0-9._:-]{1,128}$/.test(body[k])) || !Number.isSafeInteger(body.baseMaterialVersion) || body.baseMaterialVersion < 0 || !Number.isFinite(body.expiresAt)) { status.textContent = 'Check the IDs, version and expiry.'; return; }
    button.disabled = true; status.textContent = 'Creating the grant and draft…';
    try {
      assertIdentity(scope);
      const key = 'entrelineas.w22.coedit.setup.v1:' + await digest([scope.sessionId,scope.actorBinding]);
      const fingerprint = await digest(body); assertIdentity(scope);
      if (!navigator.locks) throw Error('Lock unavailable');
      await navigator.locks.request(key, async () => {
        assertIdentity(scope); if (epoch !== generation) return;
        let saved = JSON.parse(localStorage.getItem(key) || 'null');
        if (saved && (saved.fingerprint !== fingerprint || !/^[A-Za-z0-9._:-]{1,128}$/.test(saved.requestId || ''))) throw Error('A different setup remains unconfirmed');
        if (!saved) { saved = {fingerprint, requestId:crypto.randomUUID()}; localStorage.setItem(key, JSON.stringify(saved)); }
        await grant(body,scope); assertIdentity(scope); if (epoch !== generation) return;
        const {expiresAt, ...draft} = body;
        const result = await create({...draft, requestId:saved.requestId},scope);
        assertIdentity(scope); if (epoch !== generation) return;
        if (result?.operation?.state !== 'committed' || result?.draft?.draftId !== body.draftId) throw Error('Draft unconfirmed');
        const current = JSON.parse(localStorage.getItem(key) || 'null');
        if (current?.requestId !== saved.requestId || current?.fingerprint !== fingerprint) throw Error('Recovery record changed');
        localStorage.removeItem(key); status.textContent = 'Draft created.';
        if (typeof openCreated === 'function') {
          try { openCreated(body.draftId, scope); } catch (_) { status.textContent = 'Draft created. Use Find my coauthor drafts to open it.'; }
        }
      });
    } catch (_) { if (epoch === generation) status.textContent = 'Setup remains unconfirmed. Re-enter the exact same values to recover it; no different setup will be sent.'; }
    finally { if (epoch === generation) button.disabled = false; }
  });
  return {
    selectMaterial(selection, captured) {
      try { assertIdentity(captured); } catch (_) { return; }
      if (captured.role !== 'creator' || !/^[A-Za-z0-9._:-]{1,128}$/.test(selection?.segmentId || '') || !/^[A-Za-z0-9._:-]{1,128}$/.test(selection?.materialId || '') || !Number.isSafeInteger(selection?.version) || selection.version < 0) return;
      generation++; button.disabled = false;
      inputs.segmentId.value = selection.segmentId; inputs.materialId.value = selection.materialId; inputs.baseMaterialVersion.value = String(selection.version);
      details.open = true; status.textContent = 'Current segment and material selected. Enter the collaborator and draft details.';
      summary.focus(); details.scrollIntoView();
    },
    reset() { generation++; form.reset(); button.disabled = false; status.textContent = ''; }
  };
}
export function mountCoeditAccess(root, {identity, assertIdentity, list, revokeGrant, read, readOperation, mutate, openDesk}) {
  const details = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = 'Open a coauthor draft';
  const form = document.createElement('form');
  const label = document.createElement('label'); label.textContent = 'Draft ID';
  const input = document.createElement('input'); input.required = true; input.maxLength = 128; label.append(input);
  const button = document.createElement('button'); button.type = 'submit'; button.textContent = 'Open draft';
  const status = document.createElement('p'); status.setAttribute('role','status');
  const recover = document.createElement('button'); recover.type = 'button'; recover.textContent = 'Recover prior operation';
  const loadGrants = document.createElement('button'); loadGrants.type = 'button'; loadGrants.textContent = 'Find my coauthor drafts';
  const recoverGrant = document.createElement('button'); recoverGrant.type = 'button'; recoverGrant.textContent = 'Recover prior access revocation';
  const grants = document.createElement('div');
  const content = document.createElement('div'); form.append(label,button); details.append(summary,loadGrants,recoverGrant,grants,form,recover,status,content); root.append(details);
  let generation = 0, editor = null;
  async function journalKey(id, captured) {
    const bytes = new TextEncoder().encode(JSON.stringify([captured.sessionId,captured.actorBinding,id]));
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)), b => b.toString(16).padStart(2,'0')).join('');
    return `entrelineas.w22.coedit.v1:${digest}`;
  }
  async function fingerprint(payload) {
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2,'0')).join('');
  }
  async function revokeKey(captured) {
    return 'entrelineas.w22.coedit.grant-revoke.v1:' + await fingerprint([captured.sessionId,captured.actorBinding]);
  }
  async function reconcileRevoke(captured, key) {
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    if (!saved) return true;
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(saved.draftId || '') || !Number.isSafeInteger(saved.revision) || saved.revision < 0) throw Error('Invalid recovery record');
    const result = await list(captured); assertIdentity(captured);
    if (!Array.isArray(result?.grants)) throw Error('Invalid grant list');
    const grant = result.grants.find(item => item?.draftId === saved.draftId);
    if (grant?.active === false && grant.revision === saved.revision + 1) {
      localStorage.removeItem(key); return true;
    }
    return false;
  }
  async function revokeSelected(grant, captured, epoch) {
    if (captured.role !== 'creator' || typeof revokeGrant !== 'function' || !Number.isSafeInteger(grant.revision) || grant.revision < 0) return;
    if (!window.confirm('Revoke this collaborator’s access to the draft?')) return;
    try {
      assertIdentity(captured); const key = await revokeKey(captured); assertIdentity(captured);
      if (!navigator.locks) throw Error('Lock unavailable');
      await navigator.locks.request(key, async () => {
        assertIdentity(captured); if (generation !== epoch) return;
        if (!await reconcileRevoke(captured, key)) throw Error('Previous revocation unconfirmed');
        assertIdentity(captured); if (generation !== epoch) return;
        localStorage.setItem(key, JSON.stringify({draftId:grant.draftId, revision:grant.revision}));
        const result = await revokeGrant(grant.draftId, grant.revision, captured);
        assertIdentity(captured);
        if (result?.revoked !== true || result.revision !== grant.revision + 1) throw Error('Revocation unconfirmed');
        const saved = JSON.parse(localStorage.getItem(key) || 'null');
        if (saved?.draftId !== grant.draftId || saved.revision !== grant.revision) throw Error('Recovery record changed');
        localStorage.removeItem(key);
        if (generation === epoch) { grants.replaceChildren(); editor?.destroy(); editor = null; status.textContent = 'Access revoked. Refresh the grant list.'; }
      });
    } catch (_) { if (generation === epoch) { grants.replaceChildren(); editor?.destroy(); editor = null; status.textContent = 'Revocation is unconfirmed. Refresh the grant list to check the saved operation.'; } }
  }
  recoverGrant.addEventListener('click', async () => {
    const captured = identity(), epoch = ++generation;
    editor?.destroy(); editor = null; grants.replaceChildren();
    if (captured.role !== 'creator' || !captured.sessionId || !captured.token || typeof revokeGrant !== 'function') { status.textContent = 'Join as creator to recover a revocation.'; return; }
    try {
      assertIdentity(captured); const key = await revokeKey(captured); assertIdentity(captured);
      if (!navigator.locks) throw Error('Lock unavailable');
      await navigator.locks.request(key, async () => {
        assertIdentity(captured); if (generation !== epoch) return;
        const saved = JSON.parse(localStorage.getItem(key) || 'null');
        if (!saved) { status.textContent = 'No prior revocation is recorded.'; return; }
        if (await reconcileRevoke(captured,key)) { if (generation === epoch) status.textContent = 'The prior revocation was confirmed.'; return; }
        const current = await list(captured); assertIdentity(captured); if (generation !== epoch) return;
        const grant = current?.grants?.find(item => item?.draftId === saved.draftId);
        if (grant?.active !== true || grant.revision !== saved.revision) throw Error('Grant changed');
        const result = await revokeGrant(saved.draftId,saved.revision,captured); assertIdentity(captured);
        if (result?.revoked !== true || result.revision !== saved.revision + 1) throw Error('Revocation unconfirmed');
        const pending = JSON.parse(localStorage.getItem(key) || 'null');
        if (pending?.draftId !== saved.draftId || pending.revision !== saved.revision) throw Error('Recovery record changed');
        localStorage.removeItem(key); if (generation === epoch) status.textContent = 'The prior revocation was confirmed.';
      });
    } catch (_) { if (generation === epoch) status.textContent = 'The prior revocation remains unconfirmed. Its recovery record was retained.'; }
  });
  recover.addEventListener('click', async () => {
    const id = input.value.trim(), captured = identity(), epoch = ++generation;
    editor?.destroy(); editor = null;
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(id) || !captured.sessionId || !captured.token) { status.textContent = 'Enter the original draft ID and join the session.'; return; }
    status.textContent = 'Checking the prior operation…';
    try {
      assertIdentity(captured); const key = await journalKey(id, captured); assertIdentity(captured);
      if (!navigator.locks) throw Error('Recovery lock unavailable');
      await navigator.locks.request(key, async () => {
        assertIdentity(captured); if (generation !== epoch || input.value.trim() !== id) return;
        const saved = JSON.parse(localStorage.getItem(key) || 'null');
        if (!saved) { status.textContent = 'No prior operation is recorded for this draft.'; return; }
        if (!['patch','approve','adopt','withdraw'].includes(saved.kind) || saved.draftId !== id || !Number.isInteger(saved.revision) || saved.revision < 0 || typeof saved.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(saved.requestId)) { status.textContent = 'Recovery metadata is invalid; no request was sent.'; return; }
        let result;
        if (saved.kind === 'adopt') {
          result = await mutate('adopt',id,{requestId:saved.requestId,expectedRevision:saved.revision},captured);
        } else {
          if (typeof readOperation !== 'function') throw Error('Receipt lookup unavailable');
          result = await readOperation(id,saved.requestId,captured);
          if (result?.operation?.action !== saved.kind) throw Error('Receipt action mismatch');
          if (saved.kind === 'patch' && (result.operation.state === 'conflict' ? result.operation.baseRevision !== saved.revision : result.operation.revision !== saved.revision + 1)) throw Error('Receipt revision mismatch');
        }
        assertIdentity(captured); if (generation !== epoch || input.value.trim() !== id) return;
        if (!result?.operation || !['committed','conflict'].includes(result.operation.state)) throw Error('Unconfirmed');
        const current = JSON.parse(localStorage.getItem(key) || 'null');
        if (!current || current.requestId !== saved.requestId || current.kind !== saved.kind || current.revision !== saved.revision || current.draftId !== id) throw Error('Recovery metadata changed');
        localStorage.removeItem(key);
        status.textContent = result.operation.state === 'conflict' ? 'The prior operation conflicted. Open the current draft to review it.' : saved.kind === 'withdraw' ? 'The prior withdrawal was confirmed.' : saved.kind === 'adopt' ? 'The prior adoption was confirmed. Review and approve the material separately in Studio.' : 'The prior operation was confirmed. Open the draft to review it.';
      });
    } catch (_) { if (generation === epoch) status.textContent = 'The prior operation remains unconfirmed. Its recovery record was retained.'; }
  });
  loadGrants.addEventListener('click', async () => {
    const captured = identity(), epoch = ++generation;
    editor?.destroy(); editor = null; grants.replaceChildren();
    if (!captured.sessionId || !captured.token || typeof list !== 'function') { status.textContent = 'Join the session to find drafts.'; return; }
    status.textContent = 'Finding your drafts…';
    try {
      assertIdentity(captured);
      if (captured.role === 'creator') {
        const key = await revokeKey(captured); assertIdentity(captured);
        if (!navigator.locks) throw Error('Lock unavailable');
        const resolved = await navigator.locks.request(key, () => reconcileRevoke(captured, key));
        assertIdentity(captured); if (generation !== epoch) return;
        if (!resolved) { status.textContent = 'A prior revocation remains unconfirmed. No new revocation will be sent.'; return; }
      }
      const result = await list(captured); assertIdentity(captured);
      if (generation !== epoch) return;
      if (!Array.isArray(result?.grants)) throw Error('Invalid grant list');
      const available = result.grants.filter(g => g && g.active === true && Number.isFinite(g.expiresAt) && g.expiresAt * 1000 > Date.now() && /^[A-Za-z0-9._:-]{1,128}$/.test(g.draftId || ''));
      for (const grant of available) {
        const choice = document.createElement('button'); choice.type = 'button';
        choice.textContent = `Open draft ${grant.draftId} · segment ${grant.segmentId}`;
        choice.addEventListener('click', () => {
          try { assertIdentity(captured); } catch (_) { return; }
          if (generation !== epoch) return;
          input.value = grant.draftId; form.requestSubmit();
        });
        grants.append(choice);
        if (typeof openDesk === 'function' && /^[A-Za-z0-9._:-]{1,128}$/.test(grant.segmentId || '')) {
          const desk = document.createElement('button'); desk.type = 'button'; desk.textContent = `Open editorial desk for draft ${grant.draftId}`;
          desk.addEventListener('click', () => { try { assertIdentity(captured); if (generation === epoch) openDesk({draftId:grant.draftId,segmentId:grant.segmentId},captured); } catch (_) {} });
          grants.append(desk);
        }
        if (captured.role === 'creator' && typeof revokeGrant === 'function' && Number.isSafeInteger(grant.revision) && grant.revision >= 0) {
          const revoke = document.createElement('button'); revoke.type = 'button'; revoke.textContent = `Revoke access to draft ${grant.draftId}`;
          revoke.addEventListener('click', () => revokeSelected(grant,captured,epoch)); grants.append(revoke);
        }
      }
      status.textContent = available.length ? 'Choose a draft. Current access is checked when it opens.' : 'No active coauthor grants are available.';
    } catch (_) { if (generation === epoch) { grants.replaceChildren(); status.textContent = 'Draft grants are unavailable. Try again.'; } }
  });
  function reset() { generation++; editor?.destroy(); editor = null; input.value = ''; grants.replaceChildren(); status.textContent = ''; }
  input.addEventListener('input', () => { generation++; editor?.destroy(); editor = null; status.textContent = ''; });
  form.addEventListener('submit', async event => {
    event.preventDefault(); const id = input.value.trim(), captured = identity(), epoch = ++generation;
    editor?.destroy(); editor = null;
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(id) || !captured.sessionId || !captured.token) { status.textContent = 'Enter a draft ID and join the session.'; return; }
    status.textContent = 'Opening draft…';
    try {
      assertIdentity(captured); const projection = await read(id,captured); assertIdentity(captured);
      if (generation !== epoch || input.value.trim() !== id) return;
      const scope = {sourceId:id, sessionId:captured.sessionId, actorId:captured.actorBinding, role:captured.role === 'creator' ? 'creator' : 'collaborator', revocationGeneration:captured.epoch, draftId:id};
      const key = await journalKey(id, captured);
      assertIdentity(captured); if (generation !== epoch || input.value.trim() !== id) return;
      let pending; try { pending = JSON.parse(localStorage.getItem(key) || 'null'); } catch (_) { pending = {invalid:true}; }
      const actions = {
        newRequestId: () => crypto.randomUUID(),
        assertCurrent: () => { assertIdentity(captured); if (generation !== epoch || input.value.trim() !== id) throw Error('Draft changed'); },
        withLock: fn => { if (!navigator.locks) throw Error('Recovery lock unavailable'); return navigator.locks.request(key, fn); },
        journal: async (meta, payload) => { assertIdentity(captured); const digest = meta.kind === 'patch' ? await fingerprint(payload) : undefined; assertIdentity(captured); if (generation !== epoch || input.value.trim() !== id) throw Error('Draft changed'); if (localStorage.getItem(key)) throw Error('Prior operation pending'); localStorage.setItem(key,JSON.stringify({...meta, ...(digest ? {fingerprint:digest} : {})})); },
        complete: async meta => { assertIdentity(captured); const saved = JSON.parse(localStorage.getItem(key) || 'null'); if (!saved || saved.requestId !== meta.requestId) throw Error('Recovery metadata changed'); localStorage.removeItem(key); },
        recover: async pending => {
          if (!navigator.locks || !pending) throw Error('Recovery unavailable');
          return navigator.locks.request(key, async () => {
            assertIdentity(captured);
            const raw = localStorage.getItem(key), saved = JSON.parse(raw || 'null');
            if (!saved || saved.draftId !== id || saved.requestId !== pending.requestId || saved.kind !== pending.kind || !['patch','approve','adopt','withdraw'].includes(saved.kind) || !Number.isSafeInteger(saved.revision) || saved.revision < 0 || !/^[A-Za-z0-9._:-]{1,128}$/.test(saved.requestId || '')) throw Error('Invalid recovery metadata');
            const result = saved.kind === 'adopt'
              ? await mutate('adopt',id,{requestId:saved.requestId,expectedRevision:saved.revision},captured)
              : await readOperation(id,saved.requestId,captured);
            assertIdentity(captured);
            if (generation !== epoch || input.value.trim() !== id || localStorage.getItem(key) !== raw) throw Error('Recovery context changed');
            if (!['committed','conflict'].includes(result?.operation?.state)) throw Error('Unconfirmed receipt');
            if (saved.kind !== 'adopt' && result.operation.action !== saved.kind) throw Error('Receipt action mismatch');
            if (saved.kind === 'patch' && (result.operation.state === 'conflict' ? result.operation.baseRevision !== saved.revision : result.operation.revision !== saved.revision + 1)) throw Error('Receipt revision mismatch');
            localStorage.removeItem(key);
            return {resolved:true, withdrawn:saved.kind === 'withdraw' && result.operation.state === 'committed', projection:result.draft || null};
          });
        }
      };
      editor = mountCoedit(content,{scope,pending,actions,api:{open:()=>read(id,captured), ...Object.fromEntries(['patch','approve','adopt','withdraw'].map(kind => [kind,({body}) => { assertIdentity(captured); return mutate(kind,id,body,captured); }]))}});
      if (!editor.update(projection,scope,editor.getGeneration())) throw Error('Invalid draft');
      status.textContent = 'Draft opened.';
    } catch (_) { if (generation === epoch) { editor?.destroy(); editor = null; status.textContent = 'Draft unavailable or access revoked.'; } }
  });
  return {reset, open(id, captured) {
    try { assertIdentity(captured); } catch (_) { return; }
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(id)) return;
    details.open = true; input.value = id; form.requestSubmit();
  }};
}

export function mountCoedit(root, {scope, api = {}, actions = {}, pending = null} = {}) {
  const section = document.createElement('section'); section.className = 'w22-coedit';
  const heading = document.createElement('h2'); heading.textContent = 'Coauthor draft';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.setAttribute('tabindex', '-1');
  const body = document.createElement('div'); section.append(heading, status, body); root.append(section);
  let generation = 0, currentScope = scope && {...scope}, view = null, local = null, dirty = false, conflict = false, conflictDiff = null, busy = false, uncertain = null, destroyed = false, events = [], priorPending = pending;
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); return n; };
  const same = (a,b) => !!a && !!b && a.sourceId === b.sourceId && a.sessionId === b.sessionId && a.actorId === b.actorId && a.role === b.role && a.revocationGeneration === b.revocationGeneration && a.draftId === b.draftId;
  const valid = s => !!s && !!s.sourceId && !!s.sessionId && !!s.actorId && !!s.draftId && Number.isInteger(s.revocationGeneration) && ['creator','collaborator'].includes(s.role);
  const validDraft = d => d && d.draftId === currentScope.draftId && d.schemaVersion === 1 && Number.isInteger(d.revision) && d.revision >= 0 && d.content && typeof d.content.title === 'string' && typeof d.content.body === 'string' && d.content.title.length <= 200 && d.content.body.length <= 12000;
  const copy = c => ({title:c.title, body:c.body});
  const differs = (a,b) => a.title !== b.title || a.body !== b.body;
  function reset(message = 'Draft cleared.') { generation++; view = null; local = null; dirty = false; conflict = false; conflictDiff = null; busy = false; uncertain = null; priorPending = null; events = []; body.replaceChildren(); status.textContent = message; }
  function adopt(result) {
    const d = result && result.draft;
    if (!validDraft(d)) { reset('Draft unavailable or access revoked.'); return false; }
    if (view && d.revision < view.revision) return false;
    if (view && dirty && d.revision !== view.revision) conflict = true;
    view = d; if (!dirty) local = copy(d.content);
    if (Array.isArray(result.events)) events = result.events.filter(e => e && Number.isInteger(e.revision) && typeof e.actorId === 'string').slice(-200);
    return true;
  }
  function button(text, enabled, callback, reason) {
    const b = el('button', text); b.type = 'button'; b.disabled = !enabled; if (!enabled && reason) b.title = reason; b.onclick = callback; return b;
  }
  function render(message) {
    const restoreFocus = typeof body.contains === 'function' && body.contains(document.activeElement);
    body.replaceChildren(); if (!view || !local) return;
    const epoch = generation;
    body.append(el('p', `Draft revision ${view.revision}. Your role: ${currentScope.role}. Approved revision: ${view.approvedRevision == null ? 'none' : view.approvedRevision}.`));
    const presence = Array.isArray(view.presence) ? view.presence.map(p => p.actorId).filter(x => typeof x === 'string') : [];
    body.append(el('p', `Present: ${presence.length ? presence.join(', ') : 'no current presence reported'}.`));
    if (events.length) { const last = events[events.length - 1]; body.append(el('p', `Last reported change: revision ${last.revision}, ${last.actorId}.`)); }
    if (conflict) {
      if (conflictDiff && currentScope.role === 'creator') {
        const chosen = {};
        body.append(el('h3', `Compare changes from revision ${conflictDiff.baseRevision} to ${conflictDiff.currentRevision}`));
        for (const row of conflictDiff.fields) {
          const group = el('fieldset'); group.append(el('legend', row.field === 'title' ? 'Title' : 'Body'));
          group.append(el('p', `Base: ${row.base}`));
          for (const option of ['current','proposed']) {
            const label = el('label', option === 'current' ? 'Current: ' : 'Proposed: '), radio = el('input');
            radio.type = 'radio'; radio.name = `w28-${row.field}`; radio.value = option;
            radio.addEventListener('change', () => { chosen[row.field] = option; choose.disabled = !chosen.title || !chosen.body; });
            label.append(radio, el('span', row[option])); group.append(label);
          }
          body.append(group);
        }
        const choose = button('Use selected fields', false, () => {
          if (epoch !== generation || !conflictDiff || !chosen.title || !chosen.body) return;
          try { if (typeof actions.assertCurrent !== 'function') throw Error(); actions.assertCurrent(); } catch (_) { reset('Access changed. Draft cleared.'); return; }
          local = Object.fromEntries(conflictDiff.fields.map(row => [row.field, row[chosen[row.field]]]));
          conflictDiff = null; conflict = false; dirty = differs(local, view.content);
          render('Selected text is retained. Save explicitly to apply it; approval is separate.');
        }); body.append(choose);
      }
      body.append(el('h3', 'Current accepted text'), el('p', `Title: ${view.content.title}`), el('p', `Body: ${view.content.body}`), el('h3', 'Your unsent text'), el('p', `Title: ${local.title}`), el('p', `Body: ${local.body}`));
      body.append(button('Keep my text for a new edit', !busy && !uncertain, () => { if (epoch !== generation) return; conflictDiff = null; conflict = false; dirty = differs(local, view.content); render('Your text is retained against the current revision. Save explicitly to apply it.'); }));
      body.append(button('Use accepted text', !busy && !uncertain, () => { if (epoch !== generation) return; conflictDiff = null; local = copy(view.content); dirty = false; conflict = false; render('Accepted text selected.'); }));
    }
    const canMutate = typeof actions.journal === 'function' && typeof actions.newRequestId === 'function' && typeof actions.complete === 'function' && typeof actions.withLock === 'function';
    let approveButton, adoptButton, withdrawButton;
    for (const [field, labelText, limit] of [['title','Title',200],['body','Body',12000]]) {
      const label = el('label', labelText); const input = el(field === 'title' ? 'input' : 'textarea'); input.value = local[field]; input.maxLength = limit; input.disabled = conflict || busy || !!uncertain || !!priorPending;
      input.addEventListener('input', () => { if (epoch !== generation || !view) return; local[field] = input.value; dirty = differs(local, view.content); if (approveButton) approveButton.disabled = dirty || busy || !!uncertain || !!priorPending || conflict || !canMutate || typeof api.approve !== 'function'; if (adoptButton) adoptButton.disabled = dirty || busy || !!uncertain || !!priorPending || conflict || view.approvedRevision !== view.revision || !canMutate || typeof api.adopt !== 'function'; if (withdrawButton) withdrawButton.disabled = dirty || busy || !!uncertain || !!priorPending || conflict || !canMutate || typeof api.withdraw !== 'function'; }); label.append(input); body.append(label);
    }
    body.append(button('Save changes', !busy && !uncertain && !priorPending && !conflict && canMutate && typeof api.patch === 'function', () => mutate('patch'), 'Connect patch, request ID and journal callbacks.'));
    body.append(button('Reconnect and refresh', !busy && typeof api.open === 'function', reconnect, 'Connect the open callback.'));
    if (priorPending) body.append(button('Recover prior operation', !busy && typeof actions.recover === 'function', recoverPrior, 'Connect authoritative recovery.'));
    if (priorPending && typeof actions.recover !== 'function') body.append(el('p', 'A prior operation needs authoritative recovery before editing.'));
    if (uncertain) body.append(button('Reconcile unconfirmed operation', !busy && typeof api[uncertain.kind] === 'function', replay, 'Connect the original operation callback.'));
    if (currentScope.role === 'creator') {
      approveButton = button('Approve this revision', !busy && !uncertain && !priorPending && !conflict && !dirty && canMutate && typeof api.approve === 'function', () => mutate('approve'), 'Save changes and connect approval, request ID and journal callbacks.'); body.append(approveButton);
      adoptButton = button('Adopt approved revision into Studio', !busy && !uncertain && !priorPending && !conflict && !dirty && view.approvedRevision === view.revision && canMutate && typeof api.adopt === 'function', () => mutate('adopt'), 'Approve this exact saved revision first.'); body.append(adoptButton);
      withdrawButton = button('Withdraw draft', !busy && !uncertain && !priorPending && !conflict && !dirty && canMutate && typeof api.withdraw === 'function', () => mutate('withdraw'), 'Save changes and connect withdrawal, request ID and journal callbacks.'); body.append(withdrawButton);
    }
    if (!canMutate || typeof api.patch !== 'function') body.append(el('p', 'Saving is unavailable until the editor adapter is connected.'));
    if (currentScope.role === 'creator' && (typeof api.approve !== 'function' || typeof api.withdraw !== 'function')) body.append(el('p', 'Approval or withdrawal is unavailable until its adapter is connected.'));
    if (restoreFocus && typeof status.focus === 'function') status.focus();
    if (message) status.textContent = message; else status.textContent = priorPending ? 'Recover the prior operation before another change.' : uncertain ? 'Operation unconfirmed. Reconcile the same request before another change.' : conflict ? 'The accepted revision changed. Compare and choose which text to continue with.' : dirty ? 'Unsent changes retained in this view.' : 'Draft loaded.';
  }
  async function reconnect() {
    if (!view || busy || typeof api.open !== 'function') return;
    const epoch = generation, captured = currentScope; busy = true; render('Refreshing the draft.');
    try { const result = await api.open({draftId:captured.draftId, cursor:view.cursor || 0, schemaVersion:1}); if (epoch !== generation || !same(captured,currentScope)) return; busy = false; if (adopt(result)) render(); }
    catch (err) { if (epoch !== generation || !same(captured,currentScope)) return; busy = false; if (err && (err.status === 401 || err.status === 403 || err.status === 404)) reset('Draft unavailable or access revoked.'); else render('Connection unavailable. Your unsent text is retained; reconnect to refresh.'); }
  }
  async function recoverPrior() {
    if (!priorPending || busy || typeof actions.recover !== 'function') return;
    const epoch = generation, captured = currentScope; busy = true; render('Recovering the prior operation.');
    try { const result = await actions.recover(priorPending); if (epoch !== generation || !same(captured,currentScope)) return; busy = false; if (!result || result.resolved !== true) { render('Prior operation remains unconfirmed.'); return; } priorPending = null; if (result.withdrawn === true) { reset('Draft withdrawn.'); return; } if (result.projection && adopt(result.projection)) render('Prior operation reconciled.'); else render('Prior operation reconciled. Refresh the draft.'); }
    catch (err) { if (epoch !== generation || !same(captured,currentScope)) return; busy = false; if (err && (err.status === 401 || err.status === 403 || err.status === 404)) reset('Draft unavailable or access revoked.'); else render('Prior operation remains unconfirmed.'); }
  }
  async function mutate(kind) {
    try { await actions.withLock(() => mutateLocked(kind)); }
    catch (_) { render('Could not acquire the recovery lock. Nothing new was sent.'); }
  }
  async function mutateLocked(kind) {
    if (!view || busy || uncertain || priorPending || conflict || typeof actions.journal !== 'function' || typeof actions.newRequestId !== 'function' || typeof api[kind] !== 'function') return;
    if (kind !== 'patch' && (currentScope.role !== 'creator' || dirty)) return;
    if (kind === 'adopt' && view.approvedRevision !== view.revision) return;
    if (kind === 'patch' && !dirty) { render('There are no unsent changes.'); return; }
    if (kind === 'patch' && (local.title.includes('\u0000') || local.body.includes('\u0000') || local.title.length > 200 || local.body.length > 12000)) { render('Draft text exceeds the allowed limits or contains an invalid character.'); return; }
    const id = actions.newRequestId(); if (typeof id !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(id)) { render('A valid request ID is unavailable.'); return; }
    const payload = kind === 'patch' ? {requestId:id, baseRevision:view.revision, operations:['title','body'].filter(k => local[k] !== view.content[k]).map(field => ({field, value:local[field]}))} : {requestId:id, expectedRevision:view.revision};
    const operation = {kind, draftId:currentScope.draftId, payload}; const epoch = generation, captured = currentScope; busy = true; render('Preparing operation.');
    try { await actions.journal({kind, draftId:captured.draftId, requestId:id, revision:view.revision}, payload); }
    catch (_) { if (epoch === generation && same(captured,currentScope)) { busy = false; render('Could not record recovery metadata. Nothing was sent.'); } return; }
    if (epoch !== generation || !same(captured,currentScope)) return;
    uncertain = operation; await send(operation, epoch, captured);
  }
  async function replay() { if (!uncertain || busy) return; try { await actions.withLock(async () => { if (!uncertain || busy) return; busy = true; render('Reconciling the original request.'); await send(uncertain, generation, currentScope); }); } catch (_) { render('Could not acquire the recovery lock.'); } }
  async function send(operation, epoch, captured) {
    try {
      const result = await api[operation.kind]({draftId:operation.draftId, body:operation.payload});
      if (epoch !== generation || !same(captured,currentScope)) return;
      busy = false;
      if (!result || !result.operation || !['committed','conflict'].includes(result.operation.state)) { render('Operation unconfirmed. Reconcile the same request.'); return; }
      await actions.complete({requestId:operation.payload.requestId});
      if (epoch !== generation || !same(captured,currentScope)) return;
      uncertain = null;
      if (operation.kind === 'withdraw' && result.operation.state === 'committed') { reset('Draft withdrawn.'); return; }
      if (operation.kind === 'adopt' && result.operation.state === 'committed') { reset('Approved revision adopted. Review and approve the material separately in Studio.'); return; }
      if (operation.kind === 'patch') {
        if (result.operation.state === 'conflict') {
          conflictDiff = null;
          const candidate = diffConflict(result.conflict);
          if (candidate && currentScope.role === 'creator' && typeof actions.assertCurrent === 'function' && typeof api.open === 'function') {
            try {
              actions.assertCurrent();
              const fresh = await api.open({draftId:captured.draftId, cursor:0, schemaVersion:1});
              actions.assertCurrent();
              if (epoch !== generation || !same(captured,currentScope)) return;
              if (validDraft(fresh?.draft) && fresh.draft.revision === candidate.currentRevision &&
                  result.operation.baseRevision === candidate.baseRevision && result.operation.currentRevision === candidate.currentRevision &&
                  candidate.fields.every(row => fresh.draft.content[row.field] === row.current && local[row.field] === row.proposed)) conflictDiff = candidate;
            } catch (err) {
              if (epoch !== generation || !same(captured,currentScope)) return;
              try { actions.assertCurrent(); } catch (_) { reset('Access changed. Draft cleared.'); return; }
              if ([401,403,404].includes(err?.status)) { reset('Draft unavailable or access revoked.'); return; }
            }
          }
          if (result.draft && adopt(result)) { conflict = true; dirty = true; render(); } else render('Conflict received; refresh the current draft.'); return;
        }
        dirty = false; if (!adopt(result)) { render('Saved; refresh the current draft.'); return; } local = copy(view.content); conflict = false; render('Changes saved.'); return;
      }
      if (result.operation.state === 'committed') { if (view && result.operation.revision === view.revision) view = {...view, approvedRevision:view.revision}; render('Revision approved. Adoption and presentation require separate creator actions.'); }
      else render('The revision changed. Refresh before deciding.');
    } catch (err) {
      if (epoch !== generation || !same(captured,currentScope)) return;
      busy = false;
      if (err && (err.status === 401 || err.status === 403 || err.status === 404)) { reset('Draft unavailable or access revoked.'); return; }
      if (err && err.definitive === true) { uncertain = null; render('Operation was rejected. Refresh and review the current revision.'); return; }
      render('Operation unconfirmed. Reconcile the same request before another change.');
    }
  }
  function update(projection, nextScope, ticket) {
    if (destroyed || ticket !== generation) return false;
    if (!valid(nextScope) || !same(currentScope,nextScope)) { reset('Access or source changed. Draft cleared.'); currentScope = nextScope && {...nextScope}; return false; }
    if (!projection || !validDraft(projection.draft)) { reset('Draft unavailable or access revoked.'); return false; }
    const ok = adopt(projection); if (ok) render(); return ok;
  }
  if (pending) status.textContent = 'A prior operation needs authoritative recovery before editing. Connect recovery in the host.';
  return {update, getGeneration: () => generation, reset, destroy() { reset(); destroyed = true; section.remove(); }};
}
