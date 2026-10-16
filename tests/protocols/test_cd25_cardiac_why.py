"""INT-465 / CD-25: the chest-pain RED's why lines say the action and the service only.

HB-C12b (open for the physician of record) found that rf.chest_pain_cardiac_features
told the patient *"Anlattığınız belirtiler kalple ilgili olabilir"*. CLAUDE.md
invariant 2 forbids diagnosis language in patient copy. The REMOTE line also used
*"triyaj"*, which is above B1. CD-25 (D18: simulated patients only) replaces both
lines with CD-24's verified service-fact lines, and changes nothing else in the rule.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from protocols.clinical_decisions import REGISTER_DIR, load_decision
from protocols.compile.life_threat import load_life_threat_set
from protocols.generic_red import generic_red_strings, load_generic_red

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
GENERIC = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
CD25 = load_decision(REGISTER_DIR / "CD-25.yaml")
#: CD-24's own named condition words, plus the jargon the review found.
FORBIDDEN = ("kalp", "kalb", "inme", "kanama", "triyaj")


def _cardiac() -> object:
    [rule] = [
        e.rule
        for e in load_life_threat_set(LIFE_THREAT).rules
        if e.rule.id == "rf.chest_pain_cardiac_features"
    ]
    return rule


def test_the_cardiac_why_lines_are_cd25s_value() -> None:
    rule = _cardiac()
    assert rule.action is not None  # type: ignore[attr-defined]
    action = rule.action  # type: ignore[attr-defined]
    assert action.remote.why_tr == {"tr": CD25.value["why_tr"]["remote"]}
    assert action.on_site.why_tr == {"tr": CD25.value["why_tr"]["on_site"]}
    # The ON_SITE line does not carry the ambulance sentence: the patient is not travelling.
    assert "ambulans" not in action.on_site.why_tr["tr"]


def test_cd25_reuses_cd24s_verified_lines_verbatim() -> None:
    generic = load_generic_red(GENERIC)
    assert generic.action is not None
    assert CD25.value["why_tr"]["remote"] == generic.action.remote.why_tr["tr"]  # type: ignore[index]
    assert CD25.value["why_tr"]["on_site"] == generic.action.on_site.why_tr["tr"]  # type: ignore[index]


def test_no_served_red_line_names_a_condition_or_triyaj() -> None:
    rule = _cardiac()
    action = rule.action  # type: ignore[attr-defined]
    served = [
        action.remote.why_tr["tr"],
        action.on_site.why_tr["tr"],
        *generic_red_strings(load_generic_red(GENERIC)),
    ]
    for text in served:
        folded = text.casefold()
        assert not any(word in folded for word in FORBIDDEN), text


@pytest.mark.parametrize("location", ["remote", "on_site"])
def test_the_replaced_lines_are_the_near_miss(location: str) -> None:
    """The text CD-25 replaced fails the same check, so the check can fail."""
    replaced = CD25.value["replaced"][location].casefold()
    assert any(word in replaced for word in FORBIDDEN)


def test_hb_c12b_stays_open_for_the_physician() -> None:
    blockers = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
    [row] = [line for line in blockers.splitlines() if line.startswith("| **HB-C12b**")]
    assert "| **open" in row
    assert "CD-25" in row
