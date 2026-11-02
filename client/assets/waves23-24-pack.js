/** Authenticated session pack. The host owns all transport and authorization. */
export function mount(root, context = {}) {
  let ctx = context, generation = 0, editGeneration = 0, dead = false;
  let pack = null, preview = null, pending = null, choices = {}, message = '', continuation = null, profileSelection = null, profilePending = false, channelPending = null, capability = '';
  const freshDraft = c => ({packId: c.packId || '', items: JSON.stringify(c.initialItems || [], null, 2), expiry: '', source: '', sourceRevision: '', channelId: '', grantId: '', grantRevision: '', receivingRef: '', channelRevision: '', membershipSession: '', channelCapability: '', channelGrantRevision: '', sourceGrantFields: ''});
  let draft = freshDraft(ctx);
  const keys = ['scope', 'session', 'actor', 'source', 'profile'];
  const sameAuthority = (a, b) => keys.every(k => a.authority?.[k] != null && a.authority[k] !== '' && a.authority[k] === b.authority?.[k]);
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); return n; };
  const field = (parent, label, value, name) => { const l = el('label', label), input = el('input'); input.name = name; input.value = value || ''; l.append(input); parent.append(l); return input; };
  const button = (parent, label, fn, disabled = false) => { const b = el('button', label); b.type = 'button'; b.disabled = disabled; b.addEventListener('click', fn); parent.append(b); return b; };
  const section = title => { const s = el('section'); s.append(el('h3', title)); return s; };
  function invalidate() { editGeneration++; preview = null; }
  function errorCode(error) { return error && (error.code || error.error?.code); }
  async function run(callback, argument, success, failure, useEditFence = false) {
    const token = generation, edit = editGeneration;
    if (typeof callback !== 'function') { message = 'This action is unavailable.'; render(); return; }
    try {
      const result = await callback(argument);
      if (dead || token !== generation || (useEditFence && edit !== editGeneration)) return;
      success(result);
    } catch (error) {
      if (dead || token !== generation || (useEditFence && edit !== editGeneration)) return;
      if (failure) failure(errorCode(error)); else message = 'This action is unavailable. Reload current information and try again.';
    }
    if (!dead && token === generation) render();
  }
  function receipt(result) {
    if (!pending || result?.operation?.requestId !== pending.requestId || result.operation.state !== 'committed') { message = 'Operation outcome is still uncertain. Check the original operation.'; return; }
    pending = null; pack = null; invalidate(); draft.packId = result.packId;
    message = `Committed revision ${result.revision}; current revision ${result.currentRevision}. Reload the pack for current references.`;
  }
  function render() {
    const active = document.activeElement; const focusName = active && root.contains(active) ? active.name : ''; const focusText = active && root.contains(active) && active.tagName === 'BUTTON' ? active.textContent : ''; const start = active?.selectionStart, end = active?.selectionEnd;
    root.replaceChildren();
    const main = el('section'); main.className = 'channel-pack'; main.setAttribute('aria-label', 'Channel pack'); main.append(el('h2', 'Channel pack'));
    if (!keys.every(k => ctx.authority?.[k] != null && ctx.authority[k] !== '')) { main.append(el('p', 'Current session authority is unavailable.')); root.append(main); return; }
    const status = el('p', message); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); main.append(status);
    main.append(el('p', 'Packs contain accessible references. Cross-session reuse requires an approved channel grant; private practice and dictionaries remain separate.'));
    const shared = section('Shared approved references');
    const id = field(shared, 'Pack ID', draft.packId, 'packId');
    id.addEventListener('input', () => { draft.packId = id.value; pack = null; invalidate(); render(); });
    button(shared, 'Load pack', () => { const requested = draft.packId; pack = null; invalidate(); run(ctx.readPack, {packId: requested}, result => { if (result?.packId !== requested) { message = 'Pack unavailable.'; return; } pack = result; draft.expiry = result.expiresAt || ''; message = 'Current accessible references loaded.'; }, () => { pack = null; message = 'Pack unavailable or no longer accessible.'; }, true); render(); }, typeof ctx.readPack !== 'function');
    const receivingRef = field(shared, 'Receiving session source or moment reference (JSON)', draft.receivingRef, 'receivingRef');
    receivingRef.addEventListener('input', () => { draft.receivingRef = receivingRef.value; });
    if (profileSelection) shared.append(el('p', 'A current approved profile selection is available for your session.'));
    button(shared, 'Load current profile selection', () => run(ctx.readPackProfileSelection, {}, result => { profileSelection = result; message = profilePending ? 'Current selection loaded; the earlier selection request remains uncertain.' : 'Current approved profile selection loaded.'; }, () => { profileSelection = null; message = 'Current profile selection unavailable.'; }), typeof ctx.readPackProfileSelection !== 'function');
    if (pack) {
      shared.append(el('p', 'Revision ' + pack.revision + (pack.expiresAt ? ' · expires ' + pack.expiresAt : ' · no expiry') + (pack.setupReviewed ? ' · setup reviewed at this revision' : ' · setup review not recorded')));
      for (const item of pack.items || []) {
        const row = el('div'); row.className = 'pack-item';
        row.append(el('span', item.kind + ' · revision ' + item.revision + (item.projection?.status ? ' · ' + item.projection.status : '') + ' · ' + JSON.stringify(item.ref))); if (item.projection?.claim?.claim) row.append(el('p', item.projection.claim.claim));
        if (['approvedProfile', 'approvedPackProfile'].includes(item.kind)) button(row, 'Select approved profile', () => {
          if (profilePending || !globalThis.crypto?.randomUUID) return;
          let ref; try { ref = JSON.parse(draft.receivingRef); if (!ref || typeof ref !== 'object' || Array.isArray(ref)) throw Error(); } catch { message = 'Enter a valid receiving-session source reference.'; render(); return; }
          const body = {requestId: globalThis.crypto.randomUUID(), packId: pack.packId, item: {kind:item.kind, ref:item.ref, revision:item.revision}, ref};
          profilePending = body.requestId; profileSelection = null; message = 'Selecting the approved profile.'; render();
          run(ctx.selectPackProfile, body, result => { profilePending = false; profileSelection = result; message = 'Approved profile selected for your session.'; }, code => { if (['invalid_request','invalid_item','not_found','stale_context','request_conflict'].includes(code)) { profilePending = false; message = 'Profile selection was rejected; reload current references.'; } else message = 'Selection outcome uncertain. Load the current selection; do not submit it again automatically.'; });
        }, profilePending || typeof ctx.selectPackProfile !== 'function');
        button(row, 'Open reference', () => run(ctx.openSource, item, () => { message = 'Reference opened.'; }), typeof ctx.openSource !== 'function'); shared.append(row);
      }
      if (!pack.items?.length) shared.append(el('p', 'No accessible references.'));
    } else shared.append(el('p', 'Load a pack to see current accessible references.'));
    main.append(shared);
    const manage = section('Manage channel pack');
    manage.append(el('p', 'Enter a JSON array of {kind, ref, revision}. Session-local setup definitions can describe roles, glossary entries, speech settings, source-backed chapters, activities and cues; they do not grant access or activate anything. Use only shareable setup content. Update replaces the complete list; omitted items are removed.'));
    manage.append(el('p', 'For setup definitions, ref contains an id and a definition. Activity definitions use type, title, question, options and cards; chapter definitions use title and current source refs. Imported setup needs a fresh review.'));
    const items = el('textarea'); items.setAttribute('aria-label', 'Approved reference items'); items.name = 'items'; items.value = draft.items; items.addEventListener('input', () => { draft.items = items.value; invalidate(); render(); }); manage.append(items);
    const expiry = field(manage, 'Expiry (ISO date and time with timezone, or blank)', draft.expiry, 'expiresAt'); expiry.addEventListener('input', () => { draft.expiry = expiry.value; });
    const source = field(manage, 'Import source pack ID', draft.source, 'sourcePackId'); source.addEventListener('input', () => { draft.source = source.value; invalidate(); render(); });
    const sourceRevision = field(manage, 'Import source revision', draft.sourceRevision, 'sourceRevision'); sourceRevision.type = 'number'; sourceRevision.min = '1'; sourceRevision.addEventListener('input', () => { draft.sourceRevision = sourceRevision.value; invalidate(); render(); });
    for (const [label, name] of [['Channel ID','channelId'], ['Approved pack grant ID','grantId'], ['Grant revision','grantRevision']]) {
      const input = field(manage, label, draft[name], name); if (name === 'grantRevision') { input.type = 'number'; input.min = '1'; }
      input.addEventListener('input', () => { draft[name] = input.value; invalidate(); render(); });
    }
    const parse = () => { const v = JSON.parse(draft.items); if (!Array.isArray(v)) throw Error('items'); return v; };
    function makePreview(importing) {
      try {
        const body = {packId: pack.packId, expectedRevision: pack.revision};
        if (importing === 'approved') { body.channelId = draft.channelId; body.grantId = draft.grantId; body.grantRevision = Number(draft.grantRevision); if (!body.channelId || !body.grantId || !Number.isSafeInteger(body.grantRevision) || body.grantRevision < 1) throw Error('grant'); }
        else if (importing) { body.sourcePackId = draft.source; body.sourceRevision = Number(draft.sourceRevision); if (!body.sourcePackId || !Number.isSafeInteger(body.sourceRevision) || body.sourceRevision < 1) throw Error('source'); }
        else body.items = parse();
        invalidate(); run(ctx.previewPack, body, result => { if (result?.packId !== body.packId || result.revision !== body.expectedRevision || !Array.isArray(result.items)) { message = 'Preview unavailable.'; return; } preview = {result, body, importing}; message = 'Review eligibility and resolve conflicts.'; }, code => { if (code === 'stale_revision') { pack = null; message = 'Pack changed. Reload and preview again; your draft and choices remain.'; } else message = 'Preview unavailable. Check the pack and references.'; }, true);
      } catch { message = 'Enter a valid reference array or source revision.'; render(); }
    }
    button(manage, 'Preview update', () => makePreview(false), !pack || typeof ctx.previewPack !== 'function');
    button(manage, 'Preview import', () => makePreview(true), !pack || typeof ctx.previewPack !== 'function');
    button(manage, 'Preview approved import', () => makePreview('approved'), !pack || typeof ctx.previewPack !== 'function');
    if (preview) for (const entry of preview.result.items) {
      const row = el('div', 'Item ' + (entry.index + 1) + ': ' + entry.status + (entry.item ? ' · ' + entry.item.kind + ' · ' + JSON.stringify(entry.item.ref) + ' · revision ' + entry.item.revision : '')); manage.append(row);
      if (entry.status === 'conflict') {
        const label = el('label', 'Conflict decision'); const select = el('select');
        for (const [value, title] of [['','Choose'],['keep','Keep current'],['replace','Replace']]) { const option = el('option', title); option.value = value; select.append(option); }
        select.value = choices[entry.conflictId] || ''; select.addEventListener('change', () => { choices[entry.conflictId] = select.value; }); label.append(select); row.append(label);
      }
    }
    function mutate(action) {
      if (pending) { message = 'Check the original operation before starting another.'; render(); return; }
      try {
        if (typeof ctx.mutatePack !== 'function' || !globalThis.crypto?.randomUUID) throw Error('unavailable');
        const body = {action, requestId: globalThis.crypto.randomUUID(), expectedRevision: action === 'create' ? 0 : pack.revision};
        if (action !== 'create') body.packId = pack.packId;
        if (action === 'create') { body.items = parse(); body.expiresAt = draft.expiry || null; }
        if (action === 'update' || action === 'import' || action === 'importApproved') {
          if (!preview || preview.importing !== (action === 'importApproved' ? 'approved' : action === 'import') || preview.body.packId !== pack.packId || preview.body.expectedRevision !== pack.revision || preview.result.items.some(x => !['eligible','conflict'].includes(x.status) || (x.status === 'conflict' && !['keep','replace'].includes(choices[x.conflictId])))) throw Error('preview');
          body.choices = Object.fromEntries(preview.result.items.filter(x => x.status === 'conflict').map(x => [x.conflictId, choices[x.conflictId]]));
          if (action === 'update') { body.items = preview.body.items; body.expiresAt = draft.expiry || null; } else if (action === 'import') { body.sourcePackId = preview.body.sourcePackId; body.sourceRevision = preview.body.sourceRevision; } else { body.channelId = preview.body.channelId; body.grantId = preview.body.grantId; body.grantRevision = preview.body.grantRevision; }
        }
        pending = {requestId: body.requestId}; message = 'Operation submitted. Check its original receipt if the outcome is uncertain.'; render();
        run(ctx.mutatePack, body, receipt, code => {
          if (['stale_revision', 'invalid_request', 'invalid_item', 'unsupported_item', 'expired', 'request_conflict', 'conflict'].includes(code)) { pending = null; if (code === 'stale_revision') { pack = null; invalidate(); } message = code === 'stale_revision' ? 'Pack changed. Reload and preview again; your draft and choices remain.' : 'Operation was rejected. Review your inputs before a new operation.'; }
          else message = 'Operation outcome uncertain. Check the original operation before another mutation.';
        });
      } catch { message = 'Complete a valid preview and resolve every conflict, or check action availability.'; render(); }
    }
    const unavailable = !!pending || typeof ctx.mutatePack !== 'function';
    button(manage, 'Create pack', () => mutate('create'), unavailable);
    button(manage, 'Mark current setup reviewed', () => mutate('reviewSetup'), unavailable || !pack || !pack.items?.some(item => item.kind.endsWith('Definition') || item.kind === 'sharedGlossary'));
    button(manage, 'Update pack', () => mutate('update'), unavailable || !pack || !preview || preview.importing);
    button(manage, 'Import pack', () => mutate('import'), unavailable || !pack || !preview || preview.importing !== true);
    button(manage, 'Import approved pack', () => mutate('importApproved'), unavailable || !pack || !preview || preview.importing !== 'approved');
    button(manage, 'Withdraw pack', () => mutate('withdraw'), unavailable || !pack);
    if (pending) button(manage, 'Check original operation', () => run(ctx.recoverPackOperation, {requestId: pending.requestId}, receipt, () => { message = 'Receipt unavailable; the outcome remains uncertain. Do not start another mutation.'; }), typeof ctx.recoverPackOperation !== 'function');
    main.append(manage);
    const channel = section('Approved channel access');
    channel.append(el('p', 'Channel capabilities are shown once. Share them only through a trusted private channel. Lost capabilities require an intentional rotation.'));
    for (const [label, name] of [['Channel revision','channelRevision'], ['Membership session ID (blank to revoke channel)','membershipSession'], ['Capability for enrollment','channelCapability'], ['Grant revision for withdrawal','channelGrantRevision'], ['Source grant fields (JSON object)','sourceGrantFields']]) {
      const input = field(channel, label, draft[name], name); if (name === 'channelCapability') input.type = 'password';
      input.addEventListener('input', () => { draft[name] = input.value; });
    }
    if (capability) channel.append(el('p', 'One-time capability: ' + capability));
    function channelReceipt(result) {
      if (!channelPending || result?.requestId !== channelPending || result.state !== 'committed') { message = 'Channel operation outcome remains uncertain.'; return; }
      channelPending = null; capability = result.capabilityAvailable && typeof result.capability === 'string' ? result.capability : '';
      if (result.channelId) draft.channelId = result.channelId;
      message = 'Channel operation committed. Reload current permissions before reuse.';
    }
    function channelAction(route, action) {
      if (channelPending || typeof ctx.mutateChannel !== 'function' || !globalThis.crypto?.randomUUID) return;
      const requestId = globalThis.crypto.randomUUID(), body = {action, requestId};
      const revision = Number(draft.channelRevision), grantRevision = Number(draft.channelGrantRevision);
      try {
        if (!(route === 'capabilities' && action === 'create')) { if (!draft.channelId) throw Error(); body.channelId = draft.channelId; }
        if ((route === 'capabilities' && action === 'rotate') || (route === 'membership' && action === 'revoke')) { if (!Number.isSafeInteger(revision) || revision < 1) throw Error(); body.expectedRevision = revision; }
        if (route === 'membership' && action === 'enroll') { if (!draft.channelCapability) throw Error(); body.capability = draft.channelCapability; draft.channelCapability = ''; }
        if (route === 'membership' && action === 'revoke') body.sessionId = draft.membershipSession || null;
        if (route === 'source-grants' && action === 'approve') { const fields = JSON.parse(draft.sourceGrantFields); if (!fields || Array.isArray(fields) || typeof fields !== 'object' || ['action','requestId','channelId'].some(k => k in fields)) throw Error(); Object.assign(body, fields); }
        if (route === 'source-grants' && action === 'withdraw') { if (!draft.grantId || !Number.isSafeInteger(grantRevision) || grantRevision < 1) throw Error(); body.grantId = draft.grantId; body.expectedRevision = grantRevision; }
        if (route === 'pack-grants' && action === 'approve') { if (!pack) throw Error(); body.packId = pack.packId; body.expectedRevision = pack.revision; }
        if (route === 'pack-grants' && action === 'withdraw') { if (!draft.grantId || !Number.isSafeInteger(grantRevision) || grantRevision < 1) throw Error(); body.grantId = draft.grantId; body.expectedRevision = grantRevision; }
      } catch { message = 'Enter the required current channel or grant information.'; render(); return; }
      capability = ''; channelPending = requestId; message = 'Channel operation submitted.'; render();
      run(ctx.mutateChannel, {route, body}, channelReceipt, code => { if (['invalid_request','not_found','stale_revision','request_conflict','forbidden'].includes(code)) { channelPending = null; message = 'Channel operation rejected. Reload current permissions.'; } else message = 'Channel operation outcome uncertain. Check its original receipt.'; });
    }
    const channelDisabled = !!channelPending || typeof ctx.mutateChannel !== 'function';
    for (const [label, route, action] of [['Create channel','capabilities','create'], ['Rotate channel capability','capabilities','rotate'], ['Enroll session','membership','enroll'], ['Revoke membership','membership','revoke'], ['Approve source grant','source-grants','approve'], ['Withdraw source grant','source-grants','withdraw'], ['Approve current pack grant','pack-grants','approve'], ['Withdraw pack grant','pack-grants','withdraw']]) button(channel, label, () => channelAction(route, action), channelDisabled || (route === 'pack-grants' && action === 'approve' && !pack));
    if (channelPending) button(channel, 'Check channel operation', () => run(ctx.recoverChannelOperation, {requestId:channelPending}, channelReceipt, () => { message = 'Channel receipt unavailable; the outcome remains uncertain.'; }), typeof ctx.recoverChannelOperation !== 'function');
    main.append(channel);
    const personal = section('Your private continuation'); personal.append(el('p', 'Your practice is separate from shared pack references.')); if (continuation) personal.append(el('p', continuation.summary || 'No continuation available.'));
    button(personal, 'Load my continuation', () => run(ctx.loadPrivateContinuation, {}, result => { continuation = result || {}; message = 'Private continuation loaded.'; }), typeof ctx.loadPrivateContinuation !== 'function'); main.append(personal); root.append(main);
    const focus = focusName ? [...root.querySelectorAll('[name]')].find(n => n.name === focusName) : focusText ? [...root.querySelectorAll('button')].find(n => n.textContent === focusText && !n.disabled) : null; if (focus) { focus.focus(); if (typeof start === 'number' && focus.setSelectionRange) focus.setSelectionRange(start, end); }
  }
  render();
  return {
    update(next = {}) { if (dead) return; const same = sameAuthority(ctx, next); generation++; editGeneration++; ctx = next; pack = null; preview = null; continuation = null; profileSelection = null; capability = ''; draft.channelCapability = ''; if (!same) { pending = null; channelPending = null; profilePending = false; choices = {}; draft = freshDraft(next); message = ''; } else message = pending || channelPending ? 'Operation outcome uncertain. Check the original receipt before another mutation.' : profilePending ? 'Profile selection outcome uncertain. Load the current selection; do not submit it again automatically.' : 'Reload current references.'; render(); },
    destroy() { if (dead) return; dead = true; generation++; ctx = {}; pack = preview = pending = continuation = profileSelection = null; profilePending = false; channelPending = null; capability = ''; choices = {}; draft = {}; root.replaceChildren(); }
  };
}


