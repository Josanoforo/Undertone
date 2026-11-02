// Chapter recovery stores author text and reference identifiers, never capabilities or source text.
export function mountChapters(root, api, identityScope, assertIdentity, expectedRole, openMoment) {
  const box = document.createElement('section'); box.className = 'p6-card';
  box.innerHTML = `<details><summary>Chapters and indexed search</summary><p>Creator-authored chapters and lexical matches cover only indexed, currently available moments.</p><button type="button" data-chapters>Refresh chapters</button><label>Search indexed moments <input type="search" maxlength="200" data-query></label><button type="button" data-search>Search</button><p role="status" data-status></p><div data-recovery hidden><button type="button" data-check>Check chapter write status</button><button type="button" data-retry>Retry the exact saved request</button></div><div data-result></div><div data-list></div><div data-matches></div><div data-author hidden><label>Chapter title <input maxlength="160" data-title></label><p>Select one or more search results to create a chapter.</p><button type="button" data-create>Create chapter</button></div></details>`;
  root.append(box);
  const q = x => box.querySelector(x), status = q('[data-status]');
  let generation = 0, alive = true, busy = false, matches = [], selected = new Map(), chapters = [], captured = null, edits = {};
  const pendingKey = s => `w15-chapter-pending:${s.sessionId}`;
  const draftKey = s => `w15-chapter-draft:${s.sessionId}:${s.actorBinding}`;
  const owner = s => !!(s.token && s.sessionId && s.role === 'creator' && s.actorBinding);
  const guard = (s,g) => { if (!alive || generation !== g || s.role !== expectedRole) throw Error('stale'); assertIdentity(s); };
  const current = (s,g) => { try { guard(s,g); return true; } catch { return false; } };
  const read = (s,g,key) => { guard(s,g); try { const value = localStorage.getItem(key); return value === null ? null : JSON.parse(value); } catch { return {invalid:true}; } };
  const put = (s,g,key,value) => { guard(s,g); try { localStorage.setItem(key, JSON.stringify(value)); return true; } catch { return false; } };
  const pending = (s,g) => s.sessionId ? read(s,g,pendingKey(s)) : null;
  const mine = (p, s) => owner(s) && p && p.version === 2 && p.sessionId === s.sessionId && p.actorBinding === s.actorBinding && ['create','patch'].includes(p.kind) && p.body && p.body.idempotencyKey === p.key;
  const clearPending = (s,g,p) => { guard(s,g); try { const key=pendingKey(s), raw=localStorage.getItem(key); if (raw !== JSON.stringify(p)) return false; guard(s,g); localStorage.removeItem(key); return true; } catch { return false; } };
  const validRef = (r,s) => r && r.sessionId === s.sessionId && typeof r.sourceId === 'string' && Number.isInteger(r.sourceRevision) && typeof r.momentId === 'string' && Number.isInteger(r.startMs) && Number.isInteger(r.endMs);
  const saveDraft = (s,g) => owner(s) && put(s,g,draftKey(s), {title:q('[data-title]').value, refs:[...selected.values()], edits});
  const restoreDraft = (s,g) => { guard(s,g); if (!owner(s)) return; const d=read(s,g,draftKey(s)); if (!d || d.invalid) return; q('[data-title]').value = typeof d.title === 'string' ? d.title : ''; selected = new Map((Array.isArray(d.refs)?d.refs:[]).filter(r=>validRef(r,s)).map(r=>[JSON.stringify(r),r])); edits = d.edits && typeof d.edits === 'object' ? d.edits : {}; };
  const clearProjection = () => { matches=[]; chapters=[]; captured=null; q('[data-list]').replaceChildren(); q('[data-matches]').replaceChildren(); q('[data-result]').replaceChildren(); q('[data-author]').hidden=true; };
  const recovery = (s,g) => { const p=pending(s,g); q('[data-recovery]').hidden = !(expectedRole === 'creator' && mine(p,s)); if (p && expectedRole === 'creator') status.textContent = mine(p,s) ? 'A chapter write is unconfirmed. Check its status or retry the exact saved request.' : 'A chapter write belongs to another identity or an older recovery format. Reconnect with the original creator; new writes remain blocked.'; return p; };
  const reset = () => { if (!alive) return; generation++; busy=false; clearProjection(); selected.clear(); edits={}; q('[data-title]').value=''; status.textContent=''; q('[data-recovery]').hidden=true; box.querySelector('details').open=false; bind(); };
  const el = (tag,text='') => { const n=document.createElement(tag); n.textContent=text; return n; };
  function render(s,g) {
    const list=q('[data-list]'); list.replaceChildren();
    if (!chapters.length) list.append(el('p','No available chapters were returned.'));
    for (const chapter of chapters) {
      if (typeof chapter.title !== 'string' || !Array.isArray(chapter.refs) || !chapter.refs.every(r=>validRef(r,s))) continue;
      const section=el('section'); section.dataset.chapterId=chapter.id;section.tabIndex=-1; section.append(el('h3',chapter.title));
      for (const ref of chapter.refs) { section.append(el('p',`Source ${ref.sourceId} · revision ${ref.sourceRevision} · ${ref.startMs}–${ref.endMs} ms · moment ${ref.momentId}`)); if (s.role === 'viewer') { const b=el('button','Open source'); b.type='button'; b.onclick=()=>{if(current(s,g))openMoment(ref,s);}; section.append(b); } }
      if (owner(s) && typeof chapter.id === 'string' && Number.isInteger(chapter._revision)) {
        const label=el('label','Edit chapter title '), input=document.createElement('input'); input.maxLength=160; input.value=edits[chapter.id] ?? chapter.title; input.oninput=()=>{if(!current(s,g))return;edits[chapter.id]=input.value; saveDraft(s,g);}; label.append(input); section.append(label);
        const save=el('button','Save chapter revision'); save.type='button'; save.disabled=!!pending(s,g); save.onclick=()=>{if(current(s,g))start(s,g,'patch',chapter.id,{title:input.value.trim(),refs:selected.size?[...selected.values()]:chapter.refs,revision:chapter._revision});};
        section.append(el('p','Save keeps the current moments unless search results are selected.'),save);
      } list.append(section);
    }
    const out=q('[data-matches]'); out.replaceChildren();
    for (const item of matches) { if (!validRef(item?.ref,s) || typeof item.text !== 'string') continue; const row=el('article'), ref=item.ref; row.append(el('p',`Source ${ref.sourceId} · revision ${ref.sourceRevision} · ${ref.startMs}–${ref.endMs} ms`),el('p',item.text));
      if (owner(s)) { const label=el('label',' Include this moment'), checkbox=document.createElement('input'), key=JSON.stringify(ref); checkbox.type='checkbox'; checkbox.checked=selected.has(key); checkbox.onchange=()=>{if(!current(s,g))return;checkbox.checked?selected.set(key,ref):selected.delete(key);saveDraft(s,g);}; label.prepend(checkbox); row.append(label); }
      else { const b=el('button','Open source'); b.type='button'; b.onclick=()=>{if(current(s,g))openMoment(ref,s);}; row.append(b); } out.append(row);
    } q('[data-author]').hidden=!owner(s); q('[data-create]').disabled=!!pending(s,g);
  }
  async function load(kind,s,ticket) {
    if (!current(s,ticket) || busy) return; const g=++generation; bind(); clearProjection(); selected.clear(); edits={}; q('[data-title]').value='';
    if (!s.token || s.role !== expectedRole) { status.textContent=`Join as ${expectedRole} to continue.`; return; }
    restoreDraft(s,g); recovery(s,g); const query=q('[data-query]').value.trim(); if (kind==='search' && !query) {status.textContent='Enter a search query.';return;}
    busy=true; status.textContent='Checking current access…';
    try { guard(s,g); const [c,m]=await Promise.all([api.call('w15Chapters',null,{scope:s}),kind==='search'?api.call('w15Search',null,query,{scope:s}):Promise.resolve({moments:[]})]); guard(s,g); if (!Array.isArray(c.chapters)||!Array.isArray(m.moments)) throw Error(); chapters=c.chapters; matches=m.moments; captured=s; render(s,g); if (!recovery(s,g)) status.textContent=kind==='search'?`${matches.length} indexed match(es) returned; other moments may be outside the search limit.`:'Current chapters loaded.'; }
    catch {if(current(s,g)){clearProjection();status.textContent='Chapters or search are unavailable. Refresh to check access.';}} finally {if(current(s,g))busy=false;}
  }
  async function start(s,g,kind,target,body) {
    if (!current(s,g)) return;
    if (busy || !captured || pending(s,g)) {recovery(s,g);return;}
    if (!body.title || !body.refs.length || body.refs.length>20) {status.textContent='Enter a title and select 1–20 current moments.';return;}
    guard(s,g);
    body.idempotencyKey=crypto.randomUUID(); const p={version:2,sessionId:s.sessionId,actorBinding:s.actorBinding,kind,target,body,key:body.idempotencyKey};
    if (!saveDraft(s,g) || !put(s,g,pendingKey(s),p)) {status.textContent='This browser could not save recovery information. The chapter was not sent.';return;}
    await send(s,p,g);
  }
  async function send(s,p,g) {
    if (!current(s,g) || busy || !mine(p,s)) return; busy=true; status.textContent='Saving chapter…';
    try { guard(s,g); const result=p.kind==='create'?await api.call('w15CreateChapter',p.body,{scope:s}):await api.call('w15EditChapter',p.body,p.target,{scope:s}); guard(s,g); finish(s,g,p,result); }
    catch {if(current(s,g)){clearProjection();recovery(s,g);status.textContent='The chapter write is unconfirmed. Check status or retry the exact saved request.';}}
    finally {if(current(s,g))busy=false;}
  }
  function finish(s,g,p,result) {
    guard(s,g);
    const op=result?.operation; if (!op || op.state!=='committed' || op.kind!==p.kind || !op.chapterId || !Number.isInteger(op.committedRevision) || (p.kind==='patch' && op.chapterId!==p.target)) throw Error('invalid receipt');
    const recoveryHadFocus = q('[data-recovery]').contains(document.activeElement); if (!clearPending(s,g,p)) throw Error('storage'); clearProjection(); q('[data-recovery]').hidden=true; if (recoveryHadFocus) box.querySelector('summary').focus();
    if (op.eligible && result.chapter && result.chapter.id===op.chapterId && result.chapter._revision===op.currentRevision && Array.isArray(result.chapter.refs) && result.chapter.refs.every(r=>validRef(r,s))) { q('[data-result]').append(el('p',`Current chapter: ${result.chapter.title} · revision ${op.currentRevision}`)); }
    if (p.kind==='create') q('[data-title]').value=''; else delete edits[p.target]; selected.clear(); saveDraft(s,g);
    status.textContent=!op.eligible?'The write was saved, but the chapter or its sources are no longer available.':op.currentRevision!==op.committedRevision?'The write was saved. The chapter has since changed; the current result is shown when available.':'The chapter write was saved. Current access was checked.';
  }
  function bind() {
  const s=identityScope(), g=generation;
  q('[data-title]').oninput=()=>{if(current(s,g))saveDraft(s,g);};
  q('[data-chapters]').onclick=()=>load('chapters',s,g); q('[data-search]').onclick=()=>load('search',s,g);
  q('[data-create]').onclick=()=>{if(current(s,g)&&captured)start(s,g,'create',null,{title:q('[data-title]').value.trim(),refs:[...selected.values()]});};
  q('[data-retry]').onclick=()=>{if(!current(s,g))return;const p=pending(s,g); if(mine(p,s))send(s,p,g);};
  q('[data-check]').onclick=async()=>{if(!current(s,g))return;const p=pending(s,g); if(busy||!mine(p,s))return; busy=true;status.textContent='Checking the chapter write…';
    try {const result=await api.call('w15ChapterOperation',null,p.key,{scope:s});guard(s,g);const op=result?.operation;if(op?.state==='unknown'){status.textContent='The outcome is still unknown. You may retry only the exact saved request.';return;} if(op?.state!=='committed'||op.kind!==p.kind||!op.chapterId||!Number.isInteger(op.committedRevision)||(p.kind==='patch'&&op.chapterId!==p.target))throw Error();
      // The receipt has no content. An explicit exact replay returns a rights-checked current chapter.
      status.textContent=!op.eligible?'The write was saved, but the chapter or its sources are no longer available. Retry the exact request to finish recovery.':op.currentRevision!==op.committedRevision?'The write was saved and the chapter has since changed. Retry the exact request to see the current version.':'The write was saved. Retry the exact request to show the current chapter and finish recovery.';
    } catch {if(current(s,g)){clearProjection();recovery(s,g);status.textContent='Could not confirm the write or current access. Recovery remains pending.';}} finally {if(current(s,g))busy=false;}
  };
  }
  const invalidate=()=>{if(!alive)return;generation++;busy=false;clearProjection();selected.clear();edits={};q('[data-title]').value='';q('[data-recovery]').hidden=true;status.textContent='Source access changed or could not be confirmed. Refresh before acting.';bind();};
  async function focusChapter(id){const s=identityScope(), ticket=generation;guard(s,ticket);box.querySelector('details').open=true;await load('chapters',s,ticket);guard(s,ticket+1);const item=[...q('[data-list]').children].find(x=>x.dataset.chapterId===id);if(!item)throw Error('Chapter unavailable');item.focus();item.scrollIntoView?.({block:'nearest'});}
  const destroy=()=>{if(!alive)return;reset();alive=false;generation++;box.remove();};
  bind();
  // Call after the host has installed a new identity, not before changing it.
  return {reset,invalidate,activate:reset,focusChapter,destroy};
}
