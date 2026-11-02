// Selected flag sharing: durable intent, real current identity, GET-only recovery.
export function createFlagSharingHost({getOwner, isCurrent, assertIdentity, sameRef, call,
  storage = globalThis.localStorage, locks = globalThis.navigator?.locks}) {
  const id = value => typeof value === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(value);
  const unknown = () => Object.assign(new Error('Check the original share receipt.'), {outcome:'unknown'});
  function ownerFor(candidate) {
    const owner = getOwner(), scope = owner?.scope;
    if (!owner || !isCurrent(candidate) || scope?.role !== 'viewer' || !scope.viewerId || !scope.actorBinding || !scope.sessionId || !sameRef(candidate.ref, owner.ref)) throw Error('Current saved viewer required');
    assertIdentity(scope);
    return owner;
  }
  const keyFor = owner => `entrelineas.w26.flag-share.v1:${owner.scope.sessionId}:${owner.scope.actorBinding}`;
  function read(owner) {
    const raw = storage.getItem(keyFor(owner));
    if (raw === null) return null;
    const marker = JSON.parse(raw);
    if (marker?.version !== 1 || !marker.ref || !id(marker.selection?.requestId) || !id(marker.selection.flagId) || !Number.isInteger(marker.selection.flagRevision) || marker.selection.flagRevision < 1 || marker.selection.targetSessionId !== owner.scope.sessionId || marker.selection.consent !== true || !['pending','complete','revoking','unavailable'].includes(marker.state) || (['complete','revoking'].includes(marker.state) && !id(marker.shareId))) throw unknown();
    return marker;
  }
  async function current(owner, candidate) {
    if (getOwner() !== owner) throw Error('Selection changed');
    ownerFor(candidate);
    await owner.current();
    if (getOwner() !== owner) throw Error('Selection changed');
    ownerFor(candidate);
  }
  async function locked(candidate, operation, requireSource = true) {
    const owner = ownerFor(candidate);
    if (typeof locks?.request !== 'function') throw Error('Safe recovery unavailable');
    return locks.request(keyFor(owner), async () => {
      if (requireSource) await current(owner, candidate);
      else if (getOwner() !== owner || ownerFor(candidate) !== owner) throw Error('Selection changed');
      return operation(owner);
    });
  }
  function persist(owner, marker) {
    const raw = JSON.stringify(marker);
    storage.setItem(keyFor(owner), raw);
    if (storage.getItem(keyFor(owner)) !== raw) throw unknown();
  }
  return {
    flagShareReady: true,
    pendingShare(candidate) {
      try {
        const marker = read(ownerFor(candidate));
        if (!marker) return null;
        return {requestId:marker.selection.requestId, state:marker.state, shareId:marker.shareId,
          sameSelection:sameRef(marker.ref, candidate.ref)};
      } catch { return {state:'blocked'}; }
    },
    async shareFlag(candidate, selection) {
      return locked(candidate, async owner => {
        if (!selection || Object.keys(selection).sort().join(',') !== 'consent,flagId,flagRevision,requestId,targetSessionId' || !id(selection.flagId) || !id(selection.requestId) || !Number.isInteger(selection.flagRevision) || selection.flagRevision < 1 || selection.consent !== true || selection.targetSessionId !== owner.scope.sessionId) throw Error('Select the saved note explicitly');
        const previous = read(owner);
        if (previous && previous.state !== 'complete' &&
          !(previous.state === 'unavailable' && (previous.selection.flagId !== selection.flagId || previous.selection.flagRevision !== selection.flagRevision))) throw unknown();
        const marker = {version:1, ref:{...candidate.ref}, selection:{...selection}, state:'pending'};
        persist(owner, marker);
        let result;
        try { result = await call('w26MeaningShare', selection, {scope:owner.scope}); }
        catch { throw unknown(); }
        await current(owner, candidate);
        if (!id(result?.id) || storage.getItem(keyFor(owner)) !== JSON.stringify(marker)) throw unknown();
        persist(owner, {...marker, state:'complete', shareId:result.id});
        return result;
      });
    },
    async recoverShare(candidate, requestId) {
      return locked(candidate, async owner => {
        const marker = read(owner);
        if (!marker || marker.selection.requestId !== requestId) throw unknown();
        const result = await call('w26MeaningShareReceipt', null, requestId, {scope:owner.scope});
        if (getOwner() !== owner || ownerFor(candidate) !== owner) throw Error('Selection changed');
        if (!result || !['unknown','complete','pending','processing','unresolved','failed','cancelled'].includes(result.state)) throw unknown();
        if (result.state === 'complete') {
          if (!id(result.shareId) || marker.state === 'revoking') throw unknown();
          persist(owner, {...marker, state:'complete', shareId:result.shareId});
        } else if (['failed','cancelled'].includes(result.state) && result.shareId == null) {
          persist(owner, {...marker, state:'unavailable'});
        }
        // Unknown stays durable. It never authorizes another POST or new ID.
        return result;
      }, false);
    },
    async revokeFlagShare(candidate, shareId) {
      return locked(candidate, async owner => {
        const marker = read(owner);
        if (!id(shareId) || !marker || !['complete','unavailable'].includes(marker.state) || marker.shareId !== shareId) throw unknown();
        const revoking = {...marker, state:'revoking'};
        persist(owner, revoking);
        const result = await call('w26MeaningShareRevoke', null, shareId, {scope:owner.scope});
        if (getOwner() !== owner || ownerFor(candidate) !== owner) throw Error('Selection changed');
        if (result?.ok !== true || storage.getItem(keyFor(owner)) !== JSON.stringify(revoking)) throw unknown();
        storage.removeItem(keyFor(owner));
        return result;
      }, false);
    }
  };
}
