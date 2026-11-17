"""INT-518 — the engine's plan build re-checks gate values against the table.

INT-441 made the compiler refuse a gate that compares a code slot with a value
the slot cannot carry. The engine runs a :class:`ResolvedProtocol` it is
handed, and a document can reach it without passing ``protocols compile``:
the runtime and its tests build one directly. So the plan build runs the same
check (:func:`protocols.compile.gate_values.gate_value_refusals`) against the
value-set table it is given, and refuses at build. The compiler is not the
only gate.

Omitted, the table is empty: nothing is committed, so a gate on a code slot
is refused, which is the compiler's own reading (``resolve_protocol``). The
check only refuses. No gate is rewritten and no red-flag rule is read
(invariants 1 and 7).
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from intake_voice_runtime.clinical_agent import IntakeEngine, PlanError, build_plan
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.loader import load_pack
from protocols.types import Delivery
from protocols.valuesets import NO_VALUESETS, ValueSet, ValueSetTable, load_committed_valuesets

NOW = datetime.datetime(2026, 10, 16, 9, 0, tzinfo=datetime.UTC)
HASH = "0" * 64
BASE_INTAKE = (
    Path(__file__).resolve().parents[2] / "packages" / "protocols" / "base" / "intake.yaml"
)
PROXY = "identity_check.proxy_reported"
LMP = "pmh_fh_sh.lmp_date"
SCREEN = "chest_pain.present"


def _base_intake(**gates: tuple[str, str]) -> ResolvedProtocol:
    """``base.intake`` projected into the resolved shape (as test_bare_gates
    does); ``gates`` rewrites one slot's gate, ``"<section>__<key>": (field,
    text)``, for the near misses."""
    pack = load_pack(BASE_INTAKE)
    sections = []
    for section_id, section in pack.sections.items():
        slots = []
        for key, slot in section.slots.items():
            if slot.ask_tr is None:
                continue
            change = gates.get(f"{section_id}__{key}")
            authored: Slot = (
                slot if change is None else slot.model_copy(update={change[0]: change[1]})
            )
            slots.append(
                ResolvedSlot(
                    section_id=section_id,
                    key=key,
                    fhir_link_id=f"{section_id}.{key}",
                    slot=authored,
                    delivery=slot.delivery or section.delivery or Delivery.VOICE,
                )
            )
        sections.append(
            ResolvedSection(
                id=section_id,
                delivery=section.delivery or Delivery.VOICE,
                allow_paraphrase=False,
                slots=tuple(slots),
            )
        )
    return ResolvedProtocol(
        pack_id=pack.id,
        version=pack.version,
        chain=(pack.id,),
        sections=tuple(sections),
        resolved_protocol_hash=HASH,
    )


def _replaced(table: ValueSetTable, valueset_id: str, members: tuple[str, ...]) -> ValueSetTable:
    found = table.valuesets[valueset_id]
    changed = ValueSet(members=members, source=found.source)
    return table.model_copy(update={"valuesets": {**table.valuesets, valueset_id: changed}})


def test_base_intake_builds_against_the_committed_table() -> None:
    plan = build_plan(_base_intake(), load_committed_valuesets())
    assert {PROXY, LMP, SCREEN} <= set(plan.ask_gates) | set(plan.skip_gates)
    IntakeEngine(protocol=_base_intake(), reference_time=NOW, valuesets=load_committed_valuesets())


def test_omitted_the_table_is_empty_and_every_code_gate_is_refused() -> None:
    """The compiler's own reading of an omitted table (``resolve_protocol``)."""
    with pytest.raises(PlanError) as refused:
        IntakeEngine(protocol=_base_intake(), reference_time=NOW)
    message = str(refused.value)
    assert message.count("GATE_VALUESET_UNCOMMITTED") == 3
    for step in (PROXY, LMP, SCREEN):
        assert step in message
    with pytest.raises(PlanError, match="GATE_VALUESET_UNCOMMITTED"):
        build_plan(_base_intake(), NO_VALUESETS)


@pytest.mark.parametrize(
    "gate",
    [
        "subject_role != 'kendim'",
        "subject_role == 'kendim icin'",
        "subject_role == 'Yakınım adına'",
        "subject_role == 'yakınım adına '",
    ],
    ids=["prefix", "ascii-folded", "case", "trailing-space"],
)
def test_near_miss_a_gate_literal_outside_the_set_is_refused_at_build(gate: str) -> None:
    protocol = _base_intake(identity_check__proxy_reported=("ask_if", gate))
    with pytest.raises(PlanError, match=r"GATE_VALUE_OUTSIDE_VALUESET.*identity_check\."):
        build_plan(protocol, load_committed_valuesets())


def test_the_exact_member_builds() -> None:
    protocol = _base_intake(
        identity_check__proxy_reported=("ask_if", "subject_role == 'kendim için'")
    )
    assert PROXY in build_plan(protocol, load_committed_valuesets()).ask_gates


def test_near_miss_a_table_that_drifted_from_the_offered_choices_is_refused_at_build() -> None:
    """``baskı`` ASCII-folded in the table: the choice the patient is offered is
    no longer a member, so the binder and the screen disagree."""
    table = _replaced(
        load_committed_valuesets(),
        "vs.chest_pain_character",
        ("baski", "sıkışma", "ağırlık", "yanma", "başka bir his"),
    )
    with pytest.raises(PlanError, match=r"CHOICE_OUTSIDE_VALUESET.*chest_pain\.character"):
        IntakeEngine(protocol=_base_intake(), reference_time=NOW, valuesets=table)


def test_every_refusal_is_named_not_only_the_first() -> None:
    protocol = _base_intake(
        identity_check__proxy_reported=("ask_if", "subject_role != 'kendim'"),
        pmh_fh_sh__lmp_date=("ask_if", "pregnancy_status != 'hayir'"),
    )
    with pytest.raises(PlanError) as refused:
        build_plan(protocol, load_committed_valuesets())
    assert str(refused.value).count("GATE_VALUE_OUTSIDE_VALUESET") == 2
