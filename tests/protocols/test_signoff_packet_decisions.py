"""INT-448 — every #642 sign-off packet item has a decision record and a verdict.

The #642 packets (PR #642, commit 151cf34f) list 197 unique open items from the
verification trail. tests/fixtures/clinical/int448_signoff_items.json is that
list, keyed ``<trail doc>#L<line>`` at that commit. Owner decision D18 lets
agents resolve the CLINICAL part of each item for simulated-patient stress
testing; a part whose decider is the owner, the base owner or counsel is not
D18's and is recorded as an owner question, never decided.

Near misses: an item decided twice, an item missing, and an owner item
"decided" by an agent all fail here rather than pass quietly.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from protocols.clinical_decisions import VerifierVerdict, load_register

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "clinical" / "int448_signoff_items.json"
OUTCOMES = frozenset({"accept", "change", "reject", "owner_question", "draft_needs_source"})
NON_CLINICAL_DECIDERS = frozenset({"owner", "base owner"})


def _expected() -> dict[str, dict[str, Any]]:
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert document["count"] == len(document["items"]) == 197
    return {item["key"]: item for item in document["items"]}


def _recorded() -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for decision_id, decision in load_register().items():
        for entry in decision.value.get("items", ()):
            rows.append((decision_id, entry))
    return rows


def _non_clinical_only(deciders: list[str]) -> bool:
    return bool(deciders) and all(
        d in NON_CLINICAL_DECIDERS or d.startswith("HB-L") for d in deciders
    )


def test_every_packet_item_is_decided_exactly_once_in_its_decision() -> None:
    expected = _expected()
    recorded = _recorded()
    counts = Counter(entry["item"] for _, entry in recorded)
    assert sorted(k for k, n in counts.items() if n > 1) == [], "an item is decided twice"
    assert sorted(set(expected) - set(counts)) == [], "packet items with no decision"
    assert sorted(set(counts) - set(expected)) == [], "decisions for items no packet lists"
    for decision_id, entry in recorded:
        assert expected[entry["item"]]["decision_id"] == decision_id, entry["item"]


def test_every_outcome_is_one_the_packets_allow_and_says_what_it_rests_on() -> None:
    for decision_id, entry in _recorded():
        outcome = entry["outcome"]
        assert outcome in OUTCOMES, (decision_id, entry["item"])
        if outcome == "change":
            assert str(entry.get("change", "")).strip(), (decision_id, entry["item"])
        if outcome in {"accept", "change", "reject"}:
            assert entry.get("sources") or entry.get("spec_basis_ref"), entry["item"]


def test_no_agent_decides_what_only_the_owner_may() -> None:
    """D18 delegates clinical decisions only. An item whose only deciders are
    the owner, the base owner or counsel is an owner question; an item with
    both keeps its owner part as a question beside the clinical decision."""
    expected = _expected()
    for _, entry in _recorded():
        deciders = expected[entry["item"]]["deciders"]
        if _non_clinical_only(deciders):
            assert entry["outcome"] == "owner_question", entry["item"]
        elif set(deciders) & NON_CLINICAL_DECIDERS:
            assert str(entry.get("owner_part", "")).strip(), entry["item"]


@pytest.mark.parametrize("decision_id", [f"CD-10{n}" for n in range(7)])
def test_each_packet_decision_carries_an_independent_verdict(decision_id: str) -> None:
    decision = load_register()[decision_id]
    assert decision.verifier.verdict is not VerifierVerdict.PENDING, decision_id
