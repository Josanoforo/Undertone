/* B28.1: adapter for the existing handoff component and authenticated host. */
import { mount as mountHandoff } from './waves28-handoff.js';

const fields = ['scopeId','sessionId','actorId','role','creatorId','collaboratorId','collaborationId','sourceId','sourceRevision','draftId','revision','grantGeneration','eligible'];
const snapshot = s => Object.fromEntries(fields.map(k => [k, s?.[k] ?? null]));
const same = (a,b) => fields.every(k => a[k] === b[k]);
const stale = () => Object.assign(new Error('Current handoff access changed'), {rightsLost:true});
// A change of revision or grant must not conceal an unconfirmed request.
const journalKey = s => JSON.stringify(['handoff28',s.sessionId,s.actorId,s.draftId]);

export function mount(root, host) {
  let dead = false, epoch = 0, bound;
  function context(scope) {
    const s = snapshot(scope), ticket = epoch, key = journalKey(s);
    function guard(action) {
      if (dead || ticket !== epoch || !s.eligible || !same(s, snapshot(host.getScope())) || host.isCurrent(s, action) !== true) throw stale();
    }
    const journal = host.intentJournal;
    const protectedJournal = {
      read() { guard('journal'); if (!host.savedAccess || !journal || typeof journal.read !== 'function') throw stale(); return journal.read(key); },
      write(_ignored, value) { guard('journal'); if (!host.savedAccess || !journal || typeof journal.write !== 'function') throw stale(); return journal.write(key,value); },
      remove() { guard('journal'); if (!host.savedAccess || !journal || typeof journal.remove !== 'function') throw stale(); return journal.remove(key); }
    };
    async function request(action, suffix, method, body) {
      guard(action);
      const path = `/api/sessions/${encodeURIComponent(s.sessionId)}/w28/handoffs/${encodeURIComponent(s.draftId)}${suffix}`;
      try {
        const result = await host.request(path, {method, ...(body ? {body} : {})}, s);
        guard(action);
        return result;
      } catch (error) { guard(action); throw error; }
    }
    return {...s, intentJournal:protectedJournal,
      newRequestId() { guard('decide'); return host.newRequestId(); },
      currentReasonRefs() { guard('decide'); return host.currentReasonRefs(s); },
      viewHandoff() { return request('read','', 'GET'); },
      offerHandoff({draftId, ...body}) {
        if (draftId !== s.draftId || body.expectedRevision !== s.revision || s.actorId !== s.creatorId) throw stale();
        return request('offer','/offer','POST',body);
      },
      decideHandoff({draftId, ...body}) {
        if (draftId !== s.draftId || body.expectedRevision !== s.revision || !['accept','return','complete'].includes(body.action)) throw stale();
        return request(body.action,'/decide','POST',body);
      },
      readHandoffReceipt({draftId,requestId}) {
        if (draftId !== s.draftId || !requestId) throw stale();
        return request('receipt',`/receipts/${encodeURIComponent(requestId)}`,'GET');
      }
    };
  }
  bound = mountHandoff(root, context(host.getScope()));
  return {
    reset() { if (dead) return; epoch++; bound.destroy(); bound = mountHandoff(root, context(host.getScope())); },
    destroy() { if (dead) return; dead = true; epoch++; bound.destroy(); }
  };
}
export function reset(controller) { controller.reset(); }
export function destroy(controller) { controller.destroy(); }
