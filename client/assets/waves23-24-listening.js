// Listening UI; network and the sole player are injected by PRIMARY.
export function mount(root, initialContext = {}) {
  if (!root || typeof root.append !== 'function') throw new TypeError('A root element is required');
  let context = initialContext, epoch = 0, destroyed = false, profiles = [], selected = null, pending = null, busy = false, playerState = 'unavailable';
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
  const section = el('section'); section.className = 'w23-listening'; section.setAttribute('aria-label', 'Listening');
  const heading = el('h2', 'Listening profiles');
  const languageLabel = el('label', 'Listening language'); const language = el('select'); language.setAttribute('aria-label', 'Listening language');
  for (const [v, t] of [['en', 'English'], ['es', 'Español']]) { const o = el('option', t); o.value = v; o.lang = v; language.append(o); } languageLabel.append(language);
  const voiceLabel = el('label', 'Voice'); const voice = el('select'); voiceLabel.append(voice);
  const profileLabel = el('label', 'Pronunciation and quality profile'); const profile = el('select'); profileLabel.append(profile);
  const details = el('p', 'Load available profiles to choose a voice.');
  const load = el('button', 'Load profiles'), restore = el('button', 'Restore selected profile'), choose = el('button', 'Select profile'), start = el('button', 'Start listening'), pause = el('button', 'Pause'), stop = el('button', 'Stop'), recover = el('button', 'Check previous request'), resume = el('button', 'Resume'), play = el('button', 'Play ready audio');
  for (const b of [load, restore, choose, start, pause, stop, recover, resume, play]) b.type = 'button';
  const controls = el('div'); controls.className = 'w23-listening-controls'; controls.append(load, restore, choose, start, pause, stop, recover, resume, play);
  const status = el('p', 'Unavailable'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  section.append(heading, languageLabel, voiceLabel, profileLabel, details, controls, status); root.append(section);
  const refKeys = ['sessionId', 'sourceId', 'momentId', 'sourceRevision', 'startMs', 'endMs'];
  const refKey = r => r && refKeys.every(k => r[k] !== null && r[k] !== undefined) ? JSON.stringify(refKeys.map(k => r[k])) : null;
  const identity = c => [c?.scopeGeneration, c?.sessionId, c?.actorId, c?.sourceId, c?.sourceRevision, c?.profileGeneration, c?.rightsGeneration, refKey(c?.sourceRef)];
  const deliveryIdentity = c => [c?.policyRevision, c?.generation?.runId, c?.generation?.segmentId, c?.generation?.expectedRevision, c?.generation?.outputFormat, c?.playerScope];
  const same = (a,b) => a.every((v,i) => Object.is(v,b[i]));
  const eligible = c => identity(c).every(v => v !== null && v !== undefined && v !== '') && c.sourceRef.sessionId === c.sessionId && c.sourceRef.sourceId === c.sourceId && c.sourceRef.sourceRevision === c.sourceRevision;
  // Only opaque request metadata is journaled. Never save source text, audio,
  // credentials, or response bodies. A mismatch blocks a replacement request.
  const journalKey = 'w23-listening-pending-v1';
  let journalReady = false, journalScope = null, foreignJournal = false;
  async function loadJournal() {
    const token = epoch, c = context;
    journalReady = false; journalScope = null; foreignJournal = false; render();
    try {
      if (!eligible(c) || !globalThis.crypto?.subtle || !globalThis.sessionStorage) throw Error('Recovery unavailable');
      const stable = JSON.stringify([c.sessionId,c.actorId,refKey(c.sourceRef),c.policyRevision,c.generation?.runId,c.generation?.segmentId,c.generation?.expectedRevision,c.generation?.outputFormat]);
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(stable));
      if (destroyed || token !== epoch) return;
      journalScope = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2,'0')).join('');
      const raw = sessionStorage.getItem(journalKey);
      if (raw) {
        const saved = JSON.parse(raw);
        if (saved.scope !== journalScope || !['selection','generation','prepared','delivery'].includes(saved.kind) || typeof saved.requestId !== 'string') { foreignJournal = true; status.textContent = 'A previous request belongs to another context or cannot be read. Return to that context to check it; no new request was started.'; }
        else {
          pending = {kind:saved.kind, requestId:saved.requestId, runId:saved.runId, ticket:saved.ticket || null, state:saved.state || 'unknown'};
          if (saved.kind === 'selection') pending.body = {profileId:saved.profileId, revision:saved.revision, ref:{...c.sourceRef}};
          status.textContent = 'A previous request is preserved. Restore the selected profile and check it before continuing.';
        }
      }
      journalReady = true;
    } catch (_) { if (!destroyed && token === epoch) status.textContent = 'Safe request recovery is unavailable. Listening requests are disabled.'; }
    if (!destroyed && token === epoch) render();
  }
  function saveJournal(intent) {
    if (!journalReady || foreignJournal || !journalScope) throw Error('Recovery unavailable');
    const saved = {scope:journalScope,kind:intent.kind,requestId:intent.requestId};
    if (intent.runId) saved.runId = intent.runId;
    if (intent.ticket) saved.ticket = intent.ticket;
    if (intent.state) saved.state = intent.state;
    if (intent.kind === 'selection') { saved.profileId = intent.body.profileId; saved.revision = intent.body.revision; }
    sessionStorage.setItem(journalKey, JSON.stringify(saved));
  }
  function clearJournal() { sessionStorage.removeItem(journalKey); }
  const validProfile = p => p && typeof p.profileId === 'string' && Number.isSafeInteger(p.revision) && ['en','es'].includes(p.language) && typeof p.voiceId === 'string' && typeof p.engine === 'string' && Number.isSafeInteger(p.ruleSetRevision) && p.deliveryMode === 'buffered' && p.availability === 'unknown' && ['local','hosted_unknown'].includes(p.costMode);
  let fence = identity(context), deliveryFence = deliveryIdentity(context);
  function stopAudio(c) { try { Promise.resolve(c?.audioAuthority?.stopPlayback?.()).catch(() => {}); } catch (_) {} }
  function option(select, value, text) { const o = el('option', text); o.value = value; select.append(o); }
  function redrawOptions() {
    const priorVoice = voice.value, priorProfile = profile.value; voice.replaceChildren(); profile.replaceChildren();
    const available = profiles.filter(p => p.language === language.value);
    for (const v of [...new Set(available.map(p => p.voiceId))]) option(voice, v, v);
    if (available.some(p => p.voiceId === priorVoice)) voice.value = priorVoice;
    for (const p of available.filter(p => p.voiceId === voice.value)) option(profile, p.profileId, `${p.profileId} (revision ${p.revision})`);
    if (available.some(p => p.profileId === priorProfile && p.voiceId === voice.value)) profile.value = priorProfile;
    const p = currentProfile();
    details.textContent = p ? `${p.engine}; pronunciation revision ${p.ruleSetRevision}; availability unknown; ${p.costMode === 'local' ? 'local cost mode' : 'hosted cost unknown; audio delivery unavailable for this profile'}; buffered delivery. No automatic fallback. Use the shared player for playback controls.` : 'No available profile for this language and voice.';
  }
  function currentProfile() { return profiles.find(p => p.profileId === profile.value && p.voiceId === voice.value && p.language === language.value); }
  function render() {
    const ok = eligible(context), p = currentProfile(), a = context?.audioAuthority, safe = journalReady && !foreignJournal;
    language.disabled = busy || !!pending || !ok;
    load.disabled = busy || !ok || typeof context.listProfiles !== 'function';
    restore.disabled = busy || (pending && pending.kind === 'selection') || !ok || typeof context.getSelection !== 'function';
    voice.disabled = busy || !!pending || !profiles.some(p => p.language === language.value); profile.disabled = busy || !!pending || !p;
    choose.disabled = busy || !safe || !!pending || !ok || !p || typeof context.selectProfile !== 'function' || typeof context.createRequestId !== 'function';
    start.disabled = busy || !safe || (pending && pending.kind !== 'prepared') || !ok || !selected || !p || p.costMode !== 'local' || selected.profileId !== p.profileId || selected.revision !== p.revision || typeof context.prepareGeneration !== 'function' || typeof context.createRequestId !== 'function' || typeof context.admitDelivery !== 'function' || !context.generation || !Number.isSafeInteger(context.policyRevision) || context.policyRevision < 0;
    start.textContent = pending?.kind === 'prepared' ? 'Request prepared audio' : 'Start listening';
    play.disabled = busy || pending?.kind !== 'delivery' || pending.state !== 'ready' || !pending.ticket || !selected || !p || selected.profileId !== p.profileId || selected.revision !== p.revision || typeof context.viewDelivery !== 'function' || typeof a?.playReady !== 'function';
    // The released player has its own native pause/resume controls; its
    // injected authority does not report those events or expose callbacks.
    resume.disabled = true; pause.disabled = true;
    resume.title = pause.title = 'Use the shared player controls; this component cannot observe their state.';
    stop.disabled = !['playing','buffering','waiting','paused'].includes(playerState) || typeof a?.stopPlayback !== 'function';
    recover.disabled = busy || !safe || !ok || !pending || (pending.kind === 'selection' ? typeof context.getOperation !== 'function' : pending.kind === 'generation' ? !selected || typeof context.getGeneration !== 'function' : pending.kind === 'delivery' ? (pending.ticket ? typeof context.viewDelivery !== 'function' : !selected || !p || selected.profileId !== p.profileId || selected.revision !== p.revision || typeof context.lookupDeliveryReceipt !== 'function') : true);
  }
  function validCapture(owner, token, captured) { return !destroyed && epoch === token && same(captured, identity(context)) && eligible(context); }
  async function run(fn, onSuccess, onFailure) {
    const owner = context, token = epoch, captured = identity(owner); busy = true; render();
    try { const value = await fn(owner); if (validCapture(owner, token, captured)) onSuccess(value); }
    catch (_) { if (validCapture(owner, token, captured)) onFailure(); }
    finally { if (validCapture(owner, token, captured)) { busy = false; render(); } }
  }
  function clearSelection() { epoch++; busy = false; selected = null; stopAudio(context); playerState = 'unavailable'; }
  load.onclick = () => { if (load.disabled) return; run(c => c.listProfiles(), r => { if (!Array.isArray(r?.profiles) || !r.profiles.every(validProfile)) throw Error('Invalid profiles'); profiles = r.profiles; clearSelection(); redrawOptions(); status.textContent = 'Choose a profile. Availability is unknown until used.'; render(); }, () => { profiles = []; clearSelection(); redrawOptions(); status.textContent = 'Profiles unavailable.'; render(); }); };
  restore.onclick = () => { if (restore.disabled) return; run(c => c.getSelection(), r => { const s = r?.selection, p = r?.profile; if (!validProfile(p) || !s || s.profileId !== p.profileId || s.revision !== p.revision || refKey(s.ref) !== refKey(context.sourceRef)) throw Error('Invalid selection'); stopAudio(context); playerState = 'unavailable'; profiles = [p]; language.value = p.language; redrawOptions(); selected = s; status.textContent = 'Selected profile restored. Availability remains unknown.'; }, () => { selected = null; status.textContent = 'Selected profile unavailable for this source.'; }); };
  language.onchange = () => { epoch++; busy = false; clearSelection(); profiles = []; redrawOptions(); status.textContent = 'Language selected. Load profiles for this source.'; render(); };
  voice.onchange = () => { clearSelection(); redrawOptions(); render(); };
  profile.onchange = () => { clearSelection(); redrawOptions(); render(); };
  async function selectExactProfile(target) {
    if (destroyed || busy || pending || !journalReady || foreignJournal || !eligible(context) || typeof context.selectProfile !== 'function' || typeof context.createRequestId !== 'function') return {state:'unavailable'};
    if (!profiles.length && typeof context.listProfiles === 'function') {
      const owner = context, token = epoch, captured = identity(owner);
      await run(c => c.listProfiles(), r => { if (!Array.isArray(r?.profiles) || !r.profiles.every(validProfile)) throw Error('Invalid profiles'); profiles = r.profiles; redrawOptions(); }, () => { status.textContent = 'Profiles unavailable.'; });
      if (!validCapture(owner, token, captured) || busy || pending || !journalReady || foreignJournal) return {state:'unavailable'};
    }
    const matches = profiles.filter(p => p.profileId === target?.profileId && p.revision === target?.revision);
    if (matches.length !== 1) return {state:'unavailable'};
    const p = matches[0];
    let requestId; try { requestId = context.createRequestId(); } catch (_) { return {state:'unavailable'}; }
    if (typeof requestId !== 'string' || !requestId) return {state:'unavailable'};
    clearSelection(); language.value = p.language; redrawOptions(); voice.value = p.voiceId; redrawOptions(); profile.value = p.profileId; redrawOptions();
    const body = {requestId, profileId:p.profileId, revision:p.revision, ref:{...context.sourceRef}}; pending = {kind:'selection', requestId, body};
    let confirmed = false;
    await run(c => { saveJournal(pending); return c.selectProfile(body); }, r => { const s = r?.selection; if (!s || s.profileId !== body.profileId || s.revision !== body.revision || refKey(s.ref) !== refKey(body.ref)) throw Error('Invalid selection'); clearJournal(); selected = s; pending = null; confirmed = true; status.textContent = 'Profile selected. Start listening when ready.'; }, () => { status.textContent = 'Selection outcome unknown. Check the previous request before another selection.'; });
    return {state:confirmed ? 'confirmed' : 'unknown'};
  }
  choose.onclick = () => { if (!choose.disabled) void selectExactProfile(currentProfile()); };
  function acceptBinding(r, requestId, runId) { const b = r?.binding; if (!b || b.requestId !== requestId || b.runId !== runId || b.profileId !== selected?.profileId || b.profileRevision !== selected?.revision || refKey(b.selectionRef) !== refKey(context.sourceRef) || typeof b.identityDigest !== 'string') throw Error('Invalid binding'); return b; }
  function observeDelivery(r) {
    if (!r || !['queued','running','ready','stale','cancelled','unavailable','unknown','full'].includes(r.state)) throw Error('Invalid delivery');
    if (r.ticket != null && (typeof r.ticket !== 'string' || !/^[0-9a-f]{64}$/.test(r.ticket))) throw Error('Invalid ticket');
    pending = {...pending, kind:'delivery', ticket:r.ticket || pending.ticket || null, state:r.state};
    saveJournal(pending);
    playerState = ['queued','running'].includes(r.state) ? 'waiting' : 'unavailable';
    status.textContent = `Buffered delivery: ${r.state}. ${r.state === 'ready' ? 'Play when ready.' : 'Check the previous request for updates.'}`;
  }
  function deliveryBody(intent) {
    const p = currentProfile();
    if (!p || !selected || selected.profileId !== p.profileId || selected.revision !== p.revision || !intent.runId) throw Error('Selection unavailable');
    return {requestId:intent.requestId, source:'speech:' + intent.runId, sourceRevision:context.sourceRevision, language:p.language, voice:p.voiceId, policyRevision:context.policyRevision, choice:'local'};
  }
  function dispatchPrepared() {
    const intent = pending, body = deliveryBody(intent);
    pending = {...intent, kind:'delivery', ticket:null, state:'unknown'};
    run(c => { saveJournal(pending); return c.admitDelivery(body); }, observeDelivery, () => { status.textContent = 'Delivery outcome unknown. No automatic retry or alternative was started.'; });
  }
  start.onclick = () => {
    if (start.disabled) return; if (pending?.kind === 'prepared') { dispatchPrepared(); return; } const p = currentProfile(), g = context.generation, requestId = context.createRequestId();
    if (typeof requestId !== 'string' || !requestId || !g || typeof g.runId !== 'string' || typeof g.segmentId !== 'string' || !Number.isSafeInteger(g.expectedRevision) || typeof g.outputFormat !== 'string') { status.textContent = 'Listening input unavailable.'; return; }
    const body = {runId:g.runId, segmentId:g.segmentId, expectedRevision:g.expectedRevision, requestId, outputFormat:g.outputFormat, profileId:p.profileId, profileRevision:p.revision}; pending = {kind:'generation', requestId, runId:g.runId};
    run(c => { saveJournal(pending); return c.prepareGeneration(body); }, r => { acceptBinding(r, requestId, g.runId); pending = {kind:'prepared', requestId, runId:g.runId}; saveJournal(pending); status.textContent = 'Preparation confirmed. Request prepared audio to continue.'; }, () => { status.textContent = 'Preparation outcome unknown. Check the previous request; no automatic retry.'; });
  };
  recover.onclick = () => { if (recover.disabled) return; const intent = pending;
    run(c => intent.kind === 'selection' ? c.getOperation(intent.requestId) : intent.kind === 'generation' ? c.getGeneration(intent.runId, intent.requestId) : intent.ticket ? c.viewDelivery(intent.ticket) : c.lookupDeliveryReceipt(deliveryBody(intent)), r => {
      if (intent.kind === 'selection') { const op = r?.operation, s = op?.result; if (op?.requestId !== intent.requestId || op.operation !== 'profile.select' || op.state !== 'complete' || s?.profileId !== intent.body.profileId || s.revision !== intent.body.revision || refKey(s.ref) !== refKey(intent.body.ref)) throw Error('Invalid receipt'); selected = s; status.textContent = 'Selection confirmed. Start listening when ready.'; }
      else if (intent.kind === 'generation') { acceptBinding(r, intent.requestId, intent.runId); pending = {...intent, kind:'prepared'}; saveJournal(pending); status.textContent = 'Preparation confirmed. Request prepared audio to continue.'; return; }
      else { observeDelivery(r); return; }
      clearJournal(); pending = null;
    }, () => { status.textContent = 'The previous request remains unknown or unavailable. No new request was started.'; });
  };
  play.onclick = () => { if (play.disabled) return; const intent = pending, owner = context, token = epoch, captured = identity(owner), selection = {source:'speech:' + intent.runId, sourceRevision:owner.sourceRevision, language:currentProfile().language, voice:currentProfile().voiceId, policyRevision:owner.policyRevision, choice:'local'}; busy = true; playerState = 'buffering'; status.textContent = 'Checking buffered audio and current access.'; render();
    const guard = () => { if (!validCapture(owner, token, captured) || pending !== intent) throw Error('Context changed'); };
    Promise.resolve().then(() => owner.viewDelivery(intent.ticket)).then(fresh => { guard(); if (fresh?.state !== 'ready' || !fresh.result) throw Error('Not ready'); status.textContent = 'Buffered audio is delegated to the shared player. Use its controls to play or pause.'; return owner.audioAuthority.playReady(fresh.result, selection, owner.playerScope, async digest => { guard(); const current = await owner.viewDelivery(intent.ticket); guard(); if (current?.state !== 'ready' || current.result?.audioSha256 !== digest) throw Error('Delivery changed'); }); }).then(() => { guard(); clearJournal(); pending = null; playerState = 'completed'; status.textContent = 'Buffered listening completed.'; }).catch(() => { if (validCapture(owner, token, captured)) { playerState = 'failed'; status.textContent = 'Playback unavailable or current access could not be confirmed.'; } }).finally(() => { if (validCapture(owner, token, captured)) { busy = false; render(); } });
  };
  stop.onclick = () => { if (stop.disabled) return; epoch++; busy = false; stopAudio(context); playerState = 'unavailable'; status.textContent = 'Listening stopped.'; render(); };
  redrawOptions(); render(); loadJournal();
  function update(next = {}) { if (destroyed) return; const changed = !same(fence, identity(next)) || !same(deliveryFence, deliveryIdentity(next)) || context.audioAuthority !== next.audioAuthority; if (changed) { epoch++; busy = false; stopAudio(context); profiles = []; selected = null; pending = null; playerState = 'unavailable'; status.textContent = 'Source or access changed. Load profiles again.'; } context = next; fence = identity(next); deliveryFence = deliveryIdentity(next); redrawOptions(); render(); if (changed) loadJournal(); }
  function destroy() { if (destroyed) return; destroyed = true; epoch++; stopAudio(context); for (const n of [load,restore,choose,start,pause,stop,recover,resume,play]) n.onclick = null; language.onchange = voice.onchange = profile.onchange = null; section.remove(); context = null; }
  return {update, destroy, selectExactProfile};
}
