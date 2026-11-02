// Buffered sentence delivery through existing authenticated Wave21/Wave20 routes.
let activeSentencePlayer = null;

export class SentencePlayback {
  constructor({audio, read, current, urls = URL}) { Object.assign(this, {audio, read, current, urls}); this.version = 0; this.url = null; this.timer = null; }
  select() { if (activeSentencePlayer && activeSentencePlayer !== this) activeSentencePlayer.stop(); activeSentencePlayer = this; }
  owns(version) { return version === this.version && activeSentencePlayer === this; }
  stop() { this.version++; clearInterval(this.timer); this.timer=null; this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load(); if (this.url) this.urls.revokeObjectURL(this.url); this.url=null; this.requestId=null; if (activeSentencePlayer === this) activeSentencePlayer=null; }
  pause() { this.version++; clearInterval(this.timer); this.timer=null; this.audio.pause(); }
  async play(requestId) {
    if (this.requestId && this.requestId!==requestId) this.stop();
    this.select();
    const version=++this.version;
    clearInterval(this.timer); this.timer=null; this.audio.pause();
    try {
      if (!this.current()) { this.stop(); return false; }
      const delivery=await this.read(requestId);
      if (!this.owns(version)) return false;
      if (!this.current()) { this.stop(); return false; }
      if (delivery?.state!=='ready' || typeof delivery.result?.audioBase64!=='string') throw Error('Sentence audio unavailable');
      if (!this.url) { const bytes=Uint8Array.from(atob(delivery.result.audioBase64),c=>c.charCodeAt(0)); this.url=this.urls.createObjectURL(new Blob([bytes],{type:'audio/wav'})); this.audio.src=this.url; this.requestId=requestId; }
      await this.audio.play();
      if (!this.owns(version)) { if (activeSentencePlayer!==this) this.audio.pause(); return false; }
      if (!this.current()) { this.stop(); return false; }
      this.timer=setInterval(async()=>{try {const value=await this.read(requestId); if (this.owns(version) && (!this.current() || value?.state!=='ready')) this.stop();} catch {if(this.owns(version))this.stop();}},1000);
      this.audio.onended=()=>{if(this.owns(version)){clearInterval(this.timer);this.timer=null;}};
      return true;
    } catch (error) {
      if (!this.owns(version)) return false;
      this.stop();
      throw error;
    }
  }
}

export function mountSentenceDelivery(root,{call,current,scopeKey,event,configuration,useForTranslation}) {
  const node=(tag,value)=>{const el=document.createElement(tag);el.textContent=value;return el;};
  const status=node('p','Each explicit request delivers one buffered sentence. Native streaming and word alignment are unavailable.');status.setAttribute('role','status');
  const load=node('button','List final sentences'),select=document.createElement('select'),language=document.createElement('select');
  select.setAttribute('aria-label','Final sentence');language.setAttribute('aria-label','Sentence target language');
  for(const [value,title] of [['','Choose target language'],['en','English'],['es','Spanish']]){const o=node('option',title);o.value=value;if(value&&value!==event.language){o.disabled=true;o.textContent+=' (translated sentence binding unavailable)';}language.append(o);}
  const request=node('button','Request selected sentence'),recover=node('button','Read existing delivery'),cancel=node('button','Cancel request'),play=node('button','Play or resume sentence'),pause=node('button','Pause'),stop=node('button','Stop audio');
  for(const b of [load,request,recover,cancel,play,pause,stop])b.type='button';
  const audio=document.createElement('audio');audio.preload='none';root.append(load,select,language,request,recover,cancel,play,pause,stop,audio,status);
  const translate=node('button','Use selected sentence for translation');translate.type='button';translate.disabled=typeof useForTranslation!=='function';root.append(translate);
  if(translate.disabled)root.append(node('p','Sentence translation is unavailable in this view.'));
  let epoch=0,disposed=false,key=null,marker=null,units=[];
  const valid=()=>!disposed&&current();
  const player=new SentencePlayback({audio,read:async rid=>(await call(`generation/${encodeURIComponent(rid)}`)).delivery,current:valid});
  const safe=work=>async()=>{const e=epoch;try{if(!valid())throw Error();await work(e);}catch{if(valid()&&e===epoch)status.textContent='Operation unavailable or unconfirmed. Read the same request; an unknown request is never resubmitted.';}};
  const saved=()=>{try{return key?JSON.parse(localStorage.getItem(key)):null;}catch{throw Error('Unknown saved request');}};
  const store=value=>{localStorage.setItem(key,JSON.stringify(value));marker=value;};
  async function initialize(){if(!crypto.subtle||!navigator.locks)throw Error();const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(scopeKey));key='audience.w21.sentence.'+Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join('');marker=saved();}
  const fingerprint=()=>JSON.stringify([configuration(),select.value,language.value,event.segmentId,event.revision]);
  load.onclick=safe(async e=>{await initialize();const value=await call('sentences');if(!valid()||e!==epoch)return;const group=value.segments?.find(s=>s.segmentId===event.segmentId&&s.revision===event.revision);if(!group?.units?.length)throw Error();units=group.units;select.replaceChildren();for(const unit of units){const o=node('option',`${unit.index+1}: ${unit.text}`);o.value=unit.index;select.append(o);}status.textContent='Choose the exact voice settings and target language. Requesting does not play audio.';});
  translate.onclick=safe(async()=>{const unit=units.find(u=>u.index===Number(select.value)),selection=unit?.selection;if(typeof useForTranslation!=='function'||selection?.type!=='speech_sentence'||selection.segmentId!==event.segmentId||selection.revision!==event.revision||selection.sentenceIndex!==unit.index)throw Error();player.stop();player.select();useForTranslation(structuredClone(selection),event.language);});
  request.onclick=safe(async e=>{
    if(!select.options.length||!language.value)throw Error();player.stop();player.select();await initialize();const selected=fingerprint();
    await navigator.locks.request(key,async()=>{
      if(!valid()||e!==epoch||selected!==fingerprint())throw Error();const old=saved();
      if(old?.fingerprint===selected){const existing=await call(`generation/${encodeURIComponent(old.requestId)}`);if(valid()&&e===epoch){store({...old,state:existing.delivery?.state||'unknown'});status.textContent=`Existing sentence: ${marker.state}. No new admission.`;}return;}
      if(old&&!['ready','cancelled','unavailable','stale','full','not_admitted'].includes(old.state))throw Error('Previous outcome unresolved');player.stop();
      const rid=crypto.randomUUID();
      const preview=await call('preview','POST',{...configuration(),requestId:rid,sentenceIndex:Number(select.value),segmentId:event.segmentId,expectedRevision:event.revision});
      if(!preview.preview?.ready||!valid()||e!==epoch||selected!==fingerprint())throw Error('Sentence settings unavailable');
      const policy=await call(null,'policy');if(!Number.isInteger(policy.policyRevision))throw Error();if(!valid()||e!==epoch||selected!==fingerprint())throw Error();
      store({requestId:rid,state:'pending',fingerprint:selected});
      const value=await call('generation','POST',{request:{...configuration(),requestId:rid,sentenceIndex:Number(select.value),targetLanguage:language.value,segmentId:event.segmentId,expectedRevision:event.revision},policyRevision:policy.policyRevision});
      if(saved()?.requestId===rid)store({requestId:rid,state:value.delivery?.state||'unknown',fingerprint:selected});
      if(valid()&&e===epoch)status.textContent=`Sentence request: ${marker.state}. Read existing delivery; no automatic playback.`;
    });
  });
  recover.onclick=safe(async e=>{await initialize();if(!marker)throw Error();const observed=marker,value=await call(`generation/${encodeURIComponent(observed.requestId)}`);if(!valid()||e!==epoch||saved()?.requestId!==observed.requestId)return;store({...observed,state:value.delivery?.state||'unknown'});status.textContent=`Existing sentence: ${marker.state}. No new admission. ${value.delivery?.result?.text || ''}`;});
  cancel.onclick=safe(async e=>{await initialize();if(!marker)throw Error();player.stop();const observed=marker,value=await call(`generation/${encodeURIComponent(observed.requestId)}`,'DELETE');if(!valid()||e!==epoch||saved()?.requestId!==observed.requestId)return;store({...observed,state:value.delivery?.state||'unknown'});status.textContent=`Request: ${marker.state}.`;});
  play.onclick=safe(async()=>{await initialize();if(!marker||marker.fingerprint!==fingerprint())throw Error();await player.play(marker.requestId);});
  pause.onclick=()=>player.pause();stop.onclick=()=>player.stop();
  for(const field of [select,language])field.onchange=()=>{epoch++;player.stop();player.select();status.textContent='Selection changed. Audio stopped; unresolved requests must be read or canceled explicitly.';};
  return {stop:()=>{epoch++;player.stop();},dispose:()=>{disposed=true;epoch++;player.stop();}};
}
