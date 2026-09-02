"""Minimal FHIR R4 shapes for the INT-033 exchange surface.

files/03 §7 names FHIR R4 (HAPI) as the exchange format. These are
pydantic v2 models of exactly the profiled subset the mappers emit and
ingest — deliberately not a full FHIR library (nothing heavyweight is
needed for nine resources, and every field here is one we actually map).

Wire conventions:
- JSON uses FHIR camelCase via the ``to_camel`` alias generator; Python
  stays snake_case.
- ``extra="ignore"``: foreign FHIR carries many elements outside this
  subset; ingestion reads what the blueprint maps and drops the rest
  (files/03 §4.6 — JSON/FHIR inputs bypass OCR but still normalise).
- Quantity values are ``Decimal`` in Python (CLAUDE.md invariant 22: no
  floats across a representation boundary for clinical magnitudes) and
  serialize to JSON numbers, as FHIR requires.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic.alias_generators import to_camel


class R4Base(BaseModel):
    """Base for every R4 shape: frozen value, camelCase wire aliases,
    foreign elements ignored on ingestion."""

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class Coding(R4Base):
    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(R4Base):
    coding: tuple[Coding, ...] | None = None
    text: str | None = None


class Quantity(R4Base):
    value: Decimal | None = None
    unit: str | None = None

    @field_serializer("value", when_used="json")
    def _value_as_json_number(self, value: Decimal | None) -> float | None:
        # FHIR decimal is a JSON number; the Python side stays Decimal.
        return None if value is None else float(value)


class Reference(R4Base):
    reference: str


class Identifier(R4Base):
    system: str | None = None
    value: str


class Extension(R4Base):
    url: str
    value_string: str | None = None
    value_boolean: bool | None = None
    value_integer: int | None = None
    value_decimal: float | None = None
    extension: tuple[Extension, ...] | None = None


class Narrative(R4Base):
    status: str = "generated"
    div: str


class Dosage(R4Base):
    text: str


class AllergyReaction(R4Base):
    manifestation: tuple[CodeableConcept, ...]


class Patient(R4Base):
    resource_type: Literal["Patient"] = "Patient"
    id: str | None = None


class Observation(R4Base):
    resource_type: Literal["Observation"] = "Observation"
    id: str | None = None
    extension: tuple[Extension, ...] | None = None
    status: str
    category: tuple[CodeableConcept, ...] | None = None
    code: CodeableConcept
    subject: Reference | None = None
    performer: tuple[Reference, ...] | None = None
    effective_date_time: str | None = None
    value_quantity: Quantity | None = None
    value_integer: int | None = None


class Condition(R4Base):
    resource_type: Literal["Condition"] = "Condition"
    id: str | None = None
    extension: tuple[Extension, ...] | None = None
    clinical_status: CodeableConcept | None = None
    verification_status: CodeableConcept | None = None
    code: CodeableConcept | None = None
    subject: Reference
    recorded_date: str | None = None


class MedicationStatement(R4Base):
    resource_type: Literal["MedicationStatement"] = "MedicationStatement"
    id: str | None = None
    extension: tuple[Extension, ...] | None = None
    status: str
    medication_codeable_concept: CodeableConcept
    subject: Reference
    date_asserted: str | None = None
    dosage: tuple[Dosage, ...] | None = None


class AllergyIntolerance(R4Base):
    resource_type: Literal["AllergyIntolerance"] = "AllergyIntolerance"
    id: str | None = None
    extension: tuple[Extension, ...] | None = None
    clinical_status: CodeableConcept | None = None
    verification_status: CodeableConcept | None = None
    code: CodeableConcept | None = None
    patient: Reference
    recorded_date: str | None = None
    reaction: tuple[AllergyReaction, ...] | None = None


class RiskPrediction(R4Base):
    """Deliberately category-only: the rules result is categorical, so no
    ``probability[x]`` element exists in this subset at all (invariant 20 —
    no numeric risk figure is ever asserted)."""

    qualitative_risk: CodeableConcept | None = None


class RiskAssessment(R4Base):
    resource_type: Literal["RiskAssessment"] = "RiskAssessment"
    id: str | None = None
    extension: tuple[Extension, ...] | None = None
    status: str
    method: CodeableConcept | None = None
    subject: Reference | None = None
    reason_code: tuple[CodeableConcept, ...] | None = None
    prediction: tuple[RiskPrediction, ...] | None = None


class Flag(R4Base):
    resource_type: Literal["Flag"] = "Flag"
    id: str | None = None
    status: str
    code: CodeableConcept
    subject: Reference


class QrAnswer(R4Base):
    value_string: str | None = None
    value_integer: int | None = None
    value_decimal: float | None = None
    value_boolean: bool | None = None


class QrItem(R4Base):
    link_id: str
    extension: tuple[Extension, ...] | None = None
    answer: tuple[QrAnswer, ...] | None = None
    item: tuple[QrItem, ...] | None = None


class QuestionnaireResponse(R4Base):
    resource_type: Literal["QuestionnaireResponse"] = "QuestionnaireResponse"
    id: str | None = None
    extension: tuple[Extension, ...] | None = None
    identifier: Identifier | None = None
    questionnaire: str | None = None
    status: str
    subject: Reference | None = None
    authored: str | None = None
    item: tuple[QrItem, ...] | None = None


class CompositionSection(R4Base):
    title: str | None = None
    code: CodeableConcept | None = None
    text: Narrative | None = None
    entry: tuple[Reference, ...] | None = None


class Composition(R4Base):
    resource_type: Literal["Composition"] = "Composition"
    id: str | None = None
    extension: tuple[Extension, ...] | None = None
    text: Narrative | None = None
    status: str
    type: CodeableConcept
    subject: Reference | None = None
    date: str
    author: tuple[Reference, ...]
    title: str
    section: tuple[CompositionSection, ...] | None = None


class BundleEntry(R4Base):
    full_url: str | None = None
    resource: R4Resource


class Bundle(R4Base):
    resource_type: Literal["Bundle"] = "Bundle"
    id: str | None = None
    identifier: Identifier | None = None
    type: str
    timestamp: str | None = None
    entry: tuple[BundleEntry, ...] | None = None


R4Resource = Annotated[
    Patient
    | Observation
    | Condition
    | MedicationStatement
    | AllergyIntolerance
    | RiskAssessment
    | Flag
    | QuestionnaireResponse
    | Composition
    | Bundle,
    Field(discriminator="resource_type"),
]
"""The nine INT-033 exchange resources plus the synthetic document Patient,
discriminated on ``resourceType`` exactly as the wire is."""

Extension.model_rebuild()
QrItem.model_rebuild()
BundleEntry.model_rebuild()
Bundle.model_rebuild()


def to_wire(resource: R4Base) -> dict[str, Any]:
    """Dump a resource exactly as HAPI receives it: camelCase, JSON-mode
    values, absent elements omitted (FHIR forbids explicit nulls)."""
    return resource.model_dump(mode="json", by_alias=True, exclude_none=True)
