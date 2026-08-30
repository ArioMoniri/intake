"""INT-041 — the refusals. Most of this issue is what the compiler will NOT emit.

Each test names the blueprint gate it stands for. The rules under test are
built with ``model_construct`` where the DSL schema (INT-040) already rejects
the shape: the point is that the compiler is a **second, independent** gate,
exactly as files/04 §8.2 asks of ``on_site_action_never_offers_112`` — "asserted
on the compiled action, so an author cannot set the flag true at all".

Everything here is synthetic (files/04 §7).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from typing import Any

import pytest
from protocols.bindings import OperationalTemplate
from protocols.compile import (
    CompileError,
    LifeThreatSet,
    RefusalCode,
    compile_bundle,
)
from protocols.dsl import (
    Instrument,
    InstrumentItem,
    LocationAction,
    RedFlagAction,
    RedFlagRule,
    Section,
    Slot,
    SourceBlock,
    UnknownAction,
    VoiceSettings,
)
from protocols.licences import InstrumentLicence
from protocols.loader import PackRegistry
from protocols.ops import SetVoiceOp
from protocols.pack import ProtocolPack
from protocols.types import (
    Delivery,
    EK4Level,
    Maturity,
    NotifyClinic,
    Pace,
    PackLayer,
    RedFlagRoute,
    RedRegister,
    RuleStatus,
    SlotType,
    Tense,
)

VOICE = "sentetik-ses"
# A synthetic instrument id, so the licence gate is exercised without
# asserting anything about a real instrument (files/04 header table).
SYNTHETIC_LICENCES = {"SYN-X": InstrumentLicence.GO}
SOURCE = SourceBlock(
    guideline_id="SYN-GUIDE-A",
    guideline_title="Sentetik kılavuz A",
    version_or_date="sürüm bir",
    url="https://example.invalid/syn-guide-a",
    retrieved_on=date(2026, 8, 28),
    quote="sentetik alıntı metni",
)


def _remote(*, show_112: bool = True) -> LocationAction:
    return LocationAction(
        primary="CALL_112",
        show_112=show_112,
        action_tr="Hemen yardım isteyin.",
        why_tr="Bu bir sentetik test metnidir.",
    )


def _on_site(*, show_112: bool = False) -> LocationAction:
    return LocationAction(
        primary="GO_TO_IN_HOUSE_ACIL",
        show_112=show_112,
        notify_staff_immediate=True,
        action_tr="Görevlilere haber verin.",
        why_tr="Bu bir sentetik test metnidir.",
    )


def _unknown(ask: str = "Şu anda hastanede misiniz?") -> UnknownAction:
    return UnknownAction(ask_one_tr=ask, on_yes="ON_SITE", on_no="REMOTE", on_no_answer="REMOTE")


def _red_action(**kwargs: Any) -> RedFlagAction:
    payload: dict[str, Any] = {
        "REMOTE": _remote(),
        "ON_SITE": _on_site(),
        "UNKNOWN": _unknown(),
    }
    payload.update(kwargs)
    return RedFlagAction.model_validate(payload)


def _red_rule(**overrides: Any) -> RedFlagRule:
    payload: dict[str, Any] = {
        "id": "rf.sentetik_kirmizi",
        "label_tr": "Sentetik kırmızı kural",
        "when": "ziyaret.basvuru_nedeni == 'sentetik_acil'",
        "tense": Tense.NOW,
        "tense_anchor": "sure_dakika",
        "level": EK4Level.KIRMIZI_K2,
        "route": RedFlagRoute.EMERGENCY_NOW,
        "register": RedRegister.ALERT,
        "notify_clinic": NotifyClinic.ALWAYS,
        "status": RuleStatus.ACTIVE,
        "source": SOURCE,
        "action": _red_action(),
        "distress_sensitive": False,
        "source_gap": None,
    }
    payload.update(overrides)
    # model_construct: the DSL already refuses several of these shapes, and the
    # compiler must refuse them again on its own (files/04 §8.2).
    return RedFlagRule.model_construct(**payload)


def _slot(**overrides: Any) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.STRING,
        "required": True,
        "ask_tr": "Bugün sizi buraya getiren nedir?",
        "follow_up_tr": "En önemli şikâyetinizi söyleyebilir misiniz?",
        "openehr_path": "/content[openEHR-EHR-EVALUATION.reason_for_encounter.v1]",
    }
    payload.update(overrides)
    return Slot(**payload)


def _pack(**overrides: Any) -> ProtocolPack:
    payload: dict[str, Any] = {
        "kind": "pack",
        "id": "base.sentetik_kapali",
        "layer": PackLayer.BASE,
        "version": "1.0.0",
        "schema_version": 2,
        "maturity": Maturity.L1,
        "status": "clinically-reviewed-synthetic",
        "language": "tr",
        "title_tr": "Sentetik kapanış paketi",
        "sections": {"ziyaret": Section(slots={"basvuru_nedeni": _slot()})},
        "red_flags": (_red_rule(),),
    }
    payload.update(overrides)
    return ProtocolPack.model_construct(**payload)


def _registry(*packs: ProtocolPack) -> PackRegistry:
    registry = PackRegistry()
    for pack in packs:
        registry.add(pack)
    return registry


def _refuse(
    pack: ProtocolPack,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    *,
    extra: tuple[ProtocolPack, ...] = (),
    overlays: tuple[str, ...] = (),
) -> tuple[RefusalCode, ...]:
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id=pack.id,
            registry=_registry(pack, *extra),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
            overlays=overlays,
        )
    return tuple(refusal.code for refusal in excinfo.value.refusals)


# --------------------------------------------------------------------------
# HB-C1 — the clinical sign-off interlock.
# --------------------------------------------------------------------------


def test_refuses_an_l1_bundle_while_clinical_signoff_is_empty(
    patched_life_threat: Callable[[Mapping[str, Any]], LifeThreatSet],
    template: OperationalTemplate,
) -> None:
    unsigned = patched_life_threat(
        {
            "served": False,
            "serve_blocked_reason": "L0 / awaiting-clinical-review (synthetic fixture).",
            "clinical_signoff": {
                "reviewer_name": None,
                "reviewer_licence_no": None,
                "reviewer_specialty": None,
                "signed_commit": None,
                "signed_on": None,
                "paediatric_reviewer_name": None,
            },
        }
    )
    codes = _refuse(_pack(), unsigned, template)
    assert RefusalCode.CLINICAL_SIGNOFF_INCOMPLETE in codes


def test_refuses_a_partially_signed_block_naming_every_missing_field(
    patched_life_threat: Callable[[Mapping[str, Any]], LifeThreatSet],
    template: OperationalTemplate,
) -> None:
    partial = patched_life_threat(
        {
            "clinical_signoff": {
                "reviewer_name": "Sentetik Hekim",
                "reviewer_licence_no": None,
                "reviewer_specialty": None,
                "signed_commit": "0" * 40,
                "signed_on": date(2026, 8, 29),
                "paediatric_reviewer_name": None,
            }
        }
    )
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id="base.sentetik_kapali",
            registry=_registry(_pack()),
            life_threat=partial,
            template=template,
            voice=VOICE,
        )
    message = excinfo.value.refusals[0].message
    assert "reviewer_licence_no" in message
    assert "reviewer_specialty" in message


def test_refuses_a_paediatric_rule_without_a_paediatrician_signature(
    patched_life_threat: Callable[[Mapping[str, Any]], LifeThreatSet],
    template: OperationalTemplate,
) -> None:
    """HB-C1: the paediatric reviewer is a SEPARATE signature — an adult
    signature does not cover a rule whose age_band is paediatric."""
    raw_rule = _paediatric_rule_yaml()
    paediatric = patched_life_threat({"rules": [raw_rule]})
    codes = _refuse(_pack(), paediatric, template)
    assert RefusalCode.PAEDIATRIC_SIGNOFF_MISSING in codes


def test_refuses_a_life_threat_set_marked_not_served(
    patched_life_threat: Callable[[Mapping[str, Any]], LifeThreatSet],
    template: OperationalTemplate,
) -> None:
    blocked = patched_life_threat(
        {"served": False, "serve_blocked_reason": "Sentetik servis kilidi."}
    )
    codes = _refuse(_pack(), blocked, template)
    assert RefusalCode.LIFE_THREAT_SET_NOT_SERVED in codes


# --------------------------------------------------------------------------
# Invariant 13 / 17 — maturity and provenance.
# --------------------------------------------------------------------------


def test_refuses_an_l0_pack(life_threat: LifeThreatSet, template: OperationalTemplate) -> None:
    codes = _refuse(_pack(maturity=Maturity.L0), life_threat, template)
    assert RefusalCode.PACK_NOT_SERVABLE in codes


def test_refuses_any_draft_needs_source_rule(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    draft = _red_rule(
        id="rf.sentetik_taslak",
        status=RuleStatus.DRAFT_NEEDS_SOURCE,
        source=None,
        source_gap="Sentetik kaynak boşluğu.",
        level=EK4Level.YESIL,
        register=None,
        action=None,
        notify_clinic=NotifyClinic.NEVER,
    )
    codes = _refuse(_pack(red_flags=(_red_rule(), draft)), life_threat, template)
    assert RefusalCode.DRAFT_RULE_NOT_SERVED in codes


def test_refuses_a_draft_rule_inside_the_life_threat_set(
    patched_life_threat: Callable[[Mapping[str, Any]], LifeThreatSet],
    template: OperationalTemplate,
) -> None:
    drafted = patched_life_threat({"rules": [_draft_life_threat_rule_yaml()]})
    codes = _refuse(_pack(), drafted, template)
    assert RefusalCode.DRAFT_RULE_NOT_SERVED in codes


# --------------------------------------------------------------------------
# Invariant 21 — RED has three axes.
# --------------------------------------------------------------------------


def test_refuses_a_red_rule_without_a_register(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    codes = _refuse(_pack(red_flags=(_red_rule(register=None),)), life_threat, template)
    assert RefusalCode.RED_MISSING_REGISTER in codes


def test_refuses_a_red_rule_whose_action_does_not_resolve(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    codes = _refuse(_pack(red_flags=(_red_rule(action=None),)), life_threat, template)
    assert RefusalCode.RED_ACTION_UNRESOLVED in codes


@pytest.mark.parametrize("missing", ["remote", "on_site", "unknown"])
def test_refuses_a_red_action_missing_any_one_location(
    missing: str, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    action = RedFlagAction.model_construct(remote=_remote(), on_site=_on_site(), unknown=_unknown())
    object.__setattr__(action, missing, None)
    codes = _refuse(_pack(red_flags=(_red_rule(action=action),)), life_threat, template)
    assert RefusalCode.RED_ACTION_UNRESOLVED in codes


def test_refuses_an_on_site_action_that_offers_112(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/04 §8.2 on_site_action_never_offers_112 — under ON_SITE the
    affordance is ABSENT, not de-emphasised (CLAUDE.md invariant 21)."""
    action = RedFlagAction.model_construct(
        remote=_remote(), on_site=_on_site(show_112=True), unknown=_unknown()
    )
    codes = _refuse(_pack(red_flags=(_red_rule(action=action),)), life_threat, template)
    assert RefusalCode.ON_SITE_OFFERS_112 in codes


@pytest.mark.parametrize(
    "ask",
    [
        "Şu anda hastanede misiniz? Yanınızda biri var mı?",
        "Şu anda hastanede misiniz, yanınızda biri var mı?",
    ],
)
def test_refuses_an_unknown_branch_that_asks_more_than_one_question(
    ask: str, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/04 §8.2 unknown_location_asks_exactly_one_question — one
    question, then branch: never two, never zero."""
    action = RedFlagAction.model_construct(
        remote=_remote(), on_site=_on_site(), unknown=_unknown(ask)
    )
    codes = _refuse(_pack(red_flags=(_red_rule(action=action),)), life_threat, template)
    assert RefusalCode.UNKNOWN_NOT_ONE_QUESTION in codes


def test_refuses_an_unknown_branch_that_asks_nothing(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    unknown = UnknownAction.model_construct(
        ask_one_tr="Hastanedesiniz.", on_yes="ON_SITE", on_no="REMOTE", on_no_answer="REMOTE"
    )
    action = RedFlagAction.model_construct(remote=_remote(), on_site=_on_site(), unknown=unknown)
    codes = _refuse(_pack(red_flags=(_red_rule(action=action),)), life_threat, template)
    assert RefusalCode.UNKNOWN_NOT_ONE_QUESTION in codes


def test_accepts_a_single_question_that_ends_in_a_question_mark(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    bundle = compile_bundle(
        pack_id="base.derlenebilir",
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    assert bundle.resolved_protocol_hash


# --------------------------------------------------------------------------
# Invariant 7 — monotonic inheritance, and the sealed sibling set.
# --------------------------------------------------------------------------


def test_refuses_a_child_that_lowers_an_inherited_acuity(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    parent = _pack()
    child = _pack(
        id="specialty.sentetik",
        layer=PackLayer.SPECIALTY,
        extends="base.sentetik_kapali",
        red_flags=(_red_rule(level=EK4Level.SARI_K2),),
    )
    codes = _refuse(child, life_threat, template, extra=(parent,))
    assert RefusalCode.MONOTONICITY_VIOLATION in codes


def test_refuses_a_pack_that_extends_the_life_threat_set(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """CLAUDE.md invariant 7: base.life_threat is a sealed sibling set and
    nothing may extend it (files/12 §1). The schema refuses it; so does the
    compiler, independently."""
    child = _pack(
        id="specialty.sentetik",
        layer=PackLayer.SPECIALTY,
        extends="base.life_threat",
    )
    codes = _refuse(child, life_threat, template)
    assert RefusalCode.LIFE_THREAT_SET_EXTENDED in codes


def test_refuses_conflicting_overlays_naming_every_writer(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §3.4: two overlays writing the same pointer with different
    values is a COMPILE ERROR naming every (pack_id, pointer, value_hash) —
    never last-writer-wins."""
    base = _pack()
    one = _pack(
        id="overlay.sentetik_bir",
        layer=PackLayer.OVERLAY,
        extends="base.sentetik_kapali",
        sections={},
        red_flags=(),
        ops=(
            SetVoiceOp(
                op="set_voice",
                pointer="/sections/ziyaret",
                voice=VoiceSettings(pace=Pace.NORMAL),
            ),
        ),
    )
    two = _pack(
        id="overlay.sentetik_iki",
        layer=PackLayer.OVERLAY,
        extends="base.sentetik_kapali",
        sections={},
        red_flags=(),
        ops=(
            SetVoiceOp(
                op="set_voice",
                pointer="/sections/ziyaret",
                voice=VoiceSettings(pace=Pace.SLOW),
            ),
        ),
    )
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id="base.sentetik_kapali",
            registry=_registry(base, one, two),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
            overlays=("overlay.sentetik_bir", "overlay.sentetik_iki"),
        )
    conflicts = [r for r in excinfo.value.refusals if r.code is RefusalCode.OVERLAY_CONFLICT]
    assert conflicts, "a differing-value overlay pair must refuse"
    message = conflicts[0].message
    assert "overlay.sentetik_bir" in message
    assert "overlay.sentetik_iki" in message
    assert "/sections/ziyaret" in message


def test_supersedes_is_the_reviewed_escape_hatch_for_a_conflict(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/12 §3.4: the escape hatch is an explicit, reviewed
    ``supersedes:`` declaration — not a silent precedence rule."""
    base = _pack()
    one = _pack(
        id="overlay.sentetik_bir",
        layer=PackLayer.OVERLAY,
        extends="base.sentetik_kapali",
        sections={},
        red_flags=(),
        ops=(
            SetVoiceOp(
                op="set_voice",
                pointer="/sections/ziyaret",
                voice=VoiceSettings(pace=Pace.NORMAL),
            ),
        ),
    )
    two = _pack(
        id="overlay.sentetik_iki",
        layer=PackLayer.OVERLAY,
        extends="base.sentetik_kapali",
        sections={},
        red_flags=(),
        supersedes=("overlay.sentetik_bir",),
        ops=(
            SetVoiceOp(
                op="set_voice",
                pointer="/sections/ziyaret",
                voice=VoiceSettings(pace=Pace.SLOW),
            ),
        ),
    )
    bundle = compile_bundle(
        pack_id="base.sentetik_kapali",
        registry=_registry(base, one, two),
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        overlays=("overlay.sentetik_bir", "overlay.sentetik_iki"),
    )
    assert bundle.resolved_protocol_hash


# --------------------------------------------------------------------------
# Invariant 10 — scripted text is verbatim.
# --------------------------------------------------------------------------


def test_refuses_a_paraphrasable_section_that_administers_an_instrument(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """CLAUDE.md invariant 10: validated instruments are spoken verbatim from
    ``text_tr``; paraphrase is permitted only where the protocol sets
    allow_paraphrase: true, which an instrument-bearing section never may.

    INT-040's validator checks the instrument's own voice block and each
    item's flag. The hole it cannot see is the SECTION that administers the
    instrument: its voice hints reach the delivery, so a section carrying
    ``questionnaires`` while paraphrase is permitted anywhere up the chain is
    a compile error here."""
    section = Section(
        slots={"basvuru_nedeni": _slot()},
        questionnaires=("SYN-X",),
        voice=VoiceSettings(allow_paraphrase=True),
    )
    pack = _pack(sections={"ziyaret": section}, instruments=(_instrument(),))
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id=pack.id,
            registry=_registry(pack),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
            licences=SYNTHETIC_LICENCES,
        )
    assert RefusalCode.SCRIPTED_TEXT_PARAPHRASABLE in tuple(
        refusal.code for refusal in excinfo.value.refusals
    )


def test_refuses_an_instrument_item_marked_paraphrasable(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """The INT-040 finding, re-raised as a compile refusal rather than a
    report the caller might not read."""
    instrument = Instrument(
        id="SYN-X",
        items=(
            InstrumentItem(
                id="madde_bir", text_tr="Sentetik ölçek maddesi.", allow_paraphrase=True
            ),
        ),
    )
    section = Section(slots={"basvuru_nedeni": _slot()}, questionnaires=("SYN-X",))
    pack = _pack(sections={"ziyaret": section}, instruments=(instrument,))
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id=pack.id,
            registry=_registry(pack),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
            licences=SYNTHETIC_LICENCES,
        )
    assert RefusalCode.SCRIPTED_TEXT_PARAPHRASABLE in tuple(
        refusal.code for refusal in excinfo.value.refusals
    )


def test_refuses_a_licence_blocked_instrument(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/04 header + HB-L2/HB-L3: a pack referencing a non-GO instrument
    must fail the build (invariant 45 ``instrument_licence_gate``)."""
    section = Section(slots={"basvuru_nedeni": _slot()}, questionnaires=("C-SSRS",))
    pack = _pack(sections={"ziyaret": section})
    with pytest.raises(CompileError) as excinfo:
        compile_bundle(
            pack_id=pack.id,
            registry=_registry(pack),
            life_threat=life_threat,
            template=template,
            voice=VOICE,
        )
    assert RefusalCode.VALIDATION_FINDING in tuple(
        refusal.code for refusal in excinfo.value.refusals
    )


# --------------------------------------------------------------------------
# ADR-002 / files/12 §8 — the openEHR annotation is compiler-enforced.
# --------------------------------------------------------------------------


def test_refuses_a_slot_with_neither_openehr_path_nor_deferred_reason(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    naked = _slot(openehr_path=None, openehr_deferred_reason=None)
    codes = _refuse(
        _pack(sections={"ziyaret": Section(slots={"basvuru_nedeni": naked})}),
        life_threat,
        template,
    )
    assert RefusalCode.OPENEHR_BINDING_UNDECLARED in codes


def test_refuses_a_slot_declaring_both_a_path_and_a_deferral(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    both = _slot(openehr_deferred_reason="Sentetik erteleme gerekçesi.")
    codes = _refuse(
        _pack(sections={"ziyaret": Section(slots={"basvuru_nedeni": both})}),
        life_threat,
        template,
    )
    assert RefusalCode.OPENEHR_BINDING_AMBIGUOUS in codes


def test_refuses_an_openehr_path_that_does_not_resolve_in_the_committed_opt(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    unresolvable = _slot(
        openehr_path="/content[openEHR-EHR-OBSERVATION.sentetik_yok.v1]",
    )
    codes = _refuse(
        _pack(sections={"ziyaret": Section(slots={"basvuru_nedeni": unresolvable})}),
        life_threat,
        template,
    )
    assert RefusalCode.OPENEHR_PATH_UNRESOLVED in codes


# --------------------------------------------------------------------------
# files/13 §13 — text_only means text only.
# --------------------------------------------------------------------------


def test_a_text_only_section_contributes_no_clip(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    """files/13 §13: `text_only` must mean text only — no clip, no speech,
    ever (CI gate safeguarding_never_spoken)."""
    bundle = compile_bundle(
        pack_id="base.derlenebilir",
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
    )
    clips = bundle.clip_manifest
    assert clips, "the voice sections must still produce clips"
    assert all("tarama" not in row.subject for row in clips)
    assert all("Sentetik metin-yalnız soru." != row.text_tr for row in clips)


def test_refuses_a_text_only_slot_that_declares_voice_delivery_on_its_section(
    life_threat: LifeThreatSet, template: OperationalTemplate
) -> None:
    section = Section(
        delivery=Delivery.TEXT_ONLY,
        slots={"basvuru_nedeni": _slot(delivery=Delivery.VOICE)},
    )
    codes = _refuse(_pack(sections={"ziyaret": section}), life_threat, template)
    assert RefusalCode.TEXT_ONLY_SPOKEN in codes


# --------------------------------------------------------------------------
# Helpers producing life-threat YAML rule payloads.
# --------------------------------------------------------------------------


def _life_threat_rule_yaml(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "rf.sentetik_yasamsal",
        "label_tr": "Sentetik yaşamsal tehdit kuralı",
        "age_band": "adult",
        "gate": "ziyaret.basvuru_nedeni == 'sentetik_yasamsal'",
        "tense": "now",
        "tense_anchor": "sure_dakika",
        "level": "KIRMIZI_K1",
        "route": "EMERGENCY_NOW",
        "register": "ALERT",
        "distress_sensitive": False,
        "notify_clinic": "always",
        "status": "active",
        "evidence": {
            "guideline_id": "SYN-GUIDE-B",
            "guideline_title": "Sentetik kılavuz B",
            "version_or_date": "sürüm bir",
            "url": "https://example.invalid/syn-guide-b",
            "retrieved_on": date(2026, 8, 28),
            "quote": "sentetik yaşamsal alıntı",
        },
        "action": {
            "REMOTE": {
                "primary": "CALL_112",
                "show_112": True,
                "action_tr": "Hemen yardım isteyin.",
                "why_tr": "Bu bir sentetik test metnidir.",
            },
            "ON_SITE": {
                "primary": "GO_TO_IN_HOUSE_ACIL",
                "show_112": False,
                "notify_staff_immediate": True,
                "action_tr": "Görevlilere haber verin.",
                "why_tr": "Bu bir sentetik test metnidir.",
            },
            "UNKNOWN": {
                "ask_one_tr": "Şu anda hastanede misiniz?",
                "on_yes": "ON_SITE",
                "on_no": "REMOTE",
                "on_no_answer": "REMOTE",
            },
        },
    }
    payload.update(overrides)
    return payload


def _paediatric_rule_yaml() -> dict[str, Any]:
    """A synthetic paediatric rule, in the shape INT-255 now requires: a rule
    that says its age_band is paediatric must also say its subject is a
    child, and files/02 §5.3 then puts it in the CALM register rather than
    ALERT — the alarm is what produces the deterioration."""
    return _life_threat_rule_yaml(
        id="rf.sentetik_cocuk",
        age_band="paediatric",
        subject_is_child=True,
        register="CALM",
        distress_sensitive=True,
        suppress_attention_interrupt=True,
    )


def _draft_life_threat_rule_yaml() -> dict[str, Any]:
    payload = _life_threat_rule_yaml(id="rf.sentetik_taslak")
    payload.pop("evidence")
    payload.pop("action")
    payload["status"] = "draft_needs_source"
    payload["source_gap"] = "Sentetik kaynak boşluğu."
    payload["level"] = "YESIL"
    payload["route"] = "EXPEDITE"
    payload["register"] = None
    payload["notify_clinic"] = "never"
    return payload


def _instrument() -> Instrument:
    return Instrument(
        id="SYN-X",
        items=(
            InstrumentItem(
                id="madde_bir", text_tr="Sentetik ölçek maddesi.", allow_paraphrase=False
            ),
        ),
    )
