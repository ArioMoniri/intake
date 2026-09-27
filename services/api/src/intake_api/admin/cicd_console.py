"""The CI/CD & releases composite behind ``GET /admin/cicd`` (INT-187; files/08 §3).

One JSON document, ``intake.admin.cicd.v1``, that ``apps/admin-web`` renders.
Every source is server-side (files/08 §0b F1 — the browser names none):

- **Prometheus**, through the fixed :data:`CICD_QUERIES` table: the ops
  collector's ``ops_cicd_*`` families (``intake_probes.ops_cicd`` — recent
  runs per workflow with their failing jobs, every required gate on the
  watched branch and on the open PRs, whether GitHub itself enforces them,
  releases and their signing state). The collector holds the read-only GitHub
  token (OpenBao, egress-guarded); this API never sees it and never dials
  GitHub. Every series is catalogued (invariant 13; a test holds it).
- **The SLO files and their SLIs** — the error budget, through
  :func:`~intake_api.admin.release_gate.error_budget`, which the deploy path's
  release gate calls too.
- **The release-freeze store and the four-eyes service** — the freeze, who set
  it, and lift requests awaiting a second key (ids and roles only).
- **This process's own ``/version``** — the deployment the console runs beside
  (``VersionInfo``, read in process: no network, nothing to guess).

**Not deployed is a fact, not a gap to paint over.** No Argo CD Application
and no canary controller exist under ``infra/``; the Argo CD and canary tiles
say so, and ``tests/admin/test_cicd_console.py`` fails the day one lands so the
tile is wired rather than left claiming absence. The one deploy path is
``infra/staging/deploy.sh``, and :data:`ENFORCEMENT_POINTS` says where the
freeze is enforced — held against the script by a test.

**Unknown is a state (invariant 17).** A tile whose source is unconfigured,
unreachable, erroring, silent or failing at the collector is ``{"state":
"unknown", "reason": <code>}`` with no figure; one failing source blanks its
own tiles only. **Ids only (invariant 6)**: a label that is not id-shaped, or a
state outside its closed vocabulary, turns its tile unknown rather than paint it.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml
from intake_platform.admin.actions import (
    CICD_CEREMONIES,
    DEPLOY_FREEZE_ENGAGE,
    DEPLOY_FREEZE_LIFT,
    DangerousAction,
)
from intake_platform.admin.flag_governance import FlagChangeReason
from intake_platform.admin.four_eyes import PendingAction
from intake_platform.health import VersionInfo
from intake_platform.release_freeze import (
    DeployFreeze,
    DeployFreezeChange,
    ReleaseFreezeStore,
    release_verdict,
)
from intake_platform.slo import SLOFile
from intake_probes.ops_ci import CI_CONCLUSIONS, CI_STATUSES

from intake_api.admin.ops_prom import (
    ID_LABEL,
    PromClient,
    PromSession,
    Sample,
    TileUnknown,
    prom_client_from_env,
)
from intake_api.admin.release_gate import error_budget, read_freeze
from intake_api.admin.reliability_console import ENV_SLO_DIR, load_slo_files
from intake_api.settings import environment_name

__all__ = [
    "CICD_QUERIES",
    "CICD_SCHEMA",
    "ENFORCEMENT_POINTS",
    "build_cicd_console",
    "error_budget",
    "freeze_view",
    "load_cicd_console",
]

CICD_SCHEMA: Final = "intake.admin.cicd.v1"
_DEFAULT_SLO_DIR: Final = "docs/slo"

#: The only PromQL this API runs for the CI/CD tiles. A caller cannot add to it.
CICD_QUERIES: Final[Mapping[str, str]] = {
    "collector_up": "max by (source) (ops_collector_source_up)",
    "runs": ("max by (workflow, branch, run_number, status, conclusion, head_sha) (ops_cicd_run)"),
    "run_duration": "max by (workflow, branch, run_number) (ops_cicd_run_duration_seconds)",
    "run_updated": "max by (workflow, branch, run_number) (ops_cicd_run_updated_seconds)",
    "failed_job": "max by (workflow, branch, run_number, job) (ops_cicd_failed_job)",
    "failed_jobs": "max by (workflow, branch, run_number) (ops_cicd_failed_jobs)",
    "branch_gate": "max by (branch, workflow, gate, conclusion) (ops_cicd_branch_gate)",
    "pr_gate": "max by (pr, workflow, gate, conclusion) (ops_cicd_pr_gate)",
    "checks_enforced": "max by (branch) (ops_cicd_branch_checks_enforced)",
    "release": "max by (tag, head_sha) (ops_cicd_release)",
    "release_published": "max by (tag) (ops_cicd_release_published_seconds)",
    "release_signing": "max by (tag, state) (ops_cicd_release_signing)",
}

#: The label set each query must come back with — exactly.
_LABELS: Final[Mapping[str, frozenset[str]]] = {
    "collector_up": frozenset({"source"}),
    "runs": frozenset({"workflow", "branch", "run_number", "status", "conclusion", "head_sha"}),
    "run_duration": frozenset({"workflow", "branch", "run_number"}),
    "run_updated": frozenset({"workflow", "branch", "run_number"}),
    "failed_job": frozenset({"workflow", "branch", "run_number", "job"}),
    "failed_jobs": frozenset({"workflow", "branch", "run_number"}),
    "branch_gate": frozenset({"branch", "workflow", "gate", "conclusion"}),
    "pr_gate": frozenset({"pr", "workflow", "gate", "conclusion"}),
    "checks_enforced": frozenset({"branch"}),
    "release": frozenset({"tag", "head_sha"}),
    "release_published": frozenset({"tag"}),
    "release_signing": frozenset({"tag", "state"}),
}

#: A check run's conclusion, plus the two the collector adds for a required
#: gate: still running, and no check run at all on that head.
_GATE_CONCLUSIONS: Final = CI_CONCLUSIONS | {"pending", "missing"}
#: What GitHub treats as satisfying a required check.
_PASSING: Final = frozenset({"success", "neutral", "skipped"})
_SIGNING: Final = frozenset(
    {"signed", "sign_failed", "sign_pending", "not_signed", "not_applicable"}
)
_SHA: Final = re.compile(r"^[0-9a-f]{40}$")
_DIGEST: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
_ISO: Final = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")

#: Where the freeze is enforced, stated once and held against the scripts by
#: ``tests/infra/test_staging_release_freeze.py``. Argo CD would be the second
#: point; it is not deployed, and the list says so rather than omitting it.
ENFORCEMENT_POINTS: Final[tuple[Mapping[str, str], ...]] = (
    {"point": "infra/staging/deploy.sh", "status": "enforced"},
    {"point": "argo_cd_sync", "status": "not_deployed"},
)


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _closed(value: str, allowed: frozenset[str]) -> str:
    if value not in allowed:
        raise TileUnknown("unexpected_label")
    return value


def _sha(value: str) -> str:
    if not _SHA.fullmatch(value):
        raise TileUnknown("unexpected_label")
    return value


def _number(value: str) -> int:
    if not value.isdigit():
        raise TileUnknown("unexpected_label")
    return int(value)


def _by(samples: tuple[Sample, ...], *names: str) -> dict[tuple[str, ...], float]:
    return {tuple(s.labels[name] for name in names): s.value for s in samples}


def _require_collector(session: PromSession) -> None:
    """The collector's cicd source must be reporting and healthy: a failing
    read cleared its series, and absence is never painted as "no runs"."""
    sources = _by(session.fetch("collector_up"), "source")
    state = sources.get(("cicd",))
    if state is None:
        raise TileUnknown("no_series")
    if state < 1:
        raise TileUnknown("collector_source_failing")


def _one_branch(samples: tuple[Sample, ...]) -> str | None:
    branches = {s.labels["branch"] for s in samples}
    if len(branches) > 1:
        raise TileUnknown("unexpected_label")
    return branches.pop() if branches else None


# --- Prometheus tiles --------------------------------------------------------------


def _pipelines(session: PromSession, _: VersionInfo) -> dict[str, Any]:
    _require_collector(session)
    runs = session.fetch("runs")
    branch = _one_branch(runs)
    durations = _by(session.fetch("run_duration"), "workflow", "run_number")
    updated = _by(session.fetch("run_updated"), "workflow", "run_number")
    counts = _by(session.fetch("failed_jobs"), "workflow", "run_number")
    jobs: dict[tuple[str, str], list[str]] = {}
    for s in session.fetch("failed_job"):
        jobs.setdefault((s.labels["workflow"], s.labels["run_number"]), []).append(s.labels["job"])
    workflows: dict[str, list[dict[str, Any]]] = {}
    for s in runs:
        if s.value < 1:
            continue
        key = (s.labels["workflow"], s.labels["run_number"])
        duration = durations.get(key)
        count = counts.get(key)
        workflows.setdefault(s.labels["workflow"], []).append(
            {
                "run_number": _number(s.labels["run_number"]),
                "status": _closed(s.labels["status"], CI_STATUSES),
                "conclusion": _closed(s.labels["conclusion"], CI_CONCLUSIONS),
                "head_sha": _sha(s.labels["head_sha"]),
                "duration_s": None if duration is None else int(round(duration)),
                "updated_at": _iso(updated.get(key)),
                "failed_jobs": sorted(jobs.get(key, [])),
                "failed_job_count": None if count is None else int(round(count)),
            }
        )
    return {
        "branch": branch,
        "workflows": [
            {
                "workflow": name,
                "runs": sorted(rows, key=lambda row: row["run_number"], reverse=True),
            }
            for name, rows in sorted(workflows.items())
        ],
    }


def _gate_results(samples: Sequence[Sample]) -> list[dict[str, str]]:
    results = [
        {
            "workflow": s.labels["workflow"],
            "gate": s.labels["gate"],
            "conclusion": _closed(s.labels["conclusion"], _GATE_CONCLUSIONS),
        }
        for s in samples
        if s.value >= 1
    ]
    return sorted(results, key=lambda row: (row["workflow"], row["gate"]))


def _ref(kind: str, ref: str, samples: Sequence[Sample]) -> dict[str, Any]:
    results = _gate_results(samples)
    return {
        "kind": kind,
        "ref": ref,
        "results": results,
        "passing": sum(1 for row in results if row["conclusion"] in _PASSING),
        "total": len(results),
    }


def _gates(session: PromSession, _: VersionInfo) -> dict[str, Any]:
    _require_collector(session)
    on_branch = session.fetch("branch_gate")
    on_prs = session.fetch("pr_gate")
    enforced = session.fetch("checks_enforced")
    branch = _one_branch(on_branch) or _one_branch(enforced)
    by_pr: dict[str, list[Sample]] = {}
    for s in on_prs:
        _number(s.labels["pr"])
        by_pr.setdefault(s.labels["pr"], []).append(s)
    refs = [_ref("branch", branch, on_branch)] if branch is not None and on_branch else []
    refs += [
        _ref("pull_request", pr, rows)
        for pr, rows in sorted(by_pr.items(), key=lambda kv: -int(kv[0]))
    ]
    required = sorted({(row["workflow"], row["gate"]) for ref in refs for row in ref["results"]})
    flags = _by(enforced, "branch")
    return {
        "branch": branch,
        "checks_enforced": None
        if branch is None or (branch,) not in flags
        else flags[(branch,)] >= 1,
        "required": [{"workflow": workflow, "gate": gate} for workflow, gate in required],
        "refs": refs,
    }


def _releases(session: PromSession, version: VersionInfo) -> dict[str, Any]:
    _require_collector(session)
    published = _by(session.fetch("release_published"), "tag")
    signing: dict[str, str] = {}
    for s in session.fetch("release_signing"):
        if s.value < 1:
            continue
        if s.labels["tag"] in signing:
            raise TileUnknown("unexpected_label")
        signing[s.labels["tag"]] = _closed(s.labels["state"], _SIGNING)
    rows = []
    for s in session.fetch("release"):
        if s.value < 1:
            continue
        tag, sha = s.labels["tag"], _sha(s.labels["head_sha"])
        rows.append(
            {
                "tag": tag,
                "head_sha": sha,
                "published_at": _iso(published.get((tag,))),
                # the collector states a signing state for every release it
                # reports; a missing one is shown as unknown, never guessed
                "signing": signing.get(tag),
                "deployed_here": sha == version.git_sha,
            }
        )
    rows.sort(key=lambda row: (row["published_at"] or "", row["tag"]), reverse=True)
    return {"releases": rows}


#: Every Prometheus tile's shape when it is unknown: the same keys, no figure.
_PROM_TILES: Final[
    Mapping[str, tuple[Callable[[PromSession, VersionInfo], dict[str, Any]], dict[str, Any]]]
] = {
    "pipelines": (_pipelines, {"branch": None, "workflows": []}),
    "gates": (_gates, {"branch": None, "checks_enforced": None, "required": [], "refs": []}),
    "releases": (_releases, {"releases": []}),
}


# --- the process, the infra tree, the store and the ceremony ---------------------------


def _deployments(version: VersionInfo, environment: str) -> dict[str, Any]:
    """This API's own ``/version``. A value that is not a real stamp is
    withheld (``None``) rather than shown: "dev" is not a version."""
    if not ID_LABEL.fullmatch(environment):
        return {"state": "unknown", "reason": "environment_not_id_shaped", "rows": []}
    sha = version.git_sha if _SHA.fullmatch(version.git_sha) else None
    built = version.built_at if _ISO.fullmatch(version.built_at) else None
    digest = version.sbom_digest if _DIGEST.fullmatch(version.sbom_digest) else None
    row = {
        "environment": environment,
        "source": "this_api",
        "git_sha": sha,
        "built_at": built,
        "sbom_digest": digest,
        "stamped": None not in (sha, built, digest),
    }
    return {"state": "ok", "reason": None, "rows": [row]}


def _not_deployed(basis: str) -> dict[str, Any]:
    return {"state": "ok", "reason": None, "deployed": False, "basis": basis}


def freeze_view(freeze: DeployFreeze) -> dict[str, Any]:
    """The freeze as the console and the write routes show it."""
    return {
        "engaged": freeze.engaged,
        "revision": freeze.revision,
        "changed_at": freeze.changed_at.isoformat() if freeze.changed_at else None,
        "changed_by": freeze.changed_by,
        "approved_by": freeze.approved_by,
        "last_change": freeze.last_change.value if freeze.last_change else None,
        "reason_class": freeze.reason_class,
    }


_FREEZE_EMPTY: Final[Mapping[str, Any]] = {
    "engaged": None,
    "revision": None,
    "changed_at": None,
    "changed_by": None,
    "approved_by": None,
    "last_change": None,
    "reason_class": None,
}


def _pending(actions: Sequence[PendingAction]) -> dict[str, Any]:
    rows = [
        {
            "action_id": pending.id,
            "dangerous_action_id": pending.action.id,
            "tier": int(pending.action.tier),
            "control": pending.evidence["control"],
            "base_revision": int(pending.evidence["base_revision"]),
            "requested_role": pending.actor.role.value,
            "created_at": pending.created_at.isoformat(),
            "expires_at": pending.expires_at.isoformat(),
        }
        for pending in actions
        if pending.action in CICD_CEREMONIES
    ]
    return {"state": "ok", "reason": None, "actions": rows}


_CATALOGUE: Final[tuple[tuple[DeployFreezeChange, DangerousAction, str], ...]] = (
    (DeployFreezeChange.ENGAGE, DEPLOY_FREEZE_ENGAGE, "POST /admin/cicd/freeze"),
    (DeployFreezeChange.LIFT, DEPLOY_FREEZE_LIFT, "POST /admin/cicd/freeze/lift"),
)


def _control_catalogue() -> list[dict[str, Any]]:
    """What each control is, read off the ``DangerousAction`` registry."""
    return [
        {
            "control": change.value,
            "dangerous_action_id": action.id,
            "route": route,
            "tier": int(action.tier),
            "direction": action.direction.value,
            "actor_roles": sorted(role.value for role in action.actor_roles),
            "approver_roles": sorted(role.value for role in action.approver_roles),
        }
        for change, action, route in _CATALOGUE
    ]


def build_cicd_console(
    *,
    prom: PromClient | None,
    slo_files: Sequence[SLOFile] | None,
    freeze_store: ReleaseFreezeStore | None,
    pending: Sequence[PendingAction],
    version: VersionInfo,
    environment: str,
    now: datetime,
    prom_misconfigured: bool = False,
) -> dict[str, Any]:
    """The whole ``intake.admin.cicd.v1`` document."""
    tiles: dict[str, Any] = {}
    session = PromSession(prom, CICD_QUERIES, _LABELS) if prom is not None else None
    no_prom = "prometheus_misconfigured" if prom_misconfigured else "prometheus_unconfigured"
    for tile_id, (builder, empty) in _PROM_TILES.items():
        if session is None:
            tiles[tile_id] = {"state": "unknown", "reason": no_prom, **empty}
            continue
        try:
            tiles[tile_id] = {"state": "ok", "reason": None, **empty, **builder(session, version)}
        except TileUnknown as unknown:
            tiles[tile_id] = {"state": "unknown", "reason": unknown.reason, **empty}
    tiles["deployments"] = _deployments(version, environment)
    tiles["argo_cd"] = {**_not_deployed("no_argocd_in_infra"), "applications": []}
    tiles["canary"] = _not_deployed("no_canary_controller_in_infra")

    freeze, failure = read_freeze(freeze_store)
    tiles["freeze"] = (
        {"state": "ok", "reason": None, **freeze_view(freeze)}
        if freeze is not None
        else {"state": "unknown", "reason": failure, **_FREEZE_EMPTY}
    )
    budget, budget_tile = error_budget(prom, slo_files, prom_misconfigured)
    tiles["error_budget"] = budget_tile
    verdict = release_verdict(freeze=freeze, freeze_failure=failure, budget=budget)
    tiles["deploy_gate"] = {
        "state": "ok",
        "reason": None,
        "allowed": verdict.allowed,
        "refusals": list(verdict.refusals),
        "notes": list(verdict.notes),
        "enforcement": [dict(point) for point in ENFORCEMENT_POINTS],
    }
    tiles["pending"] = _pending(pending)

    if session is None:
        prometheus = "misconfigured" if prom_misconfigured else "unconfigured"
    else:
        prometheus = "unreachable" if session.unreachable else "ok"
    return {
        "schema": CICD_SCHEMA,
        "generated_at": now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # INT-188's closed change-reason set, served so the page's forms offer
        # exactly what the write routes accept rather than a copy of it
        "reason_classes": [reason.value for reason in FlagChangeReason],
        "sources": {
            "prometheus": prometheus,
            "freeze_store": "ok" if freeze is not None else (failure or "unconfigured"),
            "slo_files": "ok" if slo_files is not None else "unreadable",
        },
        "control_catalogue": _control_catalogue(),
        "tiles": tiles,
    }


def load_cicd_console(
    now: datetime,
    *,
    freeze_store: ReleaseFreezeStore | None,
    pending: Sequence[PendingAction],
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Wire the composite from the process environment (the same Prometheus and
    SLO variables as the ops and reliability composites, and ``/version``'s own
    stamps). A malformed URL is ``prometheus_misconfigured``, never a crash."""
    env = os.environ if env is None else env
    try:
        prom, misconfigured = prom_client_from_env(env), False
    except ValueError:
        prom, misconfigured = None, True
    try:
        files: tuple[SLOFile, ...] | None = load_slo_files(
            Path(env.get(ENV_SLO_DIR, "").strip() or _DEFAULT_SLO_DIR)
        )
    except (OSError, ValueError, yaml.YAMLError):
        files = None
    version = VersionInfo(
        git_sha=env.get("INTAKE_GIT_SHA", "dev"),
        built_at=env.get("INTAKE_BUILT_AT", "dev"),
        sbom_digest=env.get("INTAKE_SBOM_DIGEST", "dev"),
    )
    return build_cicd_console(
        prom=prom,
        slo_files=files,
        freeze_store=freeze_store,
        pending=pending,
        version=version,
        environment=environment_name(env),
        now=now,
        prom_misconfigured=misconfigured,
    )
