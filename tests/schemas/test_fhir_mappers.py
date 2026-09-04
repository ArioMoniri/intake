"""INT-033 — FHIR R4 mappers, example-based unit lane.

Acceptance under test, verbatim (docs/backlog/issues.yaml):
  "QuestionnaireResponse, Observation, Condition, MedicationStatement,
   AllergyIntolerance, RiskAssessment, Flag, Composition, Bundle;
   hypothesis roundtrip; Bundle validates on HAPI container"

Blueprint anchors:
- files/03 §7: FHIR R4 (HAPI) is the exchange format; the mapping layer is
  ``packages/clinical-schemas/mappers/``, bidirectional, roundtrip-tested;
  code systems ICD-10 / ATC / LOINC (SNOMED not licensed in Türkiye).
- files/03 §4.6: ExtractedRecordItem[] → Observation/Condition/… with
  ``verificationStatus=unconfirmed`` and Provenance page/bbox.
- files/03 §5: engine output persists as FHIR QuestionnaireResponse +
  Observations; files/03 §4.8: FHIR Composition + Bundle renderer.
- Invariant 1 interop face: RiskAssessment/Flag carry the RULES result only;
  an LlmCandidateTriage never maps to any FHIR resource.

All fixture content is synthetic (invariant 6): ids only, no real personal
data anywhere.
"""

from __future__ import annotations

import datetime
import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from clinical_schemas import (
    AllergyItem,
    CandidateFlag,
    ChiefComplaint,
    CodeSystem,
    Consideration,
    ExtractedRecordItem,
    FamilySocial,
    Hpi,
    ImportedObjectiveItem,
    LlmCandidateTriage,
    MedicationItem,
    NoteMeta,
    NoteTriage,
    Oldcarts,
    PmhItem,
    PreVisitNote,
    RecordCode,
    RecordItemKind,
    RecordProvenance,
    RosItem,
    RuleFire,
    RulesTriageResult,
    ScreeningBlock,
    ScreeningProvenance,
    SessionBudget,
    SessionState,
    SessionStatus,
    TriageLevel,
    VerificationStatus,
)
from clinical_schemas.mappers import (
    NOTE_SECTION_IDS,
    MappingError,
    allergy_intolerance_to_allergy_item,
    allergy_intolerance_to_record_item,
    allergy_item_to_allergy_intolerance,
    codes,
    condition_to_pmh_item,
    medication_item_to_medication_statement,
    medication_statement_to_medication_item,
    medication_statement_to_record_item,
    observation_to_record_item,
    observations_to_screening_block,
    pmh_item_to_condition,
    previsit_note_to_document_bundle,
    questionnaire_response_to_session_state,
    r4_to_record_item,
    record_item_to_r4,
    risk_assessment_to_triage,
    screening_to_observations,
    session_state_to_questionnaire_response,
    to_wire,
    triage_to_flag,
    triage_to_risk_assessment,
)
from clinical_schemas.mappers.r4 import (
    AllergyIntolerance,
    Condition,
    MedicationStatement,
    Observation,
    QrAnswer,
    QrItem,
    QuestionnaireResponse,
    RiskAssessment,
)
from clinical_schemas.mappers.to_r4 import _scalar_answer
from clinical_schemas.triage import RedLocation, RedRegister

SUBJECT = "urn:uuid:00000000-0000-4000-8000-000000000001"
DOC_REF = "doc-0001"
GENERATED_AT = datetime.datetime(2026, 8, 28, 10, 0, tzinfo=datetime.UTC)
SHA = "ab" * 32


def _provenance(**kwargs: Any) -> RecordProvenance:
    base: dict[str, Any] = {"document_ref": DOC_REF, "page": 2, "bbox": (0.1, 0.2, 0.3, 0.4)}
    base.update(kwargs)
    return RecordProvenance(**base)


def _lab_item(**kwargs: Any) -> ExtractedRecordItem:
    base: dict[str, Any] = {
        "kind": RecordItemKind.LAB,
        "summary": "Hemoglobin",
        "code": RecordCode(system=CodeSystem.LOINC, code="718-7"),
        "value_magnitude": Decimal("10.2"),
        "unit": "g/dL",
        "date": datetime.date(2026, 8, 14),
        "verification_status": VerificationStatus.UNCONFIRMED,
        "provenance": _provenance(),
    }
    base.update(kwargs)
    return ExtractedRecordItem(**base)


def _screening_provenance() -> ScreeningProvenance:
    return ScreeningProvenance(
        administration_mode="voice",
        proxy_reported=False,
        third_party_present=True,
        qualifier_tr="başka bir konuşmacı duyuldu",
    )


def _screening_block(**kwargs: Any) -> ScreeningBlock:
    base: dict[str, Any] = {
        "phq2": 3,
        "gad2": 2,
        "phq9": 7,
        "gad7": 8,
        "provenance": _screening_provenance(),
    }
    base.update(kwargs)
    return ScreeningBlock(**base)


def _red_triage() -> RulesTriageResult:
    return RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id="rf.chest_pain", evidence="slot hpi.chest_pressure = evet"),),
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
    )


def _session_state(**kwargs: Any) -> SessionState:
    base: dict[str, Any] = {
        "session_id": "sess-0001",
        "protocol_id": "base.intake",
        "protocol_version": "1.0.0",
        "protocol_hash": SHA,
        "mode": "fast",
        "status": SessionStatus.COMPLETED,
        "reference_time": GENERATED_AT,
        "step_states": {"hpi.onset": "ASKED_PRESENT"},
        "slots": {"hpi.onset": "iki gündür"},
        "budget": SessionBudget(turns_used=4, turns_remaining=14),
    }
    base.update(kwargs)
    return SessionState(**base)


def _note(**kwargs: Any) -> PreVisitNote:
    base: dict[str, Any] = {
        "meta": NoteMeta(
            visit_id="visit-0001",
            protocol_hash=SHA,
            mode="fast",
            generated_at=GENERATED_AT,
            model="llm-extractor@r1",
            prompt_version="p1",
        ),
        "triage": NoteTriage(
            level=TriageLevel.YELLOW,
            rules=(RuleFire(id="rf.uncontrolled_htn", evidence="tansiyon yüksek"),),
            llm_candidates=(
                CandidateFlag(text="SENTINEL-CANDIDATE-TEXT", evidence="SENTINEL-EVIDENCE"),
            ),
        ),
        "chief_complaint": ChiefComplaint(text="karın ağrısı", patient_goals=("ağrı geçsin",)),
        "hpi": Hpi(
            narrative="iki gündür karın ağrısı",
            oldcarts=Oldcarts(onset="iki gün önce", severity_nrs=6),
            associated=("bulantı",),
            negatives=("ateş yok",),
        ),
        "ros_pertinent": (RosItem(system="GIS", finding="bulantı", present=True),),
        "pmh": (
            PmhItem(condition="hipertansiyon", icd10="I10", status="confirmed", source="patient"),
        ),
        "medications": (
            MedicationItem(
                name="omeprazol",
                atc="A02BC01",
                dose="günde bir kez yirmi miligram",
                adherence="düzenli",
                source="patient",
                reconciliation="matches",
            ),
        ),
        "allergies": (AllergyItem(substance="penisilin", reaction="döküntü", severity="hafif"),),
        "family_social": FamilySocial(occupation="öğretmen"),
        "screening": _screening_block(),
        "imported_objective": (
            ImportedObjectiveItem(
                type="lab",
                summary="Hemoglobin on virgül iki",
                date="2026-08-14",
                provenance=DOC_REF,
            ),
        ),
        "data_gaps": ("belge sayfa üç okunamadı",),
        "suggested_focus_questions": ("ağrı yayılıyor mu?",),
        "considerations": (Consideration(pattern="dispepsi paterni", why="yemekle ilişki"),),
        "patient_confirmed_sections": ("medications",),
    }
    base.update(kwargs)
    return PreVisitNote(**base)


# ---------------------------------------------------------------- record items


class TestRecordItemToR4:
    def test_lab_maps_to_observation_with_loinc_and_quantity(self) -> None:
        obs = record_item_to_r4(_lab_item(), subject_ref=SUBJECT)
        assert isinstance(obs, Observation)
        wire = to_wire(obs)
        assert wire["resourceType"] == "Observation"
        assert wire["status"] == "preliminary"
        assert wire["subject"]["reference"] == SUBJECT
        assert wire["category"][0]["coding"][0]["code"] == "laboratory"
        assert {"system": codes.LOINC, "code": "718-7"} in wire["code"]["coding"]
        assert wire["code"]["text"] == "Hemoglobin"
        assert wire["valueQuantity"]["value"] == 10.2
        assert wire["valueQuantity"]["unit"] == "g/dL"
        assert wire["effectiveDateTime"] == "2026-08-14"

    @pytest.mark.parametrize(
        ("kind", "category"),
        [
            (RecordItemKind.IMAGING, "imaging"),
            (RecordItemKind.PROCEDURE, "procedure"),
        ],
    )
    def test_imaging_and_procedure_categories(self, kind: RecordItemKind, category: str) -> None:
        item = _lab_item(kind=kind, code=None, value_magnitude=None, unit=None)
        wire = to_wire(record_item_to_r4(item, subject_ref=SUBJECT))
        assert wire["category"][0]["coding"][0]["code"] == category

    def test_provenance_travels_as_extension(self) -> None:
        wire = to_wire(record_item_to_r4(_lab_item(), subject_ref=SUBJECT))
        by_url = {e["url"]: e for e in wire["extension"]}
        assert by_url[codes.EXT_DOCUMENT_REF]["valueString"] == DOC_REF
        assert by_url[codes.EXT_PAGE]["valueInteger"] == 2
        bbox = {e["url"]: e["valueDecimal"] for e in by_url[codes.EXT_BBOX]["extension"]}
        assert bbox == {"x0": 0.1, "y0": 0.2, "x1": 0.3, "y1": 0.4}

    def test_unit_conflict_flag_is_carried_never_converted(self) -> None:
        # CLAUDE.md invariant 22: disagreement raises a flag, never converts.
        item = _lab_item(unit_conflict=True)
        wire = to_wire(record_item_to_r4(item, subject_ref=SUBJECT))
        by_url = {e["url"]: e for e in wire["extension"]}
        assert by_url[codes.EXT_UNIT_CONFLICT]["valueBoolean"] is True
        assert wire["valueQuantity"]["value"] == 10.2  # magnitude untouched
        back = observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)
        assert back.unit_conflict is True

    def test_medication_maps_to_medication_statement_with_atc(self) -> None:
        item = _lab_item(
            kind=RecordItemKind.MEDICATION,
            summary="omeprazol",
            code=RecordCode(system=CodeSystem.ATC, code="A02BC01"),
            value_magnitude=None,
            unit=None,
        )
        ms = record_item_to_r4(item, subject_ref=SUBJECT)
        assert isinstance(ms, MedicationStatement)
        wire = to_wire(ms)
        assert wire["status"] == "unknown"
        assert {"system": codes.ATC, "code": "A02BC01"} in (
            wire["medicationCodeableConcept"]["coding"]
        )
        assert wire["dateAsserted"] == "2026-08-14"

    def test_diagnosis_maps_to_condition_with_native_verification(self) -> None:
        item = _lab_item(
            kind=RecordItemKind.DIAGNOSIS,
            summary="esansiyel hipertansiyon",
            code=RecordCode(system=CodeSystem.ICD10, code="I10"),
            value_magnitude=None,
            unit=None,
            verification_status=VerificationStatus.UNCONFIRMED,
        )
        cond = record_item_to_r4(item, subject_ref=SUBJECT)
        assert isinstance(cond, Condition)
        wire = to_wire(cond)
        ver = wire["verificationStatus"]["coding"][0]
        assert ver == {"system": codes.CONDITION_VER_STATUS, "code": "unconfirmed"}
        assert {"system": codes.ICD10, "code": "I10"} in wire["code"]["coding"]

    def test_allergy_maps_with_clinical_status_present(self) -> None:
        # HAPI R4 rule ait-1: clinicalStatus SHALL be present when
        # verificationStatus is not entered-in-error.
        item = _lab_item(
            kind=RecordItemKind.ALLERGY,
            summary="penisilin",
            code=None,
            value_magnitude=None,
            unit=None,
        )
        ai = record_item_to_r4(item, subject_ref=SUBJECT)
        assert isinstance(ai, AllergyIntolerance)
        wire = to_wire(ai)
        assert wire["clinicalStatus"]["coding"][0]["code"] == "active"
        assert wire["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
        assert wire["patient"]["reference"] == SUBJECT

    @pytest.mark.parametrize(
        "kind",
        [RecordItemKind.MEDICATION, RecordItemKind.DIAGNOSIS, RecordItemKind.ALLERGY],
    )
    def test_value_on_non_observable_kind_is_refused(self, kind: RecordItemKind) -> None:
        # Explicit refusal, never a silent drop (INT-033 scope item 2).
        item = _lab_item(kind=kind, code=None)
        with pytest.raises(MappingError):
            record_item_to_r4(item, subject_ref=SUBJECT)

    def test_confirmed_lab_is_final(self) -> None:
        item = _lab_item(verification_status=VerificationStatus.CONFIRMED)
        wire = to_wire(record_item_to_r4(item, subject_ref=SUBJECT))
        assert wire["status"] == "final"

    def test_roundtrip_through_wire_json(self) -> None:
        item = _lab_item()
        obs = record_item_to_r4(item, subject_ref=SUBJECT)
        parsed = Observation.model_validate_json(json.dumps(to_wire(obs)))
        assert r4_to_record_item(parsed, document_ref=DOC_REF) == item

    def test_unknown_code_system_is_never_guessed(self) -> None:
        wire = to_wire(record_item_to_r4(_lab_item(), subject_ref=SUBJECT))
        wire["code"]["coding"] = [{"system": "urn:oid:1.2.3", "code": "x"}]
        back = observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)
        assert back.code is None  # files/03 §4.6: never a guessed code

    def test_observation_without_category_or_loinc_is_refused(self) -> None:
        wire = to_wire(record_item_to_r4(_lab_item(code=None), subject_ref=SUBJECT))
        del wire["category"]
        with pytest.raises(MappingError):
            observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)


# ------------------------------------------------------------------ note items


class TestNoteItemMappers:
    def test_medication_item_roundtrip(self) -> None:
        item = MedicationItem(
            name="omeprazol",
            atc="A02BC01",
            dose="günde bir kez yirmi miligram",
            adherence="düzenli",
            source="patient",
            reconciliation="matches",
        )
        ms = medication_item_to_medication_statement(item, subject_ref=SUBJECT)
        wire = to_wire(ms)
        assert wire["dosage"][0]["text"] == "günde bir kez yirmi miligram"
        assert (
            medication_statement_to_medication_item(MedicationStatement.model_validate(wire))
            == item
        )

    def test_pmh_item_roundtrip(self) -> None:
        item = PmhItem(condition="astım", icd10="J45", status="unconfirmed", source="record")
        cond = pmh_item_to_condition(item, subject_ref=SUBJECT)
        wire = to_wire(cond)
        assert wire["verificationStatus"]["coding"][0]["code"] == "unconfirmed"
        assert condition_to_pmh_item(Condition.model_validate(wire)) == item

    def test_allergy_item_roundtrip(self) -> None:
        item = AllergyItem(substance="penisilin", reaction="döküntü", severity="hafif")
        ai = allergy_item_to_allergy_intolerance(item, subject_ref=SUBJECT)
        wire = to_wire(ai)
        assert wire["reaction"][0]["manifestation"][0]["text"] == "döküntü"
        assert allergy_intolerance_to_allergy_item(AllergyIntolerance.model_validate(wire)) == item

    def test_extracted_allergy_ingests_back(self) -> None:
        item = _lab_item(
            kind=RecordItemKind.ALLERGY,
            summary="penisilin",
            code=None,
            value_magnitude=None,
            unit=None,
        )
        ai = record_item_to_r4(item, subject_ref=SUBJECT)
        assert isinstance(ai, AllergyIntolerance)
        assert allergy_intolerance_to_record_item(ai, document_ref=DOC_REF) == item


# ------------------------------------------------------------------- screening


class TestScreeningObservations:
    def test_scores_become_survey_observations_with_performer_patient(self) -> None:
        obs = screening_to_observations(
            _screening_block(), subject_ref=SUBJECT, effective=GENERATED_AT
        )
        assert len(obs) == 4  # phq2, gad2, phq9, gad7 — cssrs never emitted
        for o in obs:
            wire = to_wire(o)
            assert wire["category"][0]["coding"][0]["code"] == "survey"
            assert wire["performer"] == [{"reference": SUBJECT}]  # files/03 §7
            ext_urls = {e["url"] for e in wire["extension"]}
            # files/04 §4.3: the factual qualifiers ride with every score.
            assert codes.EXT_ADMINISTRATION_MODE in ext_urls
            assert codes.EXT_PROXY_REPORTED in ext_urls
            assert codes.EXT_THIRD_PARTY_PRESENT in ext_urls

    def test_verified_loinc_totals_only(self) -> None:
        obs = {  # instrument -> wire codings
            o.code.text if o.code else "": to_wire(o)["code"]["coding"]
            for o in screening_to_observations(_screening_block(), subject_ref=SUBJECT)
        }
        loinc = {
            name: [c["code"] for c in codings if c["system"] == codes.LOINC]
            for name, codings in obs.items()
        }
        assert loinc["phq9"] == ["44261-6"]
        assert loinc["gad7"] == ["70274-6"]
        assert loinc["phq2"] == ["55758-7"]
        # No LOINC code for a standalone GAD-2 total could be verified
        # (NLM lookup 2026-08-28; 70272-0 is PHQ-4) — never a guessed code.
        assert loinc["gad2"] == []

    def test_cssrs_never_emitted(self) -> None:
        # C-SSRS is licence-BLOCKED (HUMAN_BLOCKERS.md HB-L2); its open slot
        # never crosses into exchange. Explicit, tested loss.
        with_cssrs = _screening_block(cssrs={"screen": "done"})
        assert len(screening_to_observations(with_cssrs, subject_ref=SUBJECT)) == 4
        assert "cssrs" not in json.dumps(
            [to_wire(o) for o in screening_to_observations(with_cssrs, subject_ref=SUBJECT)]
        )

    def test_roundtrip_via_wire(self) -> None:
        block = _screening_block()
        obs = screening_to_observations(block, subject_ref=SUBJECT)
        parsed = [Observation.model_validate_json(o.model_dump_json(by_alias=True)) for o in obs]
        assert observations_to_screening_block(parsed) == block

    def test_no_scores_yields_no_observations(self) -> None:
        empty = ScreeningBlock(provenance=_screening_provenance())
        assert screening_to_observations(empty, subject_ref=SUBJECT) == ()


# ---------------------------------------------------------------------- triage


class TestTriageMapping:
    def test_red_roundtrips_with_register_and_location(self) -> None:
        result = _red_triage()
        ra = triage_to_risk_assessment(result, subject_ref=SUBJECT)
        wire = to_wire(ra)
        assert wire["method"]["coding"][0] == {
            "system": codes.TRIAGE_METHOD_SYSTEM,
            "code": "rules",
        }
        levels = wire["prediction"][0]["qualitativeRisk"]["coding"]
        assert {"system": codes.TRIAGE_LEVEL_SYSTEM, "code": "RED"} in levels
        assert risk_assessment_to_triage(RiskAssessment.model_validate(wire)) == result

    def test_green_and_yellow_roundtrip(self) -> None:
        green = RulesTriageResult(level=TriageLevel.GREEN)
        yellow = RulesTriageResult(
            level=TriageLevel.YELLOW,
            rules=(RuleFire(id="rf.htn", evidence="tansiyon yüksek"),),
        )
        for result in (green, yellow):
            ra = triage_to_risk_assessment(result, subject_ref=SUBJECT)
            assert risk_assessment_to_triage(ra) == result

    def test_llm_candidate_never_becomes_risk_assessment(self) -> None:
        # Invariant 1's interop face (INT-033 scope item 3).
        candidate = LlmCandidateTriage(
            candidate_flags=(CandidateFlag(text="aday", evidence="metin"),)
        )
        with pytest.raises(MappingError):
            triage_to_risk_assessment(candidate, subject_ref=SUBJECT)  # type: ignore[arg-type]
        with pytest.raises(MappingError):
            triage_to_flag(candidate, subject_ref=SUBJECT)  # type: ignore[arg-type]

    def test_foreign_risk_assessment_without_rules_method_is_refused(self) -> None:
        wire = to_wire(triage_to_risk_assessment(_red_triage(), subject_ref=SUBJECT))
        wire["method"]["coding"][0]["code"] = "model-estimate"
        with pytest.raises(MappingError):
            risk_assessment_to_triage(RiskAssessment.model_validate(wire))

    def test_no_probability_anywhere(self) -> None:
        # Invariant 20: the rules result is categorical; no numeric risk
        # figure is ever asserted on the wire.
        wire = to_wire(triage_to_risk_assessment(_red_triage(), subject_ref=SUBJECT))
        assert "probability" not in json.dumps(wire).lower()

    def test_flag_for_red_and_yellow_only(self) -> None:
        assert triage_to_flag(RulesTriageResult(level=TriageLevel.GREEN), subject_ref=SUBJECT) is (
            None
        )
        flag = triage_to_flag(_red_triage(), subject_ref=SUBJECT)
        assert flag is not None
        wire = to_wire(flag)
        assert wire["status"] == "active"
        codings = wire["code"]["coding"]
        assert {"system": codes.TRIAGE_LEVEL_SYSTEM, "code": "RED"} in codings
        assert {"system": codes.TRIAGE_RULE_SYSTEM, "code": "rf.chest_pain"} in codings


# --------------------------------------------------------- QuestionnaireResponse


class TestQuestionnaireResponse:
    def test_maps_slots_and_protocol_identity(self) -> None:
        state = _session_state(
            slots={
                "hpi.onset": "iki gündür",
                "hpi.severity": 6,
                "vitals.temp_c": 37.5,
                "meds.any": True,
                "hpi.associated": ["bulantı", "gaz"],
                "family.smoking": {"status": "hiç", "paket_yil": 0},
            }
        )
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        wire = to_wire(qr)
        assert wire["status"] == "completed"
        assert wire["identifier"]["value"] == "sess-0001"
        assert wire["questionnaire"] == "urn:intake:protocol:base.intake|1.0.0"
        items = {i["linkId"]: i for i in wire["item"]}
        assert items["hpi.onset"]["answer"] == [{"valueString": "iki gündür"}]
        assert items["hpi.severity"]["answer"] == [{"valueInteger": 6}]
        assert items["vitals.temp_c"]["answer"] == [{"valueDecimal": 37.5}]
        assert items["meds.any"]["answer"] == [{"valueBoolean": True}]
        assert [a["valueString"] for a in items["hpi.associated"]["answer"]] == ["bulantı", "gaz"]
        sub = {i["linkId"]: i["answer"] for i in items["family.smoking"]["item"]}
        assert sub["status"] == [{"valueString": "hiç"}]
        assert sub["paket_yil"] == [{"valueInteger": 0}]

    def test_roundtrip_restores_state(self) -> None:
        state = _session_state(status=SessionStatus.ACTIVE)
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        wire_qr = qr.model_copy()  # exercise the frozen model path
        restored = questionnaire_response_to_session_state(
            wire_qr, step_states=dict(state.step_states), budget=state.budget
        )
        assert restored == state

    def test_none_answers_are_never_emitted(self) -> None:
        # Documented, pinned loss: a None answer is never emitted, at any
        # depth — an unanswered slot is absence, not a value.
        state = _session_state(slots={"a": None, "b": {"k": None}, "c": "var"})
        wire = to_wire(session_state_to_questionnaire_response(state, subject_ref=SUBJECT))
        assert [i["linkId"] for i in wire["item"]] == ["c"]

    def test_int_outside_fhir_32bit_range_is_refused(self) -> None:
        state = _session_state(slots={"n": 2**31})
        with pytest.raises(MappingError):
            session_state_to_questionnaire_response(state, subject_ref=SUBJECT)

    def test_list_with_none_entry_is_refused(self) -> None:
        state = _session_state(slots={"xs": ["a", None]})
        with pytest.raises(MappingError):
            session_state_to_questionnaire_response(state, subject_ref=SUBJECT)

    @pytest.mark.parametrize(
        ("status", "fhir_status"),
        [
            (SessionStatus.CREATED, "in-progress"),
            (SessionStatus.ACTIVE, "in-progress"),
            (SessionStatus.COMPLETED, "completed"),
            (SessionStatus.CANCELLED, "stopped"),
        ],
    )
    def test_status_mapping(self, status: SessionStatus, fhir_status: str) -> None:
        state = _session_state(status=status)
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        assert to_wire(qr)["status"] == fhir_status
        restored = questionnaire_response_to_session_state(
            qr, step_states=dict(state.step_states), budget=state.budget
        )
        assert restored.status is status  # exact status survives via extension


# ------------------------------------------------------------- document bundle


class TestDocumentBundle:
    def test_document_shape(self) -> None:
        bundle = previsit_note_to_document_bundle(_note(), patient_id="pt-0001")
        wire = to_wire(bundle)
        assert wire["resourceType"] == "Bundle"
        assert wire["type"] == "document"
        assert wire["identifier"] == {"system": codes.VISIT_ID_SYSTEM, "value": "visit-0001"}
        assert wire["timestamp"] == GENERATED_AT.isoformat()
        assert wire["entry"][0]["resource"]["resourceType"] == "Composition"

    def test_every_reference_resolves_inside_the_bundle(self) -> None:
        wire = to_wire(previsit_note_to_document_bundle(_note(), patient_id="pt-0001"))
        full_urls = {e["fullUrl"] for e in wire["entry"]}
        assert len(full_urls) == len(wire["entry"])  # bdl-7 uniqueness

        def refs(node: Any) -> list[str]:
            if isinstance(node, dict):
                found = [node["reference"]] if "reference" in node else []
                return found + [r for v in node.values() for r in refs(v)]
            if isinstance(node, list):
                return [r for v in node for r in refs(v)]
            return []

        for ref in refs(wire):
            assert ref in full_urls

    def test_section_codes_are_the_note_field_ids_in_note_order(self) -> None:
        assert NOTE_SECTION_IDS == tuple(
            name for name in PreVisitNote.model_fields if name != "meta"
        )
        wire = to_wire(previsit_note_to_document_bundle(_note(), patient_id="pt-0001"))
        composition = wire["entry"][0]["resource"]
        section_codes = [s["code"]["coding"][0]["code"] for s in composition["section"]]
        assert section_codes == [
            s for s in NOTE_SECTION_IDS if s in set(section_codes)
        ]  # note order preserved
        assert set(section_codes) <= set(NOTE_SECTION_IDS)
        for s in composition["section"]:
            assert s["code"]["coding"][0]["system"] == codes.SECTION_SYSTEM
            assert "text" in s or "entry" in s  # cmp-1

    def test_llm_candidates_never_cross_into_fhir(self) -> None:
        # Invariant 1 interop face: candidates are clinician-review material,
        # not exchangeable clinical assertions.
        payload = json.dumps(to_wire(previsit_note_to_document_bundle(_note(), patient_id="p")))
        assert "SENTINEL-CANDIDATE-TEXT" not in payload
        assert "SENTINEL-EVIDENCE" not in payload

    def test_composition_meta_carried(self) -> None:
        wire = to_wire(previsit_note_to_document_bundle(_note(), patient_id="pt-0001"))
        composition = wire["entry"][0]["resource"]
        assert composition["status"] == "final"
        assert composition["title"] == "Ön görüşme notu"
        assert composition["date"] == GENERATED_AT.isoformat()
        ext = {e["url"]: e.get("valueString") for e in composition["extension"]}
        assert ext[codes.EXT_PROTOCOL_HASH] == SHA
        assert ext[codes.EXT_MODE] == "fast"

    def test_deterministic_output(self) -> None:
        a = previsit_note_to_document_bundle(_note(), patient_id="pt-0001")
        b = previsit_note_to_document_bundle(_note(), patient_id="pt-0001")
        assert a.model_dump_json(by_alias=True) == b.model_dump_json(by_alias=True)

    def test_narrative_is_escaped_xhtml(self) -> None:
        hostile = _note(chief_complaint=ChiefComplaint(text="<script>alert(1)</script> & ağrı"))
        wire = to_wire(previsit_note_to_document_bundle(hostile, patient_id="pt-0001"))
        composition = wire["entry"][0]["resource"]
        chief = next(
            s for s in composition["section"] if s["code"]["coding"][0]["code"] == "chief_complaint"
        )
        assert "<script>" not in chief["text"]["div"]
        assert "&lt;script&gt;" in chief["text"]["div"]
        assert chief["text"]["div"].startswith('<div xmlns="http://www.w3.org/1999/xhtml">')

    def test_patient_entry_is_not_empty(self) -> None:
        # An id-less, field-less Patient parses to nothing on HAPI and then
        # fails bdl-5; the synthetic Patient always carries its id.
        wire = to_wire(previsit_note_to_document_bundle(_note(), patient_id="pt-0001"))
        patient = next(
            e["resource"] for e in wire["entry"] if e["resource"]["resourceType"] == "Patient"
        )
        assert patient["id"] == "pt-0001"

    def test_full_urls_are_urn_uuids_and_resources_carry_no_ids(self) -> None:
        wire = to_wire(previsit_note_to_document_bundle(_note(), patient_id="pt-0001"))
        for entry in wire["entry"]:
            assert entry["fullUrl"].startswith("urn:uuid:")
            uuid.UUID(entry["fullUrl"].removeprefix("urn:uuid:"))
            if entry["resource"]["resourceType"] != "Patient":
                assert "id" not in entry["resource"]

    def test_note_triage_red_without_axes_still_maps(self) -> None:
        # files/04 §5 note.triage has no register/location — the document
        # mapper must accept the authoritative note shape as-is.
        note = _note(
            triage=NoteTriage(
                level=TriageLevel.RED,
                rules=(RuleFire(id="rf.melena", evidence="siyah dışkı + baş dönmesi"),),
            )
        )
        wire = to_wire(previsit_note_to_document_bundle(note, patient_id="pt-0001"))
        types = [e["resource"]["resourceType"] for e in wire["entry"]]
        assert "RiskAssessment" in types
        assert "Flag" in types


# -------------------------------------------------------------------- hygiene


class TestWireHygiene:
    def test_wire_has_no_nulls(self) -> None:
        wire = to_wire(previsit_note_to_document_bundle(_note(), patient_id="pt-0001"))

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                for v in node.values():
                    assert v is not None
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(wire)

    def test_ingestion_ignores_foreign_fields(self) -> None:
        wire = to_wire(record_item_to_r4(_lab_item(), subject_ref=SUBJECT))
        wire["meta"] = {"versionId": "3"}
        wire["specimen"] = {"reference": "Specimen/abc"}
        back = observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)
        assert back == _lab_item()


# -------------------------------------------------- foreign-FHIR refusal guards


class TestIngestionRefusals:
    """The R4→internal face refuses malformed or foreign shapes instead of
    guessing — every branch here is a documented, deliberate refusal."""

    def test_summary_falls_back_to_display_then_refuses(self) -> None:
        wire = to_wire(record_item_to_r4(_lab_item(), subject_ref=SUBJECT))
        wire["code"] = {
            "coding": [{"system": codes.LOINC, "code": "718-7", "display": "Hemoglobin"}]
        }
        back = observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)
        assert back.summary == "Hemoglobin"
        wire["code"] = {"coding": [{"system": codes.LOINC, "code": "718-7"}]}
        with pytest.raises(MappingError):
            observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)

    def test_malformed_date_is_refused(self) -> None:
        wire = to_wire(record_item_to_r4(_lab_item(), subject_ref=SUBJECT))
        wire["effectiveDateTime"] = "not-a-date"
        with pytest.raises(MappingError):
            observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)

    def test_incomplete_bbox_extension_is_refused(self) -> None:
        wire = to_wire(record_item_to_r4(_lab_item(), subject_ref=SUBJECT))
        for ext in wire["extension"]:
            if ext["url"] == codes.EXT_BBOX:
                ext["extension"] = ext["extension"][:2]
        with pytest.raises(MappingError):
            observation_to_record_item(Observation.model_validate(wire), document_ref=DOC_REF)

    def test_survey_observation_is_not_a_record_item(self) -> None:
        observation = screening_to_observations(_screening_block(), subject_ref=SUBJECT)[0]
        with pytest.raises(MappingError):
            observation_to_record_item(observation, document_ref=DOC_REF)

    def test_foreign_medication_statement_defaults_to_unconfirmed(self) -> None:
        item = _lab_item(
            kind=RecordItemKind.MEDICATION,
            summary="omeprazol",
            code=None,
            value_magnitude=None,
            unit=None,
        )
        wire = to_wire(record_item_to_r4(item, subject_ref=SUBJECT))
        wire["extension"] = [e for e in wire["extension"] if e["url"] != codes.EXT_VERIFICATION]
        back = medication_statement_to_record_item(
            MedicationStatement.model_validate(wire), document_ref=DOC_REF
        )
        assert back.verification_status is VerificationStatus.UNCONFIRMED

    def test_note_item_inverses_require_the_intake_extensions(self) -> None:
        med = _lab_item(
            kind=RecordItemKind.MEDICATION,
            summary="omeprazol",
            code=None,
            value_magnitude=None,
            unit=None,
        )
        statement = record_item_to_r4(med, subject_ref=SUBJECT)
        assert isinstance(statement, MedicationStatement)
        with pytest.raises(MappingError):
            medication_statement_to_medication_item(statement)  # no reconciliation ext
        diagnosis = _lab_item(
            kind=RecordItemKind.DIAGNOSIS,
            summary="hipertansiyon",
            code=None,
            value_magnitude=None,
            unit=None,
        )
        condition = record_item_to_r4(diagnosis, subject_ref=SUBJECT)
        assert isinstance(condition, Condition)
        with pytest.raises(MappingError):
            condition_to_pmh_item(condition)  # no pmh-source ext

    def test_wrong_kind_direct_calls_are_refused(self) -> None:
        from clinical_schemas.mappers import (
            record_item_to_allergy_intolerance,
            record_item_to_condition,
            record_item_to_medication_statement,
            record_item_to_observation,
        )

        lab = _lab_item()
        with pytest.raises(MappingError):
            record_item_to_condition(lab, subject_ref=SUBJECT)
        with pytest.raises(MappingError):
            record_item_to_medication_statement(lab, subject_ref=SUBJECT)
        with pytest.raises(MappingError):
            record_item_to_allergy_intolerance(lab, subject_ref=SUBJECT)
        diagnosis = _lab_item(
            kind=RecordItemKind.DIAGNOSIS, code=None, value_magnitude=None, unit=None
        )
        with pytest.raises(MappingError):
            record_item_to_observation(diagnosis, subject_ref=SUBJECT)

    def test_screening_block_ingestion_refusals(self) -> None:
        with pytest.raises(MappingError):
            observations_to_screening_block([])
        good = screening_to_observations(_screening_block(), subject_ref=SUBJECT)
        wire = to_wire(good[0])
        foreign = dict(wire)
        foreign["code"] = {"coding": [{"system": codes.LOINC, "code": "44261-6"}]}
        with pytest.raises(MappingError):  # no screening-instrument coding
            observations_to_screening_block([Observation.model_validate(foreign)])
        no_score = dict(wire)
        del no_score["valueInteger"]
        with pytest.raises(MappingError):
            observations_to_screening_block([Observation.model_validate(no_score)])
        no_mode = dict(wire)
        no_mode["extension"] = [
            e for e in wire["extension"] if e["url"] != codes.EXT_ADMINISTRATION_MODE
        ]
        with pytest.raises(MappingError):
            observations_to_screening_block([Observation.model_validate(no_mode)])
        no_qualifiers = dict(wire)
        no_qualifiers["extension"] = [
            e for e in wire["extension"] if e["url"] == codes.EXT_ADMINISTRATION_MODE
        ]
        with pytest.raises(MappingError):
            observations_to_screening_block([Observation.model_validate(no_qualifiers)])

    def test_risk_assessment_without_level_is_refused(self) -> None:
        wire = to_wire(triage_to_risk_assessment(_red_triage(), subject_ref=SUBJECT))
        del wire["prediction"]
        with pytest.raises(MappingError):
            risk_assessment_to_triage(RiskAssessment.model_validate(wire))

    def test_allergy_reaction_without_text_reads_as_empty(self) -> None:
        item = AllergyItem(substance="polen", reaction="", severity="")
        ai = allergy_item_to_allergy_intolerance(item, subject_ref=SUBJECT)
        assert allergy_intolerance_to_allergy_item(ai) == item


class TestQuestionnaireResponseIngestionRefusals:
    def _qr_wire(self) -> dict[str, Any]:
        return to_wire(
            session_state_to_questionnaire_response(_session_state(), subject_ref=SUBJECT)
        )

    def test_missing_identifier(self) -> None:
        wire = self._qr_wire()
        del wire["identifier"]
        with pytest.raises(MappingError):
            questionnaire_response_to_session_state(
                QuestionnaireResponse.model_validate(wire),
                step_states={},
                budget=SessionBudget(turns_used=0, turns_remaining=1),
            )

    def test_foreign_questionnaire_canonical(self) -> None:
        wire = self._qr_wire()
        wire["questionnaire"] = "http://example.org/Questionnaire/q1|1.0"
        with pytest.raises(MappingError):
            questionnaire_response_to_session_state(
                QuestionnaireResponse.model_validate(wire),
                step_states={},
                budget=SessionBudget(turns_used=0, turns_remaining=1),
            )

    def test_missing_mode_extension(self) -> None:
        wire = self._qr_wire()
        wire["extension"] = [e for e in wire["extension"] if e["url"] != codes.EXT_MODE]
        with pytest.raises(MappingError):
            questionnaire_response_to_session_state(
                QuestionnaireResponse.model_validate(wire),
                step_states={},
                budget=SessionBudget(turns_used=0, turns_remaining=1),
            )

    def test_fhir_status_fallback_without_session_status_extension(self) -> None:
        for fhir_status, expected in (
            ("completed", SessionStatus.COMPLETED),
            ("stopped", SessionStatus.CANCELLED),
            ("in-progress", SessionStatus.ACTIVE),
        ):
            wire = self._qr_wire()
            wire["extension"] = [
                e for e in wire["extension"] if e["url"] != codes.EXT_SESSION_STATUS
            ]
            wire["status"] = fhir_status
            restored = questionnaire_response_to_session_state(
                QuestionnaireResponse.model_validate(wire),
                step_states={},
                budget=SessionBudget(turns_used=0, turns_remaining=1),
            )
            assert restored.status is expected
        wire = self._qr_wire()
        wire["extension"] = [e for e in wire["extension"] if e["url"] != codes.EXT_SESSION_STATUS]
        wire["status"] = "entered-in-error"
        with pytest.raises(MappingError):
            questionnaire_response_to_session_state(
                QuestionnaireResponse.model_validate(wire),
                step_states={},
                budget=SessionBudget(turns_used=0, turns_remaining=1),
            )

    def test_missing_authored(self) -> None:
        wire = self._qr_wire()
        del wire["authored"]
        with pytest.raises(MappingError):
            questionnaire_response_to_session_state(
                QuestionnaireResponse.model_validate(wire),
                step_states={},
                budget=SessionBudget(turns_used=0, turns_remaining=1),
            )

    def test_malformed_items_are_refused(self) -> None:
        from clinical_schemas.mappers.from_r4 import _item_value

        with pytest.raises(MappingError):  # neither answers nor children
            _item_value(QrItem(link_id="empty"))
        with pytest.raises(MappingError):  # nested child with two answers
            _item_value(
                QrItem(
                    link_id="parent",
                    item=(
                        QrItem(
                            link_id="child",
                            answer=(QrAnswer(value_string="a"), QrAnswer(value_string="b")),
                        ),
                    ),
                )
            )
        with pytest.raises(MappingError):  # multiple answers, no list marker
            _item_value(
                QrItem(
                    link_id="xs",
                    answer=(QrAnswer(value_string="a"), QrAnswer(value_string="b")),
                )
            )
        with pytest.raises(MappingError):  # answer with no value at all
            _item_value(QrItem(link_id="v", answer=(QrAnswer(),)))


# ------------------------------------------- INT-309: the FHIR scalar mapper


class TestDecimalScalarAnswer:
    """INT-309 boundary 1 — ``to_r4._scalar_answer`` had bool/int/float/str
    and no ``Decimal``, so the type files/13 §9.5 names for a clinical
    quantity fell through to a raise that says *"a None answer inside a list
    is malformed"*. That diagnosis is false twice over: the value is neither
    ``None`` nor inside a list, and a wrong error message costs more
    debugging time than no error message at all.

    The near-miss controls are the point of the class. A naive fix —
    ``isinstance(value, (float, Decimal))`` into a ``float``-typed
    ``valueDecimal`` — passes ``Decimal("37.5")`` and fails both of these:
    it flattens the declared scale of ``38.50`` and it rounds an integer
    past 2**53. Invariant 22: numbers never cross a representation boundary
    unguarded.
    """

    def test_a_decimal_slot_maps_to_value_decimal_rather_than_a_false_diagnosis(
        self,
    ) -> None:
        state = _session_state(slots={"vitals.temp_c": Decimal("38.5")})
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        answer = (qr.item or ())[0].answer or ()
        assert answer[0].value_decimal == Decimal("38.5")

    def test_the_declared_scale_survives_the_mapper(self) -> None:
        # Near-miss control: 38.50 and 38.5 are the same float and two
        # different clinical quantities. A float-typed carrier passes the
        # test above and fails this one.
        state = _session_state(slots={"vitals.temp_c": Decimal("38.50")})
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        carried = ((qr.item or ())[0].answer or ())[0].value_decimal
        assert isinstance(carried, Decimal)
        assert carried.as_tuple() == Decimal("38.50").as_tuple()
        assert carried.as_tuple() != Decimal("38.5").as_tuple()

    def test_an_integer_too_large_for_a_float_survives_the_mapper(self) -> None:
        # Near-miss control: 2**53 + 1 is the first integer a float cannot
        # hold. As a Decimal it is exact; through a float it becomes 2**53.
        big = Decimal(2**53 + 1)
        state = _session_state(slots={"labs.count": big})
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        carried = ((qr.item or ())[0].answer or ())[0].value_decimal
        assert carried == big
        assert carried != Decimal(2**53)

    def test_a_decimal_survives_the_mapper_round_trip(self) -> None:
        state = _session_state(slots={"vitals.temp_c": Decimal("38.50")})
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        restored = questionnaire_response_to_session_state(
            qr, step_states=dict(state.step_states), budget=state.budget
        )
        assert restored.slots["vitals.temp_c"] == Decimal("38.50")
        assert isinstance(restored.slots["vitals.temp_c"], Decimal)

    def test_a_float_slot_is_still_a_float_and_is_not_promoted(self) -> None:
        # Negative control: adding the Decimal branch must not quietly
        # convert every float. Decimal(str(0.1)) != 0.1, so a promotion here
        # would change an observer-lane-shaped value into a different number
        # and break the INT-033 property round trip.
        state = _session_state(slots={"vitals.temp_c": 0.1})
        qr = session_state_to_questionnaire_response(state, subject_ref=SUBJECT)
        carried = ((qr.item or ())[0].answer or ())[0].value_decimal
        assert carried == 0.1
        assert isinstance(carried, float)

    def test_a_none_inside_a_list_still_reads_as_the_true_diagnosis(self) -> None:
        # Negative control: the message this class exists to fix is CORRECT
        # for the one case it was written for, and must survive the fix.
        state = _session_state(slots={"xs": ["a", None]})
        with pytest.raises(MappingError, match="a None answer inside a list is malformed"):
            session_state_to_questionnaire_response(state, subject_ref=SUBJECT)

    def test_a_type_outside_the_carrier_is_named_by_type_and_never_by_value(self) -> None:
        # Invariant 6: an error that interpolated a slot value would put what
        # the patient said into a log.
        planted = datetime.date(2026, 8, 30)
        with pytest.raises(MappingError) as caught:
            _scalar_answer(planted, "vitals.temp_c")  # type: ignore[arg-type]
        assert "date" in str(caught.value)
        assert "2026-08-30" not in str(caught.value)
