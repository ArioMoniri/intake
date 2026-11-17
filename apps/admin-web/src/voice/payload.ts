/**
 * INT-182 — the wire shape the Voice page reads: the `GET /admin/voice`
 * document (`intake.admin.voice.v1`, produced by
 * `services/api/src/intake_api/admin/voice_console.py`). Field names are the
 * API's, snake_case, so a rename on either side is a type error here rather
 * than a silently blank cell.
 */

export const VOICE_SCHEMA = "intake.admin.voice.v1";

/** The profiles that exist (CLAUDE.md invariant 19; ADR-010). There is no third. */
export const VOICE_PROFILES = ["residency_tr", "typed"] as const;
export type VoiceProfileId = (typeof VOICE_PROFILES)[number];

export const CANARY_WEIGHT_MIN = 0;
export const CANARY_WEIGHT_MAX = 100;

export type TileState = "ok" | "unknown";

export interface SectionPayload {
  state: TileState;
  reason: string | null;
}

export interface TenantControlPayload {
  tenant_id: string;
  kill_switch: boolean;
  default_profile: string;
  canary_profile: string | null;
  canary_weight: number;
  effective_profile: string;
  revision: number;
  changed_at: string | null;
  changed_by: string | null;
  approved_by: string | null;
  last_change: string | null;
}

export interface PendingPayload {
  action_id: string;
  dangerous_action_id: string;
  tier: number;
  tenant_id: string;
  control: string;
  profile: string | null;
  weight: number | null;
  requested_role: string;
  created_at: string;
  expires_at: string;
}

export interface CatalogueRowPayload {
  control: string;
  dangerous_action_id: string;
  route: string;
  tier: number;
  direction: string;
  actor_roles: string[];
  approver_roles: string[];
  weight_bounds?: { min: number; max: number };
}

export interface VoicePayload {
  schema: typeof VOICE_SCHEMA;
  generated_at: string;
  profiles: string[];
  reason_classes: string[];
  sources: { prometheus: string; controls: string };
  control_catalogue: CatalogueRowPayload[];
  tiles: {
    controls: SectionPayload & { tenants: TenantControlPayload[] };
    pending: SectionPayload & { actions: PendingPayload[] };
    sessions: SectionPayload & {
      window: string;
      rows: { profile: string; reason: string; sessions: number | null }[];
    };
    kill_switch_activity: SectionPayload & {
      window: string;
      inflight: { outcome: string; count: number | null }[];
      read_failures: { phase: string; count: number | null }[];
    };
    turn_latency: SectionPayload & {
      metric_id: string;
      window: string;
      rows: { profile: string; p50_ms: number | null; p95_ms: number | null }[];
    };
    speech_errors: SectionPayload & {
      window: string;
      rows: {
        component: string;
        kind: string;
        calls: number;
        failures: number;
        error_ratio: number | null;
      }[];
    };
    failovers: SectionPayload & {
      window: string;
      rows: { from_component: string; to_component: string; count: number | null }[];
    };
    breakers: SectionPayload & { rows: { component: string; state: string | null }[] };
  };
}
