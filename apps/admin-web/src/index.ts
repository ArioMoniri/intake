/**
 * `@intake/admin-web` — the console's typed surface (INT-183, INT-189, INT-184).
 *
 * The app is assembled module by module inside the INT-180 admin shell; this
 * index is the public API of what exists today: the Models & self-hosting
 * registry module (files/08 §148), the measurement discipline every figure on
 * the console must pass through (CLAUDE.md invariant 20), the Compliance
 * module (files/08 §4 — vendor-transfer register, consent coverage, audit
 * search, DSAR queue and evidence export), and the Protocols module (files/09
 * §1-4 — branch × maturity matrix, the four-eyes review queue for learning
 * proposals, and clip coverage per voice).
 */
export {
  InconsistentReleaseState,
  renderModelsModule,
  type BenchmarkLane,
  type BlockReason,
  type Cell,
  type Finding,
  type LanePresentation,
  type ModelsPayload,
  type ModelsPresentation,
  type ModelsRow,
  type RowPresentation,
  type Severity,
} from "./models/module";
export { UnlabelledMeasurement, renderMeasurement, type Measurement } from "./models/measurement";
export {
  ChainMaterialLeaked,
  MissingLawfulBasis,
  UnsafeExportCell,
  renderAuditSearch,
  renderComplianceModule,
  renderConsentCoverage,
  renderDsarQueue,
  renderEvidenceBundle,
  renderVendorRegister,
  type AuditRow,
  type AuditSearchPayload,
  type CompliancePayload,
  type CompliancePresentation,
  type ConsentCoveragePayload,
  type ConsentRow,
  type DsarQueuePayload,
  type DsarRow,
  type EvidencePayload,
  type EvidencePresentation,
  type RegisterCell,
  type VendorRegisterPayload,
  type VendorRow,
} from "./compliance/module";
export {
  ClipsUnderTypedProfile,
  ForbiddenProposalTarget,
  IncompleteEvidenceApprovable,
  InconsistentClipCounts,
  L0CountedAsCoverage,
  renderClipCoverage,
  renderCoverageMatrix,
  renderProtocolsModule,
  renderReviewQueue,
  SelfApprovalWouldBeRendered,
  type Cell as ProtocolsCell,
  type ClipCoveragePayload,
  type ClipCoveragePresentation,
  type ClipVoice,
  type ClipVoicePresentation,
  type Control,
  type CoveragePayload,
  type CoverageRow,
  type CoverageSummary,
  type MatrixPresentation,
  type MatrixRow,
  type MissingClip,
  type ProtocolsPayload,
  type ProtocolsPresentation,
  type ResolutionStatus,
  type ReviewQueuePayload,
  type ReviewQueuePresentation,
  type ReviewRow,
  type ReviewRowPresentation,
} from "./protocols/module";
