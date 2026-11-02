import {createReceiptJournal} from './waves19-20-receipts.js';

// Durable metadata recovery for the existing Wave29 quality UI. No second policy.
export function mountQualityChoice(root) {
  const section=document.createElement('section'),status=document.createElement('p'),recover=document.createElement('button');
  status.setAttribute('role','status');recover.type='button';recover.textContent='Check previous quality choice';section.append(recover,status);root.append(section);
  let host=null,epoch=0,busy=false;
  const check=(owner,ticket)=>{if(!owner||host!==owner||ticket!==epoch)throw Error('Selection changed');owner.check();};
  const targetFor=body=>JSON.stringify({quality29:2,profileId:body.presetId,profileRevision:body.expectedRevision,
    policyRevision:body.policyRevision,conditionsDigest:body.conditionsDigest,
    ref:Object.fromEntries(['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].map(key=>[key,body.ref[key]]))});
  const journal=createReceiptJournal('quality29',{
    call:async(_op,query)=>{const owner=host,ticket=epoch;check(owner,ticket);const value=await owner.invoke('w23ProfileOperation',null,query.requestId);check(owner,ticket);
      const expected=JSON.parse(query.target),op=value?.operation,result=op?.result;
      if(expected?.quality29!==2||expected.profileRevision!==query.revision||!Number.isSafeInteger(expected.policyRevision)||expected.policyRevision<1||typeof expected.conditionsDigest!=='string'||!expected.conditionsDigest||
        !owner.sameRef(expected.ref,owner.ref)||op?.requestId!==query.requestId||op.operation!=='profile.select'||op.state!=='complete'||result?.requestId!==query.requestId||
        result.profileId!==expected.profileId||result.revision!==expected.profileRevision||result.policyRevision!==expected.policyRevision||result.conditionsDigest!==expected.conditionsDigest||!owner.sameRef(result.ref,expected.ref))throw Error('Receipt unavailable');
      return {...query,status:'committed',qualityReceipt:value};},isReceiptReplaySafe:()=>false
  },scope=>{if(!host||host.scope!==scope)throw Error('Access changed');host.check();});
  recover.onclick=async()=>{const owner=host,ticket=epoch;if(busy||owner?.scope.role!=='creator')return;busy=true;recover.disabled=true;
    try{check(owner,ticket);const result=await journal.lookup(owner.scope,()=>check(owner,ticket));check(owner,ticket);status.textContent=result.status==='committed'?'Previous quality choice confirmed. Refresh operating status and restore the listening selection.':result.status==='none'?'No previous quality choice is pending.':'Previous choice remains unconfirmed. No new choice was sent.';}
    catch{if(host===owner&&ticket===epoch)status.textContent='The original choice remains unconfirmed. No retry was sent.';}
    finally{if(host===owner&&ticket===epoch){busy=false;recover.disabled=false;}}};
  function update(next=null){epoch++;host=next;busy=false;section.hidden=next?.scope.role!=='creator';recover.disabled=section.hidden;status.textContent='Open current operating status to review the existing quality presets. Selection never starts audio.';}
  function bindings(){const owner=host,ticket=epoch;if(owner?.scope.role!=='creator')return {};
    return {
      ref:owner.ref,createRequestId:()=>crypto.randomUUID(),
      listQualityPresets:async ref=>{check(owner,ticket);if(!owner.sameRef(ref,owner.ref))throw Error('Source changed');const pending=await journal.pending(owner.scope);check(owner,ticket);if(pending){status.textContent='A previous quality choice is unconfirmed. Check its original receipt before another selection.';throw Error('Unconfirmed original choice');}return owner.invoke('w29QualityList',{ref});},
      chooseQualityPreset:async body=>{check(owner,ticket);if(!owner.sameRef(body?.ref,owner.ref)||body.acceptConditions!==true)throw Error('Explicit source-bound consent required');
        let definitiveRejection=null;
        const result=await journal.mutate(owner.scope,'profile.select',body,targetFor(body),body.expectedRevision,async request=>{
          let value;
          try { value=await owner.invoke('w29QualityChoose',request); }
          catch(error) {
            check(owner,ticket);
            // These two mounted-authority codes occur before profiles.write.
            // Its post-commit final guard uses stale_context. Do not classify
            // stale_profile: current_selection can emit it after a commit.
            if(error?.status===409&&['stale_conditions','preset_unavailable'].includes(error.code)&&request.requestId===body.requestId&&targetFor(request)===targetFor(body)) {
              definitiveRejection=error;return {requestId:request.requestId,noncommit:true};
            }
            if(error?.code==='stale_profile') { const unknown=Error('Selection outcome requires its original receipt.');unknown.code='quality_choice_unconfirmed';throw unknown; }
            throw error;
          }
          check(owner,ticket);const selected=value?.selection;
          if(selected?.requestId!==body.requestId||selected.profileId!==body.presetId||selected.revision!==body.expectedRevision||selected.policyRevision!==body.policyRevision||selected.conditionsDigest!==body.conditionsDigest||!owner.sameRef(selected.ref,owner.ref))throw Error('Unconfirmed selection');return value;
        },false,()=>check(owner,ticket));
        if(definitiveRejection) { definitiveRejection.noncommit=true;throw definitiveRejection; }
        return result;},
      readQualityReceipt:async id=>{check(owner,ticket);const pending=await journal.pending(owner.scope);check(owner,ticket);
        if(!pending||pending.requestId!==id)throw Error('Original quality request changed');
        const receipt=await journal.lookup(owner.scope,()=>check(owner,ticket));check(owner,ticket);
        if(receipt.status!=='committed'||receipt.requestId!==id||!receipt.qualityReceipt)throw Error('Quality receipt unconfirmed');
        return receipt.qualityReceipt;}
    };
  }
  update();return {update,bindings};
}
