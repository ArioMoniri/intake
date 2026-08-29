"""INT-206 — self-hosted CI runners in the TR DC, and the no-PHI-in-CI policy.

Two halves of one issue, and they meet at a single sentence in files/08 §6: the
self-hosting registry's CI row reads *"GitHub Actions with self-hosted runners
in the TR DC … probe: runner heartbeat … fallback: GitHub-hosted runners (no
PHI in CI ever)"*. The parenthesis is what makes the fallback acceptable, so
the policy that keeps it true is not a companion to the runner work — it is its
precondition.

- :mod:`intake_platform.ci.pools` — the runner-pool declaration and label
  resolution. The pool list is empty; HB-I7 (spend) and HB-L11 (physical
  residency is not legal residency) own it — NOT HB-I5, which is GPU supply and
  does not bind a CPU runner — and nothing is filled in to look complete.
- :mod:`intake_platform.ci.heartbeat` — the probe's decision half.
- :mod:`intake_platform.ci.phi` — identifier detection, borrowed from
  :mod:`intake_platform.deid` so there is one definition rather than two, and
  reporting digests rather than values.
- :mod:`intake_platform.ci.policy` — the declaration and the six surfaces.
- :mod:`intake_platform.ci.workflows` — a read-only parse of
  ``.github/workflows``. This package checks workflows; it never writes them.
"""

from __future__ import annotations

from intake_platform.ci.errors import CiPolicyError
from intake_platform.ci.heartbeat import HeartbeatReport, evaluate_heartbeats
from intake_platform.ci.phi import (
    IdentifierHit,
    IdentifierKind,
    find_identifiers,
    identifier_digest,
)
from intake_platform.ci.policy import (
    CACHE_ACTIONS,
    POLICY_PATH,
    POOLS_PATH,
    UPLOAD_ACTIONS,
    WORKFLOW_DIR,
    Finding,
    NoPhiPolicy,
    Surface,
    SyntheticCorpus,
    load_policy,
    run_ci_policy,
    scan_environment,
    scan_fixture_tree,
    scan_workflows,
)
from intake_platform.ci.pools import (
    GITHUB_HOSTED_LABELS,
    RUNNER_POOL_ASK,
    SELF_HOSTED_LABEL,
    RunnerPool,
    RunnerPools,
    RunsOnKind,
    RunsOnResolution,
    load_runner_pools,
    resolve_runs_on,
)
from intake_platform.ci.workflows import (
    SECRET_REFERENCE_RE,
    Workflow,
    WorkflowJob,
    WorkflowStep,
    load_workflows,
    uses_is_pinned,
    with_paths,
)

__all__ = [
    "CACHE_ACTIONS",
    "GITHUB_HOSTED_LABELS",
    "POLICY_PATH",
    "POOLS_PATH",
    "RUNNER_POOL_ASK",
    "SECRET_REFERENCE_RE",
    "SELF_HOSTED_LABEL",
    "UPLOAD_ACTIONS",
    "WORKFLOW_DIR",
    "CiPolicyError",
    "Finding",
    "HeartbeatReport",
    "IdentifierHit",
    "IdentifierKind",
    "NoPhiPolicy",
    "RunnerPool",
    "RunnerPools",
    "RunsOnKind",
    "RunsOnResolution",
    "Surface",
    "SyntheticCorpus",
    "Workflow",
    "WorkflowJob",
    "WorkflowStep",
    "evaluate_heartbeats",
    "find_identifiers",
    "identifier_digest",
    "load_policy",
    "load_runner_pools",
    "load_workflows",
    "resolve_runs_on",
    "run_ci_policy",
    "scan_environment",
    "scan_fixture_tree",
    "scan_workflows",
    "uses_is_pinned",
    "with_paths",
]
