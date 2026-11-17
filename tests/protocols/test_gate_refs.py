"""INT-355 — a gate reads the slot it names, whichever way it names it.

files/03 §6 atoms are section-qualified (``identity_check.subject_role``) or
bare (``subject_role``): :data:`protocols.types.SLOT_REF_PATTERN` admits both,
and ``base.intake`` writes the bare form. The engine, the FHIR emitter and the
compiler key every slot ``<section>.<slot>`` — the step id, the linkId and the
JSON pointer are one identity (``protocols.bindings.fhir_link``). Before
INT-355 a bare name was looked up as written, read Unknown, and the gate it
sat in never opened: the dependent question was silently never asked.

What is pinned here: a qualified name resolves to itself when that slot
exists; a bare name resolves to the ONE slot of that name across the resolved
chain (base + cluster + specialty); a bare name two sections hold is ambiguous
and a name nothing holds is unknown, and the compiler refuses both — a gate
that cannot resolve to exactly one slot can never open.

Every id, key and string here is synthetic (files/04 §7).
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
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
from protocols.compile.emit_fhir import questionnaire
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Section, Slot
from protocols.gates import GateRefIssue, GateRefProblem, SlotNamespace, qualify_gate
from protocols.loader import PackRegistry, load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.pack import ProtocolPack
from protocols.triage.expr import Truth, evaluate_node, parse_when, referenced_slots
from protocols.types import Delivery, Maturity, PackLayer, SlotType

VOICE = "sentetik-ses"
DEFERRED = "leaf-node binding awaits an openEHR informatician (INT-032, P3)"
BASE_INTAKE = (
    Path(__file__).resolve().parents[2] / "packages" / "protocols" / "base" / "intake.yaml"
)


def _namespace(*refs: str) -> SlotNamespace:
    pairs = [tuple(ref.split(".")) for ref in refs]
    return SlotNamespace((section, key) for section, key in pairs)


# --- the namespace --------------------------------------------------------------


def test_a_qualified_name_resolves_to_itself() -> None:
    namespace = _namespace("ziyaret.belirti_var", "sorular.sure")
    assert namespace.resolve("ziyaret.belirti_var") == "ziyaret.belirti_var"


def test_a_bare_name_resolves_to_the_one_slot_that_holds_it() -> None:
    namespace = _namespace("ziyaret.belirti_var", "sorular.sure")
    assert namespace.resolve("belirti_var") == "ziyaret.belirti_var"


def test_a_bare_name_two_sections_hold_is_ambiguous_and_names_both() -> None:
    namespace = _namespace("ziyaret.belirti_var", "sorular.belirti_var")
    issue = namespace.resolve("belirti_var")
    assert isinstance(issue, GateRefIssue)
    assert issue.problem is GateRefProblem.AMBIGUOUS
    assert issue.candidates == ("sorular.belirti_var", "ziyaret.belirti_var")
    assert "sorular.belirti_var" in issue.describe()
    assert "ziyaret.belirti_var" in issue.describe()


def test_a_qualified_name_stays_exact_when_its_bare_key_is_duplicated() -> None:
    """Near-miss control for the ambiguity refusal: qualifying is the fix."""
    namespace = _namespace("ziyaret.belirti_var", "sorular.belirti_var")
    assert namespace.resolve("sorular.belirti_var") == "sorular.belirti_var"


@pytest.mark.parametrize(
    "name",
    [
        "yok",  # bare, held by nothing
        "ziyaret",  # a section is not a slot
        "yok.belirti_var",  # qualified with a section that does not exist
        "ziyaret.yok",  # qualified with a key the section does not hold
        "ziyaret.belirti_var.fazla",  # three parts name nothing in a section/slot space
    ],
)
def test_a_name_nothing_holds_is_unknown(name: str) -> None:
    namespace = _namespace("ziyaret.belirti_var")
    issue = namespace.resolve(name)
    assert isinstance(issue, GateRefIssue)
    assert issue.problem is GateRefProblem.UNKNOWN
    assert issue.candidates == ()
    assert name in issue.describe()


# --- rewriting a parsed gate -------------------------------------------------------


def test_every_reference_in_every_node_shape_is_qualified() -> None:
    """BoolRef, Compare (both operands), InSet, Not, And and Or — every node the
    closed ``when`` grammar can build — come back reading qualified keys, and a
    lookup that only knows qualified keys evaluates the rewritten gate."""
    namespace = _namespace("ziyaret.belirti_var", "ziyaret.renk", "sorular.sure", "sorular.esik")
    text = "belirti_var && !(renk in {'mavi', 'yesil'}) && (sure >= esik || sorular.sure < 2)"
    qualified, issues = qualify_gate(parse_when(text), namespace)
    assert issues == ()
    assert referenced_slots(qualified) == frozenset(
        {"ziyaret.belirti_var", "ziyaret.renk", "sorular.sure", "sorular.esik"}
    )
    values: dict[str, bool | Decimal | str] = {
        "ziyaret.belirti_var": True,
        "ziyaret.renk": "kirmizi",
        "sorular.sure": Decimal(5),
        "sorular.esik": Decimal(3),
    }
    assert evaluate_node(qualified, values.get) is Truth.TRUE


def test_a_literal_spelled_like_a_slot_is_never_renamed() -> None:
    namespace = _namespace("ziyaret.renk")
    qualified, _ = qualify_gate(parse_when("renk == 'renk'"), namespace)
    assert evaluate_node(qualified, {"ziyaret.renk": "renk"}.get) is Truth.TRUE


def test_every_bad_reference_is_reported_not_just_the_first() -> None:
    namespace = _namespace("ziyaret.belirti_var", "sorular.belirti_var")
    node = parse_when("belirti_var == true || yok == true")
    unchanged, issues = qualify_gate(node, namespace)
    assert unchanged == node
    assert {(issue.name, issue.problem) for issue in issues} == {
        ("belirti_var", GateRefProblem.AMBIGUOUS),
        ("yok", GateRefProblem.UNKNOWN),
    }


def test_base_intake_gates_name_one_slot_each() -> None:
    """The gates the authored base pack carries resolve, across all of its
    sections, to exactly the slot their question depends on. INT-432 (CD-01)
    adds six: every chest-pain follow-up opens on the one screen, across three
    sections, and each must resolve to that screen and nothing else."""
    chest_follow_ups = (
        "chest_pain.character",
        "chest_pain.radiation",
        "chest_pain.onset_at",
        "associated.diaphoresis",
        "associated.dyspnoea",
        "trauma.recent",
    )
    pack = load_pack(BASE_INTAKE)
    namespace = SlotNamespace(
        (section_id, key) for section_id, section in pack.sections.items() for key in section.slots
    )
    gates = {
        f"{section_id}.{key}": slot.ask_if
        for section_id, section in pack.sections.items()
        for key, slot in section.slots.items()
        if slot.ask_if is not None
    }
    resolved = {}
    for step_id, text in gates.items():
        qualified, issues = qualify_gate(parse_when(text), namespace)
        assert issues == (), step_id
        resolved[step_id] = referenced_slots(qualified)
    assert resolved == {
        "identity_check.proxy_reported": frozenset({"identity_check.subject_role"}),
        "pmh_fh_sh.lmp_date": frozenset({"pmh_fh_sh.pregnancy_status"}),
        **{step: frozenset({"chest_pain.present"}) for step in chest_follow_ups},
    }


# --- the compiler ------------------------------------------------------------------


def _slot(**overrides: Any) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.STRING,
        "ask_tr": {TR: "Sentetik soru."},
        "openehr_deferred_reason": DEFERRED,
    }
    payload.update(overrides)
    return Slot(**payload)


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


def _base() -> ProtocolPack:
    return _pack(
        "base.sentetik_gate",
        PackLayer.BASE,
        {
            "ziyaret": Section(
                slots={
                    "belirti_var": _slot(
                        type=SlotType.BOOLEAN, ask_tr={TR: "Sentetik belirti sorusu."}
                    ),
                }
            )
        },
    )


def _specialty(**slots: Slot) -> ProtocolPack:
    return _pack(
        "specialty.sentetik_gate",
        PackLayer.SPECIALTY,
        {"sorular": Section(slots=slots)},
        extends="base.sentetik_gate",
    )


def _registry(*packs: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return registry


def _compile(
    *packs: ProtocolPack, life_threat: LifeThreatSet, template: OperationalTemplate
) -> dict[str, Any]:
    bundle = compile_bundle(
        pack_id="specialty.sentetik_gate",
        registry=_registry(*packs),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    payload = json.loads(bundle.artifacts["questionnaire.json"])
    assert isinstance(payload, dict)
    return {item["linkId"]: item for group in payload["item"] for item in group["item"]}


def _refusals(
    *packs: ProtocolPack, life_threat: LifeThreatSet, template: OperationalTemplate
) -> dict[RefusalCode, list[tuple[str, str]]]:
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id="specialty.sentetik_gate",
            registry=_registry(*packs),
            life_threat=life_threat,
            template=template,
        )
    grouped: dict[RefusalCode, list[tuple[str, str]]] = {}
    for refusal in excinfo.value.refusals:
        grouped.setdefault(refusal.code, []).append((refusal.subject, refusal.message))
    return grouped


def test_a_bare_gate_on_a_parent_slot_projects_the_qualified_link_id(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The specialty-candidate spelling: the gate names a slot the base pack
    declares, bare. The Questionnaire's enableWhen must point at the qualified
    linkId the base slot actually carries."""
    items = _compile(
        _base(),
        _specialty(sure=_slot(ask_tr={TR: "Sentetik süre sorusu."}, ask_if="belirti_var == true")),
        life_threat=life_threat,
        template=template,
    )
    assert items["sorular.sure"]["enableWhen"] == [
        {"question": "ziyaret.belirti_var", "operator": "=", "answerBoolean": True}
    ]


def test_a_bare_skip_if_projects_the_qualified_link_id_inverted(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    items = _compile(
        _base(),
        _specialty(
            sure=_slot(ask_tr={TR: "Sentetik süre sorusu."}, skip_if="belirti_var == false")
        ),
        life_threat=life_threat,
        template=template,
    )
    assert items["sorular.sure"]["enableWhen"] == [
        {"question": "ziyaret.belirti_var", "operator": "!=", "answerBoolean": False}
    ]


def test_an_ambiguous_bare_gate_is_refused_at_compile(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Two sections of the resolved chain hold ``belirti_var``; a bare gate on
    it could read either, so the compiler refuses to pick one."""
    specialty = _specialty(
        belirti_var=_slot(type=SlotType.BOOLEAN, ask_tr={TR: "İkinci sentetik belirti sorusu."}),
        sure=_slot(ask_tr={TR: "Sentetik süre sorusu."}, ask_if="belirti_var == true"),
    )
    grouped = _refusals(_base(), specialty, life_threat=life_threat, template=template)
    assert set(grouped) == {RefusalCode.GATE_REF_AMBIGUOUS}
    [(subject, message)] = grouped[RefusalCode.GATE_REF_AMBIGUOUS]
    assert subject == "sorular.sure"
    assert "sorular.belirti_var" in message
    assert "ziyaret.belirti_var" in message


def test_the_same_chain_compiles_once_the_gate_is_qualified(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Near-miss negative control for the ambiguity refusal: identical chain,
    duplicated bare key, gate section-qualified — it compiles and projects."""
    specialty = _specialty(
        belirti_var=_slot(type=SlotType.BOOLEAN, ask_tr={TR: "İkinci sentetik belirti sorusu."}),
        sure=_slot(ask_tr={TR: "Sentetik süre sorusu."}, ask_if="sorular.belirti_var == true"),
    )
    items = _compile(_base(), specialty, life_threat=life_threat, template=template)
    assert items["sorular.sure"]["enableWhen"] == [
        {"question": "sorular.belirti_var", "operator": "=", "answerBoolean": True}
    ]


def test_an_ambiguous_bare_skip_if_is_refused_too(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    specialty = _specialty(
        belirti_var=_slot(type=SlotType.BOOLEAN, ask_tr={TR: "İkinci sentetik belirti sorusu."}),
        sure=_slot(ask_tr={TR: "Sentetik süre sorusu."}, skip_if="belirti_var == false"),
    )
    grouped = _refusals(_base(), specialty, life_threat=life_threat, template=template)
    assert [subject for subject, _ in grouped[RefusalCode.GATE_REF_AMBIGUOUS]] == ["sorular.sure"]


def test_a_bare_gate_naming_no_slot_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A gate on a name nothing holds reads Unknown forever — it would never
    open, so its question would never be asked."""
    specialty = _specialty(
        sure=_slot(ask_tr={TR: "Sentetik süre sorusu."}, ask_if="ates_var == true"),
    )
    grouped = _refusals(_base(), specialty, life_threat=life_threat, template=template)
    assert set(grouped) == {RefusalCode.GATE_REF_UNKNOWN}
    [(subject, message)] = grouped[RefusalCode.GATE_REF_UNKNOWN]
    assert subject == "sorular.sure"
    assert "ates_var" in message


def test_every_unresolvable_gate_is_reported(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    specialty = _specialty(
        belirti_var=_slot(type=SlotType.BOOLEAN, ask_tr={TR: "İkinci sentetik belirti sorusu."}),
        sure=_slot(ask_tr={TR: "Sentetik süre sorusu."}, ask_if="belirti_var == true"),
        ek_not=_slot(ask_tr={TR: "Sentetik not sorusu."}, skip_if="yok == true"),
    )
    grouped = _refusals(_base(), specialty, life_threat=life_threat, template=template)
    assert [s for s, _ in grouped[RefusalCode.GATE_REF_AMBIGUOUS]] == ["sorular.sure"]
    assert [s for s, _ in grouped[RefusalCode.GATE_REF_UNKNOWN]] == ["sorular.ek_not"]


# --- the emitter, on a document that never went through the resolver ---------------


def _hand_built(gate: str) -> ResolvedProtocol:
    def resolved(section_id: str, key: str, slot: Slot) -> ResolvedSlot:
        return ResolvedSlot(
            section_id=section_id,
            key=key,
            fhir_link_id=f"{section_id}.{key}",
            slot=slot,
            delivery=Delivery.VOICE,
        )

    boolean = _slot(type=SlotType.BOOLEAN)
    return ResolvedProtocol(
        pack_id="base.sentetik_gate",
        version="1.0.0",
        chain=("base.sentetik_gate",),
        sections=(
            ResolvedSection(
                id="ziyaret",
                delivery=Delivery.VOICE,
                allow_paraphrase=False,
                slots=(resolved("ziyaret", "belirti_var", boolean),),
            ),
            ResolvedSection(
                id="sorular",
                delivery=Delivery.VOICE,
                allow_paraphrase=False,
                slots=(
                    resolved("sorular", "belirti_var", boolean),
                    resolved("sorular", "sure", _slot(ask_if=gate)),
                ),
            ),
        ),
        resolved_protocol_hash="0" * 64,
    )


def test_the_emitter_never_picks_one_holder_of_an_ambiguous_bare_name() -> None:
    """Defence in depth. The resolver refuses this document; an emitter handed
    it anyway must not project the gate onto whichever holder came last."""
    _, refusals = questionnaire(_hand_built("belirti_var == true"), {})
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.GATE_NOT_PROJECTABLE, "sorular.sure")
    ]


def test_the_emitter_refuses_a_conjunction_with_one_ambiguous_conjunct() -> None:
    """One unresolvable conjunct refuses the whole gate — projecting the rest
    would widen it, showing the question in cases the protocol hides it."""
    _, refusals = questionnaire(
        _hand_built("sorular.belirti_var == true && belirti_var == true"), {}
    )
    assert [(r.code, r.subject) for r in refusals] == [
        (RefusalCode.GATE_NOT_PROJECTABLE, "sorular.sure")
    ]


def test_the_emitter_projects_a_qualified_name_on_the_same_document() -> None:
    doc, refusals = questionnaire(_hand_built("sorular.belirti_var == true"), {})
    assert refusals == []
    items = {item["linkId"]: item for group in doc["item"] for item in group["item"]}
    assert items["sorular.sure"]["enableWhen"] == [
        {"question": "sorular.belirti_var", "operator": "=", "answerBoolean": True}
    ]
