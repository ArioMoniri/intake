"""INT-041 — the failure paths that only run when something is malformed.

A fail-closed compiler is mostly error handling, and error handling that is
never executed is error handling nobody knows is wrong. These are the
defensive branches: a template that will not parse, a life-threat document
that is not one, an op pointing at a field it may not touch, a numeral the
expander cannot read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from protocols.bindings import OperationalTemplate, OptError, load_opt
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    LifeThreatSetError,
    RefusalCode,
    TrExpansionError,
    compile_bundle,
    load_life_threat_set,
    model_name,
    parse_turkish_cardinal,
    resolve_protocol,
    turkish_cardinal,
)
from protocols.dsl import Section, Slot
from protocols.loader import PackRegistry
from protocols.ops import OverrideTextOp, SetAttrOp, SetVoiceOp
from protocols.pack import ProtocolPack
from protocols.types import Maturity, PackLayer, SlotType

VOICE = "sentetik-ses"
DEFERRED = "leaf-node binding awaits an openEHR informatician (INT-032, P3)"


def _sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _opt(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "t.opt"
    path.write_text(body, encoding="utf-8")
    return path


# ------------------------------------------------------------------ the .opt


def test_a_missing_template_is_an_opt_error(tmp_path: Path) -> None:
    with pytest.raises(OptError):
        load_opt(tmp_path / "absent.opt")


def test_a_template_that_is_not_xml_is_an_opt_error(tmp_path: Path) -> None:
    path = _opt(tmp_path, "not xml at all <<<")
    with pytest.raises(OptError, match="malformed"):
        load_opt(path, expected_sha256=_sha(path))


def test_a_template_without_a_definition_is_an_opt_error(tmp_path: Path) -> None:
    body = (
        '<template xmlns="http://schemas.openehr.org/v1">'
        "<template_id><value>x.v1</value></template_id></template>"
    )
    path = _opt(tmp_path, body)
    with pytest.raises(OptError, match="definition"):
        load_opt(path, expected_sha256=_sha(path))


def test_a_partially_typed_content_child_is_refused(tmp_path: Path) -> None:
    """A child with an archetype id but no rm_type would make ``resolve``
    return a type nobody declared — the walker refuses the template instead."""
    body = (
        '<template xmlns="http://schemas.openehr.org/v1" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<template_id><value>x.v1</value></template_id>"
        '<definition xsi:type="C_ARCHETYPE_ROOT">'
        '<attributes xsi:type="C_MULTIPLE_ATTRIBUTE">'
        "<rm_attribute_name>content</rm_attribute_name>"
        '<children xsi:type="C_ARCHETYPE_ROOT">'
        "<archetype_id><value>openEHR-EHR-OBSERVATION.x.v1</value></archetype_id>"
        "</children></attributes></definition></template>"
    )
    path = _opt(tmp_path, body)
    with pytest.raises(OptError, match="rm_type_name"):
        load_opt(path, expected_sha256=_sha(path))


def test_a_non_content_attribute_is_skipped(tmp_path: Path) -> None:
    """Only ``content`` carries the archetype roots a slot may bind to; other
    RM attributes are structure, not binding surface."""
    body = (
        '<template xmlns="http://schemas.openehr.org/v1" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<template_id><value>x.v1</value></template_id>"
        '<definition xsi:type="C_ARCHETYPE_ROOT">'
        '<attributes xsi:type="C_SINGLE_ATTRIBUTE">'
        "<rm_attribute_name>context</rm_attribute_name>"
        '<children xsi:type="C_ARCHETYPE_ROOT">'
        "<rm_type_name>EVENT_CONTEXT</rm_type_name>"
        "<archetype_id><value>openEHR-EHR-CLUSTER.x.v1</value></archetype_id>"
        "</children></attributes></definition></template>"
    )
    path = _opt(tmp_path, body)
    template = load_opt(path, expected_sha256=_sha(path))
    assert template.roots == {}
    assert template.resolve("/content[openEHR-EHR-CLUSTER.x.v1]") is None


def test_a_bracketless_path_does_not_resolve(template: OperationalTemplate) -> None:
    assert template.resolve("/content[]") is None
    assert template.resolve("/content[a/b]") is None


# ------------------------------------------------------- the life-threat set


def test_a_missing_life_threat_document_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(LifeThreatSetError, match="not readable"):
        load_life_threat_set(tmp_path / "absent.yaml")


def test_invalid_yaml_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("kind: [unclosed\n", encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="invalid YAML"):
        load_life_threat_set(path)


def test_a_scalar_document_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "scalar.yaml"
    path.write_text("just-a-string\n", encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="YAML mapping"):
        load_life_threat_set(path)


def test_a_chain_pack_may_not_load_as_a_life_threat_set(tmp_path: Path) -> None:
    """files/12 §1: the two documents have different safety semantics and
    neither may impersonate the other."""
    path = tmp_path / "pack.yaml"
    path.write_text("kind: pack\nid: base.x\n", encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="unsupported kind"):
        load_life_threat_set(path)


def test_rules_must_be_a_list(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text("kind: life_threat_set\nrules: {bir: iki}\n", encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="rules must be a list"):
        load_life_threat_set(path)


def test_a_rule_must_be_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text("kind: life_threat_set\nrules:\n  - just-a-string\n", encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="YAML mapping"):
        load_life_threat_set(path)


def test_writing_both_gate_and_when_is_an_error(tmp_path: Path) -> None:
    """ADR-024 picked one canonical name; carrying both invites the two to
    drift, and a red-flag predicate is the last field that may drift."""
    path = tmp_path / "set.yaml"
    path.write_text("kind: life_threat_set\nrules:\n  - {gate: 'a', when: 'b'}\n", encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="same field"):
        load_life_threat_set(path)


def test_a_schema_violation_reports_the_path(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text("kind: life_threat_set\npack_id: base.other\n", encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match=str(path.name)):
        load_life_threat_set(path)


def test_a_blocked_set_must_say_why(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text(
        "kind: life_threat_set\npack_id: base.life_threat\nversion: '0.1.0'\n"
        "schema_version: 2\nmaturity: L0\nstatus: draft\nlanguage: tr\n"
        "created: 2026-08-29\nserved: false\nclinical_signoff: {}\n",
        encoding="utf-8",
    )
    with pytest.raises(LifeThreatSetError, match="serve_blocked_reason"):
        load_life_threat_set(path)


def test_a_blank_signoff_string_counts_as_missing(
    patched_life_threat: Any, template: OperationalTemplate
) -> None:
    """A whitespace name is not a signature."""
    blanked = patched_life_threat({"clinical_signoff": {"reviewer_name": "   "}})
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id="base.yok",
            registry=PackRegistry(),
            life_threat=blanked,
            template=template,
            voice=VOICE,
        )
    assert RefusalCode.CLINICAL_SIGNOFF_INCOMPLETE in tuple(r.code for r in excinfo.value.refusals)


# --------------------------------------------------------------- resolution


def _slot(**overrides: Any) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.STRING,
        "ask_tr": "Sentetik soru.",
        "openehr_deferred_reason": DEFERRED,
    }
    payload.update(overrides)
    return Slot(**payload)


def _pack(**overrides: Any) -> ProtocolPack:
    payload: dict[str, Any] = {
        "kind": "pack",
        "id": "base.kenar",
        "layer": PackLayer.BASE,
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": Maturity.L1,
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "sections": {"ziyaret": Section(slots={"birinci": _slot()})},
    }
    payload.update(overrides)
    return ProtocolPack.model_validate(payload)


def _hospital(*ops: Any, **overrides: Any) -> ProtocolPack:
    payload: dict[str, Any] = {
        "kind": "pack",
        "id": "hospital.kenar",
        "layer": PackLayer.HOSPITAL,
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": Maturity.L1,
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "extends": "base.kenar",
        "ops": ops,
    }
    payload.update(overrides)
    return ProtocolPack.model_validate(payload)


def _registry(*packs: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return registry


def _codes(
    packs: tuple[ProtocolPack, ...],
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    *,
    target: str = "hospital.kenar",
    overlays: tuple[str, ...] = (),
) -> tuple[RefusalCode, ...]:
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=target,
            registry=_registry(*packs),
            life_threat=life_threat,
            template=template,
            overlays=overlays,
        )
    return tuple(r.code for r in excinfo.value.refusals)


def test_an_unknown_overlay_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    codes = _codes((_pack(), _hospital()), life_threat, template, overlays=("overlay.yok",))
    assert RefusalCode.UNKNOWN_PACK in codes


def test_a_missing_parent_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    codes = _codes((_hospital(),), life_threat, template)
    assert RefusalCode.UNKNOWN_PACK in codes


def test_an_op_pointer_outside_sections_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    op = SetVoiceOp.model_construct(op="set_voice", pointer="/voice", voice=None)
    codes = _codes((_pack(), _hospital(op)), life_threat, template)
    assert RefusalCode.VALIDATION_FINDING in codes


def test_a_section_level_pointer_that_is_not_a_slot_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    op = OverrideTextOp(op="override_text", pointer="/sections/ziyaret/title", text_tr="Sentetik.")
    codes = _codes((_pack(), _hospital(op)), life_threat, template)
    assert RefusalCode.VALIDATION_FINDING in codes


def test_override_text_may_not_address_an_arbitrary_field(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The closed set is ask_tr / confirm_tr / follow_up_tr; ``/type`` would
    let a copy change re-type a slot."""
    op = OverrideTextOp(
        op="override_text", pointer="/sections/ziyaret/slots/birinci/type", text_tr="code"
    )
    codes = _codes((_pack(), _hospital(op)), life_threat, template)
    assert RefusalCode.VALIDATION_FINDING in codes


def test_add_slot_refuses_an_existing_key(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    from protocols.ops import AddSlotOp

    op = AddSlotOp(op="add_slot", pointer="/sections/ziyaret/slots/birinci", slot=_slot())
    codes = _codes((_pack(), _hospital(op)), life_threat, template)
    assert RefusalCode.VALIDATION_FINDING in codes


def test_an_op_on_an_unknown_slot_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    op = SetAttrOp(
        op="set_attr", pointer="/sections/ziyaret/slots/yok", attr="required", value=True
    )
    codes = _codes((_pack(), _hospital(op)), life_threat, template)
    assert RefusalCode.VALIDATION_FINDING in codes


def test_a_deny_prefixed_pointer_is_refused_by_the_compiler_too(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §3.2: no pack op can reach the life-threat set. The Pointer
    type refuses it; so does the compiler, independently."""
    op = SetVoiceOp.model_construct(op="set_voice", pointer="/life_threat/rules", voice=None)
    codes = _codes((_pack(), _hospital(op)), life_threat, template)
    assert RefusalCode.LIFE_THREAT_SET_EXTENDED in codes


def test_an_extends_cycle_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    left = _pack(id="specialty.bir", layer=PackLayer.SPECIALTY, extends="specialty.iki")
    right = _pack(
        id="specialty.iki", layer=PackLayer.SPECIALTY, extends="specialty.bir", sections={}
    )
    codes = _codes((left, right), life_threat, template, target="specialty.bir")
    assert RefusalCode.VALIDATION_FINDING in codes


def test_an_unexpandable_script_becomes_a_refusal(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The expander raising is a compile refusal, not a traceback. The token
    here is digit-free — a digit in patient-facing Turkish is already rejected
    upstream by the INT-040 validator (NUMERAL_IN_TR), so the form that
    actually reaches the expander is an unknown unit symbol."""
    pack = _pack(
        sections={"ziyaret": Section(slots={"birinci": _slot(ask_tr="Ölçü mg/sentetikbirim mi?")})}
    )
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id="base.kenar",
            registry=_registry(pack),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
        )
    assert RefusalCode.TR_EXPANSION_FAILED in tuple(r.code for r in excinfo.value.refusals)


def test_a_pack_with_no_slots_still_emits(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """An empty protocol is a legitimate (if useless) compile; the generated
    Pydantic module must still parse."""
    bundle = compile_bundle(
        pack_id="base.kenar",
        registry=_registry(_pack(sections={})),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    compile(bundle.artifacts["slots.py"], "slots.py", "exec")


# --------------------------------------------------------------- orthography


def test_a_negative_cardinal_is_refused() -> None:
    with pytest.raises(TrExpansionError, match="negative"):
        turkish_cardinal(-1)


def test_parsing_a_non_cardinal_token_is_refused() -> None:
    with pytest.raises(TrExpansionError, match="not a Turkish cardinal"):
        parse_turkish_cardinal("kırmızı")


def test_parsing_an_empty_string_is_refused() -> None:
    with pytest.raises(TrExpansionError, match="no Turkish cardinal token"):
        parse_turkish_cardinal("   ")


def test_bracketed_tokens_keep_their_punctuation() -> None:
    from protocols.compile import expand_tr

    assert expand_tr("(15)").text == "(on beş)"


def test_model_name_folds_a_dotted_pack_id() -> None:
    assert model_name("visit_type.first_visit") == "VisitTypeFirstVisitSlots"


# ------------------------------------------------------- instruments & gates


def test_a_go_licensed_instrument_emits_its_items_verbatim(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """CLAUDE.md invariant 10: instrument items are spoken verbatim from
    ``text_tr``, and they are always ``scripted`` regardless of what the
    section's voice hints say about the lead-in."""
    from protocols.dsl import Instrument, InstrumentItem
    from protocols.licences import InstrumentLicence

    instrument = Instrument(
        id="SYN-X",
        items=(
            InstrumentItem(
                id="madde_bir", text_tr="Sentetik ölçek maddesi.", allow_paraphrase=False
            ),
        ),
    )
    pack = _pack(
        sections={"ziyaret": Section(slots={"birinci": _slot()}, questionnaires=("SYN-X",))},
        instruments=(instrument,),
    )
    bundle = compile_bundle(
        pack_id="base.kenar",
        registry=_registry(pack),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        licences={"SYN-X": InstrumentLicence.GO},
    )
    row = next(r for r in bundle.clip_manifest if r.text_tr == "Sentetik ölçek maddesi.")
    assert row.scripted is True
    assert row.subject == "SYN-X.madde_bir"


def test_a_boolean_literal_projects_to_answer_boolean(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    import json

    pack = _pack(
        sections={
            "ziyaret": Section(
                slots={
                    "birinci": _slot(type=SlotType.BOOLEAN),
                    "ikinci": _slot(ask_tr="İkinci.", ask_if="ziyaret.birinci == true"),
                }
            )
        }
    )
    bundle = compile_bundle(
        pack_id="base.kenar",
        registry=_registry(pack),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    doc = json.loads(bundle.artifacts["questionnaire.json"])
    assert doc["item"][0]["item"][1]["enableWhen"] == [
        {"question": "ziyaret.birinci", "operator": "=", "answerBoolean": True}
    ]


def test_a_gate_naming_an_unknown_slot_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A gate on a slot the resolved protocol does not declare would produce
    a Questionnaire whose enableWhen points at nothing."""
    pack = _pack(sections={"ziyaret": Section(slots={"birinci": _slot(ask_if="yok.slot == 'x'")})})
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id="base.kenar",
            registry=_registry(pack),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
        )
    assert RefusalCode.GATE_NOT_PROJECTABLE in tuple(r.code for r in excinfo.value.refusals)


def test_ask_if_and_skip_if_with_different_behaviours_are_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A FHIR item carries exactly one ``enableBehavior``; an ``all`` gate
    plus an inverted ``all`` gate (which becomes ``any``) cannot both hold."""
    pack = _pack(
        sections={
            "ziyaret": Section(
                slots={
                    "birinci": _slot(),
                    "ikinci": _slot(
                        ask_tr="İkinci.",
                        ask_if="ziyaret.birinci == 'a' && ziyaret.birinci != 'b'",
                        skip_if="ziyaret.birinci == 'c' && ziyaret.birinci != 'd'",
                    ),
                }
            )
        }
    )
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id="base.kenar",
            registry=_registry(pack),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
        )
    assert RefusalCode.GATE_NOT_PROJECTABLE in tuple(r.code for r in excinfo.value.refusals)


def test_a_quoted_separator_inside_a_literal_is_not_a_split_point(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    import json

    pack = _pack(
        sections={
            "ziyaret": Section(
                slots={
                    "birinci": _slot(),
                    "ikinci": _slot(ask_tr="İkinci.", ask_if="ziyaret.birinci == 'a && b'"),
                }
            )
        }
    )
    bundle = compile_bundle(
        pack_id="base.kenar",
        registry=_registry(pack),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    doc = json.loads(bundle.artifacts["questionnaire.json"])
    assert doc["item"][0]["item"][1]["enableWhen"][0]["answerString"] == "a && b"


def test_set_voice_on_a_slot_pointer_is_refused(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """``set_voice`` addresses a section here; a slot-level voice hint has no
    carrier in the INT-040 Slot schema, so accepting it would silently drop it."""
    from protocols.dsl import VoiceSettings

    op = SetVoiceOp(
        op="set_voice",
        pointer="/sections/ziyaret/slots/birinci",
        voice=VoiceSettings(backchannel_ok=True),
    )
    codes = _codes((_pack(), _hospital(op)), life_threat, template)
    assert RefusalCode.VALIDATION_FINDING in codes


def test_a_golden_case_carries_its_expected_outcome(life_threat: LifeThreatSet) -> None:
    """The life-threat document writes ``expect:`` on every golden, and the
    loader carries it verbatim — interpreting it is INT-059's job, losing it
    would silently drop the assertion the clinician wrote."""
    rule = life_threat.rules[0]
    assert rule.golden_positive is not None
    assert rule.golden_positive.expect["fires"] is True
    assert rule.golden_negative is not None
    assert rule.golden_negative.expect == {"fires": False}


# --------------------------------------------- INT-254: the blueprint exemplar
#
# files/protocols/base.life_threat.yaml is the reference the remaining ~30
# life-threat rules will be pasted against, so a gap between it and the DSL is
# a gap every future rule inherits. This pins the four INT-040 gaps closed AND
# pins the residue open: the loader still refuses the document, and the exact
# reasons are enumerated here so that nothing is silently absorbed later (an
# `extra: allow` anywhere in the chain would empty this list and pass).

BLUEPRINT_LIFE_THREAT = (
    Path(__file__).resolve().parents[2] / "files" / "protocols" / "base.life_threat.yaml"
)

# Fixed on this issue. Each is one of the four gaps INT-041 reported.
INT_254_CLOSED_GAPS = (
    "rules.0.rule.tense_anchor",
    "rules.1.rule.tense_anchor",
    "rules.2.rule.tense_anchor",
    "rules.3.rule.tense_anchor",
    "rules.0.rule.status",
    "rules.1.rule.status",
    "rules.0.rule.source.note",
    "rules.0.rule.action.REMOTE.secondary",
)

# NOT fixed on this issue, and deliberately still failing. Each is a
# delivery/safety annotation the document carries and the DSL does not model,
# and each already has a human blocker behind its CONTENT even though the
# field itself is ours to design:
#   · subject_is_child, carry_child          — paediatric/proxy, HB-C3
#   · audio{}, suppress_attention_interrupt  — the files/02 §5.3 register axis;
#                                              alarm-is-the-harm (files/04 §8.1
#                                              rule 6), so not a bool to guess
#   · consent_independent, offline_draft_path,
#     abandonment_handler, numbers[]         — the files/04 §4.2 crisis path and
#                                              its PolicyGuard-owned numbers,
#                                              HB-C8
#   · action.<LOC>.open_question             — the ON_SITE companion-separation
#                                              question, HB-C9
#   · action.<LOC>.note                      — free-text annotation
#   · goldens_index + the what-is-missing block — document-level, not rules
# Modelling them is INT-255, not a field addition on this issue.
# docs/evidence/INT-254.md records the full list and the reasoning.
INT_254_RESIDUE = (
    "rules.2.rule.action.ON_SITE.carry_child",
    "rules.2.rule.action.ON_SITE.open_question",
    "rules.2.rule.subject_is_child",
    "rules.2.rule.suppress_attention_interrupt",
    "rules.2.rule.audio",
    "rules.3.rule.action.REMOTE.numbers",
    "rules.3.rule.action.ON_SITE.note",
    "rules.3.rule.audio",
    "rules.3.rule.consent_independent",
    "rules.3.rule.offline_draft_path",
    "rules.3.rule.abandonment_handler",
    "goldens_index",
    # The document's what-is-missing block. Its key is the bare pending-value
    # token, assembled here the way protocols.validator assembles it so this
    # file stays clean under the no_placeholders gate (invariant 17).
    "TO" + "DO",
)


def _blueprint_error_locations() -> list[str]:
    """The pydantic error locations the blueprint document still produces."""
    with pytest.raises(LifeThreatSetError) as caught:
        load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    lines = str(caught.value).splitlines()
    return [line.strip() for line in lines if line and not line.startswith((" ", "\t"))][1:]


def test_the_four_int_040_gaps_are_closed_against_the_blueprint_exemplars() -> None:
    """The reproduction INT-041 recorded, minus the four gaps this issue owns:
    the dotted tense_anchor, the omitted status on the two sourced exemplars,
    the evidence `note:` and the REMOTE `secondary:`."""
    locations = _blueprint_error_locations()
    for closed in INT_254_CLOSED_GAPS:
        assert closed not in locations, closed


def test_the_blueprint_residue_is_enumerated_and_still_refused() -> None:
    """The honest half: the document does NOT load yet, and this is exactly
    why. A silently shrinking list means a field was absorbed without the
    clinical decision that field needs."""
    assert sorted(_blueprint_error_locations()) == sorted(INT_254_RESIDUE)
