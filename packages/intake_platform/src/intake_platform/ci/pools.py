"""INT-206 — self-hosted runner pools, and what happens while there are none.

files/08 §6 gives the CI row of the self-hosting registry as *"GitHub Actions
with self-hosted runners in the TR DC … probe: runner heartbeat … fallback:
GitHub-hosted runners (no PHI in CI ever)"*. This module is the pool half of
that row: the declaration schema, the loader, and label resolution.

The pool list in ``infra/ci/runners.yaml`` is empty, and it stays empty until a
human supplies what nobody has supplied. Every field a row would need is refused
rather than defaulted, and resolution of a self-hosted label fails closed with
the blocker row named. A runner label that resolves to nothing is a job running
somewhere nobody decided, which is a worse outcome than a job that does not
start.

**What blocks this is a decision, not capacity, and the distinction matters
because the obvious reading is wrong.** HB-I5 records that no in-country
provider is under contract — but that row is about **GPU** supply, and a CI
runner needs CPU. files/00_STATE.md §2 records the AWS Istanbul Local Zone as GA
since May 2026 with C7i/M7i/R7i, which is this shape exactly. So the open
questions are HB-I7 (does the owner spend on CI capacity at all) and HB-L11
(physical residency is not legal residency; the operator of that zone is AWS
EMEA SARL and its control plane is in Frankfurt, so "TR DC" is a claim somebody
has to be able to defend). Neither is answerable here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from intake_platform.ci.errors import CiPolicyError

__all__ = [
    "GITHUB_HOSTED_LABELS",
    "RUNNER_POOL_ASK",
    "SELF_HOSTED_LABEL",
    "RunnerPool",
    "RunnerPools",
    "RunsOnKind",
    "RunsOnResolution",
    "load_runner_pools",
    "resolve_runs_on",
]

#: The GitHub-hosted labels this repository is allowed to select. A closed set
#: rather than a prefix match: `ubuntu-latest` moving under us is a supply-chain
#: event we want to notice, and an unrecognised label is a typo that would
#: otherwise queue forever.
GITHUB_HOSTED_LABELS = frozenset(
    {
        "ubuntu-latest",
        "ubuntu-24.04",
        "ubuntu-22.04",
        "macos-latest",
        "macos-15",
        "macos-14",
        "windows-latest",
        "windows-2022",
    }
)

#: The label GitHub requires on every self-hosted runner.
SELF_HOSTED_LABEL = "self-hosted"

RUNNER_POOL_ASK = (
    "No self-hosted runner pool is declared in infra/ci/runners.yaml, and none may be "
    "invented. HB-I7 owns it (self-hosted CI runners — 175 issues x a 35-60 min PR gate is "
    "100-175 CPU-hours; owner, spend), and HB-L11 is why naming a facility is a decision "
    "rather than a lookup: physical residency is not legal residency, and the residency "
    "claim files/06 §5 makes about CI has to be one somebody can check. Note what does NOT "
    "block this: HB-I5's 'no in-country provider' finding is about GPU supply, and a CI "
    "runner needs CPU — files/00_STATE.md §2 records the AWS Istanbul Local Zone as GA with "
    "C7i/M7i/R7i, which is this shape exactly. The constraint is the decision and the spend, "
    "not capacity. Until a pool exists, CI runs on GitHub-hosted runners, which files/08 §6 "
    "records as the fallback exactly because no PHI is ever in CI."
)


class RunnerPool(BaseModel):
    """One declared pool of self-hosted runners."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    #: The facility. Empty is refused: a residency claim nobody can check is
    #: worse than an absent one (files/06 §5, HB-I5).
    location: str = Field(min_length=1)
    #: The operator, and the DPA counterparty.
    provider: str = Field(min_length=1)
    #: The GitHub runner group, so the pool is reachable from this repo only.
    runner_group: str = Field(min_length=1)
    ephemeral: bool
    phi_path: bool
    heartbeat_url: str = Field(min_length=1)
    max_heartbeat_age_s: int = Field(gt=0)

    @field_validator("ephemeral")
    @classmethod
    def _must_be_ephemeral(cls, value: bool) -> bool:  # noqa: FBT001
        if not value:
            raise ValueError(
                "a runner pool must be ephemeral: a persistent runner keeps its "
                "workspace between jobs, and a workspace that outlives a job is how "
                "one repository's checkout reaches the next one"
            )
        return value

    @field_validator("phi_path")
    @classmethod
    def _may_not_be_on_the_phi_path(cls, value: bool) -> bool:  # noqa: FBT001
        if value:
            raise ValueError(
                "a runner pool may not declare itself on the PHI path — there is no CI "
                "job that may touch patient data (CLAUDE.md invariant 6; files/06 §5)"
            )
        return value


class RunnerPools(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pools: tuple[RunnerPool, ...] = ()

    def get(self, label: str) -> RunnerPool | None:
        for pool in self.pools:
            if pool.label == label:
                return pool
        return None


class RunsOnKind(StrEnum):
    GITHUB_HOSTED = "github-hosted"
    SELF_HOSTED = "self-hosted"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class RunsOnResolution:
    kind: RunsOnKind
    labels: tuple[str, ...]
    pool: RunnerPool | None
    reason: str


def load_runner_pools(path: Path) -> RunnerPools:
    """Load and validate infra/ci/runners.yaml."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        raise CiPolicyError(f"{path}: unreadable runner-pool file: {err}") from err
    if raw is None:
        raw = {}
    try:
        return RunnerPools.model_validate(raw)
    except ValidationError as err:
        raise CiPolicyError(f"{path}: {err}") from err


def resolve_runs_on(runs_on: str | Sequence[str], pools: RunnerPools) -> RunsOnResolution:
    """Decide what a workflow's ``runs-on`` actually selects.

    A GitHub-hosted label from the closed set resolves. A `self-hosted` label
    resolves only to a declared pool. Everything else is UNRESOLVED, and an
    unresolved `runs-on` is a finding rather than a warning.
    """
    labels = (runs_on,) if isinstance(runs_on, str) else tuple(str(label) for label in runs_on)

    if SELF_HOSTED_LABEL in labels:
        specific = [label for label in labels if label != SELF_HOSTED_LABEL]
        for label in specific:
            pool = pools.get(label)
            if pool is not None:
                return RunsOnResolution(RunsOnKind.SELF_HOSTED, labels, pool, "")
        named = ", ".join(specific) or SELF_HOSTED_LABEL
        return RunsOnResolution(
            RunsOnKind.UNRESOLVED,
            labels,
            None,
            f"self-hosted runner {named} is not a declared pool. {RUNNER_POOL_ASK}",
        )

    if len(labels) == 1 and labels[0] in GITHUB_HOSTED_LABELS:
        return RunsOnResolution(RunsOnKind.GITHUB_HOSTED, labels, None, "")

    return RunsOnResolution(
        RunsOnKind.UNRESOLVED,
        labels,
        None,
        f"runs-on {list(labels)} is neither a known GitHub-hosted label nor a declared "
        f"self-hosted pool",
    )
