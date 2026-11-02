const eligible = m => m && ['approved','published'].includes(m.status) && m.dependencyState === 'current' && Number.isInteger(m.currentVersion) && m.requiresReview === false && (!Object.hasOwn(m, 'approvedVersion') || m.approvedVersion === m.currentVersion);

// Cues are deliberately separate from the editable Studio so refreshing them never removes a draft.
export function mountCues(root, api, identityScope, assertIdentity) {
  root.innerHTML = `<details><summary>Reviewed production cues</summary><p>Prepare, edit, preview and approve an exact version in Source-connected creator materials above. Refresh here after any change. Only the creator may choose and present a cue.</p><p>Browser Source is a local page. An OBS connection and a Twitch broadcast are separate; this panel does not start a broadcast.</p><button type="button" data-refresh>Refresh cues and eligibility</button><p role="status" aria-live="polite" data-status></p><p data-transport>OBS connection: not checked.</p><div data-recovery hidden><p>An earlier cue request has an unknown outcome. Check its receipt before deciding whether to replay the exact request.</p><button type="button" data-check>Check request receipt</button><button type="button" data-replay disabled>Replay exact request</button></div><div data-controls hidden><label>Approved current material <select data-material></select></label><button type="button" data-create>Prepare cue</button><div data-list></div></div><div data-receipt aria-live="polite"></div></details>`;
  const q = s => root.querySelector(s), status = q('[data-status]'); status.tabIndex = -1;
  let generation = 0, busy = false, scope = null, materials = [], cues = [], pending = null, storageKey = null, mayReplay = false, mayWithdraw = false;
  const clear = () => { materials=[]; cues=[]; q('[data-controls]').hidden=true; q('[data-list]').replaceChildren(); q('[data-material]').replaceChildren(); q('[data-receipt]').replaceChildren(); q('[data-transport]').textContent='OBS connection: not checked.'; };
  const invalidate = () => { generation++; busy=false; clear(); status.textContent='Source or identity changed. Refresh cues before acting.'; };
  const reset = () => { invalidate(); scope=null; pending=null; storageKey=null; mayReplay=false; q('[data-recovery]').hidden=true; q('[data-replay]').disabled=true; root.querySelector('details').open=false; };
  const guard = (s,g) => { assertIdentity(s); if (generation !== g) throw Error('stale'); };
  async function keyFor(s) {
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(`${s.sessionId}\0${s.token}`));
    return 'w15-cue-pending:' + Array.from(new Uint8Array(bytes), b=>b.toString(16).padStart(2,'0')).join('');
  }
  function restore() { const raw=localStorage.getItem(storageKey); pending=raw ? JSON.parse(raw) : null; mayReplay=false; mayWithdraw=false; recovery(); }
  function recovery() { q('[data-recovery]').hidden=!pending; q('[data-replay]').disabled=!pending || !mayReplay || busy; q('[data-create]').disabled=!!pending || busy; }
  function describeTransport(t) {
    const state=typeof t?.state==='string' ? t.state : 'unknown';
    const destination=typeof t?.destination==='string' ? ` · destination: ${t.destination}` : '';
    q('[data-transport]').textContent=`OBS connection: ${state}${destination}. A local Browser Source page alone is not an OBS render or Twitch broadcast.`;
  }
  async function showReceipt(result, current, s, g) {
    const target=q('[data-receipt]'); target.replaceChildren();
    const t=result?.transport, proof=t?.proof;
    if (!proof || !current || t.cueId!==current.id || t.materialId!==current.materialId || t.materialVersion!==current.materialVersion) return;
    if (t.state==='presented' && (!current.eligible || !materials.some(m=>m.id===current.materialId && m.currentVersion===current.materialVersion))) return;
    if (!['presented','withdrawn'].includes(t.state) || proof.enabled !== (t.state==='presented') || !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(proof.imageData || '') || !/^[a-f0-9]{64}$/.test(proof.pngSha256 || '')) return;
    try {
      const raw=atob(proof.imageData.slice('data:image/png;base64,'.length)), bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
      if (bytes.length<8 || ![137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v)) return;
      const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      guard(s,g); if(hash!==proof.pngSha256) return;
      const p=document.createElement('p');
      p.textContent=`Local OBS ${t.state} · material ${t.materialId} · version ${t.materialVersion} · cue ${t.cueId} · scene ${proof.scene} · input ${proof.input} · item ${proof.sceneItemId} · enabled ${proof.enabled} · PNG SHA-256 ${hash} · public JSON SHA-256 ${t.publicJsonSha256 || 'not applicable'} · pinned URL ${proof.url || 'unavailable'}`;
      const img=document.createElement('img'); img.src=proof.imageData; img.alt=`OBS Program frame after ${t.state}, material version ${t.materialVersion}`; img.style.maxWidth='100%'; target.append(p,img);
    } catch { /* Invalid or stale proof is never displayed. */ }
  }
  async function load(s,g) {
    const [m,c]=await Promise.all([api.call('p10StudioMaterials',null,{scope:s}),api.call('w15Cues',null,{scope:s})]); guard(s,g);
    if(!Array.isArray(m.materials)||!Array.isArray(c.cues)) throw Error('invalid response');
    materials=m.materials.filter(eligible); cues=c.cues; describeTransport(c.transport); render(); q('[data-controls]').hidden=false;
  }
  async function refresh() {
    if(busy)return; const s=identityScope(),g=++generation; clear(); q('[data-recovery]').hidden=true;
    if(s.role!=='creator'||!s.token||!s.sessionId){status.textContent='Join as creator to manage cues.';return;}
    busy=true; status.textContent='Checking current approvals and cues…';
    try { const k=await keyFor(s); guard(s,g); scope=s; storageKey=k; restore(); await load(s,g); status.textContent=pending?'Request outcome unresolved. Check its receipt.':'Current cue and approval state loaded.'; }
    catch { if(g===generation){clear();status.textContent='Cue state unavailable. Refresh before acting.';} }
    finally {if(g===generation){busy=false;render();recovery();}}
  }
  async function send(held,s,g) {
    return held.cueId ? api.call('w15CueAction',held.body,held.cueId,{scope:s}) : api.call('w15CueCreate',held.body,{scope:s});
  }
  async function mutate(cueId, body) {
    if(busy||!scope||(pending&&!(mayWithdraw&&body.action==='withdraw'&&cueId===pending.cueId)))return; const prior=pending; const s=scope,g=++generation; busy=true; clear(); status.textContent=body.action==='present'?'Presenting in local OBS. This may take more than 12 seconds; please wait…':'Checking current approval and cue…'; status.focus();
    try {
      guard(s,g); await load(s,g);
      if(cueId){const c=cues.find(x=>x.id===cueId); if(!c||c._revision!==body.revision||c.status==='withdrawn'||(body.action!=='withdraw'&&(!c.eligible||!materials.some(m=>m.id===c.materialId&&m.currentVersion===c.materialVersion)))) throw Error('changed');}
      else if(!materials.some(m=>m.id===body.materialId&&m.currentVersion===body.materialVersion)) throw Error('changed');
      const held={cueId,body:{...body,idempotencyKey:crypto.randomUUID()},...(prior?{previous:prior}:{})};
      localStorage.setItem(storageKey,JSON.stringify(held)); pending=held; recovery();
      const result=await send(held,s,g); guard(s,g);
      if(result?.operation?.state !== 'committed') throw Error('unconfirmed');
      localStorage.removeItem(storageKey); pending=null; await load(s,g); await showReceipt(result,cues.find(c=>c.id===result?.cue?.id),s,g);
      status.textContent='Cue request confirmed. Review the current state below.';
    } catch(e) {if(g===generation){clear(); status.textContent=pending?'Request outcome unknown. Check the receipt; no new request was sent.':'Current approval or cue could not be confirmed. Refresh before acting.';}}
    finally {if(g===generation){busy=false;render();recovery();}}
  }
  async function check() {
    if(busy||!pending||!scope)return; const s=scope,g=++generation; busy=true; clear(); mayReplay=false; recovery();
    try {const r=await api.call('w15CueOperation',null,pending.body.idempotencyKey,{scope:s});guard(s,g);
      if(r?.operation?.state==='committed'){localStorage.removeItem(storageKey);pending=null;await load(s,g);await showReceipt(r,cues.find(c=>c.id===r.operation.cueId),s,g);status.textContent='The earlier request was confirmed. Current state is shown below.';}
      else if(r?.operation?.state==='unknown'){mayReplay=true; mayWithdraw=pending.body.action==='present' && !!pending.cueId; await load(s,g); status.textContent=mayWithdraw?'Present is unconfirmed. Replay the exact request or withdraw this same cue using its current revision.':'The server has no confirmed receipt. You may explicitly replay the exact request with the same key.';}
      else throw Error('invalid receipt');
    }catch{if(g===generation)status.textContent='Receipt unavailable. The request remains unresolved; no duplicate was sent.';}
    finally{if(g===generation){busy=false;render();recovery();}}
  }
  async function replay() {
    if(busy||!pending||!mayReplay||!scope)return; const s=scope,g=++generation,held=pending; busy=true;mayReplay=false;clear();recovery();
    try{const result=await send(held,s,g);guard(s,g);if(result?.operation?.state !== 'committed') throw Error('unconfirmed');localStorage.removeItem(storageKey);pending=null;await load(s,g);await showReceipt(result,cues.find(c=>c.id===result?.cue?.id),s,g);status.textContent='Exact request confirmed. Current state is shown below.';}
    catch{if(g===generation)status.textContent='Replay outcome remains unknown. Check the receipt again before any further action.';}
    finally{if(g===generation){busy=false;render();recovery();}}
  }
  function render() {
    const select=q('[data-material]'); select.replaceChildren(new Option('Choose approved material…',''));
    for(const m of materials)select.add(new Option(`${m.title||'Material'} · version ${m.currentVersion}`,m.id));
    const list=q('[data-list]');list.replaceChildren();
    for(const c of cues){const row=document.createElement('article'),line=document.createElement('p'),m=materials.find(x=>x.id===c.materialId&&x.currentVersion===c.materialVersion),current=c.eligible===true&&!!m;
      line.textContent=`${m?.title||'Material unavailable'} · version ${c.materialVersion} · ${c.status} · ${current?'current and approved':'approval or source no longer current'}`;row.append(line);
      if(c.status!=='withdrawn') for(const action of ['present','defer','withdraw']){const b=document.createElement('button');b.type='button';b.textContent=action[0].toUpperCase()+action.slice(1);b.disabled=busy||(!!pending&&!(mayWithdraw&&action==='withdraw'&&c.id===pending.cueId))||(action!=='withdraw'&&!current);b.onclick=()=>mutate(c.id,{action,revision:c._revision});row.append(b);}
      list.append(row);
    }
  }
  q('[data-refresh]').onclick=refresh; q('[data-check]').onclick=check; q('[data-replay]').onclick=replay;
  q('[data-create]').onclick=()=>{const m=materials.find(x=>x.id===q('[data-material]').value);if(m)mutate(null,{materialId:m.id,materialVersion:m.currentVersion});else status.textContent='Choose an approved current material.';};
  return {invalidate,reset};
}
