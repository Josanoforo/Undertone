// Tab-scoped ciphertext-only recovery. The host owns authorization and lifecycle.
const PREFIX = 'entrelineas.w22.protected.v1:';
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', {fatal:true});
const id = value => typeof value === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(value);
const revision = value => Number.isSafeInteger(value) && value >= 0;
const hex = bytes => Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2,'0')).join('');

function validPending(meta, body, draftId) {
  if (!meta || !body || !['patch','approve','withdraw'].includes(meta.kind) || meta.draftId !== draftId || !id(meta.requestId) || !revision(meta.revision) || body.requestId !== meta.requestId) return false;
  if (meta.kind !== 'patch') return Object.keys(body).sort().join(',') === 'expectedRevision,requestId' && body.expectedRevision === meta.revision;
  if (Object.keys(body).sort().join(',') !== 'baseRevision,operations,requestId' || body.baseRevision !== meta.revision || !Array.isArray(body.operations) || body.operations.length < 1 || body.operations.length > 2) return false;
  const fields = new Set();
  return body.operations.every(op => op && Object.keys(op).sort().join(',') === 'field,value' && ['title','body'].includes(op.field) && !fields.has(op.field) && (fields.add(op.field), true) && typeof op.value === 'string' && op.value.length <= (op.field === 'title' ? 200 : 12000));
}

/**
 * scope: {sessionId, actorId, role, draftId, token}; token is memory only.
 * isCurrent(): true only while explicit opt-in, current verified identity AND
 * this exact view generation remain alive. Host must open the current authorized
 * draft before constructing/loading this adapter and again before display.
 */
export function createProtectedCoeditJournal({scope, isCurrent, storage: suppliedStorage, cryptoProvider = globalThis.crypto} = {}) {
  const captured = scope && {...scope};
  let destroyed = false, storage;
  function guard() {
    if (destroyed || typeof isCurrent !== 'function' || isCurrent() !== true || !captured || !id(captured.sessionId) || !id(captured.actorId) || !id(captured.draftId) || !['creator','collaborator'].includes(captured.role) || typeof captured.token !== 'string' || !captured.token || !cryptoProvider?.subtle || typeof cryptoProvider.getRandomValues !== 'function') throw Error('Protected recovery unavailable');
    storage = suppliedStorage === undefined ? globalThis.sessionStorage : suppliedStorage;
    if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function' || typeof storage.removeItem !== 'function') throw Error('Protected recovery unavailable');
  }
  const context = () => JSON.stringify(['w22-protected',1,captured.sessionId,captured.actorId,captured.role,captured.draftId]);
  async function keyName() {
    guard(); const result = await cryptoProvider.subtle.digest('SHA-256',encoder.encode(context())); guard(); return PREFIX + hex(result);
  }
  async function key() {
    guard(); const raw = await cryptoProvider.subtle.digest('SHA-256',encoder.encode(JSON.stringify([context(),captured.token]))); guard();
    const result = await cryptoProvider.subtle.importKey('raw',raw,{name:'AES-GCM'},false,['encrypt','decrypt']); guard(); return result;
  }
  async function decode(raw) {
    guard(); const envelope = JSON.parse(raw);
    if (!envelope || envelope.v !== 1 || !Array.isArray(envelope.iv) || envelope.iv.length !== 12 || !Array.isArray(envelope.cipher) || envelope.cipher.length < 16 || envelope.cipher.length > 100000 || ![...envelope.iv,...envelope.cipher].every(x => Number.isInteger(x) && x >= 0 && x <= 255)) throw Error('Invalid protected recovery');
    const k = await key(); guard();
    const bytes = await cryptoProvider.subtle.decrypt({name:'AES-GCM',iv:new Uint8Array(envelope.iv),additionalData:encoder.encode(context())},k,new Uint8Array(envelope.cipher)); guard();
    const saved = JSON.parse(decoder.decode(bytes));
    if (!saved || !validPending(saved.meta,saved.body,captured.draftId)) throw Error('Invalid protected recovery');
    return saved;
  }
  async function load() {
    const name = await keyName(); guard(); const raw = storage.getItem(name); guard();
    if (raw === null) return null;
    const saved = await decode(raw); guard();
    if (storage.getItem(name) !== raw) throw Error('Recovery record changed'); guard(); return saved;
  }
  async function savePending(meta, body) {
    guard(); if (!validPending(meta,body,captured.draftId)) throw Error('Invalid pending request');
    // Snapshot before any await, so a caller cannot change the encrypted request.
    const pending = JSON.parse(JSON.stringify({meta,body}));
    const name = await keyName(); guard(); if (storage.getItem(name) !== null) throw Error('Prior operation pending'); guard();
    const k = await key(); guard(); const iv = cryptoProvider.getRandomValues(new Uint8Array(12)); guard();
    const cipher = await cryptoProvider.subtle.encrypt({name:'AES-GCM',iv,additionalData:encoder.encode(context())},k,encoder.encode(JSON.stringify(pending))); guard();
    const envelope = JSON.stringify({v:1,iv:Array.from(iv),cipher:Array.from(new Uint8Array(cipher))});
    // The check and write are synchronous within this tab, after all awaits.
    if (storage.getItem(name) !== null) throw Error('Prior operation pending'); guard(); storage.setItem(name,envelope); guard();
  }
  async function clearConfirmed(expected, receipt) {
    const name = await keyName(); guard(); const raw = storage.getItem(name); guard(); if (raw === null) throw Error('Recovery record missing');
    const saved = await decode(raw); guard(); const m = saved.meta, op = receipt?.operation;
    if (!expected || expected.requestId !== m.requestId || expected.kind !== m.kind || expected.draftId !== m.draftId || expected.revision !== m.revision || !op || op.action !== m.kind || !['committed','conflict'].includes(op.state)) throw Error('Receipt mismatch');
    if (m.kind === 'patch' ? (op.state === 'conflict' ? op.baseRevision !== m.revision : op.revision !== m.revision + 1) : (op.state !== 'committed' || op.revision !== m.revision)) throw Error('Receipt revision mismatch');
    guard(); if (storage.getItem(name) !== raw) throw Error('Recovery record changed'); guard(); storage.removeItem(name); guard();
  }
  return {available:() => { try { guard(); return true; } catch { return false; } }, currentScope:() => { guard(); return {sessionId:captured.sessionId,actorId:captured.actorId,role:captured.role,draftId:captured.draftId}; }, load, savePending, clearConfirmed, destroy:() => { destroyed = true; }};
}
