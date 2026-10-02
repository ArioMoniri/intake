/**
 * INT-428 — the row projections of the Model lanes view-model: each reads one
 * object of the `GET /admin/model-lanes` document through `./shape`'s closed
 * key check, and refuses a label outside its closed set or not id-shaped
 * (invariant 6) and a state the server could not hold
 * ({@link ModelLanesIncoherent}).
 */
import {
  ID,
  ISO,
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsUnknownCarriesFigure,
  REASON,
  count,
  ms,
  withUnit,
} from "../ops/guards";
import {
  CEREMONIES,
  COST_STATES,
  IDENTITY_STATES,
  KEY_STATES,
  LANES,
  LAST4,
  MODEL_KEY,
  PENDING_STATES,
  PROBE_STATES,
  PROVIDERS,
  READY_STATES,
  ROLE,
  ROUTES,
  type DataClass,
} from "./payload";
import { bool, closed, figure, list } from "./shape";
import type {
  HostedOptionView,
  LaneOptionsView,
  ModelRefView,
  PendingView,
  ProviderView,
  RoleView,
  SelfHostedOptionView,
  SettingView,
  UsageView,
} from "./view";

export class ModelLanesIncoherent extends OpsPayloadRefused {}

const MODEL_ID = /^[A-Za-z0-9][A-Za-z0-9._/:-]{0,127}$/;
const VERSION = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const GIT_REVISION = /^[0-9a-f]{40}$/;
const JURISDICTION = /^[A-Z]{2}$/;
const REF_KEYS = [
  "source",
  "provider",
  "model_id",
  "version",
  "wire",
  "sha256",
  "component",
  "key",
];
const ROLE_KEYS = ["role", "lane", "inherits", "setting", "serving", "self_hosted"];
const SERVING_KEYS = [
  "available",
  "reason",
  "provider",
  "route",
  "fallback",
  "model",
  "qualified",
  "clinical_evidence",
];

// --- shapes --------------------------------------------------------------------

export function oneOf<T extends string>(value: unknown, allowed: readonly T[], what: string): T {
  if (typeof value !== "string" || !(allowed as readonly string[]).includes(value)) {
    throw new OpsLabelLeaked("label_outside_vocabulary", `${what} is outside its closed set`);
  }
  return value as T;
}

export function shaped(value: unknown, pattern: RegExp, what: string): string {
  if (typeof value !== "string" || !pattern.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not id-shaped (invariant 6)`);
  }
  return value;
}

export function nullable<T>(value: unknown, read: (inner: unknown) => T): T | null {
  return value === null ? null : read(value);
}

export function code(value: unknown, what: string): string {
  return shaped(value, REASON, what);
}

export function instant(value: unknown, what: string): string {
  if (typeof value !== "string" || !ISO.test(value)) {
    throw new OpsPayloadRefused("not_a_date", `${what} is not a timestamp`);
  }
  return value;
}

export function incoherent(what: string): never {
  throw new ModelLanesIncoherent("incoherent", what);
}

export function carriesFigure(what: string): never {
  throw new OpsUnknownCarriesFigure(
    "unknown_carries_figure",
    `${what} is unknown and still carries a figure (invariant 17)`,
  );
}

function usd(value: number): string {
  return withUnit(value.toFixed(value > 0 && value < 0.01 ? 6 : 4), "USD") ?? "";
}

// --- rows ----------------------------------------------------------------------

function modelRef(raw: unknown, what: string): ModelRefView {
  const m = closed(raw, REF_KEYS, what);
  const source = oneOf(m["source"], ["self_hosted", "hosted"] as const, `${what}.source`);
  const provider =
    source === "self_hosted"
      ? oneOf(m["provider"], ["self_hosted"] as const, `${what}.provider`)
      : oneOf(m["provider"], PROVIDERS, `${what}.provider`);
  const version = shaped(m["version"], VERSION, `${what}.version`);
  const sha256 = nullable(m["sha256"], (v) => shaped(v, SHA256, `${what}.sha256`));
  const component = nullable(m["component"], (v) => shaped(v, ID, `${what}.component`));
  if (source === "self_hosted" && (sha256 === null || component === null)) {
    incoherent(`${what}: a self-hosted model is pinned by revision and sha256 (invariant 14)`);
  }
  return {
    source,
    provider,
    modelId: shaped(m["model_id"], MODEL_ID, `${what}.model_id`),
    version,
    shortVersion: GIT_REVISION.test(version) ? version.slice(0, 8) : version,
    wire: shaped(m["wire"], MODEL_ID, `${what}.wire`),
    sha256,
    shortPin: sha256 === null ? null : sha256.slice(0, 12),
    component,
    key: shaped(m["key"], MODEL_KEY, `${what}.key`),
  };
}

function setting(raw: unknown, what: string): SettingView {
  const s = closed(raw, ["route", "model", "fallback", "fallback_model"], what);
  return {
    route: oneOf(s["route"], ROUTES, `${what}.route`),
    model: nullable(s["model"], (v) => shaped(v, MODEL_KEY, `${what}.model`)),
    fallback: nullable(s["fallback"], (v) => oneOf(v, PROVIDERS, `${what}.fallback`)),
    fallbackModel: nullable(s["fallback_model"], (v) =>
      shaped(v, MODEL_KEY, `${what}.fallback_model`),
    ),
  };
}

function serving(raw: unknown, what: string, effective: DataClass): RoleView["serving"] {
  const s = closed(raw, SERVING_KEYS, what);
  const view = {
    available: bool(s["available"], `${what}.available`),
    reason: code(s["reason"], `${what}.reason`),
    provider: nullable(s["provider"], (v) =>
      oneOf(v, ["self_hosted", ...PROVIDERS], `${what}.provider`),
    ),
    route: nullable(s["route"], (v) => oneOf(v, ROUTES, `${what}.route`)),
    fallback: bool(s["fallback"], `${what}.fallback`),
    model: nullable(s["model"], (v) => modelRef(v, `${what}.model`)),
    qualified: bool(s["qualified"], `${what}.qualified`),
    clinicalEvidence: bool(s["clinical_evidence"], `${what}.clinical_evidence`),
  };
  const route = view.route;
  if (view.available !== (route !== null)) incoherent(`${what}: served exactly when routed`);
  if (route === null && (view.provider !== null || view.model !== null || view.fallback)) {
    incoherent(`${what}: nothing serves, and still names a provider`);
  }
  if (route !== null && view.provider !== route.replace(/^hosted:/, "")) {
    incoherent(`${what}: the provider is not the route's`);
  }
  if (route !== null && route !== "self_hosted" && effective === "real_phi") {
    incoherent(`${what}: a hosted lane is unrepresentable for a real_phi deployment`);
  }
  const evidence =
    view.available && route === "self_hosted" && view.qualified && effective === "real_phi";
  if (view.clinicalEvidence && !evidence) {
    incoherent(`${what}: clinical evidence comes only from a qualified self-hosted model on PHI`);
  }
  return view;
}

function selfHostedState(raw: unknown, what: string): RoleView["selfHosted"] {
  const s = closed(raw, ["identity", "expected"], what);
  const identity = oneOf(s["identity"], IDENTITY_STATES, `${what}.identity`);
  const expected = nullable(s["expected"], (v) => modelRef(v, `${what}.expected`));
  const probed = ["healthy", "quarantined", "unreachable", "identity_mismatch"].includes(identity);
  if ((probed && expected === null) || (identity === "unattested" && expected !== null)) {
    incoherent(`${what}: an identity state with nothing to compare against`);
  }
  return { identity, expected };
}

function usageRow(raw: unknown, what: string): UsageView {
  const u = closed(raw, ["route", "provider", "p50_ms", "p95_ms", "calls", "cost"], what);
  const route = oneOf(u["route"], ["self_hosted", "hosted"] as const, `${what}.route`);
  const provider = oneOf(u["provider"], ["none", ...PROVIDERS], `${what}.provider`);
  if ((route === "self_hosted") !== (provider === "none")) {
    incoherent(`${what}: a self-hosted route has no provider, a hosted one has one`);
  }
  const c = closed(u["cost"], ["state", "usd"], `${what}.cost`);
  const state = oneOf(c["state"], COST_STATES, `${what}.cost.state`);
  const amount = figure(c["usd"], `${what}.cost.usd`);
  if (state === "known" && amount === null) incoherent(`${what}: a known cost names its figure`);
  if (state !== "known" && amount !== null) carriesFigure(`${what}.cost (${state})`);
  if ((state === "not_metered") !== (route === "self_hosted")) {
    incoherent(`${what}: only a self-hosted route is unmetered (its GPU host is billed hourly)`);
  }
  return {
    route,
    provider,
    p50: ms(figure(u["p50_ms"], `${what}.p50_ms`)),
    p95: ms(figure(u["p95_ms"], `${what}.p95_ms`)),
    calls: count(figure(u["calls"], `${what}.calls`)),
    cost: { state, usd: amount === null ? null : usd(amount) },
  };
}

export function roleRow(
  raw: unknown,
  what: string,
  effective: DataClass,
  isLane: boolean,
): RoleView {
  const r = closed(raw, isLane ? [...ROLE_KEYS, "usage"] : ROLE_KEYS, what);
  const role = shaped(r["role"], ROLE, `${what}.role`);
  const lane = oneOf(r["lane"], LANES, `${what}.lane`);
  if (role.split(".")[0] !== lane || isLane !== (role === lane)) {
    incoherent(`${what}: the role is not under its lane`);
  }
  return {
    role,
    lane,
    isLane,
    inherits: bool(r["inherits"], `${what}.inherits`),
    setting: nullable(r["setting"], (v) => setting(v, `${what}.setting`)),
    serving: serving(r["serving"], `${what}.serving`, effective),
    selfHosted: selfHostedState(r["self_hosted"], `${what}.self_hosted`),
    usage: isLane
      ? list(r["usage"], `${what}.usage`).map((u, i) => usageRow(u, `${what}.usage[${i}]`))
      : null,
  };
}

function selfHostedOption(raw: unknown, what: string): SelfHostedOptionView {
  const o = closed(
    raw,
    ["component", "pinned", "attested", "jurisdiction", "model", "identity", "qualified"],
    what,
  );
  const view = {
    component: shaped(o["component"], ID, `${what}.component`),
    pinned: bool(o["pinned"], `${what}.pinned`),
    attested: bool(o["attested"], `${what}.attested`),
    jurisdiction: nullable(o["jurisdiction"], (v) => shaped(v, JURISDICTION, `${what}.jur`)),
    model: nullable(o["model"], (v) => modelRef(v, `${what}.model`)),
    identity: oneOf(o["identity"], IDENTITY_STATES, `${what}.identity`),
    qualified: bool(o["qualified"], `${what}.qualified`),
  };
  if (view.attested && (view.model === null || !view.pinned)) {
    incoherent(`${what}: an attested model is a pinned registry row`);
  }
  if (!view.attested && !["unattested", "unconfigured"].includes(view.identity)) {
    incoherent(`${what}: an identity probe for a model nobody attested`);
  }
  return { ...view, selectable: view.attested && view.model !== null };
}

function hostedOption(raw: unknown, what: string): HostedOptionView {
  const o = closed(raw, ["provider", "model", "default", "probe", "qualified"], what);
  const provider = oneOf(o["provider"], PROVIDERS, `${what}.provider`);
  const model = modelRef(o["model"], `${what}.model`);
  if (model.source !== "hosted" || model.provider !== provider) {
    incoherent(`${what}: a hosted option names its provider's model`);
  }
  const p = closed(o["probe"], ["state", "reason"], `${what}.probe`);
  const state = oneOf(p["state"], PROBE_STATES, `${what}.probe.state`);
  const reason = nullable(p["reason"], (v) => code(v, `${what}.probe.reason`));
  if ((state === "skipped") !== (reason !== null)) {
    incoherent(`${what}: a skipped probe says why, a run one does not`);
  }
  return {
    provider,
    model,
    isDefault: bool(o["default"], `${what}.default`),
    probe: { state, reason },
    qualified: bool(o["qualified"], `${what}.qualified`),
  };
}

export function laneOptions(
  raw: unknown,
  configured: boolean,
  hostedLanes: boolean,
): LaneOptionsView[] {
  const models = closed(raw, configured ? LANES : [], "models");
  return (configured ? LANES : []).map((lane) => {
    const what = `models.${lane}`;
    const m = closed(models[lane], ["gated", "self_hosted", "hosted"], what);
    const hosted = list(m["hosted"], `${what}.hosted`).map((o, i) =>
      hostedOption(o, `${what}.hosted[${i}]`),
    );
    if (!hostedLanes && hosted.length > 0) {
      incoherent(`${what}: hosted options in a deployment that carries no hosted lane`);
    }
    for (const provider of PROVIDERS) {
      if (hosted.filter((o) => o.provider === provider && o.isDefault).length > 1) {
        incoherent(`${what}: two defaults for one provider`);
      }
    }
    return {
      lane,
      gated: bool(m["gated"], `${what}.gated`),
      selfHosted: list(m["self_hosted"], `${what}.self_hosted`).map((o, i) =>
        selfHostedOption(o, `${what}.self_hosted[${i}]`),
      ),
      hosted,
    };
  });
}

export function providerRow(raw: unknown, what: string): ProviderView {
  const p = closed(
    raw,
    ["provider", "egress_row", "listed", "self_hostable", "phi_path", "key", "ready"],
    what,
  );
  if (p["self_hostable"] !== false || p["phi_path"] !== false) {
    incoherent(`${what}: a hosted provider is neither self-hostable nor on the PHI path`);
  }
  const k = closed(p["key"], ["state", "last4", "set_at"], `${what}.key`);
  const state = oneOf(k["state"], KEY_STATES, `${what}.key.state`);
  const last4 = nullable(k["last4"], (v) => shaped(v, LAST4, `${what}.key.last4`));
  const setAt = nullable(k["set_at"], (v) => instant(v, `${what}.key.set_at`));
  if (state === "set" && last4 === null) incoherent(`${what}: a set key names its last four`);
  if (state !== "set" && (last4 !== null || setAt !== null)) carriesFigure(`${what}.key`);
  const r = closed(p["ready"], ["state", "reason"], `${what}.ready`);
  const ready = oneOf(r["state"], READY_STATES, `${what}.ready.state`);
  const reason = nullable(r["reason"], (v) => code(v, `${what}.ready.reason`));
  if ((ready === "blocked") !== (reason !== null)) {
    incoherent(`${what}: a blocked provider says why, a ready one does not`);
  }
  return {
    provider: oneOf(p["provider"], PROVIDERS, `${what}.provider`),
    egressRow: shaped(p["egress_row"], ID, `${what}.egress_row`),
    listed: bool(p["listed"], `${what}.listed`),
    key: { state, last4, setAt },
    ready: { state: ready, reason },
  };
}

export function pendingRow(raw: unknown, what: string): PendingView {
  const p = closed(
    raw,
    ["action_id", "dangerous_action_id", "tier", "state", "expires_at", "approver_role"],
    what,
  );
  const action = oneOf(
    p["dangerous_action_id"],
    Object.keys(CEREMONIES) as (keyof typeof CEREMONIES)[],
    `${what}.dangerous_action_id`,
  );
  const tier = p["tier"];
  if (tier !== 2 && tier !== 3) incoherent(`${what}: a ceremony is tier 2 or 3`);
  return {
    actionId: shaped(p["action_id"], ID, `${what}.action_id`),
    ceremony: CEREMONIES[action],
    tier: String(tier),
    state: oneOf(p["state"], PENDING_STATES, `${what}.state`),
    expiresAt: instant(p["expires_at"], `${what}.expires_at`),
    approverRole: nullable(p["approver_role"], (v) => shaped(v, ID, `${what}.approver_role`)),
  };
}
