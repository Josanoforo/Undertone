function voiceSummary(engines) {
  if (!Array.isArray(engines)) return 'Voice availability unknown.';
  return engines.map(engine => {
    const state = engine.available === true ? 'available' : engine.available === false ? 'unavailable' : 'unknown';
    let detail = '';
    if (engine.available === true && engine.tested !== true) detail = 'configuration detected; synthesis not tested';
    else if (engine.emergency && engine.available == null) detail = 'emergency voice; checked only on request';
    else if (engine.id === 'elevenlabs' && engine.configured === false) detail = 'account or pricing not verified';
    return `${engine.id}: ${state}${detail ? ` (${detail})` : ''}`;
  }).join(' · ') || 'Voice availability unknown.';
}

const unknownVoice = 'Voice availability is unknown. Read current context for text, or check the available listening routes. No automatic fallback.';

function openGuidedContext(root, open) {
  const dialog = root.ownerDocument.getElementById('contextDialog');
  if (dialog) {
    dialog.classList.add('w19-guided-context');
    dialog.addEventListener('close', () => dialog.classList.remove('w19-guided-context'), {once:true});
  }
  return open?.();
}

export function mountEntry(root, api, identityScope, assertIdentity, actions = {}) {
  const section = document.createElement('section'); section.className = 'w19-guide';
  section.innerHTML = `<h2>Start with the companion</h2><p>Choose a language, then read received context or open the existing listening controls. Participation is optional.</p><label>Language <select data-language><option value="en">English</option><option value="es">Español</option></select></label> <button type="button" data-read>Read current context</button> <button type="button" data-voice>Choose a voice</button> <button type="button" data-check>Check voice availability</button><p role="status" aria-live="polite" data-status></p>`;
  root.append(section); const q = s => section.querySelector(s), status = q('[data-status]'); let generation = 0;
  status.textContent = unknownVoice;
  q('[data-language]').value = actions.language?.() || 'en';
  q('[data-language]').onchange = e => actions.setLanguage?.(e.target.value);
  q('[data-read]').onclick = () => openGuidedContext(root, actions.openContext);
  q('[data-voice]').onclick = () => actions.openCaptions?.();
  q('[data-check]').onclick = async () => { const s = identityScope(), g = ++generation; status.textContent = 'Checking available voices…'; try { const result = await api.call('p12CollabGet', null, 'speech-options', {scope:s}); assertIdentity(s); if (g !== generation) return; if (!Array.isArray(result.engines)) throw Error(); status.textContent = `${voiceSummary(result.engines)}. Read current context for text instead, or choose a voice explicitly in listening controls. No automatic fallback.`; } catch { if (g === generation) status.textContent = 'Voice availability could not be confirmed. Read current context for text; no automatic fallback.'; } };
  return {reset(){generation++; status.textContent=unknownVoice;}, refresh(){q('[data-language]').value=actions.language?.()||'en';}};
}
export function mountSetup(root, actions = {}) {
 const section=document.createElement('section');section.className='w19-guide';section.innerHTML=`<h2>Guided session setup</h2><ol><li>Review received context and choose a source.</li><li>Choose the interface language, preview current text, or inspect available listening controls.</li><li>Review invitation status and use the offered preview or configured viewer link.</li></ol><p>Configured invitation links do not establish external reachability. Voice availability must be checked separately; reading text remains an explicit choice.</p><button type="button" data-readiness>Check readiness</button><p role="status" aria-live="polite" data-readiness-status>Readiness is unknown.</p><button type="button" data-source>Review sources</button> <button type="button" data-text-preview>Preview current text</button> <button type="button" data-preview>Open listening controls</button> <button type="button" data-invite>Open invitation controls</button> <button type="button" data-copy>Copy invitation</button>`;root.append(section);
 let generation=0;
 section.querySelector('[data-readiness]').onclick=async()=>{const status=section.querySelector('[data-readiness-status]'), ticket=++generation;status.textContent='Checking readiness…';try{const data=await actions.readiness();if(ticket!==generation)return;const text=data.textFallback===true?(data.source?.state==='available'?'Text reading: available. Use Preview current text.':'Text reading is available when a source is shared.'):'Text reading availability is unconfirmed.';status.textContent=`Source: ${data.source?.state||'unknown'} · invitation: ${data.invitation?.state||'unknown'} · ${voiceSummary(data.engines)}. ${text} Configured link reachability is unverified; no automatic fallback.`;}catch{if(ticket===generation)status.textContent='Readiness could not be confirmed. Review sources to inspect available text before continuing.';}};section.querySelector('[data-source]').onclick=()=>actions.sources?.();section.querySelector('[data-text-preview]').onclick=()=>actions.sources?.();section.querySelector('[data-preview]').onclick=()=>actions.preview?.();section.querySelector('[data-invite]').onclick=()=>actions.invitation?.();section.querySelector('[data-copy]').onclick=()=>actions.copy?.();return {reset(){generation++;section.querySelector('[data-readiness-status]').textContent='Readiness is unknown.';},refresh(){}};
}
