/**
 * INT-181 — the wire shape the overview reads: the `GET /admin/reliability`
 * document (`intake.admin.reliability.v1`, produced by
 * `services/api/src/intake_api/admin/reliability_console.py`). Field names are
 * the API's, snake_case, so a rename on either side is a type error here
 * rather than a silently blank cell.
 */

export const RELIABILITY_SCHEMA = "intake.admin.reliability.v1";

export type TileState = "ok" | "unknown";

export interface SectionPayload {
  state: TileState;
  reason: string | null;
}

export interface BurnLanePayload {
  lane: string;
  severity: string;
  factor: number;
  long_window: string;
  short_window: string;
  long_burn: number | null;
  short_burn: number | null;
  condition_met: boolean | null;
}

export interface SloTilePayload extends SectionPayload {
  service: string;
  slo: string;
  objective_percent: number;
  slo_window: string;
  sli_percent: number | null;
  error_budget_remaining: number | null;
  burn_rates: BurnLanePayload[];
}

export interface ProbeRowPayload {
  component: string;
  probe: string;
  phi_path: boolean;
  self_hosted_now: boolean;
  budget_ms: number;
  status: string;
  latency_ms: number | null;
  checked_at: string | null;
  age_s: number | null;
  stale: boolean;
}

export interface ProbeMatrixPayload extends SectionPayload {
  sweep_interval_s: number;
  stale_after_s: number;
  rows: ProbeRowPayload[];
}

export interface ComponentRowPayload {
  component: string;
  probe: string;
  health: string;
  health_reason: string | null;
  checked_at: string | null;
  fallback_kind: string;
  fallback: string | null;
  fallback_health: string | null;
}

export interface ReliabilityPayload {
  schema: typeof RELIABILITY_SCHEMA;
  generated_at: string;
  sources: { prometheus: string; slo_files: string; registry: string; probe_sweep: string };
  slos: SectionPayload & { tiles: SloTilePayload[] };
  probe_matrix: ProbeMatrixPayload;
  dependencies: {
    components: SectionPayload & { rows: ComponentRowPayload[] };
    prometheus: SectionPayload & { health: string | null; health_reason: string | null };
    gpu_hosts: SectionPayload & { rows: { host_id: string; health: string }[] };
    vendors: SectionPayload & {
      rows: { component: string; breaker: string | null; health: string }[];
    };
  };
}
