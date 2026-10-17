"""INT-554 D7 — a late proxy binding never removes the RED its answers would fire.

GitHub #938, CD-01 round 4 (author revision after the verifier's D7 finding).
When ``identity_check.subject_role`` binds "yakınım adına" after chest-pain
answers were given, CD-01 invalidates them: they leave the patient's slots,
which read NOT_ASKED. The verifier's case: ``chest_pain.present`` and one
feature affirmed, the onset anchor never asked. Kept, those answers would let
CD-05's ``never_asked_at_close`` read the anchor as the reference day at close
and fire K2. Invalidated, the patient's slots fire nothing.

CD-01 now keeps them on the session's triage record (``answered_before_role_bound``)
and evaluates the rules under files/13 §11.2's worst-case union of the
patient's slots and those answers. This golden evaluates the two worlds
against the life-threat rules exactly as the golden suite does
(``triage_goldens_corpus``), and is read from the decision itself:

- the kept answers, closed as the patient's would have been, fire K2;
- the patient's slots alone fire nothing — the RED the union keeps;
- **near miss:** the same answers with no late binding are the patient's own,
  fire the same K2 at close, and raise no proxy item.

The answers are synthetic (files/04 §7). Not part of the counted corpus: the
runtime that invalidates and keeps them is engineering this decision lists.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from clinical_schemas.triage import RedLocation, TriageLevel
from protocols.clinical_decisions import load_register
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from protocols.types import EK4Level
from triage_goldens_corpus import C1, REF_TIME, TODAY, build_rule_sets, p
from triage_goldens_fixtures import chest


def _d7() -> Mapping[str, Any]:
    value = load_register()["CD-01"].value
    [item] = [
        entry
        for amendment in value["amendments"]
        if amendment["issue"].startswith("INT-554")
        for entry in amendment["items"]
        if entry["item"] == "D7"
    ]
    late: Mapping[str, Any] = item["answered_before_proxy_binding"]
    return late


def _closed_answers(given: Mapping[str, object]) -> dict[str, SlotAnswer]:
    """The answers as given, closed as CD-05 closes a never-asked anchor."""
    cd05 = load_register()["CD-05"].value["never_asked_at_close"]
    assert cd05["evaluated_as"] == "reference_day"
    assert given.get("chest_pain.present") is True  # CD-05's condition for the close reading
    answers = {ref: p(value) for ref, value in given.items()}
    return {**chest(p(TODAY)), **answers}


def _evaluate(answers: Mapping[str, SlotAnswer]) -> tuple[TriageLevel, EK4Level, frozenset[str]]:
    rules = build_rule_sets().sets["life"]
    evaluation = evaluate_triage(
        rules, TriageContext(reference_time=REF_TIME, answers=dict(answers)), RedLocation.REMOTE
    )
    fired = frozenset(fire.id for fire in evaluation.result.rules)
    return evaluation.result.level, evaluation.ek4, fired


def test_d7_the_decision_keeps_the_red_under_the_worst_case_union() -> None:
    late = _d7()
    assert late["answers"] == "invalidated" and late["slots_read"] == "NOT_ASKED"
    assert late["red_it_would_fire"] == "never_removed"
    assert late["evaluated_under"] == "worst_case_union"
    assert late["kept_as"] == late["red_label"] == "answered_before_role_bound"


def test_d7_golden_the_kept_answers_fire_k2_at_close_and_the_patient_slots_alone_do_not() -> None:
    golden = _d7()["golden"]
    assert golden["anchor"] == "never_asked" and golden["patient_slots"] == "NOT_ASKED"
    kept = _evaluate(_closed_answers(golden["answered_before_role_bound"]))
    patient_only = _evaluate({})
    # the worst-case union: if either world would fire a rule, the rule fires
    union_fires_red = TriageLevel.RED in (kept[0], patient_only[0])
    expected = (TriageLevel.RED, EK4Level[golden["level"]], frozenset(golden["fires_at_close"]))
    assert kept == expected
    assert golden["fires_at_close"] == [C1]
    # without the union the invalidation would remove that RED
    assert patient_only == (TriageLevel.GREEN, EK4Level.YESIL, frozenset())
    assert union_fires_red
    assert "proxy_chest_pain_screen_unasked" in golden["clinic_items"]


def test_d7_near_miss_the_same_answers_with_no_late_binding_fire_the_same_k2() -> None:
    golden = _d7()["golden"]
    near_miss = golden["near_miss"]
    assert near_miss["role_binds_before"] == "kendim için"
    assert near_miss["patient_slots"] == "the_same_answers"
    own = _evaluate(_closed_answers(golden["answered_before_role_bound"]))
    assert own == (
        TriageLevel.RED,
        EK4Level[near_miss["level"]],
        frozenset(near_miss["fires_at_close"]),
    )
    assert near_miss["proxy_item"] is False
