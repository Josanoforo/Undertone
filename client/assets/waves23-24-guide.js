/** Guided entry; all capabilities and destinations are supplied by the host. */
export function mount(root, initial = {}) {
  let context = initial, epoch = 0, dead = false, capabilities = null, message = '', busy = false;
  const paths = [
    ['Follow, ask and correct', [['setup', 'Set up your channel'], ['follow', 'Follow and listen'], ['inspect', 'Inspect a moment'], ['question', 'Ask privately'], ['edition', 'Return to the corrected edition']]],
    ['Edit, approve and present', [['coedit', 'Edit together'], ['contribute', 'Contribute (optional)'], ['review', 'Review and approve'], ['present', 'Present approved material']]],
    ['Return, inspect and practise', [['approved', 'Inspect approved material'], ['edition', 'Return to the corrected edition'], ['practice', 'Resume practice']]]
  ];
  const node = (tag, text) => { const e = document.createElement(tag); e.textContent = text; return e; };
  function button(label, action, enabled = true) {
    const b = node('button', label); b.type = 'button'; b.disabled = !enabled;
    b.addEventListener('click', action); return b;
  }
  async function perform(fn, ...args) {
    if (busy) return;
    const ticket = epoch;
    busy = true; render();
    try {
      await fn(...args);
      if (!dead && ticket === epoch) { busy = false; message = ''; render(); }
    } catch (_) {
      if (!dead && ticket === epoch) { busy = false; message = 'This destination is unavailable. Check your connection and access, then try again.'; render(); }
    }
  }
  async function refresh() {
    const ticket = ++epoch; capabilities = null; message = ''; busy = false; render();
    if (!context.connected || typeof context.getCapabilities !== 'function') {
      message = 'Disconnected or capability information unavailable. Reconnect and check access before resuming.'; render(); return;
    }
    try {
      const result = await context.getCapabilities();
      if (dead || ticket !== epoch) return;
      capabilities = result; render();
    } catch (_) {
      if (dead || ticket !== epoch) return;
      message = 'Capabilities are unavailable. Check your connection and access.'; render();
    }
  }
  function render() {
    if (dead) return;
    const focused = document.activeElement;
    const focusKey = focused && root.contains(focused) ? focused.dataset.guideFocus : null;
    root.replaceChildren();
    const section = node('section', ''); section.className = 'audience-guide';
    section.append(node('h2', 'Your audience companion guide'));
    const status = node('p', message || (busy ? 'Opening selection…' : !capabilities ? 'Checking availability…' : 'Choose a step. Access is checked when you open it.'));
    status.setAttribute('role', 'status'); section.append(status);
    if (capabilities) {
      const langs = Array.isArray(capabilities.languages) ? capabilities.languages : [];
      section.append(node('p', langs.length ? `Available languages: ${langs.join(', ')}` : 'Language availability is unknown.'));
      if (context.language && !langs.includes(context.language)) section.append(node('p', 'Your selected language is unsupported or its availability is unknown.'));
      section.append(node('p', 'Channel packs contain eligible shared references; your private continuation remains separate. Cross-session reuse requires current membership and approved grants.'));
      for (const [pathIndex, [title, stages]] of paths.entries()) {
        section.append(node('h3', title));
        const list = node('ol', '');
        for (const [id, label] of stages) {
          const item = node('li', '');
          const destination = capabilities.destinations && capabilities.destinations[id];
          const allowed = destination && destination.available === true && typeof context.navigate === 'function';
          const step = button(label, () => perform(context.navigate, id, destination.ref), !!allowed);
          step.dataset.guideFocus = `stage:${pathIndex}:${id}`;
          item.append(step);
          if (!allowed) item.append(node('span', destination && destination.configured === true ? ' Configured; availability or access not confirmed.' : ' Unavailable or access not confirmed.'));
          list.append(item);
        }
        section.append(list);
      }
    }
    const controls = node('div', ''); controls.className = 'audience-guide-controls';
    controls.append(button('Check connection and access', refresh, !busy));
    controls.append(button('Privacy, export and delete', () => perform(context.openPrivacy), !!capabilities && typeof context.openPrivacy === 'function'));
    controls.append(button('Open channel pack', () => perform(context.openPack), !!capabilities && typeof context.openPack === 'function'));
    controls.append(button('Resume session', () => perform(context.resumeSession), !!capabilities && typeof context.resumeSession === 'function'));
    [...controls.children].forEach((control, index) => { control.dataset.guideFocus = `control:${index}`; });
    section.append(controls); root.append(section);
    if (focusKey) {
      const replacement = [...root.querySelectorAll('button')].find(control => control.dataset.guideFocus === focusKey && !control.disabled);
      if (replacement) replacement.focus();
    }
  }
  refresh();
  return {
    update(next = {}) { if (dead) return; ++epoch; capabilities = null; root.replaceChildren(); context = next; refresh(); },
    destroy() { if (dead) return; dead = true; ++epoch; capabilities = null; root.replaceChildren(); }
  };
}
