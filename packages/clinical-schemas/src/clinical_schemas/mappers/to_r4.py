"""Internal → FHIR R4 mappers (INT-033).

Sources: files/03 §4.6 (ExtractedRecordItem → Observation/Condition/… with
``verificationStatus=unconfirmed`` and Provenance page/bbox), files/03 §5
(engine output → QuestionnaireResponse + Observations), files/03 §7
(resource roles: Observation performer=Patient for screening, Condition
verificationStatus, RiskAssessment for triage, Flag for RED/YELLOW).

Invariant 1's interop face: only ``RulesTriageResult`` may become a
RiskAssessment or Flag. An ``LlmCandidateTriage`` is refused at runtime on
top of the type signature — candidates are clinician-review material and
never exchangeable clinical assertions.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from clinical_schemas.common import JsonScalar, JsonValue
from clinical_schemas.mappers import codes
from clinical_schemas.mappers.r4 import (
    AllergyIntolerance,
    AllergyReaction,
    CodeableConcept,
    Coding,
    Condition,
    Dosage,
    Extension,
    Flag,
    Identifier,
    MedicationStatement,
    Observation,
    QrAnswer,
    QrItem,
    Quantity,
    QuestionnaireResponse,
    Reference,
    RiskAssessment,
    RiskPrediction,
)
from clinical_schemas.note import AllergyItem, MedicationItem, PmhItem, ScreeningBlock
from clinical_schemas.records import ExtractedRecordItem, RecordCode, RecordItemKind
from clinical_schemas.session import SessionState, SessionStatus
from clinical_schemas.triage import RuleFire, RulesTriageResult, TriageLevel


class MappingError(ValueError):
    """A value that must not cross the FHIR boundary as-is. Raised instead
    of silently dropping or converting (INT-033 scope: loss is explicit)."""


_OBSERVATION_CATEGORY: dict[RecordItemKind, str] = {
    RecordItemKind.LAB: "laboratory",
    RecordItemKind.IMAGING: "imaging",
    RecordItemKind.PROCEDURE: "procedure",
}

_SESSION_TO_QR_STATUS: dict[SessionStatus, str] = {
    SessionStatus.CREATED: "in-progress",
    SessionStatus.ACTIVE: "in-progress",
    SessionStatus.COMPLETED: "completed",
    SessionStatus.CANCELLED: "stopped",
}


def _concept(system: str, code: str, text: str | None = None) -> CodeableConcept:
    return CodeableConcept(coding=(Coding(system=system, code=code),), text=text)


def _record_concept(code: RecordCode | None, text: str) -> CodeableConcept:
    if code is None:
        return CodeableConcept(text=text)
    return CodeableConcept(
        coding=(Coding(system=codes.CODE_SYSTEM_URI[code.system], code=code.code),),
        text=text,
    )


def _string_ext(url: str, value: str) -> Extension:
    return Extension(url=url, value_string=value)


def _provenance_extensions(item: ExtractedRecordItem) -> tuple[Extension, ...]:
    out: list[Extension] = [_string_ext(codes.EXT_DOCUMENT_REF, item.provenance.document_ref)]
    if item.provenance.page is not None:
        out.append(Extension(url=codes.EXT_PAGE, value_integer=item.provenance.page))
    if item.provenance.bbox is not None:
        x0, y0, x1, y1 = item.provenance.bbox
        out.append(
            Extension(
                url=codes.EXT_BBOX,
                extension=(
                    Extension(url="x0", value_decimal=x0),
                    Extension(url="y0", value_decimal=y0),
                    Extension(url="x1", value_decimal=x1),
                    Extension(url="y1", value_decimal=y1),
                ),
            )
        )
    if item.unit_conflict:
        # CLAUDE.md invariant 22: disagreement raises a flag and travels as
        # one; nothing here ever converts a magnitude.
        out.append(Extension(url=codes.EXT_UNIT_CONFLICT, value_boolean=True))
    return tuple(out)


def _refuse_value_on(item: ExtractedRecordItem) -> None:
    if item.value_magnitude is not None or item.unit is not None or item.unit_conflict:
        raise MappingError(
            f"a {item.kind.value} item cannot carry a numeric value on the FHIR "
            "boundary; only lab/imaging/procedure items map to Observation values"
        )


def record_item_to_observation(item: ExtractedRecordItem, *, subject_ref: str) -> Observation:
    """LAB/IMAGING/PROCEDURE → Observation (files/03 §4.6; category codes are
    the standard observation-category codes, recoverable on ingestion)."""
    category = _OBSERVATION_CATEGORY.get(item.kind)
    if category is None:
        raise MappingError(f"{item.kind.value} does not map to Observation")
    quantity: Quantity | None = None
    if item.value_magnitude is not None or item.unit is not None:
        quantity = Quantity(value=item.value_magnitude, unit=item.unit)
    return Observation(
        extension=_provenance_extensions(item),
        status="final" if item.verification_status == "confirmed" else "preliminary",
        category=(_concept(codes.OBSERVATION_CATEGORY, category),),
        code=_record_concept(item.code, item.summary),
        subject=Reference(reference=subject_ref),
        effective_date_time=item.date.isoformat() if item.date else None,
        value_quantity=quantity,
    )


def record_item_to_condition(item: ExtractedRecordItem, *, subject_ref: str) -> Condition:
    """DIAGNOSIS → Condition with native verificationStatus (files/03 §4.6:
    ``verificationStatus=unconfirmed`` until the patient confirms)."""
    if item.kind is not RecordItemKind.DIAGNOSIS:
        raise MappingError(f"{item.kind.value} does not map to Condition")
    _refuse_value_on(item)
    return Condition(
        extension=_provenance_extensions(item),
        verification_status=_concept(codes.CONDITION_VER_STATUS, item.verification_status.value),
        code=_record_concept(item.code, item.summary),
        subject=Reference(reference=subject_ref),
        recorded_date=item.date.isoformat() if item.date else None,
    )


def record_item_to_medication_statement(
    item: ExtractedRecordItem, *, subject_ref: str
) -> MedicationStatement:
    """MEDICATION → MedicationStatement. The extraction pipeline cannot know
    whether a med on an old report is still taken, so status is the honest
    ``unknown`` and the INTAKE verification travels as an extension."""
    if item.kind is not RecordItemKind.MEDICATION:
        raise MappingError(f"{item.kind.value} does not map to MedicationStatement")
    _refuse_value_on(item)
    return MedicationStatement(
        extension=(
            *_provenance_extensions(item),
            _string_ext(codes.EXT_VERIFICATION, item.verification_status.value),
        ),
        status="unknown",
        medication_codeable_concept=_record_concept(item.code, item.summary),
        subject=Reference(reference=subject_ref),
        date_asserted=item.date.isoformat() if item.date else None,
    )


def record_item_to_allergy_intolerance(
    item: ExtractedRecordItem, *, subject_ref: str
) -> AllergyIntolerance:
    """ALLERGY → AllergyIntolerance with native verificationStatus.
    ``clinicalStatus=active`` is required by R4 rule ait-1 whenever
    verificationStatus is not entered-in-error."""
    if item.kind is not RecordItemKind.ALLERGY:
        raise MappingError(f"{item.kind.value} does not map to AllergyIntolerance")
    _refuse_value_on(item)
    return AllergyIntolerance(
        extension=_provenance_extensions(item),
        clinical_status=_concept(codes.ALLERGY_CLINICAL, "active"),
        verification_status=_concept(codes.ALLERGY_VER_STATUS, item.verification_status.value),
        code=_record_concept(item.code, item.summary),
        patient=Reference(reference=subject_ref),
        recorded_date=item.date.isoformat() if item.date else None,
    )


def record_item_to_r4(
    item: ExtractedRecordItem, *, subject_ref: str
) -> Observation | Condition | MedicationStatement | AllergyIntolerance:
    """Kind dispatch for the files/03 §4.6 ingestion pipeline output."""
    if item.kind in _OBSERVATION_CATEGORY:
        return record_item_to_observation(item, subject_ref=subject_ref)
    if item.kind is RecordItemKind.DIAGNOSIS:
        return record_item_to_condition(item, subject_ref=subject_ref)
    if item.kind is RecordItemKind.MEDICATION:
        return record_item_to_medication_statement(item, subject_ref=subject_ref)
    return record_item_to_allergy_intolerance(item, subject_ref=subject_ref)


# ------------------------------------------------------------------ note items


def medication_item_to_medication_statement(
    item: MedicationItem, *, subject_ref: str
) -> MedicationStatement:
    """files/04 §5 medications[] → MedicationStatement. The dose stays the
    Turkish orthography text verbatim (invariant 22: numbers never cross a
    representation boundary unguarded — no numeric re-parse here)."""
    extensions = [_string_ext(codes.EXT_RECONCILIATION, item.reconciliation)]
    if item.adherence:
        extensions.append(_string_ext(codes.EXT_ADHERENCE, item.adherence))
    if item.source:
        extensions.append(_string_ext(codes.EXT_MED_SOURCE, item.source))
    concept = (
        CodeableConcept(coding=(Coding(system=codes.ATC, code=item.atc),), text=item.name)
        if item.atc
        else CodeableConcept(text=item.name)
    )
    return MedicationStatement(
        extension=tuple(extensions),
        status="unknown",
        medication_codeable_concept=concept,
        subject=Reference(reference=subject_ref),
        dosage=(Dosage(text=item.dose),) if item.dose else None,
    )


def pmh_item_to_condition(item: PmhItem, *, subject_ref: str) -> Condition:
    """files/04 §5 pmh[] → Condition; confirmed|unconfirmed map onto the
    native condition-ver-status codes unchanged."""
    concept = (
        CodeableConcept(coding=(Coding(system=codes.ICD10, code=item.icd10),), text=item.condition)
        if item.icd10
        else CodeableConcept(text=item.condition)
    )
    return Condition(
        extension=(_string_ext(codes.EXT_PMH_SOURCE, item.source),),
        verification_status=_concept(codes.CONDITION_VER_STATUS, item.status),
        code=concept,
        subject=Reference(reference=subject_ref),
    )


def allergy_item_to_allergy_intolerance(
    item: AllergyItem, *, subject_ref: str
) -> AllergyIntolerance:
    """files/04 §5 allergies[] → AllergyIntolerance. The free-text severity
    is carried as an extension rather than forced into the coded
    ``reaction.severity`` value set — never a guessed code."""
    return AllergyIntolerance(
        extension=(
            (_string_ext(codes.EXT_ALLERGY_SEVERITY, item.severity),) if item.severity else None
        ),
        clinical_status=_concept(codes.ALLERGY_CLINICAL, "active"),
        verification_status=_concept(codes.ALLERGY_VER_STATUS, "confirmed"),
        code=CodeableConcept(text=item.substance),
        patient=Reference(reference=subject_ref),
        reaction=(
            (AllergyReaction(manifestation=(CodeableConcept(text=item.reaction),)),)
            if item.reaction
            else None
        ),
    )


# ------------------------------------------------------------------- screening


def _screening_qualifiers(block: ScreeningBlock) -> tuple[Extension, ...]:
    # files/04 §4.3: the factual provenance qualifiers ride with every
    # instrument score, never detached from it.
    out = [
        _string_ext(codes.EXT_ADMINISTRATION_MODE, block.provenance.administration_mode),
        Extension(url=codes.EXT_PROXY_REPORTED, value_boolean=block.provenance.proxy_reported),
        Extension(
            url=codes.EXT_THIRD_PARTY_PRESENT,
            value_boolean=block.provenance.third_party_present,
        ),
    ]
    if block.provenance.qualifier_tr:
        out.append(_string_ext(codes.EXT_QUALIFIER_TR, block.provenance.qualifier_tr))
    return tuple(out)


def screening_to_observations(
    block: ScreeningBlock,
    *,
    subject_ref: str,
    effective: datetime.datetime | None = None,
) -> tuple[Observation, ...]:
    """Screening totals → survey Observations with ``performer=Patient``
    (files/03 §7). The C-SSRS slot never crosses into exchange: the
    instrument licence is BLOCKED (HUMAN_BLOCKERS.md HB-L2) and its shape is
    unfixed — an explicit, tested omission, not an oversight."""
    qualifiers = _screening_qualifiers(block)
    scores: dict[str, int | None] = {
        "phq2": block.phq2,
        "gad2": block.gad2,
        "phq9": block.phq9,
        "gad7": block.gad7,
    }
    out: list[Observation] = []
    for instrument in codes.SCREENING_INSTRUMENTS:
        score = scores[instrument]
        if score is None:
            continue  # files/12 §2.2: InstrumentNotScored is never a number
        codings: list[Coding] = []
        loinc = codes.LOINC_TOTALS.get(instrument)
        if loinc is not None:
            codings.append(Coding(system=codes.LOINC, code=loinc))
        codings.append(Coding(system=codes.SCREENING_SYSTEM, code=instrument))
        out.append(
            Observation(
                extension=qualifiers,
                status="final",
                category=(_concept(codes.OBSERVATION_CATEGORY, "survey"),),
                code=CodeableConcept(coding=tuple(codings), text=instrument),
                subject=Reference(reference=subject_ref),
                performer=(Reference(reference=subject_ref),),
                effective_date_time=effective.isoformat() if effective else None,
                value_integer=score,
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------- triage


def _require_rules_result(result: RulesTriageResult) -> None:
    if not isinstance(result, RulesTriageResult) or result.source != "rules":
        raise MappingError(
            "only a packages/protocols/triage rules result maps to a FHIR triage "
            "resource; LLM candidates are clinician-review material (invariant 1)"
        )


def _rule_concepts(rules: tuple[RuleFire, ...]) -> tuple[CodeableConcept, ...] | None:
    if not rules:
        return None
    return tuple(
        CodeableConcept(
            coding=(Coding(system=codes.TRIAGE_RULE_SYSTEM, code=rule.id),),
            text=rule.evidence,
        )
        for rule in rules
    )


def triage_to_risk_assessment(result: RulesTriageResult, *, subject_ref: str) -> RiskAssessment:
    """RulesTriageResult → RiskAssessment (files/03 §7: "RiskAssessment
    (triage)"). Categorical only — the prediction subset has no probability
    element at all (invariant 20)."""
    _require_rules_result(result)
    extensions: list[Extension] = []
    if result.register is not None:
        extensions.append(_string_ext(codes.EXT_RED_REGISTER, result.register.value))
    if result.location is not None:
        extensions.append(_string_ext(codes.EXT_RED_LOCATION, result.location.value))
    return RiskAssessment(
        extension=tuple(extensions) or None,
        status="final",
        method=_concept(codes.TRIAGE_METHOD_SYSTEM, codes.TRIAGE_METHOD_RULES),
        subject=Reference(reference=subject_ref),
        reason_code=_rule_concepts(result.rules),
        prediction=(
            RiskPrediction(
                qualitative_risk=_concept(codes.TRIAGE_LEVEL_SYSTEM, result.level.value)
            ),
        ),
    )


def triage_to_flag(result: RulesTriageResult, *, subject_ref: str) -> Flag | None:
    """RulesTriageResult → Flag for RED/YELLOW only (files/03 §7: "Flag
    (RED/YELLOW)"); GREEN raises no flag."""
    _require_rules_result(result)
    if result.level is TriageLevel.GREEN:
        return None
    codings = [Coding(system=codes.TRIAGE_LEVEL_SYSTEM, code=result.level.value)]
    codings.extend(Coding(system=codes.TRIAGE_RULE_SYSTEM, code=rule.id) for rule in result.rules)
    return Flag(
        status="active",
        code=CodeableConcept(coding=tuple(codings), text=result.level.value),
        subject=Reference(reference=subject_ref),
    )


# --------------------------------------------------------- QuestionnaireResponse


def _scalar_answer(value: JsonScalar, slot: str) -> QrAnswer:
    if isinstance(value, bool):
        return QrAnswer(value_boolean=value)
    if isinstance(value, int):
        if not codes.FHIR_INT32_MIN <= value <= codes.FHIR_INT32_MAX:
            raise MappingError(
                f"slot {slot!r}: integer outside the FHIR 32-bit range cannot be "
                "represented losslessly"
            )
        return QrAnswer(value_integer=value)
    if isinstance(value, (Decimal, float)):
        # One branch for both, because ``QrAnswer.value_decimal`` carries
        # both and keeps them apart (INT-309). Before that a Decimal — the
        # type files/13 §9.5 names for a clinical quantity, and the type
        # extraction produces — fell past every branch to the raise below.
        return QrAnswer(value_decimal=value)
    if isinstance(value, str):
        return QrAnswer(value_string=value)
    if value is None:
        # True here and only here: _slot_item drops a top-level None and a
        # None dict entry, so the only None that reaches this function is
        # one inside a list. That is what the message used to say about
        # every unhandled type, including a Decimal.
        raise MappingError(f"slot {slot!r}: a None answer inside a list is malformed")
    raise MappingError(
        f"slot {slot!r}: an answer of type {type(value).__name__!r} is outside "
        "clinical_schemas.common.JsonScalar and has no FHIR answer element"
    )


def _slot_item(slot: str, value: JsonValue) -> QrItem | None:
    # A None answer is never emitted, at any depth: an unanswered slot is
    # absence, not a value (pinned in tests).
    if value is None:
        return None
    if isinstance(value, list):
        return QrItem(
            link_id=slot,
            extension=(Extension(url=codes.EXT_LIST_SLOT, value_boolean=True),),
            answer=tuple(_scalar_answer(v, slot) for v in value),
        )
    if isinstance(value, dict):
        children = tuple(
            QrItem(link_id=key, answer=(_scalar_answer(v, f"{slot}.{key}"),))
            for key, v in value.items()
            if v is not None
        )
        if not children:
            return None
        return QrItem(link_id=slot, item=children)
    return QrItem(link_id=slot, answer=(_scalar_answer(value, slot),))


def session_state_to_questionnaire_response(
    state: SessionState, *, subject_ref: str
) -> QuestionnaireResponse:
    """SessionState answers → QuestionnaireResponse (files/03 §5: the engine
    state persists as QuestionnaireResponse + Observations). ``step_states``
    and ``budget`` are engine bookkeeping, not answers — the inverse takes
    them back explicitly, which is the documented loss."""
    items = tuple(
        item for slot, value in state.slots.items() if (item := _slot_item(slot, value)) is not None
    )
    return QuestionnaireResponse(
        extension=(
            _string_ext(codes.EXT_PROTOCOL_HASH, state.protocol_hash),
            _string_ext(codes.EXT_MODE, state.mode),
            _string_ext(codes.EXT_SESSION_STATUS, state.status.value),
        ),
        identifier=Identifier(system=codes.SESSION_ID_SYSTEM, value=state.session_id),
        questionnaire=(
            f"{codes.PROTOCOL_CANONICAL_PREFIX}{state.protocol_id}|{state.protocol_version}"
        ),
        status=_SESSION_TO_QR_STATUS[state.status],
        subject=Reference(reference=subject_ref),
        authored=state.reference_time.isoformat(),
        item=items or None,
    )
