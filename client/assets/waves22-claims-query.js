import {mountClaims} from './waves22-claims.js';

// Query the authorized claim history; the server decides which citations remain eligible.
export function mountClaimsQuery(root, {identity, assertIdentity, query, mutate, openSource, selectedSource}) {
  const details = document.createElement('details');
  const summary = document.createElement('summary'); summary.textContent = 'Explore claim history'; details.append(summary);
  const form = document.createElement('form');
  const input = (label, type) => { const wrapper=document.createElement('label'); wrapper.textContent=label; const field=document.createElement('input'); field.type=type; field.required=true; wrapper.append(field); form.append(wrapper); return field; };
  const topic=input('Topic', 'text'); topic.maxLength=200;
  const eventTime=input('Event time', 'datetime-local');
  const knownAt=input('Known at', 'datetime-local');
  eventTime.step='any'; knownAt.step='any';
  const submit=document.createElement('button'); submit.type='submit'; submit.textContent='Find claims'; form.append(submit);
  const status=document.createElement('p'); status.setAttribute('role','status');
  const content=document.createElement('div'); details.append(form,status,content); root.append(details);
  let epoch=0, rightsTimer=null, displayed=null;
  const signature=result=>JSON.stringify([...(result.current||[]).map(x=>['current',x.id,x.revision,x.sourceRefs]),...(result.prior||[]).map(x=>['prior',x.id,x.revision,x.sourceRefs]),result.disputed,result.unknown]);
  const view=mountClaims(content,{scope:{},actions:{openSource:async ({scope,ref})=>{
    const generation=epoch, snapshot=displayed;
    if (!snapshot) throw Error('History changed');
    assertIdentity(scope);
    const result=await query(snapshot.query,scope);
    assertIdentity(scope);
    if (generation!==epoch) return;
    if (signature(result)!==snapshot.signature) { invalidate(); status.textContent='History or source access changed. Search again.'; return; }
    await openSource?.(ref,scope,()=>{assertIdentity(scope); if (generation!==epoch) throw Error('History changed');});
  }}});
  // A forget receipt contains no claim text. Keep its exact request until confirmed.
  async function forget(scope, item, generation) {
    if (!navigator.locks || !crypto?.randomUUID || !scope.actorBinding || !scope.sessionId) throw Error('Safe recovery unavailable');
    const key=`entrelineas.w22.forget.v1:${scope.sessionId}:${scope.actorBinding}`;
    await navigator.locks.request(`entrelineas.w22.claim-mutation:${scope.sessionId}:${scope.actorBinding}`, async () => {
      assertIdentity(scope);
      if (localStorage.getItem(`entrelineas.w22.correct.v1:${scope.sessionId}:${scope.actorBinding}`)) throw Error('A correction remains unconfirmed');
      if (localStorage.getItem(`entrelineas.w22.create.v1:${scope.sessionId}:${scope.actorBinding}`)) throw Error('A creation remains unconfirmed');
      let body;
      const saved=localStorage.getItem(key);
      if (saved) {
        body=JSON.parse(saved);
        if (body.action !== 'forget' || body.claimId !== item.id || body.expectedRevision !== item.revision || typeof body.requestId !== 'string') throw Error('Another action remains unconfirmed');
      } else {
        body={action:'forget',requestId:crypto.randomUUID(),expectedRevision:item.revision,claimId:item.id};
        localStorage.setItem(key,JSON.stringify(body));
      }
      assertIdentity(scope);
      if (generation !== epoch) return;
      const result=await mutate(body,scope);
      assertIdentity(scope);
      if (result?.operation?.state !== 'committed' || result.operation.requestId !== body.requestId || result.forgotten !== true) throw Error('Unconfirmed');
      if (localStorage.getItem(key) === JSON.stringify(body)) localStorage.removeItem(key);
      if (generation === epoch) { invalidate(); status.textContent='Private note forgotten. Search again to refresh history.'; }
    });
  }
  // Store only a fingerprint and request metadata; the user reconstructs the
  // same correction to recover an uncertain response without saving its text.
  async function correct(scope, item, changes, generation, isCurrent) {
    if (!navigator.locks || !crypto?.randomUUID || !crypto?.subtle || !scope.actorBinding || !scope.sessionId) throw Error('Safe recovery unavailable');
    const key=`entrelineas.w22.correct.v1:${scope.sessionId}:${scope.actorBinding}`;
    const payload={action:'correct',expectedRevision:item.revision,claimId:item.id,...changes};
    const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(payload)));
    const fingerprint=Array.from(new Uint8Array(bytes), b=>b.toString(16).padStart(2,'0')).join('');
    await navigator.locks.request(`entrelineas.w22.claim-mutation:${scope.sessionId}:${scope.actorBinding}`, async () => {
      assertIdentity(scope);
      if (localStorage.getItem(`entrelineas.w22.forget.v1:${scope.sessionId}:${scope.actorBinding}`)) throw Error('A forget action remains unconfirmed');
      if (localStorage.getItem(`entrelineas.w22.create.v1:${scope.sessionId}:${scope.actorBinding}`)) throw Error('A creation remains unconfirmed');
      if (generation !== epoch || !isCurrent()) throw Error('Correction changed');
      const saved=localStorage.getItem(key);
      let record;
      if (saved) {
        record=JSON.parse(saved);
        if (record.fingerprint !== fingerprint || record.claimId !== item.id || record.expectedRevision !== item.revision || typeof record.requestId !== 'string') throw Error('Another correction remains unconfirmed');
      } else {
        record={claimId:item.id,expectedRevision:item.revision,requestId:crypto.randomUUID(),fingerprint};
        localStorage.setItem(key,JSON.stringify(record));
      }
      assertIdentity(scope);
      if (generation !== epoch || !isCurrent()) throw Error('Correction changed');
      const result=await mutate({...payload,requestId:record.requestId},scope);
      assertIdentity(scope);
      if (result?.operation?.state !== 'committed' || result.operation.requestId !== record.requestId || result.claim?.id !== item.id) throw Error('Unconfirmed');
      if (localStorage.getItem(key) === JSON.stringify(record)) localStorage.removeItem(key);
      if (generation === epoch) { invalidate(); status.textContent='Private correction saved. Search again to refresh history.'; }
    });
  }
  const createForm=document.createElement('form');
  const createTitle=document.createElement('h3'); createTitle.textContent='Add a sourced claim'; createForm.append(createTitle);
  const createInput=(label,type)=>{const wrap=document.createElement('label'); wrap.textContent=label; const field=document.createElement('input'); field.type=type; wrap.append(field); createForm.append(wrap); return field;};
  const createTopic=createInput('Topic','text'); createTopic.required=true; createTopic.maxLength=200;
  const claimLabel=document.createElement('label'); claimLabel.textContent='Claim'; const claimText=document.createElement('textarea'); claimText.required=true; claimText.maxLength=4000; claimLabel.append(claimText); createForm.append(claimLabel);
  const from=createInput('Valid from','datetime-local'); from.required=true;
  const until=createInput('Valid until (optional)','datetime-local');
  const occurred=createInput('Event time','datetime-local'); occurred.required=true;
  const scopeLabel=document.createElement('label'); scopeLabel.textContent='Visibility'; const visibility=document.createElement('select');
  for (const [value,label] of [['private','Private'],['creator','Creator reviewed']]) {const option=document.createElement('option'); option.value=value; option.textContent=label; visibility.append(option);}
  scopeLabel.append(visibility); createForm.append(scopeLabel);
  const relationLabel=document.createElement('label'); relationLabel.textContent='Relationship to an existing claim'; const relationType=document.createElement('select');
  for (const [value,label] of [['','No relationship'],['supersedes','Supersedes'],['disputes','Disputes']]) {const option=document.createElement('option'); option.value=value; option.textContent=label; relationType.append(option);}
  relationLabel.append(relationType); createForm.append(relationLabel);
  const relationId=createInput('Related claim ID','text'); relationId.maxLength=128;
  const relationRevision=createInput('Related claim revision','number'); relationRevision.min='0'; relationRevision.step='1';
  const createHint=document.createElement('p'); createHint.textContent='Select an indexed caption in the listening controls before saving. To recover an unconfirmed save, enter the same values and select the same source again.'; createForm.append(createHint);
  const createButton=document.createElement('button'); createButton.type='submit'; createButton.textContent='Save sourced claim'; createForm.append(createButton); details.insertBefore(createForm,form);
  for (const field of [createTopic,claimText,from,until,occurred,visibility,relationType,relationId,relationRevision]) field.addEventListener('input',invalidate);
  createForm.addEventListener('submit',async event=>{
    event.preventDefault(); const scope=identity(), generation=epoch;
    try {
      assertIdentity(scope);
      if (!navigator.locks || !crypto?.randomUUID || !crypto?.subtle || !scope.sessionId || !scope.actorBinding) throw Error('Safe recovery unavailable');
      const ref=selectedSource?.(); const start=new Date(from.value), end=until.value ? new Date(until.value) : null, time=new Date(occurred.value);
      if (!ref || !createTopic.value.trim() || !claimText.value.trim() || !Number.isFinite(start.getTime()) || !Number.isFinite(time.getTime()) || (end && (!Number.isFinite(end.getTime()) || end<=start)) || (visibility.value==='creator' && scope.role!=='creator')) throw Error('Invalid input');
      const revision=relationRevision.value.trim();
      if (relationType.value ? (!relationId.value.trim() || !/^\d+$/.test(revision) || !Number.isSafeInteger(Number(revision))) : (relationId.value.trim() || revision)) throw Error('Invalid relationship');
      const relations=relationType.value ? [{type:relationType.value,claimId:relationId.value.trim(),revision:Number(revision)}] : [];
      const payload={action:'create',expectedRevision:0,scope:visibility.value,topic:createTopic.value.trim(),claim:claimText.value.trim(),sourceRefs:[ref],validFrom:start.toISOString(),validUntil:end ? end.toISOString() : null,eventTime:time.toISOString(),relations};
      const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(payload)));
      const fingerprint=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
      createButton.disabled=true;
      await navigator.locks.request(`entrelineas.w22.claim-mutation:${scope.sessionId}:${scope.actorBinding}`,async()=>{
        assertIdentity(scope); if (generation!==epoch || JSON.stringify(selectedSource?.())!==JSON.stringify(ref)) return;
        const key=`entrelineas.w22.create.v1:${scope.sessionId}:${scope.actorBinding}`;
        if (localStorage.getItem(`entrelineas.w22.correct.v1:${scope.sessionId}:${scope.actorBinding}`) || localStorage.getItem(`entrelineas.w22.forget.v1:${scope.sessionId}:${scope.actorBinding}`)) throw Error('Another action remains unconfirmed');
        const saved=localStorage.getItem(key); let record;
        if (saved) {record=JSON.parse(saved); if (record.fingerprint!==fingerprint || typeof record.requestId!=='string') throw Error('Another creation remains unconfirmed');}
        else {record={fingerprint,requestId:crypto.randomUUID()}; localStorage.setItem(key,JSON.stringify(record));}
        assertIdentity(scope); if (generation!==epoch || JSON.stringify(selectedSource?.())!==JSON.stringify(ref)) return;
        const result=await mutate({...payload,requestId:record.requestId},scope); assertIdentity(scope);
        if (result?.operation?.state!=='committed' || result.operation.requestId!==record.requestId || !result.claim?.id) throw Error('Unconfirmed');
        if (localStorage.getItem(key)===JSON.stringify(record)) localStorage.removeItem(key);
        if (generation===epoch) {createForm.reset(); invalidate(); status.textContent='Claim saved. Search the topic to review its history.';}
      });
    } catch {if (generation===epoch) status.textContent='Claim could not be confirmed. Check the selected source, access and times; if a save was attempted, re-enter the same values to recover it.';}
    finally {createButton.disabled=false;}
  });
  const recover=document.createElement('button'); recover.type='button'; recover.textContent='Check previous forget action'; form.append(recover);
  recover.addEventListener('click', async () => {
    const scope=identity(), generation=epoch;
    try {
      assertIdentity(scope);
      if (!scope.sessionId || !scope.actorBinding) throw Error();
      const key=`entrelineas.w22.forget.v1:${scope.sessionId}:${scope.actorBinding}`;
      const saved=JSON.parse(localStorage.getItem(key));
      if (!saved || saved.action !== 'forget' || typeof saved.claimId !== 'string' || !Number.isInteger(saved.expectedRevision) || typeof saved.requestId !== 'string') { status.textContent='No recoverable forget action is recorded for this access.'; return; }
      recover.disabled=true;
      await forget(scope,{id:saved.claimId,revision:saved.expectedRevision},generation);
    } catch { if(generation===epoch) status.textContent='The previous action remains unconfirmed. Check your access and try again.'; }
    finally { recover.disabled=false; }
  });
  function invalidate() { epoch++; clearInterval(rightsTimer); rightsTimer=null; displayed=null; view.reset(); content.querySelectorAll('.w22-forget-row').forEach(row=>row.remove()); status.textContent=''; }
  function reset() { invalidate(); topic.value=''; eventTime.value=''; knownAt.value=''; createForm.reset(); }
  // Do not restore private text from a back/forward or background-page snapshot.
  window.addEventListener('pagehide',reset);
  window.addEventListener('pageshow',event=>{if(event.persisted) reset();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden) reset();});
  details.addEventListener('toggle',()=>{if(!details.open) invalidate();});
  for (const field of [topic,eventTime,knownAt]) field.addEventListener('input',invalidate);
  form.addEventListener('submit', async event => {
    event.preventDefault(); invalidate(); const generation=epoch, scope=identity();
    const snapshot=[topic.value.trim(),eventTime.value,knownAt.value];
    const asOf=new Date(snapshot[1]), known=new Date(snapshot[2]);
    if (!snapshot[0] || !Number.isFinite(asOf.getTime()) || !Number.isFinite(known.getTime())) { status.textContent='Enter a topic and both times.'; return; }
    status.textContent='Loading current eligible history…';
    try {
      const request={topic:snapshot[0],asOfEventTime:asOf.toISOString(),knownAt:known.toISOString()};
      const result=await query(request,scope);
      assertIdentity(scope);
      if (generation!==epoch || snapshot[0]!==topic.value.trim() || snapshot[1]!==eventTime.value || snapshot[2]!==knownAt.value) return;
      if (!Array.isArray(result.current) || !Array.isArray(result.prior) || !Array.isArray(result.disputed)) throw Error('Invalid history');
      const disputed=new Set(result.disputed);
      const all=[...result.current,...result.prior];
      const explain=item=>{
        if (!item.priorReason) return '';
        const replacements=(item.replacedBy||[]).map(ref=>all.find(x=>x.id===ref.claimId && x.revision===ref.revision)).filter(Boolean);
        if(item.priorReason==='corrected') return `Earlier private interpretation; corrected by revision ${replacements[0]?.revision || 'unavailable'}.`;
        if(item.priorReason==='superseded') return replacements.length ? `Replaced by: ${replacements.map(x=>x.claim).join('; ')}` : 'Explicitly replaced. The replacement is unavailable under current source access; this earlier claim is not current.';
        return 'The validity interval ended; this claim is not current.';
      };
      const map=(item,state)=>({id:item.id,revision:item.revision,scope:item.scope,text:item.claim,status:state==='current'&&disputed.has(item.id)?'disputed':state,explanation:explain(item),eventTime:item.eventTime,validFrom:item.validFrom,validUntil:item.validUntil,recordedAt:item.recordedAt,relations:(item.relations||[]).map(r=>({kind:r.type,targetId:r.claimId,reviewed:true})),sources:(item.sourceRefs||[]).map(ref=>({available:true,title:`Source ${ref.sourceId || ''}, moment ${ref.momentId || ''}`,revision:ref.sourceRevision,ref}))});
      const claims=[...result.current.map(x=>map(x,'current')),...result.prior.map(x=>map(x,'prior'))];
      view.update({rightsState:'available',claims},scope,view.getGeneration());
      for (const item of result.current) {
        if (!item.id || !Number.isInteger(item.revision)) continue;
        const row=document.createElement('p'); row.className='w22-forget-row';
        row.textContent=`Relate a new claim to: ${item.claim} (revision ${item.revision}). `;
        for (const [type,label] of [['supersedes','Supersede'],['disputes','Dispute']]) {
          const button=document.createElement('button'); button.type='button'; button.textContent=label;
          button.addEventListener('click',()=>{
            if (generation!==epoch) return;
            try { assertIdentity(scope); } catch { return; }
            createTopic.value=snapshot[0]; relationType.value=type; relationId.value=item.id; relationRevision.value=String(item.revision);
            invalidate(); claimText.focus(); status.textContent='Relationship selected. Complete the new claim and select its source.';
          });
          row.append(button);
        }
        content.append(row);
      }
      for (const item of [...result.current,...result.prior]) {
        if (item.scope !== 'private' || !item.id || !Number.isInteger(item.revision) || typeof mutate !== 'function') continue;
        if (all.some(other=>other.id===item.id && other.revision>item.revision)) continue;
        const row=document.createElement('p'); row.className='w22-forget-row'; row.textContent=`Private note ${item.id}, revision ${item.revision}: `;
        const label=document.createElement('label'); label.textContent='Correct this private note';
        const correction=document.createElement('textarea'); correction.value=item.claim || ''; correction.maxLength=4000; label.append(correction); row.append(label);
        const timeField=(labelText,value)=>{const wrap=document.createElement('label'); wrap.textContent=labelText; const field=document.createElement('input'); field.type='text'; field.value=value || ''; field.placeholder='2026-10-31T12:00:00Z'; wrap.append(field); row.append(wrap); return field;};
        const validFrom=timeField('Valid from (timestamp with timezone)',item.validFrom);
        const validUntil=timeField('Valid until (optional, timestamp with timezone)',item.validUntil);
        const eventAt=timeField('Event time (timestamp with timezone)',item.eventTime);
        const sourceLabel=document.createElement('label'); const replaceSource=document.createElement('input'); replaceSource.type='checkbox'; sourceLabel.append(replaceSource,document.createTextNode(' Replace sources with the selected indexed caption')); row.append(sourceLabel);
        const save=document.createElement('button'); save.type='button'; save.textContent='Save private correction'; row.append(save);
        save.addEventListener('click', async () => {
          if (generation !== epoch) return;
          const text=correction.value.trim(), start=validFrom.value.trim(), end=validUntil.value.trim(), occurred=eventAt.value.trim();
          const timestamp=value=>/T.*(?:Z|[+-]\d\d:\d\d)$/i.test(value) && Number.isFinite(Date.parse(value));
          const replacement=replaceSource.checked ? selectedSource?.() : null;
          if (!text || !timestamp(start) || !timestamp(occurred) || (end && (!timestamp(end) || Date.parse(end)<=Date.parse(start))) || (replaceSource.checked && !replacement)) { status.textContent='Enter a correction and valid timestamps with timezones; select a caption if replacing sources.'; return; }
          const changes={claim:text,sourceRefs:replaceSource.checked ? [replacement] : item.sourceRefs,validFrom:start,validUntil:end || null,eventTime:occurred};
          const snapshot=JSON.stringify([correction.value.trim(),validFrom.value.trim(),validUntil.value.trim(),eventAt.value.trim(),replaceSource.checked,replacement]);
          save.disabled=true;
          try { await correct(scope,item,changes,generation,()=>JSON.stringify([correction.value.trim(),validFrom.value.trim(),validUntil.value.trim(),eventAt.value.trim(),replaceSource.checked,replaceSource.checked ? selectedSource?.() : null])===snapshot); }
          catch { if(generation===epoch) status.textContent='Correction unconfirmed or unavailable. Re-enter the same text for the same note and revision to retry the original request.'; }
          finally { if(generation===epoch) save.disabled=false; }
        });
        const button=document.createElement('button'); button.type='button'; button.textContent='Forget private note'; row.append(button); content.append(row);
        let confirmed=false;
        button.addEventListener('click', async () => {
          if (generation !== epoch) return;
          if (!confirmed) { confirmed=true; button.textContent='Confirm forgetting private note'; return; }
          button.disabled=true;
          try { await forget(scope,item,generation); }
          catch { if(generation===epoch) status.textContent='The action is unconfirmed or unavailable. Use the same note and revision to check it; no new action was sent.'; }
          finally { if(generation===epoch) button.disabled=false; }
        });
      }
      status.textContent=result.unknown?'Insufficient evidence for one undisputed current claim. Explicit disagreements remain unresolved.':'One current claim is available for these times. This is an evidence account, not a truth ranking.';
      displayed={query:request,signature:signature(result)};
      // Recheck only while history is displayed. Retain identifiers/revisions,
      // never claim text, in this access-check snapshot. No response is cached.
      let checking=false;
      rightsTimer=setInterval(async()=>{
        if(checking || generation!==epoch || !details.open || document.hidden) return;
        checking=true;
        try {
          const latest=await query(request,scope); assertIdentity(scope);
          if(generation===epoch && signature(latest)!==displayed?.signature) {invalidate(); status.textContent='History or source access changed. Search again.';}
        } catch {if(generation===epoch) {invalidate(); status.textContent='Current history access could not be confirmed. Search again.';}}
        finally {checking=false;}
      },5000);
    } catch { if (generation===epoch) {view.reset();status.textContent='History is unavailable. Check your access and try again.';} }
  });
  return {reset};
}
