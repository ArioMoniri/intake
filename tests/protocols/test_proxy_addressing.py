"""INT-483 / ADR-040 — subject-aware addressing in the DSL and the compiler.

Owner decision D24, answer 1Y: in a proxy session every self-addressed
question is reworded for the patient or skipped, and the child and carer paths
stay closed until that mechanism exists. These tests pin the mechanism and its
closed state:

* the DSL can say, per slot, "reworded for the proxy" or "skipped in a proxy
  session", and nothing in between;
* the compiler refuses a proxy path while any self-addressed slot of the
  resolved chain — inherited base items included — lacks that handling;
* a red-flag probe is never skippable in a proxy session and never addressed
  to the speaker (CLAUDE.md invariant 7);
* the proxy bundle speaks the pack's own proxy text verbatim (invariant 10).

Every Turkish string below is SYNTHETIC test text (files/04 §7) on the
INT-041 compiler fixture. None of it is proxy copy for a real pack: which item
is reworded and which is skipped is a D18 clinical decision, and no pack in
the tree carries a proxy block (the last test pins that).
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.addressing import Addressee, Addressing, ProxyAddressing
from protocols.bindings import OperationalTemplate
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    RefusalCode,
    compile_bundle,
    load_life_threat_set,
    resolve_protocol,
    write_bundle,
)
from protocols.compile.proxy_path import slot_origins
from protocols.dsl import Slot
from protocols.licences import InstrumentLicence
from protocols.loader import PackRegistry, load_pack
from protocols.pack import ProtocolPack
from protocols.validator import FindingCode, validate_packs
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "protocols" / "compile" / "tree" / "base" / "intake.yaml"
)
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
LIFE_THREAT_SET = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"
PACK_TREES = (
    REPO_ROOT / "packages" / "protocols" / "base",
    REPO_ROOT / "packages" / "protocols" / "specialty",
    REPO_ROOT / "packages" / "protocols" / "review",
)
PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"

# --- synthetic proxy text (test-only; never proxy copy for a real pack) -------

VEKIL_NEDEN = "Sentetik vekil sorusu: yakınınızı bugün buraya getiren nedir?"
VEKIL_NEDEN_TEKRAR = "Sentetik vekil sorusu: yakınınızın en önemli şikâyeti nedir?"
VEKIL_SURE = "Sentetik vekil sorusu: yakınınızın şikâyeti ne kadar sürüyor?"
VEKIL_SURE_ONAY = "Sentetik vekil onayı: mg cinsinden mi?"
VEKIL_SURE_TEKRAR = "Sentetik vekil sorusu: yaklaşık olarak söyleyebilir misiniz?"
VEKIL_SESSIZ = "Sentetik vekil metin-yalnız sorusu."

SELF_NEDEN = "Bugün sizi buraya getiren nedir?"


def _text(value: str) -> dict[str, str]:
    return {"tr": value}


def _raw() -> dict[str, Any]:
    loaded = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _slot(raw: dict[str, Any], section: str, key: str) -> dict[str, Any]:
    slot = raw["sections"][section]["slots"][key]
    assert isinstance(slot, dict)
    return slot


def _handled() -> dict[str, Any]:
    """The fixture with every askable patient-addressed slot handled.

    ``ziyaret.basvuru_nedeni`` (read by both red-flag rules' ``when``) and
    ``ziyaret.sure_dakika`` (their ``tense_anchor``) are red-flag probes, so
    they are reworded. ``renk_secimi`` and ``tarama.sessiz_soru`` are free to
    take either form; one of each is used.
    """
    raw = _raw()
    _slot(raw, "ziyaret", "basvuru_nedeni")["proxy"] = {
        "ask_tr": _text(VEKIL_NEDEN),
        "follow_up_tr": _text(VEKIL_NEDEN_TEKRAR),
    }
    _slot(raw, "ziyaret", "sure_dakika")["proxy"] = {
        "ask_tr": _text(VEKIL_SURE),
        "confirm_tr": _text(VEKIL_SURE_ONAY),
        "follow_up_tr": _text(VEKIL_SURE_TEKRAR),
    }
    _slot(raw, "ziyaret", "renk_secimi")["proxy"] = {"skip": True}
    _slot(raw, "tarama", "sessiz_soru")["proxy"] = {"ask_tr": _text(VEKIL_SESSIZ)}
    return raw


def _registry(*raws: dict[str, Any]) -> PackRegistry:
    registry = PackRegistry()
    for raw in raws:
        registry.add(ProtocolPack.model_validate(raw))
    return registry


def _refusals(
    raw: dict[str, Any],
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    *,
    addressing: Addressing,
) -> dict[RefusalCode, list[str]]:
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=PACK_ID,
            registry=_registry(raw),
            life_threat=life_threat,
            template=template,
            addressing=addressing,
        )
    grouped: dict[RefusalCode, list[str]] = {}
    for refusal in excinfo.value.refusals:
        grouped.setdefault(refusal.code, []).append(refusal.subject)
    return grouped


# --- the DSL -------------------------------------------------------------------


def test_a_slot_is_patient_addressed_unless_it_says_otherwise() -> None:
    """Silence is read as self-addressed: every slot authored before ADR-040
    speaks to the patient in the second person, so it needs proxy handling."""
    slot = Slot.model_validate({"type": "string", "ask_tr": _text(SELF_NEDEN)})
    assert slot.addressee is Addressee.PATIENT
    assert slot.proxy is None


def test_a_proxy_block_is_reworded_or_skipped_never_both() -> None:
    with pytest.raises(ValidationError, match="reworded OR skipped"):
        ProxyAddressing.model_validate({"skip": True, "ask_tr": _text(VEKIL_NEDEN)})
    # near miss: either half alone is well formed
    assert ProxyAddressing.model_validate({"skip": True}).skip
    assert ProxyAddressing.model_validate({"ask_tr": _text(VEKIL_NEDEN)}).ask_tr is not None


def test_a_proxy_block_that_does_not_skip_carries_its_own_question() -> None:
    """No runtime rewording exists, so an empty block would leave the proxy
    session with nothing verbatim to say (invariant 10)."""
    with pytest.raises(ValidationError, match="must carry its own ask_tr"):
        ProxyAddressing.model_validate({})
    with pytest.raises(ValidationError, match="must carry its own ask_tr"):
        ProxyAddressing.model_validate({"follow_up_tr": _text(VEKIL_NEDEN_TEKRAR)})


def test_a_speaker_addressed_slot_carries_no_proxy_block() -> None:
    with pytest.raises(ValidationError, match="speaker"):
        Slot.model_validate(
            {
                "type": "string",
                "addressee": "speaker",
                "ask_tr": _text(SELF_NEDEN),
                "proxy": {"skip": True},
            }
        )
    near_miss = Slot.model_validate(
        {"type": "string", "addressee": "speaker", "ask_tr": _text(SELF_NEDEN)}
    )
    assert near_miss.addressee is Addressee.SPEAKER


def _findings(raw: dict[str, Any]) -> list[tuple[FindingCode, str]]:
    return [(finding.code, finding.subject) for finding in validate_packs(_registry(raw))]


def test_a_rewording_speaks_every_text_the_self_form_speaks() -> None:
    """A second-person follow-up after a reworded question is the same defect
    one turn later. A pack finding rather than a schema error, so that a
    merged slot a hospital copy change made inconsistent stays representable
    and the compiler can name it (PROXY_TEXT_INCOMPLETE below)."""
    raw = _handled()
    _slot(raw, "ziyaret", "basvuru_nedeni")["proxy"] = {"ask_tr": _text(VEKIL_NEDEN)}
    assert _findings(raw) == [(FindingCode.PROXY_TEXT_MISMATCH, "ziyaret.basvuru_nedeni")]
    # near miss: the complete rewording of _handled()
    assert _findings(_handled()) == []


def test_a_proxy_text_with_no_self_counterpart_is_a_finding() -> None:
    raw = _handled()
    _slot(raw, "tarama", "sessiz_soru")["proxy"] = {
        "ask_tr": _text(VEKIL_SESSIZ),
        "confirm_tr": _text(VEKIL_SURE_ONAY),
    }
    assert _findings(raw) == [(FindingCode.PROXY_TEXT_MISMATCH, "tarama.sessiz_soru")]


def test_a_slot_with_no_question_cannot_be_reworded_into_one() -> None:
    raw = _handled()
    del _slot(raw, "tarama", "sessiz_soru")["ask_tr"]
    assert _findings(raw) == [(FindingCode.PROXY_TEXT_MISMATCH, "tarama.sessiz_soru")]


def test_a_mismatched_rewording_refuses_on_every_path(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    raw = _handled()
    _slot(raw, "ziyaret", "basvuru_nedeni")["proxy"] = {"ask_tr": _text(VEKIL_NEDEN)}
    for addressing in Addressing:
        grouped = _refusals(raw, life_threat, template, addressing=addressing)
        assert grouped[RefusalCode.VALIDATION_FINDING] == [
            "base.derlenebilir:ziyaret.basvuru_nedeni"
        ]


def test_a_numeral_in_proxy_text_is_a_validation_finding() -> None:
    """Invariant 22 reaches the proxy form: it is spoken like any question."""
    raw = _handled()
    _slot(raw, "tarama", "sessiz_soru")["proxy"] = {"ask_tr": _text("Sentetik vekil 3 sorusu.")}
    findings = validate_packs(_registry(raw))
    assert [(f.code, f.subject) for f in findings] == [
        (FindingCode.NUMERAL_IN_TR, "tarama.sessiz_soru@tr")
    ]
    assert _findings(_handled()) == []


# --- the compiler: the self path ------------------------------------------------


def test_the_self_path_is_the_default_and_projects_nothing(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    document = resolve_protocol(
        pack_id=PACK_ID, registry=_registry(_handled()), life_threat=life_threat, template=template
    )
    assert document.addressing is Addressing.SELF
    slots = {slot.fhir_link_id: slot for section in document.sections for slot in section.slots}
    assert not any(slot.proxy_skipped for slot in slots.values())
    neden = slots["ziyaret.basvuru_nedeni"].slot.ask_tr
    assert neden is not None and neden["tr"] == SELF_NEDEN


def test_a_pack_with_no_proxy_handling_still_compiles_on_the_self_path(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The mechanism closes the proxy path only; the self bundle is unchanged."""
    bundle = compile_bundle(
        pack_id=PACK_ID,
        registry=_registry(_raw()),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    assert bundle.addressing is Addressing.SELF
    assert "addressing" not in yaml.safe_load(bundle.artifacts["manifest.json"])


# --- the compiler: the proxy path ----------------------------------------------


def test_a_proxy_path_with_one_unhandled_self_addressed_must_ask_refuses(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    raw = _handled()
    del _slot(raw, "ziyaret", "basvuru_nedeni")["proxy"]
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {RefusalCode.PROXY_ADDRESSING_MISSING: ["ziyaret.basvuru_nedeni"]}


def test_the_same_pack_compiles_on_the_proxy_path_once_every_item_is_handled(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The near miss of the test above: one block more and the path opens."""
    bundle = compile_bundle(
        pack_id=PACK_ID,
        registry=_registry(_handled()),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        addressing=Addressing.PROXY,
    )
    assert bundle.addressing is Addressing.PROXY
    manifest = yaml.safe_load(bundle.artifacts["manifest.json"])
    assert manifest["addressing"] == "proxy"


def test_an_unhandled_slot_that_is_not_must_ask_also_refuses(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Fail closed past the must-ask set: an optional question spoken in the
    second person to a proxy fills the patient's slot with the speaker's own
    answer just the same, and defaulting it to "skip" would be a clinical
    decision taken by the compiler."""
    raw = _handled()
    del _slot(raw, "ziyaret", "renk_secimi")["proxy"]
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {RefusalCode.PROXY_ADDRESSING_MISSING: ["ziyaret.renk_secimi"]}


def test_a_speaker_addressed_slot_needs_no_proxy_handling(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    raw = _handled()
    del _slot(raw, "ziyaret", "renk_secimi")["proxy"]
    _slot(raw, "ziyaret", "renk_secimi")["addressee"] = "speaker"
    document = resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.PROXY,
    )
    assert document.addressing is Addressing.PROXY


def test_the_proxy_bundle_speaks_the_packs_proxy_text_verbatim(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Invariant 10: what the proxy hears is the pack's own proxy text, in the
    clip manifest and in the Questionnaire; the self text is not in the
    proxy bundle's clip manifest at all."""
    bundle = compile_bundle(
        pack_id=PACK_ID,
        registry=_registry(_handled()),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        addressing=Addressing.PROXY,
    )
    spoken = {row.text_tr for row in bundle.clip_manifest}
    assert {VEKIL_NEDEN, VEKIL_NEDEN_TEKRAR, VEKIL_SURE_TEKRAR} <= spoken
    assert SELF_NEDEN not in spoken
    questionnaire = yaml.safe_load(bundle.artifacts["questionnaire.json"])
    items = {item["linkId"]: item for group in questionnaire["item"] for item in group["item"]}
    assert items["ziyaret.basvuru_nedeni"]["text"] == VEKIL_NEDEN


def test_a_skipped_slot_is_not_spoken_and_not_offered_in_the_proxy_bundle(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    document = resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(_handled()),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.PROXY,
    )
    skipped = [
        slot.fhir_link_id
        for section in document.sections
        for slot in section.slots
        if slot.proxy_skipped
    ]
    assert skipped == ["ziyaret.renk_secimi"]
    bundle = compile_bundle(
        pack_id=PACK_ID,
        registry=_registry(_handled()),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        addressing=Addressing.PROXY,
    )
    assert "ziyaret.renk_secimi" not in {row.subject for row in bundle.clip_manifest}
    questionnaire = yaml.safe_load(bundle.artifacts["questionnaire.json"])
    link_ids = {item["linkId"] for group in questionnaire["item"] for item in group["item"]}
    assert "ziyaret.renk_secimi" not in link_ids
    # the slot itself stays in the schema: it exists, it is just never asked
    assert "ziyaret.renk_secimi" in bundle.artifacts["slots.py"]


# --- invariant 7: a red-flag probe stays asked ----------------------------------


@pytest.mark.parametrize(
    ("key", "why"),
    [
        ("basvuru_nedeni", "read by the rules' when"),
        ("sure_dakika", "the rules' tense_anchor"),
    ],
)
def test_a_red_flag_probe_marked_skip_in_proxy_refuses(
    key: str, why: str, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    raw = _handled()
    _slot(raw, "ziyaret", key)["proxy"] = {"skip": True}
    for addressing in Addressing:
        grouped = _refusals(raw, life_threat, template, addressing=addressing)
        assert grouped == {RefusalCode.PROXY_SKIPS_RED_FLAG_PROBE: [f"ziyaret.{key}"]}, why


def test_a_skip_on_a_slot_no_rule_reads_is_the_near_miss(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    raw = _handled()
    _slot(raw, "tarama", "sessiz_soru")["proxy"] = {"skip": True}
    document = resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.PROXY,
    )
    assert {
        slot.fhir_link_id
        for section in document.sections
        for slot in section.slots
        if slot.proxy_skipped
    } == {"ziyaret.renk_secimi", "tarama.sessiz_soru"}


def test_a_slot_in_the_red_flags_section_is_a_probe_before_any_rule_reads_it(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/04 §1 row 4: the families' triggers are unsigned (HB-C1), so no
    rule reads their probes yet. A probe must not become skippable in that gap."""
    raw = _handled()
    raw["sections"]["red_flags"] = {
        "delivery": "voice",
        "slots": {
            "rf_sentetik": {
                "type": "boolean",
                "openehr_deferred_reason": "synthetic probe; no binding in this fixture",
                "ask_tr": _text("Sentetik kırmızı bayrak sorusu?"),
                "proxy": {"skip": True},
            }
        },
    }
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.SELF)
    assert grouped == {RefusalCode.PROXY_SKIPS_RED_FLAG_PROBE: ["red_flags.rf_sentetik"]}


def test_a_red_flag_probe_cannot_be_addressed_to_the_speaker(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The speaker's own answer would fill the patient's rule slot — the
    chest-pain stop-gap's hazard (CD-01 F13) by another door."""
    raw = _handled()
    del _slot(raw, "ziyaret", "basvuru_nedeni")["proxy"]
    _slot(raw, "ziyaret", "basvuru_nedeni")["addressee"] = "speaker"
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.SELF)
    assert grouped == {RefusalCode.RED_FLAG_PROBE_SPEAKER_ADDRESSED: ["ziyaret.basvuru_nedeni"]}


def _with_identity_section(raw: dict[str, Any]) -> dict[str, Any]:
    raw = copy.deepcopy(raw)
    raw["sections"] = {
        "identity_check": {
            "delivery": "voice",
            "slots": {
                "subject_role": {
                    "type": "code",
                    "valueset": "vs.subject_role",
                    "required": True,
                    "must_ask": True,
                    "addressee": "speaker",
                    "openehr_deferred_reason": "session fact in this synthetic fixture",
                    "ask_tr": _text("Sentetik kimlik sorusu?"),
                    "choices_tr": {"tr": ["kendim için", "yakınım adına"]},
                    "follow_up_tr": _text("Sentetik kimlik tekrar sorusu?"),
                }
            },
        },
        **raw["sections"],
    }
    return raw


def test_a_red_flag_probe_gated_on_the_subject_role_refuses_on_the_proxy_path(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The base pack's chest-pain stop-gap (``skip_if`` on the subject role)
    skips a probe in exactly the sessions ADR-040 says must still ask it."""
    raw = _with_identity_section(_handled())
    _slot(raw, "ziyaret", "basvuru_nedeni")["skip_if"] = (
        "identity_check.subject_role == 'yakınım adına'"
    )
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {RefusalCode.RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE: ["ziyaret.basvuru_nedeni"]}
    # near miss 1: the same gate is legal on the self path, where it is the
    # stop-gap CD-01 sanctions until proxy text exists
    resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.SELF,
    )


def test_a_patient_question_gated_on_the_subject_role_refuses_on_the_proxy_path(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A gate that closes in a proxy session skips the question with no
    NOT_ASKED_PROXY, no coverage gap and no note line; the skip has to be the
    explicit ``proxy: skip`` instead."""
    raw = _with_identity_section(_handled())
    _slot(raw, "tarama", "sessiz_soru")["ask_if"] = "subject_role == 'kendim için'"
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {RefusalCode.PROXY_GATED_ON_SUBJECT_ROLE: ["tarama.sessiz_soru"]}


def test_a_speaker_question_gated_on_the_subject_role_is_the_near_miss(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """A question about whoever holds the device (``proxy_reported`` in the
    base pack) may follow the role: nobody's clinical answer is lost."""
    raw = _with_identity_section(_handled())
    sessiz = _slot(raw, "tarama", "sessiz_soru")
    del sessiz["proxy"]
    sessiz["addressee"] = "speaker"
    sessiz["ask_if"] = "subject_role == 'yakınım adına'"
    document = resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.PROXY,
    )
    assert document.addressing is Addressing.PROXY


def test_a_probe_gated_through_another_slot_on_the_subject_role_refuses(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The reach is transitive: a probe whose gate reads a slot whose gate
    reads the subject role is decided by the role all the same."""
    raw = _with_identity_section(_handled())
    _slot(raw, "tarama", "sessiz_soru")["ask_if"] = "subject_role == 'kendim için'"
    _slot(raw, "ziyaret", "basvuru_nedeni")["ask_if"] = "tarama.sessiz_soru == true"
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {
        RefusalCode.PROXY_GATED_ON_SUBJECT_ROLE: ["tarama.sessiz_soru"],
        RefusalCode.RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE: ["ziyaret.basvuru_nedeni"],
    }


def test_a_probe_gated_on_a_speaker_question_refuses(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The speaker's own answer would decide whether the patient's probe is
    asked at all."""
    raw = _with_identity_section(_handled())
    sessiz = _slot(raw, "tarama", "sessiz_soru")
    del sessiz["proxy"]
    sessiz["addressee"] = "speaker"
    _slot(raw, "ziyaret", "basvuru_nedeni")["ask_if"] = "tarama.sessiz_soru == true"
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {RefusalCode.RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE: ["ziyaret.basvuru_nedeni"]}
    # near miss: the same probe gated on a patient-addressed, reworded slot
    raw = _with_identity_section(_handled())
    _slot(raw, "ziyaret", "basvuru_nedeni")["ask_if"] = "tarama.sessiz_soru == true"
    resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.PROXY,
    )


def test_a_skipped_slot_cannot_silently_close_the_gate_of_a_question_asked_after_it(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/13 §9.5: a question behind a gate that never opens is silently
    never asked. A skipped slot reads Unknown, so a gate on it never opens."""
    raw = _handled()
    raw["sections"]["ziyaret"]["slots"]["renk_tonu"] = {
        "type": "string",
        "ask_if": "ziyaret.renk_secimi == 'mavi'",
        "openehr_deferred_reason": "synthetic dependent; no binding in this fixture",
        "ask_tr": _text("Sentetik ton sorusu?"),
        "proxy": {"ask_tr": _text("Sentetik vekil ton sorusu?")},
    }
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {RefusalCode.PROXY_SKIP_CLOSES_GATE: ["ziyaret.renk_tonu"]}
    # near miss: the dependent is skipped too, so nothing is silently dropped
    raw["sections"]["ziyaret"]["slots"]["renk_tonu"]["proxy"] = {"skip": True}
    resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.PROXY,
    )


def test_a_copy_change_that_adds_a_spoken_field_reopens_the_gap(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The DSL checks a rewording against its own slot; a hospital
    ``override_text`` can still add a field the proxy form lacks, so the
    compiler checks the merged slot again."""
    hospital = {
        "kind": "pack",
        "id": "hospital.sentetik",
        "layer": "hospital",
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": "L1",
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "extends": PACK_ID,
        "ops": [
            {
                "op": "override_text",
                "pointer": "/sections/tarama/slots/sessiz_soru/follow_up_tr",
                "text_tr": _text("Sentetik hastane tekrar metni."),
            }
        ],
    }
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id="hospital.sentetik",
            registry=_registry(_handled(), hospital),
            life_threat=life_threat,
            template=template,
            addressing=Addressing.PROXY,
        )
    assert [(r.code, r.subject) for r in excinfo.value.refusals] == [
        (RefusalCode.PROXY_TEXT_INCOMPLETE, "tarama.sessiz_soru")
    ]
    # near miss: the same override compiles on the self path
    resolve_protocol(
        pack_id="hospital.sentetik",
        registry=_registry(_handled(), hospital),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.SELF,
    )


# --- the real tree: base.intake and the closed state -----------------------------


def _base_proxy_refusals(
    template: OperationalTemplate, *extra: dict[str, Any], pack_id: str = "base.intake"
) -> dict[RefusalCode, list[str]]:
    registry = PackRegistry()
    registry.add(load_pack(BASE_INTAKE))
    for raw in extra:
        registry.add(ProtocolPack.model_validate(raw))
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=pack_id,
            registry=registry,
            life_threat=load_life_threat_set(LIFE_THREAT_SET),
            template=template,
            addressing=Addressing.PROXY,
        )
    grouped: dict[RefusalCode, list[str]] = {}
    for refusal in excinfo.value.refusals:
        grouped.setdefault(refusal.code, []).append(refusal.subject)
    return grouped


#: The base items INT-470 names as depending on this mechanism (D24 1Y; CD-103
#: cluster-wave-b #L77): a guardian's own pregnancy, complaint history, weight,
#: smoking or alcohol use must never be read as the child's. The first four are
#: must_ask; the last three are not, and are refused all the same.
D24_BASE_MUST_ASK: tuple[str, ...] = (
    "pmh_fh_sh.pregnancy_status",
    "hpi.onset_date",
    "hpi.location_text",
    "hpi.duration",
)
D24_BASE_ITEMS: tuple[str, ...] = (
    *D24_BASE_MUST_ASK,
    "pmh_fh_sh.weight_kg",
    "pmh_fh_sh.smoking_status",
    "pmh_fh_sh.alcohol_use",
)


def test_base_intake_on_the_proxy_path_names_every_self_addressed_askable_slot(
    template: OperationalTemplate,
) -> None:
    pack = load_pack(BASE_INTAKE)
    askable = sorted(
        f"{section_id}.{key}"
        for section_id, section in pack.sections.items()
        for key, slot in section.slots.items()
        if slot.ask_tr is not None
    )
    grouped = _base_proxy_refusals(template)
    assert sorted(grouped[RefusalCode.PROXY_ADDRESSING_MISSING]) == askable
    assert set(D24_BASE_ITEMS) <= set(askable)
    # the CD-01 stop-gap skips a life-threat probe in a proxy session, and the
    # six follow-ups gated on it with it
    assert sorted(grouped[RefusalCode.RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE]) == [
        "associated.diaphoresis",
        "associated.dyspnoea",
        "chest_pain.character",
        "chest_pain.onset_at",
        "chest_pain.present",
        "chest_pain.radiation",
        "trauma.recent",
    ]
    # PHQ-2, GAD-2, PHQ-9 and GAD-7 are self-report by validation
    assert grouped[RefusalCode.PROXY_ADMINISTERS_INSTRUMENT] == ["screening"]


def test_inherited_base_items_keep_a_child_pack_off_the_proxy_path(
    template: OperationalTemplate,
) -> None:
    """A cluster that handles its own slots does not open the proxy path:
    every inherited base item is named, with the pack that declared it."""
    cluster = {
        "kind": "pack",
        "id": "cluster.sentetik_cocuk",
        "layer": "cluster",
        "version": "0.1.0",
        "schema_version": 2,
        "maturity": "L0",
        "status": "awaiting-clinical-review",
        "language": "tr",
        "extends": "base.intake",
        "sections": {
            "sentetik_bolum": {
                "delivery": "voice",
                "slots": {
                    "sentetik_soru": {
                        "type": "boolean",
                        "openehr_deferred_reason": "synthetic cluster slot",
                        "ask_tr": _text("Sentetik küme sorusu?"),
                        "proxy": {"ask_tr": _text("Sentetik vekil küme sorusu?")},
                    }
                },
            }
        },
    }
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id="cluster.sentetik_cocuk",
            registry=_registry_with_base(cluster),
            life_threat=load_life_threat_set(LIFE_THREAT_SET),
            template=template,
            addressing=Addressing.PROXY,
        )
    missing = {
        refusal.subject: refusal.message
        for refusal in excinfo.value.refusals
        if refusal.code is RefusalCode.PROXY_ADDRESSING_MISSING
    }
    assert "sentetik_bolum.sentetik_soru" not in missing
    for item in D24_BASE_ITEMS:
        assert "declared in base.intake" in missing[item]
    for item in D24_BASE_MUST_ASK:
        assert "a must_ask item" in missing[item]
    assert "a must_ask item" not in missing["pmh_fh_sh.weight_kg"]


def _registry_with_base(*raws: dict[str, Any]) -> PackRegistry:
    registry = PackRegistry()
    registry.add(load_pack(BASE_INTAKE))
    for raw in raws:
        registry.add(ProtocolPack.model_validate(raw))
    return registry


def test_base_intake_on_the_self_path_gains_no_refusal_from_the_mechanism(
    template: OperationalTemplate,
) -> None:
    """The self path of the real base pack refuses for its own blockers only
    (L0, unsourced drafts, the unsigned life-threat set) — none of them an
    addressing code."""
    registry = PackRegistry()
    registry.add(load_pack(BASE_INTAKE))
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id="base.intake",
            registry=registry,
            life_threat=load_life_threat_set(LIFE_THREAT_SET),
            template=template,
        )
    addressing_codes = {
        RefusalCode.PROXY_ADDRESSING_MISSING,
        RefusalCode.PROXY_SKIPS_RED_FLAG_PROBE,
        RefusalCode.RED_FLAG_PROBE_SPEAKER_ADDRESSED,
        RefusalCode.RED_FLAG_PROBE_GATED_ON_SUBJECT_ROLE,
        RefusalCode.PROXY_TEXT_INCOMPLETE,
        RefusalCode.PROXY_SKIP_CLOSES_GATE,
        RefusalCode.PROXY_ADMINISTERS_INSTRUMENT,
        RefusalCode.PROXY_GATED_ON_SUBJECT_ROLE,
    }
    assert not {refusal.code for refusal in excinfo.value.refusals} & addressing_codes


def test_no_pack_in_the_tree_carries_proxy_content_yet() -> None:
    """The closed state of D24 1Y, pinned. Proxy text and the reword-or-skip
    choice per item are a D18 clinical decision record's to make; until one
    lands, no pack declares a proxy block or an addressee, so the compiler
    refuses the proxy path for every pack. A content PR that adds them edits
    this test and cites its decision record."""
    declaring: list[str] = []
    for tree in PACK_TREES:
        for path in sorted(tree.rglob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("kind") != "pack":
                continue
            for section_id, section in (raw.get("sections") or {}).items():
                for key, slot in (section.get("slots") or {}).items():
                    if isinstance(slot, dict) and ("proxy" in slot or "addressee" in slot):
                        declaring.append(f"{path.relative_to(REPO_ROOT)}:{section_id}.{key}")
    assert declaring == []


# --- edges: what the addressing pass leaves to other gates --------------------------


def test_the_proxy_bundle_is_written_beside_the_self_bundle_never_over_it(
    tmp_path: Path, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    registry = _registry(_handled())
    paths = {
        addressing: write_bundle(
            compile_bundle(
                pack_id=PACK_ID,
                registry=registry,
                life_threat=life_threat,
                template=template,
                voice=VOICE,
                addressing=addressing,
            ),
            tmp_path,
        )
        for addressing in Addressing
    }
    assert {path.parent for path in paths[Addressing.SELF]} == {tmp_path / PACK_ID}
    assert {path.parent for path in paths[Addressing.PROXY]} == {tmp_path / PACK_ID / "proxy"}


def _with_unreadable_rule(raw: dict[str, Any]) -> dict[str, Any]:
    rule = copy.deepcopy(raw["red_flags"][0])
    rule.update(
        {
            "id": "rf.sentetik_okunamaz",
            "when": "ziyaret.basvuru_nedeni ~~ 'sentetik'",
            "status": "draft_needs_source",
            "source_gap": "synthetic rule whose when is outside the grammar",
        }
    )
    rule.pop("source")
    raw["red_flags"].append(rule)
    return raw


def test_a_skip_beside_a_rule_whose_reads_cannot_be_listed_refuses(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The INT-382 reasoning: an unreadable rule's probes are unknowable, so
    no skip can be shown to spare them."""
    grouped = _refusals(
        _with_unreadable_rule(_handled()), life_threat, template, addressing=Addressing.SELF
    )
    assert grouped[RefusalCode.PROXY_SKIPS_RED_FLAG_PROBE] == ["rf.sentetik_okunamaz"]
    # near miss: no skip anywhere, so nothing is spared or not spared
    raw = _with_unreadable_rule(_handled())
    _slot(raw, "ziyaret", "renk_secimi")["proxy"] = {"ask_tr": _text("Sentetik vekil renk?")}
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.SELF)
    assert RefusalCode.PROXY_SKIPS_RED_FLAG_PROBE not in grouped


def test_a_gate_that_names_no_slot_is_left_to_its_own_refusal(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    raw = _handled()
    _slot(raw, "tarama", "sessiz_soru")["ask_if"] = "bilinmeyen == true"
    grouped = _refusals(raw, life_threat, template, addressing=Addressing.PROXY)
    assert grouped == {RefusalCode.GATE_REF_UNKNOWN: ["tarama.sessiz_soru"]}


def test_a_gate_outside_the_grammar_is_left_to_the_emitter(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    raw = _handled()
    _slot(raw, "tarama", "sessiz_soru")["ask_if"] = "ziyaret.renk_secimi ~~ 'mavi'"
    resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.PROXY,
    )
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id=PACK_ID,
            registry=_registry(raw),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
            addressing=Addressing.PROXY,
        )
    assert {r.code for r in excinfo.value.refusals} == {RefusalCode.GATE_NOT_PROJECTABLE}


def test_an_added_slot_is_named_by_the_pack_that_added_it() -> None:
    cluster = ProtocolPack.model_validate(
        {
            "kind": "pack",
            "id": "cluster.sentetik",
            "layer": "cluster",
            "version": "0.1.0",
            "schema_version": 2,
            "maturity": "L0",
            "status": "awaiting-clinical-review",
            "language": "tr",
            "extends": PACK_ID,
            "ops": [
                {
                    "op": "add_slot",
                    "pointer": "/sections/ziyaret/slots/eklenen",
                    "slot": {"type": "boolean", "ask_tr": _text("Sentetik eklenen soru?")},
                },
                {
                    "op": "add_slot",
                    "pointer": "/sections/ziyaret",
                    "slot": {"type": "boolean", "ask_tr": _text("Sentetik bozuk hedef?")},
                },
            ],
        }
    )
    origins = slot_origins([ProtocolPack.model_validate(_raw()), cluster])
    assert origins[("ziyaret", "eklenen")] == "cluster.sentetik"
    assert origins[("ziyaret", "basvuru_nedeni")] == PACK_ID
    assert len(origins) == 5


def _with_instrument(raw: dict[str, Any]) -> dict[str, Any]:
    raw = copy.deepcopy(raw)
    raw["sections"]["tarama"]["questionnaires"] = ["SYN-X"]
    raw["instruments"] = [
        {
            "id": "SYN-X",
            "items": [
                {
                    "id": "madde_bir",
                    "text_tr": _text("Sentetik ölçek maddesi."),
                    "allow_paraphrase": {"tr": False},
                }
            ],
        }
    ]
    return raw


def test_a_chain_that_administers_an_instrument_has_no_proxy_path(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §2.2: a validated self-report instrument answered by a proxy
    yields InstrumentNotScored, never a number. No engine path implements
    that, so the proxy path is refused rather than served with a score a
    clinician would read as "screened"."""
    raw = _with_instrument(_handled())
    licences = {"SYN-X": InstrumentLicence.GO}
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id=PACK_ID,
            registry=_registry(raw),
            life_threat=life_threat,
            template=template,
            licences=licences,
            addressing=Addressing.PROXY,
        )
    assert [(r.code, r.subject) for r in excinfo.value.refusals] == [
        (RefusalCode.PROXY_ADMINISTERS_INSTRUMENT, "tarama")
    ]
    # near miss: the same chain on the self path
    resolve_protocol(
        pack_id=PACK_ID,
        registry=_registry(raw),
        life_threat=life_threat,
        template=template,
        licences=licences,
        addressing=Addressing.SELF,
    )


def test_a_copy_change_to_a_reworded_slot_leaves_its_proxy_form_unreviewed(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """Every field still exists, but the self form was rewritten under the
    proxy form it was reviewed against."""
    hospital = {
        "kind": "pack",
        "id": "hospital.sentetik",
        "layer": "hospital",
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": "L1",
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "extends": PACK_ID,
        "ops": [
            {
                "op": "override_text",
                "pointer": "/sections/ziyaret/slots/basvuru_nedeni/ask_tr",
                "text_tr": _text("Sentetik hastane sorusu: bugün neden geldiniz?"),
            }
        ],
    }
    with pytest.raises(CompileError) as excinfo:
        resolve_protocol(
            pack_id="hospital.sentetik",
            registry=_registry(_handled(), hospital),
            life_threat=life_threat,
            template=template,
            addressing=Addressing.PROXY,
        )
    assert [(r.code, r.subject) for r in excinfo.value.refusals] == [
        (RefusalCode.PROXY_TEXT_INCOMPLETE, "ziyaret.basvuru_nedeni")
    ]
    assert "override_text" in excinfo.value.refusals[0].message
    # near miss: the same copy change on the self path
    resolve_protocol(
        pack_id="hospital.sentetik",
        registry=_registry(_handled(), hospital),
        life_threat=life_threat,
        template=template,
        addressing=Addressing.SELF,
    )
