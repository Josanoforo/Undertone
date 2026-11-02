// Authenticated operations are supplied by the owning shell; this module constructs no URLs.
export function mount(root, context = {}) {
  let destroyed = false;
  let generation = 0;
  let scope = scopeKey(context);
  let draft = freshDraft();
  function freshDraft() {
    return { kind: 'RGB_LINEAR_MEAN_V1', prediction: '', r1: '0', g1: '0', b1: '0', w1: '1', r2: '0', g2: '0', b2: '0', w2: '1', a: '6', b: '6' };
  }
  function scopeKey(value) {
    return JSON.stringify([value.scopeId, value.sessionId, value.actorId, value.sourceId, value.sourceRevision, value.profileId, value.profileRevision]);
  }
  function paragraph(container, text) {
    const node = document.createElement('p'); node.textContent = text; container.append(node);
  }
  function describeActivity(container, definition) {
    const rgb = definition.kind === 'RGB_LINEAR_MEAN_V1';
    if (!rgb && definition.kind !== 'RESOURCE_BUDGET_12_V1') throw new Error('unavailable');
    paragraph(container, rgb
      ? 'Objective: inspect how two digital RGB colors combine when their weights change.'
      : 'Objective: inspect how twelve resource tokens are divided between A and B.');
    paragraph(container, rgb
      ? 'Rule and units: each channel (0–255 integer channel levels) is a weighted mean, rounded half upward. Weights are 0–100 weight units; at least one must be positive. This is simplified digital arithmetic, not pigment mixing.'
      : 'Rule and units: A + B must equal exactly 12 resource tokens. Each allocation is a whole number from 0 to 12; unused tokens equal 0. This toy rule does not optimize the allocation.');
    paragraph(container, `Approved rule: ${definition.kind}; definition version ${definition.version}.`);
  }
  function showRecord(container, record) {
    if (!record || !Array.isArray(record.reasons) || typeof record.review !== 'string') throw new Error('unavailable');
    const card = document.createElement('article'); card.className = 'w24-reviewed-record';
    const title = document.createElement('h3'); title.textContent = 'Creator-reviewed activity'; card.append(title);
    paragraph(card, `Record ${record.recordId}; activity ${record.activityId}, revision ${record.activityRevision}.`);
    describeActivity(card, record.definition);
    const outcome = document.createElement('h4'); outcome.textContent = 'Creator-reviewed explanation and result'; card.append(outcome);
    paragraph(card, record.review);
    const heading = document.createElement('h4'); heading.textContent = 'Contributed reasons'; card.append(heading);
    if (!record.reasons.length) paragraph(card, 'No contributions. You can understand this activity without answering, predicting or sharing.');
    else {
      paragraph(card, 'Every reason included in this review is retained below, including differing positions.');
      const list = document.createElement('ol');
      for (const reason of record.reasons) {
        const item = document.createElement('li');
        paragraph(item, reason.text);
        for (const correction of reason.corrections || []) paragraph(item, `Author correction: ${correction}`);
        list.append(item);
      }
      card.append(list);
    }
    container.replaceChildren(card);
  }
  function render() {
    root.replaceChildren();
    const section = document.createElement('section');
    section.className = 'w24-activities';
    section.setAttribute('aria-label', 'Creator activities');
    const title = document.createElement('h2');
    title.textContent = 'Creator activities';
    const intro = document.createElement('p');
    intro.textContent = 'Watch without participating, or make a prediction when an approved activity is available.';
    const rules = document.createElement('details');
    const summary = document.createElement('summary');
    summary.textContent = 'Inspect supported model rules';
    const rgb = document.createElement('p');
    rgb.textContent = 'RGB linear mean: each output channel is a weighted mean of two integer channels from 0 to 255. Weights are integers from 0 to 100 and cannot both be zero. Results round half up.';
    const budget = document.createElement('p');
    budget.textContent = 'Resource budget: allocate exactly 12 units between A and B, using whole numbers from 0 to 12.';
    rules.append(summary, rgb, budget);
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    status.textContent = typeof context.readActivity === 'function' && typeof context.demonstrateActivity === 'function'
      ? 'Open an approved activity to inspect and demonstrate it.'
      : 'Activities are unavailable until the activity service is connected.';
    section.append(title, intro, rules, status);
    const exploration = document.createElement('details');
    const exploreTitle = document.createElement('summary');
    exploreTitle.textContent = 'Explore model inputs';
    const note = document.createElement('p');
    note.textContent = 'These inputs stay in this view and cannot be submitted or evaluated until an approved activity is available.';
    const label = document.createElement('label');
    label.textContent = 'Model';
    const select = document.createElement('select');
    for (const [value, name] of [['RGB_LINEAR_MEAN_V1', 'RGB linear mean'], ['RESOURCE_BUDGET_12_V1', 'Resource budget']]) {
      const option = document.createElement('option'); option.value = value; option.textContent = name;
      option.selected = draft.kind === value; select.append(option);
    }
    label.append(select);
    const fields = document.createElement('div'); fields.className = 'w24-activity-fields';
    function renderFields() {
      fields.replaceChildren();
      const entries = draft.kind === 'RGB_LINEAR_MEAN_V1'
        ? [['r1','First red',255], ['g1','First green',255], ['b1','First blue',255], ['w1','First weight',100], ['r2','Second red',255], ['g2','Second green',255], ['b2','Second blue',255], ['w2','Second weight',100]]
        : [['a','Allocation A',12], ['b','Allocation B',12]];
      for (const [key, name, max] of entries) {
        const field = document.createElement('label'); field.textContent = name;
        const input = document.createElement('input'); input.type = 'number'; input.min = '0'; input.max = String(max); input.step = '1'; input.value = draft[key];
        input.addEventListener('input', () => { draft[key] = input.value; }); field.append(input); fields.append(field);
      }
    }
    select.addEventListener('change', () => { draft.kind = select.value; renderFields(); });
    renderFields();
    const prediction = document.createElement('label'); prediction.textContent = 'Your prediction (private to this view)';
    const text = document.createElement('textarea'); text.value = draft.prediction; text.maxLength = 2000;
    text.addEventListener('input', () => { draft.prediction = text.value; }); prediction.append(text);
    const check = document.createElement('button'); check.type = 'button'; check.textContent = 'Check input ranges';
    const feedback = document.createElement('p'); feedback.setAttribute('role', 'status');
    check.addEventListener('click', () => {
      const rgb = draft.kind === 'RGB_LINEAR_MEAN_V1';
      const limits = rgb ? {r1:255, g1:255, b1:255, w1:100, r2:255, g2:255, b2:255, w2:100} : {a:12, b:12};
      const invalid = Object.entries(limits).some(([key, max]) => !/^\d+$/.test(draft[key]) || !Number.isSafeInteger(Number(draft[key])) || Number(draft[key]) > max);
      if (invalid) feedback.textContent = 'Enter whole numbers within the displayed ranges.';
      else if (rgb && Number(draft.w1) + Number(draft.w2) === 0) feedback.textContent = 'At least one weight must be greater than zero.';
      else if (!rgb && Number(draft.a) + Number(draft.b) !== 12) feedback.textContent = 'Allocations A and B must total 12 units.';
      else feedback.textContent = 'Inputs meet the model ranges. No result has been calculated or submitted.';
    });
    exploration.append(exploreTitle, note, label, fields, prediction, check, feedback); section.append(exploration);
    // This seam consumes only the published read/demonstrate interface. The
    // shared shell supplies authenticated callbacks; this module makes no URL.
    if (typeof context.readActivity === 'function' && typeof context.demonstrateActivity === 'function') {
      const activityLabel = document.createElement('label'); activityLabel.textContent = 'Approved activity ID';
      const activityInput = document.createElement('input'); activityInput.autocomplete = 'off'; activityLabel.append(activityInput);
      const load = document.createElement('button'); load.type = 'button'; load.textContent = 'Open approved activity';
      const demo = document.createElement('button'); demo.type = 'button'; demo.textContent = 'Demonstrate with these inputs'; demo.disabled = true;
      const output = document.createElement('pre'); output.setAttribute('aria-live', 'polite');
      const description = document.createElement('div');
      const history = document.createElement('div'); history.className = 'w24-demonstrations';
      history.setAttribute('aria-label', 'Local demonstration history');
      let activity = null, request = 0;
      function clearDemonstrations() {
        history.replaceChildren(); description.replaceChildren(); demo.textContent = 'Demonstrate with these inputs';
      }
      activityInput.addEventListener('input', () => { request += 1; activity = null; demo.disabled = true; output.textContent = ''; clearDemonstrations(); });
      load.addEventListener('click', async () => {
        const token = generation, serial = ++request, id = activityInput.value.trim();
        activity = null; demo.disabled = true; clearDemonstrations(); output.textContent = 'Loading activity…';
        try {
          const result = await context.readActivity(id);
          if (destroyed || token !== generation || serial !== request || id !== activityInput.value.trim()) return;
          if (!result || result.activityId !== id || !Number.isSafeInteger(result.revision) || !result.definition) throw new Error('unavailable');
          if (!['RGB_LINEAR_MEAN_V1', 'RESOURCE_BUDGET_12_V1'].includes(result.definition.kind)) throw new Error('unavailable');
          draft.kind = result.definition.kind; select.value = draft.kind; renderFields();
          describeActivity(description, result.definition);
          activity = result; demo.disabled = false;
          output.textContent = `Activity revision ${result.revision}. Demonstrations stay in this view. Existing reviewed records are unchanged; a revised explanation needs a separate creator review.`;
        } catch (_) { if (!destroyed && token === generation && serial === request) output.textContent = 'Activity unavailable. Check the ID and current access.'; }
      });
      demo.addEventListener('click', async () => {
        if (!activity) return;
        if (draft.kind !== activity.definition.kind) { output.textContent = 'Choose the approved activity model before demonstrating.'; return; }
        const token = generation, serial = ++request, selected = activity;
        const rgb = draft.kind === 'RGB_LINEAR_MEAN_V1';
        const limits = rgb ? {r1:255, g1:255, b1:255, w1:100, r2:255, g2:255, b2:255, w2:100} : {a:12, b:12};
        if (Object.entries(limits).some(([key, max]) => !/^\d+$/.test(draft[key]) || !Number.isSafeInteger(Number(draft[key])) || Number(draft[key]) > max) || (rgb && Number(draft.w1) + Number(draft.w2) === 0) || (!rgb && Number(draft.a) + Number(draft.b) !== 12)) {
          output.textContent = 'Check the model input ranges and totals first.'; return;
        }
        const n = key => Number(draft[key]);
        const parameters = rgb ? {c1:{r:n('r1'),g:n('g1'),b:n('b1')},w1:n('w1'),c2:{r:n('r2'),g:n('g2'),b:n('b2')},w2:n('w2')} : {total:12,a:n('a'),b:n('b')};
        const prediction = draft.prediction;
        demo.disabled = true; output.textContent = 'Calculating demonstration…';
        try {
          const result = await context.demonstrateActivity(selected.activityId, {revision:selected.revision, parameters});
          if (destroyed || token !== generation || serial !== request || activity !== selected) return;
          if (!result || result.activityId !== selected.activityId || result.revision !== selected.revision || !result.result?.values) throw new Error('unavailable');
          const card = document.createElement('article');
          const heading = document.createElement('h3');
          heading.textContent = `${history.children.length ? 'Retry' : 'Demonstration'} ${history.children.length + 1}`; card.append(heading);
          paragraph(card, `Activity ${selected.activityId}, revision ${selected.revision}. Local result; not saved or approved.`);
          paragraph(card, `Submitted parameters: ${JSON.stringify(parameters)}`);
          if (prediction.trim()) paragraph(card, `Prediction in this view: ${prediction}`);
          paragraph(card, `Result: ${JSON.stringify(result.result.values)}`);
          paragraph(card, result.result.explanation);
          history.append(card); demo.textContent = 'Retry with changed inputs';
          output.textContent = 'Result shown for the submitted inputs. Change inputs or prediction and explicitly retry. Previous demonstrations and existing reviewed records are unchanged.';
        } catch (_) {
          if (!destroyed && token === generation && serial === request && activity === selected) {
            history.replaceChildren();
            demo.textContent = 'Demonstrate with these inputs';
            output.textContent = 'Demonstration unavailable. Check that the activity and source are current.';
          }
        } finally { if (!destroyed && token === generation && serial === request && activity === selected) demo.disabled = false; }
      });
      section.append(activityLabel, load, description, demo, output, history);
    }
    // The caller supplies identifiers explicitly. Failed mutations are never retried
    // implicitly: the original request identifier remains available for a receipt lookup.
    function field(container, name, initial = '') {
      const label = document.createElement('label'); label.textContent = name;
      const input = document.createElement('input'); input.value = initial; input.autocomplete = 'off';
      label.append(input); container.append(label); return input;
    }
    function button(container, name, action) {
      const control = document.createElement('button'); control.type = 'button'; control.textContent = name;
      control.addEventListener('click', async () => { if (control.disabled) return; control.disabled = true; try { await action(); } finally { control.disabled = false; } }); container.append(control); return control;
    }
    function notice(container) { const node = document.createElement('pre'); node.setAttribute('role', 'status'); container.append(node); return node; }
    function integer(input, minimum = 0) {
      if (!/^\d+$/.test(input.value)) throw new Error('Enter a whole revision or sequence number.');
      const value = Number(input.value); if (!Number.isSafeInteger(value) || value < minimum) throw new Error('Enter a whole revision or sequence number.'); return value;
    }
    function required(input) { const value = input.value.trim(); if (!value) throw new Error('Complete the required identifiers.'); return value; }
    const ignored = Symbol('ignored stale response');
    function guarded(output, fn) {
      return async () => {
        const token = generation; output.textContent = 'Working…';
        try { const value = await fn(); if (!destroyed && token === generation && value !== ignored) output.textContent = JSON.stringify(value, null, 2); }
        catch (error) { if (!destroyed && token === generation) output.textContent = error && error.message && /^(Enter |Complete |Choose )/.test(error.message) ? error.message : 'Unavailable or outcome uncertain. Preserve your inputs and check the original operation receipt before trying again.'; }
      };
    }
    if (typeof context.mutateActivity === 'function') {
      const creator = document.createElement('details');
      const heading = document.createElement('summary'); heading.textContent = 'Configure an approved activity'; creator.append(heading);
      const requestId = field(creator, 'Request ID');
      const activityId = field(creator, 'Activity ID (for update or withdrawal)');
      const revision = field(creator, 'Expected revision', '0');
      const approvalId = field(creator, 'Exact model approval ID');
      const outcome = notice(creator);
      const mutate = action => guarded(outcome, () => {
        const body = {action, requestId: required(requestId), expectedRevision: integer(revision)};
        if (action !== 'create') body.activityId = required(activityId);
        if (action !== 'withdraw') body.approvalId = required(approvalId);
        if (action === 'create' && body.expectedRevision !== 0) throw new Error('Enter revision 0 to create an activity.');
        return context.mutateActivity(body);
      });
      button(creator, 'Create activity', mutate('create'));
      button(creator, 'Update activity', mutate('update'));
      button(creator, 'Withdraw activity', mutate('withdraw'));
      if (typeof context.readActivityOperation === 'function') button(creator, 'Check original operation receipt', guarded(outcome, () => context.readActivityOperation(required(requestId))));
      if (typeof context.listModelApprovals === 'function') button(creator, 'List current approvals', guarded(outcome, () => context.listModelApprovals()));
      section.append(creator);
    }
    if (typeof context.mutateModel === 'function') {
      const practice = document.createElement('details'); const heading = document.createElement('summary');
      heading.textContent = 'Private prediction and practice'; practice.append(heading);
      const description = document.createElement('p'); description.textContent = 'Create a private prediction from an approved activity and your existing attempt. Evaluating again is an explicit retry. Sharing and identity disclosure are separate choices.'; practice.append(description);
      const activityId = field(practice, 'Approved activity ID');
      const attemptId = field(practice, 'Your existing attempt ID');
      const modelId = field(practice, 'Private model ID');
      const requestId = field(practice, 'Request ID');
      const revision = field(practice, 'Expected model revision', '0');
      const sequence = field(practice, 'Event sequence to share', '1');
      const shareId = field(practice, 'Share ID to revoke');
      const identityLabel = document.createElement('label'); const identity = document.createElement('input'); identity.type = 'checkbox';
      identityLabel.append(identity, document.createTextNode(' Include my identity when sharing this event')); practice.append(identityLabel);
      const output = notice(practice);
      let selected = null, selection = 0;
      activityId.addEventListener('input', () => { selected = null; selection += 1; });
      if (typeof context.readActivity === 'function') button(practice, 'Load approved definition', guarded(output, async () => {
        const id = required(activityId), serial = ++selection, token = generation;
        const activity = await context.readActivity(id);
        if (destroyed || token !== generation || serial !== selection || id !== activityId.value.trim()) return ignored;
        if (!activity || activity.activityId !== id || !activity.definition || !['RGB_LINEAR_MEAN_V1', 'RESOURCE_BUDGET_12_V1'].includes(activity.definition.kind)) throw new Error('unavailable');
        selected = activity; draft.kind = activity.definition.kind; select.value = draft.kind; renderFields();
        return {activityId: id, revision: activity.revision, definition: activity.definition, units: activity.units};
      }));
      button(practice, 'Create private prediction', guarded(output, () => {
        if (!selected) throw new Error('Choose an approved definition first.');
        if (!draft.prediction.trim()) throw new Error('Enter your prediction in Explore model inputs first.');
        return context.mutateModel({action:'create', requestId:required(requestId), expectedRevision:0, definition:selected.definition, attemptId:required(attemptId), prediction:draft.prediction});
      }));
      button(practice, 'Evaluate or retry', guarded(output, () => {
        if (!selected || selected.definition.kind !== draft.kind) throw new Error('Choose the approved activity model before evaluating.');
        const rgb = draft.kind === 'RGB_LINEAR_MEAN_V1';
        if (!rgb && draft.kind !== 'RESOURCE_BUDGET_12_V1') throw new Error('Choose a supported model.');
        const limits = rgb ? {r1:255,g1:255,b1:255,w1:100,r2:255,g2:255,b2:255,w2:100} : {a:12,b:12};
        if (Object.entries(limits).some(([key,max]) => !/^\d+$/.test(draft[key]) || !Number.isSafeInteger(Number(draft[key])) || Number(draft[key]) > max) || (rgb && Number(draft.w1)+Number(draft.w2) === 0) || (!rgb && Number(draft.a)+Number(draft.b) !== 12)) throw new Error('Enter valid inputs in Explore model inputs first.');
        const n = key => Number(draft[key]);
        const parameters = rgb ? {c1:{r:n('r1'),g:n('g1'),b:n('b1')},w1:n('w1'),c2:{r:n('r2'),g:n('g2'),b:n('b2')},w2:n('w2')} : {total:12,a:n('a'),b:n('b')};
        return context.mutateModel({action:'evaluate',requestId:required(requestId),expectedRevision:integer(revision),modelId:required(modelId),parameters});
      }));
      button(practice, 'Share selected event with creator', guarded(output, () => context.mutateModel({action:'share',requestId:required(requestId),expectedRevision:integer(revision),modelId:required(modelId),sequence:integer(sequence,1),consent:true,identityConsent:Boolean(identity.checked)})));
      button(practice, 'Revoke my share', guarded(output, () => context.mutateModel({action:'revoke',requestId:required(requestId),expectedRevision:integer(revision),modelId:required(modelId),shareId:required(shareId)})));
      if (typeof context.readModel === 'function') button(practice, 'Read my private model', guarded(output, () => context.readModel(required(modelId))));
      if (typeof context.listOwnedModelShares === 'function') button(practice, 'List my share handles', guarded(output, () => context.listOwnedModelShares()));
      if (typeof context.listModelReceipts === 'function') button(practice, 'Check my operation receipts', guarded(output, () => context.listModelReceipts()));
      section.append(practice);
    }
    if (typeof context.listModelShares === 'function') {
      const review = document.createElement('details'); const heading = document.createElement('summary');
      heading.textContent = 'Review selected shared model events'; review.append(heading);
      const explanation = document.createElement('p'); explanation.textContent = 'Only voluntarily shared events are shown. A shared event does not include a private prediction or reason. Review and approval of reasons require the activity record service.'; review.append(explanation);
      const output = notice(review);
      button(review, 'Load shared events', guarded(output, () => context.listModelShares()));
      section.append(review);
    }
    // The complete review uses the exact current consented set, including minorities.
    if (typeof context.linkActivityReason === 'function' && typeof context.unlinkActivityReason === 'function') {
      const box = document.createElement('details'); const heading = document.createElement('summary'); heading.textContent = 'Share a reason with an activity'; box.append(heading);
      const activityId = field(box, 'Activity ID'); const activityRevision = field(box, 'Activity revision');
      const reasonId = field(box, 'Your shared reason ID'); const reasonRevision = field(box, 'Reason revision'); const output = notice(box);
      button(box, 'Consent to link my reason', guarded(output, () => context.linkActivityReason({activityId:required(activityId), activityRevision:integer(activityRevision,1), reasonId:required(reasonId), reasonRevision:integer(reasonRevision,1), consent:true})));
      button(box, 'Withdraw my reason link', guarded(output, () => context.unlinkActivityReason({activityId:required(activityId), activityRevision:integer(activityRevision,1), reasonId:required(reasonId)})));
      section.append(box);
    }
    if (typeof context.listActivityReasons === 'function' && typeof context.saveActivityRecord === 'function') {
      const box = document.createElement('details'); const heading = document.createElement('summary'); heading.textContent = 'Review activity reasons'; box.append(heading);
      const explanation = document.createElement('p'); explanation.textContent = 'Load and review every linked reason, including minority views. An empty list is valid. Changes or withdrawal require a new review.'; box.append(explanation);
      const activityId = field(box, 'Activity ID'); const revision = field(box, 'Activity revision'); const requestId = field(box, 'Request ID'); const recordId = field(box, 'Record ID');
      const label = document.createElement('label'); label.textContent = 'Creator review'; const review = document.createElement('textarea'); review.maxLength = 4000; label.append(review); box.append(label);
      const output = notice(box); let loaded = null, serial = 0;
      const clear = () => { loaded = null; serial++; output.textContent = ''; }; activityId.addEventListener('input', clear); revision.addEventListener('input', clear);
      button(box, 'Load all linked reasons', guarded(output, async () => {
        const id = required(activityId), rev = integer(revision,1), ticket = ++serial, token = generation; loaded = null;
        const result = await context.listActivityReasons(id, rev);
        if (destroyed || token !== generation || ticket !== serial) return ignored;
        if (!result || result.activityId !== id || result.activityRevision !== rev || !Array.isArray(result.reasons) || result.reasons.some(r => !r || typeof r.id !== 'string' || !Number.isSafeInteger(r.revision) || r.revision < 1)) throw new Error('unavailable');
        loaded = {id, rev, refs:result.reasons.map(r => ({id:r.id,revision:r.revision}))}; return result;
      }));
      button(box, 'Save reviewed record', guarded(output, () => {
        if (!loaded || loaded.id !== required(activityId) || loaded.rev !== integer(revision,1)) throw new Error('Choose the current linked reasons first.');
        if (!review.value.trim()) throw new Error('Enter a creator review.');
        return context.saveActivityRecord({requestId:required(requestId), activityId:loaded.id, activityRevision:loaded.rev, reasonRefs:loaded.refs, review:review.value});
      }));
      if (typeof context.withdrawActivityRecord === 'function') button(box, 'Withdraw reviewed record', guarded(output, () => context.withdrawActivityRecord(required(recordId), {requestId:required(requestId), expectedRevision:1})));
      if (typeof context.readActivityRecordOperation === 'function') button(box, 'Check record operation receipt', guarded(output, () => context.readActivityRecordOperation(required(requestId))));
      section.append(box);
    }
    if (typeof context.readActivityRecord === 'function') {
      const box = document.createElement('details'); const heading = document.createElement('summary'); heading.textContent = 'Open a reviewed activity record'; box.append(heading);
      const explanation = document.createElement('p'); explanation.textContent = 'The record is available only while the activity and linked reasons remain eligible.'; box.append(explanation);
      const recordId = field(box, 'Record ID'); const output = notice(box); let serial = 0;
      const recordView = document.createElement('div'); box.append(recordView);
      recordId.addEventListener('input', () => { serial += 1; output.textContent = ''; recordView.replaceChildren(); });
      button(box, 'Read reviewed record', guarded(output, async () => {
        const id = required(recordId), ticket = ++serial, token = generation;
        recordView.replaceChildren();
        try {
          const result = await context.readActivityRecord(id);
          if (destroyed || token !== generation || ticket !== serial || id !== recordId.value.trim()) return ignored;
          if (result?.recordId !== id) throw new Error('unavailable');
          showRecord(recordView, result); output.textContent = 'Read-only record. No response or participation is required.';
          return ignored;
        } catch (error) {
          if (destroyed || token !== generation || ticket !== serial || id !== recordId.value.trim()) return ignored;
          throw error;
        }
      }));
      section.append(box);
    }
    if (typeof context.useActivityPackReference === 'function') {
      const box = document.createElement('details'); const heading = document.createElement('summary'); heading.textContent = 'Add an activity definition to a pack'; box.append(heading);
      const note = document.createElement('p'); note.textContent = 'The pack references the approved activity definition, not the reviewed record or private practice. Pack rights are checked again when used.'; box.append(note);
      const id = field(box, 'Activity ID'); const revision = field(box, 'Activity revision'); const output = notice(box);
      button(box, 'Choose this activity for the pack', guarded(output, () => context.useActivityPackReference({kind:'activity',ref:required(id),revision:integer(revision,1)})));
      section.append(box);
    }
    root.append(section);
  }
  render();
  return {
    update(next = {}) { if (destroyed) return; generation += 1; const nextScope = scopeKey(next); if (nextScope !== scope) { scope = nextScope; draft = freshDraft(); } context = next; render(); },
    destroy() { if (destroyed) return; destroyed = true; generation += 1; context = null; draft = freshDraft(); root.replaceChildren(); }
  };
}
