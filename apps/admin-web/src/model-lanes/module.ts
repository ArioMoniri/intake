/**
 * INT-428 — the Model lanes module's view-model (files/08 §3; ADR-035).
 *
 * One input, the `GET /admin/model-lanes` composite; one output, the tree the
 * page paints. Pure, and it refuses rather than repairs. Before any field is
 * read, the whole document must carry no credential (`./shape`
 * {@link ModelLanesSecretLeaked}) and no target (invariant 20); then every
 * object must have exactly the schema's keys ({@link ModelLanesShapeRefused})
 * and every label must be id-shaped or inside its closed set (invariant 6).
 * Beyond the shared refusals of `../ops/guards`, one of its own:
 *
 * - {@link ModelLanesIncoherent} — a state the server could not hold: a hosted
 *   lane serving a real-PHI deployment, "clinical evidence" from anything but
 *   a qualified self-hosted model on a real-PHI deployment, a hosted provider
 *   that is self-hostable or on the PHI path (invariant 19), hosted options in
 *   a deployment that carries no hosted lane, a self-hosted model without its
 *   pin (invariant 14), or a cost whose state and figure disagree.
 *
 * Unknown is a state (invariant 17): a key not set, a price nobody supplied,
 * a Prometheus nobody configured each reach the page as a word and a code,
 * and a figure beside one is refused.
 */

import { OpsSchemaMismatch, noTarget } from "../ops/guards";
import {
  CHANGES,
  DATA_CLASSES,
  LANES,
  MODEL_LANES_SCHEMA,
  ROUTES,
  type DataClass,
  type ModelLanesPayload,
} from "./payload";
import {
  carriesFigure,
  code,
  incoherent,
  instant,
  laneOptions,
  nullable,
  oneOf,
  pendingRow,
  providerRow,
  roleRow,
  shaped,
} from "./rows";
import { bool, closed, list, noSecrets } from "./shape";
import type { Banner, ControlView, DeploymentView, ModelLanesView } from "./view";

export type * from "./payload";
export type * from "./view";
export { LANES, MODEL_LANES_SCHEMA, PROVIDERS, REASON_CLASSES, ROUTES } from "./payload";
export { ModelLanesIncoherent } from "./rows";
export { ModelLanesSecretLeaked, ModelLanesShapeRefused } from "./shape";

const SUBJECT = /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$/;
const WINDOW = /^[1-9][0-9]{0,2}[mhd]$/;

const TOP_KEYS = [
  "schema",
  "generated_at",
  "state",
  "reason",
  "deployment",
  "control",
  "lanes",
  "roles",
  "models",
  "providers",
  "usage_window",
  "usage_reason",
  "pending",
] as const;
const CONTROL_KEYS = [
  "state",
  "reason",
  "revision",
  "hosted_disabled",
  "changed_at",
  "changed_by",
  "approved_by",
  "last_change",
];

const BLANK_CONTROL: ControlView = {
  state: "unknown",
  reason: null,
  revision: null,
  hostedDisabled: null,
  changedAt: null,
  changedBy: null,
  approvedBy: null,
  lastChange: null,
};

function control(raw: unknown): ControlView {
  const state = oneOf(
    (raw as Record<string, unknown> | null)?.["state"],
    ["known", "unknown"] as const,
    "control.state",
  );
  if (state === "unknown") {
    const c = closed(raw, ["state", "reason"], "control");
    const reason = code(c["reason"], "control.reason");
    return { ...BLANK_CONTROL, reason };
  }
  const c = closed(raw, CONTROL_KEYS, "control");
  const revision = c["revision"];
  if (c["reason"] !== null || !Number.isInteger(revision) || (revision as number) < 0) {
    incoherent("control: a known record has a revision and no reason");
  }
  return {
    state,
    reason: null,
    revision: String(revision),
    hostedDisabled: bool(c["hosted_disabled"], "control.hosted_disabled"),
    changedAt: nullable(c["changed_at"], (v) => instant(v, "control.changed_at")),
    changedBy: nullable(c["changed_by"], (v) => shaped(v, SUBJECT, "control.changed_by")),
    approvedBy: nullable(c["approved_by"], (v) => shaped(v, SUBJECT, "control.approved_by")),
    lastChange: nullable(c["last_change"], (v) => oneOf(v, CHANGES, "control.last_change")),
  };
}

function deployment(raw: unknown): DeploymentView {
  const d = closed(
    raw,
    ["declared", "bound", "effective", "hosted_lanes", "data_class_mismatch"],
    "deployment",
  );
  const view = {
    declared: oneOf(d["declared"], DATA_CLASSES, "deployment.declared"),
    bound: nullable(d["bound"], (v) => oneOf(v, DATA_CLASSES, "deployment.bound")),
    effective: oneOf(d["effective"], DATA_CLASSES, "deployment.effective"),
    hostedLanes: bool(d["hosted_lanes"], "deployment.hosted_lanes"),
    mismatch: bool(d["data_class_mismatch"], "deployment.data_class_mismatch"),
  };
  if (view.mismatch !== (view.bound !== null && view.bound !== view.declared)) {
    incoherent("deployment: the mismatch flag disagrees with the classes it compares");
  }
  if (view.declared === "real_phi" && view.hostedLanes) {
    incoherent("deployment: a real-PHI image carries no hosted lane (ADR-035)");
  }
  return view;
}

function banners(d: DeploymentView | null): Banner[] {
  if (d === null) return [];
  const out: Banner[] = [];
  if (!d.hostedLanes) out.push("no_hosted_lanes");
  if (d.effective === "real_phi") out.push("real_phi");
  if (d.mismatch) out.push("data_class_mismatch");
  return out;
}

/** The whole Model lanes view. Throws an `OpsPayloadRefused` rather than paint a lie. */
export function renderModelLanes(payload: ModelLanesPayload): ModelLanesView {
  if (payload === null || typeof payload !== "object" || payload.schema !== MODEL_LANES_SCHEMA) {
    throw new OpsSchemaMismatch("schema_mismatch", `expected ${MODEL_LANES_SCHEMA}`);
  }
  noSecrets(payload, "$");
  noTarget(payload, "$");
  const top = closed(payload, TOP_KEYS, "$");
  const state = oneOf(top["state"], ["known", "unknown"] as const, "state");
  const reason = nullable(top["reason"], (v) => code(v, "reason"));
  const ctl = control(top["control"]);
  if ((state === "known") !== (ctl.state === "known") || (state === "unknown") === !reason) {
    incoherent("$: the document's state is its control's, and an unknown one names a code");
  }
  const usageReason = nullable(top["usage_reason"], (v) => code(v, "usage_reason"));
  const lanesRaw = list(top["lanes"], "lanes");
  const rolesRaw = list(top["roles"], "roles");
  const providersRaw = list(top["providers"], "providers");
  const pendingRaw = list(top["pending"], "pending");

  if (top["deployment"] === null) {
    const blank = [lanesRaw, rolesRaw, providersRaw, pendingRaw].every((l) => l.length === 0);
    if (!blank || state !== "unknown" || usageReason === null) carriesFigure("$ (unconfigured)");
  }
  const dep = nullable(top["deployment"], deployment);
  const effective: DataClass = dep?.effective ?? "real_phi";
  const lanes = lanesRaw.map((r, i) => roleRow(r, `lanes[${i}]`, effective, true));
  if (dep !== null && lanes.map((l) => l.role).join() !== LANES.join()) {
    incoherent("lanes: every lane, once, in order");
  }
  if (usageReason !== null && lanes.some((l) => (l.usage ?? []).length > 0)) {
    carriesFigure("usage");
  }
  const roles = rolesRaw.map((r, i) => roleRow(r, `roles[${i}]`, effective, false));
  if (new Set(roles.map((r) => r.role)).size !== roles.length) incoherent("roles: one row each");
  const providers = providersRaw.map((p, i) => providerRow(p, `providers[${i}]`));
  if (dep !== null && !dep.hostedLanes && providers.length > 0) {
    incoherent("providers: a deployment without hosted lanes lists no provider");
  }
  return {
    generatedAt: instant(top["generated_at"], "generated_at"),
    state,
    reason,
    deployment: dep,
    banners: banners(dep),
    control: ctl,
    lanes,
    roles,
    options: laneOptions(top["models"], dep !== null, dep?.hostedLanes ?? false),
    providers,
    usage: { window: shaped(top["usage_window"], WINDOW, "usage_window"), reason: usageReason },
    pending: pendingRaw.map((p, i) => pendingRow(p, `pending[${i}]`)),
    routes: dep?.hostedLanes ? [...ROUTES] : ["self_hosted"],
  };
}
