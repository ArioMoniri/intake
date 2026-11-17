"""INT-396 — a backlog row's status and its evidence agree.

Acceptance line under test, verbatim:
  "a backlog test fails when a row has an `evidence:` path but is `todo`, or is
   `done` without `evidence:` (near-miss controls)"

The rule is `backlog_lib.status_violations`, the same function
scripts/backlog/reconcile.py reports with, so this gate and the reconciler
cannot disagree about what a consistent row is.

There is no allow-list. INT-396 checked every `done` row and each one has an
evidence file, so none is exempt; a new exemption would be a new drift.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "backlog"))

from backlog_lib import load_issues, status_violations  # noqa: E402


def _exists(path: str) -> bool:
    return (REPO / path).is_file()


def _row(status: str | None, evidence: str | None = None, iid: str = "INT-901") -> dict[str, Any]:
    row: dict[str, Any] = {"id": iid}
    if status is not None:
        row["status"] = status
    if evidence is not None:
        row["evidence"] = evidence
    return row


def _kinds(rows: list[dict[str, Any]], exists: bool = True) -> list[str]:
    return [v.kind for v in status_violations(rows, lambda _path: exists)]


def test_every_backlog_row_is_consistent() -> None:
    violations = status_violations(load_issues(), _exists)
    assert violations == [], "\n".join(f"{v.id}: {v.kind} — {v.detail}" for v in violations)


def test_a_todo_row_with_evidence_fails() -> None:
    assert _kinds([_row("todo", "docs/evidence/INT-901.md")]) == ["todo-with-evidence"]


def test_a_row_with_no_status_is_todo_and_fails_with_evidence() -> None:
    # `status` defaults to `todo` everywhere else in scripts/backlog.
    assert _kinds([_row(None, "docs/evidence/INT-901.md")]) == ["todo-with-evidence"]


@pytest.mark.parametrize("status", ["doing", "awaiting-human", "blocked"])
def test_near_miss_evidence_on_a_non_todo_open_row_passes(status: str) -> None:
    # The rule names `todo` only: an awaiting-human row whose mechanism shipped
    # carries its evidence while the human half is open.
    assert _kinds([_row(status, "docs/evidence/INT-901.md")]) == []


def test_near_miss_todo_without_evidence_passes() -> None:
    assert _kinds([_row("todo")]) == []


def test_a_done_row_without_evidence_fails() -> None:
    assert _kinds([_row("done")]) == ["done-without-evidence"]


def test_a_done_row_whose_evidence_file_is_missing_fails() -> None:
    assert _kinds([_row("done", "docs/evidence/INT-901.md")], exists=False) == [
        "evidence-file-missing"
    ]


def test_near_miss_done_row_with_its_evidence_file_passes() -> None:
    assert _kinds([_row("done", "docs/evidence/INT-901.md")]) == []


@pytest.mark.parametrize(
    "path",
    [
        "docs/evidence/INT-902.md",  # another row's file
        "docs/evidence/../../pyproject.toml",  # a path that leaves docs/evidence
        "/etc/hosts",
    ],
)
def test_evidence_must_be_the_rows_own_file(path: str) -> None:
    assert _kinds([_row("done", path)]) == ["evidence-path-not-own"]
