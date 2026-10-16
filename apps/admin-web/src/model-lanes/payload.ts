/**
 * INT-428 — the wire shape the Model lanes page reads: the
 * `GET /admin/model-lanes` document (`intake.admin.model_lanes.v1`, produced by
 * `services/api/src/intake_api/admin/model_lanes_console.py`). Field names are
 * the API's, snake_case, so a rename on either side is a type error here
 * rather than a silently blank cell.
 *
 * The closed sets below mirror the server's own enums. Each is closed on
 * purpose (ADR-035): a lane, a provider or a route is a catalogue row and a
 * reviewed change, never a string the page accepts because it looks plausible.
 * There is no `mock` route anywhere in this module.
 */

export const MODEL_LANES_SCHEMA = "intake.admin.model_lanes.v1";

/** `intake_platform.model_lanes.Lane`, in the order the console renders them. */
export const LANES = ["llm", "asr", "tts"] as const;
export type LaneId = (typeof LANES)[number];

/** `intake_platform.model_lanes.ProviderId` — the hosted providers that exist. */
export const PROVIDERS = ["openai"] as const;
export type ProviderId = (typeof PROVIDERS)[number];

/** A lane route on the wire (`LaneRoute.wire`): self-hosted, or one hosted provider. */
export type Route = "self_hosted" | `hosted:${ProviderId}`;
export const ROUTES: readonly Route[] = [
  "self_hosted",
  ...PROVIDERS.map((provider): Route => `hosted:${provider}`),
];

/** A role: a lane, or a dotted use of one (`llm.council.chair`) — `parse_role`. */
export const ROLE = /^(llm|asr|tts)(\.[a-z0-9][a-z0-9_-]{0,31}){0,3}$/;

/** A model selection key — `parse_model_key`. */
export const MODEL_KEY = /^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,191}$/;

/** The last four characters of a provider key: all the console ever sees of one. */
export const LAST4 = /^[A-Za-z0-9_.-]{4}$/;

/** `intake_platform.model_lanes.TenantDataClass`. */
export const DATA_CLASSES = ["synthetic", "real_phi"] as const;
export type DataClass = (typeof DATA_CLASSES)[number];

/** `intake_platform.admin.flag_governance.FlagChangeReason` — the closed
 * category every governed write is filed under. */
export const REASON_CLASSES = [
  "incident_mitigation",
  "config_correction",
  "rollout_expansion",
  "rollout_rollback",
  "experiment_start",
  "experiment_end",
  "study_enablement",
] as const;
export type ReasonClass = (typeof REASON_CLASSES)[number];

/** `ModelLanesChange` — what the last write to the control did. */
export const CHANGES = [
  "route_switch",
  "self_hosted_engage",
  "hosted_disable",
  "hosted_release",
  "key_set",
] as const;

/** The self-hosted identity probe (`LaneHealth.state`). */
export const IDENTITY_STATES = [
  "healthy",
  "unconfigured",
  "unattested",
  "quarantined",
  "unreachable",
  "identity_mismatch",
] as const;

export const PROBE_STATES = ["healthy", "unhealthy", "skipped"] as const;
export const KEY_STATES = ["set", "not_set", "unknown", "unconfigured"] as const;
export const READY_STATES = ["ready", "blocked"] as const;
export const COST_STATES = ["known", "price_not_configured", "not_metered"] as const;
export const PENDING_STATES = ["pending", "approved", "expired"] as const;

/** The four-eyes ceremonies this module opens, by their `DangerousAction` id. */
export const CEREMONIES = {
  "admin.model_lanes.hosted.release": "hosted_release",
  "admin.model_lanes.route.switch": "route_switch",
  "admin.model_lanes.key.set": "key_set",
} as const;
export type Ceremony = (typeof CEREMONIES)[keyof typeof CEREMONIES];

export interface ModelRefPayload {
  source: "self_hosted" | "hosted";
  provider: string;
  model_id: string;
  version: string;
  wire: string;
  sha256: string | null;
  component: string | null;
  key: string;
}

export interface SettingPayload {
  route: string;
  model: string | null;
  fallback: string | null;
  fallback_model: string | null;
}

export interface ServingPayload {
  available: boolean;
  reason: string;
  provider: string | null;
  route: string | null;
  fallback: boolean;
  model: ModelRefPayload | null;
  qualified: boolean;
  clinical_evidence: boolean;
}

export interface CostPayload {
  state: (typeof COST_STATES)[number];
  usd: number | null;
}

export interface UsagePayload {
  route: string;
  provider: string;
  p50_ms: number | null;
  p95_ms: number | null;
  calls: number | null;
  cost: CostPayload;
}

export interface RoleRowPayload {
  role: string;
  lane: string;
  inherits: boolean;
  setting: SettingPayload | null;
  serving: ServingPayload;
  self_hosted: { identity: string; expected: ModelRefPayload | null };
  /** Present on the three lane rows only. */
  usage?: UsagePayload[];
}

export interface SelfHostedOptionPayload {
  component: string;
  pinned: boolean;
  attested: boolean;
  jurisdiction: string | null;
  model: ModelRefPayload | null;
  identity: string;
  qualified: boolean;
}

export interface HostedOptionPayload {
  provider: string;
  model: ModelRefPayload;
  default: boolean;
  probe: { state: string; reason: string | null };
  qualified: boolean;
}

export interface LaneModelsPayload {
  gated: boolean;
  self_hosted: SelfHostedOptionPayload[];
  hosted: HostedOptionPayload[];
}

export interface ProviderPayload {
  provider: string;
  egress_row: string;
  listed: boolean;
  self_hostable: boolean;
  phi_path: boolean;
  key: { state: string; last4: string | null; set_at: string | null };
  ready: { state: string; reason: string | null };
}

export interface PendingPayload {
  action_id: string;
  dangerous_action_id: string;
  tier: number;
  state: string;
  expires_at: string;
  approver_role: string | null;
}

export interface DeploymentPayload {
  declared: string;
  bound: string | null;
  effective: string;
  hosted_lanes: boolean;
  data_class_mismatch: boolean;
}

export type ControlPayload =
  | { state: "unknown"; reason: string | null }
  | {
      state: "known";
      reason: null;
      revision: number;
      hosted_disabled: boolean;
      changed_at: string | null;
      changed_by: string | null;
      approved_by: string | null;
      last_change: string | null;
    };

export interface ModelLanesPayload {
  schema: typeof MODEL_LANES_SCHEMA;
  generated_at: string;
  state: "known" | "unknown";
  reason: string | null;
  deployment: DeploymentPayload | null;
  control: ControlPayload;
  lanes: RoleRowPayload[];
  roles: RoleRowPayload[];
  models: Partial<Record<LaneId, LaneModelsPayload>>;
  providers: ProviderPayload[];
  usage_window: string;
  usage_reason: string | null;
  pending: PendingPayload[];
}
