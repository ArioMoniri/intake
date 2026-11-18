"""INT-604 (ADR-043) — an exclusive multi-select option in the protocol DSL.

What this file pins, layer by layer:

- **Schema** (``protocols.dsl.Slot``): ``multiple: true`` is a code slot only;
  ``options: {<member>: {exclusive: true}}`` is refused on a single-select slot,
  and a slot may declare at most one exclusive option.
- **Compiler** (``protocols.compile.choice_options``): an option key must be a
  member of the slot's committed value set, and every "yok"/"hiçbiri" choice
  of a multi-select slot must be declared exclusive, so the patient cannot
  hold "yok" beside a symptom. Each refusal has its near miss.
- **Binding** (``protocols.choices.bind_choice_set``): the server binds a
  submitted set exactly as submitted. A set holding the exclusive option and
  another one is refused, never trimmed, so no symptom is dropped after the
  patient submitted it.
- **Served-candidate pack**: base.intake's ``chest_pain.radiation`` — the input
  of both active chest-pain rules — is multi-select with ``yok`` exclusive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.session import AnswerState
from protocols.bindings import OperationalTemplate
from protocols.choices import ChoiceSetRefused, bind_choice_set, submitted_set_answer
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    RefusalCode,
    resolve_protocol,
)
from protocols.compile.choice_options import NONE_WORDS, choice_option_refusals
from protocols.dsl import ChoiceOption, Section, Slot
from protocols.loader import PackRegistry, load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.pack import ProtocolPack
from protocols.types import Maturity, PackLayer, SlotType
from protocols.valuesets import ValueSetTable, load_committed_valuesets
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
DEFERRED = "leaf-node binding awaits an openEHR informatician (INT-032, P3)"
VS = "vs.sentetik_yayilim"
MEMBERS = ("kol", "çene", "sırt", "yok")


def _table(members: tuple[str, ...] = MEMBERS) -> ValueSetTable:
    return ValueSetTable.model_validate(
        {
            "kind": "valueset_table",
            "valuesets": {VS: {"members": list(members), "source": "sentetik"}},
        }
    )


def _slot(**overrides: Any) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.CODE,
        "valueset": VS,
        "ask_tr": {TR: "Sentetik soru."},
        "choices_tr": {TR: MEMBERS},
        "openehr_deferred_reason": DEFERRED,
    }
    payload.update(overrides)
    return Slot(**payload)


EXCLUSIVE_YOK = {"yok": ChoiceOption(exclusive=True)}


# --- schema ---------------------------------------------------------------------


def test_a_multi_select_slot_may_declare_one_exclusive_option() -> None:
    slot = _slot(multiple=True, options=EXCLUSIVE_YOK)
    assert slot.multiple is True
    assert slot.exclusive_choices() == ("yok",)


def test_exclusive_on_a_single_select_slot_is_refused() -> None:
    with pytest.raises(ValidationError, match="single-select"):
        _slot(options=EXCLUSIVE_YOK)


def test_near_miss_a_non_exclusive_option_on_a_single_select_slot_is_accepted() -> None:
    slot = _slot(options={"yok": ChoiceOption(exclusive=False)})
    assert slot.exclusive_choices() == ()


def test_two_exclusive_options_in_one_question_are_refused() -> None:
    with pytest.raises(ValidationError, match="one exclusive option"):
        _slot(
            multiple=True,
            options={"yok": ChoiceOption(exclusive=True), "sırt": ChoiceOption(exclusive=True)},
        )


@pytest.mark.parametrize("slot_type", [SlotType.BOOLEAN, SlotType.STRING])
def test_multiple_and_options_belong_to_code_slots_only(slot_type: SlotType) -> None:
    with pytest.raises(ValidationError, match="code slot"):
        Slot(type=slot_type, multiple=True, openehr_deferred_reason=DEFERRED)
    with pytest.raises(ValidationError, match="code slot"):
        Slot(type=slot_type, options=EXCLUSIVE_YOK, openehr_deferred_reason=DEFERRED)


def test_the_yaml_spelling_loads() -> None:
    slot = Slot.model_validate(
        {
            "type": "code",
            "valueset": VS,
            "multiple": True,
            "options": {"yok": {"exclusive": True}},
            "openehr_deferred_reason": DEFERRED,
        }
    )
    assert slot.exclusive_choices() == ("yok",)


# --- compiler ---------------------------------------------------------------------


def _entries(slot: Slot) -> list[tuple[str, str, Slot]]:
    return [("bolum", "yayilim", slot)]


def test_a_marked_none_choice_compiles() -> None:
    assert (
        choice_option_refusals(_entries(_slot(multiple=True, options=EXCLUSIVE_YOK)), _table())
        == []
    )


@pytest.mark.parametrize("none_word", ["yok", "Yok", "YOK", "hiçbiri", "Hiçbiri", "HİÇBİRİ"])
def test_an_unmarked_none_choice_on_a_multi_select_slot_is_refused(none_word: str) -> None:
    members = ("kol", "çene", none_word)
    slot = _slot(multiple=True, choices_tr={TR: members})
    refusals = choice_option_refusals(_entries(slot), _table(members))
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.NONE_CHOICE_NOT_EXCLUSIVE, "bolum.yayilim")
    ]
    assert repr(none_word) in refusals[0].message


def test_near_miss_an_unmarked_none_choice_on_a_single_select_slot_compiles() -> None:
    # A single-select slot cannot hold "yok" beside anything; nothing to clear.
    assert choice_option_refusals(_entries(_slot()), _table()) == []


def test_near_miss_a_choice_that_only_contains_yok_is_not_a_none_word() -> None:
    members = ("sabahları", "belli bir saati yok")
    slot = _slot(multiple=True, choices_tr={TR: members})
    assert choice_option_refusals(_entries(slot), _table(members)) == []
    assert "belli bir saati yok" not in NONE_WORDS


def test_an_option_naming_no_member_is_refused() -> None:
    slot = _slot(multiple=True, options={"hiçbiri": ChoiceOption(exclusive=True)})
    refusals = choice_option_refusals(_entries(slot), _table())
    codes = [r.code for r in refusals]
    assert RefusalCode.OPTION_OUTSIDE_CHOICES in codes


def _pack(slot: Slot) -> ProtocolPack:
    return ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": "base.sentetik_secim",
            "layer": PackLayer.BASE,
            "version": "1.0.0",
            "schema_version": 2,
            "maturity": Maturity.L1,
            "status": "clinically-reviewed-synthetic",
            "language": "tr",
            "sections": {"bolum": Section(slots={"yayilim": slot})},
        }
    )


def test_the_resolver_runs_the_check(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = PackRegistry()
    registry.add(_pack(_slot(multiple=True)))
    with pytest.raises(CompileError) as caught:
        resolve_protocol(
            pack_id="base.sentetik_secim",
            registry=registry,
            life_threat=life_threat,
            template=template,
            valuesets=_table(),
        )
    assert RefusalCode.NONE_CHOICE_NOT_EXCLUSIVE in {r.code for r in caught.value.refusals}


# --- binding ------------------------------------------------------------------------


MULTI = _slot(multiple=True, options=EXCLUSIVE_YOK)


def test_a_symptom_set_binds_as_every_member() -> None:
    answer = bind_choice_set(MULTI, ["kol", "sırt"], MEMBERS)
    assert answer.state is AnswerState.CONTESTED
    assert answer.values == ("kol", "sırt")


def test_the_exclusive_option_alone_binds() -> None:
    answer = bind_choice_set(MULTI, ["yok"], MEMBERS)
    assert answer.state is AnswerState.ASKED_PRESENT
    assert answer.values == ("yok",)


@pytest.mark.parametrize("values", [["kol", "yok"], ["yok", "kol"]])
def test_exclusive_beside_a_symptom_is_refused_never_trimmed(values: list[str]) -> None:
    with pytest.raises(ChoiceSetRefused, match="exclusive"):
        bind_choice_set(MULTI, values, MEMBERS)


def test_near_miss_two_symptoms_without_the_exclusive_bind() -> None:
    assert bind_choice_set(MULTI, ["kol", "çene"], MEMBERS).values == ("kol", "çene")


@pytest.mark.parametrize(
    ("slot", "values", "match"),
    [
        (MULTI, [], "empty"),
        (MULTI, ["omuz"], "member"),
        (_slot(), ["kol", "çene"], "single-select"),
    ],
)
def test_other_shapes_are_refused(slot: Slot, values: list[str], match: str) -> None:
    with pytest.raises(ChoiceSetRefused, match=match):
        bind_choice_set(slot, values, MEMBERS)


def test_a_repeated_member_is_one_member() -> None:
    assert bind_choice_set(MULTI, ["kol", "kol"], MEMBERS).values == ("kol",)


def test_a_submitted_set_is_read_whole() -> None:
    assert submitted_set_answer([]) is None
    single = submitted_set_answer(["kol"])
    assert single is not None
    assert single.values == ("kol",)
    union = submitted_set_answer(["kol", "yok", "kol"])
    assert union is not None
    assert union.state is AnswerState.CONTESTED
    assert union.values == ("kol", "yok")


# --- the served-candidate pack --------------------------------------------------------


def test_base_intake_radiation_is_multi_select_with_yok_exclusive() -> None:
    pack = load_pack(BASE_INTAKE)
    radiation = pack.sections["chest_pain"].slots["radiation"]
    assert radiation.multiple is True
    assert radiation.exclusive_choices() == ("yok",)


def test_every_base_intake_slot_passes_the_none_word_check() -> None:
    pack = load_pack(BASE_INTAKE)
    entries = [
        (section_id, key, slot)
        for section_id, section in pack.sections.items()
        for key, slot in section.slots.items()
    ]
    assert choice_option_refusals(entries, load_committed_valuesets()) == []


def test_non_code_slots_are_outside_both_checks() -> None:
    boolean = Slot(type=SlotType.BOOLEAN, openehr_deferred_reason=DEFERRED)
    assert choice_option_refusals([("bolum", "var_mi", boolean)], _table()) == []
    with pytest.raises(ChoiceSetRefused, match="code slot"):
        bind_choice_set(boolean, ["evet"], ("evet",))


def test_a_multi_select_slot_without_tr_choices_has_nothing_to_mark() -> None:
    slot = _slot(multiple=True, choices_tr=None)
    assert choice_option_refusals(_entries(slot), _table()) == []
