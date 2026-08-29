"""PatientOverlay (INT-031).

files/09 §3 (Loop 1): versioned, patient-owned, exported/deletable, built
from three sources only — confirmed extraction from the patient's own
intakes, clinician-accepted note content, confirmed imported records. LLM
output alone never becomes a learned fact (invariant 12: confirmation is
type-level — ``LearnedFactSource`` has no unconfirmed member). Every fact
shows "where from" and can be corrected or deleted by the patient; a fact
older than 12 months is re-confirmed before use.
"""

from __future__ import annotations

import enum
from datetime import datetime, timedelta

from pydantic import AwareDatetime, Field

from clinical_schemas.common import FrozenModel, JsonValue, Ref

#: files/09 §3: "a fact older than 12 months is re-confirmed before use".
RECONFIRM_AFTER = timedelta(days=365)


class LearnedFactSource(enum.StrEnum):
    """The only three provenances a learned fact may carry (files/09 §3;
    invariant 12). There is deliberately no unconfirmed/LLM member."""

    CONFIRMED_INTAKE_EXTRACTION = "confirmed_intake_extraction"
    CLINICIAN_ACCEPTED_NOTE = "clinician_accepted_note"
    CONFIRMED_IMPORTED_RECORD = "confirmed_imported_record"


class LearnedFact(FrozenModel):
    """One learned fact with provenance and confidence (files/09 §3)."""

    key: Ref = Field(
        description="Fact identifier, e.g. chronic.hipertansiyon (files/09 §3: every "
        "PatientOverlay field is inspectable in Me → Hakkımda öğrendikleri)."
    )
    value: JsonValue = Field(
        description="The learned value (files/09 §3: baselines, medication list, "
        "communication preferences, companion relationships, cross-specialty facts)."
    )
    source: LearnedFactSource = Field(
        description="Confirmed provenance — the type admits nothing unconfirmed "
        "(files/09 §3; invariant 12)."
    )
    source_ref: Ref = Field(
        description="Id of the confirming artefact (note, confirmed item, intake) — "
        "the 'where from' every fact must show (files/09 §3 guardrails)."
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence carried with the fact (files/09 §3: 'with provenance "
        "and confidence').",
    )
    confirmed_at: AwareDatetime = Field(
        description="When the confirmation happened — drives the 12-month "
        "re-confirmation rule (files/09 §3 guardrails)."
    )
    shared: bool = Field(
        default=True,
        description="Per-field share scope (files/09 §3 guardrails); default-on to "
        "match the app's section scopes (files/02 §5.1).",
    )


def fact_needs_reconfirmation(fact: LearnedFact, now: datetime) -> bool:
    """files/09 §3: a fact older than 12 months is re-confirmed before use."""
    return now - fact.confirmed_at > RECONFIRM_AFTER


class PatientOverlay(FrozenModel):
    """The per-patient learning object (files/09 §3): patient-owned,
    versioned, exported/deletable; may only add/tighten red flags via the
    overlays it activates, never relax them (invariant 7)."""

    patient_ref: Ref = Field(
        description="Pseudonymised patient (INT-030 patients.pseudonym; the overlay is "
        "patient-owned and exportable/deletable, files/09 §3)."
    )
    version: int = Field(
        ge=1, description="Overlay version — the object is versioned (files/09 §3)."
    )
    facts: tuple[LearnedFact, ...] = Field(
        default=(),
        description="The learned facts, each with confirmed provenance (files/09 §3).",
    )
