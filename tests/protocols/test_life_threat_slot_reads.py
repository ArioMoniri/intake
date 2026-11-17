"""INT-432 / HB-C6 — the active life-threat rules read slots a session can fill.

files/04 §8.2 gate ``no_rule_references_an_undeclared_slot``. The two active
chest-pain rules of ``base.life_threat`` read ``chest_pain.*``,
``associated.*`` and ``trauma.*`` — and until INT-432 ``base.intake``
declared none of them. A rule fires only on TRUE (files/12 §1.1); a read no
pack declares is never asked, so it reads Unknown for the whole session and
the rule can never fire. The golden suite could not see it, because its
answers are keyed by reference strings, not by the slots a patient answers.

This suite proves the opposite end: every read of an active rule is a slot
``base.intake`` declares, every literal the rule compares is an answer the
patient can actually give (a declared choice, or a boolean), every tense
anchor is a date, and the goldens — built ONLY from answers the declared
slots admit — fire and stay quiet where they must. The life-threat set
itself is not touched (invariant 7; nothing extends it, files/12 §1).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation
from protocols.clinical_decisions import DecisionStatus, load_register
from protocols.compile.life_threat import load_life_threat_set
from protocols.compile.rule_reads import rule_reads
from protocols.dsl import RedFlagRule, Slot
from protocols.loader import load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.locale_text import entry_for
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from protocols.triage.expr import (
    And,
    BoolRef,
    Compare,
    InSet,
    Lit,
    Not,
    Or,
    Ref,
    WhenNode,
    parse_when,
)
from protocols.types import EK4Level, RuleStatus, SlotType

REPO_ROOT = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"

C1 = "rf.chest_pain_cardiac_features"
C2 = "rf.chest_pain_no_cardiac_history"
SCREEN = "chest_pain.present"
OPENS_ON_YES = "chest_pain.present == true"
PROXY_CHOICE = "yakınım adına"
PROXY_SKIP = f"identity_check.subject_role == '{PROXY_CHOICE}'"
CARDIAC_CHARACTER = frozenset({"baskı", "sıkışma", "ağırlık"})

REF_TIME = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
TODAY = REF_TIME.date().isoformat()
THREE_DAYS_AGO = (REF_TIME.date() - timedelta(days=3)).isoformat()


def _rules() -> tuple[RedFlagRule, ...]:
    return tuple(entry.rule for entry in load_life_threat_set(LIFE_THREAT).rules)


def _active() -> tuple[RedFlagRule, ...]:
    return tuple(rule for rule in _rules() if rule.status is RuleStatus.ACTIVE)


def _declared() -> dict[str, Slot]:
    pack = load_pack(BASE_INTAKE)
    return {
        f"{section_id}.{key}": slot
        for section_id, section in pack.sections.items()
        for key, slot in section.slots.items()
    }


def _reads(rule: RedFlagRule) -> frozenset[str]:
    reads = rule_reads(rule)
    assert reads is not None and reads.parsed, rule.id
    return reads.all


def _choices(slot: Slot) -> tuple[str, ...]:
    return tuple(entry_for(slot.choices_tr, TR)) if slot.choices_tr is not None else ()


def _comparisons(node: WhenNode) -> Iterator[tuple[str, tuple[bool | Decimal | str, ...]]]:
    """Every (slot, literal values) pair a predicate compares."""
    if isinstance(node, BoolRef):
        yield node.ref.name, (True,)
    elif isinstance(node, InSet) and isinstance(node.operand, Ref):
        yield node.operand.name, tuple(element.value for element in node.elements)
    elif isinstance(node, Compare):
        pairs = ((node.left, node.right), (node.right, node.left))
        for ref, lit in pairs:
            if isinstance(ref, Ref) and isinstance(lit, Lit):
                yield ref.name, (lit.value,)
    elif isinstance(node, Not):
        yield from _comparisons(node.item)
    elif isinstance(node, (And, Or)):
        for item in node.items:
            yield from _comparisons(item)


# --- the gate ------------------------------------------------------------------


def test_the_two_chest_pain_rules_are_the_active_life_threat_rules() -> None:
    """The scope of HB-C6 as INT-432 resolves it. A new active rule joins
    the suite below automatically; this pin only says which two exist now."""
    assert {rule.id for rule in _active()} == {C1, C2}


@pytest.mark.parametrize("rule", _active(), ids=lambda rule: rule.id)
def test_no_active_life_threat_rule_reads_an_undeclared_slot(rule: RedFlagRule) -> None:
    missing = sorted(_reads(rule) - _declared().keys())
    assert not missing, f"{rule.id} reads slots base.intake never declares: {missing}"


def test_only_draft_rules_still_read_undeclared_slots() -> None:
    """The drafts (paediatric airway, crisis signposting) are not served and
    their content is blocked elsewhere (HB-C3, HB-C8); their reads stay
    undeclared on purpose rather than being guessed into base.intake."""
    declared = _declared().keys()
    for rule in _rules():
        if _reads(rule) - declared:
            assert rule.status is RuleStatus.DRAFT_NEEDS_SOURCE, rule.id


@pytest.mark.parametrize("rule", _active(), ids=lambda rule: rule.id)
def test_every_literal_a_rule_compares_is_an_answer_the_patient_can_give(
    rule: RedFlagRule,
) -> None:
    declared = _declared()
    for ref, literals in _comparisons(parse_when(rule.when)):
        slot = declared[ref]
        for literal in literals:
            if isinstance(literal, bool):
                assert slot.type is SlotType.BOOLEAN, f"{rule.id}: {ref}"
            else:
                assert slot.type is SlotType.CODE, f"{rule.id}: {ref}"
                assert literal in _choices(slot), f"{rule.id}: {ref} cannot answer {literal!r}"


@pytest.mark.parametrize("rule", _active(), ids=lambda rule: rule.id)
def test_every_tense_anchor_is_a_date(rule: RedFlagRule) -> None:
    """files/12 §2.4: a tense-qualified rule cannot fire on an undated symptom,
    and the engine reads an ISO date (protocols.triage.context.temporal_within)."""
    assert _declared()[rule.tense_anchor].type is SlotType.DATE


def test_the_screen_is_always_asked_and_every_other_read_opens_on_its_yes() -> None:
    """The screen costs every self-reporting patient one turn; the follow-ups
    cost a turn only after a yes. Asked any other way, either the rule cannot
    fire (the follow-ups never open) or every patient pays for six questions."""
    declared = _declared()
    screen = declared[SCREEN]
    assert screen.must_ask and screen.ask_if is None
    follow_ups = set().union(*(_reads(rule) for rule in _active())) - {SCREEN}
    for ref in sorted(follow_ups):
        assert declared[ref].ask_if == OPENS_ON_YES, ref
        assert declared[ref].skip_if is None, ref


def test_the_proxy_stop_gap_skips_only_the_screen_and_only_for_a_proxy() -> None:
    """CD-01 `proxy_until_dsl_selects_copy`: self-worded copy is never spoken
    in a proxy session, so the speaker's own chest pain cannot fill the
    patient's rule-gate slot. Near miss: the gate compares a value
    subject_role can actually carry — a literal no choice produces (the
    session's own `'kendim'` vs `'kendim için'` hazard) would never skip."""
    declared = _declared()
    assert declared[SCREEN].skip_if == PROXY_SKIP
    subject_role = declared["identity_check.subject_role"]
    assert PROXY_CHOICE in _choices(subject_role)
    assert "kendim için" in _choices(subject_role)


def test_cd01_carries_proxy_copy_for_every_slot_it_skips() -> None:
    """The stop-gap is a stop-gap: the proxy wording is decided and waiting
    for the DSL to select it, and it obeys the same patient-copy rules."""
    sections = load_register()["CD-01"].value["sections"]
    for section, slots in sections.items():
        for key, spec in slots.items():
            ask = spec["proxy_ask_tr"]
            assert "akınınız" in ask, f"{section}.{key}: the proxy ask names the relative"
            for field in ("proxy_ask_tr", "proxy_follow_up_tr"):
                text = spec[field]
                assert "Göğsünüz" not in text and "göğsünüz" not in text, f"{section}.{key}"
                assert text.count("?") == 1 and not any(c.isdigit() for c in text), field


def test_every_new_slot_is_patient_askable_turkish() -> None:
    declared = _declared()
    for ref in sorted(set().union(*(_reads(rule) for rule in _active()))):
        slot = declared[ref]
        assert slot.ask_tr is not None and slot.follow_up_tr is not None, ref
        if slot.type is SlotType.CODE:
            assert slot.valueset is not None and _choices(slot), ref


# --- goldens built only from answers the declared slots admit -------------------


def _answer(ref: str, value: bool | str) -> SlotAnswer:
    """ASKED_PRESENT / ASKED_ABSENT carrying a value the declared slot admits —
    a golden that needs a value no patient can give proves nothing."""
    slot = _declared()[ref]
    if slot.type is SlotType.BOOLEAN:
        assert isinstance(value, bool), ref
    elif slot.type is SlotType.CODE:
        assert value in _choices(slot), f"{ref}: {value!r} is not a declared choice"
    else:
        assert slot.type is SlotType.DATE and isinstance(value, str), ref
    state = AnswerState.ASKED_ABSENT if value is False else AnswerState.ASKED_PRESENT
    return SlotAnswer(state=state, values=(value,))


def _non_cardiac_character() -> str:
    options = [
        c for c in _choices(_declared()["chest_pain.character"]) if c not in CARDIAC_CHARACTER
    ]
    assert options, "the character question offers no non-cardiac answer"
    return options[0]


def _session(**overrides: bool | str) -> dict[str, SlotAnswer]:
    values: dict[str, bool | str] = {
        "chest_pain.present": True,
        "chest_pain.onset_at": TODAY,
        "chest_pain.character": _non_cardiac_character(),
        "chest_pain.radiation": "yok",
        "associated.diaphoresis": False,
        "associated.dyspnoea": False,
        "trauma.recent": False,
    }
    values.update({key.replace("__", "."): value for key, value in overrides.items()})
    return {ref: _answer(ref, value) for ref, value in values.items()}


def _fired(answers: dict[str, SlotAnswer]) -> tuple[set[str], EK4Level | None]:
    evaluation = evaluate_triage(
        _active(), TriageContext(reference_time=REF_TIME, answers=answers), RedLocation.REMOTE
    )
    return {fire.id for fire in evaluation.result.rules}, evaluation.ek4


def test_lt01p_pressure_radiating_to_the_arm_with_sweating_fires_kirmizi() -> None:
    fired, ek4 = _fired(
        _session(
            chest_pain__character="baskı", chest_pain__radiation="kol", associated__diaphoresis=True
        )
    )
    assert fired == {C1} and ek4 is EK4Level.KIRMIZI_K2


def test_lt01n_near_miss_three_days_of_non_cardiac_pain_fires_nothing() -> None:
    """Same slot, same region: non-cardiac character, no radiation, nothing
    associated, onset three days ago. Neither arm may fire."""
    fired, _ = _fired(_session(chest_pain__onset_at=THREE_DAYS_AGO))
    assert fired == set()


def test_lt02p_non_cardiac_pain_today_fires_the_sari_arm() -> None:
    fired, ek4 = _fired(_session())
    assert fired == {C2} and ek4 is EK4Level.SARI_K1


def test_lt02n_near_miss_the_same_pain_with_breathlessness_lands_kirmizi() -> None:
    """A negative that only said "C2 does not fire" would pass on a broken
    gate that fires nothing; this one asserts where the case lands."""
    fired, ek4 = _fired(_session(associated__dyspnoea=True))
    assert fired == {C1} and ek4 is EK4Level.KIRMIZI_K2


def test_a_no_to_the_screen_fires_nothing_and_opens_no_follow_up() -> None:
    answers = {SCREEN: _answer(SCREEN, False)}
    fired, _ = _fired(answers)
    assert fired == set()


def test_a_yes_with_the_follow_ups_unasked_fires_nothing() -> None:
    """Why the follow-ups must open on the yes: with only the screen
    answered, both rules read Unknown and stay silent (files/12 §1.1)."""
    fired, _ = _fired({SCREEN: _answer(SCREEN, True)})
    assert fired == set()


def test_naming_several_sites_is_contested_and_the_escalating_world_fires() -> None:
    """The radiation slot holds one value, but a patient may name several
    sites. The answer is CONTESTED carrying every named site, which triage
    reads in the escalating world (files/12 §7.3) — so a neck-and-arm answer
    fires the K2 arm. Near miss: neck alone (CD-01 finding F5) fires neither."""
    both = _session(chest_pain__character="baskı")
    both["chest_pain.radiation"] = SlotAnswer(state=AnswerState.CONTESTED, values=("boyun", "kol"))
    fired, ek4 = _fired(both)
    assert fired == {C1} and ek4 is EK4Level.KIRMIZI_K2
    neck_only = _session(chest_pain__radiation="boyun")
    fired, _ = _fired(neck_only)
    assert fired == set()


# --- the pack carries exactly what decision CD-01 decided ------------------------


def test_the_declared_slots_are_exactly_decision_cd01() -> None:
    """The copy in base.intake is CD-01's, verbatim: a later edit to either
    without the other is a change nobody verified (D18)."""
    decision = load_register()["CD-01"]
    assert decision.status is DecisionStatus.ACTIVE
    declared = _declared()
    decided = {
        f"{section}.{key}": spec
        for section, slots in decision.value["sections"].items()
        for key, spec in slots.items()
    }
    assert set(decided) == set().union(*(_reads(rule) for rule in _active()))
    for ref, spec in decided.items():
        slot = declared[ref]
        assert slot.type.value == spec["type"], ref
        assert slot.valueset == spec["valueset"], ref
        assert slot.ask_tr is not None and slot.follow_up_tr is not None, ref
        assert entry_for(slot.ask_tr, TR) == spec["ask_tr"], ref
        assert entry_for(slot.follow_up_tr, TR) == spec["follow_up_tr"], ref
        assert list(_choices(slot)) == list(spec["choices_tr"]), ref
        assert slot.ask_if == spec["ask_if"], ref
        assert (slot.must_ask, slot.required) == (spec["must_ask"], spec["required"]), ref
