const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const requestCache = new Map();
const ownerPrefix = "entrelineas.phase6.project-owner.v1:";
let controllerConfig = null;
let role = null;
let currentReading = null;
let currentCoactivity = null;
let currentInquiry = null;
let currentProject = null;
let currentProjectScopes = null;
let projectLoadPending = false;
let selectedProjectId = null;
let currentPresentation = null;
let currentGrouping = null;
let currentGroupingScopeKey = null;
let currentInquiryPresentation = null;
let currentSharePreview = null;
let currentObservationToSupersede = null;
let submittedReadingMap = new Map();
let activeOwnShare = null;
let currentProposalList = [];
let inquiryObservationMap = new Map();
const operationDraftCache = new Map();

const phase6Views = new Set(["perspectives", "work", "inquiry", "project"]);

function node(tag, text = "", attrs = {}) {
  const out = document.createElement(tag);
  if (text !== "") out.textContent = text;
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") out.className = value;
    else if (key === "dataset") Object.assign(out.dataset, value);
    else out.setAttribute(key, value);
  }
  return out;
}
function setStatus(view, text, alert = false) {
  const out = $(`[data-p6-status]`, $(`#view-${view}`));
  if (!out) return;
  out.textContent = text;
  out.setAttribute("role", alert ? "alert" : "status");
}
function setList(id, items, render, empty) {
  const host = $(`#${id}`);
  if (!host) return;
  host.replaceChildren();
  if (!items?.length) host.append(node("div", empty, { class: "p6-empty" }));
  else for (const item of items) host.append(render(item));
}
function escapeReason(error, view = "") {
  if (error?.code === "request_in_progress") return "This action may still be resolving. Its saved result is unknown; refresh before deciding whether to make a new attempt.";
  if (error?.code === "request_id_conflict") return "This action ID was already used for a different request. Refresh the current record before continuing.";
  if (error?.code === "stale_revision") return "This item changed. Your entries are preserved; refresh and review the current version before deliberately retrying.";
  if (error?.code === "invalid_transition") return "This action is not available from the current state. Refresh and review the available actions.";
  if (error?.status === 409) return "This item changed or its source is no longer eligible. Refresh the list and review it before trying again.";
  if (error?.status === 403 || error?.status === 404) return "This item is unavailable to this identity.";
  if (error?.status === 422 || error?.status === 413) return "The entry needs changes before it can be saved.";
  if (error?.code === "busy" && view === "work") return "The step could not be generated. Your entered details remain available for manual editing.";
  if (error?.code === "provider_unavailable" || error?.code === "provider_invalid_output" || error?.code === "stale_context") return "The step could not be generated. Your entered details remain available for manual editing.";
  if (error?.code === "busy") return "The service is busy. Your entries remain available; review the current version before trying again.";
  return "This action could not be completed. Your entries remain on screen; no success is assumed.";
}
function scopeNow() { return controllerConfig.identityScope(); }
function assert(scope) { controllerConfig.assertIdentity(scope); }
function assertJournal(scope) {
  if (typeof controllerConfig?.assertSavedIdentity !== "function") throw new DOMException("Saved access unavailable", "AbortError");
  controllerConfig.assertSavedIdentity(scope);
}
function clearRequestJournal(scope, key, rid, fingerprint) {
  assertJournal(scope);
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || "null");
    assertJournal(scope);
    if (saved?.requestId === rid && saved?.fingerprint === fingerprint) sessionStorage.removeItem(key);
    assertJournal(scope);
    const cached = requestCache.get(key);
    if (cached?.requestId === rid && cached?.fingerprint === fingerprint) requestCache.delete(key);
  } catch (error) {
    assertJournal(scope);
    const saved = requestCache.get(key);
    if (saved?.requestId === rid && saved?.fingerprint === fingerprint) requestCache.delete(key);
  }
}
function requestId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return [...bytes].map((v) => v.toString(16).padStart(2, "0")).join("");
}
async function digest(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((v) => v.toString(16).padStart(2, "0")).join("");
}
function actorKey(scope, route) {
  return `entrelineas.p6.request.v1:${scope.sessionId}:${scope.role}:${scope.viewerId || "creator"}:${route}`;
}
async function withRequestId(route, data, scope) {
  assertJournal(scope);
  const fingerprint = await digest({ target: route, payload: data });
  assertJournal(scope);
  const key = actorKey(scope, route);
  let saved = null;
  try { assertJournal(scope); saved = JSON.parse(sessionStorage.getItem(key) || "null"); } catch { assertJournal(scope); }
  if (!saved) saved = requestCache.get(key) || null;
  if (saved?.fingerprint === fingerprint && saved.requestId) return { requestId: saved.requestId, key, fingerprint };
  const value = { requestId: requestId(), key, fingerprint };
  try { assertJournal(scope); sessionStorage.setItem(key, JSON.stringify(value)); } catch { assertJournal(scope); requestCache.set(key, value); }
  return value;
}
const mutationInFlight = new Set();
const viewGeneration = new Map();
const objectGeneration = new Map();
function beginLoad(view) { const next = (viewGeneration.get(view) || 0) + 1; viewGeneration.set(view, next); return next; }
function beginObject(name) { const next = (objectGeneration.get(name) || 0) + 1; objectGeneration.set(name, next); return next; }
function assertObject(name, generation, scope) { assert(scope); if (objectGeneration.get(name) !== generation) throw new DOMException("Selection changed", "AbortError"); }
function assertLoad(view, generation, scope) {
  assert(scope);
  if (viewGeneration.get(view) !== generation || !$(`#view-${view}`)?.classList.contains("active")) throw new DOMException("View changed", "AbortError");
}
async function mutate(routeKey, body, args = [], scope = scopeNow(), headers = {}) {
  const target = `${routeKey}:${JSON.stringify(args)}`;
  const startedView = $$('.p6-view.active')[0]?.id || null;
  const startedViewName = startedView?.replace("view-", "") || null;
  const startedGeneration = startedViewName ? (viewGeneration.get(startedViewName) || 0) : 0;
  const { requestId: rid, key, fingerprint } = await withRequestId(target, body, scope);
  assertJournal(scope);
  const flight = `${key}:${rid}`;
  if (mutationInFlight.has(flight)) throw Object.assign(new Error("busy"), { code: "busy" });
  mutationInFlight.add(flight);
  try {
    assertJournal(scope);
    const result = await controllerConfig.api.call(routeKey, { ...body, requestId: rid }, ...args, { scope, headers });
    assertJournal(scope);
    clearRequestJournal(scope, key, rid, fingerprint);
    const currentView = $$('.p6-view.active')[0]?.id || null;
    if (startedView && (currentView !== startedView || (viewGeneration.get(startedViewName) || 0) !== startedGeneration)) throw new DOMException("View changed", "AbortError");
    return result;
  } catch (error) {
    if (!["request_in_progress"].includes(error?.code) && !(error?.name === "TypeError" || error?.status == null)) {
      try { clearRequestJournal(scope, key, rid, fingerprint); } catch { /* preserve the original unknown request after identity changes */ }
    }
    throw error;
  } finally { mutationInFlight.delete(flight); }
}
async function pages(routeKey, scope, args = [], headers = {}) {
  const items = [];
  let cursor = null;
  const cursors = new Set();
  for (let page = 0; page < 100; page++) {
    const query = new URLSearchParams({ limit: "100" });
    if (cursor) query.set("cursor", cursor);
    const result = await controllerConfig.api.call(routeKey, null, ...args, `?${query}`, { scope, headers });
    assert(scope);
    items.push(...(Array.isArray(result.items) ? result.items : []));
    cursor = result.nextCursor;
    if (!cursor) return items;
    if (cursors.has(cursor)) throw new Error("page_cursor_repeated");
    cursors.add(cursor);
  }
  throw new Error("page_limit");
}
function p6Button(label, action, style = "secondary") {
  const b = node("button", label, { type: "button", class: `button ${style}`, dataset: { p6Action: action } });
  return b;
}
function requestFailed(view, error) { if (error?.name === "AbortError") return; setStatus(view, escapeReason(error, view), true); }
function clearViewBodies(view) {
  const ids = view === "perspectives" ? ["p6MyReadings", "p6ReadingReviewList", "p6PresentationSelection", "p6ReadingExactPreview", "p6PublicReadings", "p6PublicInquiries", "p6Grants", "p6CreatorGrants", "p6SavedGroups"]
    : view === "work" ? ["p6Coactivities", "p6CreatorShares", "p6WorkSharePreview", "p6OwnShares"]
      : view === "inquiry" ? ["p6InquiryList", "p6ObservationList", "p6InquiryPresentationSelection", "p6InquiryPresentations", "p6InquiryExactPreview", "p6Grants", "p6CreatorGrants", "p6NextExaminationContent"]
        : ["p6ProjectState", "p6NextActionView", "p6ProjectHistory", "p6ProjectImports", "p6ProposalList", "p6ProjectLinkRequests", "p6OwnerLinks", "p6BeforePreview", "p6AfterPreview"];
  for (const id of ids) { const host = $(`#${id}`); if (host) host.replaceChildren(node("div", "Current information is unavailable.", { class: "p6-empty" })); }
  if (view === "perspectives") { currentPresentation = null; submittedReadingMap = new Map(); currentGrouping = null; currentGroupingScopeKey = null; clearGroupingDraft(); }
  if (view === "work") { currentCoactivity = null; currentSharePreview = null; updateWorkControls(null); updateWorkShareControls(); }
  if (view === "inquiry") { currentInquiry = null; currentInquiryPresentation = null; currentObservationToSupersede = null; inquiryObservationMap.clear(); }
  if (view === "project") { currentProject = null; currentProjectScopes = null; currentProposalList = []; resolvedProjectRefs.clear(); const title = $("#p6ProjectTitleDisplay"); if (title) title.textContent = "Project identity and binding status are unavailable."; }
}

function sourceOptions(select, sourceRef = null) {
  if (!select) return;
  const context = controllerConfig.state.context || {};
  const list = controllerConfig.normalizeList(context.sources || context);
  const eligible = list.filter((x) => x?.id && x.status === "active" && x.audienceVisible === true && Number.isInteger(Number(x.revision)) && Number(x.revision) > 0);
  select.replaceChildren(node("option", eligible.length ? "Choose an exact source revision" : "No eligible source is available", { value: "" }));
  for (const source of eligible) {
    const option = node("option", `${source.title || source.kind || "Source"} · revision ${source.revision}`, { value: JSON.stringify({ sourceId: source.id, revision: Number(source.revision) }) });
    select.append(option);
  }
  select.disabled = eligible.length === 0;
  if (sourceRef) select.value = JSON.stringify(sourceRef);
}
function selectedSource(select) {
  try { const value = JSON.parse(select?.value || "null"); return value?.sourceId && Number.isInteger(value.revision) && value.revision > 0 ? value : null; } catch { return null; }
}
function setButtons(selector, enabled) { $$(selector).forEach((b) => { b.disabled = !enabled; }); }
function statusForObject(view, status, prefix) {
  const text = status === "withdrawn" || status === "revoked" ? `${prefix}: ${status}.` : `${prefix}: ${status}.`;
  setStatus(view, text);
}
function clearReadingForm() {
  currentReading = null;
  for (const id of ["p6ReadingText", "p6ReadingReason", "p6Pseudonym"]) { const el = $(`#${id}`); if (el) el.value = ""; }
  const source = $("#p6ReadingSource"); if (source) source.value = "";
  for (const el of $$('#view-perspectives [data-p6-role="viewer"] input[type="checkbox"]')) el.checked = false;
  const attribution = $("#p6Attribution"); if (attribution) attribution.value = "name";
}
function renderMyReadings(items) {
  setList("p6MyReadings", items, (reading) => {
    const card = node("article", "", { class: "p6-record" });
    if (reading.available === false || reading.text == null) {
      card.append(node("strong", "Reading unavailable"), node("p", "Its source or consent is no longer eligible. The original text is hidden.", { class: "muted" }));
    } else {
      card.append(node("strong", `Reading · ${reading.status} · revision ${reading.revision}`));
      card.append(node("p", reading.text));
      if (reading.reason) card.append(node("p", `Reason: ${reading.reason}`));
      if (reading.consent) card.append(node("p", `Review ${reading.consent.review ? "allowed" : "not allowed"} · public quotation ${reading.consent.publicQuotation ? "allowed" : "not allowed"} · cross-session ${reading.consent.crossSession ? "allowed" : "not allowed"}`, { class: "muted" }));
    }
    if (reading.status === "draft" && reading.available !== false) {
      const edit = p6Button("Edit private draft", "reading-edit"); edit.dataset.id = reading.id; card.append(edit);
      const withdraw = p6Button("Withdraw draft", "reading-withdraw", "danger"); withdraw.dataset.id = reading.id; card.append(withdraw);
    }
    if (reading.status === "submitted") { const withdraw = p6Button("Withdraw submitted reading", "reading-withdraw", "danger"); withdraw.dataset.id = reading.id; card.append(withdraw); }
    if (reading.status === "submitted" && reading.consent?.crossSession && reading.consent?.publicQuotation) { const grant = p6Button("Grant this exact reading to the named destination project", "reading-grant"); grant.dataset.id = reading.id; grant.dataset.revision = String(reading.revision); card.append(grant); }
    return card;
  }, "No reading drafts or submissions are available.");
}
function renderReadingReview(items) {
  const eligible = items.filter((x) => x.status === "submitted" && x.available !== false && x.text != null);
  submittedReadingMap = new Map(eligible.map((reading) => [reading.id, reading]));
  setList("p6ReadingReviewList", items, (reading) => {
    const card = node("article", "", { class: "p6-record" });
    if (reading.available === false || reading.text == null) card.append(node("strong", "Reading unavailable"), node("p", "Source or consent eligibility changed. Revoked text and derived rationale are hidden.", { class: "muted" }));
    else {
      const select = node("input", "", { type: "checkbox", value: reading.id, dataset: { readingId: reading.id, revision: String(reading.revision) } });
      const label = node("label", "Select for this rationale group", { class: "check-line" }); label.prepend(select); card.append(label);
      card.append(node("strong", `Submitted reading · revision ${reading.revision}`), node("p", reading.text), node("p", `Reason: ${reading.reason || "No reason supplied."}`));
      card.append(node("p", `Allowed attribution: ${reading.consent?.attribution?.mode || "unknown"}${reading.consent?.attribution?.label ? ` · ${reading.consent.attribution.label}` : ""} · public quote ${reading.consent?.publicQuotation ? "allowed" : "not allowed"}`, { class: "muted" }));
    }
    return card;
  }, "No eligible submitted readings are available.");
  const groupSelect = $("#p6GroupSelection");
  if (groupSelect) {
    groupSelect.replaceChildren();
    for (const item of eligible) groupSelect.append(node("option", `Revision ${item.revision}: ${item.text.slice(0, 90)}`, { value: JSON.stringify({ id: item.id, revision: item.revision }) }));
  }
  const choices = $("#p6PresentationSelection");
  if (choices) {
    choices.replaceChildren();
    for (const item of eligible.filter((x) => x.consent?.publicQuotation === true)) {
      const wrapper = node("div", "", { class: "p6-record" });
      const check = node("input", "", { type: "checkbox", dataset: { presentationReading: item.id, revision: String(item.revision) } });
      const label = node("label", `Include reading: ${item.text.slice(0, 90)}`, { class: "check-line" }); label.prepend(check); wrapper.append(label);
      const attr = item.consent.attribution;
      const fixed = node("p", `Contributor-selected attribution: ${attr.mode}${attr.label ? ` · ${attr.label}` : ""}. Omit the whole reading to leave it out.`, { class: "muted", dataset: { p6ReadingSource: item.id } });
      fixed.dataset.attribution = JSON.stringify(attr); wrapper.append(fixed); choices.append(wrapper);
    }
  }
}
function groupingScopeKey(scope) {
  return `${scope.sessionId}:${scope.role}:${scope.viewerId || "creator"}`;
}
function groupingStorageKey(scope) {
  return `entrelineas.p6.last-grouping.v1:${groupingScopeKey(scope)}`;
}
function savedGroupingId(scope) {
  try { return sessionStorage.getItem(groupingStorageKey(scope)) || null; } catch { return null; }
}
function rememberGroupingId(scope, id) {
  if (typeof id !== "string" || !id) throw new Error("grouping_reference_missing");
  sessionStorage.setItem(groupingStorageKey(scope), id);
}
function savedGroupingHost() {
  let host = $("#p6SavedGroups");
  if (!host) {
    host = node("div", "", { id: "p6SavedGroups", class: "p6-list" });
    $("#p6SaveGroup")?.after(host);
  }
  return host;
}
function clearGroupingDraft() {
  for (const id of ["p6GroupLabel", "p6GroupRationale", "p6Disagreement"]) {
    const field = $(`#${id}`); if (field) field.value = "";
  }
}
function clearGroupingProjection(message, clearDraft = false) {
  currentGrouping = null;
  currentGroupingScopeKey = null;
  savedGroupingHost()?.replaceChildren(node("div", message, { class: "p6-empty", role: "status" }));
  if (clearDraft) clearGroupingDraft();
}
function renderSavedGrouping(grouping, scope) {
  const host = savedGroupingHost();
  host.replaceChildren();
  const eligible = [...submittedReadingMap.values()];
  if (grouping?.reasoningStatus !== "current") {
    clearGroupingDraft();
    host.append(node("div", "Saved rationale is pending eligibility review. Individual eligible readings and reasons remain available above; unresolved review is not shown as current.", { class: "p6-empty", role: "status" }));
    const refs = [...new Set((grouping?.groups || []).flatMap((group) => group?.readings || []).map((ref) => ref?.id).filter((id) => typeof id === "string"))];
    if (refs.length) {
      const list = node("ul", "", { class: "p6-reference-list" });
      for (const id of refs) {
        const item = eligible.find((reading) => reading.id === id);
        if (item) list.append(node("li", `Eligible reading reference · revision ${item.revision}`));
      }
      if (list.childElementCount) host.append(list);
    }
    return;
  }
  currentGrouping = grouping;
  currentGroupingScopeKey = groupingScopeKey(scope);
  for (const group of grouping.groups || []) {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("strong", group.label), node("p", group.rationale), node("p", `Remaining disagreement: ${group.disagreement}`, { class: "muted" }), node("p", `${(group.readings || []).length} separate reading reference(s); each eligible reason stays available above.`, { class: "muted" }));
    host.append(card);
  }
  if (grouping.ungrouped?.length) host.append(node("p", `${grouping.ungrouped.length} eligible reading(s) remain ungrouped, including singleton perspectives.`, { class: "muted" }));
  if (!host.childElementCount) host.append(node("div", "No saved rationale group is available.", { class: "p6-empty" }));
}
async function refreshSavedGrouping(scope, generation) {
  clearGroupingProjection("Checking the saved rationale against current reading eligibility…");
  const id = savedGroupingId(scope);
  if (!id) {
    clearGroupingProjection("No saved rationale group is recorded for this creator and session. Review eligible submissions above.");
    return;
  }
  try {
    const result = await controllerConfig.api.call("p6ReadingGroup", null, id, { scope });
    assertLoad("perspectives", generation, scope);
    const grouping = result?.grouping;
    if (!grouping || grouping.id !== id) throw new Error("grouping_unavailable");
    renderSavedGrouping(grouping, scope);
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    assertLoad("perspectives", generation, scope);
    clearGroupingProjection("Saved rationale is unavailable for current review. Individual eligible submissions remain above.", true);
  }
}
function ensureReadingPreview() {
  let host = $("#p6ReadingExactPreview");
  if (!host) { host = node("div", "No exact public version has been previewed.", { id: "p6ReadingExactPreview", class: "p6-list p6-empty", "aria-live": "polite" }); $("#p6PresentationSelection")?.after(host); }
  return host;
}
function previewCurrentReadingVersion() {
  const host = ensureReadingPreview(); const presentation = currentPresentation;
  const version = presentation?.versions?.find((item) => item.number === presentation.currentVersion);
  if (!version || version.eligible !== true) { host.replaceChildren(node("p", "Exact current version is unavailable or ineligible. No older version will be substituted.", { class: "p6-empty" })); host.dataset.version = ""; return; }
  renderExactReadingVersionPreview(version.title, version.items, version.number);
  host.dataset.presentationId = presentation.id;
}
function renderPresentations(items) {
  const select = $("#p6PresentationSelect");
  if (!select) return;
  const selectedId = select.value || currentPresentation?.id;
  select.replaceChildren(node("option", "Choose a presentation", { value: "" }));
  for (const item of items) select.append(node("option", `${item.id} · ${item.status} · revision ${item.revision} · version ${item.currentVersion}`, { value: item.id }));
  currentPresentation = items.find((x) => x.id === selectedId) || items.at(-1) || null;
  select.value = currentPresentation?.id || "";
  ensureReadingPreview(); previewCurrentReadingVersion();
}
function publicReadings(data) {
  const host = $("#p6PublicReadings"); if (!host) return;
  const presentation = data?.presentation;
  host.replaceChildren();
  if (!presentation) { host.append(node("div", "No eligible presented perspective version is available.", { class: "p6-empty" })); return; }
  host.append(node("h3", presentation.title || "Presented perspectives"), node("p", `Exact version ${presentation.version}`, { class: "muted" }));
  for (const item of presentation.items || []) {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("p", item.text), node("p", `Reason: ${item.reason}`, { class: "muted" }));
    card.append(node("p", item.attribution?.mode === "unattributed" ? "Unattributed" : item.attribution?.label || "Attribution unavailable", { class: "muted" }));
    host.append(card);
  }
}

function renderCoactivities(items) {
  setList("p6Coactivities", items, (item) => {
    const card = node("article", "", { class: "p6-record" });
    const use = p6Button(`Open ${item.status} activity`, "work-select"); use.dataset.id = item.id;
    card.append(node("strong", `${item.activity} · ${item.status} · revision ${item.revision}`), node("p", `Your state: ${item.declaredState} · time available: ${item.minutes} minutes`, { class: "muted" }));
    if (!item.sourceRef) card.append(node("p", "No stream context was selected. Your own activity remains available.", { class: "muted" }));
    else if (item.contextAvailable === false) card.append(node("p", "Selected stream context is unavailable. Your own activity remains available.", { class: "muted" }));
    if (item.stepDraft) card.append(node("p", `Editable ${item.preparation === "ai" ? "AI-generated" : "manual"} proposal: ${item.stepDraft}`));
    if (item.acceptedStep) card.append(node("p", `Accepted step: ${item.acceptedStep}`));
    if (item.reentryDraft) card.append(node("p", `Re-entry step: ${item.reentryDraft}`));
    card.append(use); return card;
  }, "No private activity records are available.");
}
function updateWorkControls(item) {
  const status = item?.status;
  const active = Boolean(item);
  const toggle = (action, disabled) => { const button = $(`[data-p6-action='${action}']`); if (button) button.disabled = disabled; };
  toggle("work-create", role !== "viewer"); toggle("work-save", !active || status === "ended");
  toggle("work-prepare", !active || !["draft", "ready"].includes(status)); toggle("work-generate", !active || !["draft", "ready"].includes(status));
  toggle("work-generate-reentry", !active || status !== "reentry");
  toggle("work-accept", !active || !["draft", "ready"].includes(status)); toggle("work-start", !active || status !== "ready");
  toggle("work-pause", !active || status !== "active"); toggle("work-return", !active || status !== "paused");
  toggle("work-resume", !active || status !== "reentry"); toggle("work-end", !active || status === "ended");
}
function fillCoactivity(item) {
  if (currentCoactivity && (currentCoactivity.id !== item.id || currentCoactivity.revision !== item.revision)) {
    currentSharePreview = null;
    $("#p6WorkShareConsent").checked = false;
    $("#p6WorkSharePreview").replaceChildren(node("div", "Activity changed. Preview the selected result again before sharing.", { class: "p6-empty" }));
  }
  currentCoactivity = item;
  $("#p6Activity").value = item.activity || "";
  $("#p6DeclaredState").value = item.declaredState || "";
  $("#p6Minutes").value = String(item.minutes || "");
  $("#p6Step").value = item.status === "reentry" ? (item.reentryDraft || "") : (item.stepDraft || item.acceptedStep || "");
  for (const field of [$("#p6Activity"), $("#p6DeclaredState"), $("#p6Minutes"), $("#p6Step")]) delete field.dataset.dirty;
  updateWorkControls(item);
  updateWorkShareControls();
}
function updateWorkShareControls() {
  const preview = $("#p6WorkSharePreviewButton"), confirm = $("#p6WorkShareConfirm");
  if (preview) preview.disabled = !currentCoactivity || !$("#p6WorkResult")?.value.trim();
  if (confirm) confirm.disabled = !currentCoactivity || !currentSharePreview || !$("#p6WorkShareConsent")?.checked;
}
function renderCreatorShares(items) {
  setList("p6CreatorShares", items, (share) => {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("p", share.text), node("p", `Active selected derivative · revision ${share.revision}`, { class: "muted" }));
    return card;
  }, "No active viewer-shared results are available.");
}

function inquiryPayload() {
  return {
    question: $("#p6InquiryQuestion").value,
    alternatives: [
      { text: $("#p6AltA").value, prediction: $("#p6PredA").value },
      { text: $("#p6AltB").value, prediction: $("#p6PredB").value },
    ],
    discriminator: $("#p6Discriminator").value,
    procedure: $("#p6Procedure").value,
    sourceRefs: selectedSource($("#p6InquirySource")) ? [selectedSource($("#p6InquirySource"))] : [],
  };
}
function fillInquiry(item, preserveAuthoredFields = false) {
  currentInquiry = item;
  if (!preserveAuthoredFields) {
    $("#p6InquiryQuestion").value = item.question || "";
    $("#p6AltA").value = item.alternatives?.[0]?.text || "";
    $("#p6PredA").value = item.alternatives?.[0]?.prediction || "";
    $("#p6AltB").value = item.alternatives?.[1]?.text || "";
    $("#p6PredB").value = item.alternatives?.[1]?.prediction || "";
    $("#p6Discriminator").value = item.discriminator || "";
    $("#p6Procedure").value = item.procedure || "";
    sourceOptions($("#p6InquirySource"), item.sourceRefs?.[0] || null);
  }
  const noObs = item.observationCount === 0;
  $("[data-p6-observation-empty]").textContent = noObs ? "No observation has been recorded." : `${item.observationCount} human-entered observation(s) are recorded. Reports remain separate.`;
  const next = item.nextExamination || {};
  const nextHost = ensureNextExaminationUI();
  nextHost.replaceChildren();
  if (next.status === "awaiting_observation" || item.observationCount === 0) nextHost.append(node("p", "No observation has been recorded. A plan has no result yet.", { class: "p6-empty" }));
  else if (next.status === "pending") nextHost.append(node("p", "This next examination is pending because exact provenance is unavailable. Its question and reason are hidden.", { class: "p6-empty" }));
  else if (next.status === "provisional" && !next.question) nextHost.append(node("p", "No generated comparison proposal is available yet. You can request one from the eligible human observations below, or enter a question and reason yourself.", { class: "p6-empty" }));
  else {
    nextHost.append(node("p", `Provisional or selected question: ${next.question}`, { class: "p6-record" }), node("p", `Reason: ${next.reason}`, { class: "muted" }));
    if (next.status === "provisional") {
      const refs = node("p", `Grounded in ${next.observationRefs?.length || 0} exact observation reference(s).`, { class: "muted" }); nextHost.append(refs);
    }
  }
  const editor = ensureNextExaminationEditor();
  const unavailableNext = next.status === "pending" || next.status === "awaiting_observation" || noObs;
  if (unavailableNext) {
    for (const field of [editor.question, editor.reason, editor.refs]) { field.value = ""; delete field.dataset.dirty; }
    editor.refs.replaceChildren();
    editor.refs.disabled = true;
  } else {
    editor.refs.disabled = false;
    if (!editor.question.dataset.dirty) editor.question.value = next.question || "";
    if (!editor.reason.dataset.dirty) editor.reason.value = next.reason || "";
  }
  if (!unavailableNext && !editor.refs.dataset.dirty) {
    editor.refs.replaceChildren();
    const selectedRefs = new Set((next.observationRefs || []).map((ref) => JSON.stringify(ref)));
    for (const observation of inquiryObservationMap.values()) {
      const ref = { id: observation.id, revision: observation.revision };
      editor.refs.append(node("option", `${observation.id} · revision ${observation.revision} · ${observation.origin}`, { value: JSON.stringify(ref), selected: selectedRefs.has(JSON.stringify(ref)) }));
    }
  }
  editor.save.disabled = next.status !== "provisional" && next.status !== "selected";
  editor.generate.disabled = item.status !== "ready" || item.observationCount < 1 || inquiryObservationMap.size === 0;
  $("#p6InquiryAccept").disabled = !currentInquiry || currentInquiry.status === "closed";
  $("#p6InquirySave").disabled = false;
  $("#p6ObservationRecord").disabled = !currentInquiry || currentInquiry.status !== "ready";
}
function ensureNextExaminationUI() {
  let host = $("#p6NextExaminationContent");
  if (!host) { host = node("div", "", { id: "p6NextExaminationContent", class: "p6-list", "aria-live": "polite" }); const form = $("#p6ObservationRecord")?.closest("form"); form?.after(host); }
  return host;
}
function ensureNextExaminationEditor() {
  let form = $("#p6NextExaminationEditor");
  if (!form) {
    form = node("fieldset", "", { id: "p6NextExaminationEditor" }); form.append(node("legend", "Creator edit and selection"));
    const q = node("textarea", "", { id: "p6NextQuestion", rows: 3, maxlength: 2000, "aria-label": "Edited next examination question" });
    const r = node("textarea", "", { id: "p6NextReason", rows: 3, maxlength: 2000, "aria-label": "Reason and unresolved issue" });
    const refs = node("select", "", { id: "p6NextRefs", multiple: true, size: 4, "aria-label": "Exact observations grounding the selected next examination" });
    const save = node("button", "Select this edited next examination", { id: "p6NextSave", type: "button", class: "button secondary", disabled: true });
    const generate = node("button", "Generate a comparison proposal (AI)", { id: "p6NextGenerate", type: "button", class: "button secondary", disabled: true });
    form.append(generate, node("label", "Question", { for: "p6NextQuestion" }), q, node("label", "Reason and unresolved issue", { for: "p6NextReason" }), r, node("label", "Select exact observations", { for: "p6NextRefs" }), refs, save);
    const host = ensureNextExaminationUI(); host.after(form);
  }
  return { question: $("#p6NextQuestion"), reason: $("#p6NextReason"), refs: $("#p6NextRefs"), save: $("#p6NextSave"), generate: $("#p6NextGenerate") };
}
function renderInquiries(items) {
  let host = $("#p6InquiryList");
  if (!host) {
    host = node("div", "", { id: "p6InquiryList", class: "p6-list" });
    $("#p6InquiryPlanTitle").closest(".p6-card").append(host);
  }
  setList("p6InquiryList", items, (item) => {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("strong", `${item.question} · ${item.status} · revision ${item.revision}`));
    card.append(node("p", `${item.alternatives?.length || 0} alternative(s) · ${item.observationCount || 0} observation(s) · next examination: ${item.nextExamination?.status || "awaiting_observation"}`, { class: "muted" }));
    const open = p6Button("Open inquiry", "inquiry-select"); open.dataset.id = item.id; card.append(open);
    return card;
  }, "No inquiry records are available.");
}
function renderObservations(items) {
  const host = $("#p6ObservationList"); if (!host) return;
  inquiryObservationMap = new Map(items.filter((item) => item.status === "active" && item.available !== false && item.text != null).map((item) => [item.id, item]));
  setList("p6ObservationList", items, (item) => {
    const card = node("article", "", { class: "p6-record" });
    if (item.available === false || item.status === "revoked") card.append(node("strong", "Observation unavailable"), node("p", "Its exact source or consent is no longer eligible; body text is hidden.", { class: "muted" }));
    else {
      card.append(node("strong", `Actor: ${item.actor || "creator"} · ${item.status} · revision ${item.revision}`), node("p", item.text));
      card.append(node("p", `Origin: ${item.origin} · observed at: ${item.observedAt || "unknown"}`, { class: "muted" }));
      card.append(node("p", `Method: ${item.method} · uncertainty: ${item.uncertainty} · limitations: ${item.limitations}`, { class: "muted" }));
      if (item.supersedes) card.append(node("p", `Supersedes observation ${item.supersedes.id} revision ${item.supersedes.revision}.`, { class: "muted" }));
      if (item.status === "active") { const correct = p6Button("Append a corrected observation", "observation-correct"); correct.dataset.id = item.id; correct.dataset.revision = String(item.revision); card.append(correct); }
      if (item.status === "active" && item.consent?.project && item.consent?.crossSession) { const grant = p6Button("Grant exact observation for a destination project", "observation-grant"); grant.dataset.id = item.id; grant.dataset.revision = String(item.revision); card.append(grant); }
      if (item.status === "active") { const revoke = p6Button("Revoke observation", "observation-revoke", "danger"); revoke.dataset.id = item.id; revoke.dataset.revision = String(item.revision); card.append(revoke); }
    }
    return card;
  }, "No observation records are available.");
}
function renderGrants(items) {
  const hostId = role === "creator" ? "p6CreatorGrants" : "p6Grants";
  if (role === "creator" && !$("#p6CreatorGrants")) {
    const host = node("div", "", { id: hostId, class: "p6-list" });
    $("#p6SaveGroup")?.closest(".p6-card")?.after(host);
  }
  setList(hostId, items, (grant) => {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("strong", `${grant.kind} grant · ${grant.status} · revision ${grant.revision}`));
    card.append(node("p", `Origin ${grant.originSessionId} · item ${grant.object.id} revision ${grant.object.revision} · destination project ${grant.destinationProjectId}`, { class: "muted" }));
    if (role === "creator" && grant.kind === "reading" && grant.status === "pending_creator") { const approve = p6Button("Approve this cross-session grant", "grant-approve"); approve.dataset.id = grant.id; approve.dataset.revision = String(grant.revision); card.append(approve); }
    if (grant.status !== "revoked") { const revoke = p6Button("Revoke exact grant", "grant-revoke", "danger"); revoke.dataset.id = grant.id; revoke.dataset.revision = String(grant.revision); card.append(revoke); }
    return card;
  }, "No export grants are available.");
}
function renderInquiryPresentationChoices(observations) {
  const host = $("#p6InquiryPresentationSelection"); if (!host) return;
  host.replaceChildren();
  const eligible = observations.filter((x) => x.status === "active" && x.available !== false && x.consent?.editorial === true);
  if (!eligible.length) host.append(node("div", "No currently eligible observation has a separate editorial grant.", { class: "p6-empty" }));
  for (const item of eligible) {
    const check = node("input", "", { type: "checkbox", dataset: { inquiryObservation: item.id, revision: String(item.revision) } });
    const label = node("label", `Select exact observation: ${item.text.slice(0, 100)}`, { class: "check-line" }); label.prepend(check); host.append(label);
  }
}
function renderInquiryPresentations(items) {
  const select = $("#p6InquiryPresentationSelect"); if (!select) return;
  const selectedId = select.value || currentInquiryPresentation?.id;
  select.replaceChildren(node("option", "Choose a presentation", { value: "" }));
  for (const item of items) select.append(node("option", `${item.id} · ${item.status} · revision ${item.revision}`, { value: item.id }));
  currentInquiryPresentation = items.find((x) => x.id === selectedId) || items.at(-1) || null;
  select.value = currentInquiryPresentation?.id || "";
  $("#p6InquiryPresentationCreate").disabled = false;
  $("#p6InquiryPresentationVersion").disabled = !currentInquiryPresentation;
  const eligible = currentInquiryPresentation?.versions?.some((v) => v.number === currentInquiryPresentation.currentVersion && v.eligible) === true;
  $("#p6InquiryPresentationApprove").disabled = !eligible || currentInquiryPresentation.status !== "draft";
  $("#p6InquiryPresentationPresent").disabled = !eligible || currentInquiryPresentation.status !== "approved";
  $("#p6InquiryPresentationWithdraw").disabled = !currentInquiryPresentation || currentInquiryPresentation.status !== "presented";
  setList("p6CreatorInquiryPresentations", items, (item) => node("article", `${item.status} · exact version ${item.currentVersion} · eligible ${item.versions?.find((v) => v.number === item.currentVersion)?.eligible === true}`, { class: "p6-record" }), "No inquiry presentation versions are available.");
  previewCurrentInquiryVersion();
}
function ensureInquiryPresentationPreview() {
  let host = $("#p6InquiryExactPreview");
  if (!host) { host = node("div", "No exact inquiry version has been previewed.", { id: "p6InquiryExactPreview", class: "p6-list p6-empty", "aria-live": "polite" }); $("#p6InquiryPresentationSelection")?.after(host); }
  return host;
}
function previewCurrentInquiryVersion() {
  const host = ensureInquiryPresentationPreview(); const presentation = currentInquiryPresentation;
  const version = presentation?.versions?.find((item) => item.number === presentation.currentVersion);
  if (!version || version.eligible !== true) { host.replaceChildren(node("p", "The exact current inquiry version is unavailable or ineligible. No older version will be substituted.", { class: "p6-empty" })); host.dataset.version = ""; return; }
  host.replaceChildren(node("h4", `${version.title} · exact version ${version.number}`));
  for (const ref of version.observations || []) {
    const observation = inquiryObservationMap.get(ref.id);
    if (!observation || observation.revision !== ref.revision || observation.consent?.editorial !== true) { host.replaceChildren(node("p", "Exact preview unavailable because a selected observation is no longer eligible.", { class: "p6-empty" })); host.dataset.version = ""; return; }
    const card = node("article", "", { class: "p6-record" });
    card.append(node("p", observation.text), node("p", `${observation.origin} · ${observation.observedAt || "time unknown"} · ${observation.method}`, { class: "muted" }));
    card.append(node("p", `Uncertainty: ${observation.uncertainty} · limitations: ${observation.limitations}. This is a human report, not independently verified physical truth.`, { class: "muted" })); host.append(card);
  }
  host.dataset.version = String(version.number);
  host.dataset.presentationId = presentation.id;
}

function projectOwnerToken(projectId) {
  if (role !== "creator" || !$("#p6OwnerMode")?.checked) return null;
  try { return sessionStorage.getItem(`${ownerPrefix}${projectId}`) || localStorage.getItem(`${ownerPrefix}${projectId}`); } catch { return null; }
}
function ownerHeaders(projectId) {
  const token = projectOwnerToken(projectId);
  return token ? { Authorization: `Bearer ${token}` } : null;
}
function encodeCapability() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  let binary = ""; for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}
function renderJsonState(hostId, value) {
  const host = $(`#${hostId}`); if (!host) return;
  host.replaceChildren();
  if (!value) { host.append(node("div", "No authorized project state is available.", { class: "p6-empty" })); return; }
  const project = value.project || value;
  host.append(node("strong", `${project.title} · project ${project.id} · revision ${project.revision}`));
  host.append(node("p", project.question, { class: "muted" }));
  const state = project.state || {};
  host.append(node("p", `Review available: ${state.reviewAvailable === true ? "yes" : "no"}.`, { class: "muted" }));
  if (state.selectedPlan) host.append(node("p", state.selectedPlan.available === false || state.selectedPlan.text == null ? "Selected plan provenance is unavailable; its text is hidden." : `Selected plan: ${state.selectedPlan.text}`));
  if (state.observations?.length) host.append(node("p", `${state.observations.filter((x) => x.available).length} available explicitly shared observation(s).`));
  for (const decision of state.decisions || []) host.append(node("p", decision.provenanceStatus === "invalidated" ? `Decision provenance invalidated${decision.reversed ? " · reversed" : ""}; derived decision text is hidden.` : `Decision: ${decision.text} · qualification: ${decision.qualification} · provenance ${decision.provenanceStatus}${decision.reversed ? " · reversed" : ""}`));
  for (const action of state.actions || []) host.append(node("p", action.provenanceStatus === "invalidated" || action.text == null ? `A next app action is suspended because its provenance is unavailable.` : `Next app action: ${action.text} · ${action.status} · provenance ${action.provenanceStatus}`));
  host.dataset.projectRevision = String(project.revision);
  const nextHost = $("#p6NextActionView");
  if (nextHost) {
    nextHost.replaceChildren();
    const actions = (state.actions || []).filter((x) => x.status === "open" && x.provenanceStatus === "valid");
    if (!actions.length) nextHost.append(node("div", "No available next app action is recorded.", { class: "p6-empty" }));
    else for (const action of actions) nextHost.append(node("article", action.text, { class: "p6-record" }));
  }
}

function exactProjectRef() {
  const originSessionId = $("#p6ExactOriginSession").value.trim();
  const kind = $("#p6ExactKind").value;
  const id = $("#p6ExactObjectId").value.trim();
  const revision = Number($("#p6ExactObjectRevision").value);
  const grantId = $("#p6ExactGrantId").value.trim();
  return originSessionId && id && grantId && Number.isInteger(revision) && revision > 0 ? { originSessionId, kind, id, revision, grantId } : null;
}
function renderProjectItems(id, items, empty, renderItem) {
  setList(id, items, renderItem, empty);
}
function renderLinks(items, ownerView = false) {
  const hostId = ownerView ? "p6OwnerLinks" : "p6ProjectLinkRequests";
  renderProjectItems(hostId, items, "No pending or active project link requests are available.", (link) => {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("strong", `Project link ${link.id} · ${link.status} · revision ${link.revision}`));
    const creatorScopes = Object.entries(link.scopes?.creator || {}).filter(([, allowed]) => allowed).map(([name]) => `creator ${name}`);
    const viewerScopes = Object.entries(link.scopes?.viewer || {}).filter(([, allowed]) => allowed).map(([name]) => `viewer ${name}`);
    card.append(node("p", `Project ${link.projectId} · granted access: ${[...creatorScopes, ...viewerScopes].join(", ") || "none"}`, { class: "muted" }));
    if (!ownerView && link.status === "pending" && role === "creator") { const approve = p6Button("Approve this exact session link", "link-approve"); approve.dataset.id = link.id; approve.dataset.revision = String(link.revision); card.append(approve); }
    if (!ownerView && link.status === "active" && role === "creator") { const revoke = p6Button("Revoke this session link", "link-revoke", "danger"); revoke.dataset.id = link.id; revoke.dataset.revision = String(link.revision); card.append(revoke); }
    if (ownerView && link.status !== "revoked") { const revoke = p6Button("Revoke this owner link", "owner-link-revoke", "danger"); revoke.dataset.id = link.id; revoke.dataset.revision = String(link.revision); card.append(revoke); }
    return card;
  });
}
function renderProposals(items, ownerMode) {
  currentProposalList = items;
  const select = $("#p6ProposalSelect");
  if (select) {
    const selectedId = select.value;
    select.replaceChildren(node("option", "Choose a proposal", { value: "" }));
    for (const proposal of items) select.append(node("option", `${proposal.id} · ${proposal.status} · revision ${proposal.revision}`, { value: proposal.id }));
    if (items.some((proposal) => proposal.id === selectedId)) select.value = selectedId;
  }
  renderProjectItems("p6ProposalList", items, "No project proposals are available.", (proposal) => {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("strong", `Proposal ${proposal.status} · revision ${proposal.revision}`));
    if (proposal.operation) card.append(node("p", `${proposal.operation.type}: ${proposal.operation.text || proposal.operation.actionId || proposal.operation.ref?.id || "typed change"}`));
    if (proposal.reason) card.append(node("p", `Reason: ${proposal.reason}`, { class: "muted" }));
    if (proposal.refs?.length) card.append(node("p", `Pinned exact references: ${proposal.refs.map((x) => `${x.kind} ${x.id} revision ${x.revision}`).join("; ")}`, { class: "muted" }));
    if (proposal.status === "blocked" || proposal.operation == null) card.append(node("p", "A source is unavailable; its body and derived proposal content are hidden.", { class: "muted" }));
    if (!ownerMode && proposal.status === "proposed" && proposal.actor === (role === "creator" ? "creator" : "viewer")) { const withdraw = p6Button("Withdraw proposal", "proposal-withdraw", "danger"); withdraw.dataset.id = proposal.id; withdraw.dataset.revision = String(proposal.revision); card.append(withdraw); }
    return card;
  });
  const selected = items.find((x) => x.id === select?.value) || items.at(0) || null;
  if (select && selected) select.value = selected.id;
  if (selected?.operation && selected.status !== "blocked" && !projectLoadPending) showProposalPreview(selected.operation);
  else clearProposalPreview("No current eligible proposal preview is available. Select and review a current proposal.");
  updateProposalControls();
}
function clearProposalPreview(message = "Proposal preview unavailable until current authorized state is reviewed.") {
  for (const id of ["p6BeforePreview", "p6AfterPreview"]) {
    const host = $(`#${id}`);
    if (host) host.replaceChildren(node("div", message, { class: "p6-empty", role: "status" }));
  }
}
function updateProposalControls() {
  const select = $("#p6ProposalSelect");
  const selected = currentProposalList.find((x) => x.id === select?.value) || null;
  const projectReady = Boolean(currentProject) && !projectLoadPending;
  const ownerCap = projectReady && ownerHeaders(currentProject.id);
  const canDecide = role === "creator" && Boolean(ownerCap);
  $("#p6ProposalAccept").disabled = !canDecide || !selected || selected.status !== "proposed";
  $("#p6ProposalApply").disabled = !canDecide || !selected || selected.status !== "accepted";
  $("#p6ProposalReverse").disabled = !canDecide || !selected || selected.status !== "applied";
  $("#p6ProposalReject").disabled = !canDecide || !selected || !["proposed", "accepted", "blocked"].includes(selected.status);
  const scope = projectReady ? currentProjectScopes?.[role] || {} : {};
  $("#p6ProjectImport").disabled = !projectReady || role !== "creator" || scope.read !== true;
  $("#p6ProposalSubmit").disabled = !projectReady || scope.propose !== true;
  $("#p6ProposalPreview").disabled = !projectReady || scope.propose !== true;
  $("#p6ProjectLinkCreate").disabled = !projectReady || !ownerCap;
  $("#p6OwnerForget").disabled = !projectReady || !ownerCap;
  const actionSelect = $("#p6ActionId");
  if (actionSelect) actionSelect.disabled = !projectReady;
}
function renderHistory(items) {
  renderProjectItems("p6ProjectHistory", items, "No project history is available.", (entry) => {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("strong", `${entry.action} · project revision ${entry.projectRevision} · ${entry.actor}`));
    if (entry.reason) card.append(node("p", entry.reason));
    card.append(node("p", `Provenance ${entry.provenanceStatus} · ${entry.at}`, { class: "muted" })); return card;
  });
}
function renderImports(items) {
  renderProjectItems("p6ProjectImports", items, "No exact references have been imported into this session.", (item) => {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("strong", `${item.ref.kind} · ${item.ref.id} revision ${item.ref.revision} · ${item.status}`));
    card.append(node("p", `Origin session ${item.ref.originSessionId} · grant ${item.ref.grantId}. Imported content is resolved on demand and is not copied into project state.`, { class: "muted" }));
    const check = node("input", "", { type: "checkbox", dataset: { projectRef: JSON.stringify(item.ref) } });
    const label = node("label", "Select this exact imported reference for a proposal", { class: "check-line" }); label.prepend(check); card.append(label);
    const resolved = node("p", "Exact source has not been rechecked.", { class: "muted", dataset: { resolveStatus: "" } }); card.append(resolved);
    if (role === "creator" && item.status === "active") { const revoke = p6Button("Revoke this destination import", "import-revoke", "danger"); revoke.dataset.id = item.id; revoke.dataset.revision = String(item.revision); card.append(revoke); }
    return card;
  });
}
function projectRefsForViewer(project) {
  const refs = new Map(); const state = project?.state || {};
  for (const ref of state.selectedPlan?.sourceRefs || []) refs.set(JSON.stringify(ref), ref);
  for (const item of state.observations || []) if (item.ref) refs.set(JSON.stringify(item.ref), item.ref);
  for (const decision of state.decisions || []) for (const ref of decision.refs || []) refs.set(JSON.stringify(ref), ref);
  return [...refs.values()].map((ref, index) => ({ id: `state-ref-${index}`, revision: 1, ref, status: "active" }));
}
const resolvedProjectRefs = new Map();
function ensureProjectPicker() {
  let picker = $("#p6ProjectChoice"); if (picker) return picker;
  const label = node("label", "Authorized project", { for: "p6ProjectChoice" });
  picker = node("select", "", { id: "p6ProjectChoice", "aria-label": "Choose an authorized project" });
  const host = $("#view-project .page-head"); if (host) host.after(label, picker);
  picker.addEventListener("change", () => { selectedProjectId = picker.value || null; clearViewBodies("project"); loadProject(); });
  return picker;
}
async function resolveImportedReference(ref, card) {
  const scope = scopeNow(); const projectId = currentProject?.id;
  if (!projectId) return;
  const body = { ref };
  try {
    const result = role === "creator" && ownerHeaders(projectId)
      ? await mutate("p6OwnerResolveProjectRef", body, [projectId], scope, ownerHeaders(projectId))
      : await mutate("p6ResolveProjectRef", body, [projectId], scope);
    assert(scope);
    const target = $("[data-resolve-status]", card);
    if (!result.reference?.available || !result.reference.content) {
      resolvedProjectRefs.delete(JSON.stringify(ref));
      if (target) target.textContent = "Unavailable. No body is exposed and this reference cannot be proposed.";
      return;
    }
    resolvedProjectRefs.set(JSON.stringify(ref), result.reference);
    if (target) target.textContent = `${result.reference.content.kind} reference rechecked and currently available. Its content remains in the origin; project state stores only the exact reference.`;
  } catch (error) { if (error.name !== "AbortError") { resolvedProjectRefs.delete(JSON.stringify(ref)); const target = $("[data-resolve-status]", card); if (target) target.textContent = escapeReason(error); } }
}
function selectedRefs() {
  return $$('#p6ProjectImports input[type="checkbox"]:checked').map((check) => {
    const ref = JSON.parse(check.dataset.projectRef);
    if (!resolvedProjectRefs.has(JSON.stringify(ref))) throw new Error("reference_unavailable");
    return ref;
  });
}

async function loadPerspectives(scope = scopeNow()) {
  const generation = beginLoad("perspectives");
  try {
    if (role === "viewer") {
      const readingSource = $("#p6ReadingSource");
      const sourceValueAtStart = readingSource?.value || "";
      const sourceRefAtStart = selectedSource(readingSource);
      await controllerConfig.refreshSources(scope); assertLoad("perspectives", generation, scope);
      const sourceValueAfterRefresh = readingSource?.value || "";
      const sourceRefToKeep = sourceValueAfterRefresh === sourceValueAtStart
        ? sourceRefAtStart
        : selectedSource(readingSource);
      sourceOptions(readingSource, sourceRefToKeep);
      const [mine, pub] = await Promise.all([
        pages("p6Readings", scope),
        controllerConfig.api.call("p6PublicReadings", null, { scope }),
      ]); assertLoad("perspectives", generation, scope);
      if (currentReading) {
        const fresh = mine.find((item) => item.id === currentReading.id);
        if (!fresh || fresh.available === false || fresh.text == null) clearReadingForm();
        else if (fresh.revision !== currentReading.revision) setStatus("perspectives", "This draft changed. Your entries remain on screen; refresh and review the current revision before saving.", true);
        else currentReading = fresh;
      }
      renderMyReadings(mine); publicReadings(pub);
      const grants = await pages("p6ExportGrants", scope); assertLoad("perspectives", generation, scope); renderGrants(grants);
      setButtons("#p6ReadingSave, #p6ReadingSubmit", true);
      await loadPublicInquiry(scope);
    } else if (role === "creator") {
      clearGroupingProjection("Checking the saved rationale against current reading eligibility…");
      const [review, presentations] = await Promise.all([pages("p6ReadingReview", scope), pages("p6ReadingPresentations", scope)]); assertLoad("perspectives", generation, scope);
      renderReadingReview(review); renderPresentations(presentations);
      const grants = await pages("p6ExportGrants", scope); assertLoad("perspectives", generation, scope); renderGrants(grants);
      await refreshSavedGrouping(scope, generation);
      setButtons("#p6SaveGroup, #p6PresentationCreate", true);
      const eligibleVersion = currentPresentation?.versions?.find((v) => v.number === currentPresentation.currentVersion)?.eligible === true;
      $("#p6PresentationNewVersion").disabled = !currentPresentation;
      $("#p6PresentationApprove").disabled = !eligibleVersion || currentPresentation.status !== "draft";
      $("#p6PresentationPresent").disabled = !eligibleVersion || currentPresentation.status !== "approved";
      $("#p6PresentationWithdraw").disabled = !currentPresentation || currentPresentation.status !== "presented";
    }
    setStatus("perspectives", "Reading records are current for this session.");
  } catch (error) { if (error.name !== "AbortError") { clearViewBodies("perspectives"); requestFailed("perspectives", error); } }
}
async function saveReadingDraft() {
  const scope = scopeNow();
  const sourceRef = selectedSource($("#p6ReadingSource"));
  const body = { sourceRef, text: $("#p6ReadingText").value, reason: $("#p6ReadingReason").value };
  if (!sourceRef || !body.text.trim() || !body.reason.trim()) { setStatus("perspectives", "Choose an eligible exact source revision and enter both a reading and its reason.", true); return null; }
  try {
    const result = currentReading?.id
      ? await mutate("p6Reading", { expectedRevision: currentReading.revision, ...body }, [currentReading.id], scope)
      : await mutate("p6ReadingCreate", body, [], scope);
    currentReading = result.reading;
    await loadPerspectives();
    setStatus("perspectives", "Private draft saved.");
    return currentReading;
  } catch (error) { requestFailed("perspectives", error); return null; }
}
async function submitReading() {
  const scope = scopeNow();
  const mode = $("#p6Attribution").value;
  const label = mode === "unattributed" ? null : mode === "name" ? $("#p6AttributionLabel").value.trim() : $("#p6Pseudonym").value.trim();
  if (mode !== "unattributed" && !label) { setStatus("perspectives", "Enter the display label you allow for this attribution choice.", true); return; }
  const checks = $$('#view-perspectives [data-p6-role="viewer"] input[type="checkbox"]');
  if (checks[0]?.checked !== true) { setStatus("perspectives", "Confirm creator review as a separate purpose before submitting.", true); return; }
  const draftBody = { sourceRef: selectedSource($("#p6ReadingSource")), text: $("#p6ReadingText").value, reason: $("#p6ReadingReason").value };
  if (!draftBody.sourceRef || !draftBody.text.trim() || !draftBody.reason.trim()) { setStatus("perspectives", "Choose an eligible exact source revision and enter both a reading and its reason.", true); return; }
  const consent = { review: true, publicQuotation: checks[1]?.checked === true, crossSession: checks[2]?.checked === true, attribution: { mode, label } };
  try {
    const draftResult = currentReading?.id
      ? await mutate("p6Reading", { expectedRevision: currentReading.revision, ...draftBody }, [currentReading.id], scope)
      : await mutate("p6ReadingCreate", draftBody, [], scope);
    assert(scope); const reading = draftResult.reading;
    await mutate("p6ReadingSubmit", { expectedRevision: reading.revision, consent }, [reading.id], scope);
    clearReadingForm(); await loadPerspectives(); setStatus("perspectives", "Reading submitted for creator review. Public quotation remains separately governed by your choice.");
  }
  catch (error) { requestFailed("perspectives", error); }
}
async function loadPublicInquiry(scope = scopeNow()) {
  try {
    const data = await controllerConfig.api.call("p6PublicInquiries", null, { scope }); assert(scope);
    const host = $("#p6PublicInquiries"); if (!host) return;
    host.replaceChildren();
    const presentation = data?.presentation;
    if (!presentation) { host.append(node("div", "No eligible presented inquiry version is available.", { class: "p6-empty" })); return; }
    host.append(node("h4", presentation.title || "Presented inquiry"), node("p", `Exact version ${presentation.version}. Reports are not verified physical truth.`, { class: "muted" }));
    for (const observation of presentation.observations || []) {
      const card = node("article", "", { class: "p6-record" });
      card.append(node("p", observation.text), node("p", `${observation.origin} · ${observation.observedAt || "time unknown"} · ${observation.method}`, { class: "muted" }));
      card.append(node("p", `Uncertainty: ${observation.uncertainty} · Limitations: ${observation.limitations}`, { class: "muted" })); host.append(card);
    }
  } catch (error) { if (error.name !== "AbortError") { const host = $("#p6PublicInquiries"); if (host) { host.replaceChildren(node("div", escapeReason(error), { class: "p6-empty" })); } } }
}
async function withdrawReading(id) {
  const scope = scopeNow();
  const reading = (await pages("p6Readings", scope)).find((x) => x.id === id); assert(scope);
  if (!reading) return setStatus("perspectives", "This reading is no longer available. Refresh the list.", true);
  try { await mutate("p6ReadingWithdraw", { expectedRevision: reading.revision }, [id], scope); clearReadingForm(); await loadPerspectives(); setStatus("perspectives", "Reading withdrawn. Dependent content is no longer treated as eligible."); }
  catch (error) { requestFailed("perspectives", error); }
}
async function createReadingGrant(id, revision, scope = scopeNow()) {
  const destinationProjectId = $("#p6DestinationProject").value.trim();
  if (!destinationProjectId) return setStatus("perspectives", "Name the destination project for this exact cross-session grant.", true);
  try {
    const reading = (await pages("p6Readings", scope)).find((item) => item.id === id); assert(scope);
    if (!reading || reading.status !== "submitted" || reading.revision !== revision || reading.available === false || reading.consent?.crossSession !== true || reading.consent?.publicQuotation !== true) return setStatus("perspectives", "This exact reading is no longer eligible for a cross-session grant. Refresh and review it.", true);
    const result = await mutate("p6ReadingGrant", { reading: { id, revision }, destinationProjectId }, [], scope); assert(scope);
    await loadPerspectives(scope); assert(scope); setStatus("perspectives", `Cross-session grant ${result.grant.id} is ${result.grant.status}. The destination has no access until current grant and link checks pass.`);
  }
  catch (error) { requestFailed("perspectives", error); }
}
async function grantAction(button, action, scope = scopeNow()) {
  const grantId = button.dataset.id, expectedRevision = Number(button.dataset.revision);
  try { await mutate("p6GrantAction", { expectedRevision }, [grantId, action], scope); assert(scope); await loadPerspectives(scope); assert(scope); setStatus("perspectives", `Exact export grant ${action} recorded.`); }
  catch (error) { requestFailed("perspectives", error); }
}
async function saveGroup() {
  const scope = scopeNow();
  const selected = [...$("#p6GroupSelection").selectedOptions].map((o) => JSON.parse(o.value));
  const label = $("#p6GroupLabel").value.trim(), rationale = $("#p6GroupRationale").value.trim(), disagreement = $("#p6Disagreement").value.trim();
  if (!selected.length || !label || !rationale || !disagreement) return setStatus("perspectives", "Choose at least one eligible reading and describe the rationale and remaining disagreement.", true);
  try {
    const result = await mutate("p6ReadingGroups", { groups: [{ label, rationale, disagreement, readings: selected }] }, [], scope);
    assert(scope);
    rememberGroupingId(scope, result.grouping?.id);
    clearGroupingDraft();
    clearGroupingProjection("Rationale saved. Checking current reading eligibility…");
    await loadPerspectives(); setStatus("perspectives", "Rationale group saved. Each submitted reason remains separately available.");
  }
  catch (error) { requestFailed("perspectives", error); }
}
function selectedPresentationItems() {
  return $$('[data-presentation-reading]:checked').map((check) => {
    const reading = { id: check.dataset.presentationReading, revision: Number(check.dataset.revision) };
    const fixed = $(`[data-p6-reading-source="${CSS.escape(reading.id)}"]`);
    return { reading, attribution: fixed ? JSON.parse(fixed.dataset.attribution) : null };
  }).filter((item) => item.attribution);
}
async function savePresentation(newVersion = false) {
  const title = $("#p6PresentationTitle").value.trim(); const items = selectedPresentationItems();
  if (!title || !items.length) return setStatus("perspectives", "Choose a title and at least one currently eligible reading with contributor-allowed attribution.", true);
  try {
    let result;
    if (newVersion) {
      if (!currentPresentation) return setStatus("perspectives", "Choose an existing presentation before saving a new version.", true);
      result = await mutate("p6ReadingPresentationVersion", { expectedRevision: currentPresentation.revision, title, items }, [currentPresentation.id], scopeNow());
    } else result = await mutate("p6ReadingPresentationCreate", { title, items }, [], scopeNow());
    currentPresentation = result.presentation; $("#p6PresentationSelect").value = result.presentation.id; renderExactReadingVersionPreview(title, items, currentPresentation.currentVersion); await loadPerspectives(); setStatus("perspectives", "Exact presentation version saved as a draft and previewed. It is not public until separately approved and presented.");
  } catch (error) { requestFailed("perspectives", error); }
}
async function presentationAction(action) {
  const scope = scopeNow();
  const id = $("#p6PresentationSelect").value;
  if (!id) return setStatus("perspectives", "Choose a presentation first.", true);
  const list = await pages("p6ReadingPresentations", scope); assert(scope); currentPresentation = list.find((x) => x.id === id);
  if (!currentPresentation) return setStatus("perspectives", "Presentation is unavailable. Refresh before continuing.", true);
  const version = currentPresentation.versions?.find((item) => item.number === currentPresentation.currentVersion);
  if (["approve", "present"].includes(action) && version?.eligible !== true) return setStatus("perspectives", "The exact current version is no longer eligible. Refresh and create a new version from eligible readings.", true);
  if (["approve", "present"].includes(action)) {
    const preview = $("#p6ReadingExactPreview");
    if (!preview?.dataset.version || preview.dataset.presentationId !== id || Number(preview.dataset.version) !== currentPresentation.currentVersion) return setStatus("perspectives", "Review the exact current-version preview before approving or presenting it.", true);
    if (!window.confirm(`${action === "approve" ? "Approve" : "Present"} the exact version shown in the preview?`)) return;
  }
  if (action === "withdraw" && !window.confirm("Withdraw this exact presented version?")) return;
  try { await mutate("p6ReadingPresentationAction", { expectedRevision: currentPresentation.revision, version: currentPresentation.currentVersion }, [id, action], scope); await loadPerspectives(); setStatus("perspectives", `Exact version ${action} action recorded.`); }
  catch (error) { requestFailed("perspectives", error); }
}
function renderExactReadingVersionPreview(title, items, version) {
  const host = $("#p6ReadingExactPreview"); if (!host) return;
  host.replaceChildren(node("h4", `${title} · exact version ${version}`));
  for (const item of items) {
    const reading = submittedReadingMap.get(item.reading.id);
    if (!reading || reading.revision !== item.reading.revision || reading.consent?.publicQuotation !== true || JSON.stringify(reading.consent.attribution) !== JSON.stringify(item.attribution)) {
      host.replaceChildren(node("p", "Exact preview unavailable: an included reading or allowed attribution is no longer current.", { class: "p6-empty" }));
      host.dataset.version = ""; return;
    }
    const card = node("article", "", { class: "p6-record" });
    card.append(node("p", reading.text), node("p", `Reason: ${reading.reason}`, { class: "muted" }));
    card.append(node("p", item.attribution.mode === "unattributed" ? "Unattributed" : item.attribution.label, { class: "muted" }));
    host.append(card);
  }
  host.dataset.version = String(version);
  host.dataset.presentationId = currentPresentation?.id || "";
}

async function loadWork() {
  const scope = scopeNow();
  const generation = beginLoad("work");
  try {
    if (role === "viewer") {
      await controllerConfig.refreshSources(scope); assertLoad("work", generation, scope); sourceOptions($("#p6WorkSource"));
      const items = await pages("p6Coactivities", scope); assertLoad("work", generation, scope); renderCoactivities(items);
      renderOwnShares();
      if (!currentCoactivity || !items.some((x) => x.id === currentCoactivity.id)) { currentCoactivity = items.at(0) || null; if (currentCoactivity) fillCoactivity(currentCoactivity); else updateWorkControls(null); }
      else {
        const fresh = items.find((item) => item.id === currentCoactivity.id);
        if (fresh.revision !== currentCoactivity.revision && ["p6Activity", "p6DeclaredState", "p6Minutes", "p6Step"].some((id) => $(`#${id}`)?.dataset.dirty)) {
          setStatus("work", "This activity changed. Your entries remain on screen; refresh and review the latest revision before saving.", true);
        } else {
          const protectedDraftRedacted = fresh.sourceRef != null && fresh.contextAvailable === false && !fresh.stepDraft && !fresh.acceptedStep && !fresh.reentryDraft;
          currentCoactivity = fresh;
          if (protectedDraftRedacted) {
            if (!$("#p6Activity").dataset.dirty) $("#p6Activity").value = fresh.activity || "";
            if (!$("#p6DeclaredState").dataset.dirty) $("#p6DeclaredState").value = fresh.declaredState || "";
            if (!$("#p6Minutes").dataset.dirty) $("#p6Minutes").value = String(fresh.minutes || "");
            $("#p6Step").value = ""; delete $("#p6Step").dataset.dirty;
            currentSharePreview = null; $("#p6WorkResult").value = ""; $("#p6WorkSharePreview").replaceChildren(node("div", "No share preview is available.", { class: "p6-empty" }));
            $("#p6WorkShareConfirm").disabled = true; $("#p6WorkSharePreviewButton").disabled = true;
            $("#p6WorkShareConsent").checked = false;
            updateWorkControls(fresh);
          } else if (!["p6Activity", "p6DeclaredState", "p6Minutes", "p6Step"].some((id) => $(`#${id}`)?.dataset.dirty)) fillCoactivity(fresh);
        }
      }
      updateWorkShareControls();
      $("[data-p6-action='work-create']").disabled = false;
      setStatus("work", "Private activity records are available only to this viewer identity.");
    } else {
      const shares = await pages("p6CoactivityShares", scope); assertLoad("work", generation, scope); renderCreatorShares(shares);
      setStatus("work", "Only explicitly shared active results are shown here. Private coactivity records are not available to creators.");
    }
  } catch (error) { if (error.name !== "AbortError") { clearViewBodies("work"); requestFailed("work", error); } }
}
async function createCoactivity() {
  const sourceRef = selectedSource($("#p6WorkSource"));
  const body = { activity: $("#p6Activity").value, declaredState: $("#p6DeclaredState").value, minutes: Number($("#p6Minutes").value), sourceRef };
  if (!body.activity.trim() || !body.declaredState.trim() || !Number.isInteger(body.minutes) || body.minutes < 1 || body.minutes > 480) return setStatus("work", "Enter your activity, current state and available time from 1 to 480 minutes.", true);
  try { const result = await mutate("p6CoactivityCreate", body); fillCoactivity(result.coactivity); await loadWork(); setStatus("work", "Private activity created. No result or sharing has been assumed."); }
  catch (error) { requestFailed("work", error); }
}
async function saveCoactivity() {
  if (!currentCoactivity) return createCoactivity();
  const body = { expectedRevision: currentCoactivity.revision, activity: $("#p6Activity").value, declaredState: $("#p6DeclaredState").value, minutes: Number($("#p6Minutes").value), stepDraft: currentCoactivity.stepDraft };
  if (currentCoactivity.status === "reentry") body.reentryDraft = $("#p6Step").value;
  else body.stepDraft = $("#p6Step").value;
  try { const result = await mutate("p6CoactivityPatch", body, [currentCoactivity.id]); fillCoactivity(result.coactivity); await loadWork(); setStatus("work", "Private activity edits saved."); }
  catch (error) { requestFailed("work", error); }
}
async function workAction(action) {
  if (action === "work-create") return createCoactivity();
  if (action === "work-save") return saveCoactivity();
  if (!currentCoactivity) return setStatus("work", "Create or select a private activity first.", true);
  const scope = scopeNow();
  try {
    let result;
    if (["work-prepare", "work-generate", "work-generate-reentry"].includes(action)) {
      const endpoint = action.slice("work-".length);
      result = await mutate("p6CoactivityAction", { expectedRevision: currentCoactivity.revision }, [currentCoactivity.id, endpoint], scope);
    } else {
      const actionName = action.slice("work-".length);
      const body = { expectedRevision: currentCoactivity.revision, action: actionName, declaredState: null, minutes: null, step: null };
      if (actionName === "accept" || actionName === "resume") body.step = $("#p6Step").value;
      if (actionName === "return") { body.declaredState = $("#p6DeclaredState").value; body.minutes = Number($("#p6Minutes").value); }
      result = await mutate("p6CoactivityActions", body, [currentCoactivity.id], scope);
    }
    fillCoactivity(result.coactivity); await loadWork(); statusForObject("work", result.coactivity.status, "Private activity");
  } catch (error) { requestFailed("work", error); }
}
async function previewWorkShare() {
  if (!currentCoactivity) return setStatus("work", "Select a private activity before previewing a result.", true);
  const scope = scopeNow(), generation = beginObject("coactivity-selection"), selected = currentCoactivity;
  const text = $("#p6WorkResult").value;
  if (!text.trim()) return setStatus("work", "Enter the exact result you choose to share.", true);
  try {
    const result = await mutate("p6CoactivityShare", { expectedRevision: selected.revision, text }, [selected.id, "share-preview"], scope);
    assertObject("coactivity-selection", generation, scope);
    currentSharePreview = result.preview;
    const host = $("#p6WorkSharePreview"); host.replaceChildren(node("p", currentSharePreview.text), node("p", `Preview for activity revision ${currentSharePreview.coactivityRevision}. Nothing has been shared.`, { class: "muted" }));
    updateWorkShareControls();
    setStatus("work", "Preview ready. This selected text is not shared until you confirm.");
  } catch (error) { requestFailed("work", error); }
}
async function confirmWorkShare() {
  if (!currentCoactivity || !currentSharePreview || !$("#p6WorkShareConsent").checked) return setStatus("work", "Preview the exact result and grant this separate share first.", true);
  const scope = scopeNow(); const coactivityId = currentCoactivity.id;
  const preview = { ...currentSharePreview };
  try {
    const result = await mutate("p6CoactivityShare", { expectedRevision: preview.coactivityRevision, text: preview.text, confirm: true }, [coactivityId, "shares"], scope);
    assert(scope); const key = `entrelineas.p6.own-shares:${scope.sessionId}:${scope.viewerId}`;
    let shares = []; try { shares = JSON.parse(sessionStorage.getItem(key) || "[]"); } catch {}
    shares = [...shares.filter((share) => share.id !== result.share.id), { id: result.share.id, revision: result.share.revision, coactivityId, status: result.share.status }];
    sessionStorage.setItem(key, JSON.stringify(shares)); activeOwnShare = result.share; currentSharePreview = null; await loadWork(); setStatus("work", "Selected result shared under the separate grant. The active share can be revoked below.");
  }
  catch (error) { requestFailed("work", error); }
}
function renderOwnShares() {
  let host = $("#p6OwnShares");
  if (!host) { host = node("div", "", { id: "p6OwnShares", class: "p6-list" }); $("#p6WorkSharePreview")?.after(host); }
  host.replaceChildren(); const scope = scopeNow(); const key = `entrelineas.p6.own-shares:${scope.sessionId}:${scope.viewerId}`;
  let shares = []; try { shares = JSON.parse(sessionStorage.getItem(key) || "[]"); } catch {}
  if (!shares.length) { host.append(node("div", "No local share references are saved for this browser session.", { class: "p6-empty" })); return; }
  for (const share of shares) {
    const card = node("article", "", { class: "p6-record" });
    card.append(node("p", `Your explicit share ${share.id} · ${share.status} · revision ${share.revision}.`));
    if (share.status === "active") { const button = p6Button("Revoke this exact share", "share-revoke", "danger"); button.dataset.id = share.id; button.dataset.revision = String(share.revision); card.append(button); }
    host.append(card);
  }
}

async function loadInquiry(scope = scopeNow()) {
  const generation = beginLoad("inquiry");
  try {
    await controllerConfig.refreshSources(scope); assertLoad("inquiry", generation, scope); sourceOptions($("#p6InquirySource")); sourceOptions($("#p6ObservationSource"));
    const items = await pages("p6Inquiries", scope); assertLoad("inquiry", generation, scope); renderInquiries(items); $("#p6InquirySave").disabled = false;
    const fresh = items.find((item) => item.id === currentInquiry?.id) || (!currentInquiry ? items.at(0) : null);
    if (fresh) { const preserve = currentInquiry?.id === fresh.id; currentInquiry = fresh; fillInquiry(fresh, preserve); }
    else if (currentInquiry && !items.some((item) => item.id === currentInquiry.id)) currentInquiry = null;
    if (currentInquiry) {
      const [observations, presentations, grants] = await Promise.all([
        pages("p6InquiryObservations", scope, [currentInquiry.id]),
        pages("p6InquiryPresentations", scope),
        pages("p6ExportGrants", scope),
      ]); assertLoad("inquiry", generation, scope); renderObservations(observations); fillInquiry(currentInquiry, true); renderInquiryPresentationChoices(observations); renderInquiryPresentations(presentations); renderGrants(grants);
    }
    setStatus("inquiry", currentInquiry?.observationCount ? "Observations below are human-entered reports, not verified physical truth." : "No observation has been recorded. A plan or provider response is not an observation.");
  } catch (error) { if (error.name !== "AbortError") { clearViewBodies("inquiry"); requestFailed("inquiry", error); } }
}
async function saveInquiry() {
  const body = inquiryPayload();
  if (!body.question.trim()) return setStatus("inquiry", "Enter the question before saving a plan.", true);
  try {
    const result = currentInquiry
      ? await mutate("p6InquiryPatch", { expectedRevision: currentInquiry.revision, ...body }, [currentInquiry.id])
      : await mutate("p6InquiryCreate", body);
    fillInquiry(result.inquiry); await loadInquiry(); setStatus("inquiry", "Inquiry draft saved. No observation or result has been inferred."); return result.inquiry;
  } catch (error) { requestFailed("inquiry", error); }
}
async function inquiryAction(action) {
  const scope = scopeNow();
  if (action === "save") return saveInquiry();
  if (!currentInquiry) return setStatus("inquiry", "Save an inquiry draft before accepting it.", true);
  if (action === "accept") {
    const body = inquiryPayload();
    if (!body.question.trim() || body.alternatives.some((x) => !x.text.trim() || !x.prediction.trim()) || body.alternatives[0].prediction.trim() === body.alternatives[1].prediction.trim() || !body.discriminator.trim() || !body.procedure.trim()) return setStatus("inquiry", "Complete two explanations with distinct predictions, a discriminator and a procedure before acceptance.", true);
    const saved = await saveInquiry(); if (!saved) return; assert(scope);
  }
  try { const result = await mutate("p6InquiryActions", { expectedRevision: currentInquiry.revision, action }, [currentInquiry.id], scope); fillInquiry(result.inquiry); await loadInquiry(); setStatus("inquiry", `Inquiry ${action} recorded. Observation count: ${result.inquiry.observationCount}.`); }
  catch (error) { requestFailed("inquiry", error); }
}
async function recordObservation() {
  if (!currentInquiry || currentInquiry.status !== "ready") return setStatus("inquiry", "Accept a current inquiry plan before recording an observation.", true);
  const checks = $$('#view-inquiry [data-p6-consent]');
  const body = {
    expectedRevision: currentInquiry.revision,
    text: $("#p6ObservationText").value,
    origin: $("#p6ObservationOrigin").value,
    observedAt: $("#p6ObservedAt").value ? new Date($("#p6ObservedAt").value).toISOString() : null,
    method: $("#p6Method").value,
    uncertainty: $("#p6Uncertainty").value,
    limitations: $("#p6Limitations").value,
    sourceRef: selectedSource($("#p6ObservationSource")),
    consent: { editorial: checks[0]?.checked === true, project: checks[1]?.checked === true, crossSession: checks[2]?.checked === true },
    supersedes: currentObservationToSupersede,
  };
  if (!body.text.trim() || !body.origin || !body.method.trim() || !body.uncertainty.trim() || !body.limitations.trim()) return setStatus("inquiry", "Enter the observation, source kind, method, uncertainty and limitations. Use the explicit unknown time if the time is unavailable.", true);
  if (body.origin === "source_report" && !body.sourceRef) return setStatus("inquiry", "Choose the exact source revision for a source report.", true);
  try { const result = await mutate("p6InquiryObservationCreate", body, [currentInquiry.id]); currentInquiry = result.inquiry; currentObservationToSupersede = null; $("#p6ObservationText").value = ""; await loadInquiry(); setStatus("inquiry", "Observation recorded as a human-entered report. Its next examination is ready for review."); }
  catch (error) { requestFailed("inquiry", error); }
}
async function createObservationGrant(id, revision, scope = scopeNow()) {
  const observation = inquiryObservationMap.get(id);
  if (!currentInquiry || !observation || observation.inquiryId !== currentInquiry.id || observation.status !== "active" || observation.available === false || observation.revision !== revision || observation.consent?.project !== true || observation.consent?.crossSession !== true) return setStatus("inquiry", "This exact observation is no longer eligible for a cross-session grant. Refresh and review it.", true);
  const destinationProjectId = $("#p6ObservationDestinationProject").value.trim();
  if (!destinationProjectId) return setStatus("inquiry", "Name the destination project for this exact observation grant.", true);
  try { const result = await mutate("p6ObservationGrant", { observation: { id, revision }, destinationProjectId }, [], scope); assert(scope); await loadInquiry(scope); assert(scope); setStatus("inquiry", `Observation grant ${result.grant.id} is ${result.grant.status}. The destination still needs a project link and import.`); }
  catch (error) { requestFailed("inquiry", error); }
}
async function saveInquiryPresentation(newVersion = false) {
  if (!currentInquiry) return setStatus("inquiry", "Choose an inquiry before preparing a public version.", true);
  const title = $("#p6InquiryPresentationTitle").value.trim();
  const observations = $$('[data-inquiry-observation]:checked').map((check) => ({ id: check.dataset.inquiryObservation, revision: Number(check.dataset.revision) }));
  if (!title || !observations.length) return setStatus("inquiry", "Choose a title and at least one currently eligible observation with explicit editorial consent.", true);
  try {
    let result;
    if (newVersion) {
      if (!currentInquiryPresentation) return setStatus("inquiry", "Choose an existing presentation before saving a version.", true);
      result = await mutate("p6InquiryPresentationVersion", { expectedRevision: currentInquiryPresentation.revision, title, observations }, [currentInquiryPresentation.id]);
    } else result = await mutate("p6InquiryPresentationCreate", { inquiryId: currentInquiry.id, title, observations });
    currentInquiryPresentation = result.presentation; $("#p6InquiryPresentationSelect").value = result.presentation.id; await loadInquiry(); setStatus("inquiry", "Exact inquiry presentation saved as a draft. It is not public until separately approved and presented.");
  } catch (error) { requestFailed("inquiry", error); }
}
async function inquiryPresentationAction(action) {
  const scope = scopeNow();
  const id = $("#p6InquiryPresentationSelect").value;
  if (!id) return setStatus("inquiry", "Choose an inquiry presentation first.", true);
  try {
    const items = await pages("p6InquiryPresentations", scope); assert(scope);
    currentInquiryPresentation = items.find((x) => x.id === id);
    if (!currentInquiryPresentation) return setStatus("inquiry", "Presentation is unavailable. Refresh before continuing.", true);
    if (["approve", "present"].includes(action)) {
      const preview = $("#p6InquiryExactPreview");
      if (!preview?.dataset.version || preview.dataset.presentationId !== id || Number(preview.dataset.version) !== currentInquiryPresentation.currentVersion) return setStatus("inquiry", "Review the exact current inquiry version before approving or presenting it.", true);
      if (!window.confirm(`${action === "approve" ? "Approve" : "Present"} the exact inquiry version shown in the preview?`)) return;
    }
    if (action === "withdraw" && !window.confirm("Withdraw this exact presented inquiry version?")) return;
    await mutate("p6InquiryPresentationAction", { expectedRevision: currentInquiryPresentation.revision, version: currentInquiryPresentation.currentVersion }, [id, action], scope);
    await loadInquiry(); setStatus("inquiry", `Exact inquiry presentation ${action} recorded.`);
  } catch (error) { requestFailed("inquiry", error); }
}

function applyRole(nextRole) {
  role = nextRole;
  const authenticated = role === "viewer" || role === "creator";
  for (const nav of $$('[data-phase6-view][data-view]')) {
    const view = nav.dataset.view;
    const allowed = authenticated && (view !== "inquiry" || role === "creator");
    nav.hidden = !allowed;
  }
  for (const view of $$('.p6-view[data-phase6-view]')) view.hidden = !(authenticated && (view.id !== "view-inquiry" || role === "creator"));
  for (const panel of $$('[data-p6-role]')) {
    const scope = panel.dataset.p6Role;
    panel.hidden = scope === "creator" ? role !== "creator" : scope === "viewer" ? role !== "viewer" : !authenticated;
  }
  for (const button of $$('.p6-view button')) button.disabled = true;
  if (authenticated) initializeHandlers();
}
function initializeHandlers() {
  if (controllerConfig.initialized) return;
  controllerConfig.initialized = true;
  ensureNextExaminationEditor();
  $("#p6ReadingSave").addEventListener("click", saveReadingDraft);
  $("#p6ReadingSubmit").addEventListener("click", submitReading);
  $("#p6SaveGroup").addEventListener("click", saveGroup);
  $("#p6PresentationCreate").addEventListener("click", () => savePresentation(false));
  $("#p6PresentationNewVersion").addEventListener("click", () => savePresentation(true));
  $("#p6PresentationApprove").addEventListener("click", () => presentationAction("approve"));
  $("#p6PresentationPresent").addEventListener("click", () => presentationAction("present"));
  $("#p6PresentationWithdraw").addEventListener("click", () => presentationAction("withdraw"));
  $("#p6MyReadings").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-p6-action]"); if (!button) return;
    if (button.dataset.p6Action === "reading-withdraw") await withdrawReading(button.dataset.id);
    if (button.dataset.p6Action === "reading-edit") {
      const scope = scopeNow(); const generation = beginObject("reading-selection");
      const item = (await pages("p6Readings", scope)).find((x) => x.id === button.dataset.id); assertObject("reading-selection", generation, scope);
      if (!item || item.available === false) return setStatus("perspectives", "This reading is unavailable and cannot be edited.", true);
      currentReading = item; $("#p6ReadingText").value = item.text; $("#p6ReadingReason").value = item.reason; sourceOptions($("#p6ReadingSource"), item.sourceRef); setStatus("perspectives", "Editing a private draft. Submit separately if you choose creator review.");
    }
  });
  $("#view-perspectives").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-p6-action]"); if (!button) return;
    const scope = scopeNow(); const { id } = button.dataset; const revision = Number(button.dataset.revision);
    if (button.dataset.p6Action === "reading-grant") createReadingGrant(id, revision, scope);
    else if (button.dataset.p6Action === "grant-approve") grantAction(button, "approve", scope);
    else if (button.dataset.p6Action === "grant-revoke") grantAction(button, "revoke", scope);
  });
  $("#p6PresentationSelect").addEventListener("change", async () => { const scope = scopeNow(); const generation = beginObject("reading-presentation-selection"); const id = $("#p6PresentationSelect").value; try { const list = await pages("p6ReadingPresentations", scope); assertObject("reading-presentation-selection", generation, scope); currentPresentation = list.find((x) => x.id === id) || null; previewCurrentReadingVersion(); } catch (error) { requestFailed("perspectives", error); } });
  for (const button of $$('[data-p6-action^="work-"]')) button.addEventListener("click", () => workAction(button.dataset.p6Action));
  for (const field of [$("#p6Activity"), $("#p6DeclaredState"), $("#p6Minutes"), $("#p6Step")]) field.addEventListener("input", () => { field.dataset.dirty = "true"; });
  $("#p6WorkSharePreviewButton").addEventListener("click", previewWorkShare);
  $("#p6WorkShareConfirm").addEventListener("click", confirmWorkShare);
  $("#p6WorkShareConsent").addEventListener("change", updateWorkShareControls);
  $("#p6WorkResult").addEventListener("input", () => {
    currentSharePreview = null;
    $("#p6WorkSharePreview").replaceChildren(node("div", "The selected text changed. Preview it again before sharing.", { class: "p6-empty" }));
    updateWorkShareControls();
  });
  $("#view-work").addEventListener("click", async (event) => {
    const button = event.target.closest('[data-p6-action="share-revoke"]'); if (!button) return;
    const scope = scopeNow(); const id = button.dataset.id; const expectedRevision = Number(button.dataset.revision);
    if (!window.confirm("Revoke this exact selected derivative?")) return;
    try {
      const result = await mutate("p6CoactivityShareRevoke", { expectedRevision }, [id], scope);
      const key = `entrelineas.p6.own-shares:${scope.sessionId}:${scope.viewerId}`;
      const shares = JSON.parse(sessionStorage.getItem(key) || "[]").map((share) => share.id === id ? { ...share, revision: result.share.revision, status: "revoked" } : share);
      sessionStorage.setItem(key, JSON.stringify(shares)); assert(scope); renderOwnShares(); setStatus("work", "This selected share has been revoked.");
    } catch (error) { requestFailed("work", error); }
  });
  $("#p6Coactivities").addEventListener("click", async (event) => { const b = event.target.closest('[data-p6-action="work-select"]'); if (!b) return; const scope = scopeNow(), generation = beginObject("coactivity-selection"), id = b.dataset.id; try { const result = await controllerConfig.api.call("p6Coactivity", null, id, { scope }); assertObject("coactivity-selection", generation, scope); fillCoactivity(result.coactivity); } catch (error) { requestFailed("work", error); } });
  $("#p6InquirySave").addEventListener("click", () => inquiryAction("save"));
  $("#p6InquiryAccept").addEventListener("click", () => inquiryAction("accept"));
  $("#p6ObservationRecord").addEventListener("click", recordObservation);
  for (const field of [$("#p6NextQuestion"), $("#p6NextReason"), $("#p6NextRefs")]) field.addEventListener("input", () => { field.dataset.dirty = "true"; });
  $("#p6InquiryPresentationCreate")?.addEventListener("click", () => saveInquiryPresentation(false));
  $("#p6InquiryPresentationVersion")?.addEventListener("click", () => saveInquiryPresentation(true));
  $("#p6InquiryPresentationApprove")?.addEventListener("click", () => inquiryPresentationAction("approve"));
  $("#p6InquiryPresentationPresent")?.addEventListener("click", () => inquiryPresentationAction("present"));
  $("#p6InquiryPresentationWithdraw")?.addEventListener("click", () => inquiryPresentationAction("withdraw"));
  $("#p6InquiryPresentationSelect")?.addEventListener("change", async () => { const scope = scopeNow(); try { const items = await pages("p6InquiryPresentations", scope); assert(scope); renderInquiryPresentations(items); previewCurrentInquiryVersion(); } catch (error) { requestFailed("inquiry", error); } });
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("#p6NextSave, #p6NextGenerate");
    if (!button) return;
    if (button.id === "p6NextSave") {
      if (!currentInquiry || currentInquiry.observationCount < 1) return setStatus("inquiry", "Record an actual observation before selecting a changed examination.", true);
      const scope = scopeNow();
      const refs = [...$("#p6NextRefs").selectedOptions].map((option) => JSON.parse(option.value));
      const body = { expectedRevision: currentInquiry.revision, observationRefs: refs, question: $("#p6NextQuestion").value, reason: $("#p6NextReason").value };
      if (!refs.length || !body.question.trim() || !body.reason.trim()) return setStatus("inquiry", "Select at least one exact observation and enter the changed question and reason.", true);
      try { const result = await mutate("p6NextExamination", body, [currentInquiry.id], scope); assert(scope); for (const field of [$("#p6NextQuestion"), $("#p6NextReason"), $("#p6NextRefs")]) delete field.dataset.dirty; currentInquiry = result.inquiry; fillInquiry(result.inquiry); setStatus("inquiry", "Creator-edited next examination selected with exact observation references."); }
      catch (error) { requestFailed("inquiry", error); }
      return;
    }
    if (!currentInquiry || currentInquiry.status !== "ready") return setStatus("inquiry", "Accept the inquiry plan before requesting a comparison proposal.", true);
    const scope = scopeNow(); const refs = [...$("#p6NextRefs").selectedOptions].map((option) => JSON.parse(option.value));
    if (!refs.length) return setStatus("inquiry", "Select at least one exact human-entered observation before requesting a proposal.", true);
    try {
      const result = await mutate("p6NextExaminationGenerate", { expectedRevision: currentInquiry.revision, observationRefs: refs }, [currentInquiry.id], scope);
      assert(scope); currentInquiry = result.inquiry;
      for (const field of [$("#p6NextQuestion"), $("#p6NextReason"), $("#p6NextRefs")]) delete field.dataset.dirty;
      fillInquiry(result.inquiry, true); setStatus("inquiry", "An editable provisional comparison proposal is available. It is not an observation or a selected examination.");
    } catch (error) { requestFailed("inquiry", error); }
  }, true);
  $("#p6InquiryList")?.addEventListener("click", async (event) => { const b = event.target.closest('[data-p6-action="inquiry-select"]'); if (!b) return; const scope = scopeNow(), generation = beginObject("inquiry-selection"), id = b.dataset.id; try { const result = await controllerConfig.api.call("p6Inquiry", null, id, { scope }); assertObject("inquiry-selection", generation, scope); for (const field of [$("#p6NextQuestion"), $("#p6NextReason"), $("#p6NextRefs")]) if (field) delete field.dataset.dirty; currentInquiry = result.inquiry; fillInquiry(result.inquiry); const obs = await pages("p6InquiryObservations", scope, [id]); assertObject("inquiry-selection", generation, scope); renderObservations(obs); renderInquiryPresentationChoices(obs); fillInquiry(currentInquiry, true); } catch (error) { requestFailed("inquiry", error); } });
  $("#p6ObservationList")?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-p6-action]"); if (!button) return;
    const scope = scopeNow(); const id = button.dataset.id; const revision = Number(button.dataset.revision);
    if (button.dataset.p6Action === "observation-grant") { await createObservationGrant(id, revision, scope); return; }
    const observation = inquiryObservationMap.get(id);
    if (!currentInquiry || !observation || observation.inquiryId !== currentInquiry.id || observation.status !== "active" || observation.revision !== revision) return setStatus("inquiry", "This exact observation is no longer active. Refresh and review its current status.", true);
    if (button.dataset.p6Action === "observation-revoke") {
      try { await mutate("p6InquiryObservationRevoke", { expectedRevision: revision }, [currentInquiry.id, id], scope); assert(scope); await loadInquiry(scope); }
      catch (error) { requestFailed("inquiry", error); }
    } else if (button.dataset.p6Action === "observation-correct") {
      currentObservationToSupersede = { id, revision };
      setStatus("inquiry", "Correction mode: the new human report will supersede this exact observation while keeping its eligible history.");
    }
  });
  $("#p6ProjectCreate").addEventListener("click", createProject);
  $("#p6OwnerMode")?.addEventListener("change", () => { currentProject = null; clearViewBodies("project"); loadProject(); });
  $("#p6OwnerForget")?.addEventListener("click", () => {
    if (!currentProject || !window.confirm("Forget this project's owner capability in this browser? The server project remains, and creator-session recovery is not available.")) return;
    sessionStorage.removeItem(`${ownerPrefix}${currentProject.id}`); localStorage.removeItem(`${ownerPrefix}${currentProject.id}`);
    currentProject = null; $("#p6OwnerMode").checked = false; clearViewBodies("project"); setStatus("project", "This browser has forgotten the project owner capability."); loadProject();
  });
  $("#p6ProjectImport")?.addEventListener("click", importProjectRef);
  $("#p6ProjectLinkCreate")?.addEventListener("click", createProjectLink);
  $("#p6ProposalPreview")?.addEventListener("click", () => { try { if (projectLoadPending || !currentProject) throw new Error("Refresh and review current authorized project state before previewing."); showProposalPreview(buildOperation()); } catch (error) { setStatus("project", error.message, true); } });
  $("#p6ProposalSubmit")?.addEventListener("click", createProposal);
  for (const action of ["accept", "apply", "reverse", "reject"]) $(`#p6Proposal${action[0].toUpperCase()}${action.slice(1)}`)?.addEventListener("click", () => ownerProposalAction(action));
  $("#p6ProposalSelect")?.addEventListener("change", () => {
    const proposal = currentProposalList.find((item) => item.id === $("#p6ProposalSelect").value);
    if (!projectLoadPending && proposal?.operation && proposal.status !== "blocked") showProposalPreview(proposal.operation);
    else clearProposalPreview("This proposal has no currently eligible preview. Refresh and review its status.");
    updateProposalControls();
  });
  const refreshProject = p6Button("Refresh authorized project state", "project-refresh");
  $("#p6ProjectTitleDisplay")?.after(refreshProject);
  $("#view-project").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-p6-action]"); if (!button) return;
    if (button.dataset.p6Action === "project-refresh") projectAction("project-refresh");
    if (button.dataset.p6Action === "link-approve") transitionLink(button, "approve");
    if (button.dataset.p6Action === "link-revoke") transitionLink(button, "revoke");
    if (button.dataset.p6Action === "owner-link-revoke") transitionLink(button, "owner-revoke");
    if (button.dataset.p6Action === "proposal-withdraw") mutate("p6ProjectProposalWithdraw", { expectedProposalRevision: Number(button.dataset.revision) }, [currentProject.id, button.dataset.id]).then(loadProject).catch((error) => requestFailed("project", error));
  });
  $("#p6ProjectImports")?.addEventListener("change", async (event) => {
    const check = event.target.closest("input[data-project-ref]"); if (!check || !currentProject) return;
    const card = check.closest("article"); const ref = JSON.parse(check.dataset.projectRef);
    if (check.checked) await resolveImportedReference(ref, card); else resolvedProjectRefs.delete(JSON.stringify(ref));
  });
  $("#p6ProjectImports")?.addEventListener("click", async (event) => {
    const button = event.target.closest('[data-p6-action="import-revoke"]'); if (!button || !currentProject) return;
    const scope = scopeNow(); if (!window.confirm("Revoke this exact destination import? Its body will no longer resolve in this project.")) return;
    try { await mutate("p6ProjectImportRevoke", { expectedRevision: Number(button.dataset.revision) }, [currentProject.id, button.dataset.id], scope); assert(scope); await loadProject(); }
    catch (error) { requestFailed("project", error); }
  });
  $("#view-project").addEventListener("input", (event) => {
    if (["p6ProjectOperation", "p6ProposalContent", "p6ProposalReason", "p6DecisionQualification", "p6NextAction", "p6ActionId"].includes(event.target.id)) {
      $("#p6AfterPreview").textContent = "Inputs changed. Preview the exact proposed operation again.";
    }
  });
  for (const button of $$('#view-project button[data-p6-action]')) button.addEventListener("click", () => projectAction(button.dataset.p6Action));
}

async function loadProject() {
  const scope = scopeNow();
  const generation = beginLoad("project");
  projectLoadPending = true;
  clearViewBodies("project");
  clearProposalPreview("Refreshing authorized project state; preview cleared until eligibility is rechecked.");
  resolvedProjectRefs.clear();
  operationDraftCache.clear();
  updateProposalControls();
  try {
    const links = role === "creator" || role === "viewer" ? await pages("p6Projects", scope) : [];
    assertLoad("project", generation, scope);
    const projectIds = new Set(links.map((x) => x.projectId));
    if (role === "creator" && $("#p6OwnerMode")?.checked) {
      for (const storage of [sessionStorage, localStorage]) for (let i = 0; i < storage.length; i++) {
        const key = storage.key(i); if (key?.startsWith(ownerPrefix) && !key.includes(":pending:")) projectIds.add(key.slice(ownerPrefix.length));
      }
    }
    const available = [];
    for (const id of projectIds) {
      try {
        const headers = projectOwnerToken(id) ? ownerHeaders(id) : null;
        const result = headers
          ? await controllerConfig.api.call("p6OwnerProject", null, id, { scope, headers })
          : await controllerConfig.api.call("p6Project", null, id, { scope });
        assertLoad("project", generation, scope); available.push(result.project);
      } catch (error) { if (error.status !== 403 && error.status !== 404) throw error; }
    }
    const picker = ensureProjectPicker();
    const selectionKey = `entrelineas.p6.project-selection:${scope.sessionId}:${scope.role}:${scope.viewerId || "creator"}`;
    const priorSelection = selectedProjectId || currentProject?.id || sessionStorage.getItem(selectionKey);
    picker.replaceChildren(node("option", "Choose an authorized project", { value: "" }));
    for (const project of available) picker.append(node("option", `${project.title} · ${project.id}`, { value: project.id }));
    selectedProjectId = available.some((project) => project.id === priorSelection) ? priorSelection : available[0]?.id || null;
    picker.value = selectedProjectId || "";
    try { if (selectedProjectId) sessionStorage.setItem(selectionKey, selectedProjectId); } catch {}
    const host = $("#p6ProjectStateTitle")?.closest(".p6-card");
    if (host) {
      const content = $("#p6ProjectState");
      if (available.length) {
        currentProject = available.find((project) => project.id === selectedProjectId) || available[0];
        currentProjectScopes = links.find((x) => x.projectId === currentProject.id)?.scopes || null;
        if (content) renderJsonState("p6ProjectState", { project: currentProject });
        if (role === "viewer") renderImports(projectRefsForViewer(currentProject));
        $("#p6ExpectedRevision").value = String(currentProject.revision);
        $("#p6ProjectTitleDisplay") && ($("#p6ProjectTitleDisplay").textContent = `${currentProject.title} · stable ID ${currentProject.id} · revision ${currentProject.revision} · named authority: project owner`);
        if (role === "creator") {
          const owner = ownerHeaders(currentProject.id);
          if (owner) {
            const [history, proposals, linksOwned] = await Promise.all([
              pages("p6OwnerProjectHistory", scope, [currentProject.id], owner),
              pages("p6OwnerProjectProposals", scope, [currentProject.id], owner),
              pages("p6ProjectLinks", scope, [currentProject.id], owner),
            ]); assertLoad("project", generation, scope); renderHistory(history); renderProposals(proposals, true); renderLinks(linksOwned, true);
            if (currentProjectScopes?.creator?.read === true) { const importItems = await pages("p6ProjectImports", scope, [currentProject.id]); assertLoad("project", generation, scope); renderImports(importItems); }
            else renderImports([]);
          }
        }
        if (!(role === "creator" && ownerHeaders(currentProject.id))) {
          if (role === "creator") { const imported = await pages("p6ProjectImports", scope, [currentProject.id]); assertLoad("project", generation, scope); renderImports(imported); }
          const sessionProposals = await pages("p6ProjectProposals", scope, [currentProject.id]); assertLoad("project", generation, scope); renderProposals(sessionProposals, false);
        }
        updateProposalControls();
        const actionSelect = $("#p6ActionId");
        actionSelect.replaceChildren(node("option", "Choose an action", { value: "" }));
        for (const action of currentProject.state?.actions || []) actionSelect.append(node("option", `${action.text} · ${action.status}`, { value: action.id, disabled: action.provenanceStatus === "invalidated" || action.status === "suspended" }));
      } else { currentProject = null; currentProjectScopes = null; if (content) content.replaceChildren(node("div", "No authorized project state is available.", { class: "p6-empty" })); renderImports([]); renderProposals([], false); $("#p6ProjectTitleDisplay").textContent = "Project identity and binding status are unavailable."; }
    }
    if (role === "creator") {
      const requests = await pages("p6ProjectLinkRequests", scope); assertLoad("project", generation, scope); renderLinks(requests);
      $("#p6ProjectCreate").disabled = false;
    }
    assertLoad("project", generation, scope);
    projectLoadPending = false;
    const selected = currentProposalList.find((item) => item.id === $("#p6ProposalSelect")?.value);
    if (selected?.operation && selected.status !== "blocked") showProposalPreview(selected.operation);
    else clearProposalPreview("No current eligible proposal preview is available. Select and review a current proposal.");
    updateProposalControls();
    setStatus("project", available.length ? "Project state refreshed through current authorized access." : "No authorized project state is available in this session.");
  } catch (error) { if (error.name !== "AbortError" && viewGeneration.get("project") === generation) { projectLoadPending = false; clearViewBodies("project"); clearProposalPreview("Current project state is unavailable; preview remains cleared."); updateProposalControls(); requestFailed("project", error); } }
}
async function createProject() {
  const title = $("#p6ProjectName").value.trim(); const question = $("#p6ProjectQuestion")?.value.trim();
  if (!title || !question) return setStatus("project", "Enter a project title and its open question.", true);
  const scope = scopeNow(); const body = { title, question };
  const auth = await withRequestId("p6ProjectCreate", body, scope);
  assertJournal(scope);
  if (mutationInFlight.has(`project-create:${auth.requestId}`)) return;
  mutationInFlight.add(`project-create:${auth.requestId}`);
  const pendingKey = `${ownerPrefix}pending:${scope.sessionId}:${auth.requestId}`;
  try {
    assertJournal(scope);
    let capability;
    try { capability = sessionStorage.getItem(pendingKey); } catch { return setStatus("project", "Session storage is unavailable; project creation was not sent.", true); }
    if (!capability) { capability = encodeCapability(); assertJournal(scope); try { sessionStorage.setItem(pendingKey, capability); } catch { return setStatus("project", "Session storage is unavailable; project creation was not sent.", true); } }
    assertJournal(scope);
    const result = await controllerConfig.api.call("p6ProjectCreate", { ...body, requestId: auth.requestId }, { scope, headers: { "X-Project-Owner": capability } });
    assertJournal(scope); currentProject = result.project;
    try { sessionStorage.setItem(`${ownerPrefix}${currentProject.id}`, capability); sessionStorage.removeItem(pendingKey); }
    catch { setStatus("project", "Project created, but this browser could not retain its owner capability. Save the capability securely before leaving; it cannot be recovered from the creator session.", true); return; }
    assertJournal(scope);
    if ($("#p6OwnerPersist")?.checked) localStorage.setItem(`${ownerPrefix}${currentProject.id}`, capability);
    $("#p6OwnerMode").checked = true;
    clearRequestJournal(scope, auth.key, auth.requestId, auth.fingerprint);
    await loadProject(); setStatus("project", `Project ${currentProject.id} created. Its owner capability uses this browser session unless you explicitly chose persistent local storage.`);
  } catch (error) {
    if (error?.code !== "request_in_progress" && error?.name !== "TypeError" && error?.status != null) { try { clearRequestJournal(scope, auth.key, auth.requestId, auth.fingerprint); } catch { /* retain unknown request on identity change */ } }
    try { assertJournal(scope); } catch { return; }
    requestFailed("project", error);
  } finally { mutationInFlight.delete(`project-create:${auth.requestId}`); }
}
function buildOperation() {
  const type = $("#p6ProjectOperation").value;
  const text = $("#p6ProposalContent").value.trim();
  const refs = selectedRefs();
  const stableInput = JSON.stringify({ type, text, refs, qualification: $("#p6DecisionQualification").value.trim(), nextAction: $("#p6NextAction").value.trim(), actionId: $("#p6ActionId").value });
  if (operationDraftCache.has(stableInput)) return operationDraftCache.get(stableInput);
  const remember = (operation) => { operationDraftCache.set(stableInput, operation); return operation; };
  if (!type) throw new Error("Choose one allowed typed operation.");
  if (["select_plan", "supersede_plan"].includes(type)) {
    if (!text) throw new Error("Enter the comparison plan text.");
    if (!refs.length) throw new Error("Select and recheck at least one eligible imported exact reference for the plan.");
    return remember({ type, planId: requestId(), text, refs });
  }
  if (type === "attach_observation") {
    const ref = refs.find((x) => x.kind === "observation");
    if (!ref) throw new Error("Select and recheck an imported observation reference.");
    return remember({ type, ref });
  }
  if (type === "record_decision") {
    const qualification = $("#p6DecisionQualification").value.trim();
    const nextAction = $("#p6NextAction").value.trim();
    if (!text || !qualification || !nextAction || !refs.length) throw new Error("A qualified decision needs text, limits, a next app action and at least one rechecked exact reference.");
    return remember({ type, decisionId: requestId(), text, qualification, refs, nextAction: { id: requestId(), text: nextAction } });
  }
  if (type === "open_action") {
    if (!text) throw new Error("Enter the next app action.");
    return remember({ type, actionId: requestId(), text, decisionId: null });
  }
  const actionId = $("#p6ActionId").value;
  if (!actionId) throw new Error("Choose an existing project action.");
  return remember({ type, actionId });
}
function showProposalPreview(operation) {
  const before = $("#p6BeforePreview"), after = $("#p6AfterPreview");
  if (projectLoadPending || !currentProject) { clearProposalPreview("Current project state is unavailable; preview remains cleared."); return false; }
  if (currentProject) {
    const state = currentProject.state || {};
    const parts = [`${currentProject.title} · project revision ${currentProject.revision}`, `Review available: ${state.reviewAvailable === true ? "yes" : "no"}`];
    if (state.selectedPlan) parts.push(state.selectedPlan.available === false || state.selectedPlan.text == null ? "Selected plan is unavailable." : `Selected plan: ${state.selectedPlan.text}`);
    for (const action of state.actions || []) parts.push(action.text == null || action.status === "suspended" ? "A source-dependent next action is suspended." : `Next action: ${action.text} (${action.status})`);
    for (const decision of state.decisions || []) parts.push(decision.text == null || decision.provenanceStatus === "invalidated" ? "A source-dependent decision is unavailable." : `Decision: ${decision.text} (${decision.provenanceStatus})`);
    before.replaceChildren(...parts.map((part) => node("p", part)));
  } else before.textContent = "Current project state unavailable.";
  let effect = "No project state has changed.";
  if (operation.type === "select_plan" || operation.type === "supersede_plan") effect = `Selected plan would become: ${operation.text}`;
  if (operation.type === "attach_observation") effect = `The project would make the exact observation reference ${operation.ref.id} available for review.`;
  if (operation.type === "record_decision") effect = `A qualified app decision would be recorded and open the next app action: ${operation.nextAction.text}`;
  if (operation.type === "open_action") effect = `An app action would be opened: ${operation.text}`;
  if (operation.type === "complete_action" || operation.type === "reopen_action") effect = `Project action ${operation.actionId} would become ${operation.type === "complete_action" ? "completed" : "open"}.`;
  after.textContent = `${effect} This is a preview only. Project state changes only after separate owner accept and apply.`;
  return true;
}
async function importProjectRef() {
  if (!currentProject) return setStatus("project", "Open an authorized project before importing a reference.", true);
  const ref = exactProjectRef();
  if (!ref) return setStatus("project", "Enter a complete exact origin reference, revision and grant ID.", true);
  try { await mutate("p6ProjectImport", { ref }, [currentProject.id]); await loadProject(); setStatus("project", "Exact reference import recorded. Its body will still be checked against current origin rights on each use."); }
  catch (error) { requestFailed("project", error); }
}
async function createProjectLink() {
  if (!currentProject || !ownerHeaders(currentProject.id)) return setStatus("project", "The project-owner capability is unavailable in this identity.", true);
  const sessionId = $("#p6DestinationSession").value.trim();
  const scopes = { creator: { read: false, propose: false, decide: false }, viewer: { read: false, propose: false } };
  for (const check of $$('[data-p6-link-scope]')) { const [actor, permission] = check.dataset.p6LinkScope.split("."); scopes[actor][permission] = check.checked; }
  if ((!scopes.creator.read && !scopes.viewer.read) || (scopes.creator.propose && !scopes.creator.read) || (scopes.creator.decide && !scopes.creator.read) || (scopes.viewer.propose && !scopes.viewer.read)) return setStatus("project", "Choose at least one read scope. Propose and decide scopes require the matching read scope.", true);
  const headers = ownerHeaders(currentProject.id);
  try { await mutate("p6ProjectLinkCreate", { sessionId, scopes }, [currentProject.id], scopeNow(), headers); await loadProject(); setStatus("project", "Link request sent for the destination creator's separate approval. It is not active until approved."); }
  catch (error) { requestFailed("project", error); }
}
async function createProposal() {
  if (!currentProject) return setStatus("project", "Open a linked project before proposing a change.", true);
  try {
    const operation = buildOperation(); showProposalPreview(operation);
    const reason = $("#p6ProposalReason").value.trim();
    if (!reason) return setStatus("project", "Enter a reason for the proposal.", true);
    if (!window.confirm("Submit this exact typed proposal? The project will not change until its named authority separately accepts and applies it.")) return;
    const result = await mutate("p6ProjectProposalCreate", { expectedProjectRevision: currentProject.revision, operation, reason }, [currentProject.id]);
    await loadProject(); setStatus("project", `Proposal ${result.proposal.id} created. Status is proposed; project state has not been applied.`);
  } catch (error) { requestFailed("project", error); }
}
async function ownerProposalAction(action) {
  if (!currentProject) return setStatus("project", "Choose an owner-authorized project first.", true);
  const headers = ownerHeaders(currentProject.id);
  if (!headers) return setStatus("project", "Project-owner authority is unavailable. Session creator access cannot replace it.", true);
  const proposalId = $("#p6ProposalSelect").value;
  if (!proposalId) return setStatus("project", "Choose a proposal first.", true);
  const reason = $("#p6ProposalReason").value.trim();
  if (!reason) return setStatus("project", "Enter the authority reason for this transition.", true);
  if (!window.confirm(`Confirm ${action} for this exact proposal and current project revision?`)) return;
  try {
    const scope = scopeNow();
    const proposalList = await pages("p6OwnerProjectProposals", scope, [currentProject.id], headers);
    const proposal = proposalList.find((x) => x.id === proposalId);
    if (!proposal) return setStatus("project", "This proposal is unavailable. Refresh before deciding.", true);
    const body = { expectedProjectRevision: currentProject.revision, expectedProposalRevision: proposal.revision, reason };
    const result = await mutate("p6OwnerProposalAction", body, [currentProject.id, proposalId, action], scope, headers);
    currentProject = result.project; await loadProject(); setStatus("project", `Proposal ${action} recorded. ${action === "apply" ? "The project state and available app action were refreshed." : "Acceptance, application and reversal remain separate history events."}`);
  } catch (error) { requestFailed("project", error); }
}
async function transitionLink(button, action) {
  const id = button.dataset.id, revision = Number(button.dataset.revision);
  try {
    if (action === "approve" || action === "revoke") await mutate(action === "approve" ? "p6ProjectLinkApprove" : "p6ProjectLinkRevoke", { expectedRevision: revision }, [id]);
    else if (action === "owner-revoke") {
      if (!currentProject || !ownerHeaders(currentProject.id)) throw new Error("Project-owner authority is unavailable.");
      await mutate("p6ProjectLinkRevokeOwner", { expectedRevision: revision }, [currentProject.id, id], scopeNow(), ownerHeaders(currentProject.id));
    }
    await loadProject(); setStatus("project", `Session link ${action}d. Access is checked against the current link state.`);
  } catch (error) { requestFailed("project", error); }
}
async function projectAction(action) {
  if (!currentProject) return setStatus("project", "Create a project or open an authorized linked project first.", true);
  if (action === "project-refresh") return loadProject();
  if (action === "project-propose") return createProposal();
  if (action === "project-import") return importProjectRef();
  if (action === "project-link-create") return createProjectLink();
  if (["accept", "apply", "reverse", "reject"].includes(action)) return ownerProposalAction(action);
  setStatus("project", "This project action is not available in the current screen state.", true);
}

export function createPhase6Controller(config) {
  controllerConfig = { ...config, initialized: false };
  return {
    setRole: applyRole,
    reset() {
      role = null; currentReading = null; currentCoactivity = null; currentInquiry = null; currentProject = null; currentProjectScopes = null; projectLoadPending = false; selectedProjectId = null; currentPresentation = null; currentInquiryPresentation = null; currentSharePreview = null; currentObservationToSupersede = null; activeOwnShare = null; submittedReadingMap.clear(); resolvedProjectRefs.clear(); currentProposalList = [];
      for (const view of phase6Views) { viewGeneration.set(view, (viewGeneration.get(view) || 0) + 1); clearViewBodies(view); }
      for (const input of $$('[data-p6-input]')) { if (input.type === "checkbox") input.checked = false; else input.value = ""; }
      for (const input of $$('[data-p6-consent]')) input.checked = false;
      for (const id of ["p6ReadingSource", "p6WorkSource", "p6InquirySource", "p6ObservationSource"]) {
        const select = $(`#${id}`); if (select) { select.replaceChildren(node("option", "No eligible source is available", { value: "" })); select.disabled = true; }
      }
      for (const id of ["p6GroupSelection", "p6NextRefs"]) { const select = $(`#${id}`); if (select) select.replaceChildren(); }
      for (const [id, label] of [["p6PresentationSelect", "Choose a presentation"], ["p6InquiryPresentationSelect", "Choose a presentation"], ["p6ProposalSelect", "Choose a proposal"], ["p6ActionId", "Choose an action"], ["p6ProjectChoice", "Choose an authorized project"]]) {
        const select = $(`#${id}`); if (select) select.replaceChildren(node("option", label, { value: "" }));
      }
      for (const input of [$("#p6NextQuestion"), $("#p6NextReason"), $("#p6NextRefs")]) if (input) { input.value = ""; delete input.dataset.dirty; }
      if ($("#p6NextRefs")) $("#p6NextRefs").disabled = true;
      for (const host of $$('[data-p6-status]')) host.textContent = "Unavailable for this identity. No new information has been loaded.";
      for (const nav of $$('[data-phase6-view][data-view]')) nav.hidden = true;
      for (const view of $$('.p6-view[data-phase6-view]')) { view.hidden = true; view.classList.remove("active"); }
      for (const panel of $$('[data-p6-role]')) panel.hidden = true;
      for (const button of $$('.p6-view button')) button.disabled = true;
    },
    async load(view) {
      if (role !== "viewer" && role !== "creator") return;
      if (view === "perspectives") await loadPerspectives();
      else if (view === "work") await loadWork();
      else if (view === "inquiry" && role === "creator") await loadInquiry();
      else if (view === "project") await loadProject();
    },
  };
}
