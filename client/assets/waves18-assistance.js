export function mountAssistance(root, api, identityScope, assertIdentity, actions = {}) {
  const box = document.createElement('section'); box.className = 'w18-assistance';
  box.innerHTML = '<h2>Creator assistance</h2><p>Creator-controlled, deterministic source excerpts. Nothing is scheduled, approved or presented automatically.</p><p role="status" aria-live="polite" data-status></p><div data-recovery hidden><p>The outcome is unknown. Retry the exact saved request before making another change.</p><button type="button" data-retry>Retry exact request</button></div><div data-content></div>';
  root.append(box);
  const status = box.querySelector('[data-status]'), content = box.querySelector('[data-content]'), recovery = box.querySelector('[data-recovery]');
  let context = null, scope = null, generation = 0, busy = false, state = null, alive = true;
  const el = (tag, text = '') => { const n = document.createElement(tag); n.textContent = text; return n; };
  const button = (parent, label, fn) => { const b = el('button', label); b.type = 'button'; b.onclick = fn; parent.append(b); return b; };
  const field = (parent, label, value, type = 'text') => { const l = el('label', label), i = el(type === 'textarea' ? 'textarea' : 'input'); if (type !== 'textarea') i.type = type; i.value = value; l.append(i); parent.append(l); return i; };
  const check = (parent, label, value) => { const l = el('label'), i = el('input'); i.type = 'checkbox'; i.checked = value; l.append(i, document.createTextNode(' ' + label)); parent.append(l); return i; };
  const canonical = x => Array.isArray(x) ? x.map(canonical) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canonical(x[k])])) : x;
  const same = (a,b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  const guard = (s, g) => { if (!alive || g !== generation || !s) throw Error('stale'); assertIdentity(s); };
  const key = s => `w18-assistance:${s.sessionId}:${s.actorBinding}`;
  const saved = (s,g) => { guard(s,g); try { const v = localStorage.getItem(key(s)); return v ? JSON.parse(v) : null; } catch { return {invalid:true}; } };
  const own = (p,s) => p && p.version === 1 && p.sessionId === s.sessionId && p.actorBinding === s.actorBinding && p.contextId === context?.id && p.body?.requestId && Array.isArray(p.args) && ['w18AssistancePolicy','w18AssistanceCandidates','w18AssistanceFeedback'].includes(p.operation);
  const removeOriginal = (s,g,p) => { guard(s,g); const current = saved(s,g); if (!same(current,p)) return false; guard(s,g); localStorage.removeItem(key(s)); return true; };
  const clear = () => { content.replaceChildren(); state = null; recovery.hidden = true; };
  function reset() { generation++; busy = false; scope = null; context = null; clear(); status.textContent = 'Choose a current segment or context in the workspace.'; }
  function setContext(next) {
    reset();
    if (!next) return;
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(next.id || '') || !Array.isArray(next.sources) || (next.signals && !Array.isArray(next.signals))) { status.textContent = 'Current context or eligible selections are unavailable.'; return; }
    context = JSON.parse(JSON.stringify({id:next.id, label:next.label || 'Selected context', sources:next.sources, signals:next.signals || []}));
    bindRetry();
    status.textContent = 'Context selected. Refresh to verify current permissions.';
  }
  async function call(operation, body, args, s, g) { guard(s,g); const result = await api.call(operation, body, ...args, {scope:s}); guard(s,g); return result; }
  function showRecovery(s,g) { const p = saved(s,g); recovery.hidden = !own(p,s); return p; }
  async function send(s,p,g) {
    busy = true; clear(); status.textContent = 'Checking the saved action…';
    try {
      const result = await call(p.operation,p.body,p.args,s,g);
      if (!result || !('assistance' in result)) throw Error('Invalid response');
      if (!removeOriginal(s,g,p)) { status.textContent = 'The saved action changed. Resolve the current recovery before another action.'; return; }
      if (result.materialId && typeof actions.onDraftCreated === 'function') { try { actions.onDraftCreated(result.materialId); } catch { /* The draft is already committed. */ } }
      status.textContent = result.materialId ? 'Unapproved Studio draft created. Review and approval remain separate.' : 'Action confirmed. Refreshing current permissions…';
      busy = false; await refresh();
    } catch (e) {
      try { guard(s,g); } catch { return; }
      const code = e?.code || e?.error?.code;
      if (['stale_revision','stale_receipt','request_conflict','stale_context','forbidden','not_found','invalid_refs','invalid_request','quiet','not_allowed','duplicate','queue_full','cooldown','frequency_limit','candidate_capacity','receipt_capacity','no_signal'].includes(code)) {
        if (['stale_revision','stale_receipt','request_conflict','stale_context','forbidden','not_found','invalid_refs'].includes(code)) {
          if (!removeOriginal(s,g,p)) { status.textContent = 'The saved action changed. Resolve the current recovery before another action.'; return; }
          status.textContent = `${code}: current state or permission changed. Refresh before another action; a stale receipt does not prove the original action failed.`;
        } else { if (!removeOriginal(s,g,p)) { status.textContent = 'The saved action changed. Resolve the current recovery before another action.'; return; } status.textContent = `${code}: action was not accepted. Refresh before trying again.`; }
      } else { showRecovery(s,g); status.textContent = 'Action outcome or permission is unconfirmed. Retry the exact saved request.'; }
    } finally { if (alive && g === generation) busy = false; }
  }
  async function mutate(operation, payload, args) {
    if (!scope || busy || !state && operation !== 'w18AssistancePolicy') return;
    const s = scope, g = generation;
    try { guard(s,g); } catch { reset(); status.textContent = 'Identity changed. Select the context again.'; return; }
    if (saved(s,g)) { showRecovery(s,g); status.textContent = 'An earlier action is unresolved or belongs to another context. Resolve it before changing anything.'; return; }
    if (!s.actorBinding) { status.textContent = 'Identity binding unavailable; nothing was sent.'; return; }
    const requestId = crypto.randomUUID(), p = {version:1, sessionId:s.sessionId, actorBinding:s.actorBinding, contextId:context.id, operation, args, body:{requestId, expectedRevision:state?._revision || 0, ...payload}};
    try { guard(s,g); localStorage.setItem(key(s), JSON.stringify(p)); } catch { status.textContent = 'Recovery storage unavailable; nothing was sent.'; return; }
    await send(s,p,g);
  }
  function bindRetry() {
    const s = identityScope(), g = generation;
    box.querySelector('[data-retry]').onclick = () => {
      try { guard(s,g); if (busy || !context) return; const p = saved(s,g); if (!own(p,s)) return; return send(s,p,g); } catch { return; }
    };
  }
  function render(s,g) {
    const button = (parent,label,fn) => { const b = el('button',label); b.type = 'button'; b.onclick = (...args) => { try { guard(s,g); } catch { return; } return fn(...args); }; parent.append(b); return b; };
    content.replaceChildren(); const p = state?.policy;
    content.append(el('h3', context.label), el('p', 'Only selected audience-visible source moments and optional shared or consented signals are used.'));
    const refreshButton = button(content, 'Refresh current assistance and permissions', refresh); refreshButton.disabled = busy;
    const form = el('fieldset'); form.append(el('legend', 'Assistance policy — explicit creator choice'));
    const objective = field(form,'Objective',p?.objective || '', 'textarea'); objective.maxLength = 1000;
    const enabled = check(form,'Allow deterministic source excerpts',p?.allowedKinds?.includes('source_excerpt') || false);
    const quiet = check(form,'Quiet: stop new candidates',p?.quiet ?? true);
    const cooldown = field(form,'Cooldown in seconds (0–86400)',p?.cooldownSeconds ?? 0,'number'); cooldown.min=0; cooldown.max=86400;
    const rate = field(form,'Maximum candidates per hour (1–60)',p?.maxPerHour ?? 1,'number'); rate.min=1; rate.max=60;
    const limit = field(form,'Queue limit (1–20)',p?.queueLimit ?? 5,'number'); limit.min=1; limit.max=20;
    button(form,'Save policy',()=>{ const nums=[cooldown,rate,limit].map(x=>Number(x.value)); if(!objective.value.trim() || objective.value.length>1000 || [cooldown,rate,limit].some(x=>x.value.trim()==='') || nums.some(x=>!Number.isInteger(x)) || nums[0]<0 || nums[0]>86400 || nums[1]<1 || nums[1]>60 || nums[2]<1 || nums[2]>20){status.textContent='Enter an objective and valid whole-number limits.';return;} mutate('w18AssistancePolicy',{policy:{objective:objective.value,allowedKinds:enabled.checked?['source_excerpt']:[],cooldownSeconds:nums[0],maxPerHour:nums[1],queueLimit:nums[2],quiet:quiet.checked}},[context.id]); });
    content.append(form);
    if (!p) { content.append(el('p','No policy configured. Enabling assistance requires your explicit choice.')); return; }
    const active = (state.candidates || []).filter(c=>c.state==='pending'||c.state==='deferred');
    content.append(el('p',`Quiet ${p.quiet?'on':'off'} · eligible queue ${active.length} / ${p.queueLimit} · maximum ${p.maxPerHour} per hour · cooldown ${p.cooldownSeconds} seconds. Quiet does not change previously approved work.`));
    const select = el('fieldset'); select.append(el('legend','Select current eligible source moments'));
    const refs = context.sources.map(x=>({x,c:check(select,x.label || 'Eligible source moment',false)}));
    if (!refs.length) select.append(el('p','No eligible source moments supplied by the workspace.'));
    const choices = context.signals.map(x=>({x,c:check(select,x.label || (x.kind==='question'?'Shared question':'Consented contribution'),false)}));
    button(select,'Create deterministic candidate',()=>{const chosen=refs.filter(x=>x.c.checked).map(x=>x.x.ref), sig=choices.filter(x=>x.c.checked).map(({x})=>({kind:x.kind,id:x.id,revision:x.revision})); if(!chosen.length || chosen.some(x=>!x || x.sessionId!==s.sessionId) || sig.length>5 || sig.some(x=>!['question','contribution'].includes(x.kind))){status.textContent='Select at least one eligible local source and at most five shared or consented signals.';return;} mutate('w18AssistanceCandidates',{kind:'source_excerpt',refs:chosen,signals:sig},[context.id]); });
    content.append(select,el('h3','Review queue'));
    if (!(state.candidates || []).length) content.append(el('p','No candidates.'));
    for (const c of state.candidates || []) {
      const card=el('article'); card.append(el('h4',`Candidate · ${c.state}`));
      const refsCurrent = Array.isArray(c.refs) && c.refs.every(ref => context.sources.some(x => same(x.ref,ref)));
      const signalsCurrent = (c.signals || []).every(sig => context.signals.some(x => x.kind === sig.kind && x.id === sig.id && x.revision === sig.revision));
      if (c.state==='stale' || ((c.state==='pending' || c.state==='deferred') && (!refsCurrent || !signalsCurrent))) { card.append(el('p','Unavailable: source, consent or policy changed. Candidate content and references are suppressed.')); content.append(card); continue; }
      if (!['pending','deferred'].includes(c.state)) { card.append(el('p',c.state==='accepted'?'Accepted as an unapproved Studio draft.':'Closed; duplicate suggestions remain suppressed.')); content.append(card); continue; }
      card.append(el('p','Deterministic excerpt for review; not an AI relevance judgment.'),el('p',`Rationale: ${c.rationale || 'Selected source context.'}`));
      const list=el('ul'); for(const ref of c.refs || []) { const match=context.sources.find(x=>JSON.stringify(x.ref)===JSON.stringify(ref)); list.append(el('li',match?.label || 'Previously selected source moment')); } card.append(el('p','Sources:'),list);
      const title=field(card,'Draft title',c.draft?.title || ''), body=field(card,'Draft body',c.draft?.body || '','textarea'); title.maxLength=200; body.maxLength=12000;
      button(card,'Accept edited text as unapproved Studio draft',()=>{if(!title.value.trim() || !body.value.trim()){status.textContent='Enter a title and body before accepting.';return;} mutate('w18AssistanceFeedback',{action:'accept',title:title.value,body:body.value},[context.id,c.id]);});
      button(card,'Defer',()=>mutate('w18AssistanceFeedback',{action:'defer',title:null,body:null},[context.id,c.id]));
      button(card,'Dismiss',()=>mutate('w18AssistanceFeedback',{action:'dismiss',title:null,body:null},[context.id,c.id])); content.append(card);
    }
  }
  async function refresh() {
    if (!alive || busy || !context) return; const s=identityScope(), g=++generation; bindRetry(); clear(); busy=true; status.textContent='Checking creator access and current sources…';
    try { if (!s?.sessionId || !s.token || !s.actorBinding || s.role!=='creator') throw Error('creator'); guard(s,g); const result=await call('w18Assistance',null,[context.id],s,g); if (!result || !('assistance' in result)) throw Error('response'); scope=s; state=result.assistance; busy=false; render(s,g); const pending=showRecovery(s,g); status.textContent=pending ? (own(pending,s)?'An earlier action is unconfirmed. Retry it exactly.':'An earlier action belongs to another context or cannot be read; changes are blocked.') : 'Current assistance loaded. Source rights are checked again by the server on actions.'; }
    catch { try { guard(s,g); } catch { return; } clear();scope=null;status.textContent='Creator permission, context or current sources unavailable. Select the context again or refresh.'; }
    finally { if(alive && g===generation) busy=false; }
  }
  reset(); bindRetry(); return {refresh,reset,setContext,destroy() { reset(); alive = false; box.remove(); }};
}

