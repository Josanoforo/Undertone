export function renderWorkspaceGuide(root, role, navigate) {
  root.replaceChildren(); root.hidden = !['creator', 'viewer'].includes(role);
  if (root.hidden) return;
  const creator = role === 'creator', heading = document.createElement('h2');
  heading.textContent = creator ? 'Creator workspace' : 'Your viewer workspace'; root.append(heading);
  const steps = creator ? [
    ['Prepare a segment', 'studio', '#wave18Segment'], ['Invite viewers', null, '#copyJoinCode'],
    ['Review and correct material', 'studio', '#view-studio'], ['Curate an edition', 'studio', '#wave27Chapters'],
    ['Inspect moments and quality', 'audience', '#wave23Moments']
  ] : [['Listen and inspect a moment', 'audience', '#wave23Moments'], ['Return to saved context', 'audience', '#notebookItems']];
  for (const [label, view, selector] of steps) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'button secondary'; button.textContent = label;
    button.onclick = () => {
      if (view) navigate(view);
      const target = document.querySelector(selector); if (!target) return;
      for (let parent = target.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
      if (!target.matches('button,input,select,textarea,a')) target.tabIndex = -1;
      target.scrollIntoView({block:'center'}); target.focus({preventScroll:true});
    };
    root.append(button);
  }
  const hint = document.createElement('p'); hint.textContent = creator ? 'Start with received sources, review the exact version, and use current permissions for each step.' : 'Choose a received moment first. Listening needs a supported approved profile; saved context remains private.'; root.append(hint);
}
