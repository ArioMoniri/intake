"""INT-041 — the failure paths that only run when something is malformed.

A fail-closed compiler is mostly error handling, and error handling that is
never executed is error handling nobody knows is wrong. These are the
defensive branches: a template that will not parse, a life-threat document
that is not one, an op pointing at a field it may not touch, a numeral the
expander cannot read.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
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

SIGNED_LIFE_THREAT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "protocols"
    / "compile"
    / "life_threat_signed.yaml"
)

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


# ------------------------------------- INT-254/INT-255: the blueprint exemplar
#
# files/protocols/base.life_threat.yaml is the reference the remaining ~30
# life-threat rules will be pasted against, so a gap between it and the DSL is
# a gap every future rule inherits. INT-041 reported 21 validation errors,
# INT-254 closed eight of them and enumerated the thirteen it left open, and
# INT-255 models the rest. The list below is therefore empty — which is only
# meaningful alongside the negative control that `extra: forbid` still binds
# every level of the document.

BLUEPRINT_LIFE_THREAT = (
    Path(__file__).resolve().parents[2] / "files" / "protocols" / "base.life_threat.yaml"
)

# Closed on INT-254. Each was one of the four gaps INT-041 reported.
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

INT_254_RESIDUE: tuple[str, ...] = ()
"""Empty since INT-255. Each of the thirteen error locations INT-254 left
open is now a modelled field:

  · ``subject_is_child`` / ``carry_child``   — files/02 §5.3 Axis 2 CALM row
  · ``audio{spoken,prosody,alert_sound}``    — the register table's Audio column
  · ``suppress_attention_interrupt``         — files/04 §8.1 rule 6
  · ``consent_independent`` / ``offline_draft_path`` /
    ``abandonment_handler`` / ``numbers[]``  — the files/04 §4.2 crisis path
  · ``action.<LOC>.open_question``           — HB-C9, recorded not resolved
  · ``action.<LOC>.note``                    — free-text provenance commentary
  · ``goldens_index`` / the what-is-missing block — document level

The list may only shrink by MODELLING. An ``extra: allow`` anywhere in the
chain would empty it silently and pass, which is what
``test_extra_forbid_still_binds_every_level_of_the_document`` exists to catch.
"""

# One unknown key per level of the document, for that negative control. The
# paths mirror files/protocols/base.life_threat.yaml exactly.
UNKNOWN_KEY_PATHS: tuple[tuple[str, tuple[str | int, ...]], ...] = (
    ("document", ()),
    ("rule", ("rules", 0)),
    ("action", ("rules", 0, "action", "REMOTE")),
    ("unknown branch", ("rules", 0, "action", "UNKNOWN")),
    ("evidence", ("rules", 0, "evidence")),
    ("golden case", ("rules", 0, "golden_positive")),
    ("audio", ("rules", 2, "audio")),
    ("goldens index entry", ("goldens_index", 0)),
)


def _blueprint_document() -> dict[str, Any]:
    import yaml

    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def _write(tmp_path: Path, document: Mapping[str, Any]) -> Path:
    import yaml

    path = tmp_path / "life_threat_probe.yaml"
    path.write_text(
        yaml.safe_dump(dict(document), allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return path


def test_the_blueprint_life_threat_document_loads() -> None:
    """The whole point of INT-254 and INT-255: the reference document every
    future rule is pasted against is now expressible in the DSL."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    assert document.pack_id == "base.life_threat"
    assert len(document.rules) == 4
    assert document.served is False


def test_the_four_int_040_gaps_are_closed_against_the_blueprint_exemplars() -> None:
    """INT-254's four gaps, re-asserted on the loaded document rather than on
    an error list: the dotted tense_anchor, the stated status on the two
    sourced exemplars, the evidence `note:` and the REMOTE `secondary:`."""
    rules = load_life_threat_set(BLUEPRINT_LIFE_THREAT).rules
    assert INT_254_CLOSED_GAPS  # the list is the record of what was closed
    assert rules[0].rule.tense_anchor == "chest_pain.onset_at"
    assert rules[0].rule.status.value == "active"
    assert rules[1].rule.status.value == "active"
    assert rules[0].rule.source is not None
    assert rules[0].rule.source.note is not None
    assert rules[0].rule.action is not None
    assert rules[0].rule.action.remote.secondary == "NEAREST_ACIL_ADDRESS_AS_TEXT"


def test_the_blueprint_residue_is_empty_because_the_fields_are_modelled() -> None:
    """The honest half of INT-254 is now closed. Every annotation named in
    that list resolves to a field on the loaded document."""
    assert INT_254_RESIDUE == ()
    rules = load_life_threat_set(BLUEPRINT_LIFE_THREAT).rules
    airway, crisis = rules[2].rule, rules[3].rule
    assert airway.subject_is_child is True
    assert airway.suppress_attention_interrupt is True
    assert airway.audio is not None
    assert (airway.audio.spoken, airway.audio.alert_sound) == (True, False)
    assert airway.action is not None
    assert airway.action.on_site.carry_child is True
    assert airway.action.on_site.open_question is not None
    assert crisis.consent_independent is True
    assert crisis.offline_draft_path is not None
    assert crisis.abandonment_handler is not None
    assert crisis.action is not None
    assert [int(n) for n in crisis.action.remote.numbers] == [112]
    assert crisis.action.on_site.note is not None


@pytest.mark.parametrize(
    ("level", "path"), UNKNOWN_KEY_PATHS, ids=[name for name, _ in UNKNOWN_KEY_PATHS]
)
def test_extra_forbid_still_binds_every_level_of_the_document(
    tmp_path: Path, level: str, path: tuple[str | int, ...]
) -> None:
    """THE NEGATIVE CONTROL for the empty residue. An empty error list means
    "modelled" only if the document is still closed; `extra: allow` anywhere
    in the chain would empty the list just as effectively and pass every
    other test in this file."""
    document = _blueprint_document()
    target: Any = document
    for step in path:
        target = target[step]
    assert isinstance(target, dict), level
    target["sentetik_bilinmeyen_alan"] = "SENTETİK TEST VERİSİ"
    with pytest.raises(LifeThreatSetError, match="sentetik_bilinmeyen_alan"):
        load_life_threat_set(_write(tmp_path, document))


def test_the_document_level_pending_block_is_modelled(tmp_path: Path) -> None:
    """The what-is-missing block is the honest measure of how far from L1 the
    set is (files/04 §8). It is carried, not discarded — and a set that
    declares itself served while still carrying one is refused."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    assert document.pending_work is not None
    assert "remaining_adult_rules" in document.pending_work

    raw = _blueprint_document()
    raw["served"] = True
    raw["serve_blocked_reason"] = None
    with pytest.raises(LifeThreatSetError, match="what-is-missing"):
        load_life_threat_set(_write(tmp_path, raw))


def test_a_served_set_with_no_pending_block_is_not_refused_for_that(tmp_path: Path) -> None:
    """NEAR-MISS NEGATIVE for the check above: removing the block is what
    lifts the refusal, so the check is about the block and not about
    `served: true`."""
    raw = _blueprint_document()
    raw["served"] = True
    raw["serve_blocked_reason"] = None
    raw.pop("TO" + "DO")
    assert load_life_threat_set(_write(tmp_path, raw)).served is True


def test_the_goldens_index_must_agree_with_the_rules(tmp_path: Path) -> None:
    """files/04 §8.2 every_rule_has_a_true_positive_and_a_near_miss_negative:
    an index that disagrees with the rules is worse than no index, because it
    reads as coverage."""
    raw = _blueprint_document()
    raw["goldens_index"][0]["near_miss_negative"] = "LT-01-YOK"
    with pytest.raises(LifeThreatSetError, match="LT-01-YOK"):
        load_life_threat_set(_write(tmp_path, raw))

    raw = _blueprint_document()
    raw["goldens_index"][0]["rule"] = "rf.olmayan_kural"
    with pytest.raises(LifeThreatSetError, match="rf.olmayan_kural"):
        load_life_threat_set(_write(tmp_path, raw))

    raw = _blueprint_document()
    del raw["goldens_index"][2]
    with pytest.raises(LifeThreatSetError, match="rf.paediatric_airway_obstruction"):
        load_life_threat_set(_write(tmp_path, raw))


def test_a_document_without_a_goldens_index_is_still_loadable(tmp_path: Path) -> None:
    """NEAR-MISS NEGATIVE: the index is a cross-check on the goldens the rules
    already carry, not a second place to declare them. The committed compiler
    fixture has no index and must keep loading."""
    raw = _blueprint_document()
    del raw["goldens_index"]
    assert load_life_threat_set(_write(tmp_path, raw)).goldens_index == ()


def test_a_paediatric_rule_states_whether_its_subject_is_a_child(tmp_path: Path) -> None:
    """Both halves of the coupling: age_band decides which reviewer signs
    (HB-C1) and subject_is_child decides the delivery register
    (files/02 §5.3), and neither may be inferred from the other's silence."""
    raw = _blueprint_document()
    del raw["rules"][2]["subject_is_child"]
    with pytest.raises(LifeThreatSetError, match="subject_is_child"):
        load_life_threat_set(_write(tmp_path, raw))

    raw = _blueprint_document()
    raw["rules"][2]["age_band"] = "adult"
    with pytest.raises(LifeThreatSetError, match="paediatrician"):
        load_life_threat_set(_write(tmp_path, raw))


def test_an_adult_rule_need_not_state_subject_is_child(tmp_path: Path) -> None:
    """NEAR-MISS NEGATIVE: the requirement is scoped to paediatric rules. The
    two adult chest-pain exemplars carry no subject_is_child and must load."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    assert document.rules[0].rule.subject_is_child is None
    assert document.rules[0].age_band.value == "adult"


def test_the_blueprint_refusals_are_all_human_blockers(
    template: OperationalTemplate,
) -> None:
    """The acceptance sentence, asserted: with every annotation modelled, the
    only reasons the compiler still refuses the blueprint document are the
    open human blockers — the sign-off block (HB-C1), the two unsourced
    exemplars (files/04 §8.1 rule 3), the crisis escalation policy (HB-C8) and
    the companion-separation question (HB-C9). Not one is a schema gap."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    with pytest.raises(CompileError) as caught:
        resolve_protocol(
            pack_id="specialty.olmayan",
            registry=PackRegistry(),
            life_threat=document,
            template=template,
        )
    codes = {r.code for r in caught.value.refusals}
    assert codes == {
        RefusalCode.LIFE_THREAT_SET_NOT_SERVED,
        RefusalCode.CLINICAL_SIGNOFF_INCOMPLETE,
        RefusalCode.PAEDIATRIC_SIGNOFF_MISSING,
        RefusalCode.DRAFT_RULE_NOT_SERVED,
        RefusalCode.CRISIS_ESCALATION_POLICY_ABSENT,
        RefusalCode.ACTION_OPEN_QUESTION,
        RefusalCode.UNKNOWN_PACK,
    }


def test_the_crisis_path_is_refused_until_the_escalation_policy_exists(
    template: OperationalTemplate, tmp_path: Path
) -> None:
    """HB-C8, wired as a gate rather than a note. files/04 §4.2 states that
    running this pathway before the escalation policy exists is not
    defensible; the policy does not exist, so a consent-independent rule is
    never compiled into a served pack. There is no bypass and no dev flag
    (HUMAN_BLOCKERS rule 2)."""
    raw = yaml.safe_load(SIGNED_LIFE_THREAT.read_text(encoding="utf-8"))
    rule = raw["rules"][0]
    rule["consent_independent"] = True
    rule["offline_draft_path"] = "forbidden"
    rule["abandonment_handler"] = "server_side_on_answer"
    rule["register"] = "SILENT"
    probe = tmp_path / "crisis.yaml"
    probe.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    crisis = load_life_threat_set(probe)
    with pytest.raises(CompileError) as caught:
        resolve_protocol(
            pack_id="specialty.olmayan",
            registry=PackRegistry(),
            life_threat=crisis,
            template=template,
        )
    codes = {r.code for r in caught.value.refusals}
    assert RefusalCode.CRISIS_ESCALATION_POLICY_ABSENT in codes


def test_a_rule_without_the_crisis_path_is_not_refused_for_it(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """NEAR-MISS NEGATIVE: the committed signed fixture is a fully sourced,
    signed, servable set. If the crisis refusal fired on it too, the gate
    would be a blanket refusal rather than a gate."""
    with pytest.raises(CompileError) as caught:
        resolve_protocol(
            pack_id="specialty.olmayan",
            registry=PackRegistry(),
            life_threat=life_threat,
            template=template,
        )
    codes = {r.code for r in caught.value.refusals}
    assert codes == {RefusalCode.UNKNOWN_PACK}


def test_an_open_clinician_question_keeps_a_rule_out_of_a_served_pack(
    template: OperationalTemplate, tmp_path: Path
) -> None:
    """HB-C9. The question is recorded on the action, and recording it is not
    the same as answering it — so the rule carrying it is not servable."""
    raw = yaml.safe_load(SIGNED_LIFE_THREAT.read_text(encoding="utf-8"))
    raw["rules"][0]["action"]["ON_SITE"]["open_question"] = (
        "Companion separation at the door — Tebliğ MADDE 9(1). HB-C9."
    )
    probe = tmp_path / "open_question.yaml"
    probe.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    with pytest.raises(CompileError) as caught:
        resolve_protocol(
            pack_id="specialty.olmayan",
            registry=PackRegistry(),
            life_threat=load_life_threat_set(probe),
            template=template,
        )
    codes = {r.code for r in caught.value.refusals}
    assert RefusalCode.ACTION_OPEN_QUESTION in codes
