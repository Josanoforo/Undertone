/** Wave 29.1 connected controller. The host supplies the existing authenticated API.call. */
import { mount as mountOperatingView } from './waves29-operating-view.js';
import { mount as mountOperatingPresets } from './waves29-operating-presets.js';

const SCOPE_KEYS = ['actorId','sessionId','role','scopeGeneration','sourceId','sourceRevision','rightsGeneration'];
const atom = v => (typeof v === 'string' && v.length > 0) || (typeof v === 'number' && Number.isSafeInteger(v) && v >= 0);
const validScope = s => !!s && ['audience','operator'].includes(s.role) && SCOPE_KEYS.filter(k => k !== 'role').every(k => atom(s[k]));
const sameScope = (a,b) => validScope(a) && validScope(b) && SCOPE_KEYS.every(k => a[k] === b[k]);
const REF_KEYS = ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'];
const sameRef = (a,b) => !!a && !!b && REF_KEYS.every(k => a[k] === b[k]);

/** Accept only the published operating DTO (or its documented `operating` envelope). */
export function normalizeOperatingDTO(value, scope) {
  const dto = value?.operating ?? value;
  const states = {
    stage: new Set(['waiting','running','ready','failed','unavailable','unknown']),
    // These are the states currently emitted by server.waves29_operating_status.project.
    queue: new Set(['empty','processing_waiting','processing','ready','failed','unknown']),
    admission: new Set(['admitted','waiting','unavailable','failed','unknown']),
    effect: new Set(['none','known_failure','unknown']),
    receipt: new Set(['none','ready','running','failed','unknown','unavailable'])
  };
  const detailLabels = new Set(['Source check','Preparation','Admission','Processing']);
  const text = (v, max) => typeof v === 'string' && v.length > 0 && v.length <= max;
  if (!dto || !sameScope(dto.scope, scope) || dto.access !== 'current' ||
      !Array.isArray(dto.stages) || !dto.queue || !states.queue.has(dto.queue.state) ||
      !dto.admission || !states.admission.has(dto.admission.state) || !states.effect.has(dto.effect) ||
      !dto.receipt || !states.receipt.has(dto.receipt.state) ||
      typeof dto.receipt.canRead !== 'boolean' || typeof dto.receipt.canResume !== 'boolean' ||
      (dto.receipt.canRead && (!text(dto.receipt.receiptId, 160))) ||
      !dto.source || !text(dto.source.label, 120) || typeof dto.source.available !== 'boolean' ||
      !Array.isArray(dto.profiles)) return null;
  const stages = [];
  for (const stage of dto.stages) {
    if (!stage || !text(stage.label, 120) || !states.stage.has(stage.state)) return null;
    stages.push({label: stage.label, state: stage.state,
      ...(Number.isSafeInteger(stage.elapsedMs) && stage.elapsedMs >= 0 ? {elapsedMs: stage.elapsedMs} : {})});
  }
  const profiles = [];
  for (const profile of dto.profiles) {
    if (!profile || !text(profile.profileId, 160) || !Number.isSafeInteger(profile.revision) ||
        profile.revision < 0 || !text(profile.label, 80) || typeof profile.approved !== 'boolean' ||
        typeof profile.supported !== 'boolean') return null;
    profiles.push({profileId: profile.profileId, revision: profile.revision, label: profile.label,
      approved: profile.approved, supported: profile.supported});
  }
  const queue = {state: dto.queue.state};
  for (const key of ['position','total']) if (Number.isSafeInteger(dto.queue[key]) && dto.queue[key] >= 0) queue[key] = dto.queue[key];
  const operatorDetails = {stageTimings: []};
  if (scope.role === 'operator' && Array.isArray(dto.operatorDetails?.stageTimings)) {
    for (const detail of dto.operatorDetails.stageTimings.slice(0, 12)) {
      if (detail && detailLabels.has(detail.label) &&
          (detail.elapsedMs === null || (Number.isSafeInteger(detail.elapsedMs) && detail.elapsedMs >= 0))) {
        operatorDetails.stageTimings.push({label: detail.label, elapsedMs: detail.elapsedMs});
      }
    }
  }
  return {scope: {...dto.scope}, access: dto.access, stages, queue,
    admission: {state: dto.admission.state}, effect: dto.effect,
    receipt: {state: dto.receipt.state, canRead: dto.receipt.canRead, canResume: dto.receipt.canResume,
      ...(text(dto.receipt.receiptId, 160) ? {receiptId: dto.receipt.receiptId} : {})},
    source: {label: dto.source.label, available: dto.source.available}, profiles,
    ...(operatorDetails.stageTimings.length ? {operatorDetails} : {})};
}

/**
 * Host contract: scope is the captured current identity/source scope; assertScope(scope)
 * throws when it is stale; request is the caller's existing authenticated API.call wrapper;
 * statusOperation is the actual operation key registered by the host for M02's read-only
 * projection. Optional existing callbacks may be supplied for receipt/profile/source actions.
 * No transport, identity, token, storage, request ID, or player is created here.
 */
export function mountOperatingConnected(root, initialHost = {}) {
  let host = initialHost, destroyed = false, epoch = 0, view = null, presetsView = null;
  const current = captured => {
    if (destroyed || !sameScope(captured, host?.scope) || typeof host?.assertScope !== 'function') throw Error('stale operating scope');
    host.assertScope(captured);
  };
  const request = (...args) => {
    if (typeof host?.request !== 'function') throw Error('Authenticated request binding unavailable');
    return host.request(...args);
  };
  const authorize = (scope, action, target) => {
    try {
      current(scope);
      return typeof host?.authorize === 'function' && host.authorize(scope, action, target) === true;
    } catch { return false; }
  };
  const connectedHost = () => {
    const scope = host?.scope;
    return {
      scope,
      snapshot: normalizeOperatingDTO(host?.snapshot, scope),
      isCurrent: s => { try { current(s); return true; } catch { return false; } },
      authorize,
      readReceipt: async (receiptId, captured) => {
        current(captured);
        if (typeof host?.readReceipt !== 'function') throw Error('Existing exact receipt read is not bound');
        const result = await host.readReceipt(receiptId, captured);
        current(captured);
        return normalizeOperatingDTO(result, captured);
      },
      ...(typeof host?.playPreparedAudio === 'function' ? {playPreparedAudio: async (receiptId, captured) => {
        current(captured);
        if (receiptId !== host?.snapshot?.receipt?.receiptId || host?.snapshot?.receipt?.state !== 'ready') throw Error('Prepared audio receipt changed');
        const result = await host.playPreparedAudio(receiptId, captured);
        current(captured);
        return result;
      }} : {}),
      ...(typeof host?.resumeExisting === 'function' ? {resume: async captured => {
        current(captured); const value = await host.resumeExisting(captured); current(captured);
        return normalizeOperatingDTO(value, captured);
      }} : {}),
      ...(typeof host?.selectExistingProfile === 'function' ? {chooseProfile: async (profile, captured) => {
        current(captured); const value = await host.selectExistingProfile(profile, captured); current(captured);
        return normalizeOperatingDTO(value, captured);
      }} : {}),
      ...(typeof host?.inspectCurrentSource === 'function' ? {inspectSource: (source, captured) => {
        current(captured); host.inspectCurrentSource(source, captured); current(captured);
      }} : {})
    };
  };
  const connectedPresetsHost = () => {
    const scope = host?.scope, ref = host?.ref;
    const invoke = async (name, ...args) => {
      current(scope);
      if (scope?.role !== 'operator' || !sameRef(ref, host?.ref) || typeof host?.[name] !== 'function') throw Error('Authenticated preset action is not bound');
      const value = await host[name](...args, scope);
      current(scope);
      if (!sameRef(ref, host?.ref)) throw Error('Preset source changed');
      return value;
    };
    return {
      scope, ref,
      assertScope: captured => { current(captured); return true; },
      ...(typeof host?.listQualityPresets === 'function' ? {listQualityPresets: (exactRef, captured) => {
        current(captured);
        if (!sameRef(exactRef, ref)) throw Error('Preset source changed');
        return invoke('listQualityPresets', exactRef);
      }} : {}),
      ...(typeof host?.chooseQualityPreset === 'function' ? {chooseQualityPreset: (body, captured) => {
        current(captured);
        if (!sameRef(body?.ref, ref)) throw Error('Preset source changed');
        return invoke('chooseQualityPreset', body);
      }} : {}),
      ...(typeof host?.readQualityReceipt === 'function' ? {readQualityReceipt: (requestId, captured) => invoke('readQualityReceipt', requestId)} : {}),
      ...(typeof host?.createRequestId === 'function' ? {createRequestId: host.createRequestId} : {}),
      refreshOperatingStatus: async captured => {
        current(captured); await refresh(); current(captured); return host?.snapshot;
      }
    };
  };
  if (!validScope(host?.scope) || typeof host?.assertScope !== 'function' || typeof host?.request !== 'function') {
    throw new TypeError('Current scope, assertScope and authenticated request are required');
  }
  view = mountOperatingView(root, connectedHost());
  presetsView = mountOperatingPresets(root, connectedPresetsHost());
  async function refresh() {
    const ticket = ++epoch, captured = {...host.scope}, operation = host.statusOperation;
    current(captured);
    if (typeof operation !== 'string' || !operation) throw new Error('Read-only operating status operation is not bound');
    const result = await request(operation, null, {scope: captured});
    current(captured);
    if (destroyed || ticket !== epoch || !sameScope(captured, host.scope)) return false;
    const snapshot = normalizeOperatingDTO(result, captured);
    if (!snapshot) throw new Error('Operating status projection is unavailable or stale');
    host = {...host, snapshot};
    view.update(connectedHost());
    return true;
  }
  function update(next = {}) {
    if (destroyed) return;
    const nextScope = next.scope ?? host?.scope;
    const changed = !sameScope(host?.scope, nextScope);
    epoch++; host = {...host, ...next, scope: nextScope};
    if (changed) host = {...host, snapshot: null};
    view.update(connectedHost());
    presetsView?.update(connectedPresetsHost());
  }
  function reset() { if (destroyed) return; epoch++; host = {...host, snapshot:null}; view.reset(); presetsView?.reset(); }
  function destroy() { if (destroyed) return; destroyed = true; epoch++; view.destroy(); presetsView?.destroy(); view = null; presetsView = null; host = null; }
  return {refresh, update, reset, destroy};
}
