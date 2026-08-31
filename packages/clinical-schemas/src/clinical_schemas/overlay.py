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
from dataclasses import dataclass
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


# =====================================================================================
# INT-170 — the confirmation vocabulary: a different TYPE, never a flag
# =====================================================================================
#
# CLAUDE.md invariant 12: "``PatientOverlay`` facts require patient or clinician
# confirmation (type-level)." ``LearnedFactSource`` above carries half of that —
# its three members are all confirmed provenances and there is no LLM member —
# but a source enum still lets a caller assemble a ``LearnedFact`` out of an
# extraction that nobody looked at, because the *thing extraction produces* and
# the *thing a person confirmed* are the same type there.
#
# So INT-170 splits them. :class:`UnconfirmedObservation` is what extraction and
# record import produce; :class:`ConfirmedFact` is what a store may accept; and
# :func:`confirm` is the only bridge, which needs a :class:`Confirmation` naming
# a person. There is no boolean on either type, because a boolean is a value any
# caller can set and the acceptance says *(type-level)*.
#
# **These four are frozen dataclasses rather than ``FrozenModel``, deliberately.**
# This repository does not enable pydantic's mypy plugin (pyproject.toml declares
# no ``plugins``), so ``BaseModel.__init__`` type-checks as ``**data: Any``: a
# missing ``confirmation=`` and a stray ``confirmed=True`` both pass the checker
# and fail only at runtime. That would make "(type-level)" a runtime claim
# wearing a type's clothes. A frozen dataclass gives ``mypy --strict`` the
# synthesised ``__init__`` it needs to refuse both at the call site, and freezes
# the field so a confirmation cannot be re-pointed after the fact. It is the
# posture INT-172's ``intake_learning.proposals`` takes for the same invariant's
# first sentence.


class Confirmer(enum.StrEnum):
    """Who confirmed a fact. Exactly two members, and no third.

    files/09 §3 and invariant 12 both say "patient or clinician". They are not
    interchangeable — a clinician accepting a fact into a note and a patient
    asserting it in their own review step are different events with different
    weight — so the ledger carries which one it was all the way to the wire.
    A model is not a member: an inference that nobody looked at is an
    :class:`UnconfirmedObservation`, which the store cannot accept.
    """

    PATIENT = "patient"
    CLINICIAN = "clinician"


@dataclass(frozen=True, slots=True)
class UnconfirmedObservation:
    """What extraction, a draft note or an imported record produces.

    Not a fact. Nothing here names a confirmer, a confirmation time or a
    confirmed provenance, so "an observation that says it was confirmed" is not
    a case to reject — it cannot be written down.
    """

    key: str
    value: JsonValue
    #: The artefact the observation was made in (a session, a document).
    observed_ref: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_ref("key", self.key)
        _require_ref("observed_ref", self.observed_ref)
        _require_aware("observed_at", self.observed_at)


@dataclass(frozen=True, slots=True)
class Confirmation:
    """A person said this is so, on a date, against a named artefact.

    Every field is required. "Provenance shown" starts before rendering: a fact
    with no provenance must not exist to be rendered, so the omission is a
    ``TypeError`` from the synthesised ``__init__`` rather than a blank on a
    screen.
    """

    by: Confirmer
    #: The confirming person, as an id (invariant 6: ids, never names).
    actor_ref: str
    at: datetime
    source: LearnedFactSource
    #: The confirming artefact — the "where from" of files/09 §3's guardrails.
    source_ref: str

    def __post_init__(self) -> None:
        _require_ref("actor_ref", self.actor_ref)
        _require_ref("source_ref", self.source_ref)
        _require_aware("at", self.at)


@dataclass(frozen=True, slots=True)
class ConfirmedFact:
    """The only shape a ``PatientOverlay`` store accepts.

    It cannot be built without a :class:`Confirmation`, and the confirmation
    cannot be re-pointed afterwards (the dataclass is frozen), so a caller
    cannot walk an unconfirmed value in through a later assignment either.
    """

    key: str
    value: JsonValue
    confirmation: Confirmation
    confidence: float

    def __post_init__(self) -> None:
        _require_ref("key", self.key)
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence is a probability in [0, 1]")

    def as_learned_fact(self) -> LearnedFact:
        """Project onto INT-031's transport shape, which is what the
        IntakeEngine and INT-081's ``decide_delta`` read.

        ``LearnedFact`` has no carrier for *who* confirmed — INT-031 predates
        this split and its shape is pinned by the committed OpenAPI/TS codegen —
        so ``Confirmer`` stops here and is shown on the ledger instead. That is
        a narrowing on the way to the engine, never a widening: nothing the
        engine sees was unconfirmed.
        """
        return LearnedFact(
            key=self.key,
            value=self.value,
            source=self.confirmation.source,
            source_ref=self.confirmation.source_ref,
            confidence=self.confidence,
            confirmed_at=self.confirmation.at,
        )


def confirm(
    observation: UnconfirmedObservation,
    *,
    by: Confirmer,
    actor_ref: str,
    at: datetime,
    source: LearnedFactSource,
    source_ref: str,
    confidence: float,
) -> ConfirmedFact:
    """The one bridge from an observation to a fact.

    The key and the value carry over unchanged: confirming is agreeing with
    what was observed, never restating it. A patient who disagrees produces a
    different observation, not an edited one (INT-247's ``changed`` outcome).
    """
    return ConfirmedFact(
        key=observation.key,
        value=observation.value,
        confirmation=Confirmation(
            by=by, actor_ref=actor_ref, at=at, source=source, source_ref=source_ref
        ),
        confidence=confidence,
    )


def _require_ref(field_name: str, value: str) -> None:
    """An empty string is the shape a missing value takes once the type has
    stopped catching it, so the value type catches it too."""
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty reference (invariant 6: ids)")


def _require_aware(field_name: str, value: datetime) -> None:
    """A naive timestamp compared against an aware ``now`` raises at the point
    the twelve-month rule is applied — which is the worst possible place."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
