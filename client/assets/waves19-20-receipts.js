// Durable metadata only: bodies and credentials never enter browser storage.
export function createReceiptJournal(feature, api, assertIdentity) {
  const fields = ['operation','requestId','fingerprint','target','revision'];
  const digest = async value => {
    if (!globalThis.crypto?.subtle || !globalThis.crypto?.randomUUID) throw Error('secure recovery unavailable');
    const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
    return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2,'0')).join('');
  };
  async function context(scope) {
    assertIdentity(scope);
    if (!scope?.token || !scope.sessionId || !scope.actorBinding || !scope.role) throw Error('identity unavailable');
    if (scope.role === 'viewer' && !scope.viewerId) throw Error('identity unavailable');
    const actor = await digest(JSON.stringify([scope.sessionId, scope.role, scope.viewerId || null]));
    const binding = await digest(scope.actorBinding);
    assertIdentity(scope);
    return {key:`waves19-20-recovery:${feature}:${actor}`, binding};
  }
  function read(key) {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const entry = JSON.parse(raw);
    if (!entry || entry.version !== 1 || fields.some(f => !(f in entry)) || typeof entry.requestId !== 'string' || !/^[a-f0-9]{64}$/.test(entry.fingerprint)) throw Error('recovery journal unreadable');
    return entry;
  }
  function save(key, entry) {
    const value = JSON.stringify(entry);
    localStorage.setItem(key, value);
    if (localStorage.getItem(key) !== value) throw Error('recovery journal unavailable');
  }
  async function locked(scope, action) {
    const {key,binding} = await context(scope);
    if (!globalThis.navigator?.locks?.request) throw Error('recovery lock unavailable');
    return navigator.locks.request(key, async () => { assertIdentity(scope); return action(key,binding); });
  }
  function matches(a,b) { return fields.every(f => a[f] === b[f]); }
  function owned(entry,binding) { if (entry && entry.binding !== binding) throw Error('original identity required'); return entry; }
  async function pending(scope) { return locked(scope, (key,binding) => owned(read(key),binding)); }
  async function lookup(scope, validate = () => {}, definitive = () => true) {
    return locked(scope, async (key,binding) => {
      validate(); const entry = owned(read(key),binding); if (!entry) return {status:'none'};
      const query = Object.fromEntries(fields.map(f => [f,entry[f]]));
      const receipt = await api.call('w19_20Receipt', query, {scope});
      assertIdentity(scope); validate();
      if (!receipt || !matches(entry,receipt)) return {status:'pending'};
      if ((receipt.status !== 'committed' && !(receipt.status === 'rejected' && receipt.noncommit === true)) || !definitive(receipt)) return {status:'pending'};
      localStorage.removeItem(key);
      if (localStorage.getItem(key) !== null) throw Error('recovery journal unavailable');
      return receipt;
    });
  }
  async function mutate(scope, operation, payload, target, revision, send, replay = false, validate = () => {}) {
    return locked(scope, async (key,binding) => {
      validate(); let entry = owned(read(key),binding), body;
      if (entry) {
        if (!replay || api.isReceiptReplaySafe?.(operation) !== true || entry.operation !== operation || entry.target !== target || entry.revision !== revision) throw Error('unresolved action');
        body = {requestId:entry.requestId,...payload};
        if (await digest(JSON.stringify(body)) !== entry.fingerprint) throw Error('recovery body differs');
      } else {
        if (replay) throw Error('no unresolved action');
        body = {requestId:crypto.randomUUID(),...payload};
        entry = {version:1,binding,operation,requestId:body.requestId,fingerprint:await digest(JSON.stringify(body)),target,revision};
        assertIdentity(scope); validate();
        save(key,entry);
      }
      assertIdentity(scope); validate();
      const result = await send(body);
      assertIdentity(scope); validate();
      // A completed authenticated mutation response is definitive for this same request.
      localStorage.removeItem(key);
      if (localStorage.getItem(key) !== null) throw Error('recovery journal unavailable');
      return result;
    });
  }
  return {pending, lookup, mutate};
}
