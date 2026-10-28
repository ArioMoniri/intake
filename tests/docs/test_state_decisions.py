"""INT-585: files/00_STATE.md §3 carries the owner's 28 Oct 2026 SMS decisions.

The decision table is the authority every SMS-hardening PR cites (D34-D38), so
each row must exist exactly once, say who decided and when, and name the issue
that carries it out. Ids in the table never repeat.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "files/00_STATE.md"
ROW = re.compile(r"^\| \*\*(D\d+)\*\* \|")

OWNER_28_OCT = {
    "D34": ("webcredentials:3-211-2-143.sslip.io", "INT-580"),
    "D35": ("push", "INT-583"),
    "D36": ("passkey", "INT-582"),
    "D37": ("1000", "INT-577"),
    "D38": ("OpenBao", "INT-584"),
}


def _rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in STATE.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            assert match.group(1) not in rows, f"{match.group(1)} appears twice"
            rows[match.group(1)] = line
    return rows


def _check(decision: str, row: str, fact: str, issue: str) -> None:
    assert "owner 28 Oct 2026" in row, f"{decision} must say who decided and when"
    assert fact in row, f"{decision} must state {fact!r}"
    assert issue in row, f"{decision} must name {issue}, the issue that carries it out"


def test_the_owner_sms_decisions_are_recorded_once_with_owner_date_and_issue() -> None:
    rows = _rows()
    for decision, (fact, issue) in OWNER_28_OCT.items():
        assert decision in rows, f"{decision} is missing from files/00_STATE.md §3"
        _check(decision, rows[decision], fact, issue)


def test_near_miss_a_decision_row_without_its_issue_is_refused() -> None:
    row = "| **D37** | **Daily cap 1000.** | ✅ **owner 28 Oct 2026** | no issue named |"
    assert ROW.match(row)
    try:
        _check("D37", row, "1000", "INT-577")
    except AssertionError as refused:
        assert "INT-577" in str(refused)
    else:
        raise AssertionError("a row that names no issue must be refused")
