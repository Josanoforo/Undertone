export function mountImpact(root, {actions = {}} = {}) {
  const box=document.createElement('section'); box.className='w21-impact';
  const heading=document.createElement('h2'); heading.textContent='Correction impact';
  const status=document.createElement('p');status.setAttribute('role','status');
  const content=document.createElement('div');box.append(heading,status,content);root.append(box);
  let generation=0,current=null,pending=null,destroyed=false;
  const el=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);return n;};
  function reset(){generation++;current=null;pending=null;content.replaceChildren();status.textContent='Correction details cleared.';}
  function update(p,ticket){
    if(destroyed||ticket!==generation)return false;
    reset();
    if(!p||p.rightsState!=='available'||!p.scopeKey){status.textContent='Correction details unavailable or access changed.';return false;}
    current=p;const epoch=generation;
    if(p.actorRole==='viewer'){
      content.append(el('p','Audio already heard cannot be recalled. A correction is optional.'));
      if(p.heardCorrection && typeof actions.playCorrection==='function'){const b=el('button','Play available correction');b.type='button';b.onclick=async()=>{try{await actions.playCorrection({projection:current,correction:p.heardCorrection});if(epoch===generation)status.textContent='Correction playback requested.';}catch{if(epoch===generation)status.textContent='Correction playback unavailable.';}};content.append(b);}else content.append(el('p','No correction audio is available.'));
      status.textContent='Your listening choice remains optional.';return true;
    }
    if(p.actorRole!=='creator'||!p.preview||p.preview.visibility==='private'||!p.preview.correctionId||!Number.isInteger(p.preview.expectedRevision)){status.textContent='A current creator impact preview is unavailable.';return false;}
    const view=p.preview;content.append(el('p','Review the effects before confirming. Already heard audio cannot be recalled; public replacements require fresh approval.'));
    const list=el('ul');const selected=[];
    for(const item of Array.isArray(view.items)?view.items:[]){const li=el('li');li.append(el('span',`${item.kind || 'Item'}: ${item.state || 'unknown'}${item.requiresApproval ? '; approval required' : ''}. `));if(item.id && item.replaceable===true){const label=el('label',' Include replacement');const c=el('input');c.type='checkbox';c.value=item.id;label.prepend(c);li.append(label);selected.push(c);}list.append(li);}content.append(list);
    if(Array.isArray(view.history)){const h=el('h3','History');content.append(h);const history=el('ul');for(const row of view.history){history.append(el('li',`${row.kind || 'Output'}: ${row.state || 'unknown'}${row.heard===true ? '; already heard' : ''}.`));}content.append(history);}
    const confirmLabel=el('label',' I confirm these replacements');const confirm=el('input');confirm.type='checkbox';confirmLabel.prepend(confirm);content.append(confirmLabel);
    const replace=el('button','Confirm replacement');replace.type='button';content.append(replace);
    const retry=el('button','Check or replay unconfirmed replacement');retry.type='button';retry.hidden=true;content.append(retry);
    const available=typeof actions.createRequest==='function'&&typeof actions.loadPending==='function'&&typeof actions.journal==='function'&&typeof actions.replace==='function'&&typeof actions.replay==='function';replace.disabled=true; retry.hidden=!available;
    status.textContent=available?'Check for an unconfirmed replacement before continuing.':'Replacement unavailable; durable request recovery is not connected.';
    function result(r){if(!r || r.state==='unknown' || r.state==='pending'){status.textContent='Replacement outcome is unconfirmed. Check or replay the same request.';retry.hidden=false;return;}if(r.state==='conflict'){status.textContent='The correction changed. Refresh the preview before acting.';}else if(r.state==='denied'){status.textContent='Replacement was denied.';}else if(r.state==='complete'){status.textContent='Replacement recorded. Review and approve any public replacement separately.';}else{status.textContent='Replacement is partially complete. Refresh the authoritative history.';}pending=null;retry.hidden=true;}
    replace.onclick=async()=>{if(epoch!==generation||pending)return;if(!confirm.checked){status.textContent='Confirm the replacement before continuing.';return;}const ids=selected.filter(x=>x.checked).map(x=>x.value);if(!ids.length){status.textContent='Choose at least one replacement.';return;}replace.disabled=true;try{const req=await actions.createRequest({projection:current,correctionId:view.correctionId,expectedRevision:view.expectedRevision,selectedIds:ids});if(epoch!==generation)return;if(!req||!req.requestId||req.expectedRevision!==view.expectedRevision){status.textContent='A stable replacement request is unavailable.';return;}pending=req;await actions.journal(req);if(epoch!==generation)return;status.textContent='Submitting replacement…';const r=await actions.replace(req);if(epoch===generation)result(r);}catch{if(epoch===generation){status.textContent=pending?'Replacement outcome is unconfirmed. Check or replay the same request.':'Replacement could not be prepared.';retry.hidden=!pending;}}finally{if(epoch===generation)replace.disabled=!!pending;}};
    retry.onclick=async()=>{if(epoch!==generation)return;retry.disabled=true;try{if(!pending)pending=await actions.loadPending({projection:current,correctionId:view.correctionId});if(epoch!==generation)return;if(!pending){status.textContent='No unconfirmed replacement. Review and confirm your selection.';retry.hidden=true;replace.disabled=false;return;}const r=await actions.replay(pending);if(epoch===generation)result(r);}catch{if(epoch===generation)status.textContent='Recovery unavailable. Replacement remains blocked.';}finally{if(epoch===generation){retry.disabled=false;if(pending)replace.disabled=true;}}};
    if(view.reapproval)content.append(el('p','A public replacement requires a fresh creator approval in the connected editor.'));
    return true;
  }
  return {update,reset,destroy(){reset();destroyed=true;box.remove();},getGeneration:()=>generation};
}
