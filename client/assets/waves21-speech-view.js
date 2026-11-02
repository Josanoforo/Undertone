// Private run projections are read through the authenticated shell.
import {mountCaptions} from './waves21-captions.js';
import {mountSentenceDelivery} from './waves21_sentence_player.js';
// Load the owned stylesheet when this view is mounted by an existing shell.
if (!document.querySelector('link[data-w21-captions]')) {
  const style = document.createElement('link'); style.rel = 'stylesheet';
  style.href = new URL('./waves21-captions.css', import.meta.url).href;
  style.dataset.w21Captions = ''; document.head.append(style);
}
export function mountSpeechView(root, {read, selectedSource, createRun, ingest, readRules, createRules, updateRules, revise, finalize, preview, identity, assertIdentity, useForListening, useSentenceForListening}) {
  const section = document.createElement('section');
  const heading = document.createElement('h2'); heading.textContent = 'Private speech run';
  const help = document.createElement('p'); help.textContent = 'Open an existing private speech run to review its current captions, revision history and missing intervals. Indexed captions reuse completed recognition. An optional growing-audio preview shows provisional hypotheses until you explicitly end the utterance. The engine buffers each prefix; native streaming and live capture are unavailable here. Overlap detection and voice separation are unavailable; simultaneous speech may be omitted. Times are relative to the run.';
  const label = document.createElement('label'); label.textContent = 'Speech run ID ';
  const id = document.createElement('input'); id.autocomplete = 'off'; id.maxLength = 128; label.append(id);
  const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Open or refresh run';
  const status = document.createElement('p'); status.setAttribute('role', 'status');
  const content = document.createElement('div');
  section.append(heading, help, label, button, status, content); root.append(section);
  let generation = 0;
  let sentencePlayers = [];
  const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
  const rulesSection = document.createElement('section');
  const rulesLabel = text('label', 'Private pronunciation rule set ID ');
  const rulesId = document.createElement('input'); rulesId.autocomplete = 'off'; rulesId.maxLength = 160; rulesLabel.append(rulesId);
  const rulesButton = text('button', 'View rules'); rulesButton.type = 'button';
  const createButton = text('button', 'Create private rule set'); createButton.type = 'button';
  const rulesStatus = text('p', ''); rulesStatus.setAttribute('role', 'status');
  const rulesContent = document.createElement('div');
  rulesSection.append(text('h3', 'Pronunciation rules'), rulesLabel, rulesButton, createButton, rulesStatus, rulesContent); section.append(rulesSection);
  let rulesGeneration = 0;
  function clearRules() { rulesGeneration++; rulesContent.replaceChildren(); rulesStatus.textContent = 'Rules not loaded.'; }
  rulesId.addEventListener('input', clearRules);
  rulesButton.addEventListener('click', async () => {
    clearRules(); const ticket = rulesGeneration; const ruleId = rulesId.value.trim(); const scope = identity();
    if (!/^[A-Za-z0-9._:-]{1,160}$/.test(ruleId)) { rulesStatus.textContent = 'Enter a valid rule set ID.'; return; }
    rulesButton.disabled = true; rulesStatus.textContent = 'Checking access and loading rules…';
    try {
      assertIdentity(scope); const response = await readRules(ruleId, scope); assertIdentity(scope);
      if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) return;
      const ruleset = response?.ruleSet;
      if (!ruleset || ruleset.ruleSetId !== ruleId || ruleset.scope !== 'private' || !Number.isInteger(ruleset.revision) || !Array.isArray(ruleset.rules)) throw Error('Invalid rule set');
      if (navigator.locks && crypto.subtle) {
        const createKey = `audience.w21.rules.create.${await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token]))}`;
        await navigator.locks.request(createKey, async () => {
          assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) return;
          let entry; try { entry = JSON.parse(localStorage.getItem(createKey)); } catch { return; }
          if (entry?.version === 1 && entry.ruleSetId === ruleId) localStorage.removeItem(createKey);
        });
        assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) return;
      }
      rulesContent.append(text('p', `Private rule set, revision ${ruleset.revision}.`));
      const list = document.createElement('ul'); list.setAttribute('aria-label', 'Pronunciation rules');
      for (const rule of ruleset.rules) {
        if (!rule || typeof rule.term !== 'string' || typeof rule.alias !== 'string' || !['en', 'es'].includes(rule.language) || typeof rule.approved !== 'boolean') throw Error('Invalid rule');
        list.append(text('li', `${rule.term} → ${rule.alias} (${rule.language}; ${rule.approved ? 'approved' : 'not approved'})`));
      }
      rulesContent.append(list);
      const key = `audience.w21.rules.pending.${await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token, ruleId]))}`;
      assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) return;
      if (!navigator.locks || !crypto.subtle) { rulesStatus.textContent = 'Rules loaded; safe editing is unavailable in this browser.'; return; }
      let pending = false;
      await navigator.locks.request(key, async () => {
        assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) return;
        let entry; try { entry = JSON.parse(localStorage.getItem(key)); } catch { pending = true; return; }
        if (!entry) return;
        const actual = ruleset.rules.map(({id, language, term, alias, approved}) => ({id, language, term, alias, approved}));
        const actualFingerprint = await digest(JSON.stringify(actual));
        assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) return;
        if (entry.version === 1 && ruleset.revision === entry.expectedRevision + 1 && actualFingerprint === entry.fingerprint) localStorage.removeItem(key);
        else pending = true;
      });
      assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) return;
      if (pending) { rulesStatus.textContent = 'A previous rule change has an unknown outcome. Refresh to reconcile it; no new change will be sent.'; return; }
      const editor = document.createElement('div');
      const rows = [];
      function addRow(rule = {}) {
        const row = document.createElement('fieldset'); row.append(text('legend', 'Pronunciation rule'));
        const inputs = {};
        for (const [name, title] of [['id', 'Rule ID'], ['term', 'Term'], ['alias', 'Pronunciation alias']]) {
          const label = text('label', `${title} `); const input = document.createElement('input'); input.value = rule[name] || ''; input.maxLength = name === 'id' ? 160 : 100; label.append(input); row.append(label); inputs[name] = input;
        }
        const languageLabel = text('label', 'Language '); const language = document.createElement('select');
        for (const value of ['en', 'es']) { const option = document.createElement('option'); option.value = value; option.textContent = value === 'en' ? 'English' : 'Spanish'; language.append(option); }
        language.value = rule.language || 'en'; languageLabel.append(language); row.append(languageLabel); inputs.language = language;
        const approvalLabel = text('label', 'Approved for pronunciation '); const approval = document.createElement('input'); approval.type = 'checkbox'; approval.checked = rule.approved === true; approvalLabel.append(approval); row.append(approvalLabel); inputs.approved = approval;
        const remove = text('button', 'Remove rule'); remove.type = 'button'; remove.addEventListener('click', () => { rows.splice(rows.indexOf(inputs), 1); row.remove(); }); row.append(remove);
        rows.push(inputs); editor.append(row);
      }
      ruleset.rules.forEach(addRow);
      const add = text('button', 'Add rule'); add.type = 'button'; add.addEventListener('click', () => { if (rows.length < 100) addRow(); else rulesStatus.textContent = 'A rule set can contain at most 100 rules.'; });
      const save = text('button', 'Save rules'); save.type = 'button';
      save.addEventListener('click', async () => {
        const rules = rows.map(r => ({id: r.id.value, language: r.language.value, term: r.term.value, alias: r.alias.value, approved: r.approved.checked}));
        if (rules.some(r => !/^[A-Za-z0-9._:-]{1,160}$/.test(r.id) || !r.term.trim() || !r.alias.trim() || /[<>\r\n]/.test(r.term + r.alias)) || new Set(rules.map(r => r.id)).size !== rules.length) { rulesStatus.textContent = 'Enter unique rule IDs, terms and aliases without angle brackets or line breaks.'; return; }
        save.disabled = true; add.disabled = true; rulesStatus.textContent = 'Saving rules…';
        try {
          await navigator.locks.request(key, async () => {
            assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) throw Error('Rules changed');
            if (localStorage.getItem(key)) throw Error('Previous outcome unknown');
            const fingerprint = await digest(JSON.stringify(rules));
            assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim()) throw Error('Rules changed');
            localStorage.setItem(key, JSON.stringify({version: 1, expectedRevision: ruleset.revision, fingerprint}));
            const response = await updateRules(ruleId, {expectedRevision: ruleset.revision, rules}, scope);
            assertIdentity(scope);
            if (response?.ruleSet?.ruleSetId !== ruleId || response.ruleSet.revision !== ruleset.revision + 1) throw Error('Unconfirmed response');
            const responseFingerprint = await digest(JSON.stringify(response.ruleSet.rules));
            assertIdentity(scope); if (ticket !== rulesGeneration || ruleId !== rulesId.value.trim() || responseFingerprint !== fingerprint) throw Error('Unconfirmed response');
            localStorage.removeItem(key);
          });
          if (ticket === rulesGeneration) rulesButton.click();
        } catch { if (ticket === rulesGeneration) { rulesContent.replaceChildren(); rulesStatus.textContent = 'The change could not be confirmed. Refresh the rules to reconcile before editing again.'; } }
      });
      rulesContent.append(editor, add, save); rulesStatus.textContent = ruleset.rules.length ? 'Current rules loaded. Changes require an explicit save.' : 'This rule set has no rules. Add a rule and save explicitly.';
    } catch { if (ticket === rulesGeneration) { rulesContent.replaceChildren(); rulesStatus.textContent = 'Rules unavailable or access changed.'; } }
    finally { rulesButton.disabled = false; }
  });
  const digest = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))), b => b.toString(16).padStart(2, '0')).join('');
  const createRunButton = text('button', 'Create run from selected caption'); createRunButton.type = 'button';
  section.insertBefore(createRunButton, label);
  createRunButton.addEventListener('click', async () => {
    const scope = identity(), ticket = generation;
    if (!navigator.locks || !crypto.subtle || typeof createRun !== 'function' || typeof selectedSource !== 'function') { status.textContent = 'Safe run creation is unavailable in this browser.'; return; }
    createRunButton.disabled = true;
    try {
      assertIdentity(scope);
      const key = `audience.w21.run.create.${await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token]))}`;
      let created;
      await navigator.locks.request(key, async () => {
        assertIdentity(scope); if (ticket !== generation) throw Error('Selection changed');
        let entry; try { entry = JSON.parse(localStorage.getItem(key)); } catch { throw Error('Unknown outcome'); }
        if (entry) {
          if (entry.version !== 1 || !/^[A-Za-z0-9._:-]{1,128}$/.test(entry.runId || '')) throw Error('Unknown outcome');
          created = entry.runId; return;
        }
        const ref = selectedSource();
        if (!ref) throw Error('Select an indexed caption first');
        const fingerprint = await digest(JSON.stringify(ref));
        assertIdentity(scope);
        if (ticket !== generation || JSON.stringify(selectedSource()) !== JSON.stringify(ref)) throw Error('Selection changed');
        localStorage.setItem(key, JSON.stringify({version: 1, state: 'pending', fingerprint}));
        const response = await createRun(ref, scope);
        if (!/^[A-Za-z0-9._:-]{1,128}$/.test(response?.runId || '') || !response.state) throw Error('Unconfirmed response');
        localStorage.setItem(key, JSON.stringify({version: 1, runId: response.runId}));
        created = response.runId;
      });
      assertIdentity(scope); if (ticket !== generation) return;
      id.value = created; status.textContent = 'Private run created. Opening it…';
      if (ticket === generation) button.click();
    } catch (error) { if (ticket === generation) status.textContent = error.message === 'Select an indexed caption first' ? 'Select an indexed ASR caption in captions first.' : 'Run creation could not be confirmed. An unknown outcome will not be retried.'; }
    finally { createRunButton.disabled = false; }
  });
  createButton.addEventListener('click', async () => {
    const scope = identity(); const ticket = rulesGeneration;
    if (!navigator.locks || !crypto.subtle || typeof createRules !== 'function') { rulesStatus.textContent = 'Safe creation is unavailable in this browser.'; return; }
    createButton.disabled = true; rulesStatus.textContent = 'Creating private rules…';
    try {
      assertIdentity(scope);
      const key = `audience.w21.rules.create.${await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token]))}`;
      let created;
      await navigator.locks.request(key, async () => {
        assertIdentity(scope);
        if (ticket !== rulesGeneration) throw Error('Selection changed');
        let entry; try { entry = JSON.parse(localStorage.getItem(key)); } catch { throw Error('Unknown outcome'); }
        if (entry) {
          if (entry.version !== 1 || !/^[A-Za-z0-9._:-]{1,160}$/.test(entry.ruleSetId || '')) throw Error('Unknown outcome');
          created = entry.ruleSetId; return;
        }
        localStorage.setItem(key, JSON.stringify({version: 1, state: 'pending'}));
        const response = await createRules(scope);
        const ruleset = response?.ruleSet;
        if (!ruleset || !/^[A-Za-z0-9._:-]{1,160}$/.test(ruleset.ruleSetId || '') || ruleset.scope !== 'private' || ruleset.revision !== 0 || !Array.isArray(ruleset.rules) || ruleset.rules.length) throw Error('Unconfirmed response');
        localStorage.setItem(key, JSON.stringify({version: 1, ruleSetId: ruleset.ruleSetId}));
        created = ruleset.ruleSetId;
      });
      assertIdentity(scope);
      if (ticket !== rulesGeneration) return;
      rulesId.value = created;
      rulesStatus.textContent = 'Private rule set created. Open it to edit rules.';
      if (ticket === rulesGeneration) rulesButton.click();
    } catch { if (ticket === rulesGeneration) rulesStatus.textContent = 'Creation could not be confirmed. No new rule set will be created while its outcome is unknown.'; }
    finally { createButton.disabled = false; }
  });
  const pendingKey = async (scope, runId) => `audience.w21.speech.pending.${await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token, runId]))}`;
  async function change(kind, runId, event, fields, scope, ticket) {
    if (!navigator.locks || !crypto.subtle) throw Error('Safe recovery unavailable');
    const key = await pendingKey(scope, runId);
    return navigator.locks.request(key, async () => {
      assertIdentity(scope);
      if (ticket !== generation || id.value.trim() !== runId) throw Error('Run changed');
      if (localStorage.getItem(key)) throw Error('A previous edit has an unknown outcome. Refresh the run and contact the session owner before making another edit.');
      const body = {segmentId: event.segmentId, expectedRevision: event.revision, ...fields};
      const fingerprint = await digest(JSON.stringify([kind, body]));
      assertIdentity(scope);
      if (ticket !== generation || id.value.trim() !== runId) throw Error('Run changed');
      localStorage.setItem(key, JSON.stringify({version: 1, fingerprint}));
      const result = await (kind === 'revise' ? revise(runId, body, scope) : finalize(runId, body, scope));
      assertIdentity(scope);
      if (result?.runId !== runId || !result.state) throw Error('Unconfirmed response');
      localStorage.removeItem(key);
      return result;
    });
  }
  function reset() { sentencePlayers.forEach(p => p.dispose()); sentencePlayers = []; generation++; button.disabled = false; content.replaceChildren(); status.textContent = 'Run not loaded.'; clearRules(); }
  id.addEventListener('input', reset);
  button.addEventListener('click', async () => {
    reset(); const ticket = generation; const runId = id.value.trim(); const scope = identity();
    if (!/^[A-Za-z0-9._:-]{1,128}$/.test(runId)) { status.textContent = 'Enter a valid speech run ID.'; return; }
    button.disabled = true; status.textContent = 'Checking access and loading the run…';
    try {
      assertIdentity(scope); const result = await read(runId, scope); assertIdentity(scope);
      if (ticket !== generation || id.value.trim() !== runId) return;
      const run = result?.state;
      if (result?.runId !== runId || !run || !run.segments || typeof run.segments !== 'object' || run.clock !== 'run-relative-milliseconds') throw Error('Invalid run');
      // Keep a confirmed ID recoverable across reload until its authenticated read succeeds.
      if (navigator.locks && crypto.subtle) {
        const createKey = `audience.w21.run.create.${await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token]))}`;
        await navigator.locks.request(createKey, async () => {
          assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId) return;
          let entry; try { entry = JSON.parse(localStorage.getItem(createKey)); } catch { return; }
          if (entry?.version === 1 && entry.runId === runId) localStorage.removeItem(createKey);
        });
        assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId) return;
      }
      // A matching persisted revision reconciles a lost response without repeating the write.
      if (navigator.locks && crypto.subtle && scope && typeof scope === 'object') {
        const key = await pendingKey(scope, runId);
        await navigator.locks.request(key, async () => {
          assertIdentity(scope);
          if (ticket !== generation || id.value.trim() !== runId) return;
          let entry; try { entry = JSON.parse(localStorage.getItem(key)); } catch { return; }
          if (entry?.version !== 1 || typeof entry.fingerprint !== 'string') return;
          for (const history of Object.values(run.segments)) {
            if (!Array.isArray(history)) continue;
            for (const event of history) {
              if (!event || typeof event.segmentId !== 'string' || !Number.isInteger(event.revision) || event.revision < 2) continue;
              const common = {segmentId: event.segmentId, expectedRevision: event.revision - 1};
              const candidates = [];
              if (event.state === 'provisional' || event.state === 'correction') candidates.push(['revise', {...common, text: event.text, language: event.language}]);
              if (event.state === 'final') candidates.push(['finalize', common]);
              for (const candidate of candidates) {
                const candidateFingerprint = await digest(JSON.stringify(candidate));
                assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId) return;
                if (candidateFingerprint === entry.fingerprint) { localStorage.removeItem(key); return; }
              }
            }
          }
        });
        assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId) return;
      }
      // Re-read under the same lock as admission so an old snapshot cannot clear a newer pending request.
      if (navigator.locks && crypto.subtle) {
        const chunkKey = 'audience.w21.chunk.pending.' + await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token, runId]));
        await navigator.locks.request(chunkKey, async () => {
          assertIdentity(scope);
          if (ticket !== generation || id.value.trim() !== runId) return;
          let entry; try { entry = JSON.parse(localStorage.getItem(chunkKey)); } catch { return; }
          if (entry?.version !== 1 || typeof entry.chunkId !== 'string') return;
          const latest = await read(runId, scope);
          assertIdentity(scope);
          if (ticket !== generation || id.value.trim() !== runId) return;
          if (latest?.runId === runId && latest.state?.chunks && Object.hasOwn(latest.state.chunks, entry.chunkId) && (!entry.sequence || latest.state.prefix?.sequence >= entry.sequence)) localStorage.removeItem(chunkKey);
        });
        assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId) return;
      }
      const provenance = run.inputKind === 'file_replay' ? 'File replay' : run.inputKind === 'live_program_audio' ? 'Live program audio' : 'Input origin unknown';
      content.append(text('p', `${provenance}; times are relative to this run. Captions are private.`));
      const incremental = run.recognitionMode === 'incremental_prefix';
      if (incremental) content.append(text('p', 'Growing-audio replay preview. Each longer prefix can revise the open utterance. Only an explicitly ended utterance is eligible for translation or speech. This is buffered prefix recognition, not native streaming or live capture.'));
      if (!incremental && typeof ingest === 'function') {
        const previewButton = text('button', 'Open growing-audio preview'); previewButton.type = 'button';
        previewButton.addEventListener('click', async () => {
          previewButton.disabled = true;
          try {
            assertIdentity(scope);
            const response = run.incrementalPreviewRunId ? await read(run.incrementalPreviewRunId, scope) : await ingest(runId, {operation:'create_incremental_preview'}, scope);
            assertIdentity(scope);
            if (ticket !== generation || id.value.trim() !== runId || !/^[A-Za-z0-9._:-]{1,128}$/.test(response?.runId || '') || response.state?.recognitionMode !== 'incremental_prefix') throw Error('Unconfirmed preview');
            id.value = response.runId; button.click();
          } catch { if (ticket === generation) status.textContent = 'Preview creation could not be confirmed. Refresh the original run to recover its linked preview.'; }
          finally { previewButton.disabled = false; }
        });
        content.append(previewButton);
      }
      const captions = mountCaptions(content);
      const currentRows = Object.values(run.segments).filter(Array.isArray).filter(h => h.length).map(h => ({...h.at(-1), originalLanguage:h.at(-1).originalLanguage ?? h[0].language}));
      const missing = Array.isArray(result.gaps) ? result.gaps : [];
      captions.update({rightsState:'available', scopeKey:JSON.stringify([runId, run.sourceRef]), connection:'connected', revisions:[
        ...currentRows.map(e => ({...e, sourceId:run.sourceRef, sourceRevision:run.sourceRevision ?? 1, status:e.state, startMs:e.interval?.startMs, endMs:e.interval?.endMs})),
        ...missing.map((gap, i) => ({...gap, captureRunId:run.captureRunId, sourceId:run.sourceRef, sourceRevision:run.sourceRevision ?? 1, segmentId:`gap:${i}`, revision:1, status:'gap', startMs:gap.interval?.startMs, endMs:gap.interval?.endMs}))
      ]}, captions.getGeneration());
      if (run.indexedAsr === true) content.append(text('p', 'These final captions reuse recognition from the indexed audio. No second transcription was requested. Use the revision controls to correct them.'));
      if (typeof ingest === 'function' && run.indexedAsr !== true && !run.prefix?.final) {
        const intake = document.createElement('fieldset'); intake.append(text('legend', incremental ? 'Preview a growing utterance' : 'Transcribe an indexed WAV interval'));
        intake.append(text('p', incremental ? 'Choose a longer WAV prefix of this recording, starting at the selected interval start. Mark the end only when the utterance is complete. The server verifies the original audio; an uncertain submission is not repeated.' : 'Choose the matching indexed recording interval. The server verifies the audio and source. An uncertain submission is not repeated.'));
        const fileLabel = text('label', 'WAV file '), file = document.createElement('input'); file.type = 'file'; file.accept = '.wav,audio/wav,audio/wave,audio/x-wav'; fileLabel.append(file);
        const startLabel = text('label', 'Start (ms) '), start = document.createElement('input'); start.type = 'number'; start.min = '0'; start.step = '1'; startLabel.append(start);
        const endLabel = text('label', 'End (ms) '), end = document.createElement('input'); end.type = 'number'; end.min = '1'; end.step = '1'; endLabel.append(end);
        const languageLabel = text('label', 'Language '), language = document.createElement('select');
        for (const [value, name] of [['','Detect language'], ['en','English'], ['es','Spanish']]) { const option = text('option', name); option.value = value; language.append(option); } languageLabel.append(language);
        const finalLabel = text('label', 'End of utterance '), final = document.createElement('input'); final.type = 'checkbox'; finalLabel.append(final);
        if (incremental) { start.value = String(run.interval.startMs); start.readOnly = true; language.disabled = true; }
        const send = text('button', incremental ? 'Recognize next prefix' : 'Transcribe selected interval'); send.type = 'button';
        send.addEventListener('click', async () => {
          const selected = file.files?.[0], startMs = Number(start.value), endMs = Number(end.value), lang = language.value, isFinal = final.checked;
          if (!selected || selected.size < 1 || selected.size > 12 * 1024 * 1024 || start.value === '' || end.value === '' || !Number.isSafeInteger(startMs) || !Number.isSafeInteger(endMs) || startMs < 0 || endMs <= startMs) { status.textContent = 'Choose a WAV file up to 12 MiB and a valid interval in milliseconds.'; return; }
          if (!navigator.locks || !crypto.subtle || !crypto.randomUUID) { status.textContent = 'Safe transcription recovery is unavailable in this browser.'; return; }
          send.disabled = true; final.disabled = true; status.textContent = 'Submitting the selected interval…';
          try {
            const key = `audience.w21.chunk.pending.${await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token, runId]))}`;
            await navigator.locks.request(key, async () => {
              assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId || file.files?.[0] !== selected || Number(start.value) !== startMs || Number(end.value) !== endMs || language.value !== lang) throw Error('Selection changed');
              if (localStorage.getItem(key)) throw Error('Previous outcome unknown');
              const bytes = new Uint8Array(await selected.arrayBuffer());
              assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId || file.files?.[0] !== selected || Number(start.value) !== startMs || Number(end.value) !== endMs || language.value !== lang) throw Error('Selection changed');
              let binary = ''; for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
              const chunk = incremental ? {chunkId:run.prefix?.chunkId || crypto.randomUUID(), startMs, endMs, mimeType:'audio/wav', recognitionMode:'incremental_prefix', sequence:(run.prefix?.sequence || 0) + 1, expectedRevision:currentRows.find(e => e.segmentId === run.prefix?.chunkId + ':prefix')?.revision || 0, final:isFinal} : {chunkId: crypto.randomUUID(), startMs, endMs, mimeType: 'audio/wav', ...(lang ? {language: lang} : {})};
              const fingerprint = await digest(JSON.stringify([chunk, await crypto.subtle.digest('SHA-256', bytes).then(hash => Array.from(new Uint8Array(hash)))]));
              assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId || file.files?.[0] !== selected || Number(start.value) !== startMs || Number(end.value) !== endMs || language.value !== lang) throw Error('Selection changed');
              localStorage.setItem(key, JSON.stringify({version: 1, chunkId: chunk.chunkId, sequence:chunk.sequence, fingerprint}));
              const response = await ingest(runId, {chunk, audioBase64: btoa(binary)}, scope);
              assertIdentity(scope); if (response?.runId !== runId || !response.state?.chunks || !Object.hasOwn(response.state.chunks, chunk.chunkId) || (incremental && response.state.prefix?.sequence !== chunk.sequence)) throw Error('Unconfirmed response');
              localStorage.removeItem(key);
            });
            if (ticket === generation) button.click();
          } catch { if (ticket === generation) status.textContent = 'Transcription could not be confirmed. An uncertain submission remains fenced and will not be repeated.'; }
          finally { send.disabled = false; final.disabled = false; }
        });
        intake.append(fileLabel, startLabel, endLabel, languageLabel); if (incremental) intake.append(finalLabel); intake.append(send); content.append(intake);
      }
      const list = document.createElement('ol'); list.setAttribute('aria-label', 'Speech segments');
      const histories = Object.values(run.segments).filter(Array.isArray).filter(h => h.length);
      histories.sort((a,b) => (a.at(-1)?.interval?.startMs ?? 0) - (b.at(-1)?.interval?.startMs ?? 0));
      for (const history of histories) {
        const current = history.at(-1); if (!current || !['provisional','correction','final'].includes(current.state)) continue;
        const item = document.createElement('li');
        item.append(text('strong', `${current.state === 'correction' ? 'Correction awaiting finalization' : current.state === 'final' ? 'Final' : 'Provisional'} · revision ${current.revision} · ${current.language || 'unknown language'} · ${current.interval?.startMs}–${current.interval?.endMs} ms`));
        item.append(text('p', `Segment ${current.segmentId}; speaker unknown${Number.isInteger(current.correctionOf) ? `; corrects revision ${current.correctionOf}` : ''}.`));
        if (typeof current.segmentId === 'string' && Number.isInteger(current.revision) && (!incremental || run.prefix?.final)) {
          const editLabel = document.createElement('label'); editLabel.textContent = 'Caption text ';
          const editor = document.createElement('textarea'); editor.value = String(current.text ?? ''); editLabel.append(editor);
          const langLabel = document.createElement('label'); langLabel.textContent = 'Language ';
          const lang = document.createElement('input'); lang.value = current.language || ''; langLabel.append(lang);
          const save = document.createElement('button'); save.type = 'button'; save.textContent = 'Save correction';
          const finish = document.createElement('button'); finish.type = 'button'; finish.textContent = 'Finalize this revision'; finish.disabled = current.state === 'final';
          const act = async (kind) => {
            save.disabled = true; finish.disabled = true;
            status.textContent = 'Saving the selected revision…';
            try {
              await change(kind, runId, current, kind === 'revise' ? {text: editor.value, language: lang.value} : {}, scope, ticket);
              if (ticket === generation) { status.textContent = 'Saved. Refreshing the run…'; button.click(); }
            } catch (error) {
              if (ticket === generation) { content.replaceChildren(); status.textContent = 'The edit could not be confirmed. Refresh the run to check the saved revision before continuing.'; }
            }
          };
          save.addEventListener('click', () => act('revise'));
          finish.addEventListener('click', () => act('finalize'));
          item.append(editLabel, langLabel, save, finish);
          if (current.state === 'final' && typeof preview === 'function') {
            const details = document.createElement('details'); details.append(text('summary', 'Check pronunciation settings'));
            details.append(text('p', 'Check an existing private rule set and exact voice configuration. This prepares no audio and does not change the caption.'));
            const fields = {};
            for (const [key, title, initial] of [['ruleSetId','Rule set ID',''], ['engine','Engine',''], ['model','Model',''], ['modelVersion','Model version',''], ['voiceId','Voice ID',''], ['voiceVersion','Voice version',''], ['adapterVersion','Adapter version',''], ['rate','Rate','1']]) {
              const label = text('label', `${title} `); const input = document.createElement('input'); input.value = initial; input.autocomplete = 'off'; label.append(input); details.append(label); fields[key] = input;
            }
            const result = document.createElement('p'); result.setAttribute('role', 'status');
            const check = text('button', 'Check settings'); check.type = 'button';
            check.addEventListener('click', async () => {
              const values = Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input.value.trim()]));
              const rate = Number(values.rate);
              if (Object.entries(values).some(([key, value]) => key !== 'rate' && !/^[A-Za-z0-9._:-]{1,160}$/.test(value)) || !Number.isFinite(rate) || rate < 0.5 || rate > 2) { result.textContent = 'Enter the exact configuration and a rate between 0.5 and 2.'; return; }
              check.disabled = true; result.textContent = 'Checking current caption and settings…';
              try {
                assertIdentity(scope);
                const response = await preview(runId, {...values, rate, segmentId: current.segmentId, expectedRevision: current.revision, requestId: crypto.randomUUID(), outputFormat: 'audio/wav', controls: []}, scope);
                assertIdentity(scope);
                if (ticket !== generation || id.value.trim() !== runId || Object.entries(fields).some(([key, input]) => input.value.trim() !== values[key])) return;
                const p = response?.preview;
                if (!p || typeof p.ready !== 'boolean' || !p.capabilities || !p.unavailableControls) throw Error('Invalid preview');
                const unavailable = Object.entries(p.unavailableControls).map(([key, value]) => `${key}: ${value}`).join(', ');
                result.textContent = `${p.ready ? 'Settings supported for preparation.' : 'Settings unavailable.'} ${unavailable || 'No unsupported requested controls.'} Alignment: ${p.capabilities.alignment || 'unknown'}. No audio was generated.`;
              } catch { if (ticket === generation) result.textContent = 'Settings could not be checked; the run, rule set or access may have changed.'; }
              finally { check.disabled = false; }
            });
            const sentence = mountSentenceDelivery(details, {
              event: current, scopeKey: JSON.stringify([scope.sessionId, scope.role, scope.viewerId, scope.actorBinding, scope.token, runId, current.segmentId]),
              useForTranslation: typeof useSentenceForListening==='function' ? (selection,language)=>{assertIdentity(scope);if(ticket!==generation||id.value.trim()!==runId)throw Error('Run changed');useSentenceForListening(selection,language,scope);} : undefined,
              current: () => { try { assertIdentity(scope); return ticket === generation && id.value.trim() === runId; } catch { return false; } },
              configuration: () => ({...Object.fromEntries(Object.entries(fields).map(([key, input]) => [key, input.value.trim()])), rate:Number(fields.rate.value), outputFormat:'audio/wav', controls:[]}),
              call: async (suffix, method='GET', body) => {
                assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId) throw Error('Run changed');
                const path = method === 'policy' ? `w20/delivery-sources` : `w21/speech/runs/${encodeURIComponent(runId)}/${suffix}`;
                const response = await fetch(`/api/sessions/${encodeURIComponent(scope.sessionId)}/${path}`, {method:method === 'policy' ? 'GET' : method, headers:{Authorization:`Bearer ${scope.token}`, ...(body ? {'Content-Type':'application/json'} : {})}, ...(body ? {body:JSON.stringify(body)} : {})});
                const value = await response.json(); assertIdentity(scope);
                if (!response.ok || ticket !== generation || id.value.trim() !== runId) throw Error('Delivery unavailable'); return value;
              }
            });
            sentencePlayers.push(sentence);
            for (const input of Object.values(fields)) input.addEventListener('input', () => { sentence.stop(); result.textContent = 'Settings changed; check again.'; });
            details.append(check, result); item.append(details);
          }
        }
        if (history.length > 1) {
          const details = document.createElement('details'); details.append(text('summary', 'Revision history'));
          const revisions = document.createElement('ol');
          for (const event of history) revisions.append(text('li', `Revision ${event.revision} (${event.state}, ${event.language}): ${event.text}`));
          details.append(revisions); item.append(details);
        }
        list.append(item);
      }
      content.append(text('h3', 'Caption revision controls'), list);
      const gaps = Array.isArray(result.gaps) ? result.gaps : [];
      if (gaps.length) { const group = document.createElement('ul'); group.setAttribute('aria-label', 'Missing intervals'); for (const gap of gaps) group.append(text('li', `Missing interval: ${gap.interval?.startMs}–${gap.interval?.endMs} ms`)); content.append(group); }
      if (typeof useForListening === 'function' && histories.some(h => h.at(-1)?.state === 'final')) {
        const listen = text('button', 'Use this run for listening'); listen.type = 'button';
        listen.onclick = () => { try { assertIdentity(scope); if (ticket !== generation || id.value.trim() !== runId) throw Error('Run changed'); useForListening(runId, scope); } catch { status.textContent = 'Select a current moment before using this run for listening.'; } };
        content.append(listen);
      }
      status.textContent = histories.length ? 'Current authorized run loaded.' : 'This run has no caption segments yet.';
    } catch (error) { if (ticket === generation) { content.replaceChildren(); status.textContent = 'Run unavailable or access changed. Refresh to check again.'; } }
    finally { button.disabled = false; }
  });
  reset(); return {reset};
}
