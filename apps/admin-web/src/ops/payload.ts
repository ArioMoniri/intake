/**
 * INT-351 — the wire shapes the ops console reads: the `GET /admin/ops`
 * document (`intake.admin.ops.v1`, produced by
 * `services/api/src/intake_api/admin/ops_console.py`) and the three health
 * endpoints every service mounts (`intake_platform.health.mount_health`).
 * Field names are the API's, snake_case, so a rename on either side is a type
 * error here rather than a silently blank cell.
 */

export const OPS_SCHEMA = "intake.admin.ops.v1";

export type TileState = "ok" | "unknown";

export interface TileBase {
  state: TileState;
  reason: string | null;
}

export interface ModelRowPayload {
  component: string;
  pin: string | null;
  self_hostable: boolean;
  self_hosted_now: boolean;
  phi_path: boolean;
  probe: string;
  probe_status: string;
  licence_verified_at: string | null;
  severity: string;
}

export interface ModelsTilePayload extends TileBase {
  release_blocked: boolean | null;
  rows: ModelRowPayload[];
}

export interface GpuPayload {
  gpu_index: string;
  utilization_ratio: number | null;
  memory_used_bytes: number | null;
  memory_total_bytes: number | null;
}

export interface GpuTilePayload extends TileBase {
  hosts: { host_id: string; up: boolean; gpus: GpuPayload[] }[];
}

export interface LanePayload {
  kind: string;
  lane: string;
  requests: number | null;
  p95_ms: number | null;
  failures: number | null;
}

export interface UsageTilePayload extends TileBase {
  window: string;
  lanes: LanePayload[];
}

export interface ClipTilePayload extends TileBase {
  window: string;
  hit: number | null;
  miss: number | null;
  syntheses: { gateway: string; outcome: string; count: number | null }[];
  manifests: {
    pack: string;
    locale: string;
    voice: string;
    rows: number | null;
    present: number | null;
  }[];
}

export interface WaitTilePayload extends TileBase {
  metric_id: string;
  window: string;
  k_floor: number;
  n: number | null;
  suppressed: boolean | null;
  mean_min: number | null;
}

export interface SatisfactionTilePayload extends TileBase {
  csat_metric_id: string;
  nps_metric_id: string;
  window: string;
  k_floor: number;
  csat_n: number | null;
  csat_suppressed: boolean | null;
  csat_mean: number | null;
  nps: number | null;
}

export interface CicdTilePayload extends TileBase {
  branch: string | null;
  workflows: {
    workflow: string;
    status: string;
    conclusion: string;
    head_sha: string;
    updated_at: string | null;
  }[];
}

export interface OpsPayload {
  schema: typeof OPS_SCHEMA;
  generated_at: string;
  sources: { prometheus: string; registry: string };
  tiles: {
    models: ModelsTilePayload;
    gpu: GpuTilePayload;
    model_usage: UsageTilePayload;
    clip_cache: ClipTilePayload;
    wait_time: WaitTilePayload;
    satisfaction: SatisfactionTilePayload;
    cicd: CicdTilePayload;
  };
}

/** One health endpoint as the loader saw it. */
export type Probe = { ok: true; status: number; body: unknown } | { ok: false; reason: string };

export interface HealthResponses {
  healthz: Probe;
  readyz: Probe;
  version: Probe;
}
