"""Typed answer/slot state the triage engine evaluates over (INT-080).

The shapes align with the INT-031 ``SessionState`` (files/13 §9.2-9.3):
answer states are :class:`clinical_schemas.session.AnswerState`, values are
:data:`clinical_schemas.common.JsonValue`, and the clock is the session's
``reference_time`` — a pure fold input, never a wall clock. The projection
from a live ``SessionState`` (step ↔ slot bookkeeping) is owned by the
IntakeEngine issue (INT-081); this module owns only what a rule can read.

Three-valued reading (files/12 §1.1; files/13 §9.5): a slot whose answer
state carries no usable value — ``not_asked``, ``unclear``, and equally
``asked_pending`` (nothing bound yet) and ``declined`` (rendering a decline
as *elicited and absent* is the exact defect §1.1 names) — reads Unknown.
``contested`` keeps every value: files/12 §7.3, triage evaluates on the
union of head and superseded values and takes max acuity.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.session import AnswerState
from pydantic import AwareDatetime, Field, model_validator

from protocols.triage.expr import Truth
from protocols.types import Tense

__all__ = [
    "SlotAnswer",
    "TriageContext",
    "UncomparableSlotValue",
    "canonical_scalar",
    "temporal_within",
]

_VALUE_BEARING = frozenset({AnswerState.ASKED_PRESENT, AnswerState.ASKED_ABSENT})


class UncomparableSlotValue(TypeError):
    """A slot value outside the declared carrier reached a comparison.

    Unknown and *uncomparable* are two different things and were one code
    path (INT-303). "This slot has no answer" is a reading the grammar
    defines and a rule must survive; "I was handed a type the carrier does
    not declare" is a programming error, and answering it with Unknown makes
    a red-flag rule quietly never fire — the failure CLAUDE.md invariant 1
    exists to prevent, and the one nothing reports.

    It names the offending TYPE and never the value: an exception that
    interpolated a slot value would put what the patient said into a log
    (invariant 6).
    """

    def __init__(self, offending: type) -> None:
        super().__init__(
            f"slot value of type {offending.__name__!r} is outside "
            "clinical_schemas.common.JsonValue and cannot be compared"
        )


class SlotAnswer(FrozenModel):
    """One slot's answer state plus the value(s) it carries."""

    state: AnswerState = Field(
        description="Answer state, files/13 §9.3 seven states via the INT-031 SessionState enum."
    )
    values: tuple[JsonValue, ...] = Field(
        default=(),
        description="Carried values: exactly one for asked_present/asked_absent; "
        "two or more (head + superseded) for contested (files/12 §7.3); none "
        "otherwise — those states read Unknown (files/12 §1.1).",
    )

    @model_validator(mode="after")
    def _values_match_state(self) -> SlotAnswer:
        if self.state in _VALUE_BEARING:
            if len(self.values) != 1:
                raise ValueError(f"{self.state.value} carries exactly one value (files/13 §9.3)")
        elif self.state is AnswerState.CONTESTED:
            if len(self.values) < 2:
                raise ValueError(
                    "contested keeps both answers — at least head + one "
                    "superseded value (files/12 §7.3; files/13 §9.3)"
                )
        elif self.values:
            raise ValueError(
                f"{self.state.value} carries no value — it reads Unknown (files/12 §1.1)"
            )
        return self


class TriageContext(FrozenModel):
    """The pure evaluation context: answers plus the session's clock."""

    reference_time: AwareDatetime = Field(
        description="The session's 'now', stamped at SessionStarted — the fold "
        "input of files/13 §9.2, never a wall clock."
    )
    answers: dict[str, SlotAnswer] = Field(
        default_factory=dict,
        description="Answers keyed by the dotted slot reference exactly as the "
        "rule's when predicate spells it (files/03 §6 atoms).",
    )
    units: dict[str, str] = Field(
        default_factory=dict,
        description="The declared unit of each quantity slot (files/03 §6 ``unit:``), "
        "keyed like ``answers``. Evidence only: it travels with the value into "
        "``RuleFire.evidence_slots`` so a reader sees number and unit as one atom "
        "(CLAUDE.md invariant 22; INT-404). No predicate reads it, because a rule "
        "compares the bare magnitude.",
    )

    def candidate_values(self, ref: str) -> tuple[JsonValue, ...] | None:
        """The value(s) a predicate may read for ``ref``; None reads Unknown."""
        slot = self.answers.get(ref)
        if slot is None:
            return None
        if slot.state in _VALUE_BEARING or slot.state is AnswerState.CONTESTED:
            return slot.values
        return None


def canonical_scalar(value: JsonValue) -> bool | Decimal | str | None:
    """Canonicalise a JsonValue for comparison; None reads Unknown.

    Numbers are Decimal (files/13 §9.5: exact comparison, no floats). A
    ``Decimal`` is carried through **unchanged**, so the scale the patient
    stated survives the comparison; an ``int`` and a ``float`` are converted
    through their string form, deterministically — that conversion is the
    guard CLAUDE.md invariant 22 requires at this representation boundary.
    ``bool`` is checked first: ``True == 1`` in Python, and a boolean answer
    must not satisfy a numeric threshold of one.

    Two outcomes, and they are deliberately not the same one:

    - **Unknown** (``None``) for JSON null and for collections. Those are
      inside the carrier and simply do not compare in this grammar, so a
      predicate over them reads Unknown and a rule does not fire.
    - **A raise** for anything outside the carrier. Reading that as Unknown
      is what let a ``Decimal`` — the very type extraction produces — make a
      red-flag rule silently never fire. The engine calls this on a value
      that has already passed a typed boundary, so a raise here is a caller
      bug surfacing at once rather than a new failure mode for patient data.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (list, dict)):
        return None
    raise UncomparableSlotValue(type(value))


def temporal_within(anchor_value: JsonValue, tense: Tense, reference_time: datetime) -> Truth:
    """``temporal.within(anchor, tense, now)`` of files/12 §2.4.

    Calendar-day windows, computed against the session's reference time so
    replay is exact (files/13 §9.2):

    - ``ever``    — any dated event up to and including today
    - ``within_30d`` / ``within_7d`` — at most that many days ago
    - ``today``   — the reference day itself
    - ``now``     — the reference day, same window as ``today``: the
      *ongoing-ness* of a now-tensed event is asserted by the rule's own
      predicate (files/protocols/base.life_threat.yaml exemplar 1 pairs
      ``tense: now`` with ``present == true``), and a tighter calendar
      bound would need a clinical constant no human has supplied
      (HUMAN_BLOCKERS rule 1 — never a plausible number).

    Unknown, never True, for an undated / unparseable / naive / future
    anchor — a tense-qualified rule cannot fire on an undated symptom
    (files/12 §2.4).
    """
    anchor_date = _anchor_date(anchor_value, reference_time)
    if anchor_date is None:
        return Truth.UNKNOWN
    days_ago = (reference_time.date() - anchor_date).days
    if days_ago < 0:
        return Truth.UNKNOWN  # a future-dated event is a data defect, not a firing
    if tense is Tense.EVER:
        return Truth.TRUE
    if tense is Tense.WITHIN_30D:
        return Truth.TRUE if days_ago <= 30 else Truth.FALSE
    if tense is Tense.WITHIN_7D:
        return Truth.TRUE if days_ago <= 7 else Truth.FALSE
    return Truth.TRUE if days_ago == 0 else Truth.FALSE  # today | now


def _anchor_date(anchor_value: JsonValue, reference_time: datetime) -> date | None:
    if not isinstance(anchor_value, str):
        return None
    try:
        return date.fromisoformat(anchor_value)
    except ValueError:
        pass
    try:
        stamp = datetime.fromisoformat(anchor_value)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None  # a naive timestamp cannot be placed on the session's clock
    return stamp.astimezone(reference_time.tzinfo).date()
