export function mountFiniteFormats(root, api, identityScope, assertIdentity, onWorkCreated = () => {}) {
  const box = document.createElement('section'); box.className = 'p6-card';
  box.innerHTML = `<details><summary>Choices and proposal boards</summary><p>Share only what you choose. The creator reviews contributions; private notes are never included.</p><button type="button" data-refresh>Refresh choices and boards</button><p role="status" aria-live="polite" data-status></p><div data-recovery hidden><button type="button" data-check>Check saved action receipt</button><button type="button" data-retry>Retry exact saved action</button></div><div data-author hidden><h3>Create a format</h3><div data-create-form></div></div><div data-formats></div><div data-offers></div></details>`;
  root.append(box);
  const q = selector => box.querySelector(selector), status = q('[data-status]');
  let generation = 0, busy = false, scope = null, formats = [], contributions = [], transfers = [], checkedKey = null;
  const el = (tag, text = '') => { const n = document.createElement(tag); n.textContent = text; return n; };
  const button = (parent, label, action) => { const b = el('button', label); b.type = 'button'; b.onclick = action; parent.append(b); return b; };
  const field = (parent, label, value = '', multiline = false) => { const l = el('label', label + ' '), input = el(multiline ? 'textarea' : 'input'); input.value = value; l.append(input); parent.append(l); return input; };
  const check = (parent, label, checked = false) => { const l = el('label', ' ' + label), input = el('input'); input.type = 'checkbox'; input.checked = checked; l.prepend(input); parent.append(l); return input; };
  const guard = (s, g) => { assertIdentity(s); if (g !== generation) throw Error('stale'); };
  const pendingKey = s => `w15-format-pending:${s.sessionId}`;
  const pending = s => { try { const v=localStorage.getItem(pendingKey(s)); return v ? JSON.parse(v) : null; } catch { return {invalid:true}; } };
  const mine = (p,s) => !!(s.token && s.actorBinding && p?.version===2 && p.sessionId===s.sessionId && p.actorBinding===s.actorBinding && p.body && p.body.mutationRequestId===p.key && typeof p.route==='string');
  const recovery = s => { const p=pending(s); q('[data-recovery]').hidden=!mine(p,s); return p; };
  const clear = () => { scope = null; formats = []; contributions = []; transfers = []; q('[data-formats]').replaceChildren(); q('[data-offers]').replaceChildren(); q('[data-author]').hidden = true; q('[data-recovery]').hidden = true; };
  const reset = () => { checkedKey=null; generation++; busy = false; clear(); status.textContent = ''; };
  const invalidate = () => { checkedKey=null; generation++; busy = false; clear(); status.textContent = 'Source access changed or could not be confirmed. Refresh before acting.'; };
  async function refresh() {
    if (busy) return; const s = identityScope(), g = ++generation; clear(); busy = true; status.textContent = 'Checking current access…';
    try { if (!s.token || !s.sessionId) throw Error('identity'); const r = await api.call('w15Formats', null, {scope:s}); guard(s,g); if (!Array.isArray(r.formats) || !Array.isArray(r.contributions)) throw Error('response');
      let t = {transfers:[]}; if (s.role === 'creator') { t = await api.call('w15FormatTransfers', null, {scope:s}); guard(s,g); if (!Array.isArray(t.transfers)) throw Error('response'); }
      formats = r.formats; contributions = r.contributions; transfers = t.transfers; scope = s; render(); const p=recovery(s); status.textContent = p ? (mine(p,s) ? 'A previous action is unconfirmed. Check its receipt, then retry the exact saved action.' : 'A previous action belongs to another identity or an older recovery format. Changes remain blocked.') : 'Current choices and boards loaded.';
    } catch { if (g === generation) { clear(); status.textContent = 'Choices and boards are unavailable. Refresh to check access.'; } } finally { if (g === generation) busy = false; }
  }
  async function sendSaved(s,p,g) {
    busy=true; status.textContent='Saving the exact action…';
    try {
      const args=p.args || (p.id?[p.id]:[]); const result=await api.call(p.route,p.body,...args,{scope:s});
      guard(s,g); localStorage.removeItem(pendingKey(s)); checkedKey=null; if (p.route === 'w15CreateFormatWork' && result?.work?.id && result?.material?.id) onWorkCreated(); clear(); const ids=[result?.work?.id && `Work ID: ${result.work.id}`,result?.material?.id && `Studio material ID: ${result.material.id}`,result?.transfer?.id && `Offer ID: ${result.transfer.id}`,result?.grant?.id && `Source permission ID: ${result.grant.id}`].filter(Boolean); status.textContent='Action confirmed with current access. Refresh to see the current state. '+ids.join(' · ');
    } catch { if(g===generation) { clear(); recovery(s); status.textContent='The action remains unconfirmed or current access was lost. Check the receipt; no changed action was sent.'; } }
    finally {if(g===generation)busy=false;}
  }
  async function mutate(route, body, id, extra) {
    if(!scope || busy)return; const s=scope,g=generation;
    try {guard(s,g);} catch {invalidate();return;}
    if(pending(s)){status.textContent='A previous action is unconfirmed. Further changes are blocked.';return;}
    if(!s.actorBinding){status.textContent='Cannot bind this action to the current identity.';return;}
    const key=crypto.randomUUID(), p={version:2,sessionId:s.sessionId,actorBinding:s.actorBinding,route,id:id||null,args:id?(extra?[id,extra]:[id]):[],key,body:{...body,mutationRequestId:key}};
    try {localStorage.setItem(pendingKey(s),JSON.stringify(p));} catch {status.textContent='Cannot safely track this action. It was not sent.';return;}
    await sendSaved(s,p,g);
  }
  q('[data-check]').onclick=async()=>{const s=identityScope(),p=pending(s),g=generation;if(busy||!mine(p,s))return;try{guard(s,g);}catch{invalidate();return;}busy=true;
    try {const r=await api.call('w15FormatReceipt',null,p.key,{scope:s});guard(s,g);if(r?.receipt?.requestId!==p.key||!['unknown','committed'].includes(r.receipt.state))throw Error();checkedKey=p.key;status.textContent=r.receipt.state==='committed'?'The action was committed. Retry the exact saved action to check current rights and complete recovery.':'The outcome is unknown. Only the exact saved action may be retried; absence is not established.';}
    catch {if(g===generation)status.textContent='Receipt or current access could not be confirmed. Recovery remains pending.';}finally{if(g===generation)busy=false;}
  };
  q('[data-retry]').onclick=()=>{const s=identityScope(),p=pending(s),g=generation;try{guard(s,g);if(!mine(p,s)||checkedKey!==p.key)throw Error();}catch{status.textContent='Check the saved action receipt with the original identity first.';return;}sendSaved(s,p,g);};
  function sourcePicker(parent, initial = []) {
    let refs = initial.slice(), results = [];
    const details = el('details'), summary = el('summary','Sources (optional)'); details.append(summary);
    const selected = el('div'); details.append(selected);
    const show = () => { selected.replaceChildren(); if (!refs.length) selected.append(el('p','No source selected.')); refs.forEach((r,i) => { const p = el('p', `Source ${r.sourceId}, moment ${r.momentId}, ${r.startMs}–${r.endMs} ms, revision ${r.sourceRevision} `); button(p,'Remove source',()=>{refs.splice(i,1);show();}); selected.append(p); }); };
    const query = field(details,'Find an indexed source'); const out = el('div');
    button(details,'Search sources',async()=>{ if (!scope || busy || !query.value.trim()) return; const s=scope,g=generation; busy=true; try { const r=await api.call('w15Search',null,query.value.trim(),{scope:s}); guard(s,g); results=Array.isArray(r.moments)?r.moments:[]; out.replaceChildren(); if (!results.length) out.append(el('p','No current indexed moments found.')); for (const item of results) { if (!item.ref || item.ref.sessionId !== s.sessionId || typeof item.text !== 'string') continue; const row=el('p',item.text+' '); button(row,'Use this source',()=>{if(!refs.some(x=>JSON.stringify(x)===JSON.stringify(item.ref))) refs.push(item.ref);show();}); out.append(row); } } catch { if(g===generation) invalidate(); } finally { if(g===generation) busy=false; } }); details.append(out); parent.append(details); show(); return () => refs.slice();
  }
  function definitionForm(parent, f = null) {
    const typeLabel = el('label','Format '), type = el('select'); for (const [v,l] of [['choice','Choice'],['structured_board','Proposal board']]) { const o=el('option',l); o.value=v; type.append(o); } type.value=f?.type || 'choice'; if(f) type.disabled=true; typeLabel.append(type); parent.append(typeLabel);
    const title=field(parent,'Title',f?.title||''), question=field(parent,'Question or prompt',f?.question||'',true), items=field(parent,'Options, one per line (2–20)',(f ? (f.type==='choice'?f.options:f.cards) : []).join('\n'),true);
    const label=items.parentElement; type.onchange=()=>{label.firstChild.textContent=type.value==='choice'?'Options, one per line (2–20) ':'Proposal cards, one per line (1–30) ';}; type.onchange(); const getRefs=sourcePicker(parent,f?.refs||[]);
    return () => { const list=items.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean), choice=type.value==='choice'; if(!title.value.trim()||!question.value.trim()||list.length<(choice?2:1)||list.length>(choice?20:30)||new Set(list).size!==list.length){status.textContent='Enter a title, prompt and distinct items within the stated limits.';return null;} return {type:type.value,title:title.value.trim(),question:question.value.trim(),options:choice?list:[],cards:choice?[]:list,refs:getRefs()}; };
  }
  function contributionForm(parent,f,c=null) {
    const label=el('label',f.type==='choice'?'Choose an option ':'Choose a proposal '), select=el('select'), blank=el('option','Select one'); blank.value='';select.append(blank); for(const item of (f.type==='choice'?f.options:f.cards)){const o=el('option',item);o.value=item;select.append(o);} select.value=c?.selection||'';label.append(select);parent.append(label);
    const reason=field(parent,'Reason (optional)',c?.reason||'',true), alternative=f.type==='structured_board'?field(parent,'Alternative (optional)',c?.alternative||'',true):null, getRefs=sourcePicker(parent,c?.refs||[]), consent=check(parent,'Share this contribution with the session');
    button(parent,c?'Save correction':'Share contribution',()=>{ if(!select.value||!consent.checked){status.textContent='Select an item and choose whether to share it.';return;} const body={selection:select.value,reason:reason.value.trim(),alternative:alternative?.value.trim()||'',refs:getRefs(),consent:true,formatRevision:f._revision,idempotencyKey:crypto.randomUUID()}; if(c) {body.revision=c._revision;mutate('w15EditContribution',body,c.id);} else mutate('w15ContributeFormat',body,f.id); });
  }
  function continuationPermission(parent, f, c, s) {
    const panel=el('details'); panel.append(el('summary','Permission for another creator to continue'));
    panel.append(el('p','This choice is separate from sharing your contribution in this session. You choose one receiving creator’s session. You can withdraw permission for that session. Your private notes are not included.'));
    panel.append(el('p',`Review your contribution, version ${c._revision}: ${c.selection}`),el('p',`Reason: ${c.reason||'None given'}`));
    if(c.alternative) panel.append(el('p',`Alternative: ${c.alternative}`));
    panel.append(el('p','Credit: your contribution is identified as yours here; no separate credit text is available.'),el('p','Permission does not grant rights to referenced sources or confirm what a future offer will contain.'));
    const target=field(panel,'Receiving creator session ID'), review=el('p'), result=el('p'); result.setAttribute('role','status'); result.setAttribute('aria-live','polite');
    let reviewed='';
    target.oninput=()=>{reviewed='';review.textContent='';result.textContent='';};
    button(panel,'Review recipient and contribution',()=>{const value=target.value.trim(); reviewed=value && value!==s.sessionId?value:''; review.textContent=reviewed?`Receiving session: ${reviewed}. Contribution: ${c.selection}. Reason: ${c.reason||'None given'}${c.alternative?' · Alternative: '+c.alternative:''}. Version ${c._revision}.`:'Enter a different receiving session ID.';});
    panel.append(review,result);
    button(panel,'Check exact permissions',async()=>{if(!scope||busy)return;const g=generation;busy=true;try{const r=await api.call('w15GetContinuationConsent',null,c.id,{scope:s});guard(s,g);if(!Array.isArray(r.consents))throw Error();const found=r.consents.filter(x=>x.targetSessionId===target.value.trim() && x.contributionRevision===c._revision);result.textContent=found.length?found.map(x=>`Permission ${x.id}: session ${x.targetSessionId}, contribution revision ${x.contributionRevision}: ${x.status} (permission revision ${x.revision}).`).join(' '):'No matching permission was returned for this target and contribution revision.';}catch{if(g===generation)result.textContent='Permission could not be checked with current access.';}finally{if(g===generation)busy=false;}});
    async function choose(allow) {
      if(!reviewed || reviewed!==target.value.trim()){result.textContent='Review the receiving session and contribution first.';return;}
      await mutate('w15ContinuationConsent',{revision:c._revision,targetSessionId:reviewed,allow},c.id);
    }
    button(panel,'Allow continuation',()=>choose(true)); button(panel,'Withdraw permission',()=>choose(false)); parent.append(panel);
  }
  function continuationWork(parent,f,cs,s) {
    const d=el('details');d.append(el('summary','Prepare reviewed continuation'),el('p','Source onward permission and each author’s target-specific contribution permission are separate from session sharing. Include all decision reasons and minority positions. The Studio draft must be reviewed and approved before an offer.'));
    const target=field(d,'Receiving creator session ID'), grantOut=el('div');
    button(d,'Read source permissions',async()=>{if(busy)return;const g=generation;busy=true;try{const r=await api.call('w15SourceGrants',null,f.id,{scope:s});guard(s,g);if(!Array.isArray(r.grants))throw Error();grantOut.replaceChildren();for(const x of r.grants){const row=el('p',`Permission ${x.id} · ${x.status} · target ${x.targetSessionId} · source ${x.ref?.sourceId} · moment ${x.ref?.momentId} · revision ${x.ref?.sourceRevision} `);if(x.status==='active')button(row,'Revoke',()=>mutate('w15RevokeSourceGrant',{revision:x._revision},f.id,x.id));grantOut.append(row);}}catch{if(g===generation)grantOut.textContent='Current source permissions unavailable.';}finally{if(g===generation)busy=false;}});d.append(grantOut);
    const getRefs=sourcePicker(d);button(d,'Permit selected source onward',()=>{const refs=getRefs();if(refs.length!==1||!target.value.trim()){status.textContent='Select exactly one current source and a receiving session.';return;}mutate('w15CreateSourceGrant',{revision:f._revision,targetSessionId:target.value.trim(),ref:refs[0]},f.id);});
    const grantIds=field(d,'Source permission IDs in unique source order, one per line','',true), chosen=[];
    for(const c of cs.filter(x=>x.status==='accepted')){const row=el('div');row.append(el('p',`${c.id} · ${c.selection} · ${c.reason||'No reason'}${f.decision?.minorityIds?.includes(c.id)?' · minority position':''}`));const include=check(row,'Include this accepted contribution'), consent=field(row,'Author permission ID for this exact revision and target');chosen.push({c,include,consent});d.append(row);}
    button(d,'Create editable Studio draft',()=>{const selected=chosen.filter(x=>x.include.checked), ids=new Set(selected.map(x=>x.c.id));if(!target.value.trim()||selected.some(x=>!x.consent.value.trim())||[...(f.decision?.reasonIds||[]),...(f.decision?.minorityIds||[])].some(x=>!ids.has(x))){status.textContent='Enter the target and exact author permissions, and include every decision and minority contribution.';return;}mutate('w15CreateFormatWork',{revision:f._revision,targetSessionId:target.value.trim(),contributions:selected.map(x=>({id:x.c.id,revision:x.c._revision,consentId:x.consent.value.trim()})),sourceGrantIds:grantIds.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean)},f.id);});
    const work=field(d,'Reviewed work ID'), material=field(d,'Approved Studio material ID'), version=field(d,'Exact approved version');version.type='number';version.min='1';
    button(d,'Offer exact approved work',()=>{const v=Number(version.value);if(!work.value.trim()||!material.value.trim()||!Number.isInteger(v)||v<1){status.textContent='Enter the work, approved material and exact version.';return;}mutate('w15OfferFormat',{revision:f._revision,workId:work.value.trim(),materialId:material.value.trim(),materialVersion:v},f.id);});parent.append(d);
  }
  function render() {
    const s=scope, author=q('[data-author]'); author.hidden=s.role!=='creator'; const create=q('[data-create-form]'); create.replaceChildren(); if(s.role==='creator'){const get=definitionForm(create);button(create,'Create choice or board',()=>{const d=get();if(d)mutate('w15CreateFormat',d);});}
    const host=q('[data-formats]'); if(!formats.length)host.append(el('p','No current choices or boards.'));
    for(const f of formats){if(!['choice','structured_board'].includes(f.type)||!Array.isArray(f.options)||!Array.isArray(f.cards))continue;const card=el('article');card.dataset.formatId=f.id;card.tabIndex=-1;card.append(el('h3',f.title),el('p',`${f.type==='choice'?'Choice':'Proposal board'} · revision ${f._revision}`),el('p',f.question)); const ul=el('ul');for(const item of (f.type==='choice'?f.options:f.cards))ul.append(el('li',item));card.append(ul);for(const r of f.refs||[])card.append(el('p',`Source ${r.sourceId} · moment ${r.momentId} · revision ${r.sourceRevision} · ${r.startMs}–${r.endMs} ms`));
      if(f.provenance)card.append(el('p',`Continued from session ${f.provenance.sourceSessionId}, version ${f.provenance.sourceRevision}. Your changes affect your own copy.`));
      if(f.decision)card.append(el('p',`Decision: ${f.decision.decision}`),el('p',`Consequence: ${f.decision.consequence}`));
      if(s.role==='viewer' || (s.role==='creator' && f.type==='structured_board')){const d=el('details');d.append(el('summary',s.role==='creator'?'Add a reason or alternative to a proposal':'Share a contribution'));contributionForm(d,f);card.append(d);}
      const cs=contributions.filter(c=>c.formatId===f.id); if(cs.length)card.append(el('h4',s.role==='creator'?'Review contributions':'Your and accepted contributions'));
      for(const c of cs){const row=el('section');row.append(el('p',`${c.selection} · ${c.status}${f.decision?.minorityIds?.includes(c.id)?' · minority position':f.decision?.reasonIds?.includes(c.id)?' · considered in decision':''}`),el('p',`Reason: ${c.reason||'None given'}`));if(c.alternative)row.append(el('p',`Alternative: ${c.alternative}`));for(const r of c.refs||[])row.append(el('p',`Source ${r.sourceId} · moment ${r.momentId} · revision ${r.sourceRevision}`));
        if(s.role==='creator'&&c.status==='pending')button(row,'Accept this contribution',()=>mutate('w15AcceptContribution',{revision:c._revision,formatRevision:f._revision},c.id));
        if(c.canEdit === true || c.isMine === true || (s.role==='viewer' && c.isMine === undefined && c.authorId===s.viewerId)){continuationPermission(row,f,c,s);const d=el('details');d.append(el('summary','Correct your contribution'));contributionForm(d,f,c);row.append(d);button(row,'Withdraw your contribution',()=>mutate('w15WithdrawContribution',{revision:c._revision},c.id));}card.append(row);}
      if(s.role==='creator'){const edit=el('details');edit.append(el('summary','Edit or adapt this format'));const get=definitionForm(edit,f);button(edit,'Save new revision',()=>{const d=get();if(d)mutate('w15EditFormat',{...d,revision:f._revision},f.id);});card.append(edit);
        const accepted=cs.filter(c=>c.status==='accepted');const decision=el('details');decision.append(el('summary','Record a decision and consequence'),el('p','Select the reasons considered and mark minority positions separately.'));const picks=[];for(const c of accepted){const group=el('div');group.append(el('p',`${c.selection}: ${c.reason||'No reason given'}${c.alternative?' · Alternative: '+c.alternative:''}`));const include=check(group,'Consider this contribution',f.decision?.reasonIds?.includes(c.id)),minor=check(group,'This is a minority position',f.decision?.minorityIds?.includes(c.id));picks.push({id:c.id,include,minor});decision.append(group);}const outcome=field(decision,'Decision',f.decision?.decision||'',true), consequence=field(decision,'Consequence',f.decision?.consequence||'',true);button(decision,'Save decision',()=>{if(!outcome.value.trim()||!consequence.value.trim()||picks.some(x=>x.minor.checked&&!x.include.checked)){status.textContent='Enter a decision and consequence; include each marked minority reason.';return;}mutate('w15FormatDecision',{revision:f._revision,reasonIds:picks.filter(x=>x.include.checked).map(x=>x.id),minorityIds:picks.filter(x=>x.minor.checked).map(x=>x.id),decision:outcome.value.trim(),consequence:consequence.value.trim()},f.id);});card.append(decision);
        continuationWork(card,f,cs,s);
      } host.append(card);
    }
    const out=q('[data-offers]');if(s.role==='creator')for(const t of transfers){const row=el('article');row.append(el('h3',t.sourceSessionId===s.sessionId?'Sent offer':'Received offer'),el('p',`Status: ${t.status} · source version ${t.sourceRevision}`));if(t.status==='offered'&&t.sourceSessionId===s.sessionId)button(row,'Withdraw offer',()=>mutate('w15WithdrawFormatTransfer',{revision:t._revision},t.id));if(t.status==='offered'&&t.targetSessionId===s.sessionId){const preview=el('div'); let reviewed=false; button(row,'Preview exact eligible offer',async()=>{if(busy)return;const g=generation;busy=true;reviewed=false;preview.replaceChildren();try{const r=await api.call('w15TransferPreview',null,t.id,{scope:s});guard(s,g);const x=r?.transfer;if(!x||x.id!==t.id||!x.formatSnapshot||!Array.isArray(x.contributionSnapshot)||!x.materialSnapshot||!x.snapshot)throw Error();preview.append(el('pre',JSON.stringify({format:x.formatSnapshot,contributions:x.contributionSnapshot,material:x.materialSnapshot,rights:x.snapshot},null,2)));reviewed=true;}catch{if(g===generation)preview.textContent='Current offer and rights could not be confirmed.';}finally{if(g===generation)busy=false;}});row.append(preview);button(row,'Accept and create editable draft',()=>{if(!reviewed){status.textContent='Preview the current eligible offer first.';return;}mutate('w15AcceptFormatTransfer',{revision:t._revision},t.id);});button(row,'Decline offer',()=>mutate('w15DeclineFormatTransfer',{revision:t._revision},t.id));}out.append(row);}
  }
  async function focusRound(formatId, roundId) {
    const s=identityScope();
    box.querySelector('details').open=true;
    await refresh();
    try {
      assertIdentity(s);
      const f=formats.find(x=>x.id===formatId && x.templateRoundId===roundId);
      if (!f) throw Error('round unavailable');
      const view=await api.call('w17TemplateRound',null,roundId,{scope:s});
      assertIdentity(s);
      if (!scope || scope.epoch!==s.epoch || view?.format?.id!==formatId || view?.round?.id!==roundId) throw Error('stale');
      const card=[...q('[data-formats]').children].find(x=>x.dataset.formatId===formatId);
      if (!card) throw Error('round unavailable');
      const stage=el('p',`Current round stage: ${view.round.stage}. Participation, review and decisions are available at their corresponding stages; authors may withdraw.`);
      card.prepend(stage); card.focus(); card.scrollIntoView?.({block:'nearest'});
    } catch { status.textContent='This round or its current stage could not be confirmed. Refresh before acting.'; }
  }
  async function focusFormat(id){const s=identityScope();box.querySelector('details').open=true;await refresh();assertIdentity(s);const card=[...q('[data-formats]').children].find(x=>x.dataset.formatId===id);if(!card)throw Error('Format unavailable');card.focus();card.scrollIntoView?.({block:'nearest'});}
  q('[data-refresh]').onclick=refresh; return {reset,invalidate,refresh,focusRound,focusFormat};
}
