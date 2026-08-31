"""Typed answer/slot state the triage engine evaluates over (INT-080).

The shapes align with the INT-031 ``SessionState`` (files/13 §9.2-9.3):
answer states are :class:`clinical_schemas.session.AnswerState`, values are
:data:`SlotValue`, and the clock is the session's ``reference_time`` — a
pure fold input, never a wall clock. The projection from a live
``SessionState`` (step ↔ slot bookkeeping) is owned by the IntakeEngine
issue (INT-081); this module owns only what a rule can read.

Three-valued reading (files/12 §1.1; files/13 §9.5): a slot whose answer
state carries no usable value — ``not_asked``, ``unclear``, and equally
``asked_pending`` (nothing bound yet) and ``declined`` (rendering a decline
as *elicited and absent* is the exact defect §1.1 names) — reads Unknown.
``contested`` keeps every value: files/12 §7.3, triage evaluates on the
union of head and superseded values and takes max acuity.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.session import AnswerState
from pydantic import AwareDatetime, Field, model_validator

from protocols.triage.expr import Truth
from protocols.types import Tense

__all__ = [
    "SlotAnswer",
    "SlotValue",
    "TriageContext",
    "canonical_scalar",
    "render_slot_value",
    "temporal_within",
]

#: What one slot answer may carry. ``JsonValue`` alone would be wrong in
#: both directions (INT-267): it admits ``float``, which files/13 §9.5
#: forbids on the comparison path, and it excludes ``Decimal``, which is
#: exactly what INT-083's extraction emits for a decimal or quantity slot
#: so that no float crosses that boundary (CLAUDE.md invariant 22). A
#: pydantic field typed ``JsonValue`` silently coerces an incoming
#: ``Decimal`` into a ``float`` — the unguarded representation crossing the
#: invariant names — so ``Decimal`` is admitted here explicitly and carried
#: through untouched. ``float`` stays admitted because the JSON carrier can
#: still produce one; :func:`canonical_scalar` is where it stops being one.
type SlotValue = Decimal | JsonValue

_VALUE_BEARING = frozenset({AnswerState.ASKED_PRESENT, AnswerState.ASKED_ABSENT})


class SlotAnswer(FrozenModel):
    """One slot's answer state plus the value(s) it carries."""

    state: AnswerState = Field(
        description="Answer state, files/13 §9.3 seven states via the INT-031 SessionState enum."
    )
    values: tuple[SlotValue, ...] = Field(
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

    def candidate_values(self, ref: str) -> tuple[SlotValue, ...] | None:
        """The value(s) a predicate may read for ``ref``; None reads Unknown."""
        slot = self.answers.get(ref)
        if slot is None:
            return None
        if slot.state in _VALUE_BEARING or slot.state is AnswerState.CONTESTED:
            return slot.values
        return None


def canonical_scalar(value: SlotValue) -> bool | Decimal | str | None:
    """Canonicalise one slot value for comparison; None reads Unknown.

    Numbers become Decimal (files/13 §9.5: exact comparison, no floats —
    a float arriving through the JSON carrier is converted through its
    string form, deterministically). A ``Decimal`` is *already* that
    canonical form, so it is accepted and returned **unchanged**: this
    function's own declared return type is one of its inputs, and INT-083's
    extraction emits decimal and quantity slots as exact ``Decimal``
    precisely so that no float crosses the boundary (invariant 22). Before
    INT-267 a ``Decimal`` fell through to ``None`` and therefore read
    Unknown to every gate that referenced it.

    **Scale is carried, never normalised.** files/13 §9.5 types a decimal
    slot as "``Decimal`` with declared scale and exact comparison", so
    ``Decimal("38.50")`` stays ``Decimal("38.50")``: the scale belongs to
    the slot that was authored, not to this function. Re-converting through
    ``str`` would be a no-op and ``quantize`` would silently rewrite the
    authored scale, which every textual render — a rule's evidence line,
    the clinician note, the invariant-22 orthography expansion — would then
    report wrong. No verdict can turn on the choice: :mod:`protocols.triage.
    expr` compares Decimals by numeric value, where ``38.50 == 38.5``.

    A non-finite number — NaN or an infinity, reachable both through the
    JSON carrier and as a ``Decimal`` — is a data defect rather than a
    magnitude, so it reads Unknown: a rule can never fire on it, and an
    ordered comparison against it can never raise ``InvalidOperation`` on
    the triage path. Collections and null do not compare in this grammar
    and read Unknown too.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        value = Decimal(str(value))
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, str):
        return value
    return None


def render_slot_value(value: SlotValue) -> str:
    """One carried value as text, exactly as it was carried.

    The single canonical rendering of a slot value, used by two callers that
    must never disagree: the engine's rule-evidence line
    (:func:`~protocols.triage.engine.evaluate_triage`) and the attestation's
    ``inputs_hash`` (:func:`~protocols.triage.attestation.context_inputs_hash`).
    Two copies of a canonicalisation is how a hash and the text it claims to
    cover drift apart.

    ``json.dumps`` cannot serialise a ``Decimal`` at all, and routing one
    through ``float`` to make it serialisable would put a float on the path
    files/13 §9.5 keeps clear of them and drop the authored scale that
    :func:`canonical_scalar` deliberately carries (INT-267). A Decimal
    therefore renders from its own exact form, which is already a JSON number
    literal.
    """
    if isinstance(value, Decimal):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def temporal_within(anchor_value: SlotValue, tense: Tense, reference_time: datetime) -> Truth:
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


def _anchor_date(anchor_value: SlotValue, reference_time: datetime) -> date | None:
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
