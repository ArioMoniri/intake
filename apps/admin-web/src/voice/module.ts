/**
 * INT-182 — the Voice module's view-model (files/08 §3 "Voice runtime").
 *
 * One input, the `GET /admin/voice` composite; one output, the tree the page
 * paints. Pure, and it refuses rather than repairs — with the shared refusals
 * of `../ops/guards` (schema, ids, unknown-with-a-figure, targets) and three
 * of its own, each a figure the page would otherwise paint over its evidence:
 *
 * - {@link VoiceProfileOutsideSet} — a profile that does not exist, anywhere
 *   in the document (CLAUDE.md invariant 19: `residency_tr` and `typed`, no
 *   third). A console that paints a third profile has shown an operator a
 *   choice the runtime cannot make.
 * - {@link VoiceWeightOutOfBounds} — a canary weight that is not an integer
 *   percentage 0..100.
 * - {@link VoiceControlIncoherent} — a tenant shown on voice while its kill
 *   switch is engaged, or a canary the record could not hold. A stale or bent
 *   payload must not show a tenant as speaking when it is on the keyboard.
 */

import {
  ID,
  ISO,
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsSchemaMismatch,
  blank,
  count,
  id,
  noTarget,
  reason,
  withUnit,
} from "../ops/guards";
import {
  CANARY_WEIGHT_MAX,
  CANARY_WEIGHT_MIN,
  VOICE_PROFILES,
  VOICE_SCHEMA,
  type PendingPayload,
  type TenantControlPayload,
  type TileState,
  type VoicePayload,
  type VoiceProfileId,
} from "./payload";

export type * from "./payload";
export { VOICE_PROFILES, VOICE_SCHEMA } from "./payload";

export class VoiceProfileOutsideSet extends OpsPayloadRefused {}
export class VoiceWeightOutOfBounds extends OpsPayloadRefused {}
export class VoiceControlIncoherent extends OpsPayloadRefused {}

const ROUTE_REASONS = new Set(["default", "canary", "kill_switch", "control_unreadable"]);
const CONTROLS = new Set([
  "kill_switch_engage",
  "kill_switch_release",
  "default_profile",
  "canary",
]);
const BREAKER_STATES = new Set(["closed", "half_open", "open"]);
const CALL_KINDS = new Set(["asr", "tts"]);
const FLIP_OUTCOMES = new Set(["switched", "not_armed"]);
const READ_PHASES = new Set(["start", "poll"]);
const WINDOW = /^[0-9]{1,4}[smhd]$/;

// --- shapes --------------------------------------------------------------------

export function isProfile(value: unknown): value is VoiceProfileId {
  return typeof value === "string" && (VOICE_PROFILES as readonly string[]).includes(value);
}

function profile(value: unknown, what: string): VoiceProfileId {
  if (!isProfile(value)) {
    throw new VoiceProfileOutsideSet(
      "profile_outside_set",
      `${what}: only residency_tr and typed exist (invariant 19)`,
    );
  }
  return value;
}

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

function subject(value: string | null, what: string): string | null {
  if (
    value !== null &&
    (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$/.test(value))
  ) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not a staff subject`);
  }
  return value;
}

export function isWeight(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= CANARY_WEIGHT_MIN &&
    value <= CANARY_WEIGHT_MAX
  );
}

function weight(value: unknown, what: string): number {
  if (!isWeight(value)) {
    throw new VoiceWeightOutOfBounds(
      "weight_out_of_bounds",
      `${what}: a canary weight is an integer ${CANARY_WEIGHT_MIN}..${CANARY_WEIGHT_MAX}`,
    );
  }
  return value;
}

function ratio(value: number | null): string | null {
  return value === null || !Number.isFinite(value) ? null : withUnit((value * 100).toFixed(2), "%");
}

function millis(value: number | null): string | null {
  return value === null || !Number.isFinite(value) ? null : withUnit(value.toFixed(0), "ms");
}

// --- the view ------------------------------------------------------------------

interface Head {
  state: TileState;
  reason: string | null;
}

export interface TenantView {
  tenantId: string;
  killSwitch: boolean;
  defaultProfile: VoiceProfileId;
  effectiveProfile: VoiceProfileId;
  canary: string | null;
  revision: string;
  changedAt: string | null;
  changedBy: string | null;
  approvedBy: string | null;
  lastChange: string | null;
}

export interface PendingView {
  actionId: string;
  control: string;
  tenantId: string;
  profile: VoiceProfileId | null;
  weight: string | null;
  requestedRole: string;
  expiresAt: string;
}

export interface ControlView {
  control: string;
  tier: number;
  route: string;
  actorRoles: string[];
  approverRoles: string[];
}

export interface VoiceView {
  generatedAt: string;
  sources: { prometheus: string; controls: string };
  profiles: VoiceProfileId[];
  reasonClasses: string[];
  catalogue: ControlView[];
  controls: Head & { tenants: TenantView[] };
  pending: Head & { actions: PendingView[] };
  sessions: Head & {
    window: string;
    rows: { profile: VoiceProfileId; reason: string; sessions: string | null }[];
  };
  killSwitchActivity: Head & {
    window: string;
    inflight: { outcome: string; count: string | null }[];
    readFailures: { phase: string; count: string | null }[];
  };
  turnLatency: Head & {
    metricId: string;
    window: string;
    rows: { profile: VoiceProfileId; p50: string | null; p95: string | null }[];
  };
  speechErrors: Head & {
    window: string;
    rows: {
      component: string;
      kind: string;
      calls: string;
      failures: string;
      errorRatio: string | null;
    }[];
  };
  failovers: Head & { window: string; rows: { from: string; to: string; count: string | null }[] };
  breakers: Head & { rows: { component: string; state: string | null }[] };
}

function head(tile: Head, figures: unknown[], what: string): Head {
  const code = reason(tile, what);
  blank(tile, figures, what);
  return { state: tile.state, reason: code };
}

function tenant(row: TenantControlPayload): TenantView {
  const tenantId = id(row.tenant_id, "controls.tenant_id");
  const where = `controls[${tenantId}]`;
  const defaultProfile = profile(row.default_profile, `${where}.default_profile`);
  const effectiveProfile = profile(row.effective_profile, `${where}.effective_profile`);
  const canaryProfile =
    row.canary_profile === null ? null : profile(row.canary_profile, `${where}.canary_profile`);
  const share = weight(row.canary_weight, `${where}.canary_weight`);
  if (typeof row.kill_switch !== "boolean") {
    throw new OpsPayloadRefused("not_a_boolean", `${where}.kill_switch`);
  }
  const expected: VoiceProfileId = row.kill_switch ? "typed" : defaultProfile;
  if (effectiveProfile !== expected) {
    throw new VoiceControlIncoherent(
      "control_incoherent",
      `${where}: the effective profile contradicts the kill switch and the default`,
    );
  }
  const canaryCoherent =
    share === CANARY_WEIGHT_MIN
      ? canaryProfile === null
      : canaryProfile !== null && canaryProfile !== defaultProfile;
  if (!canaryCoherent) {
    throw new VoiceControlIncoherent("control_incoherent", `${where}: an impossible canary`);
  }
  return {
    tenantId,
    killSwitch: row.kill_switch,
    defaultProfile,
    effectiveProfile,
    canary: canaryProfile === null ? null : `${canaryProfile} · ${withUnit(String(share), "%")}`,
    revision: String(row.revision),
    changedAt: instant(row.changed_at, `${where}.changed_at`),
    changedBy: subject(row.changed_by, `${where}.changed_by`),
    approvedBy: subject(row.approved_by, `${where}.approved_by`),
    lastChange:
      row.last_change === null ? null : oneOf(row.last_change, CONTROLS, `${where}.last_change`),
  };
}

function pendingRow(row: PendingPayload): PendingView {
  const actionId = id(row.action_id, "pending.action_id");
  return {
    actionId,
    control: oneOf(row.control, CONTROLS, `pending[${actionId}].control`),
    tenantId: id(row.tenant_id, `pending[${actionId}].tenant_id`),
    profile: row.profile === null ? null : profile(row.profile, `pending[${actionId}].profile`),
    weight:
      row.weight === null
        ? null
        : withUnit(String(weight(row.weight, `pending[${actionId}].weight`)), "%"),
    requestedRole: id(row.requested_role, `pending[${actionId}].requested_role`),
    expiresAt: instant(row.expires_at, `pending[${actionId}].expires_at`) ?? "",
  };
}

/** The whole Voice view. Throws an `OpsPayloadRefused` rather than paint a lie. */
export function renderVoice(payload: VoicePayload): VoiceView {
  if (payload.schema !== VOICE_SCHEMA) {
    throw new OpsSchemaMismatch("schema_mismatch", `expected ${VOICE_SCHEMA}`);
  }
  noTarget(payload, "$");
  const profiles = payload.profiles.map((p, i) => profile(p, `profiles[${i}]`));
  if (new Set(profiles).size !== VOICE_PROFILES.length) {
    throw new VoiceProfileOutsideSet("profile_outside_set", "profiles must be exactly the two");
  }
  const t = payload.tiles;

  const controls = {
    ...head(t.controls, [t.controls.tenants], "controls"),
    tenants: t.controls.tenants.map(tenant),
  };
  const pending = {
    ...head(t.pending, [t.pending.actions], "pending"),
    actions: t.pending.actions.map(pendingRow),
  };
  const sessions = {
    ...head(t.sessions, [t.sessions.rows], "sessions"),
    window: window(t.sessions.window, "sessions.window"),
    rows: t.sessions.rows.map((row) => ({
      profile: profile(row.profile, "sessions.profile"),
      reason: oneOf(row.reason, ROUTE_REASONS, "sessions.reason"),
      sessions: count(row.sessions),
    })),
  };
  const k = t.kill_switch_activity;
  const killSwitchActivity = {
    ...head(k, [k.inflight, k.read_failures], "kill_switch_activity"),
    window: window(k.window, "kill_switch_activity.window"),
    inflight: k.inflight.map((row) => ({
      outcome: oneOf(row.outcome, FLIP_OUTCOMES, "kill_switch_activity.outcome"),
      count: count(row.count),
    })),
    readFailures: k.read_failures.map((row) => ({
      phase: oneOf(row.phase, READ_PHASES, "kill_switch_activity.phase"),
      count: count(row.count),
    })),
  };
  const l = t.turn_latency;
  const turnLatency = {
    ...head(l, [l.rows], "turn_latency"),
    metricId: oneOf(l.metric_id, new Set(["voice.round_trip_ms"]), "turn_latency.metric_id"),
    window: window(l.window, "turn_latency.window"),
    rows: l.rows.map((row) => ({
      profile: profile(row.profile, "turn_latency.profile"),
      p50: millis(row.p50_ms),
      p95: millis(row.p95_ms),
    })),
  };
  const s = t.speech_errors;
  const speechErrors = {
    ...head(s, [s.rows], "speech_errors"),
    window: window(s.window, "speech_errors.window"),
    rows: s.rows.map((row) => ({
      component: id(row.component, "speech_errors.component"),
      kind: oneOf(row.kind, CALL_KINDS, "speech_errors.kind"),
      calls: count(row.calls) ?? "0",
      failures: count(row.failures) ?? "0",
      errorRatio: ratio(row.error_ratio),
    })),
  };
  const f = t.failovers;
  const failovers = {
    ...head(f, [f.rows], "failovers"),
    window: window(f.window, "failovers.window"),
    rows: f.rows.map((row) => ({
      from: id(row.from_component, "failovers.from_component"),
      to: id(row.to_component, "failovers.to_component"),
      count: count(row.count),
    })),
  };
  const b = t.breakers;
  const breakers = {
    ...head(b, [b.rows], "breakers"),
    rows: b.rows.map((row) => ({
      component: id(row.component, "breakers.component"),
      state: row.state === null ? null : oneOf(row.state, BREAKER_STATES, "breakers.state"),
    })),
  };
  const catalogue = payload.control_catalogue.map((row) => ({
    control: oneOf(row.control, CONTROLS, "control_catalogue.control"),
    tier: row.tier,
    route: row.route,
    actorRoles: row.actor_roles.map((r) => id(r, "control_catalogue.actor_roles")),
    approverRoles: row.approver_roles.map((r) => id(r, "control_catalogue.approver_roles")),
  }));
  return {
    generatedAt: instant(payload.generated_at, "generated_at") ?? "",
    sources: {
      prometheus: id(payload.sources.prometheus, "sources.prometheus"),
      controls: id(payload.sources.controls, "sources.controls"),
    },
    profiles,
    reasonClasses: payload.reason_classes.map((r) => id(r, "reason_classes")),
    catalogue,
    controls,
    pending,
    sessions,
    killSwitchActivity,
    turnLatency,
    speechErrors,
    failovers,
    breakers,
  };
}

/** `ID` re-exported for the form planner, so both sides share one tenant shape. */
export const TENANT_ID = ID;
