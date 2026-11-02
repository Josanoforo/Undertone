// Local authoring previews. Shared workflows require their corresponding service interfaces.
export function mountWaveDrafts(root, identityScope) {
  const host = document.createElement('section'); host.className = 'p6-card';
  host.innerHTML = `<details><summary>Creator planning previews</summary><p>These previews stay in this tab and are cleared when the session identity changes. They do not publish, schedule, transfer, or record contributions.</p><div data-body></div></details>`;
  root.append(host); const body = host.querySelector('[data-body]');
  let owner = null;
  function key() { const s = identityScope(); return s?.token && s.sessionId && s.role === 'creator' ? `${s.epoch}:${s.sessionId}:${s.role}` : null; }
  function guard() { if (!owner || owner !== key()) { reset(); return false; } return true; }
  function make(tag, text) { const n=document.createElement(tag); if(text) n.textContent=text; return n; }
  function field(parent, label, name, type='textarea') { const l=make('label',label), x=make(type); x.name=name; x.maxLength=2000; l.append(x); parent.append(l); return x; }
  function section(title, description) { const s=make('section'); s.append(make('h3',title), make('p',description)); body.append(s); return s; }
  function button(parent, label, action) { const b=make('button',label); b.type='button'; b.addEventListener('click',()=>{if(guard())action();}); parent.append(b); }
  function lineList(value) { return value.split('\n').map(v=>v.trim()).filter(Boolean).slice(0,20); }
  function paragraph(out, label, value) { out.append(make('p', `${label}: ${value || 'Not entered'}`)); }
  function render() {
    body.replaceChildren(); owner=key();
    if (!owner) { body.append(make('p','Join as a creator to use local planning previews.')); return; }
    const decisions=section('Reasons and decision preview','One reason per line. This preview does not include submitted audience reasons or publish a decision.');
    const reasons=field(decisions,'Reasons, one per line','reasons'), decision=field(decisions,'Decision','decision'), consequence=field(decisions,'Expected consequence','consequence'), unresolved=field(decisions,'Unresolved reasons or corrections','unresolved'), decisionOut=make('div');
    button(decisions,'Preview decision',()=>{decisionOut.replaceChildren(); paragraph(decisionOut,'Decision',decision.value.trim()); paragraph(decisionOut,'Expected consequence',consequence.value.trim()); const list=make('ul');for(const text of lineList(reasons.value))list.append(make('li',text));decisionOut.append(list);paragraph(decisionOut,'Unresolved or corrected',unresolved.value.trim());}); decisions.append(decisionOut);
    const formats=section('Portable format preview','Draft the rules and state for a format. A preview is not a transfer or an accepted format.');
    const title=field(formats,'Format title','title','input'), rules=field(formats,'Rules, one per line','rules'), current=field(formats,'Current accepted state to propose','state'), outcome=field(formats,'How contributions change the state','outcome'), recipient=field(formats,'Intended recipient creator','recipient','input'), formatOut=make('div');
    button(formats,'Preview proposed transfer',()=>{formatOut.replaceChildren();paragraph(formatOut,'Format',title.value.trim());paragraph(formatOut,'Recipient',recipient.value.trim());paragraph(formatOut,'Proposed state',current.value.trim());paragraph(formatOut,'Contribution effect',outcome.value.trim());const list=make('ul');for(const text of lineList(rules.value))list.append(make('li',text));formatOut.append(list);paragraph(formatOut,'Transfer','Not sent');});formats.append(formatOut);
    const schedule=section('Break planning preview','Plan an intervention for a creator-defined break. Nothing is scheduled or presented by this preview.');
    const when=field(schedule,'Break time or cue','when','input'), intervention=field(schedule,'Intervention','intervention'), scheduleOut=make('div');
    button(schedule,'Preview break',()=>{scheduleOut.replaceChildren();paragraph(scheduleOut,'Break',when.value.trim());paragraph(scheduleOut,'Intervention',intervention.value.trim());paragraph(scheduleOut,'Status','Draft only');});schedule.append(scheduleOut);
  }
  function reset() { owner=null; body.replaceChildren(); host.querySelector('details').open=false; }
  host.querySelector('details').addEventListener('toggle',event=>{if(event.currentTarget.open && !owner)render();});
  return {reset};
}
