"""Shared backlog logic: loading, readiness, selection (LOOP.md step 1).

Selection rules, from LOOP.md verbatim:
  "Select: first issue in file order (phase P0->P3) with `status: todo`, all
   `depends_on` satisfied, and no `blocked:*` label. `awaiting-human`
   SATISFIES a dependency for an issue that depends only on the non-gated part
   of it — this is deliberate, and without it 58 % of the backlog silently
   never becomes Ready."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[2]
ISSUES_FILE = REPO / "docs" / "backlog" / "issues.yaml"

PHASE_ORDER = ["P0", "P1", "P2", "P3"]
DEP_SATISFIED_STATUSES = {"done", "awaiting-human", "withdrawn"}


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
