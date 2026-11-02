const sourceRefKeys=['sessionId','sourceId','momentId','sourceRevision','startMs','endMs'];
const canonical=x=>Array.isArray(x)?x.map(canonical):x && typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
const same=(a,b)=>JSON.stringify(canonical(a))===JSON.stringify(canonical(b));

export function buildSegmentListeningContext(segment, ref, moment) {
  if (!segment || segment.dependencyState !== 'current' || !moment || !same(ref, moment.ref) || !sourceRefKeys.every(k=>ref?.[k]!==null&&ref?.[k]!==undefined)) return null;
  if (typeof ref.sessionId!=='string' || typeof ref.sourceId!=='string' || typeof ref.momentId!=='string' || !Number.isSafeInteger(ref.sourceRevision) || !Number.isSafeInteger(ref.startMs) || !Number.isSafeInteger(ref.endMs) || ref.endMs<=ref.startMs) return null;
  return {segmentId:segment.id,segmentRevision:segment._revision,segmentState:segment.state,dependencyState:segment.dependencyState,sourceRef:{...ref},sourceLabel:[moment.title,moment.text].filter(Boolean).join(' — ')||'Source moment',sourceLanguage:null};
}

const listeningRefKey=ref=>ref&&sourceRefKeys.map(k=>[k,ref[k]]);
export const sameListeningRef=(a,b)=>JSON.stringify(listeningRefKey(a))===JSON.stringify(listeningRefKey(b));

// Stamp only the focusCaptions scope captured synchronously by that call.
// Phase 12 checks assertIdentity after its catalog refresh and before select().
export function createSegmentListeningFence(identityScope, assertIdentity, assertSavedIdentity=assertIdentity) {
  let generation=0, activeStamp=null, contextKey=null, contextRecord=null, active=false, ownedRefs=[];
  const stamp=Symbol('segment-listening-generation');
  const check=(base, scope)=>{base(scope);const captured=scope?.[stamp];if(captured!==undefined&&captured!==generation)throw Error('Listening context changed');};
  const ownsContext=context=>!!contextRecord&&context?.dependencyState==='current'&&context.segmentId===contextRecord.id&&context.segmentRevision===contextRecord.segmentRevision&&contextRecord.dependencyState==='current'&&contextRecord.refs.some(ref=>sameListeningRef(ref,context.sourceRef));
  return {
    identityScope(){const scope=identityScope();if(activeStamp!==null)Object.defineProperty(scope,stamp,{value:activeStamp});return scope;},
    assertIdentity:scope=>check(assertIdentity,scope),
    assertSavedIdentity:scope=>check(assertSavedIdentity,scope),
    get generation(){return generation;},
    invalidate(){generation++;activeStamp=null;ownedRefs=[];active=false;return generation;},
    get hasActiveContext(){return active;},
    owns(ref){return active&&ownedRefs.some(owned=>sameListeningRef(owned,ref));},
    isCurrent(context){return ownsContext(context)&&active&&sameListeningRef(ownedRefs.at(-1),context.sourceRef);},
    setContext(context){const next=context?JSON.stringify(canonical({id:context.id,segmentRevision:context.segmentRevision,dependencyState:context.dependencyState,sources:(context.sources||[]).map(x=>x.ref).sort((a,b)=>JSON.stringify(listeningRefKey(a)).localeCompare(JSON.stringify(listeningRefKey(b))))})):null;if(next===contextKey)return {changed:false,stopPrevious:false};const stopPrevious=active;contextKey=next;contextRecord=context?{id:context.id,segmentRevision:context.segmentRevision,dependencyState:context.dependencyState,refs:(context.sources||[]).map(x=>x.ref)}:null;this.invalidate();return {changed:true,stopPrevious};},
    async open(context, focus){
      if(!context||context.dependencyState!=='current'||!context.sourceRef||!ownsContext(context))throw Error('Current source required');
      const captured=++generation, base=identityScope();assertIdentity(base);
      const scoped={...base};Object.defineProperty(scoped,stamp,{value:captured});
      check(assertIdentity,scoped);
      activeStamp=captured;active=true;ownedRefs.push({...context.sourceRef});let pending;try{pending=focus(context.sourceRef);}finally{activeStamp=null;}
      await pending;
      check(assertIdentity,scoped);
      if(generation!==captured||!ownsContext(context)||!this.isCurrent(context))throw Error('Listening context changed');
      return {scope:base,sourceRef:{...context.sourceRef}};
    }
  };
}

export function readListeningControls(root) {
  const labels=[...(root?.querySelectorAll?.('label')||[])];
  const languageLabel=labels.find(x=>/^Caption language\b/i.test(x.textContent.trim()));
  const engineLabel=labels.find(x=>/^Speech engine\b/i.test(x.textContent.trim()));
  const language=languageLabel?.querySelector('select'), engine=engineLabel?.querySelector('select');
  const options=engine?[...engine.options].filter(x=>x.value).map(x=>({id:x.value,label:x.textContent,disabled:x.disabled})):[];
  return {targetLanguage:language?.selectedOptions?.[0]?.textContent||null,engine:engine?.value||null,options,loaded:options.length>0};
}

export function mountSegment(root, api, identityScope, assertIdentity, actions = {}) {
  const box=document.createElement('section'); box.className='w18-segment';
  box.innerHTML='<h2>Segment workspace</h2><p>Creator review controls each step. Drafts are deterministic excerpts; nothing is approved or presented automatically.</p><p role="status" aria-live="polite" data-status></p><div data-recovery></div><div data-content></div>';
  root.append(box); const status=box.querySelector('[data-status]'), content=box.querySelector('[data-content]'), recovery=box.querySelector('[data-recovery]');
  let scope=null, generation=0, busy=false, options=null, segments=[], selected=null, receipt=null, discovery=null;
  const node=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  const button=(parent,label,fn,disabled=false)=>{const b=node('button',label), captured=scope, ticket=generation;b.type='button';b.disabled=disabled||(label==='Save edited draft'&&journalMode()==='memory');b.onclick=()=>{try{if(captured)guard(captured,ticket);}catch{return;}return fn();};parent.append(b);return b;};
  const field=(parent,label,value='',multi=false)=>{const l=node('label',label), i=node(multi?'textarea':'input');i.value=value;l.append(i);parent.append(l);return i;};
  const check=(parent,label)=>{const l=node('label'), i=node('input');i.type='checkbox';l.append(i,document.createTextNode(' '+label));parent.append(l);return i;};
  const notify=value=>{try { actions.onContextChanged?.(value); } catch { /* host callback cannot change server state */ }};
  const clear=()=>{content.replaceChildren();recovery.replaceChildren();options=null;segments=[];selected=null;discovery=null;notify(null);};
  function reset(){generation++;busy=false;scope=null;receipt=null;memoryJournal.clear();clear();status.textContent='Refresh to load the current creator workspace.';}
  // Tab-only access is opt-in and never falls back to a saved journal.
  // The host must also provide durable original-operation discovery before
  // enabling this mode; memory alone cannot recover a reload.
  const memoryJournal=new Map();
  const journalMode=()=>actions.journalMode?.() === 'memory' ? 'memory' : 'saved';
  const key=s=>`w18-segment:${s.sessionId}:${s.actorBinding}`;
  const load=s=>{try{if(journalMode()==='memory')return memoryJournal.get(key(s))||null;const x=localStorage.getItem(key(s));return x?JSON.parse(x):null;}catch{return {invalid:true};}};
  const guard=(s,g)=>{if(g!==generation)throw Error('stale');assertIdentity(s);};
  const valid=s=>s?.role==='creator'&&s.sessionId&&s.token&&s.actorBinding;
  const own=(p,s)=>p?.version===1&&p.sessionId===s.sessionId&&p.actorBinding===s.actorBinding&&p.body?.requestId&&['w18SegmentCreate','w18SegmentAction'].includes(p.operation)&&Array.isArray(p.args);
  const call=async(op,body,args,s,g)=>{guard(s,g);const r=await api.call(op,body,...args,{scope:s});guard(s,g);return r;};
  const save=(s,p)=>{if(journalMode()==='memory')memoryJournal.set(key(s),p);else localStorage.setItem(key(s),JSON.stringify(p));};
  const forget=s=>{if(journalMode()==='memory')memoryJournal.delete(key(s));else localStorage.removeItem(key(s));};
  function failedIdentity(s,g){if(g!==generation)return true;try{assertIdentity(s);return false;}catch{reset();status.textContent='Identity changed; protected workspace data was cleared.';return true;}}
  function labelSignal(x){return x.kind==='question' ? (x.text||'Shared question') : [x.selection||'Accepted contribution',x.reason].filter(Boolean).join(' — ');}
  function signalOptions(){return [...(options?.questions||[]).filter(x=>['shared','selected'].includes(x.status)).map(x=>({...x,kind:'question'})),...(options?.contributions||[]).filter(x=>x.status==='accepted').map(x=>({...x,kind:'contribution'}))];}
  function publishContext(){if(!selected || selected.dependencyState!=='current'){notify(null);return;}const sources=(selected.refs||[]).map(ref=>{const m=(options?.moments||[]).find(x=>same(x.ref,ref));return m?{ref,label:[m.title,m.text].filter(Boolean).join(' — ')}:null;});const signals=(selected.signals||[]).map(sig=>{const x=signalOptions().find(v=>v.kind===sig.kind&&v.id===sig.id&&v._revision===sig.revision);return x?{...sig,label:labelSignal(x)}:null;});if(sources.some(x=>!x)||signals.some(x=>!x)){notify(null);return;}notify({id:selected.id,label:selected.title,segmentRevision:selected._revision,dependencyState:selected.dependencyState,sources,signals});}
  async function readReceipt(s,p,g){const r=await call('w18SegmentOperation',null,[p.body.requestId],s,g);if(r?.operation?.requestId!==p.body.requestId||typeof r.operation.state!=='string')throw Error('Invalid receipt');return r.operation;}
  async function discover(s,id,g){
    const r=await call('w18SegmentPendingOperations',null,[id],s,g);
    if(typeof r?.incomplete!=='boolean'||!Array.isArray(r.operations)||r.operations.length>50||r.operations.some(x=>!x||typeof x.requestId!=='string'||!/^[A-Za-z0-9._:-]{1,128}$/.test(x.requestId)||!['pending','unknown'].includes(x.state)||typeof x.action!=='string')) throw Error('Invalid recovery metadata');
    return r;
  }
  function discoveredUI(){
    if(journalMode()!=='memory'||!selected)return;
    if(!discovery){recovery.append(node('p','Original operation recovery is unavailable. Changes are blocked.'));return;}
    if(discovery.incomplete)recovery.append(node('p','Some original requests cannot be identified. Changes remain blocked; do not repeat them.'));
    for(const item of discovery.operations){
      recovery.append(node('p',`Original ${item.action} request: ${item.state}.`));
      button(recovery,'Check original request receipt',async()=>{if(busy)return;const s=scope,g=generation,id=selected.id;busy=true;try{const r=await call('w18SegmentOperation',null,[item.requestId],s,g);if(r?.operation?.requestId!==item.requestId||typeof r.operation.state!=='string')throw Error('Invalid receipt');busy=false;await refresh(id);}catch{if(!failedIdentity(s,g))status.textContent='Original receipt unavailable; changes remain blocked.';}finally{if(g===generation)busy=false;}});
    }
  }
  function recoveryUI(p){recovery.replaceChildren();discoveredUI();if(!p)return;if(!own(p,scope)){recovery.append(node('p','Saved recovery data cannot be verified for this identity. Changes are blocked.'));return;}
    const action=p.body.action||'create';recovery.append(node('p',`Saved ${action} request: ${receipt?.state||'not yet checked'}. Its outcome may be unknown.`));
    button(recovery,'Check saved request receipt',async()=>{if(busy)return;const s=scope,g=generation;busy=true;try{receipt=await readReceipt(s,p,g);busy=false;recoveryUI(p);status.textContent='Receipt checked. A receipt is not proof of a visible OBS result.';}catch{if(!failedIdentity(s,g))status.textContent='Receipt unavailable; the saved request remains blocked.';}finally{if(g===generation)busy=false;}});
    if(receipt && ['committed','resolved'].includes(receipt.state)) button(recovery,'Accept confirmed receipt and refresh',()=>{const target=p.args[0] || receipt?.segmentId;forget(scope);receipt=null;refresh(target);},busy);
    if(journalMode()==='saved' && receipt && ['create','select','compose','close','prepare_cue'].includes(action)) button(recovery,'Replay exact saved request',()=>replay(p),busy);
    if(['edit','approve'].includes(action)) { recovery.append(node('p','Studio edit or approval may have happened. Preserved request and draft require operator reconciliation; no automatic or exact retry is offered.')); if(action==='edit'){recovery.append(node('p','Preserved unsent-or-unconfirmed edit:'),node('p',p.body.title),node('pre',p.body.body));} }
    if(journalMode()==='saved' && action==='present' && selected?.id===p.args[0] && selected.cueId) button(recovery,'Withdraw matching cue',()=>mutate('withdraw_cue',{},true),busy);
  }
  async function replay(p){if(busy||!scope)return;const s=scope,g=generation;busy=true;clear();status.textContent='Reading receipt before exact replay…';try{const op=await readReceipt(s,p,g);guard(s,g);if(['edit','approve'].includes(p.body.action))throw Error('reconcile');const r=await call(p.operation,p.body,p.args,s,g);guard(s,g);if(!r?.operation||!r.segment)throw Error('response');if(['committed','resolved'].includes(r.operation.state)){forget(s);receipt=null;selected=r.segment;status.textContent='Saved request confirmed. Refreshing current rights.';}else{receipt=op;status.textContent='Outcome remains unknown; no new external effect was dispatched by exact replay.';}busy=false;await refresh(r.segment.id);}catch{if(!failedIdentity(s,g)){status.textContent='Recovery is unconfirmed. The exact saved request remains preserved.';busy=false;await refresh(p.args[0]);}}finally{if(g===generation)busy=false;}}
  async function mutate(action,extra={},withdraw=false){if(!scope||busy)return;const s=scope,g=generation;try{guard(s,g);}catch{reset();return;}const prior=load(s);if(prior&&!(withdraw&&own(prior,s)&&prior.body.action==='present'&&prior.args[0]===selected?.id)){status.textContent='Resolve the saved request before another change.';return;}if(action!=='create'&&!selected)return;
    if(journalMode()==='memory'){
      if(action==='edit'){status.textContent='Editing a draft requires saved access for recovery.';return;}
      if(action==='create'){status.textContent='Creating a segment requires saved access for recovery.';return;}
      const id=selected.id; busy=true;
      try{const current=await discover(s,id,g);guard(s,g);if(!selected||selected.id!==id||current.incomplete||current.operations.length){discovery=current;busy=false;render();status.textContent='Resolve original requests before another change.';return;}}
      catch{if(!failedIdentity(s,g)){discovery=null;busy=false;render();status.textContent='Original operation recovery is unavailable; nothing was sent. Refresh before trying again.';}return;}
      finally{if(g===generation)busy=false;}
    }
    const body=action==='create'?{requestId:crypto.randomUUID(),title:extra.title}:{requestId:crypto.randomUUID(),revision:selected._revision,action,...extra};const p={version:1,sessionId:s.sessionId,actorBinding:s.actorBinding,operation:action==='create'?'w18SegmentCreate':'w18SegmentAction',args:action==='create'?[]:[selected.id],body,prior:withdraw?prior:null};
    try{save(s,p);}catch{status.textContent='Recovery storage unavailable; nothing was sent.';return;}busy=true;clear();status.textContent='Sending explicit creator action…';
    try{const r=await call(p.operation,p.body,p.args,s,g);guard(s,g);if(!r?.operation||!r.segment)throw Error('response');if(r.operation.state==='committed'){forget(s);receipt=null;status.textContent=action==='withdraw_cue'?'Withdrawal confirmed by the service; OBS visibility is not established here.':'Action confirmed. Refreshing current rights.';}else{receipt=null;status.textContent='Action outcome is unknown; check its receipt.';}busy=false;await refresh(r.segment.id);}catch(e){if(failedIdentity(s,g))return;const code=e?.code||e?.error?.code;status.textContent=`Action outcome is unconfirmed${code?' ('+code+')':''}. Check its receipt before recovery.`;busy=false;await refresh(p.args[0]);}finally{if(g===generation)busy=false;}}
  function render(){content.replaceChildren();if(!scope)return;const pending=load(scope);recoveryUI(pending);button(content,'Refresh workspace and permissions',()=>refresh(selected?.id));
    const create=node('fieldset');create.append(node('legend','Create a segment'));const title=field(create,'Segment title');title.maxLength=160;button(create,'Create segment',()=>{if(!title.value.trim()){status.textContent='Enter a segment title.';return;}mutate('create',{title:title.value});},!!pending||journalMode()==='memory');if(journalMode()==='memory')create.append(node('p','Creating a segment requires saved access for recovery.'));content.append(create);
    const chooser=node('label','Current segment');const select=node('select');select.append(new Option('Choose a segment',''));for(const x of segments)select.append(new Option(`${x.title} · ${x.state}`,x.id));select.value=selected?.id||'';select.onchange=()=>refresh(select.value);chooser.append(select);content.append(chooser);
    if(!selected){content.append(node('p','Choose a segment to continue.'));return;}const x=selected;content.append(node('h3',x.title),node('p',`Workspace: ${x.state} · revision ${x._revision}`));
    const stale=x.dependencyState==='unavailable'||(x.material && x.material.dependencyState && x.material.dependencyState!=='current');if(stale){notify(null);content.append(node('p','Sources or consent are unavailable. Derived content is suppressed. Refresh permissions or start a new segment.'));if(x.cueId&&x.state!=='closed')button(content,'Withdraw cue',()=>mutate('withdraw_cue'),!!pending||(journalMode()==='memory'&&(!discovery||discovery.incomplete||discovery.operations.length>0)));return;}
    publishContext();
    const listening=node('fieldset');listening.className='w18-segment-listening';listening.append(node('legend','Listening context'));
    const selectedMoments=(x.refs||[]).map(ref=>({ref,moment:(options?.moments||[]).find(m=>same(m.ref,ref))}));
    if(actions.openListening){
      const availability=node('div');
      const refreshListeningControls=()=>{
        const controls=actions.readListeningControls?.()||null, engines=controls?.options||[];
        availability.replaceChildren(node('p', 'Target listening language: '+(controls?.targetLanguage||'unknown')+'; current selection is left unchanged. Opening listening does not translate, synthesize, or start audio.'));
        if(controls?.loaded){
          for(const option of engines)availability.append(node('p', option.label+(option.label.toLowerCase().includes('(unavailable)')?' (reported unavailable)':option.disabled?' (unconfirmed; unavailable to choose)':'')));
          if(!engines.some(x=>x.id==='elevenlabs'&&!x.disabled))availability.append(node('p','Hosted speech is unavailable here. Choose an available speech option or try again later.'));
        }else availability.append(node('p','Speech options are unconfirmed. Load available options before choosing how to listen.'));
      };
      refreshListeningControls();listening.append(availability);
      button(listening,'Refresh listening options display',refreshListeningControls);
    }
    for(const {ref,moment} of selectedMoments){
      const context=buildSegmentListeningContext(x,ref,moment);
      if(!context){listening.append(node('p','A selected source is no longer current. Refresh permissions before opening listening.'));continue;}
      listening.append(node('p', context.sourceLabel+' · source revision '+ref.sourceRevision+' · interval '+ref.startMs+'-'+ref.endMs+' ms · source language unknown · segment '+context.segmentState+' · segment revision '+context.segmentRevision));
      if(actions.openListening){
        const open=async()=>{
          const ticket=generation,captured=scope;
          try{guard(captured,ticket);if(selected?.id!==context.segmentId||selected?._revision!==context.segmentRevision||selected?.dependencyState!=='current')throw Error('stale');await actions.openListening(context,captured);if(generation!==ticket||selected?.id!==context.segmentId||selected?._revision!==context.segmentRevision)return;}
          catch{if(generation===ticket&&selected?.id===context.segmentId&&selected?._revision===context.segmentRevision)status.textContent='Listening could not be opened. Your segment and draft are unchanged. Retry with the current source.';}
        };
        button(listening,'Open listening for this source',open);
        button(listening,'Retry listening for this source',open);
      }else listening.append(node('p','Listening is unavailable from this workspace.'));
    }
    if(!selectedMoments.length)listening.append(node('p','Select a current source before opening listening.'));
    content.append(listening);
    if(x.state==='closed'){content.append(node('p','Closed. Closure alone does not prove presentation or withdrawal.'));return;}
    const locked=!!pending||(journalMode()==='memory'&&(!discovery||discovery.incomplete||discovery.operations.length>0));const hasMaterial=!!x.materialId;
    if(!hasMaterial){const fs=node('fieldset');fs.append(node('legend','Select current sources and voluntary participation'));const moments=(options?.moments||[]).map(m=>({m,c:check(fs,[m.title,m.text].filter(Boolean).join(' — ')||'Source moment')}));for(const z of moments)z.c.checked=(x.refs||[]).some(r=>same(r,z.m.ref));const sigs=signalOptions().map(v=>({v,c:check(fs,`${v.kind==='question'?'Shared question':'Accepted contribution'}: ${labelSignal(v)}`)}));for(const z of sigs)z.c.checked=(x.signals||[]).some(s=>s.kind===z.v.kind&&s.id===z.v.id&&s.revision===z.v._revision);if(!moments.length)fs.append(node('p','No currently eligible source moments.'));button(fs,'Save selected context',()=>{const refs=moments.filter(z=>z.c.checked).map(z=>z.m.ref),signals=sigs.filter(z=>z.c.checked).map(z=>({kind:z.v.kind,id:z.v.id,revision:z.v._revision}));if(!refs.length||refs.length>20||signals.length>20){status.textContent='Select 1–20 sources and at most 20 contributions or questions.';return;}mutate('select',{refs,signals});},locked);if(actions.openQuestions)button(fs,'Open question controls',()=>actions.openQuestions());if(actions.openParticipation)button(fs,'Open participation controls',()=>actions.openParticipation());content.append(fs);button(content,'Compose unapproved deterministic draft',()=>mutate('compose'),locked||x.dependencyState!=='current');content.append(node('p',x.dependencyState==='current'?'Current step: compose a draft from the chosen context.':'Current step: select at least one current source.'));}
    else {const m=x.material;content.append(node('p','Current step: review the exact draft, approve it, then prepare a cue.'),node('h4','Selected sources and voluntary signals'));for(const r of x.refs||[]){const a=(options?.moments||[]).find(v=>same(v.ref,r));content.append(node('p',a?`${a.title}: ${a.text}`:'Selected source (label unavailable)'));}for(const s of x.signals||[]){const a=signalOptions().find(v=>v.kind===s.kind&&v.id===s.id&&v._revision===s.revision);content.append(node('p',a?`${s.kind}: ${labelSignal(a)}`:'Selected signal (label unavailable)'));}
      if(m?.citations?.length){const citations=node('ul');for(const c of m.citations) citations.append(node('li',typeof c==='string'?c:JSON.stringify(c)));content.append(node('p','Citations'),citations);}if(!m){content.append(node('p','Material projection unavailable; protected actions are disabled.'));}else{content.append(node('p',`Draft status: ${m.status} · current version ${m.currentVersion} · approved version ${m.approvedVersion??'none'}`));const t=field(content,'Draft title',m.title||''), b=field(content,'Draft body',m.body||'',true);t.maxLength=200;b.maxLength=12000;button(content,'Save edited draft',()=>{if(!t.value.trim()||!b.value.trim()){status.textContent='Enter draft title and body.';return;}mutate('edit',{version:m.currentVersion,title:t.value,body:b.value});},locked);button(content,`Approve exact version ${m.currentVersion}`,()=>mutate('approve',{version:m.currentVersion}),locked);button(content,'Prepare cue for approved version',()=>mutate('prepare_cue'),locked||!!x.cueId||m.approvedVersion!==m.currentVersion);}}
    if(journalMode()==='memory' && hasMaterial)content.append(node('p','Editing a draft requires saved access for recovery. Approval and cue actions remain subject to current permissions and original-request recovery.'));
    if(x.cue){content.append(node('h4','Cue and outcome'),node('p',`Cue status: ${x.cue.status} · cue ${x.cue.id} · material version ${x.cue.materialVersion} · cue revision ${x.cue._revision} · eligible: ${x.cue.eligible?'yes':'no'}`));if(!x.deliveryGuardsWired)content.append(node('p','Presentation unavailable: delivery guard integration is not wired.'));const transport=x.presentationTransport;if(transport?.state!=='bound')content.append(node('p',transport?.state==='unavailable'&&typeof transport.message==='string' ? `Presentation unavailable: ${transport.message}` : 'Presentation unavailable: transport configuration could not be verified.'));button(content,'Present cue',()=>mutate('present'),locked||!x.deliveryGuardsWired||!x.cue.eligible||transport?.state!=='bound');button(content,'Defer cue',()=>mutate('defer'),locked);button(content,'Withdraw cue',()=>mutate('withdraw_cue'),locked);}
    if (journalMode()==='saved' && actions.openCoedit && x.material && Number.isSafeInteger(x.material.currentVersion) && x.dependencyState === 'current') button(content,'Create a coauthor draft from this material',()=>{try{guard(scope,generation);actions.openCoedit({segmentId:x.id,materialId:x.materialId,version:x.material.currentVersion},scope);}catch{status.textContent='Access changed. Refresh the workspace.';}},locked);
    button(content,'Close segment',()=>mutate('close'),locked);
  }
  async function refresh(id){if(busy)return;const s=identityScope(),g=++generation;clear();receipt=null;busy=true;status.textContent='Checking creator access, sources and consent…';try{if(!valid(s))throw Error('identity');guard(s,g);const [o,l]=await Promise.all([call('w18SegmentOptions',null,[],s,g),call('w18Segments',null,[],s,g)]);guard(s,g);if(!Array.isArray(o?.moments)||!Array.isArray(l?.segments))throw Error('response');options=o;segments=l.segments;scope=s;const pending=load(s);const target=id || (own(pending,s)?pending.args[0]:null) || null;if(target){const r=await call('w18Segment',null,[target],s,g);guard(s,g);if(!r?.segment)throw Error('response');selected=r.segment;if(journalMode()==='memory'){discovery=await discover(s,target,g);guard(s,g);}}busy=false;render();status.textContent=load(s)||discovery?.incomplete||discovery?.operations.length?'An original action needs receipt review before another change.':'Current creator workspace loaded. Permissions are rechecked by the server on each action.';}catch{if(g===generation){clear();scope=null;status.textContent='Creator access or current source state is unavailable. Refresh before continuing.';}}finally{if(g===generation)busy=false;}}
  reset();return {refresh,reset};
}
