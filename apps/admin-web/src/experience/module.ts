/**
 * Experience & Satisfaction module — the console side (INT-186; files/08 §3,
 * §4 group F/G; INT-240, INT-241, INT-180).
 *
 * Like the models, compliance, protocols and safety modules, this turns the
 * `GET /admin/experience` composite into exactly what the page paints and
 * decides nothing the server did not already decide. It is a pure projection:
 * it reads the recorded payload and returns the presentation tree, performs no
 * mutation and opens no socket — survey cadence (INT-242) and the aggregate
 * reads flow through the INT-180 admin shell's audited, RBAC/ABAC routes, which
 * this file never re-implements (invariant 4).
 *
 * What it adds is a set of refusals that mirror the platform's invariants, so a
 * stale tab, a cached response or a tampered body cannot buy the page a
 * property the server would never have served:
 *
 * - **A cohort below the k >= 10 floor keeps only its count**
 *   (`SuppressedCohortLeaked`). files/06 §8 and files/08 §0c F9: a satisfaction
 *   or wait aggregate carrying a time filter is exactly the shape that
 *   re-identifies below the floor, and a five-response mean re-identifies as
 *   readily as a five-response list (INT-240 `roll_up_csat`). A suppressed
 *   rollup that still carries a mean, an NPS or a score distribution is refused.
 *
 * - **A figure carries counts and scores, never words** (`SatisfactionFigureLeaked`).
 *   Invariant 6: `csat.v1` has an optional patient-authored `text` field, and
 *   the rollup drops it at the boundary (INT-240 `CsatPoint` has no text member).
 *   A score-distribution key that is not an integer 1-5, or a rollup that
 *   acquired a free-text field, is the transcript reappearing on a console.
 *
 * - **CSAT reasons stay in the sealed enum** (`UnknownCsatReason`). The reason
 *   distribution is `clinical_schemas.events.CsatReason` (too long / didn't
 *   understand me / felt rushed / helpful / felt heard); a reason outside it is
 *   a tampered or drifted body.
 *
 * - **A figure is a measurement, never a claim** (`SatisfactionTargetRendered`).
 *   Invariant 20: the catalogue states a target for `csat.score` (>= 4.3) and
 *   `session.completion_rate` (>= 80 %), and rendering a target beside a
 *   measurement is how a measurement becomes a claim (INT-241 §4). Every figure
 *   names its cohort and window instead; a `target`, `sla`, `good`/`bad` beside
 *   a figure is refused.
 *
 * - **The branch/profile/clinic filters fail closed** (`ExperienceFilterEnabled`).
 *   The acceptance asks to filter by branch/profile/clinic; the experience
 *   aggregates carry no such dimension. `csat.v1`/`nps.v1`/`clinician_pulse.v1`
 *   have only `tenant_id` and a score, the visit's branch lives in an encrypted
 *   slot rather than a column, and slicing an operational aggregate by branch ×
 *   narrow window × small clinic is precisely files/08 §0c F9's
 *   re-identification case. Adding a dimension is a data-inventory decision
 *   under invariant 18 and a stop-and-ask (Owner + compliance_officer), open as
 *   the third refused value in docs/evidence/INT-241.md — with no
 *   HUMAN_BLOCKERS.md row minted for it. So the console presents the filter
 *   mechanism and marks every dimension unavailable; a payload asserting one is
 *   available is refused rather than painting a slice the data cannot support.
 *
 * - **Tenant scope is a token claim, never a query parameter** (`TenantFromQuery`).
 *   files/08 §8 rule (a) exists because F9 is an IDOR: a `tenant` filter is the
 *   parameter that returns the other hospital, so a filter dimension named for
 *   the tenant is refused.
 *
 * - **The SDS-01 export is the committed shape, aggregate only**
 *   (`SdsColumnForbidden`, `SdsRowArityMismatch`, `UnsafeExportCell`). The
 *   column set is `intake_metrics.sds01.SDS01_COLUMNS`, recorded verbatim and
 *   pinned; it carries no clinic, branch, clinician or patient column (F9), so
 *   any such column is refused, a row whose width does not match the columns is
 *   refused, and a cell that would evaluate in a spreadsheet (invariant 47,
 *   files/08 §0c F13) is refused rather than rendered.
 */

/* ------------------------------------------------------------------ */
/* Wire contract — the recorded shape of GET /admin/experience         */
/* ------------------------------------------------------------------ */

/** The cohort a rollup measured and when — invariant 20's "named cohort over a
 * stated window", made part of every figure (INT-240 `Cohort`). */
export interface RollupCohort {
  readonly window_start: string;
  readonly window_end: string;
  readonly measured_at: string;
}

/** Shared by every satisfaction rollup: the cohort, its size, whether it fell
 * below the floor, and the catalogued metric it projects. */
export interface RollupBase {
  readonly metric_id: string;
  readonly metric_status: string;
  readonly cohort: RollupCohort;
  readonly n: number;
  readonly k_floor: number;
  readonly suppressed: boolean;
  readonly note: string;
}

export interface CsatRollupPayload extends RollupBase {
  /** The score-metric id (`csat.score`) and the reason-metric id (`csat.reason`). */
  readonly reason_metric_id: string;
  /** The sealed `CsatReason` enumeration, for the console to hold the counts to. */
  readonly allowed_reasons: readonly string[];
  /** Mean CSAT (1-5), or null when suppressed or empty — never a bare 0. */
  readonly mean_score: number | null;
  /** Score → count. Keys are the integers 1-5 as strings; empty when suppressed. */
  readonly score_counts: Readonly<Record<string, number>>;
  /** Reason → count over the sealed enum; empty when suppressed. */
  readonly reason_counts: Readonly<Record<string, number>>;
}

export interface NpsRollupPayload extends RollupBase {
  readonly promoters: number | null;
  readonly passives: number | null;
  readonly detractors: number | null;
  /** The -100..100 NPS, or null when suppressed or empty. */
  readonly nps: number | null;
}

export interface PulseRollupPayload extends RollupBase {
  readonly mean_score: number | null;
  readonly score_counts: Readonly<Record<string, number>>;
}

/** One filter the console offers, and whether the data can honour it. */
export interface FilterDimension {
  readonly id: string;
  readonly label_tr: string;
  readonly label_en: string;
  /** False today for branch/profile/clinic — see `ExperienceFilterEnabled`. */
  readonly available: boolean;
  readonly reason: string;
}

export interface FiltersPayload {
  /** "token_claim" and only that: tenant scope never comes from a query string. */
  readonly tenant_scope: string;
  /** The window is required and has no default (invariant 20; INT-241). */
  readonly window_required: boolean;
  readonly k_floor: number;
  readonly dimensions: readonly FilterDimension[];
  readonly note: string;
}

export interface Sds01ExportPayload {
  /** The committed `intake_metrics.sds01.SDS01_COLUMNS`, recorded verbatim. */
  readonly columns: readonly string[];
  /** True: the export is tenant-scoped aggregate, no patient-level row (F9). */
  readonly aggregate_only: boolean;
  readonly tenant_scope: string;
  /** Data rows, each one cell per column; empty in the current no-data state. */
  readonly rows: readonly (readonly string[])[];
  readonly note: string;
}

export interface ExperiencePayload {
  readonly csat: CsatRollupPayload;
  readonly nps: NpsRollupPayload;
  readonly pulse: PulseRollupPayload;
  readonly filters: FiltersPayload;
  readonly sds01_export: Sds01ExportPayload;
}

/* ------------------------------------------------------------------ */
/* Presentation tree — what the page paints                            */
/* ------------------------------------------------------------------ */

export interface Cell {
  readonly label: string;
  readonly value: string;
}

export interface CohortPresentation {
  readonly windowStart: string;
  readonly windowEnd: string;
  readonly measuredAt: string;
}

export interface DistributionBar {
  readonly key: string;
  readonly count: string;
}

export interface CsatPresentation {
  readonly metricId: string;
  readonly reasonMetricId: string;
  readonly metricStatus: string;
  readonly cohort: CohortPresentation;
  readonly n: string;
  readonly suppressed: boolean;
  readonly hasData: boolean;
  readonly meanScore: string | null;
  readonly scores: readonly DistributionBar[];
  readonly reasons: readonly DistributionBar[];
  readonly note: string;
}

export interface NpsPresentation {
  readonly metricId: string;
  readonly metricStatus: string;
  readonly cohort: CohortPresentation;
  readonly n: string;
  readonly suppressed: boolean;
  readonly hasData: boolean;
  readonly nps: string | null;
  readonly cells: readonly Cell[];
  readonly note: string;
}

export interface PulsePresentation {
  readonly metricId: string;
  readonly metricStatus: string;
  readonly cohort: CohortPresentation;
  readonly n: string;
  readonly suppressed: boolean;
  readonly hasData: boolean;
  readonly meanScore: string | null;
  readonly scores: readonly DistributionBar[];
  readonly note: string;
}

export interface FilterDimensionPresentation {
  readonly id: string;
  readonly labelTr: string;
  readonly labelEn: string;
  readonly available: boolean;
  readonly reason: string;
}

export interface FiltersPresentation {
  readonly tenantScope: string;
  readonly windowRequired: boolean;
  readonly kFloor: string;
  readonly dimensions: readonly FilterDimensionPresentation[];
  readonly note: string;
}

export interface Sds01ExportPresentation {
  readonly columns: readonly string[];
  readonly aggregateOnly: boolean;
  readonly tenantScope: string;
  readonly rows: readonly (readonly string[])[];
  readonly empty: boolean;
  readonly note: string;
}

export interface ExperiencePresentation {
  readonly csat: CsatPresentation;
  readonly nps: NpsPresentation;
  readonly pulse: PulsePresentation;
  readonly filters: FiltersPresentation;
  readonly sds01Export: Sds01ExportPresentation;
}

/* ------------------------------------------------------------------ */
/* Refusals — the properties a stale or tampered payload cannot buy    */
/* ------------------------------------------------------------------ */

/** A cohort below the k-anonymity floor that still carries a figure. */
export class SuppressedCohortLeaked extends Error {
  constructor(metricId: string, field: string, n: number, floor: number) {
    super(
      `refusing to render '${field}' for ${metricId}: the cohort is ${n} < the k >= ${floor} ` +
        `floor, so nothing but the count survives — a small-cohort figure re-identifies as ` +
        `readily as the raw list (files/06 §8; files/08 §0c F9; INT-240)`,
    );
    this.name = "SuppressedCohortLeaked";
  }
}

/** A satisfaction figure carrying free text or a non-id-shaped key (invariant 6). */
export class SatisfactionFigureLeaked extends Error {
  constructor(metricId: string, detail: string) {
    super(
      `refusing to render ${metricId}: ${detail}. A rollup carries counts and scores, never ` +
        `words — csat.v1's optional free text is dropped at the rollup boundary (invariant 6; ` +
        `INT-240 CsatPoint has no text member)`,
    );
    this.name = "SatisfactionFigureLeaked";
  }
}

/** A CSAT reason outside the sealed `CsatReason` enumeration. */
export class UnknownCsatReason extends Error {
  constructor(reason: string, allowed: readonly string[]) {
    super(
      `refusing to render CSAT reason '${reason}': it is not one of the sealed reasons ` +
        `(${allowed.join(", ")}). The reason distribution is a fixed enum, so a new value is a ` +
        `tampered or drifted body`,
    );
    this.name = "UnknownCsatReason";
  }
}

/** A target/SLA/verdict rendered beside a measurement (invariant 20). */
export class SatisfactionTargetRendered extends Error {
  constructor(metricId: string, field: string) {
    super(
      `refusing to render '${field}' beside ${metricId}: a figure is a measurement of a named ` +
        `cohort over a stated window, never a property of the product — rendering a target or a ` +
        `good/bad verdict beside it is how a measurement becomes a claim (invariant 20; INT-241 §4)`,
    );
    this.name = "SatisfactionTargetRendered";
  }
}

/** A branch/profile/clinic filter asserted available while the data carries no
 * such dimension (files/08 §0c F9; invariant 18). */
export class ExperienceFilterEnabled extends Error {
  constructor(dimension: string) {
    super(
      `refusing to render the '${dimension}' filter as available: the experience aggregates ` +
        `carry no such dimension, and slicing an operational aggregate by branch × narrow ` +
        `window × small clinic is files/08 §0c F9's re-identification case. Adding a dimension ` +
        `is a data-inventory decision under invariant 18 and a stop-and-ask (Owner + ` +
        `compliance_officer), open in docs/evidence/INT-241.md — the console offers the ` +
        `mechanism and fails closed, it does not paint a slice the data cannot support`,
    );
    this.name = "ExperienceFilterEnabled";
  }
}

/** A tenant scope taken from anywhere but the token claim (files/08 §8 (a), F9 IDOR). */
export class TenantFromQuery extends Error {
  constructor(where: string, scope: string) {
    super(
      `refusing to render ${where} with tenant scope '${scope}': tenant scope is a token claim, ` +
        `never a query parameter — a tenant filter is the IDOR that returns the other hospital ` +
        `(files/08 §8 rule (a); files/08 §0c F9)`,
    );
    this.name = "TenantFromQuery";
  }
}

/** An SDS-01 column outside the committed set, or a re-identifying column (F9). */
export class SdsColumnForbidden extends Error {
  constructor(detail: string) {
    super(
      `refusing to render the SDS-01 export: ${detail}. The column set is the committed ` +
        `intake_metrics.sds01.SDS01_COLUMNS and carries no clinic, branch, clinician or patient ` +
        `column (files/08 §0c F9; INT-241 §4)`,
    );
    this.name = "SdsColumnForbidden";
  }
}

/** An SDS-01 row whose width does not match the column set. */
export class SdsRowArityMismatch extends Error {
  constructor(rowIndex: number, got: number, want: number) {
    super(
      `refusing to render SDS-01 row ${rowIndex}: it has ${got} cells against ${want} columns — ` +
        `a stale or tampered body`,
    );
    this.name = "SdsRowArityMismatch";
  }
}

/** An SDS-01 cell that a spreadsheet would evaluate (invariant 47). */
export class UnsafeExportCell extends Error {
  constructor(rowIndex: number) {
    super(
      `refusing to render an SDS-01 cell (row ${rowIndex}) that would evaluate when opened in a ` +
        `spreadsheet: the server sanitises every cell (invariant 47; files/08 §0c F13), so a raw ` +
        `formula here is a tampered or pre-sanitisation body`,
    );
    this.name = "UnsafeExportCell";
  }
}

/* ------------------------------------------------------------------ */
/* Renderers                                                           */
/* ------------------------------------------------------------------ */

/** Score keys are the integers 1-5 (csat/pulse), 0-10 has no distribution here. */
const SCORE_KEY = /^(?:[1-9]|10)$/;
/** Fields a figure must never carry: any of them turns a measurement into a claim. */
const CLAIM_FIELDS = ["target", "sla", "good", "bad", "verdict", "rag"] as const;
/** Columns an SDS-01 export may never carry — F9's re-identification set. */
const FORBIDDEN_SDS_COLUMNS = [
  "clinic",
  "branch",
  "clinician",
  "clinician_ref",
  "patient",
  "patient_id",
  "session_id",
  "tenant",
  "tenant_id",
] as const;
/** A cell leading with any of these evaluates in Excel/Sheets (invariant 47). */
const FORMULA_LEADS = ["=", "+", "-", "@", "\t", "\r"];
/** The only permitted tenant scope on every experience surface (files/08 §8 (a)). */
const TOKEN_CLAIM = "token_claim";

/** A count crosses the boundary as one atom, no grouping separator (inv 22). */
function count(value: number): string {
  return value.toLocaleString("en-GB", { useGrouping: false });
}

/** A figure that is a genuine value or a genuine absence — never a bare 0. */
function figure(value: number | null): string | null {
  return value === null ? null : String(value);
}

function cohort(payload: RollupCohort): CohortPresentation {
  return {
    windowStart: payload.window_start,
    windowEnd: payload.window_end,
    measuredAt: payload.measured_at,
  };
}

/** Reject any claim-shaped field sitting on a rollup body (invariant 20). */
function refuseClaimFields(metricId: string, body: object): void {
  for (const field of CLAIM_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(body, field)) {
      throw new SatisfactionTargetRendered(metricId, field);
    }
  }
}

/** A distribution is publishable only at or above the floor, and only over
 * id-shaped keys. Returns the bars, or refuses. */
function distribution(
  metricId: string,
  counts: Readonly<Record<string, number>>,
  suppressed: boolean,
  n: number,
  floor: number,
  keyOk: (key: string) => boolean,
): readonly DistributionBar[] {
  const keys = Object.keys(counts);
  if (suppressed && keys.length > 0) {
    throw new SuppressedCohortLeaked(metricId, "distribution", n, floor);
  }
  for (const key of keys) {
    if (!keyOk(key)) {
      throw new SatisfactionFigureLeaked(metricId, `distribution key '${key}' is not id-shaped`);
    }
  }
  return keys.map((key) => ({ key, count: count(counts[key]!) }));
}

/** Build the CSAT surface: score distribution + reason counts, floor-suppressed. */
export function renderCsat(payload: CsatRollupPayload): CsatPresentation {
  refuseClaimFields(payload.metric_id, payload);
  const hasData = !payload.suppressed && payload.n >= payload.k_floor;
  if (payload.suppressed && payload.mean_score !== null) {
    throw new SuppressedCohortLeaked(payload.metric_id, "mean_score", payload.n, payload.k_floor);
  }
  const scores = distribution(
    payload.metric_id,
    payload.score_counts,
    payload.suppressed,
    payload.n,
    payload.k_floor,
    (key) => SCORE_KEY.test(key),
  );
  const reasons = distribution(
    payload.reason_metric_id,
    payload.reason_counts,
    payload.suppressed,
    payload.n,
    payload.k_floor,
    (key) => {
      if (!payload.allowed_reasons.includes(key)) {
        throw new UnknownCsatReason(key, payload.allowed_reasons);
      }
      return true;
    },
  );
  return {
    metricId: payload.metric_id,
    reasonMetricId: payload.reason_metric_id,
    metricStatus: payload.metric_status,
    cohort: cohort(payload.cohort),
    n: count(payload.n),
    suppressed: payload.suppressed,
    hasData,
    meanScore: figure(payload.mean_score),
    scores,
    reasons,
    note: payload.note,
  };
}

/** Build the NPS surface: promoter/passive/detractor split + NPS, floor-suppressed. */
export function renderNps(payload: NpsRollupPayload): NpsPresentation {
  refuseClaimFields(payload.metric_id, payload);
  const hasData = !payload.suppressed && payload.n >= payload.k_floor;
  const bandFields: readonly (readonly [string, number | null])[] = [
    ["promoters", payload.promoters],
    ["passives", payload.passives],
    ["detractors", payload.detractors],
    ["nps", payload.nps],
  ];
  if (payload.suppressed) {
    for (const [field, value] of bandFields) {
      if (value !== null) {
        throw new SuppressedCohortLeaked(payload.metric_id, field, payload.n, payload.k_floor);
      }
    }
  }
  const cells: Cell[] = hasData
    ? [
        { label: "promoters", value: count(payload.promoters ?? 0) },
        { label: "passives", value: count(payload.passives ?? 0) },
        { label: "detractors", value: count(payload.detractors ?? 0) },
      ]
    : [];
  return {
    metricId: payload.metric_id,
    metricStatus: payload.metric_status,
    cohort: cohort(payload.cohort),
    n: count(payload.n),
    suppressed: payload.suppressed,
    hasData,
    nps: figure(payload.nps),
    cells,
    note: payload.note,
  };
}

/** Build the clinician-pulse surface, floor-suppressed. Clinicians appear as
 * counts only — a `clinician_ref` never reaches an aggregate (invariant 6). */
export function renderPulse(payload: PulseRollupPayload): PulsePresentation {
  refuseClaimFields(payload.metric_id, payload);
  const hasData = !payload.suppressed && payload.n >= payload.k_floor;
  if (payload.suppressed && payload.mean_score !== null) {
    throw new SuppressedCohortLeaked(payload.metric_id, "mean_score", payload.n, payload.k_floor);
  }
  const scores = distribution(
    payload.metric_id,
    payload.score_counts,
    payload.suppressed,
    payload.n,
    payload.k_floor,
    (key) => SCORE_KEY.test(key),
  );
  return {
    metricId: payload.metric_id,
    metricStatus: payload.metric_status,
    cohort: cohort(payload.cohort),
    n: count(payload.n),
    suppressed: payload.suppressed,
    hasData,
    meanScore: figure(payload.mean_score),
    scores,
    note: payload.note,
  };
}

/** Build the filter mechanism, refusing any dimension asserted available and
 * any tenant scope that is not the token claim. */
export function renderFilters(payload: FiltersPayload): FiltersPresentation {
  if (payload.tenant_scope !== TOKEN_CLAIM) {
    throw new TenantFromQuery("the filter bar", payload.tenant_scope);
  }
  const dimensions = payload.dimensions.map((dim) => {
    // the tenant is scope, never a filter dimension (F9 IDOR)
    if (dim.id === "tenant" || dim.id === "tenant_id") {
      throw new TenantFromQuery(`the '${dim.id}' filter`, dim.id);
    }
    if (dim.available) {
      throw new ExperienceFilterEnabled(dim.id);
    }
    return {
      id: dim.id,
      labelTr: dim.label_tr,
      labelEn: dim.label_en,
      available: dim.available,
      reason: dim.reason,
    };
  });
  return {
    tenantScope: payload.tenant_scope,
    windowRequired: payload.window_required,
    kFloor: count(payload.k_floor),
    dimensions,
    note: payload.note,
  };
}

/** Build the SDS-01 export, refusing a forbidden column, a mis-sized row or a
 * cell that would evaluate in a spreadsheet. */
export function renderSds01Export(payload: Sds01ExportPayload): Sds01ExportPresentation {
  if (payload.tenant_scope !== TOKEN_CLAIM) {
    throw new TenantFromQuery("the SDS-01 export", payload.tenant_scope);
  }
  if (!payload.aggregate_only) {
    throw new SdsColumnForbidden("the export is not marked aggregate-only");
  }
  const width = payload.columns.length;
  for (const column of payload.columns) {
    if (FORBIDDEN_SDS_COLUMNS.includes(column as (typeof FORBIDDEN_SDS_COLUMNS)[number])) {
      throw new SdsColumnForbidden(`column '${column}' would re-identify a cohort`);
    }
  }
  payload.rows.forEach((row, index) => {
    if (row.length !== width) {
      throw new SdsRowArityMismatch(index, row.length, width);
    }
    for (const cell of row) {
      if (cell.length > 0 && FORMULA_LEADS.includes(cell[0]!)) {
        throw new UnsafeExportCell(index);
      }
    }
  });
  return {
    columns: payload.columns,
    aggregateOnly: payload.aggregate_only,
    tenantScope: payload.tenant_scope,
    rows: payload.rows,
    empty: payload.rows.length === 0,
    note: payload.note,
  };
}

/**
 * Build the whole module from the recorded composite.
 *
 * A refusal in any surface propagates: an experience console that painted a
 * small-cohort mean, a leaked transcript fragment, a target beside a figure, a
 * branch slice the data cannot support or a re-identifying export column would
 * be worse than no console, so the page does not render past one.
 */
export function renderExperienceModule(payload: ExperiencePayload): ExperiencePresentation {
  return {
    csat: renderCsat(payload.csat),
    nps: renderNps(payload.nps),
    pulse: renderPulse(payload.pulse),
    filters: renderFilters(payload.filters),
    sds01Export: renderSds01Export(payload.sds01_export),
  };
}
