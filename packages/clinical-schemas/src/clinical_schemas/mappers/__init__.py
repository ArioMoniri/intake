"""INTAKE ↔ FHIR R4 mapping layer (INT-033).

files/03 §7: "Mapping layer ``packages/clinical-schemas/mappers/`` is
bidirectional and tested with round-trip golden files. Code systems: ICD-10
(e-Nabız/SGK usage), ATC for drugs, LOINC for labs." ADR-002: FHIR R4 is the
canonical exchange format.

The internal side is exactly the INT-031 models — nothing here invents an
internal shape. The R4 side is the minimal profiled subset in
``clinical_schemas.mappers.r4``.
"""

from __future__ import annotations

from clinical_schemas.mappers.codes import NOTE_SECTION_IDS
from clinical_schemas.mappers.document import previsit_note_to_document_bundle
from clinical_schemas.mappers.from_r4 import (
    allergy_intolerance_to_allergy_item,
    allergy_intolerance_to_record_item,
    condition_to_pmh_item,
    condition_to_record_item,
    medication_statement_to_medication_item,
    medication_statement_to_record_item,
    observation_to_record_item,
    observations_to_screening_block,
    questionnaire_response_to_session_state,
    r4_to_record_item,
    risk_assessment_to_triage,
)
from clinical_schemas.mappers.r4 import to_wire
from clinical_schemas.mappers.to_r4 import (
    MappingError,
    allergy_item_to_allergy_intolerance,
    medication_item_to_medication_statement,
    pmh_item_to_condition,
    record_item_to_allergy_intolerance,
    record_item_to_condition,
    record_item_to_medication_statement,
    record_item_to_observation,
    record_item_to_r4,
    screening_to_observations,
    session_state_to_questionnaire_response,
    triage_to_flag,
    triage_to_risk_assessment,
)

__all__ = [
    "NOTE_SECTION_IDS",
    "MappingError",
    "allergy_intolerance_to_allergy_item",
    "allergy_intolerance_to_record_item",
    "allergy_item_to_allergy_intolerance",
    "condition_to_pmh_item",
    "condition_to_record_item",
    "medication_item_to_medication_statement",
    "medication_statement_to_medication_item",
    "medication_statement_to_record_item",
    "observation_to_record_item",
    "observations_to_screening_block",
    "pmh_item_to_condition",
    "previsit_note_to_document_bundle",
    "questionnaire_response_to_session_state",
    "r4_to_record_item",
    "record_item_to_allergy_intolerance",
    "record_item_to_condition",
    "record_item_to_medication_statement",
    "record_item_to_observation",
    "record_item_to_r4",
    "risk_assessment_to_triage",
    "screening_to_observations",
    "session_state_to_questionnaire_response",
    "to_wire",
    "triage_to_flag",
    "triage_to_risk_assessment",
]
