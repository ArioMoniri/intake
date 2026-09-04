"""FHIR R4 → internal mappers (INT-033).

The ingestion face of files/03 §4.6: JSON/FHIR uploads bypass OCR and land
directly here, normalising into ``ExtractedRecordItem`` (LOINC for labs,
ATC for meds, ICD-10 for diagnoses; a code from an unknown system yields
``code=None`` — never a guessed code). The remaining inverses make the
files/03 §7 mapping layer genuinely bidirectional and give the hypothesis
roundtrips their return path.

Invariant 1 on ingestion: ``risk_assessment_to_triage`` refuses any
RiskAssessment whose method is not the rules engine — a foreign or
model-estimated risk figure can never become a routing result.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from decimal import Decimal
from typing import Literal

from clinical_schemas.common import JsonScalar, JsonValue
from clinical_schemas.mappers import codes
from clinical_schemas.mappers.r4 import (
    AllergyIntolerance,
    CodeableConcept,
    Condition,
    Extension,
    MedicationStatement,
    Observation,
    QrItem,
    QuestionnaireResponse,
    RiskAssessment,
)
from clinical_schemas.mappers.to_r4 import MappingError
from clinical_schemas.note import (
    AllergyItem,
    MedicationItem,
    PmhItem,
    ScreeningBlock,
    ScreeningProvenance,
)
from clinical_schemas.records import (
    ExtractedRecordItem,
    RecordCode,
    RecordItemKind,
    RecordProvenance,
    VerificationStatus,
)
from clinical_schemas.session import (
    AnswerState,
    SessionBudget,
    SessionState,
    SessionStatus,
)
from clinical_schemas.triage import (
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)

_CATEGORY_KIND: dict[str, RecordItemKind] = {
    "laboratory": RecordItemKind.LAB,
    "imaging": RecordItemKind.IMAGING,
    "procedure": RecordItemKind.PROCEDURE,
}

_CONFIRMED_OBSERVATION_STATUS = frozenset({"final", "amended", "corrected"})


def _ext_map(extensions: tuple[Extension, ...] | None) -> dict[str, Extension]:
    return {e.url: e for e in extensions or ()}


def _known_code(concept: CodeableConcept | None) -> RecordCode | None:
    """First coding from a system the blueprint names (files/03 §7); anything
    else is left uncoded rather than guessed (files/03 §4.6)."""
    if concept is None:
        return None
    for coding in concept.coding or ():
        system = codes.URI_CODE_SYSTEM.get(coding.system or "")
        if system is not None and coding.code:
            return RecordCode(system=system, code=coding.code)
    return None


def _summary(concept: CodeableConcept | None, resource_name: str) -> str:
    if concept is not None:
        if concept.text:
            return concept.text
        for coding in concept.coding or ():
            if coding.display:
                return coding.display
    raise MappingError(f"{resource_name} carries no human-readable summary")


def _date_part(value: str | None, field: str) -> datetime.date | None:
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(value[:10])
    except ValueError as exc:
        raise MappingError(f"{field} is not a parseable FHIR date: {value!r}") from exc


def _provenance(ext: dict[str, Extension], document_ref: str) -> RecordProvenance:
    ref_ext = ext.get(codes.EXT_DOCUMENT_REF)
    ref = ref_ext.value_string if ref_ext and ref_ext.value_string else document_ref
    page_ext = ext.get(codes.EXT_PAGE)
    bbox: tuple[float, float, float, float] | None = None
    bbox_ext = ext.get(codes.EXT_BBOX)
    if bbox_ext is not None:
        corners = {e.url: e.value_decimal for e in bbox_ext.extension or ()}
        try:
            bbox = (
                float(corners["x0"]),  # type: ignore[arg-type]
                float(corners["y0"]),  # type: ignore[arg-type]
                float(corners["x1"]),  # type: ignore[arg-type]
                float(corners["y1"]),  # type: ignore[arg-type]
            )
        except (KeyError, TypeError) as exc:
            raise MappingError("source-bbox extension is incomplete") from exc
    return RecordProvenance(
        document_ref=ref,
        page=page_ext.value_integer if page_ext else None,
        bbox=bbox,
    )


def _unit_conflict(ext: dict[str, Extension]) -> bool:
    flag = ext.get(codes.EXT_UNIT_CONFLICT)
    return bool(flag.value_boolean) if flag else False


def _concept_verification(concept: CodeableConcept | None) -> VerificationStatus:
    for coding in (concept.coding or ()) if concept else ():
        if coding.code == "confirmed":
            return VerificationStatus.CONFIRMED
    return VerificationStatus.UNCONFIRMED


def observation_to_record_item(
    observation: Observation, *, document_ref: str
) -> ExtractedRecordItem:
    """Observation → lab/imaging/procedure item. The kind comes from the
    standard category codes; a category-less Observation is accepted as a
    lab only when it carries a LOINC coding (files/03 §7: LOINC for labs) —
    otherwise the kind would be a guess, and we refuse instead."""
    kind: RecordItemKind | None = None
    for category in observation.category or ():
        for coding in category.coding or ():
            if coding.system == codes.OBSERVATION_CATEGORY:
                if coding.code == "survey":
                    raise MappingError(
                        "a survey Observation is a screening score, not a record item"
                    )
                kind = _CATEGORY_KIND.get(coding.code or "")
    if kind is None:
        loinc_coded = any(coding.system == codes.LOINC for coding in observation.code.coding or ())
        if not loinc_coded:
            raise MappingError(
                "cannot determine the record kind: no observation-category and no "
                "LOINC coding — refusing to guess"
            )
        kind = RecordItemKind.LAB
    ext = _ext_map(observation.extension)
    quantity = observation.value_quantity
    return ExtractedRecordItem(
        kind=kind,
        summary=_summary(observation.code, "Observation.code"),
        code=_known_code(observation.code),
        value_magnitude=quantity.value if quantity else None,
        unit=quantity.unit if quantity else None,
        unit_conflict=_unit_conflict(ext),
        date=_date_part(observation.effective_date_time, "effectiveDateTime"),
        verification_status=(
            VerificationStatus.CONFIRMED
            if observation.status in _CONFIRMED_OBSERVATION_STATUS
            else VerificationStatus.UNCONFIRMED
        ),
        provenance=_provenance(ext, document_ref),
    )


def condition_to_record_item(condition: Condition, *, document_ref: str) -> ExtractedRecordItem:
    """Condition → diagnosis item; verification from the native
    condition-ver-status coding (files/03 §4.6)."""
    ext = _ext_map(condition.extension)
    return ExtractedRecordItem(
        kind=RecordItemKind.DIAGNOSIS,
        summary=_summary(condition.code, "Condition.code"),
        code=_known_code(condition.code),
        date=_date_part(condition.recorded_date, "recordedDate"),
        verification_status=_concept_verification(condition.verification_status),
        provenance=_provenance(ext, document_ref),
    )


def medication_statement_to_record_item(
    statement: MedicationStatement, *, document_ref: str
) -> ExtractedRecordItem:
    """MedicationStatement → medication item; INTAKE verification travels in
    the dedicated extension because R4 gives this resource no such concept."""
    ext = _ext_map(statement.extension)
    verification_ext = ext.get(codes.EXT_VERIFICATION)
    verification = (
        VerificationStatus.CONFIRMED
        if verification_ext is not None and verification_ext.value_string == "confirmed"
        else VerificationStatus.UNCONFIRMED
    )
    return ExtractedRecordItem(
        kind=RecordItemKind.MEDICATION,
        summary=_summary(statement.medication_codeable_concept, "medicationCodeableConcept"),
        code=_known_code(statement.medication_codeable_concept),
        date=_date_part(statement.date_asserted, "dateAsserted"),
        verification_status=verification,
        provenance=_provenance(ext, document_ref),
    )


def allergy_intolerance_to_record_item(
    allergy: AllergyIntolerance, *, document_ref: str
) -> ExtractedRecordItem:
    """AllergyIntolerance → allergy item; verification from the native
    allergyintolerance-verification coding."""
    ext = _ext_map(allergy.extension)
    return ExtractedRecordItem(
        kind=RecordItemKind.ALLERGY,
        summary=_summary(allergy.code, "AllergyIntolerance.code"),
        code=_known_code(allergy.code),
        date=_date_part(allergy.recorded_date, "recordedDate"),
        verification_status=_concept_verification(allergy.verification_status),
        provenance=_provenance(ext, document_ref),
    )


def r4_to_record_item(
    resource: Observation | Condition | MedicationStatement | AllergyIntolerance,
    *,
    document_ref: str,
) -> ExtractedRecordItem:
    """Resource-type dispatch, the inverse of ``record_item_to_r4``."""
    if isinstance(resource, Observation):
        return observation_to_record_item(resource, document_ref=document_ref)
    if isinstance(resource, Condition):
        return condition_to_record_item(resource, document_ref=document_ref)
    if isinstance(resource, MedicationStatement):
        return medication_statement_to_record_item(resource, document_ref=document_ref)
    return allergy_intolerance_to_record_item(resource, document_ref=document_ref)


# ------------------------------------------------------------------ note items


def _ext_string(ext: dict[str, Extension], url: str) -> str:
    entry = ext.get(url)
    return entry.value_string or "" if entry else ""


def medication_statement_to_medication_item(
    statement: MedicationStatement,
) -> MedicationItem:
    ext = _ext_map(statement.extension)
    reconciliation = _ext_string(ext, codes.EXT_RECONCILIATION)
    if reconciliation not in ("matches", "new", "stopped", "conflict"):
        raise MappingError(
            "MedicationStatement carries no INTAKE reconciliation extension — "
            "not a note medication item"
        )
    atc: str | None = None
    for coding in statement.medication_codeable_concept.coding or ():
        if coding.system == codes.ATC and coding.code:
            atc = coding.code
    return MedicationItem(
        name=_summary(statement.medication_codeable_concept, "medicationCodeableConcept"),
        atc=atc,
        dose=statement.dosage[0].text if statement.dosage else "",
        adherence=_ext_string(ext, codes.EXT_ADHERENCE),
        source=_ext_string(ext, codes.EXT_MED_SOURCE),
        reconciliation=reconciliation,  # type: ignore[arg-type]
    )


def condition_to_pmh_item(condition: Condition) -> PmhItem:
    ext = _ext_map(condition.extension)
    source = _ext_string(ext, codes.EXT_PMH_SOURCE)
    if source not in ("patient", "record"):
        raise MappingError("Condition carries no INTAKE pmh-source extension — not a note pmh item")
    icd10: str | None = None
    for coding in (condition.code.coding or ()) if condition.code else ():
        if coding.system == codes.ICD10 and coding.code:
            icd10 = coding.code
    status: Literal["confirmed", "unconfirmed"] = (
        "confirmed"
        if _concept_verification(condition.verification_status) is VerificationStatus.CONFIRMED
        else "unconfirmed"
    )
    return PmhItem(
        condition=_summary(condition.code, "Condition.code"),
        icd10=icd10,
        status=status,
        source=source,  # type: ignore[arg-type]
    )


def allergy_intolerance_to_allergy_item(allergy: AllergyIntolerance) -> AllergyItem:
    ext = _ext_map(allergy.extension)
    reaction = ""
    if allergy.reaction:
        manifestations = allergy.reaction[0].manifestation
        if manifestations and manifestations[0].text:
            reaction = manifestations[0].text
    return AllergyItem(
        substance=_summary(allergy.code, "AllergyIntolerance.code"),
        reaction=reaction,
        severity=_ext_string(ext, codes.EXT_ALLERGY_SEVERITY),
    )


# ------------------------------------------------------------------- screening


def observations_to_screening_block(
    observations: Sequence[Observation],
) -> ScreeningBlock:
    """Survey Observations → ScreeningBlock. The provenance qualifiers are
    required on every score (files/04 §4.3); missing qualifiers refuse
    rather than fabricating an administration mode."""
    if not observations:
        raise MappingError("no screening observations to map")
    scores: dict[str, int] = {}
    for observation in observations:
        instrument: str | None = None
        for coding in observation.code.coding or ():
            if coding.system == codes.SCREENING_SYSTEM:
                instrument = coding.code
        if instrument not in codes.SCREENING_INSTRUMENTS:
            raise MappingError(f"unknown screening instrument coding: {instrument!r}")
        if observation.value_integer is None:
            raise MappingError(f"screening observation {instrument} carries no score")
        scores[instrument] = observation.value_integer
    ext = _ext_map(observations[0].extension)
    mode = _ext_string(ext, codes.EXT_ADMINISTRATION_MODE)
    if mode not in ("voice", "typed", "keypad"):
        raise MappingError("screening observation carries no administration-mode qualifier")
    proxy = ext.get(codes.EXT_PROXY_REPORTED)
    third_party = ext.get(codes.EXT_THIRD_PARTY_PRESENT)
    if proxy is None or third_party is None:
        raise MappingError("screening observation is missing its provenance qualifiers")
    return ScreeningBlock(
        phq2=scores.get("phq2"),
        gad2=scores.get("gad2"),
        phq9=scores.get("phq9"),
        gad7=scores.get("gad7"),
        provenance=ScreeningProvenance(
            administration_mode=mode,  # type: ignore[arg-type]
            proxy_reported=bool(proxy.value_boolean),
            third_party_present=bool(third_party.value_boolean),
            qualifier_tr=_ext_string(ext, codes.EXT_QUALIFIER_TR),
        ),
    )


# ---------------------------------------------------------------------- triage


def risk_assessment_to_triage(assessment: RiskAssessment) -> RulesTriageResult:
    """RiskAssessment → RulesTriageResult, only when the method names the
    rules engine (invariant 1 on ingestion: no other provenance may become
    a routing result)."""
    method_codes = {
        coding.code
        for coding in ((assessment.method.coding or ()) if assessment.method else ())
        if coding.system == codes.TRIAGE_METHOD_SYSTEM
    }
    if method_codes != {codes.TRIAGE_METHOD_RULES}:
        raise MappingError(
            "RiskAssessment.method does not name the rules engine — refusing to "
            "ingest as a triage result (invariant 1)"
        )
    level: TriageLevel | None = None
    for prediction in assessment.prediction or ():
        risk = prediction.qualitative_risk
        for coding in (risk.coding or ()) if risk else ():
            if coding.system == codes.TRIAGE_LEVEL_SYSTEM and coding.code:
                level = TriageLevel(coding.code)
    if level is None:
        raise MappingError("RiskAssessment carries no triage-level prediction")
    rules = tuple(
        RuleFire(id=coding.code, evidence=concept.text or "")
        for concept in assessment.reason_code or ()
        for coding in concept.coding or ()
        if coding.system == codes.TRIAGE_RULE_SYSTEM and coding.code
    )
    ext = _ext_map(assessment.extension)
    register = _ext_string(ext, codes.EXT_RED_REGISTER)
    location = _ext_string(ext, codes.EXT_RED_LOCATION)
    return RulesTriageResult(
        level=level,
        rules=rules,
        register=RedRegister(register) if register else None,
        location=RedLocation(location) if location else None,
    )


# --------------------------------------------------------- QuestionnaireResponse


def _item_value(item: QrItem) -> JsonValue:
    if item.item:
        # JsonScalar rather than a hand-spelled copy of it: the carrier gained
        # Decimal in INT-303 and a duplicate spelling would have gone stale.
        out: dict[str, JsonScalar] = {}
        for child in item.item:
            if child.answer is None or len(child.answer) != 1:
                raise MappingError(f"nested item {child.link_id!r} must carry exactly one answer")
            out[child.link_id] = _answer_scalar(child)
        return out
    if item.answer is None:
        raise MappingError(f"item {item.link_id!r} has neither answers nor children")
    ext = _ext_map(item.extension)
    list_marker = ext.get(codes.EXT_LIST_SLOT)
    if list_marker is not None and list_marker.value_boolean:
        return [_answer_scalar(item, index) for index in range(len(item.answer))]
    if len(item.answer) != 1:
        raise MappingError(
            f"item {item.link_id!r} carries multiple answers without the list marker"
        )
    return _answer_scalar(item)


def _answer_scalar(item: QrItem, index: int = 0) -> str | int | Decimal | float | bool:
    """``Decimal`` is in the return type because ``QrAnswer.value_decimal``
    carries one (INT-309): a clinical quantity that went out with a declared
    scale comes back with it, rather than as the ``float`` the pre-INT-303
    carrier would have flattened it to."""
    answer = (item.answer or ())[index]
    if answer.value_boolean is not None:
        return answer.value_boolean
    if answer.value_integer is not None:
        return answer.value_integer
    if answer.value_decimal is not None:
        return answer.value_decimal
    if answer.value_string is not None:
        return answer.value_string
    raise MappingError(f"item {item.link_id!r} answer {index} carries no value")


def questionnaire_response_to_session_state(
    response: QuestionnaireResponse,
    *,
    step_states: dict[str, AnswerState],
    budget: SessionBudget,
) -> SessionState:
    """QuestionnaireResponse → SessionState. A QR is the answers, not the
    engine bookkeeping: ``step_states`` and ``budget`` never cross the FHIR
    boundary, so the caller supplies them — the loss is in the signature,
    not in a silent default."""
    if response.identifier is None or not response.identifier.value:
        raise MappingError("QuestionnaireResponse carries no session identifier")
    canonical = response.questionnaire or ""
    if not canonical.startswith(codes.PROTOCOL_CANONICAL_PREFIX) or "|" not in canonical:
        raise MappingError(
            f"questionnaire canonical is not an INTAKE protocol reference: {canonical!r}"
        )
    protocol_id, _, protocol_version = canonical.removeprefix(
        codes.PROTOCOL_CANONICAL_PREFIX
    ).partition("|")
    ext = _ext_map(response.extension)
    protocol_hash = _ext_string(ext, codes.EXT_PROTOCOL_HASH)
    mode = _ext_string(ext, codes.EXT_MODE)
    if mode not in ("fast", "detailed"):
        raise MappingError("QuestionnaireResponse carries no INTAKE intake-mode extension")
    status_text = _ext_string(ext, codes.EXT_SESSION_STATUS)
    if status_text:
        status = SessionStatus(status_text)
    elif response.status == "completed":
        status = SessionStatus.COMPLETED
    elif response.status == "stopped":
        status = SessionStatus.CANCELLED
    elif response.status == "in-progress":
        status = SessionStatus.ACTIVE
    else:
        raise MappingError(f"unmappable QuestionnaireResponse.status: {response.status!r}")
    if response.authored is None:
        raise MappingError("QuestionnaireResponse carries no authored timestamp")
    return SessionState(
        session_id=response.identifier.value,
        protocol_id=protocol_id,
        protocol_version=protocol_version,
        protocol_hash=protocol_hash,
        mode=mode,  # type: ignore[arg-type]
        status=status,
        reference_time=datetime.datetime.fromisoformat(response.authored),
        step_states=step_states,
        slots={item.link_id: _item_value(item) for item in response.item or ()},
        budget=budget,
    )
