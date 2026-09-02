"""What extraction produces, and the two things it structurally cannot produce.

**It cannot produce a triage level.** :class:`ExtractionResult` has no ``level``
field. CLAUDE.md invariant 1 caps an LLM-derived flag at ``YELLOW_REVIEW``, and
the way this type honours that is the way ``CandidateRedFlag`` does in
``services/learning/.../proposals.py``: there is no constructor argument through
which ``RED`` could be expressed, so an over-reach is a ``TypeError`` at the
call site rather than a rejection three layers later. :attr:`level` is a
read-only class constant, and the only triage value the result can build is
:class:`clinical_schemas.triage.LlmCandidateTriage`, whose ``level`` is
``Literal["YELLOW_REVIEW"]``.

**It cannot produce speech.** There is no ``speech_tr`` field. files/03 §4.9.6
invariant 30 requires that no numeric slot value is spoken without a matching
``inline`` render on the same ``work_id``; extraction emits ``inline`` material
only, so the pairing cannot be broken from here. The spoken side belongs to the
Backend Agent's delivery (INT-092).

**Nothing here has a ``repr`` that shows a value.** A slot value is what the
patient said; an exception that interpolated a result would put it in a log
(invariant 6). Refs and counts are ids and measurements, and those are what the
``repr`` shows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

from clinical_schemas.triage import CandidateFlag, LlmCandidateTriage

__all__ = [
    "ExtractionFlag",
    "ExtractionResult",
    "FlagReason",
    "SlotUpdate",
    "SlotValue",
]

#: The scalar kinds a slot may carry after typed coercion. ``Decimal`` and not
#: ``float`` for the numeric ones — files/13 §9.5, "no floats anywhere": a
#: decimal literal that round-trips through binary floating point is exactly
#: the silent corruption files/03 §4.9.6 is about.
type SlotValue = bool | int | Decimal | str


class FlagReason(StrEnum):
    """Why one slot did not bind. A closed enumeration, because a reason is a
    thing an operator counts, and a free-text reason is a thing that ends up
    carrying the value it was meant to describe."""

    #: The model answered for a ref this step does not declare. files/03
    #: §4.9.6's `üre` / `Üre Nitrojeni` case: refs match by equality, never by
    #: prefix, so a near-miss is a flag rather than a binding to the neighbour.
    UNKNOWN_SLOT_REF = "unknown_slot_ref"
    #: The reported unit is not the declared one (files/03 §4.9.6).
    UNIT_DISAGREEMENT = "unit_disagreement"
    #: A numeric slot answered with a string. The separator cannot be resolved
    #: without the analyte's expected magnitude, so it is not resolved.
    AMBIGUOUS_NUMERAL = "ambiguous_numeral"
    #: Below the confidence floor the pack author declared on the slot.
    BELOW_CONFIDENCE_FLOOR = "below_confidence_floor"
    #: The value is not of the declared slot type.
    WRONG_TYPE = "wrong_type"
    #: A code slot answered outside its valueset.
    VALUESET_VIOLATION = "valueset_violation"


@dataclass(frozen=True)
class ExtractionFlag:
    """One slot that did not bind, and why.

    Two fields, and there is deliberately no third: a flag that carried the
    offending value would be the log line invariant 6 forbids, and the value is
    recoverable from the session's own state if a human needs it.
    """

    ref: str
    reason: FlagReason


@dataclass(frozen=True, repr=False)
class SlotUpdate:
    """One slot the extraction bound, with the model's own confidence."""

    ref: str
    value: SlotValue
    confidence: Decimal

    def __repr__(self) -> str:
        return f"SlotUpdate(ref={self.ref!r}, confidence={self.confidence!r})"

    def __str__(self) -> str:
        return self.__repr__()


@dataclass(frozen=True, repr=False)
class ExtractionResult:
    """One extraction, validated against the step's declared slot schemas."""

    step_id: str
    slot_updates: tuple[SlotUpdate, ...]
    candidate_flags: tuple[CandidateFlag, ...]
    clarification_needed: bool
    flags: tuple[ExtractionFlag, ...] = field(default=())

    #: The cap, as a ``ClassVar`` — which ``dataclasses`` excludes from the
    #: field set, so it is not a constructor argument either. A plain string
    #: rather than ``TriageLevel``: ``YELLOW_REVIEW`` is not a member of
    #: ``TriageLevel`` at all (files/12 §2.3 — clinician-only, never routing).
    _LEVEL: ClassVar[str] = "YELLOW_REVIEW"

    @property
    def level(self) -> str:
        """The ceiling of files/03 §4.6 and CLAUDE.md invariant 1, read-only."""
        return self._LEVEL

    def triage(self) -> LlmCandidateTriage | None:
        """The candidate triage value, or ``None`` when there is nothing to say.

        ``None`` and not a GREEN: an extraction that found no candidate has not
        determined that the patient is well, and a type that could express
        "GREEN from the LLM" would be invariant 1 broken in the other
        direction.
        """
        if not self.candidate_flags:
            return None
        return LlmCandidateTriage(candidate_flags=self.candidate_flags)

    def as_engine_call(self) -> dict[str, Any]:
        """Exactly the parameters of ``IntakeEngine.apply_extraction``.

        docs/evidence/INT-081.md: *"patient text never reaches the engine at
        all — transcripts become ``slot_updates`` in INT-083, one layer out."*
        This method is that sentence. The transcript is not here, the candidate
        flags are not here (they are clinician-facing, and the engine holds no
        rule), and the flags are not here (they are a data-quality record).

        ``Decimal`` crosses as ``Decimal`` (INT-303). It used to be cast to
        ``int`` or ``float`` here because the engine's carrier
        (``clinical_schemas.common.JsonValue``) declared no ``Decimal``; that
        carrier now does, so the cast is gone. It was the one place a clinical
        quantity crossed a representation boundary through binary floating
        point — the crossing files/13 §9.5 forbids outright ("no floats
        anywhere ... exact comparison, because floats are how two machines
        disagree about the same session") and CLAUDE.md invariant 22 calls
        unguarded. It also dropped the declared scale: ``38.50`` and ``38.5``
        are the same float and are not the same ``Decimal``.
        """
        updates: dict[str, Any] = {update.ref: update.value for update in self.slot_updates}
        return {
            "step_id": self.step_id,
            "slot_updates": updates,
            "clarification_needed": self.clarification_needed,
        }

    def bound_refs(self) -> frozenset[str]:
        """The refs that actually bound — the measurement the eval scores."""
        return frozenset(update.ref for update in self.slot_updates)

    def __repr__(self) -> str:
        return (
            f"ExtractionResult(step_id={self.step_id!r}, "
            f"bound={sorted(self.bound_refs())!r}, "
            f"candidate_flags={len(self.candidate_flags)}, "
            f"flags={[(f.ref, f.reason.value) for f in self.flags]!r}, "
            f"clarification_needed={self.clarification_needed})"
        )

    def __str__(self) -> str:
        return self.__repr__()
