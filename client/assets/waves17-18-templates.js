export function mountTemplates(root, api, identityScope, assertIdentity, onRoundOpened = () => {}, callbacks = {}) {
  const box = document.createElement('section'); box.className = 'w17-templates';
  box.innerHTML = '<details><summary>Reusable choices and boards</summary><p>Definitions are separate from responses and permissions. Participation and withdrawal use the existing choices and boards controls.</p><button type="button" data-refresh>Refresh templates and rounds</button><p role="status" aria-live="polite" data-status></p><div data-recovery hidden><p>A saved action has an unknown outcome. Only the exact original request can be replayed with the same identity. A conflict may mean the result has changed; do not create a replacement blindly.</p><button type="button" data-replay>Replay exact saved action</button></div><div data-content></div></details>';
  root.append(box);
  const q = x => box.querySelector(x), status = q('[data-status]'), content = q('[data-content]');
  const resetPolicy = {responses:'reset', identities:'reset', consents:'reset', decision:'reset', sources:'explicit'};
  const stages = ['open','contribute','review','decide','reveal','close'];
  let generation = 0, scope = null, busy = false;
  const el = (tag, text = '') => { const n = document.createElement(tag); n.textContent = text; return n; };
  const button = (parent, text, fn) => { const b = el('button', text); b.type = 'button'; b.onclick = fn; parent.append(b); return b; };
  const field = (parent, label, value = '', multi = false) => { const l = el('label', label + ' '), i = el(multi ? 'textarea' : 'input'); i.value = value; l.append(i); parent.append(l); return i; };
  const guard = (s,g) => { assertIdentity(s); if (g !== generation) throw Error('stale'); };
  const keyFor = s => `w17-template-pending:${s.sessionId}`;
  const pending = s => { assertIdentity(s); try { const p = localStorage.getItem(keyFor(s)); return p ? JSON.parse(p) : null; } catch { return {invalid:true}; } };
  const mine = (p,s) => !!(s.token && s.actorBinding && p?.version === 1 && p.sessionId === s.sessionId && p.actorBinding === s.actorBinding && p.method === 'POST' && typeof p.operation === 'string' && Array.isArray(p.args) && p.body?.requestId === p.key);
  const digest = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))), b => b.toString(16).padStart(2,'0')).join('');
  const ownedV2 = async (p,s) => !!(p?.version === 2 && p.binding === await digest(JSON.stringify([s.sessionId,s.actorBinding])) && typeof p.key === 'string' && typeof p.fingerprint === 'string');
  const clear = () => { scope = null; content.replaceChildren(); q('[data-recovery]').hidden = true; };
  function reset() { generation++; busy = false; clear(); status.textContent = ''; }
  function recovery(s) { const p = pending(s); q('[data-recovery]').hidden = !mine(p,s); return p; }
  async function call(op, body, args, s, g) { const r = await api.call(op, body, ...args, {scope:s}); guard(s,g); return r; }
  const confirmed = (operation, result) => operation !== 'w17InstantiateTemplate' || !!(result?.round?.id && result?.format?.id);
  async function send(s,p,g) {
    busy = true; clear(); status.textContent = 'Saving the exact action…';
    try {
      if (!navigator?.locks?.request) throw Error('Safe recovery unavailable');
      await navigator.locks.request(keyFor(s), async () => {
        guard(s,g);
        const raw = localStorage.getItem(keyFor(s));
        if (!raw || JSON.stringify(JSON.parse(raw)) !== JSON.stringify(p) || !mine(p,s)) throw Error('Original action changed');
        const r = await call(p.operation,p.body,p.args,s,g);
        if (!confirmed(p.operation,r) || localStorage.getItem(keyFor(s)) !== raw) throw Error('Unconfirmed result');
        localStorage.removeItem(keyFor(s));
        if (p.operation === 'w17InstantiateTemplate') onRoundOpened(r.format.id,r.round.id);
        status.textContent = 'Action confirmed. Refresh to check current rights and state.';
      });
    } catch { if (g === generation) { recovery(s); status.textContent = 'Outcome or current access is unconfirmed. Replay only the exact saved action; a conflict does not prove failure.'; } }
    finally { if (g === generation) busy = false; }
  }
  async function mutate(operation, body, args = [], onSuccess = null) {
    if (!scope || busy) return; const s = scope, g = generation;
    busy = true; let sent = false;
    try {
      guard(s,g);
      if (!s.actorBinding || !crypto?.subtle || !navigator?.locks?.request) throw Error('Secure recovery is unavailable. Nothing was sent.');
      await navigator.locks.request(keyFor(s), async () => {
        guard(s,g); let p = pending(s);
        if (p && !(await ownedV2(p,s))) throw Error('A previous action is unresolved; use its original recovery controls.');
        const key = p?.key || crypto.randomUUID(), wire = {...body,requestId:key};
        const fingerprint = await digest(JSON.stringify([operation,args,wire]));
        guard(s,g);
        if (p && p.fingerprint !== fingerprint) throw Error('A previous action is unresolved. Re-enter its exact selections to retry.');
        if (!p) {
          p = {version:2,binding:await digest(JSON.stringify([s.sessionId,s.actorBinding])),key,fingerprint};
          guard(s,g); localStorage.setItem(keyFor(s),JSON.stringify(p));
          if (localStorage.getItem(keyFor(s)) !== JSON.stringify(p)) throw Error('Cannot safely save recovery information. Nothing was sent.');
        }
        const saved = localStorage.getItem(keyFor(s));
        status.textContent = 'Saving the exact action…';
        sent = true; const result = await call(operation,wire,args,s,g);
        if (!confirmed(operation,result) || localStorage.getItem(keyFor(s)) !== saved) throw Error('Unconfirmed result');
        localStorage.removeItem(keyFor(s));
        if (localStorage.getItem(keyFor(s)) !== null) throw Error('Recovery information could not be cleared.');
        if (result?.round?.id && result?.format?.id && operation === 'w17InstantiateTemplate') onRoundOpened(result.format.id,result.round.id);
        if (onSuccess) onSuccess(result);
        status.textContent = 'Action confirmed. Refresh to check current rights and state.';
      });
    } catch (e) { if (g === generation) status.textContent = sent ? 'Outcome or current access is unconfirmed. Re-enter the exact action to retry with the original request ID.' : (e?.message || 'Recovery is unavailable. Nothing was sent.'); }
    finally { if (g === generation) busy = false; }
  }
  q('[data-replay]').onclick = () => { const s = identityScope(), g = generation; if (busy) return; let p; try { guard(s,g); p = pending(s); if (!mine(p,s)) throw Error(); } catch { clear(); status.textContent = 'The original saved access is required to replay this action.'; return; } send(s,p,g); };
  function definitionForm(parent, original, submit, newDefinition = false) {
    const l = el('label','Type '), type = el('select'); for (const [v,t] of [['choice','Choice'],['structured_board','Structured board']]) { const o = el('option',t); o.value=v; type.append(o); } type.value=original?.type || 'choice'; type.disabled=!!original && !newDefinition; l.append(type); parent.append(l);
    const title=field(parent,'Title',original?.title || ''), question=field(parent,'Question or prompt',original?.question || '',true), items=field(parent,'Options or cards, one per line',original ? (original.type === 'choice' ? original.options : original.cards).join('\n') : '',true);
    button(parent,original && !newDefinition ? 'Create immutable version' : 'Create definition',()=>{const list=items.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean), choice=type.value==='choice'; if(!title.value.trim() || !question.value.trim() || list.length<(choice?2:1) || list.length>(choice?20:30) || new Set(list).size!==list.length){status.textContent='Enter a title, prompt and distinct items: 2–20 options or 1–30 cards.';return;} submit({type:type.value,title:title.value.trim(),question:question.value.trim(),options:choice?list:[],cards:choice?[]:list});});
  }
  function showDefinition(parent,d) { parent.append(el('p',`${d.type === 'choice' ? 'Choice' : 'Structured board'}: ${d.title}`),el('p',d.question)); const list=el('ul'); for(const x of (d.type==='choice'?d.options:d.cards)) list.append(el('li',x)); parent.append(list); }
  function roundCard(parent,view,s) {
    const {round:r,format:f,contributions:cs,carriedMaterial:materials}=view;
    if(!r || !f || !Array.isArray(cs) || !Array.isArray(materials)) throw Error('round');
    const card=el('article'); card.append(el('h3',f.title),el('p',`Stage: ${r.stage}`),el('p',f.question));
    if(s.role==='creator' || ['reveal','close'].includes(r.stage)) { if(f.decision) { card.append(el('p',`Decision: ${f.decision.decision}`),el('p',`Consequence: ${f.decision.consequence}`)); } }
    // The authenticated round projection already limits pre-reveal contributions to this viewer.
    const visible = cs;
    for(const c of visible) { const minority=f.decision?.minorityIds?.includes(c.id) && (s.role==='creator'||['reveal','close'].includes(r.stage)); card.append(el('p',`${c.selection} · ${c.status}${minority?' · minority position':''} · ${c.reason || 'No reason'}`)); }
    for(const m of materials) card.append(el('p',`Current eligible material: ${m.title} · version ${m.version}`),el('p',m.body));
    if(r.materialLinks?.length > materials.length) card.append(el('p','Some linked material is unavailable under current approval or source permissions.'));
    const cardGeneration = generation;
    button(card,'Open participation and withdrawal',()=>{try{guard(s,cardGeneration);onRoundOpened(f.id,r.id);}catch{reset();status.textContent='Identity changed. Refresh before acting.';}});
    if(s.role==='creator' && r.stage!=='close') { const i=stages.indexOf(r.stage), next=stages[i+1]; if(next && (next!=='reveal'||f.decision)) button(card,`Move to ${next}`,()=>mutate('w17TransitionTemplateRound',{expectedRevision:r._revision,stage:next},[r.id])); if(next!=='close' && !cs.some(c=>c.status!=='withdrawn')) button(card,'Close with zero responses',()=>mutate('w17TransitionTemplateRound',{expectedRevision:r._revision,stage:'close'},[r.id])); }
    parent.append(card);
  }
  async function loadTemplate(t,s,g,host,materials,selectedTemplateId = null) {
    host.replaceChildren(); try { const result=await call('w17Template',null,[t.id],s,g); if(!Array.isArray(result.versions)||!result.template) throw Error(); const current=result.template;
      for(const v of result.versions) { const section=el('section'); section.append(el('h4',`Definition version ${v.version}`)); showDefinition(section,v.definition);
        const adapt=el('details'); adapt.append(el('summary','Adapt as a new version')); definitionForm(adapt,v.definition,d=>mutate('w17TemplateVersion',{expectedRevision:current._revision,definition:d},[t.id])); section.append(adapt);
        const setup=el('details'); if(t.id===selectedTemplateId) setup.open=true; setup.append(el('summary','Preview a fresh round'),el('p','Responses, identities, consents and the decision reset. Sources must be explicitly selected. No previous responses or consent are copied.'));
        const chosen=[], refs=[]; for(const m of materials){const l=el('label'), c=el('input'); c.type='checkbox'; l.append(c,document.createTextNode(` Include approved ${m.title || m.id}, exact version ${m.currentVersion}`)); setup.append(l); chosen.push({c,m});}
        const search=field(setup,'Find current source moment'), found=el('div'), selected=el('div'); setup.append(found,selected);
        button(setup,'Search sources',async()=>{if(busy)return; busy=true; found.replaceChildren(); try{const res=await call('w15Search',null,[search.value.trim()],s,g); for(const x of res.moments || []) if(x.ref?.sessionId===s.sessionId){const row=el('p',x.text || 'Source moment');button(row,'Select source',()=>{if(!refs.some(r=>JSON.stringify(r)===JSON.stringify(x.ref)))refs.push(x.ref);selected.textContent=refs.map(r=>`${r.sourceId} / ${r.momentId} / revision ${r.sourceRevision}`).join('; ');});found.append(row);}}catch{if(g===generation){clear();status.textContent='Source access could not be confirmed. Refresh before acting.';}}finally{if(g===generation)busy=false;}});
        const preview=el('div'); setup.append(preview); let reviewed=null;
        const payload=()=>({version:v.version,resetPolicy:{...resetPolicy},refs:refs.slice(),materialLinks:chosen.filter(x=>x.c.checked).map(x=>({id:x.m.id,version:x.m.currentVersion}))});
        button(setup,'Preview exact definition and eligible material',()=>{reviewed=null;preview.replaceChildren();const body=payload();mutate('w17TemplatePreview',body,[t.id],result=>{if(!result.preview)throw Error('Preview unavailable.');showDefinition(preview,result.preview.definition);preview.append(el('p','Reset policy and source selection:'),el('pre',JSON.stringify({resetPolicy:result.preview.resetPolicy,refs:result.preview.refs},null,2)));for(const m of result.preview.carriedMaterial||[])preview.append(el('p',`Eligible material: ${m.title} · exact version ${m.version}`),el('p',m.body),el('pre',JSON.stringify(m.refs,null,2)));reviewed=JSON.stringify(body);});});
        button(setup,'Instantiate fresh round',()=>{const body=payload();if((!reviewed||reviewed!==JSON.stringify(body)) && !pending(s)){status.textContent='Preview these exact selections first.';return;}mutate('w17InstantiateTemplate',body,[t.id]);}); section.append(setup);host.append(section);
      }
    } catch (e) { if(g===generation){host.replaceChildren();status.textContent='Definition or current permission unavailable. Refresh before acting.';} if(selectedTemplateId) throw e; }
  }
  async function refresh(entry = null) {
    if(busy) { if(entry) throw Error("Templates are busy. Try again."); return; } const s=identityScope(); if(entry) { assertIdentity(entry.scope); assertIdentity(s); if(s.sessionId!==entry.scope.sessionId || s.actorBinding!==entry.scope.actorBinding || s.token!==entry.scope.token || s.role!=='creator') throw Error("Creator identity changed. Refresh and try again."); } const g=++generation; clear(); busy=true;status.textContent='Checking current access…';
    try {if(!s.token||!s.sessionId)throw Error(); const f=await call('w15Formats',null,[],s,g); if(!Array.isArray(f.formats))throw Error(); let templates=[],materials=[];
      if(s.role==='creator'){const [t,m]=await Promise.all([call('w17Templates',null,[],s,g),call('p10StudioMaterials',null,[],s,g)]);if(!Array.isArray(t.templates)||!Array.isArray(m.materials))throw Error();templates=t.templates;materials=m.materials.filter(x=>['approved','published'].includes(x.status)&&x.currentVersion===x.approvedVersion&&Number.isInteger(x.currentVersion));}
      const views=[];for(const fmt of f.formats.filter(x=>x.templateRoundId)){try{views.push(await call('w17TemplateRound',null,[fmt.templateRoundId],s,g));}catch{guard(s,g);}}
      guard(s,g);scope=s; const saved=recovery(s); status.textContent=saved ? (mine(saved,s)?'A saved action is unconfirmed. Replay it exactly before making another change.':saved.version===2?'A saved action is unconfirmed. Re-enter its exact selections to retry with the original request ID.':'A saved action belongs to another identity or cannot be read; changes are blocked.') : 'Current templates and rounds loaded.';
      if(s.role==='creator'){const create=el('details');create.append(el('summary','Create a reusable definition'));definitionForm(create,entry?.definition || null,d=>mutate('w17CreateTemplate',{definition:d},[],result=>{const id=result?.template?.id;if(typeof id!=='string' || !id) return; const next=el('p','Definition saved. ');button(next,'Select saved definition for a fresh round',()=>{try{guard(s,g);refresh({scope:s,templateId:id}).catch(()=>{});}catch{status.textContent='Identity changed. Refresh before selecting a definition.';}});create.append(next);}),!!entry?.definition);if(entry?.definition){create.open=true;box.querySelector('details').open=true;}content.append(create);const imp=el('details');imp.append(el('summary','Import an accepted continuation definition'),el('p','Only an accepted continuation of a marked template round can be imported.'));const id=field(imp,'Accepted continuation ID');button(imp,'Import exact reviewed definition',()=>{if(id.value.trim())mutate('w17ImportContinuation',{transferId:id.value.trim()});});content.append(imp);const lib=el('section');lib.append(el('h3','Your definition library'));if(!templates.length)lib.append(el('p','No definitions available.'));for(const t of templates){const d=el('details');d.append(el('summary',`Template ${t.id} · latest version ${t.latestVersion}`));const host=el('div');d.append(host);if(callbacks.exportDefinition)button(d,'Export saved definition',async()=>{if(busy)return;busy=true;try{guard(s,g);const r=await callbacks.exportDefinition(t.id,s);guard(s,g);if(!r?.envelope)throw Error();const out=el('textarea');out.readOnly=true;out.setAttribute('aria-label','Exported saved definition JSON');out.value=JSON.stringify(r.envelope,null,2);d.append(out);out.focus();out.select();status.textContent='Saved definition ready to copy.';}catch{if(g===generation)status.textContent='Saved definition export or current access is unavailable. Refresh and try again.';}finally{if(g===generation)busy=false;}});d.ontoggle=()=>{if(d.open && !host.childNodes.length)loadTemplate(t,s,g,host,materials);};lib.append(d);if(entry?.templateId===t.id){box.querySelector('details').open=true;d.open=true;await loadTemplate(t,s,g,host,materials,t.id);guard(s,g);}}content.append(lib);if(entry?.templateId && !templates.some(t=>t.id===entry.templateId))throw Error('Imported template is unavailable. Refresh and check access.');}
      const rounds=el('section');rounds.append(el('h3','Current rounds'));if(!views.length)rounds.append(el('p','No eligible marked rounds available.'));for(const view of views)roundCard(rounds,view,s);content.append(rounds);
    } catch (e) {if(g===generation){clear();status.textContent=entry?.templateId ? 'Imported template or current access unavailable. Refresh and check access.' : 'Templates or current access unavailable. Refresh before acting.';} if(entry) throw e;} finally {if(g===generation)busy=false;}
  }
  function prefillDefinition(definition, entryScope) {
    const keys=['type','title','question','options','cards'];
    if(!definition || typeof definition!=='object' || Array.isArray(definition) || Object.keys(definition).length!==keys.length || !keys.every(k=>Object.hasOwn(definition,k)) || !['choice','structured_board'].includes(definition.type) || typeof definition.title!=='string' || typeof definition.question!=='string' || !Array.isArray(definition.options) || !Array.isArray(definition.cards) || ![...definition.options,...definition.cards].every(x=>typeof x==='string') || (definition.type==='choice' ? definition.cards.length : definition.options.length)) throw Error('Unsupported definition. Check compatibility and use schema version 1 with only definition fields.');
    const copy={type:definition.type,title:definition.title,question:definition.question,options:[...definition.options],cards:[...definition.cards]};
    return refresh({scope:entryScope,definition:copy});
  }
  function selectTemplate(templateId, entryScope) { if(typeof templateId!=='string' || !templateId) throw Error('Import or save a definition first.'); return refresh({scope:entryScope,templateId}); }
  q('[data-refresh]').onclick=()=>refresh(); return {refresh:()=>refresh(),reset,prefillDefinition,selectTemplate};
}

