/**
 * Clinical Quality & Safety module — the console side (INT-185; files/08 §4 D/E;
 * INT-175, INT-180).
 *
 * Like the models, compliance and protocols modules, this turns the
 * `GET /admin/quality-safety` composite into exactly what the page paints and
 * decides nothing the server did not already decide. What it adds is a set of
 * refusals that mirror the platform's invariants, so a stale tab, a cached
 * response or a tampered body cannot buy the page a property the server would
 * never have served:
 *
 * - **Triage routing has one source** (`TriageNotFromRulesEngine`). Invariant 1:
 *   RED/YELLOW/GREEN can only be produced by `packages/protocols/triage`; an
 *   LLM may append `candidate_flags` capped at `YELLOW_REVIEW` (a clinician-only,
 *   non-routing ceiling). A distribution row that attributes a routing count to
 *   anything but the rules engine, or a candidate cap above `YELLOW_REVIEW`, is
 *   refused rather than rendered.
 *
 * - **The false-RED queue annotates; it never downgrades**
 *   (`TriageDowngradeInFalseRedQueue`). It is a review surface (the INT-175
 *   `false_red_review` annotation queue): a clinician records that a RED that
 *   fired looks false, and that record is an annotation — a rules-engine RED is
 *   inviolable (invariant 1). A payload that slips a triage-level mutation onto
 *   an item is refused.
 *
 * - **The queue holds ids, not patient words** (`ClinicalContentLeaked`).
 *   Invariant 6: items are pointers. A field carrying free text is the shape of
 *   the transcript reappearing on a console, so it is refused.
 *
 * - **The content behind an item is unreadable** (`ContentReadNotRefused`).
 *   HB-L6 is open and files/06 §2 enumerates no purpose for staff reads of
 *   patient content, so the annotation module has no granted content-read path
 *   at all (files/08 §2.6). A body asserting one is refused.
 *
 * - **Review verdicts stay in the closed vocabulary** (`ForbiddenReviewVerdict`).
 *   The label, the section reason and the reviewer role are closed enums
 *   precisely so "reason" cannot become the free-text box a note gets pasted
 *   into, and so only a permitted role acts (four-eyes, files/08 §2.1).
 *
 * - **PolicyGuard classes are sealed** (`UnknownPolicyClass`). Invariant 2's
 *   categories are a fixed set; a class outside it is a tampered or drifted body.
 *   Their counts are read from the scrape at serve time (INT-565): with none
 *   behind the section, a count — a zero included — is refused
 *   (`PolicyGuardCountWithoutScrape`), so "no blocks" and "no data" never look
 *   alike.
 *
 * - **A rate is a measurement, never a claim** (`UnlabelledMeasurement`, reused
 *   from INT-183). Invariant 20: an acceptance figure is shown only with a named
 *   corpus and a date; a bare number is refused. Acceptance is a count of notes,
 *   never an accuracy or sensitivity claim.
 *
 * The whole module is a pure projection: it reads the recorded payload and
 * returns the presentation tree. It performs no mutation and opens no socket —
 * enqueue/review flow through the INT-175 annotation module and the INT-180
 * admin shell's audited, four-eyes, RBAC/ABAC routes, which this file never
 * re-implements.
 */
import { renderMeasurement, type Measurement } from "../models/measurement";

/* ------------------------------------------------------------------ */
/* Wire contract — the recorded shape of GET /admin/quality-safety     */
/* ------------------------------------------------------------------ */

export interface TriageLevelRow {
  /** A `clinical_schemas.triage.TriageLevel`: GREEN | YELLOW | RED. */
  readonly level: string;
  readonly count: number;
  /** The producer of this routing count — "rules_engine" and only that (inv 1). */
  readonly produced_by: string;
}

export interface TriageEventsPayload {
  readonly metric_id: string;
  readonly metric_status: string;
  /** The LLM candidate ceiling — `YELLOW_REVIEW`, a non-routing level (inv 1). */
  readonly candidate_flag_cap: string;
  readonly levels: readonly TriageLevelRow[];
  readonly note: string;
}

export interface FalseRedReview {
  readonly label: string;
  readonly section_reason: string;
  readonly reviewer_role: string;
  readonly recorded_at_utc: string;
}

export interface FalseRedItem {
  readonly item_id: string;
  readonly session_id_hash: string;
  readonly work_id: string;
  readonly span_ref: string;
  /** The RED rule that fired — a rule id, structural, not content. */
  readonly rule_id: string;
  readonly branch_id: string;
  readonly created_at_utc: string;
  readonly review: FalseRedReview | null;
}

export interface FalseRedQueuePayload {
  readonly queue_id: string;
  readonly enqueue_scope: string;
  readonly reviewer_roles: readonly string[];
  readonly labels: readonly string[];
  readonly section_reasons: readonly string[];
  readonly content_scope: string | null;
  readonly content_blocker: string;
  /** "refused" and only "refused": the annotation module grants no content read. */
  readonly content_read_state: string;
  readonly items: readonly FalseRedItem[];
  readonly note: string;
}

export interface PolicyGuardClassRow {
  /** A `ViolationClass`: diagnosis | treatment | prognosis | multi_question | … */
  readonly class: string;
  /** Blocks in the window, or null when no scrape was read — never a bare 0. */
  readonly count: number | null;
}

export interface PolicyGuardPayload {
  readonly metric_id: string;
  readonly metric_status: string;
  /** The window the counts are summed over (INT-565: `24h`). */
  readonly window: string;
  /** False when the route read no scrape (INT-565); then every count is null. */
  readonly source_available: boolean;
  /** Why the scrape was not read (`prometheus_unconfigured`, …), else null. */
  readonly source_reason: string | null;
  readonly allowed_classes: readonly string[];
  readonly classes: readonly PolicyGuardClassRow[];
  readonly note: string;
}

export interface AcceptanceRow {
  readonly branch_id: string;
  readonly name_tr: string;
  readonly cluster: string;
  readonly delivered: number;
  readonly accepted: number;
  /** A dated measurement over a named corpus, or null when there is no data. */
  readonly measurement: Measurement | null;
}

export interface AcceptanceBySpecialtyPayload {
  readonly metric_id: string;
  readonly metric_status: string;
  readonly rows: readonly AcceptanceRow[];
  readonly note: string;
}

export interface QualitySafetyPayload {
  readonly triage_events: TriageEventsPayload;
  readonly false_red_queue: FalseRedQueuePayload;
  readonly policyguard_classes: PolicyGuardPayload;
  readonly acceptance_by_specialty: AcceptanceBySpecialtyPayload;
}

/* ------------------------------------------------------------------ */
/* Presentation tree — what the page paints                            */
/* ------------------------------------------------------------------ */

export interface Cell {
  readonly label: string;
  readonly value: string;
}

export interface TriageLevelPresentation {
  readonly level: string;
  readonly count: string;
  readonly producedBy: string;
}

export interface TriageEventsPresentation {
  readonly metricId: string;
  readonly metricStatus: string;
  readonly candidateFlagCap: string;
  readonly note: string;
  readonly levels: readonly TriageLevelPresentation[];
}

export interface FalseRedReviewPresentation {
  readonly label: string;
  readonly sectionReason: string;
  readonly reviewerRole: string;
  readonly recordedAt: string;
}

export interface FalseRedItemPresentation {
  readonly itemId: string;
  readonly sessionIdHash: string;
  readonly workId: string;
  readonly spanRef: string;
  readonly ruleId: string;
  readonly branchId: string;
  readonly createdAt: string;
  readonly review: FalseRedReviewPresentation | null;
}

export interface FalseRedQueuePresentation {
  readonly queueId: string;
  readonly enqueueScope: string;
  readonly reviewerRoles: readonly string[];
  readonly labels: readonly string[];
  readonly sectionReasons: readonly string[];
  readonly contentScope: string | null;
  readonly contentBlocker: string;
  readonly contentReadState: string;
  readonly note: string;
  readonly empty: boolean;
  readonly items: readonly FalseRedItemPresentation[];
}

export interface PolicyGuardClassPresentation {
  readonly className: string;
  /** The count, or null while no scrape backs the section. */
  readonly count: string | null;
}

export interface PolicyGuardPresentation {
  readonly metricId: string;
  readonly metricStatus: string;
  readonly window: string;
  readonly sourceAvailable: boolean;
  readonly sourceReason: string | null;
  readonly note: string;
  readonly classes: readonly PolicyGuardClassPresentation[];
}

export interface AcceptanceRowPresentation {
  readonly branchId: string;
  readonly nameTr: string;
  readonly cluster: string;
  readonly cells: readonly Cell[];
  /** The rendered measurement (corpus + date), or null in the empty state. */
  readonly rate: string | null;
  readonly hasData: boolean;
}

export interface AcceptanceBySpecialtyPresentation {
  readonly metricId: string;
  readonly metricStatus: string;
  readonly note: string;
  readonly rows: readonly AcceptanceRowPresentation[];
}

export interface QualitySafetyPresentation {
  readonly triageEvents: TriageEventsPresentation;
  readonly falseRedQueue: FalseRedQueuePresentation;
  readonly policyGuardClasses: PolicyGuardPresentation;
  readonly acceptanceBySpecialty: AcceptanceBySpecialtyPresentation;
}

/* ------------------------------------------------------------------ */
/* Refusals — the properties a stale or tampered payload cannot buy    */
/* ------------------------------------------------------------------ */

/** A triage routing count not from the rules engine, or a candidate above the
 * YELLOW_REVIEW ceiling (invariant 1). */
export class TriageNotFromRulesEngine extends Error {
  constructor(detail: string) {
    super(
      `refusing to render this triage figure: ${detail}. RED/YELLOW/GREEN can only be ` +
        `produced by packages/protocols/triage; an LLM may only append candidate_flags ` +
        `capped at YELLOW_REVIEW (CLAUDE.md invariant 1; files/03 §4.6)`,
    );
    this.name = "TriageNotFromRulesEngine";
  }
}

/** A false-RED item that would move a triage level (invariant 1). */
export class TriageDowngradeInFalseRedQueue extends Error {
  constructor(itemId: string, field: string) {
    super(
      `refusing to render false-RED item '${itemId}': it carries '${field}', a triage-level ` +
        `mutation. The false-RED queue records a clinician's annotation of a RED; it never ` +
        `downgrades it — a rules-engine RED is inviolable (CLAUDE.md invariant 1)`,
    );
    this.name = "TriageDowngradeInFalseRedQueue";
  }
}

/** A queue pointer carrying free-text patient content (invariant 6). */
export class ClinicalContentLeaked extends Error {
  constructor(itemId: string, field: string) {
    super(
      `refusing to render false-RED item '${itemId}': field '${field}' is not id-shaped, so ` +
        `it may carry patient content. The queue holds pointers only — ids, a span ref and a ` +
        `timestamp, never clinical text (CLAUDE.md invariant 6; INT-175)`,
    );
    this.name = "ClinicalContentLeaked";
  }
}

/** A body asserting a granted content-read path while HB-L6 is open. */
export class ContentReadNotRefused extends Error {
  constructor(state: string) {
    super(
      `refusing to render a content-read state of '${state}': staff reads of the patient ` +
        `content behind a queue item are refused, not granted — HB-L6 is open and files/06 §2 ` +
        `enumerates no purpose covering staff access (files/08 §2.6). The only state is 'refused'`,
    );
    this.name = "ContentReadNotRefused";
  }
}

/** A review verdict outside the closed annotation vocabulary or role set. */
export class ForbiddenReviewVerdict extends Error {
  constructor(detail: string) {
    super(
      `refusing to render this false-RED review: ${detail}. The verdict label, the section ` +
        `reason and the reviewer role are closed sets — so 'reason' cannot become a free-text ` +
        `box and only a permitted role acts (files/08 §2.1, §2.5; INT-175)`,
    );
    this.name = "ForbiddenReviewVerdict";
  }
}

/** A PolicyGuard class outside the sealed set (invariant 2). */
export class UnknownPolicyClass extends Error {
  constructor(className: string, allowed: readonly string[]) {
    super(
      `refusing to render PolicyGuard class '${className}': it is not one of the sealed ` +
        `violation classes (${allowed.join(", ")}). Invariant 2's categories are fixed, so a ` +
        `new class is a tampered or drifted body`,
    );
    this.name = "UnknownPolicyClass";
  }
}

/** A PolicyGuard count presented while no scrape backs the section (inv 17). */
export class PolicyGuardCountWithoutScrape extends Error {
  constructor(className: string) {
    super(
      `refusing to render a PolicyGuard count for '${className}' while no metrics scrape ` +
        `backs the section: policyguard.blocks_total is read at serve time, and a number with ` +
        `no scrape behind it reads as "no blocks" when it means "no data" (invariant 17)`,
    );
    this.name = "PolicyGuardCountWithoutScrape";
  }
}

/** An acceptance row whose accepted count exceeds notes delivered. */
export class AcceptanceCountsInconsistent extends Error {
  constructor(branchId: string, accepted: number, delivered: number) {
    super(
      `refusing to render acceptance for '${branchId}': accepted (${accepted}) exceeds ` +
        `delivered (${delivered}), so a rate would be greater than 1 — the body is stale or ` +
        `tampered`,
    );
    this.name = "AcceptanceCountsInconsistent";
  }
}

/* ------------------------------------------------------------------ */
/* Renderers                                                           */
/* ------------------------------------------------------------------ */

/** The sole producer of any triage routing level (invariant 1). */
const RULES_ENGINE = "rules_engine";
/** The LLM candidate ceiling (invariant 1; files/03 §4.6). */
const CANDIDATE_CEILING = "YELLOW_REVIEW";
/** Id shape mirrored from `intake_platform.observability.spans` (INT-175):
 * starts alphanumeric, then id characters only — a sentence carries none. */
const REF_SHAPE = /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$/;
/** Fields a false-RED item must never carry: any of them moves a triage level. */
const DOWNGRADE_FIELDS = [
  "level",
  "new_level",
  "triage_level",
  "downgrades_to",
  "override_level",
  "set_level",
] as const;

/** A count crosses the boundary as one atom, no grouping separator (inv 22). */
function count(value: number): string {
  return value.toLocaleString("en-GB", { useGrouping: false });
}

/** Build the RED/YELLOW/GREEN distribution, refusing any non-rules producer. */
export function renderTriageEvents(payload: TriageEventsPayload): TriageEventsPresentation {
  if (payload.candidate_flag_cap !== CANDIDATE_CEILING) {
    throw new TriageNotFromRulesEngine(
      `the candidate cap is '${payload.candidate_flag_cap}', above the ${CANDIDATE_CEILING} ceiling`,
    );
  }
  const levels = payload.levels.map((row) => {
    if (row.produced_by !== RULES_ENGINE) {
      throw new TriageNotFromRulesEngine(
        `level ${row.level} is attributed to '${row.produced_by}', not the rules engine`,
      );
    }
    return { level: row.level, count: count(row.count), producedBy: row.produced_by };
  });
  return {
    metricId: payload.metric_id,
    metricStatus: payload.metric_status,
    candidateFlagCap: payload.candidate_flag_cap,
    note: payload.note,
    levels,
  };
}

function renderFalseRedItem(
  item: FalseRedItem,
  labels: readonly string[],
  sectionReasons: readonly string[],
  reviewerRoles: readonly string[],
): FalseRedItemPresentation {
  // a level mutation must never reach a surface whose only job is to annotate
  for (const field of DOWNGRADE_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(item, field)) {
      throw new TriageDowngradeInFalseRedQueue(item.item_id, field);
    }
  }
  // pointers only — a field with a space or a non-id character may carry content
  const pointers: readonly [string, string][] = [
    ["item_id", item.item_id],
    ["session_id_hash", item.session_id_hash],
    ["work_id", item.work_id],
    ["span_ref", item.span_ref],
    ["rule_id", item.rule_id],
    ["branch_id", item.branch_id],
    ["created_at_utc", item.created_at_utc],
  ];
  for (const [field, value] of pointers) {
    if (!REF_SHAPE.test(value)) {
      throw new ClinicalContentLeaked(item.item_id, field);
    }
  }

  let review: FalseRedReviewPresentation | null = null;
  if (item.review !== null) {
    const { label, section_reason, reviewer_role, recorded_at_utc } = item.review;
    if (!labels.includes(label)) {
      throw new ForbiddenReviewVerdict(`label '${label}' is not one of ${labels.join(", ")}`);
    }
    if (!sectionReasons.includes(section_reason)) {
      throw new ForbiddenReviewVerdict(
        `section reason '${section_reason}' is not one of ${sectionReasons.join(", ")}`,
      );
    }
    if (!reviewerRoles.includes(reviewer_role)) {
      throw new ForbiddenReviewVerdict(
        `reviewer role '${reviewer_role}' may not review this queue (permitted: ${reviewerRoles.join(", ")})`,
      );
    }
    if (!REF_SHAPE.test(recorded_at_utc)) {
      throw new ClinicalContentLeaked(item.item_id, "review.recorded_at_utc");
    }
    review = {
      label,
      sectionReason: section_reason,
      reviewerRole: reviewer_role,
      recordedAt: recorded_at_utc,
    };
  }

  return {
    itemId: item.item_id,
    sessionIdHash: item.session_id_hash,
    workId: item.work_id,
    spanRef: item.span_ref,
    ruleId: item.rule_id,
    branchId: item.branch_id,
    createdAt: item.created_at_utc,
    review,
  };
}

/** Build the false-RED queue, refusing any downgrade, content leak or bad verdict. */
export function renderFalseRedQueue(payload: FalseRedQueuePayload): FalseRedQueuePresentation {
  if (payload.content_read_state !== "refused") {
    throw new ContentReadNotRefused(payload.content_read_state);
  }
  const items = payload.items.map((item) =>
    renderFalseRedItem(item, payload.labels, payload.section_reasons, payload.reviewer_roles),
  );
  return {
    queueId: payload.queue_id,
    enqueueScope: payload.enqueue_scope,
    reviewerRoles: payload.reviewer_roles,
    labels: payload.labels,
    sectionReasons: payload.section_reasons,
    contentScope: payload.content_scope,
    contentBlocker: payload.content_blocker,
    contentReadState: payload.content_read_state,
    note: payload.note,
    empty: items.length === 0,
    items,
  };
}

/** Build the PolicyGuard class breakdown, refusing any class off the sealed set. */
export function renderPolicyGuardClasses(payload: PolicyGuardPayload): PolicyGuardPresentation {
  const classes = payload.classes.map((row) => {
    if (!payload.allowed_classes.includes(row.class)) {
      throw new UnknownPolicyClass(row.class, payload.allowed_classes);
    }
    if (row.count === null) return { className: row.class, count: null };
    if (!payload.source_available) throw new PolicyGuardCountWithoutScrape(row.class);
    return { className: row.class, count: count(row.count) };
  });
  return {
    metricId: payload.metric_id,
    metricStatus: payload.metric_status,
    window: payload.window,
    sourceAvailable: payload.source_available,
    sourceReason: payload.source_available ? null : payload.source_reason,
    note: payload.note,
    classes,
  };
}

function renderAcceptanceRow(row: AcceptanceRow): AcceptanceRowPresentation {
  if (row.accepted > row.delivered) {
    throw new AcceptanceCountsInconsistent(row.branch_id, row.accepted, row.delivered);
  }
  // a rate is shown only through the INT-183 measurement discipline, which
  // refuses an unlabelled number (invariant 20); no data means no rate, not 0 %
  const rate = row.measurement === null ? null : renderMeasurement(row.measurement);
  return {
    branchId: row.branch_id,
    nameTr: row.name_tr,
    cluster: row.cluster,
    cells: [
      { label: "delivered", value: count(row.delivered) },
      { label: "accepted", value: count(row.accepted) },
    ],
    rate,
    hasData: row.measurement !== null,
  };
}

/** Build the acceptance-by-specialty rollup, refusing impossible counts. */
export function renderAcceptanceBySpecialty(
  payload: AcceptanceBySpecialtyPayload,
): AcceptanceBySpecialtyPresentation {
  return {
    metricId: payload.metric_id,
    metricStatus: payload.metric_status,
    note: payload.note,
    rows: payload.rows.map(renderAcceptanceRow),
  };
}

/**
 * Build the whole module from the recorded composite.
 *
 * A refusal in any surface propagates: a safety console that painted an
 * LLM-produced RED, a false-RED downgrade, a leaked transcript or an unlabelled
 * rate would be worse than no console, so the page does not render past one.
 */
export function renderQualitySafetyModule(
  payload: QualitySafetyPayload,
): QualitySafetyPresentation {
  return {
    triageEvents: renderTriageEvents(payload.triage_events),
    falseRedQueue: renderFalseRedQueue(payload.false_red_queue),
    policyGuardClasses: renderPolicyGuardClasses(payload.policyguard_classes),
    acceptanceBySpecialty: renderAcceptanceBySpecialty(payload.acceptance_by_specialty),
  };
}
