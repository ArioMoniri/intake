/**
 * INT-490 — the Analytics page's view-model (LD-06; files/08 §2.1 `researcher`).
 *
 * One input — the `GET /admin/analytics` document, fetched server-side by
 * `load.ts` — and one output: the tree the page paints. Pure, and it refuses
 * rather than repairs. The API already gated the release within and across
 * views; this is the page's own, independent statement of the same rules, so
 * a bent or stale API cannot make the page paint what LD-06 forbids:
 *
 * - {@link AnalyticsThinCellRendered} — a shown cell holding 1..k-1 people, or
 *   a shown view whose population is under k;
 * - {@link AnalyticsWithheldCarriesCells} — a withheld view that still carries
 *   a cell (LD-06 `whole_views_only`: none of its cells show);
 * - {@link AnalyticsFloorLowered} — a k under the product floor of ten;
 * - the shared refusals of `../ops/guards`: another schema, a label that is
 *   not id-shaped or outside its closed set (invariant 6), a target beside a
 *   figure (invariant 20).
 *
 * Every figure leaves as a string a reader cannot misread (invariant 22): a
 * count, or a whole percentage joined to its sign by a no-break space. A
 * share is always "of this table's people" — a measurement of a named week,
 * never a property of the product (invariant 20).
 */

import {
  ISO,
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsSchemaMismatch,
  OpsSuppressedCohortLeaked,
  REASON,
  noTarget,
  percent,
} from "../ops/guards";
import {
  ANALYTICS_SCHEMA,
  type AnalyticsPayload,
  type ViewKind,
  type ViewPayload,
} from "./payload";

export type * from "./payload";
export { ANALYTICS_SCHEMA } from "./payload";

export class AnalyticsThinCellRendered extends OpsSuppressedCohortLeaked {}
export class AnalyticsWithheldCarriesCells extends OpsSuppressedCohortLeaked {}
export class AnalyticsFloorLowered extends OpsSuppressedCohortLeaked {}

/** LD-06 `cell_size.product_floor_subjects`; INT-171's K_ANONYMITY_FLOOR. */
export const PRODUCT_FLOOR = 10;

/** The server's id shape (INT-171 `_ID_SHAPE`): mixed case and `:` allowed. */
const DIMENSION_VALUE = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/;
const PERIOD = /^\d{4}-W\d{2}$/;

interface KindSpec {
  partition: string;
  scope: "family" | "question";
  /** `null` — a registry-defined domain (locale), checked for shape only */
  domain: readonly string[] | null;
}

export const KINDS: Record<ViewKind, KindSpec> = {
  funnel: {
    partition: "stage",
    scope: "family",
    domain: ["invited", "started", "finished", "shared"],
  },
  triage: {
    partition: "triage_level",
    scope: "family",
    domain: ["red", "yellow", "green", "not_evaluated"],
  },
  locale: { partition: "locale", scope: "family", domain: null },
  platform: { partition: "platform", scope: "family", domain: ["ios", "android", "web"] },
  question_outcome: {
    partition: "outcome",
    scope: "question",
    domain: ["answered", "skipped", "abandoned"],
  },
  question_mode: { partition: "input_mode", scope: "question", domain: ["typed", "voice"] },
  question_repeat: { partition: "repeat_band", scope: "question", domain: ["none", "one_or_more"] },
  question_time: {
    partition: "time_band",
    scope: "question",
    domain: ["under_10s", "10s_to_30s", "30s_to_60s", "over_60s"],
  },
  question_asr: { partition: "asr_band", scope: "question", domain: ["high", "medium", "low"] },
};

const FAMILY_ORDER: readonly ViewKind[] = ["funnel", "triage", "locale", "platform"];
export const QUESTION_ORDER: readonly ViewKind[] = [
  "question_outcome",
  "question_mode",
  "question_repeat",
  "question_time",
  "question_asr",
];

export interface RowView {
  value: string;
  people: string;
  share: string | null;
  /** funnel only: people lost since the previous stage */
  dropOff: string | null;
  /** for a `<meter>`: the count and the table's population */
  meter: { value: number; max: number };
}

export interface TableView {
  kind: ViewKind;
  state: "shown" | "withheld";
  reason: "below_k" | "cross_view" | null;
  population: string | null;
  rows: RowView[];
}

export interface QuestionView {
  question: string;
  tables: TableView[];
}

export interface FamilyView {
  protocol: string;
  version: string;
  tables: TableView[];
  questions: QuestionView[];
}

export interface AnalyticsView {
  generatedAt: string;
  k: number;
  period: { id: string; start: string; end: string; previous: string; following: string | null };
  tenants: { state: "unconfigured" } | { state: "configured"; admitted: string; refused: string };
  retention: {
    aggregates: { state: "undecided" } | { state: "set"; days: string };
    rawTelemetry: { state: "undecided" } | { state: "set"; days: string };
  };
  families: FamilyView[];
  notCollected: { kind: ViewKind; reason: string }[];
}

function dimension(value: unknown, what: string): string {
  if (typeof value !== "string" || !DIMENSION_VALUE.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not id-shaped (invariant 6)`);
  }
  return value;
}

function kindOf(value: unknown, what: string): ViewKind {
  if (typeof value !== "string" || !(value in KINDS)) {
    throw new OpsLabelLeaked("label_outside_vocabulary", `${what} is not a view kind`);
  }
  return value as ViewKind;
}

function instant(value: unknown, what: string): string {
  if (typeof value !== "string" || !ISO.test(value)) {
    throw new OpsPayloadRefused("not_a_date", `${what} is not a timestamp`);
  }
  return value;
}

function period(value: unknown, what: string): string {
  if (typeof value !== "string" || !PERIOD.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not an ISO week`);
  }
  return value;
}

function wholeCount(value: unknown, what: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new OpsPayloadRefused("not_a_count", `${what} is not a count`);
  }
  return value;
}

function retention(
  value: unknown,
  what: string,
): { state: "undecided" } | { state: "set"; days: string } {
  const item = value as { state?: unknown; days?: unknown } | null;
  if (item?.state === "undecided") return { state: "undecided" };
  if (item?.state === "set") return { state: "set", days: String(wholeCount(item.days, what)) };
  throw new OpsPayloadRefused("retention_state_unknown", `${what} is neither set nor undecided`);
}

function table(view: ViewPayload, k: number): TableView {
  const kind = kindOf(view.kind, "view kind");
  const spec = KINDS[kind];
  if (view.partition !== spec.partition) {
    throw new OpsLabelLeaked("label_outside_vocabulary", `${kind}: partition is not its own`);
  }
  if (view.state === "withheld") {
    if ("cells" in view) {
      throw new AnalyticsWithheldCarriesCells(
        "withheld_view_carries_cells",
        `${kind}: a withheld view shows none of its cells (LD-06 whole_views_only)`,
      );
    }
    if (view.reason !== "below_k" && view.reason !== "cross_view") {
      throw new OpsPayloadRefused("withheld_reason_unknown", `${kind}: unknown withheld reason`);
    }
    return { kind, state: "withheld", reason: view.reason, population: null, rows: [] };
  }
  if (view.state !== "shown" || !Array.isArray(view.cells) || view.cells.length === 0) {
    throw new OpsPayloadRefused("view_state_unknown", `${kind}: neither shown nor withheld`);
  }
  const cells = view.cells.map((cell) => {
    const value = dimension(cell.value, `${kind} cell`);
    if (spec.domain !== null && !spec.domain.includes(value)) {
      throw new OpsLabelLeaked("label_outside_vocabulary", `${kind}: a cell outside its domain`);
    }
    const subjects = wholeCount(cell.subjects, `${kind} cell`);
    if (subjects > 0 && subjects < k) {
      throw new AnalyticsThinCellRendered(
        "thin_cell",
        `${kind}: a cell of 1..${k - 1} people is never shown (LD-06)`,
      );
    }
    return { value, subjects };
  });
  const total = cells.reduce((sum, cell) => sum + cell.subjects, 0);
  if (total < k) {
    throw new AnalyticsThinCellRendered("thin_cell", `${kind}: a population under ${k}`);
  }
  if (kind === "funnel") {
    // The funnel's cells are the furthest stage each person reached; the
    // page shows how many reached AT LEAST each stage, and the loss between
    // stages — every one of them a sum or difference of shown cells.
    const order = spec.domain ?? [];
    const byStage = new Map(cells.map((cell) => [cell.value, cell.subjects]));
    let reached = total;
    let previous: number | null = null;
    const rows: RowView[] = [];
    for (const stage of order) {
      rows.push({
        value: stage,
        people: String(reached),
        share: percent(reached / total),
        dropOff: previous === null ? null : String(previous - reached),
        meter: { value: reached, max: total },
      });
      previous = reached;
      reached -= byStage.get(stage) ?? 0;
    }
    return { kind, state: "shown", reason: null, population: String(total), rows };
  }
  return {
    kind,
    state: "shown",
    reason: null,
    population: String(total),
    rows: cells.map((cell) => ({
      value: cell.value,
      people: String(cell.subjects),
      share: percent(cell.subjects / total),
      dropOff: null,
      meter: { value: cell.subjects, max: total },
    })),
  };
}

export function renderAnalytics(payload: AnalyticsPayload): AnalyticsView {
  if (payload?.schema !== ANALYTICS_SCHEMA) {
    throw new OpsSchemaMismatch("schema_mismatch", "not an intake.admin.analytics.v1 document");
  }
  noTarget(payload, "analytics");
  const k = wholeCount(payload.k, "k");
  if (k < PRODUCT_FLOOR) {
    throw new AnalyticsFloorLowered("k_below_floor", `k=${k} is under the product floor`);
  }
  if (payload.grain !== "iso_week") {
    throw new OpsPayloadRefused("grain_unknown", "the release is cut by ISO week only");
  }
  const families = new Map<string, FamilyView>();
  for (const view of payload.views) {
    const protocol = dimension(view.dimensions?.protocol, "protocol");
    const version = dimension(view.dimensions?.protocol_version, "protocol_version");
    const keys = Object.keys(view.dimensions ?? {});
    const kind = kindOf(view.kind, "view kind");
    const questionScoped = KINDS[kind].scope === "question";
    const allowed = questionScoped
      ? ["protocol", "protocol_version", "question"]
      : ["protocol", "protocol_version"];
    if (keys.some((key) => !allowed.includes(key)) || keys.length !== allowed.length) {
      throw new OpsLabelLeaked("dimension_key_refused", `${kind}: dimensions are not its own`);
    }
    const key = `${protocol}\u0000${version}`;
    const family = families.get(key) ?? { protocol, version, tables: [], questions: [] };
    families.set(key, family);
    const rendered = table(view, k);
    if (!questionScoped) {
      family.tables.push(rendered);
      continue;
    }
    const question = dimension(view.dimensions.question, "question");
    let entry = family.questions.find((item) => item.question === question);
    if (entry === undefined) {
      entry = { question, tables: [] };
      family.questions.push(entry);
    }
    entry.tables.push(rendered);
  }
  for (const family of families.values()) {
    family.tables.sort((a, b) => FAMILY_ORDER.indexOf(a.kind) - FAMILY_ORDER.indexOf(b.kind));
    for (const question of family.questions) {
      question.tables.sort(
        (a, b) => QUESTION_ORDER.indexOf(a.kind) - QUESTION_ORDER.indexOf(b.kind),
      );
    }
  }
  const tenants = payload.tenants;
  return {
    generatedAt: instant(payload.generated_at, "generated_at"),
    k,
    period: {
      id: period(payload.period.id, "period"),
      start: instant(payload.period.start, "period start"),
      end: instant(payload.period.end, "period end"),
      previous: period(payload.period.previous, "previous period"),
      following:
        payload.period.following === null ? null : period(payload.period.following, "next period"),
    },
    tenants:
      tenants.state === "unconfigured"
        ? { state: "unconfigured" }
        : {
            state: "configured",
            admitted: String(wholeCount(tenants.admitted, "admitted tenants")),
            refused: String(wholeCount(tenants.refused, "refused tenants")),
          },
    retention: {
      aggregates: retention(payload.retention.aggregates, "aggregate retention"),
      rawTelemetry: retention(payload.retention.raw_telemetry, "raw telemetry retention"),
    },
    families: [...families.values()],
    notCollected: payload.not_collected.map((item) => {
      if (typeof item.reason !== "string" || !REASON.test(item.reason)) {
        throw new OpsPayloadRefused("reason_not_a_code", "a not-collected reason is not a code");
      }
      return { kind: kindOf(item.kind, "not-collected kind"), reason: item.reason };
    }),
  };
}
