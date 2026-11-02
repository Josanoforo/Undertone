// The host persists verified access only when the user explicitly chooses it.
/** @typedef {{sessionId:string, credential:string, signal:AbortSignal}} VerificationRequest */
/** @typedef {{sessionId:string, role:'creator'|'viewer', actorId:string, expiresAt:string, session:object}} VerifiedIdentity */
/** @typedef {{generation:()=>unknown, verify:(request:VerificationRequest)=>Promise<VerifiedIdentity>, commit:(identity:VerifiedIdentity, credential:string, options:{mode:'tab-only'|'saved',generation:unknown,signal:AbortSignal})=>('tab-only'|'saved'|'save-failed'|false)}} Host */
export function mount(root, host) {
  if (!root || typeof root.append !== 'function') throw new TypeError('A root element is required');
  let generation=0, controller=null, destroyed=false, busy=false;
  const el=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  const section=el('section'),heading=el('h2','Resume saved access'),description=el('p','Use access you already hold. By default access is for this tab only.'),form=el('form'),sessionLabel=el('label','Session ID'),session=el('input'),credentialLabel=el('label','Access credential'),credential=el('input'),saveLabel=el('label','Save access on this device (stores your credential in this browser until removed).'),save=el('input'),submit=el('button','Verify and resume'),cancel=el('button','Cancel'),status=el('p');
  section.className='w30-resume';section.setAttribute('aria-label','Resume saved access');session.type='text';session.autocomplete='off';session.required=true;session.spellcheck=false;credential.type='password';credential.autocomplete='off';credential.required=true;credential.spellcheck=false;save.type='checkbox';sessionLabel.append(session);credentialLabel.append(credential);saveLabel.prepend(save);submit.type='submit';cancel.type='button';status.setAttribute('role','status');status.setAttribute('aria-live','polite');form.append(sessionLabel,credentialLabel,saveLabel,submit,cancel);section.append(heading,description,form,status);root.append(section);
  const clear=()=>{session.value='';credential.value='';save.checked=false;};
  const invalidate=()=>{generation++;controller?.abort();controller=null;busy=false;submit.disabled=false;clear();};
  const current=(n,h,g,c)=>{try{return !destroyed&&generation===n&&host===h&&!c.signal.aborted&&typeof h?.generation==='function'&&h.generation()===g;}catch{return false;}};
  const cancelAction=()=>{invalidate();status.textContent='Access entry cancelled.';session.focus();};
  cancel.addEventListener('click',cancelAction);
  form.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();cancelAction();}});
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(destroyed||busy)return;
    const sid=session.value.trim(),secret=credential.value,saveRequested=save.checked;
    clear();
    if(!sid||!secret){status.textContent='Enter the session ID and access credential.';session.focus();return;}
    const h=host;if(typeof h?.verify!=='function'||typeof h?.commit!=='function'||typeof h?.generation!=='function'){status.textContent='Access verification is unavailable.';session.focus();return;}
    let g;try{g=h.generation();}catch{status.textContent='Access verification is unavailable.';session.focus();return;}
    const n=++generation,c=new AbortController();controller=c;busy=true;submit.disabled=true;status.textContent='Verifying access…';
    try{
      const identity=await h.verify({sessionId:sid,credential:secret,signal:c.signal});
      if(!current(n,h,g,c))return;
      const expiry=Date.parse(identity?.expiresAt);
      if(!identity||identity.sessionId!==sid||!['creator','viewer'].includes(identity.role)||typeof identity.actorId!=='string'||!identity.actorId||!identity.session||identity.session.id!==sid||!Number.isFinite(expiry)||expiry<=Date.now())throw new Error('unverified');
      if(!current(n,h,g,c))return;
      const result=h.commit(identity,secret,{mode:saveRequested?'saved':'tab-only',generation:g,signal:c.signal});
      if(!['saved','tab-only','save-failed'].includes(result))throw new Error('unavailable');
      status.textContent=result==='saved'?'Access saved on this device.':result==='save-failed'?'Access resumed for this tab only. Browser storage could not be confirmed; check your browser storage before trying to save again.':'Access resumed for this tab only.';submit.focus();
    }catch{if(current(n,h,g,c)){status.textContent='Access could not be verified. Check your saved access and try again.';session.focus();}}
    finally{if(!destroyed&&generation===n){controller=null;busy=false;submit.disabled=false;clear();}}
  });
  return {update(next){if(destroyed)return;invalidate();host=next;status.textContent='';},reset(){if(destroyed)return;invalidate();status.textContent='';},destroy(){if(destroyed)return;invalidate();destroyed=true;host=null;section.remove();}};
}
