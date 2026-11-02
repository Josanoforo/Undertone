// B26.2: source-bound, effect-free-on-mount meaning inspection.
export function mountMeaning(root, host) {
  if (!root || !host || typeof host.isCurrent !== 'function') throw new TypeError('current host scope required');
  let epoch = 0, scope = null, flag = null, pending = false, alive = true;
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
  let restoreFocus = false;
  const clear = () => { restoreFocus = root.contains(document.activeElement); root.replaceChildren(); flag = null; pending = false; };
  const message = text => { const p=el('p',text);p.tabIndex=-1;p.setAttribute('role','status');root.append(p);if(restoreFocus)p.focus(); };
  const sameRef = (a,b) => !!a && !!b && ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(k=>a[k]===b[k]);
  const valid = (s, e) => alive && e === epoch && scope === s && host.isCurrent(s) === true;
  const line = (parent, label, value) => { const p = el('p'); p.append(el('strong', label + ' '), el('span', value)); parent.append(p); };
  const render = () => {
    const s = scope, e = epoch; clear();
    if (!s || !host.isCurrent(s)) { message('This source is unavailable.'); return; }
    const d = s.result;
    if (!d || !d.source || !d.source.ref || !d.destination || !sameRef(d.source.ref,s.ref) || !sameRef(d.destination.ref,s.ref) || typeof d.source.text !== 'string') { message('This inspection is unavailable.'); return; }
    const panel = el('section'); panel.className = 'meaning-inspection'; panel.append(el('h2', 'Compare meaning'));
    const original = el('section'); original.append(el('h3', 'Original')); line(original, 'Exact text:', d.source.text); original.lang=d.source.language||'';line(original, 'Transcription certainty:', 'Unknown');line(original,'Fragment:',`${s.ref.startMs}–${s.ref.endMs} ms; source revision ${s.ref.sourceRevision}.`);line(original,'Evidence:',d.source.provenance==='received_asr'?'Received transcription; human accuracy review is unassessed.':'Source provenance unknown.'); panel.append(original);
    const trans = el('section'); trans.append(el('h3', 'Translation'));
    if (d.translation?.state === 'available' && typeof d.translation.text === 'string' && typeof d.translation.requestId === 'string') { const text=el('p',d.translation.text);text.lang=d.translation.language||'';trans.append(text);line(trans, 'Source uncertainty:', 'Unknown; this completed translation does not confirm the transcription.');line(trans,'Text provenance:',({fixture:'Fixture; no real translation quality is established.',creator_text:'Creator-authored correction.',user_text:'User-authored correction.',provider_output:'Provider output; human meaning review is unassessed.'})[d.translation.provenance]||'Unknown'); line(trans, 'Translation uncertainty:', d.translation.uncertainty == null || d.translation.uncertainty === '' ? 'Unknown' : JSON.stringify(d.translation.uncertainty)); }
    else line(trans, 'Status:', 'Unavailable; no completed translation is bound.'); panel.append(trans);
    const visual = el('section'); visual.append(el('h3', 'Visual evidence'));
    if (d.visual?.state === 'available' && d.visual.evidence && ((d.visual.associationId && d.visual.associationId === s.associationId && d.visual.association?.kind === 'creator_selected' && d.visual.frameRef && Number.isInteger(d.visual.revision) && JSON.stringify(d.visual.evidence.ref) === JSON.stringify(d.visual.frameRef)) || (!d.visual.associationId && JSON.stringify(d.visual.evidence.ref) === JSON.stringify(s.ref)))) {
      const evidence = d.visual.evidence;
      line(visual, 'Observed reference:', JSON.stringify({ref: evidence.ref, regionId: evidence.regionId, time: evidence.time}));
      line(visual, 'Association:', d.visual.associationId ? 'Creator-selected; visual and source are distinct records.' : 'Selected source record.');
      if (typeof evidence.explanation === 'string') line(visual, evidence.evidenceKind === 'inference' ? 'Inferred description:' : 'Description (status unknown):', evidence.explanation);
      line(visual,'Description provenance:',({fixture:'Fixture; this description is authored test evidence.',provider_output:'Provider output; visual correctness is unassessed.',creator_text:'Creator-authored description.'})[d.visual.descriptionProvenance]||'Unknown; do not treat this description as an observed fact.');
      line(visual,'Current rights:',evidence.rightsState==='current'?'Checked for this selected reference.':'Unknown');
      line(visual, 'Certainty:', d.visual.certainty || 'Unknown'); line(visual, 'Interpretation:', 'Inferences are not established.');
    }
    else line(visual, 'Status:', 'Unavailable; no visual association is established.'); panel.append(visual);
    const form = el('form'); form.append(el('h3', 'Private mismatch note')); line(form, 'Visibility:', 'Private to you until explicitly shared through an authorized contribution.');
    const label = el('label', 'Area '), select = el('select'); select.name = 'field'; for (const v of ['source', 'translation', 'visual']) { const o = el('option', v); o.value = v; select.append(o); } label.append(select); form.append(label);
    const noteLabel = el('label', 'Note '), note = el('textarea'); note.maxLength = 1000; note.required = true; noteLabel.append(note); form.append(noteLabel);
    const save = el('button', 'Save private note'); save.type = 'submit'; save.disabled = typeof host.createFlag !== 'function' || typeof host.newRequestId !== 'function'; form.append(save);
    const status = el('p'); status.setAttribute('role', 'status'); form.append(status);
    const share = el('button', 'Share explicitly'); share.type = 'button'; share.disabled = true; form.append(share);
    const revoke = el('button', 'Revoke share'); revoke.type = 'button'; revoke.disabled = true; form.append(revoke);
    const sharingReady = host.flagShareReady === true && typeof host.shareFlag === 'function' && typeof host.revokeFlagShare === 'function' && typeof host.newRequestId === 'function' && typeof s.ref.sessionId === 'string';
    line(form, 'Sharing:', sharingReady ? 'Share explicitly sends this saved note to the current session creator. You can revoke it.' : 'Unavailable until an authorized source-bound contribution and revocation authority is connected.');
    let sharedId = null, shareAttempted = false, revokeAttempted = false;
    share.addEventListener('click', async () => {
      if (!sharingReady || !flag || pending || shareAttempted || !valid(s, e)) return;
      const requestId = host.newRequestId();
      if (typeof requestId !== 'string' || !requestId) return;
      const selection = {flagId: flag.id, flagRevision: flag.revision, targetSessionId: s.ref.sessionId, consent: true, requestId};
      shareAttempted = true; pending = true; share.disabled = true; status.textContent = 'Sharing selected note…';
      try {
        let id;
        try { const result = await host.shareFlag(s, selection); id = result?.id; }
        catch (error) {
          if (!valid(s, e)) return;
          if (error?.outcome !== 'unknown' || typeof host.recoverShare !== 'function') throw error;
          const receipt = await host.recoverShare(s, requestId);
          if (receipt?.state === 'complete') id = receipt.shareId;
        }
        if (!valid(s, e)) return;
        if (typeof id !== 'string' || !id) throw new Error('unconfirmed share');
        sharedId = id; revoke.disabled = false; status.textContent = 'Note shared with the current session creator.';
      } catch (_) { if (valid(s, e)) status.textContent = 'Could not confirm the share. Check its original receipt before trying again.'; }
      finally { if (valid(s, e)) pending = false; }
    });
    revoke.addEventListener('click', async () => {
      if (!sharedId || pending || revokeAttempted || !valid(s, e)) return;
      revokeAttempted = true; pending = true; revoke.disabled = true; status.textContent = 'Revoking share…';
      try {
        const result = await host.revokeFlagShare(s, sharedId);
        if (!valid(s, e)) return;
        if (result?.ok !== true) throw new Error('unconfirmed revoke');
        sharedId = null; status.textContent = 'Share revoked.';
      } catch (_) { if (valid(s, e)) status.textContent = 'Could not confirm revocation. Check its original outcome.'; }
      finally { if (valid(s, e)) pending = false; }
    });
    let submitted = false;
    form.addEventListener('submit', async event => {
      event.preventDefault(); if (submitted || pending || !valid(s, e) || !note.value.trim() || note.value.length > 1000 || note.value.includes('\0')) return;
      const request = { ref: s.ref, field: select.value, note: note.value, requestId: host.newRequestId() };
      if (typeof request.requestId !== 'string' || !request.requestId) return;
      submitted = true; pending = true; save.disabled = true; status.textContent = 'Saving private note…';
      try {
        let result;
        try { result = await host.createFlag(s, request); }
        catch (error) { if (!valid(s, e)) return; if (error?.outcome !== 'unknown' || typeof host.recoverFlag !== 'function') throw error; result = await host.recoverFlag(s, request); }
        if (!valid(s, e)) return;
        if (!result || result.visibility !== 'private' || JSON.stringify(result.ref) !== JSON.stringify(s.ref) || result.field !== request.field || result.note !== request.note || typeof result.id !== 'string' || !Number.isInteger(result.revision)) throw new Error('invalid receipt');
        flag = result; share.disabled = !sharingReady; status.textContent = 'Private note saved.';
      } catch (_) { if (valid(s, e)) status.textContent = 'Could not confirm the private note. Check its original receipt before trying again.'; }
      finally { if (valid(s, e)) { pending = false; save.disabled = true; } }
    });
    panel.append(form); root.append(panel);if(restoreFocus){const heading=panel.querySelector('h2');heading.tabIndex=-1;heading.focus();}
  };
  return { setScope(next) { ++epoch; scope = next; render(); }, invalidate() { ++epoch; scope = null; clear(); message('This source is unavailable.'); }, destroy() { ++epoch; alive = false; scope = null; clear(); } };
}
