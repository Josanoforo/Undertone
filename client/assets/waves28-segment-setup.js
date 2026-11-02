/** Reviewed setup preview. The host owns authentication, transport and current selections. */
export function mount(root, initial = {}) {
  let ctx = initial, epoch = 0, dead = false, busy = false, preview = null, choices = {}, pending = null, notice = '';
  const authorityKeys = ['scope', 'session', 'actor', 'source'];
  const validId = s => typeof s === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(s);
  const validRev = n => Number.isSafeInteger(n) && n > 0;
  const key = c => JSON.stringify([...(authorityKeys.map(k => c.authority?.[k])), c.packId, c.expectedRevision, c.sourcePackId, c.sourceRevision]);
  const available = c => authorityKeys.every(k => validId(c.authority?.[k])) && validId(c.packId) && validId(c.sourcePackId) && c.packId !== c.sourcePackId && validRev(c.expectedRevision) && validRev(c.sourceRevision);
  const input = c => ({packId:c.packId, expectedRevision:c.expectedRevision, sourcePackId:c.sourcePackId, sourceRevision:c.sourceRevision});
  const element = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); return n; };
  const exact = (o, keys) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).sort().join('|') === keys.slice().sort().join('|');
  const definitionFields = {roleDefinition:['label'], glossaryDefinition:['term','meaning'], profileDefinition:['language','engine','model','modelVersion','voiceId','voiceVersion','adapterVersion','rate','qualityPreference'], chapterDefinition:['title','refs'], activityDefinition:['type','title','question','options','cards'], cueDefinition:['label','kind','materialFormat']};
  function safeItem(item) {
    if (!exact(item, ['kind','ref','revision']) || !validRev(item.revision)) return false;
    if (item.kind === 'sharedGlossary') return exact(item.ref,['profileId','ruleSetRevision','ruleIds']) && validId(item.ref.profileId) && validRev(item.ref.ruleSetRevision) && Array.isArray(item.ref.ruleIds) && item.ref.ruleIds.length > 0 && item.ref.ruleIds.length <= 100 && item.ref.ruleIds.every(validId) && new Set(item.ref.ruleIds).size === item.ref.ruleIds.length;
    if (definitionFields[item.kind]) return exact(item.ref,['id','definition']) && validId(item.ref.id) && exact(item.ref.definition,definitionFields[item.kind]) && definitionFields[item.kind].every(k => k === 'rate' ? typeof item.ref.definition[k] === 'number' && Number.isFinite(item.ref.definition[k]) : ['refs','options','cards'].includes(k) ? Array.isArray(item.ref.definition[k]) : typeof item.ref.definition[k] === 'string' && item.ref.definition[k].length > 0 && item.ref.definition[k].length <= (k === 'meaning' || k === 'question' ? 1000 : 160));
    if (item.kind === 'activity') return validId(item.ref);
    const approved = ['approvedActivity','approvedProfile'];
    const pack = ['approvedPackActivity','approvedPackProfile'];
    const fields = approved.includes(item.kind) ? ['channelId','grantId'] : pack.includes(item.kind) ? ['channelId','grantId','sourceGrantId','sourceRevision'] : null;
    return !!fields && exact(item.ref, fields) && fields.every(k => k === 'sourceRevision' ? validRev(item.ref[k]) : validId(item.ref[k]));
  }
  function validPreview(r, c) {
    if (!r || r.packId !== c.packId || r.targetRevision !== c.expectedRevision || r.sourcePackId !== c.sourcePackId || r.sourceRevision !== c.sourceRevision || !Array.isArray(r.items) || !r.target || r.target.sessionId !== c.authority.session || r.target.creatorCanEdit !== true || r.target.adapterCanActivate !== false || r.target.freshReviewRequired !== true || typeof r.canImport !== 'boolean') return false;
    const seen = new Set(), conflicts = new Set();
    for (const e of r.items) {
      if (!e || !Number.isSafeInteger(e.index) || e.index < 0 || seen.has(e.index) || typeof e.kind !== 'string' || !['ready','missing_or_revoked','unsupported'].includes(e.state)) return false;
      seen.add(e.index);
      if (e.state === 'ready') {
        if (!exact(e, e.conflictId == null ? ['index','kind','state','item'] : ['index','kind','state','item','conflictId']) || !safeItem(e.item) || e.kind !== e.item.kind) return false;
        if (e.conflictId != null) { const ref = definitionFields[e.item.kind] ? {id:e.item.ref.id} : e.item.kind === 'sharedGlossary' ? {profileId:e.item.ref.profileId} : typeof e.item.ref === 'object' ? Object.fromEntries(Object.entries(e.item.ref).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0)) : e.item.ref; if (e.conflictId !== JSON.stringify([e.item.kind, ref]) || conflicts.has(e.conflictId)) return false; conflicts.add(e.conflictId); }
      } else if (!exact(e, ['index','kind','state']) || !/^[A-Za-z0-9]{1,64}$/.test(e.kind)) return false;
    }
    if (r.requiresSourceReview !== undefined && (typeof r.requiresSourceReview !== 'boolean' || typeof r.sourceReviewed !== 'boolean')) return false;
    if (r.profileChecks !== undefined && !Array.isArray(r.profileChecks)) return false;
    if (r.cueRequirements !== undefined && !Array.isArray(r.cueRequirements)) return false;
    if (r.glossaryChecks !== undefined && !Array.isArray(r.glossaryChecks)) return false;
    return r.canImport === (r.items.length > 0 && r.items.every(e => e.state === 'ready') && (!r.requiresSourceReview || r.sourceReviewed));
  }
  function receipt(r) {
    if (!pending || r?.operation?.requestId !== pending.body.requestId || r.operation.state !== 'committed' || r.packId !== pending.body.packId || !validRev(r.revision) || !validRev(r.currentRevision) || r.currentRevision < r.revision) { notice = 'The original import is still uncertain. Check its receipt.'; return; }
    pending = null; preview = null; choices = {}; notice = `Imported editable setup items at revision ${r.revision}; current revision ${r.currentRevision}. Review them before activation.`;
  }
  function render() {
    const active = document.activeElement, name = root.contains(active) ? active?.name : '';
    root.replaceChildren(); const main = element('section'); main.className = 'segment-setup'; main.setAttribute('aria-label','Segment setup'); main.append(element('h2','Segment setup'));
    const status = element('p',notice); status.setAttribute('role','status'); status.setAttribute('aria-live','polite'); main.append(status);
    main.append(element('p','Preview creator-authored setup definitions and supported activity or profile references. Enter only shareable setup text, never credentials, conversations or answers. Preview does not activate anything.'));
    const addButton = (label, handler, disabled) => { const b = element('button',label); b.type='button'; b.disabled=disabled; b.addEventListener('click',handler); main.append(b); };
    if (!available(ctx)) main.append(element('p','Current actor, session, source, target or exact revisions are unavailable.'));
    else {
      main.append(element('p',`Source ${ctx.sourcePackId}, revision ${ctx.sourceRevision}; target ${ctx.packId}, revision ${ctx.expectedRevision}.`));
      addButton('Preview setup', doPreview, busy || !!pending || typeof ctx.previewSetup !== 'function');
      if (preview) {
        main.append(element('p','Target session: creator can edit. Target activation capability is unknown; fresh review is required. Source items are rechecked on import.'));
        if (preview.requiresSourceReview) main.append(element('p', preview.sourceReviewed ? 'Source setup was reviewed at this exact pack revision.' : 'Review the source setup in its pack before importing.'));
        for (const check of preview.profileChecks || []) main.append(element('p', `Profile item ${check.index + 1}: voice ${check.voiceAvailability}${check.reason ? ' (' + check.reason + ')' : ''}; fresh pronunciation-rule binding required. Controls: ${JSON.stringify(check.controls)}`));
        for (const cue of preview.cueRequirements || []) main.append(element('p', `Cue item ${cue.index + 1}: ${cue.materialFormat}; choose current approved material before use. Destination availability: ${cue.destinationAvailability}.`));
        for (const glossary of preview.glossaryChecks || []) for (const form of glossary.forms || []) main.append(element('p', `Glossary item ${glossary.index + 1}: ${form.language} · ${form.term} · ${form.spokenForm}. Fresh target review required.`));
        for (const e of preview.items) {
          const row = element('div'); row.className='segment-setup-item';
          if (e.state === 'ready') row.append(element('p',`${e.kind} · ${typeof e.item.ref === 'string' ? e.item.ref : JSON.stringify(e.item.ref)} · revision ${e.item.revision} · available`));
          else row.append(element('p',`${e.kind} · ${e.state === 'unsupported' ? 'Not supported here' : 'Missing or access revoked'}`));
          if (e.conflictId) {
            const label = element('label','For this changed reference '), select = element('select'); select.name='choice-' + e.index;
            for (const [value,title] of [['','Choose'],['keep','Keep current'],['replace','Replace']]) { const o=element('option',title); o.value=value; select.append(o); }
            select.value=choices[e.conflictId] || ''; select.addEventListener('change',()=>{ choices[e.conflictId]=select.value; render(); }); label.append(select); row.append(label);
          }
          main.append(row);
        }
        if (!preview.canImport) main.append(element('p','Review the source and resolve unavailable or unsupported items, then preview again.'));
        const conflicts = preview.items.filter(e => e.conflictId);
        addButton('Import setup for fresh review', doImport, busy || !!pending || !preview.canImport || conflicts.some(e => !['keep','replace'].includes(choices[e.conflictId])) || typeof ctx.importSetup !== 'function' || !globalThis.crypto?.randomUUID);
      }
    }
    if (pending) {
      main.append(element('p', key(ctx) === pending.key ? 'An import outcome is uncertain. Check the original operation; do not start another import.' : 'An earlier import outcome is uncertain. Return to its original session and selection to check it.'));
      addButton('Check original import', recover, busy || key(ctx) !== pending.key || typeof ctx.recoverSetup !== 'function');
    }
    root.append(main); if (name) { const n = Array.from(root.querySelectorAll('[name]')).find(x => x.name === name); n?.focus(); }
  }
  async function doPreview() {
    if (busy || pending || !available(ctx) || typeof ctx.previewSetup !== 'function') return;
    const token=epoch, selected=key(ctx), body=input(ctx); busy=true; preview=null; choices={}; notice='Loading preview.'; render();
    try { const r=await ctx.previewSetup(body); if (dead || token!==epoch || selected!==key(ctx)) return; if (!validPreview(r,ctx)) throw Error('invalid'); preview=r; notice='Review the current setup items and any conflicts.'; }
    catch { if (dead || token!==epoch || selected!==key(ctx)) return; notice='Preview unavailable or changed. Reload current selections and try again.'; }
    finally { if (!dead && token===epoch) { busy=false; render(); } }
  }
  async function doImport() {
    if (busy || pending || !preview?.canImport || !available(ctx) || typeof ctx.importSetup !== 'function' || !globalThis.crypto?.randomUUID) return;
    const conflicts=preview.items.filter(e=>e.conflictId); if (conflicts.some(e=>!['keep','replace'].includes(choices[e.conflictId]))) return;
    const body={requestId:globalThis.crypto.randomUUID(), ...input(ctx), choices:Object.fromEntries(conflicts.map(e=>[e.conflictId,choices[e.conflictId]]))};
    pending={key:key(ctx),body}; const token=epoch; busy=true; notice='Importing reviewed references.'; render();
    try { const r=await ctx.importSetup(body); if (dead || token!==epoch || key(ctx)!==pending?.key) return; if (r?.freshReviewRequired !== true || r?.activated !== false) { notice='Import outcome uncertain. Check the original operation.'; return; } receipt(r); }
    catch (e) { if (dead || token!==epoch || key(ctx)!==pending?.key) return; notice='Import response unavailable or changed. Check the original operation; its outcome remains uncertain.'; }
    finally { if (!dead && token===epoch) { busy=false; render(); } }
  }
  async function recover() {
    if (busy || !pending || key(ctx)!==pending.key || typeof ctx.recoverSetup!=='function') return;
    const token=epoch, id=pending.body.requestId; busy=true; notice='Checking the original import.'; render();
    try { const r=await ctx.recoverSetup({requestId:id}); if (dead || token!==epoch || id!==pending?.body.requestId || key(ctx)!==pending.key) return; receipt(r); }
    catch { if (dead || token!==epoch) return; notice='Receipt unavailable. The original import remains uncertain.'; }
    finally { if (!dead && token===epoch) { busy=false; render(); } }
  }
  render();
  return {update(next={}) { const changed=key(ctx)!==key(next); ctx=next; if (changed) { epoch++; busy=false; preview=null; choices={}; notice='Selections changed. Preview again.'; } render(); }, destroy() { dead=true; epoch++; root.replaceChildren(); }};
}


