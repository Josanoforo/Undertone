// Local controls over current host-supplied content. No storage or audio engine.
export function mountAccessibility(root, {scope, actions = {}} = {}) {
  const box = document.createElement('section'); box.className = 'w26-accessibility';
  const title = document.createElement('h2'); title.textContent = 'Accessibility';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.tabIndex = -1;
  const content = document.createElement('div'); box.append(title, status, content); root.append(box);
  let currentScope = scope, fingerprint = key(scope), generation = 0, narrationGeneration = 0, view = null, busy = false, saving = false, destroyed = false, preference = null;
  function key(value) {
    try {
      const canonical = x => Array.isArray(x) ? x.map(canonical) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canonical(x[k])])) : x;
      return JSON.stringify(canonical(value)) || '';
    } catch { return ''; }
  }
  const active = epoch => !destroyed && epoch === generation && !!fingerprint && key(currentScope) === fingerprint;
  function element(tag, text) { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; }
  function reset(nextScope = currentScope) {
    const focused=content.contains(document.activeElement);
    generation++; narrationGeneration++; currentScope = nextScope; fingerprint = key(nextScope); view = null; busy = false; saving = false; preference = null; content.replaceChildren();
    status.textContent = 'Current access and accessibility preferences need to be checked.';
    if(focused)status.focus();
    if (typeof actions.stopDescription === 'function') actions.stopDescription();
  }
  function validPreference(p) { return p && Number.isInteger(p.revision) && p.revision >= 0 && typeof p.descriptionEnabled === 'boolean' && ['off','original','translated','both'].includes(p.captionMode) && typeof p.descriptionAvailable === 'boolean' && typeof p.captionAvailable === 'boolean'; }
  async function saveChange(change, focusTag) {
    const epoch = generation; if (!active(epoch) || saving || !preference || typeof actions.savePreferences !== 'function') return;
    saving = true; status.textContent = 'Saving preference…';
    try {
      const result = await actions.savePreferences({scope:currentScope, expectedRevision:preference.revision, change});
      if (!active(epoch)) return;
      if (!validPreference(result)) throw new Error('Unavailable preference');
      preference = result; status.textContent = 'Preference saved.';
    } catch { if (active(epoch)) status.textContent = 'Preference could not be saved. Refresh or choose an available alternative.'; }
    finally { if (active(epoch)) { saving = false; render(); content.querySelector(focusTag)?.focus(); } }
  }
  function render() {
    const epoch = generation; if (!active(epoch) || !view) return;
    content.replaceChildren();
    const label = element('label', 'Captions for this view '), select = element('select');
    const tracks = Array.isArray(view.captions) ? view.captions.filter(t => (t.kind === 'original' || t.kind === 'translated') && typeof t.text === 'string' && t.text.trim()) : [];
    const available = kind => tracks.some(t => t.kind === kind);
    const choices = [['off', 'Off'], ['original', 'Original'], ['translated', 'Translated'], ['both', 'Original and translated']];
    const supported = value => value === 'off' || (value === 'both' ? available('original') && available('translated') : available(value));
    const choice = preference?.captionMode;
    for (const [value, name] of choices) { const usable = supported(value) && !(value === choice && !preference?.captionAvailable); const option = element('option', name + (usable ? '' : ' — unavailable')); option.value = value; option.disabled = !usable; select.append(option); }
    select.disabled = !preference || saving || typeof actions.savePreferences !== 'function';
    if (preference) select.value = choice; label.append(select); content.append(label);
    select.addEventListener('change', () => { if (active(epoch) && supported(select.value)) void saveChange({captionMode:select.value}, 'select'); });
    if (!preference) content.append(element('p', 'Saved accessibility preferences are unavailable. Refresh the view.'));
    else if (!preference.captionAvailable || !supported(choice)) content.append(element('p', 'The saved caption choice is unavailable here. Choose an available alternative.'));
    const captions = element('div'); captions.setAttribute('aria-label', 'Captions');
    for (const track of tracks.filter(t => preference?.captionAvailable && supported(choice) && (choice === 'both' || t.kind === choice))) {
      const p = element('p', `${track.kind === 'original' ? 'Original' : 'Translated'}${typeof track.language === 'string' && track.language ? ` (${track.language})` : ''}: ${track.text}`); captions.append(p);
    }
    content.append(captions);
    const section = element('section'); section.append(element('h3', 'Audio description'));
    const descriptionLabel = element('label', 'Prefer audio description '), descriptionToggle = element('input'); descriptionToggle.type = 'checkbox'; descriptionToggle.checked = preference?.descriptionEnabled === true; descriptionToggle.disabled = !preference || saving || typeof actions.savePreferences !== 'function'; descriptionLabel.append(descriptionToggle); section.append(descriptionLabel);
    descriptionToggle.addEventListener('change', () => { if (active(epoch)) { if(!descriptionToggle.checked){narrationGeneration++;busy=false;actions.stopDescription?.();}void saveChange({descriptionEnabled:descriptionToggle.checked}, 'input'); } });
    if (preference && !preference.descriptionAvailable) section.append(element('p', 'The saved description preference is unavailable here. It is retained for other views; no audio starts automatically.'));
    const d = view.description;
    const valid = view.kind === 'edition' && view.approval === 'approved' && d?.state === 'available' && d.delivery === 'on_demand_approved_record' && d.authorizedRef === null && typeof d.recordId === 'string' && Number.isInteger(d.recordVersion) && Number.isInteger(d.recordRevision) && typeof d.language === 'string' && typeof d.text === 'string' && !!d.text && d.sourceRef && typeof d.sourceRef === 'object' && typeof d.regionId === 'string';
    if (!valid) section.append(element('p', 'Approved description or permission is unavailable for this view.'));
    else {
      section.append(element('p', `Approved description (${d.language}): ${d.text}`));
      if (typeof actions.readCurrentEdition === 'function' && typeof actions.playDescription === 'function' && typeof actions.stopDescription === 'function') {
        const button = element('button', busy ? 'Checking description…' : 'Listen to approved description'); button.type = 'button'; button.disabled = busy; section.append(button);
        button.addEventListener('click', async () => {
          if (!active(epoch) || busy) return;
          const narrationTicket=++narrationGeneration;
          const audioCurrent=()=>active(epoch)&&narrationTicket===narrationGeneration;
          busy = true; button.disabled = true; status.textContent = 'Checking description access…';
          const expected = key(d), expectedEdition = view.editionId, requestScope = currentScope;
          try {
            const fresh = await actions.readCurrentEdition({scope:requestScope});
            if (!audioCurrent()) return;
            if (!fresh || fresh.approval !== 'approved' || fresh.editionId !== expectedEdition || key(fresh.descriptionAudio) !== expected) {
              reset(); status.textContent = 'The edition, description or permission changed. Refresh the view.'; return;
            }
            actions.stopDescription();
            await actions.playDescription({scope:requestScope, editionId:expectedEdition, description:fresh.descriptionAudio, isCurrent:audioCurrent});
            if (audioCurrent()) status.textContent = 'Description requested in the existing player.';
          } catch { if (audioCurrent()) { reset(); status.textContent = 'Description or current permission is unavailable. Refresh the view.'; } }
          finally { if (audioCurrent()) { busy = false; button.disabled = false; } }
        });
      } else section.append(element('p', 'Audio is unavailable. Read the approved description above.'));
    }
    content.append(section);
    if (typeof actions.returnFocus === 'function') { const back = element('button', 'Return to view'); back.type = 'button'; back.addEventListener('click', () => { if (active(epoch)) actions.returnFocus({scope:currentScope}); }); content.append(back); }
  }
  async function update(nextView, nextScope = currentScope) {
    if (destroyed) return;
    // Every update invalidates old asynchronous responses, even in the same scope.
    reset(nextScope); const epoch = generation; view = nextView; if (!active(epoch) || !view) return;
    status.textContent = 'Checking accessibility preferences…'; render();
    try { const result = await actions.readPreferences?.({scope:currentScope}); if (!active(epoch)) return; if (!validPreference(result)) throw new Error('Unavailable preference'); preference = result; status.textContent = 'Choose available captions or explicitly request approved description audio.'; }
    catch { if (active(epoch)) status.textContent = 'Current accessibility preferences are unavailable.'; }
    if (active(epoch)) render();
  }
  function destroy() { if (destroyed) return; reset(); destroyed = true; box.remove(); }
  reset(scope);
  return {update, reset, destroy};
}
