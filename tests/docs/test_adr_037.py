"""INT-451 — ADR-037, the owner-ratified press and glass amendment to ADR-033.

The owner approved ADR-037 in chat on 3 Oct 2026 ("approve ADR-037"); the
status flip lands with INT-451's PR (#771). Ratification makes the three
exceptions shippable; it does not answer the ClinicalAuthor's question, so
that one keeps its fail-closed default.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "adr" / "ADR-037-motion-amendment-press-and-glass-response.md"
INDEX = REPO / "docs" / "index.md"
STATE = REPO / "files" / "00_STATE.md"

OWNER_QUOTE = '"approve ADR-037"'


def _text() -> str:
    return ADR.read_text(encoding="utf-8")


def test_accepted_with_the_owner_quote() -> None:
    status = re.search(r"^Status:\s+(.+)$", _text(), re.M)
    assert status is not None
    assert status.group(1).startswith("Accepted"), status.group(1)
    assert OWNER_QUOTE in status.group(1)
    assert "3 Oct 2026" in status.group(1)


def test_the_bounds_survive_ratification() -> None:
    text = _text()
    for needle in ("0.97", "ζ = 1", "overshootClamping: true", "isInteractive", "headerLargeTitle"):
        assert needle in text, f"ADR-037 lost {needle!r}"


def test_the_clinical_question_stays_open_and_fails_closed() -> None:
    row = next(line for line in _text().splitlines() if line.startswith("| Q-37.2 |"))
    assert "every chip on an intake step is excluded" in row


def test_index_and_state_record_the_ratification() -> None:
    index = INDEX.read_text(encoding="utf-8")
    entry = next(line for line in index.splitlines() if "adr/ADR-037-" in line)
    assert "(Proposed)" not in entry
    assert "ratified by the owner, 3 Oct 2026" in entry
    state = STATE.read_text(encoding="utf-8")
    row = next((line for line in state.splitlines() if line.startswith("| **D22**")), None)
    assert row is not None, "files/00 §3 has no D22 row"
    assert "ADR-037" in row and OWNER_QUOTE in row
