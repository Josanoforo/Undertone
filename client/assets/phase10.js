const $ = (selector, root = document) => root.querySelector(selector);

function element(tag, text = "", attributes = {}) {
  const result = document.createElement(tag);
  if (text !== "") result.textContent = text;
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "class") result.className = value;
    else result.setAttribute(key, value);
  }
  return result;
}

const requestId = () => crypto.randomUUID();
const list = value => Array.isArray(value) ? value : [];
const referenceKey = ref => [ref?.sessionId, ref?.sourceId, ref?.sourceRevision, ref?.momentId, ref?.startMs, ref?.endMs].join("|");
const timeLabel = ms => Number.isFinite(ms)
  ? `${String(Math.floor(ms / 3600000)).padStart(2, "0")}:${String(Math.floor(ms / 60000) % 60).padStart(2, "0")}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`
  : "Time unavailable";

export function safePublishedUrl(supplied, origin, path) {
  if (typeof supplied !== "string" || !supplied) return null;
  try {
    const url = new URL(supplied, origin);
    if (!["http:", "https:"].includes(url.protocol) || url.origin !== origin
        || url.username || url.password || url.search || url.hash || url.pathname !== path) return null;
    return url.href;
  } catch { return null; }
}

export function createPhase10Controller({ api, state, identityScope, assertIdentity }) {
  let role = null;
  let sourceGeneration = 0;
  let openedMomentRequest = 0;
  let timelineSearchPending = false;
  let comparisonSpeaking = false;
  let comparisonView = 0;
  function stopComparisonSpeech() {
    if (comparisonSpeaking && window.speechSynthesis) window.speechSynthesis.cancel();
    comparisonSpeaking = false;
  }
  let vaultGeneration = 0;
  let grantGeneration = 0;
  let sources = [];
  let moments = [];
  let selectedRefs = new Set();
  let materials = [];
  let vaultEntries = [];
  let vaultToken = "";
  let grants = [];
  let sourceReady = false;
  let sourceCheckPending = false;
  let vaultReady = false;
  let vaultCreateUnknown = false;
  let materialCreateUnknown = false;
  let memorySaveUnknown = false;
  let grantCreateUnknown = false;
  const sourceLocks = new Set();
  const vaultLocks = new Set();
  const lockedMaterials = new Set();
  const reviewedVersions = new Set();
  const lockedEntries = new Set();
  const unresolved = new Map();
  const edits = new Map();
  // A rejected publication URL remains blocked until a fresh material readback.
  const publicationUrls = new Map();

  const sourceMap = () => new Map(sources.map(source => [source.id, source]));
  const selectableMoment = moment => {
    const source = exactSource(moment?.ref);
    return !!source && source.audienceVisible === true && ["available", "uncertain"].includes(moment.status);
  };
  // A timeline DTO may omit status. This is only a candidate for server review,
  // never a client assertion that the source is eligible for publication.
  const editableMoment = moment => {
    const ref = moment?.ref, source = exactSource(ref);
    const validId = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);
    return sourceReady && source?.audienceVisible === true
      && validId(ref?.sessionId) && ref.sessionId === identityScope().sessionId
      && validId(ref.sourceId) && validId(ref.momentId)
      && Number.isInteger(ref.sourceRevision) && ref.sourceRevision > 0
      && Number.isInteger(ref.startMs) && Number.isInteger(ref.endMs)
      && ref.startMs >= 0 && ref.endMs >= ref.startMs && ref.endMs <= 864000000
      && ref.sourceRevision <= 864000000
      && moment.available !== false && moment.redacted !== true && moment.retracted !== true && moment.stale !== true
      && (moment.status == null || ["available", "uncertain"].includes(moment.status));
  };
  // Foreign references are candidates only from this exact, current material detail.
  // The server remains authoritative for transfer lineage, source rights and preview.
  const inheritedRefs = material => sourceReady && !sourceCheckPending && material.dependencyState === "current"
    && typeof material.body === "string" && typeof material.title === "string"
    ? list(material.refs).filter(ref => {
      const validId = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);
      return ref?.sessionId !== identityScope().sessionId && validId(ref?.sessionId)
        && validId(ref.sourceId) && validId(ref.momentId)
        && Number.isInteger(ref.sourceRevision) && ref.sourceRevision > 0 && ref.sourceRevision <= 864000000
        && Number.isInteger(ref.startMs) && Number.isInteger(ref.endMs)
        && ref.startMs >= 0 && ref.endMs >= ref.startMs && ref.endMs <= 864000000;
    }) : [];
  const materialOptions = material => {
    const own = moments.filter(editableMoment).map(moment => ({ ref: moment.ref, status: moment.status }));
    // Studio drafts can retain a current, audience-visible untimed text note
    // as an exact source. Offering a choice never replaces the stored reference.
    const untimed = sourceReady && !sourceCheckPending
      && ["current", "stale"].includes(material.dependencyState) && material.redacted !== true
      && typeof material.body === "string" && typeof material.title === "string"
      ? list(material.refs).filter(ref => {
        const validId = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);
        const source = sourceMap().get(ref?.sourceId);
        return ref && Object.keys(ref).sort().join("|") === "sessionId|sourceId|sourceRevision"
          && ref.sessionId === identityScope().sessionId && validId(ref.sessionId) && validId(ref.sourceId)
          && Number.isInteger(ref.sourceRevision) && ref.sourceRevision > 0 && ref.sourceRevision <= 864000000
          && source?.audienceVisible === true && source.status === "active"
          && Number.isInteger(source.revision) && source.revision >= ref.sourceRevision && source.revision <= 864000000
          && (!source.expiresAt || (Number.isFinite(Date.parse(source.expiresAt)) && Date.parse(source.expiresAt) > Date.now()))
          && list(material.dependencies).some(dep => dep.sourceId === ref.sourceId && ["current", "stale"].includes(dep.state)
            && dep.recordedRevision === ref.sourceRevision && dep.currentRevision === source.revision);
      }).map(ref => ({ ref: { ...ref, sourceRevision: sourceMap().get(ref.sourceId).revision }, untimed: true })) : [];
    const foreign = inheritedRefs(material).map(ref => ({ ref, inherited: true }));
    return [...own, ...untimed, ...foreign.filter(item => !own.some(candidate => referenceKey(candidate.ref) === referenceKey(item.ref)))];
  };
  const selectedMoment = selector => moments.find(moment => referenceKey(moment.ref) === $(selector)?.value && selectableMoment(moment));
  const exactSelectedRefs = () => moments
    .filter(moment => selectedRefs.has(referenceKey(moment.ref))
      && editableMoment(moment))
    .map(moment => moment.ref)
    .slice(0, 20);
  const untimedSourceChoice = element("input", "", { type: "checkbox", "aria-label": "Use selected text note as an untimed reference" });
  const untimedSourceLabel = element("label", "Use the full selected audience-visible text note as an untimed reference for this draft.", { class: "check-line" });
  untimedSourceLabel.prepend(untimedSourceChoice);
  $("#p10StudioSource")?.insertAdjacentElement("afterend", untimedSourceLabel);
  let untimedSourceChoiceKey = "";
  const currentUntimedSource = () => {
    const source = sourceMap().get($("#p10StudioSource")?.value);
    const sessionId = identityScope().sessionId;
    const validId = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value);
    const key = source && `${source.id}:${source.revision}`;
    if (key !== untimedSourceChoiceKey) {
      untimedSourceChoice.checked = false;
      untimedSourceChoiceKey = key || "";
    }
    const eligible = sourceReady && !sourceCheckPending && role === "creator"
      && source?.kind === "note" && source.audienceVisible === true && source.status === "active"
      && validId(sessionId) && validId(source.id)
      && Number.isInteger(source.revision) && source.revision > 0 && source.revision <= 864000000
      && (!source.expiresAt || (Number.isFinite(Date.parse(source.expiresAt)) && Date.parse(source.expiresAt) > Date.now()));
    untimedSourceLabel.hidden = !source || source.kind !== "note";
    untimedSourceChoice.disabled = !eligible;
    if (!eligible) untimedSourceChoice.checked = false;
    return eligible && untimedSourceChoice.checked
      ? { sessionId, sourceId: source.id, sourceRevision: source.revision }
      : null;
  };
  const selectedMaterialRefs = () => {
    const refs = exactSelectedRefs();
    const untimed = currentUntimedSource();
    if (!untimed || refs.length >= 20 || refs.some(ref => ref.sourceId === untimed.sourceId)) return refs;
    return [...refs, untimed];
  };

  function assertCurrent(scope, sourceEpoch, vaultEpoch = null) {
    assertIdentity(scope);
    if (sourceEpoch !== sourceGeneration) throw new DOMException("Source response expired", "AbortError");
    if (vaultEpoch !== null && vaultEpoch !== vaultGeneration) throw new DOMException("Vault response expired", "AbortError");
  }

  function resultIsCurrent(scope, sourceEpoch, vaultEpoch = null) {
    try { assertCurrent(scope, sourceEpoch, vaultEpoch); return true; }
    catch { return false; }
  }

  function writeStatus(selector, message, alert = false) {
    const host = $(selector);
    if (!host) return;
    host.textContent = message;
    if (alert) host.setAttribute("role", "alert");
    else host.setAttribute("role", "status");
  }

  function clearResult(selector) {
    $(selector)?.replaceChildren();
  }

  function clearVaultProtected(message = "Vault access is not confirmed. Private results are hidden.") {
    vaultGeneration += 1;
    vaultReady = false;
    vaultEntries = [];
    clearResult("#p10Memories");
    clearResult("#p10MemoryAnswer");
    const query = $("#p10QueryMemory");
    if (query) query.disabled = true;
    const save = $("#p10SaveMemory");
    if (save) save.disabled = true;
    const load = $("#p10LoadMemory");
    if (load) load.disabled = !vaultToken;
    writeStatus("#p10MemoryStatus", message);
  }

  function invalidateVaultQuery(message = "Private memory changed. Query results were cleared.") {
    vaultGeneration += 1;
    clearResult("#p10MemoryAnswer");
    writeStatus("#p10MemoryStatus", message);
  }

  function clearSourceProtected(message = "Refreshing exact source access. Source-derived content is hidden until verified.") {
    stopComparisonSpeech();
    comparisonView += 1;
    sourceGeneration += 1;
    openedMomentRequest += 1;
    grantGeneration += 1;
    sourceReady = false;
    sources = [];
    moments = [];
    selectedRefs.clear();
    reviewedVersions.clear();
    grants = [];
    for (const selector of ["#p10Moments", "#p10StudioMoments", "#p10Grants", "#p10Materials"]) clearResult(selector);
    for (const selector of ["#p10TimelineAnswer", "#p10OpenedMoment", "#p10SearchResults", "#p10Representation", "#p10Comparison", "#p10MaterialPreview"]) clearResult(selector);
    for (const selector of ["#p10Moment", "#p10Before", "#p10After", "#p10StudioSource", "#p10MemoryGrant"]) {
      const select = $(selector);
      if (select) select.replaceChildren(element("option", "Choose a current exact source", { value: "" }));
    }
    for (const selector of ["#p10Retrieve", "#p10Concise", "#p10Detailed", "#p10Translate", "#p10VisualDescription", "#p10Compare", "#p10Index", "#p10Derive", "#p10Grant", "#p10SaveMemory"]) {
      const button = $(selector);
      if (button) button.disabled = true;
    }
    writeStatus("#p10ViewerStatus", message);
    writeStatus("#p10StudioStatus", message);
    clearVaultProtected("Source rights are being refreshed. Private memory results are hidden until rechecked.");
  }

  function exactSource(ref) {
    const source = sourceMap().get(ref?.sourceId);
    return source?.revision === ref?.sourceRevision ? source : null;
  }

  function exactReferenceLabel(ref) {
    if (ref && Object.keys(ref).sort().join("|") === "sessionId|sourceId|sourceRevision")
      return `source ${ref.sourceId} · revision ${ref.sourceRevision} · untimed reference`;
    return `source ${ref?.sourceId ?? "unknown"} · revision ${ref?.sourceRevision ?? "unknown"} · moment ${ref?.momentId ?? "unknown"} · ${ref?.startMs ?? "?"}–${ref?.endMs ?? "?"} ms (${timeLabel(ref?.startMs)})`;
  }

  async function openExactMoment(ref) {
    if (state.role !== "viewer") return;
    const detail = $("#p10OpenedMoment");
    const scope = identityScope(), epoch = sourceGeneration;
    const request = ++openedMomentRequest;
    const unavailable = () => {
      if (detail) detail.textContent = "This exact moment is unavailable or changed. Its content and any documented reason cannot be retrieved. Refresh received moments.";
    };
    if (!sourceReady || !exactSource(ref)) {
      unavailable();
      return;
    }
    if (detail) detail.textContent = "Checking this exact source revision and interval…";
    try {
      const currentSources = await api.call("sources", null, { scope });
      assertCurrent(scope, epoch);
      const source = list(currentSources?.sources || currentSources?.items || currentSources)
        .find(item => item.id === ref.sourceId && item.revision === ref.sourceRevision
          && item.status === "active" && item.audienceVisible === true);
      if (!source) throw new Error("moment_unavailable");
      const response = await api.call("p10Timeline", null, ref.sourceId, { scope });
      assertCurrent(scope, epoch);
      if (request !== openedMomentRequest) return;
      const moment = list(response?.moments).find(item => referenceKey(item.ref) === referenceKey(ref)
        && ["available", "uncertain"].includes(item.status));
      if (!moment) throw new Error("moment_unavailable");
      if (detail) detail.replaceChildren(
        element("strong", `${source.title || "Source"} · ${exactReferenceLabel(ref)}`),
        element("br"),
        element("span", moment.text || "Source-derived text is unavailable; a reason is not established by this moment.", { class: "preserve-lines" }),
        element("br"),
        element("small", `${moment.alignment?.origin || "alignment unknown"} · ${moment.captureRunId || "run unknown"} · ${moment.status}`));
      const sourceSelect = $("#questionSource"), momentInput = $("#questionMoment");
      if (sourceSelect) sourceSelect.value = ref.sourceId;
      if (momentInput) momentInput.value = timeLabel(ref.startMs);
    } catch (error) {
      if (request === openedMomentRequest && resultIsCurrent(scope, epoch)) unavailable();
    }
  }

  function sourceMomentCard(moment, creatorView, includeSelection = true) {
    const ref = moment.ref || {};
    const source = exactSource(ref);
    if (!source) return null;
    const key = referenceKey(ref);
    const label = `${source.title || source.kind || "Source"} · ${timeLabel(ref.startMs)}–${timeLabel(ref.endMs)} · r${ref.sourceRevision} · ${moment.kind || "moment"}${moment.status === "uncertain" ? " · uncertain" : moment.status == null ? " · eligibility unconfirmed" : ""}`;
    const card = element("article", "", { class: "p10-moment" });
    const choose = element("input", "", { type: "checkbox", "aria-label": `Select ${label}` });
    choose.checked = selectedRefs.has(key);
    choose.disabled = creatorView ? !editableMoment(moment) : !selectableMoment(moment);
    choose.addEventListener("change", () => {
      if (choose.checked) selectedRefs.add(key);
      else selectedRefs.delete(key);
        if (creatorView && choose.checked) discoverRetentionGrants(ref);
      updateControls();
    });
    if (includeSelection) card.append(choose);
    card.append(element("strong", label));
    card.append(element("p", exactReferenceLabel(ref), { class: "muted" }));
    card.append(element("p", moment.text || "Source-derived text unavailable", { class: "preserve-lines" }));
    const alignment = moment.alignment || {};
    card.append(element("p", `${alignment.origin || "alignment unknown"} · ${alignment.captureRunId || "run unknown"} · ${alignment.capturedAt || "capture time unknown"}${moment.status === "uncertain" ? " · uncertain source alignment" : ""}`, { class: "muted" }));
    if (!creatorView) {
      const open = element("button", "Open this exact moment", { type: "button", class: "text-button" });
      open.disabled = !selectableMoment(moment);
      open.addEventListener("click", () => openExactMoment(ref));
      card.append(open);
    }
    return card;
  }

  function renderMoments() {
    const viewerList = $("#p10Moments");
    const creatorList = $("#p10StudioMoments");
    viewerList?.replaceChildren();
    creatorList?.replaceChildren();
    const momentSelect = $("#p10Moment");
    const beforeSelect = $("#p10Before");
    const afterSelect = $("#p10After");
    for (const select of [momentSelect, beforeSelect, afterSelect]) {
      if (!select) continue;
      const label = select === momentSelect ? "Choose an exact moment" : "Choose an exact frame moment";
      select.replaceChildren(element("option", label, { value: "" }));
    }

    for (const moment of chronologicalMoments(moments)) {
      const ref = moment.ref || {};
      const source = exactSource(ref);
      if (!selectableMoment(moment) && !(role === "creator" && editableMoment(moment))) continue;
      const label = `${source.title || source.kind || "Source"} · ${timeLabel(ref.startMs)} · r${ref.sourceRevision} · ${moment.kind || "moment"}${moment.status === "uncertain" ? " · uncertain" : moment.status == null ? " · eligibility unconfirmed" : ""}`;
      if (selectableMoment(moment)) momentSelect?.append(element("option", label, { value: referenceKey(ref) }));
      if (source.kind === "capture" && selectableMoment(moment)) {
        beforeSelect?.append(element("option", label, { value: referenceKey(ref) }));
        afterSelect?.append(element("option", label, { value: referenceKey(ref) }));
      }
      const viewerCard = selectableMoment(moment) ? sourceMomentCard(moment, false) : null;
      const creatorCard = sourceMomentCard(moment, true);
      if (viewerCard) viewerList?.append(viewerCard);
      if (creatorCard) creatorList?.append(creatorCard);
    }
    if (viewerList && !viewerList.childElementCount) viewerList.append(element("p", "No current indexed audience-visible moments are available.", { class: "muted" }));
    if (creatorList && !creatorList.childElementCount) creatorList.append(element("p", "No current audience-visible moments are available to select for a derivative.", { class: "muted" }));
    if (creatorList && role === "creator") renderExplanationAuthoring(creatorList);
    updateControls();
  }

  function updateControls() {
    currentUntimedSource();
    const currentMoment = selectedMoment("#p10Moment");
    const canUseMoment = sourceReady && !!currentMoment;
    for (const selector of ["#p10Concise", "#p10Detailed", "#p10Translate", "#p10VisualDescription"]) {
      if ($(selector)) $(selector).disabled = !canUseMoment || sourceLocks.has("p10Representation");
    }
    if ($("#p10Retrieve")) $("#p10Retrieve").disabled = !sourceReady || !moments.length || sourceLocks.has("p10TimelineQuery");
    if ($("#p10SearchReceived")) $("#p10SearchReceived").disabled = role !== "viewer" || !sourceReady || sourceCheckPending || timelineSearchPending || !$("#p10Topic")?.value.trim();
    const before = selectedMoment("#p10Before");
    const after = selectedMoment("#p10After");
    if ($("#p10Compare")) $("#p10Compare").disabled = !sourceReady || !before || !after || before.ref.sourceId === after.ref.sourceId || sourceLocks.has("p10VisualCompare");
    if ($("#p10Index")) $("#p10Index").disabled = role !== "creator" || !sourceReady || !$("#p10StudioSource")?.value || sourceLocks.has("timeline-index");
    if ($("#p10Derive")) $("#p10Derive").disabled = role !== "creator" || !sourceReady || selectedMaterialRefs().length === 0 || !$("#p10Instruction")?.value.trim() || materialCreateUnknown || sourceLocks.has("studio-create");
    if ($("#p10Grant")) $("#p10Grant").disabled = role !== "creator" || !sourceReady || selectedRefsForSource().length !== 1 || grantCreateUnknown || sourceLocks.has("grant-create");
    if ($("#p10SaveMemory")) $("#p10SaveMemory").disabled = role !== "viewer" || !vaultReady || !sourceReady || memorySaveUnknown || sourceLocks.has("vault-entry-create");
  }

  function selectedRefsForSource() {
    const sourceId = $("#p10StudioSource")?.value;
    return exactSelectedRefs().filter(ref => ref.sourceId === sourceId);
  }

  function syncSourceChoices() {
    const select = $("#p10StudioSource");
    if (!select) return;
    const previous = select.value;
    select.replaceChildren(element("option", "Choose an exact source revision", { value: "" }));
    for (const source of sources.filter(item => item.audienceVisible === true)) {
      select.append(element("option", `${source.title || source.kind || "Source"} · r${source.revision} · audience-visible`, { value: source.id }));
    }
    if (sources.some(source => source.id === previous && source.audienceVisible === true)) select.value = previous;
  }

  function renderResult(host, result, text, extraUncertainty = false) {
    host.replaceChildren();
    host.append(element("p", text || "No text result was returned.", { class: "preserve-lines" }));
    if (result?.comparison?.uncertain === true || extraUncertainty) {
      host.append(element("p", "The selected evidence is uncertain. This result does not establish a cause for the visible difference.", { role: "alert", class: "p10-uncertain" }));
    }
    if (result?.limitations?.length) host.append(element("p", result.limitations.join(" · "), { class: "muted" }));
    if (result?.provider || result?.model) host.append(element("p", `${result.provider || "Provider unknown"}${result.model ? ` · ${result.model}` : ""}`, { class: "muted" }));
    if (result?.provider === "fixture" || result?.provider?.includes("fixture")) host.append(element("p", "Synthetic fixture provider; this is not real AI or vision evidence.", { class: "muted" }));
    const citations = list(result?.citations);
    if (!citations.length) {
      host.append(element("p", "No source citations were returned.", { role: "alert", class: "muted" }));
      return;
    }
    const listHost = element("ul", "", { class: "p10-citations" });
    for (const citation of citations) {
      if (citation.entryId && citation.ref === null) {
        listHost.append(element("li", `Private authored note · entry revision ${citation.entryRevision ?? "unknown"}`));
        continue;
      }
      const ref = citation.ref || {};
      const item = element("li");
      item.append(element("strong", `${citation.title || ref.sourceId || "Source"} · ${timeLabel(ref.startMs)} · revision ${ref.sourceRevision ?? "unknown"}`));
      if (citation.excerpt) item.append(element("p", citation.excerpt));
      item.append(element("p", exactReferenceLabel(ref), { class: "muted" }));
      const open = element("button", "Open cited exact moment", { type: "button", class: "text-button" });
      open.disabled = !exactSource(ref);
      open.addEventListener("click", () => openExactMoment(ref));
      item.append(open);
      listHost.append(item);
    }
    host.append(listHost);
  }

  function imageFromFrame(host, frame, index, onOpen = null) {
    const image = frame?.image;
    if (!image || typeof image.data !== "string" || image.data.length > 5592408 || !["image/png", "image/jpeg", "image/webp"].includes(image.mimeType)) {
      host.append(element("p", `Frame ${index} image is unavailable or exceeds the supported image limits.`, { role: "alert" }));
      return;
    }
    const ref = frame.ref || {};
    const safe = image.data.replace(/\s/g, "");
    if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(safe)) {
      host.append(element("p", `Frame ${index} bytes were malformed and were not displayed.`, { role: "alert" }));
      return;
    }
    const figure = element("figure", "", { class: "p10-frame" });
    const img = element("img", "", { alt: `Authorized frame ${index} at ${timeLabel(ref.startMs)}; visual cause is not inferred` });
    img.src = `data:${image.mimeType};base64,${safe}`;
    const alignment = frame.alignment || {};
    const imageWrap = element("div", "", { class: "p10-region-image" });
    const outline = element("span", "", { class: "p10-region-outline", "aria-hidden": "true" });
    imageWrap.append(img, outline);
    figure.append(imageWrap, element("figcaption", `Frame ${index} · ${exactReferenceLabel(ref)} · captured ${frame.capturedAt || "time unknown"} · ${alignment.origin || "alignment origin unknown"} · ${alignment.captureRunId || "run unknown"}`));
    if (onOpen) {
      const open = element("button", "Open exact frame", { type: "button", class: "text-button" });
      open.addEventListener("click", onOpen);
      figure.append(open);
    }
    const region = element("fieldset");
    region.append(element("legend", `Select a region in frame ${index}`), element("p", "Use percentages from the top-left corner. Select a region for a later comparison. The full authorized frames will be sent and spatial precision is uncertain."));
    const controls = {};
    for (const [key, label, value] of [["left", "Left", 0], ["top", "Top", 0], ["width", "Width", 100], ["height", "Height", 100]]) {
      const wrapper = element("label", `${label} (%) `);
      const input = element("input", "", { type: "number", min: "0", max: "100", step: "1", value: String(value) });
      wrapper.append(input); region.append(wrapper); controls[key] = input;
    }
    const status = element("p", "Whole frame selected.", { role: "status" });
    const update = () => {
      const values = Object.fromEntries(Object.entries(controls).map(([key, input]) => [key, Number(input.value)]));
      if (Object.values(controls).some(input => input.value === "" || !input.checkValidity()) || values.width <= 0 || values.height <= 0 || values.left + values.width > 100 || values.top + values.height > 100) {
        outline.hidden = true; status.textContent = "Choose a non-empty region within the frame."; return;
      }
      outline.hidden = false; Object.assign(outline.style, { left: `${values.left}%`, top: `${values.top}%`, width: `${values.width}%`, height: `${values.height}%` });
      status.textContent = `Region: ${values.left}% from left, ${values.top}% from top, ${values.width}% wide and ${values.height}% high. This selection has not yet been sent for description.`;
    };
    const useRegion = element("button", "Use this region in the next comparison", { type: "button" });
    useRegion.addEventListener("click", () => {
      const values = Object.fromEntries(Object.entries(controls).map(([key, input]) => [key, Number(input.value)]));
      if (Object.values(controls).some(input => input.value === "" || !input.checkValidity()) || values.width <= 0 || values.height <= 0 || values.left + values.width > 100 || values.top + values.height > 100) { update(); return; }
      for (const [selector, value] of [["#p10RegionX", values.left], ["#p10RegionY", values.top], ["#p10RegionWidth", values.width], ["#p10RegionHeight", values.height]]) { const field = $(selector); if (field) field.value = String(value); }
      const enabled = $("#p10RegionEnabled"); if (enabled) enabled.checked = true;
      status.textContent = "Region selected for the next explicit comparison.";
    });
    region.addEventListener("input", update); region.append(status, useRegion); figure.append(region);
    host.append(figure);
  }

  async function showFrameEvidence(host, refs, contextRefs = [], openedRef = null) {
    if (!sourceReady || sourceCheckPending || role !== "viewer") return;
    const scope = identityScope(), epoch = sourceGeneration, view = ++comparisonView;
    stopComparisonSpeech();
    // Discard any old description before checking current image/source access.
    host.replaceChildren(element("p", "Checking exact frame evidence and authorized context…"));
    try {
      const [reads, response, contextReads] = await Promise.all([
        Promise.allSettled(refs.map(ref => readFrame(ref))),
        api.call("sources", null, { scope }),
        Promise.allSettled(contextRefs.map(ref => api.call("p10Timeline", null, ref.sourceId, { scope })))
      ]);
      assertCurrent(scope, epoch);
      if (view !== comparisonView) return;
      const current = list(response?.sources || response?.items || response);
      const sourceFor = ref => current.find(source => source.id === ref.sourceId
        && source.revision === ref.sourceRevision && source.status === "active" && source.audienceVisible === true);
      host.replaceChildren(element("p", "Frame evidence only; no comparison was generated. A cause is not documented by these frames. Available source context is shown separately.", { class: "muted" }));
      const pair = element("div", "", { class: "p10-frame-pair" });
      let available = 0, openedFigure = null;
      for (const [index, ref] of refs.entries()) {
        const read = reads[index], source = sourceFor(ref);
        if (read.status !== "fulfilled" || !source) {
          pair.append(element("p", `Frame ${index + 1} is unavailable or changed. Its image and derived description are not current evidence.`, { role: "alert" }));
          continue;
        }
        available += 1;
        imageFromFrame(pair, read.value, index + 1, () => showFrameEvidence(host, refs, contextRefs, ref));
        const figure = pair.lastElementChild;
        figure.append(element("p", `${source.title || "Source"} · authorized source context: ${source.text || "No text context was supplied; the cause remains unknown."}`, { class: "preserve-lines" }));
        if (referenceKey(ref) === referenceKey(openedRef)) openedFigure = figure;
      }
      host.append(pair);
      if (available !== 2) host.prepend(element("p", "Both exact frames are not available. No before/after description is presented as current; remaining authorized evidence is preserved.", { role: "alert" }));
      for (const [index, ref] of contextRefs.entries()) {
        const read = contextReads[index];
        const moment = read.status === "fulfilled" && sourceFor(ref)
          ? list(read.value?.moments).find(item => referenceKey(item.ref) === referenceKey(ref) && ["available", "uncertain"].includes(item.status)) : null;
        host.append(element("p", moment ? `Authorized context · ${exactReferenceLabel(ref)} · ${moment.text}`
          : "An exact context moment is unavailable; its content and reason are not supplied."));
      }
      if (openedRef) host.prepend(element("p", openedFigure ? `Opened exact frame · ${exactReferenceLabel(openedRef)}`
        : "The requested exact frame is unavailable; remaining authorized evidence is shown.", { role: "status" }));
      if (openedFigure) {
        openedFigure.setAttribute("tabindex", "-1");
        openedFigure.focus({ preventScroll: true });
        openedFigure.scrollIntoView({ block: "nearest" });
      }
    } catch {
      if (resultIsCurrent(scope, epoch) && view === comparisonView)
        host.replaceChildren(element("p", "Frame evidence or source context could not be verified. No previous description is presented as current.", { role: "alert" }));
    }
  }

  function renderComparison(host, result, frames = []) {
    stopComparisonSpeech();
    host.replaceChildren();
    const comparison = result?.comparison;
    if (!comparison) {
      host.append(element("p", "No comparison was returned. No visual conclusion is assumed.", { role: "alert" }));
      return;
    }
    renderResult(host, result, comparison.text, comparison.uncertain === true);
    const frameRefs = list(result?.frames).map(frame => frame.ref);
    const contextRefs = list(result?.citations).map(citation => citation.ref)
      .filter(ref => ref && !frameRefs.some(frameRef => referenceKey(frameRef) === referenceKey(ref)));
    // Visual citations must open authoritative image bytes, not just a text moment.
    for (const [index, citation] of list(result?.citations).entries()) {
      if (!frameRefs.some(ref => referenceKey(ref) === referenceKey(citation.ref))) continue;
      const old = host.querySelectorAll(".p10-citations button")[index];
      if (!old) continue;
      const open = element("button", "Open cited exact frame", { type: "button", class: "text-button" });
      open.addEventListener("click", () => showFrameEvidence(host, frameRefs, contextRefs, citation.ref));
      old.replaceWith(open);
    }
    host.prepend(element("p", "Machine observation; visual causes are not established. Creator explanation, when available, must be inspected in its source context.", { class: "muted" }));
    if (typeof comparison.text === "string" && comparison.text.trim() && window.speechSynthesis && window.SpeechSynthesisUtterance) {
      const listen = element("button", "Read machine observation aloud", { type: "button" });
      const stop = element("button", "Stop reading", { type: "button" });
      const audioStatus = element("p", "Optional browser-generated speech; no creator voice is used.", { role: "status" });
      listen.addEventListener("click", () => {
        if (!sourceReady || sourceCheckPending) return;
        stopComparisonSpeech();
        const utterance = new SpeechSynthesisUtterance(comparison.text);
        comparisonSpeaking = true;
        utterance.onend = () => { comparisonSpeaking = false; audioStatus.textContent = "Reading ended."; };
        utterance.onerror = () => { comparisonSpeaking = false; audioStatus.textContent = "Reading unavailable. The observation remains readable."; };
        window.speechSynthesis.speak(utterance);
        audioStatus.textContent = "Reading machine observation. Stop at any time.";
      });
      stop.addEventListener("click", () => { stopComparisonSpeech(); audioStatus.textContent = "Reading stopped. Text remains available."; });
      host.append(listen, stop, audioStatus);
    }
    const frameHost = element("div", "", { class: "p10-frame-pair" });
    for (const [index, frame] of frames.entries()) imageFromFrame(frameHost, frame, index + 1,
      () => showFrameEvidence(host, frameRefs, contextRefs, frame.ref));
    const returnToCaptions = element("button", "Return to live captions", { type: "button" });
    returnToCaptions.addEventListener("click", () => {
      const target = $("#p12Root h2");
      if (!target) return;
      target.setAttribute("tabindex", "-1");
      target.scrollIntoView({ block: "start" });
      target.focus({ preventScroll: true });
    });
    host.prepend(frameHost, returnToCaptions);
    if (frames.length !== 2) host.prepend(element("p", "Both exact authorized frame images were not available; comparison coverage is incomplete.", { role: "alert" }));
  }

  function renderExplanationAuthoring(host) {
    const section = element("section");
    section.append(element("h3", "Explain two authorized frames"));
    const before = element("select", "", { "aria-label": "Explanation before frame" });
    const after = element("select", "", { "aria-label": "Explanation after frame" });
    for (const select of [before, after]) {
      select.append(element("option", "Choose an exact frame", { value: "" }));
      for (const moment of moments) {
        const source = exactSource(moment.ref);
        if (source?.kind === "capture" && selectableMoment(moment))
          select.append(element("option", `${exactReferenceLabel(moment.ref)}${moment.status === "uncertain" ? " · uncertain" : ""}`, { value: referenceKey(moment.ref) }));
      }
    }
    const input = element("textarea", "", { "aria-label": "Creator explanation", maxlength: "4000", rows: "3" });
    const submit = element("button", "Publish creator explanation", { type: "button" });
    const status = element("p", "Choose two indexed frames from the same capture run in increasing time order.", { role: "status" });
    section.append(element("label", "Before frame"), before, element("label", "After frame"), after, input, submit, status);
    host.append(section);
    submit.addEventListener("click", async () => {
      const first = moments.find(m => referenceKey(m.ref) === before.value);
      const second = moments.find(m => referenceKey(m.ref) === after.value);
      const text = input.value.trim();
      if (!sourceReady || sourceCheckPending || !selectableMoment(first) || !selectableMoment(second) || !text || first.ref.startMs >= second.ref.startMs) {
        status.textContent = "Choose two current frames in increasing time order and enter an explanation."; return;
      }
      const scope = identityScope(), epoch = sourceGeneration;
      submit.disabled = true;
      try {
        await api.call("p10VisualExplanationCreate", { before: first.ref, after: second.ref, text }, { scope });
        assertCurrent(scope, epoch);
        input.value = "";
        status.textContent = "Creator explanation published for these exact source versions.";
      } catch (error) {
        if (resultIsCurrent(scope, epoch)) status.textContent = "Explanation could not be confirmed. Check current source access and refresh before another submission.";
      } finally { /* Reconcile uncertain writes by refreshing; do not repeat automatically. */ }
    });
  }

  async function loadComparisonExplanation(host, refs, scope, epoch) {
    const area = element("section", "", { "aria-label": "Creator explanation" });
    area.append(element("h3", "Creator explanation"), element("p", "Checking for an eligible explanation…", { role: "status" }));
    host.append(area);
    try {
      const response = await api.call("p10VisualExplanations", null, { scope });
      assertCurrent(scope, epoch);
      if (!area.isConnected) return;
      const matches = list(response?.explanations).filter(item => item?.origin === "creator" && Array.isArray(item.refs) && item.refs.length === 2 && item.refs.every((ref, i) => referenceKey(ref) === referenceKey(refs[i])));
      area.replaceChildren(element("h3", "Creator explanation"));
      if (!matches.length) {
        area.append(element("p", "No eligible creator explanation was returned for these exact frame versions. It may not exist or its source access may have changed.")); return;
      }
      for (const item of matches) {
        area.append(element("p", item.text || "Explanation text unavailable.", { class: "preserve-lines" }), element("p", `Creator authored · explanation revision ${item.revision ?? "unknown"} · ${item.authoredAt || "time unavailable"}`, { class: "muted" }));
        for (const ref of item.refs) area.append(element("p", exactReferenceLabel(ref), { class: "muted" }));
      }
    } catch (error) {
      if (resultIsCurrent(scope, epoch) && area.isConnected) area.replaceChildren(element("h3", "Creator explanation"), element("p", "Creator explanations could not be checked. Their availability is unknown.", { role: "status" }));
    }
  }

  async function refreshSources() {
    const scope = identityScope();
    if (!scope.token || !scope.sessionId || !scope.role) return;
    const previousRefs = new Set(selectedRefs);
    clearSourceProtected();
    const epoch = sourceGeneration;
    const failures = [];
    try {
      const sourceResponse = await api.call("sources", null, { scope });
      assertCurrent(scope, epoch);
      sources = list(sourceResponse?.sources || sourceResponse?.items || sourceResponse)
        .filter(source => source?.id && source.status === "active" && Number.isInteger(source.revision) && source.revision > 0)
        .filter(source => scope.role === "creator" || source.audienceVisible === true);
      const nextMoments = [];
      const coverageNotes = [];
      for (const source of sources) {
        try {
          const response = await api.call("p10Timeline", null, source.id, { scope });
          assertCurrent(scope, epoch);
          const coverage = response?.coverage || {};
          if (coverage.missing) coverageNotes.push(`${source.id} r${source.revision}: indexed coverage reports missing data`);
          coverageNotes.push(...list(coverage.limitations).map(item => `${source.id}: ${item}`));
          for (const moment of list(response?.moments)) {
            if (moment?.ref?.sessionId !== scope.sessionId || moment.ref.sourceId !== source.id || moment.ref.sourceRevision !== source.revision) continue;
            nextMoments.push(moment);
          }
        } catch (error) {
          if (error.name === "AbortError") throw error;
          failures.push(`${source.id} r${source.revision}: timeline unavailable (${error.code || "read failed"})`);
        }
      }
      assertCurrent(scope, epoch);
      moments = nextMoments;
      selectedRefs = new Set([...previousRefs].filter(key => nextMoments.some(moment => referenceKey(moment.ref) === key)));
      sourceReady = true;
      renderMoments();
      syncSourceChoices();
      const notes = [...coverageNotes, ...failures];
      writeStatus("#p10ViewerStatus", `${moments.length} exact indexed moment(s) loaded. ${notes.length ? `Coverage gaps: ${notes.join("; ")}` : "No coverage gaps were reported by the sources read."} This does not verify continuous capture or live ingestion.`);
      writeStatus("#p10StudioStatus", `${sources.length} current sources checked. Capture alignment is reported metadata; it does not prove live intake.${notes.length ? ` Gaps: ${notes.join("; ")}` : ""}`);
      if (role === "creator") await refreshMaterials(scope, epoch);
      if (role === "viewer" && vaultToken) await loadVaultEntries();
      updateControls();
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) {
        clearSourceProtected("Source refresh failed. Source-derived outputs and actions remain hidden until a complete retry succeeds.");
        writeStatus("#p10ViewerStatus", "Source refresh failed. No partial snapshot is presented as complete; refresh before continuing.", true);
        writeStatus("#p10StudioStatus", "Source refresh failed. No source-based mutation is enabled.", true);
      }
    }
  }

  async function refreshMaterials(scope, epoch) {
    try {
      const response = await api.call("p10StudioMaterials", null, { scope });
      assertCurrent(scope, epoch);
      materials = list(response?.materials).map(summary => ({ ...summary, version: summary.currentVersion, stale: summary.dependencyState !== "current" }));
      // A collection summary does not establish access to each exact material.
      // Keep retained edits hidden until its individual read succeeds.
      for (const material of materials) lockedMaterials.add(material.id);
      renderMaterials();
      for (const material of [...materials]) await readMaterial(material.id, epoch);
    } catch (error) {
      if (error.name === "AbortError") throw error;
      assertCurrent(scope, epoch);
      materials = [];
      clearResult("#p10Materials");
      writeStatus("#p10StudioStatus", "Creator material collection could not be read. Existing source-derived drafts remain hidden.", true);
    }
  }

  async function runGeneration(operation, buttonSelector, hostSelector, payloadFactory, resultText) {
    if (!sourceReady || sourceCheckPending || sourceLocks.has(operation)) return null;
    if (unresolved.has(operation)) {
      const held = unresolved.get(operation);
      const scope = identityScope();
      const epoch = sourceGeneration;
      sourceLocks.add(operation);
      updateControls();
      try {
        const status = await readOperation(held.requestId, operation);
        assertCurrent(scope, epoch);
        if (status?.state !== "complete") return null;
        const replay = await api.call(operation, held.payload, { scope });
        assertCurrent(scope, epoch);
        renderResult($(hostSelector), replay, resultText(replay));
        unresolved.delete(operation);
        return replay;
      } catch { return null; }
      finally { sourceLocks.delete(operation); updateControls(); }
    }
    if (sourceLocks.has(operation)) return null;
    const scope = identityScope();
    const epoch = sourceGeneration;
    const host = $(hostSelector);
    const button = $(buttonSelector);
    const payload = payloadFactory();
    if (!payload) return null;
    sourceLocks.add(operation);
    if (button) button.disabled = true;
    if (host) host.replaceChildren(element("p", "Request in progress…", { class: "muted" }));
    try {
      const response = await api.call(operation, payload, { scope });
      assertCurrent(scope, epoch);
      unresolved.delete(operation);
      if (host) {
        if (operation === "p10VisualCompare") renderComparison(host, response);
        else renderResult(host, response, resultText(response));
      }
      return response;
    } catch (error) {
      try { assertIdentity(scope); } catch { return null; }
      if (error.name === "AbortError" || !error.status || error.code === "request_pending" || error.code === "request_conflict" || error.code === "operation_unresolved" || error.status >= 500) {
        unresolved.set(operation, { requestId: payload.clientRequestId, payload });
      }
      if (!resultIsCurrent(scope, epoch)) return null;
      if (host) host.replaceChildren(element("p", error.code === "provider_unavailable"
        ? "The requested provider is unavailable. No substitute result was created."
        : error.code === "stale_context"
          ? "A selected source became stale. Refresh and deliberately choose the current exact revision."
          : "The outcome is unresolved or the request failed. Read operation status before choosing a deliberate retry.", { role: "alert" }));
      return null;
    } finally {
      sourceLocks.delete(operation);
      if (resultIsCurrent(scope, epoch) && button) button.disabled = false;
      if (resultIsCurrent(scope, epoch)) updateControls();
    }
  }

  function resultText(result) {
    return result?.answer || result?.representation?.text || result?.comparison?.text || "No generated text was returned.";
  }

  async function readOperation(requestIdValue, operation, vault = false) {
    const scope = identityScope();
    const sourceEpoch = sourceGeneration;
    const vaultEpoch = vaultGeneration;
    const epoch = vault ? vaultEpoch : sourceEpoch;
    const name = vault ? "p10VaultOperation" : "p10SessionOperation";
    try {
      const result = await api.call(name, null, requestIdValue, { scope, ...(vault ? vaultHeaders() : {}) });
      if (vault) assertCurrent(scope, sourceEpoch, epoch);
      else assertCurrent(scope, epoch);
      const status = result?.operation;
      if (status?.state === "failed") {
        if (vault) vaultLocks.delete(operation);
        else unresolved.delete(operation);
        unresolved.delete(operation);
        if (operation === "p10StudioCreate") materialCreateUnknown = false;
        if (operation === "vault-entry-create") memorySaveUnknown = false;
        if (operation === "grant-create") grantCreateUnknown = false;
        writeStatus(vault ? "#p10MemoryStatus" : "#p10StudioStatus", "The operation is confirmed failed. You may deliberately submit a new request if still needed.");
      } else if (status?.state === "complete") {
        if (operation === "p10StudioCreate") { materialCreateUnknown = false; await refreshMaterials(scope, sourceGeneration); }
        if (operation === "vault-entry-create") { memorySaveUnknown = false; await loadVaultEntries(); }
      }
      return status;
    } catch (error) {
      if (error.name !== "AbortError" && (vault ? resultIsCurrent(scope, sourceEpoch, epoch) : resultIsCurrent(scope, epoch))) {
        writeStatus(vault ? "#p10MemoryStatus" : "#p10StudioStatus", "Operation status could not be read. The action remains blocked; no retry was sent.", true);
      }
      return null;
    }
  }

  function selectedQueryRefs() {
    const selected = selectedMoment("#p10Moment");
    return selected ? [selected.ref] : exactSelectedRefs();
  }

  function chronologicalMoments(items) {
    // Offsets are comparable within an identified run. Keep separate/unknown
    // runs in received order rather than inventing a shared clock.
    const runs = new Map();
    const runKey = item => item.captureRunId || item.alignment?.captureRunId || `source:${item.ref.sourceId}`;
    for (const item of items) if (!runs.has(runKey(item))) runs.set(runKey(item), runs.size);
    return [...items].sort((a, b) => runs.get(runKey(a)) - runs.get(runKey(b))
      || a.ref.startMs - b.ref.startMs || a.ref.endMs - b.ref.endMs);
  }

  async function searchReceivedMoments() {
    const query = $("#p10Topic")?.value.trim();
    if (!query || role !== "viewer" || timelineSearchPending || sourceCheckPending) return;
    const scope = identityScope();
    timelineSearchPending = true;
    updateControls();
    try {
      // Read-only freshness check; never replay or replace an AI request.
      await refreshSources();
      assertIdentity(scope);
      const host = $("#p10SearchResults");
      if (!host || !sourceReady || sourceCheckPending) return;
      const terms = new Set(query.toLocaleLowerCase().match(/[\p{L}\p{N}_]+/gu) || []);
      const matching = chronologicalMoments(moments.filter(moment => selectableMoment(moment)
        && (moment.text || "").toLocaleLowerCase().match(/[\p{L}\p{N}_]+/gu)?.some(word => terms.has(word))));
      // Automatic ASR indexing and explicit event classification may name the
      // same source interval. Show one exact ref, preferring its explicit kind.
      const intervals = new Map();
      for (const moment of matching) {
        const key = [moment.ref.sourceId, moment.ref.sourceRevision, moment.ref.startMs, moment.ref.endMs, moment.text].join("|");
        const prior = intervals.get(key);
        if (!prior || (prior.kind === "other" && moment.kind !== "other")) intervals.set(key, moment);
      }
      host.replaceChildren(element("p", "Search matches words in current received text. Moments are ordered within each capture run. Missing or withdrawn context is unavailable; no reason is inferred.", { class: "muted", role: "status" }));
      if (!intervals.size) host.append(element("p", "No current received moments match these words. A reason is not established by these search results. Try the AI action for a question phrased differently; it uses only currently eligible moments.", { role: "status" }));
      for (const moment of intervals.values()) host.append(sourceMomentCard(moment, false, false));
    } catch (error) {
      try {
        assertIdentity(scope);
        writeStatus("#p10SearchResults", "Received context could not be checked. No reason for the change is established; refresh before continuing.", true);
      } catch { /* An earlier identity must not update the current view. */ }
    } finally {
      timelineSearchPending = false;
      updateControls();
    }
  }

  async function retrieveTopic() {
    const query = $("#p10Topic")?.value.trim();
    if (!query || !sourceReady || sourceCheckPending || sourceLocks.has("p10TimelineQuery")) return;
    const refs = selectedQueryRefs();
    const payload = { query, clientRequestId: requestId(), ...(refs.length ? { refs } : {}) };
    await runGeneration("p10TimelineQuery", "#p10Retrieve", "#p10TimelineAnswer", () => payload, resultText);
  }

  let representationView = 0;
  const representationResults = new Map();
  const representationKey = payload => [referenceKey(payload.ref), payload.kind, payload.language].join("|");

  function invalidateRepresentation() {
    representationView += 1;
    clearResult("#p10Representation");
  }

  async function representationEvidence(payload, scope, epoch) {
    const [sourceResponse, timeline] = await Promise.all([
      api.call("sources", null, { scope }),
      api.call("p10Timeline", null, payload.ref.sourceId, { scope })
    ]);
    assertCurrent(scope, epoch);
    const source = list(sourceResponse?.sources || sourceResponse?.items || sourceResponse)
      .find(item => item.id === payload.ref.sourceId && item.revision === payload.ref.sourceRevision
        && item.status === "active" && item.audienceVisible === true);
    const moment = list(timeline?.moments).find(item => referenceKey(item.ref) === referenceKey(payload.ref)
      && ["available", "uncertain"].includes(item.status));
    if (!source || !moment) {
      const error = new Error("representation_context_unavailable");
      error.status = 409; error.code = "stale_context";
      throw error;
    }
    const frame = source.kind === "capture" ? await readFrame(payload.ref) : null;
    assertCurrent(scope, epoch);
    return { source, moment, frame, text: frame ? source.text || "" : moment.text || "" };
  }

  function renderRepresentation(host, result, payload, evidence) {
    const representation = result?.representation;
    if (referenceKey(representation?.ref) !== referenceKey(payload.ref)
        || representation?.kind !== payload.kind || representation?.language !== payload.language
        || !representation.text?.trim() || list(result.citations).length !== 1
        || referenceKey(result.citations[0].ref) !== referenceKey(payload.ref)
        || (result.original && (referenceKey(result.original.ref) !== referenceKey(payload.ref) || result.original.text !== evidence.text)))
      throw new Error("representation_reference_mismatch");
    renderResult(host, result, representation.text);
    const names = { concise: "Concise explanation", detailed: "Detailed explanation", translation: "Translation", visual_description: "Visual description" };
    const original = element("section", "", { class: "p10-representation-original", "aria-label": "Original selected evidence" });
    original.append(element("strong", `${names[payload.kind]} · Requested language: ${payload.language} · Private reading only`),
      element("p", `${evidence.source.title || "Source"} · ${exactReferenceLabel(payload.ref)}`),
      element("p", `Original language: ${result.original?.language || evidence.source.language || "und (not recorded)"}. ${evidence.frame ? "Creator-authored frame context; not ASR or an inferred visual fact." : "Exact selected source text."}`),
      element("p", evidence.text || "No original text context was supplied. The exact frame is shown below.", { class: "preserve-lines" }));
    if (evidence.frame) {
      const image = evidence.frame.image;
      const img = element("img", "", { alt: `Original authorized frame · ${exactReferenceLabel(payload.ref)}` });
      img.src = `data:${image.mimeType};base64,${image.data}`;
      original.append(img, element("small", `Original frame · captured ${evidence.frame.capturedAt || "time unknown"} · operator-reported timing; live capture is not established.`));
    }
    host.prepend(original);
  }

  async function represent(kind) {
    const moment = selectedMoment("#p10Moment");
    if (!sourceReady || sourceCheckPending || sourceLocks.has("p10Representation") || !moment) return;
    const language = $("#p10Language")?.value.trim() || "en";
    if (!/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(language)) {
      invalidateRepresentation();
      writeStatus("#p10Representation", "Enter a language tag such as en or es-MX. Language coverage depends on the selected provider.", true);
      return;
    }
    const payload = { ref: moment.ref, kind, language };
    const scope = identityScope(), epoch = sourceGeneration, view = ++representationView;
    const cacheKey = JSON.stringify([scope.epoch, scope.actorBinding, representationKey(payload)]);
    const host = $("#p10Representation");
    const current = () => resultIsCurrent(scope, epoch) && view === representationView
      && referenceKey(selectedMoment("#p10Moment")?.ref) === referenceKey(payload.ref)
      && ($("#p10Language")?.value.trim() || "en") === language;
    const operation = "p10Representation";
    const held = unresolved.get(operation);
    let sentPayload = null;
    sourceLocks.add(operation); updateControls();
    host.replaceChildren(element("p", "Checking this exact moment and representation…"));
    try {
      if (held && representationKey(held.payload) !== representationKey(payload)) {
        const status = await readOperation(held.requestId, operation);
        if (current()) host.textContent = `An earlier representation is bound to a different moment, kind or language (${held.payload.kind}, ${held.payload.language}). Its status is ${status?.state || "unavailable"}. Select that exact representation to inspect it; no new request was sent.`;
        return;
      }
      const evidence = await representationEvidence(payload, scope, epoch);
      if (!current()) return;
      const cached = representationResults.get(cacheKey);
      if (cached && !held) {
        renderRepresentation(host, cached, payload, evidence);
        return;
      }
      if (held) {
        const status = await readOperation(held.requestId, operation);
        if (!current()) return;
        if (status?.state !== "complete") {
          host.textContent = "The earlier representation is unresolved or failed. No automatic retry or replacement was sent.";
          return;
        }
        sentPayload = held.payload;
      } else sentPayload = { ...payload, clientRequestId: requestId() };
      const response = await api.call(operation, sentPayload, { scope });
      assertCurrent(scope, epoch);
      unresolved.delete(operation);
      if (!current()) return;
      renderRepresentation(host, response, payload, evidence);
      representationResults.set(cacheKey, response);
    } catch (error) {
      try { assertIdentity(scope); } catch { return; }
      if (sentPayload && (error.name === "AbortError" || !error.status || error.code === "request_pending" || error.code === "request_conflict" || error.code === "operation_unresolved" || error.status >= 500))
        unresolved.set(operation, { requestId: sentPayload.clientRequestId, payload: sentPayload });
      if (current()) host.textContent = error.code === "stale_context"
        ? "This exact moment is unavailable or changed. No previous representation is current; refresh and deliberately select its current revision."
        : "This representation could not be verified or its outcome is unresolved. No substitute or automatic retry was created.";
    } finally {
      sourceLocks.delete(operation);
      updateControls();
    }
  }

  async function compareFrames() {
    const before = selectedMoment("#p10Before");
    const after = selectedMoment("#p10After");
    const view = ++comparisonView;
    if (!sourceReady || sourceCheckPending || sourceLocks.has("p10VisualCompare") || !before || !after || before.ref.sourceId === after.ref.sourceId) return;
    if (unresolved.has("p10VisualCompare")) {
      const held = unresolved.get("p10VisualCompare");
      const replayScope = identityScope();
      const replayEpoch = sourceGeneration;
      sourceLocks.add("p10VisualCompare");
      updateControls();
      try {
        const status = await readOperation(held.requestId, "p10VisualCompare");
        assertCurrent(replayScope, replayEpoch);
        if (status?.state !== "complete") return;
        const frames = await Promise.all([readFrame(held.payload.before), readFrame(held.payload.after)]);
        assertCurrent(replayScope, replayEpoch);
        const replay = await api.call("p10VisualCompare", held.payload, { scope: replayScope });
        assertCurrent(replayScope, replayEpoch);
        if (view !== comparisonView) return;
        renderComparison($("#p10Comparison"), replay, frames);
        await loadComparisonExplanation($("#p10Comparison"), [held.payload.before, held.payload.after], replayScope, replayEpoch);
        unresolved.delete("p10VisualCompare");
      } catch { /* The original request remains blocked. */ }
      finally { sourceLocks.delete("p10VisualCompare"); updateControls(); }
      return;
    }
    const scope = identityScope();
    const epoch = sourceGeneration;
    const host = $("#p10Comparison");
    stopComparisonSpeech();
    const button = $("#p10Compare");
    let payload = null;
    sourceLocks.add("p10VisualCompare");
    if (button) button.disabled = true;
    host.replaceChildren(element("p", "Checking both exact authorized frame records…", { class: "muted" }));
    try {
      const frames = await Promise.all([readFrame(before.ref), readFrame(after.ref)]);
      assertCurrent(scope, epoch);
      const contextRefs = exactSelectedRefs().filter(ref => referenceKey(ref) !== referenceKey(before.ref) && referenceKey(ref) !== referenceKey(after.ref)).slice(0, 8);
      let region;
      if ($("#p10RegionEnabled")?.checked) {
        const fields = ["#p10RegionX", "#p10RegionY", "#p10RegionWidth", "#p10RegionHeight"].map(selector => $(selector));
        const values = fields.map(field => Number(field?.value));
        if (fields.some(field => !field || field.value === "" || !field.checkValidity()) || values.some(value => !Number.isInteger(value)) || values[2] <= 0 || values[3] <= 0 || values[0] + values[2] > 100 || values[1] + values[3] > 100) {
          host.replaceChildren(element("p", "Choose a non-empty region inside the frame before comparing.", { role: "alert" })); return;
        }
        region = { x: values[0] * 100, y: values[1] * 100, width: values[2] * 100, height: values[3] * 100 };
      }
      payload = { before: before.ref, after: after.ref, contextRefs, clientRequestId: requestId(), ...(region ? { region } : {}) };
      const response = await api.call("p10VisualCompare", payload, { scope });
      assertCurrent(scope, epoch);
      if (view !== comparisonView) return;
      renderComparison(host, response, frames);
      await loadComparisonExplanation(host, [before.ref, after.ref], scope, epoch);
    } catch (error) {
      try { assertIdentity(scope); } catch { return; }
      if (payload && (error.name === "AbortError" || !error.status || error.code === "request_pending" || error.code === "request_conflict" || error.code === "operation_unresolved" || error.status >= 500)) {
        unresolved.set("p10VisualCompare", { requestId: payload.clientRequestId, payload });
      }
      if (resultIsCurrent(scope, epoch)) {
        host.replaceChildren(element("p", "One or both exact frames are missing, stale, ambiguous, or unavailable, or the comparison outcome is unresolved. Read the operation status before another request.", { role: "alert" }));
      }
    } finally {
      sourceLocks.delete("p10VisualCompare");
      if (resultIsCurrent(scope, epoch)) updateControls();
    }
  }

  async function readFrame(ref) {
    const scope = identityScope();
    const epoch = sourceGeneration;
    const query = new URLSearchParams({ sourceId: ref.sourceId, sourceRevision: String(ref.sourceRevision), momentId: ref.momentId, startMs: String(ref.startMs), endMs: String(ref.endMs) });
    const response = await api.call("p10Frame", null, query, { scope });
    assertCurrent(scope, epoch);
    const frame = response?.frame;
    if (referenceKey(frame?.ref) !== referenceKey(ref)) throw new Error("frame_reference_mismatch");
    const image = frame?.image;
    if (!image || !["image/png", "image/jpeg", "image/webp"].includes(image.mimeType)
        || typeof image.data !== "string" || image.data.length > 5592408
        || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(image.data)) {
      throw new Error("frame_image_unavailable");
    }
    return frame;
  }

  async function indexSourceMoment() {
    const source = sourceMap().get($("#p10StudioSource")?.value);
    if (!source || role !== "creator") return;
    const button = $("#p10Index");
    const scope = identityScope();
    const epoch = sourceGeneration;
    const startMs = Number($("#p10Start")?.value);
    const endMs = Number($("#p10End")?.value);
    if (source.kind !== "capture" && (!Number.isInteger(startMs) || !Number.isInteger(endMs) || startMs < 0 || endMs <= startMs)) {
      writeStatus("#p10StudioStatus", "Enter a valid, explicit start and end offset in milliseconds.", true);
      return;
    }
    if (sourceLocks.has("timeline-index")) return;
    sourceLocks.add("timeline-index");
    if (button) button.disabled = true;
    try {
      const payload = source.kind === "capture"
        ? { sourceId: source.id, sourceRevision: source.revision, frame: true }
        : { sourceId: source.id, sourceRevision: source.revision, segments: [{ startMs, endMs, kind: $("#p10Kind")?.value || "other" }] };
      await api.call("p10TimelineIndex", payload, { scope });
      assertCurrent(scope, epoch);
      writeStatus("#p10StudioStatus", "Index request accepted. Refreshing the server-derived moment, exact time, and coverage.");
      await refreshSources();
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) writeStatus("#p10StudioStatus", error.code === "alignment_unavailable"
        ? "The source has no usable alignment. No guessed timestamp was created."
        : "Indexing could not be confirmed. Refresh source state before another deliberate attempt.", true);
    } finally {
      sourceLocks.delete("timeline-index");
      if (resultIsCurrent(scope, epoch) && button) updateControls();
    }
  }

  function publishedLink(material) {
    const version = material.version ?? material.currentVersion;
    const joinCode = state.session?.joinCode || state.joinCode;
    const refs = list(material.refs);
    if (!sourceReady || sourceCheckPending || role !== "creator" || !joinCode || !material.id
        || !Number.isInteger(version) || material.approvedVersion !== version
        || (material.currentVersion !== undefined && material.currentVersion !== version)
        || list(material.dependencies).some(dependency => dependency.state !== "current")
        || material.status !== "published" || material.dependencyState !== "current"
        || material.requiresReview === true || material.stale === true || material.redacted === true
        || lockedMaterials.has(material.id) || unresolved.has(`material:${material.id}`)
        || edits.has(material.id) || !refs.length
        || refs.some(ref => !exactSource(ref) || exactSource(ref).audienceVisible !== true)) return null;
    const path = `/p10/public/${encodeURIComponent(joinCode)}/${encodeURIComponent(material.id)}`;
    const key = `${material.id}:${version}`;
    const supplied = publicationUrls.has(key) ? publicationUrls.get(key) : path;
    return safePublishedUrl(supplied, location.origin, path);
  }

  function renderMaterials(openMaterialId = null) {
    const host = $("#p10Materials");
    if (!host) return;
    host.replaceChildren();
    if (!materials.length) host.append(element("p", "No creator materials are currently listed.", { class: "muted" }));
    for (const material of materials) {
      const card = element("article", "", { class: "p10-moment" });
      const version = material.version ?? material.currentVersion;
      const stale = material.stale === true || material.dependencyState !== "current";
      const locked = lockedMaterials.has(material.id);
      card.append(element("strong", locked ? `Material · v${version ?? "?"} · current access unconfirmed` : `${material.title || material.format || "Material"} · v${version ?? "?"} · ${material.status || "draft"}`));
      if (material.status === "draft") card.append(element("p", "Untrusted editable draft: check claims against the exact sources below. Preview and approve this version before a cue; withdraw to reject it.", { class: "muted" }));
      const publicHref = publishedLink(material);
      if (publicHref) card.append(element("a", `Open published version ${version}`, {
        href: publicHref, target: "_blank", rel: "noopener noreferrer", class: "button secondary"
      }));
      if (stale) card.append(element("p", `Source dependency state: ${material.dependencyState || "requires review"}. Select newly indexed current moments, edit and re-review exact version.`, { role: "alert" }));
      else if (material.requiresReview === true) card.append(element("p", "This exact version requires creator review before approval or publication.", { role: "status" }));
      for (const dependency of locked ? [] : list(material.dependencies)) {
        const state = ["current", "stale", "unavailable"].includes(dependency.state) ? dependency.state : "unconfirmed";
        const recorded = Number.isInteger(dependency.recordedRevision) ? dependency.recordedRevision : "unknown";
        const current = Number.isInteger(dependency.currentRevision) ? dependency.currentRevision : "unknown";
        card.append(element("p", `Source ${dependency.sourceId || "unknown"}: recorded revision ${recorded}, current revision ${current} — ${state}`, { class: "muted" }));
      }
      for (const ref of locked ? [] : list(material.refs)) card.append(element("p", exactReferenceLabel(ref), { class: "muted" }));
      if (!locked && !stale && typeof material.continuationWorkId === "string" && material.continuationWorkId)
        card.append(element("p", `Reviewed work ID: ${material.continuationWorkId} · Studio material ID: ${material.id} · Current version: ${version}`, { class: "muted" }));
      const details = element("details");
      if (material.id === openMaterialId) details.open = true;
      details.append(element("summary", "Edit this exact version"));
      const draft = lockedMaterials.has(material.id) ? { title: "", body: "", selectedKeys: [] }
        : edits.get(material.id) || material;
      // An ordinary stale draft may still be returned for private creator review.
      // Missing/withdrawn content stays absent because the server omits its body.
      if (!locked && stale && typeof material.body === "string")
        details.append(element("p", "Past draft content for private review only. It has not been updated to the corrected source. Deliberately select current exact references and edit before saving a new version.", { role: "alert", class: "p10-uncertain" }));
      const title = element("input", "", { maxlength: "160", "aria-label": "Material title" });
      title.value = draft.title || "";
      const body = element("textarea", draft.body || "", { maxlength: "12000", rows: "4", "aria-label": "Material body" });
      title.disabled = body.disabled = lockedMaterials.has(material.id);
      let missingKeys = [];
      const markDirty = (referencesChanged = false) => {
        if (referencesChanged) missingKeys = [];
        edits.set(material.id, { title: title.value, body: body.value, selectedKeys: [...refsField.selectedOptions].map(option => option.value).concat(missingKeys) });
        reviewedVersions.delete(`${material.id}:${version}`);
        clearResult("#p10MaterialPreview");
        card.querySelector("a")?.remove();
        for (const button of card.querySelectorAll("button[data-review-action]")) button.disabled = true;
      };
      title.addEventListener("input", () => markDirty());
      body.addEventListener("input", () => markDirty());
      const refsField = element("select", "", { multiple: "", "aria-label": "Select exact source references for the next version" });
      refsField.disabled = lockedMaterials.has(material.id);
      const currentKeys = new Set(draft.selectedKeys || list(material.refs).map(referenceKey));
      const options = locked ? [] : materialOptions(material);
      missingKeys = [...currentKeys].filter(key => !options.some(candidate => referenceKey(candidate.ref) === key));
      for (const candidate of options) {
        const option = element("option", `${exactReferenceLabel(candidate.ref)}${candidate.inherited ? " · inherited from this accepted material" : candidate.untimed ? "" : candidate.status === "uncertain" ? " · uncertain alignment" : candidate.status == null ? " · eligibility unconfirmed" : ""}`, { value: referenceKey(candidate.ref) });
        option.selected = currentKeys.has(option.value);
        refsField.append(option);
      }
      details.append(element("p", "Source eligibility is checked by the server during preview and approval. An unconfirmed status does not establish publication rights.", { class: "muted" }));
      const missingNotice = element("p", missingKeys.length ? "A previously selected source reference is no longer available. Review and change the selection before saving; unavailable content is not shown." : "", { role: "status" });
      details.append(missingNotice);
      const save = element("button", "Save as a new version", { type: "button", class: "button secondary" });
      save.disabled = missingKeys.length > 0 || lockedMaterials.has(material.id) || unresolved.has(`material:${material.id}`);
      refsField.addEventListener("change", () => {
        markDirty(true);
        missingNotice.textContent = "";
        save.disabled = lockedMaterials.has(material.id) || unresolved.has(`material:${material.id}`);
      });
      save.addEventListener("click", () => saveMaterial(material, title.value, body.value, [...refsField.selectedOptions].map(option => option.value)));
      const read = element("button", "Read current version", { type: "button", class: "button secondary" });
      read.addEventListener("click", () => readMaterial(material.id));
      details.append(title, body, refsField, save, read);
      card.append(details);
      for (const [action, label] of [["preview", "Preview exact version"], ["approve", "Approve exact version"], ["publish", "Publish exact version"], ["withdraw", "Withdraw exact version"]]) {
        const button = element("button", label, { type: "button", class: action === "publish" ? "button primary" : "button secondary" });
        button.setAttribute("data-review-action", action);
        const reviewed = reviewedVersions.has(`${material.id}:${version}`) && !edits.has(material.id);
        button.disabled = lockedMaterials.has(material.id) || unresolved.has(`material:${material.id}`) || edits.has(material.id) || !Number.isInteger(version)
          || ((action === "approve" || action === "publish") && (stale || !reviewed))
          || (action === "publish" && material.status !== "approved");
        button.addEventListener("click", () => materialAction(material, action));
        card.append(button);
      }
      host.append(card);
    }
  }

  async function readMaterial(materialId, sourceEpoch = sourceGeneration) {
    const scope = identityScope();
    try {
      const response = await api.call("p10StudioMaterial", null, materialId, { scope });
      assertCurrent(scope, sourceEpoch);
      const material = response?.material;
      if (material?.id !== materialId || !Number.isInteger(material.currentVersion ?? material.version)) throw new Error("material_shape_invalid");
      materials = materials.map(item => item.id === material.id ? { ...material, stale: material.dependencyState !== "current" } : item);
      publicationUrls.delete(`${material.id}:${material.version ?? material.currentVersion}`);
      lockedMaterials.delete(material.id);
      unresolved.delete(`material:${material.id}`);
      renderMaterials();
      return material;
    } catch (error) {
      if (error.name === "AbortError") throw error;
      if (resultIsCurrent(scope, sourceEpoch)) {
        lockedMaterials.add(materialId);
        materials = materials.map(item => item.id === materialId ? { id: item.id, currentVersion: item.currentVersion, version: item.version, dependencyState: "unconfirmed", requiresReview: true } : item);
        clearResult("#p10MaterialPreview");
        writeStatus("#p10StudioStatus", "Exact material read failed. Its source-derived body stays hidden until a successful readback.", true);
        renderMaterials();
      }
      return null;
    }
  }

  async function saveMaterial(material, title, body, selectedKeys) {
    if (lockedMaterials.has(material.id) || unresolved.has(`material:${material.id}`)) return;
    const current = materials.find(item => item.id === material.id);
    if (current !== material || !sourceReady || sourceCheckPending) return;
    const options = materialOptions(current);
    const refs = selectedKeys.map(key => options.find(item => referenceKey(item.ref) === key)?.ref).filter(Boolean);
    const requiredInherited = inheritedRefs(current);
    const allForeign = list(current.refs).filter(ref => ref?.sessionId !== identityScope().sessionId);
    if (!refs.length || refs.length !== selectedKeys.length || requiredInherited.length !== allForeign.length
        || requiredInherited.some(ref => !selectedKeys.includes(referenceKey(ref)))) {
      writeStatus("#p10StudioStatus", "Choose current exact source moments and retain all inherited references for this material.", true);
      return;
    }
    const scope = identityScope();
    const epoch = sourceGeneration;
    edits.set(material.id, { ...material, title, body, selectedKeys });
    reviewedVersions.delete(`${material.id}:${material.version ?? material.currentVersion}`);
    lockedMaterials.add(material.id);
    renderMaterials();
    try {
      const response = await api.call("p10StudioPatch", { version: material.version ?? material.currentVersion, title, body, refs }, material.id, { scope });
      assertCurrent(scope, epoch);
      const updated = response?.material;
      if (updated?.id !== material.id || !Number.isInteger(updated.currentVersion ?? updated.version)) throw new Error("material_shape_invalid");
      materials = materials.map(item => item.id === updated.id ? { ...updated, stale: updated.dependencyState !== "current" } : item);
      edits.delete(material.id);
      lockedMaterials.delete(material.id);
      await readMaterial(material.id, epoch);
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) {
        unresolved.set(`material:${material.id}`, true);
        writeStatus("#p10StudioStatus", "Save outcome is unresolved or conflicted. Your title/body edits remain in the editor; read the current version before any further mutation.", true);
      }
    } finally {
      if (resultIsCurrent(scope, epoch)) renderMaterials();
    }
  }

  async function materialAction(material, action) {
    if (lockedMaterials.has(material.id) || unresolved.has(`material:${material.id}`)) return;
    const scope = identityScope();
    const epoch = sourceGeneration;
    const version = material.version ?? material.currentVersion;
    if (["approve", "publish", "withdraw"].includes(action) && !confirm(`${action[0].toUpperCase()}${action.slice(1)} this exact material version (${version})?`)) return;
    lockedMaterials.add(material.id);
    renderMaterials();
    try {
      if (action === "preview") {
        reviewedVersions.delete(`${material.id}:${version}`);
        clearResult("#p10MaterialPreview");
        const response = await api.call("p10StudioPreview", { version }, material.id, { scope });
        assertCurrent(scope, epoch);
        const preview = response?.preview;
        if (preview?.materialId !== material.id || preview.version !== version || typeof preview.eligible !== "boolean") throw new Error("preview_shape_invalid");
        const host = $("#p10MaterialPreview");
        host.replaceChildren(element("h4", `${preview?.title || "Preview"} · exact version ${preview?.version ?? "unknown"}`));
        host.append(element("p", `Material ${preview.materialId} · private preview of exact version ${preview.version}`, { class: "muted" }));
        host.append(element("p", preview?.body || "No preview body was returned.", { class: "preserve-lines" }));
        host.append(element("p", preview?.eligible ? "Eligible for creator review." : "Not eligible; sources or rights require review.", { role: preview?.eligible ? "status" : "alert" }));
        for (const ref of list(preview?.refs)) host.append(element("p", exactReferenceLabel(ref), { class: "muted" }));
        if (preview?.eligible === true) reviewedVersions.add(`${material.id}:${version}`);
        renderMaterials();
      } else {
        const response = await api.call("p10StudioAction", { version }, material.id, action, { scope });
        assertCurrent(scope, epoch);
        const updated = response?.material;
        if (updated?.id !== material.id || (updated.currentVersion ?? updated.version) !== version || updated.status !== ({ approve: "approved", publish: "published", withdraw: "withdrawn" })[action]) throw new Error("material_action_unconfirmed");
        if (action === "publish") {
          // Missing URL permits the documented route; a supplied invalid URL does not.
          const key = `${material.id}:${version}`;
          if (response?.publicUrl === undefined) publicationUrls.delete(key);
          else publicationUrls.set(key, response.publicUrl);
        }
        materials = materials.map(item => item.id === material.id ? { ...updated, stale: updated?.dependencyState !== "current" } : item);
        if (action !== "preview") reviewedVersions.delete(`${material.id}:${version}`);
      }
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) {
        reviewedVersions.delete(`${material.id}:${version}`);
        unresolved.set(`material:${material.id}`, true);
        writeStatus("#p10StudioStatus", "Material action outcome is uncertain. No action was retried; reading back the exact material.", true);
        const current = await readMaterial(material.id, epoch);
        if (current) unresolved.delete(`material:${material.id}`);
      }
    } finally {
      if (resultIsCurrent(scope, epoch)) {
        lockedMaterials.delete(material.id);
        renderMaterials();
      }
    }
  }

  async function createMaterial() {
    if (materialCreateUnknown || sourceLocks.has("studio-create")) return;
    const refs = selectedMaterialRefs();
    const instruction = $("#p10Instruction")?.value.trim();
    if (!refs.length || !instruction) return;
    const scope = identityScope();
    const epoch = sourceGeneration;
    const payload = { format: $("#p10Format")?.value, refs, instruction, clientRequestId: requestId() };
    sourceLocks.add("studio-create");
    updateControls();
    try {
      const response = await api.call("p10StudioCreate", payload, { scope });
      assertCurrent(scope, epoch);
      const material = response?.material;
      if (!material?.id) throw new Error("material_shape_invalid");
      materialCreateUnknown = false;
      await refreshMaterials(scope, epoch);
      writeStatus("#p10StudioStatus", "Draft created from selected exact sources or moments. Review/edit the listed version; creation did not approve or publish it.");
    } catch (error) {
      try { assertIdentity(scope); } catch { return; }
      if (error.name === "AbortError" || !error.status || error.status >= 500 || error.status === 409) {
        materialCreateUnknown = true;
        unresolved.set("p10StudioCreate", { requestId: payload.clientRequestId, payload });
      }
      if (resultIsCurrent(scope, epoch)) writeStatus("#p10StudioStatus", materialCreateUnknown
        ? "Material creation is unresolved. Use Check draft request before another draft."
        : "Material creation failed. You may deliberately try again.", true);
    } finally {
      sourceLocks.delete("studio-create");
      if (resultIsCurrent(scope, epoch)) updateControls();
    }
  }

  function selectedMomentForMemory() {
    const moment = selectedMoment("#p10Moment");
    return moment || null;
  }

  async function discoverRetentionGrants(explicitRef = null) {
    const scope = identityScope();
    const epoch = sourceGeneration;
    const grantsEpoch = grantGeneration;
    const moment = explicitRef ? null : selectedMomentForMemory();
    if (role !== "viewer" && role !== "creator") return;
    const ref = explicitRef || moment?.ref;
    if (!ref || !exactSource(ref) || (role === "viewer" && !moment)) return;
    const params = new URLSearchParams({ sourceId: ref.sourceId, sourceRevision: String(ref.sourceRevision), momentId: ref.momentId, startMs: String(ref.startMs), endMs: String(ref.endMs) });
    clearResult("#p10MemoryGrant");
    try {
      const result = await api.call("p10RetentionGrantLookup", null, `?${params}`, { scope });
      assertCurrent(scope, epoch);
      if (grantsEpoch !== grantGeneration) return;
      grants = list(result?.grants).filter(grant => grant.status === "active" && referenceKey(grant.ref) === referenceKey(ref));
      if (role === "creator") grantCreateUnknown = false;
      if (role === "creator") { renderGrants(); return; }
      const select = $("#p10MemoryGrant");
      if (select) {
        select.replaceChildren(element("option", grants.length ? "Choose this exact active grant" : "No active grant for this exact moment", { value: "" }));
        for (const grant of grants) select.append(element("option", `Active grant ${grant.id} · exact revision ${ref.sourceRevision}`, { value: grant.id }));
      }
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) writeStatus(role === "creator" ? "#p10StudioStatus" : "#p10MemoryStatus", "Exact retention-grant status could not be confirmed. Source retention is unavailable until readback.", true);
    }
  }

  function renderGrants() {
    const host = $("#p10Grants");
    if (!host) return;
    host.replaceChildren();
    for (const grant of grants) {
      const row = element("div", "", { class: "p10-grant-row" });
      row.append(element("p", `Active retention grant ${grant.id} · ${exactReferenceLabel(grant.ref)}. Purpose: private cross-session viewer memory.`));
      const revoke = element("button", "Revoke this grant", { type: "button", class: "button danger" });
      revoke.addEventListener("click", () => revokeGrant(grant, row, revoke));
      row.append(revoke);
      host.append(row);
    }
  }

  async function createGrant() {
    const refs = selectedRefsForSource();
    if (role !== "creator" || refs.length !== 1 || grantCreateUnknown || sourceLocks.has("grant-create")) return;
    const source = exactSource(refs[0]);
    if (!source || !confirm(`Grant private cross-session retention for ${exactReferenceLabel(refs[0])}? This is explicit consent for this exact audience-visible reference only.`)) return;
    const scope = identityScope();
    const epoch = sourceGeneration;
    grantGeneration += 1;
    const grantsEpoch = grantGeneration;
    sourceLocks.add("grant-create");
    updateControls();
    try {
      const response = await api.call("p10RetentionGrants", { ref: refs[0], consent: true }, { scope });
      assertCurrent(scope, epoch);
      if (grantsEpoch !== grantGeneration) throw new DOMException("Grant response expired", "AbortError");
      grantGeneration += 1;
      if (response?.grant) grants.push(response.grant);
      renderGrants();
      writeStatus("#p10StudioStatus", "Grant is active for the exact selected reference. The viewer still chooses whether to retain it.");
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) {
        grantCreateUnknown = true;
        writeStatus("#p10StudioStatus", "Grant creation outcome is unknown. It was not repeated; refresh authorization before any new grant.", true);
      }
    } finally {
      sourceLocks.delete("grant-create");
      if (resultIsCurrent(scope, epoch)) updateControls();
    }
  }

  async function revokeGrant(grant, row, button) {
    if (!confirm(`Revoke exact retention grant ${grant.id}? Future queries will be denied source access.`)) return;
    const scope = identityScope();
    const epoch = sourceGeneration;
    grantGeneration += 1;
    const grantsEpoch = grantGeneration;
    button.disabled = true;
    try {
      await api.call("p10RetentionGrantDelete", null, grant.id, { scope });
      assertCurrent(scope, epoch);
      if (grantsEpoch !== grantGeneration) throw new DOMException("Grant response expired", "AbortError");
      grantGeneration += 1;
      row.replaceChildren(element("p", `Grant ${grant.id} revoked. Source-backed saved items must be rechecked.`));
      grants = grants.filter(item => item.id !== grant.id);
      clearVaultProtected("Source retention rights changed. Private memory results were cleared; reload to recheck saved entries.");
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) writeStatus("#p10StudioStatus", "Grant revocation is unresolved. The control remains locked until explicit readback.", true);
    }
  }

  function vaultHeaders(includeViewer = false, scope = identityScope()) {
    if (!vaultToken) throw new Error("vault_capability_required");
    const headers = { Authorization: `Bearer ${vaultToken}` };
    if (includeViewer) headers["X-Viewer-Capability"] = scope.token;
    return { headers };
  }

  async function vaultCall(name, body, ...args) {
    const scope = identityScope();
    const epoch = vaultGeneration;
    const sourceEpoch = sourceGeneration;
    const response = await api.call(name, body, ...args, { scope, ...vaultHeaders(name === "p10VaultEntryCreate", scope) });
    assertCurrent(scope, sourceEpoch, epoch);
    return response;
  }

  function renderVaultEntries() {
    const host = $("#p10Memories");
    if (!host) return;
    host.replaceChildren();
    for (const entry of vaultEntries) {
      const card = element("article", "", { class: "p10-moment" });
      const active = element("input", "", { type: "checkbox", "aria-label": `Use memory ${entry.id} in a private query` });
      active.checked = entry.active === true;
      active.addEventListener("change", () => patchVaultEntry(entry, { active: active.checked }));
      const interpretation = element("textarea", entry.interpretation || "", { maxlength: "4000", rows: "3", "aria-label": "Edit private interpretation" });
      const past = element("textarea", entry.pastStatement || "", { maxlength: "4000", rows: "2", "aria-label": "Edit your record of the past statement" });
      const correction = element("textarea", entry.correction || "", { maxlength: "4000", rows: "2", "aria-label": "Edit your note about a current correction" });
      const save = element("button", "Save private memory", { type: "button", class: "button secondary" });
      save.addEventListener("click", () => patchVaultEntry(entry, { interpretation: interpretation.value.trim(), pastStatement: past.value.trim() || null, correction: correction.value.trim() || null }));
      const forget = element("button", "Forget this private item", { type: "button", class: "button danger" });
      forget.addEventListener("click", () => forgetVaultEntry(entry, card));
      const stateLabel = entry.status === "available" ? "Available" : "Source unavailable";
      card.append(active, element("strong", `${stateLabel} · entry revision ${entry.revision}`));
      card.append(element("p", entry.ref ? exactReferenceLabel(entry.ref) : "Private note; no source reference", { class: "muted" }));
      if (entry.status !== "available") { active.disabled = true; interpretation.disabled = true; past.disabled = true; correction.disabled = true; save.disabled = true; }
      card.append(element("label", "Personal interpretation"), interpretation, element("label", "Past statement as you recorded it"), past, element("label", "Your note about a current correction (not verified as creator-authored)"), correction);
      const creatorCorrection = entry.creatorCorrection;
      card.append(element("h4", "Creator correction"));
      if (creatorCorrection && typeof creatorCorrection.text === "string" && creatorCorrection.ref && creatorCorrection.correctedAt) {
        card.append(element("p", creatorCorrection.text, { class: "preserve-lines" }), element("p", `Creator correction · ${creatorCorrection.correctedAt} · ${exactReferenceLabel(creatorCorrection.ref)}`, { class: "muted" }));
      } else {
        card.append(element("p", "No eligible creator correction is available. A correction may not exist, or its source or retention access may have changed.", { class: "muted" }));
      }
      if (entry.ref && entry.active === true && entry.status === "available") {
        const resume = element("button", "Resume this retained moment", { type: "button", class: "button secondary" });
        resume.addEventListener("click", () => resumeVaultEntry(entry));
        card.append(resume);
      }
      card.append(save, forget);
      host.append(card);
    }
    const queryEnabled = vaultReady && vaultEntries.some(entry => entry.active === true && entry.status === "available") && !vaultLocks.has("vault-query");
    if ($("#p10QueryMemory")) $("#p10QueryMemory").disabled = !queryEnabled;
  }

  async function resumeVaultEntry(entry) {
    if (!vaultReady || vaultLocks.has("resume")) return;
    const scope = identityScope(), epoch = vaultGeneration, sourceEpoch = sourceGeneration;
    vaultLocks.add("resume"); clearResult("#p10MemoryAnswer");
    writeStatus("#p10MemoryStatus", "Checking this retained moment and its current grant…");
    try {
      const response = await vaultCall("p10VaultResume", { entryId: entry.id, revision: entry.revision });
      assertCurrent(scope, sourceEpoch, epoch);
      if (response?.entry?.id !== entry.id || response.entry.revision !== entry.revision || referenceKey(response.moment?.ref) !== referenceKey(entry.ref) || typeof response.moment?.text !== "string") throw new Error("invalid_resume");
      const host = $("#p10MemoryAnswer");
      host.replaceChildren(element("h3", "Retained moment"), element("p", exactReferenceLabel(response.moment.ref), { class: "muted" }), element("p", response.moment.text, { class: "preserve-lines" }));
      writeStatus("#p10MemoryStatus", "Retained moment opened after checking its current grant. This does not advance your session review point.");
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, sourceEpoch, epoch)) {
        clearResult("#p10MemoryAnswer"); writeStatus("#p10MemoryStatus", "This retained moment or grant is unavailable or changed. Reload the private vault before trying again.", true);
      }
    } finally { vaultLocks.delete("resume"); }
  }

  async function loadVaultEntries() {
    if (!vaultToken || role !== "viewer") return;
    clearVaultProtected("Checking private vault and current source rights…");
    const scope = identityScope();
    const epoch = vaultGeneration;
    const sourceEpoch = sourceGeneration;
    try {
      const response = await vaultCall("p10VaultEntries");
      assertCurrent(scope, sourceEpoch, epoch);
      vaultEntries = list(response?.entries);
      vaultReady = true;
      renderVaultEntries();
      if ($("#p10SaveMemory")) $("#p10SaveMemory").disabled = !sourceReady;
      writeStatus("#p10MemoryStatus", `${vaultEntries.length} private entry record(s) loaded. Unavailable source-backed entries cannot be queried.`);
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, sourceEpoch, epoch)) {
        vaultReady = false;
        vaultEntries = [];
        renderVaultEntries();
        clearResult("#p10MemoryAnswer");
        writeStatus("#p10MemoryStatus", "Vault read failed. Protected entries, prior query results, and actions are cleared.", true);
      }
    }
  }

  async function patchVaultEntry(entry, changes) {
    if (vaultLocks.has(`entry:${entry.id}`)) return;
    invalidateVaultQuery("Memory entry update pending. Existing query results and citations were cleared.");
    const scope = identityScope();
    const epoch = vaultGeneration;
    const sourceEpoch = sourceGeneration;
    clearResult("#p10MemoryAnswer");
    vaultLocks.add(`entry:${entry.id}`);
    const existing = vaultEntries.find(item => item.id === entry.id);
    const payload = { revision: entry.revision, interpretation: changes.interpretation ?? entry.interpretation, active: changes.active ?? entry.active };
    if (Object.hasOwn(changes, "pastStatement")) payload.pastStatement = changes.pastStatement;
    if (Object.hasOwn(changes, "correction")) payload.correction = changes.correction;
    try {
      const response = await vaultCall("p10VaultEntry", payload, entry.id);
      assertCurrent(scope, sourceEpoch, epoch);
      vaultEntries = vaultEntries.map(item => item.id === entry.id ? response.entry : item);
      vaultReady = true;
      writeStatus("#p10MemoryStatus", "Private entry updated. Any earlier query result was cleared.");
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, sourceEpoch, epoch)) {
        vaultReady = false;
        writeStatus("#p10MemoryStatus", "Entry update outcome is unresolved. No repeat was sent; reload to reconcile.", true);
      }
    } finally {
      vaultLocks.delete(`entry:${entry.id}`);
      if (resultIsCurrent(scope, sourceEpoch, epoch) && existing) renderVaultEntries();
    }
  }

  async function forgetVaultEntry(entry, card) {
    if (vaultLocks.has(`entry:${entry.id}`) || !confirm("Forget this selected private memory? Eligible indexed and derived context will be invalidated.")) return;
    invalidateVaultQuery("Forget pending. This entry is excluded from queries while the result is reconciled.");
    const scope = identityScope();
    const epoch = vaultGeneration;
    const sourceEpoch = sourceGeneration;
    clearResult("#p10MemoryAnswer");
    card.replaceChildren(element("p", "Forget is pending. This item is excluded from queries while the outcome is checked."));
    vaultEntries = vaultEntries.filter(item => item.id !== entry.id);
    vaultLocks.add(`entry:${entry.id}`);
    renderVaultEntries();
    try {
      await vaultCall("p10VaultEntryDelete", null, entry.id);
      assertCurrent(scope, sourceEpoch, epoch);
      writeStatus("#p10MemoryStatus", "Selected memory forgotten. Its query results were cleared.");
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, sourceEpoch, epoch)) {
        vaultReady = false;
        writeStatus("#p10MemoryStatus", "Forget outcome is unresolved. The item remains excluded until a deliberate vault reload reconciles it.", true);
      }
    } finally {
      vaultLocks.delete(`entry:${entry.id}`);
      if (resultIsCurrent(scope, sourceEpoch, epoch)) renderVaultEntries();
    }
  }

  async function saveVaultEntry() {
    if (!vaultReady || !sourceReady || memorySaveUnknown || sourceLocks.has("vault-entry-create")) return;
    const scope = identityScope();
    const epoch = sourceGeneration;
    const vaultEpoch = vaultGeneration;
    const interpretation = $("#p10MemoryText")?.value.trim();
    const pastStatement = $("#p10MemoryPast")?.value.trim() || null;
    const correction = $("#p10MemoryCorrection")?.value.trim() || null;
    const sourceBacked = $("#p10MemorySource")?.checked === true;
    const moment = selectedMomentForMemory();
    const grantId = $("#p10MemoryGrant")?.value;
    if (!interpretation) return;
    if (sourceBacked && (!moment || !grantId || !grants.some(grant => grant.id === grantId && referenceKey(grant.ref) === referenceKey(moment.ref)))) {
      writeStatus("#p10MemoryStatus", "A source-backed memory requires the currently selected exact moment and an active grant discovered for that exact reference.", true);
      return;
    }
    const payload = { sessionId: scope.sessionId, ref: sourceBacked ? moment.ref : null, interpretation, pastStatement, correction, retainSourceGrantId: sourceBacked ? grantId : null };
    sourceLocks.add("vault-entry-create");
    updateControls();
    try {
      const response = await vaultCall("p10VaultEntryCreate", payload);
      assertCurrent(scope, epoch, vaultEpoch);
      vaultEntries.unshift(response.entry);
      $("#p10MemoryText").value = "";
      $("#p10MemoryPast").value = ""; $("#p10MemoryCorrection").value = "";
      renderVaultEntries();
      writeStatus("#p10MemoryStatus", "Selected private memory saved. The creator cannot access this vault.");
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch, vaultEpoch)) {
        memorySaveUnknown = true;
        writeStatus("#p10MemoryStatus", "Memory save outcome is unresolved. No duplicate was sent. Read vault operation status before any deliberate retry.", true);
        // Entry creation has no receipt ID; reconcile through a deliberate vault read.
      }
    } finally {
      sourceLocks.delete("vault-entry-create");
      if (resultIsCurrent(scope, epoch, vaultEpoch)) updateControls();
    }
  }

  async function queryVault() {
    if (!vaultReady || sourceCheckPending || vaultLocks.has("vault-query")) return;
    const queryToken = vaultToken;
    if (unresolved.has("vault-query")) {
      const held = unresolved.get("vault-query");
      const scope = identityScope();
      const sourceEpoch = sourceGeneration;
      const vaultEpoch = vaultGeneration;
      vaultLocks.add("vault-query");
      renderVaultEntries();
      try {
        const status = await readOperation(held.requestId, "vault-query", true);
        assertCurrent(scope, sourceEpoch, vaultEpoch);
        if (status?.state !== "complete") return;
        const replay = await vaultCall("p10VaultQuery", held.payload);
        assertCurrent(scope, sourceEpoch, vaultEpoch);
        renderResult($("#p10MemoryAnswer"), replay, replay.answer);
        unresolved.delete("vault-query");
      } catch { /* Keep the exact request blocked. */ }
      finally { if (queryToken === vaultToken) vaultLocks.delete("vault-query"); if (resultIsCurrent(scope, sourceEpoch, vaultEpoch)) renderVaultEntries(); }
      return;
    }
    const query = $("#p10MemoryQuery")?.value.trim();
    const entryIds = vaultEntries.filter(entry => entry.active === true && entry.status === "available").map(entry => entry.id).slice(0, 20);
    if (!query || !entryIds.length || !vaultReady || vaultLocks.has("vault-query")) return;
    const scope = identityScope();
    const sourceEpoch = sourceGeneration;
    const vaultEpoch = vaultGeneration;
    const payload = { entryIds, query, clientRequestId: requestId() };
    vaultLocks.add("vault-query");
    const host = $("#p10MemoryAnswer");
    host.replaceChildren(element("p", "Searching only selected active private memories…", { class: "muted" }));
    try {
      const response = await vaultCall("p10VaultQuery", payload);
      assertCurrent(scope, sourceEpoch, vaultEpoch);
      unresolved.delete("vault-query");
      renderResult(host, response, response.answer);
    } catch (error) {
      try { assertIdentity(scope); } catch { return; }
      if (queryToken !== vaultToken) return;
      if (error.name === "AbortError" || !error.status || error.status >= 500 || error.status === 409) {
        unresolved.set("vault-query", { requestId: payload.clientRequestId, payload });
      }
      if (resultIsCurrent(scope, sourceEpoch, vaultEpoch)) host.replaceChildren(element("p", "Private query failed or is unresolved. Use the same action deliberately to check its status; no new request ID is sent while unresolved.", { role: "alert" }));
    } finally {
      if (queryToken === vaultToken) vaultLocks.delete("vault-query");
      if (resultIsCurrent(scope, sourceEpoch, vaultEpoch)) renderVaultEntries();
    }
  }

  async function useVaultToken() {
    const nextToken = $("#p10VaultToken")?.value.trim() || "";
    if (nextToken !== vaultToken) {
      unresolved.delete("vault-query");
      vaultLocks.delete("vault-query");
    }
    vaultToken = nextToken;
    clearVaultProtected(vaultToken ? "Vault token changed. Checking this separate private capability…" : "Vault token cleared. Private query results were erased.");
    if (vaultToken && role === "viewer") await loadVaultEntries();
  }

  async function createVault() {
    if (vaultCreateUnknown || sourceLocks.has("vault-create")) return;
    const scope = identityScope();
    const epoch = sourceGeneration;
    sourceLocks.add("vault-create");
    try {
      const local = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname);
      const body = local ? {} : { sessionId: scope.sessionId };
      const headers = local ? {} : { "X-Viewer-Capability": scope.token };
      const response = await api.call("p10VaultCreate", body, { scope, headers, captureHeaders: true });
      assertCurrent(scope, epoch);
      const capability = response?.headers?.get?.("x-vault-capability") || "";
      vaultToken = capability;
      if (!vaultToken || !response?.vault?.id) throw new Error("vault_capability_header_missing");
      const tokenInput = $("#p10VaultToken");
      if (tokenInput) tokenInput.value = vaultToken;
      clearVaultProtected("New vault created. Copy the one-time token to your password manager if you choose; it is held in memory only.");
      await useVaultToken();
    } catch (error) {
      if (error.name !== "AbortError" && resultIsCurrent(scope, epoch)) {
        vaultCreateUnknown = true;
        writeStatus("#p10MemoryStatus", "Vault creation response could not be confirmed. The one-time capability was not recovered and no duplicate vault was created.", true);
      }
    } finally {
      sourceLocks.delete("vault-create");
    }
  }

  function bind() {
    const retrieve = $("#p10Retrieve"), answer = $("#p10TimelineAnswer");
    if (retrieve) retrieve.textContent = "Find supporting moments with AI";
    if (retrieve && answer && !$("#p10SearchReceived")) {
      const search = element("button", "Search received text", { type: "button", id: "p10SearchReceived", class: "button secondary" });
      search.addEventListener("click", searchReceivedMoments);
      retrieve.before(search);
      answer.before(element("div", "", { id: "p10SearchResults", class: "p10-list", "aria-live": "polite" }));
      $("#p10Topic")?.addEventListener("input", updateControls);
    }
    const studioStatus = $("#p10StudioStatus");
    if (studioStatus && !$("#p10StudioRefresh")) {
      const refresh = element("button", "Refresh source moments", { type: "button", id: "p10StudioRefresh", class: "button secondary" });
      refresh.addEventListener("click", refreshSources);
      studioStatus.before(refresh);
    }
    const formatSelect = $("#p10Format");
    if (formatSelect) {
      for (const [value, label] of [["highlight", "Highlight"], ["chapter", "Chapter"], ["export", "Export"]]) {
        if (![...formatSelect.options].some(option => option.value === value)) {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = label;
          formatSelect.append(option);
        }
      }
    }
    $("#p10Refresh")?.addEventListener("click", refreshSources);
    $("#p10Index")?.addEventListener("click", indexSourceMoment);
    $("#p10Derive")?.addEventListener("click", createMaterial);
    $("#p10Instruction")?.addEventListener("input", updateControls);
    $("#p10DraftStatus")?.addEventListener("click", async () => {
      const held = unresolved.get("p10StudioCreate");
      if (!held || sourceCheckPending) return;
      const scope = identityScope();
      const epoch = sourceGeneration;
      const status = await readOperation(held.requestId, "p10StudioCreate");
      if (!resultIsCurrent(scope, epoch)) return;
      if (status?.state === "complete") {
        unresolved.delete("p10StudioCreate");
        materialCreateUnknown = false;
        writeStatus("#p10StudioStatus", "The draft request completed. Review the current material collection before creating another.");
      }
      updateControls();
    });
    $("#p10Retrieve")?.addEventListener("click", retrieveTopic);
    if ($("#p10Compare") && !$("#p10PreviewFrames")) {
      const preview = element("button", "Open selected frame evidence", { type: "button", id: "p10PreviewFrames", class: "button secondary" });
      preview.addEventListener("click", () => {
        const refs = [selectedMoment("#p10Before")?.ref, selectedMoment("#p10After")?.ref]
          .filter((ref, index, all) => ref && all.findIndex(item => referenceKey(item) === referenceKey(ref)) === index);
        if (!refs.length) {
          $("#p10Comparison").textContent = "Choose an exact frame to open its available evidence. No comparison is generated.";
          return;
        }
        const contextRefs = exactSelectedRefs().filter(ref => !refs.some(frameRef => referenceKey(frameRef) === referenceKey(ref))).slice(0, 8);
        showFrameEvidence($("#p10Comparison"), refs, contextRefs);
      });
      $("#p10Compare").before(preview);
    }
    $("#p10Compare")?.addEventListener("click", compareFrames);
    for (const selector of ["#p10Before", "#p10After"]) $(selector)?.addEventListener("change", () => {
      comparisonView += 1; stopComparisonSpeech(); clearResult("#p10Comparison"); updateControls();
    });
    $("#p10Moment")?.addEventListener("change", invalidateRepresentation);
    $("#p10Language")?.addEventListener("input", invalidateRepresentation);
    $("#p10Moment")?.addEventListener("change", () => { updateControls(); discoverRetentionGrants(); });
    $("#p10Before")?.addEventListener("change", updateControls);
    $("#p10After")?.addEventListener("change", updateControls);
    $("#p10StudioSource")?.addEventListener("change", () => { untimedSourceChoice.checked = false; updateControls(); });
    untimedSourceChoice.addEventListener("change", updateControls);
    $("#p10Grant")?.addEventListener("click", createGrant);
    $("#p10Concise")?.addEventListener("click", () => represent("concise"));
    $("#p10Detailed")?.addEventListener("click", () => represent("detailed"));
    $("#p10Translate")?.addEventListener("click", () => represent("translation"));
    $("#p10VisualDescription")?.addEventListener("click", () => represent("visual_description"));
    $("#p10CreateVault")?.addEventListener("click", createVault);
    $("#p10UseVault")?.addEventListener("click", useVaultToken);
    $("#p10LoadMemory")?.addEventListener("click", loadVaultEntries);
    $("#p10SaveMemory")?.addEventListener("click", saveVaultEntry);
    $("#p10QueryMemory")?.addEventListener("click", queryVault);
    $("#p10MemorySource")?.addEventListener("change", () => {
      const sourceBacked = $("#p10MemorySource").checked;
      const grant = $("#p10MemoryGrantLabel");
      if (grant) grant.hidden = !sourceBacked;
      if (sourceBacked) discoverRetentionGrants();
      updateControls();
    });
    document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => requestAnimationFrame(() => {
      const active = document.querySelector(".view.active")?.id?.replace("view-", "");
      if ((active === "audience" && role === "viewer") || (active === "studio" && role === "creator")) refreshSources();
    })));
  }

  bind();
  return {
    setRole(next) {
      const roleChanged = role !== next;
      if (roleChanged) {
        vaultToken = "";
        vaultEntries = [];
        vaultReady = false;
        if ($("#p10VaultToken")) $("#p10VaultToken").value = "";
        clearVaultProtected("Role changed. Private vault capability and results were cleared.");
      }
      role = next;
      const viewerPanel = $("#p10Viewer");
      const creatorPanel = $("#p10Studio");
      if (viewerPanel) viewerPanel.hidden = next !== "viewer";
      if (creatorPanel) creatorPanel.hidden = next !== "creator";
      if (next) refreshSources();
    },
    refreshStudioCollection() {
      if (role !== "creator" || !sourceReady || sourceCheckPending) return;
      const scope = identityScope(), epoch = sourceGeneration;
      refreshMaterials(scope, epoch).catch(() => {});
    },
    async openExactStudioMaterial({ materialId, version, revision }) {
      if (role !== "creator" || !sourceReady || sourceCheckPending || !$("#p10Materials")
          || typeof materialId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(materialId)
          || !Number.isSafeInteger(version) || version < 1
          || !Number.isSafeInteger(revision) || revision < 1 || edits.has(materialId)
          || unresolved.has(`material:${materialId}`)) return null;
      const scope = identityScope(), epoch = sourceGeneration;
      const response = await api.call("p10StudioMaterial", null, materialId, { scope });
      assertCurrent(scope, epoch);
      if (role !== "creator" || !sourceReady || sourceCheckPending || !$("#p10Materials") || edits.has(materialId)
          || unresolved.has(`material:${materialId}`)) return null;
      const material = response?.material;
      if (material?.id !== materialId || material.currentVersion !== version
          || material.revision !== revision || material.status !== "draft"
          || material.dependencyState !== "current" || typeof material.title !== "string"
          || typeof material.body !== "string") return null;
      const index = materials.findIndex(item => item.id === materialId);
      const exact = { ...material, stale: false };
      if (index < 0) materials.push(exact); else materials[index] = exact;
      lockedMaterials.delete(materialId);
      publicationUrls.delete(`${materialId}:${version}`);
      renderMaterials(materialId);
      return { materialId, version, revision };
    },
    notifyNewSources() {
      writeStatus("#p10ViewerStatus", "New sources are available. Refresh moments when you want to include them; your current exact selection remains unchanged.");
    },
    beginSourceCheck() {
      stopComparisonSpeech();
      sourceCheckPending = true;
      for (const panel of [$("#p10Viewer"), $("#p10Studio")]) if (panel) {
        panel.style.visibility = "hidden";
        panel.inert = true;
      }
    },
    endSourceCheck() {
      sourceCheckPending = false;
      for (const panel of [$("#p10Viewer"), $("#p10Studio")]) if (panel) {
        panel.style.visibility = "";
        panel.inert = false;
      }
      updateControls();
    },
    invalidate() { clearSourceProtected(); },
    reset() {
      sourceCheckPending = false;
      for (const panel of [$("#p10Viewer"), $("#p10Studio")]) if (panel) {
        panel.style.visibility = "";
        panel.inert = false;
      }
      clearSourceProtected("Identity or session changed. Phase 10 source-derived content was cleared.");
      role = null;
      vaultGeneration += 1;
      vaultToken = "";
      vaultEntries = [];
      grants = [];
      materials = [];
      selectedRefs.clear();
      if ($("#p10MemorySource")) $("#p10MemorySource").checked = false;
      if ($("#p10MemoryGrant")) $("#p10MemoryGrant").value = "";
      lockedMaterials.clear();
      reviewedVersions.clear();
      vaultLocks.clear();
      sourceLocks.clear();
      unresolved.clear();
      edits.clear();
      publicationUrls.clear();
      vaultReady = false;
      vaultCreateUnknown = false;
      materialCreateUnknown = false;
      memorySaveUnknown = false;
      grantCreateUnknown = false;
      for (const selector of ["#p10VaultToken", "#p10MemoryText", "#p10MemoryPast", "#p10MemoryCorrection", "#p10MemoryQuery", "#p10Topic", "#p10Instruction", "#p10MaterialPreview"]) {
        const field = $(selector);
        if (field && "value" in field) field.value = "";
        else field?.replaceChildren();
      }
      clearVaultProtected("Private vault capability and results cleared after identity change.");
    },
    refresh: refreshSources,
    refreshIfVisible() { const view = document.querySelector(".view.active")?.id; if ((view === "view-audience" && role === "viewer") || (view === "view-studio" && role === "creator")) refreshSources(); },
    setVisible(view) { if ((view === "audience" && role === "viewer") || (view === "studio" && role === "creator")) refreshSources(); },
  };
}
