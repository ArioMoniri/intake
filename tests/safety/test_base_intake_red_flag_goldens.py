"""INT-619 — the base.intake red-flag goldens, executed (files/04 §8.2).

``every_rule_has_a_true_positive_and_a_near_miss_negative``: for each family whose
rule is active, the positive must fire at the rule's level and register and resolve
the expected location's action, and the near-miss negative — one attribute away —
must not fire. Each case is evaluated against the rule alone and against the whole
active set, so a sibling family that over-fires on the near miss is caught too.

Families still ``draft_needs_source`` keep ``executable: false`` with their
blocker, because a golden asserting an outcome for an unsigned trigger would
assert the judgment nobody has made.

SENTETİK TEST VERİSİ: every case is invented (files/04 §7).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from protocols.dsl import LocationAction, RedFlagRule, UnknownAction
from protocols.loader import load_pack
from protocols.triage.context import SlotAnswer, TriageContext
from protocols.triage.engine import evaluate_triage
from protocols.types import RuleStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
GOLDENS = REPO_ROOT / "tests" / "protocols" / "goldens" / "base" / "red_flag_families.yaml"
#: The session clock every golden is evaluated against (files/13 §9.2: a fold
#: input, never a wall clock). Dates in the goldens are relative to it.
REFERENCE_TIME = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)

_PACK = load_pack(BASE_INTAKE)
_RULES: dict[str, RedFlagRule] = {rule.id: rule for rule in _PACK.red_flags}
_ACTIVE: tuple[RedFlagRule, ...] = tuple(
    rule for rule in _PACK.red_flags if rule.status is RuleStatus.ACTIVE
)
_GOLDENS: dict[str, Any] = yaml.safe_load(GOLDENS.read_text(encoding="utf-8"))["families"]
_EXECUTABLE = [family for family, entry in _GOLDENS.items() if entry["executable"]]


def _context(answers: dict[str, Any]) -> TriageContext:
    slots: dict[str, SlotAnswer] = {}
    for ref, value in answers.items():
        state = AnswerState.ASKED_ABSENT if value is False else AnswerState.ASKED_PRESENT
        slots[ref] = SlotAnswer(state=state, values=(value,))
    return TriageContext(reference_time=REFERENCE_TIME, answers=slots)


def test_executable_goldens_are_exactly_the_active_rules() -> None:
    assert set(_EXECUTABLE) == {rule.id for rule in _ACTIVE}
    for family, entry in _GOLDENS.items():
        if not entry["executable"]:
            assert _RULES[family].status is RuleStatus.DRAFT_NEEDS_SOURCE, family
            assert "HB-" in entry["blocked_by"], family


@pytest.mark.parametrize("family", _EXECUTABLE)
def test_the_positive_fires_at_the_rules_level_register_and_location(family: str) -> None:
    case = _GOLDENS[family]["positive"]
    expect = case["expect"]
    location = RedLocation(expect.get("location", "REMOTE"))
    rule = _RULES[family]
    alone = evaluate_triage([rule], _context(case["answers"]), location)
    assert alone.ek4.value == expect["level"], family
    assert [fire.id for fire in alone.result.rules] == [family]
    if rule.level.is_red:
        assert alone.result.level is TriageLevel.RED
        assert alone.result.register is not None
        assert alone.result.register.value == expect["register"], family
        assert rule.action is not None
        if location is RedLocation.REMOTE:
            assert isinstance(alone.action, LocationAction)
            assert alone.action is rule.action.remote
        elif location is RedLocation.ON_SITE:
            assert alone.action is rule.action.on_site
        else:
            assert isinstance(alone.action, UnknownAction)
    else:
        assert alone.result.level is not TriageLevel.RED
        assert alone.action is None
    together = evaluate_triage(list(_ACTIVE), _context(case["answers"]), location)
    assert family in {fire.id for fire in together.result.rules}


@pytest.mark.parametrize("family", _EXECUTABLE)
def test_the_near_miss_negative_does_not_fire_alone_or_in_the_set(family: str) -> None:
    case = _GOLDENS[family]["near_miss_negative"]
    assert case["expect"] == {"fires": False}, family
    context = _context(case["answers"])
    alone = evaluate_triage([_RULES[family]], context, RedLocation.REMOTE)
    assert alone.result.rules == (), family
    assert alone.result.level is TriageLevel.GREEN
    together = evaluate_triage(list(_ACTIVE), context, RedLocation.REMOTE)
    assert family not in {fire.id for fire in together.result.rules}, family


@pytest.mark.parametrize("family", _EXECUTABLE)
def test_the_near_miss_differs_from_the_positive_by_one_named_attribute(family: str) -> None:
    """A distant negative tests nothing. The near miss keeps every answer of the
    positive but the attribute the gate turns on."""
    positive = _GOLDENS[family]["positive"]["answers"]
    negative = _GOLDENS[family]["near_miss_negative"]["answers"]
    changed = {
        ref for ref in positive.keys() | negative.keys() if positive.get(ref) != negative.get(ref)
    }
    assert len(changed) == 1, (family, changed)
    assert _GOLDENS[family]["near_miss_negative"]["why_it_is_a_near_miss"].strip()


def test_an_undated_symptom_never_fires() -> None:
    """files/12 §2.4: a tense-qualified rule cannot fire on an undated symptom.
    Every positive with its anchor removed reads Unknown and does not fire."""
    for family in _EXECUTABLE:
        rule = _RULES[family]
        answers = dict(_GOLDENS[family]["positive"]["answers"])
        answers.pop(rule.tense_anchor, None)
        result = evaluate_triage([rule], _context(answers), RedLocation.REMOTE)
        assert result.result.rules == (), family
