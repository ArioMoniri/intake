"""INT-375 — the compiler's "later" is the engine's "later".

The compiler refuses a gate that reads a slot of equal or higher ask rank
(:func:`protocols.gates.gates_reading_later_slots`, files/13 §9.5). That rank is
only worth enforcing if it is the order the engine actually asks in, so this
module pins the two against each other: the rank the compiler computes for every
slot is the ``(priority_class, order)`` of the step :func:`build_plan` makes of
it, and a document the check passes is asked in plan order while one it refuses
is asked out of it — the gated question passed over at its place and asked once
the later slot is answered.

Synthetic ids and strings throughout (files/04 §7). No triage level is produced
anywhere here (CLAUDE.md invariant 1).
"""

from __future__ import annotations

import datetime

from intake_voice_runtime.clinical_agent import IntakeEngine, build_plan
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.gates import ask_ranks, gates_reading_later_slots
from protocols.types import Delivery, SlotType

NOW = datetime.datetime(2026, 9, 27, 9, 0, tzinfo=datetime.UTC)


def _slot(*, must_ask: bool = False, ask_if: str | None = None) -> Slot:
    return Slot.model_validate(
        {
            "type": SlotType.BOOLEAN,
            "must_ask": must_ask,
            "ask_if": ask_if,
            "ask_tr": {"tr": "Sentetik soru mu?"},
        }
    )


def _protocol(*sections: tuple[str, tuple[tuple[str, Slot], ...]]) -> ResolvedProtocol:
    return ResolvedProtocol(
        pack_id="specialty.sentetik_sira",
        version="1.0.0",
        chain=("base.sentetik_sira", "specialty.sentetik_sira"),
        sections=tuple(
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
                        delivery=Delivery.VOICE,
                    )
                    for key, slot in slots
                ),
            )
            for section_id, slots in sections
        ),
        resolved_protocol_hash="0" * 64,
    )


def _rows(protocol: ResolvedProtocol) -> tuple[tuple[str, str, Slot], ...]:
    return tuple(
        (section.id, resolved.key, resolved.slot)
        for section in protocol.sections
        for resolved in section.slots
    )


def _asked(protocol: ResolvedProtocol) -> list[str]:
    """Interview to the end, answering every question ``true``."""
    engine = IntakeEngine(protocol=protocol, reference_time=NOW)
    asked: list[str] = []
    while (head := engine.next_step()) is not None:
        engine.mark_asked(head.step_id)
        engine.apply_extraction(head.step_id, {head.step_id: True})
        asked.append(head.step_id)
    return asked


def test_the_compiler_rank_is_the_engine_sort_key_for_every_step() -> None:
    protocol = _protocol(
        ("ziyaret", (("a", _slot()), ("b", _slot(must_ask=True)), ("c", _slot()))),
        ("sorular", (("d", _slot(must_ask=True)), ("e", _slot(ask_if="a == true")))),
    )
    plan = build_plan(protocol)
    assert ask_ranks(_rows(protocol)) == {
        step.step_id: (int(step.priority), step.order) for step in plan.steps
    }


def test_a_document_the_check_passes_is_asked_in_plan_order() -> None:
    protocol = _protocol(
        ("sorular", (("a", _slot()), ("b", _slot(ask_if="a == true")), ("c", _slot()))),
    )
    assert gates_reading_later_slots(_rows(protocol)) == ()
    ranks = ask_ranks(_rows(protocol))
    asked = _asked(protocol)
    assert asked == ["sorular.a", "sorular.b", "sorular.c"]
    assert [ranks[step] for step in asked] == sorted(ranks[step] for step in asked)


def test_a_document_the_check_refuses_is_asked_out_of_plan_order() -> None:
    """The gated question is not dropped: it is deferred past its gate slot."""
    protocol = _protocol(
        ("sorular", (("b", _slot(ask_if="a == true")), ("c", _slot()), ("a", _slot()))),
    )
    [late] = gates_reading_later_slots(_rows(protocol))
    assert (late.reader, late.read) == ("sorular.b", "sorular.a")
    ranks = ask_ranks(_rows(protocol))
    asked = _asked(protocol)
    assert asked == ["sorular.c", "sorular.a", "sorular.b"]
    assert [ranks[step] for step in asked] != sorted(ranks[step] for step in asked)


def test_a_must_ask_step_gated_on_a_detail_slot_is_asked_after_it() -> None:
    """The class dimension: the must-ask step sorts first but cannot open until
    the DETAIL slot it reads is answered, after every other must-ask step."""
    protocol = _protocol(
        (
            "sorular",
            (
                ("a", _slot()),
                ("b", _slot(must_ask=True, ask_if="a == true")),
                ("c", _slot(must_ask=True)),
            ),
        ),
    )
    [late] = gates_reading_later_slots(_rows(protocol))
    assert (late.reader, late.read) == ("sorular.b", "sorular.a")
    assert _asked(protocol) == ["sorular.c", "sorular.a", "sorular.b"]
