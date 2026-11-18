"""INT-604 (ADR-043) — an exclusive "yok" can never suppress a red-flag rule.

The goldens run the two ACTIVE chest-pain rules of the served
``files/protocols/base.life_threat.yaml`` over ``chest_pain.radiation`` answered
as a multi-select set (base.intake: ``multiple: true``, ``yok`` exclusive):

- a set naming an arm fires the K2 cardiac RED;
- near miss: ``yok`` alone, everything else identical, does not fire it — the
  SARI sibling fires instead, which is the rule ``yok`` exists for;
- a set holding both reaches triage only if something bypassed the lanes and
  the binder. Triage reads it whole (the files/12 §7.3 union), so the arm still
  fires: no option, exclusive or not, ever removes a value triage was handed;
- the binder refuses that same set instead of trimming it, so the only path by
  which "yok" displaces a symptom is the patient clearing it on screen before
  submit (the lanes' ``toggleOption``; apps/mobile).

The served rules are read, never edited: red-flag semantics are unchanged and the
monotonicity of invariant 7 is untouched (no rule is added, removed or relaxed).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, TriageLevel
from protocols.choices import ChoiceSetRefused, bind_choice_set, submitted_set_answer
from protocols.compile.life_threat import load_life_threat_set
from protocols.dsl import RedFlagRule
from protocols.loader import load_pack
from protocols.triage import TriageContext, evaluate_triage
from protocols.triage.context import SlotAnswer
from protocols.types import RuleStatus
from protocols.valuesets import load_committed_valuesets

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
BASE_INTAKE = REPO / "packages" / "protocols" / "base" / "intake.yaml"
CARDIAC = "rf.chest_pain_cardiac_features"
NON_CARDIAC = "rf.chest_pain_no_cardiac_history"
REFERENCE = datetime.fromisoformat("2026-08-29T10:00:00+03:00")

#: Every other input of both rules, held so that ONLY radiation decides.
HELD: dict[str, bool | str] = {
    "chest_pain.present": True,
    "chest_pain.character": "başka bir his",
    "associated.diaphoresis": False,
    "associated.dyspnoea": False,
    "trauma.recent": False,
    "chest_pain.onset_at": "2026-08-29",
}


def _served() -> list[RedFlagRule]:
    return [
        entry.rule
        for entry in load_life_threat_set(LIFE_THREAT).rules
        if entry.rule.status is RuleStatus.ACTIVE
    ]


def _fired(radiation: list[str]) -> tuple[TriageLevel, set[str]]:
    answers = {
        ref: SlotAnswer(state=AnswerState.ASKED_PRESENT, values=(value,))
        for ref, value in HELD.items()
    }
    bound = submitted_set_answer(radiation)
    assert bound is not None
    answers["chest_pain.radiation"] = bound
    result = evaluate_triage(
        _served(), TriageContext(reference_time=REFERENCE, answers=answers), RedLocation.REMOTE
    ).result
    return result.level, {fire.id for fire in result.rules}


@pytest.mark.parametrize("radiation", [["kol"], ["omuz", "çene"], ["sırt", "boyun"]])
def test_a_named_cardiac_site_fires_the_red(radiation: list[str]) -> None:
    level, fired = _fired(radiation)
    assert level is TriageLevel.RED
    assert CARDIAC in fired


def test_near_miss_yok_alone_does_not_fire_the_red() -> None:
    level, fired = _fired(["yok"])
    assert CARDIAC not in fired
    assert level is not TriageLevel.RED
    assert NON_CARDIAC in fired


def test_near_miss_a_non_cardiac_site_alone_does_not_fire_the_red() -> None:
    level, fired = _fired(["omuz"])
    assert CARDIAC not in fired
    assert level is not TriageLevel.RED


@pytest.mark.parametrize("radiation", [["kol", "yok"], ["yok", "kol"]])
def test_a_set_holding_yok_beside_a_symptom_still_fires(radiation: list[str]) -> None:
    level, fired = _fired(radiation)
    assert level is TriageLevel.RED
    assert CARDIAC in fired


@pytest.mark.parametrize("radiation", [["kol", "yok"], ["yok", "kol"]])
def test_the_binder_refuses_that_set_rather_than_trim_it(radiation: list[str]) -> None:
    radiation_slot = load_pack(BASE_INTAKE).sections["chest_pain"].slots["radiation"]
    members = load_committed_valuesets().members(radiation_slot.valueset or "")
    assert members is not None
    with pytest.raises(ChoiceSetRefused):
        bind_choice_set(radiation_slot, radiation, members)
    # positive control: the symptom alone binds, whole
    assert bind_choice_set(radiation_slot, ["kol"], members).values == ("kol",)
