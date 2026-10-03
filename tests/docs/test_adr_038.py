"""INT-461 — ADR-038, the owner-ratified amendment to ADR-033.

Acceptance (GitHub #786): the ADR records the amendment as Accepted, quotes
the owner, and bounds each exception by number, surface and guard; files/00
§3 carries its D-row and docs/index.md registers it. An amendment that loses
a bound is worse than none, because the next screen issue would cite it as
permission, so every bound is pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
INDEX = REPO / "docs" / "index.md"
STATE = REPO / "files" / "00_STATE.md"

OWNER_QUOTE = '"yes approve 1-3"'


def _adr() -> str:
    matches = sorted(ADR_DIR.glob("ADR-038-*.md"))
    assert matches, "missing ADR-038"
    assert len(matches) == 1, f"two files claim ADR-038: {matches}"
    return matches[0].read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    rest = text[start + len(heading) :]
    end = re.search(r"^#{2,3} ", rest, re.M)
    return rest if end is None else rest[: end.start()]


def test_accepted_with_the_owner_quote_and_date() -> None:
    text = _adr()
    status = re.search(r"^Status:\s+(.+)$", text, re.M)
    assert status is not None
    assert status.group(1).startswith("Accepted"), status.group(1)
    assert OWNER_QUOTE in text
    assert "3 Oct 2026" in status.group(1)
    for section in ("## Context", "## Decision", "## Consequences"):
        assert section in text


def test_it_names_what_it_amends() -> None:
    text = _adr()
    assert re.search(r"^Amends: ADR-033", text, re.M)
    assert "ADR-037" in text


def test_a1_bubble_spring_is_bounded() -> None:
    a1 = _section(_adr(), "### A1")
    for needle in (
        "8 pt → 0",
        "stiffness 1500",
        "damping 77.5",
        "ζ = 1",
        "overshootClamping: true",
        "120 ms",
        "No scale",
        "Never on RED",
        "Reduce Motion",
        "`content` class",
    ):
        assert needle in a1, f"A1 lost {needle!r}"


def test_a2_haptics_are_bounded() -> None:
    a2 = _section(_adr(), "### A2")
    for needle in (
        "`intakeChip`",
        "`dialogueMic`",
        "`select`",
        "INT-340",
        "Never while a voice session is active",
        "microphone is hot",
        "Never on RED",
        "sticky suppression",
        "Validated instrument response options",
        "no warning, error or heavy member",
    ):
        assert needle in a2, f"A2 lost {needle!r}"


def test_a3_sheets_stay_under_the_red_root_layer() -> None:
    a3 = _section(_adr(), "### A3")
    for needle in (
        "inside the navigator container",
        "never a React Native `Modal`",
        "`formSheet`",
        "RED root layer",
        "paints above any open sheet",
        "privacy close and a RED close are instant",
        "zoom",
        "120 ms stack pin",
        "Reduce Motion",
    ):
        assert needle in a3, f"A3 lost {needle!r}"


def test_registered_in_the_index_and_the_state_file() -> None:
    assert "adr/ADR-038-" in INDEX.read_text(encoding="utf-8")
    state = STATE.read_text(encoding="utf-8")
    decisions = _section(state, "## 3. Decisions")
    row = next((line for line in decisions.splitlines() if line.startswith("| **D21**")), None)
    assert row is not None, "files/00 §3 has no D21 row"
    assert "ADR-038" in row and OWNER_QUOTE in row
