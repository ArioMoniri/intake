/**
 * INT-181 — the overview's view-model (files/08 §3 Overview, Reliability).
 *
 * Two inputs, both fetched server-side by `load.ts`: the `GET /admin/reliability`
 * composite and the API's own `/readyz`. One output: the tree the page paints.
 *
 * Pure, and it refuses rather than repairs — with the shared refusals of
 * `../ops/guards` (schema, ids, unknown-with-a-figure, targets) and three of
 * its own, each a figure the page would otherwise paint over its own evidence:
 * - {@link OverviewBurnInconsistent} — a lane's alert condition that is not
 *   exactly "both windows above the factor" (or that is claimed while a window
 *   has no observation). A stale or bent payload cannot hide a burning budget.
 * - {@link OverviewBudgetInconsistent} — a budget remaining that does not
 *   follow from the SLI and objective printed beside it.
 * - {@link OverviewStaleRenderedFresh} — a probe result past three sweeps, or
 *   of unknown age, presented as current (invariant 17: never a stale value).
 */

import {
  ID,
  ISO,
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsSchemaMismatch,
  OpsUnknownCarriesFigure,
  REASON,
  blank,
  id,
  noTarget,
  age,
  reason,
  withUnit,
  type Age,
} from "../ops/guards";

// INT-560: the age formatter moved to ../ops/guards, which the ops console's
// registry tile reads too; re-exported so every existing import keeps its path.
export { age, type Age } from "../ops/guards";
import type { Probe } from "../ops/payload";
import {
  RELIABILITY_SCHEMA,
  type ReliabilityPayload,
  type SloTilePayload,
  type TileState,
} from "./payload";

export type * from "./payload";
export { RELIABILITY_SCHEMA } from "./payload";

export class OverviewBurnInconsistent extends OpsPayloadRefused {}
export class OverviewBudgetInconsistent extends OpsPayloadRefused {}
export class OverviewStaleRenderedFresh extends OpsPayloadRefused {}

const WINDOW = /^[0-9]{1,4}[smhd]$/;
const HEALTH = new Set(["healthy", "degraded", "unhealthy", "skipped", "unknown"]);
const PROBE_STATUS = new Set(["healthy", "unhealthy", "skipped", "no_result"]);
const BREAKER_HEALTH: Record<string, string> = {
  closed: "healthy",
  half_open: "degraded",
  open: "unhealthy",
};
const FALLBACK_KINDS = new Set(["none", "component", "in_process"]);
const SEVERITIES = new Set(["page", "ticket"]);
const UP_DOWN = new Set(["healthy", "unhealthy"]);
/** A budget remaining may differ from its recomputation by float noise only. */
const BUDGET_TOLERANCE = 1e-3;

// --- shapes --------------------------------------------------------------------

function oneOf(value: string, allowed: Set<string>, what: string): string {
  if (typeof value !== "string" || !allowed.has(value)) {
    throw new OpsLabelLeaked("label_outside_vocabulary", `${what} is outside its closed set`);
  }
  return value;
}

function window(value: string, what: string): string {
  if (typeof value !== "string" || !WINDOW.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not a window`);
  }
  return value;
}

function instant(value: string | null, what: string): string | null {
  if (value !== null && (typeof value !== "string" || !ISO.test(value))) {
    throw new OpsPayloadRefused("not_a_date", `${what} is not a timestamp`);
  }
  return value;
}

function code(value: string | null, what: string): string | null {
  if (value !== null && (typeof value !== "string" || !REASON.test(value))) {
    throw new OpsPayloadRefused("reason_not_a_code", `${what} is not a code`);
  }
  return value;
}

function finite(value: number | null, what: string): number | null {
  if (value !== null && (typeof value !== "number" || !Number.isFinite(value))) {
    throw new OpsPayloadRefused("not_a_number", `${what} is not a finite number`);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

// --- formatting (invariant 22) -------------------------------------------------

function fixed(value: number | null, digits: number, unit: string): string | null {
  return value === null ? null : withUnit(value.toFixed(digits), unit);
}

function latency(value: number | null): string | null {
  if (value === null) return null;
  const digits = value < 1 ? 2 : value < 10 ? 1 : 0;
  return withUnit(value.toFixed(digits), "ms");
}

// --- the view ------------------------------------------------------------------

export interface BurnLaneView {
  lane: string;
  severity: string;
  factor: string;
  longWindow: string;
  shortWindow: string;
  longBurn: string | null;
  shortBurn: string | null;
  conditionMet: boolean | null;
}

export interface SloView {
  key: string;
  service: string;
  slo: string;
  state: TileState;
  reason: string | null;
  objective: string;
  window: string;
  sli: string | null;
  budgetRemaining: string | null;
  budgetOverspent: boolean | null;
  lanes: BurnLaneView[];
}

export interface ProbeRowView {
  component: string;
  probe: string;
  phiPath: boolean;
  selfHostedNow: boolean;
  budget: string;
  status: string;
  latency: string | null;
  checkedAt: string | null;
  age: Age | null;
  stale: boolean;
}

export interface ComponentRowView {
  component: string;
  probe: string;
  health: string;
  healthReason: string | null;
  checkedAt: string | null;
  fallbackKind: string;
  fallback: string | null;
  fallbackHealth: string | null;
}

interface Head {
  state: TileState;
  reason: string | null;
}

export interface OverviewView {
  generatedAt: string;
  sources: { prometheus: string; sloFiles: string; registry: string; probeSweep: string };
  slos: Head & { tiles: SloView[] };
  probeMatrix: Head & { sweepInterval: Age | null; staleAfter: Age | null; rows: ProbeRowView[] };
  dependencies: {
    components: Head & { rows: ComponentRowView[] };
    prometheus: Head & { health: string | null; healthReason: string | null };
    gpuHosts: Head & { rows: { hostId: string; health: string }[] };
    vendors: Head & { rows: { component: string; breaker: string | null; health: string }[] };
    apiReadiness: Head & { checks: { check: string; health: string }[] };
  };
}

function sloView(tile: SloTilePayload): SloView {
  const service = id(tile.service, "slo service");
  const slo = id(tile.slo, "slo name");
  const key = `${service}.${slo}`;
  const why = reason(tile, key);
  const lanes = tile.burn_rates;
  blank(
    tile,
    [
      tile.sli_percent,
      tile.error_budget_remaining,
      ...lanes.flatMap((l) => [l.long_burn, l.short_burn, l.condition_met]),
    ],
    key,
  );

  const objective = finite(tile.objective_percent, `${key} objective`);
  if (objective === null || objective <= 0 || objective >= 100) {
    throw new OpsPayloadRefused(
      "not_an_objective",
      `${key}: an objective is a percent in (0, 100)`,
    );
  }
  const sli = finite(tile.sli_percent, `${key} sli`);
  const remaining = finite(tile.error_budget_remaining, `${key} budget`);
  if ((sli === null) !== (remaining === null)) {
    throw new OverviewBudgetInconsistent(
      "budget_inconsistent",
      `${key}: SLI and budget travel together`,
    );
  }
  if (sli !== null && remaining !== null) {
    const budget = (100 - objective) / 100;
    const expected = 1 - (100 - sli) / 100 / budget;
    if (Math.abs(expected - remaining) > BUDGET_TOLERANCE) {
      throw new OverviewBudgetInconsistent(
        "budget_inconsistent",
        `${key}: the budget remaining does not follow from the SLI and objective beside it`,
      );
    }
  }

  const laneViews = lanes.map((l) => {
    const factor = finite(l.factor, `${key} factor`);
    if (factor === null || factor <= 0) {
      throw new OpsPayloadRefused("not_a_factor", `${key}: a burn factor is positive`);
    }
    const long = finite(l.long_burn, `${key} long burn`);
    const short = finite(l.short_burn, `${key} short burn`);
    const expected = long !== null && short !== null ? long > factor && short > factor : null;
    if (l.condition_met !== expected) {
      throw new OverviewBurnInconsistent(
        "burn_condition_inconsistent",
        `${key} ${l.lane}: the condition is exactly "both windows above ${factor}"`,
      );
    }
    return {
      lane: id(l.lane, "lane"),
      severity: oneOf(l.severity, SEVERITIES, "severity"),
      factor: withUnit(String(factor), "×")!,
      longWindow: window(l.long_window, "long window"),
      shortWindow: window(l.short_window, "short window"),
      longBurn: fixed(long, 2, "×"),
      shortBurn: fixed(short, 2, "×"),
      conditionMet: l.condition_met,
    };
  });

  return {
    key,
    service,
    slo,
    state: tile.state,
    reason: why,
    objective: withUnit(String(objective), "%")!,
    window: window(tile.slo_window, "slo window"),
    sli: fixed(sli, 3, "%"),
    budgetRemaining: remaining === null ? null : fixed(remaining * 100, 1, "%"),
    budgetOverspent: remaining === null ? null : remaining < 0,
    lanes: laneViews,
  };
}

function readiness(probe: Probe): OverviewView["dependencies"]["apiReadiness"] {
  const unknown = (why: string) => ({ state: "unknown" as const, reason: why, checks: [] });
  if (!probe.ok) return unknown("api_unreachable");
  const body = probe.body;
  if (!isRecord(body) || !isRecord(body["checks"])) return unknown("readiness_malformed");
  const entries = Object.entries(body["checks"]);
  if (entries.length === 0) return unknown("readiness_malformed");
  if (entries.some(([name, state]) => !ID.test(name) || typeof state !== "string")) {
    return unknown("readiness_malformed");
  }
  const checks = entries.map(([check, state]) => ({
    check,
    health: state === "ok" ? "healthy" : "unhealthy",
  }));
  const failing = checks.some((c) => c.health === "unhealthy");
  const consistent = (probe.status === 200 && !failing) || (probe.status === 503 && failing);
  return consistent ? { state: "ok", reason: null, checks } : unknown("readiness_malformed");
}

export function renderOverview(payload: ReliabilityPayload, readyz: Probe): OverviewView {
  if (payload.schema !== RELIABILITY_SCHEMA) {
    throw new OpsSchemaMismatch("schema_mismatch", `expected ${RELIABILITY_SCHEMA}`);
  }
  noTarget(payload, "payload");
  const generatedAt = instant(payload.generated_at, "generated_at");
  if (generatedAt === null) throw new OpsPayloadRefused("not_a_date", "generated_at is required");

  // SLO tiles
  const slos = payload.slos;
  const slosReason = reason(slos, "slos");
  blank(slos, [slos.tiles], "slos");
  const tiles = slos.tiles.map(sloView);

  // probe matrix
  const matrix = payload.probe_matrix;
  const matrixReason = reason(matrix, "probe matrix");
  blank(matrix, [matrix.rows], "probe matrix");
  const staleAfter = finite(matrix.stale_after_s, "stale_after_s");
  const rows = matrix.rows.map((row) => {
    const rowAge = finite(row.age_s, `${row.component} age`);
    if (rowAge !== null && (rowAge < 0 || !Number.isInteger(rowAge))) {
      throw new OpsPayloadRefused("not_an_age", "an age is a whole number of seconds");
    }
    if (!row.stale && (rowAge === null || staleAfter === null || rowAge > staleAfter)) {
      throw new OverviewStaleRenderedFresh(
        "stale_rendered_fresh",
        `${row.component}: a result past three sweeps, or of unknown age, is not current`,
      );
    }
    const budget = finite(row.budget_ms, "budget_ms");
    if (budget === null || budget <= 0) {
      throw new OpsPayloadRefused("not_a_budget", `${row.component}: a probe budget is positive`);
    }
    return {
      component: id(row.component, "component"),
      probe: id(row.probe, "probe"),
      phiPath: row.phi_path === true,
      selfHostedNow: row.self_hosted_now === true,
      budget: withUnit(String(budget), "ms")!,
      status: oneOf(row.status, PROBE_STATUS, "probe status"),
      latency: latency(finite(row.latency_ms, `${row.component} latency`)),
      checkedAt: instant(row.checked_at, "checked_at"),
      age: age(rowAge),
      stale: row.stale === true,
    };
  });

  // dependency health
  const deps = payload.dependencies;
  const comp = deps.components;
  const compReason = reason(comp, "components");
  blank(comp, [comp.rows], "components");
  const componentRows = comp.rows.map((row) => {
    const health = oneOf(row.health, HEALTH, "component health");
    const checkedAt = instant(row.checked_at, "checked_at");
    if (health === "unknown" && checkedAt !== null) {
      throw new OpsUnknownCarriesFigure(
        "unknown_carries_figure",
        `${row.component}: an unknown health carries no instant (invariant 17)`,
      );
    }
    const kind = oneOf(row.fallback_kind, FALLBACK_KINDS, "fallback kind");
    const fallback = row.fallback === null ? null : id(row.fallback, "fallback");
    if ((kind === "component") !== (fallback !== null)) {
      throw new OpsPayloadRefused("fallback_inconsistent", "only a component fallback names one");
    }
    return {
      component: id(row.component, "component"),
      probe: id(row.probe, "probe"),
      health,
      healthReason: code(row.health_reason, "health reason"),
      checkedAt,
      fallbackKind: kind,
      fallback,
      fallbackHealth:
        row.fallback_health === null ? null : oneOf(row.fallback_health, HEALTH, "fallback health"),
    };
  });

  const prom = deps.prometheus;
  const promReason = reason(prom, "prometheus");
  blank(prom, [prom.health, prom.health_reason], "prometheus");

  const gpu = deps.gpu_hosts;
  const gpuReason = reason(gpu, "gpu hosts");
  blank(gpu, [gpu.rows], "gpu hosts");

  const vendors = deps.vendors;
  const vendorsReason = reason(vendors, "vendors");
  blank(vendors, [vendors.rows], "vendors");
  const vendorRows = vendors.rows.map((row) => {
    const breaker =
      row.breaker === null
        ? null
        : oneOf(row.breaker, new Set(Object.keys(BREAKER_HEALTH)), "breaker");
    const health = oneOf(row.health, HEALTH, "vendor health");
    if (health !== (breaker === null ? "unknown" : BREAKER_HEALTH[breaker])) {
      throw new OpsPayloadRefused(
        "breaker_health_mismatch",
        "a breaker's health follows its state",
      );
    }
    return { component: id(row.component, "vendor component"), breaker, health };
  });

  return {
    generatedAt,
    sources: {
      prometheus: id(payload.sources.prometheus, "prometheus source"),
      sloFiles: id(payload.sources.slo_files, "slo files source"),
      registry: id(payload.sources.registry, "registry source"),
      probeSweep: id(payload.sources.probe_sweep, "probe sweep source"),
    },
    slos: { state: slos.state, reason: slosReason, tiles },
    probeMatrix: {
      state: matrix.state,
      reason: matrixReason,
      sweepInterval: age(finite(matrix.sweep_interval_s, "sweep_interval_s")),
      staleAfter: age(staleAfter),
      rows,
    },
    dependencies: {
      components: { state: comp.state, reason: compReason, rows: componentRows },
      prometheus: {
        state: prom.state,
        reason: promReason,
        health: prom.health === null ? null : oneOf(prom.health, UP_DOWN, "prometheus health"),
        healthReason: code(prom.health_reason, "prometheus health reason"),
      },
      gpuHosts: {
        state: gpu.state,
        reason: gpuReason,
        rows: gpu.rows.map((row) => ({
          hostId: id(row.host_id, "host id"),
          health: oneOf(row.health, UP_DOWN, "host health"),
        })),
      },
      vendors: { state: vendors.state, reason: vendorsReason, rows: vendorRows },
      apiReadiness: readiness(readyz),
    },
  };
}
