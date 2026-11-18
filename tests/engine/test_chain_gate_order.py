"""INT-353 — a gate that reads a slot merged after it, run through a real IntakeEngine.

The PR #582 review (docs/evidence/verification/sibling-rebinds-582.md §A) found four
gates in the kadın hastalıkları ve doğum chain that read ``gebelik_durumu``, a branch
slot, from four slots the branch re-declares with cluster ids. The resolver's
``_merge_chain`` keeps a re-declared id at the parent's position, so the four gated
questions sit before their gate slot in the merged plan.

What the engine does with that (files/13 §9.2, §9.5): the frontier re-reads every gate
on every call, and an unanswered gate slot reads Unknown, which does not open a gate.
So each gated question is passed over at its own plan position, and it is asked only
after ``gebelik_durumu`` is answered — deferred, not dropped. The defect is the order:
the patient is not asked in the frozen order ``(priority_class, order, id)`` the plan
declares (files/13 §9.1, §9.6), which files/13 §9.5's stratified-acyclicity check
forbids ("a gate on step S may reference only slots owned by steps of strictly lower
(priority, order)").

The chain is merged by the resolver's own ``_merge_chain`` and ``_apply_ops``, from the
committed review candidates. ``resolve_protocol`` itself refuses an L0 pack, and
``build_plan`` refuses base's red-flag probe and instrument slots, which carry no
``ask_tr`` until HB-C1 (cluster-wave-a §A-2), so those two base sections are left out.
No other section is touched. Every answer is synthetic (files/04 §7); no triage level
is produced anywhere here (CLAUDE.md invariant 1).
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from pathlib import Path

from clinical_schemas.common import JsonValue
from intake_voice_runtime.clinical_agent import IntakeEngine, build_plan
from protocols.compile.resolve import (
    ResolvedProtocol,
    ResolvedSection,
    ResolvedSlot,
    _apply_ops,
    _merge_chain,
    _ordered_ops,
)
from protocols.loader import load_pack
from protocols.types import Delivery, SlotType

NOW = datetime.datetime(2026, 9, 27, 9, 0, tzinfo=datetime.UTC)
PROTOCOLS = Path(__file__).resolve().parents[2] / "packages" / "protocols"
SLUG = "kadin_hastaliklari_ve_dogum"
GATE = "sorular.gebelik_durumu"
GATED = (
    "sorular.gebelikte_kanama",
    "sorular.bebek_hareketlerinde_azalma",
    "sorular.gebelikte_siddetli_bas_agrisi",
    "sorular.gebelikte_gorme_bozuklugu",
    "sorular.gebelikte_su_gelmesi",
)


def _chain_protocol(slug: str) -> ResolvedProtocol:
    """The review chain base → cluster → branch, merged as the resolver merges it."""
    branch = load_pack(PROTOCOLS / "review" / "specialty" / f"{slug}.yaml")
    assert branch.extends is not None
    cluster = load_pack(
        PROTOCOLS / "review" / "cluster" / f"{branch.extends.removeprefix('cluster.')}.yaml"
    )
    chain = [load_pack(PROTOCOLS / "base" / "intake.yaml"), cluster, branch]
    merged = _merge_chain(chain)
    assert _apply_ops(merged, _ordered_ops(chain), "tr") == []
    sections = tuple(
        ResolvedSection(
            id=section_id,
            delivery=Delivery.VOICE,
            allow_paraphrase=False,
            slots=tuple(
                ResolvedSlot(
                    section_id=section_id,
                    key=key,
                    fhir_link_id=f"{section_id}.{key}",
                    slot=slot,
                    delivery=slot.delivery or Delivery.VOICE,
                )
                for key, slot in state.slots.items()
            ),
        )
        for section_id, state in merged.items()
        if all(slot.ask_tr is not None for slot in state.slots.values())
    )
    return ResolvedProtocol(
        pack_id=branch.id,
        version=branch.version,
        chain=tuple(pack.id for pack in chain),
        sections=sections,
        resolved_protocol_hash="0" * 64,
    )


def _interview(protocol: ResolvedProtocol, answers: Mapping[str, JsonValue]) -> list[str]:
    """Ask the frontier head, answer it, repeat — no ask-ahead, no clarification.

    ``answers`` is keyed by slot key; every other boolean is answered "hayır" and
    every other slot with a synthetic string.
    """
    types = {
        f"{section.id}.{resolved.key}": resolved.slot.type
        for section in protocol.sections
        for resolved in section.slots
    }
    engine = IntakeEngine(protocol=protocol, reference_time=NOW)
    asked: list[str] = []
    while (head := engine.next_step()) is not None:
        step_id = head.step_id
        assert step_id not in asked, f"{step_id} offered twice"
        key = step_id.rsplit(".", 1)[1]
        default: JsonValue = False if types[step_id] is SlotType.BOOLEAN else "sentetik"
        engine.mark_asked(step_id)
        engine.apply_extraction(step_id, {step_id: answers.get(key, default)})
        asked.append(step_id)
    return asked


MAY_BE_PREGNANT: dict[str, JsonValue] = {
    "subject_role": "kendim",
    "pregnancy_status": "evet",
    "gebelik_durumu": True,
}


def test_every_gated_pregnancy_question_is_asked_once_its_gate_slot_is_answered() -> None:
    """Engine semantics: a gate on a later slot defers its question, it does not drop it."""
    asked = _interview(_chain_protocol(SLUG), MAY_BE_PREGNANT)
    for step_id in GATED:
        assert asked.count(step_id) == 1, f"{step_id} was not asked"
        assert asked.index(step_id) > asked.index(GATE), f"{step_id} asked before its gate"


def test_the_chain_is_asked_in_the_frozen_order_its_plan_declares() -> None:
    """files/13 §9.1 and §9.6: the asked order is the plan's ``(priority, order)``.

    A gated step whose gate slot sorts after it cannot be asked at its own position;
    the engine asks it once the gate opens, out of the frozen order.
    """
    protocol = _chain_protocol(SLUG)
    key = {step.step_id: step.sort_key[:2] for step in build_plan(protocol).steps}
    asked = _interview(protocol, MAY_BE_PREGNANT)
    late = [
        f"{step_id} (plan {key[step_id]}) asked after {ahead} (plan {key[ahead]})"
        for position, step_id in enumerate(asked)
        if position and key[step_id] < key[(ahead := max(asked[:position], key=key.__getitem__))]
    ]
    assert late == []


def test_a_closed_pregnancy_gate_asks_none_of_its_questions() -> None:
    """Near-miss control: "hayır" to the gate slot keeps all five gated questions shut."""
    answers: dict[str, JsonValue] = {**MAY_BE_PREGNANT, "gebelik_durumu": False}
    asked = _interview(_chain_protocol(SLUG), answers)
    assert GATE in asked
    assert [step_id for step_id in GATED if step_id in asked] == []
