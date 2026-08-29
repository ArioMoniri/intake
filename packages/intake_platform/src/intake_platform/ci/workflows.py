"""INT-206 — reading .github/workflows as data.

The policy checks the workflows; it never writes them. Ownership of that
directory sits with the repository owner, so the shape here is deliberately
one-way: parse what is committed, assert the properties the policy needs, and
report a finding when one does not hold. A workflow change the policy would
require is a diff for a human to apply, not an edit this code makes.

The parse is intentionally shallow. Everything the policy asks about — which
runner a job selects, what a step caches, what it uploads, what it prints,
which secrets it reaches for, what permissions it holds — is visible in the
literal YAML. Evaluating `${{ }}` expressions would be a second, worse
implementation of GitHub's own engine, and the interesting attacks are visible
without it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from intake_platform.ci.errors import CiPolicyError

__all__ = [
    "SECRET_REFERENCE_RE",
    "Workflow",
    "WorkflowJob",
    "WorkflowStep",
    "load_workflows",
    "uses_is_pinned",
    "with_paths",
]

#: `${{ secrets.NAME }}`, in any of the spacings GitHub accepts.
SECRET_REFERENCE_RE = re.compile(r"secrets\.([A-Za-z_][A-Za-z0-9_]*)")

#: A pinned `uses:` names a full 40-hex commit. A tag can be repointed
#: silently, which is the reason ci.yml pins in the first place.
_PINNED_USES_RE = re.compile(r"^[^@]+@[0-9a-f]{40}$")

_LOCAL_USES_PREFIXES = ("./", "docker://")


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    index: int
    name: str
    uses: str
    run: str
    with_: Mapping[str, object] = field(default_factory=dict)
    env: Mapping[str, object] = field(default_factory=dict)

    @property
    def where(self) -> str:
        return self.name or (f"step {self.index}")


@dataclass(frozen=True, slots=True)
class WorkflowJob:
    name: str
    runs_on: str | tuple[str, ...]
    permissions: object
    steps: tuple[WorkflowStep, ...]
    env: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Workflow:
    path: Path
    name: str
    permissions: object
    jobs: tuple[WorkflowJob, ...]
    #: The file as committed. Kept so the secret-reference sweep reads every
    #: place an expression can appear — `if:`, `continue-on-error:`, a matrix
    #: entry — rather than only the keys this parse models.
    raw_text: str = ""
    env: Mapping[str, object] = field(default_factory=dict)


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _runs_on(raw: object) -> str | tuple[str, ...]:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return tuple(str(item) for item in raw)
    # `runs-on: {group: …, labels: […]}` — the labels are what selects.
    if isinstance(raw, dict):
        labels = raw.get("labels")
        if isinstance(labels, list):
            return tuple(str(item) for item in labels)
        if isinstance(labels, str):
            return labels
    return ()


def _steps(raw: object) -> tuple[WorkflowStep, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[WorkflowStep] = []
    for index, item in enumerate(raw):
        mapping = _as_mapping(item)
        out.append(
            WorkflowStep(
                index=index,
                name=str(mapping.get("name", "")),
                uses=str(mapping.get("uses", "")),
                run=str(mapping.get("run", "")),
                with_=_as_mapping(mapping.get("with")),
                env=_as_mapping(mapping.get("env")),
            )
        )
    return tuple(out)


def _workflow_from(path: Path, raw: object, raw_text: str) -> Workflow:
    document = _as_mapping(raw)
    jobs_raw = _as_mapping(document.get("jobs"))
    jobs: list[WorkflowJob] = []
    for job_name, job_raw in jobs_raw.items():
        job = _as_mapping(job_raw)
        jobs.append(
            WorkflowJob(
                name=str(job_name),
                runs_on=_runs_on(job.get("runs-on")),
                permissions=job.get("permissions"),
                steps=_steps(job.get("steps")),
                env=_as_mapping(job.get("env")),
            )
        )
    return Workflow(
        path=path,
        name=str(document.get("name", path.stem)),
        permissions=document.get("permissions"),
        jobs=tuple(jobs),
        raw_text=raw_text,
        env=_as_mapping(document.get("env")),
    )


def load_workflows(directory: Path) -> tuple[Workflow, ...]:
    """Parse every workflow in ``directory``, in a stable order."""
    if not directory.is_dir():
        raise CiPolicyError(f"{directory}: no workflow directory")
    out: list[Workflow] = []
    for path in sorted(directory.iterdir()):
        if path.suffix not in {".yml", ".yaml"} or not path.is_file():
            continue
        try:
            raw_text = path.read_text(encoding="utf-8")
            raw = yaml.safe_load(raw_text)
        except (OSError, yaml.YAMLError) as err:
            raise CiPolicyError(f"{path}: unreadable workflow: {err}") from err
        out.append(_workflow_from(path, raw, raw_text))
    return tuple(out)


def uses_is_pinned(uses: str) -> bool:
    """True when a `uses:` reference names a commit rather than a moving ref."""
    if not uses or uses.startswith(_LOCAL_USES_PREFIXES):
        return True
    return bool(_PINNED_USES_RE.match(uses))


def with_paths(step: WorkflowStep) -> tuple[str, ...]:
    """Every path an action's `path:` input names — it accepts a multi-line list."""
    raw = step.with_.get("path")
    if raw is None:
        return ()
    if isinstance(raw, list):
        candidates: Iterable[str] = (str(item) for item in raw)
    else:
        candidates = str(raw).splitlines()
    return tuple(line.strip() for line in candidates if line.strip())
