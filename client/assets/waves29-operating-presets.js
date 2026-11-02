/** Wave 29.2 creator policy UI. All transport and authority stay with the host. */
const REF_KEYS=['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'];
const atom=v=>(typeof v==='string'&&v.length>0)||(typeof v==='number'&&Number.isSafeInteger(v)&&v>=0);
const sameRef=(a,b)=>!!a&&!!b&&REF_KEYS.every(k=>a[k]===b[k]);
const validRef=ref=>!!ref&&REF_KEYS.every(k=>atom(ref[k]));
const safeUsd=v=>typeof v==='string'&&/^\d+(?:\.\d{1,6})?$/.test(v)?v:null;
const safeText=(v,max)=>typeof v==='string'&&v.length>0&&v.length<=max?v:null;
const knownReasons=new Set([
  'This profile language does not match the current source; this route does not switch languages.',
  'This profile identity is not supported by the current local source-reading route.',
  'This profile path is not configured by current policy.',
  'Current policy availability is unknown.',
  'Current policy reports this path unavailable.'
]);

function normalizeList(value,ref){
  const dto=value?.quality??value;
  if(!dto||!sameRef(dto.ref,ref)||!Array.isArray(dto.presets))return null;
  const presets=[];
  for(const p of dto.presets){
    const c=p?.conditions,f=c?.facts;
    if(!p||!safeText(p.id,160)||p.profileId!==p.id||!Number.isSafeInteger(p.profileRevision)||p.profileRevision<1||
       !safeText(p.label,100)||!['available','unavailable','unknown'].includes(p.availability)||
       typeof p.language!=='string'||!['en','es'].includes(p.language)||
       !safeText(p.conditionsDigest,128)||!c||!Number.isSafeInteger(c.policyRevision)||c.policyRevision<1||
       !['local','hosted'].includes(c.policyChoice)||!['primary','alternative'].includes(c.role)||
       typeof c.configured!=='boolean'||typeof c.deliveryPathSupported!=='boolean'||
       !(typeof c.sourceLanguage==='string'||c.sourceLanguage===null)||typeof c.profileLanguageMatches!=='boolean'||
       !(c.availabilityReason===null||knownReasons.has(c.availabilityReason))||
       !['available','unavailable','unknown'].includes(c.policyAvailability)||
       !f||!['available','unavailable','unknown'].includes(f.availability)||
       !(f.estimatedUsd===null||safeUsd(f.estimatedUsd))||!(f.reservationsUsd===null||safeUsd(f.reservationsUsd))||
       !(f.unknownHoldsUsd===null||safeUsd(f.unknownHoldsUsd))||
       !(f.estimateBasis===null||safeText(f.estimateBasis,100))||
       !(f.unknownHoldsPresent===null||typeof f.unknownHoldsPresent==='boolean')||
       !(f.unknownAfterDispatch===null||typeof f.unknownAfterDispatch==='boolean')||
       !(typeof c.sessionCapUsd==='string'||c.sessionCapUsd===null)||
       !['local','hosted_unknown'].includes(c.costMode))return null;
    presets.push({id:p.id,profileRevision:p.profileRevision,label:p.label,language:p.language,
      availability:p.availability,conditions:{policyRevision:c.policyRevision,policyChoice:c.policyChoice,
        role:c.role,configured:c.configured,deliveryPathSupported:c.deliveryPathSupported,
        sourceLanguage:c.sourceLanguage,profileLanguageMatches:c.profileLanguageMatches,
        availabilityReason:c.availabilityReason,policyAvailability:c.policyAvailability,
        sessionCapUsd:safeUsd(c.sessionCapUsd),costMode:c.costMode,
        facts:{availability:f.availability,estimatedUsd:safeUsd(f.estimatedUsd),
          estimateBasis:safeText(f.estimateBasis,100),reservationsUsd:safeUsd(f.reservationsUsd),
          unknownHoldsUsd:safeUsd(f.unknownHoldsUsd),unknownHoldsPresent:f.unknownHoldsPresent,
          unknownAfterDispatch:f.unknownAfterDispatch}},conditionsDigest:p.conditionsDigest});
  }
  return {ref:{...dto.ref},presets};
}

function validReceipt(value,pending){
  const operation=value?.operation??value;
  const result=operation?.result;
  return operation?.requestId===pending.requestId&&operation?.operation==='profile.select'&&
    operation?.state==='complete'&&result?.requestId===pending.requestId&&
    result?.profileId===pending.presetId&&result?.revision===pending.expectedRevision&&
    result?.policyRevision===pending.policyRevision&&result?.conditionsDigest===pending.conditionsDigest&&
    sameRef(result?.ref,pending.ref);
}

export function mount(root,initialHost={}){
  if(!root||typeof root.append!=='function')throw new TypeError('A root element is required');
  let host=initialHost,list=null,selected=null,accepted=false,pending=null,busy=false,destroyed=false,epoch=0,message='Check current quality choices when ready.';
  const el=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  const section=el('section');section.className='w29-presets';section.setAttribute('aria-label','Creator quality presets');
  const title=el('h3','Quality presets'),intro=el('p','Review current availability, policy and cost conditions before choosing an existing profile. Choosing a preset changes selection only; it does not start delivery.'),
    status=el('p');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const controls=el('div'),cards=el('div');section.append(title,intro,controls,cards,status);root.append(section);
  const scopeNow=scope=>!destroyed&&typeof host?.assertScope==='function'&&host.assertScope(scope)!==false;
  const callbacksReady=()=>validRef(host?.ref)&&typeof host?.listQualityPresets==='function'&&typeof host?.chooseQualityPreset==='function'&&typeof host?.readQualityReceipt==='function';
  const conditionsText=(preset)=>{
    const c=preset.conditions,f=c.facts,lines=[];
    lines.push(`Availability: ${preset.availability}.`);
    lines.push(`Policy role: ${c.role==='primary'?'Primary':'Explicit alternative'} (${c.policyChoice}).`);
    lines.push(`Policy availability: ${c.policyAvailability}.`);
    lines.push(`Cost mode: ${c.costMode==='hosted_unknown'?'Hosted; actual cost unknown':'Local; compute cost not measured'}.`);
    lines.push(`Session cap: ${c.sessionCapUsd===null?'unknown':`USD ${c.sessionCapUsd}`}.`);
    lines.push(`Estimated cost: ${f.estimatedUsd===null?'unknown':`USD ${f.estimatedUsd}`}${f.estimateBasis?` (${f.estimateBasis})`:''}.`);
    lines.push(`Existing reservations: ${f.reservationsUsd===null?'unknown':`USD ${f.reservationsUsd}`}.`);
    lines.push(`Unknown holds: ${f.unknownHoldsUsd===null?'unknown':`USD ${f.unknownHoldsUsd}`}; present=${f.unknownHoldsPresent===null?'unknown':f.unknownHoldsPresent}; after dispatch=${f.unknownAfterDispatch===null?'unknown':f.unknownAfterDispatch}.`);
    if(c.availabilityReason)lines.push(`Reason: ${c.availabilityReason}`);
    return lines;
  };
  function render(){
    if(destroyed)return;
    controls.replaceChildren();cards.replaceChildren();
    if(host?.scope?.role!=='operator'){
      status.textContent='Quality presets are available only in creator settings.';return;
    }
    const callbacks=callbacksReady();
    const check=el('button','Check current quality choices');check.type='button';check.disabled=busy||!callbacks;
    check.addEventListener('click',()=>loadChoices());controls.append(check);
    if(!callbacks){status.textContent='Preset selection is disabled because this host has not connected authenticated list, choose and receipt-read actions.';return;}
    if(!list){status.textContent=message;return;}
    for(const [index,p] of list.presets.entries()){
      const card=el('article');card.className='w29-preset-card';
      const label=el('label');const radio=el('input');radio.type='radio';radio.name='w29-quality-preset';radio.value=String(index);
      radio.checked=selected?.id===p.id&&selected?.profileRevision===p.profileRevision;
      radio.disabled=busy||!!pending||p.availability!=='available';
      radio.addEventListener('change',()=>{selected=p;accepted=false;message='Review these exact conditions and explicitly accept before selection.';render();});
      label.append(radio,el('strong',`${p.label} (${p.language==='en'?'English':'Spanish'})`));card.append(label);
      for(const line of conditionsText(p))card.append(el('p',line));
      cards.append(card);
    }
    if(selected&&selected.availability==='available'&&!pending){
      const consentLabel=el('label');const consent=el('input');consent.type='checkbox';consent.checked=accepted;consent.disabled=busy;
      consent.addEventListener('change',()=>{accepted=consent.checked;message=accepted?'Conditions accepted for this exact source and policy digest.':'Review and accept the current conditions to enable selection.';render();});
      consentLabel.append(consent,el('span',' I reviewed and accept the displayed conditions for this source and policy revision.'));controls.append(consentLabel);
      const choose=el('button','Choose this preset');choose.type='button';choose.disabled=busy||!accepted;
      choose.addEventListener('click',()=>chooseSelected());controls.append(choose);
    }
    if(pending){
      const notice=el('p','Selection result is unconfirmed. Do not submit again; read the original selection receipt.');notice.className='w29-preset-pending';cards.append(notice);
      const recover=el('button','Read original selection receipt');recover.type='button';recover.disabled=busy;
      recover.addEventListener('click',()=>recoverSelection());controls.append(recover);
    }
    status.textContent=message;
  }
  async function loadChoices(){
    if(busy||!callbacksReady())return;
    const captured={...host.scope},ref={...host.ref},ticket=++epoch;busy=true;message='Checking current policy and availability.';render();
    try{
      if(!sameRef(ref,host.ref)||!scopeNow(captured))throw Error('stale');
      const value=await host.listQualityPresets(ref,captured);
      if(destroyed||ticket!==epoch||!sameRef(ref,host.ref)||!scopeNow(captured))return;
      const next=normalizeList(value,ref);if(!next)throw Error('invalid listing');
      list=next;selected=null;accepted=false;message='Current choices loaded. Select an available preset to review its conditions.';
    }catch{if(ticket===epoch)message='Current choices could not be confirmed. Check current access and try the read again.';}
    finally{if(ticket===epoch&&!destroyed){busy=false;render();}}
  }
  async function chooseSelected(){
    if(busy||pending||!selected||!accepted||selected.availability!=='available'||!callbacksReady())return;
    const captured={...host.scope},ref={...host.ref},preset=selected,ticket=++epoch;
    if(!sameRef(ref,list?.ref)||!scopeNow(captured)){message='Source or access changed. Refresh current choices.';render();return;}
    const makeId=host.createRequestId;
    const requestId=typeof makeId==='function'?makeId():globalThis.crypto?.randomUUID?.();
    if(typeof requestId!=='string'||! /^[A-Za-z0-9._:-]{1,128}$/.test(requestId)){message='A fresh operation ID is unavailable; no selection was sent.';render();return;}
    const body={requestId,presetId:preset.id,expectedRevision:preset.profileRevision,ref,
      policyRevision:preset.conditions.policyRevision,conditionsDigest:preset.conditionsDigest,acceptConditions:true};
    pending=body;busy=true;accepted=false;message='Saving this explicit selection; delivery will not start.';render();
    try{
      if(!scopeNow(captured))throw Error('stale');
      const value=await host.chooseQualityPreset(body,captured);
      if(destroyed||ticket!==epoch||!scopeNow(captured)||!sameRef(ref,host.ref))return;
      const result=value?.selection??value;
      if(result?.requestId!==requestId||result?.profileId!==preset.id||result?.revision!==preset.profileRevision||
         result?.policyRevision!==body.policyRevision||result?.conditionsDigest!==body.conditionsDigest||!sameRef(result?.ref,ref))throw Error('selection not confirmed');
      pending=null;selected=null;list=null;message='Preset selection confirmed. Delivery has not started.';
      try{await host.refreshOperatingStatus?.(captured);}catch{}
    }catch(error){
      if(ticket===epoch&&!destroyed){
        if(['stale_conditions','preset_unavailable','stale_profile'].includes(error?.code)){
          pending=null;selected=null;accepted=false;list=null;
          message='Conditions changed or this option became unavailable. Review current choices and accept the updated conditions before selecting.';
        }else message='Selection result is unconfirmed. Do not submit again; read the original selection receipt.';
      }
    }finally{if(ticket===epoch&&!destroyed){busy=false;render();}}
  }
  async function recoverSelection(){
    if(busy||!pending||typeof host?.readQualityReceipt!=='function')return;
    const captured={...host.scope},expected=pending,ticket=++epoch;busy=true;message='Reading the original selection receipt.';render();
    try{
      if(!scopeNow(captured))throw Error('stale');
      const value=await host.readQualityReceipt(expected.requestId,captured);
      if(destroyed||ticket!==epoch||!scopeNow(captured)||!sameRef(expected.ref,host.ref))return;
      if(!validReceipt(value,expected))throw Error('receipt mismatch');
      pending=null;selected=null;accepted=false;list=null;message='Original selection receipt confirms this profile, source and accepted policy digest.';
      try{await host.refreshOperatingStatus?.(captured);}catch{}
    }catch{if(ticket===epoch&&!destroyed)message='The original selection receipt is unavailable or does not match. Selection remains unconfirmed; no new request was sent.';}
    finally{if(ticket===epoch&&!destroyed){busy=false;render();}}
  }
  function update(next={}){
    if(destroyed)return;
    const changed=host?.scope?.actorId!==next?.scope?.actorId||host?.scope?.sessionId!==next?.scope?.sessionId||
      host?.scope?.role!==next?.scope?.role||host?.scope?.scopeGeneration!==next?.scope?.scopeGeneration||!sameRef(host?.ref,next?.ref);
    const rightsChanged=host?.scope?.rightsGeneration!==next?.scope?.rightsGeneration;
    epoch++;busy=false;host=next;
    if(changed||rightsChanged){list=null;selected=null;accepted=false;pending=null;message='Source or access changed. Check current quality choices again.';}
    render();
  }
  function reset(){if(destroyed)return;epoch++;busy=false;list=null;selected=null;accepted=false;pending=null;message='Preset view cleared. Check current quality choices again.';render();}
  function destroy(){if(destroyed)return;destroyed=true;epoch++;section.remove();host=null;list=null;selected=null;pending=null;}
  render();return {update,reset,destroy};
}
