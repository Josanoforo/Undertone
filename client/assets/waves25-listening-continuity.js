// Scoped continuity controls; all effects belong to injected host authorities.
/** @typedef {{actorId:string,sessionId:string,scopeGeneration:string|number,sourceId:string,sourceRevision:string|number,rightsGeneration:string|number}} Scope */
/** @typedef {{language:string,profileId:string,profileRevision:number,mode:'read'|'listen'}} Choice */
/** @typedef {{bindingId:string,offsetMs:number,sourceId:string,sourceRevision:string|number}} Position */
/** @typedef {{scope:Scope,saved:Choice|null,supported:Choice[],position:Position|null,available:boolean,message:string|null,currentness:{state:'live'|'delayed'|'unknown',delayMs?:number,catchUpDescription?:string,catchUpPolicy?:string},receipt:'ready'|'unknown'|'stale'|'withdrawn'|'unavailable',revision:number}} Snapshot */
/** @typedef {{kind:'position-save-not-dispatched',scope:Scope,token:object}} PositionNotDispatched Trusted host assertion: no journal or effect issued. */
/** @typedef {{kind:'preference-save-not-dispatched',scope:Scope,token:object}} PreferenceNotDispatched Trusted host assertion: no journal or effect issued. */
/** @typedef {{scope:Scope,snapshot?:Snapshot,load:()=>Promise<Snapshot>,save:(value:{choice:Choice,expectedRevision:number},token:object)=>Promise<Snapshot>,savePosition:(value:{expectedRevision:number},token:object)=>Promise<Snapshot>,preload:()=>Promise<{state:string}>,restorePosition:(scope:Scope,position:Position)=>Promise<void>,catchUp:(scope:Scope,policy:string)=>Promise<void>}} Host */
/** Convert the released M02 reconcile DTO; other arguments are current host-authorized observations. */
export function snapshotFromDTO(scope, dto, supported, currentness, receipt) {
  if (!dto || !['unset','available','unavailable'].includes(dto.state) || !Number.isSafeInteger(dto.revision) || dto.revision < 0) throw new TypeError('Invalid reconciliation');
  const selection=dto.selection, ref=selection?.ref;
  if (selection && (!ref || ref.sessionId!==scope.sessionId || ref.sourceId!==scope.sourceId || ref.sourceRevision!==scope.sourceRevision)) throw new TypeError('Stale selection');
  if (dto.state==='available' && !selection) throw new TypeError('Missing selection');
  const saved=selection ? {language:selection.language,profileId:selection.profileId,profileRevision:selection.profileRevision,mode:dto.mode} : null;
  let position=null;
  if (selection && dto.positionAvailable===true && dto.position!==null) {
    if (!dto.position || typeof dto.position.bindingId!=='string' || !dto.position.bindingId || !Number.isSafeInteger(dto.position.offsetMs) || dto.position.offsetMs<0) throw new TypeError('Invalid position');
    position={...dto.position,sourceId:scope.sourceId,sourceRevision:scope.sourceRevision};
  }
  let preparation=null;
  if(dto.continuity){
    const observation=dto.continuity, selected=selection||dto.modeSupport?.selection, bound=observation.selection;
    if(!selected||!bound||['profileId','profileRevision','language','configDigest'].some(k=>selected[k]!==bound[k])||['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].some(k=>selected.ref?.[k]!==bound.ref?.[k])||bound.ref.sessionId!==scope.sessionId||bound.ref.sourceId!==scope.sourceId||bound.ref.sourceRevision!==scope.sourceRevision)throw new TypeError('Stale continuity observation');
    currentness=observation.currentness;preparation=observation.preparation||null;if(preparation)receipt=preparation.state;
  }
  return {scope,saved,supported,position,available:dto.state==='available',message:typeof dto.message==='string'?dto.message:null,currentness,receipt,preparation,revision:dto.revision};
}
export function mount(root, initialHost) {
  if (!root || typeof root.append !== 'function') throw new TypeError('A root element is required');
  let host=initialHost, epoch=0, destroyed=false, busy=false, snapshot=null, chosen=null;
  const uncertainSaves=new Map(), uncertainCatchups=new Set();
  const el=(tag,text)=>{const n=document.createElement(tag); if(text!=null)n.textContent=text; return n;};
  const section=el('section'); section.className='w25-continuity'; section.setAttribute('aria-label','Listening continuity');
  const title=el('h2','Continue listening'), saved=el('p'), position=el('p'), current=el('p'), receipt=el('p');
  const label=el('label','Supported language, voice profile and mode'), choices=el('select'); label.append(choices);
  const reload=el('button','Restore preferences'), save=el('button','Save chosen preference'), savePosition=el('button','Save current position'), preload=el('button','Check prepared audio'), restore=el('button','Return to saved position'), catchup=el('button','Catch up');
  for(const b of [reload,save,savePosition,preload,restore,catchup]) b.type='button';
  const status=el('p','Restore preferences when ready.'); status.setAttribute('role','status'); status.setAttribute('aria-live','polite');
  const recoveryLink=el('a','Open Catch up and Go live controls in the player');recoveryLink.href='#p12Root';
  const policyNotice=el('p');
  section.append(title,saved,position,current,receipt,policyNotice,recoveryLink,label,reload,save,savePosition,preload,restore,catchup,status); root.append(section);
  const keys=['actorId','sessionId','scopeGeneration','sourceId','sourceRevision','rightsGeneration'];
  const validScope=s=>s && keys.every(k=>(typeof s[k]==='string' && s[k].length>0)||(typeof s[k]==='number' && Number.isSafeInteger(s[k]) && s[k]>=0));
  const sameScope=(a,b)=>validScope(a)&&validScope(b)&&keys.every(k=>a[k]===b[k]);
  const scopeKey=s=>JSON.stringify(keys.map(k=>s[k]));
  const validChoice=c=>c && typeof c.language==='string' && !!c.language && typeof c.profileId==='string' && !!c.profileId && Number.isSafeInteger(c.profileRevision) && c.profileRevision>=0 && ['read','listen'].includes(c.mode);
  const sameChoice=(a,b)=>validChoice(a)&&validChoice(b)&&['language','profileId','profileRevision','mode'].every(k=>a[k]===b[k]);
  const validPosition=(p,s)=>p===null || (p && typeof p.bindingId==='string' && !!p.bindingId && Number.isSafeInteger(p.offsetMs) && p.offsetMs>=0 && p.sourceId===s.sourceId && p.sourceRevision===s.sourceRevision);
  function validSnapshot(s){return s && sameScope(s.scope,host?.scope) && (s.saved===null||validChoice(s.saved)) && typeof s.available==='boolean' && (s.message===null||typeof s.message==='string') && Array.isArray(s.supported) && s.supported.every(validChoice) && validPosition(s.position,s.scope) && s.currentness && ['live','delayed','unknown'].includes(s.currentness.state) && (s.currentness.delayMs===undefined || (Number.isSafeInteger(s.currentness.delayMs)&&s.currentness.delayMs>=0)) && ['ready','pending','failed','unknown','stale','withdrawn','unavailable'].includes(s.receipt) && (!s.preparation||(s.preparation.state===s.receipt&&typeof s.preparation.message==='string')) && Number.isSafeInteger(s.revision)&&s.revision>=0;}
  const describe=c=>c.language+' · '+c.profileId+' (revision '+c.profileRevision+') · '+c.mode;
  function render(){
    const s=snapshot, supported=s && s.supported.some(c=>sameChoice(c,s.saved));
    saved.textContent=s?.saved ? 'Saved: '+describe(s.saved)+(supported&&s.available?'':' — no longer available. Choose an available alternative explicitly.') : (s?.message || 'No saved preference.');
    position.textContent=s?.position ? 'Saved playback position: '+s.position.offsetMs+' ms in the current source.' : 'Playback position unknown or untimed.';
    current.textContent=(!s || s.currentness.state==='unknown' ? 'Live position unavailable.' : s.currentness.state==='live' ? 'At the latest reported source position.' : 'Delayed'+(s.currentness.delayMs===undefined?'':' by '+s.currentness.delayMs+' ms')+'.')+(s?.currentness.message?' '+s.currentness.message:'');
    policyNotice.textContent=s?.currentness.catchUpDescription||'Catch-up policy unavailable. No segments will be discarded here.';
    recoveryLink.hidden=!s;
    receipt.textContent=s?'Prepared audio: '+s.receipt+'.'+(s.preparation?.message?' '+s.preparation.message:''):'Prepared audio not checked.';
    choices.replaceChildren(); const placeholder=el('option','Choose an available preference'); placeholder.value=''; choices.append(placeholder);
    if(s)s.supported.forEach((c,i)=>{const o=el('option',describe(c));o.value=String(i+1);choices.append(o);});
    const i=chosen && s ? s.supported.findIndex(c=>sameChoice(c,chosen)) : -1; choices.value=i<0?'':String(i+1);
    reload.disabled=busy||!validScope(host?.scope)||typeof host?.load!=='function'; choices.disabled=busy||!s||!s.supported.length;
    save.disabled=busy||!s||uncertainSaves.has(scopeKey(host.scope))||!chosen||typeof host?.save!=='function'; preload.disabled=busy||!s||(!s.preparation&&typeof host?.preload!=='function');
    savePosition.disabled=busy||!s||uncertainSaves.has(scopeKey(host.scope))||typeof host?.savePosition!=='function';
    restore.disabled=busy||!s?.position||!s.available||!supported||typeof host?.restorePosition!=='function';
    catchup.disabled=busy||!s||!s.available||!supported||uncertainCatchups.has(scopeKey(host.scope))||s.receipt!=='ready'||s.currentness.state!=='delayed'||typeof s.currentness.catchUpDescription!=='string'||!s.currentness.catchUpDescription.trim()||typeof s.currentness.catchUpPolicy!=='string'||!s.currentness.catchUpPolicy||typeof host?.catchUp!=='function';
    catchup.hidden=typeof host?.catchUp!=='function';
  }
  function run(action,success,failure){
    const token=epoch,owner=host,scope={...host.scope}; busy=true; render();
    const active=()=>!destroyed&&token===epoch&&host===owner&&sameScope(scope,host.scope);
    Promise.resolve().then(()=>{if(!active())throw Error('Scope changed');return action(owner);}).then(v=>{if(active())success(v);}).catch(e=>{if(active())failure(e);}).finally(()=>{if(active()){busy=false;render();}});
  }
  function accept(s){if(!validSnapshot(s))throw Error('Invalid or stale snapshot');snapshot=s;chosen=null;}
  reload.onclick=()=>{if(reload.disabled)return;run(h=>h.load(),s=>{accept(s);const key=scopeKey(host.scope),pending=uncertainSaves.get(key);if(pending?.choice&&s.revision>pending.revision&&sameChoice(s.saved,pending.choice))uncertainSaves.delete(key);status.textContent=uncertainSaves.has(key)?'Previous save remains unknown. Check its original receipt before another save.':'Preferences restored. Choose an available preference before saving.';},()=>{snapshot=null;chosen=null;status.textContent='Preferences could not be restored; no change was made.';});};
  choices.onchange=()=>{const i=Number(choices.value)-1;chosen=Number.isInteger(i)&&snapshot?.supported[i]?snapshot.supported[i]:null;render();};
  save.onclick=()=>{if(save.disabled)return;const choice={...chosen},expectedRevision=snapshot.revision,key=scopeKey(host.scope),scope={...host.scope},token=Object.freeze({});uncertainSaves.set(key,{kind:'preference',choice,revision:expectedRevision,token});run(h=>h.save({choice,expectedRevision},token),s=>{accept(s);if(s.revision<=expectedRevision||!sameChoice(s.saved,choice))throw Error('Unconfirmed save');uncertainSaves.delete(key);status.textContent='Preference saved.';},e=>{const pending=uncertainSaves.get(key);if(e?.kind==='preference-save-not-dispatched'&&e.token===token&&sameScope(e.scope,scope)&&pending?.kind==='preference'&&pending.token===token){uncertainSaves.delete(key);status.textContent='Preference was not saved. Review the current conditions before trying again.';}else status.textContent='Save outcome unknown. Restore preferences and check its original receipt.';});};
  savePosition.onclick=()=>{if(savePosition.disabled)return;const expectedRevision=snapshot.revision,key=scopeKey(host.scope),scope={...host.scope},token=Object.freeze({});uncertainSaves.set(key,{kind:'position',revision:expectedRevision,token});run(h=>h.savePosition({expectedRevision},token),s=>{accept(s);if(s.revision<=expectedRevision||!s.position)throw Error('Unconfirmed position');uncertainSaves.delete(key);status.textContent='Current position saved.';},e=>{const pending=uncertainSaves.get(key);if(e?.kind==='position-save-not-dispatched'&&e.token===token&&sameScope(e.scope,scope)&&pending?.kind==='position'&&pending.token===token){uncertainSaves.delete(key);status.textContent='Position was not saved. Review the current conditions before trying again.';}else status.textContent='Position save outcome unknown. Check its original receipt before another save.';});};
  preload.onclick=()=>{if(preload.disabled)return;const readSnapshot=!!snapshot?.preparation;run(h=>readSnapshot?h.load():h.preload(),r=>{if(readSnapshot){accept(r);r={state:r.receipt};}status.textContent=r&&['ready','pending','failed','unknown','stale','withdrawn','unavailable'].includes(r.state)?'Prepared audio: '+r.state+'. No playback was started.':'Prepared audio state unavailable.';},()=>{snapshot=null;chosen=null;status.textContent='Prepared audio state unavailable. No playback was started.';});};
  restore.onclick=()=>{if(restore.disabled)return;const p={...snapshot.position};run(h=>h.restorePosition({...h.scope},p),()=>{status.textContent='Position restored in the shared player. Start playback there when ready.';},()=>{status.textContent='Position could not be restored. Check the current source and access.';});};
  catchup.onclick=()=>{if(catchup.disabled)return;const policy=snapshot.currentness.catchUpPolicy,key=scopeKey(host.scope);uncertainCatchups.add(key);run(h=>h.catchUp({...h.scope},policy),()=>{uncertainCatchups.delete(key);status.textContent='Catch-up requested. Restore the current position to see the result.';snapshot=null;chosen=null;},()=>{status.textContent='Catch-up outcome unknown. Check its original receipt before another request.';snapshot=null;chosen=null;});};
  function update(next){if(destroyed)return;epoch++;busy=false;const changed=!sameScope(host?.scope,next?.scope);host=next;snapshot=null;chosen=null;status.textContent=changed?'Context changed. Restore preferences for this viewer and source.':'Restore current preferences.';if(next?.snapshot&&validSnapshot(next.snapshot))snapshot=next.snapshot;render();}
  function confirmPositionSave(scope,token,confirmed){
    if(destroyed||busy||!sameScope(scope,host?.scope))return false;
    const key=scopeKey(scope),pending=uncertainSaves.get(key);
    if(!pending||pending.kind!=='position'||pending.token!==token||!validSnapshot(confirmed)||confirmed.revision<=pending.revision||!confirmed.position)return false;
    snapshot=confirmed;chosen=null;uncertainSaves.delete(key);status.textContent='Original position save confirmed.';render();return true;
  }
  function reset(){if(destroyed)return;epoch++;busy=false;snapshot=null;chosen=null;status.textContent='View reset. Restore preferences when ready.';render();}
  function destroy(){if(destroyed)return;destroyed=true;epoch++;for(const b of [reload,save,savePosition,preload,restore,catchup])b.onclick=null;choices.onchange=null;section.remove();host=null;snapshot=null;chosen=null;}
  if(host?.snapshot&&validSnapshot(host.snapshot))snapshot=host.snapshot;render();return {update,reset,destroy,confirmPositionSave};
}
