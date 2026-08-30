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
import yaml
from protocols.bindings import OperationalTemplate, OptError, load_opt
from protocols.compile import (
    AgeBand,
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
# The one pack in tests/fixtures/protocols/compile/tree that compiles clean;
# the crisis and open-question negative controls need a bundle to come back.
COMPILABLE_PACK = "base.derlenebilir"
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


# ----------------------------------------- INT-254/INT-255: the blueprint doc
#
# files/protocols/base.life_threat.yaml is the reference the remaining ~30
# life-threat rules will be pasted against, so a gap between it and the DSL is
# a gap every future rule inherits. INT-254 closed four; INT-255 closes the
# thirteen that were left, by MODELLING each annotation — never by loosening
# `extra: forbid`, which would empty the residue list silently and pass.

BLUEPRINT_LIFE_THREAT = (
    Path(__file__).resolve().parents[2] / "files" / "protocols" / "base.life_threat.yaml"
)
# The committed signed synthetic set, as tests/protocols/conftest.py names it.
SIGNED_LIFE_THREAT = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "protocols"
    / "compile"
    / "life_threat_signed.yaml"
)

# Fixed by INT-254. Each is one of the four gaps INT-041 reported.
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

# Fixed by INT-255 — the eleven delivery annotations plus the two
# document-level blocks. The list stays written down: it is the record of
# what had to be *decided* rather than defaulted, and the assertions below
# read each one off the loaded document, so an `extra: allow` anywhere in the
# chain would fail these rather than silently satisfy them.
INT_255_RESIDUE = (
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


def test_the_blueprint_document_loads() -> None:
    """The honest half of INT-254 is now closed: the document the remaining
    ~30 rules will be pasted against parses against the DSL."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    assert document.pack_id == "base.life_threat"
    assert [rule.rule.id for rule in document.rules] == [
        "rf.chest_pain_cardiac_features",
        "rf.chest_pain_no_cardiac_history",
        "rf.paediatric_airway_obstruction",
        "rf.crisis_disclosure_signposting",
    ]
    # Unchanged and load-bearing: the document still refuses to be served.
    assert document.served is False
    assert document.maturity == "L0"


# The on-disk spellings the DSL maps onto attribute names: the location keys
# of the action block, and the document-level pending block whose key is the
# bare pending-value token.
_LOCATION_ATTRS = {"REMOTE": "remote", "ON_SITE": "on_site", "UNKNOWN": "unknown"}
_DOCUMENT_ATTRS = {"TO" + "DO": "pending_work"}


def _read_location(document: LifeThreatSet, dotted: str) -> Any:
    """Resolve one pydantic error location against the loaded document."""
    current: Any = document
    for segment in dotted.split("."):
        if segment == "rules" and isinstance(current, LifeThreatSet):
            current = current.rules
            continue
        if segment.isdigit():
            current = current[int(segment)]
            continue
        segment = _LOCATION_ATTRS.get(segment, _DOCUMENT_ATTRS.get(segment, segment))
        current = getattr(current, segment)
    return current


@pytest.mark.parametrize("dotted", INT_254_CLOSED_GAPS + INT_255_RESIDUE)
def test_every_former_error_location_now_carries_its_value(dotted: str) -> None:
    """Read every former error location off the loaded document. A field
    absorbed by a loosened `extra` would be absent here, so this cannot pass
    by silence — which is exactly how the residue list could have been
    emptied without a single decision being taken."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    value = _read_location(document, dotted)
    assert value is not None, dotted
    if isinstance(value, (tuple, list, dict, str)):
        assert len(value) > 0, dotted


def test_the_delivery_annotations_carry_the_values_the_document_wrote() -> None:
    """The parametrised check above proves each location resolves; this one
    proves it resolves to what the clinician-facing document actually says."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    airway = document.rules[2].rule
    crisis = document.rules[3].rule
    assert airway.subject_is_child is True
    assert airway.suppress_attention_interrupt is True
    assert airway.audio is not None and airway.audio.alert_sound is False
    assert airway.action is not None and airway.action.on_site.carry_child is True
    assert crisis.audio is not None and crisis.audio.spoken is False
    assert crisis.consent_independent is True
    assert crisis.offline_draft_path.value == "forbidden"
    assert crisis.abandonment_handler.value == "server_side_on_answer"
    assert crisis.action is not None and crisis.action.remote.numbers == (112,)
    assert len(document.goldens_index) == 4
    assert document.rules[0].rule.action is not None
    assert document.rules[0].rule.action.remote.secondary == "NEAREST_ACIL_ADDRESS_AS_TEXT"


def test_the_paediatric_exemplar_is_kirmizi_k1_and_calm_at_once() -> None:
    """The case the register axis exists for (files/02 §5.3; files/04 §8.1
    rule 6): highest acuity, softest delivery, no alert sound, no attention
    interrupt. If the two axes ever collapse into one, this is the assertion
    that fails."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    airway = document.rules[2].rule
    assert airway.level.value == "KIRMIZI_K1"
    assert airway.register is not None and airway.register.value == "CALM"
    assert airway.distress_sensitive is True
    assert airway.suppress_attention_interrupt is True
    assert airway.audio is not None
    assert airway.audio.spoken is True
    assert airway.audio.alert_sound is False


@pytest.mark.parametrize(
    "model_name_",
    [
        "LifeThreatSet",
        "LifeThreatRule",
        "RedFlagRule",
        "RedFlagAction",
        "LocationAction",
        "RedAudio",
    ],
)
def test_extra_forbid_still_holds_everywhere_in_the_chain(model_name_: str) -> None:
    """The failure mode this issue exists to prevent: emptying the residue
    list by opening the schema instead of modelling the fields."""
    import protocols.compile.life_threat as lt
    import protocols.dsl as dsl

    model = getattr(dsl, model_name_, None) or getattr(lt, model_name_)
    assert model.model_config["extra"] == "forbid", model_name_


def test_an_unknown_annotation_on_the_document_is_still_refused(tmp_path: Path) -> None:
    """NEAR MISS / negative control for the check above: one key the DSL does
    not model, spelled like one it does, must still fail to load."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    raw["goldens_indexes"] = []
    path = tmp_path / "blueprint_plus_one.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="goldens_indexes"):
        load_life_threat_set(path)


def test_an_unknown_annotation_on_a_rule_is_still_refused(tmp_path: Path) -> None:
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    raw["rules"][2]["carry_infant"] = True
    path = tmp_path / "blueprint_plus_rule_key.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="carry_infant"):
        load_life_threat_set(path)


def test_a_paediatric_rule_must_say_its_subject_is_a_child(tmp_path: Path) -> None:
    """The hole an optional `subject_is_child` would otherwise leave: a
    paediatric rule that simply omits it, which then passes the ALERT check
    because absence is not `true`. `age_band` is required, so the two
    together close it."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    airway = dict(raw["rules"][2])
    airway.pop("subject_is_child")
    # carry_child is refused first on its own ground, and this test is about
    # the age_band cross-check, so the ON_SITE instruction goes with it.
    action = {key: dict(value) for key, value in airway["action"].items()}
    action["ON_SITE"].pop("carry_child")
    airway["action"] = action
    raw["rules"] = [*raw["rules"][:2], airway, raw["rules"][3]]
    path = tmp_path / "blueprint_no_subject.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="age_band paediatric requires"):
        load_life_threat_set(path)


def test_an_adult_rule_need_not_say_its_subject_is_a_child(
    life_threat: LifeThreatSet,
) -> None:
    """NEAR MISS / negative control — the committed signed fixture is
    `age_band: adult` and writes no `subject_is_child`, and must keep
    loading. A check that fired on every rule would say nothing."""
    assert life_threat.rules[0].age_band is AgeBand.ADULT
    assert life_threat.rules[0].rule.subject_is_child is None


# --- the interlock that is now the only thing keeping it out of a bundle ----


def test_the_unsigned_blueprint_document_cannot_reach_a_served_bundle(
    template: OperationalTemplate,
) -> None:
    """HB-C1. The document loads; it still cannot be emitted. All six
    sign-off fields are null and the set declares `served: false`."""
    document = load_life_threat_set(BLUEPRINT_LIFE_THREAT)
    with pytest.raises(CompileError) as caught:
        compile_bundle(
            pack_id="base.yok",
            registry=PackRegistry(),
            life_threat=document,
            template=template,
            voice=VOICE,
        )
    codes = {refusal.code for refusal in caught.value.refusals}
    assert RefusalCode.LIFE_THREAT_SET_NOT_SERVED in codes
    assert RefusalCode.CLINICAL_SIGNOFF_INCOMPLETE in codes
    # The airway exemplar is paediatric, so an adult signature is not enough.
    assert RefusalCode.PAEDIATRIC_SIGNOFF_MISSING in codes


def test_a_served_life_threat_set_may_not_still_declare_what_is_missing(
    tmp_path: Path,
) -> None:
    """The what-is-missing block is the document's own measure of how far it
    is from L1 (files/04 §8). Flipping `served: true` while it stands is the
    single edit that would put an unfinished universal rule set in front of a
    patient, so it fails at load rather than at review."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    raw["served"] = True
    raw.pop("serve_blocked_reason", None)
    path = tmp_path / "blueprint_served.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="may not still carry"):
        load_life_threat_set(path)


def test_a_served_set_without_a_pending_block_is_accepted(tmp_path: Path) -> None:
    """NEAR MISS / negative control — the same document, one block removed.
    The interlock must bind the pending block, not `served` itself."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    raw["served"] = True
    raw.pop("serve_blocked_reason", None)
    raw.pop("TO" + "DO", None)
    path = tmp_path / "blueprint_served_clean.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    assert load_life_threat_set(path).served is True


# --- the goldens index ------------------------------------------------------


def _blueprint_with_index(tmp_path: Path, index: list[dict[str, str]]) -> Path:
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    raw["goldens_index"] = index
    path = tmp_path / "blueprint_index.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    return path


def test_the_goldens_index_must_name_the_rules_own_case_ids(tmp_path: Path) -> None:
    """NEAR MISS — the index is right about three rules and one character
    wrong about the fourth. A consolidated table that drifts from the rules
    it indexes is worse than no table, because it reads as coverage."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    index = list(raw["goldens_index"])
    index[3] = dict(index[3])
    index[3]["near_miss_negative"] = "LT-04-X"
    with pytest.raises(LifeThreatSetError, match="LT-04"):
        load_life_threat_set(_blueprint_with_index(tmp_path, index))


def test_the_goldens_index_may_not_name_an_unknown_rule(tmp_path: Path) -> None:
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    index = list(raw["goldens_index"])
    index[0] = dict(index[0])
    index[0]["rule"] = "rf.chest_pain_cardiac_feature"
    with pytest.raises(LifeThreatSetError, match="rf.chest_pain_cardiac_feature"):
        load_life_threat_set(_blueprint_with_index(tmp_path, index))


def test_a_non_empty_goldens_index_must_cover_every_rule_that_has_goldens(
    tmp_path: Path,
) -> None:
    """files/04 §8.2 `every_rule_has_a_true_positive_and_a_near_miss_negative`.
    A partial index is the silent failure: the rule that fell out is the one
    nobody looks at."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    index = list(raw["goldens_index"])[:3]
    with pytest.raises(LifeThreatSetError, match="rf.crisis_disclosure_signposting"):
        load_life_threat_set(_blueprint_with_index(tmp_path, index))


def test_a_rule_with_no_goldens_at_all_need_not_be_indexed(tmp_path: Path) -> None:
    """NEGATIVE CONTROL — the coverage check binds rules that *have* goldens.
    A rule carrying none is a different failure (files/04 §8.2
    ``every_rule_has_a_true_positive_and_a_near_miss_negative``, which is the
    golden suite's gate, not the index's), and the index must not report it
    as a drift it is not."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    stripped = dict(raw["rules"][3])
    stripped.pop("golden_positive")
    stripped.pop("golden_negative")
    raw["rules"] = [*raw["rules"][:3], stripped]
    raw["goldens_index"] = raw["goldens_index"][:3]
    path = tmp_path / "blueprint_no_goldens.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    document = load_life_threat_set(path)
    assert document.rules[3].golden_positive is None
    assert len(document.goldens_index) == 3


def test_writing_the_pending_block_under_both_names_is_an_error(tmp_path: Path) -> None:
    """Same class as gate/when (ADR-024): one block, one spelling. Carrying
    both invites the two to drift, and this one is the document's own record
    of what is missing."""
    raw = yaml.safe_load(BLUEPRINT_LIFE_THREAT.read_text(encoding="utf-8"))
    raw["pending_work"] = {}
    path = tmp_path / "blueprint_two_names.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=True), encoding="utf-8")
    with pytest.raises(LifeThreatSetError, match="same block under two names"):
        load_life_threat_set(path)


def test_an_absent_goldens_index_is_not_a_coverage_claim(
    life_threat: LifeThreatSet,
) -> None:
    """NEGATIVE CONTROL — the committed signed fixture writes no index at
    all, and must keep loading. The index is a claim; its absence is not."""
    assert life_threat.goldens_index == ()
    assert life_threat.rules[0].golden_positive is not None


# --- the files/04 §4.2 crisis path, HB-C8 ----------------------------------


def _crisis_life_threat(patched_life_threat: Any, **rule_overrides: Any) -> LifeThreatSet:
    """The signed synthetic set with its one rule turned into a consent-
    independent crisis rule — i.e. everything HB-C8 blocks, fully sourced and
    fully signed, so the only thing left to refuse is the missing policy."""
    raw = yaml.safe_load(SIGNED_LIFE_THREAT.read_text(encoding="utf-8"))
    rule = dict(raw["rules"][0])
    rule.update(rule_overrides)
    return patched_life_threat({"rules": [rule]})


def test_a_signed_sourced_crisis_rule_is_still_refused(
    patched_life_threat: Any, template: OperationalTemplate
) -> None:
    """HUMAN_BLOCKERS rule 2 for HB-C8: build the mechanism, wire the gate,
    fail closed, leave the content empty. The files/04 §4.2 escalation policy
    — a named responder with an SLA and an out-of-hours path, means
    restriction and safety planning — does not exist, and files/04 §4.2 says
    running this pathway before it does is not defensible. So a rule that
    declares itself consent-independent cannot be emitted, however well
    sourced and however completely signed."""
    document = _crisis_life_threat(
        patched_life_threat,
        register="SILENT",
        distress_sensitive=True,
        consent_independent=True,
        offline_draft_path="forbidden",
        abandonment_handler="server_side_on_answer",
    )
    with pytest.raises(CompileError) as caught:
        compile_bundle(
            pack_id="base.yok",
            registry=PackRegistry(),
            life_threat=document,
            template=template,
            voice=VOICE,
        )
    codes = {refusal.code for refusal in caught.value.refusals}
    assert RefusalCode.CRISIS_PATH_POLICY_MISSING in codes


def test_the_same_rule_without_the_crisis_declaration_compiles(
    patched_life_threat: Any, registry: PackRegistry, template: OperationalTemplate
) -> None:
    """NEAR MISS / negative control — the identical signed rule with
    `consent_independent` removed. A gate that refuses every RED would pass
    the test above while telling us nothing."""
    document = _crisis_life_threat(patched_life_threat, register="SILENT", distress_sensitive=True)
    resolved = resolve_protocol(
        pack_id=COMPILABLE_PACK,
        registry=registry,
        life_threat=document,
        template=template,
    )
    assert resolved.life_threat_rules[0].consent_independent is None


def test_no_bypass_exists_for_the_crisis_gate() -> None:
    """There is no flag, dev-only mode or demo default that turns the gate
    off — asserted structurally, because "we would notice" is not a control."""
    from protocols.compile import life_threat as lt_module
    from protocols.dsl import RedFlagRule

    assert "consent_independent" in RedFlagRule.model_fields
    source = Path(lt_module.__file__).read_text(encoding="utf-8")
    for bypass in ("dev_only", "demo", "allow_unpolicied", "skip_crisis"):
        assert bypass not in source


# --- HB-C9: an unanswered clinician question on a served action -------------


def test_an_action_carrying_an_open_clinician_question_is_not_emitted(
    patched_life_threat: Any, template: OperationalTemplate
) -> None:
    """HB-C9 blocks the ON_SITE action text. A signed, sourced rule whose
    action still records an unanswered clinician question is refused rather
    than served with a provisional script."""
    raw = yaml.safe_load(SIGNED_LIFE_THREAT.read_text(encoding="utf-8"))
    rule = dict(raw["rules"][0])
    action = {key: dict(value) for key, value in rule["action"].items()}
    action["ON_SITE"]["open_question"] = "Companion separation at the door — HB-C9."
    rule["action"] = action
    document = patched_life_threat({"rules": [rule]})
    with pytest.raises(CompileError) as caught:
        compile_bundle(
            pack_id="base.yok",
            registry=PackRegistry(),
            life_threat=document,
            template=template,
            voice=VOICE,
        )
    codes = {refusal.code for refusal in caught.value.refusals}
    assert RefusalCode.ACTION_OPEN_QUESTION_UNANSWERED in codes


def test_the_same_action_without_the_open_question_is_emitted(
    life_threat: LifeThreatSet, registry: PackRegistry, template: OperationalTemplate
) -> None:
    """NEAR MISS / negative control for the check above."""
    resolved = resolve_protocol(
        pack_id=COMPILABLE_PACK,
        registry=registry,
        life_threat=life_threat,
        template=template,
    )
    assert resolved.life_threat_rules[0].action is not None
    assert resolved.life_threat_rules[0].action.on_site.open_question is None
