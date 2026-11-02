export function mountPronunciation(root, {actions = {}} = {}) {
  const box=document.createElement('section'); box.className='w21-pronunciation';
  const heading=document.createElement('h2'); heading.textContent='Pronunciation preview';
  const intro=document.createElement('p'); intro.textContent='Preview a creator rule for the selected voice. Visible text and meaning remain unchanged.';
  const status=document.createElement('p'); status.setAttribute('role','status');
  const content=document.createElement('div'); box.append(heading,intro,status,content); root.append(box);
  let generation=0, current=null, preview=null, destroyed=false;
  const el=(tag,text)=>{const n=document.createElement(tag); if(text != null)n.textContent=String(text); return n;};
  function reset(){generation++;current=null;preview=null;content.replaceChildren();status.textContent='Preview cleared.';}
  function update(p,ticket){
    if(destroyed || ticket!==generation)return false;
    reset();
    if(!p || p.rightsState!=='available' || p.actorRole!=='creator' || !p.scopeKey || !p.rule || !Number.isInteger(p.rule.revision)){status.textContent='Pronunciation preview unavailable or access changed.';return false;}
    current=p; const epoch=generation;
    content.append(el('p',`Voice: ${p.voice || 'unknown'} · Language: ${p.language || 'unknown'} · Rule revision: ${p.rule.revision}`));
    content.append(el('p',`Original text: ${p.text || ''}`));
    const caps=p.capabilities || {}; const state=k=>{const value=caps[k==='pronunciation'?'aliases':k];return ['supported','unsupported','unknown'].includes(value)?value:'unknown';};
    for(const [label,k] of [['Pronunciation rules','pronunciation'],['Rate','rate'],['Text alignment','alignment']])content.append(el('p',`${label}: ${state(k)}.`));
    const ruleLabel=el('label','Spoken form for this preview '), spoken=el('input'); spoken.value=String(p.rule.spokenForm || ''); spoken.disabled=state('pronunciation')!=='supported'; ruleLabel.append(spoken); content.append(ruleLabel);
    const label=el('label','Rate '), rate=el('input'); rate.type='number'; rate.min='0.75';rate.max='1.5';rate.step='0.05';rate.value='1';rate.disabled=state('rate')!=='supported';label.append(rate);content.append(label);
    const make=el('button','Prepare preview');make.type='button'; make.disabled=state('pronunciation')!=='supported' || typeof actions.preview!=='function'; content.append(make);
    const play=el('button','Play preview');play.type='button';play.disabled=true;content.append(play);
    spoken.oninput=rate.oninput=()=>{preview=null;play.disabled=true;status.textContent='Settings changed. Prepare a new preview.';};
    if(make.disabled)status.textContent=state('pronunciation')==='unknown'?'Voice support is unknown; preview is unavailable.':'Preview is unavailable for this voice.';else status.textContent='Preview is ready to request; no audio starts automatically.';
    make.onclick=async()=>{if(epoch!==generation)return;const value=Number(rate.value);if(!Number.isFinite(value)||value<0.75||value>1.5){status.textContent='Choose a rate between 0.75 and 1.5.';return;}make.disabled=true;play.disabled=true;preview=null;const draft=spoken.value; const chosenRate=rate.value;status.textContent='Preparing preview…';try{const result=await actions.preview({projection:current,spokenForm:draft,rate:state('rate')==='supported'?value:null});if(epoch!==generation)return;if(spoken.value!==draft || rate.value!==chosenRate){status.textContent='Settings changed. Prepare a new preview.';return;}if(!result || result.rightsState!=='available' || result.ruleRevision!==current.rule.revision || result.textRevision!==current.textRevision || !result.audioRef){status.textContent='Preview is unavailable or no longer current.';return;}preview=result;play.disabled=typeof actions.play!=='function';status.textContent=play.disabled?'Preview available; playback is unavailable.':'Preview ready. Choose Play preview to listen.';}catch{if(epoch===generation)status.textContent='Preview could not be prepared.';}finally{if(epoch===generation)make.disabled=false;}};
    play.onclick=async()=>{if(epoch!==generation||!preview||typeof actions.play!=='function')return;try{await actions.play({projection:current,preview});if(epoch===generation)status.textContent='Playback requested.';}catch{if(epoch===generation)status.textContent='Playback unavailable.';}};
    return true;
  }
  return {update,reset,destroy(){reset();destroyed=true;box.remove();},getGeneration:()=>generation};
}
