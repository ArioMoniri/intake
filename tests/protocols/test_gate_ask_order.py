"""INT-375 — no gate reads a slot the merged ask order puts at or after it.

files/13 §9.5 lists stratified acyclicity among the CI-blocking compiler checks:
"a gate on step S may reference only slots owned by steps of strictly lower
``(priority, order)``". The engine sorts its plan by ``(priority_class, order,
id)`` (files/13 §9.1) and re-reads every gate on every turn; a slot not yet
asked reads Unknown, and Unknown does not open a gate. So a gate that reads a
later slot does not drop its question — it passes it over at its own place and
asks it once the later slot is answered, out of the frozen plan order. PR #582
found four of these in one review chain; nothing in the compiler refused them.

What is pinned here: the rank is the engine's sort key (a clinician-marked
must-ask sorts as class 5, everything else as class 7, then merged position),
read after the chain is merged and every op is applied; a gate that reads a
slot of strictly lower rank passes and one that reads an equal or higher rank
is refused as ``GATE_READS_LATER_SLOT``, naming the pack that wrote the gate,
the gated slot and the slot it reads — ids only. The check refuses; it never
reorders, never touches ``must_ask`` and never reads a red-flag rule (CLAUDE.md
invariants 1 and 7).

Every id, key and string here is synthetic (files/04 §7).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from protocols.bindings import OperationalTemplate
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    RefusalCode,
    compile_bundle,
    resolve_protocol,
)
from protocols.dsl import Section, Slot
from protocols.gates import (
    DETAIL_CLASS,
    MUST_ASK_CLASS,
    LaterSlotRead,
    ask_ranks,
    gates_reading_later_slots,
)
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.pack import ProtocolPack
from protocols.types import Maturity, PackLayer, SlotType

VOICE = "sentetik-ses"
DEFERRED = "leaf-node binding awaits an openEHR informatician (INT-032, P3)"
BASE = "base.sentetik_sira"
SPECIALTY = "specialty.sentetik_sira"


def _slot(*, must_ask: bool = False, **gates: str) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.BOOLEAN,
        "must_ask": must_ask,
        "ask_tr": {TR: "Sentetik soru mu?"},
        "openehr_deferred_reason": DEFERRED,
    }
    payload.update(gates)
    return Slot(**payload)


def _rows(*rows: tuple[str, str, Slot]) -> tuple[tuple[str, str, Slot], ...]:
    return rows


# --- the rank ---------------------------------------------------------------------


def test_the_rank_is_the_engines_sort_key_class_then_merged_position() -> None:
    """files/13 §9.1: MUST_ASK is class 5 and DETAIL class 7; ``order`` counts
    across sections in merged order, not per section."""
    ranks = ask_ranks(
        _rows(
            ("ziyaret", "a", _slot()),
            ("ziyaret", "b", _slot(must_ask=True)),
            ("sorular", "c", _slot()),
        )
    )
    assert (MUST_ASK_CLASS, DETAIL_CLASS) == (5, 7)
    assert ranks == {"ziyaret.a": (7, 0), "ziyaret.b": (5, 1), "sorular.c": (7, 2)}


# --- the pure check -----------------------------------------------------------------


def test_a_gate_reading_the_immediately_preceding_slot_passes() -> None:
    """Near-miss control: the closest a gate slot can sit to its reader."""
    rows = _rows(
        ("sorular", "p", _slot()),
        ("sorular", "a", _slot()),
        ("sorular", "b", _slot(ask_if="a == true")),
        ("sorular", "q", _slot()),
    )
    assert gates_reading_later_slots(rows) == ()


def test_the_same_gate_with_its_slot_one_position_later_is_found() -> None:
    """The control above with ``a`` moved one place later — now directly after
    the question it gates."""
    rows = _rows(
        ("sorular", "p", _slot()),
        ("sorular", "b", _slot(ask_if="a == true")),
        ("sorular", "a", _slot()),
        ("sorular", "q", _slot()),
    )
    assert gates_reading_later_slots(rows) == (
        LaterSlotRead(
            reader="sorular.b",
            field="ask_if",
            read="sorular.a",
            reader_rank=(7, 1),
            read_rank=(7, 2),
        ),
    )


def test_a_skip_if_that_reads_a_later_slot_is_found_too() -> None:
    rows = _rows(("sorular", "b", _slot(skip_if="a == false")), ("sorular", "a", _slot()))
    [late] = gates_reading_later_slots(rows)
    assert (late.reader, late.field, late.read) == ("sorular.b", "skip_if", "sorular.a")


def test_a_gate_reading_its_own_slot_is_found() -> None:
    """Equal rank is not strictly lower: the slot is Unknown until asked and
    is not asked until its gate opens."""
    [late] = gates_reading_later_slots(_rows(("sorular", "a", _slot(ask_if="a == true"))))
    assert late.read == late.reader == "sorular.a"
    assert "itself" in late.describe()


def test_a_gate_slot_in_a_later_section_is_later() -> None:
    rows = _rows(("ziyaret", "b", _slot(ask_if="a == true")), ("sorular", "a", _slot()))
    [late] = gates_reading_later_slots(rows)
    assert (late.reader, late.read) == ("ziyaret.b", "sorular.a")


def test_a_must_ask_reader_gated_on_an_earlier_detail_slot_is_found() -> None:
    """The priority class sorts first: a MUST_ASK step is asked before every
    DETAIL step, whatever its position, so a DETAIL gate slot comes later."""
    rows = _rows(("sorular", "a", _slot()), ("sorular", "b", _slot(must_ask=True, ask_if="a")))
    [late] = gates_reading_later_slots(rows)
    assert (late.reader_rank, late.read_rank) == ((5, 1), (7, 0))


def test_a_detail_reader_gated_on_a_later_must_ask_slot_passes() -> None:
    """Near-miss control for the class ordering: the mirror image is earlier."""
    rows = _rows(("sorular", "b", _slot(ask_if="a")), ("sorular", "a", _slot(must_ask=True)))
    assert gates_reading_later_slots(rows) == ()


def test_every_later_read_is_reported_once_and_in_order() -> None:
    """Two spellings of one slot are one read; an earlier conjunct is not
    reported; the later ones come back sorted by the slot they read."""
    rows = _rows(
        ("sorular", "a", _slot()),
        ("sorular", "b", _slot(ask_if="d == true && a == true && c == true && sorular.d")),
        ("sorular", "c", _slot()),
        ("sorular", "d", _slot()),
    )
    assert [late.read for late in gates_reading_later_slots(rows)] == ["sorular.c", "sorular.d"]


def test_names_that_do_not_resolve_are_left_to_the_gate_ref_refusals() -> None:
    """Ambiguous and unknown names are INT-355's refusals and an unparseable
    gate is the emitter's; this check judges only reads it can place."""
    rows = _rows(
        ("ziyaret", "x", _slot()),
        ("sorular", "x", _slot()),
        ("sorular", "b", _slot(ask_if="x == true || yok == true")),
        ("sorular", "c", _slot(ask_if="(((")),
    )
    assert gates_reading_later_slots(rows) == ()


def test_the_description_names_ids_and_ranks_only() -> None:
    late = LaterSlotRead(
        reader="sorular.b",
        field="ask_if",
        read="sorular.a",
        reader_rank=(7, 1),
        read_rank=(7, 2),
    )
    assert late.describe() == (
        "ask_if on sorular.b (ask rank (7, 1)) reads sorular.a (ask rank (7, 2)), "
        "which is not strictly before it"
    )


# --- the resolver -------------------------------------------------------------------


def _pack(
    pack_id: str, layer: PackLayer, sections: dict[str, Section], **extra: Any
) -> ProtocolPack:
    payload: dict[str, Any] = {
        "kind": "pack",
        "id": pack_id,
        "layer": layer,
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": Maturity.L1,
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "sections": sections,
    }
    payload.update(extra)
    return ProtocolPack.model_validate(payload)


def _base(**slots: Slot) -> ProtocolPack:
    return _pack(BASE, PackLayer.BASE, {"ziyaret": Section(slots=slots or {"belirti": _slot()})})


def _specialty(slots: dict[str, Slot], *ops: dict[str, Any]) -> ProtocolPack:
    return _pack(
        SPECIALTY,
        PackLayer.SPECIALTY,
        {"sorular": Section(slots=slots)},
        extends=BASE,
        ops=list(ops),
    )


def _reorder(*order: str, section: str = "sorular") -> dict[str, Any]:
    return {"op": "reorder", "pointer": f"/sections/{section}/slots", "order": list(order)}


def _registry(*packs: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return registry


def _compiled_order(
    *packs: ProtocolPack, life_threat: LifeThreatSet, template: OperationalTemplate
) -> list[str]:
    bundle = compile_bundle(
        pack_id=packs[-1].id,
        registry=_registry(*packs),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    payload = json.loads(bundle.artifacts["questionnaire.json"])
    return [item["linkId"] for group in payload["item"] for item in group["item"]]


def _refusals(
    *packs: ProtocolPack, life_threat: LifeThreatSet, template: OperationalTemplate
) -> list[tuple[RefusalCode, str, str]]:
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=packs[-1].id,
            registry=_registry(*packs),
            life_threat=life_threat,
            template=template,
        )
    return [(r.code, r.subject, r.message) for r in excinfo.value.refusals]


def test_a_forward_gate_is_refused_naming_pack_slot_and_gate_slot(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    specialty = _specialty({"sure": _slot(ask_if="yeni == true"), "yeni": _slot()})
    [(code, subject, message)] = _refusals(
        _base(), specialty, life_threat=life_threat, template=template
    )
    assert code is RefusalCode.GATE_READS_LATER_SLOT
    assert subject == f"{SPECIALTY}:sorular.sure"
    assert "reads sorular.yeni" in message
    assert "files/13 §9.5" in message
    assert "yeni == true" not in message  # ids only, never the gate text


def test_the_same_gate_after_a_reorder_op_is_admitted(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The order is read after the chain's ops (files/12 §3.1 ``reorder``)."""
    specialty = _specialty(
        {"sure": _slot(ask_if="yeni == true"), "yeni": _slot()}, _reorder("yeni", "sure")
    )
    order = _compiled_order(_base(), specialty, life_threat=life_threat, template=template)
    assert order == ["ziyaret.belirti", "sorular.yeni", "sorular.sure"]


def test_a_reorder_op_that_moves_a_gate_slot_after_its_reader_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Near-miss pair on the compiler: reading the immediately preceding slot
    compiles; the same op with the gate slot one position later refuses."""
    slots = {"p": _slot(), "a": _slot(), "b": _slot(ask_if="a == true"), "q": _slot()}
    admitted = _specialty(slots, _reorder("p", "a", "b", "q"))
    order = _compiled_order(_base(), admitted, life_threat=life_threat, template=template)
    assert order[1:] == ["sorular.p", "sorular.a", "sorular.b", "sorular.q"]

    refused = _specialty(slots, _reorder("p", "b", "a", "q"))
    [(code, subject, _)] = _refusals(_base(), refused, life_threat=life_threat, template=template)
    assert (code, subject) == (RefusalCode.GATE_READS_LATER_SLOT, f"{SPECIALTY}:sorular.b")


def test_a_gate_on_a_base_slot_is_admitted(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    specialty = _specialty({"sure": _slot(ask_if="belirti == true")})
    order = _compiled_order(_base(), specialty, life_threat=life_threat, template=template)
    assert order == ["ziyaret.belirti", "sorular.sure"]


def test_a_redeclared_parent_slot_keeps_its_place_so_a_gate_on_a_new_slot_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The PR #582 shape: a child re-declares a parent slot and gates it on a
    slot the child adds. The merge keeps the re-declared slot at the parent's
    position and appends the new one, so the gate reads forward — and the
    refusal names the child, whose declaration carries the gate."""
    base = _base(belirti=_slot(), kanama=_slot())
    child = _pack(
        SPECIALTY,
        PackLayer.SPECIALTY,
        {"ziyaret": Section(slots={"kanama": _slot(ask_if="gebelik == true"), "gebelik": _slot()})},
        extends=BASE,
    )
    [(code, subject, message)] = _refusals(base, child, life_threat=life_threat, template=template)
    assert (code, subject) == (RefusalCode.GATE_READS_LATER_SLOT, f"{SPECIALTY}:ziyaret.kanama")
    assert "reads ziyaret.gebelik" in message


def test_a_gate_the_parent_wrote_is_attributed_to_the_parent(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    base = _base(sure=_slot(ask_if="belirti == true"), belirti=_slot())
    specialty = _specialty({"ek": _slot()})
    [(code, subject, _)] = _refusals(base, specialty, life_threat=life_threat, template=template)
    assert (code, subject) == (RefusalCode.GATE_READS_LATER_SLOT, f"{BASE}:ziyaret.sure")


def test_a_gate_on_a_slot_added_by_op_is_attributed_to_the_ops_pack(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A three-pack chain, so the pack that wrote the gate (the cluster, by an
    ``add_slot`` op into a base section) is not the pack being compiled. The
    added slot lands at the end of ``ziyaret``; its gate slot sits in the
    cluster's own later section."""
    cluster_id = "cluster.sentetik_sira"
    add = {
        "op": "add_slot",
        "pointer": "/sections/ziyaret/slots/eklenen",
        "slot": _slot(ask_if="son == true").model_dump(mode="json", exclude_none=True),
    }
    cluster = _pack(
        cluster_id,
        PackLayer.CLUSTER,
        {"kume": Section(slots={"son": _slot()})},
        extends=BASE,
        ops=[add],
    )
    specialty = _pack(
        SPECIALTY,
        PackLayer.SPECIALTY,
        {"sorular": Section(slots={"ek": _slot()})},
        extends=cluster_id,
    )
    [(code, subject, message)] = _refusals(
        _base(), cluster, specialty, life_threat=life_threat, template=template
    )
    assert (code, subject) == (RefusalCode.GATE_READS_LATER_SLOT, f"{cluster_id}:ziyaret.eklenen")
    assert "reads kume.son" in message


def test_tightening_must_ask_on_a_gated_slot_whose_gate_slot_is_detail_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """set_attr may raise ``must_ask`` (files/12 §3.2) and that moves the slot
    into class 5, ahead of its DETAIL gate slot. The check reads the rank after
    the op; it does not undo the tightening."""
    tighten = {
        "op": "set_attr",
        "pointer": "/sections/ziyaret/slots/sure",
        "attr": "must_ask",
        "value": True,
    }
    base = _base(belirti=_slot(), sure=_slot(ask_if="belirti == true"))
    specialty = _specialty({"ek": _slot()}, tighten)
    [(code, subject, message)] = _refusals(
        base, specialty, life_threat=life_threat, template=template
    )
    assert (code, subject) == (RefusalCode.GATE_READS_LATER_SLOT, f"{BASE}:ziyaret.sure")
    assert "(5, 1)" in message and "(7, 0)" in message


def test_tightening_the_gate_slot_as_well_is_admitted(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Near-miss control: both slots in class 5, gate slot first."""
    ops = [
        {
            "op": "set_attr",
            "pointer": f"/sections/ziyaret/slots/{key}",
            "attr": "must_ask",
            "value": True,
        }
        for key in ("belirti", "sure")
    ]
    base = _base(belirti=_slot(), sure=_slot(ask_if="belirti == true"))
    specialty = _specialty({"ek": _slot()}, *ops)
    order = _compiled_order(base, specialty, life_threat=life_threat, template=template)
    assert order == ["ziyaret.belirti", "ziyaret.sure", "sorular.ek"]


def test_an_order_the_ops_did_not_produce_is_not_judged(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A reorder that is not a permutation is refused and not applied; the
    order left behind is not the one the author wrote, so the forward gate it
    would have fixed is not reported against it."""
    specialty = _specialty(
        {"sure": _slot(ask_if="yeni == true"), "yeni": _slot()}, _reorder("yeni")
    )
    codes = [
        code
        for code, _, _ in _refusals(_base(), specialty, life_threat=life_threat, template=template)
    ]
    assert codes == [RefusalCode.VALIDATION_FINDING]
