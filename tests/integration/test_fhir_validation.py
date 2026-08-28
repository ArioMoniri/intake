"""INT-033 — FHIR exchange integration lane: real HAPI from the dev compose.

Acceptance line under test, verbatim: "… Bundle validates on HAPI container".

Runs under ``-m integration`` (``make check-integration``; the unit lane
never dials a network). Requires the compose ``hapi`` service from
infra/docker-compose.dev.yml healthy on 127.0.0.1:8091 (R4 mode).

What only this lane can prove: the emitted resources satisfy HAPI's full R4
validator — profile constraints (bdl-*, cmp-*, ait-1), xhtml narrative
well-formedness, reference resolution inside the document — not just our own
pydantic shapes. Every payload is synthetic (invariant 6): ids only, no real
personal data.
"""

from __future__ import annotations

import datetime
import os
from decimal import Decimal
from typing import Any

import httpx
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
    KonusmaOzellikleri,
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
)
from clinical_schemas.mappers import (
    previsit_note_to_document_bundle,
    record_item_to_r4,
    screening_to_observations,
    session_state_to_questionnaire_response,
    to_wire,
    triage_to_flag,
    triage_to_risk_assessment,
)
from clinical_schemas.triage import RedLocation, RedRegister

pytestmark = pytest.mark.integration

HAPI_BASE = os.environ.get("INTAKE_HAPI_URL", "http://127.0.0.1:8091/fhir")
SUBJECT = "urn:uuid:00000000-0000-4000-8000-000000000001"
GENERATED_AT = datetime.datetime(2026, 8, 28, 10, 0, tzinfo=datetime.UTC)
SHA = "ab" * 32

# The first $validate call warms HAPI's validation support; be generous.
TIMEOUT = httpx.Timeout(180.0, connect=15.0)


@pytest.fixture(scope="module")
def client() -> httpx.Client:
    return httpx.Client(
        base_url=HAPI_BASE,
        timeout=TIMEOUT,
        headers={"Content-Type": "application/fhir+json"},
    )


def _validate(client: httpx.Client, resource_type: str, payload: dict[str, Any]) -> list[str]:
    """POST to $validate; return the error/fatal diagnostics (must be empty)."""
    response = client.post(f"/{resource_type}/$validate", json=payload)
    assert response.status_code == 200, response.text[:2000]
    outcome = response.json()
    assert outcome.get("resourceType") == "OperationOutcome", outcome
    issues = outcome.get("issue", [])
    summary: dict[str, int] = {}
    for issue in issues:
        severity = str(issue.get("severity"))
        summary[severity] = summary.get(severity, 0) + 1
    print(f"$validate {resource_type}: {summary or 'no issues'}")
    return [
        f"{issue.get('severity')}: {issue.get('diagnostics')} @ {issue.get('location')}"
        for issue in issues
        if issue.get("severity") in ("error", "fatal")
    ]


def _note() -> PreVisitNote:
    return PreVisitNote(
        meta=NoteMeta(
            visit_id="visit-0001",
            protocol_hash=SHA,
            mode="detailed",
            generated_at=GENERATED_AT,
            model="llm-extractor@r1",
            prompt_version="p1",
        ),
        triage=NoteTriage(
            level=TriageLevel.RED,
            rules=(RuleFire(id="rf.melena", evidence="siyah dışkı ve baş dönmesi"),),
            llm_candidates=(CandidateFlag(text="aday bulgu", evidence="metin"),),
        ),
        chief_complaint=ChiefComplaint(
            text="karın ağrısı", patient_goals=("ağrının nedenini öğrenmek",)
        ),
        hpi=Hpi(
            narrative="iki gündür karın ağrısı, dün gece kötüleşmiş",
            oldcarts=Oldcarts(onset="iki gün önce", severity_nrs=6),
            associated=("bulantı",),
            negatives=("ateş yok",),
        ),
        ros_pertinent=(RosItem(system="GIS", finding="bulantı", present=True),),
        pmh=(
            PmhItem(condition="hipertansiyon", icd10="I10", status="confirmed", source="patient"),
        ),
        medications=(
            MedicationItem(
                name="omeprazol",
                atc="A02BC01",
                dose="günde bir kez yirmi miligram",
                adherence="düzenli",
                source="patient",
                reconciliation="matches",
            ),
        ),
        allergies=(AllergyItem(substance="penisilin", reaction="döküntü", severity="hafif"),),
        family_social=FamilySocial(occupation="öğretmen"),
        screening=ScreeningBlock(
            phq2=3,
            gad2=2,
            phq9=7,
            gad7=8,
            provenance=ScreeningProvenance(
                administration_mode="voice",
                proxy_reported=False,
                third_party_present=True,
                qualifier_tr="başka bir konuşmacı duyuldu",
            ),
        ),
        konusma_ozellikleri=KonusmaOzellikleri(
            speech_rate_syll_s=4.1,
            pause_ratio=0.22,
            f0_mean_hz=190.0,
            f0_sd_hz=28.0,
            response_latency_ms_mean=640.0,
            reference_ranges={"speech_rate_syll_s": "3.5-5.5"},
            recording_conditions_caveat_tr="ev ortamında, telefon mikrofonuyla kaydedildi",
        ),
        imported_objective=(
            ImportedObjectiveItem(
                type="lab",
                summary="Hemoglobin on virgül iki",
                date="2026-08-14",
                provenance="doc-0001",
            ),
        ),
        data_gaps=("belge sayfa üç okunamadı",),
        suggested_focus_questions=("ağrı sırta yayılıyor mu?",),
        considerations=(Consideration(pattern="dispepsi paterni", why="yemekle ilişkili"),),
        patient_confirmed_sections=("medications",),
    )


def test_document_bundle_validates_on_hapi(client: httpx.Client) -> None:
    bundle = previsit_note_to_document_bundle(_note(), patient_id="pt-0001")
    errors = _validate(client, "Bundle", to_wire(bundle))
    assert errors == []


def test_standalone_resources_validate_on_hapi(client: httpx.Client) -> None:
    lab = ExtractedRecordItem(
        kind=RecordItemKind.LAB,
        summary="Hemoglobin",
        code=RecordCode(system=CodeSystem.LOINC, code="718-7"),
        value_magnitude=Decimal("10.2"),
        unit="g/dL",
        date=datetime.date(2026, 8, 14),
        provenance=RecordProvenance(document_ref="doc-0001", page=2, bbox=(0.1, 0.2, 0.3, 0.4)),
    )
    diagnosis = lab.model_copy(
        update={
            "kind": RecordItemKind.DIAGNOSIS,
            "summary": "esansiyel hipertansiyon",
            "code": RecordCode(system=CodeSystem.ICD10, code="I10"),
            "value_magnitude": None,
            "unit": None,
        }
    )
    medication = lab.model_copy(
        update={
            "kind": RecordItemKind.MEDICATION,
            "summary": "omeprazol",
            "code": RecordCode(system=CodeSystem.ATC, code="A02BC01"),
            "value_magnitude": None,
            "unit": None,
        }
    )
    allergy = lab.model_copy(
        update={
            "kind": RecordItemKind.ALLERGY,
            "summary": "penisilin",
            "code": None,
            "value_magnitude": None,
            "unit": None,
        }
    )
    triage = RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id="rf.chest_pain", evidence="göğüste baskı hissi"),),
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
    )
    session = SessionState(
        session_id="sess-0001",
        protocol_id="base.intake",
        protocol_version="1.0.0",
        protocol_hash=SHA,
        mode="fast",
        status=SessionStatus.COMPLETED,
        reference_time=GENERATED_AT,
        step_states={"hpi.onset": "ASKED_PRESENT"},
        slots={"hpi.onset": "iki gündür", "hpi.severity": 6},
        budget=SessionBudget(turns_used=4, turns_remaining=14),
    )
    screening = _note().screening

    payloads: list[tuple[str, dict[str, Any]]] = [
        ("Observation", to_wire(record_item_to_r4(lab, subject_ref=SUBJECT))),
        ("Condition", to_wire(record_item_to_r4(diagnosis, subject_ref=SUBJECT))),
        (
            "MedicationStatement",
            to_wire(record_item_to_r4(medication, subject_ref=SUBJECT)),
        ),
        (
            "AllergyIntolerance",
            to_wire(record_item_to_r4(allergy, subject_ref=SUBJECT)),
        ),
        ("RiskAssessment", to_wire(triage_to_risk_assessment(triage, subject_ref=SUBJECT))),
        (
            "QuestionnaireResponse",
            to_wire(session_state_to_questionnaire_response(session, subject_ref=SUBJECT)),
        ),
    ]
    flag = triage_to_flag(triage, subject_ref=SUBJECT)
    assert flag is not None
    payloads.append(("Flag", to_wire(flag)))
    for observation in screening_to_observations(
        screening, subject_ref=SUBJECT, effective=GENERATED_AT
    ):
        payloads.append(("Observation", to_wire(observation)))

    failures: list[str] = []
    for resource_type, payload in payloads:
        for line in _validate(client, resource_type, payload):
            failures.append(f"{resource_type} -> {line}")
    assert failures == []
