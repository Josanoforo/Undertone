// Read-only choices from the existing actor-authorized visual-association route.
export function mountVisualAssociations(root, {owner, sameRef, changed}) {
  const label=document.createElement('label');label.textContent='Visual reference for this fragment ';
  const select=document.createElement('select');label.append(select);
  const load=document.createElement('button');load.type='button';load.textContent='Load eligible visual references';
  const status=document.createElement('p');status.setAttribute('role','status');root.append(label,load,status);
  let epoch=0,bound=null,items=[];
  function reset(){epoch++;bound=null;items=[];select.replaceChildren(new Option('Source only',''));load.disabled=!owner();status.textContent='Only existing visual associations readable with your current access can be selected.';}
  select.addEventListener('change',()=>{changed();status.textContent=select.value?'Visual reference selected. Inspect to recheck its exact revision and rights.':'Source-only inspection selected.';});
  load.addEventListener('click',async()=>{
    const current=owner(),ticket=++epoch;if(!current)return;
    bound=null;items=[];select.replaceChildren(new Option('Source only',''));changed();load.disabled=true;status.textContent='Checking eligible visual references…';
    try{
      await current.current();const data=await current.invoke('w26VisualAssociations',{ref:current.ref});await current.current();
      if(owner()!==current||ticket!==epoch||!sameRef(data.ref,current.ref)||!Array.isArray(data.items)||data.coverage!=='bounded_current_actor_readable_only')throw Error('Selection changed');
      items=data.items.map(item=>{
        if(!item||typeof item.associationId!=='string'||!/^[A-Za-z0-9._:-]{1,128}$/.test(item.associationId)||!Number.isSafeInteger(item.revision)||item.revision<1||!sameRef(item.asrRef,current.ref)||!item.frameRef||typeof item.regionId!=='string'||typeof item.description!=='string')throw Error('Invalid visual reference');
        return item;
      });
      bound=current;
      for(const item of items)select.append(new Option(`${item.regionId} · ${item.frameRef.startMs} ms · source revision ${item.frameRef.sourceRevision} · ${item.description.slice(0,120)}`,item.associationId));
      status.textContent=items.length?'Choose a visual reference, then inspect. Descriptions may be uncertain.':'No eligible visual reference in this bounded selection. Source-only inspection remains available.';
    }catch{if(owner()===current&&ticket===epoch)status.textContent='Visual references are unavailable or access changed. No generation or sharing was started.';}
    finally{if(owner()===current&&ticket===epoch)load.disabled=false;}
  });
  select.append(new Option('Source only',''));load.disabled=true;
  return {reset,selected(){if(!select.value)return null;if(bound!==owner())throw Error('Visual scope changed');const item=items.find(item=>item.associationId===select.value);if(!item)throw Error('Visual selection changed');return item;}};
}
