"""INT-041 — op application and the resolved document (files/12 §3).

``ops:`` is the whole merge language (files/12 §3.1); if the compiler quietly
ignored one, a hospital's copy change or a clinician's tightening would look
applied in review and be absent at runtime. So every member of the closed op
set is exercised here against the emitted document, and the ordering rule of
files/12 §3.3 — ``(layer_rank, priority, pack_id)`` then declared index — is
pinned as a total order.

The INT-040 op schema declares no ``priority`` field, so the tiebreaker chain
here is ``(layer_rank, pack_id, declared index)``. That is still total,
because pack ids are unique by construction (files/12 §3.3 relies on exactly
that), and it is recorded rather than inferred.
"""

from __future__ import annotations

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
from protocols.dsl import Section, Slot, VoiceSettings
from protocols.loader import PackRegistry
from protocols.ops import (
    AddSlotOp,
    OverrideTextOp,
    ReorderOp,
    SetAttrOp,
    SetVoiceOp,
    SuppressSlotOp,
)
from protocols.pack import ProtocolPack
from protocols.types import Delivery, Maturity, Pace, PackLayer, SlotType

VOICE = "sentetik-ses"
DEFERRED = "leaf-node binding awaits an openEHR informatician (INT-032, P3)"


def _slot(**overrides: Any) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.STRING,
        "ask_tr": "Sentetik soru.",
        "openehr_deferred_reason": DEFERRED,
    }
    payload.update(overrides)
    return Slot(**payload)


def _base(**overrides: Any) -> ProtocolPack:
    payload: dict[str, Any] = {
        "kind": "pack",
        "id": "base.sentetik_ops",
        "layer": PackLayer.BASE,
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": Maturity.L1,
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "sections": {
            "ziyaret": Section(
                slots={
                    "birinci": _slot(),
                    "ikinci": _slot(ask_tr="İkinci sentetik soru."),
                }
            )
        },
    }
    payload.update(overrides)
    return ProtocolPack.model_validate(payload)


def _hospital(*ops: Any) -> ProtocolPack:
    return ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": "hospital.sentetik",
            "layer": PackLayer.HOSPITAL,
            "version": "1.0.0",
            "schema_version": 2,
            "maturity": Maturity.L1,
            "status": "clinically-reviewed-synthetic",
            "language": "tr",
            "extends": "base.sentetik_ops",
            "ops": ops,
        }
    )


def _registry(*packs: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return registry


def _resolve(
    *packs: ProtocolPack,
    target: str = "hospital.sentetik",
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
) -> Any:
    return resolve_protocol(
        pack_id=target,
        registry=_registry(*packs),
        life_threat=life_threat,
        template=template,
    )


def _slot_keys(resolved: Any) -> list[str]:
    return [slot.key for section in resolved.sections for slot in section.slots]


def test_add_slot_appends_a_slot(life_threat: LifeThreatSet, template: OperationalTemplate) -> None:
    op = AddSlotOp(
        op="add_slot",
        pointer="/sections/ziyaret/slots/ucuncu",
        slot=_slot(ask_tr="Üçüncü sentetik soru."),
    )
    resolved = _resolve(_base(), _hospital(op), life_threat=life_threat, template=template)
    assert _slot_keys(resolved) == ["birinci", "ikinci", "ucuncu"]


def test_suppress_slot_removes_a_slot(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    op = SuppressSlotOp(op="suppress_slot", pointer="/sections/ziyaret/slots/ikinci")
    resolved = _resolve(_base(), _hospital(op), life_threat=life_threat, template=template)
    assert _slot_keys(resolved) == ["birinci"]


def test_set_attr_tightens_a_slot(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    base = _base(
        sections={
            "ziyaret": Section(
                slots={
                    "birinci": _slot(follow_up_tr="Sentetik takip."),
                    "ikinci": _slot(ask_tr="İkinci sentetik soru."),
                }
            )
        }
    )
    op = SetAttrOp(
        op="set_attr", pointer="/sections/ziyaret/slots/birinci", attr="required", value=True
    )
    resolved = _resolve(base, _hospital(op), life_threat=life_threat, template=template)
    birinci = next(s for s in resolved.sections[0].slots if s.key == "birinci")
    assert birinci.slot.required is True


def test_override_text_replaces_the_scripted_turkish(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §3.1: HOSPITAL gets ``override_text`` — the 'copy changes'
    case that had no syntax in v1.4."""
    op = OverrideTextOp(
        op="override_text",
        pointer="/sections/ziyaret/slots/birinci/ask_tr",
        text_tr="Hastaneye özgü sentetik soru.",
    )
    resolved = _resolve(_base(), _hospital(op), life_threat=life_threat, template=template)
    birinci = next(s for s in resolved.sections[0].slots if s.key == "birinci")
    assert birinci.slot.ask_tr == "Hastaneye özgü sentetik soru."


def test_set_voice_sets_section_hints(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    op = SetVoiceOp(
        op="set_voice", pointer="/sections/ziyaret", voice=VoiceSettings(pace=Pace.SLOW)
    )
    resolved = _resolve(_base(), _hospital(op), life_threat=life_threat, template=template)
    assert resolved.sections[0].voice is not None
    assert resolved.sections[0].voice.pace is Pace.SLOW


def test_reorder_reorders_slots(life_threat: LifeThreatSet, template: OperationalTemplate) -> None:
    op = ReorderOp(op="reorder", pointer="/sections/ziyaret/slots", order=("ikinci", "birinci"))
    resolved = _resolve(_base(), _hospital(op), life_threat=life_threat, template=template)
    assert _slot_keys(resolved) == ["ikinci", "birinci"]


def test_an_op_pointing_at_nothing_fails_closed(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    op = OverrideTextOp(
        op="override_text",
        pointer="/sections/yok/slots/birinci/ask_tr",
        text_tr="Sentetik metin.",
    )
    with pytest.raises(CompileError) as excinfo:
        _resolve(_base(), _hospital(op), life_threat=life_threat, template=template)
    assert RefusalCode.VALIDATION_FINDING in tuple(r.code for r in excinfo.value.refusals)


def test_reorder_that_drops_a_key_fails_closed(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A reorder is a permutation; anything else silently deletes a question."""
    op = ReorderOp(op="reorder", pointer="/sections/ziyaret/slots", order=("birinci",))
    with pytest.raises(CompileError) as excinfo:
        _resolve(_base(), _hospital(op), life_threat=life_threat, template=template)
    assert RefusalCode.VALIDATION_FINDING in tuple(r.code for r in excinfo.value.refusals)


def test_ops_apply_in_the_layer_then_pack_id_order(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §3.3: the total order is (layer_rank, priority, pack_id) then
    declared index. Two packs at different layers writing compatible ops must
    apply lower-layer-first, whichever order they were named in."""
    base = _base()
    specialty = ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": "specialty.sentetik",
            "layer": PackLayer.SPECIALTY,
            "version": "1.0.0",
            "schema_version": 2,
            "maturity": Maturity.L1,
            "status": "clinically-reviewed-synthetic",
            "language": "tr",
            "extends": "base.sentetik_ops",
            "ops": (
                AddSlotOp(
                    op="add_slot",
                    pointer="/sections/ziyaret/slots/ucuncu",
                    slot=_slot(ask_tr="Üçüncü sentetik soru."),
                ),
            ),
        }
    )
    hospital = ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": "hospital.sentetik",
            "layer": PackLayer.HOSPITAL,
            "version": "1.0.0",
            "schema_version": 2,
            "maturity": Maturity.L1,
            "status": "clinically-reviewed-synthetic",
            "language": "tr",
            "extends": "specialty.sentetik",
            "ops": (
                ReorderOp(
                    op="reorder",
                    pointer="/sections/ziyaret/slots",
                    order=("ucuncu", "ikinci", "birinci"),
                ),
            ),
        }
    )
    resolved = _resolve(base, specialty, hospital, life_threat=life_threat, template=template)
    assert _slot_keys(resolved) == ["ucuncu", "ikinci", "birinci"]


def test_the_life_threat_rules_are_carried_beside_the_pack_rules(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §1: the life-threat set is NOT merged into the resolved
    protocol; it is a sibling evaluated on every session. The compiled bundle
    carries both, separately, so nothing can accidentally treat one as the
    other."""
    resolved = _resolve(_base(), _hospital(), life_threat=life_threat, template=template)
    assert [rule.id for rule in resolved.life_threat_rules] == ["rf.sentetik_yasamsal"]
    assert resolved.red_flags == ()


def test_a_text_first_slot_still_produces_a_clip(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/13 §13: only ``text_only`` bans the clip; ``text_first`` is a
    channel preference, not a prohibition."""
    base = _base(
        sections={
            "ziyaret": Section(
                delivery=Delivery.TEXT_FIRST,
                slots={"birinci": _slot(ask_tr="Metin öncelikli sentetik soru.")},
            )
        }
    )
    bundle = compile_bundle(
        pack_id="base.sentetik_ops",
        registry=_registry(base),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    assert "Metin öncelikli sentetik soru." in {row.text_tr for row in bundle.clip_manifest}


def test_a_non_projectable_gate_fails_closed(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A ``Questionnaire`` that silently drops an ``ask_if`` shows a consumer
    a question the protocol says to hide. The projectable grammar is narrow
    on purpose and everything outside it is a build failure, not a drop."""
    base = _base(
        sections={
            "ziyaret": Section(
                slots={
                    "birinci": _slot(ask_if="meds.any(class == DMARD)"),
                }
            )
        }
    )
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id="base.sentetik_ops",
            registry=_registry(base),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
        )
    assert RefusalCode.GATE_NOT_PROJECTABLE in tuple(r.code for r in excinfo.value.refusals)


def test_skip_if_projects_as_the_inverted_gate(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """``skip_if: A == x`` is ``enableWhen: A != x``; De Morgan over a
    top-level conjunction flips the behaviour to ``any``."""
    import json

    base = _base(
        sections={
            "ziyaret": Section(
                slots={
                    "birinci": _slot(),
                    "ikinci": _slot(
                        ask_tr="İkinci sentetik soru.",
                        skip_if="ziyaret.birinci == 'atla' && ziyaret.birinci != 'kal'",
                    ),
                }
            )
        }
    )
    bundle = compile_bundle(
        pack_id="base.sentetik_ops",
        registry=_registry(base),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    doc = json.loads(bundle.artifacts["questionnaire.json"])
    item = doc["item"][0]["item"][1]
    assert item["enableBehavior"] == "any"
    assert item["enableWhen"] == [
        {"question": "ziyaret.birinci", "operator": "!=", "answerString": "atla"},
        {"question": "ziyaret.birinci", "operator": "=", "answerString": "kal"},
    ]


@pytest.mark.parametrize(
    ("expression", "operator"),
    [
        ("ziyaret.birinci > 3", ">"),
        ("ziyaret.birinci >= 3", ">="),
        ("ziyaret.birinci < 3", "<"),
        ("ziyaret.birinci <= 3", "<="),
    ],
)
def test_numeric_comparisons_project(
    expression: str,
    operator: str,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
) -> None:
    import json

    base = _base(
        sections={
            "ziyaret": Section(
                slots={
                    "birinci": _slot(type=SlotType.INTEGER, ask_tr="Sentetik sayı sorusu."),
                    "ikinci": _slot(ask_tr="İkinci sentetik soru.", ask_if=expression),
                }
            )
        }
    )
    bundle = compile_bundle(
        pack_id="base.sentetik_ops",
        registry=_registry(base),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    doc = json.loads(bundle.artifacts["questionnaire.json"])
    condition = doc["item"][0]["item"][1]["enableWhen"][0]
    assert condition == {
        "question": "ziyaret.birinci",
        "operator": operator,
        "answerInteger": 3,
    }
