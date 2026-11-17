/**
 * INT-187 — the CI/CD & releases module's view-model (files/08 §3 "CI/CD &
 * releases").
 *
 * One input, the `GET /admin/cicd` composite; one output, the tree the page
 * paints. Pure, and it refuses rather than repairs — with the shared refusals
 * of `../ops/guards` (schema, ids, unknown-with-a-figure, targets) and three
 * of its own, each a figure the page would otherwise paint over its evidence:
 *
 * - {@link CicdGateIncoherent} — "deploys allowed" beside an engaged freeze,
 *   an exhausted error budget or a freeze nobody could read; or an allowed
 *   verdict that still lists a refusal. A bent payload must not tell an
 *   operator a deploy would ship when the deploy path would refuse it.
 * - {@link CicdFreezeIncoherent} — a freeze record the server could not hold:
 *   engaged by a lift, a lift with no second key, an engage with one.
 * - {@link CicdNotWired} — Argo CD or a deploy canary shown as deployed. Neither
 *   exists in `infra/`; the day one does, this page is wired to it, and until
 *   then a "deployed" it cannot render is a claim it cannot back.
 */

import {
  ISO,
  OpsLabelLeaked,
  OpsPayloadRefused,
  OpsSchemaMismatch,
  REASON,
  blank,
  count,
  id,
  noTarget,
  reason,
  withUnit,
} from "../ops/guards";
import {
  CICD_SCHEMA,
  type CicdPayload,
  type DeploymentPayload,
  type FreezePayload,
  type PendingPayload,
  type RefPayload,
  type ReleasePayload,
  type RunPayload,
  type TileState,
} from "./payload";

export type * from "./payload";
export { CICD_SCHEMA } from "./payload";

export class CicdGateIncoherent extends OpsPayloadRefused {}
export class CicdFreezeIncoherent extends OpsPayloadRefused {}
export class CicdNotWired extends OpsPayloadRefused {}

/** GitHub's run vocabularies (intake_probes.ops_ci). */
const RUN_STATUSES = new Set([
  "queued",
  "in_progress",
  "completed",
  "waiting",
  "requested",
  "pending",
]);
const CONCLUSIONS = new Set([
  "success",
  "failure",
  "cancelled",
  "skipped",
  "timed_out",
  "action_required",
  "neutral",
  "stale",
  "startup_failure",
  "none",
]);
const GATE_CONCLUSIONS = new Set([...CONCLUSIONS, "pending", "missing"]);
const SIGNING = new Set(["signed", "sign_failed", "sign_pending", "not_signed", "not_applicable"]);
const CONTROLS = new Set(["freeze_engage", "freeze_lift"]);
const ENFORCEMENT = new Set(["enforced", "not_deployed"]);
const REF_KINDS = new Set(["branch", "pull_request"]);

/** A git ref name: a branch or a release tag, named by the repository. */
const REF = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$/;
const SHA = /^[0-9a-f]{40}$/;
const DIGEST = /^sha256:[0-9a-f]{64}$/;
const PR = /^[0-9]{1,9}$/;
const SLO = /^[a-z0-9][a-z0-9_.-]{0,63}\/[a-z0-9][a-z0-9_.-]{0,63}$/;
const POINT = /^[a-z0-9][a-z0-9_./-]{0,127}$/;
const SUBJECT = /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$/;

// --- shapes --------------------------------------------------------------------

function oneOf(value: string, allowed: Set<string>, what: string): string {
  if (typeof value !== "string" || !allowed.has(value)) {
    throw new OpsLabelLeaked("label_outside_vocabulary", `${what} is outside its closed set`);
  }
  return value;
}

function shaped(value: string, pattern: RegExp, what: string): string {
  if (typeof value !== "string" || !pattern.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not id-shaped (invariant 6)`);
  }
  return value;
}

function instant(value: string | null, what: string): string | null {
  if (value !== null && (typeof value !== "string" || !ISO.test(value))) {
    throw new OpsPayloadRefused("not_a_date", `${what} is not a timestamp`);
  }
  return value;
}

function code(value: string, what: string): string {
  if (typeof value !== "string" || !REASON.test(value)) {
    throw new OpsLabelLeaked("label_not_id_shaped", `${what} is not a code`);
  }
  return value;
}

function short(sha: string): string {
  return sha.slice(0, 8);
}

// --- the view ------------------------------------------------------------------

interface Head {
  state: TileState;
  reason: string | null;
}

export interface RunView {
  runNumber: string;
  status: string;
  conclusion: string;
  sha: string;
  shortSha: string;
  duration: string | null;
  updatedAt: string | null;
  failedJobs: string[];
  unnamedFailures: string | null;
}

export interface RefView {
  kind: string;
  ref: string;
  results: { workflow: string; gate: string; conclusion: string }[];
  passing: string;
  total: string;
}

export interface ReleaseView {
  tag: string;
  sha: string;
  shortSha: string;
  publishedAt: string | null;
  signing: string | null;
  deployedHere: boolean;
}

export interface DeploymentView {
  environment: string;
  source: string;
  sha: string | null;
  shortSha: string | null;
  builtAt: string | null;
  sbomDigest: string | null;
  stamped: boolean;
}

export interface PendingView {
  actionId: string;
  control: string;
  baseRevision: string;
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

export interface CicdView {
  generatedAt: string;
  sources: { prometheus: string; freezeStore: string; sloFiles: string };
  reasonClasses: string[];
  catalogue: ControlView[];
  pipelines: Head & { branch: string | null; workflows: { workflow: string; runs: RunView[] }[] };
  gates: Head & {
    branch: string | null;
    checksEnforced: boolean | null;
    required: { workflow: string; gate: string }[];
    refs: RefView[];
  };
  releases: Head & { rows: ReleaseView[] };
  deployments: Head & { rows: DeploymentView[] };
  argoCd: { deployed: false; basis: string };
  canary: { deployed: false; basis: string };
  freeze: Head & {
    engaged: boolean | null;
    revision: string | null;
    changedAt: string | null;
    changedBy: string | null;
    approvedBy: string | null;
    lastChange: string | null;
    reasonClass: string | null;
  };
  errorBudget: Head & { exhausted: string[]; unmeasured: string[] };
  deployGate: {
    allowed: boolean;
    refusals: string[];
    notes: string[];
    enforcement: { point: string; status: string }[];
  };
  pending: Head & { actions: PendingView[] };
}

function head(tile: Head, figures: unknown[], what: string): Head {
  const why = reason(tile, what);
  blank(tile, figures, what);
  return { state: tile.state, reason: why };
}

function run(row: RunPayload, workflow: string): RunView {
  const where = `pipelines[${workflow}#${row.run_number}]`;
  if (!Number.isInteger(row.run_number) || row.run_number < 0) {
    throw new OpsPayloadRefused("not_a_count", `${where}.run_number`);
  }
  const sha = shaped(row.head_sha, SHA, `${where}.head_sha`);
  const failedJobs = row.failed_jobs.map((job) => id(job, `${where}.failed_jobs`));
  const total = row.failed_job_count;
  if (total !== null && (!Number.isInteger(total) || total < failedJobs.length)) {
    throw new OpsPayloadRefused("count_incoherent", `${where}: fewer failing jobs than named`);
  }
  const unnamed = total === null ? 0 : total - failedJobs.length;
  return {
    runNumber: String(row.run_number),
    status: oneOf(row.status, RUN_STATUSES, `${where}.status`),
    conclusion: oneOf(row.conclusion, CONCLUSIONS, `${where}.conclusion`),
    sha,
    shortSha: short(sha),
    duration: withUnit(count(row.duration_s), "s"),
    updatedAt: instant(row.updated_at, `${where}.updated_at`),
    failedJobs,
    unnamedFailures: unnamed > 0 ? String(unnamed) : null,
  };
}

function ref(row: RefPayload): RefView {
  const kind = oneOf(row.kind, REF_KINDS, "gates.refs.kind");
  const name = shaped(row.ref, kind === "branch" ? REF : PR, "gates.refs.ref");
  const results = row.results.map((result) => ({
    workflow: id(result.workflow, `gates[${name}].workflow`),
    gate: id(result.gate, `gates[${name}].gate`),
    conclusion: oneOf(result.conclusion, GATE_CONCLUSIONS, `gates[${name}].conclusion`),
  }));
  if (row.total !== results.length || row.passing < 0 || row.passing > row.total) {
    throw new OpsPayloadRefused("count_incoherent", `gates[${name}]: counts do not match rows`);
  }
  return { kind, ref: name, results, passing: String(row.passing), total: String(row.total) };
}

function release(row: ReleasePayload): ReleaseView {
  const tag = shaped(row.tag, REF, "releases.tag");
  const sha = shaped(row.head_sha, SHA, `releases[${tag}].head_sha`);
  return {
    tag,
    sha,
    shortSha: short(sha),
    publishedAt: instant(row.published_at, `releases[${tag}].published_at`),
    signing: row.signing === null ? null : oneOf(row.signing, SIGNING, `releases[${tag}].signing`),
    deployedHere: row.deployed_here === true,
  };
}

function deployment(row: DeploymentPayload): DeploymentView {
  const environment = id(row.environment, "deployments.environment");
  const sha = row.git_sha === null ? null : shaped(row.git_sha, SHA, "deployments.git_sha");
  const digest =
    row.sbom_digest === null ? null : shaped(row.sbom_digest, DIGEST, "deployments.sbom_digest");
  const builtAt = instant(row.built_at, "deployments.built_at");
  if (row.stamped && (sha === null || digest === null || builtAt === null)) {
    throw new OpsPayloadRefused("count_incoherent", "a stamped deployment names all three stamps");
  }
  return {
    environment,
    source: id(row.source, "deployments.source"),
    sha,
    shortSha: sha === null ? null : short(sha),
    builtAt,
    sbomDigest: digest,
    stamped: row.stamped === true,
  };
}

function subject(value: string | null, what: string): string | null {
  return value === null ? null : shaped(value, SUBJECT, what);
}

function freeze(tile: FreezePayload): CicdView["freeze"] {
  const figures = [tile.engaged, tile.revision, tile.changed_by, tile.last_change];
  const view = {
    ...head(tile, figures, "freeze"),
    engaged: tile.engaged,
    revision: tile.revision === null ? null : String(tile.revision),
    changedAt: instant(tile.changed_at, "freeze.changed_at"),
    changedBy: subject(tile.changed_by, "freeze.changed_by"),
    approvedBy: subject(tile.approved_by, "freeze.approved_by"),
    lastChange:
      tile.last_change === null ? null : oneOf(tile.last_change, CONTROLS, "freeze.last_change"),
    reasonClass: tile.reason_class === null ? null : code(tile.reason_class, "freeze.reason_class"),
  };
  if (view.state === "ok") {
    const lifted = view.lastChange === "freeze_lift";
    const engagedBy = view.lastChange === "freeze_engage";
    if (
      (view.engaged === true && !engagedBy) ||
      (view.engaged === false && view.lastChange !== null && !lifted) ||
      (lifted && view.approvedBy === null) ||
      (engagedBy && view.approvedBy !== null)
    ) {
      throw new CicdFreezeIncoherent(
        "freeze_incoherent",
        "the freeze record says something the server could not hold",
      );
    }
  }
  return view;
}

function pendingRow(row: PendingPayload): PendingView {
  const actionId = id(row.action_id, "pending.action_id");
  return {
    actionId,
    control: oneOf(row.control, CONTROLS, `pending[${actionId}].control`),
    baseRevision: String(row.base_revision),
    requestedRole: id(row.requested_role, `pending[${actionId}].requested_role`),
    expiresAt: instant(row.expires_at, `pending[${actionId}].expires_at`) ?? "",
  };
}

function notDeployed(tile: { deployed: boolean; basis: string }, what: string) {
  if (tile.deployed !== false) {
    throw new CicdNotWired(
      "not_wired",
      `${what} is shown as deployed, and this page is not wired to it`,
    );
  }
  return { deployed: false as const, basis: code(tile.basis, `${what}.basis`) };
}

/** The whole CI/CD view. Throws an `OpsPayloadRefused` rather than paint a lie. */
export function renderCicd(payload: CicdPayload): CicdView {
  if (payload.schema !== CICD_SCHEMA) {
    throw new OpsSchemaMismatch("schema_mismatch", `expected ${CICD_SCHEMA}`);
  }
  noTarget(payload, "$");
  const t = payload.tiles;

  const p = t.pipelines;
  const pipelines = {
    ...head(p, [p.workflows, p.branch], "pipelines"),
    branch: p.branch === null ? null : shaped(p.branch, REF, "pipelines.branch"),
    workflows: p.workflows.map((w) => {
      const workflow = id(w.workflow, "pipelines.workflow");
      return { workflow, runs: w.runs.map((row) => run(row, workflow)) };
    }),
  };
  const g = t.gates;
  const gates = {
    ...head(g, [g.refs, g.required, g.branch, g.checks_enforced], "gates"),
    branch: g.branch === null ? null : shaped(g.branch, REF, "gates.branch"),
    checksEnforced: g.checks_enforced,
    required: g.required.map((row) => ({
      workflow: id(row.workflow, "gates.required.workflow"),
      gate: id(row.gate, "gates.required.gate"),
    })),
    refs: g.refs.map(ref),
  };
  const r = t.releases;
  const releases = { ...head(r, [r.releases], "releases"), rows: r.releases.map(release) };
  const d = t.deployments;
  const deployments = { ...head(d, [d.rows], "deployments"), rows: d.rows.map(deployment) };
  const f = freeze(t.freeze);
  const b = t.error_budget;
  const errorBudget = {
    ...head(b, [b.exhausted, b.unmeasured], "error_budget"),
    exhausted: b.exhausted.map((name) => shaped(name, SLO, "error_budget.exhausted")),
    unmeasured: b.unmeasured.map((name) => shaped(name, SLO, "error_budget.unmeasured")),
  };
  const v = t.deploy_gate;
  const deployGate = {
    allowed: v.allowed,
    refusals: v.refusals.map((c) => code(c, "deploy_gate.refusals")),
    notes: v.notes.map((c) => code(c, "deploy_gate.notes")),
    enforcement: v.enforcement.map((row) => ({
      point: shaped(row.point, POINT, "deploy_gate.enforcement.point"),
      status: oneOf(row.status, ENFORCEMENT, "deploy_gate.enforcement.status"),
    })),
  };
  const mustRefuse =
    f.engaged === true || f.state === "unknown" || errorBudget.exhausted.length > 0;
  if (
    deployGate.allowed !== (deployGate.refusals.length === 0) ||
    (deployGate.allowed && mustRefuse)
  ) {
    throw new CicdGateIncoherent(
      "gate_incoherent",
      "the deploy gate says allowed where the deploy path would refuse",
    );
  }
  const pending = {
    ...head(t.pending, [t.pending.actions], "pending"),
    actions: t.pending.actions.map(pendingRow),
  };
  const catalogue = payload.control_catalogue.map((row) => ({
    control: oneOf(row.control, CONTROLS, "control_catalogue.control"),
    tier: row.tier,
    route: row.route,
    actorRoles: row.actor_roles.map((role) => id(role, "control_catalogue.actor_roles")),
    approverRoles: row.approver_roles.map((role) => id(role, "control_catalogue.approver_roles")),
  }));
  return {
    generatedAt: instant(payload.generated_at, "generated_at") ?? "",
    sources: {
      prometheus: id(payload.sources.prometheus, "sources.prometheus"),
      freezeStore: id(payload.sources.freeze_store, "sources.freeze_store"),
      sloFiles: id(payload.sources.slo_files, "sources.slo_files"),
    },
    reasonClasses: payload.reason_classes.map((c) => code(c, "reason_classes")),
    catalogue,
    pipelines,
    gates,
    releases,
    deployments,
    argoCd: notDeployed(t.argo_cd, "argo_cd"),
    canary: notDeployed(t.canary, "canary"),
    freeze: f,
    errorBudget,
    deployGate,
    pending,
  };
}
