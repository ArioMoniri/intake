/**
 * `@intake/admin-web` — the console's typed surface (INT-183, INT-189).
 *
 * The app is assembled module by module inside the INT-180 admin shell; this
 * index is the public API of what exists today: the Models & self-hosting
 * registry module (files/08 §148), the measurement discipline every figure on
 * the console must pass through (CLAUDE.md invariant 20), and the Compliance
 * module (files/08 §4 — vendor-transfer register, consent coverage, audit
 * search, DSAR queue and evidence export).
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
