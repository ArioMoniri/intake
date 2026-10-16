"""INT-466: ADR-039, the chat stage, owner-ratified.

Acceptance (GitHub #795): the ADR is Accepted, quotes the owner, and bounds
each of the six approved items by number and surface. It records where
Apple's Liquid Glass guidance narrowed a request, and names the test that
pins each bound. files/00 §3 carries its D-row and docs/index.md registers
it. An approval that loses a bound becomes a licence, so every bound is
pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR_DIR = REPO / "docs" / "adr"
INDEX = REPO / "docs" / "index.md"
STATE = REPO / "files" / "00_STATE.md"
RESEARCH = REPO / "docs" / "design" / "liquid-glass-research.md"

OWNER_QUOTE = '"yes to all"'


def _adr() -> str:
    matches = sorted(ADR_DIR.glob("ADR-039-*.md"))
    assert matches, "missing ADR-039"
    assert len(matches) == 1, f"two files claim ADR-039: {matches}"
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
    assert "3 Oct 2026" in status.group(1)
    assert OWNER_QUOTE in text
    for section in ("## Context", "## Decision", "## Consequences"):
        assert section in text


def test_it_names_what_it_amends() -> None:
    text = _adr()
    amends = re.search(r"^Amends: (.+)$", text, re.M)
    assert amends is not None
    for adr in ("ADR-033", "ADR-037", "ADR-038"):
        assert adr in amends.group(1)
    assert "INT-422" in text


def test_s1_orb_motion_is_bounded() -> None:
    s1 = _section(_adr(), "### S1")
    for needle in (
        "1.06",
        "+10 %",
        "listening only",
        "3 s",
        "1.2 s",
        "Reduce Motion",
        "RED",
        "still",
        "0.2 Hz",
        "shared value",
        "never the only signal",
    ):
        assert needle in s1, f"S1 lost {needle!r}"


def test_s2_gradients_are_bounded() -> None:
    s2 = _section(_adr(), "### S2")
    for needle in ("backdrop", "orb", "`expo-linear-gradient` stays banned", "Reduce Transparency"):
        assert needle in s2, f"S2 lost {needle!r}"


def test_s3_glass_stays_on_the_control_layer() -> None:
    s3 = _section(_adr(), "### S3")
    for needle in (
        "control layer",
        "content layer",
        "answer cards",
        "never glass",
        "no glass on glass",
        "regular",
        "clear",
        "`GlassContainer`",
        "Reduce Transparency",
        "liquid-glass-research.md",
    ):
        assert needle in s3, f"S3 lost {needle!r}"


def test_s4_to_s6_are_bounded() -> None:
    text = _adr()
    s4 = _section(text, "### S4")
    assert "isInteractive" in s4 and "nothing else" in s4
    s5 = _section(text, "### S5")
    for needle in ("capsule", "22 pt", "12 pt"):
        assert needle in s5, f"S5 lost {needle!r}"
    s6 = _section(text, "### S6")
    for needle in ("lib/stage/palette.ts", "every stop", "never pure black", "RED"):
        assert needle in s6, f"S6 lost {needle!r}"


def test_s7_welcome_and_sign_in_are_bounded() -> None:
    """INT-464 (GitHub #793): the stage, still, on welcome and sign-in."""
    text = _adr()
    decision = _section(text, "## Decision")
    assert "S7" in decision.split("### S1")[0], "the decision line must name S7's reach"
    s7 = _section(text, "### S7")
    for needle in (
        "INT-464",
        "#793",
        OWNER_QUOTE,
        "welcome",
        "phone entry",
        "OTP",
        "still",
        "`stillOrb()`",
        "gate",
        "`interactive={false}`",
        "`stageFieldChrome`",
        "no resting outline",
        "Increase Contrast",
        "solid native bar",
        "back chevron",
        "grouped inset list",
        "consent screen",
        "No copy changes",
    ):
        assert needle in s7, f"S7 lost {needle!r}"
    table = _section(text, "## Where each bound is enforced")
    assert "authStage.spec.ts" in table and "field.test.ts" in table


def test_unchanged_list_holds_the_invariants() -> None:
    unchanged = _section(_adr(), "## Unchanged")
    for needle in ("RED", "haptic", "announce", "verbatim", "siz"):
        assert needle in unchanged, f"Unchanged lost {needle!r}"


def test_the_research_is_cited_and_exists() -> None:
    assert RESEARCH.exists()
    research = RESEARCH.read_text(encoding="utf-8")
    assert len(research.splitlines()) <= 60
    for url in (
        "https://developer.apple.com/design/human-interface-guidelines/materials",
        "https://developer.apple.com/documentation/swiftui/applying-liquid-glass-to-custom-views",
        "https://developer.apple.com/videos/play/wwdc2025/219/",
    ):
        assert url in research


def test_registered_in_the_index_and_the_state_file() -> None:
    assert "adr/ADR-039-" in INDEX.read_text(encoding="utf-8")
    state = STATE.read_text(encoding="utf-8")
    decisions = _section(state, "## 3. Decisions")
    row = next((line for line in decisions.splitlines() if line.startswith("| **D33**")), None)
    assert row is not None, "files/00 §3 has no D33 row"
    assert "ADR-039" in row and OWNER_QUOTE in row
