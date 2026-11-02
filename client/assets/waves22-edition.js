// Shell-free reader for the finalized M02 edition manifest. The host must reset on
// actor, source, record or rights changes and enforce current authorization on actions.
export function mountEdition(root, {scope, api = {}, actions = {}} = {}) {
  const box = document.createElement('section'); box.className = 'w22-edition';
  const heading = document.createElement('h2'); heading.textContent = 'Approved moment';
  const status = document.createElement('p'); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.tabIndex = -1;
  const content = document.createElement('div'); box.append(heading, status, content); root.append(box);
  let generation = 0, currentScope = scope, scopeKey = '', destroyed = false, manifest = null, language = '';
  let playback = null, captionView = null, checkingPlayback = false;
  const scopeFingerprint = value => { try { const canonical = x => Array.isArray(x) ? x.map(canonical) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k, canonical(x[k])])) : x; return JSON.stringify(canonical(value)) ?? ''; } catch { return ''; } };
  const scopeCurrent = () => !!scopeKey && scopeFingerprint(currentScope) === scopeKey;
  const active = epoch => { if (epoch !== generation || destroyed) return false; if (!scopeCurrent()) { reset(currentScope); return false; } return true; };
  const node = (tag, value) => { const n = document.createElement(tag); if (value != null) n.textContent = String(value); return n; };
  const button = (parent, text, fn) => { const b = node('button', text); b.type = 'button'; b.addEventListener('click', fn); parent.append(b); return b; };
  const clear = () => { disconnectPlayer(); captionView = null; manifest = null; content.replaceChildren(); };
  const validInterval = x => Number.isFinite(x?.startMs) && Number.isFinite(x?.endMs) && x.startMs >= 0 && x.endMs > x.startMs;
  const intervalText = x => validInterval(x) ? `${x.startMs}–${x.endMs} ms` : Number.isFinite(x?.startMs) && x.startMs >= 0 && x.endMs === x.startMs ? `${x.startMs} ms (still frame)` : 'Time unavailable';
  function reset(nextScope = currentScope) { generation++; currentScope = nextScope; scopeKey = scopeFingerprint(nextScope); clear(); status.textContent = 'Access needs to be checked before reading this moment.'; }
  async function currentEdition(epoch) {
    if (!active(epoch) || !manifest || typeof api.read !== 'function') return false;
    const expected = scopeFingerprint(manifest);
    try {
      const fresh = await api.read({scope:currentScope});
      if (!active(epoch)) return false;
      if (scopeFingerprint(fresh) !== expected) {
        if (update(fresh, currentScope, epoch)) status.textContent = 'The edition changed. Showing the current approved version; the previous selection was discarded.';
        return false;
      }
      return true;
    } catch {
      if (active(epoch)) { reset(); status.textContent = 'This edition or selection is unavailable or withdrawn. Refresh current access.'; }
      return false;
    }
  }
  function disconnectPlayer() {
    const old = playback; playback = null;
    if (old) { clearInterval(old.timer); for (const [name, fn] of old.listeners) old.element.removeEventListener(name, fn); old.stop(); }
  }
  function playerCurrent() {
    try { return playback && playback.isCurrent() === true && playback.element.currentSrc === playback.src && scopeFingerprint(playback.binding) === scopeFingerprint(manifest?.timedPlayback?.binding); }
    catch { return false; }
  }
  function paintCaptions() {
    if (!captionView) return;
    const current = playerCurrent(), time = current ? playback.element.currentTime * 1000 + playback.binding.originMs : NaN;
    let text = '';
    for (const item of captionView.items) {
      const selected = current && time >= item.cue.startMs && time < item.cue.endMs;
      item.li.classList.toggle('w22-caption-current', !!selected);
      if (selected) { item.li.setAttribute('aria-current', 'true'); text = item.cue.text; }
      else item.li.removeAttribute('aria-current');
    }
    captionView.current.textContent = !current ? 'Connect the authorized original player to follow captions.' : text || 'No caption at the current media position.';
  }
  async function checkPlayback(epoch) {
    if (checkingPlayback || !active(epoch) || !playback) return;
    if (!playerCurrent()) { reset(); status.textContent = 'The original source player changed; previous captions were cleared.'; return; }
    checkingPlayback = true;
    try { await currentEdition(epoch); } finally { checkingPlayback = false; }
  }
  async function connectPlayer(epoch) {
    if (!await currentEdition(epoch)) return false;
    if (playerCurrent()) return true;
    disconnectPlayer();
    const timed = manifest?.timedPlayback;
    if (timed?.state !== 'available' || typeof actions.connectPlayer !== 'function') return false;
    const binding = timed.binding, ref = binding?.sourceRef;
    if (!validInterval(ref) || !Number.isInteger(binding.originMs) || binding.originMs < 0 || binding.originMs > ref.startMs) return false;
    const expected = scopeFingerprint(manifest);
    const bridge = await actions.connectPlayer({scope:currentScope, binding, reference:timed.authorizedRef,
      offsetMs:ref.startMs - binding.originMs,
      isCurrent:() => active(epoch) && scopeFingerprint(manifest) === expected});
    if (!active(epoch) || !await currentEdition(epoch)) { bridge?.stop?.(); return false; }
    if (!(bridge?.element instanceof HTMLMediaElement) || typeof bridge.isCurrent !== 'function' || typeof bridge.stop !== 'function' || scopeFingerprint(bridge.binding) !== scopeFingerprint(binding) || !bridge.isCurrent()) { bridge?.stop?.(); throw Error('Original player binding unavailable'); }
    const element = bridge.element;
    playback = {...bridge, src:element.currentSrc, listeners:[], timer:null};
    const tick = () => { if (!active(epoch)) return; if (!playerCurrent()) { reset(); status.textContent = 'The original source player changed; previous captions were cleared.'; return; } paintCaptions(); void checkPlayback(epoch); };
    const invalid = () => { if (active(epoch)) { reset(); status.textContent = 'Original media changed or became unavailable; previous captions were cleared.'; } };
    for (const name of ['timeupdate', 'seeking', 'seeked', 'play', 'pause', 'ended']) { element.addEventListener(name, tick); playback.listeners.push([name, tick]); }
    for (const name of ['emptied', 'error', 'abort', 'loadstart']) { element.addEventListener(name, invalid); playback.listeners.push([name, invalid]); }
    // Reauthorize even while paused. This timer never advances the media clock.
    playback.timer = setInterval(() => { void checkPlayback(epoch); }, 1000);
    paintCaptions(); return true;
  }
  function renderTimedCaptions(epoch) {
    captionView = null;
    const timed = manifest.timedPlayback;
    if (timed?.state !== 'available' || !Array.isArray(timed.tracks)) return;
    const section = node('section'); section.className = 'w22-timed-captions'; section.append(node('h3', 'Captions following original media'));
    const current = node('p'); current.className = 'w22-caption-now'; current.setAttribute('aria-live', 'polite');
    section.append(current);
    const track = timed.tracks.find(t => t.language === language);
    const items = [];
    if (track) {
      section.append(node('p', `${track.language} · ${track.provenance}. Whole verified source interval; no word timing is inferred.`));
      const list = node('ol');
      for (const cue of track.cues || []) {
        if (!validInterval(cue) || scopeFingerprint(cue.sourceRef) !== scopeFingerprint(timed.binding?.sourceRef)) continue;
        const li = node('li'); li.append(node('p', `${intervalText(cue)}: ${cue.text}`));
        if (typeof actions.connectPlayer === 'function') button(li, 'Go to caption interval', async () => {
          if (!active(epoch)) return;
          try {
            if (!await connectPlayer(epoch) || !await currentEdition(epoch) || !playerCurrent()) return;
            const offset = (cue.startMs - playback.binding.originMs) / 1000;
            if (!Number.isFinite(playback.element.duration) || offset < 0 || offset > playback.element.duration) throw Error('Interval unavailable');
            playback.element.currentTime = offset; paintCaptions();
            status.textContent = 'Original player positioned at the exact caption interval; playback was not started.';
          } catch { if (active(epoch)) { reset(); status.textContent = 'Caption interval or current media access is unavailable.'; } }
        });
        list.append(li); items.push({li, cue});
      }
      section.append(list);
    } else section.append(node('p', 'No approved timed translation is available for this language. The approved meaning below remains untimed.'));
    if (typeof actions.connectPlayer === 'function') button(section, 'Connect original player', async () => {
      try { if (await connectPlayer(epoch) && active(epoch)) status.textContent = 'Captions follow the original media clock. Use the existing player controls to listen.'; }
      catch { if (active(epoch)) { reset(); status.textContent = 'The authorized original player is unavailable.'; } }
    });
    else section.append(node('p', 'The original player connection is unavailable in this host.'));
    content.append(section); captionView = {current, items}; paintCaptions();
  }
  async function inspectFrame(region, epoch, host) {
    if (!await currentEdition(epoch)) return;
    try {
      const response = await api.readAsset({scope:currentScope, reference:manifest.media.authorizedRef});
      if (!active(epoch)) return;
      const asset = response?.asset;
      const box = region.box;
      if (!asset || !['image/png','image/jpeg'].includes(asset.mimeType) || typeof asset.data !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(asset.data) || !box || !['x','y','width','height'].every(k=>Number.isFinite(box[k])) || box.x<0 || box.y<0 || box.width<=0 || box.height<=0 || box.x+box.width>1 || box.y+box.height>1) throw Error('Region unavailable');
      host.replaceChildren();
      const frame = node('div'); frame.className = 'w22-region-frame';
      const img = node('img'); img.alt = `Received frame, marked region ${region.regionId}.`; img.src = `data:${asset.mimeType};base64,${asset.data}`;
      const outline = node('span'); outline.className = 'w22-region-outline'; outline.setAttribute('aria-hidden','true');
      Object.assign(outline.style,{left:`${box.x*100}%`,top:`${box.y*100}%`,width:`${box.width*100}%`,height:`${box.height*100}%`});
      frame.append(img,outline); host.append(frame,node('p','Evidence: the received source frame with the server-authorized region box. The outline is not a new visual inference or OCR result.'));
      status.textContent = `${region.regionId} selected.`;
    } catch {
      if (active(epoch)) { reset(); status.textContent = 'The region or current source access is unavailable. Refresh the edition.'; }
    }
  }
  async function showCaptionFrame(epoch, host) {
    if (!await currentEdition(epoch)) return;
    try {
      const response = await api.readAsset({scope:currentScope, reference:manifest.media.authorizedRef});
      if (!active(epoch)) return;
      const asset = response?.asset;
      if (!asset || !['image/png','image/jpeg'].includes(asset.mimeType) || typeof asset.data !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(asset.data)) throw Error('Invalid asset');
      const img = node('img'); img.alt = 'Current authorized source frame for the approved captions.'; img.src = `data:${asset.mimeType};base64,${asset.data}`;
      host.replaceChildren(img); host.focus(); status.textContent = 'Current caption frame selected at its verified source instant.';
    } catch { if (active(epoch)) { reset(); status.textContent = 'The frame or current access is unavailable. Refresh the edition to continue.'; } }
  }
  function render(epoch) {
    if (!active(epoch) || !manifest) return;
    content.replaceChildren();
    const tracks = Array.isArray(manifest.tracks) ? manifest.tracks : [];
    const languages = [...new Set(tracks.map(t => t.language).filter(x => typeof x === 'string' && x))];
    if (!languages.includes(language)) language = languages.includes(manifest.language) ? manifest.language : languages[0] || '';
    if (languages.length) {
      const label = node('label', 'Reading language '), select = node('select');
      for (const lang of languages) { const option = node('option', lang); option.value = lang; select.append(option); }
      select.value = language; select.addEventListener('change', async () => {
        if (!active(epoch)) return;
        const next = select.value;
        // Finish this rights-checked language transition before another frame
        // action can write into controls that render() is about to replace.
        select.disabled = true;
        content.querySelectorAll('button').forEach(control => { control.disabled = true; });
        if (!await currentEdition(epoch)) return;
        language = next; render(epoch); content.querySelector('select')?.focus();
        status.textContent = 'Reading language access checked.';
      }); label.append(select); content.append(label);
    }
    content.append(node('p', `Approved record version ${manifest.recordVersion}; record revision ${manifest.revision}. Source language: ${manifest.sourceLanguage || 'unknown'}.`));
    for (const source of manifest.provenance?.sources || []) {
      const ref = source.ref;
      if (ref) content.append(node('p', `Source ${ref.sourceId}, revision ${ref.sourceRevision}; moment ${ref.momentId}; ${intervalText(ref)}.`));
    }
    const media = manifest.media;
    let captionFrame = null;
    content.append(node('p', media?.state === 'available' ? 'A received frame is available. Read the approved text and regions below.' : 'Media is missing, withdrawn, or unavailable. Read the approved text and evidence below.'));
    // The released media is a still frame, not a player timeline. The host reads
    // the same-origin reference with current credentials and must reset on rights changes.
    if (media?.state === 'available' && typeof api.readAsset === 'function' && typeof media.authorizedRef === 'string' && /^\/api\/sessions\/[^/]+\/w22\/edition\/[^/]+\/(?:en|es)\/assets\/[a-f0-9]{64}$/.test(media.authorizedRef)) {
      const frame = node('div'); frame.tabIndex = -1; frame.setAttribute('role','group'); frame.setAttribute('aria-label','Caption source frame'); captionFrame = frame; content.append(frame);
      button(frame, 'Show received frame', async () => {
        if (!active(epoch)) return;
        try {
          const response = await api.readAsset({scope:currentScope, reference:media.authorizedRef});
          if (!active(epoch)) return;
          const asset = response?.asset;
          if (!asset || !['image/png','image/jpeg'].includes(asset.mimeType) || typeof asset.data !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(asset.data)) throw new Error('Invalid asset');
          const img = node('img'); img.alt = 'Received frame. Refer to marked region text for details.'; img.src = `data:${asset.mimeType};base64,${asset.data}`; frame.replaceChildren(img);
          status.textContent = 'Received frame loaded.';
        } catch { if (active(epoch)) { reset(); status.textContent = 'The frame or current access is unavailable. Refresh the edition to continue.'; } }
      });
    }
    content.append(node('p', 'Times indicate supplied intervals; they do not imply frame-accurate synchronization.'));
    if (tracks.some(t => t.cues?.some(c => c.timingProvenance === 'approved_still_instant'))) content.append(node('p', 'Approved captions refer to the same still-frame instant. Original audio is unavailable; a still has no playback duration.'));
    renderTimedCaptions(epoch);
    for (const track of tracks.filter(t => !t.language || t.language === language || t.kind === 'original' || (t.kind === 'approved_text' && t.role === 'original'))) {
      const title = track.kind === 'approved_text' ? (track.role === 'original' ? 'Original approved meaning' : track.role === 'translation' ? 'Approved translation' : 'Approved meaning') : track.kind || 'Text';
      const section = node('section'); section.append(node('h3', `${title}${track.language ? ` · ${track.language}` : ''}`));
      if (track.provenance) section.append(node('p', `Provenance: ${track.provenance}.`));
      const list = node('ol');
      for (const cue of Array.isArray(track.cues) ? track.cues : []) {
        const li = node('li'); li.append(node('p', `${intervalText(cue)}: ${typeof cue.text === 'string' ? cue.text : 'Text unavailable'}`));
        if (captionFrame && cue.timingProvenance === 'approved_still_instant') button(li, 'Inspect caption source frame', () => showCaptionFrame(epoch, captionFrame));
        if (validInterval(cue) && typeof actions.seek === 'function') button(li, 'Go to this interval', async () => { if (!await currentEdition(epoch)) return; try { await actions.seek({scope:currentScope, interval:{startMs:cue.startMs,endMs:cue.endMs}, sourceRef:cue.sourceRef, mediaRef:null}); if (active(epoch)) status.textContent = 'Interval requested in the existing player.'; } catch { if (active(epoch)) status.textContent = 'The interval is unavailable in the existing player.'; } });
        list.append(li);
      }
      section.append(list); content.append(section);
    }
    const regions = Array.isArray(manifest.regions) ? manifest.regions : [];
    const regionSection = node('section'); regionSection.append(node('h3', 'Marked regions'));
    if (!regions.length) regionSection.append(node('p', 'No marked region is available.'));
    const regionList = node('ol');
    regions.forEach((region, i) => { const li = node('li'); const title = region.regionId || `Region ${i + 1}`; li.append(node('h4', title), node('p', `Time: ${intervalText(region.sourceRef || region.interval || region)}`)); if (region.box && typeof region.box === 'object') li.append(node('p', `Region coordinates: ${Object.entries(region.box).map(([key,value]) => `${key}: ${value}`).join(', ')}`)); for (const [label, value] of [['Description',region.description],['Text',region.ocrText],['Interpretation',region.interpretation],['Uncertainty',region.uncertainty]]) if (typeof value === 'string' && value) li.append(node('p', `${label}: ${value}`));
      if (typeof actions.inspectRegion === 'function') button(li, `Inspect ${title}`, async () => { if (!await currentEdition(epoch)) return; try { await actions.inspectRegion({scope:currentScope, region}); if (active(epoch)) status.textContent = `${title} selected.`; } catch { if (active(epoch)) status.textContent = 'Region inspection is unavailable.'; } });
      else if (manifest.media?.state === 'available' && typeof api.readAsset === 'function' && typeof api.read === 'function') {
        const evidence = node('div');
        button(li, `Inspect ${title}`, () => inspectFrame(region, epoch, evidence)); li.append(evidence);
      }
      regionList.append(li); });
    regionSection.append(regionList); content.append(regionSection);
    const description = manifest.descriptionAudio;
    const descriptionSection = node('section');
    descriptionSection.append(node('h3', 'Approved audio description'));
    const available = description?.state === 'available' && description.delivery === 'on_demand_approved_record' &&
      description.authorizedRef === null && typeof description.recordId === 'string' &&
      Number.isInteger(description.recordVersion) && Number.isInteger(description.recordRevision) &&
      typeof description.language === 'string' && typeof description.text === 'string' &&
      description.sourceRef && typeof description.sourceRef === 'object' && typeof description.regionId === 'string';
    if (available) {
      descriptionSection.append(node('p', `Approved description (${description.language}): ${description.text}`));
      if (description.language !== language) descriptionSection.append(node('p', 'This description is available in its approved language.'));
      if (typeof actions.playDescription === 'function' && typeof api.read === 'function') {
        button(descriptionSection, 'Listen to approved description', async () => {
          if (!active(epoch)) return;
          const expected = scopeFingerprint(description), edition = scopeFingerprint(manifest), requestScope = currentScope;
          status.textContent = 'Checking description access…';
          let fresh;
          try { fresh = await api.read({scope:requestScope}); }
          catch { if (active(epoch)) { reset(); status.textContent = 'Edition or current authorization is unavailable.'; } return; }
          try {
            if (!active(epoch)) return;
            if (!fresh || fresh.approval !== 'approved' || scopeFingerprint(fresh) !== edition ||
                scopeFingerprint(fresh.descriptionAudio) !== expected) {
              reset(); status.textContent = 'The edition or description changed. Refresh to continue.'; return;
            }
            // The single host player must call isCurrent and reauthorize the exact
            // descriptor at admission, completion and bytes delivery, and stop on reset.
            await actions.playDescription({scope:requestScope, editionId:fresh.editionId,
              description:fresh.descriptionAudio,
              isCurrent:() => active(epoch) && scopeFingerprint(manifest) === edition});
            if (active(epoch)) status.textContent = 'Description requested in the existing player.';
          } catch {
            if (active(epoch)) status.textContent = 'Audio is unavailable. Read the approved description above.';
          }
        });
      } else descriptionSection.append(node('p', 'Audio is unavailable. Read the approved description above.'));
    } else descriptionSection.append(node('p', 'An approved audio description is not available. Read the marked-region text above.'));
    content.append(descriptionSection);
    if (manifest.decision) content.append(node('h3', 'Final corrected decision'), node('p', typeof manifest.decision === 'string' ? manifest.decision : [manifest.decision.decision, manifest.decision.consequence].filter(x => typeof x === 'string' && x).join(' — ') || 'Decision text unavailable.'));
    const history = node('section'); history.append(node('h3', 'Correction and version history'));
    const changes = Array.isArray(manifest.corrections) ? manifest.corrections : [];
    const recordChanges = Array.isArray(manifest.recordHistory) ? manifest.recordHistory : [];
    if (!changes.length && !recordChanges.length) history.append(node('p', 'No approved correction history is available.'));
    for (const change of recordChanges) history.append(node('p', `Record version ${change.version} is no longer current; replaced by approved version ${change.replacedByVersion}. Earlier text is not restored by this history.`));
    for (const change of changes) history.append(node('p', [change.revision != null ? `Revision ${change.revision} corrects ${change.correctsRevision}` : '', change.recordedAt, change.text].filter(x => typeof x === 'string' && x).join(' · ')));
    content.append(history);
    const materials = Array.isArray(manifest.materials) ? manifest.materials : [];
    const materialSection = node('section'); materialSection.append(node('h3', 'Reviewed materials'));
    if (!materials.length) materialSection.append(node('p', 'Additional approved material is not available in this edition.'));
    for (const material of materials) {
      const item = node('article');
      item.append(node('h4', typeof material.title === 'string' ? material.title : 'Untitled material'));
      item.append(node('p', typeof material.body === 'string' ? material.body : 'Material text unavailable.'));
      materialSection.append(item);
    }
    content.append(materialSection);
    if (typeof actions.returnToLive === 'function' && manifest.returnToLive) button(content, 'Return to live', async () => { if (!active(epoch)) return; try { await actions.returnToLive({scope:currentScope, reference:manifest.returnToLive}); if (active(epoch)) status.textContent = 'Live session navigation requested.'; } catch { if (active(epoch)) status.textContent = 'The live session is unavailable.'; } });
  }
  // Caller must pass the ticket captured before an asynchronous read and reset on
  // actor, source, record, or rights changes. Only a finalized, explicitly approved manifest renders; errors and withdrawal must reset it.
  function update(projection, nextScope = currentScope, ticket) {
    if (destroyed || ticket !== generation) return false;
    if (!scopeCurrent() || scopeFingerprint(nextScope) !== scopeKey) { reset(nextScope); return false; }
    generation++; clear();
    if (!projection || projection.approval !== 'approved' || typeof projection.editionId !== 'string' || !Array.isArray(projection.tracks)) { status.textContent = 'This moment or its current authorization is unavailable.'; return false; }
    manifest = projection; status.textContent = 'Approved moment available.'; render(generation); return true;
  }
  async function refresh() { if (destroyed || typeof api.read !== 'function') { reset(); status.textContent = 'Edition access is unavailable.'; return false; } reset(); const ticket = generation, s = currentScope; status.textContent = 'Checking current access…'; try { const projection = await api.read({scope:s}); return update(projection, s, ticket); } catch { if (ticket === generation) { clear(); status.textContent = 'Edition or current authorization is unavailable.'; } return false; } }
  function destroy() { if (destroyed) return; reset(); destroyed = true; box.remove(); }
  reset(scope); return {update, refresh, reset, destroy, getGeneration: () => generation};
}
