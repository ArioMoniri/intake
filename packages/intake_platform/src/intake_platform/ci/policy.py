"""INT-206 — the no-PHI-in-CI policy: the declaration, and the six surfaces.

files/06 §5 states the rule in one line — *"CI: no PHI, synthetic fixtures,
TR-DC runners"* — and CLAUDE.md invariant 6 is the law behind it. This module
turns both into something that fails.

A PHI-shaped value reaches a CI context through six doors, and each is checked
here:

1. **fixtures** — what CI reads as data. Every identifier-shaped value in a
   scanned tree must sit inside a corpus a human declared synthetic, and each
   declaration is pinned by sha256, so a new identifier can only arrive through
   a reviewed diff. Pattern-scanning fixtures alone proves that we can author
   clean fixtures; the hash is what makes it a control.
2. **env** — a variable's value *and its name*. `PATIENT_05321234567=` in a
   job's environment is a phone number in the runner's process table.
3. **logs** — a step that prints a declared corpus into the job log, which is
   retained for 30 d hot and 1 y cold (files/10 §6).
4. **artefacts** — an upload is downloadable for its entire retention window by
   anyone with read access, a wider audience than the log.
5. **cache** — a cache outlives the job and is restorable by later jobs.
6. **runners** — where the job ran at all. A `runs-on` that resolves to nothing
   is a job executing somewhere nobody decided (see
   :mod:`intake_platform.ci.pools`).

Two things this is deliberately not. It is not the runtime PHI scan — that is
invariant 36, over live `/admin/*` responses and collector output, and it
belongs to the console. And it is not the security gate set: gitleaks, Semgrep,
Trivy, cosign and `make security` are INT-019, which calls this policy rather
than reimplementing it.

Findings never carry a matched value. This runs in a job whose stdout is a
retained log, so a gate that printed the PHI it found would be the leak it
exists to prevent.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from intake_platform.ci.errors import CiPolicyError
from intake_platform.ci.phi import find_identifiers
from intake_platform.ci.pools import RunnerPools, RunsOnKind, load_runner_pools, resolve_runs_on
from intake_platform.ci.workflows import (
    SECRET_REFERENCE_RE,
    Workflow,
    WorkflowJob,
    load_workflows,
    uses_is_pinned,
    with_paths,
)

__all__ = [
    "CACHE_ACTIONS",
    "POLICY_PATH",
    "POOLS_PATH",
    "UPLOAD_ACTIONS",
    "WORKFLOW_DIR",
    "Finding",
    "NoPhiPolicy",
    "Surface",
    "SyntheticCorpus",
    "load_policy",
    "run_ci_policy",
    "scan_environment",
    "scan_fixture_tree",
    "scan_workflows",
]

#: Where the policy's own files live, relative to the repository root.
POLICY_PATH = Path("infra") / "ci" / "no-phi-policy.yaml"
POOLS_PATH = Path("infra") / "ci" / "runners.yaml"
WORKFLOW_DIR = Path(".github") / "workflows"

#: Action names whose `path:` input names a cache, in any of their sub-forms.
CACHE_ACTIONS = ("actions/cache",)
#: Action names whose `path:` input names an upload.
UPLOAD_ACTIONS = ("actions/upload-artifact",)


class Surface(StrEnum):
    FIXTURES = "fixtures"
    ENV = "env"
    LOGS = "logs"
    ARTEFACTS = "artefacts"
    CACHE = "cache"
    RUNNERS = "runners"
    WORKFLOW = "workflow"


@dataclass(frozen=True, slots=True)
class Finding:
    """One way PHI could reach CI. Carries a digest, never a value."""

    surface: Surface
    where: str
    detail: str


class SyntheticCorpus(BaseModel):
    """A file in a scanned tree that may legitimately carry identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    origin: Literal["authored", "vendored"]
    provenance: str = Field(min_length=1)
    licence: str = Field(min_length=1)
    #: What the file hashed to when a human read it and called it synthetic.
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class NoPhiPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scanned_trees: tuple[str, ...] = Field(min_length=1)
    synthetic_corpora: tuple[SyntheticCorpus, ...]
    cache_paths: tuple[str, ...]
    artefact_paths: tuple[str, ...]
    permitted_secrets: tuple[str, ...]

    def corpus_for(self, relative_path: str) -> SyntheticCorpus | None:
        for corpus in self.synthetic_corpora:
            if corpus.path == relative_path:
                return corpus
        return None

    @property
    def corpus_paths(self) -> frozenset[str]:
        return frozenset(corpus.path for corpus in self.synthetic_corpora)


def load_policy(path: Path) -> NoPhiPolicy:
    """Load and validate infra/ci/no-phi-policy.yaml."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        raise CiPolicyError(f"{path}: unreadable policy file: {err}") from err
    try:
        return NoPhiPolicy.model_validate(raw)
    except ValidationError as err:
        raise CiPolicyError(f"{path}: {err}") from err


# --- surface 1: fixtures ---------------------------------------------------------------


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan_fixture_tree(repo_root: Path, policy: NoPhiPolicy) -> tuple[Finding, ...]:
    """Every identifier in a scanned tree must sit in a declared, pinned corpus."""
    findings: list[Finding] = []
    for tree in policy.scanned_trees:
        base = repo_root / tree
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_root).as_posix()
            corpus = policy.corpus_for(relative)
            if corpus is not None:
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != corpus.sha256:
                    findings.append(
                        Finding(
                            Surface.FIXTURES,
                            relative,
                            "declared synthetic corpus no longer hashes to the reviewed "
                            f"sha256 ({corpus.sha256[:16]}… on file, {actual[:16]}… declared "
                            "in infra/ci/no-phi-policy.yaml). Re-read the file, satisfy "
                            "yourself it is still synthetic, then update the declaration.",
                        )
                    )
                continue
            text = path.read_bytes().decode("utf-8", errors="ignore")
            for hit in find_identifiers(text):
                findings.append(
                    Finding(
                        Surface.FIXTURES,
                        f"{relative}:{_line_of(text, hit.start)}",
                        f"{hit.kind.value}-shaped value (digest {hit.digest}) in a fixture "
                        "CI reads, with no synthetic-corpus declaration. Declare the file in "
                        "infra/ci/no-phi-policy.yaml with its provenance and sha256, or "
                        "remove the value.",
                    )
                )
    return tuple(findings)


# --- surface 2: env --------------------------------------------------------------------


def _is_platform_serial(name: str, value: str) -> bool:
    """A bare integer in a variable GitHub reserves for itself.

    Not an allow-list, and the difference matters. GitHub refuses to let a
    workflow, an action or a step set a variable in the ``GITHUB_`` or
    ``RUNNER_`` namespace — they are written by the runner and by nothing else —
    so nothing can be smuggled in through one. What is skipped is narrower
    still: only a value that is entirely decimal digits, which is the shape of a
    run id, a repository id or an actor id.

    The reason this exists at all is measured rather than theoretical. One
    integer in a hundred passes the TC Kimlik checksum, and ``GITHUB_RUN_ID`` is
    an eleven-digit integer that changes every run — so scanning it would fail
    roughly one CI run in a hundred, on a value that is not a person. A gate
    that cries wolf at 1 % is a gate somebody switches off. Anything else in
    those variables — ``GITHUB_HEAD_REF``, which carries an author-chosen branch
    name — is still scanned.
    """
    return name.startswith(("GITHUB_", "RUNNER_")) and value.isdigit()


def scan_environment(env: Mapping[str, str]) -> tuple[Finding, ...]:
    """Scan an environment mapping — names as well as values.

    The name is scanned with underscores opened out to spaces. The detectors
    are anchored on word boundaries because they were written for prose, and an
    underscore is a word character: ``PATIENT_05321234567`` would otherwise
    read as one token and slip past a phone-number pattern that catches the
    same digits in a sentence. That variable name is a phone number in the
    runner's process table, in the job's `env` context, and in any `set -x`
    trace, so it is a finding.
    """
    findings: list[Finding] = []
    for name in sorted(env):
        value = env[name]
        for label, text in (("name", name.replace("_", " ")), ("value", value)):
            if label == "value" and _is_platform_serial(name, value):
                continue
            for hit in find_identifiers(text):
                findings.append(
                    Finding(
                        Surface.ENV,
                        name,
                        f"{hit.kind.value}-shaped value (digest {hit.digest}) in the "
                        f"environment variable's {label}; CI carries no patient data "
                        "(CLAUDE.md invariant 6, files/06 §5)",
                    )
                )
    return tuple(findings)


# --- surfaces 3-6: the workflows -------------------------------------------------------


def _declared(path: str, declared: Sequence[str]) -> bool:
    candidate = path.lstrip("./")
    for entry in declared:
        allowed = entry.lstrip("./").rstrip("/")
        if candidate == allowed or candidate.startswith(f"{allowed}/"):
            return True
    return False


def _permission_findings(where: str, permissions: object) -> list[Finding]:
    if permissions is None:
        return [
            Finding(
                Surface.WORKFLOW,
                where,
                "no permissions block: an undeclared job inherits the repository default, "
                "which may be read-write on every scope",
            )
        ]
    if isinstance(permissions, str) and permissions != "read-all":
        return [
            Finding(
                Surface.WORKFLOW,
                where,
                f"permissions: {permissions} — a blanket grant. Declare the scopes the job "
                "needs; write-all hands the job token the whole repository",
            )
        ]
    return []


def _step_findings(workflow_name: str, job: WorkflowJob, policy: NoPhiPolicy) -> list[Finding]:
    findings: list[Finding] = []
    for step in job.steps:
        where = f"{workflow_name}:{job.name}:{step.where}"
        action = step.uses.split("@", 1)[0]

        if not uses_is_pinned(step.uses):
            findings.append(
                Finding(
                    Surface.WORKFLOW,
                    where,
                    f"action {step.uses} is not pinned to a commit sha — a tag can be "
                    "silently repointed",
                )
            )

        if action.startswith(CACHE_ACTIONS):
            for path in with_paths(step):
                if not _declared(path, policy.cache_paths):
                    findings.append(
                        Finding(
                            Surface.CACHE,
                            where,
                            f"caches {path}, which is not in cache_paths. A cache "
                            "outlives the job and any later job can restore it",
                        )
                    )

        if action.startswith(UPLOAD_ACTIONS):
            for path in with_paths(step):
                # A declared corpus is refused whatever artefact_paths says: the
                # declaration makes it safe to keep in the tree, not safe to hand
                # to everyone with read access for the retention window.
                if path in policy.corpus_paths:
                    findings.append(
                        Finding(
                            Surface.ARTEFACTS,
                            where,
                            f"uploads {path}, a declared synthetic corpus. A declaration "
                            "says the file may live in the tree, not that it may be "
                            "published as a downloadable artefact",
                        )
                    )
                elif not _declared(path, policy.artefact_paths):
                    findings.append(
                        Finding(
                            Surface.ARTEFACTS,
                            where,
                            f"uploads {path}, which is not in artefact_paths. An artefact "
                            "is downloadable for its whole retention window by anyone "
                            "with read access",
                        )
                    )

        if step.run:
            for corpus_path in sorted(policy.corpus_paths):
                if corpus_path in step.run:
                    findings.append(
                        Finding(
                            Surface.LOGS,
                            where,
                            f"a run step names {corpus_path} in its command; a corpus "
                            "printed into the job log is retained 30 d hot / 1 y cold "
                            "(files/10 §6)",
                        )
                    )

        findings.extend(
            Finding(Surface.ENV, where, finding.detail)
            for finding in scan_environment({str(k): str(v) for k, v in step.env.items()})
        )
    return findings


def scan_workflows(
    workflows: Sequence[Workflow], policy: NoPhiPolicy, pools: RunnerPools | None
) -> tuple[Finding, ...]:
    """Check every committed workflow against the policy. Reads; never writes."""
    findings: list[Finding] = []
    for workflow in workflows:
        name = workflow.path.name
        findings.extend(_permission_findings(name, workflow.permissions))

        findings.extend(
            Finding(Surface.ENV, f"{name}:env", finding.detail)
            for finding in scan_environment({str(k): str(v) for k, v in workflow.env.items()})
        )

        for secret in sorted(set(SECRET_REFERENCE_RE.findall(workflow.raw_text))):
            if secret not in policy.permitted_secrets:
                findings.append(
                    Finding(
                        Surface.WORKFLOW,
                        name,
                        f"references secrets.{secret}, which is not in permitted_secrets. "
                        "CI carries no secrets by design; a credential in a workflow is a "
                        "credential in every fork's pull-request context",
                    )
                )

        for job in workflow.jobs:
            findings.extend(
                Finding(Surface.ENV, f"{name}:{job.name}:env", finding.detail)
                for finding in scan_environment({str(k): str(v) for k, v in job.env.items()})
            )
            if job.permissions is not None:
                findings.extend(_permission_findings(f"{name}:{job.name}", job.permissions))
            if pools is not None:
                resolution = resolve_runs_on(job.runs_on, pools)
                if resolution.kind is RunsOnKind.UNRESOLVED:
                    findings.append(
                        Finding(Surface.RUNNERS, f"{name}:{job.name}", resolution.reason)
                    )
            findings.extend(_step_findings(name, job, policy))
    return tuple(findings)


# --- the whole policy ------------------------------------------------------------------


def run_ci_policy(repo_root: Path, env: Mapping[str, str] | None = None) -> tuple[Finding, ...]:
    """Every surface, over one repository. Empty means the gate is green."""
    policy = load_policy(repo_root / POLICY_PATH)
    pools = load_runner_pools(repo_root / POOLS_PATH)

    findings: list[Finding] = []
    findings.extend(scan_fixture_tree(repo_root, policy))
    findings.extend(scan_environment(env or {}))

    workflow_dir = repo_root / WORKFLOW_DIR
    # A repository with no workflow directory has no CI surface to check. Said
    # plainly rather than raised: the gate is about what CI does, and a tree
    # with no CI does nothing.
    if workflow_dir.is_dir():
        findings.extend(scan_workflows(load_workflows(workflow_dir), policy, pools))
    return tuple(findings)
