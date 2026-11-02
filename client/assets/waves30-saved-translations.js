// Select only this actor's existing exact-moment receipts. Never generates output.
export function mountSavedTranslations(root, {owner, language, sameRef, changed}) {
  const label = document.createElement('label'); label.textContent = 'Saved translation for this moment ';
  const select = document.createElement('select'); label.append(select);
  const load = document.createElement('button'); load.type = 'button'; load.textContent = 'Load my saved translations';
  const status = document.createElement('p'); status.setAttribute('role','status'); root.append(label,load,status);
  let epoch = 0;
  function reset() { epoch++; select.replaceChildren(new Option('Source only', '')); load.disabled = !owner(); status.textContent = 'Saved evidence is checked against the exact moment and current access.'; }
  select.onchange = changed;
  load.onclick = async () => {
    const current = owner(), target = language(), ticket = ++epoch; if (!current) return;
    select.replaceChildren(new Option('Source only','')); changed(); load.disabled = true; status.textContent = 'Checking your saved translations…';
    try {
      await current.current(); const data = await current.invoke('w30SavedTranslations', null); await current.current();
      if (owner() !== current || ticket !== epoch || target !== language() || !Array.isArray(data.operations)) throw Error('Selection changed');
      const matches = data.operations.filter(op => op.kind === 'translation' && op.state === 'complete' && op.targetLanguage === target && sameRef(op.ref, current.ref));
      matches.forEach((op,index) => select.append(new Option(`${op.sourceLanguage === 'es' ? 'Spanish' : 'English'} to ${target === 'es' ? 'Spanish' : 'English'} · saved translation ${index+1}`, op.requestId)));
      status.textContent = matches.length ? 'Choose a saved translation, then inspect. The server checks currentness again.' : data.hasMore ? 'No match in this page. More saved operations exist; inspect them in the bilingual controls.' : 'No completed translation matches this moment and language. Source-only inspection remains available.';
    } catch { if (owner() === current && ticket === epoch) status.textContent = 'Saved translations are unavailable or access changed. No generation was started.'; }
    finally { if (owner() === current && ticket === epoch) load.disabled = false; }
  };
  select.append(new Option('Source only', '')); load.disabled = true;
  return {reset, selected:() => select.value};
}
