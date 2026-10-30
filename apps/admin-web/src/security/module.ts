/**
 * Security module — the console side (INT-192; files/08 §3, §7; files/10 §7, §9;
 * INT-205, INT-180, INT-016, INT-018).
 *
 * Like the models, compliance, protocols, safety and experience modules, this
 * turns the `GET /admin/security` composite into exactly what the page paints
 * and decides nothing the server did not already decide. It is a pure
 * projection: it reads the recorded payload and returns the presentation tree,
 * performs no mutation and opens no socket — every route that reads a security
 * source flows through the INT-180 admin shell's audited, RBAC/ABAC routes,
 * which this file never re-implements (invariant 4). Nothing here writes to the
 * audit chain; the chain's status is read-only on this surface (invariant 4).
 *
 * The acceptance names four surfaces, and each projects a REAL source:
 *
 * - **SIEM summaries** (`intake_platform.siem.feed.load_console_feed`, INT-205)
 *   — Wazuh, Falco and CrowdSec, counted by signal and by severity. The one
 *   thing this surface must never do is let "nothing was detected" and "the SIEM
 *   was never wired up" look the same on a screen someone uses to decide whether
 *   an incident is happening: the feed returns *not configured* until the alert
 *   stream is mounted, so a count shown while the feed is not configured is
 *   refused (`SiemSummaryWithoutFeed`), the signal / severity / detector-source
 *   sets are sealed to the platform's own enumerations, and a value outside one
 *   is a tampered or drifted body.
 *
 * - **Egress denials** (`sec.egress_denied_total`, INT-018; invariants 14/19) —
 *   the allow-list default-deny counter, whose catalogue target is 0 and whose
 *   every increase pages. The console reads it from a metrics scrape at serve
 *   time; a bare 0 with no scrape behind it reads as "no denials" when it may
 *   mean "no data", so a count presented as observed while the scrape is
 *   unavailable is refused (`EgressCountWithoutScrape`).
 *
 * - **Audit-chain status** (`run_daily_verification`, INT-016; invariant 4) —
 *   the daily hash-chain verification. 1 means the chain verified against the
 *   *externally anchored* head, never merely that the store agrees with itself:
 *   a truncation and a full re-forge both survive a self-check, so a green
 *   attestation with no anchor is a pass by omission (files/10 §2) and is
 *   refused (`AuditChainAttestedWithoutAnchor`). HB-I12 is open — no anchor
 *   publisher exists yet — so the delivered state is `anchor_missing`,
 *   fail-closed, which is the honest state and not a gap. The section is the
 *   verdict alone: the head is published outside the `platform_admin` blast
 *   radius this console sits inside, so a body carrying a chain head, or any
 *   64-hex value, is refused (`ChainHeadOnConsole`, INT-565; INT-180).
 *
 * - **Pen-test findings tracker** (files/10 §7, §9; `sec.vulns_open` /
 *   `sec.vuln_age_days`) — findings with status against the vulnerability SLA.
 *   The first external pen-test is before the P2 pilot, so no assessment is
 *   recorded and the tracker is genuinely empty (invariant 17); a finding shown
 *   with no assessment recorded is refused (`FindingsWithoutAssessment`), and a
 *   finding id that is not id-shaped is the finding's prose reappearing on a
 *   console (invariant 6, `SecurityContentLeaked`).
 *
 * No accuracy claim appears on any surface (invariant 20): every figure here is
 * a security count or an integrity verdict, never a property of the product.
 * No PHI: the sources carry ids, counts and hashes, never patient content
 * (invariant 6), and this projection widens none of them.
 */

/* ------------------------------------------------------------------ */
/* Wire contract — the recorded shape of GET /admin/security           */
/* ------------------------------------------------------------------ */

/** One detector family and whether its console feed is wired. */
export interface DetectorSummary {
  /** A sealed source: wazuh | falco | crowdsec. */
  readonly detector: string;
  /** False until this detector's alert feed is mounted into the console. */
  readonly configured: boolean;
  /** The detector's alert count, or null when its feed is not configured. */
  readonly count: number | null;
  readonly reason: string;
}

export interface SiemPayload {
  /** `siem_alerts_ingested_total`, catalogued (invariant 15). */
  readonly metric_id: string;
  /** `siem_alerts_refused_total`, catalogued (invariant 15). */
  readonly refused_metric_id: string;
  readonly metric_status: string;
  /** False until the Wazuh manager's alert stream is mounted (load_console_feed → None). */
  readonly feed_configured: boolean;
  /** sha256 of the bytes the feed was built from, or null when not configured. */
  readonly feed_version: string | null;
  /** Total admitted alerts, or null when the feed is not configured — never a 0. */
  readonly total: number | null;
  /** Alerts refused at the scrub boundary, or null when not configured. */
  readonly refused: number | null;
  /** The sealed `Signal` enumeration (auth_anomaly / k8s_audit / container_runtime / unclassified). */
  readonly allowed_signals: readonly string[];
  /** The sealed `Severity` ladder (SEV1..SEV4). */
  readonly allowed_severities: readonly string[];
  /** The sealed detector sources (wazuh / falco / crowdsec). */
  readonly allowed_sources: readonly string[];
  /** Signal → count; empty when the feed is not configured. */
  readonly by_signal: Readonly<Record<string, number>>;
  /** Severity → count; empty when the feed is not configured. */
  readonly by_severity: Readonly<Record<string, number>>;
  readonly detectors: readonly DetectorSummary[];
  readonly note: string;
}

export interface EgressDenialsPayload {
  /** `sec.egress_denied_total`, catalogued live (invariant 15). */
  readonly metric_id: string;
  readonly metric_status: string;
  /** The window the count is summed over (INT-565: `24h`). */
  readonly window: string;
  /** False when no metrics scrape backs this tile (this repo records none). */
  readonly source_available: boolean;
  /** Why the scrape was not read (`prometheus_unconfigured`, …), else null. */
  readonly source_reason: string | null;
  /** The denial count, or null when no scrape is available — never a bare 0. */
  readonly denied_total: number | null;
  /** The catalogue's operational paging target ("0 (any increase pages)"). */
  readonly target: string;
  readonly note: string;
}

/**
 * The daily verifier's verdict, and nothing read off the chain (INT-565): no
 * head, no length. HB-I12 publishes the head outside the `platform_admin`
 * blast radius, and this console sits inside it, so no admin body carries a
 * chain hash (INT-180).
 */
export interface AuditChainPayload {
  /** `sec.audit_chain_ok`, catalogued (invariant 15). */
  readonly metric_id: string;
  readonly metric_status: string;
  /** The sealed `VerifierOutcome` set (intact / chain_broken / anchor_missing). */
  readonly allowed_outcomes: readonly string[];
  readonly outcome: string;
  /** 1/true only when verified against the external anchor (files/10 §2). */
  readonly ok: boolean;
  readonly anchor_available: boolean;
  readonly reason: string;
  readonly note: string;
}

export interface PentestFinding {
  readonly finding_id: string;
  /** A sealed severity (critical / high / medium / low / info). */
  readonly severity: string;
  /** A sealed status (open / remediating / resolved / accepted_risk / false_positive). */
  readonly status: string;
  readonly sla_days: number | null;
  readonly age_days: number | null;
  readonly breached: boolean;
  readonly discovered_on: string;
}

export interface PentestPayload {
  /** `sec.vulns_open`, catalogued (invariant 15). */
  readonly metric_id: string;
  /** `sec.vuln_age_days`, catalogued (invariant 15). */
  readonly age_metric_id: string;
  readonly metric_status: string;
  /** "none_recorded" until the first external pen-test (files/10 §7). */
  readonly assessment_state: string;
  /** ISO date of the last assessment, or null when none has been conducted. */
  readonly last_assessment: string | null;
  readonly allowed_severities: readonly string[];
  readonly allowed_statuses: readonly string[];
  /** Severity → SLA days (files/10 §7: critical 3 / high 7 / medium 30). */
  readonly sla_days_by_severity: Readonly<Record<string, number>>;
  readonly findings: readonly PentestFinding[];
  readonly note: string;
}

export interface SecurityPayload {
  readonly siem: SiemPayload;
  readonly egress_denials: EgressDenialsPayload;
  readonly audit_chain: AuditChainPayload;
  readonly pentest: PentestPayload;
}

/* ------------------------------------------------------------------ */
/* Presentation tree — what the page paints                            */
/* ------------------------------------------------------------------ */

export interface DistributionBar {
  readonly key: string;
  readonly count: string;
}

export interface DetectorPresentation {
  readonly detector: string;
  readonly configured: boolean;
  /** The count as a non-grouped atom, or null when not configured. */
  readonly count: string | null;
  readonly reason: string;
}

export interface SiemPresentation {
  readonly metricId: string;
  readonly refusedMetricId: string;
  readonly metricStatus: string;
  readonly feedConfigured: boolean;
  readonly feedVersion: string | null;
  readonly total: string | null;
  readonly refused: string | null;
  readonly bySignal: readonly DistributionBar[];
  readonly bySeverity: readonly DistributionBar[];
  readonly detectors: readonly DetectorPresentation[];
  readonly note: string;
}

export interface EgressDenialsPresentation {
  readonly metricId: string;
  readonly metricStatus: string;
  readonly window: string;
  readonly sourceAvailable: boolean;
  readonly sourceReason: string | null;
  readonly deniedTotal: string | null;
  readonly target: string;
  readonly note: string;
}

export interface AuditChainPresentation {
  readonly metricId: string;
  readonly metricStatus: string;
  readonly outcome: string;
  readonly ok: boolean;
  readonly anchorAvailable: boolean;
  readonly reason: string;
  readonly note: string;
}

export interface SlaRow {
  readonly severity: string;
  readonly days: string;
}

export interface PentestFindingPresentation {
  readonly findingId: string;
  readonly severity: string;
  readonly status: string;
  readonly slaDays: string | null;
  readonly ageDays: string | null;
  readonly breached: boolean;
  readonly discoveredOn: string;
}

export interface PentestPresentation {
  readonly metricId: string;
  readonly ageMetricId: string;
  readonly metricStatus: string;
  readonly assessmentState: string;
  readonly lastAssessment: string | null;
  readonly slaDaysBySeverity: readonly SlaRow[];
  readonly empty: boolean;
  readonly findings: readonly PentestFindingPresentation[];
  readonly note: string;
}

export interface SecurityPresentation {
  readonly siem: SiemPresentation;
  readonly egressDenials: EgressDenialsPresentation;
  readonly auditChain: AuditChainPresentation;
  readonly pentest: PentestPresentation;
}

/* ------------------------------------------------------------------ */
/* Refusals — the properties a stale or tampered payload cannot buy    */
/* ------------------------------------------------------------------ */

/** A SIEM count shown while its feed is not configured — the "nothing detected"
 * vs "never wired up" confusion the feed exists to prevent (INT-205). */
export class SiemSummaryWithoutFeed extends Error {
  constructor(detail: string) {
    super(
      `refusing to render this SIEM figure: ${detail}. A count shown while the feed is not ` +
        `configured makes "nothing was detected" and "the SIEM was never wired up" look the ` +
        `same — the feed returns not-configured (None), so the console shows that, never a 0 ` +
        `(INT-205; invariant 17)`,
    );
    this.name = "SiemSummaryWithoutFeed";
  }
}

/** A SIEM signal outside the sealed `Signal` enumeration (INT-205). */
export class UnknownSecuritySignal extends Error {
  constructor(signal: string, allowed: readonly string[]) {
    super(
      `refusing to render SIEM signal '${signal}': it is not one of the sealed signals ` +
        `(${allowed.join(", ")}). The signal set is a fixed enum, so a new value is a tampered ` +
        `or drifted body`,
    );
    this.name = "UnknownSecuritySignal";
  }
}

/** A SIEM severity outside the sealed ladder (INT-205; the runbook's SEV1..SEV4). */
export class UnknownSeverity extends Error {
  constructor(severity: string, allowed: readonly string[]) {
    super(
      `refusing to render SIEM severity '${severity}': it is not one of the sealed severities ` +
        `(${allowed.join(", ")}). Both detectors' own scales are mapped onto this one ladder once, ` +
        `so a value off it is a tampered or drifted body`,
    );
    this.name = "UnknownSeverity";
  }
}

/** A detector source outside the sealed set (wazuh / falco / crowdsec). */
export class UnknownDetectorSource extends Error {
  constructor(detector: string, allowed: readonly string[]) {
    super(
      `refusing to render detector '${detector}': it is not one of the acceptance's detectors ` +
        `(${allowed.join(", ")})`,
    );
    this.name = "UnknownDetectorSource";
  }
}

/** An egress-denial count presented as observed while the scrape is unavailable. */
export class EgressCountWithoutScrape extends Error {
  constructor(deniedTotal: number) {
    super(
      `refusing to render an egress-denial count (${deniedTotal}) while no metrics scrape backs ` +
        `it: a bare number here reads as "no denials" when it may mean "no data". sec.egress_` +
        `denied_total is read from a scrape at serve time; with none, the tile is source-` +
        `unavailable, never a 0 (invariant 17; files/10 §5)`,
    );
    this.name = "EgressCountWithoutScrape";
  }
}

/** An audit-chain outcome outside the sealed `VerifierOutcome` set (INT-016). */
export class UnknownAuditOutcome extends Error {
  constructor(outcome: string, allowed: readonly string[]) {
    super(
      `refusing to render audit-chain outcome '${outcome}': it is not one of ` +
        `(${allowed.join(", ")}). The verifier's outcomes are a fixed set, so a new value is a ` +
        `tampered or drifted body`,
    );
    this.name = "UnknownAuditOutcome";
  }
}

/** A green audit-chain attestation with no external anchor — a pass by omission. */
export class AuditChainAttestedWithoutAnchor extends Error {
  constructor(detail: string) {
    super(
      `refusing to render an intact audit chain: ${detail}. 1 means verified against the ` +
        `EXTERNALLY ANCHORED head, never merely that the store agrees with itself — a truncation ` +
        `and a full re-forge both survive a self-check, so a green verdict with no anchor is a ` +
        `pass by omission (files/10 §2; invariant 4; HB-I12)`,
    );
    this.name = "AuditChainAttestedWithoutAnchor";
  }
}

/** An audit-chain section carrying a chain head or anything shaped like one. */
export class ChainHeadOnConsole extends Error {
  constructor(detail: string) {
    super(
      `refusing to render the audit chain: ${detail}. The head is published outside the ` +
        `platform_admin blast radius and this console sits inside it, so it carries no chain ` +
        `hash — an operator who could read the head here could check a forgery against it ` +
        `(HB-I12; INT-180)`,
    );
    this.name = "ChainHeadOnConsole";
  }
}

/** A pen-test finding shown with no assessment recorded — empty vs not-conducted. */
export class FindingsWithoutAssessment extends Error {
  constructor(count: number) {
    super(
      `refusing to render ${count} pen-test finding(s) with no assessment recorded: a finding ` +
        `implies an assessment produced it, and "no assessment has been conducted" must not read ` +
        `as "assessed, nothing found" (files/10 §7; invariant 17)`,
    );
    this.name = "FindingsWithoutAssessment";
  }
}

/** A pen-test finding severity outside the sealed set. */
export class UnknownFindingSeverity extends Error {
  constructor(severity: string, allowed: readonly string[]) {
    super(
      `refusing to render pen-test finding severity '${severity}': it is not one of ` +
        `(${allowed.join(", ")})`,
    );
    this.name = "UnknownFindingSeverity";
  }
}

/** A pen-test finding status outside the sealed set. */
export class UnknownFindingStatus extends Error {
  constructor(status: string, allowed: readonly string[]) {
    super(
      `refusing to render pen-test finding status '${status}': it is not one of ` +
        `(${allowed.join(", ")}). The status set is a fixed vocabulary, so a new value is a ` +
        `tampered or drifted body`,
    );
    this.name = "UnknownFindingStatus";
  }
}

/** A security field carrying free text where an id belongs (invariant 6). */
export class SecurityContentLeaked extends Error {
  constructor(field: string, value: string) {
    super(
      `refusing to render field '${field}': '${value}' is not id-shaped, so it may carry a ` +
        `finding's prose — a system name, a path or patient content. Security surfaces hold ids, ` +
        `counts and hashes, never narrative (invariant 6)`,
    );
    this.name = "SecurityContentLeaked";
  }
}

/* ------------------------------------------------------------------ */
/* Renderers                                                           */
/* ------------------------------------------------------------------ */

/** Id shape mirrored from the safety module: starts alphanumeric, then id
 * characters only — a sentence carries none (invariant 6). */
const REF_SHAPE = /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$/;
/** The shape of a hash-chain head anywhere in a string (INT-180's guard). */
const HEX64_ANYWHERE = /\b[0-9a-f]{64}\b/;

/** A count crosses the boundary as one atom, no grouping separator (inv 22). */
function count(value: number): string {
  return value.toLocaleString("en-GB", { useGrouping: false });
}

/** A genuine value or a genuine absence — never a bare 0 in the empty state. */
function figure(value: number | null): string | null {
  return value === null ? null : count(value);
}

/** Build a distribution over a sealed key set, refusing an off-set key. */
function distribution(
  counts: Readonly<Record<string, number>>,
  allowed: readonly string[],
  onUnknown: (key: string) => never,
): readonly DistributionBar[] {
  return Object.keys(counts).map((key) => {
    if (!allowed.includes(key)) {
      onUnknown(key);
    }
    return { key, count: count(counts[key]!) };
  });
}

/** Build the SIEM summaries, refusing a count without a feed or an off-set key. */
export function renderSiemSummaries(payload: SiemPayload): SiemPresentation {
  // the whole feed: a count present while not configured is the confusion the
  // feed exists to prevent
  if (!payload.feed_configured) {
    if (payload.total !== null) {
      throw new SiemSummaryWithoutFeed("total is set while feed_configured is false");
    }
    if (payload.refused !== null) {
      throw new SiemSummaryWithoutFeed("refused is set while feed_configured is false");
    }
    if (Object.keys(payload.by_signal).length > 0 || Object.keys(payload.by_severity).length > 0) {
      throw new SiemSummaryWithoutFeed("a distribution is present while feed_configured is false");
    }
  }

  const bySignal = distribution(payload.by_signal, payload.allowed_signals, (key) => {
    throw new UnknownSecuritySignal(key, payload.allowed_signals);
  });
  const bySeverity = distribution(payload.by_severity, payload.allowed_severities, (key) => {
    throw new UnknownSeverity(key, payload.allowed_severities);
  });

  const detectors = payload.detectors.map((detector) => {
    if (!payload.allowed_sources.includes(detector.detector)) {
      throw new UnknownDetectorSource(detector.detector, payload.allowed_sources);
    }
    // per detector: a count while its own feed is not configured is the same leak
    if (!detector.configured && detector.count !== null) {
      throw new SiemSummaryWithoutFeed(
        `detector '${detector.detector}' carries a count while it is not configured`,
      );
    }
    return {
      detector: detector.detector,
      configured: detector.configured,
      count: figure(detector.count),
      reason: detector.reason,
    };
  });

  return {
    metricId: payload.metric_id,
    refusedMetricId: payload.refused_metric_id,
    metricStatus: payload.metric_status,
    feedConfigured: payload.feed_configured,
    feedVersion: payload.feed_version,
    total: figure(payload.total),
    refused: figure(payload.refused),
    bySignal,
    bySeverity,
    detectors,
    note: payload.note,
  };
}

/** Build the egress-denial tile, refusing a count with no scrape behind it. */
export function renderEgressDenials(payload: EgressDenialsPayload): EgressDenialsPresentation {
  if (!payload.source_available && payload.denied_total !== null) {
    throw new EgressCountWithoutScrape(payload.denied_total);
  }
  return {
    metricId: payload.metric_id,
    metricStatus: payload.metric_status,
    window: payload.window,
    sourceAvailable: payload.source_available,
    sourceReason: payload.source_available ? null : payload.source_reason,
    deniedTotal: figure(payload.denied_total),
    target: payload.target,
    note: payload.note,
  };
}

/** The keys a chain read would add; the console's section carries none. */
const CHAIN_KEYS = ["local_head", "anchor_head", "entry_hash", "head"] as const;

/** Build the audit-chain status, refusing a chain hash or a green verdict with no anchor. */
export function renderAuditChainStatus(payload: AuditChainPayload): AuditChainPresentation {
  for (const key of CHAIN_KEYS) {
    if (Object.prototype.hasOwnProperty.call(payload, key)) {
      throw new ChainHeadOnConsole(`the section carries '${key}'`);
    }
  }
  if (HEX64_ANYWHERE.test(JSON.stringify(payload))) {
    throw new ChainHeadOnConsole("the section carries a 64-hex value");
  }
  if (!payload.allowed_outcomes.includes(payload.outcome)) {
    throw new UnknownAuditOutcome(payload.outcome, payload.allowed_outcomes);
  }
  if (payload.ok && (payload.outcome !== "intact" || !payload.anchor_available)) {
    throw new AuditChainAttestedWithoutAnchor(
      `ok is true while outcome='${payload.outcome}' and anchor_available=${String(
        payload.anchor_available,
      )}`,
    );
  }
  return {
    metricId: payload.metric_id,
    metricStatus: payload.metric_status,
    outcome: payload.outcome,
    ok: payload.ok,
    anchorAvailable: payload.anchor_available,
    reason: payload.reason,
    note: payload.note,
  };
}

function renderFinding(
  finding: PentestFinding,
  payload: PentestPayload,
): PentestFindingPresentation {
  if (!REF_SHAPE.test(finding.finding_id)) {
    throw new SecurityContentLeaked("finding_id", finding.finding_id);
  }
  if (!REF_SHAPE.test(finding.discovered_on)) {
    throw new SecurityContentLeaked("discovered_on", finding.discovered_on);
  }
  if (!payload.allowed_severities.includes(finding.severity)) {
    throw new UnknownFindingSeverity(finding.severity, payload.allowed_severities);
  }
  if (!payload.allowed_statuses.includes(finding.status)) {
    throw new UnknownFindingStatus(finding.status, payload.allowed_statuses);
  }
  return {
    findingId: finding.finding_id,
    severity: finding.severity,
    status: finding.status,
    slaDays: figure(finding.sla_days),
    ageDays: figure(finding.age_days),
    breached: finding.breached,
    discoveredOn: finding.discovered_on,
  };
}

/** Build the pen-test tracker, refusing findings with no assessment behind them. */
export function renderPentestTracker(payload: PentestPayload): PentestPresentation {
  const assessed = payload.assessment_state === "assessed" && payload.last_assessment !== null;
  if (payload.findings.length > 0 && !assessed) {
    throw new FindingsWithoutAssessment(payload.findings.length);
  }
  const slaDaysBySeverity: SlaRow[] = Object.keys(payload.sla_days_by_severity).map((severity) => {
    if (!payload.allowed_severities.includes(severity)) {
      throw new UnknownFindingSeverity(severity, payload.allowed_severities);
    }
    return { severity, days: count(payload.sla_days_by_severity[severity]!) };
  });
  const findings = payload.findings.map((finding) => renderFinding(finding, payload));
  return {
    metricId: payload.metric_id,
    ageMetricId: payload.age_metric_id,
    metricStatus: payload.metric_status,
    assessmentState: payload.assessment_state,
    lastAssessment: payload.last_assessment,
    slaDaysBySeverity,
    empty: findings.length === 0,
    findings,
    note: payload.note,
  };
}

/**
 * Build the whole module from the recorded composite.
 *
 * A refusal in any surface propagates: a Security console that painted a SIEM
 * count over an unwired feed, an egress zero with no scrape, a green audit chain
 * with no anchor, or a finding with no assessment would be worse than no
 * console — an operator would be misinformed at exactly the moment it matters —
 * so the page does not render past one.
 */
export function renderSecurityModule(payload: SecurityPayload): SecurityPresentation {
  return {
    siem: renderSiemSummaries(payload.siem),
    egressDenials: renderEgressDenials(payload.egress_denials),
    auditChain: renderAuditChainStatus(payload.audit_chain),
    pentest: renderPentestTracker(payload.pentest),
  };
}
