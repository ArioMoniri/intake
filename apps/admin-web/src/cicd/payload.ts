/**
 * INT-187 — the wire shape the CI/CD page reads: the `GET /admin/cicd` document
 * (`intake.admin.cicd.v1`, produced by
 * `services/api/src/intake_api/admin/cicd_console.py`). Field names are the
 * API's, snake_case, so a rename on either side is a type error here rather
 * than a silently blank cell.
 */

export const CICD_SCHEMA = "intake.admin.cicd.v1";

export type TileState = "ok" | "unknown";

export interface SectionPayload {
  state: TileState;
  reason: string | null;
}

export interface RunPayload {
  run_number: number;
  status: string;
  conclusion: string;
  head_sha: string;
  duration_s: number | null;
  updated_at: string | null;
  failed_jobs: string[];
  failed_job_count: number | null;
}

export interface GateResultPayload {
  workflow: string;
  gate: string;
  conclusion: string;
}

export interface RefPayload {
  kind: "branch" | "pull_request";
  ref: string;
  results: GateResultPayload[];
  passing: number;
  total: number;
}

export interface ReleasePayload {
  tag: string;
  head_sha: string;
  published_at: string | null;
  signing: string | null;
  deployed_here: boolean;
}

export interface DeploymentPayload {
  environment: string;
  source: string;
  git_sha: string | null;
  built_at: string | null;
  sbom_digest: string | null;
  stamped: boolean;
}

export interface NotDeployedPayload extends SectionPayload {
  deployed: boolean;
  basis: string;
}

export interface FreezePayload extends SectionPayload {
  engaged: boolean | null;
  revision: number | null;
  changed_at: string | null;
  changed_by: string | null;
  approved_by: string | null;
  last_change: string | null;
  reason_class: string | null;
}

export interface PendingPayload {
  action_id: string;
  dangerous_action_id: string;
  tier: number;
  control: string;
  base_revision: number;
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
}

export interface CicdPayload {
  schema: typeof CICD_SCHEMA;
  generated_at: string;
  reason_classes: string[];
  sources: { prometheus: string; freeze_store: string; slo_files: string };
  control_catalogue: CatalogueRowPayload[];
  tiles: {
    pipelines: SectionPayload & {
      branch: string | null;
      workflows: { workflow: string; runs: RunPayload[] }[];
    };
    gates: SectionPayload & {
      branch: string | null;
      checks_enforced: boolean | null;
      required: { workflow: string; gate: string }[];
      refs: RefPayload[];
    };
    releases: SectionPayload & { releases: ReleasePayload[] };
    deployments: SectionPayload & { rows: DeploymentPayload[] };
    argo_cd: NotDeployedPayload & { applications: unknown[] };
    canary: NotDeployedPayload;
    freeze: FreezePayload;
    error_budget: SectionPayload & { exhausted: string[]; unmeasured: string[] };
    deploy_gate: SectionPayload & {
      allowed: boolean;
      refusals: string[];
      notes: string[];
      enforcement: { point: string; status: string }[];
    };
    pending: SectionPayload & { actions: PendingPayload[] };
  };
}
