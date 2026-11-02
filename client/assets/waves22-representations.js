// Creator approval is bound to an exact template version and current source moment.
export function mountModelApprovals(root, {identity, assertIdentity, templates, versions, search, list, approve, revoke}) {
  const box=document.createElement('details'), summary=document.createElement('summary'), status=document.createElement('p'), content=document.createElement('div');
  summary.textContent='Approve models for practice'; status.setAttribute('role','status'); status.setAttribute('aria-live','polite'); box.append(summary,status,content); root.append(box);
  let epoch=0;
  const key=s=>`entrelineas.w22.model-approval.v1:${s.sessionId}:${s.actorBinding}`;
  const el=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const button=(host,label,fn)=>{const b=el('button',label);b.type='button';b.onclick=fn;host.append(b);return b;};
  function reset(){epoch++;content.replaceChildren();status.textContent='';}
  async function fingerprint(value){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)));return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');}
  async function perform(s,ticket,action,body){
    try {
      if(!navigator.locks || !crypto?.subtle || !s.actorBinding)throw Error('recovery unavailable');
      await navigator.locks.request(key(s),async()=>{
        assertIdentity(s);if(ticket!==epoch)throw Error('view changed');
        const hash=await fingerprint(body);assertIdentity(s);if(ticket!==epoch)throw Error('view changed');
        const raw=localStorage.getItem(key(s));const pending=raw?JSON.parse(raw):null;
        if(pending && (pending.action!==action || pending.hash!==hash))throw Error('different pending action');
        const marker=pending || {action,hash,...(action==='revoke'?{approvalId:body.approvalId}:{})};if(!pending)localStorage.setItem(key(s),JSON.stringify(marker));
        const result=action==='approve'?await approve(body,s):await revoke(body.approvalId,s);assertIdentity(s);
        if(action==='approve' ? !result?.approvalId || JSON.stringify(result.definition)!==JSON.stringify(body.definition) : result?.approvalId!==body.approvalId || result?.state!=='withdrawn')throw Error('unconfirmed');
        if(localStorage.getItem(key(s))!==JSON.stringify(marker))throw Error('journal changed');
        localStorage.removeItem(key(s));if(ticket===epoch)status.textContent=action==='approve'?'Model approved. Refresh to see current approvals.':'Approval withdrawn. Refresh to see current approvals.';
      });
    }catch{if(ticket===epoch)status.textContent='Action unconfirmed or access changed. Re-enter the exact selection and retry; a different action is blocked.';}
  }
  button(box,'Refresh models and templates',async()=>{
    reset();const s=identity(),ticket=epoch;status.textContent='Checking current approvals and templates…';
    try{
      if(s.role!=='creator'||!s.token||!s.sessionId||!s.actorBinding)throw Error('access');
      assertIdentity(s);
      const [a,t]=await Promise.all([list(s),templates(s)]);assertIdentity(s);if(ticket!==epoch)return;
      if(!Array.isArray(a.approvals)||!Array.isArray(t.templates))throw Error('projection');
      const pending=localStorage.getItem(key(s));status.textContent=pending?'A previous action is unconfirmed. Re-enter its exact selection to retry.':'Select a template version and a current audience-visible source moment.';
      if(pending){const saved=JSON.parse(pending);if(saved.action==='revoke' && typeof saved.approvalId==='string')button(content,'Retry previous withdrawal',()=>perform(s,ticket,'revoke',{approvalId:saved.approvalId}));}
      const existing=el('section');existing.append(el('h3','Current approved models'));
      for(const item of a.approvals){if(typeof item.approvalId!=='string'||!item.definition)continue;const row=el('p',`${item.definition.kind} · template ${item.definition.templateId} · version ${item.definition.templateVersion} `);button(row,'Withdraw approval',()=>perform(s,ticket,'revoke',{approvalId:item.approvalId}));existing.append(row);}content.append(existing);
      const template=el('select'), version=el('select'), kind=el('select'), query=el('input'), found=el('div'), selected=el('p');let ref=null, searchGeneration=0;
      for(const [value,label] of [['RGB_LINEAR_MEAN_V1','Digital RGB weighted mean'],['RESOURCE_BUDGET_12_V1','Resource token allocation']]){const o=el('option',label);o.value=value;kind.append(o);}
      const blank=el('option','Choose a template');blank.value='';template.append(blank);
      for(const item of t.templates){if(typeof item.id!=='string')continue;const o=el('option',item.id);o.value=item.id;template.append(o);}
      template.setAttribute('aria-label','Template');version.setAttribute('aria-label','Template version');kind.setAttribute('aria-label','Model');query.setAttribute('aria-label','Search source moments');
      template.onchange=async()=>{version.replaceChildren();try{const id=template.value;if(!id)return;const data=await versions(id,s);assertIdentity(s);if(ticket!==epoch||template.value!==id)return;for(const v of data.versions||[]){if(!Number.isInteger(v.version))continue;const o=el('option',String(v.version));o.value=String(v.version);version.append(o);}}catch{if(ticket===epoch)status.textContent='Template versions are unavailable. Refresh and try again.';}};
      query.oninput=()=>{searchGeneration++;ref=null;found.replaceChildren();selected.textContent='';};
      content.append(template,version,kind,query);button(content,'Search source moments',async()=>{const generation=++searchGeneration;ref=null;selected.textContent='';found.replaceChildren();try{const data=await search(query.value.trim(),s);assertIdentity(s);if(ticket!==epoch||generation!==searchGeneration)return;for(const x of data.moments||[]){if(x.ref?.sessionId!==s.sessionId)continue;const row=el('p',x.text||'Source moment');button(row,'Select moment',()=>{assertIdentity(s);if(ticket!==epoch||generation!==searchGeneration)return;ref=x.ref;selected.textContent=`Selected ${ref.sourceId} / ${ref.momentId} / revision ${ref.sourceRevision}`;});found.append(row);}}catch{if(ticket===epoch&&generation===searchGeneration)status.textContent='Source search is unavailable. Refresh and try again.';}});content.append(found,selected);
      button(content,'Approve exact model',()=>{if(!ref||!template.value||!Number.isInteger(Number(version.value))||!version.value){status.textContent='Choose a template version and source moment.';return;}const spec=kind.value==='RGB_LINEAR_MEAN_V1'?{operation:'weighted_channel_mean_half_up',units:{channels:'integer channel levels',weights:'weight units'},ranges:{channel:[0,255],weight:[0,100]}}:{operation:'exact_fixed_sum',units:{allocation:'resource tokens'},ranges:{allocation:[0,12]},total:12};perform(s,ticket,'approve',{definition:{kind:kind.value,version:1,sourceRefs:[ref],templateId:template.value,templateVersion:Number(version.value),spec}});});
    }catch{if(ticket===epoch){content.replaceChildren();status.textContent='Approvals or templates are unavailable. Reconnect and refresh.';}}
  });
  return {reset};
}

// Owner-only withdrawal handles remain available even after source withdrawal.
export function mountModelWithdrawals(root, {identity, assertIdentity, list, mutate}) {
  const details=document.createElement('details'), summary=document.createElement('summary');
  summary.textContent='Your shared model results';
  const refresh=document.createElement('button'); refresh.type='button'; refresh.textContent='Refresh shared results';
  const status=document.createElement('p'); status.setAttribute('role','status'); status.setAttribute('aria-live','polite');
  const content=document.createElement('div'); details.append(summary,refresh,status,content); root.append(details);
  let epoch=0, busy=false;
  function reset(){epoch++;content.replaceChildren();status.textContent='';}
  const key=s=>`entrelineas.w22.model-revoke.v1:${s.sessionId}:${s.actorBinding}`;
  const valid=p=>p && p.action==='revoke' && typeof p.requestId==='string' && typeof p.modelId==='string' && typeof p.shareId==='string' && Number.isInteger(p.expectedRevision) && p.expectedRevision>=0;
  async function send(s, ticket, item) {
    if(busy || !navigator.locks || !crypto?.randomUUID || !s.actorBinding)return;
    busy=true;
    try {
      await navigator.locks.request(key(s),async()=>{
        assertIdentity(s); if(ticket!==epoch)return;
        let pending=JSON.parse(localStorage.getItem(key(s)) || 'null');
        if(pending && !valid(pending))throw Error('invalid journal');
        if(pending && item && (pending.modelId!==item.modelId || pending.shareId!==item.shareId || pending.expectedRevision!==item.revision))throw Error('another action pending');
        if(!pending){if(!item)return; pending={action:'revoke',requestId:crypto.randomUUID(),expectedRevision:item.revision,modelId:item.modelId,shareId:item.shareId}; localStorage.setItem(key(s),JSON.stringify(pending));}
        assertIdentity(s); if(ticket!==epoch)return;
        const result=await mutate(pending,s); assertIdentity(s);
        if(result?.operation?.state!=='committed' || result.operation.requestId!==pending.requestId || result.shareId!==pending.shareId)throw Error('unconfirmed');
        if(localStorage.getItem(key(s))!==JSON.stringify(pending))throw Error('journal changed');
        localStorage.removeItem(key(s));
        if(ticket===epoch){content.replaceChildren();status.textContent='Shared result withdrawn. Refresh to see remaining shares.';}
      });
    } catch {if(ticket===epoch)status.textContent='Withdrawal is unconfirmed. Refresh and retry the same action.';}
    finally {busy=false;}
  }
  refresh.onclick=async()=>{
    const s=identity(), ticket=++epoch; content.replaceChildren(); status.textContent='Checking your shared results…';
    try {
      if(s.role!=='viewer' || !s.sessionId || !s.token || !s.actorBinding)throw Error('access');
      assertIdentity(s);
      const pending=JSON.parse(localStorage.getItem(key(s)) || 'null');
      if(pending){if(!valid(pending))throw Error('journal'); const retry=document.createElement('button'); retry.type='button';retry.textContent='Retry previous withdrawal'; retry.onclick=()=>send(s,ticket,null);content.append(retry);status.textContent='A withdrawal is unconfirmed. Retry the same action before another change.';return;}
      const result=await list(s); assertIdentity(s); if(ticket!==epoch)return;
      if(!Array.isArray(result.shares))throw Error('projection');
      for(const item of result.shares){if(typeof item.modelId!=='string'||typeof item.shareId!=='string'||!Number.isInteger(item.revision)||item.revision<0||!Number.isInteger(item.sequence)||item.sequence<1)continue;
        const row=document.createElement('p');row.textContent=`Model ${item.modelId} · result ${item.sequence} · share ${item.shareId} `;
        const button=document.createElement('button');button.type='button';button.textContent='Withdraw this shared result';button.onclick=()=>send(s,ticket,item);row.append(button);content.append(row);
      }
      status.textContent=content.childElementCount?'Select a shared result to withdraw.':'No active shared model results.';
    } catch {if(ticket===epoch){content.replaceChildren();status.textContent='Shared results or recovery are unavailable. Reconnect and refresh.';}}
  };
  return {reset};
}

// Connect only server-approved definitions to the viewer's current private attempts.
export function mountModelExploration(root, {identity, assertIdentity, approvals, continuations, models, receipts, mutate, openSource}) {
  const details=document.createElement('details'), summary=document.createElement('summary'), refresh=document.createElement('button'), status=document.createElement('p'), choices=document.createElement('div'), view=document.createElement('div');
  summary.textContent='Explore an approved model'; refresh.type='button'; refresh.textContent='Find models for my attempts'; status.setAttribute('role','status'); status.setAttribute('aria-live','polite'); details.append(summary,refresh,status,choices,view); root.append(details);
  let epoch=0, component=null;
  const key=s=>`entrelineas.w22.model-action.v1:${s.sessionId}:${s.actorBinding}`;
  const scopeKey=s=>JSON.stringify([s.sessionId,s.actorBinding,s.epoch]);
  const canonical=value=>Array.isArray(value)?value.map(canonical):value && typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;
  function reset(){epoch++; component?.destroy(); component=null; choices.replaceChildren(); view.replaceChildren(); status.textContent='';}
  const valid=p=>p && typeof p.requestId==='string' && ['create','evaluate','share','revoke'].includes(p.action) && (p.modelId===null || typeof p.modelId==='string');
  function load(s){assertIdentity(s);const raw=localStorage.getItem(key(s)); if(!raw)return null; const p=JSON.parse(raw); if(!valid(p))throw Error('invalid journal'); return {...p,scopeKey:scopeKey(s)};}
  async function locked(s,fn){if(!navigator.locks || !s.actorBinding)throw Error('locking unavailable'); return navigator.locks.request(key(s),async()=>{assertIdentity(s); return fn();});}
  function mount(s, projection, pending, ticket){
    component?.destroy(); view.replaceChildren();
    component=mountRepresentations(view,{scope:s,pending,api:{mutate:({scope,body})=>{assertIdentity(scope);return mutate(body,scope);},recover:async ({scope,requestId,action,modelId})=>{const data=await receipts(scope);assertIdentity(scope);const found=data?.receipts?.find(r=>r.requestId===requestId && r.action===action && (modelId===null || r.modelId===modelId));return {status:found?'committed':'unknown'};}},actions:{
      runExclusive:locked,
      rememberPending:async op=>{assertIdentity(op.scope); if(localStorage.getItem(key(op.scope)))throw Error('action pending'); localStorage.setItem(key(op.scope),JSON.stringify({requestId:op.requestId,action:op.action,modelId:op.modelId}));},
      clearPending:async op=>{assertIdentity(op.scope);const p=load(op.scope);if(!p || p.requestId!==op.requestId || p.action!==op.action || p.modelId!==op.modelId)throw Error('journal changed');localStorage.removeItem(key(op.scope));},
      openSource:({scope,source})=>openSource(source,scope), refresh:()=>{if(ticket===epoch)refresh.click();}
    }});
    component.update(projection,s,component.getGeneration());
  }
  refresh.onclick=async()=>{reset(); const ticket=epoch,s=identity(); status.textContent='Checking approved models and your current attempts…';
    try {if(s.role!=='viewer' || !s.token || !s.sessionId || !s.actorBinding)throw Error('access'); const pending=load(s); if(pending){mount(s,null,pending,ticket);status.textContent='Check the previous model action first.';return;}
      const [a,c,m]=await Promise.all([approvals(s),continuations(s),models(s)]);assertIdentity(s);if(ticket!==epoch)return;
      if(!Array.isArray(a.approvals)||!Array.isArray(c.continuations)||!Array.isArray(m.models))throw Error('projection');
      let count=0;
      for(const item of a.approvals){const d=item.definition;if(!d || !Array.isArray(d.sourceRefs) || !d.sourceRefs.length)continue;
        for(const continuation of c.continuations){const source=continuation.source, revision=continuation.sourceVersion;if(continuation.state!=='current' || !source || !Number.isInteger(revision) || !d.sourceRefs.every(ref=>ref.sessionId===s.sessionId && ref.sourceId===source.id && ref.sourceRevision===revision))continue;
          for(const attempt of Array.isArray(continuation.newAttempts)?continuation.newAttempts:[]){if(typeof attempt.id!=='string'||!attempt.id)continue;count++;const b=document.createElement('button');b.type='button';b.textContent=`Explore ${d.kind==='RGB_LINEAR_MEAN_V1'?'digital RGB':'resource tokens'} with ${attempt.summary || attempt.text || 'this private attempt'}`;b.onclick=()=>{try{assertIdentity(s);if(ticket!==epoch)return;mount(s,{rightsState:'available',models:[{approved:true,definition:d,attemptId:attempt.id,source:{...source,revision,ref:d.sourceRefs[0]}}]},load(s),ticket);}catch{status.textContent='Access changed. Refresh to continue.';}};choices.append(b);
            for(const saved of m.models){if(saved.attemptId!==attempt.id || JSON.stringify(canonical(saved.definition))!==JSON.stringify(canonical(d)) || typeof saved.id!=='string' || !Number.isInteger(saved.revision))continue;
              const resume=document.createElement('button');resume.type='button';resume.textContent='Resume this private model';resume.onclick=()=>{try{assertIdentity(s);if(ticket!==epoch)return;mount(s,{rightsState:'available',models:[{approved:true,definition:d,attemptId:attempt.id,saved,source:{...source,revision,ref:d.sourceRefs[0]}}]},load(s),ticket);}catch{status.textContent='Access changed. Refresh to continue.';}};choices.append(resume);
            }
          }
        }
      }
      status.textContent=count?'Choose an approved model and your matching private attempt.':'No approved model matches a current private attempt.';
    }catch{if(ticket===epoch){choices.replaceChildren();status.textContent='Models or current practice are unavailable. Reconnect and refresh.';}}
  };
  return {reset};
}

// The host supplies current authorized projections and callbacks; no routes are constructed here.
export function mountRepresentations(root, {scope, api = {}, actions = {}, pending: initialPending = null}) {
  const box = document.createElement('section'); box.className = 'w22-representations';
  const heading = document.createElement('h2'); heading.textContent = 'Predict and explore';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const content = document.createElement('div'); box.append(heading, status, content); root.append(box);
  let epoch = 0, currentScope = scope, destroyed = false, pending = initialPending, busy = false;
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = String(text); return n; };
  const button = (parent, text, handler) => { const b = el('button', text); b.type = 'button'; b.addEventListener('click', handler); parent.append(b); return b; };
  const scopeKey = s => JSON.stringify([s?.sessionId,s?.actorBinding,s?.epoch]);
  function recovery() {
    content.replaceChildren(); status.textContent = 'An action is unconfirmed. Check it before another change.';
    button(content,'Check previous action',async () => {
      if (busy || !pending || pending.scopeKey !== scopeKey(currentScope) || typeof api.recover !== 'function' || typeof actions.clearPending !== 'function') return;
      const g=epoch, op=pending, s=currentScope; busy=true;
      try { const r=await actions.runExclusive(s, async () => {
        const receipt=await api.recover({scope:s,requestId:op.requestId,action:op.action,modelId:op.modelId});
        if(g!==epoch || op!==pending) return null;
        if(receipt?.status==='committed' || receipt?.status==='rejected') await actions.clearPending({...op,scope:s});
        return receipt;
      });
        if(g!==epoch || op!==pending) return;
        if(r?.status!=='committed' && r?.status!=='rejected') {status.textContent='The action remains unconfirmed.';return;}
        pending=null; content.replaceChildren(); status.textContent='Action resolved. Refresh current access.'; actions.refresh?.({scope:s});
      } catch {if(g===epoch) status.textContent='Recovery unavailable; the action remains unconfirmed.';} finally {if(g===epoch)busy=false;}
    });
  }
  async function mutate(body,g) {
    if(g!==epoch || pending || busy || !globalThis.crypto?.randomUUID || typeof api.mutate!=='function' || typeof api.recover!=='function' || typeof actions.rememberPending!=='function' || typeof actions.clearPending!=='function' || typeof actions.runExclusive!=='function') {status.textContent='Changes unavailable until safe recovery is connected.';return null;}
    const s=currentScope, op={requestId:globalThis.crypto.randomUUID(),action:body.action,modelId:body.modelId||null,scopeKey:scopeKey(s)}; pending=op; busy=true;
    try { return await actions.runExclusive(s, async () => { try { await actions.rememberPending({...op,scope:s}); } catch {if(g===epoch && pending===op){pending=null;status.textContent='Recovery could not be prepared. No change was sent.';}return null;}
      if(g!==epoch || pending!==op)return null;
      const r=await api.mutate({scope:s,body:{...body,requestId:op.requestId}});
      if(g!==epoch || pending!==op)return null;
      if(r?.operation?.state!=='committed' || r.operation.requestId!==op.requestId)throw Error();
      await actions.clearPending({...op,scope:s}); if(g!==epoch || pending!==op)return null; pending=null; return r; });
    } catch {if(g===epoch && pending===op)recovery();return null;} finally {if(g===epoch)busy=false;}
  }
  function reset() { epoch++; busy = false; content.replaceChildren(); status.textContent = ''; }
  function destroy() { reset(); destroyed = true; box.remove(); }
  function update(projection, nextScope = currentScope, ticket) {
    if (destroyed || ticket !== epoch) return false;
    reset(); currentScope = nextScope;
    if (pending) { recovery(); return true; }
    if (projection?.rightsState === 'withdrawn' && Array.isArray(projection.withdrawals)) {
      status.textContent = 'The source was withdrawn. You can withdraw your previously shared results.';
      const g=epoch;
      for(const item of projection.withdrawals) {
        if(!item.modelId || !item.shareId || !Number.isInteger(item.revision))continue;
        button(content,'Withdraw shared result',async()=>{const sent=await mutate({action:'revoke',expectedRevision:item.revision,modelId:item.modelId,shareId:item.shareId},g);if(!sent||g!==epoch)return;reset();status.textContent='Shared result withdrawn.';actions.refresh?.({scope:currentScope});});
      }
      return true;
    }
    if (!projection || projection.rightsState !== 'available' || !Array.isArray(projection.models)) {
      status.textContent = projection?.rightsState === 'withdrawn' ? 'The source was withdrawn.' : 'Current approved models or access are unavailable.'; return true;
    }
    const g = epoch;
    status.textContent = 'Choose values and make a prediction before revealing the result.';
    for (const model of projection.models) renderModel(model, g);
    return true;
  }
  function renderModel(model, g) {
    if (model.approved !== true || !['RGB_LINEAR_MEAN_V1', 'RESOURCE_BUDGET_12_V1'].includes(model.definition?.kind) || model.definition.version == null || !model.source || !model.attemptId) return;
    const definition=model.definition; let saved=model.saved || null;
    const rgb = definition.kind === 'RGB_LINEAR_MEAN_V1';
    const card = el('article'); card.append(el('h3', rgb ? 'Digital RGB weighted mean' : 'Allocate twelve resource tokens'));
    card.append(el('p', `Approved rule: ${model.rule || (rgb ? 'Weighted channel mean; halves round upward.' : 'A + B = 12; unused = 0.')} · version ${definition.version}; template revision ${definition.templateVersion}`));
    card.append(el('p', `Source: ${model.source.title || 'Source'} · revision ${model.source.revision ?? 'unavailable'}`));
    card.append(el('p', rgb ? 'Simplified digital channel arithmetic, not physical pigment or display light behavior.' : 'A toy allocation rule, not financial, staffing or optimization advice.'));
    if (typeof actions.openSource === 'function') button(card, 'Open current source', () => { if (g === epoch) actions.openSource({scope: currentScope, source: model.source}); });
    const fields = el('fieldset'); fields.append(el('legend', 'Parameters')); const grid = el('div'); grid.className = 'w22-fields'; fields.append(grid);
    const inputs = {};
    const number = (key, label, min, max, value, parent = grid) => {
      const wrap = el('label', `${label} (${min}–${max}, whole numbers)`); const input = el('input'); input.type = 'number'; input.min = String(min); input.max = String(max); input.step = '1'; input.value = String(value); wrap.append(input); parent.append(wrap); inputs[key] = input;
    };
    if (rgb) {
      for (const [key, label, value] of [['r1','First red channel',255],['g1','First green channel',0],['b1','First blue channel',0],['w1','First weight',1],['r2','Second red channel',0],['g2','Second green channel',0],['b2','Second blue channel',255],['w2','Second weight',1]]) number(key, label, 0, key[0] === 'w' ? 100 : 255, value);
    } else { fields.append(el('p', 'Total: 12 resource tokens. Both allocations must add to 12.')); number('a', 'Allocation A (tokens)', 0, 12, 0); number('b', 'Allocation B (tokens)', 0, 12, 0); }
    card.append(fields);
    const prediction = el('fieldset'); prediction.append(el('legend', rgb ? 'Your predicted result: integer channel levels' : 'Your predicted result: tokens in each allocation and unused'));
    const pred = {};
    for (const [key, label, max] of (rgb ? [['r','Red',255],['g','Green',255],['b','Blue',255]] : [['a','Allocation A',12],['b','Allocation B',12],['unused','Unused',12]])) {
      const wrap = el('label', `${label} (0–${max}, whole numbers)`); const input = el('input'); input.type = 'number'; input.min = '0'; input.max = String(max); input.step = '1'; input.value = ''; wrap.append(input); prediction.append(wrap); pred[key] = input;
    }
    card.append(prediction); const result = el('div'); card.append(result); let inputEpoch = 0, evaluating = false;
    const integer = (input, max) => { const raw = input.value.trim(); if (!/^\d+$/.test(raw)) return null; const n = Number(raw); return Number.isSafeInteger(n) && n <= max ? n : null; };
    const invalidate = () => { inputEpoch++; saved=null; result.replaceChildren(); status.textContent = 'Values changed. Make a prediction and reveal again.'; };
    for (const input of [...Object.values(inputs), ...Object.values(pred)]) input.addEventListener('input', invalidate);
    if (saved) {
      try {
        const guess=JSON.parse(saved.prediction), last=saved.events?.[saved.events.length-1]?.parameters;
        for(const [key,input] of Object.entries(pred)) if(Number.isInteger(guess[key])) input.value=String(guess[key]);
        if(last) {
          const values=rgb ? {r1:last.c1?.r,g1:last.c1?.g,b1:last.c1?.b,w1:last.w1,r2:last.c2?.r,g2:last.c2?.g,b2:last.c2?.b,w2:last.w2} : {a:last.a,b:last.b};
          for(const [key,input] of Object.entries(inputs)) if(Number.isInteger(values[key])) input.value=String(values[key]);
        }
        card.append(el('p', 'Resumed private prediction. Reveal the result again or change values to start a new prediction.'));
      } catch { saved=null; }
    }
    button(card, 'Reveal result', async () => {
      if (g !== epoch || evaluating) return; result.replaceChildren();
      const vals = {}; for (const [key, input] of Object.entries(inputs)) { vals[key] = integer(input, rgb && key[0] !== 'w' ? 255 : rgb ? 100 : 12); if (vals[key] === null) { status.textContent = 'Enter a whole number in each parameter range.'; input.focus(); return; } }
      const guess = {}; for (const [key, input] of Object.entries(pred)) { guess[key] = integer(input, rgb ? 255 : 12); if (guess[key] === null) { status.textContent = 'Enter a complete prediction within the stated ranges.'; input.focus(); return; } }
      if (rgb && vals.w1 + vals.w2 === 0) { status.textContent = 'Both weights cannot be zero. Increase at least one weight.'; return; }
      if (!rgb && vals.a + vals.b !== 12) { status.textContent = `The allocations add to ${vals.a + vals.b}; they must add to exactly 12. Adjust either value.`; return; }
      const parameters = rgb ? {c1:{r:vals.r1,g:vals.g1,b:vals.b1},w1:vals.w1,c2:{r:vals.r2,g:vals.g2,b:vals.b2},w2:vals.w2} : {total:12,a:vals.a,b:vals.b};
      const s=currentScope, requestInputEpoch=inputEpoch; evaluating=true;
      try {
        if (!saved) {
          status.textContent='Saving your private prediction…';
          const created=await mutate({action:'create',expectedRevision:0,definition,attemptId:model.attemptId,prediction:JSON.stringify(guess)},g);
          if(!created || g!==epoch)return; saved=created.model; if(requestInputEpoch!==inputEpoch){actions.refresh?.({scope:s});return;}
        }
        if(!saved?.id || !Number.isInteger(saved.revision)){status.textContent='Refresh the current model.';return;}
        status.textContent='Evaluating your private variant…';
        const response=await mutate({action:'evaluate',expectedRevision:saved.revision,modelId:saved.id,parameters},g);
        if(!response || g!==epoch)return; saved=response.model; if(requestInputEpoch!==inputEpoch){actions.refresh?.({scope:s});return;} const event=saved?.events?.[saved.events.length-1], output=event?.result;
        if(!output?.values || output.ruleVersion!==definition.kind || output.definitionVersion!==definition.version){status.textContent='Current result unavailable. Refresh.';return;}
        result.append(el('h4','Result from the current model'));
        const table=el('table'), head=el('tr'); for(const x of ['Measure','Your prediction','Result'])head.append(el('th',x));table.append(head);
        for(const key of Object.keys(guess)){const row=el('tr');row.append(el('th',key),el('td',guess[key]),el('td',output.values[key]??'Unavailable'));table.append(row);} result.append(table,el('p',output.explanation));
        if(rgb && ['r','g','b'].every(k=>Number.isInteger(output.values[k])&&output.values[k]>=0&&output.values[k]<=255)){const swatch=el('span');swatch.className='w22-swatch';swatch.style.backgroundColor=`rgb(${output.values.r}, ${output.values.g}, ${output.values.b})`;swatch.setAttribute('aria-hidden','true');result.append(swatch);}
        if(typeof actions.replay==='function')button(result,'Replay this source-linked event',()=>{if(g===epoch)actions.replay({scope:s,modelId:saved.id,sequence:event.sequence,source:model.source,definition});});
        const l=el('label','Share this selected result with the creator');const consent=el('input');consent.type='checkbox';l.append(consent);result.append(l);
        const il=el('label','Also share my identity');const identity=el('input');identity.type='checkbox';il.append(identity);result.append(il);
        button(result,'Share selected result',async()=>{if(!consent.checked){status.textContent='Select result sharing first; identity consent is separate.';return;}
          const sent=await mutate({action:'share',expectedRevision:saved.revision,modelId:saved.id,sequence:event.sequence,consent:true,identityConsent:identity.checked},g);
          if(!sent||g!==epoch)return; if(requestInputEpoch!==inputEpoch){actions.refresh?.({scope:s});return;} saved=sent.model;
          if(typeof sent.shareId!=='string' || !saved?.id || !Number.isInteger(saved.revision)){result.replaceChildren();status.textContent='Shared result recorded. Refresh your shared results to manage it.';return;}
          result.replaceChildren();result.append(el('p',`Result ${event.sequence} shared with the creator.`));
          button(result,'Withdraw this result',async()=>{const withdrawn=await mutate({action:'revoke',expectedRevision:saved.revision,modelId:saved.id,shareId:sent.shareId},g);if(!withdrawn||g!==epoch)return;result.replaceChildren();status.textContent='This result was withdrawn.';});
          status.textContent='Selected result shared. You can withdraw this result here.';});
        status.textContent='Result shown. Change values and predict again to retry.';
      } finally {evaluating=false;}

    });
    for(const item of model.shares || []) {if(!saved?.id || !item.id || item.active!==true)continue;
      const row=el('p',`Shared result ${item.sequence}. `);card.append(row);
      button(row,'Withdraw shared result',async()=>{const sent=await mutate({action:'revoke',expectedRevision:saved.revision,modelId:saved.id,shareId:item.id},g);if(!sent||g!==epoch)return;reset();status.textContent='Shared result withdrawn. Refresh current access.';actions.refresh?.({scope:currentScope});});
    }
    content.append(card);
  }
  return {update, reset, destroy, getGeneration: () => epoch};
}




