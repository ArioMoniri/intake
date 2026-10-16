"""Shared backlog logic: loading, readiness, selection (LOOP.md step 1).

Selection rules, from LOOP.md verbatim:
  "Select: first issue in file order (phase P0->P3) with `status: todo`, all
   `depends_on` satisfied, and no `blocked:*` label. `awaiting-human`
   SATISFIES a dependency for an issue that depends only on the non-gated part
   of it — this is deliberate, and without it 58 % of the backlog silently
   never becomes Ready."
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
ISSUES_FILE = REPO / "docs" / "backlog" / "issues.yaml"
# INT-452: the GitHub state the roadmap renders from, captured offline by
# `make roadmap-snapshot` (scripts/backlog/roadmap_snapshot.py), plus the row
# floor: every id that had a row when the snapshot was taken.
SNAPSHOT_FILE = REPO / "docs" / "backlog" / "github_snapshot.json"
# The count the three hard-coded pins held on main 6cd8c988 (16 Oct 2026),
# counted three ways in docs/evidence/INT-452.md. It may be raised; lowering it
# is the one way to shrink the floor, and it is a reviewed diff.
ROW_FLOOR_MINIMUM = 343

PHASE_ORDER = ["P0", "P1", "P2", "P3"]
DEP_SATISFIED_STATUSES = {"done", "awaiting-human", "withdrawn"}


def load_snapshot(path: Path | None = None) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((path or SNAPSHOT_FILE).read_text(encoding="utf-8"))
    return data


def row_floor_violations(
    ids: list[str], floor: list[str], minimum: int = ROW_FLOOR_MINIMUM
) -> list[str]:
    """INT-452: the derived replacement for the hard-coded row-count pins.

    Ids are unique; every id in the snapshot's row floor still has a row (a row
    is withdrawn, never removed); and the floor itself is not smaller than
    `minimum`. A new row needs no edit anywhere, so rows stop colliding.
    """
    out: list[str] = []
    dupes = sorted(i for i, n in Counter(ids).items() if n > 1)
    if dupes:
        out.append("duplicate row ids: " + ", ".join(dupes))
    present = set(ids)
    out += [
        f"{iid} is in the snapshot's row floor but has no row (rows are withdrawn, never removed)"
        for iid in sorted(set(floor) - present)
    ]
    if len(set(floor)) < minimum:
        out.append(
            f"the snapshot's row floor holds {len(set(floor))} ids, below the minimum of "
            f"{minimum} (backlog_lib.ROW_FLOOR_MINIMUM only rises)"
        )
    return out


def evidence_path(issue_id: str) -> str:
    """The one evidence path a row may carry, relative to the repository root."""
    return f"docs/evidence/{issue_id}.md"


@dataclass(frozen=True)
class Violation:
    id: str
    kind: str
    detail: str


def status_violations(
    issues: list[dict[str, Any]], exists: Callable[[str], bool]
) -> list[Violation]:
    """INT-396: a row's status and its `evidence:` key must agree.

    - a `todo` row carries no `evidence:` (evidence records delivered work);
    - a `done` row carries `evidence:`, and the file exists;
    - `evidence:` is the row's own `docs/evidence/<id>.md` and nothing else, so
      the path is never resolved outside that directory.
    `exists` takes a repository-relative path; tests inject it.
    """
    out: list[Violation] = []
    for issue in issues:
        iid = issue["id"]
        status = issue.get("status", "todo")
        evidence = issue.get("evidence")
        if evidence is not None and evidence != evidence_path(iid):
            out.append(Violation(iid, "evidence-path-not-own", f"evidence: {evidence}"))
            continue
        if status == "todo" and evidence is not None:
            out.append(Violation(iid, "todo-with-evidence", f"todo row carries {evidence}"))
        elif status == "done" and evidence is None:
            out.append(Violation(iid, "done-without-evidence", "done row has no evidence: key"))
        elif status == "done" and evidence is not None and not exists(evidence):
            out.append(Violation(iid, "evidence-file-missing", f"{evidence} does not exist"))
    return out


def load_issues(path: Path | None = None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = yaml.safe_load((path or ISSUES_FILE).read_text(encoding="utf-8"))
    return issues


def labels_for(issue: dict[str, Any]) -> list[str]:
    return [f"ph:{issue['phase']}", *issue.get("labels", [])]


def is_blocked(issue: dict[str, Any]) -> bool:
    return any(label.startswith("blocked:") for label in issue.get("labels", []))


def deps_satisfied(issue: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> bool:
    return all(
        by_id[dep].get("status", "todo") in DEP_SATISFIED_STATUSES
        for dep in issue.get("depends_on", [])
    )


def ready_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {i["id"]: i for i in issues}
    out = []
    for phase in PHASE_ORDER:
        for issue in issues:  # file order within the phase
            if issue["phase"] != phase:
                continue
            if issue.get("status", "todo") != "todo":
                continue
            if is_blocked(issue):
                continue
            if not deps_satisfied(issue, by_id):
                continue
            out.append(issue)
    return out


def awaiting_human(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in issues if i.get("status") == "awaiting-human"]


def blocked(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [i for i in issues if i.get("status") == "blocked" or is_blocked(i)]


def select_next(issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    ready = ready_issues(issues)
    return ready[0] if ready else None
