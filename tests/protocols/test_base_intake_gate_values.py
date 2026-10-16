"""INT-441 — base.intake's gates compare code slots against values the slots carry.

``identity_check.proxy_reported`` compared ``subject_role`` against
``'kendim'`` and ``pmh_fh_sh.lmp_date`` compared ``pregnancy_status`` against
``'hayir'``; neither literal is an answer the slot offers. This module reads
the committed pack and the committed value sets: every literal a gate
compares against a code slot is an authored ``tr`` choice, the pre-fix
spellings are refused (the near misses), each committed value set is exactly
the choices of a slot that uses it, and both gates project to a FHIR
``enableWhen``. The compiler mechanics are pinned in ``test_gate_values.py``.
"""

from __future__ import annotations

from pathlib import Path

from protocols.compile import RefusalCode
from protocols.compile.emit_fhir import questionnaire
from protocols.compile.gate_values import code_gate_comparisons, gate_value_refusals
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.loader import load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.types import Delivery, SlotType
from protocols.valuesets import VALUESETS_PATH, load_valuesets

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
COMMITTED = REPO_ROOT / VALUESETS_PATH


def _base_entries(**gates: tuple[str, str]) -> list[tuple[str, str, Slot]]:
    """base.intake's slots as ``(section, key, slot)``; ``gates`` rewrites one
    slot's gate, ``"<section>__<key>": (field, text)``, for the near misses."""
    pack = load_pack(BASE_INTAKE)
    entries = []
    for section_id, section in pack.sections.items():
        for key, slot in section.slots.items():
            change = gates.get(f"{section_id}__{key}")
            if change is not None:
                slot = slot.model_copy(update={change[0]: change[1]})
            entries.append((section_id, key, slot))
    return entries


def test_every_code_slot_gate_literal_in_base_intake_is_an_authored_choice() -> None:
    entries = _base_entries()
    choices = {
        f"{section_id}.{key}": slot.choices_tr[TR]
        for section_id, key, slot in entries
        if slot.type is SlotType.CODE and slot.choices_tr is not None
    }
    comparisons = code_gate_comparisons(entries)
    assert {c.step for c in comparisons} == {
        "identity_check.proxy_reported",
        "chest_pain.present",
        "pmh_fh_sh.lmp_date",
    }
    for comparison in comparisons:
        assert comparison.literal in choices[comparison.target], comparison


def test_base_intake_passes_the_check_against_the_committed_value_sets() -> None:
    assert gate_value_refusals(_base_entries(), load_valuesets(COMMITTED)) == []


def test_near_miss_the_pre_fix_base_intake_spellings_are_refused() -> None:
    entries = _base_entries(
        identity_check__proxy_reported=("ask_if", "subject_role != 'kendim'"),
        pmh_fh_sh__lmp_date=("ask_if", "pregnancy_status != 'hayir'"),
    )
    refusals = gate_value_refusals(entries, load_valuesets(COMMITTED))
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.GATE_VALUE_OUTSIDE_VALUESET, "identity_check.proxy_reported"),
        (RefusalCode.GATE_VALUE_OUTSIDE_VALUESET, "pmh_fh_sh.lmp_date"),
    ]


def test_every_committed_value_set_is_exactly_the_choices_of_a_slot_that_uses_it() -> None:
    """The members are the authored choices, copied, never a new decision: a
    value set no committed slot uses, or one that differs from the choices
    its slot offers, is a value nobody authored."""
    table = load_valuesets(COMMITTED)
    users = {
        slot.valueset: slot.choices_tr[TR]
        for path in (BASE_INTAKE,)
        for section in load_pack(path).sections.values()
        for slot in section.slots.values()
        if slot.type is SlotType.CODE
        and slot.valueset in table.valuesets
        and slot.choices_tr is not None
    }
    assert set(users) == set(table.valuesets)
    for valueset_id, choices in users.items():
        assert table.members(valueset_id) == choices


def _base_document() -> ResolvedProtocol:
    pack = load_pack(BASE_INTAKE)
    sections = tuple(
        ResolvedSection(
            id=section_id,
            delivery=section.delivery or Delivery.VOICE,
            allow_paraphrase=False,
            slots=tuple(
                ResolvedSlot(
                    section_id=section_id,
                    key=key,
                    fhir_link_id=f"{section_id}.{key}",
                    slot=slot,
                    delivery=slot.delivery or section.delivery or Delivery.VOICE,
                )
                for key, slot in section.slots.items()
            ),
        )
        for section_id, section in pack.sections.items()
    )
    return ResolvedProtocol(
        pack_id=pack.id,
        version=pack.version,
        chain=(pack.id,),
        sections=sections,
        resolved_protocol_hash="0" * 64,
    )


def test_both_base_intake_gates_project_to_a_fhir_enable_when() -> None:
    doc, refusals = questionnaire(_base_document(), {})
    items = {item["linkId"]: item for group in doc["item"] for item in group["item"]}
    assert [r for r in refusals if r.subject in items] == []
    proxy = items["identity_check.proxy_reported"]
    assert proxy["enableBehavior"] == "all"
    assert proxy["enableWhen"] == [
        {
            "question": "identity_check.subject_role",
            "operator": "=",
            "answerString": "yakınım adına",
        }
    ]
    lmp = items["pmh_fh_sh.lmp_date"]
    assert lmp["enableBehavior"] == "any"
    assert lmp["enableWhen"] == [
        {"question": "pmh_fh_sh.pregnancy_status", "operator": "=", "answerString": choice}
        for choice in ("evet", "hayır", "emin değilim")
    ]
