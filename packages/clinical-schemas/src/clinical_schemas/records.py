"""ExtractedRecordItem (INT-031).

Source: files/03 §4.6 (document & record understanding) — the extraction LLM
emits ``ExtractedRecordItem[]`` with LOINC for labs, ATC for meds, ICD-10 for
diagnoses, ``verificationStatus=unconfirmed`` and a ``Provenance`` carrying
page and bbox; the item reaches a clinical decision only after the patient
confirms it in the app (``POST /records/items/{id}/confirm``, files/03 §6).
CLAUDE.md invariant 22 governs the numbers: on ingestion, magnitude outranks
the printed unit token, and disagreement raises a flag rather than converting
silently.
"""

from __future__ import annotations

import datetime
import enum
from decimal import Decimal

from pydantic import Field

from clinical_schemas.common import FrozenModel, Ref


class RecordItemKind(enum.StrEnum):
    """files/03 §4.6: labs, meds, diagnoses, imaging/procedures/allergies."""

    LAB = "lab"
    IMAGING = "imaging"
    PROCEDURE = "procedure"
    MEDICATION = "medication"
    DIAGNOSIS = "diagnosis"
    ALLERGY = "allergy"


class CodeSystem(enum.StrEnum):
    """files/03 §4.6: LOINC for labs, ATC for meds, ICD-10 for diagnoses."""

    LOINC = "loinc"
    ATC = "atc"
    ICD10 = "icd10"


class VerificationStatus(enum.StrEnum):
    """files/03 §4.6: items enter as unconfirmed; the patient confirms in-app
    before any clinical use."""

    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"


class RecordCode(FrozenModel):
    """A coded concept on an extracted item (files/03 §4.6 code normalisation)."""

    system: CodeSystem = Field(
        description="Coding system: loinc|atc|icd10 (files/03 §4.6 pipeline)."
    )
    code: str = Field(min_length=1, description="The code value (files/03 §4.6).")


class RecordProvenance(FrozenModel):
    """files/03 §4.6: a Provenance carrying page and bbox, pointing at the
    stored document (INT-030 documents.object_ref/sha256 own the bytes trail)."""

    document_ref: Ref = Field(
        description="Id of the ingested document row (files/03 §4.6; INT-030 documents)."
    )
    page: int | None = Field(
        default=None, ge=1, description="1-based source page (files/03 §4.6 Provenance page)."
    )
    bbox: tuple[float, float, float, float] | None = Field(
        default=None,
        description="Normalised source bounding box (files/03 §4.6 Provenance bbox).",
    )


class ExtractedRecordItem(FrozenModel):
    """One structured item extracted from an uploaded document or record
    (files/03 §4.6). Unconfirmed items never reach a clinical decision."""

    kind: RecordItemKind = Field(
        description="What the item is: lab|imaging|procedure|medication|diagnosis|allergy "
        "(files/03 §4.6)."
    )
    summary: str = Field(
        min_length=1,
        description="Human-readable content of the item (files/03 §4.6; rendered for "
        "patient confirmation).",
    )
    code: RecordCode | None = Field(
        default=None,
        description="Normalised code when one resolved (files/03 §4.6: LOINC/ATC/ICD-10); "
        "None when no code resolved — never a guessed code.",
    )
    value_magnitude: Decimal | None = Field(
        default=None,
        description="Numeric magnitude for labs, exact decimal — no floats across a "
        "representation boundary (CLAUDE.md invariant 22).",
    )
    unit: str | None = Field(
        default=None,
        description="Unit as normalised on ingestion (files/03 §4.6 unit normalisation).",
    )
    unit_conflict: bool = Field(
        default=False,
        description="True when the magnitude and the printed unit token disagree — the "
        "flag raised instead of converting silently (CLAUDE.md invariant 22).",
    )
    date: datetime.date | None = Field(
        default=None,
        description="Clinical date of the source item when legible (files/04 §5 "
        "imported_objective.date is its note-side rendering).",
    )
    verification_status: VerificationStatus = Field(
        default=VerificationStatus.UNCONFIRMED,
        description="files/03 §4.6: enters unconfirmed; confirmed only by the patient "
        "(POST /records/items/{id}/confirm, files/03 §6).",
    )
    provenance: RecordProvenance = Field(
        description="Where in which document the item came from (files/03 §4.6)."
    )
