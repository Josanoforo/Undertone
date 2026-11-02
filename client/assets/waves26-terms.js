/** Standalone creator view over the released M02 terminology inspection DTO. */
const STATES = new Set(['absent', 'draft', 'approved', 'disabled']);
const COVERAGE = 'partial_actor_owned_phase12_queued_running_only';

/** Validate and normalize the actual M02_TERMS26 DTO without changing literal content. */
export function termsViewFromDTO(dto) {
  if (!dto || !STATES.has(dto.state) || !['partial_actor_owned_phase12_queued_running_only', 'unknown'].includes(dto.coverage)) throw new TypeError('Invalid terminology inspection');
  for (const key of ['recordRevision', 'approvedRevision', 'draftRevision']) {
    if (dto[key] !== null && (!Number.isSafeInteger(dto[key]) || dto[key] < 0)) throw new TypeError('Invalid terminology revision');
  }
  if (!Array.isArray(dto.terms) || !Array.isArray(dto.context) || !Array.isArray(dto.applications)) throw new TypeError('Incomplete terminology inspection');
  const terms = dto.terms.map(term => {
    if (!term || typeof term.id !== 'string' || typeof term.original !== 'string' || typeof term.translated !== 'string' || !Array.isArray(term.alternatives) || !Array.isArray(term.pronunciations)) throw new TypeError('Invalid term');
    return { id: term.id, original: term.original, translated: term.translated,
      alternatives: term.alternatives.slice(), ambiguity: term.ambiguity,
      pronunciations: term.pronunciations.map(rule => {
        if (!rule || typeof rule.id !== 'string' || typeof rule.language !== 'string' || typeof rule.term !== 'string' || typeof rule.alias !== 'string' || typeof rule.approved !== 'boolean') throw new TypeError('Invalid pronunciation');
        return {...rule};
      }) };
  });
  const context = dto.context.map(ref => {
    if (!ref || typeof ref.id !== 'string' || typeof ref.text !== 'string' || !ref.ref || typeof ref.ref !== 'object' || Array.isArray(ref.ref)) throw new TypeError('Invalid context reference');
    return {...ref};
  });
  const applications = dto.applications.map(app => {
    if (!app || app.kind !== 'phase12_translation' || typeof app.requestId !== 'string' || !['queued', 'running'].includes(app.state) || !['current', 'stale'].includes(app.relation) || !Number.isSafeInteger(app.terminologyRevision) || app.terminologyRevision < 0) throw new TypeError('Invalid terminology application');
    return {...app};
  });
  const completedResults = (dto.completedResults || []).map(app => {
    if (!app || app.kind !== 'phase12_translation' || app.state !== 'complete' || typeof app.requestId !== 'string' || !['current','stale'].includes(app.relation) || !Number.isSafeInteger(app.terminologyRevision)) throw new TypeError('Invalid completed terminology result');
    return {...app};
  });
  const registeredApplications = (dto.registeredApplications || []).map(app => {
    if (!app || app.kind !== 'wave20_private_delivery' || typeof app.reference !== 'string' || typeof app.source !== 'string' || !['current','stale'].includes(app.relation)) throw new TypeError('Invalid registered terminology application');
    return {...app};
  });
  let pronunciation = null;
  if (dto.pronunciation !== null) {
    if (!dto.pronunciation || typeof dto.pronunciation.ruleSetId !== 'string' || !Number.isSafeInteger(dto.pronunciation.revision) || dto.pronunciation.revision < 0) throw new TypeError('Invalid pronunciation authority');
    pronunciation = {...dto.pronunciation};
  }
  return {state:dto.state, recordRevision:dto.recordRevision, approvedRevision:dto.approvedRevision,
    draftRevision:dto.draftRevision, terms, context, pronunciation, applications, completedResults, registeredApplications,
    registeredCoverage:dto.registeredCoverage || 'unavailable',
    coverage:dto.coverage === COVERAGE ? 'partial' : 'unknown'};
}

/**
 * Host: {scope:{actorId,role,sourceId,sourceRevision,rightsGeneration}, snapshot?,
 * pronunciationRuleSetId?:string, inspect:(ruleSetId?:string)=>Promise<M02 inspection DTO>, assertScope:(scope)=>void,
 * openApplication?:(requestId,scope)=>void, openEditor?:(ruleSetId|null,scope)=>void}.
 * `inspect` must be the normal creator-authorized host binding. Callbacks run only
 * on explicit button activation; this component never approves or reprocesses.
 */
export function mountTerms(root, initialHost) {
  if (!root || typeof root.append !== 'function') throw new TypeError('A root element is required');
  let host=initialHost, scope=host?.scope && {...host.scope}, epoch=0, busy=false, activeTicket=null, destroyed=false, model=null;
  const el=(tag, value)=>{const n=document.createElement(tag); if(value!==undefined)n.textContent=String(value); return n;};
  const section=el('section'); section.className='w26-terms'; section.setAttribute('aria-labelledby','w26-terms-title');
  const heading=el('h2','Channel terminology'); heading.id='w26-terms-title';
  const status=el('p','Terminology is not loaded.'); status.setAttribute('role','status'); status.setAttribute('aria-live','polite'); status.tabIndex=-1;
  const body=el('div'); section.append(heading,status,body); root.append(section);
  const validScope=s=>s && s.role==='creator' && ['actorId','sourceId'].every(k=>typeof s[k]==='string'&&s[k].length>0) && ['sourceRevision','rightsGeneration'].every(k=>Number.isSafeInteger(s[k])&&s[k]>=0);
  const sameScope=(a,b)=>validScope(a)&&validScope(b)&&['actorId','role','sourceId','sourceRevision','rightsGeneration'].every(k=>a[k]===b[k]);
  function clear(message){const focused=body.contains(document.activeElement);epoch++;model=null;body.replaceChildren();status.textContent=message;if(focused)status.focus();}
  function render(){
    const focused=body.contains(document.activeElement);body.replaceChildren(); if(!model)return;
    body.append(el('p',`Lifecycle: ${model.state}. Record revision: ${model.recordRevision===null?'unknown':model.recordRevision}; approved revision: ${model.approvedRevision===null?'unknown':model.approvedRevision}; draft revision: ${model.draftRevision===null?'unknown':model.draftRevision}.`));
    if(model.state==='approved'&&model.approvedRevision!==null){
      const list=el('ul');
      for(const term of model.terms){
        const item=el('li'); item.append(el('strong',term.original),el('span',` → ${term.translated}`));
        for(const alternative of term.alternatives){if(!alternative||typeof alternative.en!=='string'||typeof alternative.es!=='string')throw new TypeError('Invalid alternative');item.append(el('span',` (Alternative: ${alternative.en} → ${alternative.es})`));}
        if(term.ambiguity!==null&&term.ambiguity!==undefined)item.append(el('span',` Context note: ${term.ambiguity}`));
        const bindings=[...model.applications,...model.completedResults].filter(app=>app.termIds?.includes(term.id));
        item.append(el('p', bindings.length ? `Bound work: ${bindings.map(app=>`${app.requestId}${app.literalMatchTermIds?.includes(term.id)?' (literal source match)':''}`).join(', ')}.` : 'No visible job binding for this term. Other actors and hidden work are excluded.'));
        list.append(item);
      }
      body.append(el('h3','Approved terms'),list);
    } else body.append(el('p',model.state==='disabled'?'Terminology is disabled. No terms are currently applicable.':model.state==='draft'?'A draft exists. Draft wording is withheld from this view.':'No approved terminology record is available.'));
    const pronunciation=el('section'); pronunciation.append(el('h3','Approved pronunciation'));
    if(model.pronunciation){pronunciation.append(el('p',`Separate pronunciation rule set revision ${model.pronunciation.revision}.`));const list=el('ul');for(const term of model.terms)for(const rule of term.pronunciations)if(rule.approved)list.append(el('li',`${term.original}: ${rule.alias} (${rule.language})`));if(!list.childNodes.length)pronunciation.append(el('p','No approved pronunciation rules are included in this inspection.'));else pronunciation.append(list);}
    else pronunciation.append(el('p','Pronunciation coverage is unknown; no separate approved rule set was selected.'));
    body.append(pronunciation);
    body.append(el('h3','Where this terminology applies'));
    if(model.applications.length || model.completedResults.length){const list=el('ul');for(const app of [...model.applications,...model.completedResults]){const li=el('li');li.append(el('span',`${app.kind} ${app.requestId}: ${app.state}, ${app.relation} at terminology revision ${app.terminologyRevision}.`));if(app.source)li.append(el('p',`Exact source reference: ${JSON.stringify(app.source)}`));if(app.relation==='stale')li.append(el('p',`${app.state==='complete'?'Review this completed result':'Review this pending work'} against the corrected glossary before explicitly preparing any replacement. Changed terms: ${(app.changedTermIds||[]).join(', ')||'none; inspect context or approval'}${app.contextChanged?'; context or approval changed':''}.`));if(typeof host.openApplication==='function'){const button=el('button','Open authorized application');button.type='button';button.addEventListener('click',()=>explicit(()=>host.openApplication(app.requestId,{...scope})));li.append(button);}list.append(li);}body.append(list);}
    else body.append(el('p','No eligible application is visible in this partial inspection. This does not mean there are no other applications.'));
    body.append(el('p',model.coverage==='partial'?'Coverage is partial: this creator’s visible queued, running and completed Phase 12 translations. Valid results are retained; nothing is regenerated here. Other actors and rights-suppressed work are excluded.':'Coverage is unknown; absence of listed applications is not evidence that none exist.'));
    body.append(el('h3','Registered delivery and preparation'));
    for(const app of model.registeredApplications)body.append(el('p',`Source ${app.source}, revision ${app.sourceRevision}: ${app.state}; ${app.relation} glossary revision ${app.terminologyRevision}. ${app.relation==='stale'?'Review this registered work before explicit replacement.':'Retain valid prepared work.'}`));
    body.append(el('p',model.registeredCoverage==='unavailable'?'Registered delivery coverage is unavailable. An empty list does not establish that no work needs review.':'Registered delivery coverage is partial and limited to this actor’s current authorized registrations.'));
    for(const ref of model.context)body.append(el('p',`Context reference ${ref.id}: ${ref.text}`));
    if(typeof host.openEditor==='function'){const button=el('button','Open existing creator terminology editor');button.type='button';button.addEventListener('click',()=>explicit(()=>host.openEditor(model?.pronunciation?.ruleSetId??null,{...scope})));body.append(button);}
    if(focused)status.focus();
  }
  function explicit(effect){if(destroyed||busy||!sameScope(scope,host?.scope)||typeof host?.assertScope!=='function')return;try{host.assertScope({...scope});effect();}catch(_){clear('Access changed. Terminology details are unavailable.');}}
  function accept(dto,ticket,captured,owner){if(destroyed||ticket!==epoch||owner!==host||!sameScope(captured,host?.scope))return false;try{host.assertScope({...captured});model=termsViewFromDTO(dto);render();status.textContent='Current authorized terminology inspection loaded.';return true;}catch(_){clear('Terminology details are unavailable or no longer current.');return false;}}
  function load(){if(destroyed||busy||!sameScope(scope,host?.scope)||typeof host?.inspect!=='function'||typeof host?.assertScope!=='function'){clear('Creator authorized terminology inspection is unavailable.');return;}const ticket=++epoch,captured={...scope},owner=host,ruleId=rules.value.trim();if(ruleId&&!/^[A-Za-z0-9._:-]{1,128}$/.test(ruleId)){clear('Enter a valid pronunciation rule set ID.');return;}busy=true;activeTicket=ticket;status.textContent='Loading current terminology…';try{host.assertScope(captured);}catch(_){busy=false;activeTicket=null;clear('Access changed. Terminology details are unavailable.');return;}Promise.resolve().then(()=>owner.inspect(ruleId||undefined)).then(dto=>accept(dto,ticket,captured,owner)).catch(()=>{if(!destroyed&&ticket===epoch&&owner===host)clear('Terminology could not be loaded. No change was made.');}).finally(()=>{if(!destroyed&&activeTicket===ticket){busy=false;activeTicket=null;}});}
  const ruleLabel=el('label','Approved pronunciation rule set ID (optional) '),rules=el('input');rules.maxLength=128;rules.value=host?.pronunciationRuleSetId||'';ruleLabel.append(rules);section.insertBefore(ruleLabel,status);
  rules.addEventListener('input',()=>{busy=false;activeTicket=null;clear('Pronunciation selection changed. Refresh to inspect it.');});
  const refresh=el('button','Refresh current terminology');refresh.type='button';refresh.addEventListener('click',load);section.insertBefore(refresh,status);
  if(host?.snapshot&&sameScope(scope,host?.scope)){try{model=termsViewFromDTO(host.snapshot);render();status.textContent='Current authorized terminology inspection loaded.';}catch(_){clear('Terminology details are unavailable or no longer current.');}}
  function update(next){if(destroyed)return;epoch++;busy=false;activeTicket=null;host=next;rules.value=next?.pronunciationRuleSetId||'';const changed=!sameScope(scope,next?.scope);scope=next?.scope&&{...next.scope};clear(changed?'Context or access changed. Refresh to inspect current terminology.':'Refresh to inspect current terminology.');if(next?.snapshot&&sameScope(scope,next?.scope)){try{model=termsViewFromDTO(next.snapshot);render();}catch(_){clear('Terminology details are unavailable or no longer current.');}}}
  return {refresh:load,update,reset(){busy=false;activeTicket=null;rules.value='';clear('Terminology details are unavailable.');},destroy(){destroyed=true;busy=false;activeTicket=null;epoch++;body.replaceChildren();section.remove();model=null;host=null;}};
}
