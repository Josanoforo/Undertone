// Private return: only recovery identifiers and the exact pending request are stored locally.
export function mountReturn(root, api, identityScope, assertIdentity, openMoment, openAction = null, canUseSavedRecovery = () => true) {
  const box = document.createElement('section'); box.className = 'p6-card w17-return';
  box.innerHTML = `<details><summary>Return since your last visit</summary><p>Save a private starting point, then ask what changed. Saving a new starting point is always your choice.</p><p data-checkpoint></p><button type="button" data-save>Save starting point now</button> <button type="button" data-refresh>Refresh current access</button><fieldset><legend>Optional private context</legend><label><input type="checkbox" data-opt> Include my own context in this recap</label><label>Your context <textarea data-context maxlength="1000" rows="3" disabled></textarea></label><button type="button" data-clear>Clear unsent text</button> <button type="button" data-clear-saved disabled>Clear saved private context</button><p>Only text you enter here is included. It is private to you and is not shared.</p></fieldset><button type="button" data-recap>Show what changed</button><p role="status" aria-live="polite" data-status></p><div data-recovery hidden><p>A previous request has an unconfirmed outcome.</p><button type="button" data-check>Check request status</button> <button type="button" data-retry>Retry the same request</button></div><div data-result></div></details>`;
  root.append(box);
  const q = s => box.querySelector(s), result = q('[data-result]'), status = q('[data-status]');
  let generation = 0, busy = false, scope = null, checkpoint = null, current = null;
  const valid = s => !!(canUseSavedRecovery() && s?.token && s.role === 'viewer' && s.sessionId && s.actorBinding);
  const key = s => `w17-return:${encodeURIComponent(s.sessionId)}:${encodeURIComponent(s.actorBinding)}`;
  // An unreadable or malformed journal may contain an unresolved request.
  // Treat only a genuinely absent entry as empty; never overwrite an unknown one.
  const read = s => {
    assertIdentity(s); if (!valid(s)) throw Error('saved access required');
    const raw = localStorage.getItem(key(s));
    if (raw === null) return {};
    const value = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('invalid return journal');
    return value;
  };
  const write = (s, x) => { assertIdentity(s); if (!valid(s)) throw Error('saved access required'); try { localStorage.setItem(key(s), JSON.stringify(x)); return true; } catch { return false; } };
  const guard = (s, g) => { assertIdentity(s); if (!valid(s) || generation !== g) throw Error('stale'); };
  const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text; return n; };
  const clear = () => { current = null; result.replaceChildren(); };
  const pending = s => read(s).pending;
  async function locked(s, action) {
    if (!valid(s) || !navigator.locks?.request) throw Error('safe return recovery unavailable');
    return navigator.locks.request(key(s), async () => {
      assertIdentity(s);
      if (!valid(s)) throw Error('saved access required');
      return action();
    });
  }
  function lockFailure() {
    status.textContent = 'Saved return recovery is unavailable. The existing request was preserved; restore access before continuing.';
    q('[data-save]').disabled = q('[data-recap]').disabled = q('[data-clear-saved]').disabled = true;
  }
  function controls(s) {
    let p;
    try { p = valid(s) && pending(s); }
    catch {
      q('[data-recovery]').hidden = true;
      q('[data-clear-saved]').disabled = q('[data-save]').disabled = q('[data-recap]').disabled = true;
      status.textContent = 'Saved return recovery is unavailable. The existing request was preserved; restore access before continuing.';
      return;
    }
    q('[data-recovery]').hidden = !p;
    q('[data-clear-saved]').disabled = !!p || busy || !current?.privateContext; q('[data-save]').disabled = !!p || busy; q('[data-recap]').disabled = !!p || busy || !checkpoint;
    q('[data-checkpoint]').textContent = checkpoint ? `Starting point saved ${checkpoint.createdAt || ''}.` : 'No starting point saved in this browser.';
  }
  function reset() { generation++; busy = false; scope = null; checkpoint = null; clear(); q('[data-context]').value = ''; q('[data-opt]').checked = false; q('[data-context]').disabled = true; q('[data-recovery]').hidden = true; q('[data-checkpoint]').textContent = ''; status.textContent = ''; }
  function show(s, g, data) {
    clear(); if (!data || !Array.isArray(data.changes)) throw Error('invalid projection'); current = data;
    if (Array.isArray(data.account) && data.account.length) { const intro=node('p','Since your starting point:'); result.append(intro); const list=node('ul',''); for (const item of data.account) { const li=node('li',String(item.text || '')); addAction(li,item.nextAction,s,g,data.id); list.append(li); } result.append(list); if(data.accountTruncated) result.append(node('p','More changes are listed below.')); }
    if (data.noMeaningfulChange) result.append(node('p', 'No meaningful changes were found in the covered material.'));
    else if (!data.changes.length) result.append(node('p', 'No available changes could be shown. Check the coverage information below.'));
    for (const change of data.changes) {
      const row = node('article', ''); row.className = 'w17-return-change';
      row.append(node('h4', String(change.kind || 'Change').replaceAll('_', ' ')), node('p', String(change.excerpt || '')));
      const citations = Array.isArray(change.citations) ? change.citations : change.citation ? [change.citation] : [];
      if (change.question) row.append(node('p', `Question: ${change.question}`)); if (change.outcome) row.append(node('p', `Consequence: ${change.outcome}`));
      for (const opinion of Array.isArray(change.participantOpinions) ? change.participantOpinions : []) row.append(node('p', `Participant opinion${opinion.minority ? ' (minority)' : ''}: ${opinion.excerpt || ''}`));
      if(change.opinionsTruncated) row.append(node('p','Additional participant opinions are not shown.'));
      addAction(row,change.nextAction,s,g,data.id);
      if (!citations.length) row.append(node('p','No source reference was supplied for this change.'));
      for (const citation of citations) { row.append(node('p', `Source: ${citation.title || 'Current source'} ${citation.at || ''}`));
      const ref = citation.ref;
      if (ref) { const b = node('button', 'Open current source'); b.type = 'button'; b.onclick = async () => {
        try { guard(s,g); clear(); status.textContent = 'Checking source access…'; const fresh = await api.call('w17Return', null, data.id, {scope:s}); guard(s,g);
          const found = fresh.return?.changes?.some(c => (Array.isArray(c.citations) ? c.citations : c.citation ? [c.citation] : []).some(citation => JSON.stringify(citation.ref) === JSON.stringify(ref)));
          show(s,g,fresh.return); if (!found) { status.textContent = 'This source has changed or is no longer available.'; return; }
          status.textContent = 'Current source access checked.'; await openMoment(ref,s); guard(s,g);
        } catch { if (generation === g) { clear(); status.textContent = 'Current source access could not be confirmed. Refresh to try again.'; } }
      }; row.append(b); } }
      result.append(row);
    }
    if(data.nextAction){const next=node('p','Next action: ');addAction(next,data.nextAction,s,g,data.id);result.append(next);}
    const c = data.coverage || {}; const coverage = node('p', '');
    const gaps = ['unavailable','baselineUnavailable','baselineInputsUnavailable','changedInputsUnavailable','unreferencedInputs'].filter(k => Number(c[k]) > 0);
    coverage.textContent = [typeof c.scope === 'string' ? c.scope : 'Coverage reflects the currently available indexed material.', c.truncated ? 'Some changes were omitted by a coverage limit.' : '', gaps.length ? `Some inputs are unavailable or unreferenced (${gaps.map(k => `${k}: ${c[k]}`).join(', ')}).` : ''].filter(Boolean).join(' ');
    result.append(coverage); for (const limitation of Array.isArray(data.limitations) ? data.limitations : []) result.append(node('p', String(limitation)));
    if (data.privateContext) result.append(node('p', `Your private context: ${data.privateContext}`));
  }
  function addAction(parent, action, s, g, id) {
    if (!action || !['open_source','open_chapter','open_format'].includes(action.type)) return;
    if (action.type==='open_source' ? !action.ref || !openMoment : !action.id || !openAction) return;
    const target=structuredClone(action), b=node('button',action.type==='open_source'?'Open current source':action.type==='open_chapter'?'Open chapter':'Open choice or question');
    b.type='button'; b.onclick=async()=>{try {
      guard(s,g); clear(); status.textContent='Checking current access…';
      const fresh=await api.call('w17Return',null,id,{scope:s}); guard(s,g);
      const projection=fresh.return;
      const actions=[projection?.nextAction,...(projection?.account || []).map(x=>x.nextAction),...(projection?.changes || []).map(x=>x.nextAction)];
      const found=actions.some(x=>JSON.stringify(x)===JSON.stringify(target));
      show(s,g,projection);
      if(!found){status.textContent='This item has changed or is no longer available.';return;}
      if(target.type==='open_source') await openMoment(target.ref,s); else await openAction(target,s);
      guard(s,g); status.textContent='Current access checked.';
    }catch{if(generation===g){clear();status.textContent='This item or current access could not be confirmed.';}}};
    parent.append(b);
  }
  async function reconcileClear(s,g,sendPatch) {
    if(busy)return; busy=true; controls(s); clear(); status.textContent='Checking saved context…';
    try {
      const p=pending(s); if(!p || p.kind!=='clear')return;
      const readback=await api.call('w17Return',null,p.id,{scope:s}); guard(s,g);
      let projection=readback.return;
      if(!projection || projection.id!==p.id || !Number.isInteger(projection.revision))throw Error('projection');
      if(projection.privateContext!==null && sendPatch){
        const patched=await api.call('w17PatchReturn',{revision:projection.revision,privateContext:null},p.id,{scope:s}); guard(s,g);
        projection=patched.return;
        if(!projection || projection.id!==p.id || projection.privateContext!==null)throw Error('projection');
      }
      show(s,g,projection);
      if(projection.privateContext===null){const saved=read(s);delete saved.pending;if(!write(s,saved))throw Error('storage');status.textContent='Saved private context cleared.';}
      else status.textContent='Saved context is still present. Retry clearing it.';
    }catch{if(generation===g){clear();status.textContent='The clear outcome is unconfirmed. Check current access before retrying.';}}
    finally{if(generation===g){busy=false;controls(s);}}
  }
  async function refreshUnlocked() {
    const s = identityScope(), g = ++generation; scope = null; checkpoint = null; clear(); q('[data-context]').value = ''; q('[data-opt]').checked = false; q('[data-context]').disabled = true;
    if (!valid(s)) { controls(null); status.textContent = canUseSavedRecovery() ? 'Join as a viewer to use your private return.' : 'Private return requires saved access to protect request recovery.'; return; }
    try { guard(s,g); scope=s; const saved=read(s); status.textContent='Checking current access…'; busy=true; controls(s);
      if (saved.checkpointId) { const r=await api.call('w17ReturnCheckpoint',null,saved.checkpointId,{scope:s}); guard(s,g); checkpoint=r.checkpoint; if (!checkpoint?.id || !Number.isInteger(checkpoint.revision)) throw Error('checkpoint'); }
      if (saved.returnId) { const r=await api.call('w17Return',null,saved.returnId,{scope:s}); guard(s,g); show(s,g,r.return); }
      if(saved.pending?.kind==='clear' && current?.id===saved.pending.id && current.privateContext===null){delete saved.pending;if(!write(s,saved))throw Error('storage');}
      status.textContent=saved.pending ? 'A previous request is unconfirmed. Check its status or retry the same request.' : 'Current access checked.';
    } catch { if(generation===g) { checkpoint=null; clear(); status.textContent='Current access could not be confirmed. Refresh to try again.'; } }
    finally { if(generation===g) { busy=false; controls(s); } }
  }
  async function refresh() {
    const s = identityScope();
    if (!valid(s)) return refreshUnlocked();
    try { return await locked(s, refreshUnlocked); } catch { lockFailure(); }
  }
  function finish(s,g,p,r) {
    guard(s,g); const saved=read(s);
    if (p.kind==='checkpoint') { if (!r.checkpoint?.id || !Number.isInteger(r.checkpoint.revision)) throw Error('receipt'); checkpoint=r.checkpoint; saved.checkpointId=checkpoint.id; delete saved.returnId; clear(); }
    else { if (!r.return?.id || !Array.isArray(r.return.changes)) throw Error('receipt'); saved.returnId=r.return.id; show(s,g,r.return); }
    delete saved.pending; if (!write(s,saved)) { clear(); throw Error('storage'); }
    q('[data-context]').value=''; q('[data-opt]').checked=false; q('[data-context]').disabled=true; controls(s); status.textContent=p.kind==='checkpoint'?'Starting point saved. It will not advance automatically.':'Your private recap is ready.';
  }
  async function send(s,g,p) {
    if (busy) return; if(p.kind==='clear'){await reconcileClear(s,g,true);return;} busy=true; controls(s); clear(); status.textContent='Sending your request…';
    try { const r = await api.call(p.kind==='checkpoint'?'w17CreateReturnCheckpoint':'w17CreateReturn',p.body,{scope:s}); guard(s,g); finish(s,g,p,r); }
    catch(e) { if(generation===g) { clear(); status.textContent=e?.code==='request_conflict'?'This request conflicts with an existing request. Its outcome needs review; no new write was assumed.':e?.code==='version_conflict'||e?.code==='stale_context'?'The starting point or sources changed. The request remains unconfirmed; check its status.':'The outcome is unconfirmed. Check its status or retry the same request.'; } }
    finally { if(generation===g) {busy=false;controls(s);} }
  }
  async function start(kind) {
    const s=identityScope(), g=generation; try { guard(s,g); if (!scope || pending(s) || busy) return; } catch {reset();status.textContent='Saved return recovery is unavailable. The existing request was preserved; restore access before continuing.';return;}
    const text=q('[data-context]').value.trim(); if(kind==='return' && q('[data-opt]').checked && (!text || text.length>1000)) {status.textContent='Enter 1–1000 characters of your own context, or turn off the option.';q('[data-context]').focus();return;}
    const requestId=crypto.randomUUID(), body=kind==='checkpoint'?{requestId}:{requestId,checkpointId:checkpoint.id,checkpointRevision:checkpoint.revision,privateContext:q('[data-opt]').checked?text:null};
    const p={kind,body}, saved=read(s); saved.pending=p; if(!write(s,saved)){status.textContent='Recovery information could not be saved, so the request was not sent.';return;} await send(s,g,p);
  }
  q('[data-save]').onclick=()=>locked(identityScope(),()=>start('checkpoint')).catch(lockFailure); q('[data-recap]').onclick=()=>locked(identityScope(),()=>start('return')).catch(lockFailure); q('[data-refresh]').onclick=refresh;
  q('[data-opt]').onchange=()=>{q('[data-context]').disabled=!q('[data-opt]').checked;}; q('[data-clear]').onclick=()=>{q('[data-context]').value='';q('[data-context]').focus();};
  q('[data-clear-saved]').onclick=()=>{const s=identityScope(),g=generation;return locked(s,async()=>{guard(s,g);if(busy||pending(s)||!current?.id||!current.privateContext)return;const saved=read(s);saved.pending={kind:'clear',id:current.id};if(!write(s,saved)){status.textContent='Recovery information could not be saved, so the context was not cleared.';return;}await reconcileClear(s,g,true);}).catch(lockFailure);};
  q('[data-retry]').onclick=()=>{const s=identityScope(),g=generation;return locked(s,async()=>{guard(s,g);const p=pending(s);if(p)await send(s,g,p);}).catch(lockFailure);};
  q('[data-check]').onclick=()=>{const s=identityScope(),g=generation;return locked(s,async()=>{guard(s,g);const p=pending(s);if(!p||busy)return;if(p.kind==='clear'){await reconcileClear(s,g,false);return;}try{busy=true;controls(s);clear();status.textContent='Checking request status…';const r=await api.call('w17ReturnOperation',null,p.body.requestId,{scope:s});guard(s,g);if(r.state==='unknown'){status.textContent='The outcome is still unknown. You can retry the same request.';return;}if(r.state!=='committed')throw Error('receipt');finish(s,g,p,r);}catch{if(generation===g){clear();status.textContent='The outcome or current access could not be confirmed.';}}finally{if(generation===g){busy=false;controls(s);}}}).catch(lockFailure);};
  return {refresh, reset};
}


