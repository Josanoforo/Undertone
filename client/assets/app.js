import { mountCreatorSpeechSetup } from './creator-speech-setup.js';
import { mountQualityChoice } from './waves30-quality-choice.js';
import { mountSavedTranslations } from './waves30-saved-translations.js';
import { renderWorkspaceGuide } from './waves30-workspace-guide.js';
import { looksLikeInvitation, parseInvitationSearch, parseInvitationText } from './invitation-input.mjs';
import { mountTerms } from './waves26-terms.js';
import { mountMeaning } from './waves26-meaning.js';
import { mountVisualAssociations } from './waves26-visual-selection.js';
import { mountEdition } from './waves22-edition.js';
import { mountApprovedExport, downloadApprovedChapter } from './waves27-export.js';
import { mountConnectedAccessibility } from './waves26-accessibility-connected.js';
import { mount as mountResumeAccess } from './waves30-resume-access.js';
import { verifyResumeAccess } from './waves19-20-resume-verify.js';
import { mountDelivery } from './waves19-20-delivery.js';
import { mountSpeechView } from './waves21-speech-view.js';
import { mountVisualView } from './waves21-visual-view.js';
import { mountImpactPreview, createImpactApprovalAction, createImpactReplacementJournal, createProtectedFormatAction } from './waves21-impact-connected.js';
import { mount as mountMoments23 } from './waves23-24-moments.js';
import { mount as mountMomentTrail27 } from './waves27-moment-trail.js';
import { mountChapterDraft, chaptersFromMaterial } from './waves27-chapters.js';
import { mount as mountListening23 } from './waves23-24-listening.js';
import { mount as mountContinuity25, snapshotFromDTO as continuitySnapshot } from './waves25-listening-continuity.js';
import { mountOperatingConnected } from './waves29-operating-connected.js';
import { mount as mountPack24 } from './waves23-24-pack.js';
import { mount as mountSetup28 } from './waves28-segment-setup.js';
import { mount as mountActivities24 } from './waves23-24-activities.js';
import { mount as mountGuide24 } from './waves23-24-guide.js';
import { mount as mountDesk24 } from './waves23-24-desk.js';
import { mountClaimsQuery } from './waves22-claims-query.js';
import { mountCoeditAccess, mountCoeditSetup } from './waves22-coedit.js';
import { mount as mountHandoff28 } from './waves28-handoff-connected.js';
import { mountModelHistory, mountModelShares } from './waves22-model-history.js';
import { mountModelWithdrawals, mountModelExploration, mountModelApprovals } from './waves22-representations.js';
import { mountPolicy } from './waves19-20-policy.js';
import { mountLibrary } from "./waves19-20-library.js";
import { mountPractice } from "./waves19-20-practice.js";
import { mountEntry, mountSetup } from "./waves19-20-entry.js";
import { mountInbox, mountInboxAnswers } from "./waves19-20-inbox.js";
import { mountOperator } from "./waves19-20-operator.js";
import { mountRecords } from "./waves18-record.js";
import { mountSegment, createSegmentListeningFence, readListeningControls, sameListeningRef } from "./waves18-segment.js";
import { mountAssistance } from "./waves18-assistance.js";
import { mountReturn } from "./waves17-18-return.js";
import { mountTemplates } from "./waves17-18-templates.js";
import { mountCues } from "./waves15-cues.js";
import { mountFiniteFormats } from "./waves15-16-formats.js";
import { mountChapters } from "./waves15-16-journeys.js";
import { mountFormats } from "./waves13-14-formats.js";
import { mountQuestions } from "./waves13-14-questions.js";
import { mountProduction } from "./waves13-14-production.js";
import { mountReasons } from "./waves13-14-reasons.js";
import { mountWaveDrafts } from "./waves13-14-drafts.js";
import { mountModelPreview, mountPublishedModels } from "./waves13-14-model.js";
import { createCollaboration } from "./phase12-collaboration.js";
import { createPhase12 } from "./phase12.js";
import { createPhase11Controller } from "./phase11.js";
import { createLiveAudioController } from "./live-audio.js";
import { createPhase6Controller } from "./phase6.js";
import { createPhase10Controller } from "./phase10.js";

const API = (() => {
  const pending = new Set();
  const sessionPath = () =>
    `/api/sessions/${encodeURIComponent(state.sessionId)}`;
  const routes = {
    health: ["/api/health", "GET"],
    providers: ["/api/providers", "GET"],
    createSession: ["/api/sessions", "POST"],
    join: (id) => [`/api/sessions/${encodeURIComponent(id)}/join`, "POST"],
    session: () => [sessionPath(), "GET"],
    sources: () => [`${sessionPath()}/sources`, "GET"],
    addSource: () => [`${sessionPath()}/sources`, "POST"],
    sourceUpdate: (id) => [
      `${sessionPath()}/sources/${encodeURIComponent(id)}`,
      "PATCH",
    ],
    capture: () => [`${sessionPath()}/capture`, "POST"],
    transcribe: () => [`${sessionPath()}/transcribe`, "POST"],
    cleanup: () => [`${sessionPath()}/cleanup`, "POST"],
    lifecycle: () => [`${sessionPath()}/lifecycle`, "POST"],
    captureStatus: () => [`${sessionPath()}/capture-status`, "GET"],
    setCaptureStatus: () => [`${sessionPath()}/capture-status`, "POST"],
    bookmarks: () => [`${sessionPath()}/bookmarks`, "GET"],
    addBookmark: () => [`${sessionPath()}/bookmarks`, "POST"],
    w24ActivityRead: id => [`${sessionPath()}/w24/activity/activities/${encodeURIComponent(id)}`, "GET"],
    w24ActivityDemonstrate: id => [`${sessionPath()}/w24/activity/activities/${encodeURIComponent(id)}/demonstrate`, "POST"],
    w24ActivityMutate: () => [`${sessionPath()}/w24/activity/activities`, "POST"],
    w24ActivityOperation: id => [`${sessionPath()}/w24/activity/activities/operations/${encodeURIComponent(id)}`, "GET"],
    w24ActivityReasons: (id, revision) => [`${sessionPath()}/w24/activity/activities/${encodeURIComponent(id)}/versions/${encodeURIComponent(revision)}/reasons`, "GET"],
    w24ActivityReasonLink: () => [`${sessionPath()}/w24/activity/activity-reasons`, "POST"],
    w24ActivityReasonUnlink: () => [`${sessionPath()}/w24/activity/activity-reasons/withdraw`, "POST"],
    w24ActivityRecordSave: () => [`${sessionPath()}/w24/activity/activity-records`, "POST"],
    w24ActivityRecordRead: id => [`${sessionPath()}/w24/activity/activity-records/${encodeURIComponent(id)}`, "GET"],
    w24ActivityRecordWithdraw: id => [`${sessionPath()}/w24/activity/activity-records/${encodeURIComponent(id)}/withdraw`, "POST"],
    w24ActivityRecordOperation: id => [`${sessionPath()}/w24/activity/activity-records/operations/${encodeURIComponent(id)}`, "GET"],
    w24DeskHandoff: (id, action) => [`${sessionPath()}/w24/activity/handoffs/${encodeURIComponent(id)}/${action}`, "POST"],
    w24DeskTemplates: () => [`${sessionPath()}/w24/activity/draft-templates`, "POST"],
    w24DeskTemplateReceipt: id => [`${sessionPath()}/w24/activity/draft-templates/operations/${encodeURIComponent(id)}`, "GET"],
    w24DeskApply: (id, version, action, draft) => [`${sessionPath()}/w24/activity/draft-templates/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/${action}/${encodeURIComponent(draft)}`, "POST"],
    w24DeskCrossApply: (source, id, version, action, draft) => [`${sessionPath()}/w24/activity/source-sessions/${encodeURIComponent(source)}/draft-templates/${encodeURIComponent(id)}/versions/${encodeURIComponent(version)}/${action}/${encodeURIComponent(draft)}`, "POST"],
    w28SetupPreview: () => [`${sessionPath()}/w28/segment-setup/preview`, 'POST'],
    w28SetupImport: () => [`${sessionPath()}/w28/segment-setup/import`, 'POST'],
    w24PackRead: id => [`${sessionPath()}/w24/packs/${encodeURIComponent(id)}`, "GET"],
    w24PackPreview: () => [`${sessionPath()}/w24/packs/preview`, "POST"],
    w24PackMutate: () => [`${sessionPath()}/w24/packs`, "POST"],
    w24PackOperation: id => [`${sessionPath()}/w24/packs/operations/${encodeURIComponent(id)}`, "GET"],
    w24PackProfileSelection: () => [`${sessionPath()}/w24/packs/profile-selection`, "GET"],
    w24PackProfileSelect: () => [`${sessionPath()}/w24/packs/profile-selection`, "PUT"],
    w24PackProfileReceipt: id => [`${sessionPath()}/w24/packs/profile-selection-receipts/${encodeURIComponent(id)}`, "GET"],
    w24ChannelMutate: route => [`${sessionPath()}/w24/channels/${encodeURIComponent(route)}`, "POST"],
    w24ChannelOperation: id => [`${sessionPath()}/w24/channels/operations/${encodeURIComponent(id)}`, "GET"],
    w22Edition: (id, lang) => [`${sessionPath()}/w22/edition/${encodeURIComponent(id)}/${encodeURIComponent(lang)}`, "GET"],
    w27EditionExport: () => [`${sessionPath()}/w27/export`, "POST"],
    w29OperatingStatus: () => [`${sessionPath()}/w29/operating/status`, "POST"],
    w22EditionAsset: (id, lang, asset) => [`${sessionPath()}/w22/edition/${encodeURIComponent(id)}/${encodeURIComponent(lang)}/assets/${encodeURIComponent(asset)}`, "GET"],
    w22EditionDescriptionSelect: id => [`${sessionPath()}/w22/edition/${encodeURIComponent(id)}/description`, "POST"],
    w22EditionDescriptionWithdraw: id => [`${sessionPath()}/w22/edition/${encodeURIComponent(id)}/description`, "DELETE"],
    w22EditionDescriptionOperation: (id, requestId) => [`${sessionPath()}/w22/edition/${encodeURIComponent(id)}/description/operations/${encodeURIComponent(requestId)}`, "GET"],
    w18Records: () => [`${sessionPath()}/w18/records`, "GET"],
    w18RecordOptions: () => [`${sessionPath()}/w18/records/options`, "GET"],
    w18RecordRecipient: code => [`${sessionPath()}/w18/records/recipient/${encodeURIComponent(code)}`, "GET"],
    w18RecordReuseOptions: (id, target) => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}/reuse-options/${encodeURIComponent(target)}`, "GET"],
    w18RecordIncoming: () => [`${sessionPath()}/w18/records/incoming`, "GET"],
    w18Record: id => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}`, "GET"],
    w18RecordView: (id, lang) => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}/${encodeURIComponent(lang)}`, "GET"],
    w18RecordCreate: () => [`${sessionPath()}/w18/records`, "POST"],
    w18RecordVersion: id => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}/versions`, "POST"],
    w18RecordApprove: id => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}/approve`, "POST"],
    w18RecordWithdraw: id => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}/withdraw`, "POST"],
    w18RecordOperation: id => [`${sessionPath()}/w18/record-operations/${encodeURIComponent(id)}`, "GET"],
    w18RecordPrepareReuse: id => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}/prepare-reuse`, "POST"],
    w18RecordReuseOffer: id => [`${sessionPath()}/w18/records/${encodeURIComponent(id)}/reuse-offers`, "POST"],
    w18SegmentOptions: () => [`${sessionPath()}/w18/segments/options`, "GET"],
    w18Segments: () => [`${sessionPath()}/w18/segments`, "GET"],
    w18Segment: id => [`${sessionPath()}/w18/segments/${encodeURIComponent(id)}`, "GET"],
    w18SegmentCreate: () => [`${sessionPath()}/w18/segments`, "POST"],
    w18SegmentAction: id => [`${sessionPath()}/w18/segments/${encodeURIComponent(id)}/actions`, "POST"],
    w18SegmentOperation: id => [`${sessionPath()}/w18/segment-operations/${encodeURIComponent(id)}`, "GET"],
    w18SegmentPendingOperations: id => [`${sessionPath()}/w18/segments/${encodeURIComponent(id)}/pending-operations`, "GET"],
    w18Assistance: id => [`${sessionPath()}/w18/assistance/${encodeURIComponent(id)}`, "GET"],
    w18AssistancePolicy: id => [`${sessionPath()}/w18/assistance/${encodeURIComponent(id)}/policy`, "POST"],
    w18AssistanceCandidates: id => [`${sessionPath()}/w18/assistance/${encodeURIComponent(id)}/candidates`, "POST"],
    w18AssistanceFeedback: (id, candidate) => [`${sessionPath()}/w18/assistance/${encodeURIComponent(id)}/candidates/${encodeURIComponent(candidate)}/feedback`, "POST"],
    w17CreateReturnCheckpoint: () => [`${sessionPath()}/w17/return-checkpoints`, "POST"],
    w17ReturnCheckpoint: id => [`${sessionPath()}/w17/return-checkpoints/${encodeURIComponent(id)}`, "GET"],
    w17CreateReturn: () => [`${sessionPath()}/w17/returns`, "POST"],
    w17Return: id => [`${sessionPath()}/w17/returns/${encodeURIComponent(id)}`, "GET"],
    w17PatchReturn: id => [`${sessionPath()}/w17/returns/${encodeURIComponent(id)}`, "PATCH"],
    w17ReturnOperation: id => [`${sessionPath()}/w17/return-operations/${encodeURIComponent(id)}`, "GET"],
    w17Templates: () => [`${sessionPath()}/w17/templates`, "GET"],
    w17Template: id => [`${sessionPath()}/w17/templates/${encodeURIComponent(id)}`, "GET"],
    w17CreateTemplate: () => [`${sessionPath()}/w17/templates`, "POST"],
    w17TemplateVersion: id => [`${sessionPath()}/w17/templates/${encodeURIComponent(id)}/versions`, "POST"],
    w17TemplatePreview: id => [`${sessionPath()}/w17/templates/${encodeURIComponent(id)}/preview`, "POST"],
    w17InstantiateTemplate: id => [`${sessionPath()}/w17/templates/${encodeURIComponent(id)}/instantiate`, "POST"],
    w17TemplateRound: id => [`${sessionPath()}/w17/template-rounds/${encodeURIComponent(id)}`, "GET"],
    w17TransitionTemplateRound: id => [`${sessionPath()}/w17/template-rounds/${encodeURIComponent(id)}/transition`, "POST"],
    w17ImportContinuation: () => [`${sessionPath()}/w17/templates/import-continuation`, "POST"],
    w15Formats: () => [`${sessionPath()}/w15/formats`, "GET"],
    w15FormatReceipt: (id) => [`${sessionPath()}/w15/formats/receipts/${encodeURIComponent(id)}`, "GET"],
    w15GetContinuationConsent: (id) => [`${sessionPath()}/w15/format-contributions/${encodeURIComponent(id)}/continuation-consent`, "GET"],
    w15CreateFormat: () => [`${sessionPath()}/w15/formats`, "POST"],
    w15EditFormat: (id) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}`, "PATCH"],
    w15ContributeFormat: (id) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}/contributions`, "POST"],
    w15ContinuationConsent: (id) => [`${sessionPath()}/w15/format-contributions/${encodeURIComponent(id)}/continuation-consent`, "POST"],
    w15EditContribution: (id) => [`${sessionPath()}/w15/format-contributions/${encodeURIComponent(id)}`, "PATCH"],
    w15WithdrawContribution: (id) => [`${sessionPath()}/w15/format-contributions/${encodeURIComponent(id)}`, "DELETE"],
    w15AcceptContribution: (id) => [`${sessionPath()}/w15/format-contributions/${encodeURIComponent(id)}/accept`, "POST"],
    w15FormatDecision: (id) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}/decision`, "POST"],
    w15SourceGrants: (id) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}/source-grants`, "GET"],
    w15CreateSourceGrant: (id) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}/source-grants`, "POST"],
    w15RevokeSourceGrant: (id, grant) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}/source-grants/${encodeURIComponent(grant)}/revoke`, "POST"],
    w15CreateFormatWork: (id) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}/work`, "POST"],
    w15TransferPreview: (id) => [`${sessionPath()}/w15/format-transfers/${encodeURIComponent(id)}/preview`, "GET"],
    w15FormatTransfers: () => [`${sessionPath()}/w15/format-transfers`, "GET"],
    w15OfferFormat: (id) => [`${sessionPath()}/w15/formats/${encodeURIComponent(id)}/transfer`, "POST"],
    w15AcceptFormatTransfer: (id) => [`${sessionPath()}/w15/format-transfers/${encodeURIComponent(id)}/accept`, "POST"],
    w15DeclineFormatTransfer: (id) => [`${sessionPath()}/w15/format-transfers/${encodeURIComponent(id)}/decline`, "POST"],
    w15WithdrawFormatTransfer: (id) => [`${sessionPath()}/w15/format-transfers/${encodeURIComponent(id)}/withdraw`, "POST"],
    w15Chapters: () => [`${sessionPath()}/w15/chapters`, "GET"],
    w15ChapterOperation: (id) => [`${sessionPath()}/w15/operations/${encodeURIComponent(id)}`, "GET"],
    w15CreateChapter: () => [`${sessionPath()}/w15/chapters`, "POST"],
    w15EditChapter: (id) => [`${sessionPath()}/w15/chapters/${encodeURIComponent(id)}`, "PATCH"],
    w15Search: (query) => [`${sessionPath()}/w15/search?q=${encodeURIComponent(query)}`, "GET"],
    catchup: () => [`${sessionPath()}/catch-up`, "GET"],
    acknowledgeCatchup: () => [`${sessionPath()}/catch-up/ack`, "POST"],
    catchupRecap: () => [`${sessionPath()}/catch-up/recap`, "POST"],
    activity: () => [`${sessionPath()}/activity`, "GET"],
    interventionFeedback: () => [`${sessionPath()}/intervention-feedback`, "POST"],
    interventionAggregate: (materialId, version) => [`${sessionPath()}/intervention-feedback?materialId=${encodeURIComponent(materialId)}&version=${encodeURIComponent(version)}`, "GET"],
    notebook: () => [`${sessionPath()}/notebook`, "GET"],
    addNotebookItem: () => [`${sessionPath()}/notebook`, "POST"],
    deleteNotebookItem: (id) => [`${sessionPath()}/notebook/${encodeURIComponent(id)}`, "DELETE"],
    exportNotebook: () => [`${sessionPath()}/notebook/export`, "POST"],
    importNotebook: () => [`${sessionPath()}/notebook/import`, "POST"],
    notebookImportReceipt: id => [`${sessionPath()}/notebook/receipts/${encodeURIComponent(id)}`, "GET"],
    deleteBookmark: (id) => [`${sessionPath()}/bookmarks/${encodeURIComponent(id)}`, "DELETE"],
    compareAttempts: () => [`${sessionPath()}/attempt-comparison`, "POST"],
    workbench: () => [`${sessionPath()}/workbench`, "GET"],
    operations: () => [`${sessionPath()}/operations`, "GET"],
    deletePrivateData: () => [`${sessionPath()}/private-data`, "DELETE"],
    connection: () => [`${sessionPath()}/connection`, "GET"],
    twitch: () => [`${sessionPath()}/twitch/connect`, "POST"],
    conversations: () => [`${sessionPath()}/conversations`, "GET"],
    createConversation: () => [`${sessionPath()}/conversations`, "POST"],
    conversation: (cid) => [
      `${sessionPath()}/conversations/${encodeURIComponent(cid)}`,
      "GET",
    ],
    ask: (cid) => [
      `${sessionPath()}/conversations/${encodeURIComponent(cid)}/messages`,
      "POST",
    ],
    practice: (cid) => [
      `${sessionPath()}/conversations/${encodeURIComponent(cid)}/attempts`,
      "POST",
    ],
    deleteConversation: (cid) => [
      `${sessionPath()}/conversations/${encodeURIComponent(cid)}`,
      "DELETE",
    ],
    share: () => [`${sessionPath()}/shares`, "POST"],
    contributions: () => [`${sessionPath()}/shares`, "GET"],
    withdraw: (id) => [
      `${sessionPath()}/shares/${encodeURIComponent(id)}`,
      "DELETE",
    ],
    shareConsentUpdate: (id) => [
      `${sessionPath()}/shares/${encodeURIComponent(id)}`,
      "PATCH",
    ],
    insights: () => [`${sessionPath()}/insights`, "GET"],
    materials: () => [`${sessionPath()}/materials`, "GET"],
    editorial: () => [`${sessionPath()}/materials`, "POST"],
    material: (id) => [
      `${sessionPath()}/materials/${encodeURIComponent(id)}`,
      "GET",
    ],
    version: (id) => [
      `${sessionPath()}/materials/${encodeURIComponent(id)}/versions`,
      "POST",
    ],
    approve: (id) => [
      `${sessionPath()}/materials/${encodeURIComponent(id)}/approve`,
      "POST",
    ],
    publish: (id) => [
      `${sessionPath()}/materials/${encodeURIComponent(id)}/publish`,
      "POST",
    ],
    materialStatus: (id) => [
      `${sessionPath()}/materials/${encodeURIComponent(id)}/status`,
      "POST",
    ],
    stage: () => [
      `/api/public/${encodeURIComponent(state.session?.joinCode || state.joinCode)}`,
      "GET",
    ],
    p6Readings: (query = "") => [`${sessionPath()}/readings${query}`, "GET"],
    p6ReadingCreate: () => [`${sessionPath()}/readings`, "POST"],
    p6Reading: (id) => [`${sessionPath()}/readings/${encodeURIComponent(id)}`, "PATCH"],
    p6ReadingSubmit: (id) => [`${sessionPath()}/readings/${encodeURIComponent(id)}/submit`, "POST"],
    p6ReadingWithdraw: (id) => [`${sessionPath()}/readings/${encodeURIComponent(id)}/withdraw`, "POST"],
    p6ReadingReview: (query = "") => [`${sessionPath()}/reading-review${query}`, "GET"],
    p6ReadingGroups: () => [`${sessionPath()}/reading-groups`, "POST"],
    p6ReadingGroup: (id) => [`${sessionPath()}/reading-groups/${encodeURIComponent(id)}`, "GET"],
    p6ReadingPresentations: (query = "") => [`${sessionPath()}/reading-presentations${query}`, "GET"],
    p6ReadingPresentationCreate: () => [`${sessionPath()}/reading-presentations`, "POST"],
    p6ReadingPresentationVersion: (id) => [`${sessionPath()}/reading-presentations/${encodeURIComponent(id)}/versions`, "POST"],
    p6ReadingPresentationAction: (id, action) => [`${sessionPath()}/reading-presentations/${encodeURIComponent(id)}/${action}`, "POST"],
    p6PublicReadings: () => [`/api/public/${encodeURIComponent(state.session?.joinCode || state.joinCode)}/readings`, "GET"],
    p6Coactivities: (query = "") => [`${sessionPath()}/coactivities${query}`, "GET"],
    p6CoactivityCreate: () => [`${sessionPath()}/coactivities`, "POST"],
    p6Coactivity: (id) => [`${sessionPath()}/coactivities/${encodeURIComponent(id)}`, "GET"],
    p6CoactivityPatch: (id) => [`${sessionPath()}/coactivities/${encodeURIComponent(id)}`, "PATCH"],
    p6CoactivityAction: (id, action) => [`${sessionPath()}/coactivities/${encodeURIComponent(id)}/${action}`, "POST"],
    p6CoactivityActions: (id) => [`${sessionPath()}/coactivities/${encodeURIComponent(id)}/actions`, "POST"],
    p6CoactivityShare: (id, action) => [`${sessionPath()}/coactivities/${encodeURIComponent(id)}/${action}`, "POST"],
    p6CoactivityShares: (query = "") => [`${sessionPath()}/coactivity-shares${query}`, "GET"],
    p6CoactivityShareRevoke: (id) => [`${sessionPath()}/coactivity-shares/${encodeURIComponent(id)}/revoke`, "POST"],
    p6Inquiries: (query = "") => [`${sessionPath()}/inquiries${query}`, "GET"],
    p6InquiryCreate: () => [`${sessionPath()}/inquiries`, "POST"],
    p6Inquiry: (id) => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}`, "GET"],
    p6InquiryPatch: (id) => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}`, "PATCH"],
    p6InquiryActions: (id) => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}/actions`, "POST"],
    p6NextExamination: (id) => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}/next-examination`, "POST"],
    p6NextExaminationGenerate: (id) => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}/generate-next-examination`, "POST"],
    p6InquiryObservations: (id, query = "") => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}/observations${query}`, "GET"],
    p6InquiryObservationCreate: (id) => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}/observations`, "POST"],
    p6InquiryObservationRevoke: (id, oid) => [`${sessionPath()}/inquiries/${encodeURIComponent(id)}/observations/${encodeURIComponent(oid)}/revoke`, "POST"],
    p6InquiryPresentations: (query = "") => [`${sessionPath()}/inquiry-presentations${query}`, "GET"],
    p6InquiryPresentationCreate: () => [`${sessionPath()}/inquiry-presentations`, "POST"],
    p6InquiryPresentationVersion: (id) => [`${sessionPath()}/inquiry-presentations/${encodeURIComponent(id)}/versions`, "POST"],
    p6InquiryPresentationAction: (id, action) => [`${sessionPath()}/inquiry-presentations/${encodeURIComponent(id)}/${action}`, "POST"],
    p6PublicInquiries: () => [`/api/public/${encodeURIComponent(state.session?.joinCode || state.joinCode)}/inquiries`, "GET"],
    p6Projects: (query = "") => [`${sessionPath()}/projects${query}`, "GET"],
    p6ProjectCreate: () => [`${sessionPath()}/projects`, "POST"],
    p6ProjectLinkRequests: (query = "") => [`${sessionPath()}/project-link-requests${query}`, "GET"],
    p6ProjectLinkApprove: (id) => [`${sessionPath()}/project-links/${encodeURIComponent(id)}/approve`, "POST"],
    p6ProjectLinkRevoke: (id) => [`${sessionPath()}/project-links/${encodeURIComponent(id)}/revoke`, "POST"],
    p6Project: (id) => [`${sessionPath()}/projects/${encodeURIComponent(id)}`, "GET"],
    p6ProjectProposals: (id, query = "") => [`${sessionPath()}/projects/${encodeURIComponent(id)}/proposals${query}`, "GET"],
    p6ProjectProposalCreate: (id) => [`${sessionPath()}/projects/${encodeURIComponent(id)}/proposals`, "POST"],
    p6ProjectProposalWithdraw: (id, proposalId) => [`${sessionPath()}/projects/${encodeURIComponent(id)}/proposals/${encodeURIComponent(proposalId)}/withdraw`, "POST"],
    p6OwnerProject: (id) => [`/api/projects/${encodeURIComponent(id)}`, "GET"],
    p6OwnerProjectHistory: (id, query = "") => [`/api/projects/${encodeURIComponent(id)}/history${query}`, "GET"],
    p6OwnerProjectProposals: (id, query = "") => [`/api/projects/${encodeURIComponent(id)}/proposals${query}`, "GET"],
    p6ProjectLinks: (id, query = "") => [`/api/projects/${encodeURIComponent(id)}/links${query}`, "GET"],
    p6ProjectLinkCreate: (id) => [`/api/projects/${encodeURIComponent(id)}/links`, "POST"],
    p6ProjectLinkRevokeOwner: (id, linkId) => [`/api/projects/${encodeURIComponent(id)}/links/${encodeURIComponent(linkId)}/revoke`, "POST"],
    p6OwnerProposalAction: (id, proposalId, action) => [`/api/projects/${encodeURIComponent(id)}/proposals/${encodeURIComponent(proposalId)}/${action}`, "POST"],
    p6ExportGrants: (query = "") => [`${sessionPath()}/export-grants${query}`, "GET"],
    p6ReadingGrant: () => [`${sessionPath()}/reading-export-grants`, "POST"],
    p6ObservationGrant: () => [`${sessionPath()}/observation-export-grants`, "POST"],
    p6GrantAction: (id, action) => [`${sessionPath()}/export-grants/${encodeURIComponent(id)}/${action}`, "POST"],
    p6ProjectImports: (id, query = "") => [`${sessionPath()}/projects/${encodeURIComponent(id)}/imports${query}`, "GET"],
    p6ProjectImport: (id) => [`${sessionPath()}/projects/${encodeURIComponent(id)}/imports`, "POST"],
    p6ProjectImportRevoke: (id, importId) => [`${sessionPath()}/projects/${encodeURIComponent(id)}/imports/${encodeURIComponent(importId)}/revoke`, "POST"],
    p6ResolveProjectRef: (id) => [`${sessionPath()}/projects/${encodeURIComponent(id)}/resolve-reference`, "POST"],
    p6OwnerResolveProjectRef: (id) => [`/api/projects/${encodeURIComponent(id)}/resolve-reference`, "POST"],
    p10TimelineIndex: () => [`${sessionPath()}/p10/timeline/index`, "POST"],
    p10Timeline: (sourceId) => [`${sessionPath()}/p10/timeline?sourceId=${encodeURIComponent(sourceId)}`, "GET"],
    p10TimelineQuery: () => [`${sessionPath()}/p10/timeline/query`, "POST"],
    p10VisualCompare: () => [`${sessionPath()}/p10/visual/compare`, "POST"],
    p10VisualExplanations: () => [`${sessionPath()}/p10/visual/explanations`, "GET"],
    p10VisualExplanationCreate: () => [`${sessionPath()}/p10/visual/explanations`, "POST"],
    w23InstalledVoices: () => [`${sessionPath()}/w23/speech/installed-voices`, 'GET'],
    w23CreatorProfile: id => [`${sessionPath()}/w23/speech/profiles/${encodeURIComponent(id)}`, 'GET'],
    w23CreatorProfileSave: id => [`${sessionPath()}/w23/speech/profiles/${encodeURIComponent(id)}`, 'PUT'],
    w23CreatorProfileApprove: id => [`${sessionPath()}/w23/speech/profiles/${encodeURIComponent(id)}/approval`, 'PUT'],
    w23Profiles: () => [`${sessionPath()}/w23/speech/profiles`, 'GET'],
    w23SelectionGet: () => [`${sessionPath()}/w23/speech/selection`, 'GET'],
    w23SelectionPut: () => [`${sessionPath()}/w23/speech/selection`, 'PUT'],
    w29QualityList: () => [`${sessionPath()}/w29/quality/list`, 'POST'],
    w29QualityChoose: () => [`${sessionPath()}/w29/quality/choose`, 'POST'],
    w30SavedTranslations: () => [`${sessionPath()}/p12/operations?after=0&limit=100`, 'GET'],
    w26TerminologyInspect: () => [`${sessionPath()}/w26/terminology/inspect`, 'POST'],
    w25PreferencesGet: editionId => [`${sessionPath()}/w25/listening/preferences${editionId ? `?editionId=${encodeURIComponent(editionId)}` : ''}`, 'GET'],
    w25PreferencesPut: editionId => [`${sessionPath()}/w25/listening/preferences${editionId ? `?editionId=${encodeURIComponent(editionId)}` : ''}`, 'PUT'],
    w25ListeningPreload: () => [`${sessionPath()}/w25/listening/preload`, 'POST'],
    w23ProfileOperation: id => [`${sessionPath()}/w23/speech/operations/${encodeURIComponent(id)}`, 'GET'],
    w23GenerationPrepare: () => [`${sessionPath()}/w23/speech/generation/prepare`, 'POST'],
    w23GenerationGet: (runId, requestId) => [`${sessionPath()}/w23/speech/generation/${encodeURIComponent(runId)}/${encodeURIComponent(requestId)}`, 'GET'],
    w23MomentSearch: () => [`${sessionPath()}/w23/moments/search`, 'POST'],
    w23MomentDestination: () => [`${sessionPath()}/w23/moments/destination`, 'POST'],
    w27MomentTrail: () => [`${sessionPath()}/w27/moments/trail`, 'POST'],
    w27ChapterCommit: () => [`${sessionPath()}/w27/chapters/commits`, 'POST'],
    w27ChapterReceipt: id => [`${sessionPath()}/w27/chapters/receipts/${encodeURIComponent(id)}`, 'GET'],
    w27ChapterRecovery: (id, revision, version) => [`${sessionPath()}/w27/chapters/recovery/${encodeURIComponent(id)}/${revision}/${version}`, 'GET'],
    p10Frame: (query) => [`${sessionPath()}/p10/frame?${query}`, "GET"],
    p10StudioCreate: () => [`${sessionPath()}/p10/studio/materials`, "POST"],
    p10StudioMaterials: () => [`${sessionPath()}/p10/studio/materials`, "GET"],
    p10StudioMaterial: (id) => [`${sessionPath()}/p10/studio/materials/${encodeURIComponent(id)}`, "GET"],
    p10StudioPatch: (id) => [`${sessionPath()}/p10/studio/materials/${encodeURIComponent(id)}`, "PATCH"],
    p10StudioPreview: (id) => [`${sessionPath()}/p10/studio/materials/${encodeURIComponent(id)}/preview`, "POST"],
    p10StudioAction: (id, action) => [`${sessionPath()}/p10/studio/materials/${encodeURIComponent(id)}/${action}`, "POST"],
    p10RetentionGrants: () => [`${sessionPath()}/p10/retention-grants`, "POST"],
    p10RetentionGrantLookup: (query) => [`${sessionPath()}/p10/retention-grants${query}`, "GET"],
    p10RetentionGrantDelete: (id) => [`${sessionPath()}/p10/retention-grants/${encodeURIComponent(id)}`, "DELETE"],
    p10SessionOperation: (id) => [`${sessionPath()}/p10/operations/${encodeURIComponent(id)}`, "GET"],
    p10VaultCreate: () => ["/api/p10/vaults", "POST"],
    p10VaultEntries: () => ["/api/p10/vault/entries", "GET"],
    p10VaultEntryCreate: () => ["/api/p10/vault/entries", "POST"],
    p10VaultEntry: (id) => [`/api/p10/vault/entries/${encodeURIComponent(id)}`, "PATCH"],
    p10VaultEntryDelete: (id) => [`/api/p10/vault/entries/${encodeURIComponent(id)}`, "DELETE"],
    p10VaultQuery: () => ["/api/p10/vault/query", "POST"],
    p10VaultResume: () => ["/api/p10/vault/resume", "POST"],
    p10VaultOperation: (id) => [`/api/p10/operations/${encodeURIComponent(id)}`, "GET"],
    p10Representation: () => [`${sessionPath()}/p10/representations`, "POST"],
    w14Formats: () => [`${sessionPath()}/w14/formats`, "GET"],
    w14AdaptFormat: (id) => [`${sessionPath()}/w14/formats/${encodeURIComponent(id)}`, "PATCH"],
    w14CreateFormat: () => [`${sessionPath()}/w14/formats`, "POST"],
    w14ContributeFormat: (id) => [`${sessionPath()}/w14/formats/${encodeURIComponent(id)}/contributions`, "POST"],
    w14AcceptContribution: (id) => [`${sessionPath()}/w14/format-contributions/${encodeURIComponent(id)}/accept`, "POST"],
    w14OfferFormat: (id) => [`${sessionPath()}/w14/formats/${encodeURIComponent(id)}/transfer`, "POST"],
    w14FormatTransfers: () => [`${sessionPath()}/w14/format-transfers`, "GET"],
    w14AcceptTransfer: (id) => [`${sessionPath()}/w14/format-transfers/${encodeURIComponent(id)}/accept`, "POST"],
    w14DeclineTransfer: (id) => [`${sessionPath()}/w14/format-transfers/${encodeURIComponent(id)}/decline`, "POST"],
    w14WithdrawTransfer: (id) => [`${sessionPath()}/w14/format-transfers/${encodeURIComponent(id)}/withdraw`, "POST"],
    w19LibraryCatalog: () => [`${sessionPath()}/w19/library`, "GET"],
    w19LibraryValidate: () => [`${sessionPath()}/w19/library/check`, "POST"],
    w19LibraryImport: () => [`${sessionPath()}/w19/library/import`, "POST"],
    w19OwnedLibraryExport: id => [`${sessionPath()}/w19/library/export/${encodeURIComponent(id)}`, "GET"],
    w19_20Receipt: () => [`${sessionPath()}/w19_20/receipt`, "POST"],
    w19Inbox: () => [`${sessionPath()}/w19/inbox`, "GET"],
    w19InboxAnswers: () => [`${sessionPath()}/w19/inbox/answers`, "GET"],
    w19InboxCreate: () => [`${sessionPath()}/w19/inbox/groups`, "POST"],
    w19InboxEdit: id => [`${sessionPath()}/w19/inbox/groups/${encodeURIComponent(id)}`, "PATCH"],
    w19InboxAnswer: id => [`${sessionPath()}/w19/inbox/groups/${encodeURIComponent(id)}/answer`, "POST"],
    w20CreatorPracticeShare: id => [`${sessionPath()}/w20/practice/shares/${encodeURIComponent(id)}`, "GET"],
    w20PracticeContinuations: () => [`${sessionPath()}/w20/practice/continuations`, "GET"],
    w20PriorAttempts: () => [`${sessionPath()}/w20/practice/prior-attempts`, "POST"],
    w20BridgeCreate: () => [`${sessionPath()}/w20/bridges`, "POST"],
    w20BridgeRevoke: id => [`${sessionPath()}/w20/bridges/${encodeURIComponent(id)}`, "DELETE"],
    w20PracticeDiscovery: () => [`${sessionPath()}/w20/practice/discovery`, "GET"],
    w20PracticeAttempt: id => [`${sessionPath()}/w20/practice/continuations/${encodeURIComponent(id)}/attempts`, "POST"],
    w20PracticeCreate: () => [`${sessionPath()}/w20/practice/continuations`, "POST"],
    w20PracticeReview: (id, attemptId) => [`${sessionPath()}/w20/practice/continuations/${encodeURIComponent(id)}/attempts/${encodeURIComponent(attemptId)}/review`, "POST"],
    w20PracticeRevoke: (id, shareId) => [`${sessionPath()}/w20/practice/continuations/${encodeURIComponent(id)}/shares/${encodeURIComponent(shareId)}/revoke`, "POST"],
    w20PracticeShare: id => [`${sessionPath()}/w20/practice/continuations/${encodeURIComponent(id)}/shares`, "POST"],
    w20PolicyGet: () => [`${sessionPath()}/w20/policy`, "GET"],
    w20PolicySave: () => [`${sessionPath()}/w20/policy`, "POST"],
    w20PolicyAdmit: () => [`${sessionPath()}/w20/policy/admit`, "POST"],
    w20DeliveryAdmit: () => [`${sessionPath()}/w20/delivery`, "POST"],
    w20DeliveryReceipt: () => [`${sessionPath()}/w20/delivery/receipt`, "POST"],
    w21VisualSource: () => [`${sessionPath()}/w21/visual-source`, "POST"],
    w21VisualGround: () => [`${sessionPath()}/w21/visual/ground`, "POST"],
    w21VisualReceipt: id => [`${sessionPath()}/w21/visual/requests/${encodeURIComponent(id)}`, "GET"],
    w21ImpactPreview: () => [`${sessionPath()}/w21/impact/preview`, "POST"],
    w21ImpactChange: () => [`${sessionPath()}/w21/impact/changes`, "POST"],
    w21ImpactRequest: id => [`${sessionPath()}/w21/impact/requests/${encodeURIComponent(id)}`, "GET"],
    w21ImpactRecovery: id => [`${sessionPath()}/w21/impact/recovery/${encodeURIComponent(id)}`, "GET"],
    w21ImpactGet: id => [`${sessionPath()}/w21/impact/changes/${encodeURIComponent(id)}`, "GET"],
    w21ImpactSpeechReplacement: id => [`${sessionPath()}/w21/impact/changes/${encodeURIComponent(id)}/speech-replacement`, "POST"],
    w21ImpactCaptionReplacement: id => [`${sessionPath()}/w21/impact/changes/${encodeURIComponent(id)}/caption-replacement`, "POST"],
    w21ImpactMaterialReplacement: id => [`${sessionPath()}/w21/impact/changes/${encodeURIComponent(id)}/material-replacement`, "POST"],
    w21ImpactRecordReplacement: id => [`${sessionPath()}/w21/impact/changes/${encodeURIComponent(id)}/record-replacement`, "POST"],
    w21SpeechRun: id => [`${sessionPath()}/w21/speech/runs/${encodeURIComponent(id)}`, "GET"],
    w21SpeechCreate: () => [`${sessionPath()}/w21/speech/runs`, "POST"],
    w21SpeechChunk: id => [`${sessionPath()}/w21/speech/runs/${encodeURIComponent(id)}/chunks`, "POST"],
    w21SpeechRules: id => [`${sessionPath()}/w21/speech/rules/${encodeURIComponent(id)}`, "GET"],
    w21SpeechRulesCreate: () => [`${sessionPath()}/w21/speech/rules`, "POST"],
    w21SpeechRulesUpdate: id => [`${sessionPath()}/w21/speech/rules/${encodeURIComponent(id)}`, "PUT"],
    w21SpeechRevise: id => [`${sessionPath()}/w21/speech/runs/${encodeURIComponent(id)}/revise`, "POST"],
    w21SpeechFinalize: id => [`${sessionPath()}/w21/speech/runs/${encodeURIComponent(id)}/finalize`, "POST"],
    w21SpeechPreview: id => [`${sessionPath()}/w21/speech/runs/${encodeURIComponent(id)}/preview`, "POST"],
    w26MeaningInspect: () => [`${sessionPath()}/w26/meaning/inspect`, "POST"],
    w26VisualAssociations: () => [`${sessionPath()}/w26/visual-associations/list`, "POST"],
    w26MeaningFlag: () => [`${sessionPath()}/w26/meaning/flags`, "POST"],
    w22Claims: () => [`${sessionPath()}/w22/claims`, "POST"],
    w22ModelShares: () => [`${sessionPath()}/w22/models/shares`, "GET"],
    w22ModelOwnedShares: () => [`${sessionPath()}/w22/models/owned-shares`, "GET"],
    w22ModelApprovals: () => [`${sessionPath()}/w22/models/approvals`, "GET"],
    w22ModelApprove: () => [`${sessionPath()}/w22/models/approvals`, "POST"],
    w22ModelApprovalRevoke: id => [`${sessionPath()}/w22/models/approvals/${encodeURIComponent(id)}/revoke`, "POST"],
    w22Models: () => [`${sessionPath()}/w22/models`, "GET"],
    w22ModelReceipts: () => [`${sessionPath()}/w22/models/receipts`, "GET"],
    w22ModelMutate: () => [`${sessionPath()}/w22/models`, "POST"],
    w22CoeditRead: id => [`${sessionPath()}/w22/coedit/drafts/${encodeURIComponent(id)}?cursor=0&schemaVersion=1`, "GET"],
    w28HandoffScope: id => [`${sessionPath()}/w28/handoffs/${encodeURIComponent(id)}/scope`, "GET"],
    w28HandoffRead: id => [`${sessionPath()}/w28/handoffs/${encodeURIComponent(id)}`, "GET"],
    w28HandoffOffer: id => [`${sessionPath()}/w28/handoffs/${encodeURIComponent(id)}/offer`, "POST"],
    w28HandoffDecide: id => [`${sessionPath()}/w28/handoffs/${encodeURIComponent(id)}/decide`, "POST"],
    w28HandoffReceipt: (id, requestId) => [`${sessionPath()}/w28/handoffs/${encodeURIComponent(id)}/receipts/${encodeURIComponent(requestId)}`, "GET"],
    w22CoeditPresence: id => [`${sessionPath()}/w22/coedit/drafts/${encodeURIComponent(id)}/presence`, "POST"],
    w22CoeditOperation: (id, requestId) => [`${sessionPath()}/w22/coedit/drafts/${encodeURIComponent(id)}/operations/${encodeURIComponent(requestId)}`, "GET"],
    w22CoeditGrants: () => [`${sessionPath()}/w22/coedit/grants`, "GET"],
    w22CoeditGrantCreate: () => [`${sessionPath()}/w22/coedit/grants`, "POST"],
    w22CoeditGrantRevoke: id => [`${sessionPath()}/w22/coedit/grants/${encodeURIComponent(id)}/revoke`, "POST"],
    w22CoeditDraftCreate: () => [`${sessionPath()}/w22/coedit/drafts`, "POST"],
    w22CoeditPatch: id => [`${sessionPath()}/w22/coedit/drafts/${encodeURIComponent(id)}/patch`, "POST"],
    w22CoeditApprove: id => [`${sessionPath()}/w22/coedit/drafts/${encodeURIComponent(id)}/approve`, "POST"],
    w22CoeditAdopt: id => [`${sessionPath()}/w22/coedit/drafts/${encodeURIComponent(id)}/adopt`, "POST"],
    w22CoeditWithdraw: id => [`${sessionPath()}/w22/coedit/drafts/${encodeURIComponent(id)}/withdraw`, "POST"],
    w20DeliverySources: () => [`${sessionPath()}/w20/delivery-sources`, "GET"],
    w20DeliveryView: id => [`${sessionPath()}/w20/delivery/${encodeURIComponent(id)}`, "GET"],
    w20DeliveryCancel: id => [`${sessionPath()}/w20/delivery/${encodeURIComponent(id)}`, "DELETE"],
    w19OperatorState: () => [`${sessionPath()}/w19/operator/state`, "GET"],
    w19Readiness: () => [`${sessionPath()}/w19/readiness`, "GET"],
    w13Questions: () => [`${sessionPath()}/w13/questions`, "GET"],
    w13ShareQuestion: () => [`${sessionPath()}/w13/questions`, "POST"],
    w13SelectQuestion: (id) => [`${sessionPath()}/w13/questions/${encodeURIComponent(id)}/select`, "POST"],
    w13UnselectQuestion: (id) => [`${sessionPath()}/w13/questions/${encodeURIComponent(id)}/unselect`, "POST"],
    w13CorrectQuestion: (id) => [`${sessionPath()}/w13/questions/${encodeURIComponent(id)}`, "PATCH"],
    w13AnswerQuestion: (id) => [`${sessionPath()}/w13/questions/${encodeURIComponent(id)}/answer`, "POST"],
    w13WithdrawQuestion: (id) => [`${sessionPath()}/w13/questions/${encodeURIComponent(id)}`, "DELETE"],
    w15Cues: () => [`${sessionPath()}/w15/cues`, "GET"],
    w15CueCreate: () => [`${sessionPath()}/w15/cues`, "POST"],
    w15CueAction: (id) => [`${sessionPath()}/w15/cues/${encodeURIComponent(id)}/action`, "POST"],
    w15CueOperation: (key) => [`${sessionPath()}/w15/cue-operations/${encodeURIComponent(key)}`, "GET"],
    w14Breaks: () => [`${sessionPath()}/w14/breaks`, "GET"],
    w14CreateBreak: () => [`${sessionPath()}/w14/breaks`, "POST"],
    w14Prepare: () => [`${sessionPath()}/w14/interventions`, "POST"],
    w14ProductionAction: (id) => [`${sessionPath()}/w14/interventions/${encodeURIComponent(id)}/action`, "POST"],
    w14Reasons: () => [`${sessionPath()}/w14/reasons`, "GET"],
    w14ShareReason: () => [`${sessionPath()}/w14/reasons`, "POST"],
    w14CorrectReason: (id) => [`${sessionPath()}/w14/reasons/${encodeURIComponent(id)}/corrections`, "POST"],
    w14WithdrawReason: (id) => [`${sessionPath()}/w14/reasons/${encodeURIComponent(id)}`, "DELETE"],
    w14Decision: () => [`${sessionPath()}/w14/decisions`, "POST"],
    w13Models: () => [`${sessionPath()}/w13/models`, "GET"],
    w13CreateModel: () => [`${sessionPath()}/w13/models`, "POST"],
    w13ReviseModel: (id) => [`${sessionPath()}/w13/models/${encodeURIComponent(id)}`, "PATCH"],
    w13WithdrawModel: (id) => [`${sessionPath()}/w13/models/${encodeURIComponent(id)}`, "DELETE"],
    w13DemonstrateModel: (id) => [`${sessionPath()}/w13/models/${encodeURIComponent(id)}/demonstrate`, "POST"],
    w13EvaluateModel: (id) => [`${sessionPath()}/w13/models/${encodeURIComponent(id)}/evaluate`, "POST"],
    p12CollabGet: (path) => [`${sessionPath()}/p12/${path}`, "GET"],
    p12CollabPost: (path) => [`${sessionPath()}/p12/${path}`, "POST"],
    p11Create: () => [`${sessionPath()}/activities`, "POST"],
    p11List: () => [`${sessionPath()}/activities`, "GET"],
    p11Read: (aid) => [`${sessionPath()}/activities/${encodeURIComponent(aid)}`, "GET"],
    p11Get: (aid, part) => [`${sessionPath()}/activities/${encodeURIComponent(aid)}/${part}`, "GET"],
    p11Post: (aid, part) => [`${sessionPath()}/activities/${encodeURIComponent(aid)}/${part}`, "POST"],
    p11Public: (aid) => [`/api/public/activities/${encodeURIComponent(aid)}`, "GET"],
  };
  async function call(key, body, ...args) {
    const requestOptions =
      args.at(-1)?.signal || args.at(-1)?.scope || args.at(-1)?.headers ? args.pop() : {};
    const scope = requestOptions.scope || identityScope();
    assertIdentity(scope);
    // These operations can lose their only request identity on reload. Preserve
    // the read and exact-preview paths for tab-only review, but never dispatch
    // a journal-dependent mutation or generation without saved access.
    if (tabOnlyAccess && new Set(["addSource", "addBookmark", "deleteBookmark", "addNotebookItem", "deleteNotebookItem", "insights", "editorial", "p10TimelineIndex", "p10TimelineQuery", "p10VisualCompare", "p10VisualExplanationCreate", "w27ChapterCommit", "p10StudioCreate", "p10StudioPatch", "p10StudioAction", "p10RetentionGrants", "p10RetentionGrantDelete", "p10Representation", "p10VaultCreate", "p10VaultEntryCreate", "p10VaultEntry", "p10VaultEntryDelete", "p10VaultQuery", "p10VaultResume", "w13ShareQuestion", "w13CorrectQuestion", "w13WithdrawQuestion", "w13SelectQuestion", "w13UnselectQuestion", "w13AnswerQuestion"]).has(key)) {
      const error = new Error("Saved access is required for request recovery");
      error.code = "saved_access_required";
      error.status = 400;
      throw error;
    }
    if (key === "p10StudioPatch" || key === "p10StudioAction" || key === "p10StudioCreate") cueController?.invalidate();
    const route =
      typeof routes[key] === "function" ? routes[key](...args) : routes[key];
    if (!route || route[0].includes("undefined"))
      throw new Error("session_required");
    const [path, method] = route;
    // Existing source, sharing and participation mutations can revoke a selected dependency.
    if (method !== "GET" && /^(sourceUpdate|p10RetentionGrantDelete|w13(?:Share|Select|Unselect|Correct|Answer|Withdraw)Question|w15(?:Edit|Withdraw|Accept)Contribution|w15(?:EditFormat|FormatDecision|EditChapter|RevokeSourceGrant|AcceptFormatTransfer|WithdrawFormatTransfer)|w17TransitionTemplateRound|w18RecordVersion|w18RecordApprove|w18RecordWithdraw)$/.test(key)) {
      wave19Library?.reset(); wave20Practice?.reset(); w20CreatorClear(); wave20Delivery?.reset(); wave21Speech?.reset(); wave21Visual?.reset(); wave21ImpactPreview?.reset(); wave23Moments?.reset(); wave22ClaimsViewer?.reset(); wave22ClaimsCreator?.reset(); wave22Coedit?.reset(); wave22ModelHistory?.reset(); wave22ModelShares?.reset(); wave22ModelWithdrawals?.reset(); wave20Policy?.reset(); wave19Entry?.reset(); wave19Setup?.reset(); wave19Inbox?.reset(); wave19Answers?.reset(); wave19Operator?.reset(); wave18Segment?.reset(); wave18Assistance?.reset(); wave18CreatorRecord?.reset(); wave18ViewerRecord?.reset(); wave22EditionReader?.reset(); wave22DescriptionCreator?.reset();
    }
    // Bind credentials to the identity captured by the caller. Never combine a
    // stale action with whichever bearer happens to be current now.
    const token = key === "stage" || key === "p11Public" || key === "p6PublicReadings" || key === "p6PublicInquiries" || key === "p10VaultCreate" ? null : scope.token;
    const headers = { Accept: "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (requestOptions.headers) Object.assign(headers, requestOptions.headers);
    if (body != null && !(body instanceof FormData))
      headers["Content-Type"] = "application/json";
    const timeoutSignal = AbortSignal.timeout(120000);
    const controller = new AbortController();
    pending.add(controller);
    const signals = [timeoutSignal, controller.signal];
    if (requestOptions.signal) signals.push(requestOptions.signal);
    const signal = AbortSignal.any(signals);
    try {
      const response = await fetch(path, {
        method,
        credentials: "same-origin",
        headers,
        signal,
        body:
          body == null
            ? undefined
            : body instanceof FormData
              ? body
              : JSON.stringify(body),
      });
      // Ignore late responses from a previous identity before interpreting status.
      assertIdentity(scope);
      const data =
        response.status === 204 ? {} : await response.json().catch(() => ({}));
      assertIdentity(scope);
      if (!response.ok) {
        if (key === 'w22CoeditPatch' && response.status === 409 && data?.operation?.state === 'conflict' && data?.draft) return data;
        if (key.startsWith("w18") && [401, 403, 404].includes(response.status)) {
          wave19Library?.reset(); wave20Practice?.reset(); w20CreatorClear(); wave20Delivery?.reset(); wave21Speech?.reset(); wave21Visual?.reset(); wave21ImpactPreview?.reset(); wave23Moments?.reset(); wave22ClaimsViewer?.reset(); wave22ClaimsCreator?.reset(); wave22Coedit?.reset(); wave22ModelHistory?.reset(); wave22ModelShares?.reset(); wave22ModelWithdrawals?.reset(); wave20Policy?.reset(); wave19Entry?.reset(); wave19Setup?.reset(); wave19Inbox?.reset(); wave19Answers?.reset(); wave19Operator?.reset(); wave18Segment?.reset(); wave18Assistance?.reset(); wave18CreatorRecord?.reset(); wave18ViewerRecord?.reset(); wave22EditionReader?.reset(); wave22DescriptionCreator?.reset();
        }
        const detail = data.error || {};
        const e = new Error(
          detail.code === "busy" ? "Generation is busy. This request was not started; retry when ready." : detail.code === "session_call_limit" ? "Session generation limit reached." : detail.message || detail.code || `http_${response.status}`,
        );
        e.status = response.status;
        e.code = detail.code;
        e.result = data;
        throw e;
      }
      assertIdentity(scope);
      return requestOptions.captureHeaders ? { ...data, headers: response.headers } : data;
    } finally {
      pending.delete(controller);
    }
  }
  async function momentImage(body, scope) {
    assertIdentity(scope);
    const controller = new AbortController(); pending.add(controller);
    try {
      const response = await fetch(`${sessionPath()}/w23/moments/image`, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { Authorization: `Bearer ${scope.token}`, 'Content-Type': 'application/json', Accept: 'image/png, image/jpeg, image/webp' },
        body: JSON.stringify(body), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(120000)])
      });
      assertIdentity(scope);
      if (!response.ok || !['image/png', 'image/jpeg', 'image/webp'].includes(response.headers.get('content-type'))) throw Error('Moment image unavailable');
      const blob = await response.blob(); assertIdentity(scope);
      if (!blob.size || blob.size > 4 * 1024 * 1024) throw Error('Moment image unavailable');
      return blob;
    } finally { pending.delete(controller); }
  }
  return {
    call, momentImage,
    abortAll: () => pending.forEach((controller) => controller.abort()),
  };
})();

const translations = {
  es: {
    skip: "Saltar al contenido",
    connecting: "Conectando…",
    language: "Idioma",
    workspace: "ESPACIO DE TRABAJO",
    navAudience: "Acompañante",
    navPractice: "Práctica",
    navStudio: "Estudio editorial",
    navStage: "En emisión",
    sessionActive: "SESIÓN ACTIVA",
    loadingSession: "Cargando sesión…",
    sessionSettings: "Ajustes de sesión →",
    privateDefault: "Tu conversación es privada por defecto.",
    liveCompanion: "ACOMPAÑANTE EN DIRECTO",
    audienceTitle: "Entiende lo que está pasando.",
    audienceLead:
      "Pregunta en privado. La respuesta usa el contexto que la sesión realmente recibió.",
    private: "Privado",
    contextLabel: "Contexto de la sesión",
    contextLoading: "Consultando fuentes disponibles…",
    welcomeTitle: "Empecemos por tu duda.",
    welcomeBody:
      "Puedes preguntar por una idea, un momento del directo o un paso que no te quedó claro. No necesitas compartir nada.",
    questionLabel: "Tu pregunta",
    questionPlaceholder: "¿Qué te gustaría entender?",
    onlyYou: "Solo tú ves esta conversación",
    send: "Preguntar",
    shareTitle: "¿Quieres llevar una idea al creador?",
    shareLead:
      "Tú decides qué aportación compartir, siempre de forma voluntaria.",
    shareExplain:
      "Revisa exactamente qué se enviará antes de confirmarlo. Tu conversación privada no se comparte automáticamente.",
    shareWhat: "Aportación que quieres compartir",
    sharePlaceholder: "Escribe solo lo que quieres que el creador reciba",
    shareConsent:
      "Confirmo que quiero compartir este texto con el creador para que pueda considerarlo al preparar el directo.",
    shareButton: "Revisar y compartir",
    practiceEyebrow: "APRENDE HACIENDO",
    practiceTitle: "Prueba una idea en tu trabajo.",
    practiceLead:
      "Define qué intentas resolver y recibe una orientación basada en el contexto disponible.",
    goalLabel: "¿Qué intentas conseguir?",
    goalPlaceholder: "Por ejemplo: entender por qué mi solución se atasca",
    difficultyLabel: "¿Qué te está costando?",
    diffConcept: "Entender el concepto",
    diffNext: "Saber cuál es el siguiente paso",
    diffDiagnose: "Encontrar qué falla",
    diffRefine: "Mejorar lo que ya hice",
    attemptLabel: "Cuéntame qué has probado hasta ahora",
    attemptPlaceholder: "Describe tu intento con tus propias palabras",
    attachments: "Adjuntos opcionales",
    attachmentHelp:
      "Texto y archivos solo según las modalidades que admita esta sesión.",
    addFile: "Añadir archivo",
    getHint: "Pedir una pista",
    practiceHistory: "Tus intentos",
    privateHistory: "Solo tú puedes verlos",
    historyEmpty: "Tus orientaciones y reintentos aparecerán aquí.",
    creatorWorkspace: "ESPACIO DEL CREADOR",
    studioTitle: "Prepara algo que valga compartir.",
    studioLead:
      "Revisa aportaciones autorizadas y decide qué merece entrar en tu programa.",
    refresh: "Actualizar",
    "EDITORIAL DESK": "MESA EDITORIAL",
    builderTitle: "Elabora una intervención",
    creatorControls: "Control del creador",
    builderLead:
      "Selecciona aportaciones autorizadas para darles contexto y preparar una pieza utilizable.",
    formatLabel: "Formato",
    formatExplanation: "Explicación",
    formatComparison: "Comparación",
    formatQuestion: "Pregunta para la audiencia",
    formatExample: "Ejemplo",
    formatDemonstration: "Demostración",
    formatVisual: "Material visual",
    focusLabel: "Enfoque editorial (opcional)",
    focusPlaceholder: "¿Qué quieres que se lleve la audiencia?",
    createDraft: "Preparar borrador",
    studioLoading: "Cargando aportaciones compartidas…",
    publicSurface: "SUPERFICIE PÚBLICA",
    stageTitle: "En emisión.",
    stageLead:
      "Esta vista muestra únicamente una intervención aprobada y publicada por el creador.",
    public: "Público",
    stageEmpty:
      "No hay ninguna intervención aprobada y publicada para mostrar.",
    stageEmptyHint:
      "Aprobar una pieza no la publica: aparecerá aquí sólo después de aprobarla y publicarla.",
    captureTitle: "Contexto del directo",
    manageSources: "Gestión de fuentes",
    captureLead:
      "La captura solo empieza tras una acción explícita del creador y se puede detener en cualquier momento.",
    captureStopped: "Captura detenida",
    startCapture: "Iniciar captura",
    stopCapture: "Detener",
    sessionSetup: "SESIÓN",
    sessionDetails: "Detalles de la sesión",
    channelLabel: "Canal o creador",
    purposeLabel: "Propósito del directo",
    materialsLabel: "Materiales de referencia (enlaces o texto)",
    cancel: "Cancelar",
    saveSession: "Guardar sesión",
    sourcesTitle: "Fuentes disponibles",
    sourceNote:
      "Las respuestas distinguen el contexto recibido de lo que todavía no se sabe.",
    askFailed:
      "No se pudo obtener una respuesta del servicio. Tu pregunta sigue aquí; comprueba la conexión e inténtalo de nuevo.",
    requestPending:
      "La acción pudo guardarse, pero la respuesta no llegó. Reintentar conservará la misma solicitud.",
    requestInterrupted:
      "El servicio aún está recuperando esta acción. No se creó otra solicitud; inténtalo más tarde o edita el texto para empezar una acción distinta.",
    imageReselect:
      "Para reintentar este envío, vuelve a elegir la misma imagen. El archivo no se guarda en este dispositivo.",
    shareReviewChanged:
      "La selección cambió después de la revisión. Revisa de nuevo el contenido y los permisos antes de compartir.",
    practiceFailed:
      "No se pudo obtener una evaluación del servicio. Tu borrador sigue aquí para reintentar.",
    shareFailed:
      "No se pudo compartir la aportación. Tu texto sigue en el formulario.",
    studioFailed:
      "No se pudieron cargar las aportaciones. Comprueba la conexión e inténtalo de nuevo.",
    editorialFailed:
      "No se pudo elaborar el borrador. No se ha generado contenido de demostración.",
    captureFailed: "No se pudo cambiar el estado de captura.",
    sessionFailed: "No se pudo guardar la sesión.",
    retry: "Reintentar",
    networkReady: "Servicio conectado",
    networkDown: "Servicio sin conexión",
    drafting: "Preparando…",
    sending: "Enviando…",
    response: "Respuesta",
    you: "Tú",
    sources: "Fuentes",
    insufficient: "Contexto insuficiente",
    contextCorrection: "Corregir contexto",
    contextCorrectionLabel: "¿Qué dato o referencia debería corregirse?",
    sendCorrection: "Enviar corrección",
    shareReviewTitle: "Vista previa de lo que se enviará",
    confirmShare: "Confirmar y compartir",
    editShare: "Seguir editando",
    shared: "Aportación compartida",
    withdraw: "Retirar",
    withdrawn: "Aportación retirada",
    noContributions: "Aún no hay aportaciones compartidas.",
    oneContribution: "aportación autorizada",
    manyContributions: "aportaciones autorizadas",
    reason: "Motivo de selección",
    frequency: "Frecuencia",
    sourcePrivate: "Origen privado",
    anonymous: "Anónimo",
    selectContribution: "Selecciona al menos una aportación compartida.",
    draftTitle: "Borrador editorial",
    editorialTitleLabel: "Título de la pieza",
    draftEditable: "Puedes editar este borrador antes de decidir.",
    editorialOutputHint:
      "La salida pública es un Browser Source local. OBS, Twitch y la emisión requieren un paso de conexión aparte.",
    approve: "Aprobar versión",
    postpone: "Posponer",
    reject: "Descartar",
    variant: "Solicitar variante",
    variantDirection: "¿Qué enfoque alternativo quieres explorar?",
    saveEdit: "Guardar cambios",
    approved: "Intervención aprobada",
    postponed: "Intervención pospuesta",
    rejected: "Intervención descartada",
    stageFailed: "No se pudo consultar el contenido aprobado.",
    captureRunning: "Captura activa",
    captureStopped: "Captura detenida",
    captureStarted: "Captura iniciada",
    captureEnded: "Captura detenida",
    sessionSaved: "Sesión actualizada",
    contextEmpty: "La sesión todavía no ha recibido fuentes de contexto.",
    contextRefreshSuccess: "La última actualización del contexto terminó correctamente.",
    contextRefreshFailed: "Falló la actualización. Se muestra la última lista de fuentes recibida; el estado y los permisos actuales no están confirmados.",
    contextRefreshFailedNoSnapshot: "Falló la actualización del contexto. No hay una lista actual de fuentes disponible.",
    contextRefreshUnknown: "El estado de actualización del contexto no está disponible.",
    contextRefreshShort: "Falló la actualización del contexto.",
    contextReportedAt: "Última actualización de fuentes reportada: ",
    contextRefreshing: "Actualizando contexto…",
    contextRefreshButton: "Actualizar contexto",
    noPurpose: "Añade el propósito para orientar mejor las respuestas.",
    fileUnsupported:
      "La modalidad de este archivo no está confirmada por el servicio. Puedes describir su contenido en texto.",
    required: "Completa este campo.",
    genericError: "Algo salió mal. Inténtalo de nuevo.",
    connectionError:
      "El servicio todavía no está disponible. Los borradores no se han perdido.",
    accessEyebrow: "ACCESO LOCAL",
    accessTitle: "Entra a una sesión",
    viewerTab: "Tengo un código",
    creatorTab: "Soy creador",
    sessionIdLabel: "ID de sesión",
    joinCodeLabel: "Código de sesión",
    displayNameLabel: "Nombre visible (opcional)",
    sessionTitleLabel: "Nombre del directo",
    localCreateNote: "Crear sesión solo está disponible en instalación local.",
    joinSession: "Entrar",
    createSession: "Crear sesión",
    accessFailed:
      "No se pudo verificar este acceso o permiso. Inicia sesión con tu acceso vigente o pide al propietario de la sesión que lo revise.",
    joinFailed:
      "No se pudo usar esta invitación. Revisa el ID de sesión y el código; pudieron vencer o reemplazarse, o la sesión podría no estar disponible. Si hace falta, pide al creador una invitación actual. Unirte de nuevo crea un espacio privado separado; no restaura el trabajo de un acceso anterior.",
    renewedInviteKeepsViewers: "Renovar cambia el código y el vencimiento de la invitación; quienes ya tienen acceso vigente conservan su historial privado.",
    renewedInviteNewIdentity: "Una nueva entrada crea un historial privado separado. Un nombre, código o enlace no puede restaurar un acceso perdido o revocado.",
    renewInvitation: "Renovar invitación",
    rotateInvitation: "Rotar y revocar acceso de audiencia",
    refreshInvitationState: "Actualizar estado de invitación y enlaces",
    invitationUrlLabel: "Enlace de invitación para nuevas entradas",
    invitationUrlUnavailable: "Enlace público no configurado; comparte el ID y el código actuales.",
    invitationRenewConfirm: "¿Renovar la invitación? Cambiará el código anterior y el vencimiento de la invitación, no el vencimiento de la sesión. La audiencia con acceso vigente conservará su acceso; las nuevas entradas tendrán un historial privado separado. Cada renovación deliberada crea otro código.",
    rotateInvitationConfirm: "¿Rotar la invitación y revocar el acceso de audiencia? Esto reemplaza la invitación y cierra el acceso de quienes ya entraron. Los registros privados se conservan; los enlaces anteriores dejarán de funcionar.",
    invitationRenewSuccess: "Invitación renovada. Comparte la invitación y la URL de Browser Source actualizadas.",
    invitationRotateSuccess: "Invitación rotada. Se revocó el acceso anterior; comparte la invitación y la URL de Browser Source actualizadas.",
    invitationRefreshStarted: "Consultando la invitación y los enlaces actuales…",
    invitationRefreshSuccess: "Se actualizó el estado de la invitación y sus enlaces.",
    invitationRefreshUnknown: "No se pudo confirmar el estado actual de la invitación. Los valores visibles podrían estar desactualizados. Actualiza el estado antes de otra acción de ciclo de vida.",
    captureConsentEyebrow: "CAPTURA MANUAL",
    captureConsentTitle: "Añade contexto con permiso",
    captureConsentLead:
      "La imagen o nota que elijas se guardará como fuente de contexto. No se captura pantalla ni audio automáticamente.",
    captureTitleLabel: "Título",
    captureTextLabel: "Nota de contexto (opcional)",
    captureImageLabel: "Imagen elegida por ti (PNG, JPEG o WebP; hasta 4 MB)",
    captureConsentCheck:
      "Confirmo que tengo autorización para compartir este contenido en la sesión.",
    submitCapture: "Añadir contexto",
    captureNoContent: "Añade una nota o elige una imagen.",
    sourceAdded: "Contexto añadido",
    authRequired: "Entra con un código o crea una sesión para continuar.",
    shareSourceLabel: "Aportación privada a resumir",
    shareLastQuestion: "Mi última pregunta",
    shareLastAttempt: "Mi último intento de práctica",
    sharePublicConsent:
      "También autorizo que se use en una pieza editorial pública. Puedo retirar este permiso después.",
    materialsAudienceConsent:
      "Permito que estas fuentes orienten conversaciones privadas de la audiencia.",
    captureAudienceConsent:
      "Permito que esta fuente oriente conversaciones privadas de la audiencia.",
    mySharesTitle: "Mis aportaciones compartidas",
    withdrawMine: "Retirar mi aportación",
    publicConsentRevoked: "Permiso público retirado",
    connectTwitch: "Conectar metadatos de Twitch →",
    twitchConnected: "Metadatos de Twitch conectados",
    twitchUnavailable:
      "No fue posible conectar Twitch. Las fuentes de contexto locales siguen disponibles.",
    connectionLabel: "Conexión del canal",
    copyJoinCode: "Copiar código de audiencia →",
    stageUrlLabel: "URL pública para Browser Source",
    copyUrl: "Copiar URL",
    publish: "Mostrar en salida pública",
    published: "Versión pública actualizada",
    reviewMaterial: "Revisar",
    providerUnavailable:
      "El proveedor de IA no está disponible; no se generó contenido.",
    diagnosticsUnknown: "No se pudo verificar el estado del proveedor ni de la transcripción.",
    providerUnknown: "Proveedor de IA configurado; aún sin verificar",
    providerReady: "Proveedor de IA disponible",
    providerError:
      "La elaboración no pudo validar el formato generado. El backend debe informar o corregir esta respuesta.",
    noShareSource:
      "Comparte después de enviar una pregunta o completar un intento de práctica.",
    chooseScreen: "Elegir pantalla o ventana",
    captureFrame: "Capturar fotograma",
    stopScreen: "Detener captura de pantalla",
    screenSharing: "Pantalla compartida temporalmente",
    frameCaptured: "Fotograma capturado; comparte sólo al confirmar.",
    screenUnsupported: "Este navegador no permite captura de pantalla.",
    visualUnavailable:
      "El proveedor no confirma lectura de imágenes. Describe el contenido en texto; no enviaremos el archivo al modelo.",
    visualCapabilityUnknown: "No se pudo verificar la capacidad visual. Las cargas de imágenes están desactivadas.",
    visionReady:
      "El proveedor indica que puede recibir imágenes; la respuesta mostrará si el contenido pudo interpretarse.",
  },
  en: {
    skip: "Skip to content",
    connecting: "Connecting…",
    language: "Language",
    workspace: "WORKSPACE",
    navAudience: "Companion",
    navPractice: "Practice",
    navStudio: "Editorial studio",
    navStage: "On air",
    sessionActive: "ACTIVE SESSION",
    loadingSession: "Loading session…",
    sessionSettings: "Session settings →",
    privateDefault: "Your conversation is private by default.",
    liveCompanion: "LIVE COMPANION",
    audienceTitle: "Understand what is happening.",
    audienceLead:
      "Ask privately. Answers use the context this session actually received.",
    private: "Private",
    contextLabel: "Session context",
    contextLoading: "Checking available sources…",
    welcomeTitle: "Start with your question.",
    welcomeBody:
      "Ask about an idea, a moment in the stream, or a step that was unclear. You do not need to share anything.",
    questionLabel: "Your question",
    questionPlaceholder: "What would you like to understand?",
    onlyYou: "Only you can see this conversation",
    send: "Ask",
    shareTitle: "Would you like to bring an idea to the creator?",
    shareLead: "You choose what to share, and sharing is always optional.",
    shareExplain:
      "Review exactly what will be sent before you confirm. Your private conversation is never shared automatically.",
    shareWhat: "The contribution you want to share",
    sharePlaceholder: "Write only what you want the creator to receive",
    shareConsent:
      "I choose to share this text with the creator so they can consider it while preparing the stream.",
    shareButton: "Review and share",
    practiceEyebrow: "LEARN BY DOING",
    practiceTitle: "Try an idea in your own work.",
    practiceLead:
      "Describe what you are working through and get guidance based on available context.",
    goalLabel: "What are you trying to achieve?",
    goalPlaceholder: "For example: understand why my solution gets stuck",
    difficultyLabel: "What feels difficult?",
    diffConcept: "Understanding the concept",
    diffNext: "Knowing the next step",
    diffDiagnose: "Finding what is wrong",
    diffRefine: "Improving what I have done",
    attemptLabel: "Tell us what you have tried so far",
    attemptPlaceholder: "Describe your attempt in your own words",
    attachments: "Optional attachments",
    attachmentHelp:
      "Text and files depend on the modalities this session supports.",
    addFile: "Add files",
    getHint: "Get a hint",
    practiceHistory: "Your attempts",
    privateHistory: "Only you can see these",
    historyEmpty: "Your guidance and retries will appear here.",
    creatorWorkspace: "CREATOR WORKSPACE",
    studioTitle: "Prepare something worth sharing.",
    studioLead:
      "Review authorized contributions and decide what belongs in your program.",
    refresh: "Refresh",
    "EDITORIAL DESK": "EDITORIAL DESK",
    builderTitle: "Prepare an intervention",
    creatorControls: "Creator controlled",
    builderLead:
      "Select authorized contributions to contextualize and prepare a usable piece.",
    formatLabel: "Format",
    formatExplanation: "Explanation",
    formatComparison: "Comparison",
    formatQuestion: "Audience question",
    formatExample: "Example",
    formatDemonstration: "Demonstration",
    formatVisual: "Visual material",
    focusLabel: "Editorial focus (optional)",
    focusPlaceholder: "What should the audience take away?",
    createDraft: "Prepare draft",
    studioLoading: "Loading shared contributions…",
    publicSurface: "PUBLIC SURFACE",
    stageTitle: "On air.",
    stageLead:
      "This view shows only an intervention approved and published by the creator.",
    public: "Public",
    stageEmpty: "There is no approved and published intervention to show.",
    stageEmptyHint:
      "Approval does not publish a piece: it appears here only after the creator approves and publishes it.",
    captureTitle: "Live context",
    manageSources: "Manage sources",
    captureLead:
      "Capture starts only after an explicit action by the creator and can be stopped at any time.",
    captureStopped: "Capture stopped",
    startCapture: "Start capture",
    stopCapture: "Stop",
    sessionSetup: "SESSION",
    sessionDetails: "Session details",
    channelLabel: "Channel or creator",
    purposeLabel: "Stream purpose",
    materialsLabel: "Reference materials (links or text)",
    cancel: "Cancel",
    saveSession: "Save session",
    sourcesTitle: "Available sources",
    sourceNote:
      "Answers distinguish received context from what is still unknown.",
    askFailed:
      "The service could not provide an answer. Your question is still here; check the connection and retry.",
    requestPending:
      "The action may have been saved, but its response did not arrive. Retrying will reuse the same request.",
    requestInterrupted:
      "The service is still recovering this action. No new request was created; try later or edit the text to start a different action.",
    imageReselect:
      "To retry this submission, choose the same image again. The file is not stored on this device.",
    shareReviewChanged:
      "The selection changed after review. Review the content and permissions again before sharing.",
    practiceFailed:
      "The service could not provide feedback. Your draft is still here to retry.",
    shareFailed:
      "The contribution could not be shared. Your text remains in the form.",
    studioFailed:
      "Contributions could not be loaded. Check the connection and retry.",
    editorialFailed:
      "The draft could not be prepared. No demo content was generated.",
    captureFailed: "The capture state could not be changed.",
    sessionFailed: "The session could not be saved.",
    retry: "Retry",
    networkReady: "Service connected",
    networkDown: "Service unavailable",
    drafting: "Preparing…",
    sending: "Sending…",
    response: "Response",
    you: "You",
    sources: "Sources",
    insufficient: "Insufficient context",
    contextCorrection: "Correct context",
    contextCorrectionLabel: "What detail or reference should be corrected?",
    sendCorrection: "Send correction",
    shareReviewTitle: "Preview what will be sent",
    confirmShare: "Confirm and share",
    editShare: "Keep editing",
    shared: "Contribution shared",
    withdraw: "Withdraw",
    withdrawn: "Contribution withdrawn",
    noContributions: "No shared contributions yet.",
    oneContribution: "authorized contribution",
    manyContributions: "authorized contributions",
    reason: "Selection reason",
    frequency: "Frequency",
    sourcePrivate: "Private source",
    anonymous: "Anonymous",
    selectContribution: "Select at least one shared contribution.",
    draftTitle: "Editorial draft",
    editorialTitleLabel: "Piece title",
    draftEditable: "You can edit this draft before deciding.",
    editorialOutputHint:
      "The public output is a local Browser Source. Connecting OBS and Twitch and starting a broadcast are separate steps.",
    approve: "Approve version",
    postpone: "Postpone",
    reject: "Discard",
    variant: "Request a variation",
    variantDirection: "What alternative angle would you like to explore?",
    saveEdit: "Save edits",
    approved: "Intervention approved",
    postponed: "Intervention postponed",
    rejected: "Intervention discarded",
    stageFailed: "Approved content could not be loaded.",
    captureRunning: "Capture active",
    captureStopped: "Capture stopped",
    captureStarted: "Capture started",
    captureEnded: "Capture stopped",
    sessionSaved: "Session updated",
    contextEmpty: "The session has not received context sources yet.",
    contextRefreshSuccess: "The latest context refresh succeeded.",
    contextRefreshFailed: "Refresh failed. Showing the last received source list; current status and permissions are unconfirmed.",
    contextRefreshFailedNoSnapshot: "Context refresh failed. No current source list is available.",
    contextRefreshUnknown: "Context refresh status is unavailable.",
    contextRefreshShort: "Context refresh failed.",
    contextReportedAt: "Latest source update reported: ",
    contextRefreshing: "Refreshing context…",
    contextRefreshButton: "Refresh context",
    noPurpose: "Add the purpose to better guide responses.",
    fileUnsupported:
      "Support for this file type is not confirmed by the service. You can describe its contents in text.",
    required: "Complete this field.",
    genericError: "Something went wrong. Please try again.",
    connectionError:
      "The service is not available yet. Your drafts have not been lost.",
    accessEyebrow: "LOCAL ACCESS",
    accessTitle: "Join a session",
    viewerTab: "Viewer · join with a code",
    creatorTab: "Creator · start locally",
    sessionIdLabel: "Session ID",
    joinCodeLabel: "Session code",
    displayNameLabel: "Display name (optional)",
    sessionTitleLabel: "Stream title",
    localCreateNote: "Session creation is available only in local deployments.",
    joinSession: "Join session",
    createSession: "Create session",
    accessFailed:
      "This access or permission could not be verified. Sign in with your current access or ask the session owner to review it.",
    joinFailed:
      "This invitation could not be used. Check the session ID and code; they may have expired or been replaced, or the session may be unavailable. Ask the creator for a current invitation if needed. Joining again creates separate private history; it does not restore work from a previous access.",
    renewedInviteKeepsViewers: "Renewing changes the invitation code and deadline; viewers with valid existing access keep their private history.",
    renewedInviteNewIdentity: "A new join creates separate private history. A name, code, or link cannot restore a lost or revoked viewer access.",
    renewInvitation: "Renew invitation",
    rotateInvitation: "Rotate and revoke viewer access",
    refreshInvitationState: "Refresh invitation and URL status",
    invitationUrlLabel: "Invitation link for new joins",
    invitationUrlUnavailable: "Public invitation link is not configured; share the current session ID and code.",
    invitationRenewConfirm: "Renew the invitation? This replaces the old code and invitation deadline, not the session expiry. Existing viewers keep their current access; new joins get separate private history. Each deliberate renewal creates another code.",
    rotateInvitationConfirm: "Rotate and revoke viewer access? This replaces the invitation and signs out every current viewer. Private records remain stored; old viewer links will no longer open them.",
    invitationRenewSuccess: "Invitation renewed. Share the updated invitation and Browser Source URL.",
    invitationRotateSuccess: "Invitation rotated. Existing viewer access was revoked; share the updated invitation and Browser Source URL.",
    invitationRefreshStarted: "Checking the current invitation and URL…",
    invitationRefreshSuccess: "Invitation and URL status refreshed.",
    invitationRefreshUnknown: "Could not confirm the current invitation state. The last displayed values may be stale. Refresh status before taking another lifecycle action.",
    captureConsentEyebrow: "MANUAL CAPTURE",
    captureConsentTitle: "Add context with permission",
    captureConsentLead:
      "The image or note you choose will be saved as session context. No screen or audio is captured automatically.",
    captureTitleLabel: "Title",
    captureTextLabel: "Context note (optional)",
    captureImageLabel: "Image you choose (PNG, JPEG or WebP; up to 4 MB)",
    captureConsentCheck:
      "I confirm I am authorized to share this content in the session.",
    submitCapture: "Add context",
    captureNoContent: "Add a note or choose an image.",
    sourceAdded: "Context added",
    authRequired: "Join with a code or create a session to continue.",
    shareSourceLabel: "Private contribution to summarize",
    shareLastQuestion: "My latest question",
    shareLastAttempt: "My latest practice attempt",
    sharePublicConsent:
      "I also allow this to be used in a public editorial piece. I can withdraw this permission later.",
    materialsAudienceConsent:
      "Allow these sources to guide private audience conversations.",
    captureAudienceConsent:
      "Allow this source to guide private audience conversations.",
    mySharesTitle: "My shared contributions",
    withdrawMine: "Withdraw my contribution",
    publicConsentRevoked: "Public use permission withdrawn",
    connectTwitch: "Connect Twitch metadata →",
    twitchConnected: "Twitch metadata connected",
    twitchUnavailable:
      "Twitch could not be connected. Local context sources remain available.",
    connectionLabel: "Channel connection",
    copyJoinCode: "Copy invitation →",
    stageUrlLabel: "Public Browser Source URL",
    copyUrl: "Copy URL",
    publish: "Show in public output",
    published: "Public version updated",
    reviewMaterial: "Review",
    providerUnavailable:
      "The AI provider is unavailable; no content was generated.",
    diagnosticsUnknown: "Provider and transcription status could not be verified.",
    providerUnknown: "AI provider configured; not yet verified",
    providerReady: "AI provider available",
    providerError:
      "The generated format failed validation. The backend must report or correct this response.",
    noShareSource:
      "Share after sending a question or completing a practice attempt.",
    chooseScreen: "Choose screen or window",
    captureFrame: "Capture frame",
    stopScreen: "Stop screen sharing",
    screenSharing: "Screen shared temporarily",
    frameCaptured: "Frame captured; it will be shared only after confirmation.",
    screenUnsupported: "Screen capture is not available in this browser.",
    visualUnavailable:
      "The provider has not confirmed image understanding. Describe the content in text; the file will not be sent to the model.",
    visualCapabilityUnknown: "Image support could not be verified. Image uploads are disabled.",
    visionReady:
      "The provider reports image input support; the answer will state whether it interpreted the content.",
  },
};
Object.assign(translations.es, {
  shareIncludeImage:
    "Incluir imagen en la aportación al creador; el permiso público sigue separado.",
  startMic: "Grabar audio",
  stopMic: "Detener audio",
  audioRecorded: "Audio listo para enviar",
  asrUnavailable: "La transcripción no está disponible; el audio no se envió.",
  asrReady: "Transcripción disponible",
  sourceRetracted: "Fuente retirada",
  staleError: "Esta pieza cambió. Actualiza y revísala otra vez.",
  timeoutError: "La operación tardó demasiado. El borrador sigue guardado.",
  groundedNo: "La respuesta indica contexto insuficiente.",
  materialsAudienceConsent:
    "Permitir que la audiencia de la sesión lea esta fuente completa como contexto.",
  captureAudienceConsent:
    "Permitir que la audiencia de la sesión lea esta fuente completa como contexto.",
  audioConsent:
    "Acepto capturar este audio y enviar segmentos separados al servicio de transcripción.",
  audioAudience:
    "Permito que la audiencia lea completa cada fuente transcrita. Desactivado por defecto.",
  selectedSource: "Todas las fuentes de texto vigentes",
  momentLabel: "Momento específico (opcional)",
  audioIdle: "Audio capture is off.",
  audioPending: "Transcribing queued audio…",
  audioDelayed:
    "Transcription is delayed; pending segments are shown.",
  audioError: "Audio capture or transcription failed.",
  noSpeech: "No speech was detected; no source was created.",
  publicAccess: "ID y código de audiencia",
  publicConsentNeeded:
    "Requiere permiso de uso editorial público de todas las aportaciones.",
  liveAudioTitle: "Audio del directo",
  liveAudioConsentLead:
    "El audio se enviará al servicio para transcribirlo. Si autorizas a la audiencia, podrá leer completa cada transcripción compartida.",
  audioSourceLabel: "Fuente de audio",
  audioMicrophone: "Micrófono",
  audioDisplay: "Audio de pestaña o pantalla compartida",
  startAudio: "Iniciar audio",
  stopAudio: "Detener audio",
});
Object.assign(translations.en, {
  shareIncludeImage:
    "Include the image with the creator contribution; public permission remains separate.",
  startMic: "Record audio",
  stopMic: "Stop audio",
  audioRecorded: "Audio ready to send",
  asrUnavailable: "Transcription is unavailable; the audio was not sent.",
  asrReady: "Transcription available",
  sourceRetracted: "Source withdrawn",
  staleError: "This piece changed. Refresh and review it again.",
  timeoutError: "The operation took too long. Your draft is still saved.",
  groundedNo: "The answer reports insufficient context.",
  materialsAudienceConsent:
    "Allow the session audience to read this complete source as context.",
  captureAudienceConsent:
    "Allow the session audience to read this complete source as context.",
  audioConsent:
    "I agree to capture this audio and send separate segments to the transcription service.",
  audioAudience:
    "Allow the audience to read each complete transcript source. Off by default.",
  selectedSource: "All current text sources",
  momentLabel: "Specific moment (optional)",
  audioIdle: "Audio capture is off.",
  audioPending: "Transcribing queued audio…",
  audioDelayed: "Transcription is delayed; pending segments are shown.",
  audioError: "Audio capture or transcription failed.",
  noSpeech: "No speech was detected; no source was created.",
  publicAccess: "Audience ID and code",
  publicConsentNeeded:
    "Public editorial permission is required for every contribution.",
  liveAudioTitle: "Live audio",
  liveAudioConsentLead:
    "Audio is sent to the service for transcription. If you allow the audience, it can read each complete shared transcript.",
  audioSourceLabel: "Audio source",
  audioMicrophone: "Microphone",
  audioDisplay: "Audio from a shared tab or screen",
  startAudio: "Start audio",
  stopAudio: "Stop audio",
});
translations.en.identityTitle = "Identity";
translations.en.contextView = "View session context";
translations.en.exactSource = "Specific source";
translations.en.close = "Close";
translations.en.selectedFrame = "Selected frame";
Object.assign(translations.es, { identityTitle: "Identidad", contextView: "Ver contexto de la sesión", exactSource: "Fuente específica", close: "Cerrar", selectedFrame: "Fotograma seleccionado", brandHome: "Undertone, inicio", mainNavigation: "Navegación principal" });
Object.assign(translations.en, { brandHome: "Undertone, home", mainNavigation: "Main navigation" });
const state = {
  identityEpoch: 0,
  lang: ["en", "es"].includes(localStorage.getItem("entrelineas.lang"))
    ? localStorage.getItem("entrelineas.lang")
    : "en",
  session: null,
  sessionId: null,
  joinCode: null,
  token: null,
  role: null,
  viewerId: null,
  conversationId: null,
  practiceConversationId: null,
  context: null,
  questionSourceChoices: [],
  selectedFiles: [],
  contributions: [],
  insights: [],
  materials: [],
  captureSourceId: null,
  screenStream: null,
  screenImage: null,
  liveAudio: null,
  liveAudioState: null,
  captureEpoch: 0,
  lastPracticeImage: null,
  providers: [],
  diagnosticsAvailable: null,
  visionSupported: false,
  history: [],
  lastAttemptId: null,
  retryFromAttemptId: null,
  lastMessageId: null,
  nextCorrection: null,
  conversationRendered: false,
  renderedMessageIds: new Set(),
  sourceRefreshTimer: null,
  connectionRefreshTimer: null,
  audioUiTimer: null,
  audioStartedAt: 0,
  audioNoSpeech: false,
  pendingQuestionAction: null,
  pendingPracticeAction: null,
  shareReviewSnapshot: null,
  catchupSnapshot: null,
  catchupRecap: null,
  pendingCatchupRecapAction: null,
  activity: null,
  notebookItems: [],
  pendingPracticeActivity: null,
};
let phase6Controller = null;
let resumeAccess = null, tabOnlyAccess = false, tabOnlyExpiryTimer = null;
let phase10Controller = null;
let wave27Chapters = null;
let phase11Controller = null;
let wave15Viewer = null, wave15Creator = null, wave15Formats = null;
let wave17Return = null, wave17Templates = null;
let wave22EditionReader = null, wave22DescriptionCreator = null;
let wave18Segment = null, wave18Assistance = null, wave18CreatorRecord = null, wave18ViewerRecord = null;
let phase12Controller = null;
let wave22ClaimsViewer = null, wave22ClaimsCreator = null, wave22Coedit = null, wave22ModelHistory = null, wave22ModelShares = null, wave22ModelWithdrawals = null, wave22ModelExploration = null;
let wave23Moments = null, wave26Terms = null;
let wave19Answers = null, wave19Entry = null, wave19Setup = null, wave19Inbox = null, wave19Operator = null, wave19Library = null, wave20Practice = null, wave20Delivery = null, wave20Policy = null, wave21Speech = null, wave21Visual = null, wave21ImpactPreview = null;
let waveModelPreview = null, wavePublishedModels = null, waveDrafts = null, waveReasons = null, waveProduction = null, waveQuestions = null, waveFormats = null;
let collaborationController = null;
let cueController = null;
function identityScope() {
  return {
    epoch: state.identityEpoch,
    sessionId: state.sessionId,
    role: state.role,
    viewerId: state.viewerId,
    actorBinding: capabilityNamespace,
    token: state.token,
  };
}
function assertIdentity(scope) {
  if (
    scope.epoch !== state.identityEpoch ||
    scope.sessionId !== state.sessionId ||
    scope.role !== state.role ||
    scope.viewerId !== state.viewerId ||
    (scope.actorBinding && scope.actorBinding !== capabilityNamespace) ||
    scope.token !== state.token
  ) {
    throw new DOMException("Identity changed", "AbortError");
  }
}
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const t = (key) => translations[state.lang]?.[key] || translations.en[key] || key;
const escapeHtml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
function setBusy(button, busy, label) {
  if (busy && !button.dataset.label) {
    button.dataset.label = button.innerHTML;
    button.dataset.disabledBeforeBusy = String(button.disabled);
  }
  button.disabled = busy;
  if (busy)
    button.innerHTML = escapeHtml(
      label || button.dataset.label || button.textContent,
    );
  if (!busy) {
    if (button.dataset.label !== undefined)
      button.innerHTML = button.dataset.label;
    button.disabled = button.dataset.disabledBeforeBusy === "true";
    delete button.dataset.label;
    delete button.dataset.disabledBeforeBusy;
  }
}
function showError(el, message) {
  el.textContent = message;
  el.hidden = false;
}
function clearError(el) {
  el.hidden = true;
  el.textContent = "";
}
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  delete el.dataset.contextRefreshFailure;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3200);
}
function contextRefreshFailureToast(message) {
  toast(message);
  $("#toast").dataset.contextRefreshFailure = "true";
}
function clearContextRefreshFailureToast() {
  const el = $("#toast");
  if (el.dataset.contextRefreshFailure !== "true") return;
  clearTimeout(toast.timer);
  el.classList.remove("show");
  el.textContent = "";
  delete el.dataset.contextRefreshFailure;
}
function setConnection(online) {
  const el = $("#connection");
  el.className = `connection ${online ? "online" : "offline"}`;
  el.querySelector("span").textContent = online
    ? t("networkReady")
    : t("networkDown");
}
function applyLanguage() {
  document.documentElement.lang = state.lang;
  $("#language").value = state.lang;
  $$("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    el.textContent = t(key);
  });
  $$('[data-i18n-aria-label]').forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel)));
  $$('[data-i18n-title]').forEach((el) => el.setAttribute("title", t(el.dataset.i18nTitle)));
  $$('[data-i18n-alt]').forEach((el) => el.setAttribute("alt", t(el.dataset.i18nAlt)));
  $$("[data-placeholder]").forEach(
    (el) => (el.placeholder = t(el.dataset.placeholder)),
  );
  $("#question").setAttribute("aria-label", t("questionLabel"));
  $("#questionMoment").setAttribute("aria-label", t("momentLabel"));
  renderSession();
  renderContributions();
  renderHistory();
  updateVisualCapabilities();
  renderProviderState();
  renderStage().catch(() => {});
}
function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (data == null) return [];
  return (
    data.items ||
    data.results ||
    data.data ||
    data.conversations ||
    data.sources ||
    data.shares ||
    data.materials ||
    data.attempts ||
    data.messages ||
    []
  );
}
function renderContextFreshness() {
  const status = $("#contextFreshness");
  if (!status) return;
  const context = state.context || {};
  const reported = context.updatedAt ? new Date(context.updatedAt) : null;
  const reportedText = reported && Number.isFinite(reported.valueOf())
    ? t("contextReportedAt") + reported.toLocaleString(state.lang === "es" ? "es-MX" : "en-US")
    : "";
  if (sourceContextStale) {
    const hasSnapshot = normalizeList(context.sources || context).length > 0;
    status.textContent = hasSnapshot
      ? t("contextRefreshFailed") + (reportedText ? " " + reportedText : "")
      : t("contextRefreshFailedNoSnapshot");
    return;
  }
  if (sourceContextLastRefreshAt) {
    const refreshed = new Date(sourceContextLastRefreshAt).toLocaleTimeString(state.lang === "es" ? "es-MX" : "en-US");
    status.textContent = t("contextRefreshSuccess") + " " + refreshed + (reportedText ? " " + reportedText : "");
  } else status.textContent = t("contextRefreshUnknown");
}
function renderSession() {
  const s = state.session || {};
  $("#channelName").textContent =
    s.channel || s.creator_name || t("loadingSession");
  $("#sessionPurpose").textContent = s.purpose || t("noPurpose");
  $("#sessionChannel").value = s.channel || s.creator_name || "";
  $("#sessionPurposeInput").value = s.purpose || "";
  $("#sessionMaterials").value = "";
  $("#joinCodeDisplay").textContent =
    state.role === "creator" && state.joinCode
      ? `${state.lang === "es" ? "ID" : "ID"}: ${state.sessionId} · ${state.lang === "es" ? "Código" : "Code"}: ${state.joinCode}`
      : "";
  const deadline = Date.parse(s.lifecycle?.invitationExpiresAt || "");
  const invitationExpired = Number.isFinite(deadline) && deadline <= Date.now();
  const expiredNotice = state.lang === "es" ? "La invitación venció. Renuévala para permitir nuevas entradas." : "Invitation expired. Renew it to allow new joins.";
  const invitationUrl = state.session?.invitationUrl || "";
  $("#invitationUrlValue").textContent = invitationExpired ? expiredNotice : invitationUrl || t("invitationUrlUnavailable");
  const code = state.session?.joinCode || state.joinCode;
  const preview = $("#localPreviewInvitation");
  if (state.role === "creator" && state.sessionId && code && !invitationExpired) {
    const url = new URL(location.pathname, location.origin);
    url.searchParams.set("sessionId", state.sessionId);
    url.searchParams.set("joinCode", code);
    preview.href = url.href; preview.textContent = url.href;
  } else { preview.removeAttribute("href"); preview.textContent = invitationExpired ? expiredNotice : "—"; }
  const localStageUrl = code
    ? new URL("/public/" + encodeURIComponent(code), location.origin).toString()
    : "—";
  $("#stageUrlValue").textContent = state.session?.publicUrl || localStageUrl;
  const c = state.context || {};
  const sources = normalizeList(c.sources || c);
  // Clarification DTOs are partial. Only current authorized source records
  // determine selectable options and survive a refresh.
  const selectableSources = sources.filter(source => source?.id && source.status === "active");
  $("#contextSummary").textContent = sources.length
    ? `${sources.length} ${state.lang === "es" ? "fuentes recibidas" : "sources received"}${c.updatedAt ? ` · ${new Date(c.updatedAt).toLocaleTimeString()}` : ""}`
    : t("contextEmpty");
  if (sourceContextStale) $("#contextSummary").textContent += " · " + t("contextRefreshShort");
  renderContextFreshness();
  $("#contextSources").innerHTML = sources.length
    ? sources
        .map(
          (x) =>
            `<article class="source-item" data-source-id="${escapeHtml(x.id || "")}"><strong>${escapeHtml(x.title || x.kind || x.type || "Source")} · ${escapeHtml(x.status || "active")} · ${escapeHtml(x.audienceVisible ? (state.lang === "es" ? "visible para audiencia" : "audience visible") : state.lang === "es" ? "privada" : "private")}</strong><p>${escapeHtml(x.text || x.url || "")}</p><div class="contribution-meta">${escapeHtml(x.kind || x.type || "")}${x.at ? ` · ${escapeHtml(x.at)}` : ""}${x.createdAt ? ` · ${escapeHtml(new Date(x.createdAt).toLocaleString())}` : ""}</div>${state.role === "viewer" && x.status === "active" ? `<button type="button" class="button secondary bookmark-source" data-id="${escapeHtml(x.id)}">Save source</button>` : ""}${state.role === "creator" ? `<label class="check-line"><input type="checkbox" class="source-visible" data-id="${escapeHtml(x.id)}" ${x.audienceVisible ? "checked" : ""}><span>${escapeHtml(t("materialsAudienceConsent"))}</span></label><button type="button" class="button danger source-retract" data-id="${escapeHtml(x.id)}">${escapeHtml(t("withdraw"))}</button>` : ""}</article>`,
        )
        .join("")
    : `<p class="empty-state">${escapeHtml(t("contextEmpty"))}</p>`;
  $$(".bookmark-source").forEach(button => {
    button.disabled = sourceContextStale;
    button.onclick = async () => {
      if (sourceContextStale) return;
      if (tabOnlyAccess) { toast("Saving a source requires saved access so you can check its outcome before trying again."); return; }
    const scope = identityScope(); button.disabled = true;
    try { await API.call("addBookmark", {sourceId: button.dataset.id}, {scope}); assertIdentity(scope); await loadBookmarks(scope); toast("Source saved privately."); }
    catch (error) { if (scope.epoch === state.identityEpoch && error.name !== "AbortError") toast("Could not save this source. Refresh context and try again."); }
    finally { if (scope.epoch === state.identityEpoch) button.disabled = sourceContextStale; }
    };
  });
  $$(".source-visible, .source-retract").forEach(el => { el.disabled = sourceMutationPending || sourceContextStale; });
  $$(".source-visible").forEach(
    (el) =>
      (el.onchange = async () => {
        if (tabOnlyAccess) { el.checked = !el.checked; toast("Changing source visibility requires saved access for recovery."); return; }
        if (sourceMutationPending || sourceContextStale) return;
        const scope = identityScope();
        sourceMutationPending = true;
        wave27Chapters?.reset();
        let confirmedSourceContext = null;
        $$(".source-visible, .source-retract").forEach(control => control.disabled = true);
        try {
          assertIdentity(scope);
          await API.call(
            "sourceUpdate",
            { audienceVisible: el.checked },
            el.dataset.id,
            { scope },
          );
          assertIdentity(scope);
          await refreshSources(scope);
          confirmedSourceContext = state.context;
        } catch (error) {
          if (
            scope.epoch !== state.identityEpoch ||
            error.name === "AbortError"
          )
            return;
          el.disabled = true;
          try {
            await refreshSources(scope);
            assertIdentity(scope);
            confirmedSourceContext = state.context;
            toast(state.lang === "es" ? "Estado de la fuente actualizado. Revisa el permiso antes de continuar." : "Source status refreshed. Review its permission before continuing.");
          } catch (readError) {
            if (readError.name === "AbortError" || scope.epoch !== state.identityEpoch) return;
            toast(state.lang === "es" ? "No se pudo confirmar el permiso. Vuelve a abrir el contexto para actualizarlo." : "Could not confirm the permission. Reopen context to refresh it.");
          }
        } finally {
          if (scope.epoch === state.identityEpoch) {
            sourceMutationPending = false;
            // Only re-enable after a successful readback; a failed read remains locked.
            if (state.context === confirmedSourceContext && !sourceContextStale) $$(".source-visible, .source-retract").forEach(control => control.disabled = false);
          }
        }
      }),
  );
  const sourceSelect = $("#questionSource");
  if (sourceSelect) {
    const selected = sourceSelect.value;
    sourceSelect.innerHTML =
      `<option value="">${escapeHtml(t("selectedSource"))}</option>` +
      selectableSources
        .filter((x) => x.status === "active")
        .map(
          (x) =>
            `<option value="${escapeHtml(x.id)}">${escapeHtml(x.title || x.kind || x.id)}${x.at ? ` · ${escapeHtml(x.at)}` : ""}</option>`,
        )
        .join("");
    if (sources.some((x) => x.id === selected && x.status === "active"))
      sourceSelect.value = selected;
  }
}
let backgroundSourceCheck = false;
function sourceSnapshotChanged(previous, current) {
  const before = normalizeList(previous?.sources || previous);
  const after = normalizeList(current?.sources || current);
  const nextById = new Map(after.map(source => [source.id, source]));
  return before.some(source => {
    const next = nextById.get(source.id);
    const expiry = next?.expiresAt ? Date.parse(next.expiresAt) : NaN;
    const authorityFields = ["revision", "status", "audienceVisible", "expiresAt", "visibility", "capabilities", "permissions", "kind"];
    return !next || (Number.isFinite(expiry) && expiry <= Date.now())
      || authorityFields.some(field => JSON.stringify(source[field]) !== JSON.stringify(next[field]));
  });
}
async function refreshSources(scope = identityScope(), { background = false, chapterRefresh = false, preservePhase10Selection = false } = {}) {
  assertIdentity(scope);
  if (background && backgroundSourceCheck) return;
  cueController?.invalidate();
  if (background) {
    backgroundSourceCheck = true;
    phase10Controller?.beginSourceCheck();
  } else if (!preservePhase10Selection) phase10Controller?.invalidate();
  const previousContext = state.context;
  try {
    const context = await API.call("sources", null, { scope });
    assertIdentity(scope);
    const changed = sourceContextStale || sourceSnapshotChanged(previousContext, context);
    if (changed) wave28Handoff?.reset();
    if (changed && !chapterRefresh) wave27Chapters?.reset();
    const added = normalizeList(context?.sources || context).length > normalizeList(previousContext?.sources || previousContext).length;
    if (changed) { wave26Terms?.reset(); phase12Controller?.invalidateSources(); wave15Viewer?.invalidate(); wave15Creator?.invalidate(); wave15Formats?.invalidate(); wave17Return?.reset(); wave17Templates?.reset(); wave19Library?.reset(); wave20Practice?.reset(); w20CreatorClear(); wave20Delivery?.reset(); wave21Speech?.reset(); wave21Visual?.reset(); wave21ImpactPreview?.reset(); wave23Moments?.reset(); wave22ClaimsViewer?.reset(); wave22ClaimsCreator?.reset(); wave22Coedit?.reset(); wave22ModelHistory?.reset(); wave22ModelShares?.reset(); wave22ModelWithdrawals?.reset(); wave20Policy?.reset(); wave19Entry?.reset(); wave19Setup?.reset(); wave19Inbox?.reset(); wave19Answers?.reset(); wave19Operator?.reset(); wave18Segment?.reset(); wave18Assistance?.reset(); wave18CreatorRecord?.reset(); wave18ViewerRecord?.reset(); wave22EditionReader?.reset(); wave22DescriptionCreator?.reset(); ++catchupReadGeneration; ++catchupRecapGeneration; state.catchupSnapshot = null; state.catchupRecap = null; }
    if ((background || preservePhase10Selection) && changed) phase10Controller?.invalidate();
    state.context = context;
    sourceContextStale = false;
    sourceContextLastRefreshAt = Date.now();
    renderSession();
    if (scope.role === "viewer") renderCatchup(scope);
    if ((!background && !preservePhase10Selection) || changed) phase10Controller?.refreshIfVisible();
    else if (added) phase10Controller?.notifyNewSources();
    return context;
  } catch (error) {
    if (scope.epoch === state.identityEpoch) {
      sourceContextStale = true;
      wave28Handoff?.reset();
      wave27Chapters?.reset();
      wave26Terms?.reset(); phase12Controller?.invalidateSources(); wave15Viewer?.invalidate(); wave15Creator?.invalidate(); wave15Formats?.invalidate(); wave17Return?.reset(); wave17Templates?.reset(); wave19Library?.reset(); wave20Practice?.reset(); w20CreatorClear(); wave20Delivery?.reset(); wave21Speech?.reset(); wave21Visual?.reset(); wave21ImpactPreview?.reset(); wave23Moments?.reset(); wave22ClaimsViewer?.reset(); wave22ClaimsCreator?.reset(); wave22Coedit?.reset(); wave22ModelHistory?.reset(); wave22ModelShares?.reset(); wave22ModelWithdrawals?.reset(); wave20Policy?.reset(); wave19Entry?.reset(); wave19Setup?.reset(); wave19Inbox?.reset(); wave19Answers?.reset(); wave19Operator?.reset(); wave18Segment?.reset(); wave18Assistance?.reset(); wave18CreatorRecord?.reset(); wave18ViewerRecord?.reset(); wave22EditionReader?.reset(); wave22DescriptionCreator?.reset(); ++catchupReadGeneration; ++catchupRecapGeneration; state.catchupSnapshot = null; state.catchupRecap = null;
      if (scope.role === "viewer") renderCatchup(scope);
      phase10Controller?.invalidate();
      renderSession();
    }
    throw error;
  } finally {
    if (background) {
      backgroundSourceCheck = false;
      if (scope.epoch === state.identityEpoch) phase10Controller?.endSourceCheck();
    }
  }
}
function viewerAccessLost(scope) {
  if (scope.epoch !== state.identityEpoch || scope.role !== "viewer") return;
  const wasTabOnly = tabOnlyAccess;
  removeActiveSavedIdentity();
  resetIdentityState();
  if (!wasTabOnly) renderSavedIdentities();
  if (!$("#accessDialog").open) $("#accessDialog").showModal();
  showError($("#accessError"), "Your access expired, was replaced, or the session closed. Ask the creator for a current invitation.");
}
function startRefreshTimers() {
  clearInterval(state.sourceRefreshTimer);
  clearInterval(state.connectionRefreshTimer);
  state.connectionRefreshTimer = setInterval(
    () => updateConnection().catch(() => {}),
    15000,
  );
  state.sourceRefreshTimer = setInterval(() => {
    if (state.role === "viewer") {
      const scope = identityScope();
      refreshSources(scope, { background: true }).catch(error => {
        if ([401, 403, 404].includes(error.status)) viewerAccessLost(scope);
      });
      loadCaptureStatus(scope);
    }
  }, 10000);
}
let capabilityNamespace = null;
function removeActiveSavedIdentity() {
  if (tabOnlyAccess) return;
  const active = localStorage.getItem("entrelineas.identity.active");
  if (active) localStorage.removeItem(active);
  localStorage.removeItem("entrelineas.identity.active");
}
async function bindCapability(scope = identityScope()) {
  assertIdentity(scope);
  if (!scope.token || !globalThis.crypto?.subtle) throw new Error("Secure draft storage unavailable");
  const input = new TextEncoder().encode("entrelineas-capability-v1\0" + scope.token);
  const digest = await crypto.subtle.digest("SHA-256", input);
  assertIdentity(scope);
  capabilityNamespace = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
}
function saveIdentity() {
  if (tabOnlyAccess) return;
  if (state.role === "viewer" && !state.viewerId) return;
  const identityPart = state.role === "viewer" ? `:${state.viewerId}` : "";
  const key = `entrelineas.identity.v2:${state.role}:${state.sessionId}${identityPart}:${capabilityNamespace}`;
  localStorage.setItem(
    key,
    JSON.stringify({
      sessionId: state.sessionId,
      joinCode: state.joinCode,
      token: state.token,
      role: state.role,
      viewerId: state.viewerId,
      session: state.session,
    }),
  );
  localStorage.setItem("entrelineas.identity.active", key);
}
let sourceMutationPending = false;
let sourceContextStale = false;
let sourceContextLastRefreshAt = null;
let wave28Handoff = null;
let shareMutationPending = false, shareStatusUncertain = false, shareReadPending = false, shareLoadGeneration = 0;
let closeHelperOperator = null;
function resetIdentityState(preserveResume = false, enteringTabOnly = false) {
  wave28Handoff?.reset();
  wave27Chapters?.reset();
  // Fence saved recovery before dependent components reconfigure during activation.
  if (enteringTabOnly) tabOnlyAccess = true;
  // A preparation capability belongs to the identity being left, even if
  // its verification has not completed or failed.
  $("#operatorCapability").value = "";
  $("#operatorSession").value = "";
  closeHelperOperator?.();
  $("#operatorEntryStatus").textContent = "";
  if (!preserveResume) resumeAccess?.reset();
  clearTimeout(tabOnlyExpiryTimer);
  tabOnlyExpiryTimer = null;
  wave26Terms?.reset();
  wave17Return?.reset(); wave17Templates?.reset(); wave19Library?.reset(); wave20Practice?.reset(); w20CreatorClear(); wave20Delivery?.reset(); wave21Speech?.reset(); wave21Visual?.reset(); wave21ImpactPreview?.reset(); wave22ClaimsViewer?.reset(); wave22ClaimsCreator?.reset(); wave22Coedit?.reset(); wave22ModelHistory?.reset(); wave22ModelShares?.reset(); wave22ModelWithdrawals?.reset(); wave20Policy?.reset(); wave19Entry?.reset(); wave19Setup?.reset(); wave19Inbox?.reset(); wave19Answers?.reset(); wave19Operator?.reset(); wave18Segment?.reset(); wave18Assistance?.reset(); wave18CreatorRecord?.reset(); wave18ViewerRecord?.reset(); wave22EditionReader?.reset(); wave22DescriptionCreator?.reset();
  wave15Viewer?.reset(); wave15Creator?.reset();
  waveModelPreview?.reset();
  waveDrafts?.reset();
  waveReasons?.reset();
  waveProduction?.reset();
  cueController?.reset();
  waveQuestions?.reset();
  waveFormats?.reset();
  wave15Formats?.reset();
  wavePublishedModels?.reset();
  p12UploadAttempt=null;
  collaborationController?.reset();
  phase12Controller?.reset();
  phase6Controller?.reset();
  sourceMutationPending = false;
  shareMutationPending = false; shareStatusUncertain = false; shareReadPending = false; ++shareLoadGeneration;
  $("#editorialDraft").removeAttribute("aria-busy");
  state.identityEpoch++;
  // Preserve the activation fence while the new tab-only identity is installed.
  tabOnlyAccess = enteringTabOnly;
  phase10Controller?.reset();
  phase11Controller?.reset();
  sourceContextStale = false;
  invitationStateUncertain = false;
  sourceContextLastRefreshAt = null;
  capabilityNamespace = null;
  state.providers = [];
  state.capabilities = null;
  state.diagnosticsAvailable = null;
  updateVisualCapabilities();
  renderProviderState();
  API.abortAll();
  $$("button[data-label]").forEach((button) => setBusy(button, false));
  state.captureEpoch++;
  clearInterval(state.sourceRefreshTimer);
  clearInterval(state.connectionRefreshTimer);
  state.sourceRefreshTimer = null;
  state.connectionRefreshTimer = null;
  state.session = null;
  state.sessionId = null;
  state.joinCode = null;
  state.token = null;
  state.role = null;
  state.viewerId = null;
  state.liveAudio?.stop();
  clearInterval(state.audioUiTimer);
  state.audioUiTimer = null;
  state.audioStartedAt = 0;
  state.audioNoSpeech = false;
  audioIdentityScope = null;
  audioProgramCapture = null;
  state.liveAudioState = null;
  clearCaptureDraft();
  state.conversationId = null;
  state.practiceConversationId = null;
  state.history = [];
  state.lastAttemptId = null;
  state.retryFromAttemptId = null;
  renderRetrySelection();
  state.lastMessageId = null;
  state.pendingQuestionAction = null;
  state.pendingPracticeAction = null;
  ++catchupRecapGeneration; catchupRecapInFlight=false;
  state.shareReviewSnapshot = null;
  state.catchupSnapshot = null;
  $("#catchupSearch").value = ""; $("#catchupSearchResults").replaceChildren();
  state.catchupRecap = null;
  state.pendingCatchupRecapAction = null;
  state.activity = null;
  state.notebookItems = [];
  // A prior actor's notebook preview and in-flight file read must not survive a switch.
  ++notebookImportGeneration;
  importNotebookCandidate = null; exportNotebookCandidate = null;
  $("#notebookPreview").replaceChildren(); $("#notebookItems").replaceChildren();
  $("#notebookText").value = ""; $("#notebookSelection").replaceChildren(new Option("Choose your note, message, attempt, bookmark, or reference", ""));
  $("#notebookImportFile").value = "";
  state.pendingPracticeActivity = null;
  state.nextCorrection = null;
  state.conversationRendered = false;
  state.renderedMessageIds = new Set();
  state.context = null;
  state.questionSourceChoices = [];
  state.contributions = [];
  // Clear related components after the previous identity and context are gone.
  wave23Moments?.reset();
  state.insights = [];
  state.materials = [];
  state.captureSourceId = null;
  state.lastPracticeImage = null;
  state.selectedFiles = [];
  for (const id of ["sessionDialog", "contextDialog", "captureDialog"]) {
    const dialog = $(`#${id}`);
    if (dialog?.open) dialog.close();
  }
  $("#question").value = "";
  $("#shareReview").hidden = true;
  $("#shareReview").replaceChildren();
  $("#shareSource").disabled = false;
  $("#shareText").disabled = false;
  $("#shareConsent").disabled = false;
  $("#sharePublicConsent").disabled = false;
  $("#shareIncludeImage").disabled = true;
  clearError($("#audienceError"));
  clearError($("#practiceError"));
  clearError($("#editorialError"));
  $("#practiceFiles").value = "";
  $("#fileList").textContent = "";
  $("#editorialDraft").replaceChildren();
  $("#editorialDraft").hidden = true;
  $("#shareConsent").checked = false;
  $("#sharePublicConsent").checked = false;
  $("#shareIncludeImage").checked = false;
  $("#conversation").replaceChildren();
  $("#practiceHistoryList").replaceChildren();
  $("#contextSources").replaceChildren();
  $("#contributions").replaceChildren();
  for (const id of ["bookmarks", "comparison", "workbenchChanges", "operations"]) $(`#${id}`).replaceChildren();
  for (const id of ["compareFirst", "compareSecond"]) $(`#${id}`).replaceChildren();
  $("#viewerCapture").textContent = "Program context status unavailable.";
  $("#creatorRecovery").hidden = true;
  $("#myShares").replaceChildren();
  $("#questionSource").value = "";
  $("#questionMoment").value = "";
  $("#shareText").value = "";
  $("#practiceGoal").value = "";
  $("#practiceAttempt").value = "";
  $("#practiceActivityPrompt").textContent = "";
  $("#practiceActivityPrompt").hidden = true;
  $("#practiceDifficulty").value = "conceptual";
  $("#editorialFocus").value = "";
  $("#sessionMaterials").value = "";
  $("#materialsAudienceVisible").checked = false;
  $("#liveAudioConsent").checked = false;
  $("#liveAudioAudience").checked = false;
  $("#captureForm").reset();
  $("#captureStatus").textContent = t("captureStopped");
  $("#stopCapture").disabled = true;
  $("#liveAudioStatus").textContent = t("audioIdle");
  $("#stagePreview").replaceChildren();
  $("#toast").classList.remove("show");
  clearTimeout(toast.timer);
  applyRole();
}
function renderSavedIdentities() {
  const host = $("#savedIdentities");
  if (!host) return;
  // Keep saved credentials outside memory-only sessions.
  if (tabOnlyAccess) { host.replaceChildren(); return; }
  const renderedEpoch = state.identityEpoch;
  const keys = Object.keys(localStorage).filter((k) =>
    k.startsWith("entrelineas.identity.v1:") || k.startsWith("entrelineas.identity.v2:"),
  );
  host.replaceChildren();
  keys.forEach((key, index) => {
    try {
      const cached = JSON.parse(localStorage.getItem(key));
      if (!cached?.token) return;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "button secondary";
      const viewerLabel =
        cached.role === "viewer"
          ? ` · ${cached.session?.displayName || cached.viewerId || t("viewerTab")}`
          : "";
      b.textContent = `${cached.role === "creator" ? t("creatorTab") : t("viewerTab")}${viewerLabel} · ${cached.session?.channel || cached.sessionId} · ${state.lang === "es" ? "acceso guardado" : "saved access"} ${index + 1}`;
      b.addEventListener("click", async () => {
        // A queued click from an old saved-access view must not replace a
        // newer identity or expose its cached credential in a tab-only session.
        if (tabOnlyAccess || state.identityEpoch !== renderedEpoch) return;
        resetIdentityState();
        Object.assign(state, cached);
        localStorage.setItem("entrelineas.identity.active", key);
        $("#accessDialog").close();
        await loadCore();
      });
      host.append(b);
    } catch {}
  });
}
function assertSavedIdentity(scope) {
  assertIdentity(scope);
  if (tabOnlyAccess) throw new Error("This feature requires saved access for request recovery");
}
function draftKey() {
  return state.sessionId &&
    state.role &&
    (state.role !== "viewer" || state.viewerId)
    && capabilityNamespace
    ? `entrelineas.draft.v3:${state.role}:${state.sessionId}:${state.role === "viewer" ? state.viewerId : "creator"}:${capabilityNamespace}`
    : null;
}
function readSavedDraft(key) {
  const raw = localStorage.getItem(key);
  if (raw === null) return {};
  const saved = JSON.parse(raw);
  if (!saved || typeof saved !== "object" || Array.isArray(saved)) throw new Error("Saved draft is unavailable; its contents were preserved.");
  return saved;
}
function persistDraft(scope = identityScope(), change = null) {
  assertIdentity(scope);
  // Tab-only access never persists private drafts or unjournaled requests.
  if (tabOnlyAccess) return false;
  const key = draftKey();
  if (!key) return false;
  // Ordinary saves must take the same cross-tab lock as request changes: a
  // read/merge/write alone can race another tab between getItem and setItem.
  if (!change) {
    if (!navigator.locks?.request) return false;
    navigator.locks.request(`${key}:actions`, lock => {
      if (!lock || tabOnlyAccess) return;
      try { assertSavedIdentity(scope); persistDraft(scope, {ordinary: true}); } catch { /* stale identity or inaccessible storage */ }
    }).catch(() => {});
    return true;
  }
  try {
    const saved = readSavedDraft(key);
    const hadPendingAction = Boolean(saved.pendingQuestionAction || saved.pendingPracticeAction);
    if (!change.ordinary) {
      const existing = saved[change.name] || null;
      if ((existing?.clientRequestId || null) !== change.expected) return false;
      saved[change.name] = change.value;
    }
    const draft = {
        goal: $("#practiceGoal").value,
        attempt: $("#practiceAttempt").value,
        difficulty: $("#practiceDifficulty").value,
        question: $("#question").value,
        questionSource: $("#questionSource").value,
        questionMoment: $("#questionMoment").value,
        shareText: $("#shareText").value,
        focus: $("#editorialFocus").value,
        pendingQuestionAction: saved.pendingQuestionAction || null,
        pendingPracticeAction: saved.pendingPracticeAction
          ? saved.pendingPracticeAction.metadataOnly
            ? saved.pendingPracticeAction
            : {
                ...saved.pendingPracticeAction,
                payload: Object.fromEntries(
                  Object.entries(saved.pendingPracticeAction.payload || {}).filter(([name]) => name !== "image"),
                ),
              }
          : null,
        pendingPracticeActivity: state.pendingPracticeActivity,
        nextCorrection: state.nextCorrection,
        retryFromAttemptId: state.retryFromAttemptId,
      };
    // An unresolved request owns its original inputs until it is resolved.
    // Other tabs may still edit their in-memory forms without changing recovery.
    if (hadPendingAction) {
      for (const name of ["goal", "attempt", "difficulty", "question", "questionSource", "questionMoment", "shareText", "focus", "pendingPracticeActivity", "nextCorrection", "retryFromAttemptId"]) {
        if (Object.hasOwn(saved, name)) draft[name] = saved[name];
      }
    }
    const serialized = JSON.stringify(draft);
    localStorage.setItem(key, serialized);
    return localStorage.getItem(key) === serialized;
  } catch (error) {
    // Draft persistence is best effort; never block the current action on quota.
    if (error?.name !== "QuotaExceededError") throw error;
    return false;
  }
}
async function withDraftActionLock(scope, errorNode, callback) {
  try {
    assertSavedIdentity(scope);
    const key = draftKey();
    if (!key || !navigator.locks?.request) throw Error("Safe request recovery is unavailable in this browser.");
    await navigator.locks.request(`${key}:actions`, {ifAvailable: true}, async lock => {
      if (!lock) throw Error("Another tab is resolving a request. Wait for it to finish before trying again.");
      assertSavedIdentity(scope);
      const saved = readSavedDraft(key);
      state.pendingQuestionAction = saved.pendingQuestionAction || null;
      state.pendingPracticeAction = saved.pendingPracticeAction || null;
      await callback();
    });
  } catch (error) {
    if (scope.epoch === state.identityEpoch) showError(errorNode, error.message || "Safe request recovery is unavailable.");
  }
}
function newRequestId() {
  return crypto.randomUUID();
}
function pendingActionMatches(action, signature, conversationId) {
  return Boolean(
    action &&
    action.signature === signature &&
    action.conversationId === conversationId &&
    typeof action.clientRequestId === "string" &&
    action.clientRequestId.length <= 128,
  );
}
function definitiveActionError(error) {
  // A provider failure can retain an attempt even when it returns 503.
  // Only the documented busy response establishes that no attempt was admitted.
  return error?.code === "busy" ||
    (Number.isInteger(error?.status) && error.status >= 400 && error.status < 500 && ![408, 409, 429].includes(error.status));
}
function restoreDraft() {
  if (tabOnlyAccess) return;
  const key = draftKey();
  if (!key) return;
  try {
    const d = readSavedDraft(key);
    $("#practiceGoal").value = d.goal || "";
    $("#practiceAttempt").value = d.attempt || "";
    $("#practiceDifficulty").value = d.difficulty || "conceptual";
    $("#question").value = d.question || "";
    $("#questionSource").value = d.questionSource || "";
    $("#questionMoment").value = d.questionMoment || "";
    $("#shareText").value = d.shareText || "";
    $("#editorialFocus").value = d.focus || "";
    state.pendingQuestionAction = d.pendingQuestionAction || null;
    state.pendingPracticeAction = d.pendingPracticeAction || null;
    state.pendingPracticeActivity = d.pendingPracticeActivity || null;
    state.nextCorrection = d.nextCorrection || null;
    state.retryFromAttemptId = d.retryFromAttemptId || null;
    renderRetrySelection();
  } catch {}
}
function applyRole() {
  const creator = state.role === "creator";
  renderWorkspaceGuide($('#wave30RoleGuide'), state.role, navTo);
  wave15Viewer?.update(); wave15Creator?.update();
  wave15Formats?.activate();
  wave17Templates?.activate();
  const waveRoot = $("#waveModelPreview");
  const waveSlot = $(creator ? "#waveCreatorSlot" : "#waveAudienceSlot");
  if (waveRoot && waveSlot && waveRoot.parentNode !== waveSlot) waveSlot.appendChild(waveRoot);
  const translationRoot = $("#p12Root");
  const translationSlot = $(creator ? "#p12CreatorSlot" : "#p12AudienceSlot");
  if (translationRoot && translationSlot && translationRoot.parentNode !== translationSlot) translationSlot.appendChild(translationRoot);
  phase6Controller?.setRole(state.role);
  // Project ownership uses browser-stored capabilities and recovery state.
  // Memory-only access cannot safely use that flow or restore another entry's state.
  const projectView = $("#view-project");
  if (projectView) {
    let notice = $("#tabOnlyProjectNotice");
    if (!notice) {
      notice = document.createElement("p");
      notice.id = "tabOnlyProjectNotice";
      notice.setAttribute("role", "status");
      notice.textContent = "Community projects require saved access to protect owner capabilities and request recovery.";
      projectView.prepend(notice);
    }
    notice.hidden = !tabOnlyAccess;
    for (const child of projectView.children) if (child !== notice) child.inert = tabOnlyAccess;
  }
  phase10Controller?.setRole(state.role);
  const privateSource = $("#p10Viewer");
  if (privateSource) {
    let notice = $("#tabOnlySourceNotice");
    if (!notice) { notice = document.createElement("p"); notice.id = "tabOnlySourceNotice"; notice.setAttribute("role", "status"); notice.textContent = "Private vault changes and generated source responses require saved access for request recovery."; privateSource.prepend(notice); }
    notice.hidden = !tabOnlyAccess;
  }
  const studio = $("#p10Studio");
  if (studio) {
    let notice = $("#tabOnlyStudioNotice");
    if (!notice) {
      notice = document.createElement("p");
      notice.id = "tabOnlyStudioNotice";
      notice.setAttribute("role", "status");
      notice.textContent = "You can review current materials in this tab. Editing, generating and other actions requiring request recovery need saved access.";
      studio.prepend(notice);
    }
    notice.hidden = !tabOnlyAccess;
  }
  // Activity recovery includes saved private request bodies. Keep it unavailable
  // for memory-only access, without reading or changing another identity's journal.
  const activityRoot = $("#p11Root");
  if (activityRoot) {
    let notice = $("#tabOnlyActivityNotice");
    if (!notice) {
      notice = document.createElement("p");
      notice.id = "tabOnlyActivityNotice";
      notice.textContent = "Activities require saved access to protect request recovery.";
      activityRoot.before(notice);
    }
    notice.hidden = !tabOnlyAccess;
    activityRoot.hidden = tabOnlyAccess;
  }
  if (tabOnlyAccess || !state.role) phase11Controller?.reset();
  else phase11Controller?.setRole(state.role);
  const collaborationRoot = $("#p12CollaborationRoot");
  if (collaborationRoot) {
    let notice = $("#tabOnlyCollaborationNotice");
    if (!notice) {
      notice = document.createElement("p");
      notice.id = "tabOnlyCollaborationNotice";
      notice.textContent = "Collaboration requires saved access to protect request recovery.";
      collaborationRoot.before(notice);
    }
    notice.hidden = !tabOnlyAccess;
    collaborationRoot.hidden = tabOnlyAccess;
  }
  if (tabOnlyAccess) collaborationController?.reset();
  for (const selector of ["#wave22Coedit", "#wave22CoeditViewer", "#wave22DescriptionCreator", "#wave18CreatorRecord", "#wave18ViewerRecord", "#waveModelPreview", "#wave21Visual", "#wave21ImpactPreview", "#wave21Speech", "#wave22ClaimsViewer", "#wave22ClaimsCreator", "#wave22ModelShares", "#wave22ModelWithdrawals", "#wave22ModelExploration", "#wave20Delivery", "#wave20Practice", "#wave19Library", "#wave20Policy", "#wave23Listening", "#p12Root", "#wave18Assistance", "#wave19Inbox", "#wave19Operator", "#productionCues", "#catchupPanel .w17-return", "#view-perspectives", "#view-work", "#view-inquiry"]) {
    const root = $(selector);
    if (!root) continue;
    let notice = root.querySelector(":scope > [data-tab-only-notice]");
    if (!notice) {
      notice = document.createElement("p");
      notice.dataset.tabOnlyNotice = "";
      notice.setAttribute("role", "status");
      notice.textContent = selector === '#wave21ImpactPreview' ? "Editing requires saved access to protect request recovery. You can read a current correction below." : "This feature requires saved access to protect request recovery.";
      root.prepend(notice);
    }
    notice.hidden = !tabOnlyAccess;
    for (const child of root.children) if (child !== notice) child.inert = tabOnlyAccess && !((selector === '#wave21ImpactPreview' || selector === '#waveModelPreview') && child.hasAttribute('data-tab-only-read'));
  }
  for (const selector of ["#wave18CreatorRecordRefresh", "#wave18ViewerRecordRefresh", "#wave18AssistanceRefresh"]) {
    const control = $(selector);
    if (control) control.disabled = tabOnlyAccess;
  }
  for (const section of $$('#catchupPanel > section.p6-card')) {
    if (section.querySelector('summary')?.textContent === 'Chapters and indexed search') section.inert = tabOnlyAccess;
  }
  if (!creator) state.liveAudio?.stop();
  $$('[data-view="studio"], [data-view="stage"]').forEach(
    (el) => (el.hidden = !creator),
  );
  $$('[data-view="audience"], [data-view="practice"]').forEach(
    (el) => (el.hidden = creator),
  );
  $("#privateDataControls").hidden = state.role !== "viewer";
  $("#catchupPanel").hidden = creator;
  $("#actionableMaterial").hidden = creator;
  $("#interventionFeedback").hidden = creator;
  if (creator) $("#notebookText").value = "";
  $("#copyJoinCode").hidden = !creator;
  $("#editSession").hidden = !creator;
  $("#connectTwitch").hidden = !creator;
  $("#startCapture").hidden = !creator;
  $("#manageSources").hidden = !creator;
  $("#stopCapture").hidden = !creator;
  $("#liveAudioControls").hidden = !creator;
  $("#identity").textContent = creator ? "C" : "A";
  $("#identity").title = creator
    ? state.lang === "es"
      ? "Creador"
      : "Creator"
    : state.lang === "es"
      ? "Audiencia"
      : "Audience";
}
function updateVisualCapabilities() {
  const verified = state.diagnosticsAvailable === true;
  state.visionSupported = verified && (
    state.capabilities?.vision === true ||
    state.providers.some((p) => p.capabilities?.vision === true));
  const set = (selector, fn) => {
    const el = $(selector);
    if (el) fn(el);
  };
  set("#visualNotice", (el) => {
    el.hidden = state.visionSupported;
    el.textContent = !verified ? t("visualCapabilityUnknown") : t("visualUnavailable");
  });
  set("#captureVisualNotice", (el) => {
    el.hidden = state.visionSupported;
    el.textContent = !verified ? t("visualCapabilityUnknown") : t("visualUnavailable");
  });
  set("#practiceFiles", (el) => (el.disabled = !state.visionSupported));
  set(".file-label", (el) => (el.hidden = !state.visionSupported));
  set("#screenCaptureControls", (el) => (el.hidden = !state.visionSupported));
  set("#captureImageLabel", (el) => (el.hidden = !state.visionSupported));
}
function renderProviderState() {
  if (state.diagnosticsAvailable !== true) {
    $("#providerState").textContent = t("diagnosticsUnknown");
    return;
  }
  const p = state.providers[0],
    transcription =
      state.capabilities?.transcription === true ||
      state.providers.some((x) => x.capabilities?.transcription === true);
  const providerStatus = !p
    ? t("providerUnavailable")
    : p.available === true
      ? t("providerReady")
      : p.available === false || p.configured === false
        ? t("providerUnavailable")
        : p.configured === true
          ? t("providerUnknown")
          : t("providerUnavailable");
  $("#providerState").textContent =
    `${providerStatus}${p ? ` · ${p.model || p.name}` : ""} · ${transcription ? t("asrReady") : t("asrUnavailable")}`;
}
async function loadBackendDiagnostics(scope = identityScope()) {
  const timeout = AbortSignal.timeout(4000);
  try {
    const [health, providerData] = await Promise.all([
      API.call("health", null, { scope, signal: timeout }),
      API.call("providers", null, { scope, signal: timeout }),
    ]);
    assertIdentity(scope);
    state.providers = normalizeList(providerData?.providers || health.providers);
    state.capabilities = health.capabilities || providerData?.capabilities || {};
    state.diagnosticsAvailable = true;
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || (error.name === "AbortError" && !timeout.aborted)) throw error;
    assertIdentity(scope);
    state.providers = [];
    state.capabilities = null;
    state.diagnosticsAvailable = null;
  }
  assertIdentity(scope);
  updateVisualCapabilities();
  renderProviderState();
}
function startBackendDiagnostics(scope = identityScope()) {
  loadBackendDiagnostics(scope).catch(error => {
    if (error.name !== "AbortError") throw error;
  });
}
async function updateConnection(scope = identityScope()) {
  assertIdentity(scope);
  try {
    const d = await API.call("connection", null, { scope }),
      c = d.connection || d;
    assertIdentity(scope);
    state.session.connection = c;
    $("#liveConnection").textContent =
      `${t("connectionLabel")}: ${c.status || c.mode || "local"}${c.lastContextAt ? ` · ${new Date(c.lastContextAt).toLocaleTimeString()}` : ""}`;
  } catch (error) {
    if (scope.epoch !== state.identityEpoch) return;
    $("#liveConnection").textContent =
      `${t("connectionLabel")}: ${t("networkDown")}`;
  }
}
async function loadCore(restoreSaved = true, showSaved = true) {
  const entry = identityScope();
  state.providers = [];
  state.capabilities = null;
  state.diagnosticsAvailable = null;
  updateVisualCapabilities();
  renderProviderState();
  try {
    const active = tabOnlyAccess || !restoreSaved ? null : localStorage.getItem("entrelineas.identity.active");
    const cached = tabOnlyAccess ? {sessionId: state.sessionId, token: state.token} : active
      ? JSON.parse(localStorage.getItem(active) || "null")
      : null;
    if (cached?.sessionId && cached?.token) {
      Object.assign(state, cached);
      const scope = identityScope();
      await bindCapability(scope);
      assertIdentity(scope);
      if (!tabOnlyAccess) { wave15Viewer?.activate(); wave15Creator?.activate(); }
      const data = await API.call("session", null, { scope });
      assertIdentity(scope);
      state.session = data.session || data;
      state.joinCode = state.joinCode || state.session.joinCode;
      const currentSources = await API.call("sources", null, { scope });
      assertIdentity(scope);
      state.context = currentSources;
      sourceContextStale = false;
      sourceContextLastRefreshAt = Date.now();
      setConnection(true);
      await updateConnection(scope);
      assertIdentity(scope);
      applyRole();
      renderSession();
      if (!tabOnlyAccess) restoreDraft();
      wave23Moments?.reset();
      if (state.role === "viewer") {
        await ensureConversation(scope);
        assertIdentity(scope);
        await ensurePracticeConversation(scope);
        assertIdentity(scope);
      }
      navTo(state.role === "creator" ? "studio" : "audience");
      renderSavedIdentities();
      startRefreshTimers();
      startBackendDiagnostics(scope);
      return;
    }
    $("#accessDialog").showModal();
    if (showSaved) renderSavedIdentities();
    startBackendDiagnostics(entry);
  } catch (e) {
    if (e.name === "AbortError" || entry.epoch !== state.identityEpoch) return;
    const accessFailure = [401, 403, 404].includes(e.status);
    if (!accessFailure && e.status !== 503) setConnection(false);
    $("#contextSummary").textContent = accessFailure
      ? t("accessFailed")
      : t("connectionError");
    if (!state.session) $("#channelName").textContent = t("authRequired");
    if ([401, 403, 404].includes(e.status)) {
      const tabOnlyCreator = tabOnlyAccess && state.role === "creator";
      const creator = !tabOnlyAccess && state.role === "creator" && state.token && state.sessionId;
      clearInterval(state.sourceRefreshTimer);
      clearInterval(state.connectionRefreshTimer);
      if (!creator) {
        removeActiveSavedIdentity();
        resetIdentityState();
      }
      if (!$("#accessDialog").open) $("#accessDialog").showModal();
      $("#creatorRecovery").hidden = !creator;
      if (creator) $("#recoverySession").textContent = `Session ID: ${state.sessionId}`;
      showError($("#accessError"), creator
        ? "This session is closed, expired, or unavailable. Retained data is not deleted. You can attempt local cleanup below."
        : tabOnlyCreator ? "Your access expired, was replaced, or the session closed. Verify current creator access to continue." : "Your access expired, was replaced, or the session closed. Ask the creator for a current invitation.");
    }
  }
}
async function ensureConversation(scope = identityScope()) {
  if (state.role !== "viewer") return;
  assertIdentity(scope);
  try {
    if (!state.conversationId) {
      const data = await API.call("conversations", null, { scope });
      assertIdentity(scope);
      let c = normalizeList(data).find((x) => x.mode === "understand");
      if (!c) {
        if (tabOnlyAccess) { $("#conversation").textContent = "Starting a new conversation requires saved access for recovery."; return; }
        const made = await API.call(
          "createConversation",
          { mode: "understand" },
          { scope },
        );
        assertIdentity(scope);
        c = made.conversation || made;
      }
      state.conversationId = c.id;
    }
    if (state.conversationRendered) return;
    const detail = await API.call("conversation", null, state.conversationId, {
      scope,
    });
    const messages = normalizeList(detail.messages);
    assertIdentity(scope);
    state.lastMessageId = [...messages]
      .reverse()
      .find((m) => m.role === "user")?.id;
    $("#conversation").replaceChildren();
    state.renderedMessageIds = new Set();
    let previousQuestionText = "";
    for (const m of messages) {
      if (m.role === "user") previousQuestionText = m.text || "";
      if (m.id && state.renderedMessageIds.has(m.id)) continue;
      const el = document.createElement("div");
      el.className = `message ${m.role === "user" ? "user" : ""}`;
      if (m.id) {
        el.dataset.messageId = m.id;
        state.renderedMessageIds.add(m.id);
      }
      const answer = m.answer || m;
      const refs = normalizeList(answer.citations || []);
      el.innerHTML = `<span class="message-label">${escapeHtml(m.role === "user" ? t("you") : t("response"))}</span><p>${escapeHtml(answer.text || m.text || "")}</p>${answer.limitations?.length ? `<div class="sources">${answer.limitations.map(escapeHtml).join(" · ")}</div>` : ""}${refs.length ? `<div class="sources"><b>${escapeHtml(t("sources"))}</b>: ${refs.map(renderConversationCitation).join(" · ")}</div>` : ""}${m.role === "user" ? "" : `<button type="button" class="text-button followup">${escapeHtml(t("contextCorrection"))}</button><div class="correction" hidden><textarea rows="2" placeholder="${escapeHtml(t("contextCorrectionLabel"))}"></textarea><button type="button" class="button secondary correction-send">${escapeHtml(t("sendCorrection"))}</button></div>`}`;
      if (m.role !== "user") {
        attachCorrectionControls(el, scope, previousQuestionText);
        attachAnswerTrail(el, refs, scope, previousQuestionText);
      }
      $("#conversation").append(el);
    }
    state.conversationRendered = true;
  } catch (error) {
    throw error;
  }
}
function renderConversationCitation(citation) {
  if (citation.stale) return escapeHtml(state.lang === "es" ? "Fuente no disponible o modificada" : "Source unavailable or changed");
  return `${escapeHtml(citation.title || citation.sourceId || "")}${citation.at ? ` · ${escapeHtml(citation.at)}` : ""}${citation.excerpt ? ` — ${escapeHtml(citation.excerpt)}` : ""}`;
}
function attachCorrectionControls(box, scope, originalText) {
  box.querySelector(".followup").onclick = () => {
    if (scope.epoch !== state.identityEpoch) return;
    box.querySelector(".correction").hidden =
      !box.querySelector(".correction").hidden;
  };
  box.querySelector(".correction-send").onclick = async () => {
    if (scope.epoch !== state.identityEpoch) return;
    const correction = box.querySelector("textarea").value.trim();
    if (!correction) return;
    state.nextCorrection = correction;
    $("#question").value = originalText;
    await $("#questionForm").requestSubmit();
  };
}
function attachAnswerTrail(box, citations, scope, originalQuestion) {
  const actions = document.createElement("div");
  actions.className = "answer-trail";
  for (const citation of citations) {
    if (!citation.sourceId || citation.stale) continue;
    const button = document.createElement("button");
    button.type = "button"; button.className = "button secondary";
    button.textContent = `Use source: ${citation.title || "Source"}`;
    button.onclick = async () => {
      try {
        await refreshSources(scope); assertIdentity(scope);
        const source = normalizeList(state.context).find(x => x.id === citation.sourceId && x.status === "active");
        if (!source) { toast("This source is no longer available."); return; }
        $("#questionSource").value = source.id;
        $("#questionMoment").value = source.at || "";
        persistDraft(scope);
        $("#question").focus();
      } catch (error) {
        if (scope.epoch === state.identityEpoch && error.name !== "AbortError") toast("Could not refresh the source. Try again.");
      }
    };
    actions.append(button);
  }
  const practice = document.createElement("button");
  practice.type = "button"; practice.className = "button secondary";
  practice.textContent = "Try this privately";
  practice.onclick = () => {
    assertIdentity(scope);
    if (!$("#practiceGoal").value.trim()) $("#practiceGoal").value = originalQuestion;
    state.retryFromAttemptId = null; renderRetrySelection();
    persistDraft(scope); navTo("practice"); $("#practiceAttempt").focus();
  };
  actions.append(practice); box.append(actions);
}
async function ensurePracticeConversation(scope = identityScope()) {
  if (state.role !== "viewer") return;
  assertIdentity(scope);
  if (!state.practiceConversationId) {
    const data = await API.call("conversations", null, { scope });
    assertIdentity(scope);
    let c = normalizeList(data).find((x) => x.mode === "practice");
    if (!c) {
      if (tabOnlyAccess) { $("#practiceHistoryList").textContent = "Starting a new conversation requires saved access for recovery."; return; }
      const made = await API.call(
        "createConversation",
        { mode: "practice" },
        { scope },
      );
      assertIdentity(scope);
      c = made.conversation || made;
    }
    state.practiceConversationId = c.id;
  }
  const detail = await API.call(
    "conversation",
    null,
    state.practiceConversationId,
    { scope },
  );
  assertIdentity(scope);
  const attempts = normalizeList(detail.attempts);
  state.history = attempts.map((x) => ({
    id: x.id,
    goal: x.goal,
    attempt: x.text,
    answer: x.answer?.text || "",
    citations: (x.answer?.citations || []).map(c => c.stale ? {sourceId:c.sourceId, title:"Source unavailable or changed"} : c),
    limitations: x.answer?.limitations || [],
    grounded: x.answer?.grounded,
    created_at: x.createdAt,
    previousAttemptId: x.previousAttemptId,
  }));
  state.lastAttemptId = attempts.at(-1)?.id || null;
  renderHistory();
  renderRetrySelection();
  renderComparisonChoices();
}
function beginAccess(mode) {
  $$(".access-tab").forEach((x) =>
    x.classList.toggle("active", x.dataset.access === mode),
  );
  $("#joinFields").hidden = mode !== "join";
  $("#createFields").hidden = mode !== "create";
  $("#accessSubmit").textContent = t(
    mode === "create" ? "createSession" : "joinSession",
  );
  $("#joinSessionId").required = mode === "join";
  $("#joinCode").required = mode === "join";
  $("#newTitle").required = mode === "create";
  $("#newChannel").required = mode === "create";
  $("#accessForm").dataset.mode = mode;
}
$$(".access-tab").forEach((b) =>
  b.addEventListener("click", () => beginAccess(b.dataset.access)),
);
$("#accessClose").addEventListener("click", () => {
  if (state.token) $("#accessDialog").close();
});
$("#accessDialog").addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const dialog = event.currentTarget;
  const focusable = $$(
    'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    dialog,
  ).filter(
    (element) =>
      !element.hidden &&
      element.getAttribute("aria-hidden") !== "true" &&
      element.getClientRects().length,
  );
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (
    event.shiftKey &&
    (document.activeElement === first ||
      !dialog.contains(document.activeElement))
  ) {
    event.preventDefault();
    last.focus();
  } else if (
    !event.shiftKey &&
    (document.activeElement === last ||
      !dialog.contains(document.activeElement))
  ) {
    event.preventDefault();
    first.focus();
  }
});
$("#identity").addEventListener("click", () => {
  $("#accessDialog").showModal();
  renderSavedIdentities();
  beginAccess("join");
});
$("#connectTwitch").addEventListener("click", async () => {
  const scope = identityScope();
  try {
    const result = await API.call("twitch", {
      channel: state.session?.channel,
    });
    assertIdentity(scope);
    const c = result.connection || result;
    $("#liveConnection").textContent =
      `${t("connectionLabel")}: ${c.status || c.mode || "connected"}`;
    toast(t("twitchConnected"));
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
      return;
    toast(t("twitchUnavailable"));
  }
});
$("#accessForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#accessError"),
    btn = $("#accessSubmit");
  clearError(err);
  if (e.currentTarget.dataset.mode === "join" && (looksLikeInvitation($("#joinSessionId").value) || looksLikeInvitation($("#joinCode").value))) {
    showError(err, "This looks like partial invitation details, not a session code. Paste the complete invitation above and choose Prepare invitation, then review both fields before joining.");
    return;
  }
  let formEpoch = null;
  try {
    resetIdentityState();
    formEpoch = state.identityEpoch;
    setBusy(btn, true, t("sending"));
    const entering = identityScope();
    if (e.currentTarget.dataset.mode === "create") {
      const d = await API.call("createSession", {
        title: $("#newTitle").value.trim(),
        channel: $("#newChannel").value.trim(),
        purpose: $("#newPurpose").value.trim(),
      });
      assertIdentity(entering);
      const session = d.session;
      Object.assign(state, {
        session,
        sessionId: session.id,
        joinCode: d.joinCode || session.joinCode,
        token: d.creatorToken,
        role: "creator",
        viewerId: null,
      });
    } else {
      const id = $("#joinSessionId").value.trim(),
        code = $("#joinCode").value,
        d = await API.call(
          "join",
          {
            joinCode: code,
            displayName: $("#displayName").value.trim() || undefined,
          },
          id,
        );
      assertIdentity(entering);
      Object.assign(state, {
        session: d.session,
        sessionId: d.session.id,
        joinCode: d.session.joinCode || code,
        token: d.viewerToken,
        role: "viewer",
        viewerId: d.viewerId,
      });
    }
    const scope = identityScope();
    await bindCapability(scope);
    assertIdentity(scope);
    wave15Viewer?.activate(); wave15Creator?.activate();
    saveIdentity();
    const currentSources = await API.call("sources", null, { scope });
    assertIdentity(scope);
    state.context = currentSources;
    sourceContextStale = false;
    sourceContextLastRefreshAt = Date.now();
    setConnection(true);
    await updateConnection(scope);
    assertIdentity(scope);
    applyRole();
    renderSession();
    restoreDraft();
    wave23Moments?.reset();
    if (state.role === "viewer") {
      await ensureConversation(scope);
      assertIdentity(scope);
      await ensurePracticeConversation(scope);
      assertIdentity(scope);
      if (
        state.role !== "viewer" ||
        !state.viewerId ||
        !state.conversationId ||
        !state.conversationRendered ||
        !Array.isArray(state.history) ||
        !err.hidden ||
        !$("#accessError").hidden
      )
        throw new Error("join_gate_failed");
    }
    $("#accessDialog").close();
    navTo(state.role === "creator" ? "studio" : "audience");
    startRefreshTimers();
    renderSavedIdentities();
    startBackendDiagnostics(identityScope());
  } catch (error) {
    if (error.name === "AbortError" || formEpoch !== state.identityEpoch)
      return;
    showError(
      err,
      error.status === 503
        ? t("connectionError")
        : error.status === 401 || error.status === 403 || error.status === 404
          ? t("joinFailed")
          : error.code === "timeout"
            ? t("timeoutError")
            : t("genericError"),
    );
    if (![401, 403, 404, 503].includes(error.status)) setConnection(false);
  } finally {
    if (formEpoch === state.identityEpoch) setBusy(btn, false);
  }
});
function navTo(view) {
  const speechRoot = $('#wave21Speech');
  const activitiesRoot = $('#wave24Activities');
  const deliveryRoot = $('#wave20Delivery');
  const packDetails = $('#wave24Pack')?.closest('details');
  if (packDetails && view === 'audience' && state.role === 'viewer') $('#wave23Listening').before(packDetails);
  if (packDetails && view === 'studio' && state.role === 'creator') $('#wave21Visual').before(packDetails);
  if (deliveryRoot && view === 'studio' && state.role === 'creator') $('#wave21Speech').before(deliveryRoot);
  if (activitiesRoot && view === 'audience' && state.role === 'viewer') $('#wave23Listening').before(activitiesRoot);
  if (activitiesRoot && view === 'studio' && state.role === 'creator') $('#wave21Visual').before(activitiesRoot);
  if (speechRoot && view === 'audience' && state.role === 'viewer') $('#wave23Listening').before(speechRoot);
  if (speechRoot && view === 'studio' && state.role === 'creator') $('#wave21Visual').before(speechRoot);
  phase11Controller?.visibility(view === "together" && !tabOnlyAccess);
  collaborationController?.visibility(view === "collaboration" && !tabOnlyAccess);
  $$(".nav-item").forEach((x) =>
    (x.classList.toggle("active", x.dataset.view === view), x.dataset.view === view ? x.setAttribute("aria-current", "page") : x.removeAttribute("aria-current")),
  );
  $$(".view").forEach((x) =>
    x.classList.toggle("active", x.id === `view-${view}`),
  );
  if (view === "studio") { loadStudio(); loadOperations(); }
  if (view === "audience" && state.role === "viewer") { loadBookmarks(); loadCaptureStatus(); loadCatchup(); loadActivity(); loadNotebook(); }
  if (view === "stage") renderStage();
  if (view === "practice") {
    const source = $("#questionSource").selectedOptions[0];
    $("#practiceContext").textContent = source?.value ? `Selected context: ${source.textContent}${$("#questionMoment").value ? ` · ${$("#questionMoment").value}` : ""}` : "Practice uses available context; no exact source selected.";
    loadPractices();
  }
  if (!tabOnlyAccess && ["perspectives", "work", "inquiry", "project"].includes(view)) phase6Controller?.load(view);
  $("#main").focus({ preventScroll: true });
}
$$(".nav-item").forEach((b) =>
  b.addEventListener("click", () => navTo(b.dataset.view)),
);
$("#language").addEventListener("change", (e) => {
  state.lang = e.target.value;
  if (!tabOnlyAccess) localStorage.setItem("entrelineas.lang", state.lang);
  applyLanguage();
  renderContextFreshness();
  wave19Entry?.refresh();
  if (sourceContextStale) {
    const sources = normalizeList(state.context?.sources || state.context);
    $("#contextSummary").textContent = (sources.length ? sources.length + " " + (state.lang === "es" ? "fuentes recibidas" : "sources received") : t("contextEmpty")) + " · " + t("contextRefreshShort");
  }
});
$("#editSession").addEventListener("click", () =>
  $("#sessionDialog").showModal(),
);
const sessionDialog = $("#sessionDialog");
$("#sessionClose").addEventListener("click", () => sessionDialog.close());
$("#sessionCancel").addEventListener("click", () => sessionDialog.close());
$("#refreshContext").addEventListener("click", async () => {
  const scope = identityScope(), button = $("#refreshContext");
  button.disabled = true;
  $("#contextFreshness").textContent = t("contextRefreshing");
  try { await refreshSources(scope); assertIdentity(scope); clearContextRefreshFailureToast(); }
  catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError") return;
    if ([401, 403, 404].includes(error.status) && scope.role === "viewer") viewerAccessLost(scope);
  }
  finally { if (scope.epoch === state.identityEpoch) button.disabled = false; }
});
$("#contextDetails").addEventListener("click", async () => {
  const scope = identityScope();
  try { await refreshSources(scope); assertIdentity(scope); }
  catch (error) { if (scope.epoch !== state.identityEpoch || error.name === "AbortError") return; contextRefreshFailureToast(state.lang === "es" ? "No se pudo actualizar el contexto." : "Could not refresh context."); }
  $("#contextDialog").showModal();
});
$("#manageSources").addEventListener("click", async () => {
  const scope = identityScope();
  try {
    await refreshSources(scope);
    assertIdentity(scope);
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
      return;
  }
  assertIdentity(scope);
  $("#contextDialog").showModal();
});
$("#closeContext").addEventListener("click", () => $("#contextDialog").close());
$("#questionForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = $("#question"),
    text = input.value.trim(),
    err = $("#audienceError"),
    button = $("button[type=submit]", e.currentTarget);
  if (!text) return;
  const scope = identityScope();
  await withDraftActionLock(scope, err, async () => {
  clearError(err);
  persistDraft(scope);
  setBusy(button, true, t("sending"));
  $("#audienceError").hidden = false; $("#audienceError").textContent = "Working on your question…";
  try {
    await refreshSources(scope);
    assertIdentity(scope);
    await ensureConversation();
    assertIdentity(scope);
    if (!state.conversationId) throw new Error("conversation_unavailable");
    const cid = state.conversationId;
    if (state.pendingPracticeAction) {
      showError(err, "An earlier practice request is unconfirmed. Resolve it before starting a question.");
      return;
    }
    const chosenSource = $("#questionSource").value;
    const typedMoment = $("#questionMoment").value.trim();
    const correction = state.nextCorrection || null;
    const signature = JSON.stringify({
      text,
      chosenSource,
      typedMoment,
      correction,
      language: state.lang,
    });
    let action = pendingActionMatches(
      state.pendingQuestionAction,
      signature,
      cid,
    )
      ? state.pendingQuestionAction
      : null;
    if (state.pendingQuestionAction && !action) {
      showError(err, "An earlier question is unconfirmed. Restore its original inputs and retry it before starting another request.");
      return;
    }
    if (!action) {
      const currentSources = normalizeList(state.context).filter(
        (x) => x.status === "active",
      );
      const sourceIds = (
        chosenSource
          ? currentSources.filter((x) => x.id === chosenSource)
          : currentSources.filter(
              (x) => !x.image && !x.hasImage && x.kind !== "capture",
            )
      )
        .map((x) => x.id)
        .filter(Boolean);
      const moment =
        typedMoment ||
        currentSources.find((x) => x.id === chosenSource)?.at ||
        null;
      action = {
        signature,
        conversationId: cid,
        clientRequestId: newRequestId(),
        payload: {
          text,
          sourceIds,
          sourceSelector: { sourceId: chosenSource || null, at: moment },
          moment,
          language: state.lang,
          ...(correction ? { correction } : {}),
        },
      };
      state.pendingQuestionAction = action;
      if (!persistDraft(scope, {name: "pendingQuestionAction", expected: null, value: action})) {
        state.pendingQuestionAction = null;
        showError(err, "The question could not be safely saved for recovery. Use saved access or check browser storage; no request was sent.");
        return;
      }
    }
    assertIdentity(scope);
    let result;
    try {
      result = await API.call(
        "ask",
        { ...action.payload, clientRequestId: action.clientRequestId },
        cid,
        { scope },
      );
    } catch (error) {
      assertIdentity(scope);
      if (error.code === "activity_unavailable") {
        persistDraft(scope, {name: "pendingQuestionAction", expected: action.clientRequestId, value: null});
        state.pendingQuestionAction = null;
        if (!state.pendingPracticeAction) state.pendingPracticeActivity = null;
        persistDraft(scope);
        await loadActivity(scope);
      } else if (definitiveActionError(error)) {
        persistDraft(scope, {name: "pendingQuestionAction", expected: action.clientRequestId, value: null});
        state.pendingQuestionAction = null;
        persistDraft(scope);
      }
      throw error;
    }
    assertIdentity(scope);
    if (result.clarification_required === true) {
      persistDraft(scope, {name: "pendingQuestionAction", expected: action.clientRequestId, value: null});
      state.pendingQuestionAction = null;
      persistDraft(scope);
      const sourceSelector = result.sourceSelector || result;
      const choices = normalizeList(
        sourceSelector.allowedSources ||
          sourceSelector.options ||
          result.allowedSources,
      );
      state.questionSourceChoices = choices;
      const selector = $("#questionSource");
      const existing = new Set(
        [...selector.options].map((option) => option.value),
      );
      choices.forEach((source) => {
        if (!source.id || existing.has(source.id)) return;
        const option = document.createElement("option");
        option.value = source.id;
        option.textContent = `${source.title || source.id}${source.at ? ` · ${source.at}` : ""}`;
        selector.append(option);
      });
      const clarification = document.createElement("div");
      $("#audienceError").textContent =
        state.lang === "es"
          ? "Hace falta precisar el momento o la fuente. Elige una fuente exacta y vuelve a enviar tu pregunta."
          : "Please clarify the moment or source. Choose an exact source and send your question again.";
      $("#audienceError").hidden = false;
      return;
    }
    clearError(err);
    if (result.capture) { ++captureReadGeneration; $("#viewerCapture").textContent = captureText(result.capture); }
    state.nextCorrection = null;
    state.lastMessageId = result.message?.id;
    const ans = result.answer || {},
      answer = ans.text || result.text || "";
    if (!answer) throw new Error("empty_response");
    persistDraft(scope, {name: "pendingQuestionAction", expected: action.clientRequestId, value: null});
    state.pendingQuestionAction = null;
    const user = document.createElement("div"),
      box = document.createElement("div");
    user.className = "message user";
    const userMessageId = result.message?.id;
    if (userMessageId) user.dataset.messageId = userMessageId;
    user.innerHTML = `<span class="message-label">${escapeHtml(t("you"))}</span><p>${escapeHtml(text)}</p>`;
    box.className = "message";
    const answerMessageId = ans.id || result.answer?.id;
    if (answerMessageId) box.dataset.messageId = answerMessageId;
    const refs = normalizeList(ans.citations);
    box.innerHTML = `<span class="message-label">${escapeHtml(t("response"))}${ans.grounded === false ? ` · ${escapeHtml(t("insufficient"))}` : ""}</span><p>${escapeHtml(answer)}</p>${ans.limitations?.length ? `<div class="sources">${ans.limitations.map(escapeHtml).join(" · ")}</div>` : ""}${refs.length ? `<div class="sources"><b>${escapeHtml(t("sources"))}</b>: ${refs.map(renderConversationCitation).join(" · ")}</div>` : ""}<button type="button" class="text-button followup">${escapeHtml(t("contextCorrection"))}</button><div class="correction" hidden><textarea rows="2" placeholder="${escapeHtml(t("contextCorrectionLabel"))}"></textarea><button type="button" class="button secondary correction-send">${escapeHtml(t("sendCorrection"))}</button></div>`;
    attachCorrectionControls(box, scope, text);
    attachAnswerTrail(box, refs, scope, text);
    if (!userMessageId || !state.renderedMessageIds.has(userMessageId)) {
      $("#conversation").append(user);
      if (userMessageId) state.renderedMessageIds.add(userMessageId);
    }
    if (!answerMessageId || !state.renderedMessageIds.has(answerMessageId)) {
      $("#conversation").append(box);
      if (answerMessageId) state.renderedMessageIds.add(answerMessageId);
    }
    input.value = "";
    persistDraft();
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
      return;
    input.value = text;
    persistDraft();
    if (error.code === "stale_context") {
      try { await refreshSources(scope); assertIdentity(scope); }
      catch (refreshError) { if (scope.epoch !== state.identityEpoch || refreshError.name === "AbortError") return; }
      showError(err, state.lang === "es" ? "El contexto cambió mientras se preparaba la respuesta. Revisa las fuentes actuales y vuelve a enviar la pregunta." : "Context changed while preparing the answer. Review current sources and send again.");
      return;
    }
    showError(
      err,
      ["busy", "session_call_limit"].includes(error.code) ? error.message : error.code === "activity_unavailable"
        ? "This activity version is no longer current. Your attempt text is retained; review the latest activity before trying again."
        : error.status === 409
        ? t("requestInterrupted")
        : !Number.isInteger(error.status) || error.status >= 500 || [408, 429].includes(error.status) ||
            error.name === "TimeoutError" ||
            error.name === "AbortError"
          ? t("requestPending")
          : t("askFailed"),
    );
  } finally {
    if (scope.epoch === state.identityEpoch) setBusy(button, false);
  }
  });
});
$("#shareButton").addEventListener("click", (e) => {
  const scope = identityScope();
  const text = $("#shareText").value.trim(),
    review = $("#shareReview");
  if (!text || !$("#shareConsent").checked) {
    showError(review, t("required"));
    return;
  }
  const useAttempt = $("#shareSource").value === "attempt",
    imageAllowed = useAttempt && Boolean(state.lastPracticeImage);
  if ($("#shareIncludeImage").checked && !imageAllowed) {
    showError(review, t("fileUnsupported"));
    return;
  }
  const snapshot = Object.freeze({
    conversationId: useAttempt
      ? state.practiceConversationId
      : state.conversationId,
    messageId: useAttempt ? null : state.lastMessageId,
    attemptId: useAttempt ? state.lastAttemptId : null,
    summary: text,
    consent: true,
    allowPublicDerivative: Boolean($("#sharePublicConsent").checked),
    includeImage: Boolean($("#shareIncludeImage").checked),
  });
  if (!(snapshot.messageId || snapshot.attemptId)) {
    showError(review, t("noShareSource"));
    return;
  }
  state.shareReviewSnapshot = { scope, snapshot };
  review.hidden = false;
  review.innerHTML = `<strong>${escapeHtml(t("shareReviewTitle"))}</strong><blockquote>${escapeHtml(snapshot.summary)}</blockquote><p>${escapeHtml(snapshot.includeImage ? t("shareIncludeImage") : "")}</p><p>${escapeHtml(snapshot.allowPublicDerivative ? t("sharePublicConsent") : "")}</p><button class="button primary" id="confirmShare">${escapeHtml(t("confirmShare"))}</button><button class="button secondary" id="editShare">${escapeHtml(t("editShare"))}</button>`;
  if (snapshot.includeImage && state.lastPracticeImage) {
    const img = document.createElement("img");
    img.src = state.lastPracticeImage;
    img.alt = t("shareIncludeImage");
    img.className = "share-image-preview";
    review.append(img);
  }
  $("#editShare").onclick = () => {
    if (scope.epoch !== state.identityEpoch) return;
    state.shareReviewSnapshot = null;
    $("#shareConsent").checked = false;
    $("#sharePublicConsent").checked = false;
    $("#shareIncludeImage").checked = false;
    review.hidden = true;
    review.replaceChildren();
  };
  $("#confirmShare").onclick = async () => {
    const b = $("#confirmShare");
    const current = {
      conversationId: useAttempt
        ? state.practiceConversationId
        : state.conversationId,
      messageId: useAttempt ? null : state.lastMessageId,
      attemptId: useAttempt ? state.lastAttemptId : null,
      summary: $("#shareText").value.trim(),
      consent: Boolean($("#shareConsent").checked),
      allowPublicDerivative: Boolean($("#sharePublicConsent").checked),
      includeImage: Boolean($("#shareIncludeImage").checked),
      source: $("#shareSource").value,
    };
    const reviewed = {
      ...snapshot,
      source: useAttempt ? "attempt" : "message",
    };
    if (
      state.shareReviewSnapshot?.scope.epoch !== scope.epoch ||
      JSON.stringify(current) !== JSON.stringify(reviewed)
    ) {
      state.shareReviewSnapshot = null;
      review.hidden = true;
      review.replaceChildren();
      $("#shareConsent").checked = false;
      $("#sharePublicConsent").checked = false;
      $("#shareIncludeImage").checked = false;
      showError(review, t("shareReviewChanged"));
      return;
    }
    if (!snapshot.conversationId) {
      showError(review, t("noShareSource"));
      return;
    }
    setBusy(b, true, t("sending"));
    try {
      assertIdentity(scope);
      const requestBody = {
        conversationId: snapshot.conversationId,
        ...(snapshot.attemptId
          ? { attemptId: snapshot.attemptId }
          : { messageId: snapshot.messageId }),
        summary: snapshot.summary,
        consent: snapshot.consent,
        allowPublicDerivative: snapshot.allowPublicDerivative,
        includeImage: snapshot.includeImage,
      };
      await API.call("share", requestBody, { scope });
      assertIdentity(scope);
      toast(t("shared"));
      state.shareReviewSnapshot = null;
      $("#shareText").value = "";
      $("#shareConsent").checked = false;
      $("#sharePublicConsent").checked = false;
      $("#shareIncludeImage").checked = false;
      review.hidden = true;
      review.replaceChildren();
      persistDraft();
      await loadMyShares();
    } catch (error) {
      if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
        return;
      showError(
        review,
        error.status === 409 ? t("staleError") : t("shareFailed"),
      );
    } finally {
      if (scope.epoch === state.identityEpoch) setBusy(b, false);
    }
  };
});
$("#practiceFiles").addEventListener("change", (e) => {
  state.selectedFiles = [...e.target.files];
  $("#fileList").textContent = state.selectedFiles
    .map((f) => `${f.name} (${Math.ceil(f.size / 1024)} KB)`)
    .join(" · ");
});
function toDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
async function fingerprintFile(file, scope) {
  const bytes = await file.arrayBuffer();
  assertIdentity(scope);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  assertIdentity(scope);
  return [...new Uint8Array(digest)]
    .map((part) => part.toString(16).padStart(2, "0"))
    .join("");
}
$("#practiceForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const goal = $("#practiceGoal").value.trim(),
    attempt = $("#practiceAttempt").value.trim(),
    err = $("#practiceError"),
    btn = $("button[type=submit]", e.currentTarget);
  if (!goal || !attempt) return;
  const scope = identityScope();
  await withDraftActionLock(scope, err, async () => {
  clearError(err);
  persistDraft(scope);
  setBusy(btn, true, t("sending"));
  try {
    await ensurePracticeConversation();
    assertIdentity(scope);
    if (!state.practiceConversationId) throw Error("conversation_unavailable");
    let image;
    let imageFingerprint = null;
    const file = state.selectedFiles[0];
    if (file) {
      if (!state.visionSupported)
        throw Object.assign(Error("vision_unsupported"), { status: 415 });
      if (
        !["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
        file.size > 4 * 1024 * 1024
      )
        throw Object.assign(Error("file_unsupported"), { status: 413 });
      imageFingerprint = await fingerprintFile(file, scope);
      image = await toDataUrl(file);
      assertIdentity(scope);
    }
    const cid = state.practiceConversationId;
    if (state.pendingQuestionAction) {
      showError(err, "An earlier question is unconfirmed. Resolve it before starting practice.");
      return;
    }
    const difficulty = $("#practiceDifficulty").value;
    const signatureInput = JSON.stringify({
      goal,
      attempt,
      difficulty,
      selectedSource: $("#questionSource").value,
      language: state.lang,
      activity: state.pendingPracticeActivity
        ? { materialId: state.pendingPracticeActivity.materialId, version: state.pendingPracticeActivity.version }
        : null,
    });
    const signatureBytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(signatureInput));
    assertIdentity(scope);
    const signature = [...new Uint8Array(signatureBytes)].map(x => x.toString(16).padStart(2, "0")).join("");
    let action = pendingActionMatches(
      state.pendingPracticeAction,
      state.pendingPracticeAction?.metadataOnly ? signature : signatureInput,
      cid,
    )
      ? state.pendingPracticeAction
      : null;
    if (state.pendingPracticeAction && !action) {
      showError(err, "An earlier practice request is unconfirmed. Restore its original inputs and retry it before starting another request.");
      return;
    }
    if (action?.imageFingerprint && !file) {
      showError(err, t("imageReselect"));
      return;
    }
    if (action?.imageFingerprint && imageFingerprint !== action.imageFingerprint) {
      showError(err, "Select the original image to check the unconfirmed practice request.");
      return;
    }
    if (action?.imageFingerprint && action.payload && !action.payload.image)
      action.payload.image = image;
    if (action && !action.imageFingerprint && file) {
      showError(err, "Remove the image to check the original unconfirmed practice request.");
      return;
    }
    if (!action) {
      if (state.retryFromAttemptId && !state.history.some(item => item.id === state.retryFromAttemptId)) {
        showError(err, state.lang === "es" ? "No se puede encontrar el intento anterior. Selecciónalo de nuevo o cancela el reintento." : "The previous attempt is unavailable. Select it again or cancel the retry.");
        renderRetrySelection();
        return;
      }
      const previousAttemptId = state.retryFromAttemptId;
      action = {
        signature,
        metadataOnly: true,
        conversationId: cid,
        clientRequestId: newRequestId(),
        imageFingerprint,
        previousAttemptId,
        activity: state.pendingPracticeActivity ? { ...state.pendingPracticeActivity } : null,
      };
      state.pendingPracticeAction = action;
      if (!persistDraft(scope, {name: "pendingPracticeAction", expected: null, value: action})) {
        state.pendingPracticeAction = null;
        showError(err, "Practice could not be safely saved for recovery. Use saved access or check browser storage; no request was sent.");
        return;
      }
    }
    assertIdentity(scope);
    let result;
    try {
      result = await API.call(
        "practice",
        { ...(action.metadataOnly ? {
          goal, difficulty, text: attempt,
          ...($("#questionSource").value ? {sourceIds: [$("#questionSource").value]} : {}),
          language: state.lang,
          ...(image ? { image } : {}),
          ...(action.previousAttemptId ? { previousAttemptId: action.previousAttemptId } : {}),
          ...(action.activity ? { activity: action.activity } : {}),
        } : action.payload), clientRequestId: action.clientRequestId },
        cid,
        { scope },
      );
    } catch (error) {
      assertIdentity(scope);
      if (definitiveActionError(error)) {
        persistDraft(scope, {name: "pendingPracticeAction", expected: action.clientRequestId, value: null});
        state.pendingPracticeAction = null;
        persistDraft(scope);
      }
      throw error;
    }
    const answer = result.answer || {};
    assertIdentity(scope);
    if (result.capture) { ++captureReadGeneration; $("#viewerCapture").textContent = captureText(result.capture); }
    if (!answer.text) throw Error("empty_response");
    persistDraft(scope, {name: "pendingPracticeAction", expected: action.clientRequestId, value: null});
    state.lastAttemptId = result.attempt?.id;
    state.pendingPracticeAction = null;
    state.pendingPracticeActivity = null;
    state.retryFromAttemptId = null;
    $("#practiceActivityPrompt").hidden = true;
    $("#practiceActivityPrompt").textContent = "";
    renderRetrySelection();
    state.lastPracticeImage = image || null;
    const savedAttempt = {
      id: result.attempt?.id,
      goal,
      attempt,
      answer: answer.text,
      citations: answer.citations || [],
      limitations: answer.limitations || [],
      grounded: answer.grounded,
      created_at: result.attempt?.createdAt || new Date().toISOString(),
    };
    const existingAttemptIndex = state.history.findIndex(
      (item) => item.id && item.id === savedAttempt.id,
    );
    if (existingAttemptIndex >= 0)
      state.history[existingAttemptIndex] = savedAttempt;
    else state.history.unshift(savedAttempt);
    renderHistory();
    renderComparisonChoices();
    $("#practiceAttempt").value = "";
    state.selectedFiles = [];
    $("#practiceFiles").value = "";
    $("#fileList").textContent = "";
    persistDraft();
  } catch (error) {
    if (scope.epoch !== state.identityEpoch) return;
    showError(
      err,
      ["busy", "session_call_limit"].includes(error.code) ? error.message : error.status === 409
        ? t("requestInterrupted")
        : !Number.isInteger(error.status) || error.status >= 500 || [408, 429].includes(error.status) ||
            error.name === "TimeoutError" ||
            error.name === "AbortError"
          ? t("requestPending")
          : error.status === 413 || error.status === 415
            ? t("fileUnsupported")
            : t("practiceFailed"),
    );
  } finally {
    if (scope.epoch === state.identityEpoch) setBusy(btn, false);
  }
  });
});
function renderHistory() {
  const scope = identityScope();
  const list = $("#practiceHistoryList");
  if (!state.history.length) {
    list.innerHTML = `<p class="empty-state">${escapeHtml(t("historyEmpty"))}</p>`;
    return;
  }
  list.innerHTML = state.history
    .map(
      (h) =>
        `<article class="history-item"${h.id ? ` data-attempt-id="${escapeHtml(h.id)}"` : ""}><div class="history-meta">${escapeHtml(new Date(h.created_at).toLocaleString())}</div><h3>${escapeHtml(h.goal)}</h3><p><b>${escapeHtml(t("you"))}:</b> ${escapeHtml(h.attempt || "")}</p><p><b>${escapeHtml(t("response"))}${h.grounded === false ? ` · ${escapeHtml(t("groundedNo"))}` : ""}:</b> ${escapeHtml(h.answer || "")}</p>${h.limitations?.length ? `<p class="history-meta">${h.limitations.map(escapeHtml).join(" · ")}</p>` : ""}${
          normalizeList(h.citations).length
            ? `<p class="history-meta"><b>${escapeHtml(t("sources"))}:</b> ${normalizeList(
                h.citations,
              )
                .map(
                  (x) =>
                    `${escapeHtml(x.title || x.sourceId || "")}${x.at ? ` · ${escapeHtml(x.at)}` : ""}${x.excerpt ? ` — ${escapeHtml(x.excerpt)}` : ""}`,
                )
                .join(" · ")}</p>`
            : ""
        }<button class="button secondary retry-attempt" data-id="${escapeHtml(h.id || "")}">${escapeHtml(t("retry"))}</button></article>`,
    )
    .join("");
  $$(".retry-attempt").forEach(
    (b) =>
      (b.onclick = () => {
        if (scope.epoch !== state.identityEpoch) return;
        if (state.pendingPracticeAction) {
          showError($("#practiceError"), "An earlier practice request is unconfirmed. Restore its original inputs and retry it before choosing another attempt.");
          return;
        }
        const h = state.history.find((x) => (x.id || "") === b.dataset.id);
        if (h) {
          state.retryFromAttemptId = h.id;
          renderRetrySelection();
          state.pendingPracticeAction = null;
          $("#practiceGoal").value = h.goal;
          $("#practiceAttempt").value = h.attempt || "";
          persistDraft();
          $("#practiceAttempt").focus();
          navTo("practice");
        }
      }),
  );
}
function renderRetrySelection() {
  const box = $("#retrySelection");
  if (!box) return;
  box.hidden = !state.retryFromAttemptId;
  const selected = state.history.find(item => item.id === state.retryFromAttemptId);
  const label = $("#retrySelectionText");
  if (!selected) {
    label.textContent = state.lang === "es" ? "El intento anterior no está disponible. Selecciónalo de nuevo o cancela el reintento." : "The previous attempt is unavailable. Select it again or cancel the retry.";
  } else {
    const goal = String(selected.goal || "").slice(0, 120);
    const excerpt = String(selected.attempt || "").slice(0, 160);
    label.textContent = `${state.lang === "es" ? "Reintento de" : "Retry of"}: ${goal} — ${excerpt}`;
  }
}
$("#cancelRetry").addEventListener("click", () => {
  if (state.pendingPracticeAction) {
    showError($("#practiceError"), "An earlier practice request is unconfirmed. Restore its original inputs and retry it before changing the retry.");
    return;
  }
  state.retryFromAttemptId = null;
  state.pendingPracticeAction = null;
  renderRetrySelection();
  persistDraft();
});
async function loadPractices() {
  try {
    await ensurePracticeConversation();
  } catch {}
}
async function loadStudio() {
  const scope = identityScope();
  assertIdentity(scope);
  const list = $("#contributions");
  try {
    const [data, materials] = await Promise.all([
      API.call("contributions", null, { scope }),
      API.call("materials", null, { scope }),
    ]);
    assertIdentity(scope);
    state.contributions = normalizeList(data.shares || data);
    state.materials = normalizeList(materials.materials || materials);
    await loadWorkbench(scope);
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
      return;
    list.innerHTML = `<div class="empty-state" role="alert">${escapeHtml(t("studioFailed"))} <button type="button" class="button secondary" id="retryStudio">${escapeHtml(state.lang === "es" ? "Reintentar" : "Retry")}</button></div>`;
    $("#retryStudio").onclick = loadStudio;
  }
}
function renderContributions() {
  const scope = identityScope();
  const list = $("#contributions");
  if (!list) return;
  const n = state.contributions.length;
  $("#studioStats").innerHTML =
    `<span class="stat-chip">${n} ${escapeHtml(n === 1 ? t("oneContribution") : t("manyContributions"))}</span><span class="stat-chip">${escapeHtml(state.lang === "es" ? "Aportaciones seleccionables" : "Selectable contributions")}</span>`;
  const insightHtml = state.insights
    .map(
      (x, index) =>
        `<article class="contribution-card"><span aria-hidden="true">◇</span><div><p><b>${escapeHtml(x.label || x.title || "")}</b></p><div class="contribution-reason"><b>${escapeHtml(t("reason"))}:</b> ${escapeHtml(x.rationale || "")}</div><div class="contribution-meta">${normalizeList(x.shareIds).length} ${escapeHtml(t("sources"))}${normalizeList(
          x.causes,
        )
          .map((c) => ` · ${escapeHtml(c)}`)
          .join("")}</div><div class="contribution-meta">${normalizeList(x.provenance).map(p => `${escapeHtml(p.summary || "")} · ${escapeHtml(p.allowPublicDerivative ? "public derivative allowed" : "creator review only")}`).join("<br>")}</div><p>${escapeHtml(x.reasoningUnavailable ? "Earlier reasoning is unavailable after an input changed. Analyze again to refresh it." : "Review the authorized contributions and any distinct perspectives individually.")}</p><button type="button" class="button secondary select-insight" data-index="${index}">Select these contributions</button></div></article>`,
    )
    .join("");
  const contributionHtml = state.contributions
    .map(
      (c, i) =>
        `<article class="contribution-card"><input type="checkbox" class="contribution-select" id="contrib-${escapeHtml(c.id || i)}" value="${escapeHtml(c.id || "")}" aria-label="${escapeHtml(state.lang === "es" ? "Seleccionar aportación" : "Select contribution")}"><div><p>${escapeHtml(c.summary || c.text || c.content || "")}</p><div class="contribution-meta"><span>${escapeHtml(t("anonymous"))}</span><span>${escapeHtml(c.allowPublicDerivative ? (state.lang === "es" ? "derivado público autorizado" : "public derivative allowed") : state.lang === "es" ? "solo revisión privada" : "private review only")}</span><span>${escapeHtml(c.createdAt ? new Date(c.createdAt).toLocaleString() : "")}</span>${normalizeList(
          c.citations,
        )
          .map(
            (x) =>
              `<span>${escapeHtml(x.title || x.sourceId || "")}${x.at ? ` · ${escapeHtml(x.at)}` : ""}</span>`,
          )
          .join(
            "",
          )}${c.includeImage ? `<span>${escapeHtml(state.lang === "es" ? "Incluye imagen autorizada" : "Includes authorized image")}</span>` : ""}</div></div></article>`,
    )
    .join("");
  const materialHtml = state.materials
    .map((m) => {
      const v = m.versions?.find((x) => x.number === m.currentVersion);
      return `<article class="contribution-card"><span aria-hidden="true">▤</span><div><p><b>${escapeHtml(v?.title || m.format || t("draftTitle"))}</b></p><div class="contribution-meta">${escapeHtml(m.status || "draft")} · ${escapeHtml(m.createdAt ? new Date(m.createdAt).toLocaleString() : "")}</div></div><button type="button" class="button secondary review-material" data-id="${escapeHtml(m.id)}">${escapeHtml(t("reviewMaterial"))}</button></article>`;
    })
    .join("");
  list.innerHTML = `${insightHtml}${contributionHtml || `<div class="empty-state">${escapeHtml(t("noContributions"))}</div>`}${materialHtml}`;
  $$(".select-insight").forEach(button => button.onclick = () => {
    assertIdentity(scope);
    const ids = new Set(normalizeList(state.insights[Number(button.dataset.index)]?.shareIds));
    $$(".contribution-select").forEach(input => { input.checked = ids.has(input.value); });
    $("#editorialFormat").focus();
  });
  $$(".review-material").forEach(b => {
    b.onclick = () => openMaterialForReview(b, b.dataset.id, scope);
  });
}
// This control is available only after the exact replacement was read for review.
function mountProtectedReplacementApproval(parent, origin, kind, id, version, revision, scope, canApprove) {
  const wasTabOnly = tabOnlyAccess;
  const identityCurrent = () => { try { assertIdentity(scope); if (tabOnlyAccess !== wasTabOnly) return false; if (!wasTabOnly) assertSavedIdentity(scope); return scope.role === 'creator'; } catch { return false; } };
  const section = document.createElement('section'), label = document.createElement('label'), opt = document.createElement('input'), approve = document.createElement('button'), recover = document.createElement('button'), status = document.createElement('p');
  opt.type='checkbox'; label.append(opt,document.createTextNode(' Enable protected approval for the reviewed version')); approve.type=recover.type='button'; approve.disabled=!canApprove; approve.textContent='Approve reviewed version'; recover.textContent='Check earlier protected approval'; status.setAttribute('role','status'); section.append(label,approve,recover,status); parent.append(section);
  const reviewCurrent = () => identityCurrent() && origin?.isConnected && section.isConnected && opt.checked && (kind !== 'material' || parent.dataset.id === id && parent.dataset.version === String(version));
  const action = () => createImpactApprovalAction({scope, isCurrent:identityCurrent,
    assertClear:async () => {
      if (!reviewCurrent()) throw Error('Review changed');
      if (localStorage.getItem(`w18-record:${scope.sessionId}:${scope.actorBinding}`) !== null || localStorage.getItem(`entrelineas.w21.impact.v1:${scope.sessionId}:${scope.actorBinding}:replacement`) !== null) throw Error('Earlier action unresolved');
      const replacementJournal=createImpactReplacementJournal({scope,isCurrent:identityCurrent});
      try { if (await replacementJournal.load()) throw Error('Earlier replacement unresolved'); } finally { replacementJournal.destroy(); }
      if (!reviewCurrent()) throw Error('Review changed');
      if (kind === 'material' && localStorage.getItem(`entrelineas.editorial.v2:${scope.role}:${scope.sessionId}:${id}:${capabilityNamespace}`) !== null) throw Error('Earlier material edits remain');
    },
    beforeDispatch:async () => { if (!reviewCurrent()) throw Error('Review changed'); },
    readCurrent:(k,target,s) => API.call(k === 'record' ? 'w18Record' : 'material',null,target,{scope:s}),
    readReceipt:(requestId,s) => API.call('w18RecordOperation',null,requestId,{scope:s}),
    dispatch:(p,s) => p.kind === 'record' ? API.call('w18RecordApprove',{requestId:p.requestId,revision:p.revision,version:p.version},p.id,{scope:s}) : API.call('approve',{version:p.version},p.id,{scope:s})
  });
  approve.onclick=async()=>{ if (!canApprove || !reviewCurrent() || !crypto?.randomUUID) { status.textContent='Review the current version and enable protected approval first.'; return; } approve.disabled=recover.disabled=true; const a=action(); try { const p={kind,id,version,requestId:crypto.randomUUID(),...(kind === 'record' ? {revision} : {})}; await a.submit(p); if (section.isConnected && identityCurrent()) status.textContent='Approval confirmed for the reviewed version.'; } catch { if (section.isConnected && identityCurrent()) status.textContent='Approval could not be confirmed. Check the protected receipt; no request will be repeated.'; } finally { a.destroy(); if (section.isConnected) approve.disabled=!canApprove; recover.disabled=false; } };
  recover.onclick=async()=>{ if (!identityCurrent()) return; approve.disabled=recover.disabled=true; const a=action(); try { const result=await a.readback({kind,id,version}); if (section.isConnected && identityCurrent()) status.textContent=`Protected approval confirmed for ${result.kind}, version ${result.version}.`; } catch { if (section.isConnected && identityCurrent()) status.textContent='No confirmed protected approval is available. Any pending request remains saved; no request was repeated.'; } finally { a.destroy(); if (section.isConnected) approve.disabled=!canApprove; recover.disabled=false; } };
}
// Exact read-only review for the protected correction entry; no mutation is enabled here.
async function openTabOnlyRecordReview(origin, id, version, scope) {
  const guard = () => { assertIdentity(scope); if (!tabOnlyAccess) assertSavedIdentity(scope); if (scope.role !== 'creator' || !origin?.isConnected) throw Error('Review access changed'); };
  guard();
  const options = await API.call('w18RecordOptions', null, {scope}); guard();
  const result = await API.call('w18Record', null, id, {scope}); guard();
  const record = result?.record, snapshot = record?.snapshot;
  if (result?.stale || record?.stale || record?.id !== id || record?.version !== version || !snapshot || !Array.isArray(snapshot.refs) || !Array.isArray(snapshot.sourceRefs ?? []) || !Array.isArray(options?.moments) || !Array.isArray(options?.sources)) throw Error('Record version or sources unavailable');
  const canon = x => Array.isArray(x) ? x.map(canon) : x && typeof x === 'object' ? Object.fromEntries(Object.keys(x).sort().map(k => [k,canon(x[k])])) : x;
  const same = (a,b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));
  const refs = snapshot.refs.map(ref => options.moments.find(x => same(x.ref,ref) && x.sourceTitle && typeof x.text === 'string'));
  const sources = (snapshot.sourceRefs ?? []).map(ref => options.sources.find(x => same(x.ref,ref) && x.sourceTitle));
  if ((!refs.length && !sources.length) || refs.some(x => !x) || sources.some(x => !x)) throw Error('Current sources unavailable');
  const section = document.createElement('section'); section.tabIndex = -1;
  const add = (tag,value) => { const node=document.createElement(tag); node.textContent=value; section.append(node); };
  add('h3',`Record version ${record.version} · ${record.state}`);
  for (const source of refs) add('p',`${source.sourceTitle}: ${source.text}`);
  for (const source of sources) add('p',`Whole source: ${source.sourceTitle} · ${source.ref.sourceId} · revision ${source.ref.sourceRevision}`);
  for (const chapter of snapshot.chapters || []) add('p',`Chapter: ${chapter.title}`);
  add('p',snapshot.decision?.decision || ''); add('p',snapshot.decision?.consequence || '');
  const contributions=(options.formats || []).flatMap(f => f.contributions || []);
  for (const c of snapshot.contributions || []) { const match=contributions.find(x => x.id===c.id && x.revision===c.revision); if (!match) throw Error('Current contribution unavailable'); add('p',[match.selection,match.reason,match.alternative].filter(Boolean).join(' — ')); }
  for (const [lang,value] of Object.entries(snapshot.interpretations || {})) { if(typeof value !== 'string') throw Error('Interpretation unavailable'); add('h4',lang.toUpperCase()); add('p',value); }
  if (Number.isSafeInteger(record._revision)) mountProtectedReplacementApproval(section,origin,'record',id,version,record._revision,scope,record.state === 'draft');
  guard(); origin.parentElement.querySelector('[data-protected-record-review]')?.remove(); section.dataset.protectedRecordReview=''; origin.after(section); section.focus(); section.scrollIntoView({block:'start'});
}
let materialReviewPending = null;
async function openMaterialForReview(button, materialId, scope, requiredVersion = null) {
  if (materialReviewPending?.epoch === scope.epoch || !button.isConnected) { if (requiredVersion !== null) throw new Error("review_unavailable"); return; }
  try { assertIdentity(scope); } catch (cause) { if (requiredVersion !== null) throw cause; return; }
  const box = $("#editorialDraft");
  const errorText = state.lang === "es" ? "No se pudo abrir. Inténtalo de nuevo." : "Could not open. Try again.";
  let error = button.nextElementSibling;
  if (error?.classList.contains("material-open-error")) error.remove();
  if (box.getAttribute("aria-busy") === "true") {
    error = document.createElement("span"); error.className = "material-open-error"; error.setAttribute("role", "alert");
    error.textContent = state.lang === "es" ? "La revisión actual está guardando un cambio. Inténtalo de nuevo." : "The current review is saving a change. Try again.";
    button.after(error); if (requiredVersion !== null) throw new Error("review_busy"); return;
  }
  const pending = {epoch: scope.epoch};
  materialReviewPending = pending;
  const buttons = $$(".review-material, .workbench-review-material");
  const priorDisabled = new Map(buttons.map(b => [b, b.disabled]));
  buttons.forEach(b => { b.disabled = true; });
  try {
    assertIdentity(scope);
    const result = await API.call("material", null, materialId, { scope });
    assertIdentity(scope);
    if (!button.isConnected) { if (requiredVersion !== null) throw new Error("review_origin_gone"); return; }
    if (box.getAttribute("aria-busy") === "true") throw new Error("review_busy");
    const material = result.material || result;
    if (requiredVersion !== null && (material.id !== materialId || material.currentVersion !== requiredVersion)) throw new Error("review_target_mismatch");
    if (requiredVersion !== null && scope.role !== "creator") throw new Error("review_actor_mismatch");
    if (requiredVersion !== null && (material.redacted || !Array.isArray(material.versions) || !material.versions.some(v => v.number === requiredVersion))) throw new Error("review_content_unavailable");
    renderDraft(material);
    if (requiredVersion !== null) {
      box.querySelectorAll("button,input,textarea,select").forEach(node => { node.disabled = true; });
      mountProtectedReplacementApproval(box,button,"material",materialId,requiredVersion,null,scope,material.status === "draft");
    }
    if (tabOnlyAccess) {
      if (requiredVersion !== null && (box.dataset.id !== materialId || box.dataset.version !== String(requiredVersion))) throw new Error("review_target_mismatch");
      box.tabIndex = -1;
      box.scrollIntoView({ behavior: "smooth", block: "start" });
      box.focus({ preventScroll: true });
      return;
    }
    const expectedVersion = Number(material.versions?.find(v => Number(v.number) === Number(material.currentVersion))?.number || material.currentVersion || material.versions?.at(-1)?.number || 1);
    if (box.dataset.id !== materialId || box.dataset.version !== String(expectedVersion))
      throw new Error("review_target_mismatch");
    box.tabIndex = -1;
    box.scrollIntoView({ behavior: "smooth", block: "start" });
    box.focus({ preventScroll: true });
    $("#draftTitleInput", box)?.focus({ preventScroll: true });
  } catch (cause) {
    if (scope.epoch !== state.identityEpoch || cause.name === "AbortError" || !button.isConnected) { if (requiredVersion !== null) throw cause; return; }
    error = document.createElement("span"); error.className = "material-open-error"; error.setAttribute("role", "alert"); error.textContent = errorText;
    button.after(error);
    if (requiredVersion !== null) throw cause;
  } finally {
    if (materialReviewPending === pending) materialReviewPending = null;
    if (scope.epoch === state.identityEpoch) priorDisabled.forEach((disabled, b) => { if (b.isConnected) b.disabled = disabled; });
  }
}
function lockShareControls(locked) {
  $$(".my-share-public, .my-share-withdraw, .share-refresh, #retryMyShares").forEach(el => { el.disabled = locked; });
  $("#myShares").setAttribute("aria-busy", String(shareMutationPending || shareReadPending));
}
async function loadMyShares(force = false) {
  if (shareMutationPending || (shareStatusUncertain && !force) || (shareReadPending && !force)) return;
  const scope = identityScope(), container = $("#myShares"), generation = ++shareLoadGeneration;
  const copy = (en, es) => state.lang === "es" ? es : en;
  shareReadPending = true;
  lockShareControls(true);
  try {
    const data = await API.call("contributions", null, { scope });
    assertIdentity(scope);
    if (generation !== shareLoadGeneration || shareMutationPending) return;
    const shares = normalizeList(data.shares || data);
    shareStatusUncertain = false;
    container.innerHTML = shares.length ? `<h3>${escapeHtml(t("mySharesTitle"))}</h3>` + shares.map(x =>
      `<article class="my-share"><p><strong>${escapeHtml(copy("Shared summary", "Resumen compartido"))}:</strong> ${escapeHtml(x.summary)}</p><p class="share-permission">${escapeHtml(x.allowPublicDerivative ? copy("Public derivative allowed", "Derivado público autorizado") : copy("Creator review only", "Solo revisión del creador"))}</p><p>${escapeHtml(copy("The creator can review this contribution; original images are never authorized for public presentation by this choice.", "El creador puede revisar esta aportación; esta opción nunca autoriza presentar imágenes originales en público."))}</p><label class="check-line"><input type="checkbox" class="my-share-public" data-id="${escapeHtml(x.id)}" ${x.allowPublicDerivative ? "checked" : ""}><span>${escapeHtml(t("sharePublicConsent"))}</span></label><button type="button" class="button danger my-share-withdraw" data-id="${escapeHtml(x.id)}">${escapeHtml(t("withdrawMine"))}</button></article>`).join("") : `<p class="empty-state">${escapeHtml(t("noContributions"))}</p>`;
    container.querySelectorAll(".my-share").forEach(card => {
      const check = card.querySelector(".my-share-public"), withdraw = card.querySelector(".my-share-withdraw");
      const confirmed = check.checked;
      const mutate = async (action) => {
        if (tabOnlyAccess) { check.checked = confirmed; toast("Changing a contribution requires saved access for recovery."); return; }
        if (shareMutationPending || shareStatusUncertain || shareReadPending) { check.checked = confirmed; return; }
        const selected = check.checked;
        shareMutationPending = true;
        ++shareLoadGeneration;
        lockShareControls(true);
        try {
          await API.call(action, action === "shareConsentUpdate" ? {allowPublicDerivative: selected} : null, check.dataset.id, {scope});
          assertIdentity(scope);
          shareMutationPending = false;
          shareStatusUncertain = true;
          await loadMyShares(true);
        } catch (error) {
          if (scope.epoch !== state.identityEpoch || error.name === "AbortError") return;
          shareMutationPending = false;
          shareStatusUncertain = true;
          shareReadPending = false;
          showShareRecovery(copy("The result is uncertain. Your selection is retained. Reload status before another change.", "El resultado es incierto. Se conserva tu selección. Recarga el estado antes de otro cambio."));
        }
      };
      check.onchange = () => mutate("shareConsentUpdate");
      withdraw.onclick = () => mutate("withdraw");
    });
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError" || generation !== shareLoadGeneration) return;
    shareStatusUncertain = true;
    showShareRecovery(copy("Could not load current share status. Your selections are retained. Reload status to continue.", "No se pudo cargar el estado actual. Se conservan tus selecciones. Recarga el estado para continuar."));
  } finally {
    if (scope.epoch === state.identityEpoch && generation === shareLoadGeneration) {
      shareReadPending = false;
      lockShareControls(shareStatusUncertain);
      const retry = $("#retryMyShares");
      if (retry) retry.disabled = false;
    }
  }
}
function showShareRecovery(message) {
  $("#shareStatusError")?.remove();
  $("#retryMyShares")?.remove();
  $("#myShares").insertAdjacentHTML("beforeend", `<p id="shareStatusError" class="inline-error" role="alert">${escapeHtml(message)}</p><button type="button" class="button secondary" id="retryMyShares">${escapeHtml(state.lang === "es" ? "Recargar estado" : "Reload status")}</button>`);
  lockShareControls(true);
  $("#myShares").setAttribute("aria-busy", "false");
  $("#retryMyShares").disabled = false;
  $("#retryMyShares").onclick = () => loadMyShares(true);
}
$(".share-panel").addEventListener("toggle", () => {
  if ($(".share-panel").open) loadMyShares();
});
$("#refreshStudio").addEventListener("click", loadStudio);
$("#analyzeContributions").addEventListener("click", async event => {
  const scope = identityScope(), button = event.currentTarget, status = $("#insightStatus");
  if (tabOnlyAccess) { status.textContent = "Analyzing contributions requires saved access for request recovery."; return; }
  setBusy(button, true, "Analyzing…"); status.textContent = "Analyzing shared contributions…";
  try {
    await API.call("insights", null, {scope}); assertIdentity(scope);
    await loadWorkbench(scope); assertIdentity(scope);
    status.textContent = "Review the rationale and authorized provenance before using a group.";
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") status.textContent = ["busy", "session_call_limit"].includes(error.code) ? error.message : "Analysis unavailable. Your contributions remain available for individual review.";
  } finally { if (scope.epoch === state.identityEpoch) setBusy(button, false); }
});
$("#createEditorial").addEventListener("click", async (e) => {
  const scope = identityScope();
  if (tabOnlyAccess) { showError($("#editorialError"), "Preparing a draft requires saved access for request recovery."); return; }
  const button = e.currentTarget;
  const ids = $$(".contribution-select:checked")
      .map((x) => x.value)
      .filter(Boolean),
    err = $("#editorialError");
  if (!ids.length) {
    showError(err, t("selectContribution"));
    return;
  }
  clearError(err);
  setBusy(button, true, t("drafting"));
  try {
    const result = await API.call(
      "editorial",
      {
        shareIds: ids,
        format: $("#editorialFormat").value,
        instruction: $("#editorialFocus").value.trim(),
        language: state.lang,
      },
      { scope },
    );
    assertIdentity(scope);
    const material = result.material || result;
    renderDraft(material);
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
      return;
    showError(
      err,
      ["busy", "session_call_limit"].includes(error.code) ? error.message : error.code === "provider_unavailable"
        ? t("providerUnavailable")
        : error.code === "invalid_blocks"
          ? t("providerError")
          : t("editorialFailed"),
    );
  } finally {
    if (scope.epoch === state.identityEpoch) setBusy(button, false);
  }
});
function renderDraft(d) {
  const scope = identityScope(), box = $("#editorialDraft");
  // An external review/load must not replace a version mutation in progress.
  if (box.getAttribute("aria-busy") === "true") return;
  // Saved editorial drafts are not restored or changed in tab-only access.
  if (tabOnlyAccess) {
    const versions = normalizeList(d.versions);
    const current = d.currentVersion == null ? null : versions.find(item => Number(item.number) === Number(d.currentVersion));
    box.hidden = false;
    box.replaceChildren();
    delete box.dataset.id;
    delete box.dataset.version;
    if (!current) {
      const message = document.createElement("p");
      message.textContent = "The current material version is unavailable. Refresh before reviewing it.";
      box.append(message);
      return;
    }
    box.dataset.id = d.id;
    box.dataset.version = String(current.number);
    const heading = document.createElement("h3");
    heading.textContent = current.title ?? "Material";
    const body = document.createElement("p");
    body.className = "preserve-lines";
    body.textContent = current.body ?? "";
    const blocks = document.createElement("div");
    for (const block of normalizeList(current.blocks)) {
      if (!block || typeof block !== "object") continue;
      const section = document.createElement("section");
      const label = document.createElement("h4");
      label.textContent = typeof block.type === "string" ? block.type : "Content";
      section.append(label);
      if (typeof block.text === "string") {
        const text = document.createElement("p");
        text.className = "preserve-lines";
        text.textContent = block.text;
        section.append(text);
      }
      for (const item of normalizeList(block.items)) {
        if (typeof item !== "string") continue;
        const text = document.createElement("p");
        text.className = "preserve-lines";
        text.textContent = item;
        section.append(text);
      }
      blocks.append(section);
    }
    const message = document.createElement("p");
    message.textContent = "Read-only review. Editing and actions require saved access so recovery remains protected.";
    box.append(heading, body, blocks, message);
    return;
  }
  const copy = (en, es) => state.lang === "es" ? es : en;
  const versions = normalizeList(d.versions);
  const v = versions.find(x => Number(x.number) === Number(d.currentVersion)) || versions.at(-1) || {};
  const version = Number(v.number || d.currentVersion || 1);
  const activity = v.activity || d.activity || null;
  const title = v.title || d.title || "", body = v.body || d.body || "", blocks = normalizeList(v.blocks);
  const key = `entrelineas.editorial.v2:${state.role}:${state.sessionId}:${d.id}:${capabilityNamespace}`;
  let saved;
  try {
    assertSavedIdentity(scope);
    const raw = localStorage.getItem(key);
    saved = raw === null ? null : JSON.parse(raw);
    if (raw !== null && (!saved || typeof saved !== "object" || Array.isArray(saved) ||
        typeof saved.title !== "string" || typeof saved.body !== "string" || !Array.isArray(saved.blocks))) {
      throw new Error("Saved draft is unavailable");
    }
  } catch {
    box.hidden = false;
    box.replaceChildren();
    const message = document.createElement("p");
    message.setAttribute("role", "alert");
    message.textContent = "The saved draft could not be read safely. Your existing work has not been changed; restore access to it before editing this material.";
    box.append(message);
    return;
  }
  const edit = saved || {title, body, blocks};
  const baseVersion = Number(saved?.version || version), staleSaved = baseVersion !== version, requiresResolution = staleSaved || Boolean(saved?.needsReview);
  const editedBlocks = structuredClone(edit.blocks || blocks);
  const isMirror = (candidate, text) => d.format === "explanation" && candidate.length === 1 && candidate[0]?.type === "text" && candidate[0].text === text && Object.keys(candidate[0]).every(k => k === "type" || k === "text");
  const savedBase = versions.find(x => Number(x.number) === baseVersion);
  const canonicalBody = edit.canonicalBody ?? isMirror(normalizeList(savedBase?.blocks || blocks), savedBase?.body ?? body);
  const unsupported = list => list.length > 20 || list.some(b => !["text", "callout", "steps", "comparison"].includes(b.type) || Object.keys(b).some(k => !["type", "text", "items"].includes(k)) || ("text" in b && typeof b.text !== "string") || ("items" in b && (!Array.isArray(b.items) || b.items.length > 12 || b.items.some(x => typeof x !== "string"))));
  const unsupportedBlocks = unsupported(editedBlocks) || unsupported(blocks);
  const shareIds = normalizeList(d.shareIds).map(x => typeof x === "string" ? x : x.id);
  const publicEligible = shareIds.length > 0 && shareIds.every(id => state.contributions.some(share => share.id === id && share.active !== false && share.allowPublicDerivative === true));
  const linkedShares = shareIds.map(id=>state.contributions.find(item=>item.id===id&&item.active!==false)).filter(Boolean);
  box.hidden = false;
  box.dataset.id = d.id;
  box.dataset.version = String(version);
  box.dataset.status = d.status || "draft";
  box.dataset.dirty = saved ? "true" : "false";
  box.innerHTML = `<div class="draft-toolbar"><strong>${escapeHtml(t("draftTitle"))} · ${escapeHtml(d.format || "")} · v${version}</strong><span class="draft-state">${escapeHtml(d.status || "draft")} · ${escapeHtml(v.provider || "")}${v.limitations?.length ? ` · ${escapeHtml(v.limitations.join("; "))}` : ""}</span></div>
    <div class="contribution-reason"><b>${escapeHtml(t("reason"))}:</b> ${escapeHtml(v.rationale || "")}</div>
    <div class="contribution-meta">${normalizeList(v.citations).map(x => `${escapeHtml(x.title || x.sourceId || "")}${x.at ? ` · ${escapeHtml(x.at)}` : ""}${x.excerpt ? ` — ${escapeHtml(x.excerpt)}` : ""}`).join(" · ")}</div>
    ${activity ? `<p class="muted">This exact activity version is linked to ${linkedShares.length} currently active viewer-shared contribution(s). Shared input is reviewed here; private conversation and continuation are excluded.</p>${linkedShares.map(x=>`<p class="contribution-meta">Linked contribution: ${escapeHtml(x.summary||x.text||"Shared topic")}</p>`).join("")}${linkedShares.length<shareIds.length?`<p class="history-meta">Some linked contributions are unavailable; current server eligibility controls presentation.</p>`:""}` : ""}
    ${!publicEligible ? `<p class="history-meta">${escapeHtml(t("publicConsentNeeded"))}</p>` : ""}
    ${requiresResolution ? `<section class="draft-recovery" aria-labelledby="draftRecoveryTitle"><h3 id="draftRecoveryTitle">${escapeHtml(copy("Review a version conflict", "Revisar conflicto de versiones"))}</h3><p role="alert">${escapeHtml(copy(`Your local edits are based on v${baseVersion}; the server is at v${version}. Nothing has been overwritten.`, `Tus cambios locales parten de v${baseVersion}; el servidor está en v${version}. No se ha sobrescrito nada.`))}</p><details open><summary>${escapeHtml(copy(`Current server content · v${version}`, `Contenido actual del servidor · v${version}`))}</summary><h4>${escapeHtml(title)}</h4><p class="preserve-lines">${escapeHtml(body)}</p>${renderBlockPreview(blocks)}</details><p>${escapeHtml(copy("Your local content is in the editor below. Retaining it uses the reviewed current version as its base and replaces title, body and blocks on the next Save. Consent and source freshness are still checked by the server.", "Tu contenido local está en el editor de abajo. Conservarlo usa la versión actual revisada como base y reemplaza título, cuerpo y bloques al guardar. El servidor sigue comprobando el consentimiento y las fuentes."))}</p><button type="button" class="button secondary" id="rebaseDraft">${escapeHtml(copy("Retain local edits on reviewed version", "Conservar cambios sobre la versión revisada"))}</button><button type="button" class="button danger" id="discardLocalDraft">${escapeHtml(copy("Discard local edits and use current", "Descartar cambios locales y usar la actual"))}</button></section>` : ""}
    <p class="history-meta editorial-output-hint">${escapeHtml(t("editorialOutputHint"))}</p>
    <label for="draftTitleInput">${escapeHtml(t("editorialTitleLabel"))}${requiresResolution ? ` · ${escapeHtml(copy("local edits", "cambios locales"))}` : ""}</label><input id="draftTitleInput" maxlength="200" value="${escapeHtml(edit.title)}">
    <label for="draftContent">${escapeHtml(t("draftTitle"))}</label><textarea id="draftContent" maxlength="8000">${escapeHtml(edit.body)}</textarea>
    <fieldset class="activity-editor"><legend>Connected learning activity</legend><label class="check-line"><input id="activityEnabled" type="checkbox" ${activity ? "checked" : ""}><span>Save this exact version as an explanation + example + steps bundle</span></label><label>Explanation<textarea id="activityExplanation" maxlength="4000">${escapeHtml(edit.activity?.explanation ?? activity?.explanation ?? "")}</textarea></label><label>Example<textarea id="activityExample" maxlength="4000">${escapeHtml(edit.activity?.example ?? activity?.example ?? "")}</textarea></label><label>Steps, one per line<textarea id="activitySteps" maxlength="12012">${escapeHtml(edit.activity?.steps?.join("\n") ?? activity?.steps?.join("\n") ?? "")}</textarea></label><label class="check-line"><input id="activityAttemptEnabled" type="checkbox" ${(edit.activity?.optionalAttempt ?? activity?.optionalAttempt) ? "checked" : ""}><span>Offer an optional private attempt</span></label><label>Attempt goal<input id="activityAttemptGoal" maxlength="500" value="${escapeHtml(edit.activity?.optionalAttempt?.goal ?? activity?.optionalAttempt?.goal ?? "")}"></label><label>Attempt prompt<textarea id="activityAttemptPrompt" maxlength="4000">${escapeHtml(edit.activity?.optionalAttempt?.prompt ?? activity?.optionalAttempt?.prompt ?? "")}</textarea></label><p class="muted">The viewer may read the activity without attempting it. Approval and presentation apply to this whole exact version.</p></fieldset>
    ${canonicalBody ? "" : unsupportedBlocks ? `<pre class="unsupported-blocks">${escapeHtml(JSON.stringify(editedBlocks, null, 2))}</pre>` : editedBlocks.map((block, i) => `<fieldset class="editor-block"><legend>${escapeHtml(block.type)} ${i + 1}</legend>${typeof block.text === "string" ? `<label>${escapeHtml(copy("Text", "Texto"))}<textarea class="block-text" data-block="${i}" maxlength="2000">${escapeHtml(block.text)}</textarea></label>` : ""}${Array.isArray(block.items) ? block.items.map((item, j) => `<label>${escapeHtml(copy("Item", "Elemento"))} ${j + 1}<textarea class="block-item" data-block="${i}" data-item="${j}" maxlength="500">${escapeHtml(item)}</textarea></label>`).join("") : ""}</fieldset>`).join("")}
    <div class="draft-actions"><button type="button" class="button secondary" id="saveDraft" ${requiresResolution || unsupportedBlocks ? "disabled" : ""}>${escapeHtml(t("saveEdit"))}</button><button type="button" class="button secondary" id="variantDraft" ${requiresResolution || unsupportedBlocks ? "disabled" : ""}>${escapeHtml(t("variant"))}</button><button type="button" class="button secondary" data-action="postpone">${escapeHtml(t("postpone"))}</button><button type="button" class="button danger" data-action="discard">${escapeHtml(t("reject"))}</button><button type="button" class="button primary" data-action="approve" ${d.status === "draft" && !saved ? "" : "disabled"}>${escapeHtml(t("approve"))}</button><button type="button" class="button primary" data-action="publish" ${d.status === "approved" && !saved && publicEligible ? "" : "disabled"}>${escapeHtml(t("publish"))}</button></div>
    <div class="inline-error" id="draftError" role="alert" hidden></div><p id="draftBusyStatus" role="status"></p><button type="button" class="button secondary" id="refreshDraft">${escapeHtml(copy("Check current version", "Consultar versión actual"))}</button>`;
  const intervention=activity?.intervention||v.intervention||d.intervention;
  if (activity && d.status === "published" && (intervention?.contributionIds?.length||shareIds.length)) { const aggregate=document.createElement("section");aggregate.className="intervention-aggregate";aggregate.setAttribute("aria-label","Voluntary intervention responses");const heading=document.createElement("h3");heading.textContent=`Voluntary responses · version ${version}`;aggregate.append(heading);loadInterventionAggregate(d.id,version,aggregate,scope);box.append(aggregate); }
  const errorBox = $("#draftError"), inputs = $$('input, textarea, button', box);
  let mutationPending = false, conflictBlocked = false;
  const readActivity = () => { if (!$("#activityEnabled").checked) return null; const steps=$("#activitySteps").value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean); const optionalAttempt=$("#activityAttemptEnabled").checked?{goal:$("#activityAttemptGoal").value.trim(),prompt:$("#activityAttemptPrompt").value.trim()}:null; return {explanation:$("#activityExplanation").value.trim(),example:$("#activityExample").value.trim(),steps,optionalAttempt}; };
  const validActivity = activityValue => !activityValue || (activityValue.explanation.length>0 && activityValue.explanation.length<=4000 && activityValue.example.length>0 && activityValue.example.length<=4000 && activityValue.steps.length>=1 && activityValue.steps.length<=12 && activityValue.steps.every(x=>x.length>0&&x.length<=1000) && (!activityValue.optionalAttempt || (activityValue.optionalAttempt.goal.length>0&&activityValue.optionalAttempt.goal.length<=500&&activityValue.optionalAttempt.prompt.length>0&&activityValue.optionalAttempt.prompt.length<=4000)));
  const snapshot = () => ({version: baseVersion, title: $("#draftTitleInput").value, body: $("#draftContent").value, blocks: editedBlocks, activity: readActivity(), canonicalBody, needsReview: Boolean(saved?.needsReview || conflictBlocked)});
  const dirty = () => {
    assertSavedIdentity(scope);
    box.dataset.dirty = "true";
    box.querySelector('[data-action="approve"]').disabled = true;
    box.querySelector('[data-action="publish"]').disabled = true;
    localStorage.setItem(key, JSON.stringify(snapshot()));
  };
  const busy = value => {
    mutationPending = value;
    box.setAttribute("aria-busy", String(value));
    $("#draftBusyStatus").textContent = value ? t("sending") : "";
    inputs.forEach(el => {
      if (value) { el.dataset.draftDisabled = String(el.disabled); el.disabled = true; }
      else { el.disabled = el.dataset.draftDisabled === "true"; delete el.dataset.draftDisabled; }
    });
  };
  const currentRender = () => scope.epoch === state.identityEpoch && errorBox.isConnected;
  const replace = material => { busy(false); renderDraft(material); };
  const conflictMessage = () => copy("The version or consent changed. Local edits are retained. Check the current version and review before continuing.", "La versión o el consentimiento cambiaron. Se conservan los cambios locales. Consulta la versión actual y revísala antes de continuar.");
  if (unsupportedBlocks) showError(errorBox, copy("Unsupported block fields are preserved for inspection. Saving is disabled to prevent data loss.", "Los campos no compatibles se conservan para revisarlos. Guardar está deshabilitado para evitar pérdida de datos."));
  $("#draftTitleInput").oninput = dirty;
  $("#draftContent").oninput = dirty;
  $$("#activityEnabled, #activityExplanation, #activityExample, #activitySteps, #activityAttemptEnabled, #activityAttemptGoal, #activityAttemptPrompt",box).forEach(el=>{el.oninput=dirty;el.onchange=dirty;});
  $$(".block-text, .block-item", box).forEach(el => el.oninput = () => {
    if (el.classList.contains("block-text")) editedBlocks[Number(el.dataset.block)].text = el.value;
    else editedBlocks[Number(el.dataset.block)].items[Number(el.dataset.item)] = el.value;
    dirty();
  });
  if (requiresResolution) {
    $("#rebaseDraft").onclick = () => {
      assertSavedIdentity(scope);
      localStorage.setItem(key, JSON.stringify({...snapshot(), version, needsReview: false}));
      renderDraft(d);
      showError($("#draftError"), copy("Local edits retained on the reviewed version. The next Save replaces its title, body and blocks; review them first.", "Cambios locales conservados sobre la versión revisada. El próximo guardado reemplaza su título, cuerpo y bloques; revísalos antes."));
    };
    $("#discardLocalDraft").onclick = () => { assertSavedIdentity(scope); localStorage.removeItem(key); renderDraft(d); };
  }
  $("#refreshDraft").onclick = async () => {
    if (mutationPending) return;
    busy(true);
    try { assertSavedIdentity(scope); const latest = await API.call("material", null, d.id, {scope}); assertSavedIdentity(scope); replace(latest.material || latest); }
    catch (error) { if (currentRender() && error.name !== "AbortError") showError(errorBox, conflictMessage()); }
    finally { if (currentRender()) busy(false); }
  };
  const mutateVersion = async instruction => {
    if (mutationPending || requiresResolution || conflictBlocked || unsupportedBlocks) return;
    if (instruction && box.dataset.dirty === "true") { showError(errorBox, t("saveEdit")); return; }
    const local = snapshot();
    // Keep the exact submitted work recoverable on network or conflict failure.
    if (!instruction) dirty();
    assertSavedIdentity(scope);
    const submittedDraft = localStorage.getItem(key);
    busy(true);
    clearError(errorBox);
    try {
      const latestResult = await API.call("material", null, d.id, {scope});
      assertSavedIdentity(scope);
      const latest = latestResult.material || latestResult;
      if (Number(latest.currentVersion) !== version) { replace(latest); return; }
      const payload = instruction ? {instruction, language: state.lang} : {title: local.title, body: local.body, blocks: canonicalBody ? [] : local.blocks};
      if (!validActivity(local.activity)) { showError(errorBox,"Complete a nonempty explanation, example, and 1–12 steps. Optional attempt goal and prompt must also be complete."); return; }
      if (local.activity) payload.activity=local.activity;
      // Additive M02 contract: atomically reject stale edits and variants.
      payload.expectedVersion = version;
      const result = await API.call("version", payload, d.id, {scope});
      assertSavedIdentity(scope);
      // A different tab may have saved newer edits while this request ran.
      if (submittedDraft !== null && localStorage.getItem(key) === submittedDraft) localStorage.removeItem(key);
      replace(result.material || result);
      toast(t("saveEdit"));
      await loadStudio();
    } catch (error) {
      if (!currentRender() || error.name === "AbortError") return;
      if (error.status === 409) {
        assertSavedIdentity(scope);
        conflictBlocked = true;
        // A different tab may have replaced the draft while the request ran.
        // Never overwrite its newer edits with this response's stale snapshot.
        if (localStorage.getItem(key) === submittedDraft) localStorage.setItem(key, JSON.stringify({...snapshot(), needsReview: true}));
      }
      showError(errorBox, ["busy", "session_call_limit"].includes(error.code) ? error.message : error.status === 409 ? conflictMessage() : error.status === 503 ? t("providerUnavailable") : t("genericError"));
    } finally { if (currentRender()) { busy(false); if (conflictBlocked) { $("#saveDraft").disabled = true; $("#variantDraft").disabled = true; } if (box.dataset.dirty === "true") { box.querySelector('[data-action="approve"]').disabled = true; box.querySelector('[data-action="publish"]').disabled = true; } } }
  };
  $("#saveDraft").onclick = () => mutateVersion(null);
  $("#variantDraft").onclick = () => {
    if (box.dataset.dirty === "true") { showError(errorBox, t("saveEdit")); return; }
    const direction = prompt(t("variantDirection"));
    if (direction) mutateVersion(direction);
  };
  $$("[data-action]", box).forEach(button => button.onclick = async () => {
    if (mutationPending) return;
    if (box.dataset.dirty === "true") { showError(errorBox, t("saveEdit")); return; }
    const action = button.dataset.action;
    busy(true);
    let actionDraft;
    try {
      assertSavedIdentity(scope);
      actionDraft = localStorage.getItem(key);
      if (action === "approve" || action === "publish") {
        const result = await API.call(action, {version}, d.id, {scope});
        assertSavedIdentity(scope);
        replace(result.material || result);
        toast(t(action === "approve" ? "approved" : "published"));
        if (action === "publish") await renderStage();
      } else {
        await API.call("materialStatus", {status: action === "discard" ? "discarded" : "postponed"}, d.id, {scope});
        assertSavedIdentity(scope);
        box.hidden = true;
        toast(t(action === "discard" ? "rejected" : "postponed"));
      }
    } catch (error) {
      if (!currentRender() || error.name === "AbortError") return;
      if (error.status === 409) {
        assertSavedIdentity(scope);
        conflictBlocked = true;
        if (localStorage.getItem(key) === actionDraft) localStorage.setItem(key, JSON.stringify({...snapshot(), needsReview: true}));
      }
      showError(errorBox, ["busy", "session_call_limit"].includes(error.code) ? error.message : error.status === 409 ? conflictMessage() : error.status === 503 ? t("providerUnavailable") : t("genericError"));
    } finally { if (currentRender()) { busy(false); if (conflictBlocked) { $("#saveDraft").disabled = true; $("#variantDraft").disabled = true; } if (box.dataset.dirty === "true") { box.querySelector('[data-action="approve"]').disabled = true; box.querySelector('[data-action="publish"]').disabled = true; } } }
  });
}

function renderBlockPreview(blocks) {
  return normalizeList(blocks)
    .map((b) => {
      const type = String(b.type || "text");
      const items = normalizeList(b.items).map((x) =>
        typeof x === "string" ? x : x.text || x.label || "",
      );
      const content =
        type === "comparison"
          ? `<div class="editor-comparison-columns">${items
              .map(
                (item, i) =>
                  `<div><b>${escapeHtml(i === 0 ? "A" : i === 1 ? "B" : `${i + 1}`)}</b><p>${escapeHtml(item)}</p></div>`,
              )
              .join("")}</div>`
          : type === "steps"
            ? `<ol>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>`
            : `<p>${escapeHtml(b.text || "")}</p>`;
      return `<div class="editor-block editor-${escapeHtml(type)}"><strong>${escapeHtml(type)}</strong>${b.text && type !== "text" && type !== "callout" ? `<p>${escapeHtml(b.text)}</p>` : ""}${content}</div>`;
    })
    .join("");
}
async function renderStage() {
  const box = $("#stagePreview");
  const scope = identityScope();
  try {
    const data = await API.call("stage", null, { scope });
    assertIdentity(scope);
    const piece = data.material;
    if (!piece) {
      box.innerHTML = `<div class="stage-empty"><span class="stage-mark">e.</span><p>${escapeHtml(t("stageEmpty"))}</p><small>${escapeHtml(t("stageEmptyHint"))}</small></div>`;
      return;
    }
    const blocks = renderBlockPreview(piece.blocks);
    box.innerHTML = `<article class="stage-piece"><div class="eyebrow">${escapeHtml(piece.format || "")}</div><h2>${escapeHtml(piece.title || "")}</h2>${piece.body ? `<p>${escapeHtml(piece.body)}</p>` : ""}${blocks}</article>`;
  } catch {
    if (scope.epoch !== state.identityEpoch) return;
    box.innerHTML = `<div class="stage-empty"><p>${escapeHtml(t("stageFailed"))}</p></div>`;
  }
}
let captureRun = null;
let captureInputRevision = 0;

function clearFrameTiming() {
  $("#captureTimingEnabled").checked = false;
  for (const id of ["captureTimingUtc", "captureTimingOffset", "captureTimingRun"]) $(`#${id}`).value = "";
}

function stopScreenStream({ discardFrame = false } = {}) {
  const stream = state.screenStream;
  state.screenStream = null;
  captureRun = null;
  if (stream) stream.getTracks().forEach(track => track.stop());
  $("#screenPreview").srcObject = null;
  $("#screenPreview").hidden = true;
  $("#stopScreen").hidden = true;
  $("#captureFrame").disabled = true;
  $("#screenStatus").textContent = "";
  if (discardFrame) {
    state.screenImage = null;
    $("#screenFramePreview").removeAttribute("src");
    $("#screenFramePreview").hidden = true;
  }
}

function readFrameTiming(hasImage) {
  if (!$("#captureTimingEnabled").checked) return null;
  const capturedAt = $("#captureTimingUtc").value.trim();
  const offsetText = $("#captureTimingOffset").value.trim();
  const captureRunId = $("#captureTimingRun").value.trim();
  const stamp = Date.parse(capturedAt);
  const utcPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/;
  const dateMatches = Number.isFinite(stamp) && new Date(stamp).toISOString().slice(0, 19) === capturedAt.slice(0, 19);
  const offsetMs = Number(offsetText);
  if (!hasImage || !utcPattern.test(capturedAt) || !dateMatches || !/^\d+$/.test(offsetText)
      || !Number.isSafeInteger(offsetMs) || offsetMs > 864000000
      || !/^[A-Za-z0-9._:-]{1,128}$/.test(captureRunId)) {
    throw new Error("Enter an image and complete valid UTC time, run offset (0–864000000 ms), and capture run ID.");
  }
  return { capturedAt, offsetMs, captureRunId };
}

$("#captureForm").addEventListener("input", () => { captureInputRevision += 1; });
$("#captureForm").addEventListener("change", () => { captureInputRevision += 1; });
$("#captureImage").addEventListener("change", () => {
  state.screenImage = null;
  $("#screenFramePreview").removeAttribute("src");
  $("#screenFramePreview").hidden = true;
  clearFrameTiming();
});
$("#captureFrame").addEventListener("click", () => {
  const video = $("#screenPreview");
  if (!state.screenStream || !captureRun || !video.videoWidth || !video.videoHeight) return;
  const capturedAt = new Date().toISOString();
  const offsetMs = Math.floor(performance.now() - captureRun.origin);
  if (!Number.isSafeInteger(offsetMs) || offsetMs < 0 || offsetMs > 864000000) {
    showError($("#captureError"), "This capture run has expired. Choose a screen or window to start a new run.");
    return;
  }
  const scale = Math.min(1, 1600 / video.videoWidth, 900 / video.videoHeight),
    canvas = document.createElement("canvas");
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  let image = canvas.toDataURL("image/jpeg", 0.72);
  if ((image.length * 3) / 4 > 4 * 1024 * 1024) {
    canvas.width = Math.round(canvas.width * 0.75);
    canvas.height = Math.round(canvas.height * 0.75);
    canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
    image = canvas.toDataURL("image/jpeg", 0.62);
  }
  state.screenImage = image;
  $("#captureImage").value = "";
  $("#captureTimingUtc").value = capturedAt;
  $("#captureTimingOffset").value = String(offsetMs);
  $("#captureTimingRun").value = captureRun.id;
  $("#captureTimingEnabled").checked = true;
  captureInputRevision += 1;
  $("#screenFramePreview").src = image;
  $("#screenFramePreview").hidden = false;
  video.hidden = true;
  $("#screenStatus").textContent = t("frameCaptured");
});
$("#stopScreen").addEventListener("click", () => stopScreenStream());
function clearCaptureDraft() {
  state.captureEpoch++;
  captureInputRevision += 1;
  stopScreenStream({ discardFrame: true });
  clearFrameTiming();
  $("#captureImage").value = "";
}
$("#captureClose").onclick = $("#captureCancel").onclick = () => {
  clearCaptureDraft();
  $("#captureForm").reset();
  $("#captureDialog").close();
};
$("#captureDialog").addEventListener("cancel", () => {
  clearCaptureDraft();
  $("#captureForm").reset();
});
$("#captureDialog").addEventListener("close", () => {
  clearCaptureDraft();
  $("#captureForm").reset();
});
$("#chooseScreen").addEventListener("click", async (e) => {
  e.stopImmediatePropagation();
  clearCaptureDraft();
  const epoch = state.captureEpoch, scope = identityScope();
  try {
    if (!navigator.mediaDevices?.getDisplayMedia) throw Error("unsupported");
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    if (epoch !== state.captureEpoch || !$("#captureDialog").open) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    assertIdentity(scope);
    state.screenStream = stream;
    captureRun = { id: crypto.randomUUID(), origin: performance.now() };
    const video = $("#screenPreview");
    video.srcObject = stream;
    video.hidden = false;
    await video.play();
    assertIdentity(scope);
    if (epoch !== state.captureEpoch || state.screenStream !== stream || !$("#captureDialog").open) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    $("#captureFrame").disabled = false;
    $("#stopScreen").hidden = false;
    $("#screenStatus").textContent = t("screenSharing");
    stream.getVideoTracks()[0].addEventListener("ended", () => {
      if (state.screenStream === stream && epoch === state.captureEpoch && scope.epoch === state.identityEpoch) stopScreenStream();
    }, { once: true });
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || epoch !== state.captureEpoch || error.name === "AbortError") return;
    stopScreenStream();
    $("#screenStatus").textContent = t("screenUnsupported");
  }
}, true);
$("#captureForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (tabOnlyAccess) { showError($("#captureError"), "Adding context requires saved access. Check the source before retrying an unconfirmed submission."); return; }
  const text = $("#captureSourceText").value.trim(),
    file = $("#captureImage").files[0],
    image = state.screenImage,
    err = $("#captureError"),
    btn = $("#captureSubmit");
  clearError(err);
  if (!text && !file && !image) {
    showError(err, t("captureNoContent"));
    return;
  }
  if (!$("#captureConsent").checked) {
    showError(err, t("captureConsentCheck"));
    return;
  }
  const scope = identityScope();
  const captureEpoch = state.captureEpoch;
  const inputRevision = captureInputRevision;
  let frameTiming;
  try { frameTiming = readFrameTiming(!!(image || file)); }
  catch (error) { showError(err, error.message); return; }
  if (
    file &&
    (!["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
      file.size > 4 * 1024 * 1024)
  ) {
    showError(err, t("fileUnsupported"));
    return;
  }
  setBusy(btn, true, t("sending"));
  try {
    const capturedImage = image || (file ? await toDataUrl(file) : null);
    assertIdentity(scope);
    if (captureEpoch !== state.captureEpoch || inputRevision !== captureInputRevision || !$("#captureDialog").open)
      throw new DOMException("Capture changed", "AbortError");
    const result = await API.call(
      "capture",
      {
        title: $("#captureSourceTitle").value.trim() || t("captureTitleLabel"),
        ...(text ? { text } : {}),
        ...(capturedImage ? { image: capturedImage } : {}),
        ...(frameTiming ? { frameTiming } : {}),
        consent: true,
        audienceVisible: $("#captureAudienceVisible").checked,
      },
      { scope },
    );
    assertIdentity(scope);
    if (captureEpoch !== state.captureEpoch || inputRevision !== captureInputRevision || !$("#captureDialog").open)
      throw new DOMException("Capture changed", "AbortError");
    state.captureSourceId = result.source?.id;
    try {
      await refreshSources(scope);
      assertIdentity(scope);
    } catch (error) {
      if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
        return;
    }
    $("#captureStatus").textContent = t("sourceAdded");
    $("#stopCapture").disabled = !state.captureSourceId;
    clearCaptureDraft();
    $("#captureDialog").close();
    $("#captureForm").reset();
    toast(t("sourceAdded"));
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
      return;
    showError(
      err,
      error.status === 409
        ? t("staleError")
        : error.status === 503
          ? t("providerUnavailable")
          : error.status === 413
            ? t("fileUnsupported")
            : t("captureFailed"),
    );
  } finally {
    if (scope.epoch === state.identityEpoch) setBusy(btn, false);
  }
});
$("#startCapture").addEventListener("click", () => {
  $("#captureForm").reset();
  clearCaptureDraft();
  $("#captureDialog").showModal();
});
$("#stopCapture").addEventListener("click", async () => {
  const scope = identityScope();
  if (!state.captureSourceId) return;
  const btn = $("#stopCapture");
  btn.disabled = true;
  try {
    await API.call(
      "sourceUpdate",
      { status: "retracted" },
      state.captureSourceId,
      { scope },
    );
    assertIdentity(scope);
    state.captureSourceId = null;
    $("#captureStatus").textContent = t("captureStopped");
    await refreshSources(scope);
    toast(t("captureStopped"));
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
      return;
    showError(
      $("#stageError"),
      error.status === 409 ? t("staleError") : t("captureFailed"),
    );
    if (scope.epoch === state.identityEpoch) btn.disabled = false;
  }
});
let audioTitle = "";
let audioLanguage = "es";
let audioIdentityScope = null;
let audioProgramCapture = null;
let audioStatusQueue = Promise.resolve();
const terminalAudioRuns = new WeakSet();
function renderLiveAudioState(audioState) {
  state.liveAudioState = audioState;
  const status = $("#liveAudioStatus");
  if (!status) return;
  if (audioState.active) {
    if (!state.audioStartedAt) state.audioStartedAt = Date.now();
    if (!state.audioUiTimer) {
      const scope = audioIdentityScope;
      state.audioUiTimer = setInterval(() => {
        if (
          scope &&
          scope.epoch === state.identityEpoch &&
          identityScope().token === scope.token
        )
          renderLiveAudioState(state.liveAudio.getState());
      }, 1000);
    }
  } else {
    state.audioStartedAt = 0;
    clearInterval(state.audioUiTimer);
    state.audioUiTimer = null;
  }
  const seconds = Math.floor(
    ((audioState.active
      ? Date.now() - state.audioStartedAt
      : audioState.elapsedMs) || 0) / 1000,
  );
  const sourceHelp = audioState.source === "display"
    ? "Choose the program tab or screen in the browser and enable its audio, then try again."
    : "Allow microphone access in the browser and choose an available microphone, then try again.";
  const stateText = audioState.lastError
    ? `Audio capture could not start or continue. ${sourceHelp}`
    : audioState.pending > 0
      ? `${audioState.delayed > 0 ? t("audioDelayed") : t("audioPending")} (${audioState.pending})`
      : state.audioNoSpeech
        ? t("noSpeech")
        : audioState.active
          ? `${audioState.status} · ${seconds}s`
          : t("audioIdle");
  status.textContent = stateText;
  $("#stopLiveAudio").disabled = !audioState.active && audioState.status !== "requesting-permission";
  $("#stopLiveAudio").textContent = audioState.status === "requesting-permission" ? (state.lang === "es" ? "Cancelar solicitud" : "Cancel request") : t("stopAudio");
  $("#startLiveAudio").disabled =
    audioState.active || audioState.status === "requesting-permission";
}
state.liveAudio = createLiveAudioController({
  sendChunk: async (payload, { signal, run } = {}) => {
    const scope = run?.scope;
    if (!scope)
      throw new DOMException("Audio identity unavailable", "AbortError");
    assertIdentity(scope);
    const result = await API.call(
      "transcribe",
      {
        ...payload,
        capturedAtISO: payload.capturedAt,
        title: audioTitle,
        language: audioLanguage,
        ...(run?.program ? {programCapture:run.program} : {}),
        ...(run?.retainOriginalAudio ? {retainOriginalAudio:true} : {}),
      },
      { signal, scope },
    );
    assertIdentity(scope);
    const processingStatus = result.processing?.status || result.status;
    if (processingStatus === "no_speech" || result.no_speech === true) {
      state.audioNoSpeech = true;
      renderLiveAudioState(state.liveAudio.getState());
      return result;
    }
    if (result.source) {
      state.audioNoSpeech = false;
      try { await phase12Controller?.indexReceipt(result, scope); } catch { $("#liveAudioStatus").textContent = "Caption indexing could not be confirmed; refresh the source."; }
      await refreshSources(scope);
      assertIdentity(scope);
    }
    return result;
  },
  onState: (audioState) => {
    if (audioIdentityScope && audioIdentityScope.epoch === state.identityEpoch) {
      renderLiveAudioState(audioState);
      if (audioState.status === "stopped") reportCapture("stopped", audioState.run);
    }
  },
  onGap: (run) => { reportCapture("gap", run); },
  onError: (error) => {
    if (!audioIdentityScope || audioIdentityScope.epoch !== state.identityEpoch)
      return;
    renderLiveAudioState(state.liveAudio.getState());
  },
});
let p12UploadBusy=false, p12UploadAttempt=null;
$("#p12UploadAudio").addEventListener("click", async () => {
 if(tabOnlyAccess){$("#liveAudioStatus").textContent="Audio submission requires saved access. Check the source before retrying an unconfirmed submission.";return;}
 const scope=identityScope(),file=$("#p12AudioFile").files?.[0];
 if(p12UploadBusy||scope.role!=="creator"||!file||!["audio/wav","audio/webm","audio/ogg","audio/mpeg","audio/mp4"].includes(file.type)||file.size<=0||file.size>12*1024*1024||!$("#liveAudioConsent").checked){$("#liveAudioStatus").textContent="Choose an audio file up to 12 MiB and confirm consent.";return;}
 if(p12UploadAttempt?.done){$("#liveAudioStatus").textContent="This upload was already received.";return;}
 p12UploadBusy=true;
 try {if(!p12UploadAttempt){const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=reject;reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.readAsDataURL(file);});assertIdentity(scope);p12UploadAttempt={scope,body:{audio:encoded,mimeType:file.type,consent:true,audienceVisible:$("#liveAudioAudience").checked,captureId:'upload-'+crypto.randomUUID(),chunkId:crypto.randomUUID(),offsetSeconds:0,language:state.lang,retainOriginalAudio:$("#p12RetainAudio").checked},done:false};}
 assertIdentity(p12UploadAttempt.scope);const result=await API.call('transcribe',p12UploadAttempt.body,{scope:p12UploadAttempt.scope});assertIdentity(scope);p12UploadAttempt.done=true;p12UploadAttempt.body.audio='';
 $("#liveAudioStatus").textContent=result.processing?.captionFeed?.status==='indexed'?'Audio received; recording time is unknown.':'Audio received; recording time and caption alignment are unconfirmed.';await refreshSources(scope);await phase12Controller?.indexReceipt(result,scope);
 }catch(e){if(scope.epoch===state.identityEpoch)$("#liveAudioStatus").textContent="Audio submission was not confirmed. Repeating this action uses the same capture ID; check the source first.";}finally{p12UploadBusy=false;}
});
$("#p12AudioFile").addEventListener("change",()=>{if(!p12UploadAttempt||p12UploadAttempt.done)p12UploadAttempt=null;});
$("#startLiveAudio").addEventListener("click", async (event) => {
  if (tabOnlyAccess) { $("#liveAudioStatus").textContent = "Audio capture requires saved access."; return; }
  const button = event.currentTarget;
  const scope = identityScope();
  audioIdentityScope = scope;
  if (!$("#liveAudioConsent").checked) {
    $("#liveAudioStatus").textContent = t("audioConsent");
    return;
  }
  const source = $("#liveAudioSource").value;
  const shared = $("#programAudioIntent").checked;
  const sourceLabel = $("#programSourceLabel").value.trim();
  if (shared && (!sourceLabel || !$("#liveAudioAudience").checked)) { $("#liveAudioStatus").textContent = "Enter a program source label and allow the audience to read the transcripts."; return; }
  audioProgramCapture = shared ? Object.freeze({inputKind:"live_program_audio", sourceLabel, captureRunId:crypto.randomUUID()}) : null;
  const run = Object.freeze({scope, program:audioProgramCapture, retainOriginalAudio:$("#p12RetainAudio").checked});
  state.audioNoSpeech = false;
  audioLanguage = state.lang;
  audioTitle = `${source === "display" ? t("audioDisplay") : t("audioMicrophone")} · ${new Date().toLocaleString()}`;
  setBusy(button, true, t("sending"));
  let programStarted = false;
  try {
    await audioStatusQueue;
    assertIdentity(scope);
    if (run.program) {
      await API.call("setCaptureStatus", {state:"started",programCapture:run.program}, {scope});
      programStarted = true;
    }
    await state.liveAudio.start({
      source,
      audienceVisible: $("#liveAudioAudience").checked,
      title: audioTitle,
      language: audioLanguage,
      run,
    });
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") $("#liveAudioStatus").textContent = "Could not start capture or update its status. Check the connection and try again.";
  } finally {
    if (scope.epoch === state.identityEpoch) {
      setBusy(button, false);
      renderLiveAudioState(state.liveAudio.getState());
      if (programStarted && !state.liveAudio.getState().active) await reportCapture("stopped", run);
    }
  }
});
$("#stopLiveAudio").addEventListener("click", async () => {
  const scope = identityScope(), run = state.liveAudio.getState().run;
  state.liveAudio.stop();
  renderLiveAudioState(state.liveAudio.getState());
  $("#liveAudioStatus").textContent = "Capture stopped locally. Checking program admission status…";
  const confirmed = run?.program ? await reportCapture("stopped", run) : null;
  try { assertIdentity(scope); } catch { return; }
  $("#liveAudioStatus").textContent = confirmed === null ? "Capture stopped locally; no shared program admission was active." : confirmed
    ? "Capture stopped. Program admission stop confirmed; earlier received segments may remain available."
    : "Capture stopped locally, but program admission stop is unconfirmed. Check operations before relying on it.";
});


function captureText(c) {
  if (!c) return "Program context status unavailable.";
  const completed = c.lastCompletedAt ? new Date(c.lastCompletedAt).toLocaleString() : "none";
  const label = c.sourceLabel ? ` · ${c.sourceLabel}` : "";
  const message = c.state === "gap"
    ? "Program context has a gap — answers may miss this interval."
    : c.state === "stopped"
      ? "Stopped — earlier context may still be available."
      : c.state === "delayed"
        ? "Program context is delayed or awaiting its first completed segment."
        : c.state === "current" ? "Program context is current." : "Program context status is unknown.";
  return `${message}${label} Last completed program segment: ${completed}. Recorded gaps: ${c.gaps ?? 0}.`;
}

let captureReadGeneration = 0;
async function loadCaptureStatus(scope = identityScope()) {
  const generation = ++captureReadGeneration;
  try {
    const d = await API.call("captureStatus", null, {scope});
    assertIdentity(scope);
    if (generation === captureReadGeneration) $("#viewerCapture").textContent = captureText(d.capture);
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError") return;
    if ([401, 403, 404].includes(error.status)) { viewerAccessLost(scope); return; }
    if (generation === captureReadGeneration) $("#viewerCapture").textContent = "Program context status unavailable; answers may lack recent context.";
  }
}
function reportCapture(value, run) {
  if (!run?.program || run.scope.role !== "creator") return Promise.resolve(false);
  if (terminalAudioRuns.has(run)) return audioStatusQueue;
  if (value === "stopped") terminalAudioRuns.add(run);
  const {scope, program} = run;
  audioStatusQueue = audioStatusQueue.catch(() => {}).then(async () => {
    assertIdentity(scope);
    await API.call("setCaptureStatus", {state: value, programCapture: program}, {scope});
    assertIdentity(scope);
    return true;
  }).catch(error => {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") {
      $("#liveAudioStatus").textContent = "Could not update program status. Refresh operations before relying on it.";
    }
    return false;
  });
  return audioStatusQueue;
}

async function loadBookmarks(scope = identityScope()) {
  if (scope.role !== "viewer") return;
  const box = $("#bookmarks");
  try {
    const {bookmarks} = await API.call("bookmarks", null, {scope});
    assertIdentity(scope);
    box.replaceChildren();
    if (!bookmarks.length) {
      box.textContent = "No saved sources yet. Open session context to save one.";
      return;
    }
    for (const bookmark of bookmarks) {
      const row = document.createElement("div");
      row.className = "source-item";
      const label = document.createElement("span");
      label.textContent = bookmark.available && bookmark.source
        ? `${bookmark.source.title || "Source"}${bookmark.source.at ? ` · ${bookmark.source.at}` : ""}`
        : "Source unavailable or no longer shared";
      row.append(label);
      if (bookmark.available && bookmark.source) {
        const use = document.createElement("button");
        use.type = "button"; use.className = "button secondary"; use.textContent = "Use for a question";
        use.onclick = async () => {
          try {
            await refreshSources(scope); assertIdentity(scope);
            const selector = $("#questionSource");
            if ([...selector.options].some(option => option.value === bookmark.sourceId)) {
              selector.value = bookmark.sourceId;
              $("#questionMoment").value = bookmark.source.at || "";
              persistDraft(scope); $("#question").focus();
            } else { await loadBookmarks(scope); toast("This source is no longer available."); }
          } catch (error) {
            if (scope.epoch === state.identityEpoch && error.name !== "AbortError") toast("Could not refresh this source.");
          }
        };
        row.append(use);
      }
      const remove = document.createElement("button");
      remove.type = "button"; remove.className = "button secondary"; remove.textContent = "Remove bookmark";
      remove.onclick = async () => {
        if (tabOnlyAccess) { toast("Removing a bookmark requires saved access for recovery."); return; }
        remove.disabled = true;
        try { await API.call("deleteBookmark", null, bookmark.id, {scope}); await loadBookmarks(scope); }
        catch (error) {
          if (scope.epoch === state.identityEpoch && error.name !== "AbortError") {
            remove.disabled = false; toast("Could not remove bookmark.");
          }
        }
      };
      row.append(remove); box.append(row);
    }
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") box.textContent = "Saved sources could not be loaded. Try again.";
  }
}

function exactKeys(value, keys) { return Boolean(value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).sort().join(",") === [...keys].sort().join(",")); }
function validNotebookArtifact(value) {
  return exactKeys(value,["schemaVersion","items"]) && value.schemaVersion===1 && Array.isArray(value.items) && value.items.length>=1 && value.items.length<=100 && value.items.every(item=>{
    if(!exactKeys(item,["kind","text","reference"])||!["note","message","attempt","reference"].includes(item.kind)||typeof item.text!=="string"||item.text.length>4000)return false;
    const ref=item.reference;return ref===null||(exactKeys(ref,["type","id","revision"])&&["source","material"].includes(ref.type)&&typeof ref.id==="string"&&ref.id.length>0&&ref.id.length<=128&&Number.isInteger(ref.revision)&&ref.revision>0);
  });
}
function renderNotebookItems(scope=identityScope()) {
  const box=$("#notebookItems"); box.replaceChildren();
  if(!state.notebookItems.length){box.textContent="Your notebook is empty. Add one of your notes, messages, attempts, or an authorized reference.";return;}
  for(const item of state.notebookItems){const row=document.createElement("article");row.className="source-item";const label=document.createElement("label");label.className="check-line";const choose=document.createElement("input");choose.type="checkbox";choose.className="export-notebook-item";choose.value=item.id;const copy=document.createElement("span");copy.textContent=`${item.kind}: ${item.text||"(no personal text)"}${item.reference?` · ${item.reference.type} reference${item.available?" available":" unavailable or revoked"}`:""}`;label.append(choose,copy);row.append(label);const remove=document.createElement("button");remove.type="button";remove.className="button secondary";remove.textContent="Remove from notebook";remove.onclick=async()=>{if(tabOnlyAccess){toast("Changing your notebook requires saved access for recovery.");return;}remove.disabled=true;try{await API.call("deleteNotebookItem",null,item.id,{scope});assertIdentity(scope);await loadNotebook(scope);}catch(error){if(scope.epoch===state.identityEpoch&&error.name!=="AbortError"){remove.disabled=false;toast("Could not remove this notebook item.");}}};row.append(remove);box.append(row);}
}
let notebookLoadGeneration=0;
async function populateNotebookChoices(scope=identityScope(),generation=null) {
  const select=$("#notebookSelection"); select.replaceChildren(); const prompt=document.createElement("option");prompt.value="";prompt.textContent="Choose your note, message, attempt, bookmark, or reference";select.append(prompt);
  const add=(label,selection)=>{const option=document.createElement("option");option.value=JSON.stringify(selection);option.textContent=label;select.append(option);};
  for(const item of state.history)if(item.id)add(`Your attempt · ${String(item.goal||"Attempt").slice(0,100)}`,{kind:"attempt",conversationId:state.practiceConversationId,attemptId:item.id});
  try{const detail=await API.call("conversation",null,state.conversationId,{scope});assertIdentity(scope);if(generation!==null&&generation!==notebookLoadGeneration)return;for(const message of normalizeList(detail.messages))if(message.role==="user"&&message.id)add(`Your message · ${String(message.text||"").slice(0,100)}`,{kind:"message",conversationId:state.conversationId,messageId:message.id});}catch(error){if(error.name==="AbortError")throw error;}
  try{const data=await API.call("bookmarks",null,{scope});assertIdentity(scope);if(generation!==null&&generation!==notebookLoadGeneration)return;for(const bookmark of normalizeList(data.bookmarks))add(`Saved source reference · ${bookmark.source?.title||bookmark.sourceId}${bookmark.available?"":" · unavailable"}`,{kind:"bookmark",bookmarkId:bookmark.id});}catch(error){if(error.name==="AbortError")throw error;}
  for(const source of normalizeList(state.context?.sources||state.context))if(source?.id&&source.status==="active"&&source.audienceVisible===true&&Number.isInteger(source.revision)&&source.revision>0)add(`Current source reference · ${source.title||source.id}`,{kind:"source",id:source.id,revision:source.revision});
  if(state.activity?.materialId&&Number.isInteger(state.activity.version)&&state.activity.version>0)add(`Presented activity reference · ${state.activity.title||"Activity"}`,{kind:"material",id:state.activity.materialId,revision:state.activity.version});
}
async function loadNotebook(scope=identityScope()) {
  if(scope.role!=="viewer")return;
  const generation=++notebookLoadGeneration;
  try{const data=await API.call("notebook",null,{scope});assertIdentity(scope);if(generation!==notebookLoadGeneration)return;state.notebookItems=normalizeList(data.items);renderNotebookItems(scope);await populateNotebookChoices(scope,generation);assertIdentity(scope);}
  catch(error){if(scope.epoch!==state.identityEpoch||error.name==="AbortError"||generation!==notebookLoadGeneration)return;$("#notebookItems").textContent="Notebook unavailable. Refresh the audience view to retry.";}
}
$("#saveNotebookItem").addEventListener("click",async()=>{
  const scope=identityScope(),raw=$("#notebookSelection").value,note=$("#notebookText").value.trim(),button=$("#saveNotebookItem");if(scope.role!=="viewer")return;
  if(tabOnlyAccess){$("#notebookPreview").textContent="Changing your notebook requires saved access for recovery.";return;}
  let selection;try{selection=raw?JSON.parse(raw):{kind:"note",text:note};}catch{return;}
  if(selection.kind==="note"&&!selection.text){$("#notebookPreview").textContent="Write your own note or choose an existing item.";return;}
  const body={selection,...(selection.kind!=="note"&&note?{note}:{})};setBusy(button,true,"Saving…");
  try{await API.call("addNotebookItem",body,{scope});assertIdentity(scope);$("#notebookText").value="";$("#notebookSelection").value="";$("#notebookPreview").textContent="Saved to your private notebook.";await loadNotebook(scope);}
  catch(error){if(scope.epoch===state.identityEpoch&&error.name!=="AbortError")$("#notebookPreview").textContent=error.status===404?"That owned item is no longer available.":error.status===409?"That reference changed or is no longer available.":"Could not save this notebook item.";}
  finally{if(scope.epoch===state.identityEpoch)setBusy(button,false);}
});
let exportNotebookCandidate=null, importNotebookCandidate=null;
$("#exportNotebook").addEventListener("click",()=>{
  const scope=identityScope(),ids=$$(".export-notebook-item:checked").map(x=>x.value),box=$("#notebookPreview");box.replaceChildren();exportNotebookCandidate=null;
  if(tabOnlyAccess){box.textContent="Notebook download requires saved access to protect private data.";return;}
  if(scope.role!=="viewer"||!ids.length||ids.length>100){box.textContent="Select between 1 and 100 of your notebook items.";return;}
  exportNotebookCandidate={scope,ids};const p=document.createElement("p");p.textContent=`Preview: ${ids.length} selected item(s). Only your text and reference identifiers will transfer; no source excerpt, generated response, feedback, consent, or credentials are included.`;box.append(p);
  const confirm=document.createElement("button");confirm.type="button";confirm.className="button secondary";confirm.textContent="Confirm and download";confirm.onclick=async()=>{try{assertSavedIdentity(scope);if(exportNotebookCandidate?.scope!==scope)throw new Error("identity");confirm.disabled=true;const result=await API.call("exportNotebook",{itemIds:ids},{scope});assertSavedIdentity(scope);const notebook=result.notebook;if(!validNotebookArtifact(notebook))throw new Error("invalid_export");const blob=new Blob([JSON.stringify(notebook,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download="entrelineas-notebook-v1.json";link.click();setTimeout(()=>URL.revokeObjectURL(url),0);box.textContent=`Downloaded ${notebook.items.length} selected item(s). References remain subject to destination authorization.`;exportNotebookCandidate=null;}catch(error){if(scope.epoch===state.identityEpoch&&error.name!=="AbortError")box.textContent="Export failed. Your notebook was not assumed downloaded.";}finally{if(scope.epoch===state.identityEpoch)confirm.disabled=false;}};box.append(confirm);
});
let notebookImportGeneration=0, notebookImportInFlight=false;
// Preserve an uncertain import until an authenticated receipt can resolve it.
const notebookImportJournalKey = scope => `entrelineas.notebook-import.v1:${scope.sessionId}:${scope.actorBinding}`;
$("#recoverNotebookImport").addEventListener("click",async()=>{
  const scope=identityScope(),box=$("#notebookPreview"),button=$("#recoverNotebookImport");
  if(tabOnlyAccess || scope.role!=="viewer" || !scope.sessionId || !scope.actorBinding || !navigator.locks?.request){box.textContent="Safe import recovery requires saved access and a supported browser.";return;}
  const key=notebookImportJournalKey(scope);button.disabled=true;
  try {
    const outcome=await navigator.locks.request(key,async()=>{
      assertSavedIdentity(scope);const raw=localStorage.getItem(key);if(raw===null)return "none";
      let marker;try{marker=JSON.parse(raw);}catch{return "legacy";}
      if(marker?.version!==2 || typeof marker.requestId!=="string" || !/^[A-Za-z0-9._:-]{1,128}$/.test(marker.requestId))return "legacy";
      const response=await API.call("notebookImportReceipt",null,marker.requestId,{scope});assertSavedIdentity(scope);
      if(response.receipt?.state!=="committed" || !Array.isArray(response.receipt.itemIds))return "unknown";
      if(localStorage.getItem(key)!==raw)throw Error("Import marker changed");
      localStorage.removeItem(key);return "committed";
    });
    assertSavedIdentity(scope);
    if(outcome==="committed"){await loadNotebook(scope);assertSavedIdentity(scope);box.textContent="The original import was confirmed. Your notebook now shows current reference availability.";}
    else box.textContent=outcome==="none"?"No pending import is recorded for this session.":outcome==="legacy"?"An earlier import has no recoverable request ID. It remains preserved; do not submit it again.":"The original import is still unconfirmed. Its request is preserved; do not submit another import.";
  } catch(error){if(scope.epoch===state.identityEpoch && error.name!=="AbortError")box.textContent="The original import is still unconfirmed. Its request is preserved; try checking again.";}
  finally{button.disabled=false;}
});
$("#notebookImportFile").addEventListener("change",async event=>{
  const generation=++notebookImportGeneration,scope=identityScope(),file=event.target.files?.[0],box=$("#notebookPreview");importNotebookCandidate=null;box.replaceChildren();if(!file)return;
  if(tabOnlyAccess || scope.role!=="viewer" || !scope.sessionId || !scope.actorBinding || !navigator.locks || !crypto.randomUUID){box.textContent="Notebook import requires saved access and a supported browser.";event.target.value="";return;}
  try { assertSavedIdentity(scope); if(localStorage.getItem(notebookImportJournalKey(scope))!==null){box.textContent="A previous import is unconfirmed. It is preserved; do not submit another import until its outcome can be recovered.";event.target.value="";return;} } catch { box.textContent="Safe import recovery is unavailable. Your file was not imported."; event.target.value=""; return; }
  if(file.size>512*1024){box.textContent="Import rejected: file exceeds 512 KiB.";event.target.value="";return;}
  try{const raw=await file.text();if(generation!==notebookImportGeneration)return;assertSavedIdentity(scope);const data=JSON.parse(raw);if(!validNotebookArtifact(data))throw new Error("schema");importNotebookCandidate={scope,data,generation};const p=document.createElement("p");p.textContent=`Preview: ${data.items.length} item(s). Text remains viewer-authored; each reference is inert and will be resolved under the current destination session when confirmed. No identity, credentials, permissions, or protected source content is imported.`;box.append(p);for(const [index,item] of data.items.entries()){const row=document.createElement("p");row.textContent=`${index+1}. ${item.kind}: ${item.text||"(no personal text)"}${item.reference?` · ${item.reference.type} reference rev ${item.reference.revision} (availability checked on import)`:""}`;box.append(row);}const button=document.createElement("button");button.type="button";button.className="button secondary";button.textContent="Confirm import";button.onclick=async()=>{if(notebookImportInFlight||generation!==notebookImportGeneration||importNotebookCandidate?.generation!==generation)return;notebookImportInFlight=true;button.disabled=true;try{assertSavedIdentity(scope);if(importNotebookCandidate?.scope!==scope)throw new Error("identity");setBusy(button,true,"Importing…");const key=notebookImportJournalKey(scope);const result=await navigator.locks.request(key,async()=>{assertSavedIdentity(scope);if(localStorage.getItem(key)!==null)throw new Error("previous_import_unconfirmed");const requestId=crypto.randomUUID(),marker=JSON.stringify({version:2,requestId});localStorage.setItem(key,marker);try{const response=await API.call("importNotebook",{notebook:data,clientRequestId:requestId},{scope});assertSavedIdentity(scope);if(response.receipt?.state!=="committed" || !Array.isArray(response.receipt.itemIds))throw new Error("unconfirmed_import_response");if(localStorage.getItem(key)===marker)localStorage.removeItem(key);return response;}catch(error){if([413,422].includes(error.status)){try{assertSavedIdentity(scope);if(localStorage.getItem(key)===marker)localStorage.removeItem(key);}catch{}}throw error;}});assertSavedIdentity(scope);if(generation!==notebookImportGeneration)return;await loadNotebook(scope);assertSavedIdentity(scope);if(generation!==notebookImportGeneration)return;box.textContent=`Imported ${result.receipt.itemIds.length} item(s). Current reference availability appears in your notebook.`;importNotebookCandidate=null;}catch(error){if(scope.epoch===state.identityEpoch&&error.name!=="AbortError"&&generation===notebookImportGeneration)box.textContent=error.status===413?"Import rejected: notebook is too large.":error.status===422?"Import rejected: unsupported or invalid schema.":"Import outcome could not be confirmed. Its marker is preserved; do not submit another import until it can be recovered.";}finally{notebookImportInFlight=false;if(generation===notebookImportGeneration){button.disabled=false;if(scope.epoch===state.identityEpoch)setBusy(button,false);}}};box.append(button);
  }catch(error){if(generation===notebookImportGeneration&&error.name!=="AbortError")box.textContent="Import rejected: invalid schema, item, reference, or oversized text.";}finally{if(generation===notebookImportGeneration)event.target.value="";}
});
function appendSourceLinks(box, ids, snapshot, scope) {
  const refs = document.createElement("div"); refs.className = "catchup-citations";
  const rows = [...(snapshot?.result?.sources || []), ...(snapshot?.result?.changed || []), ...(snapshot?.result?.earlier ? [snapshot.result.earlier] : [])];
  for (const id of [...new Set(ids || [])]) {
    const source = rows.find(item => item.id === id); if (!source) continue;
    const button = document.createElement("button"); button.type = "button"; button.className = "text-button";
    button.textContent = `Source: ${source.title || "Received moment"}${source.at ? ` · ${source.at}` : ""}`;
    button.onclick = async () => { try { assertIdentity(scope); await refreshSources(scope); assertIdentity(scope); const active = normalizeList(state.context?.sources || state.context).find(item => item.id === id && item.status === "active" && item.audienceVisible === true && item.revision === source.revision); if (!active) { toast("This source changed or is no longer available. Refresh catch-up before returning."); return; } $("#questionSource").value=id; $("#questionMoment").value=active.at || source.at || ""; navTo("audience"); $("#question").focus(); } catch (error) { if (scope.epoch===state.identityEpoch && error.name!=="AbortError") toast("Could not refresh source access."); } };
    refs.append(button);
  }
  if (refs.childElementCount) box.append(refs);
}
function renderRecap(scope = identityScope()) {
  const box = $("#catchupRecap"); box.replaceChildren();
  const recap = state.catchupRecap;
  if (!recap) return;
  for (const [key, heading] of [["whatHappened","What happened"],["whatChanged","Source revisions and updates"],["openMatters","Possible follow-up (resolution unknown)"]]) {
    const section=document.createElement("section"), title=document.createElement("h3"); title.textContent=heading; section.append(title);
    let shown=0; for (const claim of recap[key] || []) { const ids=Array.isArray(claim.sourceIds)?claim.sourceIds:[],shares=Array.isArray(claim.shareIds)?claim.shareIds:[],r=state.catchupSnapshot?.result||{},rows=[...(r.sources||[]),...(r.changed||[]),...(r.earlier?[r.earlier]:[])],knownShares=(r.openMatters||[]).map(item=>item.shareId);const validSources=ids.length>0&&ids.every(id=>rows.some(row=>row.id===id));const validShares=key==="openMatters"&&shares.length>0&&shares.every(id=>knownShares.includes(id));if(!claim.text||(!validSources&&!validShares))continue;const p=document.createElement("p");p.textContent=claim.text;section.append(p);if(validSources)appendSourceLinks(section,ids,state.catchupSnapshot,scope);if(validShares){const linked=document.createElement("p");linked.className="muted";linked.textContent="Linked to your previously shared topic; whether it is resolved is unknown.";section.append(linked);}shown++; }
    if (!shown) { const p=document.createElement("p"); p.className="muted"; p.textContent=key==="openMatters" ? "No source-linked open matter was identified; this does not prove that none exists." : key==="whatChanged" ? "No supported source revisions are present in this interval." : "No source-linked detail in this category."; section.append(p); }
    box.append(section);
  }
  if (recap.limitations?.length) { const section=document.createElement("section"), title=document.createElement("h3"); title.textContent="Coverage and limitations"; section.append(title); for (const text of recap.limitations) { const p=document.createElement("p"); p.textContent=text; section.append(p); } box.append(section); }
}
function renderCatchupSearch(scope = identityScope()) {
  const box = $("#catchupSearchResults"); box.replaceChildren();
  if (scope.role !== "viewer" || !state.catchupSnapshot?.result) return;
  try { assertIdentity(scope); } catch { return; }
  const query = $("#catchupSearch").value.trim().toLocaleLowerCase();
  if (!query) return;
  const result = state.catchupSnapshot.result;
  const matches = (result.sources || []).filter(item => [item.title, item.excerpt, item.at].some(value => typeof value === "string" && value.toLocaleLowerCase().includes(query)));
  const note = document.createElement("p");
  note.textContent = `${matches.length} matching received record(s).${result.hasMore ? " More records may exist outside this interval." : ""}`;
  box.append(note);
  const list = document.createElement("ul");
  for (const item of matches) {
    const row = document.createElement("li");
    const text = document.createElement("p");
    text.textContent = `${item.title || "Received moment"}${item.at ? ` · ${item.at}` : ""}${item.excerpt ? ` — ${item.excerpt}` : ""}`;
    row.append(text); appendSourceLinks(row, [item.id], state.catchupSnapshot, scope); list.append(row);
  }
  box.append(list);
}
$("#catchupSearch").addEventListener("input", () => renderCatchupSearch());
let catchupRecapGeneration=0, catchupRecapInFlight=false;
function renderCatchup(scope = identityScope()) {
  if (scope.role !== "viewer") return;
  try { assertIdentity(scope); } catch { return; }
  const box=$("#catchupTimeline"); box.replaceChildren(); const snapshot=state.catchupSnapshot;
  if (!snapshot?.result) { $("#catchupSearchResults").replaceChildren(); $("#catchupRecap").replaceChildren(); $("#catchupAckTarget").replaceChildren(); box.textContent="Catch-up is unavailable. Refresh to try again."; $("#acknowledgeCatchup").disabled=true;$("#generateRecap").disabled=true; return; }
  const r=snapshot.result;
  const anchor=document.createElement("p"); anchor.className="muted"; anchor.textContent=snapshot.anchor ? `Earlier consulted point: ${snapshot.anchor.sourceId} · revision ${snapshot.anchor.revision}.` : r.anchorMissing ? "No earlier consulted point is available. This is the received context interval, not a complete stream record." : "No earlier consulted point is available."; box.append(anchor);
  const earlier=document.createElement("section"), eh=document.createElement("h3"); eh.textContent="Earlier context"; earlier.append(eh);
  const ep=document.createElement("p"); ep.textContent=r.earlier ? `${r.earlier.title || "Received moment"}${r.earlier.at ? ` · ${r.earlier.at}` : ""}. This is the prior consulted boundary.` : "No earlier source moment is available."; earlier.append(ep); if(r.earlier?.id)appendSourceLinks(earlier,[r.earlier.id],snapshot,scope); box.append(earlier);
  const changed=document.createElement("section"), ch=document.createElement("h3"); ch.textContent="What changed in received sources"; changed.append(ch);
  for (const item of r.changed || []) { const p=document.createElement("p"); p.textContent=`${item.change === "unavailable" ? "Source unavailable" : "Source revision changed"}: ${item.title || "Received moment"}${item.at ? ` · ${item.at}` : ""}${item.excerpt ? ` — ${item.excerpt}` : ""}`; changed.append(p);const links=document.createElement("div");appendSourceLinks(links,[item.id],snapshot,scope);if(links.childElementCount)changed.append(links); }
  if (!(r.changed||[]).length) { const p=document.createElement("p"); p.textContent="No source revision change was reported in this interval. This does not establish that nothing changed in the stream."; changed.append(p); }
  box.append(changed);
  const matters=document.createElement("section"), mh=document.createElement("h3"); mh.textContent="Possible viewer-shared follow-up"; matters.append(mh);
  for (const item of r.openMatters || []) { const p=document.createElement("p"); p.textContent=`Shared topic (resolution unknown): ${item.summary || "Details unavailable"}`; matters.append(p); }
  if (r.openMattersStatus === "not_identified" || !(r.openMatters||[]).length) { const p=document.createElement("p"); p.textContent="No supported open matter was identified. Whether any matter is actually unresolved is unknown."; matters.append(p); }
  box.append(matters);
  const coverage=document.createElement("section"), gh=document.createElement("h3"); gh.textContent="Coverage gaps"; coverage.append(gh);
  const gp=document.createElement("p"); gp.textContent=`Capture state: ${r.capture?.state || "unknown"}; reported gaps: ${Number.isInteger(r.capture?.gaps) ? r.capture.gaps : "unknown"}. ${r.incomplete ? "Coverage is incomplete or uncertain." : "No incomplete flag was reported; this is not proof of complete capture."}`; coverage.append(gp); box.append(coverage);
  const received=document.createElement("details"), summary=document.createElement("summary"); summary.textContent=`Received source records (${(r.sources||[]).length}${r.hasMore?"+":""})`; received.append(summary);
  for (const item of r.sources||[]) { const p=document.createElement("p"); p.textContent=`${item.title||"Source"}${item.at?` · ${item.at}`:""}${item.excerpt?` — ${item.excerpt}`:""}`; received.append(p); }
  box.append(received);
  const target=$("#catchupAckTarget"), previous=target.value; target.replaceChildren(); const prompt=document.createElement("option"); prompt.value=""; prompt.textContent="Choose a received moment"; target.append(prompt);
  for (const item of r.sources||[]) { const option=document.createElement("option"); option.value=item.id; option.textContent=`${item.title||"Moment"}${item.at?` · ${item.at}`:""} · rev ${item.revision}`; option.dataset.revision=String(item.revision); target.append(option); }
  target.value=[...target.options].some(o=>o.value===previous)?previous:""; $("#acknowledgeCatchup").disabled=!r.sources?.length;$("#generateRecap").disabled=false;
  $("#catchupStatus").textContent=snapshot.anchor ? "Review the interval, then choose a moment to advance your private point." : "Review the interval, then choose a moment to set your private point.";
  renderRecap(scope);
  renderCatchupSearch(scope);
}
let catchupReadGeneration=0;
async function loadCatchup(scope=identityScope()) {
  if(scope.role!=="viewer") return; const generation=++catchupReadGeneration;
  ++catchupRecapGeneration; catchupRecapInFlight=false; setBusy($("#generateRecap"),false);
  state.catchupSnapshot=null; state.catchupRecap=null; renderCatchup(scope);
  try { const data=await API.call("catchup",null,{scope}); assertIdentity(scope); if(generation!==catchupReadGeneration)return; state.catchupSnapshot=data; state.catchupRecap=null; state.pendingCatchupRecapAction=null; renderCatchup(scope); }
  catch(error) { if(scope.epoch!==state.identityEpoch || error.name==="AbortError" || generation!==catchupReadGeneration)return; state.catchupSnapshot=null; renderCatchup(scope); }
}
function renderActivity(scope=identityScope()) {
  const box=$("#activityContent"), activity=state.activity?.activity;
  for(const id of ["tryActivity","askAboutActivity","feedbackHelped","feedbackQuestion"]) $("#"+id).disabled=!activity;
  if(scope.role!=="viewer" || !activity) { box.textContent="No current eligible creator-approved activity is presented."; $("#feedbackVersion").textContent="No intervention is available for a response. Private conversation stays private."; return; }
  box.replaceChildren();
  const title=document.createElement("strong"); title.textContent=`${state.activity.title||"Learning activity"} · approved and presented version ${state.activity.version}`; box.append(title);
  const section=(heading,body)=>{const wrap=document.createElement("section"),h=document.createElement("h3"),p=document.createElement("p");h.textContent=heading;p.textContent=body;wrap.append(h,p);box.append(wrap);};
  section("Explanation",activity.explanation); section("Example",activity.example);
  const steps=document.createElement("section"),sh=document.createElement("h3"),ol=document.createElement("ol");sh.textContent="Steps";steps.append(sh);for(const step of activity.steps||[]){const li=document.createElement("li");li.textContent=step;ol.append(li);}steps.append(ol);box.append(steps);
  const sourceRows=normalizeList(state.context?.sources||state.context),sourceIds=state.activity.sourceIds||[];const lineage=document.createElement("p");lineage.className="muted";const sources=sourceIds.map(id=>sourceRows.find(x=>x.id===id&&x.status==="active"&&x.audienceVisible===true));lineage.textContent=`Version ${state.activity.version}; ${sources.filter(Boolean).length} of ${sourceIds.length} referenced source(s) currently visible. Access is checked again before use.`;box.append(lineage);
  for(const source of sources.filter(Boolean)){const link=document.createElement("button");link.type="button";link.className="text-button";link.textContent=`Source: ${source.title||"Received moment"}${source.at?` · ${source.at}`:""}`;link.onclick=()=>{const current=normalizeList(state.context?.sources||state.context).find(x=>x.id===source.id&&x.status==="active"&&x.audienceVisible===true);if(!current){toast("This source is no longer available.");return;}$("#questionSource").value=current.id;$("#questionMoment").value=current.at||"";navTo("audience");$("#question").focus();};box.append(link);}
  if(state.activity.intervention?.contributionIds?.length){const link=document.createElement("p");link.className="muted";link.textContent="This intervention responds to one or more voluntarily shared viewer difficulties. The creator does not receive your private text through this link.";box.append(link);}
  $("#tryActivity").disabled=!activity.optionalAttempt;
  $("#askAboutActivity").disabled=false;
  $("#feedbackVersion").textContent=`Optional response for ${state.activity.title||"this intervention"}, version ${state.activity.version}. The creator sees only thresholded counts; your private conversation and continuation stay private.`;
}
let activityLoadGeneration=0;
async function loadActivity(scope=identityScope()) {
  if(scope.role!=="viewer")return;
  const generation=++activityLoadGeneration;
  try { const result=await API.call("activity",null,{scope}); assertIdentity(scope); if(generation!==activityLoadGeneration)return; state.activity=result.activity||null; renderActivity(scope); await populateNotebookChoices(scope,notebookLoadGeneration); }
  catch(error) { if(scope.epoch!==state.identityEpoch||error.name==="AbortError"||generation!==activityLoadGeneration)return; state.activity=null; renderActivity(scope); }
}
async function submitInterventionResponse(response) {
  const scope=identityScope(), active=state.activity; if(scope.role!=="viewer"||!active)return;
  for(const button of [$("#feedbackHelped"),$("#feedbackQuestion")])button.disabled=true;
  try { await API.call("interventionFeedback",{materialId:active.materialId,version:active.version,response},{scope}); assertIdentity(scope); if(state.activity?.materialId!==active.materialId||Number(state.activity?.version)!==Number(active.version)){toast("Your response was recorded for the presented version. The current activity changed; refreshing it now.");await loadActivity(scope);return;} toast("Your voluntary response was recorded for this intervention version."); }
  catch(error) { if(scope.epoch===state.identityEpoch&&error.name!=="AbortError"){toast(error.status===409?"This intervention is no longer current. Refresh before responding.":"Your response could not be recorded.");if(error.status===409)await loadActivity(scope);} }
  finally { if(scope.epoch===state.identityEpoch)renderActivity(scope); }
}
$("#feedbackHelped").addEventListener("click",()=>submitInterventionResponse("helped"));
$("#feedbackQuestion").addEventListener("click",()=>submitInterventionResponse("still_question"));
$("#askAboutActivity").addEventListener("click",()=>{const active=state.activity;if(!active)return;state.nextCorrection=null;$("#question").value=`I have a question about ${active.title||"the presented activity"} (version ${active.version}).`;const sourceId=(active.sourceIds||[]).find(id=>normalizeList(state.context?.sources||state.context).some(x=>x.id===id&&x.status==="active"&&x.audienceVisible===true));if(sourceId){const source=normalizeList(state.context?.sources||state.context).find(x=>x.id===sourceId);$("#questionSource").value=sourceId;$("#questionMoment").value=source?.at||"";}navTo("audience");$("#question").focus();});
$("#tryActivity").addEventListener("click",()=>{const active=state.activity;if(!active?.activity?.optionalAttempt)return;if(state.pendingPracticeAction){navTo("practice");showError($("#practiceError"),"An earlier practice request is unconfirmed. Restore its original inputs and retry it before starting another activity.");return;}const scope=identityScope();try{assertIdentity(scope);state.pendingPracticeActivity={materialId:active.materialId,version:active.version};state.retryFromAttemptId=null;renderRetrySelection();if(!$("#practiceGoal").value.trim())$("#practiceGoal").value=active.activity.optionalAttempt.goal;const prompt=$("#practiceActivityPrompt");prompt.textContent=`Creator's optional prompt for ${active.title||"this activity"} · version ${active.version}: ${active.activity.optionalAttempt.prompt} Write your own response below; the prompt is not submitted as your answer.`;prompt.hidden=false;const sourceId=(active.sourceIds||[]).find(id=>normalizeList(state.context?.sources||state.context).some(x=>x.id===id&&x.status==="active"&&x.audienceVisible===true));if(sourceId)$("#questionSource").value=sourceId;persistDraft(scope);navTo("practice");$("#practiceAttempt").focus();}catch{state.pendingPracticeActivity=null;}});
async function loadInterventionAggregate(materialId,version,container,scope=identityScope()) {
  const button=document.createElement("button");button.type="button";button.className="button secondary";button.textContent="Load voluntary response counts";container.append(button);
  const status=document.createElement("p");status.className="muted";status.setAttribute("role","status");container.append(status);
  button.onclick=async()=>{setBusy(button,true,"Loading counts…");try{const data=await API.call("interventionAggregate",null,materialId,version,{scope});assertIdentity(scope);if(data.materialId!==materialId||Number(data.version)!==Number(version)||data.threshold!==5)throw new Error("aggregate_mismatch");const c=data.counts;if(c===null){status.textContent="Counts suppressed: neither response category met its independent threshold of five. This does not mean zero responses.";return;}if(!c||![null,"5+"].includes(c.helped)||![null,"5+"].includes(c.still_question))throw new Error("invalid_aggregate");const helped=c.helped===null?"Suppressed (0–4)":"5+";const question=c.still_question===null?"Suppressed (0–4)":"5+";status.textContent=`Viewer reports for version ${version}: helped ${helped}; still have a question ${question}. These reports do not measure learning.`;}catch(error){if(scope.epoch===state.identityEpoch&&error.name!=="AbortError")status.textContent=error.status===409?"This intervention is stale or its shared difficulty is no longer eligible.":"Counts unavailable. No viewer identity or private text is shown.";}finally{if(scope.epoch===state.identityEpoch)setBusy(button,false);}};
}
$("#refreshCatchup").addEventListener("click",()=>loadCatchup());
$("#acknowledgeCatchup").addEventListener("click", async () => {
  const scope=identityScope(), snapshot=state.catchupSnapshot, option=$("#catchupAckTarget").selectedOptions[0]; if(!snapshot?.snapshotId || !option?.value)return;
  const button=$("#acknowledgeCatchup"); setBusy(button,true,"Saving consulted point…");
  try { await API.call("acknowledgeCatchup",{snapshotId:snapshot.snapshotId,sourceId:option.value,revision:Number(option.dataset.revision)},{scope}); assertIdentity(scope); if(state.catchupSnapshot?.snapshotId!==snapshot.snapshotId){await loadCatchup(scope);return;} $("#catchupStatus").textContent="Your private consulted point was advanced."; await loadCatchup(scope); }
  catch(error) { if(scope.epoch===state.identityEpoch && error.name!=="AbortError") { $("#catchupStatus").textContent=error.status===409?"This interval changed. Refresh and review the current sources before advancing.":"Could not advance the consulted point. It has not been assumed saved."; if(error.status===409) await loadCatchup(scope); } }
  finally { if(scope.epoch===state.identityEpoch)setBusy(button,false); }
});
$("#generateRecap").addEventListener("click", async event=>{
  if(tabOnlyAccess){$("#catchupStatus").textContent="Generating a recap requires saved access. Check the existing request before retrying an unconfirmed result.";return;}
  const scope=identityScope(), snapshot=state.catchupSnapshot, button=event.currentTarget; if(!snapshot?.snapshotId||catchupRecapInFlight)return;
  const generation=++catchupRecapGeneration;catchupRecapInFlight=true;
  if(state.pendingCatchupRecapAction?.snapshotId!==snapshot.snapshotId)state.pendingCatchupRecapAction={snapshotId:snapshot.snapshotId,clientRequestId:newRequestId()};
  setBusy(button,true,"Generating recap…"); $("#catchupStatus").textContent="Generating a grounded recap for this received interval…";
  try { const action={...state.pendingCatchupRecapAction};const data=await API.call("catchupRecap",action,{scope}); assertIdentity(scope); if(generation!==catchupRecapGeneration||data.snapshotId!==snapshot.snapshotId||state.catchupSnapshot?.snapshotId!==snapshot.snapshotId)return; state.pendingCatchupRecapAction=null; state.catchupRecap=data.recap; renderRecap(scope); $("#catchupStatus").textContent="Recap generated for this snapshot. It has not advanced your consulted point."; }
  catch(error) { if(generation===catchupRecapGeneration&&scope.epoch===state.identityEpoch && error.name!=="AbortError") { $("#catchupStatus").textContent=error.status===409?"This interval changed. Refresh before generating another recap.":error.code==="busy"?"This request was not started. Generate again to make a deliberate retry.":error.code==="session_call_limit"?error.message:"Recap unavailable. Generate again to retry this same request safely."; if(error.status===409||error.code==="busy"||error.code==="session_call_limit"){state.pendingCatchupRecapAction=null;if(error.status===409)await loadCatchup(scope);} } }
  finally { if(generation===catchupRecapGeneration){catchupRecapInFlight=false;if(scope.epoch===state.identityEpoch)setBusy(button,false);} }
});
$("#continuePrivately").addEventListener("click", () => { const active=state.activity;if(state.role!=="viewer")return;if(state.pendingPracticeAction){navTo("practice");showError($("#practiceError"),"An earlier practice request is unconfirmed. Restore its original inputs and retry it before starting another follow-up.");return;}state.pendingPracticeActivity=null;state.retryFromAttemptId=null;renderRetrySelection();if(active){const prompt=$("#practiceActivityPrompt");prompt.textContent=`Private follow-up on ${active.title||"the presented intervention"} · version ${active.version}. Your question and any response remain private unless you separately choose to share.`;prompt.hidden=false;if(!$("#practiceGoal").value.trim())$("#practiceGoal").value=`Follow up on ${active.title||"the intervention"} (version ${active.version})`;persistDraft();}navTo("practice");$("#practiceAttempt").focus(); });
function renderComparisonChoices() {
  for (const selector of [$("#compareFirst"), $("#compareSecond")]) {
    const previous = selector.value;
    selector.replaceChildren();
    const prompt = document.createElement("option");
    prompt.value = ""; prompt.textContent = "Select an attempt"; selector.append(prompt);
    for (const item of state.history) {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = `${item.goal || "Attempt"} · ${new Date(item.created_at).toLocaleString()}`;
      selector.append(option);
    }
    selector.value = previous;
  }
}
$("#compareAttempts").addEventListener("click", async () => {
  const scope = identityScope(), box = $("#comparison");
  const ids = [$("#compareFirst").value, $("#compareSecond").value];
  if (!ids[0] || !ids[1] || ids[0] === ids[1]) { box.textContent = "Select two different attempts."; return; }
  box.textContent = "Loading comparison…";
  try {
    const data = await API.call("compareAttempts", {conversationId:state.practiceConversationId, attemptIds:ids}, {scope});
    assertIdentity(scope); box.replaceChildren(); box.className = "comparison-grid";
    for (const attempt of data.attempts) {
      const article = document.createElement("article"); article.className = "source-item";
      const title = document.createElement("h3"); title.textContent = attempt.goal || "Attempt"; article.append(title);
      const fields = [["Your attempt", attempt.text || "No text"], ["Feedback", attempt.answer?.text || "No saved feedback"], ["Lineage", attempt.previousAttemptId ? `Retry of ${attempt.previousAttemptId}` : "Original attempt"]];
      for (const [label, value] of fields) {
        const paragraph = document.createElement("p"), strong = document.createElement("strong");
        strong.textContent = `${label}: `; paragraph.append(strong, document.createTextNode(value)); article.append(paragraph);
      }
      for (const citation of attempt.answer?.citations || []) {
        const paragraph = document.createElement("p");
        paragraph.textContent = citation.stale ? "Source unavailable or changed" : `Source: ${citation.title || citation.sourceId}`;
        article.append(paragraph);
      }
      box.append(article);
    }
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") box.textContent = "Comparison unavailable. Refresh your attempts and try again.";
  }
});
function renderVersionComparison(versions, currentVersion, approvedVersion) {
  const details = document.createElement("details"), summary = document.createElement("summary");
  summary.textContent = "Compare saved versions"; details.append(summary);
  const grid = document.createElement("div"); grid.className = "comparison-grid";
  for (const version of versions.slice(-2)) {
    const column = document.createElement("article"), title = document.createElement("h3");
    const labels = [version.number === currentVersion ? "current" : "", version.number === approvedVersion ? "approved" : ""].filter(Boolean);
    title.textContent = `Version ${version.number}${labels.length ? ` · ${labels.join(" · ")}` : ""}`;
    column.append(title);
    const content = document.createElement("p");
    content.textContent = version.eligible && !version.redacted
      ? `${version.title || "Untitled"} — ${version.body || ""}`
      : "Content unavailable because source or consent changed.";
    column.append(content);
    if (version.eligible && !version.redacted && version.blocks?.length) {
      const blocks = document.createElement("div");
      blocks.className = "version-blocks";
      blocks.innerHTML = renderBlockPreview(version.blocks);
      column.append(blocks);
    }
    if (version.eligible && !version.redacted && version.changedFields?.length) {
      const labels = {title: "title", body: "body", blocks: "content blocks", shareRevisions: "contribution permissions", sourceRevisions: "source permissions"};
      const changedFields = version.changedFields.map(field => labels[field]).filter(Boolean);
      if (changedFields.length) {
        const changed = document.createElement("p");
        changed.textContent = `Changed: ${changedFields.join(", ")}`;
        column.append(changed);
      }
    }
    grid.append(column);
  }
  details.append(grid); return details;
}
async function loadWorkbench(scope = identityScope()) {
  const box = $("#workbenchChanges");
  try {
    const data = await API.call("workbench", null, {scope}); assertIdentity(scope);
    state.insights = normalizeList(data.insights); renderContributions(); box.replaceChildren();
    const heading = document.createElement("h2"); heading.textContent = "Review and changes"; box.append(heading);
    const summary = document.createElement("p");
    summary.textContent = data.changes.length ? `${data.changes.length} source or consent impact(s) require review. Unavailable contribution text is not shown.` : "No changed source or consent impacts reported for current versions.";
    box.append(summary);
    for (const item of data.materials) {
      const article = document.createElement("article"); article.className = "source-item";
      const current = item.versions?.find(version => Number(version.number) === Number(item.currentVersion));
      const safeTitle = current?.eligible && !current?.redacted && typeof current.title === "string" ? current.title : "";
      const label = document.createElement("strong");
      label.textContent = `${safeTitle ? `${safeTitle} · ` : ""}${item.format || "Material"} · current version ${item.currentVersion} · approved version ${item.approvedVersion ?? "none"} · ${item.stale ? "inputs changed; review required" : "inputs current"}`;
      article.append(label);
      const review = document.createElement("button"); review.type = "button"; review.className = "button secondary workbench-review-material";
      review.dataset.id = item.id; review.textContent = state.lang === "es" ? "Abrir / revisar material" : "Open / review material";
      review.setAttribute("aria-label", `${review.textContent}: ${item.format || "Material"}, version ${item.currentVersion}`);
      article.append(review);
      review.onclick = () => openMaterialForReview(review, item.id, scope);
      for (const impact of item.impacts.filter(value => value.state !== "current")) {
        const paragraph = document.createElement("p");
        paragraph.textContent = `${impact.sourceId ? "Source" : "Contribution consent"}: ${impact.state} (revision ${impact.beforeRevision} → ${impact.afterRevision ?? "unavailable"})`;
        article.append(paragraph);
      }
      if (item.versions?.length > 1) article.append(renderVersionComparison(item.versions, item.currentVersion, item.approvedVersion));
      box.append(article);
    }
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") box.textContent = "Change and consent impact information is unavailable. Refresh before review.";
  }
}
async function loadOperations() {
  const scope = identityScope();
  if (scope.role !== "creator") return;
  const box = $("#operations"), life = state.session?.lifecycle;
  $("#lifecycleStatus").textContent = life ? `Session ${life.status}; expires ${new Date(life.expiresAt).toLocaleString()}. Invitation expires ${new Date(life.invitationExpiresAt).toLocaleString()}.` : "Session expiry information unavailable.";
  try {
    const data = await API.call("operations", null, {scope}); assertIdentity(scope);
    const a = data.admission;
    box.textContent = `In flight ${a.inFlight}/${a.limit}; admitted session calls ${a.sessionCalls}/${a.sessionCallLimit}; completed ${a.completed}, busy ${a.busy}, errors ${a.errors}. Median ${a.medianMs ?? "unknown"} ms; worst ${a.worstMs ?? "unknown"} ms. No waiting queue. ${captureText(data.capture)} Reservation and invoice amounts: unknown here.`;
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") box.textContent = "Operational state unavailable. Refresh to check recovery.";
  }
}
$("#refreshOperations").onclick=loadOperations;
let lifecycleBusy = false;
let invitationStateUncertain = false;
function lockLifecycle(busy) {
  lifecycleBusy = busy;
  for (const id of ["renewInvitation", "rotateInvitation", "refreshInvitationState", "closeSession", "cleanupSession", "recoveryCleanup"]) {
    const button = document.getElementById(id);
    button.disabled = busy || (invitationStateUncertain && id !== "refreshInvitationState");
  }
}
async function cleanupRetainedSession() {
  if (tabOnlyAccess) { toast("Deleting a session requires saved access for recovery."); return; }
  if (lifecycleBusy || invitationStateUncertain) return;
  const scope = identityScope();
  const confirmation = prompt("Permanently delete this session and its data. Enter the exact session ID to confirm:");
  if (confirmation === null) return;
  lockLifecycle(true);
  try {
    await API.call("cleanup", {confirmSessionId: confirmation}, {scope});
    assertIdentity(scope);
    const wasTabOnly = tabOnlyAccess;
    if (!wasTabOnly) phase11Controller?.clearPrivateRecovery();
    removeActiveSavedIdentity();
    resetIdentityState();
    if (!wasTabOnly) renderSavedIdentities();
    if (!$("#accessDialog").open) $("#accessDialog").showModal();
    showError($("#accessError"), "Session data deleted. Separate backups and external provider records are not deleted here.");
  } catch (error) {
    if (scope.epoch !== state.identityEpoch || error.name === "AbortError") return;
    const message = error.code === "confirmation_mismatch"
      ? "Session ID did not match; nothing was deleted."
      : "Deletion could not be confirmed. Check local creator access and try again.";
    if ($("#accessDialog").open) showError($("#accessError"), message);
    else toast(message);
  } finally { lockLifecycle(false); }
}
function applyInvitationLifecycleResponse(data) {
  state.session.lifecycle = data.lifecycle || state.session.lifecycle;
  state.session.joinCode = state.joinCode = data.joinCode;
  state.session.publicUrl = data.publicUrl || null;
  state.session.invitationUrl = data.invitationUrl || null;
  state.session.viewerOrigin = data.viewerOrigin || null;
  saveIdentity();
  renderSession();
}
async function runInvitationLifecycle(action) {
  if (tabOnlyAccess) { toast("Changing an invitation requires saved access for recovery."); return; }
  if (lifecycleBusy || invitationStateUncertain || state.role !== "creator") return;
  const confirmation = action === "renew"
    ? t("invitationRenewConfirm")
    : t("rotateInvitationConfirm");
  if (!confirm(confirmation)) return;
  const scope = identityScope();
  lockLifecycle(true);
  try {
    const data = await API.call("lifecycle", {action}, {scope});
    assertIdentity(scope);
    invitationStateUncertain = false;
    applyInvitationLifecycleResponse(data);
    await loadOperations();
    toast(action === "renew"
      ? t("invitationRenewSuccess")
      : t("invitationRotateSuccess"));
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") {
      invitationStateUncertain = true;
      $("#lifecycleStatus").textContent = t("invitationRefreshUnknown");
      toast(t("invitationRefreshUnknown"));
    }
  } finally { lockLifecycle(false); }
}
$("#renewInvitation").onclick = () => runInvitationLifecycle("renew");
$("#rotateInvitation").onclick = () => runInvitationLifecycle("rotate");
$("#refreshInvitationState").onclick = async () => {
  if (lifecycleBusy || state.role !== "creator") return;
  const scope = identityScope();
  lockLifecycle(true);
  $("#lifecycleStatus").textContent = t("invitationRefreshStarted");
  try {
    const data = await API.call("session", null, {scope});
    assertIdentity(scope);
    const current = data.session || data;
    if (!current.joinCode || !current.lifecycle?.invitationExpiresAt) throw new Error("invitation_state_incomplete");
    state.session = {
      ...state.session,
      ...current,
      publicUrl: current.publicUrl || new URL("/public/" + encodeURIComponent(current.joinCode), location.origin).toString(),
      invitationUrl: current.invitationUrl || null,
      viewerOrigin: current.viewerOrigin || null,
    };
    state.joinCode = current.joinCode;
    invitationStateUncertain = false;
    saveIdentity();
    renderSession();
    await loadOperations();
    toast(t("invitationRefreshSuccess"));
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") {
      $("#lifecycleStatus").textContent = t("invitationRefreshUnknown");
      toast(t("invitationRefreshUnknown"));
    }
  } finally { lockLifecycle(false); }
};
$("#closeSession").onclick = async () => {
  if (tabOnlyAccess) { toast("Closing a session requires saved access for recovery."); return; }
  if (lifecycleBusy || invitationStateUncertain || !confirm("This ends access for everyone, including the public view. Stored data is retained until explicitly deleted.")) return;
  const scope = identityScope(); lockLifecycle(true);
  try {
    await API.call("lifecycle", {action:"close"}, {scope});
    assertIdentity(scope);
    if (!tabOnlyAccess) phase11Controller?.clearPrivateRecovery();
    const wasTabOnly = tabOnlyAccess;
    resetIdentityState();
    await loadCore(!wasTabOnly, !wasTabOnly);
  } catch (error) {
    if (scope.epoch === state.identityEpoch && error.name !== "AbortError") toast("Could not confirm closure. Refresh before trying again.");
  } finally { lockLifecycle(false); }
};
$("#cleanupSession").onclick = cleanupRetainedSession;
$("#recoveryCleanup").onclick = cleanupRetainedSession;
$("#deletePrivateData").onclick=async () => {
  if (tabOnlyAccess) { showError($("#accessError"), "Deleting private data requires saved access for recovery."); return; }
  if (!confirm("Permanently delete your private session data and withdraw your contributions?")) return;
  const scope=identityScope(); try { await API.call("deletePrivateData",null,{scope}); assertIdentity(scope); const wasTabOnly = tabOnlyAccess; if (!wasTabOnly) { phase11Controller?.clearPrivateRecovery(); const localDraft = draftKey(); if(localDraft) localStorage.removeItem(localDraft); } removeActiveSavedIdentity(); resetIdentityState(); if (!wasTabOnly) renderSavedIdentities(); showError($("#accessError"),"Your private session data was deleted and contributions withdrawn."); } catch(e) { if(scope.epoch===state.identityEpoch && e.name!=="AbortError") showError($("#accessError"),"Deletion could not be confirmed. Try again while access remains available."); }
};

applyLanguage();
phase6Controller = createPhase6Controller({ api: API, state, identityScope, assertIdentity, assertSavedIdentity, normalizeList, refreshSources });
phase10Controller = createPhase10Controller({ api: API, state, identityScope, assertIdentity });
// Chapter requests retain their original intent until the server confirms the
// exact receipt. The journal belongs to the saved capability, never the bearer.
wave27Chapters = (() => {
  const root = $('#wave27Chapters');
  const refresh = document.createElement('button'), recover = document.createElement('button');
  const status = document.createElement('p'), componentRoot = document.createElement('div');
  const listDrafts = document.createElement('button'), draftList = document.createElement('ul'), exportChapter = document.createElement('button');
  refresh.type = recover.type = 'button';
  listDrafts.type = 'button'; listDrafts.textContent = 'Find existing chapter drafts';
  exportChapter.type = 'button'; exportChapter.textContent = 'Download approved chapter'; exportChapter.disabled = true;
  refresh.textContent = 'Load current chapter sources'; recover.textContent = 'Check saved chapter request';
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  root.append(refresh, recover, listDrafts, draftList, exportChapter, status, componentRoot);
  let generation = 0, captured = null, capturedExpiry = Infinity, expiryTimer = null, availableRefs = [], exportCandidate = null;
  const sourceSignature = () => JSON.stringify(normalizeList(state.context?.sources || state.context).map(s => [s.id, s.revision, s.status, s.audienceVisible, s.expiresAt, s.visibility, s.capabilities, s.permissions]));
  const chapterScope = () => ({role:state.role, actorId:capabilityNamespace, sessionId:state.sessionId, epoch:state.identityEpoch, sources:sourceSignature()});
  const keyFor = scope => `entrelineas.chapter27:${encodeURIComponent(scope.sessionId)}:${scope.actorBinding}`;
  const check = (scope, ticket) => {
    assertSavedIdentity(scope);
    if (scope.role !== 'creator' || !scope.actorBinding || ticket !== generation || sourceContextStale || sourceMutationPending || !captured || captured !== sourceSignature() || Date.now() >= capturedExpiry) throw Error('Chapter access changed');
  };
  const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(k => [k, canonical(value[k])])) : value;
  const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
  const validMaterial = m => m && /^[A-Za-z0-9_-]{1,128}$/.test(m.id) && m.format === 'chapter' && m.status === 'draft' && m.dependencyState === 'current' && Number.isSafeInteger(m.revision) && m.revision > 0 && Number.isSafeInteger(m.currentVersion) && m.currentVersion > 0 && typeof m.title === 'string' && Array.isArray(m.refs) && m.refs.length > 0 && m.refs.every(ref => availableRefs.some(current => same(current, ref)));
  const remember = result => { exportCandidate = {materialId:result.materialId, version:result.version, refs:structuredClone(result.refs)}; exportChapter.disabled = false; };
  const curate = material => {
    const chapters = chaptersFromMaterial(material, chapterScope());
    if (!chapters || !component.setDraft({materialId:material.id,version:material.currentVersion,revision:material.revision,title:material.title,chapters},chapterScope())) { component.reset(chapterScope()); return false; }
    return true;
  };
  const matching = (result, request) => result?.state === 'committed' && result.requestId === request.requestId && typeof result.materialId === 'string' && !!result.materialId && Number.isSafeInteger(result.objectRevision) && result.objectRevision > 0 && Number.isSafeInteger(result.version) && (request.version === null ? result.version === 1 : result.version === request.version + 1 && result.objectRevision > request.baseRevision) && (request.materialId === null || result.materialId === request.materialId) && JSON.stringify(canonical(result.refs)) === JSON.stringify(canonical(request.chapters.map(item => item.ref)));
  const readMarker = (raw, scope) => {
    const marker = JSON.parse(raw);
    if (!marker || marker.version !== 1 || marker.sessionId !== scope.sessionId || marker.actorId !== scope.actorBinding || !marker.request || typeof marker.request.requestId !== 'string' || !Array.isArray(marker.request.chapters) || !marker.request.chapters.length) throw Error('Saved chapter request is unavailable');
    return marker;
  };
  const locked = (scope, fn) => {
    if (!navigator.locks?.request) throw Error('Safe chapter recovery unavailable');
    return navigator.locks.request(keyFor(scope), fn);
  };
  const readReceipt = async (scope, ticket, expectedId) => locked(scope, async () => {
    check(scope, ticket);
    const key = keyFor(scope), raw = localStorage.getItem(key);
    if (raw === null) throw Error('No saved chapter request');
    const marker = readMarker(raw, scope);
    if (expectedId && marker.request.requestId !== expectedId) throw Error('Different original request');
    // A cached receipt is recovery metadata, not current authority. Re-read the
    // original ID so revoked sources, changed versions and actors remain fenced.
    const result = await API.call('w27ChapterReceipt', null, marker.request.requestId, {scope});
    check(scope, ticket);
    if (!matching(result, marker.request) || (marker.receipt && JSON.stringify(canonical(marker.receipt)) !== JSON.stringify(canonical(result))) || localStorage.getItem(key) !== raw) throw Error('Original chapter request unconfirmed');
    if (!marker.receipt) localStorage.setItem(key, JSON.stringify({...marker, receipt:result}));
    return result;
  });
  const openConfirmed = (scope, ticket, result) => locked(scope, async () => {
    check(scope, ticket);
    const key = keyFor(scope), raw = localStorage.getItem(key);
    if (raw === null) throw Error('No saved chapter request');
    const marker = readMarker(raw, scope);
    if (!marker.receipt || !matching(marker.receipt, marker.request) || JSON.stringify(canonical(marker.receipt)) !== JSON.stringify(canonical(result))) throw Error('Different chapter receipt');
    const opened = await phase10Controller.openExactStudioMaterial({materialId:result.materialId, version:result.version, revision:result.objectRevision});
    check(scope, ticket);
    if (!opened || localStorage.getItem(key) !== raw) throw Error('Exact Studio draft unavailable');
    // Keep the original request across reconnects, including after opening it.
    if (!marker.opened) localStorage.setItem(key, JSON.stringify({...marker, opened:true}));
    return opened;
  });
  const component = mountChapterDraft(componentRoot, {
    getScope: chapterScope,
    createRequestId: () => crypto.randomUUID(),
    createDraft: async ({request, identity}) => {
      const scope = identityScope(), ticket = generation;
      return locked(scope, async () => {
        check(scope, ticket);
        if (JSON.stringify(identity) !== JSON.stringify(chapterScope())) throw Error('Chapter identity changed');
        const key = keyFor(scope);
        const previous = localStorage.getItem(key);
        if (previous !== null) {
          const marker = readMarker(previous, scope);
          if (!marker.opened || !marker.receipt || !matching(marker.receipt, marker.request)) throw Error('Earlier chapter request unconfirmed');
          // Archive the confirmed original before reusing the active slot. Never
          // overwrite a different journal, including after an interrupted write.
          const archive = `${key}:confirmed:${encodeURIComponent(marker.request.requestId)}`;
          const existing = localStorage.getItem(archive);
          if (existing !== null && existing !== previous) throw Error('Chapter archive conflict');
          if (existing === null) localStorage.setItem(archive, previous);
          if (localStorage.getItem(key) !== previous || localStorage.getItem(archive) !== previous) throw Error('Chapter journal changed');
        }
        const raw = JSON.stringify({version:1, sessionId:scope.sessionId, actorId:scope.actorBinding, request});
        localStorage.setItem(key, raw);
        check(scope, ticket);
        const result = await API.call('w27ChapterCommit', request, {scope});
        check(scope, ticket);
        if (!matching(result, request) || localStorage.getItem(key) !== raw) throw Error('Chapter request unconfirmed');
        localStorage.setItem(key, JSON.stringify({version:1, sessionId:scope.sessionId, actorId:scope.actorBinding, request, receipt:result}));
        remember(result);
        return {result, identity};
      });
    },
    recover: async ({requestId, identity}) => {
      const scope = identityScope(), ticket = generation;
      if (JSON.stringify(identity) !== JSON.stringify(chapterScope())) throw Error('Chapter identity changed');
      const result = await readReceipt(scope, ticket, requestId);
      check(scope, ticket);
      return {result, identity};
    },
    openDraft: async ({materialId, version, revision, identity}) => {
      const scope = identityScope(), ticket = generation; check(scope, ticket);
      if (JSON.stringify(identity) !== JSON.stringify(chapterScope())) throw Error('Chapter identity changed');
      const result = await readReceipt(scope, ticket);
      if (result.materialId !== materialId || result.version !== version || result.objectRevision !== revision) throw Error('Different chapter receipt');
      const opened = await openConfirmed(scope, ticket, result);
      check(scope, ticket);
      if (!opened) throw Error('Exact Studio draft unavailable');
      navTo('studio'); $('#p10Studio').querySelector('details').open = true; $('#p10Studio').scrollIntoView();
      return {...opened, identity};
    }
  });
  function reset() { generation++; clearTimeout(expiryTimer); expiryTimer = null; captured = null; capturedExpiry = Infinity; availableRefs = []; exportCandidate = null; exportChapter.disabled = true; draftList.replaceChildren(); component.update([], chapterScope()); component.reset(); status.textContent = 'Load current sources to curate or recover a chapter draft.'; }
  refresh.addEventListener('click', async () => {
    const scope = identityScope(), ticket = ++generation; clearTimeout(expiryTimer); expiryTimer = null; captured = null; capturedExpiry = Infinity; availableRefs = []; exportCandidate = null; exportChapter.disabled = true; draftList.replaceChildren(); component.update([], chapterScope()); component.reset();
    try {
      assertSavedIdentity(scope);
      if (scope.role !== 'creator' || !scope.actorBinding) throw Error('Creator access required');
      const context = await refreshSources(scope, {chapterRefresh:true}); assertSavedIdentity(scope);
      if (ticket !== generation || sourceContextStale) throw Error('Sources changed');
      captured = sourceSignature();
      const choices = [];
      for (const source of normalizeList(context?.sources || context)) {
        if (source.status !== 'active' || source.audienceVisible !== true || typeof source.id !== 'string' || !Number.isInteger(source.revision) || (source.expiresAt && (!Number.isFinite(Date.parse(source.expiresAt)) || Date.parse(source.expiresAt) <= Date.now()))) continue;
        if (source.expiresAt) capturedExpiry = Math.min(capturedExpiry, Date.parse(source.expiresAt));
        const ref = {sessionId:scope.sessionId, sourceId:source.id, sourceRevision:source.revision};
        choices.push({ref, rightsState:'current', eligible:true, sourceTitle:source.title || ''});
        const timeline = await API.call('p10Timeline', null, source.id, {scope}); check(scope, ticket);
        for (const moment of normalizeList(timeline?.moments)) {
          const r = moment.ref;
          if (moment.available !== false && moment.redacted !== true && moment.retracted !== true && moment.stale !== true && (moment.status == null || ['available','uncertain'].includes(moment.status)) && r?.sessionId === ref.sessionId && r.sourceId === ref.sourceId && r.sourceRevision === ref.sourceRevision && typeof r.momentId === 'string' && Number.isInteger(r.startMs) && Number.isInteger(r.endMs) && r.startMs >= 0 && r.endMs > r.startMs) choices.push({ref:r, rightsState:'current', eligible:true, sourceTitle:source.title || '', excerpt:moment.text || ''});
        }
      }
      check(scope, ticket); availableRefs = choices.map(choice => structuredClone(choice.ref)); component.update(choices, chapterScope());
      const armExpiry = () => { if (ticket !== generation || !Number.isFinite(capturedExpiry)) return; const delay = capturedExpiry - Date.now(); if (delay <= 0) { reset(); return; } expiryTimer = setTimeout(armExpiry, Math.min(delay, 2147483647)); };
      armExpiry();
      const saved = localStorage.getItem(keyFor(scope));
      let confirmed = false;
      if (saved !== null) { try { const marker = readMarker(saved, scope); confirmed = !!marker.receipt && matching(marker.receipt, marker.request); } catch { /* preserve unreadable recovery data */ } }
      status.textContent = saved === null ? 'Choose current sources for a chapter draft.' : confirmed ? 'The original chapter request is confirmed. Open its exact Studio draft before creating another.' : 'An earlier chapter request is unconfirmed. Check it before creating another.';
    } catch { if (ticket === generation) { captured = null; component.update([], chapterScope()); component.reset(); status.textContent = 'Current chapter sources or saved access are unavailable.'; } }
  });
  recover.addEventListener('click', async () => {
    const scope = identityScope(), ticket = generation;
    try {
      const result = await readReceipt(scope, ticket); check(scope, ticket);
      const opened = await openConfirmed(scope, ticket, result);
      check(scope, ticket);
      const material = (await API.call('p10StudioMaterial', null, result.materialId, {scope}))?.material; check(scope, ticket);
      if (!validMaterial(material) || material.id !== result.materialId || material.revision !== result.objectRevision || material.currentVersion !== result.version || !same(material.refs,result.refs)) throw Error('Draft changed');
      remember(result);
      status.textContent = curate(material) ? 'Original chapter confirmed. Its chapters are ready to edit.' : 'The Studio draft is open, but its chapter labels cannot be safely recovered.';
      if (opened) { navTo('studio'); $('#p10Studio').querySelector('details').open = true; $('#p10Studio').scrollIntoView(); }
    } catch { if (ticket === generation) status.textContent = 'The original request or its confirmed Studio draft is unavailable. Its saved recovery information remains preserved.'; }
  });
  listDrafts.addEventListener('click', async () => {
    const scope = identityScope(), ticket = generation;
    draftList.replaceChildren();
    try {
      check(scope, ticket);
      if (localStorage.getItem(keyFor(scope)) !== null) throw Error('Saved request takes precedence');
      const collection = await API.call('p10StudioMaterials', null, {scope}); check(scope, ticket);
      for (const summary of normalizeList(collection?.materials)) {
        if (summary.format !== 'chapter' || summary.status !== 'draft' || summary.dependencyState !== 'current' || !/^[A-Za-z0-9_-]{1,128}$/.test(summary.id)) continue;
        const response = await API.call('p10StudioMaterial', null, summary.id, {scope}); check(scope, ticket);
        const material = response?.material;
        if (!validMaterial(material) || material.id !== summary.id) continue;
        const selected = structuredClone(material), row = document.createElement('li'), button = document.createElement('button');
        button.type = 'button'; button.textContent = `Open ${selected.title} · version ${selected.currentVersion} · ${selected.id}`;
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            await locked(scope, async () => {
              check(scope, ticket);
              if (localStorage.getItem(keyFor(scope)) !== null) throw Error('Saved request takes precedence');
              const current = (await API.call('p10StudioMaterial', null, selected.id, {scope}))?.material; check(scope, ticket);
              if (!validMaterial(current) || current.id !== selected.id || current.revision !== selected.revision || current.currentVersion !== selected.currentVersion || !same(current.refs, selected.refs)) throw Error('Material changed');
              const receipt = await API.call('w27ChapterRecovery', null, selected.id, selected.revision, selected.currentVersion, {scope}); check(scope, ticket);
              if (receipt?.state !== 'committed' || typeof receipt.requestId !== 'string' || !receipt.requestId || receipt.materialId !== selected.id || receipt.objectRevision !== selected.revision || receipt.version !== selected.currentVersion || !same(receipt.refs, selected.refs) || localStorage.getItem(keyFor(scope)) !== null) throw Error('Draft unavailable');
              const latest = (await API.call('p10StudioMaterial', null, selected.id, {scope}))?.material; check(scope, ticket);
              if (!validMaterial(latest) || latest.id !== selected.id || latest.revision !== selected.revision || latest.currentVersion !== selected.currentVersion || !same(latest.refs, selected.refs) || localStorage.getItem(keyFor(scope)) !== null) throw Error('Material changed');
              const opened = await phase10Controller.openExactStudioMaterial({materialId:selected.id, version:selected.currentVersion, revision:selected.revision}); check(scope, ticket);
              if (!opened || localStorage.getItem(keyFor(scope)) !== null) throw Error('Draft unavailable');
              remember(receipt);
              navTo('studio'); $('#p10Studio').querySelector('details').open = true; $('#p10Studio').scrollIntoView();
              status.textContent = curate(latest) ? 'The selected Studio draft is open and ready to curate.' : 'The Studio draft is open, but its chapter labels cannot be safely recovered.';
            });
          } catch { if (ticket === generation) status.textContent = 'The selected draft could not be opened. It remains unchanged.'; }
          finally { button.disabled = false; }
        });
        row.append(button); draftList.append(row);
      }
      check(scope, ticket);
      status.textContent = draftList.children.length ? 'Select the exact Studio draft to open.' : 'No current chapter drafts are available.';
    } catch { if (ticket === generation) { draftList.replaceChildren(); status.textContent = 'Existing drafts are unavailable, or a saved request must be checked first. Nothing was changed.'; } }
  });
  exportChapter.addEventListener('click', async () => {
    const scope = identityScope(), ticket = generation, expected = exportCandidate && structuredClone(exportCandidate);
    try {
      check(scope,ticket); if (!expected) throw Error('No selected chapter');
      exportChapter.disabled = true;
      const isCurrent = () => { try { check(scope,ticket); return same(expected,exportCandidate); } catch { return false; } };
      await downloadApprovedChapter({expected,isCurrent,readCurrent:async () => {
        check(scope,ticket);
        const material = (await API.call('p10StudioMaterial',null,expected.materialId,{scope}))?.material;
        check(scope,ticket);
        if (!material?.refs?.every(ref => availableRefs.some(current => same(current,ref)))) throw Error('Source unavailable');
        return material;
      }});
      if (isCurrent()) status.textContent = 'Approved chapter downloaded. Downloaded copies cannot be recalled.';
    } catch { if (ticket === generation) status.textContent = 'The exact approved chapter is unavailable or changed. Review and approve its current version before downloading.'; }
    finally { if (ticket === generation) exportChapter.disabled = !exportCandidate; }
  });
  reset(); return {reset};
})();
async function openWave15Moment(ref, scope, guard = () => {}) {
  try {
    guard(); assertIdentity(scope); await refreshSources(scope); guard(); assertIdentity(scope);
    const source = normalizeList(state.context?.sources || state.context).find(x => x.id === ref.sourceId && x.revision === ref.sourceRevision && x.status === "active" && (scope.role === "creator" || x.audienceVisible === true));
    if (!source) { toast("This source changed or is unavailable. Refresh before returning."); return; }
    // Re-read the indexed moment under current rights before using the reference.
    const data = await API.call("p10Timeline", null, ref.sourceId, {scope}); guard(); assertIdentity(scope);
    if (!Array.isArray(data.moments) || !data.moments.some(x => ["sessionId", "sourceId", "sourceRevision", "momentId", "startMs", "endMs"].every(k => x.ref?.[k] === ref[k]))) { toast("This moment is no longer available. Refresh before returning."); return; }
    $("#questionSource").value = ref.sourceId; $("#questionMoment").value = `${Math.floor(ref.startMs / 60000)}:${String(Math.floor(ref.startMs / 1000) % 60).padStart(2, "0")}`;
    navTo("audience"); $("#question").focus();
  } catch (error) { if (scope.epoch === state.identityEpoch && error.name !== "AbortError") toast("Could not confirm access to this moment."); }
}
// Profile selection is scoped to a moment rechecked with the current actor. The
// generation input is deliberately absent until an actual run/segment is selected.
const wave23Listening = (() => {
  const sameMomentRef = (a, b) => {
    const keys = ['sessionId', 'sourceId', 'sourceRevision', 'momentId', 'startMs', 'endMs'];
    return !!a && !!b && Object.keys(a).length === keys.length && Object.keys(b).length === keys.length && keys.every(key => Object.hasOwn(a, key) && Object.hasOwn(b, key) && a[key] === b[key]);
  };
  const root = $('#wave23Listening');
  const inputLabel = document.createElement('label'); inputLabel.textContent = 'Private speech run ID ';
  const input = document.createElement('input'); input.autocomplete = 'off'; input.maxLength = 128; inputLabel.append(input);
  const open = document.createElement('button'); open.type = 'button'; open.textContent = 'Load final segments';
  const segmentLabel = document.createElement('label'); segmentLabel.textContent = 'Final segment ';
  const segment = document.createElement('select'); segmentLabel.append(segment);
  const editionLabel = document.createElement('label'); editionLabel.textContent = 'Edition ID for accessibility (optional) ';
  const edition = document.createElement('input'); edition.autocomplete = 'off'; edition.maxLength = 160; editionLabel.append(edition);
  const requestLabel = document.createElement('label'); requestLabel.textContent = 'Existing listening request ID ';
  const request = document.createElement('input'); request.autocomplete = 'off'; request.maxLength = 128; requestLabel.append(request);
  const playPrepared = document.createElement('button'); playPrepared.type = 'button'; playPrepared.textContent = 'Play prepared audio';
  const descriptionLabel = document.createElement('label'); descriptionLabel.textContent = ' Audio description ';
  const description = document.createElement('input'); description.type = 'checkbox'; description.disabled = true; descriptionLabel.append(description);
  const captionLabel = document.createElement('label'); captionLabel.textContent = 'Caption preference ';
  const captions = document.createElement('select'); captions.disabled = true;
  for (const value of ['off', 'original', 'translated', 'both']) captions.append(new Option(value, value));
  captionLabel.append(captions);
  const use = document.createElement('button'); use.type = 'button'; use.textContent = 'Use selected segment';
  const message = document.createElement('p'); message.setAttribute('role', 'status');
  root.append(inputLabel, open, segmentLabel, use, editionLabel, requestLabel, playPrepared, descriptionLabel, captionLabel, message);
  const component = mountListening23(root, {});
  const continuity = mountContinuity25(root, {});
  const qualityChoice = mountQualityChoice(root);
  const operatingButton = document.createElement('button'); operatingButton.type = 'button'; operatingButton.textContent = 'Check current operating status'; operatingButton.disabled = true;
  const operatingMessage = document.createElement('p'); operatingMessage.setAttribute('role', 'status');
  const operatingRoot = document.createElement('div'); root.append(operatingButton, operatingMessage, operatingRoot);
  let operating = null, operatingDelivery = null;
  const meaningControls = document.createElement('div');
  const meaningLabel = document.createElement('label'); meaningLabel.textContent = 'Meaning inspection language ';
  const meaningLanguage = document.createElement('select');
  meaningLanguage.append(new Option('English', 'en'), new Option('Spanish', 'es')); meaningLabel.append(meaningLanguage);
  const meaningOpen = document.createElement('button'); meaningOpen.type = 'button'; meaningOpen.textContent = 'Inspect selected moment'; meaningOpen.disabled = true;
  const meaningStatus = document.createElement('p'); meaningStatus.setAttribute('role', 'status');
  const meaningRecovery = document.createElement('div');
  const meaningRoot = document.createElement('div'); meaningControls.append(meaningLabel, meaningOpen, meaningStatus, meaningRecovery, meaningRoot); root.append(meaningControls);
  const savedTranslations = mountSavedTranslations(meaningControls, {owner:() => active, language:() => meaningLanguage.value, sameRef:sameMomentRef, changed:() => { ++meaningLanguageGeneration; meaningSelection = null; meaning.invalidate(); }});
  const visualAssociations = mountVisualAssociations(meaningControls, {owner:() => active, sameRef:sameMomentRef, changed:() => { ++meaningLanguageGeneration; meaningSelection = null; meaning.invalidate(); }});
  const accessibilityOpen = document.createElement('button'); accessibilityOpen.type = 'button'; accessibilityOpen.textContent = 'Open accessibility for selected edition'; accessibilityOpen.disabled = true;
  const momentAccessibilityOpen = document.createElement('button'); momentAccessibilityOpen.type = 'button'; momentAccessibilityOpen.textContent = 'Open accessibility for selected moment'; momentAccessibilityOpen.disabled = true;
  const accessibilityRoot = document.createElement('div'); root.append(momentAccessibilityOpen, accessibilityOpen, accessibilityRoot);
  let accessibilityContext = null, accessibilityGeneration = 0;
  const accessibility = mountConnectedAccessibility(accessibilityRoot, {
    isCurrent: ctx => { try { return !!ctx && ctx === accessibilityContext && !!active && active.ticket === ctx.ticket && active.ref === ctx.ref && (assertSavedIdentity(ctx.identity), true); } catch { return false; } },
    call: async (...args) => { const owner = active, ctx = accessibilityContext; if (!owner || !ctx) throw Error('Selection changed'); const dto = await owner.invoke(...args.slice(0,-1)); if (active !== owner || accessibilityContext !== ctx) throw Error('Selection changed'); if (args[0] === 'w25PreferencesGet') owner.displayPreference?.(dto); return dto; },
    withPreferenceSave: (ctx, operation) => ctx.withPreferenceSave(operation),
    dispatchPreferenceSave: (ctx, body, dispatch) => ctx.dispatchPreferenceSave(body, dispatch),
    requestDescription: (id, description, identity, isCurrent) => wave20Delivery.requestDescription(id, description, identity, isCurrent),
    stopDescription: () => phase12Controller?.stopDelivery(),
    returnFocus: ctx => (ctx.returnButton || accessibilityOpen).focus()
  });
  const meaning = mountMeaning(meaningRoot, {isCurrent: candidate => {
    try {
      if (!candidate || candidate !== meaningSelection || !active || candidate.ticket !== generation) return false;
      assertIdentity(active.scope);
      return normalizeList(state.context?.sources || state.context).some(x => x.id === candidate.ref.sourceId && x.revision === candidate.ref.sourceRevision && x.status === 'active' && x.audienceVisible === true);
    } catch { return false; }
  }, newRequestId: () => crypto.randomUUID(), createFlag: async (candidate, request) => {
    const owner = active;
    if (!owner || candidate !== meaningSelection || state.role !== 'viewer' || !owner.scope.viewerId || !owner.scope.actorBinding || !owner.scope.sessionId) throw Error('Current saved viewer required');
    assertSavedIdentity(owner.scope);
    if (!navigator.locks?.request) throw Error('Safe recovery unavailable');
    const key = `entrelineas.w26.meaning.v1:${owner.scope.sessionId}:${owner.scope.actorBinding}`;
    return navigator.locks.request(key, async () => {
      assertSavedIdentity(owner.scope); await owner.current(); assertSavedIdentity(owner.scope);
      if (candidate !== meaningSelection || localStorage.getItem(key) !== null) throw Error('Previous note requires recovery');
      if (!sameMomentRef(request.ref, owner.ref)) throw Error('Source changed');
      const raw = JSON.stringify({version:1, request});
      localStorage.setItem(key, raw);
      try {
        const result = await API.call('w26MeaningFlag', request, {scope:owner.scope});
        await owner.current(); assertSavedIdentity(owner.scope);
        if (candidate !== meaningSelection || result?.visibility !== 'private' || !sameMomentRef(result.ref, request.ref) || result.field !== request.field || result.note !== request.note || typeof result.id !== 'string' || !Number.isInteger(result.revision) || localStorage.getItem(key) !== raw) throw Error('Unconfirmed note');
        localStorage.removeItem(key); return result;
      } catch (error) { if (active === owner) showMeaningRecovery(owner); throw error; }
    });
  }});
  let meaningSelection = null, meaningLanguageGeneration = 0;
  const recovery = document.createElement('div'); root.append(recovery);
  const continuityNotice = document.createElement('p'); continuityNotice.setAttribute('role', 'status'); root.append(continuityNotice);
  let generation = 0;
  let active = null, loaded = null;
  function showMeaningRecovery(owner) {
    meaningRecovery.replaceChildren();
    const message = document.createElement('p'); message.textContent = 'A private note may be unconfirmed. Check its original request before saving another.';
    const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Check previous private note';
    button.onclick = async () => {
      button.disabled = true;
      try {
        assertSavedIdentity(owner.scope); if (owner.scope.role !== 'viewer' || !owner.scope.viewerId || !owner.scope.actorBinding || !owner.scope.sessionId || !navigator.locks?.request) throw Error('Safe recovery unavailable');
        const key = `entrelineas.w26.meaning.v1:${owner.scope.sessionId}:${owner.scope.actorBinding}`;
        await navigator.locks.request(key, async () => {
          assertSavedIdentity(owner.scope); await owner.current(); assertSavedIdentity(owner.scope);
          const raw = localStorage.getItem(key), marker = JSON.parse(raw), request = marker?.request;
          if (!raw || marker.version !== 1 || !sameMomentRef(request?.ref, owner.ref) || !['source','translation','visual'].includes(request.field) || typeof request.note !== 'string' || !request.note.trim() || request.note.length > 1000 || request.note.includes('\0') || typeof request.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(request.requestId)) throw Error('Original request unavailable');
          const result = await API.call('w26MeaningFlag', request, {scope:owner.scope});
          await owner.current(); assertSavedIdentity(owner.scope);
          if (result?.visibility !== 'private' || !sameMomentRef(result.ref, request.ref) || result.field !== request.field || result.note !== request.note || typeof result.id !== 'string' || !Number.isInteger(result.revision) || localStorage.getItem(key) !== raw) throw Error('Unconfirmed note');
          localStorage.removeItem(key);
        });
        if (active === owner) { meaningRecovery.replaceChildren(); meaningStatus.textContent = 'The original private note was confirmed. Inspect the moment again to save another.'; }
      } catch { if (active === owner) message.textContent = 'The original note remains unconfirmed. Return to its original moment and check again.'; }
      finally { if (active === owner) button.disabled = false; }
    };
    meaningRecovery.append(message, button);
  }
  function reset() { ++generation; active = loaded = null; qualityChoice.update(); savedTranslations.reset(); visualAssociations.reset(); operatingDelivery = null; operating?.destroy(); operating = null; operatingButton.disabled = true; operatingMessage.textContent = ''; accessibilityContext = null; accessibility.reset(); accessibilityOpen.disabled = momentAccessibilityOpen.disabled = true; phase12Controller?.stopDelivery(); input.value = edition.value = request.value = ""; description.disabled = captions.disabled = true; open.disabled = false; use.disabled = false; playPrepared.disabled = false; meaningSelection = null; meaning.invalidate(); meaningOpen.disabled = true; meaningStatus.textContent = ''; meaningRecovery.replaceChildren(); segment.replaceChildren(); component.update({}); continuity.update({}); recovery.replaceChildren(); continuityNotice.textContent = ''; message.textContent = 'Select a current moment and a private speech run.'; }
  function select(ref, scope) {
    try { assertIdentity(scope); } catch { return; }
    if (tabOnlyAccess) { reset(); message.textContent = 'Listening requires saved access to protect request recovery.'; return; }
    try { assertSavedIdentity(scope); } catch { return; }
    operatingDelivery = null; operating?.destroy(); operating = null; operatingButton.disabled = false; operatingMessage.textContent = ''; accessibilityContext = null; accessibility.reset(); accessibilityOpen.disabled = momentAccessibilityOpen.disabled = false; phase12Controller?.stopDelivery();
    const ticket = ++generation, editionId = edition.value.trim();
    meaningSelection = null; meaning.invalidate(); meaningOpen.disabled = false; meaningStatus.textContent = ''; active = {ref, scope, ticket}; loaded = null; open.disabled = false; use.disabled = false; playPrepared.disabled = false; segment.replaceChildren(); recovery.replaceChildren(); continuityNotice.textContent = ''; continuity.update({}); message.textContent = 'Enter a private speech run for this moment and load its final segments.';
    const check = () => { assertSavedIdentity(scope); if (ticket !== generation || edition.value.trim() !== editionId) throw new DOMException('Context changed', 'AbortError'); };
    const current = async () => {
      check(); await refreshSources(scope); check();
      const source = normalizeList(state.context?.sources || state.context).find(x => x.id === ref.sourceId && x.revision === ref.sourceRevision && x.status === 'active' && x.audienceVisible === true);
      if (!source) throw Error('Source unavailable');
      const data = await API.call('p10Timeline', null, ref.sourceId, {scope}); check();
      if (!Array.isArray(data.moments) || !data.moments.some(x => ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(k => x.ref?.[k] === ref[k]))) throw Error('Moment unavailable');
    };
    const invoke = async (key, body, ...args) => { await current(); check(); const value = await API.call(key, body, ...args, {scope}); check(); await current(); check(); return value; };
    const continuityScope = {actorId:scope.viewerId || scope.actorBinding, sessionId:scope.sessionId, scopeGeneration:ticket, sourceId:ref.sourceId, sourceRevision:ref.sourceRevision, rightsGeneration:ticket};
    const preferenceKey = `entrelineas.w25.preference.v1:${scope.sessionId}:${scope.actorBinding}`;
    let observedPreference = null, descriptionDirty = false, captionsDirty = false, pendingPosition = null;
    description.disabled = captions.disabled = true;
    const sameRef = other => other && ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(k => other[k] === ref[k]);
    async function selectedChoice() {
      const data = await invoke('w23SelectionGet', null), selection = data?.selection, profile = data?.profile;
      if (!sameRef(selection?.ref) || typeof selection.profileId !== 'string' || !Number.isSafeInteger(selection.revision) || profile?.profileId !== selection.profileId || profile?.revision !== selection.revision || typeof profile.language !== 'string') throw Error('Select the current profile for this moment');
      return {language:profile.language, profileId:selection.profileId, profileRevision:selection.revision, mode:'read'};
    }
    function displayPreference(dto) { check(); phase12Controller?.setAccessibilityPreference(scope, ref, dto); }
    active.displayPreference = displayPreference;
    async function preferenceSnapshot() {
      const choice = await selectedChoice(); check();
      const dto = await invoke('w25PreferencesGet', null, editionId || null); check();
      if (dto.selection && !sameRef(dto.selection.ref)) throw Error('Saved moment changed');
      const choices = supportedChoices(dto, choice);
      observedPreference = dto; displayPreference(dto);
      if (typeof dto.descriptionEnabled === 'boolean' && typeof dto.descriptionAvailable === 'boolean' && ['off','original','translated','both'].includes(dto.captionMode) && typeof dto.captionAvailable === 'boolean') {
        if (!descriptionDirty) description.checked = dto.descriptionEnabled;
        if (!captionsDirty) captions.value = dto.captionMode;
        description.disabled = captions.disabled = false;
      } else { description.disabled = captions.disabled = true; }
      const notices = [];
      if (dto.state !== 'unset' && dto.positionAvailable !== true) notices.push('The saved position cannot be verified. Preference saves are unavailable until it can be preserved.');
      if (dto.selection && typeof dto.descriptionEnabled === 'boolean' && typeof dto.descriptionAvailable === 'boolean' && typeof dto.captionMode === 'string' && typeof dto.captionAvailable === 'boolean') {
        notices.push(`Audio description: ${dto.descriptionEnabled ? 'on' : 'off'}${dto.descriptionAvailable ? '' : ' (currently unavailable)'}. Captions: ${dto.captionMode}${dto.captionAvailable ? '' : ' (currently unavailable)'}.`);
      }
      continuityNotice.textContent = notices.join(' ');
      let receipt = 'unavailable';
      const runId = input.value.trim(), requestId = request.value.trim();
      if (/^[A-Za-z0-9._:-]{1,128}$/.test(runId) && /^[A-Za-z0-9._:-]{1,128}$/.test(requestId)) {
        try {
          const prepared = await invoke('w25ListeningPreload', {runId, requestId}); check();
          if (input.value.trim() !== runId || request.value.trim() !== requestId) throw Error('Receipt changed');
          if (prepared?.state === 'ready' && prepared.binding?.runId === runId && prepared.binding?.requestId === requestId && /^[a-f0-9]{64}$/.test(prepared.audioSha256 || '')) receipt = 'ready';
          else if (prepared?.state === 'unknown') receipt = 'unknown';
        } catch { check(); receipt = 'unavailable'; }
      }
      return continuitySnapshot(continuityScope, dto, choices, {state:'unknown'}, receipt);
    }
    function supportedChoices(dto, choice) {
      const support = dto?.modeSupport, selection = support?.selection;
      const matches = sameRef(selection?.ref) && selection.profileId === choice.profileId && selection.profileRevision === choice.profileRevision && selection.language === choice.language;
      const choices = matches && support?.read === true ? [choice] : [];
      if (choices.length && support.listen === true) choices.push({...choice, mode:'listen'});
      return choices;
    }
    const validPosition = p => p === null || (p && Object.keys(p).sort().join(',') === 'bindingId,offsetMs' && typeof p.bindingId === 'string' && p.bindingId.length > 0 && p.bindingId.length <= 128 && Number.isSafeInteger(p.offsetMs) && p.offsetMs >= 0 && p.offsetMs <= 864000000);
    const confirmedPreference = (dto, body, choice) => dto?.state === 'available' && dto.revision === body.expectedRevision + 1 && dto.mode === body.mode && dto.positionAvailable === true && validPosition(dto.position) && (body.position === null ? dto.position === null : dto.position?.bindingId === body.position.bindingId && dto.position?.offsetMs === body.position.offsetMs) && (!Object.hasOwn(body, 'descriptionEnabled') || dto.descriptionEnabled === body.descriptionEnabled) && (!Object.hasOwn(body, 'captionMode') || dto.captionMode === body.captionMode) && sameRef(dto.selection?.ref) && dto.selection.profileId === choice.profileId && dto.selection.profileRevision === choice.profileRevision && dto.selection.language === choice.language;
    const markerMatches = (marker, choice) => marker?.version === 1 && sameRef(marker.ref) && ['read','listen'].includes(marker.choice?.mode) && ['profileId','profileRevision','language'].every(k => marker.choice[k] === choice[k]) && marker.body && Object.keys(marker.body).every(k => ['expectedRevision','mode','position','requestId','descriptionEnabled','captionMode'].includes(k)) && (!Object.hasOwn(marker.body,'descriptionEnabled') || typeof marker.body.descriptionEnabled === 'boolean') && (!Object.hasOwn(marker.body,'captionMode') || ['off','original','translated','both'].includes(marker.body.captionMode)) && typeof marker.body.requestId === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(marker.body.requestId) && Number.isSafeInteger(marker.body.expectedRevision) && marker.body.expectedRevision >= 0 && marker.body.mode === marker.choice.mode && validPosition(marker.body.position);
    async function lockedPreference(fn) {
      if (!navigator.locks?.request) throw Error('Safe recovery unavailable');
      return navigator.locks.request(preferenceKey, async () => { check(); return fn(); });
    }
    function showPreferenceRecovery() {
      recovery.replaceChildren();
      const notice = document.createElement('p'); notice.textContent = 'A previous preference save is unconfirmed. Check the original request before saving again.';
      const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Check previous preference save';
      button.onclick = async () => {
        button.disabled = true;
        try {
          const confirmed = await lockedPreference(async () => {
            const raw = localStorage.getItem(preferenceKey), marker = JSON.parse(raw), choice = await selectedChoice();
            check();
            if (!raw || !markerMatches(marker, choice) || localStorage.getItem(preferenceKey) !== raw) throw Error('Original selection unavailable or request changed');
            if ((marker.editionId || '') !== editionId) throw Error('Original edition unavailable');
            const dto = await invoke('w25PreferencesPut', marker.body, editionId || null);
            check();
            if (!confirmedPreference(dto, marker.body, choice) || localStorage.getItem(preferenceKey) !== raw) throw Error('Original request unconfirmed');
            const snapshot = continuitySnapshot(continuityScope, dto, supportedChoices(dto, choice), {state:'unknown'}, 'unavailable');
            localStorage.removeItem(preferenceKey);
            observedPreference = dto; displayPreference(dto);
            return {raw, snapshot};
          });
          check(); recovery.replaceChildren();
          const positionConfirmed = pendingPosition?.raw === confirmed.raw && continuity.confirmPositionSave(continuityScope, pendingPosition.token, confirmed.snapshot);
          pendingPosition = null;
          if (!positionConfirmed) continuity.update(continuityHost);
          message.textContent = 'Previous preference save confirmed. Restore preferences to see it.';
        } catch { if (ticket === generation) notice.textContent = 'The original save remains unconfirmed. Return to its selected profile and check it again.'; }
        finally { button.disabled = false; }
      };
      recovery.append(notice, button);
    }
    active.invoke = invoke;
    active.accessibilityContext = (manifest, language) => {
      const ctx = {identity:scope, ref, ticket, editionId, language, regionId:manifest.descriptionAudio?.regionId,
        scope:{...continuityScope, editionId, language},
        withPreferenceSave:operation => lockedPreference(async () => { check(); if (localStorage.getItem(preferenceKey) !== null) { showPreferenceRecovery(); throw Error('Previous save unconfirmed'); } return operation(crypto.randomUUID()); }),
        dispatchPreferenceSave:async (body, dispatch) => {
          const choice = await selectedChoice(); check();
          if (localStorage.getItem(preferenceKey) !== null) { showPreferenceRecovery(); throw Error('Previous save unconfirmed'); }
          const marker = JSON.stringify({version:1, ref:{...ref}, choice:{...choice, mode:body.mode}, body, editionId});
          localStorage.setItem(preferenceKey, marker);
          try { const dto = await dispatch(); check(); if (!confirmedPreference(dto, body, choice) || localStorage.getItem(preferenceKey) !== marker) throw Error('Save unconfirmed'); localStorage.removeItem(preferenceKey); observedPreference = dto; displayPreference(dto);
            // Keep the moment controls in sync with a confirmed edition edit,
            // without overwriting an unsaved choice made in the meantime.
            if (!descriptionDirty) description.checked = dto.descriptionEnabled;
            if (!captionsDirty) captions.value = dto.captionMode;
            return dto; }
          catch (error) { if (ticket === generation) showPreferenceRecovery(); throw error; }
        }};
      return ctx;
    };
    const continuityHost = {scope:continuityScope, load:preferenceSnapshot,
      restorePosition: async (_scope, position) => {
        if (position?.bindingId !== ref.sourceId || position.sourceId !== ref.sourceId || position.sourceRevision !== ref.sourceRevision || !Number.isSafeInteger(position.offsetMs) || position.offsetMs < 0) throw Error('Position changed');
        const validate = async () => {
          const dto = await invoke('w25PreferencesGet', null, editionId || null); check();
          if (dto?.state !== 'available' || dto.positionAvailable !== true || !sameRef(dto.selection?.ref) || dto.position?.bindingId !== position.bindingId || dto.position?.offsetMs !== position.offsetMs) throw Error('Position unavailable');
        };
        await phase12Controller.restoreOriginalPosition(ref, position, scope, validate); check();
      },
      preload: async () => {
        const runId = input.value.trim(), requestId = request.value.trim();
        if (!/^[A-Za-z0-9._:-]{1,128}$/.test(runId) || !/^[A-Za-z0-9._:-]{1,128}$/.test(requestId)) throw Error('Existing run and request required');
        const result = await invoke('w25ListeningPreload', {runId, requestId});
        check();
        if (input.value.trim() !== runId || request.value.trim() !== requestId || !['ready','unknown','unavailable'].includes(result?.state)) throw Error('Receipt changed');
        if (result.state === 'ready' && (result.binding?.runId !== runId || result.binding?.requestId !== requestId || !/^[a-f0-9]{64}$/.test(result.audioSha256 || ''))) throw Error('Receipt mismatch');
        return {state:result.state};
      },
      savePosition: async ({expectedRevision}, token) => {
        let journalStarted = false;
        try { return await lockedPreference(async () => {
        const selected = await selectedChoice(); check();
        const currentPreference = await invoke('w25PreferencesGet', null, editionId || null); check();
        if (currentPreference?.state !== 'available' || currentPreference.revision !== expectedRevision || !sameRef(currentPreference.selection?.ref) || !['profileId','profileRevision','language'].every(k => currentPreference.selection[k] === selected[k]) || !['read','listen'].includes(currentPreference.mode)) throw Error('Saved preference changed');
        const choice = {...selected, mode:currentPreference.mode};
        if (!supportedChoices(currentPreference, selected).some(item => item.mode === choice.mode)) throw Error('Selected mode is no longer available');
        if (localStorage.getItem(preferenceKey) !== null) { showPreferenceRecovery(); throw Error('Previous save unconfirmed'); }
        const position = phase12Controller.originalPosition(ref, scope); check();
        if (!position || !validPosition(position)) throw Error('Current original position unavailable');
        const body = {requestId:crypto.randomUUID(), expectedRevision, mode:choice.mode, position};
        const marker = JSON.stringify({version:1, ref:{...ref}, choice, body, editionId});
        journalStarted = true;
        localStorage.setItem(preferenceKey, marker);
        pendingPosition = {raw:marker, token};
        try {
          const dto = await invoke('w25PreferencesPut', body, editionId || null); check();
          if (!confirmedPreference(dto, body, choice) || localStorage.getItem(preferenceKey) !== marker) throw Error('Position save unconfirmed');
          const result = continuitySnapshot(continuityScope, dto, supportedChoices(dto, selected), {state:'unknown'}, 'unavailable');
          localStorage.removeItem(preferenceKey); pendingPosition = null; observedPreference = dto; return result;
        } catch (error) { if (ticket === generation) showPreferenceRecovery(); throw error; }
        }); } catch (error) {
          if (!journalStarted) throw {kind:'position-save-not-dispatched', scope:continuityScope, token};
          throw error;
        }
      },
      save: async ({choice, expectedRevision}, token) => {
        let journalStarted = false;
        try { return await lockedPreference(async () => {
        const currentChoice = await selectedChoice();
        check();
        if (!['profileId','profileRevision','language'].every(k => choice[k] === currentChoice[k]) || !['read','listen'].includes(choice.mode)) throw Error('Profile changed');
        const currentSupport = await invoke('w25PreferencesGet', null, editionId || null); check();
        if (!supportedChoices(currentSupport, currentChoice).some(item => item.mode === choice.mode)) throw Error('Selected mode is no longer available');
        if (localStorage.getItem(preferenceKey) !== null) { showPreferenceRecovery(); throw Error('Previous save unconfirmed'); }
        if (observedPreference?.revision !== expectedRevision || (observedPreference.state !== 'unset' && observedPreference.positionAvailable !== true)) throw Error('Saved position cannot be safely preserved');
        const position = observedPreference.state === 'unset' ? null : observedPreference.position;
        if (!validPosition(position)) throw Error('Invalid saved position');
        const body = {requestId:crypto.randomUUID(), expectedRevision, mode:choice.mode, position};
        if (descriptionDirty) body.descriptionEnabled = description.checked;
        if (captionsDirty) body.captionMode = captions.value;
        if (Object.hasOwn(body, 'captionMode') && !['off','original','translated','both'].includes(body.captionMode)) throw Error('Invalid caption preference');
        const marker = JSON.stringify({version:1, ref:{...ref}, choice:{...currentChoice, mode:choice.mode}, body, editionId});
        journalStarted = true;
        localStorage.setItem(preferenceKey, marker);
        try {
          const dto = await invoke('w25PreferencesPut', body, editionId || null);
          check();
          if (!confirmedPreference(dto, body, choice) || localStorage.getItem(preferenceKey) !== marker) throw Error('Save unconfirmed');
          const result = continuitySnapshot(continuityScope, dto, supportedChoices(dto, currentChoice), {state:'unknown'}, 'unavailable');
          localStorage.removeItem(preferenceKey); observedPreference = dto; displayPreference(dto);
          if (Object.hasOwn(body, 'descriptionEnabled') && description.checked === body.descriptionEnabled) descriptionDirty = false;
          if (Object.hasOwn(body, 'captionMode') && captions.value === body.captionMode) captionsDirty = false;
          return result;
        } catch (error) { if (ticket === generation) showPreferenceRecovery(); throw error; }
        }); } catch (error) {
          if (!journalStarted) throw {kind:'preference-save-not-dispatched', scope:continuityScope, token};
          throw error;
        }
      }};
    continuity.update(continuityHost);
    description.onchange = () => { try { check(); descriptionDirty = true; } catch { description.disabled = captions.disabled = true; } };
    captions.onchange = () => { try { check(); captionsDirty = true; } catch { description.disabled = captions.disabled = true; } };
    try { if (localStorage.getItem(preferenceKey) !== null) showPreferenceRecovery(); } catch { recovery.textContent = 'Safe preference recovery is unavailable.'; }
    const observeDelivery = async (runId, operation, body, ...args) => {
      const value = await invoke(operation, body, ...args); check();
      if (active?.ticket !== ticket || input.value.trim() !== runId) throw Error('Selection changed');
      if (['queued','running','ready','stale','cancelled','unavailable','unknown','full'].includes(value?.state)) {
        const originalRequestId = body?.requestId || (operatingDelivery?.runId === runId ? operatingDelivery.requestId : null);
        operatingDelivery = {ticket:typeof value.ticket === 'string' && /^[0-9a-f]{64}$/.test(value.ticket) ? value.ticket : null, runId, state:value.state,
          requestId:originalRequestId, ref:{...ref}, scopeGeneration:ticket};
        if (typeof originalRequestId === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(originalRequestId)) request.value = originalRequestId;
      }
      return value;
    };
    const bind = (g = null, policyRevision = null) => { operatingDelivery = null; component.update({scopeGeneration:ticket, sessionId:scope.sessionId, actorId:scope.viewerId || scope.actorBinding,
      sourceId:ref.sourceId, sourceRevision:ref.sourceRevision, sourceRef:{...ref}, profileGeneration:ticket, rightsGeneration:ticket,
      createRequestId:() => crypto.randomUUID(), listProfiles:() => invoke('w23Profiles', null),
      getSelection:() => invoke('w23SelectionGet', null), selectProfile:body => invoke('w23SelectionPut', body),
      getOperation:id => invoke('w23ProfileOperation', null, id),
      ...(g ? {generation:g, policyRevision, playerScope:scope,
        prepareGeneration:body => invoke('w23GenerationPrepare', body),
        getGeneration:(runId, requestId) => invoke('w23GenerationGet', null, runId, requestId),
        admitDelivery:body => observeDelivery(g.runId, 'w20DeliveryAdmit', body),
        lookupDeliveryReceipt:body => observeDelivery(g.runId, 'w20DeliveryReceipt', body),
        viewDelivery:id => observeDelivery(g.runId, 'w20DeliveryView', null, id),
        audioAuthority:{playReady:(result, selection, playerScope, guard) => phase12Controller.playDelivery(result, playerScope, guard), stopPlayback:() => phase12Controller?.stopDelivery()}
      } : {})}); };
    active.bind = bind; active.current = current;
    qualityChoice.update({scope, ref, check, invoke, sameRef:sameMomentRef}); savedTranslations.reset(); visualAssociations.reset();
    active.playPrepared = async () => {
      const runId = input.value.trim(), requestId = request.value.trim();
      if (!/^[A-Za-z0-9._:-]{1,128}$/.test(runId) || !/^[A-Za-z0-9._:-]{1,128}$/.test(requestId)) throw Error('Existing run and request required');
      const unchanged = () => { check(); if (input.value.trim() !== runId || request.value.trim() !== requestId) throw Error('Request changed'); };
      const read = async () => {
        await current(); unchanged();
        const ready = await API.call('w25ListeningPreload', {runId, requestId}, {scope}); unchanged();
        if (ready?.state !== 'ready' || ready.binding?.runId !== runId || ready.binding?.requestId !== requestId || !/^[a-f0-9]{64}$/.test(ready.audioSha256 || '')) throw Error('Prepared audio unavailable');
        const response = await fetch(`/api/sessions/${encodeURIComponent(scope.sessionId)}/w25/listening/media`, {method:'POST', credentials:'same-origin', cache:'no-store', headers:{Authorization:`Bearer ${scope.token}`, 'Content-Type':'application/json', Accept:'audio/wav'}, body:JSON.stringify({runId, requestId}), signal:AbortSignal.timeout(30000)});
        unchanged(); if (!response.ok || response.headers.get('content-type') !== 'audio/wav') throw Error('Prepared audio unavailable');
        const bytes = new Uint8Array(await response.arrayBuffer()); unchanged();
        if (bytes.length < 44 || bytes.length > 6 * 1024 * 1024 || String.fromCharCode(...bytes.subarray(0, 4)) !== 'RIFF' || String.fromCharCode(...bytes.subarray(8, 12)) !== 'WAVE') throw Error('Prepared audio unavailable');
        const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
        await current(); unchanged(); if (hash !== ready.audioSha256) throw Error('Prepared audio changed');
        return {bytes, hash};
      };
      const initial = await read(); let binary = '';
      for (let i = 0; i < initial.bytes.length; i += 32768) binary += String.fromCharCode(...initial.bytes.subarray(i, i + 32768));
      await phase12Controller.playDelivery({audioBase64:btoa(binary), audioSha256:initial.hash}, scope, async hash => { const latest = await read(); if (latest.hash !== hash) throw Error('Prepared audio changed'); });
      unchanged();
    };
    meaningRecovery.replaceChildren();
    if (state.role === 'viewer') { try { assertSavedIdentity(scope); if (!scope.viewerId || !scope.actorBinding || !scope.sessionId) throw Error('Viewer binding unavailable'); if (localStorage.getItem(`entrelineas.w26.meaning.v1:${scope.sessionId}:${scope.actorBinding}`) !== null) showMeaningRecovery(active); } catch { meaningRecovery.textContent = 'Safe private note recovery is unavailable.'; } }
    bind();
  }
  operatingButton.addEventListener('click', async () => {
    const owner = active; if (!owner) return;
    operating?.destroy(); operating = null; operatingButton.disabled = true;
    operatingMessage.textContent = 'Checking current access and status…';
    const runId = input.value.trim(), requestId = request.value.trim();
    const paired = /^[A-Za-z0-9._:-]{1,128}$/.test(runId) && /^[A-Za-z0-9._:-]{1,128}$/.test(requestId);
    const observedDelivery = operatingDelivery, delivery = observedDelivery?.runId === runId && observedDelivery.requestId === requestId && observedDelivery.scopeGeneration === owner.ticket && sameMomentRef(observedDelivery.ref, owner.ref) ? observedDelivery : null;
    const check = () => { assertSavedIdentity(owner.scope); if (active !== owner || operatingDelivery !== observedDelivery || sourceContextStale || sourceMutationPending || input.value.trim() !== runId || request.value.trim() !== requestId || !normalizeList(state.context?.sources || state.context).some(x => x.id === owner.ref.sourceId && x.revision === owner.ref.sourceRevision && x.status === 'active' && x.audienceVisible === true)) throw Error('Selection changed'); };
    const body = {ref:{...owner.ref}, ...(typeof delivery?.ticket === 'string' && /^[0-9a-f]{64}$/.test(delivery.ticket) ? {ticket:delivery.ticket} : {}), ...(paired ? {runId, requestId} : {})};
    try {
      const proof = await verifyResumeAccess({sessionId:owner.scope.sessionId, credential:owner.scope.token}); check();
      if (proof.role !== owner.scope.role || (proof.role === 'viewer' && proof.actorId !== owner.scope.viewerId)) throw Error('Identity changed');
      const snapshot = await owner.invoke('w29OperatingStatus', body); check();
      const s = snapshot?.scope;
      if (s?.actorId !== proof.actorId || s.sessionId !== owner.scope.sessionId || s.role !== (proof.role === 'creator' ? 'operator' : 'audience') || s.sourceId !== owner.ref.sourceId || s.sourceRevision !== owner.ref.sourceRevision) throw Error('Scope changed');
      const assertScope = value => { check(); if (JSON.stringify(value) !== JSON.stringify(s)) throw Error('Scope changed'); };
      const read = async () => { check(); const next = await owner.invoke('w29OperatingStatus', body); check(); if (next?.access !== 'current' || JSON.stringify(next.scope) !== JSON.stringify(s)) throw Error('Rights changed'); return next; };
      operating = mountOperatingConnected(operatingRoot, {scope:s, snapshot, assertScope, statusOperation:'w29OperatingStatus', request:read, ...qualityChoice.bindings(),
        authorize:(_scope, action, target) => (action === 'read_receipt' && paired && target?.receiptId === requestId) || (action === 'inspect_source' && target?.sourceId === owner.ref.sourceId && target?.sourceRevision === owner.ref.sourceRevision) || (action === 'choose_profile' && snapshot.profiles?.some(p => p.profileId === target?.profileId && p.revision === target?.revision && p.approved === true && p.supported === true)),
        readReceipt:async id => { if (!paired || id !== requestId) throw Error('Receipt changed'); const receipt = await owner.invoke('w25ListeningPreload', {runId, requestId}); check(); if (receipt?.state !== 'ready' || receipt.binding?.runId !== runId || receipt.binding?.requestId !== requestId) throw Error('Receipt unavailable'); return read(); },
        playPreparedAudio:async id => { if (!paired || id !== requestId) throw Error('Receipt changed'); check(); await owner.playPrepared(); check(); },
        selectExistingProfile:async (profile, captured) => {
          assertScope(captured);
          const fresh = await read(); assertScope(captured);
          if (fresh?.effect === 'unknown' || !fresh?.profiles?.some(p => p.profileId === profile.profileId && p.revision === profile.revision && p.approved === true && p.supported === true)) throw Error('Profile unavailable');
          const result = await component.selectExactProfile(profile);
          assertScope(captured);
          if (result?.state !== 'confirmed') throw Error('Profile selection not confirmed');
          return read();
        },
        inspectCurrentSource:() => { check(); void openWave15Moment(owner.ref, owner.scope, check); }});
      operatingMessage.textContent = `Current status checked.${delivery ? ` Last delivery response: ${delivery.state}. ${delivery.state === 'full' ? 'The queue was full; no admitted ticket was confirmed. Review before making another explicit request.' : delivery.state === 'unknown' ? 'The outcome is unknown; check its original receipt before another request.' : ''}` : ''}`;
    } catch { if (active === owner) operatingMessage.textContent = 'Current status or access is unavailable. Select a current moment and try again.'; }
    finally { if (active === owner) operatingButton.disabled = false; }
  });
  meaningLanguage.addEventListener('change', () => { savedTranslations.reset(); visualAssociations.reset(); ++meaningLanguageGeneration; ++accessibilityGeneration; meaningSelection = null; meaning.invalidate(); accessibilityContext = null; accessibility.reset(); meaningStatus.textContent = ''; });
  momentAccessibilityOpen.addEventListener('click', async () => {
    const owner = active; if (!owner) return;
    const requestGeneration = ++accessibilityGeneration;
    accessibilityContext = null; accessibility.reset(); momentAccessibilityOpen.disabled = true;
    try {
      const timeline = await owner.invoke('p10Timeline', null, owner.ref.sourceId);
      const moment = timeline?.moments?.find(item => sameMomentRef(item.ref, owner.ref));
      if (active !== owner || requestGeneration !== accessibilityGeneration || !moment || typeof moment.text !== 'string') throw Error('Moment unavailable');
      accessibilityContext = owner.accessibilityContext({}, null);
      accessibilityContext.returnButton = momentAccessibilityOpen;
      await accessibility.update(accessibilityContext, {kind:'moment', captions:[{kind:'original', text:moment.text}]});
    } catch { if (active === owner && requestGeneration === accessibilityGeneration) { accessibilityContext = null; accessibility.reset(); message.textContent = 'Accessibility or current moment access is unavailable.'; } }
    finally { if (active === owner) momentAccessibilityOpen.disabled = false; }
  });
  accessibilityOpen.addEventListener('click', async () => {
    const owner = active, id = edition.value.trim(), language = meaningLanguage.value;
    if (!owner || !id || !['en','es'].includes(language)) { message.textContent = 'Select a moment and enter an approved edition ID.'; return; }
    const requestGeneration = ++accessibilityGeneration;
    accessibilityContext = null; accessibility.reset(); accessibilityOpen.disabled = true;
    try {
      const result = await owner.invoke('w22Edition', null, id, language); const manifest = result.edition;
      if (active !== owner || requestGeneration !== accessibilityGeneration || edition.value.trim() !== id || manifest?.approval !== 'approved' || manifest.editionId !== id || !Array.isArray(manifest.tracks)) throw Error('Edition changed');
      const captions = manifest.tracks.filter(t => ['original','translation'].includes(t.kind)).flatMap(t => (t.cues || []).filter(c => sameMomentRef(c.sourceRef, owner.ref)).map(c => ({kind:t.kind === 'translation' ? 'translated' : 'original', language:t.language, text:c.text})));
      accessibilityContext = owner.accessibilityContext(manifest, language);
      await accessibility.update(accessibilityContext, {kind:'edition', approval:manifest.approval, editionId:id, captions, description:manifest.descriptionAudio});
    } catch { if (active === owner && requestGeneration === accessibilityGeneration) { accessibilityContext = null; accessibility.reset(); message.textContent = 'Accessibility or current edition access is unavailable.'; } }
    finally { if (active === owner) accessibilityOpen.disabled = false; }
  });
  playPrepared.addEventListener('click', async () => {
    const owner = active; if (!owner) { message.textContent = 'Select a current moment first.'; return; }
    playPrepared.disabled = true; message.textContent = 'Checking prepared audio and current access…';
    try { await owner.playPrepared(); if (active === owner) message.textContent = 'Prepared audio playback finished.'; }
    catch { if (active === owner) message.textContent = 'Prepared audio is unavailable or access changed.'; }
    finally { if (active === owner) playPrepared.disabled = false; }
  });
  meaningOpen.addEventListener('click', async () => {
    const owner = active, language = meaningLanguage.value, languageGeneration = meaningLanguageGeneration;
    if (!owner || !['en', 'es'].includes(language)) return;
    meaningSelection = null; meaning.invalidate(); meaningOpen.disabled = true; meaningStatus.textContent = 'Checking current source access…';
    try {
      await owner.current();
      assertSavedIdentity(owner.scope);
      const translationRequestId = savedTranslations.selected(), visual = visualAssociations.selected();
      const result = await API.call('w26MeaningInspect', {ref:owner.ref, targetLanguage:language, ...(translationRequestId ? {translationRequestId} : {}), ...(visual ? {associationId:visual.associationId} : {})}, {scope:owner.scope});
      await owner.current(); assertSavedIdentity(owner.scope);
      if (active !== owner || meaningLanguage.value !== language || languageGeneration !== meaningLanguageGeneration) throw Error('Selection changed');
      const selected = {ref:{...owner.ref}, result, ticket:owner.ticket, associationId:visual?.associationId};
      meaningSelection = selected; meaning.setScope(selected); meaningStatus.textContent = '';
    } catch { if (active === owner) meaningStatus.textContent = 'Inspection unavailable or access changed.'; }
    finally { if (active === owner) meaningOpen.disabled = false; }
  });
  input.addEventListener('input', () => { const owner = active; loaded = null; segment.replaceChildren(); if (owner) select(owner.ref, owner.scope); message.textContent = 'Load the run again after changing its ID.'; });
  edition.addEventListener('input', () => { const owner = active; if (owner) select(owner.ref, owner.scope); });
  request.addEventListener('input', () => { const owner = active; if (owner) select(owner.ref, owner.scope); });
  open.addEventListener('click', async () => {
    const owner = active, runId = input.value.trim(); loaded = null; segment.replaceChildren();
    if (!owner || !/^[A-Za-z0-9._:-]{1,128}$/.test(runId)) { message.textContent = 'Select a moment and enter a valid private run ID.'; return; }
    open.disabled = true;
    try {
      await owner.current(); assertSavedIdentity(owner.scope); const result = await API.call('w21SpeechRun', null, runId, {scope:owner.scope}); await owner.current(); assertSavedIdentity(owner.scope);
      if (active !== owner || input.value.trim() !== runId || result?.runId !== runId || !result.state?.segments) throw Error('Run changed');
      const finals = Object.values(result.state.segments).filter(Array.isArray).map(h => h.at(-1)).filter(e => e?.state === 'final' && typeof e.segmentId === 'string' && Number.isSafeInteger(e.revision));
      loaded = {runId, finals}; for (const e of finals) segment.append(new Option(`Revision ${e.revision} · ${e.interval?.startMs}–${e.interval?.endMs} ms`, e.segmentId));
      message.textContent = finals.length ? 'Choose a final segment. The server checks that it belongs to the selected moment.' : 'This run has no final segments.';
    } catch { if (active === owner) message.textContent = 'Run unavailable or current access changed.'; }
    finally { if (active === owner) open.disabled = false; }
  });
  use.addEventListener('click', async () => {
    const owner = active, selection = loaded, chosen = selection?.finals.find(e => e.segmentId === segment.value);
    if (!owner || !chosen || input.value.trim() !== selection.runId) { message.textContent = 'Load and select a final segment first.'; return; }
    use.disabled = true;
    try {
      await owner.current(); assertSavedIdentity(owner.scope); const data = await API.call('w20DeliverySources', null, {scope:owner.scope}); await owner.current(); assertSavedIdentity(owner.scope);
      if (active !== owner || loaded !== selection || input.value.trim() !== selection.runId || segment.value !== chosen.segmentId || !Number.isSafeInteger(data?.policyRevision)) throw Error('Selection changed');
      owner.bind({runId:selection.runId, segmentId:chosen.segmentId, expectedRevision:chosen.revision, outputFormat:'audio/wav'}, data.policyRevision);
      message.textContent = 'Segment selected. Load or restore a profile, then prepare listening.';
    } catch { if (active === owner) message.textContent = 'Current delivery policy or access is unavailable.'; }
    finally { if (active === owner) use.disabled = false; }
  });
  segment.addEventListener('change', () => { if (active) active.bind(); message.textContent = 'Use the selected segment to confirm it.'; });
  function useRun(runId, scope) {
    assertIdentity(scope);
    if (!active || !/^[A-Za-z0-9._:-]{1,128}$/.test(runId)) throw Error('Select a current moment');
    assertIdentity(active.scope);
    input.value = runId;
    input.dispatchEvent(new Event('input'));
    navTo('audience'); root.scrollIntoView(); open.focus();
    message.textContent = 'Run selected. Load its final segments; the server checks the selected moment.';
  }
  return {reset, select, useRun};
})();
// Reviewed setup uses the same pack operation lock and journal as the existing pack UI.
const wave28Setup = (() => {
  const style = document.createElement('link'); style.rel = 'stylesheet'; style.href = new URL('./waves28-segment-setup.css', import.meta.url).href; document.head.append(style);
  const container = document.createElement('section'), fields = document.createElement('div');
  const panel = document.createElement('div'), notice = document.createElement('p'), recovery = document.createElement('button');
  container.append(fields, notice, recovery, panel); $('#wave24Pack').insertAdjacentElement('afterend', container);
  notice.setAttribute('role', 'status'); recovery.type = 'button'; recovery.textContent = 'Check earlier setup import';
  const inputs = {};
  for (const [key, label] of [['packId','Target pack ID'],['expectedRevision','Target revision'],['sourcePackId','Source pack ID'],['sourceRevision','Source revision']]) {
    const wrapper = document.createElement('label'), input = document.createElement('input');
    wrapper.textContent = label + ' '; input.name = key; if (key.endsWith('Revision')) { input.type = 'number'; input.min = '1'; }
    wrapper.append(input); fields.append(wrapper); inputs[key] = input;
  }
  let component = mountSetup28(panel, {}); let generation = 0, owner = '';
  const selected = () => ({packId:inputs.packId.value.trim(), expectedRevision:Number(inputs.expectedRevision.value), sourcePackId:inputs.sourcePackId.value.trim(), sourceRevision:Number(inputs.sourceRevision.value)});
  function reset() {
    const scope = identityScope(), ticket = ++generation;
    const nextOwner = JSON.stringify([scope.sessionId, scope.actorBinding, scope.role]);
    if (owner !== nextOwner) { for (const input of Object.values(inputs)) input.value = ''; owner = nextOwner; }
    const key = `entrelineas.w24.pack.v1:${scope.sessionId}:${scope.actorBinding}`;
    const check = () => { assertSavedIdentity(scope); if (ticket !== generation || scope.role !== 'creator') throw Error('Setup access changed'); };
    const invoke = async (name, body, id) => { check(); const result = await API.call(name, body, id, {scope}); check(); return result; };
    const lock = fn => { if (!navigator.locks?.request) throw Error('Safe recovery unavailable'); return navigator.locks.request(key, fn); };
    const recover = async requestId => lock(async () => {
      check(); const raw = localStorage.getItem(key); let marker;
      try { marker = JSON.parse(raw); } catch { throw Error('Invalid original request'); }
      if (!marker || marker.version !== 1 || marker.kind !== 'setup28' || marker.request?.requestId !== requestId) throw Error('Original setup request unavailable');
      const result = await invoke('w24PackOperation', null, requestId);
      if (result?.operation?.requestId !== requestId || result.operation.state !== 'committed' || result.packId !== marker.request.packId || !Number.isSafeInteger(result.revision) || result.revision <= marker.request.expectedRevision || !Number.isSafeInteger(result.currentRevision) || result.currentRevision < result.revision || localStorage.getItem(key) !== raw) throw Error('Unconfirmed receipt');
      localStorage.removeItem(key); return result;
    });
    recovery.onclick = async () => {
      recovery.disabled = true;
      try { check(); const marker = JSON.parse(localStorage.getItem(key)); if (marker?.kind !== 'setup28') throw Error('No setup request'); await recover(marker.request.requestId); component.destroy(); component = mountSetup28(panel, {}); reset(); notice.textContent = 'Original setup import confirmed. Reload the target pack for current references.'; }
      catch { if (ticket === generation) notice.textContent = 'Original setup import unavailable or unconfirmed; recovery information remains saved.'; }
      finally { if (ticket === generation) recovery.disabled = false; }
    };
    if (tabOnlyAccess || !scope.sessionId || !scope.actorBinding || scope.role !== 'creator') { component.update({}); notice.textContent = 'Saved creator access is required for reviewed setup.'; return; }
    notice.textContent = 'Choose exact current pack revisions. An earlier unconfirmed pack operation must be recovered first.';
    const context = {authority:{scope:String(ticket), session:scope.sessionId, actor:scope.actorBinding, source:String(ticket)}, ...selected(),
      previewSetup: body => invoke('w28SetupPreview', body),
      importSetup: body => lock(async () => {
        check(); if (localStorage.getItem(key) !== null) throw Error('Earlier pack operation unconfirmed');
        const raw = JSON.stringify({version:1, kind:'setup28', request:body}); localStorage.setItem(key, raw);
        const result = await invoke('w28SetupImport', body);
        if (result?.operation?.requestId !== body.requestId || result.operation.state !== 'committed' || result.packId !== body.packId || !Number.isSafeInteger(result.revision) || result.revision <= body.expectedRevision || !Number.isSafeInteger(result.currentRevision) || result.currentRevision < result.revision || result.freshReviewRequired !== true || result.activated !== false || localStorage.getItem(key) !== raw) throw Error('Unconfirmed import');
        localStorage.removeItem(key); return result;
      }),
      recoverSetup: ({requestId}) => recover(requestId)
    };
    component.update(context);
  }
  for (const input of Object.values(inputs)) input.addEventListener('input', reset);
  reset(); return {reset};
})();
// Pack actions retain only their original request identifier until confirmed.
const wave24Pack = (() => {
  const component = mountPack24($('#wave24Pack'), {});
  let generation = 0, recoveryBox = null, channelRecoveryBox = null, profileNotice = null;
  function reset() {
    recoveryBox?.remove(); recoveryBox = null;
    channelRecoveryBox?.remove(); channelRecoveryBox = null;
    profileNotice?.remove(); profileNotice = null;
    const scope = identityScope(), ticket = ++generation;
    if (tabOnlyAccess || !scope.sessionId || !scope.token || !scope.actorBinding) { component.update({}); return; }
    const check = () => { assertSavedIdentity(scope); if (ticket !== generation) throw new DOMException('Context changed', 'AbortError'); };
    const invoke = async (name, body, id) => { check(); const result = await API.call(name, body, id, {scope}); check(); return result; };
    const key = `entrelineas.w24.pack.v1:${scope.sessionId}:${scope.actorBinding}`;
    const channelKey = `entrelineas.w24.channel.v1:${scope.sessionId}:${scope.actorBinding}`;
    const profileKey = `entrelineas.w24.pack-profile.v1:${scope.sessionId}:${scope.actorBinding}`;
    let pendingProfile = null;
    const sameValue = (a, b) => {
      if (a === b) return true;
      if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
      const keys = Object.keys(a).sort(), other = Object.keys(b).sort();
      return keys.length === other.length && keys.every((key, i) => key === other[i] && sameValue(a[key], b[key]));
    };
    function showProfileRecovery() {
      if (profileNotice) return;
      const box = document.createElement('section'), message = document.createElement('p'), button = document.createElement('button');
      message.setAttribute('role', 'status');
      message.textContent = 'An earlier profile selection is unconfirmed. Check its original receipt before selecting again.';
      button.type = 'button'; button.textContent = 'Check earlier profile selection';
      button.onclick = async () => {
        if (!navigator.locks?.request) { message.textContent = 'Safe recovery is unavailable; the original request remains saved.'; return; }
        button.disabled = true;
        try {
          const result = await navigator.locks.request(profileKey, async () => {
            check(); const raw = localStorage.getItem(profileKey); let marker;
            try { marker = JSON.parse(raw); } catch { throw Error('Invalid marker'); }
            if (!marker || marker.version !== 1 || typeof marker.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(marker.requestId)) throw Error('Invalid marker');
            const receipt = await invoke('w24PackProfileReceipt', null, marker.requestId);
            check();
            const selected = receipt?.selection;
            if (receipt?.operation?.requestId !== marker.requestId || receipt.operation.state !== 'committed' || !selected || typeof receipt.current !== 'boolean' || localStorage.getItem(profileKey) !== raw) throw Error('Unconfirmed receipt');
            if (pendingProfile && (selected.packId !== pendingProfile.packId || !sameValue(selected.item, pendingProfile.item) || !sameValue(selected.ref, pendingProfile.ref))) throw Error('Selection mismatch');
            localStorage.removeItem(profileKey); pendingProfile = null; return receipt;
          });
          check(); reset();
          profileNotice = document.createElement('p'); profileNotice.setAttribute('role', 'status');
          profileNotice.textContent = result.current ? 'The earlier selection was confirmed. Refresh the current profile selection to view it.' : 'The earlier selection was confirmed but has since been superseded. Refresh the current profile selection.';
          $('#wave24Pack').insertAdjacentElement('afterend', profileNotice);
        } catch (_) { if (ticket === generation) { message.textContent = 'The original selection could not be confirmed. Its request remains saved; check access and try again.'; button.disabled = false; } }
      };
      box.append(message, button); profileNotice = box; $('#wave24Pack').insertAdjacentElement('afterend', box);
    }
    const recover = async requestId => {
      if (!navigator.locks) throw Error('Safe action recovery unavailable');
      return navigator.locks.request(key, async () => {
        check(); const raw = localStorage.getItem(key); let marker;
        try { marker = JSON.parse(raw); } catch { throw Error('Invalid action marker'); }
        if (!marker || marker.version !== 1 || marker.requestId !== requestId) throw Error('Original request required');
        const result = await invoke('w24PackOperation', null, requestId);
        check();
        if (result?.operation?.requestId !== requestId || result.operation.state !== 'committed' || localStorage.getItem(key) !== raw) throw Error('Unconfirmed receipt');
        localStorage.removeItem(key); return result;
      });
    };
    const creator = scope.role === 'creator' ? {
      previewPack: body => invoke('w24PackPreview', body),
      mutatePack: async body => {
        if (!navigator.locks || typeof body?.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(body.requestId)) throw Error('Safe action recovery unavailable');
        return navigator.locks.request(key, async () => {
          check(); if (localStorage.getItem(key) !== null) throw Error('Previous action unconfirmed');
          const marker = JSON.stringify({version:1, requestId:body.requestId});
          localStorage.setItem(key, marker);
          try {
            const result = await invoke('w24PackMutate', body);
            check();
            if (result?.operation?.requestId !== body.requestId || result.operation.state !== 'committed' || localStorage.getItem(key) !== marker) throw Error('Unconfirmed result');
            localStorage.removeItem(key); return result;
          } catch (error) {
            if (['stale_revision','invalid_request','invalid_item','unsupported_item','expired','request_conflict','conflict'].includes(error?.code)) {
              try { check(); if (localStorage.getItem(key) === marker) localStorage.removeItem(key); } catch { /* preserve the original marker after an identity change */ }
            }
            throw error;
          }
        });
      },
      recoverPackOperation: ({requestId}) => recover(requestId)
    } : {};
    async function recoverChannel(requestId) {
      if (!navigator.locks) throw Error('Safe action recovery unavailable');
      return navigator.locks.request(channelKey, async () => {
        check(); const raw = localStorage.getItem(channelKey); let marker;
        try { marker = JSON.parse(raw); } catch { throw Error('Invalid action marker'); }
        if (!marker || marker.version !== 1 || marker.requestId !== requestId) throw Error('Original request required');
        const result = await invoke('w24ChannelOperation', null, requestId);
        check();
        if (result?.requestId !== requestId || result.state !== 'committed' || localStorage.getItem(channelKey) !== raw) throw Error('Unconfirmed receipt');
        localStorage.removeItem(channelKey); return result;
      });
    }
    if (scope.role === 'creator') {
      creator.mutateChannel = async ({route, body}) => {
        if (!navigator.locks || !['capabilities','membership','source-grants','pack-grants'].includes(route) || typeof body?.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(body.requestId)) throw Error('Safe action recovery unavailable');
        return navigator.locks.request(channelKey, async () => {
          check(); if (localStorage.getItem(channelKey) !== null) throw Error('Previous action unconfirmed');
          const marker = JSON.stringify({version:1,requestId:body.requestId}); localStorage.setItem(channelKey, marker);
          try {
            const result = await invoke('w24ChannelMutate', body, route);
            check();
            if (result?.requestId !== body.requestId || result.state !== 'committed' || localStorage.getItem(channelKey) !== marker) throw Error('Unconfirmed result');
            localStorage.removeItem(channelKey); return result;
          } catch (error) {
            if (['invalid_request','not_found','stale_revision','request_conflict','forbidden'].includes(error?.code)) {
              try { check(); if (localStorage.getItem(channelKey) === marker) localStorage.removeItem(channelKey); } catch { /* preserve the original marker after an identity change */ }
            }
            throw error;
          }
        });
      };
      creator.recoverChannelOperation = ({requestId}) => recoverChannel(requestId);
    }
    component.update({authority:{scope:String(ticket),session:scope.sessionId,actor:scope.actorBinding,source:String(ticket),profile:String(ticket)},
      readPack: ({packId}) => invoke('w24PackRead', null, packId),
      readPackProfileSelection: () => invoke('w24PackProfileSelection', null),
      selectPackProfile: async body => {
        if (!navigator.locks || typeof body?.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(body.requestId)) throw Error('Safe action recovery unavailable');
        return navigator.locks.request(profileKey, async () => {
          check(); if (localStorage.getItem(profileKey) !== null) throw Error('Previous selection unconfirmed');
          profileNotice?.remove(); profileNotice = null;
          const marker = JSON.stringify({version:1, requestId:body.requestId});
          localStorage.setItem(profileKey, marker); pendingProfile = body;
          try {
            const result = await invoke('w24PackProfileSelect', body);
            check();
            const selected = result?.selection;
            if (!selected || selected.packId !== body.packId || !sameValue(selected.item, body.item) || !sameValue(selected.ref, body.ref) || localStorage.getItem(profileKey) !== marker) throw Error('Unconfirmed selection');
            localStorage.removeItem(profileKey); pendingProfile = null; return result;
          } catch (_) { if (ticket === generation) showProfileRecovery(); throw Error('Selection unconfirmed'); }
        });
      },
      openSource: async item => {
        const ref = item?.ref;
        if (item?.kind === 'activity') {
          await wave24Activities.openReference(ref, item.revision, scope); check(); return;
        }
        if (item?.kind !== 'source' || !ref || ref.sessionId !== scope.sessionId || typeof ref.sourceId !== 'string' || typeof ref.momentId !== 'string') throw Error('Reference cannot be opened here');
        await refreshSources(scope); check();
        const source = normalizeList(state.context?.sources || state.context).find(x => x.id === ref.sourceId && x.revision === ref.sourceRevision && x.status === 'active' && x.audienceVisible === true);
        if (!source) throw Error('Source unavailable');
        const timeline = await API.call('p10Timeline', null, ref.sourceId, {scope}); check();
        if (!Array.isArray(timeline.moments) || !timeline.moments.some(x => ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(k => x.ref?.[k] === ref[k]))) throw Error('Moment unavailable');
        wave23Listening.select(ref, scope); $('#questionSource').value = ref.sourceId;
        $('#questionMoment').value = `${Math.floor(ref.startMs / 60000)}:${String(Math.floor(ref.startMs / 1000) % 60).padStart(2, '0')}`;
        navTo('audience'); $('#question').focus();
      },
      ...creator});
    if (localStorage.getItem(profileKey) !== null) showProfileRecovery();
    if (scope.role === 'creator' && localStorage.getItem(key) !== null) {
      const box = document.createElement('section'), message = document.createElement('p'), button = document.createElement('button');
      message.setAttribute('role', 'status'); message.textContent = 'An earlier pack action is unconfirmed. Check its original receipt before making another change.';
      button.type = 'button'; button.textContent = 'Check earlier pack action';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { check(); const marker = JSON.parse(localStorage.getItem(key)); await recover(marker?.requestId); check(); message.textContent = 'The earlier pack action was confirmed. Reload the pack for current references.'; button.remove(); }
        catch { try { check(); message.textContent = 'The action remains unconfirmed. Its original request is preserved.'; button.disabled = false; } catch {} }
      });
      box.append(message, button); $('#wave24Pack').insertAdjacentElement('afterend', box); recoveryBox = box;
    }
    if (scope.role === 'creator' && localStorage.getItem(channelKey) !== null) {
      const box = document.createElement('section'), message = document.createElement('p'), button = document.createElement('button');
      message.setAttribute('role', 'status'); message.textContent = 'An earlier channel action is unconfirmed. Check its original receipt before another channel action.';
      button.type = 'button'; button.textContent = 'Check earlier channel action';
      button.addEventListener('click', async () => {
        button.disabled = true;
        try { check(); const marker = JSON.parse(localStorage.getItem(channelKey)); await recoverChannel(marker?.requestId); check(); message.textContent = 'The earlier channel action was confirmed. A lost one-time capability requires an intentional rotation.'; button.remove(); }
        catch { try { check(); message.textContent = 'The channel action remains unconfirmed. Its original request is preserved.'; button.disabled = false; } catch {} }
      });
      box.append(message, button); $('#wave24Pack').insertAdjacentElement('afterend', box); channelRecoveryBox = box;
    }
  }
  return {reset};
})();
// Activity demonstrations use current authenticated access and do not create attempts.
const wave24Activities = (() => {
  const component = mountActivities24($('#wave24Activities'), {});
  let generation = 0, recoveryBoxes = [], expectedReference = null, selectedActivity = null;
  function reset() {
    expectedReference = null; selectedActivity = null;
    recoveryBoxes.forEach(box => box.remove()); recoveryBoxes = [];
    const scope = identityScope(), ticket = ++generation;
    if (!scope.sessionId || !scope.token || !scope.actorBinding) { component.update({}); return; }
    const check = () => { assertIdentity(scope); if (ticket !== generation) throw new DOMException('Context changed', 'AbortError'); };
    const invoke = async (name, body, id) => { check(); const value = await API.call(name, body, id, {scope}); check(); return value; };
    if (tabOnlyAccess) {
      component.update({scopeId:String(ticket), sessionId:scope.sessionId, actorId:scope.actorBinding,
        ...(['creator', 'viewer'].includes(scope.role) ? {readActivityRecord:id => invoke('w24ActivityRecordRead', null, id)} : {})});
      return;
    }
    const savedCheck = () => { check(); assertSavedIdentity(scope); };
    const key = `entrelineas.w24.activity.v1:${scope.sessionId}:${scope.actorBinding}`;
    const recordKey = `entrelineas.w24.activity-record.v1:${scope.sessionId}:${scope.actorBinding}`;
    const reasonKey = `entrelineas.w24.activity-reason.v1:${scope.sessionId}:${scope.actorBinding}`;
    const reasonAction = async (name, body) => {
      if (!navigator.locks) throw Error('Safe action recovery unavailable');
      return navigator.locks.request(reasonKey, async () => {
        savedCheck();
        const marker = JSON.stringify({version:1, name, body});
        const pending = localStorage.getItem(reasonKey);
        if (pending !== null && pending !== marker) throw Error('Restore the exact earlier reason action before changing it.');
        if (pending === null) localStorage.setItem(reasonKey, marker);
        const result = await invoke(name, body);
        savedCheck();
        if (result.linked !== (name === 'w24ActivityReasonLink') || result.reasonId !== body.reasonId || localStorage.getItem(reasonKey) !== marker) throw Error('Unconfirmed result');
        localStorage.removeItem(reasonKey); return result;
      });
    };
    const recordAction = async (name, body, id) => {
      if (!navigator.locks) throw Error('Safe action recovery unavailable');
      if (typeof body?.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(body.requestId)) throw Error('Enter a valid request ID');
      return navigator.locks.request(recordKey, async () => {
        savedCheck(); if (localStorage.getItem(recordKey) !== null) throw Error('Previous record action unconfirmed');
        const marker = JSON.stringify({version:1, requestId:body.requestId});
        localStorage.setItem(recordKey, marker);
        const result = await invoke(name, body, id);
        savedCheck();
        if (result.operation?.requestId !== body.requestId || result.operation?.state !== 'committed' || localStorage.getItem(recordKey) !== marker) throw Error('Unconfirmed result');
        localStorage.removeItem(recordKey); return result;
      });
    };
    const recordReceipt = async requestId => {
      if (!navigator.locks) throw Error('Safe action recovery unavailable');
      return navigator.locks.request(recordKey, async () => {
        savedCheck(); const raw = localStorage.getItem(recordKey); let pending;
        try { pending = JSON.parse(raw); } catch { throw Error('Invalid pending marker'); }
        if (!pending || pending.version !== 1 || pending.requestId !== requestId) throw Error('Original request required');
        const result = await invoke('w24ActivityRecordOperation', null, requestId);
        savedCheck();
        if (result.operation?.requestId !== requestId || result.operation?.state !== 'committed' || localStorage.getItem(recordKey) !== raw) throw Error('Unconfirmed receipt');
        localStorage.removeItem(recordKey); return result;
      });
    };
    // Share the Wave 22 journal and lock with the existing private-model journey.
    const modelKey = `entrelineas.w22.model-action.v1:${scope.sessionId}:${scope.actorBinding}`;
    const modelCheck = () => { savedCheck(); assertSavedIdentity(scope); };
    const modelLock = fn => {
      if (!navigator.locks) throw Error('Safe action recovery unavailable');
      return navigator.locks.request(modelKey, async () => { modelCheck(); return fn(); });
    };
    const modelReceipts = () => modelLock(async () => {
      const raw = localStorage.getItem(modelKey);
      const data = await invoke('w22ModelReceipts', null); modelCheck();
      if (raw !== null) {
        let pending; try { pending = JSON.parse(raw); } catch { throw Error('Invalid pending marker'); }
        if (!pending || typeof pending.requestId !== 'string' || !['create','evaluate','share','revoke'].includes(pending.action) || !(pending.modelId === null || typeof pending.modelId === 'string')) throw Error('Invalid pending marker');
        if (Array.isArray(data?.receipts) && data.receipts.some(r => r.requestId === pending.requestId && r.action === pending.action && (pending.modelId === null || r.modelId === pending.modelId))) {
          if (localStorage.getItem(modelKey) !== raw) throw Error('Journal changed');
          localStorage.removeItem(modelKey);
        }
      }
      return data;
    });
    const modelCanonical = value => Array.isArray(value) ? value.map(modelCanonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(k => [k, modelCanonical(value[k])])) : value;
    const equalModelDefinition = (a,b) => JSON.stringify(modelCanonical(a)) === JSON.stringify(modelCanonical(b));
    const modelAction = body => modelLock(async () => {
      if (!body || !['create','evaluate','share','revoke'].includes(body.action) || typeof body.requestId !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(body.requestId) || !Number.isSafeInteger(body.expectedRevision) || body.expectedRevision < 0 || (body.action !== 'create' && (typeof body.modelId !== 'string' || !body.modelId))) throw Error('Enter valid identifiers and revision');
      if (localStorage.getItem(modelKey) !== null) throw Error('Previous model action unconfirmed');
      if (body.action === 'create') {
        const selected = selectedActivity;
        if (!selected || !equalModelDefinition(selected.definition, body.definition)) throw Error('Choose an approved activity first.');
        const [activity, approvals, continuations] = await Promise.all([invoke('w24ActivityRead', null, selected.activityId), invoke('w22ModelApprovals', null), invoke('w20PracticeContinuations', null)]); modelCheck();
        if (selected !== selectedActivity || activity?.activityId !== selected.activityId || activity?.revision !== selected.revision || !equalModelDefinition(activity.definition, selected.definition)) throw Error('Choose the current activity revision.');
        const approved = approvals?.approvals?.some(item => equalModelDefinition(item.definition, body.definition));
        const current = continuations?.continuations?.some(c => c.state === 'current' && c.source && Number.isInteger(c.sourceVersion) && Array.isArray(body.definition?.sourceRefs) && body.definition.sourceRefs.length && body.definition.sourceRefs.every(ref => ref.sessionId === scope.sessionId && ref.sourceId === c.source.id && ref.sourceRevision === c.sourceVersion) && c.newAttempts?.some(a => a.id === body.attemptId));
        if (!approved || !current || body.expectedRevision !== 0) throw Error('Choose a current approved model and matching private attempt.');
      }
      modelCheck();
      const marker = JSON.stringify({requestId:body.requestId, action:body.action, modelId:body.modelId || null});
      localStorage.setItem(modelKey, marker);
      const result = await invoke('w22ModelMutate', body); modelCheck();
      if (result?.operation?.state !== 'committed' || result.operation.requestId !== body.requestId || localStorage.getItem(modelKey) !== marker) throw Error('Unconfirmed model action');
      localStorage.removeItem(modelKey); return result;
    });
    const creator = scope.role === 'creator' ? {
      listModelApprovals:() => invoke('w22ModelApprovals', null),
      listModelShares:() => invoke('w22ModelShares', null),
      listActivityReasons:(id, revision) => { savedCheck(); return API.call('w24ActivityReasons', null, id, revision, {scope}).then(value => { savedCheck(); return value; }); },
      saveActivityRecord:body => recordAction('w24ActivityRecordSave', body),
      withdrawActivityRecord:(id, body) => recordAction('w24ActivityRecordWithdraw', body, id),
      readActivityRecordOperation:recordReceipt,
      mutateActivity:async body => {
        if (!navigator.locks) throw Error('Safe action recovery unavailable');
        const validId = value => typeof value === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(value);
        if (!validId(body?.requestId) || !['create','update','withdraw'].includes(body.action) || !Number.isSafeInteger(body.expectedRevision) || body.expectedRevision < 0 || body.expectedRevision > 2147483647 || (body.action !== 'create' && !validId(body.activityId)) || (body.action !== 'withdraw' && !validId(body.approvalId))) throw Error('Enter valid identifiers and revision');
        return navigator.locks.request(key, async () => {
          savedCheck(); if (localStorage.getItem(key) !== null) throw Error('Previous action unconfirmed');
          const marker = JSON.stringify({version:1,requestId:body.requestId});
          localStorage.setItem(key, marker);
          const result = await invoke('w24ActivityMutate', body);
          savedCheck();
          if (result.operation?.requestId !== body.requestId || result.operation?.state !== 'committed' || localStorage.getItem(key) !== marker) throw Error('Unconfirmed result');
          localStorage.removeItem(key); return result;
        });
      },
      readActivityOperation:async requestId => {
        if (!navigator.locks) throw Error('Safe action recovery unavailable');
        return navigator.locks.request(key, async () => {
          savedCheck(); const raw = localStorage.getItem(key); let pending;
          try { pending = JSON.parse(raw); } catch { throw Error('Invalid pending marker'); }
          if (!pending || pending.version !== 1 || pending.requestId !== requestId) throw Error('Original request required');
          const result = await invoke('w24ActivityOperation', null, requestId);
          savedCheck();
          if (result.operation?.requestId !== requestId || result.operation?.state !== 'committed' || localStorage.getItem(key) !== raw) throw Error('Unconfirmed receipt');
          localStorage.removeItem(key); return result;
        });
      }
    } : {};
    component.update({scopeId:String(ticket), sessionId:scope.sessionId, actorId:scope.actorBinding,
      readActivity:async id => {
        const expected = expectedReference; expectedReference = null;
        const result = await invoke('w24ActivityRead', null, id);
        check();
        if (expected && (id !== expected.id || result?.activityId !== expected.id || result?.revision !== expected.revision)) throw Error('Activity version unavailable');
        selectedActivity = result?.activityId === id && Number.isSafeInteger(result?.revision) ? result : null;
        return result;
      },
      ...(['creator', 'viewer'].includes(scope.role) ? {readActivityRecord:id => invoke('w24ActivityRecordRead', null, id)} : {}),
      demonstrateActivity:(id, body) => invoke('w24ActivityDemonstrate', body, id),
      ...(scope.role === 'viewer' ? {
        linkActivityReason:body => reasonAction('w24ActivityReasonLink', body),
        unlinkActivityReason:body => reasonAction('w24ActivityReasonUnlink', body),
        mutateModel:modelAction,
        readModel:async id => { modelCheck(); const data = await invoke('w22Models', null); modelCheck(); const model = data?.models?.find(item => item.id === id); if (!model) throw Error('Model unavailable'); return model; },
        listOwnedModelShares:() => { modelCheck(); return invoke('w22ModelOwnedShares', null); },
        listModelReceipts:modelReceipts
      } : {}),
      ...creator});
    if (!tabOnlyAccess && scope.role === 'viewer' && localStorage.getItem(reasonKey) !== null) {
      const message = document.createElement('p'); message.setAttribute('role', 'status');
      message.textContent = 'An earlier reason action is unconfirmed. Enter the same activity, reason and revisions and repeat that exact action to recover it.';
      $('#wave24Activities').insertAdjacentElement('afterend', message); recoveryBoxes.push(message);
    }
    if (!tabOnlyAccess && scope.role === 'creator' && localStorage.getItem(recordKey) !== null) {
      const message = document.createElement('p'); message.setAttribute('role', 'status');
      message.textContent = 'An earlier reviewed-record action is unconfirmed. Check its original request ID using the record operation receipt control.';
      $('#wave24Activities').insertAdjacentElement('afterend', message); recoveryBoxes.push(message);
    }
    if (!tabOnlyAccess && scope.role === 'creator' && localStorage.getItem(key) !== null) {
      const box = document.createElement('section'), message = document.createElement('p'), recover = document.createElement('button');
      message.setAttribute('role', 'status');
      message.textContent = 'An earlier activity action is unconfirmed. Check its receipt before making another change.';
      recover.type = 'button'; recover.textContent = 'Check earlier activity action';
      recover.addEventListener('click', async () => {
        recover.disabled = true;
        try {
          savedCheck();
          const pending = JSON.parse(localStorage.getItem(key));
          if (!pending || pending.version !== 1 || typeof pending.requestId !== 'string') throw Error('Invalid pending marker');
          await creator.readActivityOperation(pending.requestId); savedCheck();
          message.textContent = 'The earlier activity action was confirmed. Refresh the activity to see its current state.';
          recover.remove();
        } catch { try { savedCheck(); message.textContent = 'The action is still unconfirmed. Its original request remains saved.'; recover.disabled = false; } catch {} }
      });
      box.append(message, recover); $('#wave24Activities').insertAdjacentElement('afterend', box);
      recoveryBoxes.push(box);
    }
  }
  async function openReference(id, revision, scope) {
    if (typeof id !== 'string' || !/^[A-Za-z0-9._:-]{1,128}$/.test(id) || !Number.isSafeInteger(revision) || revision < 1) throw Error('Invalid activity reference');
    assertIdentity(scope);
    const ticket = generation;
    const activity = await API.call('w24ActivityRead', null, id, {scope});
    assertIdentity(scope);
    if (ticket !== generation || activity?.activityId !== id || activity?.revision !== revision) throw Error('Activity version unavailable');
    navTo(scope.role === 'creator' ? 'studio' : 'audience');
    const root = $('#wave24Activities');
    const label = [...root.querySelectorAll('label')].find(node => node.firstChild?.textContent === 'Approved activity ID');
    const input = label?.querySelector('input');
    const button = [...root.querySelectorAll('button')].find(node => node.textContent === 'Open approved activity');
    if (!input || !button) throw Error('Activity unavailable');
    input.value = id; input.dispatchEvent(new Event('input', {bubbles:true}));
    expectedReference = {id, revision};
    button.click();
    input.focus();
  }
  return {reset, openReference};
})();
// The guide opens existing screens only after rechecking the active session.
const wave24Guide = (() => {
  const component = mountGuide24($('#wave24Guide'), {});
  let generation = 0;
  function reset() {
    const scope = identityScope(), ticket = ++generation;
    const check = () => { assertIdentity(scope); if (ticket !== generation) throw new DOMException('Context changed', 'AbortError'); };
    const current = async () => { check(); await API.call('session', null, {scope}); check(); };
    const viewer = scope.role === 'viewer', creator = scope.role === 'creator';
    const targets = {
      setup: creator && ['studio', '#wave19Setup'], follow: viewer && ['audience', '#wave23Listening'],
      inspect: viewer && ['audience', '#wave23Moments'], question: viewer && ['audience', '#question'],
      edition: viewer && ['audience', '#wave22EditionReader'], coedit: (viewer || creator) && [viewer ? 'audience' : 'studio', viewer ? '#wave22CoeditViewer' : '#wave22Coedit'],
      contribute: viewer && ['audience', '#wave19Entry'], review: creator && ['studio', '#wave19Inbox'],
      present: creator && ['studio', '#wave19Operator'], approved: viewer && ['audience', '#wave22EditionReader'],
      practice: viewer && ['practice', '#practiceTitle']
    };
    const open = async target => {
      await current(); check(); const element = target && $(target[1]);
      if (!element) throw Error('Destination unavailable');
      navTo(target[0]);
      for (let parent = element.parentElement; parent; parent = parent.parentElement) if (parent.tagName === 'DETAILS') parent.open = true;
      element.scrollIntoView();
    };
    component.update({connected:!!(scope.sessionId && scope.token && scope.actorBinding), language:state.lang,
      getCapabilities:async () => { await current(); check(); return {destinations:Object.fromEntries(Object.entries(targets).map(([key, target]) => { const available = !!target && !!$(target[1]); return [key, {available, configured:available}]; }))}; },
      navigate:stage => open(targets[stage]),
      openPrivacy:async () => {
        await current(); check();
        const dialog = $('#accessDialog');
        dialog.querySelector('#guideNotebookExport')?.remove();
        if (viewer) {
          const button = document.createElement('button');
          button.id = 'guideNotebookExport'; button.type = 'button';
          button.className = 'button secondary'; button.textContent = 'Open notebook to choose items to export';
          button.addEventListener('click', async () => {
            button.disabled = true;
            try {
              await open(['audience', '#exportNotebook']);
              dialog.close(); $('#exportNotebook').focus();
            } catch { button.disabled = false; toast('Notebook unavailable. Check your connection and access, then try again.'); }
          });
          dialog.querySelector('#privateDataControls').before(button);
          dialog.addEventListener('close', () => button.remove(), {once:true});
        }
        $('#identity').click();
      },
      openPack:viewer ? () => open(['audience', '#wave24Pack']) : undefined,
      resumeSession:(viewer || creator) ? async () => { await current(); check(); navTo(viewer ? 'audience' : 'studio'); } : undefined
    });
  }
  return {reset};
})();
let wave24Desk = null;
// Creator inspection is explicitly bound to the selected current source and actor.
wave26Terms = (() => {
  const root = $('#wave26Terms'), selected = $('#p10StudioSource');
  const button = document.createElement('button'); button.type = 'button';
  button.textContent = 'Use selected source for terminology inspection'; root.append(button);
  const componentRoot = document.createElement('div'); root.append(componentRoot);
  const component = mountTerms(componentRoot, {});
  let generation = 0;
  function reset() { ++generation; component.update({}); }
  selected.addEventListener('change', reset);
  button.addEventListener('click', async () => {
    reset(); const ticket = generation, identity = identityScope(), sourceId = selected.value;
    try {
      assertSavedIdentity(identity);
      if (identity.role !== 'creator' || !identity.actorBinding || !sourceId) throw Error('Current creator and source required');
      await refreshSources(identity, {preservePhase10Selection:true}); assertSavedIdentity(identity);
      if (ticket !== generation || selected.value !== sourceId) throw Error('Source changed');
      const source = normalizeList(state.context?.sources || state.context).find(x => x.id === sourceId && x.status === 'active');
      if (!source || !Number.isSafeInteger(source.revision) || source.revision < 0) throw Error('Current source unavailable');
      const captured = JSON.stringify(source), scope = {actorId:identity.actorBinding, role:'creator', sourceId, sourceRevision:source.revision, rightsGeneration:ticket};
      const check = candidate => {
        assertSavedIdentity(identity);
        if (ticket !== generation || selected.value !== sourceId || sourceContextStale || !candidate || Object.keys(scope).some(k => candidate[k] !== scope[k])) throw Error('Context changed');
        const current = normalizeList(state.context?.sources || state.context).find(x => x.id === sourceId);
        if (!current || JSON.stringify(current) !== captured) throw Error('Source changed');
      };
      component.update({scope, assertScope:check, openEditor:() => { check(scope); navTo('studio'); const editor = $('#p12Root [data-terms-load]')?.closest('details'); if (!editor) throw Error('Terminology editor unavailable'); editor.open = true; editor.querySelector('summary').focus(); }, inspect:async ruleSetId => {
        check(scope); await refreshSources(identity, {preservePhase10Selection:true}); check(scope);
        const dto = await API.call('w26TerminologyInspect', ruleSetId ? {ruleSetId} : {}, {scope:identity});
        check(scope); await refreshSources(identity, {preservePhase10Selection:true}); check(scope); return dto;
      }});
      component.refresh();
    } catch { if (ticket === generation) component.update({}); }
  });
  return {reset};
})();
// Search uses the authenticated session and the existing exact-moment navigation.
// Correction is handled by the separately journaled Wave 21 control.
wave23Moments = (() => {
  let generation = 0, searchGeneration = 0, destinationGeneration = 0;
  const root = $('#wave23Moments');
  const archiveLabel = document.createElement('label'), archiveChannel = document.createElement('input');
  archiveLabel.textContent = 'Approved archive channel ID'; archiveChannel.maxLength = 128;
  archiveLabel.append(archiveChannel); root.before(archiveLabel);
  let archiveIdentity = null;
  archiveChannel.addEventListener('input', () => reset(false));
  const component = mountMoments23(root, {});
  const trailRoot = document.createElement('section');
  root.after(trailRoot);
  const trail = mountMomentTrail27(trailRoot, {});
  // A changed search invalidates an in-flight destination, including its shell navigation.
  const invalidateSearch = event => {
    if (event.target.closest('form') !== root.querySelectorAll('form')[1]) return;
    ++searchGeneration; trail.update({}); phase12Controller?.stopDelivery(); wave23Listening.reset(); $('#wave23MomentDetail').replaceChildren();
  };
  root.addEventListener('input', invalidateSearch);
  root.addEventListener('change', invalidateSearch);
  function reset(reconfigureRelated = true) {
    ++searchGeneration; phase12Controller?.stopDelivery(); wave23Listening.reset();
    trail.update({});
    if (reconfigureRelated) { wave28Setup.reset(); wave24Pack.reset(); wave24Activities.reset(); wave24Guide.reset(); wave24Desk?.reset(); }
    const scope = identityScope(), ticket = ++generation;
    const identity = JSON.stringify([scope.sessionId, scope.actorBinding, scope.role]);
    if (identity !== archiveIdentity) { archiveIdentity = identity; archiveChannel.value = ''; }
    $('#wave23MomentDetail').replaceChildren();
    const check = () => { assertIdentity(scope); if (ticket !== generation) throw new DOMException('Context changed', 'AbortError'); };
    const host = {scopeGeneration: ticket, sessionId: scope.sessionId, actorId: scope.viewerId || scope.actorBinding, role: scope.role, channelId: archiveChannel.value.trim(),
      search: async body => { check(); ++searchGeneration; trail.update({}); phase12Controller?.stopDelivery(); $('#wave23MomentDetail').replaceChildren(); const result = await API.call('w23MomentSearch', body, {scope}); check(); return result; },
      destination: async body => { check(); const destinationTicket = ++destinationGeneration; trail.update({}); phase12Controller?.stopDelivery(); $('#wave23MomentDetail').replaceChildren(); const result = await API.call('w23MomentDestination', body, {scope}); check(); if (destinationTicket !== destinationGeneration) throw Error('Destination changed'); return result; },
      momentImage: async body => { check(); const image = await API.momentImage(body, scope); check(); return image; },
      returnLive: async () => { check(); ++destinationGeneration; trail.update({}); phase12Controller?.stopDelivery(); $('#wave23MomentDetail').replaceChildren(); navTo('audience'); },
      openDestination: async ({moment}) => {
        const searchTicket = searchGeneration, destinationTicket = destinationGeneration;
        const checkDestination = () => { check(); if (searchTicket !== searchGeneration || destinationTicket !== destinationGeneration) throw new DOMException('Destination changed', 'AbortError'); };
        checkDestination();
        phase12Controller?.stopDelivery();
        const ref = moment.ref;
        const selection = {ref: structuredClone(ref)};
        if (moment.destination?.archive) selection.archive = structuredClone(moment.destination.archive);
        const openTrailDestination = async (destination, valid) => {
          try {
            checkDestination(); if (!valid()) throw Error('Context changed');
            const request = {ref: structuredClone(destination.ref)};
            if (destination.archive) request.archive = structuredClone(destination.archive);
            const result = await API.call('w23MomentDestination', request, {scope});
            checkDestination(); if (!valid()) throw Error('Context changed');
            const item = result?.moment;
            const same = (a,b,keys) => !!a && !!b && keys.every(k => a[k] === b[k]);
            if (!item || item.rightsState !== 'current' || !same(item.ref, request.ref, ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs']) || !(item.destination?.archive == null && request.archive == null || same(item.destination?.archive, request.archive, ['channelId','grantId','revision']))) throw Error('Destination unavailable');
            ++destinationGeneration;
            await host.openDestination({moment:item});
          } catch (error) {
            try { checkDestination(); if (valid()) { reset(false); $('#wave23MomentDetail').textContent = 'This moment is unavailable or changed.'; } } catch { /* A newer selection owns the view. */ }
            throw error;
          }
        };
        trail.update({sessionId:scope.sessionId, actorId:scope.viewerId || scope.actorBinding, role:scope.role, sourceRef:ref.sourceId, sourceRevision:ref.sourceRevision, scopeGeneration:ticket, rightsGeneration:searchTicket, channelId:archiveChannel.value.trim(),
          loadTrail:async (request, valid) => { checkDestination(); if (!valid()) throw Error('Context changed'); const result = await API.call('w27MomentTrail', request, {scope}); checkDestination(); if (!valid()) throw Error('Context changed'); return result; },
          inspect:openTrailDestination, navigate:openTrailDestination,
          returnLive:async (_unused, valid) => { checkDestination(); if (!valid()) throw Error('Context changed'); ++destinationGeneration; phase12Controller?.stopDelivery(); trail.update({}); $('#wave23MomentDetail').replaceChildren(); navTo('audience'); }
        });
        void trail.load(selection);
        if (moment.destination?.archive) {
          const request = {ref: structuredClone(ref), archive: structuredClone(moment.destination.archive)};
          const detail = $('#wave23MomentDetail');
          const button = document.createElement('button'), status = document.createElement('p');
          button.type = 'button'; button.textContent = 'Play moment audio';
          status.setAttribute('role', 'status');
          button.onclick = async () => {
            button.disabled = true; status.textContent = 'Checking current access to moment audio…';
            try {
              const read = async () => {
                checkDestination();
                const response = await fetch(`/api/sessions/${encodeURIComponent(scope.sessionId)}/w23/moments/audio`, {
                  method:'POST', credentials:'same-origin', cache:'no-store',
                  headers:{Authorization:`Bearer ${scope.token}`, 'Content-Type':'application/json', Accept:'audio/wav'},
                  body:JSON.stringify(request), signal:AbortSignal.timeout(30000)
                });
                checkDestination();
                if (!response.ok || response.headers.get('content-type') !== 'audio/wav') throw Error('Audio unavailable');
                const bytes = new Uint8Array(await response.arrayBuffer()); checkDestination();
                if (bytes.length < 44 || bytes.length > 6 * 1024 * 1024) throw Error('Audio unavailable');
                const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
                checkDestination(); return {bytes, hash};
              };
              const initial = await read();
              let binary = ''; for (let i = 0; i < initial.bytes.length; i += 32768) binary += String.fromCharCode(...initial.bytes.subarray(i, i + 32768));
              status.textContent = 'Playing the selected moment. Use the shared player controls to pause or stop.';
              await phase12Controller.playDelivery({audioBase64:btoa(binary), audioSha256:initial.hash}, scope, async hash => {
                const current = await read(); if (current.hash !== hash) throw Error('Moment audio changed');
              });
              checkDestination(); status.textContent = 'Moment playback finished.';
            } catch (_) { try { checkDestination(); status.textContent = 'Moment audio is unavailable or access changed.'; } catch {} }
            finally { button.disabled = false; }
          };
          detail.replaceChildren(button, status);
          return;
        }
        await refreshSources(scope); checkDestination();
        const source = normalizeList(state.context?.sources || state.context).find(x => x.id === ref.sourceId && x.revision === ref.sourceRevision && x.status === 'active' && x.audienceVisible === true);
        if (!source) throw new Error('Source unavailable');
        const data = await API.call('p10Timeline', null, ref.sourceId, {scope}); checkDestination();
        if (!Array.isArray(data.moments) || !data.moments.some(x => ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(k => x.ref?.[k] === ref[k]))) throw new Error('Moment unavailable');
        if (moment.regionId != null) {
          if (moment.destination?.kind !== 'moment_region' || moment.destination.regionId !== moment.regionId || !['observation', 'ocr', 'inference'].includes(moment.evidenceKind) || typeof moment.explanation !== 'string') throw new Error('Region unavailable');
          $('#questionSource').value = ref.sourceId; $('#questionMoment').value = `${Math.floor(ref.startMs / 60000)}:${String(Math.floor(ref.startMs / 1000) % 60).padStart(2, '0')}`;
          const detail = $('#wave23MomentDetail');
          const heading = document.createElement('h3'); heading.textContent = 'Selected visual region';
          const location = document.createElement('p'); location.textContent = `${source.title || 'Received visual source'} · ${ref.startMs}–${ref.endMs} ms · source revision ${ref.sourceRevision}`;
          const evidence = document.createElement('p'); evidence.textContent = `${moment.evidenceKind === 'inference' ? 'Interpretation (inference)' : moment.evidenceKind === 'ocr' ? 'OCR observation' : 'Observation'}: ${moment.explanation}`;
          const note = document.createElement('p'); note.textContent = 'This is retained evidence, not a playable stream or a new inspection.';
          detail.replaceChildren(heading, location, evidence, note); detail.focus(); detail.scrollIntoView();
          return;
        }
        const detail = $('#wave23MomentDetail');
        const heading = document.createElement('h3'); heading.textContent = source.title || 'Selected moment';
        const interval = document.createElement('p'); interval.textContent = `${ref.startMs}–${ref.endMs} ms · source revision ${ref.sourceRevision}`;
        const excerpt = document.createElement('p'); excerpt.textContent = typeof moment.text === 'string' ? moment.text : data.moments.find(x => ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(key => x.ref?.[key] === ref[key]))?.text || 'Open the source to inspect its current content.';
        detail.replaceChildren(heading, interval, excerpt);
        if (scope.role === 'creator') {
          const technical = document.createElement('details'), summary = document.createElement('summary'), reference = document.createElement('pre');
          summary.textContent = 'Operator source reference'; reference.textContent = JSON.stringify(ref, null, 2);
          technical.append(summary, reference); detail.append(technical);
        }
        wave23Listening.select(ref, scope);
        $('#questionSource').value = ref.sourceId; $('#questionMoment').value = `${Math.floor(ref.startMs / 60000)}:${String(Math.floor(ref.startMs / 1000) % 60).padStart(2, '0')}`;
        navTo('audience'); $('#question').focus();
      }
    };
    component.update(host);
  }
  reset(); return {reset};
})();
// The edition is read through the current authenticated record and source guards.
// Description audio uses the existing delivery authority for admission and recovery.
wave22EditionReader = (() => {
  const root = $("#wave22EditionReader"), select = root.querySelector("[data-record]"), language = root.querySelector("[data-language]"), status = root.querySelector("[data-status]"), content = root.querySelector("[data-content]");
  let reader = null, exporter = null, generation = 0, actor = null;
  function reset() { generation++; reader?.destroy(); reader = null; exporter?.destroy(); exporter = null; wave20Delivery?.reset(); actor = null; select.replaceChildren(new Option("Choose a record", "")); status.textContent = "Refresh approved records to check access."; }
  async function load() {
    reset(); const current = identityScope(), ticket = generation; status.textContent = "Checking approved records…";
    try { const data = await API.call("w18Records", null, {scope:current}); assertIdentity(current); if (ticket !== generation || !Array.isArray(data.records)) return;
      actor = current; for (const record of data.records) if ((current.role !== "creator" || (record.state === "approved" && !record.stale)) && typeof record.id === "string") select.append(new Option(`Version ${record.version} · ${record.sourceLanguage || "source"}`, record.id));
      status.textContent = select.options.length > 1 ? "Choose an approved record and language." : "No approved records are available.";
    } catch { if (ticket === generation) status.textContent = "Records or current access are unavailable."; }
  }
  async function open() {
    reader?.destroy(); reader = null; exporter?.destroy(); exporter = null; wave20Delivery?.reset(); const ticket = ++generation, current = actor, id = select.value, lang = language.value;
    if (!current || !id || !["en", "es"].includes(lang)) { status.textContent = "Choose an approved record and language."; return; }
    try { assertIdentity(current); const viewScope = {epoch:current.epoch, sessionId:current.sessionId, role:current.role, viewerId:current.viewerId, recordId:id, language:lang, generation:ticket};
      const guard = () => { assertIdentity(current); if (generation !== ticket || select.value !== id || language.value !== lang) throw Error("Edition changed"); };
      reader = mountEdition(content, {scope:viewScope, api:{
        read:async () => { guard(); const result = await API.call("w22Edition", null, id, lang, {scope:current}); guard(); return result.edition; },
        readAsset:async ({reference}) => { guard(); const prefix = `/api/sessions/${encodeURIComponent(current.sessionId)}/w22/edition/${encodeURIComponent(id)}/${lang}/assets/`; if (!reference.startsWith(prefix) || !/^[a-f0-9]{64}$/.test(reference.slice(prefix.length))) throw Error("Invalid asset"); const result = await API.call("w22EditionAsset", null, id, lang, reference.slice(prefix.length), {scope:current}); guard(); return result; }
      }, actions:{connectPlayer:async ({binding,reference,offsetMs,isCurrent}) => {
        guard();
        const ref=binding?.sourceRef;
        const sameBinding=other=>other && binding && other.originMs===binding.originMs && other.audioSha256===binding.audioSha256 && other.sourceRef && ref && ['sessionId','sourceId','sourceRevision','momentId','startMs','endMs'].every(key=>other.sourceRef[key]===ref[key]);
        if(!phase12Controller || ref?.sessionId!==current.sessionId || reference!==`/api/sessions/${encodeURIComponent(current.sessionId)}/p12/sources/${encodeURIComponent(ref.sourceId)}/original-audio`)throw Error("Original player unavailable");
        const validate=async()=>{guard();if(!isCurrent())throw Error("Edition changed");const fresh=await API.call("w22Edition",null,id,lang,{scope:current});guard();if(!isCurrent()||fresh.edition?.timedPlayback?.state!=="available"||!sameBinding(fresh.edition.timedPlayback.binding)||fresh.edition.timedPlayback.authorizedRef!==reference)throw Error("Original media changed");};
        await validate();
        return phase12Controller.editionPlayer(binding,offsetMs,current,validate,()=>{try{guard();return isCurrent();}catch{return false;}});
      }, playDescription:async ({editionId, description, isCurrent}) => { guard(); if (!wave20Delivery || !isCurrent()) throw Error("Delivery unavailable"); root.querySelector("[data-delivery-slot]").append($("#wave20Delivery")); navTo("audience"); $("#wave20Delivery").scrollIntoView(); await wave20Delivery.requestDescription(editionId, description, current, () => { try { guard(); return isCurrent(); } catch { return false; } }); guard(); }, returnToLive:async ({reference}) => { guard(); if (reference?.sessionId !== current.sessionId) throw Error("Session changed"); navTo("audience"); }} });
      status.textContent = "Checking the selected edition…"; await reader.refresh(); guard();
      const result = await API.call("w22Edition", null, id, lang, {scope:current}); guard();
      const binding = {epoch:current.epoch, sessionId:current.sessionId, role:current.role, actorId:current.actorBinding, recordId:id, language:lang, generation:ticket};
      const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
      const same = (a, b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
      exporter = mountApprovedExport(content, {
        requestExport:async ({scope, body}) => { guard(); if (!same(scope, binding)) throw Error("Scope changed"); const value = await API.call("w27EditionExport", body, {scope:current}); guard(); return value; },
        verifyCurrent:async ({scope, manifest}) => { guard(); if (!same(scope, binding)) return false; const fresh = await API.call("w22Edition", null, id, lang, {scope:current}); guard(); return same(fresh.edition, manifest); }
      });
      exporter.update(result.edition, binding); status.textContent = "Edition access checked.";
    } catch { if (ticket === generation) { reader?.destroy(); reader = null; exporter?.destroy(); exporter = null; status.textContent = "Edition or current access is unavailable."; } }
  }
  root.querySelector("[data-load]").addEventListener("click", load); root.querySelector("[data-delivery]").addEventListener("click", () => { root.querySelector("[data-delivery-slot]").append($("#wave20Delivery")); $("#wave20Delivery").scrollIntoView(); }); select.addEventListener("change", open); language.addEventListener("change", open); reset(); return {reset};
})();
// Creator association uses the same current edition projection as the reader.
wave22DescriptionCreator = (() => {
  const root = $("#wave22DescriptionCreator"), edition = root.querySelector("[data-edition]"), language = root.querySelector("[data-language]"), narration = root.querySelector("[data-narration]"), region = root.querySelector("[data-region]"), status = root.querySelector("[data-status]");
  let scope = null, generation = 0, records = [], regions = [], busy = false;
  const journalKey = s => `entrelineas.w22.description.v1:${s.sessionId}:${s.actorBinding}`;
  const guard = (s, ticket) => { assertIdentity(s); if (tabOnlyAccess || scope !== s || generation !== ticket || s.role !== "creator") throw Error("Selection changed"); };
  function reset() { generation++; scope = null; records = []; regions = []; edition.replaceChildren(new Option("Choose an edition", "")); narration.replaceChildren(new Option("Choose a record", "")); region.replaceChildren(new Option("Choose a region", "")); status.textContent = "Refresh approved records to select a description."; }
  async function refresh() {
    reset(); const s = identityScope(), ticket = generation;
    if (tabOnlyAccess) { status.textContent = "Description editing requires saved access so recovery remains protected."; return; }
    try {
      if (s.role !== "creator" || !s.token || !s.actorBinding) throw Error("Creator access required");
      scope = s; const result = await API.call("w18Records", null, {scope:s}); guard(s, ticket);
      if (!Array.isArray(result.records)) throw Error("Records unavailable");
      records = result.records.filter(r => r.state === "approved" && !r.stale && typeof r.id === "string" && Number.isInteger(r.version));
      for (const r of records) { const label = `Record ${r.id} · version ${r.version} · ${r.sourceLanguage || "source"}`; edition.append(new Option(label, r.id)); narration.append(new Option(label, r.id)); }
      status.textContent = localStorage.getItem(journalKey(s)) !== null ? "A previous description action is unconfirmed. It is preserved; no new action will be sent." : "Choose an edition and language to load its available visual regions.";
    } catch { if (ticket === generation) status.textContent = "Approved records or creator access are unavailable."; }
  }
  async function loadRegions() {
    const s = scope, ticket = ++generation, id = edition.value, lang = language.value;
    regions = []; region.replaceChildren(new Option("Choose a region", ""));
    if (!s || !id) return;
    try {
      guard(s, ticket); const result = await API.call("w22Edition", null, id, lang, {scope:s}); guard(s, ticket);
      if (edition.value !== id || language.value !== lang || !Array.isArray(result.edition?.regions)) throw Error("Edition changed");
      regions = result.edition.regions.filter(r => typeof r.regionId === "string" && r.sourceRef && typeof r.sourceRef === "object");
      regions.forEach((r, i) => region.append(new Option(`Region ${r.regionId} · frame ${r.frameId}`, String(i))));
      status.textContent = localStorage.getItem(journalKey(s)) !== null ? "A previous description action is unconfirmed. It is preserved; no new action will be sent." : (regions.length ? "Select a region and an approved description record." : "No currently authorized visual region is available for this edition.");
    } catch { if (ticket === generation) status.textContent = "Edition or current visual access is unavailable."; }
  }
  async function mutate(action) {
    const s = scope, ticket = generation, id = edition.value, lang = language.value, selected = regions[Number(region.value)], record = records.find(r => r.id === narration.value);
    if (!s || !id || (action === "select" && (!record || region.value === "" || !selected))) { status.textContent = "Choose the required edition, record and region."; return; }
    if (!navigator.locks || !crypto.randomUUID || !s.actorBinding) { status.textContent = "Safe action recovery is unavailable in this browser."; return; }
    if (busy) return;
    busy = true;
    try {
      await navigator.locks.request(journalKey(s), async () => {
        guard(s, ticket); if (localStorage.getItem(journalKey(s)) !== null) throw Error("Previous action unconfirmed");
        const current = await API.call("w22Edition", null, id, lang, {scope:s}); guard(s, ticket);
        if (edition.value !== id || language.value !== lang) throw Error("Edition changed");
        let body = null;
        if (action === "select") {
          if (narration.value !== record.id || regions[Number(region.value)] !== selected || !current.edition?.regions?.some(r => r.regionId === selected.regionId && JSON.stringify(r.sourceRef) === JSON.stringify(selected.sourceRef))) throw Error("Region changed");
          const description = await API.call("w22Edition", null, record.id, lang, {scope:s}); guard(s, ticket);
          if (edition.value !== id || language.value !== lang || narration.value !== record.id || regions[Number(region.value)] !== selected || description.edition?.recordVersion !== record.version) throw Error("Record changed");
          body = {recordId:record.id, recordVersion:record.version, language:lang, sourceRef:selected.sourceRef, regionId:selected.regionId};
        } else if (!confirm("Withdraw this edition description?")) return;
        guard(s, ticket);
        const requestId = crypto.randomUUID(); body = {...body, requestId};
        const marker = JSON.stringify({version:2, action, editionId:id, requestId});
        localStorage.setItem(journalKey(s), marker);
        const result = await API.call(action === "select" ? "w22EditionDescriptionSelect" : "w22EditionDescriptionWithdraw", body, id, {scope:s});
        guard(s, ticket);
        if (result.operation?.requestId !== requestId || result.operation?.action !== action || result.operation?.state !== "committed" || localStorage.getItem(journalKey(s)) !== marker) throw Error("Unconfirmed result");
        localStorage.removeItem(journalKey(s));
        wave20Delivery?.reset(); wave22EditionReader?.reset();
        status.textContent = action === "select" ? "Description selected. Listeners can request it through the existing delivery controls." : "Description withdrawn.";
      });
    } catch { if (ticket === generation) { try { guard(s, ticket); status.textContent = localStorage.getItem(journalKey(s)) !== null ? "The action could not be confirmed. Its pending marker is preserved; do not repeat it." : "The selection or current access changed. Refresh before trying again."; } catch { status.textContent = tabOnlyAccess ? "Description editing requires saved access so recovery remains protected." : "The selection or current access changed. Refresh before trying again."; } } } finally { busy = false; }
  }
  async function recover() {
    const s = scope, ticket = generation;
    if (!s || !navigator.locks || busy) return;
    busy = true;
    try {
      await navigator.locks.request(journalKey(s), async () => {
        guard(s, ticket); const raw = localStorage.getItem(journalKey(s));
        if (raw === null) { status.textContent = "No description action is awaiting confirmation."; return; }
        let pending; try { pending = JSON.parse(raw); } catch { throw Error("Invalid pending marker"); }
        if (pending?.version !== 2 || !["select", "withdraw"].includes(pending.action) || typeof pending.editionId !== "string" || typeof pending.requestId !== "string") {
          status.textContent = "The earlier action has no recoverable request ID. Its marker remains preserved."; return;
        }
        const result = await API.call("w22EditionDescriptionOperation", null, pending.editionId, pending.requestId, {scope:s}); guard(s, ticket);
        if (result.operation?.requestId !== pending.requestId || result.operation?.action !== pending.action || result.operation?.state !== "committed" || localStorage.getItem(journalKey(s)) !== raw) throw Error("Unconfirmed receipt");
        localStorage.removeItem(journalKey(s)); wave20Delivery?.reset(); wave22EditionReader?.reset();
        status.textContent = "Previous action confirmed. Refresh the edition to see its current state.";
      });
    } catch { if (ticket === generation) status.textContent = "The previous action is still unconfirmed; its marker remains preserved."; } finally { busy = false; }
  }
  root.querySelector("[data-refresh]").addEventListener("click", refresh);
  edition.addEventListener("change", loadRegions); language.addEventListener("change", loadRegions);
  root.querySelector("[data-select]").addEventListener("click", () => mutate("select")); root.querySelector("[data-withdraw]").addEventListener("click", () => mutate("withdraw"));
  root.querySelector("[data-recover]").addEventListener("click", recover);
  reset(); return {reset};
})();
const openWave18Source = (ref, scope) => {
  assertIdentity(scope);
  if (!ref || ref.sessionId !== scope.sessionId) throw Error("Source unavailable");
  return openCurrentAudienceSource({id: ref.sourceId, revision: ref.sourceRevision}, scope);
};
wave18CreatorRecord = mountRecords($("#wave18CreatorRecord"), API, identityScope, assertSavedIdentity, openWave15Moment, openWave18Source);
wave18ViewerRecord = mountRecords($("#wave18ViewerRecord"), API, identityScope, assertSavedIdentity, openWave15Moment, openWave18Source);
$("#wave18CreatorRecordRefresh").addEventListener("click", () => { if (!tabOnlyAccess) wave18CreatorRecord.refresh(); });
$("#wave18ViewerRecordRefresh").addEventListener("click", () => { if (!tabOnlyAccess) wave18ViewerRecord.refresh(); });
// Keep chapter entry behind saved access and rebind its lifecycle only after
// the new identity and access mode have been installed.
function mountSavedChapters(root, role) {
  const host = document.createElement("div");
  const notice = document.createElement("p");
  notice.textContent = "Chapters require saved access to protect drafts and request recovery.";
  notice.setAttribute("role", "status");
  const content = document.createElement("div");
  host.append(notice, content); root.append(host);
  for (const type of ["click", "input", "change"]) content.addEventListener(type, event => {
    try { assertSavedIdentity(identityScope()); }
    catch { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  const component = mountChapters(content, API, identityScope, assertSavedIdentity, role, openWave15Moment);
  const update = () => { notice.hidden = !tabOnlyAccess; content.inert = tabOnlyAccess; };
  update();
  return {
    reset() { component.reset(); update(); },
    activate() { component.activate(); update(); },
    invalidate() { component.invalidate(); update(); },
    focusChapter(id) { assertSavedIdentity(identityScope()); return component.focusChapter(id); },
    update
  };
}
wave15Viewer = mountSavedChapters($("#catchupPanel"), "viewer");
wave15Creator = mountSavedChapters($("#waveModelPreview"), "creator");
waveModelPreview = mountModelPreview($("#waveLocalModelPreview"), identityScope);
waveDrafts = mountWaveDrafts($("#waveModelPreview"), identityScope);
waveReasons = mountReasons($("#waveModelPreview"), API, identityScope, assertSavedIdentity);
// Production actions have no durable tab-only request journal. Keep even
// delayed controls inside the saved-access boundary before they dispatch.
waveProduction = mountProduction($("#waveModelPreview"), API, identityScope, assertSavedIdentity);
cueController = mountCues($("#productionCues"), API, identityScope, assertSavedIdentity);

// Assistance reads its recovery journal immediately after asking the host for
// identity. Fail before returning a scope when saved access is unavailable.
const assistanceSavedScope = () => {
  const scope = identityScope();
  try { assertSavedIdentity(scope); return scope; }
  catch { return null; }
};
const assistanceRoot = $("#wave18Assistance");
const assistanceComponent = mountAssistance(assistanceRoot, API, assistanceSavedScope, assertSavedIdentity, {
  onDraftCreated: () => { navTo("studio"); phase10Controller?.refreshStudioCollection(); $("#p10Studio").querySelector("details").open = true; $("#p10Studio").scrollIntoView(); },
});
// The component installs generation-bound controls and guards every journal access.
wave18Assistance = assistanceComponent;
// Authenticated catalog reads are available; writes require a current-rights receipt route.
const wave19FeatureAPI = {isReceiptReplaySafe: operation => ['w19LibraryImport','w20PracticeCreate','w20PracticeAttempt','w20PracticeShare','w20BridgeCreate','w20BridgeRevoke'].includes(operation), async call(operation, body, ...args) {
  const options = args.pop(), scope = options?.scope;
  if (!scope) throw Error('Identity unavailable');
  if (operation === 'w19Library' || operation === 'w19LibraryItem' || operation === 'w19LibraryExport') {
    const data = await API.call('w19LibraryCatalog', null, {scope}); assertIdentity(scope);
    if (!Array.isArray(data.entries)) throw Error('Catalog unavailable');
    if (operation === 'w19Library') return {items:data.entries};
    const item = data.entries.find(entry => entry.id === args[0]);
    if (!item) throw Error('Definition unavailable');
    if (operation === 'w19LibraryItem') return {item};
    return API.call('w19LibraryValidate', {envelope:{schemaVersion:1,definition:item.definition}}, {scope});
  }
  if (operation === 'w19OwnedLibraryExport') return API.call(operation, null, args[0], {scope});
  if (operation === 'w19LibraryCheck') return API.call('w19LibraryValidate', body, {scope});
  if (operation === 'w19LibraryImport') { const result = await API.call(operation, body, {scope}); assertIdentity(scope); if (!result?.template || !result?.version) throw Error('Import response unconfirmed'); return result; }
  if (operation === 'w19_20Receipt' && body?.operation === 'w19LibraryImport') { const receipt = await API.call(operation, body, {scope}); assertIdentity(scope); if (receipt?.status === 'committed' && (!receipt.result?.template || !receipt.result?.version)) throw Error('Receipt projection unconfirmed'); return receipt; }
  if (operation === 'w20PracticeContinuations' || operation === 'w20PracticeDiscovery') return API.call(operation, null, {scope});
  if (operation === 'w20PracticeCreate' || operation === 'w20PriorAttempts' || operation === 'w20BridgeCreate') return API.call(operation, body, {scope});
  if (operation === 'w20BridgeRevoke') return API.call(operation, null, args[0], {scope});
  if (operation === 'w20PracticeReview') return API.call(operation, body, args[0], args[1], {scope});
  if (operation === 'w20PracticeAttempt' || operation === 'w20PracticeShare') return API.call(operation, body, args[0], {scope});
  if (operation === 'w20PracticeRevoke') return API.call(operation, body, args[0], args[1], {scope});
  if (operation === 'w19_20Receipt' && ['w20PracticeCreate','w20PracticeAttempt','w20PracticeShare','w20PracticeRevoke','w20PracticeReview'].includes(body?.operation)) return API.call(operation, body, {scope});
  throw Error('Service capability unavailable');
}};
const openWave19Templates = () => { navTo('studio'); const details=$('#waveModelPreview').querySelector('.w17-templates details'); if(details){details.open=true;details.querySelector('summary').focus();details.scrollIntoView();} };
wave19Library = mountLibrary($('#wave19Library'), wave19FeatureAPI, identityScope, assertSavedIdentity, {adaptDefinition: (definition,scope)=>{assertIdentity(scope);openWave19Templates();return wave17Templates.prefillDefinition(definition,scope);}, openTemplates:(id,scope)=>{assertIdentity(scope);openWave19Templates();return wave17Templates.selectTemplate(id,scope);}});
async function openCurrentAudienceSource(source, scope) {
  assertIdentity(scope);
  await refreshSources(scope);
  assertIdentity(scope);
  const current = normalizeList(state.context?.sources || state.context).find(x => x.id === source.id && x.revision === source.revision && x.status === 'active' && x.audienceVisible === true);
  if (!current) throw Error('Source unavailable');
  const row = [...$('#contextSources').querySelectorAll('[data-source-id]')].find(node => node.dataset.sourceId === current.id);
  if (!row) throw Error('Source unavailable');
  const dialog = $('#contextDialog');
  if (!dialog.open) dialog.showModal();
  row.tabIndex = -1; row.focus(); row.scrollIntoView({block:'nearest'});
}
wave21Visual = mountVisualView($('#wave21Visual'), {identity:identityScope, assertIdentity:assertSavedIdentity, search:(q,scope)=>API.call('w15Search',null,q,{scope}), frame:(ref,scope)=>API.call('w21VisualSource',{ref},{scope}), frameImage:(ref,scope)=>API.call('p10Frame',null,new URLSearchParams({sourceId:ref.sourceId,sourceRevision:String(ref.sourceRevision),momentId:ref.momentId,startMs:String(ref.startMs),endMs:String(ref.endMs)}),{scope}), inspect:(body,scope)=>API.call('w21VisualGround',body,{scope}), receipt:(id,scope)=>API.call('w21VisualReceipt',null,id,{scope})});
wave21ImpactPreview = mountImpactPreview($('#wave21ImpactPreview'), {identity:identityScope, assertIdentity:assertSavedIdentity, assertReadIdentity:assertIdentity, search:(q,scope)=>API.call('w15Search',null,q,{scope}), sourceSearch:(_q,scope)=>API.call('sources',null,{scope}), materialSearch:(q,scope)=>API.call('w23MomentSearch',{query:q,scope:'session'},null,{scope}), preview:(body,scope)=>API.call('w21ImpactPreview',body,null,{scope}), change:(body,scope)=>API.call('w21ImpactChange',body,null,{scope}), request:(id,scope)=>API.call('w21ImpactRequest',null,id,{scope}), getChange:(id,scope)=>API.call('w21ImpactGet',null,id,{scope}), recoverSource:(id,scope)=>API.call('w21ImpactRecovery',null,id,{scope}), listSpeech:(after,scope)=>API.call('p12CollabGet',null,`operations?after=${after}&limit=100`,{scope}), replaceSpeech:(id,body,scope)=>API.call('w21ImpactSpeechReplacement',body,id,{scope}), replaceCaption:(id,body,scope)=>API.call('w21ImpactCaptionReplacement',body,id,{scope}), replaceMaterial:(id,body,scope)=>API.call('w21ImpactMaterialReplacement',body,id,{scope}), openMaterial:async (button,id,scope,version)=>{assertIdentity(scope); navTo('studio'); await openMaterialForReview(button,id,scope,version); assertIdentity(scope);}, recordOptions:scope=>API.call('w18RecordOptions',null,{scope}), replaceRecord:(id,body,scope)=>API.call('w21ImpactRecordReplacement',body,id,{scope}), openRecord:async (id,scope,version,origin)=>{assertIdentity(scope); const result=await API.call('w18Record',null,id,{scope}); assertIdentity(scope); if(scope.role!=='creator'||result?.record?.id!==id||result.record.version!==version||result.stale||result.record.stale||!result.record.snapshot) throw Error('Record version or current sources unavailable'); if (!tabOnlyAccess) assertSavedIdentity(scope); await openTabOnlyRecordReview(origin,id,version,scope);}});
wave21Speech = mountSpeechView($('#wave21Speech'), {identity: identityScope, assertIdentity:assertSavedIdentity, useForListening: (id, scope) => wave23Listening.useRun(id, scope), selectedSource: () => phase12Controller.selectedCaption(), createRun: (ref, scope) => API.call('w21SpeechCreate', {ref}, null, {scope}), read: (id, scope) => API.call('w21SpeechRun', null, id, {scope}), ingest: (id, body, scope) => API.call('w21SpeechChunk', body, id, {scope}), readRules: (id, scope) => API.call('w21SpeechRules', null, id, {scope}), createRules: scope => API.call('w21SpeechRulesCreate', {}, null, {scope}), updateRules: (id, body, scope) => API.call('w21SpeechRulesUpdate', body, id, {scope}), revise: (id, body, scope) => API.call('w21SpeechRevise', body, id, {scope}), finalize: (id, body, scope) => API.call('w21SpeechFinalize', body, id, {scope}), preview: (id, body, scope) => API.call('w21SpeechPreview', body, id, {scope})});
const creatorSpeechSetup = mountCreatorSpeechSetup($('#wave21Speech'), {identity:identityScope, assertIdentity:assertSavedIdentity, installed:s=>API.call('w23InstalledVoices',null,null,{scope:s}), rules:(id,s)=>API.call('w21SpeechRules',null,id,{scope:s}), profile:(id,s)=>API.call('w23CreatorProfile',null,id,{scope:s}), save:(id,b,s)=>API.call('w23CreatorProfileSave',b,id,{scope:s}), approve:(id,b,s)=>API.call('w23CreatorProfileApprove',b,id,{scope:s}), operation:(id,s)=>API.call('w23ProfileOperation',null,id,{scope:s})});
const resetSpeech = wave21Speech.reset; wave21Speech.reset = () => { resetSpeech(); creatorSpeechSetup.reset(); };
const claimsOptions = {identity:identityScope, assertIdentity:assertSavedIdentity, query:(query,scope)=>API.call('w22Claims',{query},null,{scope}), mutate:(body,scope)=>API.call('w22Claims',body,null,{scope}), openSource:openWave15Moment, selectedSource:()=>phase12Controller.selectedCaption()};
wave22ModelHistory = mountModelHistory($('#wave22ModelHistory'), {identity:identityScope, assertIdentity, list:scope=>API.call('w22Models',null,{scope}), openSource:openWave15Moment});
wave22ModelWithdrawals = mountModelWithdrawals($('#wave22ModelWithdrawals'), {identity:identityScope, assertIdentity:assertSavedIdentity, list:scope=>API.call('w22ModelOwnedShares',null,{scope}), mutate:(body,scope)=>API.call('w22ModelMutate',body,{scope})});
wave22ModelExploration = mountModelExploration($('#wave22ModelExploration'), {identity:identityScope, assertIdentity:assertSavedIdentity, approvals:scope=>API.call('w22ModelApprovals',null,{scope}), continuations:scope=>API.call('w20PracticeContinuations',null,{scope}), models:scope=>API.call('w22Models',null,{scope}), receipts:scope=>API.call('w22ModelReceipts',null,{scope}), mutate:(body,scope)=>API.call('w22ModelMutate',body,{scope}), openSource:(source,scope)=>openWave15Moment(source.ref,scope)});
const resetModelWithdrawals = wave22ModelWithdrawals.reset;
wave22ModelWithdrawals.reset = () => { resetModelWithdrawals(); wave22ModelExploration.reset(); };
wave22ModelShares = mountModelShares($('#wave22ModelShares'), {identity:identityScope, assertIdentity, list:scope=>API.call('w22ModelShares',null,{scope}), openSource:openWave15Moment});
const wave22ModelApprovals = mountModelApprovals($('#wave22ModelShares'), {identity:identityScope, assertIdentity:assertSavedIdentity, templates:scope=>API.call('w17Templates',null,{scope}), versions:(id,scope)=>API.call('w17Template',null,id,{scope}), search:(query,scope)=>API.call('w15Search',null,query,{scope}), list:scope=>API.call('w22ModelApprovals',null,{scope}), approve:(body,scope)=>API.call('w22ModelApprove',body,{scope}), revoke:(id,scope)=>API.call('w22ModelApprovalRevoke',{},id,{scope})});
const resetModelShares = wave22ModelShares.reset;
wave22ModelShares.reset = () => { resetModelShares(); wave22ModelApprovals.reset(); };
wave22ClaimsViewer = mountClaimsQuery($('#wave22ClaimsViewer'), claimsOptions);
wave22ClaimsCreator = mountClaimsQuery($('#wave22ClaimsCreator'), claimsOptions);
const assertCoeditIdentity = scope => { assertIdentity(scope); if (tabOnlyAccess) throw Error('Coauthor recovery requires saved access'); };
const coeditOptions = {identity:identityScope, assertIdentity:assertCoeditIdentity, list:(scope)=>API.call('w22CoeditGrants',null,{scope}), revokeGrant:(id,revision,scope)=>API.call('w22CoeditGrantRevoke',{revision},id,{scope}), read:(id,scope)=>API.call('w22CoeditRead',null,id,{scope}), readOperation:(id,requestId,scope)=>API.call('w22CoeditOperation',null,id,requestId,{scope}), mutate:(kind,id,body,scope)=>API.call({patch:'w22CoeditPatch',approve:'w22CoeditApprove',adopt:'w22CoeditAdopt',withdraw:'w22CoeditWithdraw'}[kind],body,id,{scope}), openDesk:(selection,scope)=>wave24Desk.select(selection,scope)};
const coeditCreator = mountCoeditAccess($('#wave22Coedit'), coeditOptions), coeditViewer = mountCoeditAccess($('#wave22CoeditViewer'), coeditOptions);
const coeditSetup = mountCoeditSetup($('#wave22Coedit'), {identity:identityScope, assertIdentity:assertCoeditIdentity, grant:(body,scope)=>API.call('w22CoeditGrantCreate',body,null,{scope}), create:(body,scope)=>API.call('w22CoeditDraftCreate',body,null,{scope}), openCreated:(id,scope)=>coeditCreator.open(id,scope)});
wave22Coedit = {reset() { coeditCreator.reset(); coeditViewer.reset(); coeditSetup.reset(); }};
// The desk journals only opaque request metadata before any durable action.
// Its component retains unsaved text in memory; it is never persisted here.
wave24Desk = (() => {
  let generation = 0, mounted = null, host = null, selectDraft = null, releaseDeskLock = null, deskLockSettled = Promise.resolve();
  const keyFor = s => `entrelineas.w24.desk.v1:${s.sessionId}:${s.actorBinding}`;
  function reset() {
    generation++; mounted?.destroy(); mounted = null; releaseDeskLock?.(); releaseDeskLock = null; host?.remove(); host = null; selectDraft = null;
    const scope = identityScope();
    if (tabOnlyAccess || !scope.sessionId || !scope.token || !scope.actorBinding || !['creator','viewer'].includes(scope.role)) return;
    const ticket = generation, check = () => { assertSavedIdentity(scope); if (ticket !== generation) throw new DOMException('Context changed','AbortError'); };
    const key = keyFor(scope), parent = $(scope.role === 'creator' ? '#wave22Coedit' : '#wave22CoeditViewer');
    host = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Editorial desk'; host.append(summary);
    const draftLabel = document.createElement('label'); draftLabel.textContent = 'Draft ID'; const draft = document.createElement('input'); draft.maxLength = 128; draftLabel.append(draft);
    const segmentLabel = document.createElement('label'); segmentLabel.textContent = 'Segment ID for adoption'; const segment = document.createElement('input'); segment.maxLength = 128; segmentLabel.append(segment);
    const capabilityLabel = document.createElement('label'); capabilityLabel.textContent = 'Source session capability for cross-session templates'; const capability = document.createElement('input'); capability.type = 'password'; capability.autocomplete = 'off'; capabilityLabel.append(capability);
    const open = document.createElement('button'); open.type = 'button'; open.textContent = 'Open desk';
    const status = document.createElement('p'); status.setAttribute('role','status');
    const recover = document.createElement('button'); recover.type = 'button'; recover.textContent = 'Check earlier desk action';
    const root = document.createElement('div'); host.append(draftLabel, segmentLabel, capabilityLabel, open, status, recover, root); parent.insertAdjacentElement('afterend',host);
    const validId = x => typeof x === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(x);
    const invoke = async (name, body, ...args) => { check(); const result = await API.call(name,body,...args,{scope}); check(); return result; };
    const locked = async fn => { if (!navigator.locks) throw Error('Safe recovery unavailable'); return navigator.locks.request(key, fn); };
    const readMarker = () => { const raw = localStorage.getItem(key); if (raw === null) return null; const value = JSON.parse(raw); if (!value || value.version !== 1 || !validId(value.requestId) || !validId(value.draftId)) throw Error('Invalid pending marker'); return value; };
    const pendingStatus = () => { check(); const componentPending = Object.keys(localStorage).some(k => k.startsWith(`${key}:component:`)); recover.hidden = localStorage.getItem(key) === null || componentPending; status.textContent = componentPending ? 'Open the original draft and use Check unconfirmed action to recover it.' : recover.hidden ? 'Open a draft you are authorized to edit.' : 'An earlier action is unconfirmed. Check it before another desk action.'; };
    const reconcile = async marker => {
      let result;
      if (['patch','approve','withdraw'].includes(marker.kind)) {
        result = await invoke('w22CoeditOperation',null,marker.draftId,marker.requestId);
        if (result.operation?.action !== marker.kind || !['committed','conflict'].includes(result.operation?.state)) throw Error('Unconfirmed receipt');
      } else if (marker.kind === 'adopt') {
        result = await invoke('w24DeskHandoff',{requestId:marker.requestId,approvedRevision:marker.approvedRevision,segmentId:marker.segmentId},marker.draftId,'recover');
        if (result.operation?.state !== 'committed') throw Error('Unconfirmed handoff');
      } else if (marker.kind === 'template') {
        result = await invoke('w24DeskTemplateReceipt',null,marker.requestId);
        if (result.operation?.requestId !== marker.requestId || result.operation?.state !== 'committed') throw Error('Unconfirmed template');
      } else if (marker.kind === 'apply') {
        if (marker.sourceSessionId) {
          if (!validId(marker.sourceSessionId) || !capability.value) throw Error('Source capability required');
          check(); result = await API.call('w24DeskCrossApply',{requestId:marker.requestId,baseRevision:marker.baseRevision},marker.sourceSessionId,marker.templateId,marker.templateVersion,'recover-apply',marker.draftId,{scope,headers:{'X-Source-Capability':capability.value}}); check();
        } else result = await invoke('w24DeskApply',{requestId:marker.requestId,baseRevision:marker.baseRevision},marker.templateId,marker.templateVersion,'recover-apply',marker.draftId);
        if (!['committed','conflict','not_committed'].includes(result.operation?.state)) throw Error('Unconfirmed application');
      } else throw Error('Unknown action');
      return result;
    };
    const recoverMarker = (expected, fallback) => locked(async () => { check(); const raw = localStorage.getItem(key), marker = readMarker() || fallback; if (!marker) throw Error('No pending action'); if (expected && (marker.requestId !== expected.requestId || (expected.draftId && marker.draftId !== expected.draftId))) throw Error('Original request required'); const result = await reconcile(marker); check(); if (localStorage.getItem(key) !== raw) throw Error('Action changed'); if (raw !== null) localStorage.removeItem(key); pendingStatus(); return result; });
    const mutate = (kind, args, call) => locked(async () => {
      check(); if (readMarker()) throw Error('Earlier action unconfirmed');
      if (!validId(args.requestId) || !validId(args.draftId)) throw Error('Invalid action identifiers');
      const marker = {version:1,kind,requestId:args.requestId,draftId:args.draftId};
      if (kind === 'adopt') Object.assign(marker,{approvedRevision:args.approvedRevision,segmentId:args.segmentId});
      if (kind === 'apply') Object.assign(marker,{templateId:args.templateId,templateVersion:args.version,baseRevision:args.baseRevision,...(args.sourceSessionId ? {sourceSessionId:args.sourceSessionId} : {})});
      const raw = JSON.stringify(marker); localStorage.setItem(key,raw); pendingStatus();
      let result;
      try { result = await call(); }
      catch (error) { if ([400,422].includes(error.status) || (error.status === 409 && ['version_conflict','stale_revision','request_conflict','stale_context'].includes(error.code))) { try { check(); if (localStorage.getItem(key) === raw) { localStorage.removeItem(key); pendingStatus(); } } catch { /* preserve the original marker after an identity change */ } } throw error; }
      check();
      if (!['committed','conflict'].includes(result.operation?.state) || localStorage.getItem(key) !== raw) throw Error('Unconfirmed result');
      localStorage.removeItem(key); pendingStatus(); return result;
    });
    recover.onclick = async () => { recover.disabled = true; try { await recoverMarker(); status.textContent = 'Earlier action confirmed. Open the draft again to refresh its current state.'; } catch { try { check(); status.textContent = 'Action remains unconfirmed; its original request is preserved.'; } catch {} } finally { recover.disabled = false; } };
    open.onclick = async () => {
      if (open.disabled) return;
      open.disabled = true;
      let ownRelease = null;
      try {
        check(); const id = draft.value.trim(), segmentId = segment.value.trim(); if (!validId(id) || (segmentId && !validId(segmentId))) throw Error('Enter valid IDs');
        if (!navigator.locks?.request) throw Error('Safe desk access unavailable');
        mounted?.destroy(); mounted = null; releaseDeskLock?.(); releaseDeskLock = null; root.replaceChildren();
        // Wait only for this host's previous lock callback to finish releasing.
        await deskLockSettled; check();
        let acquired;
        const ready = new Promise(resolve => { acquired = resolve; });
        deskLockSettled = navigator.locks.request(`${key}:component`, {ifAvailable:true}, async lock => {
          if (!lock) { acquired(false); return; }
          await new Promise(resolve => { ownRelease = resolve; releaseDeskLock = resolve; acquired(true); });
        }).catch(() => acquired(false));
        if (!await ready) throw Error('Desk is open in another tab');
        check();
        const journalPrefix = `${key}:component:`;
        const intentJournal = {
          read: journalKey => { check(); const raw = localStorage.getItem(journalPrefix + journalKey); return raw === null ? null : JSON.parse(raw); },
          write: (journalKey, value) => { check(); localStorage.setItem(journalPrefix + journalKey, JSON.stringify(value)); },
          remove: journalKey => { check(); localStorage.removeItem(journalPrefix + journalKey); }
        };
        const context = {scopeId:scope.actorBinding,sessionId:scope.sessionId,actorId:scope.actorBinding,draftId:id,segmentId,eligible:true,intentJournal,
          readDraft:() => invoke('w22CoeditRead',null,id),
          presence:a => invoke('w22CoeditPresence',{seconds:a.seconds},id),
          readCoeditOperation:a => { const entry = intentJournal.read(JSON.stringify([scope.actorBinding,scope.sessionId,scope.actorBinding,null,null,id,segmentId,true])); if (!entry || entry.requestId !== a.requestId || !['patch','approve','withdraw'].includes(entry.kind)) throw Error('Original request required'); return recoverMarker(a,{kind:entry.kind,...a}); }, recoverAdoption:a => recoverMarker(a,{kind:'adopt',...a}), readTemplateOperation:a => recoverMarker(a,{kind:'template',draftId:id,...a}), recoverTemplateApplication:a => recoverMarker(a,{kind:'apply',draftId:id,templateVersion:a.version,...a}),
          patch:a => mutate('patch',a,() => invoke('w22CoeditPatch',{requestId:a.requestId,baseRevision:a.baseRevision,operations:a.operations},id)),
          approve:a => mutate('approve',a,() => invoke('w22CoeditApprove',{requestId:a.requestId,expectedRevision:a.expectedRevision},id)),
          withdraw:a => mutate('withdraw',a,() => invoke('w22CoeditWithdraw',{requestId:a.requestId,expectedRevision:a.expectedRevision},id)),
          adopt:a => mutate('adopt',a,() => invoke('w24DeskHandoff',{requestId:a.requestId,approvedRevision:a.approvedRevision,segmentId:a.segmentId},id,'adopt')),
          mutateDraftTemplate:a => mutate('template',{...a,draftId:id},() => invoke('w24DeskTemplates',a)),
          applyDraftTemplate:a => {
            if (a.sourceSessionId && (!validId(a.sourceSessionId) || !capability.value)) throw Error('Source capability required');
            return mutate('apply',{...a,draftId:id},async () => {
              if (!a.sourceSessionId) return invoke('w24DeskApply',{requestId:a.requestId,baseRevision:a.baseRevision},a.templateId,a.version,'apply',id);
              check(); const result = await API.call('w24DeskCrossApply',{requestId:a.requestId,baseRevision:a.baseRevision},a.sourceSessionId,a.templateId,a.version,'apply',id,{scope,headers:{'X-Source-Capability':capability.value}}); check(); return result;
            });
          },
          openOperator:async () => { check(); if (scope.role !== 'creator') throw Error('Creator access required'); navTo('studio'); $('#wave19Operator').scrollIntoView(); }
        };
        mounted = mountDesk24(root,context); pendingStatus();
      } catch (error) { ownRelease?.(); if (releaseDeskLock === ownRelease) releaseDeskLock = null; status.textContent = error.message || 'Unable to open this desk.'; }
      finally { open.disabled = false; }
    };
    selectDraft = (selection, captured) => { check(); assertIdentity(captured); if (captured.epoch !== scope.epoch || !validId(selection?.draftId) || !validId(selection?.segmentId)) throw Error('Draft unavailable'); draft.value = selection.draftId; segment.value = selection.segmentId; host.open = true; open.click(); host.scrollIntoView(); };
    pendingStatus();
  }
  return {reset, select(selection,scope) { if (!selectDraft) throw Error('Desk unavailable'); selectDraft(selection,scope); }};
})();
wave24Desk.reset();
// The handoff is an independent saved-access workflow. The server projection
// supplies its actor and grant scope; the local capability namespace does not.
wave28Handoff = (() => {
  let generation = 0, controller = null, release = null;
  const forms = ['#wave22Coedit', '#wave22CoeditViewer'].map(selector => {
    const box = document.createElement('details'), title = document.createElement('summary');
    title.textContent = 'Current handoff';
    const label = document.createElement('label'), input = document.createElement('input');
    label.textContent = 'Draft ID'; input.maxLength = 128; label.append(input);
    const open = document.createElement('button'); open.type = 'button'; open.textContent = 'Open handoff';
    const status = document.createElement('p'); status.setAttribute('role','status');
    const root = document.createElement('div'); box.append(title,label,open,status,root);
    $(selector).insertAdjacentElement('afterend',box);
    return {box,input,open,status,root};
  });
  function reset() {
    generation++; controller?.destroy(); controller = null; release?.(); release = null;
    for (const form of forms) { form.root.replaceChildren(); form.input.value = ''; form.status.textContent = ''; }
  }
  const fields = ['scopeId','sessionId','actorId','role','creatorId','collaboratorId','collaborationId','sourceId','sourceRevision','draftId','revision','grantGeneration','eligible'];
  const same = (a,b) => fields.every(k => a?.[k] === b?.[k]);
  for (const form of forms) {
    form.input.addEventListener('input', () => {
      generation++; controller?.destroy(); controller = null; release?.(); release = null;
      for (const item of forms) { item.root.replaceChildren(); item.status.textContent = ''; }
    });
    form.open.onclick = async () => {
    controller?.destroy(); controller = null; release?.(); release = null;
    for (const item of forms) item.root.replaceChildren();
    const ticket = ++generation, identity = identityScope(), id = form.input.value.trim();
    const check = () => {
      assertSavedIdentity(identity);
      if (ticket !== generation || form.input.value.trim() !== id || sourceContextStale || sourceMutationPending) throw Error('Handoff context changed');
    };
    form.open.disabled = true; form.status.textContent = 'Checking current handoff access…';
    let ownRelease = null;
    try {
      check();
      if (!/^[A-Za-z0-9._:-]{1,128}$/.test(id) || !navigator.locks?.request || !crypto.randomUUID) throw Error('Safe handoff access unavailable');
      const readScope = async () => { check(); const value = await API.call('w28HandoffScope',null,id,{scope:identity}); check(); return value; };
      const current = await readScope();
      if (current?.sessionId !== identity.sessionId || current.draftId !== id || current.role !== identity.role || !current.actorId || current.eligible !== true || (identity.role === 'viewer' && current.actorId !== identity.viewerId)) throw Error('Handoff access unavailable');
      const key = `entrelineas.w28.handoff.v1:${current.sessionId}:${current.actorId}:${id}`;
      let acquired;
      const ready = new Promise(resolve => { acquired = resolve; });
      navigator.locks.request(key,{ifAvailable:true},async lock => {
        if (!lock) { acquired(false); return; }
        await new Promise(resolve => { ownRelease = resolve; acquired(true); });
      }).catch(() => acquired(false));
      if (!await ready) throw Error('Handoff is open in another tab');
      check(); release = ownRelease;
      if (!same(current,await readScope())) throw Error('Handoff context changed');
      let reasonRefs = [];
      const journal = {
        read: k => { check(); const raw = localStorage.getItem(key + ':' + k); return raw === null ? null : JSON.parse(raw); },
        write: (k,v) => { check(); localStorage.setItem(key + ':' + k,JSON.stringify(v)); },
        remove: k => { check(); localStorage.removeItem(key + ':' + k); }
      };
      const request = async (path, options, captured) => {
        const scopeCheck = async () => {
          try { check(); if (!same(current,captured) || !same(current,await readScope())) throw Error('Handoff context changed'); }
          catch (error) {
            if (ticket === generation) {
              generation++; controller?.destroy(); controller = null; release?.(); release = null;
              form.root.replaceChildren(); form.status.textContent = 'Handoff access changed. Open it again to refresh; any original request is preserved.';
            }
            throw error;
          }
        };
        await scopeCheck();
        const base = `/api/sessions/${encodeURIComponent(identity.sessionId)}/w28/handoffs/${encodeURIComponent(id)}`;
        let result;
        if (path === base && options.method === 'GET') result = await API.call('w28HandoffRead',null,id,{scope:identity});
        else if (path === base + '/offer' && options.method === 'POST') result = await API.call('w28HandoffOffer',options.body,id,{scope:identity});
        else if (path === base + '/decide' && options.method === 'POST') result = await API.call('w28HandoffDecide',options.body,id,{scope:identity});
        else {
          const prefix = base + '/receipts/';
          if (options.method !== 'GET' || !path.startsWith(prefix)) throw Error('Invalid handoff request');
          const requestId = decodeURIComponent(path.slice(prefix.length));
          if (!/^[A-Za-z0-9._:-]{1,128}$/.test(requestId)) throw Error('Invalid receipt');
          result = await API.call('w28HandoffReceipt',null,id,requestId,{scope:identity});
        }
        await scopeCheck();
        if (path === base && options.method === 'GET') reasonRefs = Array.isArray(result?.reasonRefs) ? result.reasonRefs : [];
        return result;
      };
      controller = mountHandoff28(form.root, {getScope:()=>current, isCurrent:s => { try { check(); return same(s,current); } catch { return false; } },
        savedAccess:true, intentJournal:journal, request, newRequestId, currentReasonRefs:()=>reasonRefs});
      form.status.textContent = 'Current access verified. Refresh the handoff to continue.';
    } catch (error) {
      ownRelease?.(); if (release === ownRelease) release = null;
      if (ticket === generation) form.status.textContent = 'Handoff unavailable. Refresh access and try again; any original request remains preserved.';
    } finally { form.open.disabled = false; }
    };
  }
  return {reset};
})();
// Creator reads a single explicitly supplied result ID through the existing guarded projection.
const w20CreatorReader = $("#w20CreatorPracticeReader");
var w20CreatorGeneration;
function w20CreatorClear(clearId = true) { w20CreatorGeneration = (w20CreatorGeneration || 0) + 1; const reader = document.querySelector("#w20CreatorPracticeReader"); if (reader) { reader.querySelector("[data-result]").textContent = ""; reader.querySelector("[data-status]").textContent = ""; if (clearId) reader.querySelector("[data-id]").value = ""; } }
w20CreatorReader.querySelector("[data-id]").addEventListener("input", () => w20CreatorClear(false));
w20CreatorReader.querySelector("[data-read]").addEventListener("click", async () => {
  w20CreatorClear(false);
  const generation = w20CreatorGeneration, scope = identityScope(), id = w20CreatorReader.querySelector("[data-id]").value.trim();
  const status = w20CreatorReader.querySelector("[data-status]");
  try {
    assertSavedIdentity(scope);
    if (!id) { status.textContent = "Enter a result ID to read a selected result."; return; }
    if (scope.role !== "creator" || !/^[A-Za-z0-9._:-]{1,128}$/.test(id) || sourceContextStale) throw Error("unavailable");
    status.textContent = "Loading selected result...";
    const data = await API.call("w20CreatorPracticeShare", null, id, {scope});
    assertSavedIdentity(scope);
    if (generation !== w20CreatorGeneration) return;
    w20CreatorReader.querySelector("[data-result]").textContent = data.share.summary || "";
    status.textContent = "Selected result loaded. Refresh to recheck availability.";
  } catch { if (generation === w20CreatorGeneration) { w20CreatorClear(false); status.textContent = "Selected result unavailable. Check its ID and current access."; } }
});
wave20Practice = mountPractice($('#wave20Practice'), wave19FeatureAPI, identityScope, assertSavedIdentity, {
  savedPriorAccess:(scope)=>{assertIdentity(scope);if(tabOnlyAccess)return [];return Object.keys(localStorage).filter(key=>key.startsWith('entrelineas.identity.v1:')||key.startsWith('entrelineas.identity.v2:')).flatMap(key=>{try{const item=JSON.parse(localStorage.getItem(key));if(item?.role!=='viewer'||typeof item.sessionId!=='string'||typeof item.token!=='string'||!item.sessionId||!item.token||item.sessionId===scope.sessionId)return [];return [{sessionId:item.sessionId,token:item.token,label:`${item.session?.displayName || 'Viewer'} · ${item.session?.channel || item.sessionId}`}];}catch{return [];}});},
  openPriorAttempt:()=>{navTo('practice');$('#practiceHistoryList').scrollIntoView();},
  openSource: openCurrentAudienceSource
});
// Text uses the current authorized source; audio requires the guarded scheduler.
wave20Delivery = mountDelivery($('#wave20Delivery'), wave19FeatureAPI, identityScope, assertSavedIdentity, {
  playReady: (result, selection, scope, checkCurrent) => phase12Controller.playDelivery(result, scope, checkCurrent),
  stopPlayback: () => phase12Controller?.stopDelivery(),
  listSources: async scope => { assertIdentity(scope); const data=await API.call('w20DeliverySources', null, {scope}); assertIdentity(scope); return data; },
  openText: async (selection, scope) => {
    assertIdentity(scope);
    if (!selection.source.startsWith('record:')) {
      if (!phase12Controller) throw Error('Text for this source is unavailable here');
      return phase12Controller.deliveryText(selection, scope);
    }
    const data = await API.call('w18RecordView', null, selection.source.slice(7), selection.language, {scope});
    assertIdentity(scope);
    const record = data?.record;
    if (!record || record.id !== selection.source.slice(7) || record.version !== selection.sourceRevision || record.language !== selection.language || record.fallback || !['creator_authored', 'creator_reviewed_translation'].includes(record.provenance) || typeof record.interpretation !== 'string') throw Error('Record changed');
    return {text: record.interpretation, provenance: record.provenance};
  },
  getPolicy: async scope => { assertIdentity(scope); if(scope.role!=='creator') throw Error('Creator access required'); const data=await API.call('w20PolicyGet', null, {scope}); assertIdentity(scope); return data; },
  admit: (body, scope) => API.call('w20DeliveryAdmit', body, {scope}),
  lookupReceipt: (body, scope) => API.call('w20DeliveryReceipt', body, {scope}),
  view: (ticket, scope) => API.call('w20DeliveryView', null, ticket, {scope}),
  cancel: (ticket, scope) => API.call('w20DeliveryCancel', null, ticket, {scope}),
});
const policyCall = async (operation, body, scope) => { const result = await API.call(operation, body, {scope}); assertIdentity(scope); return result; };
wave20Policy = mountPolicy($('#wave20Policy'), wave19FeatureAPI, identityScope, assertSavedIdentity, {
  getPolicy: scope => policyCall('w20PolicyGet', null, scope),
  savePolicy: (body, scope) => policyCall('w20PolicySave', body, scope),
  lookupReceipt: (body, scope) => policyCall('w19_20Receipt', body, scope),
  admit: (body, scope) => policyCall('w20PolicyAdmit', body, scope),
  atomicRecoveryAvailable: () => true,
});
const openWave19Captions = () => { navTo(state.role === 'creator' ? 'studio' : 'audience'); phase12Controller?.focusCaptions(); };
const focusWave19 = (selector) => { if(state.role !== 'creator') return; navTo('studio'); const target=$(selector); target.scrollIntoView({block:'start'}); target.focus({preventScroll:true}); };
wave19Entry = mountEntry($('#wave19Entry'), API, identityScope, assertIdentity, { language:()=>state.lang, setLanguage:value=>{const input=$('#language');input.value=value;input.dispatchEvent(new Event('change'));}, openCaptions:openWave19Captions, openContext:()=>$('#contextDetails').click() });
wave19Setup = mountSetup($('#wave19Setup'), {readiness:async()=>{const scope=identityScope();if(scope.role!=='creator')throw Error();const result=await API.call('w19Readiness',null,{scope});assertIdentity(scope);return result;},sources:()=>$('#contextDetails').click(), preview:openWave19Captions, invitation:()=>{const details=$('#invitationUrlValue').closest('details');details.open=true;details.querySelector('summary').focus();details.scrollIntoView();}, copy:()=>$('#copyJoinCode').click()});
wave19Operator = mountOperator($('#wave19Operator'), {creator: true, credentials: () => { const scope=identityScope(); assertSavedIdentity(scope); if(scope.role!=='creator'||!scope.token||!scope.sessionId) throw Error('Creator access required'); return {sessionId:scope.sessionId, token:scope.token, valid:()=>assertSavedIdentity(scope)}; }, workspace:()=>focusWave19('#wave18Refresh')});
let helperOperator = null, helperEntryBusy = false;
$('#operatorEnter').addEventListener('click', async () => {
  if (helperEntryBusy || helperOperator) return;
  if (tabOnlyAccess) { $('#operatorEntryStatus').textContent = 'Helper preparation requires saved access to protect request recovery.'; return; }
  const helperEpoch = state.identityEpoch;
  const sessionId=$('#operatorSession').value.trim(), token=$('#operatorCapability').value.trim();
  if(!sessionId || !token){ $('#operatorEntryStatus').textContent='Enter both session ID and preparation capability.'; return; }
  const status=$('#operatorEntryStatus'); status.textContent='Checking preparation access…';
  helperEntryBusy = true;
  try {
    const response=await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/w19/operator/state`,{headers:{Authorization:`Bearer ${token}`,Accept:'application/json'},credentials:'same-origin'});
    if(!response.ok) throw Error();
    const view=await response.json(); if(tabOnlyAccess || helperEpoch !== state.identityEpoch || !Array.isArray(view.segments)) throw Error();
    $('#operatorCapability').value=''; document.querySelectorAll('dialog[open]').forEach(d=>d.close());
    document.body.classList.add('operator-helper-mode'); $('#operatorHelper').hidden=false;
    let active=true; const root=$('#operatorHelper'); root.replaceChildren();
    const exit=document.createElement('button'); exit.type='button'; exit.textContent='Exit helper view'; root.append(exit);
    helperOperator=mountOperator(root,{creator:false,credentials:()=>({sessionId,token,valid:()=>{if(!active || tabOnlyAccess || helperEpoch !== state.identityEpoch)throw Error('Access ended');}})});
    closeHelperOperator=()=>{active=false;helperOperator.reset();helperOperator=null;closeHelperOperator=null;root.replaceChildren();root.hidden=true;document.body.classList.remove('operator-helper-mode');status.textContent='Helper access ended.';};
    exit.onclick=closeHelperOperator;
    await helperOperator.refresh();
  } catch {if(helperEpoch === state.identityEpoch && !tabOnlyAccess) status.textContent='Preparation access could not be confirmed. Check the session and capability or ask the creator.';} finally {helperEntryBusy = false;}
});
wave19Answers = mountInboxAnswers($("#wave19Answers"), API, identityScope, assertIdentity, {openMoment:openWave15Moment, openQuestions:()=>{if(state.role!=="viewer")return;navTo("audience");const details=[...$("#p12Root").querySelectorAll("details")].find(x=>x.querySelector("summary")?.textContent==="Shared questions and answers");if(details){details.open=true;details.querySelector("summary").focus();details.scrollIntoView();}}});
wave19Inbox = mountInbox($('#wave19Inbox'), API, identityScope, assertSavedIdentity, {openMoment:openWave15Moment,review:()=>{if(state.role!=='creator')return;navTo('studio');const details=[...$('#p12Root').querySelectorAll('details')].find(x=>x.querySelector('summary')?.textContent==='Shared questions and answers');if(details){details.open=true;details.querySelector('summary').focus();details.scrollIntoView();}else $('#p12CreatorSlot').scrollIntoView();}});
const wave18ListeningFence = createSegmentListeningFence(identityScope, assertIdentity, assertSavedIdentity);
wave18Segment = mountSegment($("#wave18Segment"), API, identityScope, assertIdentity, {
  journalMode: () => tabOnlyAccess ? "memory" : "saved",
  onContextChanged: context => {
    const clearOwnedSelection = wave18ListeningFence.owns(phase12Controller?.selectedCaption());
    const change = wave18ListeningFence.setContext(context);
    if (change.changed && change.stopPrevious && clearOwnedSelection) phase12Controller?.reset();
    else if (change.changed && change.stopPrevious) phase12Controller?.invalidateSources();
    wave18Assistance.setContext(context); wave19Operator?.setContext(context);
  },
  readListeningControls: () => readListeningControls($("#p12Root")),
  openListening: async (context, scope) => {
    assertIdentity(scope);
    if (scope.role !== "creator" || context?.dependencyState !== "current") throw Error("Current creator source required");
    navTo("studio");
    await wave18ListeningFence.open(context, ref => phase12Controller.focusCaptions(ref));
    assertIdentity(scope);
    const selected = phase12Controller.selectedCaption();
    if (!wave18ListeningFence.isCurrent(context) || !selected || !sameListeningRef(selected, context.sourceRef)) throw Error("Current ASR source is unavailable");
    $("#p12Root").scrollIntoView({block:"start"});
  },
  openQuestions: () => { navTo("studio"); $("#p12CreatorSlot").scrollIntoView(); },
  openParticipation: () => { navTo("studio"); $("#waveCreatorSlot").scrollIntoView(); },
  openCoedit: (selection, scope) => { assertIdentity(scope); navTo("studio"); coeditSetup.selectMaterial(selection, scope); },
});

$("#wave18Refresh").addEventListener("click", () => { wave18Segment.refresh(); });
$("#wave18AssistanceRefresh").addEventListener("click", () => { if (!tabOnlyAccess) wave18Assistance.refresh(); });
$("#wave18Speech").addEventListener("click", () => { navTo("studio"); $("#p12CreatorSlot").scrollIntoView(); });

function mountSavedFormats(root) {
  // The component's two persistent recovery buttons read their journal before
  // checking identity. Fence those callbacks at the host lifecycle boundary.
  const savedScope = () => { const scope = identityScope(); assertSavedIdentity(scope); return scope; };
  const component = mountFiniteFormats(root, API, savedScope, assertSavedIdentity, () => phase10Controller?.refreshStudioCollection());
  const formatRoot = root.lastElementChild;
  const controls = ['[data-check]', '[data-retry]'].map(selector => {
    const element = formatRoot.querySelector(selector);
    return {element, action: element.onclick};
  });
  let generation = 0;
  const activate = () => {
    const ticket = ++generation;
    let scope = null;
    try { scope = savedScope(); } catch { /* No saved identity is active. */ }
    for (const {element, action} of controls) element.onclick = (...args) => {
      try { if (!scope || ticket !== generation) return; assertSavedIdentity(scope); }
      catch { return; }
      return action(...args);
    };
  };
  const refreshButton = formatRoot.querySelector('[data-refresh]');
  refreshButton.onclick = (...args) => { activate(); return component.refresh(...args); };
  return {
    activate,
    reset() { ++generation; component.reset(); },
    invalidate() { ++generation; component.invalidate(); },
    refresh: (...args) => { activate(); return component.refresh(...args); },
    focusRound: (...args) => { activate(); return component.focusRound(...args); },
    focusFormat: (...args) => { activate(); return component.focusFormat(...args); },
  };
}
wave15Formats = mountSavedFormats($("#waveModelPreview"));
// A separate, explicitly opted-in creator path preserves the saved-access component.
function mountTabOnlyDecisions(root) {
  const panel=document.createElement('section'); panel.dataset.tabOnlyRead=''; panel.className='p6-card';
  panel.innerHTML='<details><summary>Creator choices with tab-only access</summary><p>Choose whether to protect action recovery on this device. Only encrypted request data is stored. Unconfirmed actions are checked by receipt and never resent automatically.</p><label><input type="checkbox" data-opt> Protect recovery for these actions</label><button type="button" data-refresh>Refresh current choices</button><button type="button" data-receipt>Check previous action receipt</button><p role="status" data-status></p><div data-create></div><div data-list></div></details>';
  root.append(panel); const q=x=>panel.querySelector(x), status=q('[data-status]'); let ticket=0;
  const field=(parent,label,multi=false)=>{const l=document.createElement('label'),input=document.createElement(multi?'textarea':'input');l.textContent=label+' ';l.append(input);parent.append(l);return input;};
  const button=(parent,label,action)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.onclick=action;parent.append(b);return b;};
  function context(){const scope=identityScope(), generation=ticket;const current=()=>{try{assertIdentity(scope);return tabOnlyAccess && scope.role==='creator' && panel.isConnected && generation===ticket;}catch{return false;}};if(!current() || !q('[data-opt]').checked)throw Error('Opt in with creator access');return {scope,current,action:createProtectedFormatAction({scope,isCurrent:current,call:API.call})};}
  q('[data-opt]').onchange=()=>{ticket++;q('[data-list]').replaceChildren();status.textContent='Refresh current choices before acting.';};
  q('[data-receipt]').onclick=async()=>{let ctx;try{ctx=context();await ctx.action.readback();status.textContent='Previous action confirmed. Refresh current choices.';}catch{status.textContent='No confirmed receipt is available. Any pending action remains preserved.';}finally{ctx?.action.destroy();}};
  const create=q('[data-create]');const title=field(create,'Title'),question=field(create,'Question',true),options=field(create,'Distinct options, one per line',true);
  button(create,'Create choice',async()=>{let ctx;try{const list=options.value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);if(!title.value.trim()||!question.value.trim()||list.length<2||list.length>20||new Set(list).size!==list.length)throw Error('Enter title, question and 2–20 distinct options');ctx=context();await ctx.action.submit('w15CreateFormat',{type:'choice',title:title.value.trim(),question:question.value.trim(),options:list,cards:[],refs:[]});status.textContent='Choice confirmed. Refresh to record a decision.';}catch{status.textContent='Choice not confirmed. Check the receipt before another action.';}finally{ctx?.action.destroy();}});
  q('[data-refresh]').onclick=async()=>{let ctx;const generation=++ticket;q('[data-list]').replaceChildren();try{ctx=context();const r=await API.call('w15Formats',null,{scope:ctx.scope});if(!ctx.current()||generation!==ticket||!Array.isArray(r.formats)||!Array.isArray(r.contributions))throw Error('Current choices unavailable');for(const f of r.formats){if(!f?.id||!Number.isSafeInteger(f._revision))continue;const card=document.createElement('article'),heading=document.createElement('h3');heading.textContent=f.title;card.append(heading);const prompt=document.createElement('p');prompt.textContent=f.question;card.append(prompt);for(const item of (f.type==='choice'?f.options:f.cards)||[]){const option=document.createElement('p');option.textContent=item;card.append(option);}if(f.decision){const prior=document.createElement('p');prior.textContent='Current decision: '+f.decision.decision+' · Consequence: '+f.decision.consequence;card.append(prior);}const reason=[];for(const c of r.contributions.filter(x=>x.formatId===f.id&&x.status==='accepted')){const l=document.createElement('label'),pick=document.createElement('input'),minor=document.createElement('input');pick.type=minor.type='checkbox';l.append(pick,document.createTextNode(' Consider: '+c.selection+' · '+(c.reason||'No reason')+' '),minor,document.createTextNode(' Minority position'));card.append(l);reason.push({id:c.id,pick,minor});}const decision=field(card,'Decision',true),consequence=field(card,'Consequence',true);button(card,'Save decision',async()=>{let act;try{if(!decision.value.trim()||!consequence.value.trim()||reason.some(x=>x.minor.checked&&!x.pick.checked))throw Error('Decision incomplete');act=context();if(generation!==ticket)throw Error('Refresh needed');await act.action.submit('w15FormatDecision',{revision:f._revision,reasonIds:reason.filter(x=>x.pick.checked).map(x=>x.id),minorityIds:reason.filter(x=>x.minor.checked).map(x=>x.id),decision:decision.value.trim(),consequence:consequence.value.trim()},f.id);status.textContent='Decision confirmed. Refresh current choices and record options.';}catch{status.textContent='Decision not confirmed. Check the receipt before another action.';}finally{act?.action.destroy();}});q('[data-list]').append(card);}status.textContent='Current choices loaded.';}catch{status.textContent='Current choices could not be loaded.';}finally{ctx?.action.destroy();}};
}
mountTabOnlyDecisions($("#waveModelPreview"));
wave17Return = mountReturn($("#catchupPanel"), API, identityScope, assertIdentity, openWave15Moment, async (action,scope) => {
  assertIdentity(scope);
  if(action.type==='open_chapter') { navTo('audience'); await wave15Viewer.focusChapter(action.id); }
  else if(action.type==='open_format') { navTo('audience'); await wave15Formats.focusFormat(action.id); }
  else throw Error('Unsupported action');
  assertIdentity(scope);
}, () => !tabOnlyAccess);
function mountSavedTemplates(root) {
  const component = mountTemplates(root, API, identityScope, assertSavedIdentity, (formatId, roundId) => wave15Formats?.focusRound(formatId, roundId), {exportDefinition:(id,scope)=>API.call("w19OwnedLibraryExport",null,id,{scope})});
  const templateRoot = root.lastElementChild, replay = templateRoot.querySelector('[data-replay]');
  const replayAction = replay.onclick;
  let generation = 0;
  const activate = () => {
    const ticket = ++generation;
    let scope = null;
    try { scope = identityScope(); assertSavedIdentity(scope); } catch { scope = null; }
    replay.onclick = (...args) => {
      try { if (!scope || ticket !== generation) return; assertSavedIdentity(scope); } catch { return; }
      return replayAction(...args);
    };
  };
  const refreshButton = templateRoot.querySelector('[data-refresh]'), refreshAction = refreshButton.onclick;
  refreshButton.onclick = (...args) => { activate(); return refreshAction(...args); };
  return {activate, reset() { ++generation; component.reset(); },
    refresh(...args) { activate(); return component.refresh(...args); },
    prefillDefinition(...args) { activate(); return component.prefillDefinition(...args); },
    selectTemplate(...args) { activate(); return component.selectTemplate(...args); }};
}
wave17Templates = mountSavedTemplates($("#waveModelPreview"));
waveFormats = mountFormats($("#waveModelPreview"), API, identityScope, assertSavedIdentity);
wavePublishedModels = mountPublishedModels($("#waveModelPreview"), API, identityScope, assertIdentity);
phase11Controller = createPhase11Controller({ api: API, identityScope, assertIdentity: assertSavedIdentity, root: $("#p11Root"), onRightsChange:()=>collaborationController?.invalidateRights(), onContextChange:()=>phase12Controller?.invalidateCollaboration() });
collaborationController = createCollaboration({root: $("#p12CollaborationRoot"), api: API, identityScope, assertIdentity: assertSavedIdentity, activityAccess:()=>phase11Controller?.translationAccess(), onInvalidate:()=>phase12Controller?.invalidateCollaboration()});
phase12Controller = createPhase12({ api: API, identityScope:wave18ListeningFence.identityScope, assertIdentity:wave18ListeningFence.assertIdentity, assertSavedIdentity:wave18ListeningFence.assertSavedIdentity, activityAccess:()=>phase11Controller?.translationAccess()||phase11Controller?.observationAccess(), collaborationAccess:()=>collaborationController?.translationSelection(), onPrivateChange:()=>waveQuestions?.invalidate(), root: $("#p12Root") });
waveQuestions = mountQuestions($("#p12Root"), API, identityScope, assertIdentity, {caption:()=>phase12Controller.selectedCaption(), translate:(selection,language)=>phase12Controller.translateExchange(selection,language), invalidate:()=>phase12Controller.invalidateExchange(), returnToCaptions:(ref)=>phase12Controller.focusCaptions(ref), privateTranscript:()=>phase12Controller.privateTranscript()});
resumeAccess = mountResumeAccess($("#resumeAccess"), {
  generation: () => state.identityEpoch,
  async verify(request) {
    const generation = state.identityEpoch;
    const identity = await verifyResumeAccess(request);
    const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("entrelineas-capability-v1\0" + request.credential));
    const binding = Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, "0")).join("");
    const sources = await fetch(`/api/sessions/${encodeURIComponent(identity.sessionId)}/sources`, {method:"GET", headers:{Authorization:`Bearer ${request.credential}`}, signal:request.signal, cache:"no-store", credentials:"same-origin", redirect:"error"});
    if (!sources.ok) throw new Error("Source access unavailable");
    await sources.json();
    const current = await verifyResumeAccess(request);
    if (request.signal.aborted || generation !== state.identityEpoch || current.actorId !== identity.actorId || current.role !== identity.role || current.expiresAt !== identity.expiresAt) throw new Error("Access changed");
    return {...current, binding};
  },
  commit(identity, credential, options) {
    const expiry = Date.parse(identity.expiresAt);
    if (!['tab-only', 'saved'].includes(options.mode) || options.signal.aborted || options.generation !== state.identityEpoch || !['creator', 'viewer'].includes(identity.role) || !Number.isFinite(expiry) || expiry <= Date.now() || !identity.binding) return false;
    // Prevent a reload from silently restoring a different saved identity.
    // Saved identities and their private histories remain untouched.
    let storageUnavailable = false;
    try { localStorage.removeItem("entrelineas.identity.active"); }
    catch { storageUnavailable = true; }
    resetIdentityState(true, true);
    tabOnlyAccess = true;
    // Drop saved-access button closures before installing the tab-only actor.
    renderSavedIdentities();
    Object.assign(state, {sessionId:identity.sessionId, session:identity.session, token:credential, role:identity.role, viewerId:identity.role === 'viewer' ? identity.actorId : null});
    capabilityNamespace = identity.binding;
    let outcome = 'tab-only';
    if (options.mode === 'saved') {
      const identityPart = state.role === 'viewer' ? `:${state.viewerId}` : '';
      const key = `entrelineas.identity.v2:${state.role}:${state.sessionId}${identityPart}:${capabilityNamespace}`;
      let previous = null, readPrevious = false;
      try {
        if (storageUnavailable) throw new Error('Storage unavailable');
        previous = localStorage.getItem(key); readPrevious = true;
        tabOnlyAccess = false;
        saveIdentity();
        const saved = JSON.parse(localStorage.getItem(key));
        if (localStorage.getItem('entrelineas.identity.active') !== key || saved?.token !== credential || saved?.sessionId !== identity.sessionId || saved?.role !== identity.role || saved?.viewerId !== state.viewerId) throw new Error('Storage could not be confirmed');
        outcome = 'saved';
      } catch {
        tabOnlyAccess = true;
        try { localStorage.removeItem('entrelineas.identity.active'); if (readPrevious) { if (previous === null) localStorage.removeItem(key); else localStorage.setItem(key, previous); } } catch { /* storage failure may prevent rollback */ }
        outcome = 'save-failed';
      }
    }
    wave15Viewer?.activate(); wave15Creator?.activate();
    const scope = identityScope();
    const expire = () => {
      if (scope.epoch !== state.identityEpoch) return;
      const remaining = Date.parse(identity.expiresAt) - Date.now();
      if (remaining > 0) { tabOnlyExpiryTimer = setTimeout(expire, Math.min(remaining, 2147483647)); return; }
      if (scope.role === 'viewer') viewerAccessLost(scope);
      else { resetIdentityState(); if (!$("#accessDialog").open) $("#accessDialog").showModal(); showError($("#accessError"), "This tab's access expired. Enter current access to continue."); }
    };
    expire();
    if (scope.epoch !== state.identityEpoch) return false;
    if ($("#accessDialog").open) $("#accessDialog").close();
    void loadCore();
    return outcome;
  }
});
const startupInvitation = parseInvitationSearch(location.search);
if (startupInvitation.present) {
  const identityParams = new URLSearchParams(location.search);
  identityParams.delete("sessionId"); identityParams.delete("joinCode");
  const remaining = identityParams.toString();
  history.replaceState(null, "", location.pathname + (remaining ? "?" + remaining : "") + location.hash);
  beginAccess("join");
  renderSavedIdentities();
  if (!$("#accessDialog").open) $("#accessDialog").showModal();
  if (startupInvitation.ok) {
    $("#joinSessionId").value = startupInvitation.sessionId; $("#joinCode").value = startupInvitation.joinCode;
    showError($("#accessError"), "Invitation details are ready for review. Check both fields, then select Join session. This does not verify validity or restore prior private history.");
  } else {
    showError($("#accessError"), startupInvitation.error || "This invitation is incomplete or malformed. Ask the creator for a current link.");
  }
} else {
  // A reload cannot infer whether the previous identity was tab-only. Require an
  // explicit saved-access choice, preserving every existing recovery journal.
  loadCore(false);
}
$("#prepareInvitation").addEventListener("click", () => {
  const result = parseInvitationText($("#invitationPaste").value);
  if (!result.ok) { showError($("#accessError"), result.error); return; }
  $("#joinSessionId").value = result.sessionId;
  $("#joinCode").value = result.joinCode;
  showError($("#accessError"), "Invitation details are ready for review. Check both fields, then select Join session. This does not verify validity or restore prior private history.");
});
[
  "question",
  "shareText",
  "practiceGoal",
  "practiceAttempt",
  "editorialFocus",
].forEach((id) => $(`#${id}`).addEventListener("input", () => persistDraft()));
for (const [id, eventName] of [["questionSource", "change"], ["questionMoment", "input"], ["practiceDifficulty", "change"]]) {
  $(`#${id}`).addEventListener(eventName, () => {
    const scope = identityScope();
    if (scope.token) persistDraft(scope);
  });
}
function invalidateShareReview() {
  if (!state.shareReviewSnapshot) return;
  state.shareReviewSnapshot = null;
  const review = $("#shareReview");
  review.hidden = true;
  review.replaceChildren();
  $("#shareConsent").checked = false;
  $("#sharePublicConsent").checked = false;
  $("#shareIncludeImage").checked = false;
  showError(review, t("shareReviewChanged"));
}
$("#shareText").addEventListener("input", invalidateShareReview);
$("#shareConsent").addEventListener("change", invalidateShareReview);
$("#sharePublicConsent").addEventListener("change", invalidateShareReview);
$("#shareIncludeImage").addEventListener("change", invalidateShareReview);
$("#shareSource").addEventListener("change", () => {
  invalidateShareReview();
  $("#shareIncludeImage").disabled =
    $("#shareSource").value !== "attempt" || !state.lastPracticeImage;
  if ($("#shareIncludeImage").disabled) $("#shareIncludeImage").checked = false;
});
$("#shareIncludeImage").disabled = true;
new MutationObserver(() => {
  const review = $("#shareReview");
  if (
    review.hidden ||
    !$("#shareIncludeImage").checked ||
    !state.lastPracticeImage ||
    review.querySelector("img")
  )
    return;
  const image = document.createElement("img");
  image.src = state.lastPracticeImage;
  image.alt = t("shareIncludeImage");
  image.className = "share-image-preview";
  review.append(image);
}).observe($("#shareReview"), { childList: true });
$("#copyJoinCode").addEventListener("click", async () => {
  if (!state.sessionId || !state.joinCode) return;
  const scope = identityScope();
  const link = state.session?.invitationUrl || `Session ID: ${state.sessionId}\nInvitation code: ${state.joinCode}\nA public viewer address is not configured.`;
  try {
    await navigator.clipboard.writeText(link);
    assertIdentity(scope);
    toast(state.session?.invitationUrl ? "Invitation copied. External availability is not verified." : "Session ID and code copied; no public viewer address is configured.");
  } catch {
    if (scope.epoch !== state.identityEpoch) return;
    window.prompt(t("publicAccess"), link);
  }
});
$("#copyStageUrl").addEventListener("click", async () => {
  const scope = identityScope();
  const stageUrl = $("#stageUrlValue").textContent;
  if (!stageUrl || stageUrl === "—") return;
  try {
    await navigator.clipboard.writeText(stageUrl);
    assertIdentity(scope);
    toast(t("copyUrl"));
  } catch {
    if (scope.epoch !== state.identityEpoch) return;
    window.prompt(t("copyUrl"), stageUrl);
  }
});
$("#sessionForm").addEventListener(
  "submit",
  async (e) => {
    e.preventDefault();
    e.stopImmediatePropagation();
    const existing = new Set(
        normalizeList(state.context)
          .map((s) => s.text)
          .filter(Boolean),
      ),
      items = $("#sessionMaterials")
        .value.split("\n")
        .map((x) => x.trim())
        .filter((x) => x && !existing.has(x)),
      btn = $("#saveSession");
    if (tabOnlyAccess && items.length) {
      showError($("#sessionError"), "Adding sources requires saved access to protect recovery.");
      return;
    }
    clearError($("#sessionError"));
    setBusy(btn, true, t("sending"));
    const scope = identityScope();
    try {
      for (const text of items) {
        assertIdentity(scope);
        await API.call(
          "addSource",
          {
            kind: /^https?:\/\//i.test(text) ? "reference" : "note",
            title: /^https?:\/\//i.test(text)
              ? text
              : state.lang === "es"
                ? "Referencia del creador"
                : "Creator reference",
            text,
            audienceVisible: $("#materialsAudienceVisible").checked,
          },
          { scope },
        );
        assertIdentity(scope);
      }
      await refreshSources(scope);
      assertIdentity(scope);
      $("#sessionDialog").close();
      toast(t("sessionSaved"));
    } catch (error) {
      if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
        return;
      showError(
        $("#sessionError"),
        error.status === 409 ? t("staleError") : t("sessionFailed"),
      );
    } finally {
      if (scope.epoch === state.identityEpoch) setBusy(btn, false);
    }
  },
  true,
);
$("#contextSources").addEventListener(
  "click",
  async (e) => {
    const b = e.target.closest(".source-retract");
    if (!b) return;
    e.stopImmediatePropagation();
    if (tabOnlyAccess) { toast("Withdrawing a source requires saved access for recovery."); return; }
    if (sourceContextStale || sourceMutationPending) return;
    const scope = identityScope();
    sourceMutationPending = true;
    wave27Chapters?.reset();
    $$(".source-visible, .source-retract").forEach(control => control.disabled = true);
    try {
      await API.call("sourceUpdate", { status: "retracted" }, b.dataset.id, {
        scope,
      });
      assertIdentity(scope);
      if (state.captureSourceId === b.dataset.id) {
        state.captureSourceId = null;
        $("#captureStatus").textContent = t("captureStopped");
        $("#stopCapture").disabled = true;
      }
      await refreshSources(scope);
    } catch (error) {
      if (scope.epoch !== state.identityEpoch || error.name === "AbortError")
        return;
      toast(error.status === 409 ? t("staleError") : t("genericError"));
    } finally {
      if (scope.epoch === state.identityEpoch) {
        sourceMutationPending = false;
        if (!sourceContextStale) $$(".source-visible, .source-retract").forEach(control => control.disabled = false);
      }
    }
  },
  true,
);
window.addEventListener("pagehide", clearCaptureDraft);
