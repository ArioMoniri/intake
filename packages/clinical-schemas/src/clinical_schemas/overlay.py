"""PatientOverlay (INT-031).

files/09 §3 (Loop 1): versioned, patient-owned, exported/deletable, built
from three sources only — confirmed extraction from the patient's own
intakes, clinician-accepted note content, confirmed imported records. LLM
output alone never becomes a learned fact (invariant 12: confirmation is
type-level — ``LearnedFactSource`` has no unconfirmed member). Every fact
shows "where from" and can be corrected or deleted by the patient; a fact
older than 12 months is re-confirmed before use.

INT-170 adds the other half of invariant 12 — the *unconfirmed* form and the
act that ends it. :class:`FactCandidate` is what extraction, a note draft or a
record import proposes, and its mechanism is an absence: it carries no
``source`` field and no ``confirmed_at`` field, so it cannot be spelled as a
confirmed fact and no validator has to catch one. The only route between the
two is :func:`confirm`, which takes a :class:`Confirmation` whose ``source``
type has no unconfirmed member. This is the posture INT-172 took for
``CandidateRedFlag`` (no ``level`` field, so ``RED`` is a ``TypeError`` at the
call site rather than a rejection three layers later).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final

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


class ConfirmingActor(enum.StrEnum):
    """files/09 §3: a learned fact is confirmed "by the patient (in-app card)
    or a clinician (note acceptance)". CLAUDE.md invariant 12 says the same in
    one clause — *patient or clinician confirmation*. Those are the two
    members, and there is deliberately no third: no ``SYSTEM``, no ``MODEL``,
    nothing an extraction pipeline could name for itself."""

    PATIENT = "patient"
    CLINICIAN = "clinician"


#: Which actor each provenance implies. Total over ``LearnedFactSource`` by
#: construction — the enum has no unconfirmed member, so every source has a
#: confirming actor and the map can never grow a hole (asserted in
#: tests/learning/test_overlay_provenance.py).
CONFIRMING_ACTOR: Final[Mapping[LearnedFactSource, ConfirmingActor]] = MappingProxyType(
    {
        LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION: ConfirmingActor.PATIENT,
        LearnedFactSource.CLINICIAN_ACCEPTED_NOTE: ConfirmingActor.CLINICIAN,
        LearnedFactSource.CONFIRMED_IMPORTED_RECORD: ConfirmingActor.PATIENT,
    }
)


class FactCandidate(FrozenModel):
    """What extraction, a clinician draft or a record import *proposes* —
    before anybody has confirmed it (files/09 §3: "LLM output alone never
    becomes a learned fact").

    The mechanism is what this class does **not** have. There is no ``source``
    field and no ``confirmed_at`` field: the two things a confirmation writes
    have no representation here, so a candidate cannot be spelled as a
    confirmed fact by filling in a value, and no validator has to catch one.
    It is the posture INT-172 took for ``CandidateRedFlag`` — the class has no
    ``level``, so ``RED`` is a ``TypeError`` at the call site rather than a
    rejection three layers later — applied to invariant 12's other half.

    A candidate is not a ``LearnedFact`` and does not inherit from one: the
    only route between them is :func:`confirm`, which requires a
    :class:`Confirmation`.
    """

    key: Ref = Field(
        description="Fact identifier the proposal is about, e.g. chronic.hipertansiyon "
        "(the same key a confirmed fact would carry, files/09 §3)."
    )
    value: JsonValue = Field(description="The proposed value — unconfirmed, and no rule's input.")
    origin_ref: Ref = Field(
        description="Id of the artefact the proposal was derived from (an intake session, "
        "a note draft, an imported record). NOT a provenance: nothing here asserts that a "
        "human agreed with it."
    )
    observed_at: AwareDatetime = Field(
        description="When the proposal was derived. Deliberately not confirmed_at — the "
        "twelve-month re-confirmation window (files/09 §3) runs from a confirmation, and "
        "an observation is not one."
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="The proposer's confidence, carried through to the fact on "
        "confirmation (files/09 §3: 'with provenance and confidence').",
    )


class Confirmation(FrozenModel):
    """One patient or clinician act of confirmation (files/09 §3; invariant 12).

    ``source`` is a :class:`LearnedFactSource`, whose three members are all
    confirmations — so a ``Confirmation`` that confirms nothing is not a value
    this type can hold, and :attr:`actor` is total rather than optional.
    """

    source: LearnedFactSource = Field(
        description="The confirmed provenance this act establishes (files/09 §3)."
    )
    source_ref: Ref = Field(
        description="Id of the confirming artefact — the in-app confirmation card, the "
        "accepted note, the confirmed import. The 'where from' the patient is shown."
    )
    confirmed_at: AwareDatetime = Field(
        description="When the confirmation happened; the twelve-month re-confirmation "
        "window runs from here (files/09 §3 guardrails)."
    )

    @property
    def actor(self) -> ConfirmingActor:
        """Patient or clinician — total, because :data:`CONFIRMING_ACTOR` is."""
        return CONFIRMING_ACTOR[self.source]


def confirm(candidate: FactCandidate, confirmation: Confirmation) -> LearnedFact:
    """The only route from a proposal to a learned fact (invariant 12).

    It takes a confirmation because there is no other way to obtain the two
    fields :class:`FactCandidate` does not carry. Nothing in this module
    produces a :class:`LearnedFact` from a candidate alone, and a candidate
    cannot be placed in :attr:`PatientOverlay.facts`, which is typed
    ``tuple[LearnedFact, ...]`` — so an unconfirmed value cannot reach the
    delta-mode reader or overlay activation at all.
    """
    return LearnedFact(
        key=candidate.key,
        value=candidate.value,
        source=confirmation.source,
        source_ref=confirmation.source_ref,
        confidence=candidate.confidence,
        confirmed_at=confirmation.confirmed_at,
    )
