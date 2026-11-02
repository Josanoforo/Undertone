// P12 private-candidate wire client; injectable transport, no implicit requests or retry.
const ID = /^[A-Za-z0-9._:-]{1,128}$/;
const lang = x => x === 'es' || x === 'en';
const clone = x => structuredClone(x);
export const refKey = r => JSON.stringify([r.sessionId,r.sourceId,r.sourceRevision,r.momentId,r.startMs,r.endMs]);
export function validRef(r) { return r && Object.keys(r).sort().join(',') === 'endMs,momentId,sessionId,sourceId,sourceRevision,startMs' &&
  ['sessionId','sourceId','momentId'].every(k => typeof r[k] === 'string' && r[k].length > 0) && Number.isSafeInteger(r.sourceRevision) && r.sourceRevision > 0 && Number.isSafeInteger(r.startMs) && Number.isSafeInteger(r.endMs) && r.startMs >= 0 && r.endMs > r.startMs; }
export class WireError extends Error { constructor(code) { super(code); this.code = code; } }
export function createWire({ transport, currentScope }) {
  if (typeof transport !== 'function' || typeof currentScope !== 'function') throw new TypeError('ports required');
  // scope includes opaque identity, session, role, credential epoch, bearer; token remains only in memory.
  const capture = () => { const s = currentScope(); if (!s?.identity || !s?.sessionId || !s?.bearer || !s?.credentialEpoch) throw new WireError('identity_unavailable'); return { ...s }; };
  const same = s => { const n = currentScope(); return !!n && n.identity === s.identity && n.sessionId === s.sessionId && n.credentialEpoch === s.credentialEpoch && n.role === s.role && n.bearer === s.bearer; };
  const guard = s => { if (!same(s)) throw new WireError('stale_identity'); };
  async function call(s, suffix, method = 'GET', body, signal, binary = false) {
    guard(s);
    let response;
    try { response = await transport(`/api/sessions/${encodeURIComponent(s.sessionId)}/p12/${suffix}`, { method, headers: { Authorization: `Bearer ${s.bearer}`, ...(body === undefined ? {} : {'Content-Type':'application/json'}) }, ...(body === undefined ? {} : {body:JSON.stringify(body)}), signal }); }
    catch { guard(s); throw new WireError('transport_unknown'); }
    guard(s);
    if (!response.ok) { let code = `http_${response.status}`; try { const data = await response.json(); guard(s); if (typeof data?.error?.code === 'string') code = data.error.code; } catch (e) { if (e instanceof WireError) throw e; } throw new WireError(code); }
    if (binary) return response;
    const value = await response.json(); guard(s); return { status: response.status, value };
  }
  const opPath = id => { if (!ID.test(id)) throw new WireError('invalid_request'); return `operations/${encodeURIComponent(id)}`; };
  return { capture, same, guard,
    capabilities: s => call(s,'capabilities'),
    originalAudio: (s,sourceId,signal) => call(s,`sources/${encodeURIComponent(sourceId)}/original-audio`,'GET',undefined,signal,true),
    feed: (s,after=0) => call(s,`caption-feed?after=${after}&limit=50`),
    receipts: (s,after=0) => call(s,`operations?after=${after}&limit=50`),
    preferences: s => { if (s.role !== 'viewer') throw new WireError('viewer_only'); return call(s,'preferences'); },
    savePreferences: (s, p) => { if (s.role !== 'viewer') throw new WireError('viewer_only'); if (!lang(p.language) || typeof p.showOriginal !== 'boolean') throw new WireError('invalid_request'); return call(s,'preferences','POST',{language:p.language,showOriginal:p.showOriginal}); },
    translation(s, p, signal) { if (!ID.test(p.requestId) || !validRef(p.ref) || p.ref.sessionId !== s.sessionId || !lang(p.sourceLanguage) || !lang(p.targetLanguage) || p.sourceLanguage === p.targetLanguage || !Array.isArray(p.glossary) || p.glossary.length > 50 || p.glossary.some(x => !x || Object.keys(x).sort().join(',') !== 'source,target' || !['source','target'].every(k => typeof x[k] === 'string' && x[k].length >= 1 && x[k].length <= 120))) throw new WireError('invalid_request');
      return call(s,'translations','POST',clone(p),signal); },
    correction(s, parent, p, signal) { if (!ID.test(parent) || !ID.test(p.requestId) || Object.keys(p).sort().join(',') !== 'requestId,text' || typeof p.text !== 'string' || !p.text.trim() || p.text.length > 12000) throw new WireError('invalid_request'); return call(s,`${opPath(parent)}/corrections`,'POST',clone(p),signal); },
    speech(s, p, signal) { if (!ID.test(p.requestId) || !ID.test(p.translationRequestId) || !['requestId,translationRequestId','engine,requestId,translationRequestId','engine,requestId,translationRequestId,voice'].includes(Object.keys(p).sort().join(',')) || (p.engine && !['sapi','local_neural','elevenlabs'].includes(p.engine)) || (p.engine==='elevenlabs' && typeof p.voice!=='string')) throw new WireError('invalid_request'); return call(s,'speech','POST',clone(p),signal); },
    operation: (s,id,signal) => call(s,opPath(id),'GET',undefined,signal),
    cancel: (s,id) => call(s,`${opPath(id)}/cancel`,'POST',{}),
    audio: (s,id,signal) => call(s,`${opPath(id)}/audio`,'GET',undefined,signal,true)
  };
}
