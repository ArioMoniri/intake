/**
 * INT-351 — the ops console's view-model (files/08 §3 Ops; audit F26).
 *
 * Two inputs, both fetched server-side by `load.ts`: the `GET /admin/ops`
 * composite (`intake.admin.ops.v1`, built by `intake_api.admin.ops_console`
 * from the self-hosting registry and Prometheus) and the API's own
 * `/healthz`, `/readyz` and `/version`. One output: the tree the page paints.
 *
 * The projection is pure and it refuses rather than repairs, on the same
 * lines the platform draws:
 * - an `unknown` tile that carries a figure (invariant 17 — unknown is a
 *   state, and a figure beside it is a guess): {@link OpsUnknownCarriesFigure};
 * - a label that is not id-shaped (invariant 6): {@link OpsLabelLeaked};
 * - a mean for a cohort below the k floor (files/06 §8):
 *   {@link OpsSuppressedCohortLeaked};
 * - a target beside a figure (invariant 20): {@link OpsTargetRendered};
 * - a document of another schema: {@link OpsSchemaMismatch}.
 *
 * Numbers leave here as strings a reader cannot misread (invariant 22): no
 * grouping separators, and a number and its unit joined by a no-break space
 * into one atom.
 */

import {
  OPS_SCHEMA,
  type HealthResponses,
  type OpsPayload,
  type TileBase,
  type TileState,
} from "./payload";

export type * from "./payload";
export { OPS_SCHEMA } from "./payload";

// --- refusals ------------------------------------------------------------------

export class OpsPayloadRefused extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = new.target.name;
  }
}
export class OpsSchemaMismatch extends OpsPayloadRefused {}
export class OpsLabelLeaked extends OpsPayloadRefused {}
export class OpsSuppressedCohortLeaked extends OpsPayloadRefused {}
export class OpsTargetRendered extends OpsPayloadRefused {}
export class OpsUnknownCarriesFigure extends OpsPayloadRefused {}

// --- shapes --------------------------------------------------------------------

const ID = /^[a-z0-9][a-z0-9_.-]{0,63}$/;
const BRANCH = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$/;
const PIN = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}@[A-Za-z0-9._-]{1,64}$/;
const SHA = /^[0-9a-f]{7,40}$/;
const REASON = /^[a-z][a-z0-9_]{0,63}$/;
const ISO = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2}))?$/;
const NBSP = " ";
const GIB = 1024 ** 3;

function id(value: string, what: string): string {
  if (!ID.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not id-shaped (invariant 6)`);
  }
  return value;
}

function reason(tile: TileBase, what: string): string | null {
  if (tile.state !== "ok" && tile.state !== "unknown") {
    throw new OpsPayloadRefused("unknown_state", `${what}: state must be ok or unknown`);
  }
  if (tile.state === "ok") return null;
  if (typeof tile.reason !== "string" || !REASON.test(tile.reason)) {
    throw new OpsPayloadRefused("reason_not_a_code", `${what}: an unknown tile names a code`);
  }
  return tile.reason;
}

function noTarget(value: unknown, path: string): void {
  if (value === null || typeof value !== "object") return;
  for (const [key, inner] of Object.entries(value)) {
    if (key === "target" || key.endsWith("_target")) {
      throw new OpsTargetRendered(
        "target_rendered",
        `${path}.${key}: a target beside a figure turns a measurement into a claim (invariant 20)`,
      );
    }
    noTarget(inner, `${path}.${key}`);
  }
}

function blank(tile: TileBase, figures: unknown[], what: string): void {
  if (tile.state !== "unknown") return;
  for (const figure of figures) {
    const empty = figure === null || (Array.isArray(figure) && figure.length === 0);
    if (!empty) {
      throw new OpsUnknownCarriesFigure(
        "unknown_carries_figure",
        `${what} is unknown and still carries a figure (invariant 17)`,
      );
    }
  }
}

function floor(
  n: number | null,
  suppressed: boolean | null,
  mean: number | null,
  k: number,
  what: string,
): void {
  if (mean === null) return;
  if (suppressed !== false || n === null || n < k) {
    throw new OpsSuppressedCohortLeaked(
      "suppressed_cohort_leaked",
      `${what}: a mean for a cohort below k = ${k} (files/06 §8)`,
    );
  }
}

// --- formatting (invariant 22) -------------------------------------------------

function count(value: number | null): string | null {
  return value === null || !Number.isFinite(value) ? null : String(Math.round(value));
}

function withUnit(value: string | null, unit: string): string | null {
  return value === null ? null : `${value}${NBSP}${unit}`;
}

function gib(bytes: number | null): string | null {
  return bytes === null || !Number.isFinite(bytes)
    ? null
    : withUnit((bytes / GIB).toFixed(1), "GiB");
}

function percent(ratio: number | null): string | null {
  return ratio === null || !Number.isFinite(ratio)
    ? null
    : withUnit(String(Math.round(ratio * 100)), "%");
}

function ms(value: number | null): string | null {
  return withUnit(count(value), "ms");
}

function decimal(value: number | null, digits: number): string | null {
  return value === null || !Number.isFinite(value) ? null : value.toFixed(digits);
}

// --- the view ------------------------------------------------------------------

export interface HealthView {
  alive: "alive" | "unknown";
  ready: "ready" | "not_ready" | "unknown";
  failingChecks: string[];
  gitSha: string;
  builtAt: string;
}

export interface OpsView {
  generatedAt: string;
  prometheus: string;
  health: HealthView;
  tiles: {
    models: {
      state: TileState;
      reason: string | null;
      releaseBlocked: boolean | null;
      rows: {
        component: string;
        pin: string | null;
        selfHostable: boolean;
        selfHostedNow: boolean;
        phiPath: boolean;
        probe: string;
        probeStatus: string;
        licenceVerifiedAt: string | null;
        severity: string;
      }[];
    };
    gpu: {
      state: TileState;
      reason: string | null;
      hosts: {
        hostId: string;
        up: boolean;
        gpus: {
          index: string;
          utilization: string | null;
          memoryUsed: string | null;
          memoryTotal: string | null;
        }[];
      }[];
    };
    modelUsage: {
      state: TileState;
      reason: string | null;
      window: string;
      lanes: {
        kind: string;
        lane: string;
        requests: string | null;
        p95: string | null;
        failures: string | null;
      }[];
    };
    clipCache: {
      state: TileState;
      reason: string | null;
      window: string;
      hit: string | null;
      miss: string | null;
      hitRatio: string | null;
      syntheses: { gateway: string; outcome: string; count: string | null }[];
    };
    waitTime: {
      state: TileState;
      reason: string | null;
      metricId: string;
      window: string;
      kFloor: string;
      n: string | null;
      suppressed: boolean;
      meanMin: string | null;
    };
    satisfaction: {
      state: TileState;
      reason: string | null;
      window: string;
      kFloor: string;
      csatN: string | null;
      csatSuppressed: boolean;
      csatMean: string | null;
      nps: string | null;
    };
    cicd: {
      state: TileState;
      reason: string | null;
      branch: string | null;
      workflows: {
        workflow: string;
        status: string;
        conclusion: string;
        sha: string;
        updatedAt: string | null;
      }[];
    };
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function renderHealth(responses: HealthResponses): HealthView {
  const { healthz, readyz, version } = responses;
  const alive =
    healthz.ok &&
    healthz.status === 200 &&
    isRecord(healthz.body) &&
    healthz.body["status"] === "alive"
      ? "alive"
      : "unknown";

  let ready: HealthView["ready"] = "unknown";
  let failingChecks: string[] = [];
  if (readyz.ok && isRecord(readyz.body) && isRecord(readyz.body["checks"])) {
    const checks = Object.entries(readyz.body["checks"]);
    const failing = checks.filter(([, state]) => state !== "ok").map(([name]) => name);
    if (readyz.status === 200 && failing.length === 0) ready = "ready";
    else if (
      readyz.status === 503 &&
      failing.length > 0 &&
      failing.every((name) => ID.test(name))
    ) {
      ready = "not_ready";
      failingChecks = failing;
    }
  }

  let gitSha = "unknown";
  let builtAt = "unknown";
  if (version.ok && version.status === 200 && isRecord(version.body)) {
    const sha = version.body["git_sha"];
    const built = version.body["built_at"];
    if (typeof sha === "string" && (SHA.test(sha) || sha === "dev")) gitSha = sha;
    if (typeof built === "string" && (ISO.test(built) || built === "dev")) builtAt = built;
  }
  return { alive, ready, failingChecks, gitSha, builtAt };
}

export function renderOps(payload: OpsPayload, health: HealthResponses): OpsView {
  if (payload.schema !== OPS_SCHEMA) {
    throw new OpsSchemaMismatch("schema_mismatch", `expected ${OPS_SCHEMA}`);
  }
  noTarget(payload, "payload");
  const t = payload.tiles;

  // models — the registry, rendered as it is
  const models = t.models;
  const modelsReason = reason(models, "models");
  blank(models, [models.rows, models.release_blocked], "models");
  const modelRows = models.rows.map((row) => {
    if (row.pin !== null && !PIN.test(row.pin)) {
      throw new OpsLabelLeaked("label_not_id_shaped", "a model pin is not model_id@revision");
    }
    if (row.licence_verified_at !== null && !ISO.test(row.licence_verified_at)) {
      throw new OpsPayloadRefused("not_a_date", "licence_verified_at is not a date");
    }
    return {
      component: id(row.component, "component"),
      pin: row.pin,
      selfHostable: row.self_hostable,
      selfHostedNow: row.self_hosted_now,
      phiPath: row.phi_path,
      probe: id(row.probe, "probe"),
      probeStatus: id(row.probe_status, "probe status"),
      licenceVerifiedAt: row.licence_verified_at,
      severity: id(row.severity, "severity"),
    };
  });

  // GPU
  const gpu = t.gpu;
  const gpuReason = reason(gpu, "gpu");
  blank(gpu, [gpu.hosts], "gpu");
  const hosts = gpu.hosts.map((host) => ({
    hostId: id(host.host_id, "host id"),
    up: host.up,
    gpus: host.gpus.map((g) => ({
      index: id(g.gpu_index, "gpu index"),
      utilization: percent(g.utilization_ratio),
      memoryUsed: gib(g.memory_used_bytes),
      memoryTotal: gib(g.memory_total_bytes),
    })),
  }));

  // model usage
  const usage = t.model_usage;
  const usageReason = reason(usage, "model usage");
  blank(usage, [usage.lanes], "model usage");
  const lanes = usage.lanes.map((lane) => ({
    kind: id(lane.kind, "lane kind"),
    lane: id(lane.lane, "lane"),
    requests: count(lane.requests),
    p95: ms(lane.p95_ms),
    failures: count(lane.failures),
  }));

  // clip cache
  const clip = t.clip_cache;
  const clipReason = reason(clip, "clip cache");
  blank(clip, [clip.hit, clip.miss, clip.syntheses], "clip cache");
  const lookups = (clip.hit ?? 0) + (clip.miss ?? 0);
  const hitRatio =
    clip.hit !== null && clip.miss !== null && lookups > 0 ? percent(clip.hit / lookups) : null;
  const syntheses = clip.syntheses.map((s) => ({
    gateway: id(s.gateway, "gateway"),
    outcome: id(s.outcome, "outcome"),
    count: count(s.count),
  }));

  // wait time
  const wait = t.wait_time;
  const waitReason = reason(wait, "wait time");
  blank(wait, [wait.n, wait.mean_min, wait.suppressed], "wait time");
  floor(wait.n, wait.suppressed, wait.mean_min, wait.k_floor, "wait time");

  // satisfaction
  const sat = t.satisfaction;
  const satReason = reason(sat, "satisfaction");
  blank(sat, [sat.csat_n, sat.csat_mean, sat.nps, sat.csat_suppressed], "satisfaction");
  floor(sat.csat_n, sat.csat_suppressed, sat.csat_mean, sat.k_floor, "CSAT");

  // CI/CD
  const cicd = t.cicd;
  const cicdReason = reason(cicd, "cicd");
  blank(cicd, [cicd.workflows, cicd.branch], "cicd");
  if (cicd.branch !== null && !BRANCH.test(cicd.branch)) {
    throw new OpsLabelLeaked("label_not_id_shaped", "branch is not a ref name");
  }
  const workflows = cicd.workflows.map((w) => {
    if (!SHA.test(w.head_sha)) {
      throw new OpsLabelLeaked("label_not_id_shaped", "head_sha is not a sha");
    }
    if (w.updated_at !== null && !ISO.test(w.updated_at)) {
      throw new OpsPayloadRefused("not_a_date", "updated_at is not a timestamp");
    }
    return {
      workflow: id(w.workflow, "workflow"),
      status: id(w.status, "status"),
      conclusion: id(w.conclusion, "conclusion"),
      sha: w.head_sha.slice(0, 7),
      updatedAt: w.updated_at,
    };
  });

  return {
    generatedAt: payload.generated_at,
    prometheus: id(payload.sources.prometheus, "prometheus source state"),
    health: renderHealth(health),
    tiles: {
      models: {
        state: models.state,
        reason: modelsReason,
        releaseBlocked: models.release_blocked,
        rows: modelRows,
      },
      gpu: { state: gpu.state, reason: gpuReason, hosts },
      modelUsage: {
        state: usage.state,
        reason: usageReason,
        window: id(usage.window, "window"),
        lanes,
      },
      clipCache: {
        state: clip.state,
        reason: clipReason,
        window: id(clip.window, "window"),
        hit: count(clip.hit),
        miss: count(clip.miss),
        hitRatio,
        syntheses,
      },
      waitTime: {
        state: wait.state,
        reason: waitReason,
        metricId: wait.metric_id,
        window: id(wait.window, "window"),
        kFloor: String(wait.k_floor),
        n: count(wait.n),
        suppressed: wait.suppressed === true,
        meanMin: decimal(wait.mean_min, 1),
      },
      satisfaction: {
        state: sat.state,
        reason: satReason,
        window: id(sat.window, "window"),
        kFloor: String(sat.k_floor),
        csatN: count(sat.csat_n),
        csatSuppressed: sat.csat_suppressed === true,
        csatMean: decimal(sat.csat_mean, 2),
        nps: decimal(sat.nps, 2),
      },
      cicd: { state: cicd.state, reason: cicdReason, branch: cicd.branch, workflows },
    },
  };
}
