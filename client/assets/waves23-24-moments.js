// The injected index callbacks must enforce current rights at final delivery.
let clarificationGroup = 0;
export function mount(root, initialContext) {
  let ctx = initialContext || {}, generation = 0, searchGeneration = 0, busy = false, preview = null, receipt = null, pending = initialContext?.pendingCorrection || null, dead = false, imageUrl = null;
  const keys = ['scope', 'scopeGeneration', 'sessionId', 'actorId', 'role', 'sourceRef', 'sourceRevision', 'profileId', 'rightsGeneration', 'channelId'];
  const identity = c => JSON.stringify(keys.map(k => c[k] ?? null));
  const canonical = value => value && typeof value === 'object' ? (Array.isArray(value) ? value.map(canonical) : Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])]))) : value;
  const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  let contextIdentity = identity(ctx);
  const choiceName = 'moment-clarification-' + (++clarificationGroup);
  const el = (tag, text) => { const n = document.createElement(tag); if (text != null) n.textContent = text; return n; };
  root.classList.add('moments23');
  const status = el('p', 'Search availability depends on the current session and access.');
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const form = el('form'), reason = el('textarea'), correction = el('textarea');
  reason.required = true; reason.maxLength = 500; correction.required = true; correction.maxLength = 20000;
  const label = (text, control) => { const n = el('label', text); n.append(control); return n; };
  const previewButton = el('button', 'Preview impact'); previewButton.type = 'submit';
  form.append(label('Reason for correction', reason), label('Corrected source text', correction), previewButton);
  const impacts = el('div'); impacts.setAttribute('aria-live', 'polite');
  const commit = el('button', 'Commit correction'), recover = el('button', 'Check original correction'), resume = el('button', 'Resume current position');
  for (const b of [commit, recover, resume]) b.type = 'button';
  const fieldset = el('fieldset'); fieldset.append(el('legend', 'Replace affected artifact'));
  const kind = el('select'); for (const v of ['caption', 'speech', 'material', 'record']) { const o = el('option', v); o.value = v; kind.append(o); }
  const replacementId = el('input'), ref = el('input'), job = el('input'), title = el('input'), body = el('textarea'), refs = el('textarea'), chapters = el('textarea'), format = el('input'), contributions = el('textarea'), sourceLanguage = el('input'), interpretations = el('textarea'), replace = el('button', 'Submit replacement'); replace.type = 'button';
  job.type = 'number'; job.min = '1'; job.step = '1';
  const refLabel = label('Current indexed caption reference (JSON object)', ref), jobLabel = label('Existing speech job ID', job);
  const materialFields = [label('Title', title), label('Body', body)], sharedFields = [label('Source references (JSON array)', refs)], recordFields = [label('Chapters (JSON array)', chapters), label('Format', format), label('Contributions (JSON array)', contributions), label('Source language', sourceLanguage), label('Interpretations (JSON array)', interpretations)];
  function replacementFields() { refLabel.hidden = kind.value !== 'caption'; jobLabel.hidden = kind.value !== 'speech'; for (const n of materialFields) n.hidden = kind.value !== 'material'; for (const n of sharedFields) n.hidden = kind.value !== 'material' && kind.value !== 'record'; for (const n of recordFields) n.hidden = kind.value !== 'record'; }
  kind.addEventListener('change', replacementFields); replacementFields();
  fieldset.append(label('Artifact kind', kind), label('Replacement ID', replacementId), refLabel, jobLabel, ...materialFields, ...sharedFields, ...recordFields, replace);
  root.replaceChildren(el('h2', 'Moments and correction'), status, form, impacts, commit, recover, resume, fieldset);
  const searchForm = el('form'), query = el('input'), scope = el('select'), searchButton = el('button', 'Search moments'), results = el('div');
  query.required = true; query.maxLength = 500; searchButton.type = 'submit';
  for (const [value, text] of [['session', 'Current session'], ['approved_archive', 'Approved archive']]) { const option = el('option', text); option.value = value; scope.append(option); }
  results.setAttribute('aria-live', 'polite');
  searchForm.append(label('Find a moment', query), label('Search scope', scope), searchButton);
  root.append(searchForm, results);
  const destination = el('div'), returnLive = el('button', 'Return to live');
  returnLive.type = 'button'; destination.setAttribute('aria-live', 'polite');
  root.append(destination, returnLive);
  const say = text => { status.textContent = text; };
  function clearDestination() { if (imageUrl) URL.revokeObjectURL(imageUrl); imageUrl = null; destination.replaceChildren(); }
  for (const input of [query, scope]) input.addEventListener(input === query ? 'input' : 'change', () => { searchGeneration++; results.replaceChildren(); clearDestination(); });
  function controls() {
    const allowed = ctx.role === 'creator' && !!ctx.sourceRef && Number.isInteger(ctx.sourceRevision);
    previewButton.disabled = busy || !allowed || !!pending || typeof ctx.previewImpact !== 'function';
    commit.disabled = busy || !allowed || !preview || !!pending || typeof ctx.commitChange !== 'function' || typeof ctx.createRequestId !== 'function' || typeof ctx.recordPending !== 'function' || typeof ctx.resolvePending !== 'function' || typeof ctx.audio?.fence !== 'function';
    recover.disabled = busy || !pending || typeof ctx.recoverChange !== 'function' || typeof ctx.resolvePending !== 'function';
    resume.disabled = busy || !receipt || typeof ctx.audio?.resumeCurrent !== 'function';
    replace.disabled = busy || !allowed || !receipt || typeof ctx.replace !== 'function';
    searchButton.disabled = busy || typeof ctx.search !== 'function';
    returnLive.disabled = busy || typeof ctx.returnLive !== 'function';
  }
  function show(items) {
    impacts.replaceChildren();
    if (!Array.isArray(items) || !items.length) { impacts.append(el('p', 'No visible affected artifacts.')); return; }
    const list = el('ul'); for (const item of items) list.append(el('li', [item.kind, item.id ?? item.targetId, item.state, item.replacementId].filter(v => v != null).join(' · '))); impacts.append(list);
  }
  async function accept(result, valid) {
    const change = result?.change;
    if (!change || change.sourceId !== ctx.sourceRef || !Number.isInteger(change.revision) || !change.id || !change.fence) throw Error('Invalid receipt');
    await ctx.resolvePending({ requestId: pending.requestId, intentId: change.id }); if (!valid()) return;
    receipt = change; pending = null; preview = null; show(change.affected);
    say(`Correction committed at revision ${change.revision}. Already heard audio is historical. Material and record drafts need new approval.`);
  }
  async function run(fn) {
    const g = generation, key = identity(ctx), valid = () => !dead && generation === g && identity(ctx) === key;
    busy = true; controls(); try { await fn(valid); } finally { if (valid()) { busy = false; controls(); } }
  }
  searchForm.addEventListener('submit', e => {
    e.preventDefault(); if (searchButton.disabled || !searchForm.reportValidity() || !query.value.trim()) return;
    const request = { query: query.value.trim(), scope: scope.value }, searchKey = ++searchGeneration;
    if (request.scope === 'approved_archive') {
      if (typeof ctx.channelId !== 'string' || !ctx.channelId) { results.replaceChildren(el('p', 'An approved archive channel is unavailable.')); clearDestination(); return; }
      request.channelId = ctx.channelId;
    }
    clearDestination();
    run(async valid => { try {
      results.replaceChildren(el('p', 'Searching moments…'));
      const result = await ctx.search(request); if (!valid() || searchKey !== searchGeneration || request.query !== query.value.trim() || request.scope !== scope.value) return;
      if (!result || result.scope !== request.scope || !['available', 'ambiguous', 'unknown', 'unavailable'].includes(result.state) || !Array.isArray(result.results)) throw Error('Invalid search result');
      results.replaceChildren(el('p', { available: 'Matching moments', ambiguous: 'More than one moment may match.', unknown: 'No confirmed moment is known.', unavailable: 'Moment search is unavailable for this scope.' }[result.state]));
      if (result.state === 'unavailable' || result.state === 'unknown') return;
      const list = el('ul'), choices = [];
      if (result.state === 'ambiguous') results.append(el('p', 'Which moment did you mean? Select one before inspecting it.'));
      for (const item of result.results) {
        if (!item || item.rightsState !== 'current' || !item.ref || !item.time || !Number.isFinite(item.time.startMs) || !Number.isFinite(item.time.endMs)) continue;
        const row = el('li');
        row.append(el('p', `Source ${item.sourceRef} · ${item.time.startMs}–${item.time.endMs} ms · revision ${item.sourceRevision}${item.regionId ? ` · region ${item.regionId}` : ''}`));
        row.append(el('p', typeof item.explanation === 'string' ? item.explanation : 'Explanation unavailable.'));
        if (item.evidenceKind) row.append(el('p', `Evidence: ${item.evidenceKind}`));
        if (Array.isArray(item.limitations)) for (const limit of item.limitations) if (typeof limit === 'string') row.append(el('p', limit));
        const archive = item.destination?.archive;
        if (request.scope === 'approved_archive' && (!archive || archive.channelId !== request.channelId || typeof archive.grantId !== 'string' || !archive.grantId || !Number.isInteger(archive.revision))) continue;
        if (request.scope === 'session' && archive) continue;
        const open = el('button', 'Inspect moment'); open.type = 'button';
        const unavailable = typeof ctx.destination !== 'function' || typeof ctx.openDestination !== 'function';
        open.disabled = unavailable || result.state === 'ambiguous';
        if (result.state === 'ambiguous') {
          const choice = el('input'); choice.type = 'radio'; choice.name = choiceName;
          choice.addEventListener('change', () => {
            if (!choice.checked || searchKey !== searchGeneration) return;
            for (const entry of choices) entry.button.disabled = entry.unavailable || entry.choice !== choice;
          });
          row.append(label('I meant ' + (item.explanation || item.sourceRef) + ', ' + item.time.startMs + '–' + item.time.endMs + ' ms', choice)); choices.push({ choice, button: open, unavailable });
        }
        open.addEventListener('click', () => {
          if (open.disabled || busy || searchKey !== searchGeneration) return;
          const request = { ref: item.ref }; if (item.regionId != null) request.regionId = item.regionId;
          if (archive) request.archive = { channelId: archive.channelId, grantId: archive.grantId, revision: archive.revision };
          run(async valid => { try {
            clearDestination();
            destination.replaceChildren(el('p', 'Checking current access…'));
            const resolved = await ctx.destination(request); if (!valid() || searchKey !== searchGeneration) return;
            const moment = resolved?.moment;
            if (!moment || moment.rightsState !== 'current' || !moment.destination || !same(moment.ref, item.ref) || (moment.regionId ?? null) !== (item.regionId ?? null) || !same(moment.destination.archive ?? null, request.archive ?? null)) throw Error('Unavailable');
            const image = moment.destination.image;
            if (image) {
              if (typeof ctx.momentImage !== 'function' || typeof image.assetId !== 'string' || !image.assetId || !same(image.ref, request.ref) || (image.regionId ?? null) !== (request.regionId ?? null) || !Number.isFinite(image.timestampMs) || image.timestampMs < item.time.startMs || image.timestampMs > item.time.endMs || typeof image.caption !== 'string' || !image.caption || !['image/png', 'image/jpeg', 'image/webp'].includes(image.mimeType)) throw Error('Unavailable');
              const imageRequest = { ref: request.ref, assetId: image.assetId };
              if (request.regionId != null) imageRequest.regionId = request.regionId;
              if (request.archive) imageRequest.archive = request.archive;
              const blob = await ctx.momentImage(imageRequest);
              if (!valid() || searchKey !== searchGeneration) return;
              if (!(blob instanceof Blob) || blob.type !== image.mimeType || !blob.size || blob.size > 4 * 1024 * 1024) throw Error('Unavailable');
              imageUrl = URL.createObjectURL(blob);
              const figure = el('figure'), frame = el('img'); frame.src = imageUrl; frame.alt = image.caption;
              frame.addEventListener('error', () => { if (valid() && searchKey === searchGeneration) { clearDestination(); destination.replaceChildren(el('p', 'The moment image could not be displayed.')); } });
              const box = moment.regionBox;
              if (request.regionId != null) {
                if (!box || !same(box, item.regionBox) || !['x', 'y', 'width', 'height'].every(k => Number.isFinite(box[k])) || box.x < 0 || box.y < 0 || box.width <= 0 || box.height <= 0 || box.x + box.width > 1 || box.y + box.height > 1) throw Error('Unavailable');
                const visual = el('div'), outline = el('span'); visual.className = 'moment-region-frame'; outline.className = 'moment-region-outline'; outline.setAttribute('aria-hidden', 'true');
                Object.assign(outline.style, {left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%`});
                visual.append(frame, outline); figure.append(visual);
              } else figure.append(frame);
              figure.append(el('figcaption', `${image.caption} · ${image.timestampMs} ms${image.regionId ? ` · region ${image.regionId}` : ''}`));
              destination.replaceChildren(figure);
            } else destination.replaceChildren(el('p', 'No inspectable image is available for this moment.'));
            await ctx.openDestination({ moment });
            if (valid() && searchKey === searchGeneration) destination.append(el('p', 'Moment opened. Use Return to live when ready.'));
          } catch (_) { if (valid() && searchKey === searchGeneration) { clearDestination(); destination.replaceChildren(el('p', 'This moment or region is unavailable or has been withdrawn.')); } } });
        });
        row.append(open); list.append(row);
      }
      if (list.children.length) results.append(list); else results.append(el('p', 'No currently eligible moment details are available.'));
    } catch (_) { if (valid() && searchKey === searchGeneration) results.replaceChildren(el('p', 'Moment search is unavailable.')); } });
  });
  returnLive.addEventListener('click', () => { if (returnLive.disabled) return;
    searchGeneration++; clearDestination();
    run(async valid => { try { await ctx.returnLive(); if (valid()) destination.replaceChildren(el('p', 'Returned to live.')); } catch (_) { if (valid()) destination.replaceChildren(el('p', 'Live position is unavailable.')); } });
  });
  form.addEventListener('submit', e => {
    e.preventDefault(); if (previewButton.disabled || !form.reportValidity()) return;
    run(async valid => { try {
      const request = { sourceRef: ctx.sourceRef, expectedRevision: ctx.sourceRevision, reason: reason.value.trim() };
      const draft = { reason: reason.value, text: correction.value }; const result = await ctx.previewImpact(request); if (!valid() || draft.reason !== reason.value || draft.text !== correction.value) return;
      if (!result || result.source !== request.sourceRef || result.revision !== request.expectedRevision) throw Error('Invalid preview');
      preview = draft; show(result.affected); say('Review the visible impacts before committing.');
    } catch (_) { if (valid()) { preview = null; say('Impact preview unavailable or source changed.'); } } });
  });
  for (const input of [reason, correction]) input.addEventListener('input', () => { preview = null; controls(); });
  commit.addEventListener('click', () => {
    if (commit.disabled || !preview || preview.reason !== reason.value || preview.text !== correction.value) return;
    run(async valid => {
      let requestId; try { requestId = ctx.createRequestId(); } catch (_) { say('A request ID is unavailable.'); return; }
      const request = { sourceRef: ctx.sourceRef, expectedRevision: ctx.sourceRevision, requestId, change: { text: correction.value } };
      if (typeof request.requestId !== 'string' || !request.requestId) { say('A request ID is required.'); return; }
      pending = { requestId: request.requestId, sourceRef: request.sourceRef, expectedRevision: request.expectedRevision };
      try {
        if (typeof ctx.recordPending === 'function') await ctx.recordPending({ ...pending });
        if (!valid()) return;
        await ctx.audio.fence({ sourceRef: request.sourceRef, expectedRevision: request.expectedRevision });
        if (!valid()) return;
        const result = await ctx.commitChange(request); if (valid()) await accept(result, valid);
      } catch (_) { if (valid()) say('Correction outcome is unknown. Check the original request before another change.'); }
    });
  });
  recover.addEventListener('click', () => { if (recover.disabled) return;
    run(async valid => { try { const result = await ctx.recoverChange({ requestId: pending.requestId }); if (valid()) await accept(result, valid); } catch (_) { if (valid()) say('Original correction remains unknown; no new request was sent.'); } });
  });
  replace.addEventListener('click', () => { if (replace.disabled) return;
    run(async valid => { try {
      let extra;
      if (kind.value === 'caption') { const parsed = JSON.parse(ref.value); if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw Error('Reference required'); extra = { ref: parsed }; }
      else if (kind.value === 'speech') { const jobId = Number(job.value); if (!Number.isSafeInteger(jobId) || jobId < 1) throw Error('Job required'); extra = { jobId }; }
      else if (kind.value === 'material') extra = { title: title.value, body: body.value, refs: JSON.parse(refs.value) };
      else if (kind.value === 'record') extra = { refs: JSON.parse(refs.value), chapters: JSON.parse(chapters.value), format: format.value, contributions: JSON.parse(contributions.value), sourceLanguage: sourceLanguage.value, interpretations: JSON.parse(interpretations.value) };
      else throw Error('Unsupported kind');
      const expected = { caption: ['ref'], speech: ['jobId'], material: ['title', 'body', 'refs'], record: ['refs', 'chapters', 'format', 'contributions', 'sourceLanguage', 'interpretations'] }[kind.value];
      if (!extra || Array.isArray(extra) || typeof extra !== 'object' || Object.keys(extra).sort().join('|') !== expected.slice().sort().join('|') || !replacementId.value.trim()) throw Error('Invalid fields');
      await ctx.replace({ intentId: receipt.id, kind: kind.value, body: { ...extra, replacementId: replacementId.value.trim(), fence: receipt.fence } });
      if (valid()) say('Replacement submitted. Material and record drafts require explicit approval.');
    } catch (_) { if (valid()) say('Replacement unavailable or invalid; check its fields and current rights.'); } });
  });
  resume.addEventListener('click', () => { if (resume.disabled) return;
    run(async valid => { try { await ctx.audio.resumeCurrent({ sourceRef: receipt.sourceId, revision: receipt.revision, fence: receipt.fence }); if (valid()) say('Current position requested from the player.'); } catch (_) { if (valid()) say('Current playback position is unavailable.'); } });
  });
  controls();
  return {
    update(next) {
      next = next || {};
      const nextIdentity = identity(next);
      if (contextIdentity !== nextIdentity) { generation++; searchGeneration++; preview = null; receipt = null; pending = next.pendingCorrection || null; busy = false; for (const input of [reason, correction, ref, job, title, body, refs, chapters, format, contributions, sourceLanguage, interpretations, replacementId, query]) input.value = ''; impacts.replaceChildren(); results.replaceChildren(); clearDestination(); say('Context changed.'); }
      ctx = next; contextIdentity = nextIdentity; controls();
    },
    destroy() { dead = true; generation++; searchGeneration++; clearDestination(); root.replaceChildren(); root.classList.remove('moments23'); }
  };
}



