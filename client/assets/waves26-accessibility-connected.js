// Connects the accessibility component to the existing host authorities.
import {mountAccessibility} from './waves26-accessibility.js';

export function mountConnectedAccessibility(root, host) {
  let generation = 0, context = null, destroyed = false;
  const check = (ticket, ctx) => {
    if (destroyed || ticket !== generation || ctx !== context || !host.isCurrent(ctx)) throw new Error('Context changed');
  };
  const component = mountAccessibility(root, {actions: {
    stopDescription: () => host.stopDescription(),
    returnFocus: () => { if (context) { check(generation, context); host.returnFocus(context); } },
    readPreferences: async () => {
      const ctx = context, ticket = generation; check(ticket, ctx);
      const dto = await host.call('w25PreferencesGet', null, ctx.editionId || null, {scope:ctx.identity});
      check(ticket, ctx); return dto;
    },
    savePreferences: async ({expectedRevision, change}) => {
      const ctx = context, ticket = generation; check(ticket, ctx);
      const keys = Object.keys(change || {});
      if (keys.length !== 1 || !((keys[0] === 'descriptionEnabled' && typeof change.descriptionEnabled === 'boolean') || (keys[0] === 'captionMode' && ['off','original','translated','both'].includes(change.captionMode)))) throw new Error('Invalid choice');
      // The host uses the same preference lock and unknown-save recovery as its
      // existing listening controls. No independent journal or retry is created.
      const dto = await host.withPreferenceSave(ctx, async requestId => {
        check(ticket, ctx);
        const current = await host.call('w25PreferencesGet', null, ctx.editionId || null, {scope:ctx.identity});
        check(ticket, ctx);
        const selection = current.modeSupport?.selection;
        const sameRef = (a,b) => !!a && !!b && ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(k => a[k] === b[k]);
        if (current.revision !== expectedRevision || !sameRef(selection?.ref, ctx.ref) || (current.selection && !sameRef(current.selection.ref, ctx.ref))) throw new Error('Selection changed');
        const mode = current.state === 'unset' ? 'read' : current.mode;
        if ((current.state !== 'unset' && (current.state !== 'available' || current.positionAvailable !== true)) || !['read','listen'].includes(mode) || current.modeSupport?.[mode] !== true) throw new Error('Preference unavailable');
        const position = current.state === 'unset' ? null : current.position;
        if (!(position === null || (position && Object.keys(position).sort().join(',') === 'bindingId,offsetMs' && typeof position.bindingId === 'string' && position.bindingId.length > 0 && position.bindingId.length <= 128 && Number.isSafeInteger(position.offsetMs) && position.offsetMs >= 0 && position.offsetMs <= 864000000))) throw new Error('Position unavailable');
        const body = {requestId, expectedRevision, mode, position, ...change};
        // The existing host guard must journal this exact body before dispatch,
        // preserve uncertain results and never substitute a fresh request ID.
        const result = await host.dispatchPreferenceSave(ctx, body, async () => {
          check(ticket, ctx);
          const response = await host.call('w25PreferencesPut', body, ctx.editionId || null, {scope:ctx.identity});
          check(ticket, ctx); return response;
        });
        check(ticket, ctx);
        if (result?.revision !== expectedRevision + 1 || result[keys[0]] !== change[keys[0]] || !sameRef(result.selection?.ref, ctx.ref)) throw new Error('Save unconfirmed');
        return result;
      });
      check(ticket, ctx); return dto;
    },
    readCurrentEdition: async () => {
      const ctx = context, ticket = generation; check(ticket, ctx);
      if (!ctx.editionId || !ctx.language) throw new Error('Edition unavailable');
      const result = await host.call('w22Edition', null, ctx.editionId, ctx.language, {scope:ctx.identity});
      check(ticket, ctx); return result.edition;
    },
    playDescription: async ({editionId, description, isCurrent}) => {
      const ctx = context, ticket = generation; check(ticket, ctx);
      if (editionId !== ctx.editionId || !isCurrent() || !ctx.ref || !description.sourceRef || !['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(k => description.sourceRef[k] === ctx.ref[k]) || !ctx.regionId || description.regionId !== ctx.regionId) throw new Error('Edition or source changed');
      await host.requestDescription(editionId, description, ctx.identity, () => {
        try { check(ticket, ctx); return isCurrent(); } catch { return false; }
      });
      check(ticket, ctx);
    }
  }});
  function reset() { generation++; context = null; component.reset(null); }
  async function update(next, view) {
    reset(); if (destroyed || !next || !host.isCurrent(next)) return;
    context = next; const ticket = generation;
    await component.update(view, next.scope); check(ticket, next);
  }
  function destroy() { if (destroyed) return; reset(); destroyed = true; component.destroy(); }
  return {update, reset, destroy};
}
