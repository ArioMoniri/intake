/**
 * `@intake/admin-web` — the console's typed surface (INT-183, INT-189, INT-184).
 *
 * The app is assembled module by module inside the INT-180 admin shell; this
 * index is the public API of what exists today: the Models & self-hosting
 * registry module (files/08 §148), the measurement discipline every figure on
 * the console must pass through (CLAUDE.md invariant 20), the Compliance
 * module (files/08 §4 — vendor-transfer register, consent coverage, audit
 * search, DSAR queue and evidence export), the Protocols module (files/09
 * §1-4 — branch × maturity matrix, the four-eyes review queue for learning
 * proposals, and clip coverage per voice), the Clinical Quality & Safety
 * module (files/08 §4 D/E — triage events, the false-RED annotation queue,
 * PolicyGuard classes, and acceptance by specialty), and the Experience &
 * Satisfaction module (files/08 §3, §4 F/G — CSAT/NPS/clinician-pulse rollups,
 * the branch/profile/clinic filter mechanism, and the SDS-01 style export),
 * and the Security module (files/08 §3, §7; files/10 §7, §9 — Wazuh/Falco/
 * CrowdSec summaries, egress denials, audit-chain status, and the pen-test
 * findings tracker), and the Ops console (INT-351; files/08 §3 Ops — API
 * health, model hosts and GPU, model usage, clip cache, wait time,
 * satisfaction and CI/CD), the first module the App Router shell renders as a
 * page (`app/ops/page.tsx`).
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
// INT-190 — the Cost module (files/08 §3 "Cost", §4 J): per-session cost by
// component, vendor and profile, budgets and their alerts.
export {
  BUDGET_NOT_CONFIGURED,
  CostContentLeaked,
  CostFigureWithoutPrice,
  CostFigureWithoutUsage,
  CurrencyNotCatalogued,
  PartialTotalRendered,
  PRICE_NOT_CONFIGURED,
  renderCostModule,
  UnknownCostProfile,
  UnknownCostState,
  UnsoundBudgetVerdict,
  UnsourcedPrice,
  VENDOR_NOT_CONFIGURED,
  type BudgetPresentation,
  type BudgetWire,
  type ComponentPresentation,
  type ComponentWire,
  type CostPayload,
  type CostPresentation,
  type PerSessionRowPresentation,
  type PerSessionWire,
  type SpendPresentation,
  type TotalPresentation,
  type WindowPresentation,
  type WindowWire,
} from "./cost/module";
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
export {
  AcceptanceCountsInconsistent,
  ClinicalContentLeaked,
  ContentReadNotRefused,
  ForbiddenReviewVerdict,
  renderAcceptanceBySpecialty,
  renderFalseRedQueue,
  renderPolicyGuardClasses,
  renderQualitySafetyModule,
  renderTriageEvents,
  TriageDowngradeInFalseRedQueue,
  TriageNotFromRulesEngine,
  UnknownPolicyClass,
  type AcceptanceBySpecialtyPayload,
  type AcceptanceBySpecialtyPresentation,
  type AcceptanceRow,
  type AcceptanceRowPresentation,
  type Cell as SafetyCell,
  type FalseRedItem,
  type FalseRedItemPresentation,
  type FalseRedQueuePayload,
  type FalseRedQueuePresentation,
  type FalseRedReview,
  type FalseRedReviewPresentation,
  type PolicyGuardClassPresentation,
  type PolicyGuardClassRow,
  type PolicyGuardPayload,
  type PolicyGuardPresentation,
  type QualitySafetyPayload,
  type QualitySafetyPresentation,
  type TriageEventsPayload,
  type TriageEventsPresentation,
  type TriageLevelPresentation,
  type TriageLevelRow,
} from "./safety/module";
export {
  ExperienceFilterEnabled,
  renderCsat,
  renderExperienceModule,
  renderFilters,
  renderNps,
  renderPulse,
  renderSds01Export,
  SatisfactionFigureLeaked,
  SatisfactionTargetRendered,
  SdsColumnForbidden,
  SdsRowArityMismatch,
  SuppressedCohortLeaked,
  TenantFromQuery,
  UnknownCsatReason,
  UnsafeExportCell as ExperienceUnsafeExportCell,
  type Cell as ExperienceCell,
  type CohortPresentation,
  type CsatPresentation,
  type CsatRollupPayload,
  type DistributionBar,
  type ExperiencePayload,
  type ExperiencePresentation,
  type FilterDimension,
  type FilterDimensionPresentation,
  type FiltersPayload,
  type FiltersPresentation,
  type NpsPresentation,
  type NpsRollupPayload,
  type PulsePresentation,
  type PulseRollupPayload,
  type RollupBase,
  type RollupCohort,
  type Sds01ExportPayload,
  type Sds01ExportPresentation,
} from "./experience/module";
export {
  AuditChainAttestedWithoutAnchor,
  AuditHeadMalformed,
  EgressCountWithoutScrape,
  FindingsWithoutAssessment,
  renderAuditChainStatus,
  renderEgressDenials,
  renderPentestTracker,
  renderSecurityModule,
  renderSiemSummaries,
  SecurityContentLeaked,
  SiemSummaryWithoutFeed,
  UnknownAuditOutcome,
  UnknownDetectorSource,
  UnknownFindingSeverity,
  UnknownFindingStatus,
  UnknownSecuritySignal,
  UnknownSeverity,
  type AuditChainPayload,
  type AuditChainPresentation,
  type DetectorPresentation,
  type DetectorSummary,
  type DistributionBar as SecurityDistributionBar,
  type EgressDenialsPayload,
  type EgressDenialsPresentation,
  type PentestFinding,
  type PentestFindingPresentation,
  type PentestPayload,
  type PentestPresentation,
  type SecurityPayload,
  type SecurityPresentation,
  type SiemPayload,
  type SiemPresentation,
  type SlaRow,
} from "./security/module";
export {
  OPS_SCHEMA,
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsSchemaMismatch,
  OpsSuppressedCohortLeaked,
  OpsTargetRendered,
  OpsUnknownCarriesFigure,
  renderHealth,
  renderOps,
  type HealthResponses,
  type HealthView,
  type OpsPayload,
  type OpsView,
} from "./ops/module";
export { loadOpsConsole, type OpsConsoleState } from "./ops/load";
// INT-181 — the Overview (files/08 §3 Overview, Reliability): one tile per
// declared SLO with multiwindow burn rates, the synthetic probe matrix and
// dependency health, rendered at `app/overview/page.tsx`.
export {
  OverviewBudgetInconsistent,
  OverviewBurnInconsistent,
  OverviewStaleRenderedFresh,
  RELIABILITY_SCHEMA,
  renderOverview,
  type OverviewView,
  type ReliabilityPayload,
  type SloView,
} from "./overview/module";
export { loadOverview, type OverviewState } from "./overview/load";
// INT-182 — the Voice module (files/08 §3 "Voice runtime"): per-profile
// metrics, each tenant's kill switch / default profile / canary, the requests
// awaiting a second key and the four controls, rendered at `app/voice/page.tsx`.
export {
  VOICE_PROFILES,
  VOICE_SCHEMA,
  VoiceControlIncoherent,
  VoiceProfileOutsideSet,
  VoiceWeightOutOfBounds,
  renderVoice,
  type VoicePayload,
  type VoiceView,
} from "./voice/module";
export { loadVoice, resultFrom, type VoiceState } from "./voice/load";
export { planVoiceAction, submitVoiceAction, type ResultCode } from "./voice/actions";
// INT-187 — the CI/CD & releases module (files/08 §3): workflow runs, required
// gates, releases, deploy state, the deploy freeze and the gate it feeds, and
// the two freeze controls, rendered at `app/cicd/page.tsx`.
export {
  CICD_SCHEMA,
  CicdFreezeIncoherent,
  CicdGateIncoherent,
  CicdNotWired,
  renderCicd,
  type CicdPayload,
  type CicdView,
} from "./cicd/module";
export { loadCicd, type CicdState } from "./cicd/load";
export { planCicdAction, submitCicdAction } from "./cicd/actions";
// INT-428 — the Model lanes module (files/08 §3; ADR-035): which backend serves
// the llm, asr and tts lanes and each configured role, latency and cost per
// route and provider, the model options, the hosted providers' keys, and the
// tier-1 switches and tier-2 requests, rendered at `app/model-lanes/page.tsx`.
export {
  MODEL_LANES_SCHEMA,
  ModelLanesIncoherent,
  ModelLanesSecretLeaked,
  ModelLanesShapeRefused,
  renderModelLanes,
  type ModelLanesPayload,
  type ModelLanesView,
} from "./model-lanes/module";
export { loadModelLanes, type ModelLanesState } from "./model-lanes/load";
export { planModelLanesAction, submitModelLanesAction } from "./model-lanes/actions";
// INT-366 — the access review (files/08 §2.7, §3 Access & identity): the
// console review's age and what it makes read-only, each section's reviewer
// and digest, every staff account and the offboardings still open, rendered
// at `app/access/page.tsx`.
export {
  ACCESS_REVIEW_SCHEMA,
  AccessChainMaterialLeaked,
  AccessDirectoryLeaked,
  AccessPayloadRefused,
  AccessReviewInconsistent,
  renderAccessReview,
  type AccessReviewPayload,
  type AccessView,
} from "./access/module";
export { loadAccessReview, type AccessState } from "./access/load";
// INT-481 — the Alerts page: Alertmanager's current alerts counted by severity
// and listed by id, and a plain link to the staff Grafana, rendered at
// `app/alerts/page.tsx`.
export {
  ALERTS_SCHEMA,
  AlertsCountsIncoherent,
  AlertsShapeRefused,
  renderAlerts,
  type AlertsPayload,
  type AlertsView,
} from "./alerts/module";
export { grafanaFromEnv, loadAlerts, type AlertsState } from "./alerts/load";
