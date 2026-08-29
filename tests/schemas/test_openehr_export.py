"""INT-032 — the openEHR export mapper, offline half.

files/03 §7 names openEHR the clinical core and ADR-002 demotes it to a P3
*export* with the archetype-path annotation kept on every slot. This lane
proves, without a container, the two things the export tier owes:

1. **The envelope roundtrips.** ``IntakeEhr``/``IntakeEnvelope`` →
   canonical openEHR JSON → back → identical value. No lossy field, no
   silently defaulted code.
2. **Clinical content fails closed.** The committed operational template
   (``packages/protocols/openehr/previsit_intake.v1.opt``) carries archetype
   ROOTS only — INT-041 refused to invent leaf ``atNNNN`` codes because a
   fabricated code binds against a fiction. A root path addresses an ENTRY,
   not a datum, so a slot that holds a value has nowhere to go, and the
   export raises instead of dropping it or guessing a path.

Every code string here is transcribed from the published openEHR
terminology (openEHR/terminology, ``openEHR_RM/en/openehr_terminology.xml``,
retrieved 29 Aug 2026): group ``composition category`` 433 = event; group
``setting`` 225–238. Nothing is invented.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.mappers.openehr import (
    COMPOSITION_ARCHETYPE_ID,
    OPENEHR_RM_VERSION,
    TEMPLATE_ID,
    CompositionCategory,
    EhrSetting,
    IntakeEhr,
    IntakeEnvelope,
    OpenEhrExportBlocked,
    SlotBinding,
    composition_to_envelope,
    ehr_status_to_intake_ehr,
    envelope_to_composition,
    intake_ehr_to_ehr_status,
    session_composition,
    slot_bindings,
    unbound_slots,
)
from clinical_schemas.session import SessionBudget, SessionState, SessionStatus
from intake_platform.tokenization import Tokenizer
from protocols.bindings import OPT_PATH, load_opt

SHA = "ab" * 32
REFERENCE_TIME = datetime.datetime(2026, 8, 28, 10, 0, tzinfo=datetime.UTC)
REPO = Path(__file__).resolve().parents[2]
REPO_OPT = REPO / OPT_PATH


def _envelope(**kwargs: Any) -> IntakeEnvelope:
    base: dict[str, Any] = {
        "reference_time": REFERENCE_TIME,
        "composer": "INTAKE",
        "setting": EhrSetting.SECONDARY_MEDICAL_CARE,
    }
    base.update(kwargs)
    return IntakeEnvelope(**base)


def _session_state(**kwargs: Any) -> SessionState:
    base: dict[str, Any] = {
        "session_id": "sess-int032",
        "protocol_id": "base.intake",
        "protocol_version": "1.0.0",
        "protocol_hash": SHA,
        "mode": "fast",
        "status": SessionStatus.COMPLETED,
        "reference_time": REFERENCE_TIME,
        "step_states": {},
        "slots": {},
        "budget": SessionBudget(turns_used=0, turns_remaining=18),
    }
    base.update(kwargs)
    return SessionState(**base)


# --- the envelope roundtrips ------------------------------------------------------


def test_envelope_roundtrips_through_canonical_json() -> None:
    envelope = _envelope()
    assert composition_to_envelope(envelope_to_composition(envelope)) == envelope


def test_every_setting_in_the_published_group_roundtrips() -> None:
    for setting in EhrSetting:
        envelope = _envelope(setting=setting)
        assert composition_to_envelope(envelope_to_composition(envelope)).setting is setting


def test_composition_declares_the_committed_template_and_archetype() -> None:
    composition = envelope_to_composition(_envelope())
    assert composition["_type"] == "COMPOSITION"
    assert composition["archetype_node_id"] == COMPOSITION_ARCHETYPE_ID
    details = composition["archetype_details"]
    assert details["archetype_id"]["value"] == COMPOSITION_ARCHETYPE_ID
    assert details["template_id"]["value"] == TEMPLATE_ID
    assert details["rm_version"] == OPENEHR_RM_VERSION
    assert composition["language"]["code_string"] == "tr"
    assert composition["territory"]["code_string"] == "TR"
    assert composition["category"]["defining_code"]["code_string"] == (
        CompositionCategory.EVENT.code
    )


def test_the_composition_archetype_is_the_committed_templates_root() -> None:
    """The envelope may not name an archetype the pinned OPT does not carry."""
    template = load_opt(REPO_OPT)
    composition = envelope_to_composition(_envelope())
    assert composition["archetype_details"]["template_id"]["value"] == template.template_id
    # every content archetype the template constrains is a root path, and the
    # export emits none of them today (see the fail-closed tests below)
    assert composition.get("content", []) == []
    for archetype_id in template.roots:
        assert template.resolve(f"/content[{archetype_id}]") is not None


def test_ehr_status_roundtrips_and_carries_a_token_not_a_patient_id() -> None:
    pseudonym = Tokenizer({"v1": b"int032-test-key"}, "v1").pseudonym("12345678901")
    ehr = IntakeEhr(subject_token=pseudonym)
    status = intake_ehr_to_ehr_status(ehr)
    assert ehr_status_to_intake_ehr(status) == ehr
    external_ref = status["subject"]["external_ref"]
    assert external_ref["id"]["value"] == pseudonym
    assert external_ref["id"]["scheme"] == "intake-tokenizer"


@pytest.mark.parametrize(
    "subject",
    [
        "12345678901",  # a TCKN, which is exactly what must never arrive
        "0532 111 44 55",  # a phone
        "sess-int032",  # an internal id is still not a pseudonym
        "v1." + "z" * 64,  # right shape, not hex
        "v1." + "a" * 63,  # right shape, digest one char short
    ],
)
def test_a_subject_that_is_not_a_tokenizer_pseudonym_is_refused(subject: str) -> None:
    """invariant 6/14: the CDR sees an INT-013 pseudonym (``<key_id>.<64 hex>``),
    never an identifier. The shape is the enforcement — a validator that
    accepted "anything opaque-looking" would accept a TCKN with a prefix."""
    with pytest.raises(ValueError, match="pseudonym"):
        IntakeEhr(subject_token=subject)


# --- clinical content fails closed ------------------------------------------------


def _bindings() -> tuple[SlotBinding, ...]:
    return slot_bindings(
        [
            {
                "fhir_link_id": "hpi.onset",
                "section_id": "hpi",
                "slot_key": "onset",
                "slot_type": "text",
                "aql_path": "/content[openEHR-EHR-OBSERVATION.story.v1]",
                "rm_type": "OBSERVATION",
                "openehr_deferred_reason": None,
            },
            {
                "fhir_link_id": "meta.mode",
                "section_id": "meta",
                "slot_key": "mode",
                "slot_type": "code",
                "aql_path": None,
                "rm_type": None,
                "openehr_deferred_reason": "no CKM archetype models the intake mode",
            },
        ]
    )


def test_an_answered_slot_has_no_leaf_binding_and_the_export_refuses() -> None:
    state = _session_state(slots={"hpi.onset": "iki gündür"})
    with pytest.raises(OpenEhrExportBlocked) as excinfo:
        session_composition(state, envelope=_envelope(), bindings=_bindings())
    blocked = excinfo.value
    assert [u.slot_id for u in blocked.unbound] == ["hpi.onset"]
    only = blocked.unbound[0]
    assert only.aql_path == "/content[openEHR-EHR-OBSERVATION.story.v1]"
    assert only.rm_type == "OBSERVATION"
    assert "leaf" in only.ask.lower()


def test_a_slot_with_a_deferral_reason_is_refused_with_that_reason() -> None:
    state = _session_state(slots={"meta.mode": "fast"})
    with pytest.raises(OpenEhrExportBlocked) as excinfo:
        session_composition(state, envelope=_envelope(), bindings=_bindings())
    only = excinfo.value.unbound[0]
    assert only.aql_path is None
    assert only.deferred_reason == "no CKM archetype models the intake mode"


def test_a_slot_the_binding_table_does_not_know_is_still_refused() -> None:
    """An unknown slot is the worst case, not a free pass: the export must not
    write a composition that silently omits an answer it did not recognise."""
    state = _session_state(slots={"wellbeing.phq2_total": 3})
    with pytest.raises(OpenEhrExportBlocked) as excinfo:
        session_composition(state, envelope=_envelope(), bindings=_bindings())
    only = excinfo.value.unbound[0]
    assert only.slot_id == "wellbeing.phq2_total"
    assert only.aql_path is None


def test_a_null_slot_value_is_not_an_answer_and_does_not_block() -> None:
    state = _session_state(slots={"hpi.onset": None})
    composition = session_composition(state, envelope=_envelope(), bindings=_bindings())
    assert composition["content"] == []


def test_a_session_with_no_answers_exports_the_envelope_and_no_content() -> None:
    composition = session_composition(_session_state(), envelope=_envelope(), bindings=_bindings())
    assert composition["content"] == []
    assert composition["context"]["start_time"]["value"] == "2026-08-28T10:00:00+00:00"
    assert composition_to_envelope(composition) == _envelope()


def test_unbound_slots_is_ordered_and_total() -> None:
    state = _session_state(slots={"meta.mode": "fast", "hpi.onset": "iki gündür"})
    unbound = unbound_slots(state, bindings=_bindings())
    assert [u.slot_id for u in unbound] == ["hpi.onset", "meta.mode"]


def test_no_at_code_is_invented_anywhere_in_the_export() -> None:
    """The whole point of INT-041's shallow template: no ``atNNNN`` appears in
    an emitted composition, because none is authored anywhere upstream."""
    import re

    from clinical_schemas.mappers import openehr as module

    source = (module.__file__ or "").strip()
    assert source
    text = open(source, encoding="utf-8").read()  # noqa: SIM115, PTH123
    assert re.search(r"\bat\d{4}\b", text) is None, "an at-code was invented in the mapper"
    composition = session_composition(_session_state(), envelope=_envelope(), bindings=_bindings())
    assert re.search(r"\bat\d{4}\b", repr(composition)) is None


def test_no_committed_slot_declares_a_deeper_than_root_path() -> None:
    """A guard on the premise, read from the shipped pack rather than a fixture:
    every ``openehr_path`` in ``packages/protocols/base/intake.yaml`` addresses
    an archetype ROOT. The moment a leaf path is authored upstream this test
    fails, and the mapper must grow real placement instead of a refusal."""
    pack = REPO_OPT.parent.parent / "base" / "intake.yaml"
    declared = re.findall(r'openehr_path:\s*"([^"]+)"', pack.read_text(encoding="utf-8"))
    assert declared, "the base pack declares no openEHR paths at all"
    deeper = [p for p in declared if not p.endswith("]") or p.count("/") != 1]
    assert deeper == [], (
        f"{len(deeper)} slot(s) now declare a leaf path {sorted(set(deeper))!r}: the "
        "export mapper must place those values instead of refusing them (INT-032a)"
    )
