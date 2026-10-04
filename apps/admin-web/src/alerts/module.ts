/**
 * INT-481 — the Alerts page's view-model.
 *
 * One input is the `GET /admin/alerts` document (`intake.admin.alerts.v1`):
 * what Alertmanager holds right now, reduced by the API to ids. One output is
 * the tree the page paints. The input arrives as `unknown` and is checked
 * field by field, because this page renders nothing the contract does not
 * name. It refuses rather than repairs:
 *
 * - another schema: {@link OpsSchemaMismatch};
 * - a key outside the contract at any level (an alert's annotations are prose
 *   and never cross), or a missing one: {@link AlertsShapeRefused};
 * - a severity, state or label key outside its closed set, or an alertname or
 *   label value that is not id-shaped (invariant 6): {@link OpsLabelLeaked};
 * - an unknown source that carries a figure (invariant 17 — unknown is a
 *   state, and a figure beside it is a guess): {@link OpsUnknownCarriesFigure};
 * - counts that disagree with the rows they count: {@link AlertsCountsIncoherent};
 * - a reason outside the known codes, a timestamp that is not exactly
 *   `YYYY-MM-DDTHH:MM:SSZ`, or a count that is not a non-negative integer:
 *   {@link OpsPayloadRefused}.
 *
 * Numbers leave as plain strings with no grouping (invariant 22).
 */

import {
  ID,
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsSchemaMismatch,
  OpsUnknownCarriesFigure,
} from "../ops/guards";

export const ALERTS_SCHEMA = "intake.admin.alerts.v1";

export const SEVERITIES = ["page", "ticket", "other"] as const;
export const ALERT_STATES = ["active", "suppressed", "unprocessed"] as const;
/** The only label keys that cross; the order is the order they are shown in. */
export const LABEL_KEYS = ["service", "slo", "component", "budget_id", "scope", "period"] as const;

export type Severity = (typeof SEVERITIES)[number];
export type AlertState = (typeof ALERT_STATES)[number];
export type LabelKey = (typeof LABEL_KEYS)[number];
export type SourceState = "ok" | "unknown";

// --- the wire shape (field names are the API's) ---------------------------------

export interface AlertPayload {
  alertname: string;
  severity: Severity;
  state: AlertState;
  starts_at: string;
  labels: Partial<Record<LabelKey, string>>;
}

export interface AlertsPayload {
  schema: typeof ALERTS_SCHEMA;
  generated_at: string;
  source: { state: SourceState; reason: string | null };
  counts: Record<Severity, number> | null;
  alerts: AlertPayload[];
  withheld: number;
}

// --- the view ------------------------------------------------------------------

export interface AlertView {
  alertname: string;
  severity: Severity;
  state: AlertState;
  startsAt: string;
  labels: { key: LabelKey; value: string }[];
}

export interface AlertsView {
  generatedAt: string;
  source: { state: SourceState; reason: string | null };
  /** `null` exactly when the source is unknown. */
  counts: Record<Severity, string> | null;
  alerts: AlertView[];
  /** `null` exactly when the source is unknown. */
  withheld: string | null;
}

export class AlertsShapeRefused extends OpsPayloadRefused {}
export class AlertsCountsIncoherent extends OpsPayloadRefused {}

// --- shapes --------------------------------------------------------------------

const ALERTNAME = /^[A-Za-z][A-Za-z0-9_]{0,127}$/;
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const REASONS = new Set([
  "alertmanager_unconfigured",
  "alertmanager_misconfigured",
  "alertmanager_unreachable",
  "alertmanager_bad_response",
]);
const HTTP_REASON = /^alertmanager_http_[0-9]{3}$/;

const TOP_KEYS = ["schema", "generated_at", "source", "counts", "alerts", "withheld"];
const SOURCE_KEYS = ["state", "reason"];
const ALERT_KEYS = ["alertname", "severity", "state", "starts_at", "labels"];

function record(value: unknown, what: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new AlertsShapeRefused("not_an_object", `${what} is not an object`);
  }
  return value as Record<string, unknown>;
}

/** Exactly these keys: none missing, none added. */
function exactly(value: unknown, keys: readonly string[], what: string): Record<string, unknown> {
  const object = record(value, what);
  const present = Object.keys(object);
  const extra = present.filter((key) => !keys.includes(key));
  if (extra.length > 0) {
    throw new AlertsShapeRefused("unexpected_key", `${what} carries a key outside the contract`);
  }
  if (keys.some((key) => !present.includes(key))) {
    throw new AlertsShapeRefused("missing_key", `${what} is missing a key of the contract`);
  }
  return object;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], what: string): T {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) {
    throw new OpsLabelLeaked("label_outside_vocabulary", `${what} is outside its closed set`);
  }
  return value as T;
}

function instant(value: unknown, what: string): string {
  if (typeof value !== "string" || !INSTANT.test(value)) {
    throw new OpsPayloadRefused("not_a_date", `${what} is not YYYY-MM-DDTHH:MM:SSZ`);
  }
  // the pattern admits month 13 and February 30; a real instant round-trips
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString() !== value.replace("Z", ".000Z")) {
    throw new OpsPayloadRefused("not_a_date", `${what} is not a calendar instant`);
  }
  return value;
}

function tally(value: unknown, what: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new OpsPayloadRefused("not_a_count", `${what} is not a non-negative integer`);
  }
  return value;
}

function sourceOf(value: unknown): AlertsView["source"] {
  const source = exactly(value, SOURCE_KEYS, "source");
  const state = source["state"];
  const reason = source["reason"];
  if (state === "ok") {
    if (reason !== null) {
      throw new OpsPayloadRefused("reason_outside_set", "an ok source names no reason");
    }
    return { state, reason: null };
  }
  if (state === "unknown") {
    if (typeof reason !== "string" || !(REASONS.has(reason) || HTTP_REASON.test(reason))) {
      throw new OpsPayloadRefused("reason_outside_set", "an unknown source names a known code");
    }
    return { state, reason };
  }
  throw new OpsPayloadRefused("unknown_state", "source state must be ok or unknown");
}

function labelsOf(value: unknown, where: string): AlertView["labels"] {
  const labels = record(value, `${where}.labels`);
  for (const key of Object.keys(labels)) {
    if (!(LABEL_KEYS as readonly string[]).includes(key)) {
      throw new OpsLabelLeaked("label_key_outside_set", `${where}: a label key outside the set`);
    }
  }
  return LABEL_KEYS.filter((key) => Object.hasOwn(labels, key)).map((key) => {
    const raw = labels[key];
    if (typeof raw !== "string" || !ID.test(raw)) {
      throw new OpsLabelLeaked("label_not_id_shaped", `${where}.${key} is not id-shaped`);
    }
    return { key, value: raw };
  });
}

function alertOf(value: unknown, index: number): AlertView {
  const where = `alerts[${index}]`;
  const alert = exactly(value, ALERT_KEYS, where);
  const name = alert["alertname"];
  if (typeof name !== "string" || !ALERTNAME.test(name)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${where}.alertname is not an identifier`);
  }
  return {
    alertname: name,
    severity: oneOf(alert["severity"], SEVERITIES, `${where}.severity`),
    state: oneOf(alert["state"], ALERT_STATES, `${where}.state`),
    startsAt: instant(alert["starts_at"], `${where}.starts_at`),
    labels: labelsOf(alert["labels"], where),
  };
}

function countsOf(value: unknown): Record<Severity, number> {
  const counts = exactly(value, SEVERITIES, "counts");
  return {
    page: tally(counts["page"], "counts.page"),
    ticket: tally(counts["ticket"], "counts.ticket"),
    other: tally(counts["other"], "counts.other"),
  };
}

/**
 * The counts cover the listed alerts only, whatever their state; the withheld
 * ones are counted apart. So each severity's count is exactly its rows: a
 * count above them names alerts the page cannot show, and one below hides
 * rows it does show.
 */
function coherent(counts: Record<Severity, number>, alerts: AlertView[]): void {
  for (const severity of SEVERITIES) {
    const shown = alerts.filter((alert) => alert.severity === severity).length;
    if (counts[severity] !== shown) {
      throw new AlertsCountsIncoherent(
        "counts_incoherent",
        `the ${severity} count is not the number of ${severity} rows`,
      );
    }
  }
}

/** The whole Alerts view. Throws an `OpsPayloadRefused` rather than paint a lie. */
export function renderAlerts(payload: unknown): AlertsView {
  const body = exactly(payload, TOP_KEYS, "payload");
  if (body["schema"] !== ALERTS_SCHEMA) {
    throw new OpsSchemaMismatch("schema_mismatch", `expected ${ALERTS_SCHEMA}`);
  }
  const generatedAt = instant(body["generated_at"], "generated_at");
  const source = sourceOf(body["source"]);
  if (!Array.isArray(body["alerts"])) {
    throw new AlertsShapeRefused("not_a_list", "alerts is not a list");
  }
  const rows: unknown[] = body["alerts"];
  const withheld = tally(body["withheld"], "withheld");

  if (source.state === "unknown") {
    if (body["counts"] !== null || rows.length > 0 || withheld !== 0) {
      throw new OpsUnknownCarriesFigure(
        "unknown_carries_figure",
        "the source is unknown and still carries a figure (invariant 17)",
      );
    }
    return { generatedAt, source, counts: null, alerts: [], withheld: null };
  }

  if (body["counts"] === null) {
    throw new AlertsCountsIncoherent("counts_missing", "an ok source carries counts");
  }
  const counts = countsOf(body["counts"]);
  const alerts = rows.map(alertOf);
  coherent(counts, alerts);
  return {
    generatedAt,
    source,
    counts: {
      page: String(counts.page),
      ticket: String(counts.ticket),
      other: String(counts.other),
    },
    alerts,
    withheld: String(withheld),
  };
}
