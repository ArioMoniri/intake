"""``protocol.must_ask_coverage``, computed (INT-081).

files/08 §D lists the metric with a target of ≥ 95 %; files/09 §2 makes it
one of four conditions for a pack to reach **L2 validated**. Neither says
what "covered" means, so this module fixes the definition and every later
consumer inherits it:

**Obliged** — a ``must_ask`` step whose gate is **TRUE or UNKNOWN**. That is
not a new rule: files/13 §9.4 already defines the budget governor's
outstanding set as ``R = |{must_ask steps still unasked whose gate is TRUE
or UNKNOWN}|``. A gate that is definitively FALSE never obliged anything, so
counting it would make coverage fall when a protocol correctly skips a
branch. UNKNOWN counts, because a gate that cannot be decided is exactly the
case where the question still has to be put.

**Covered** — an obliged step whose answer state *resolves* it:
``ASKED_PRESENT``, ``ASKED_ABSENT``, ``DECLINED``, ``CONTESTED``. A decline
is an elicited answer and counts; making coverage penalise a refusal would
put the metric in tension with consent. A contested slot counts because both
values reach the note (files/13 §11.2) — the question was asked and answered
twice, which is a coverage success and a reconciliation failure.

**Not covered** — ``NOT_ASKED``, ``ASKED_PENDING``, ``UNCLEAR``, and
``NOT_ASKED_PROXY`` (ADR-040): an item the pack skips in a proxy session was
not asked by design, so it is a gap the clinician sees, never a covered item.
``ASKED_PENDING`` is the one that matters: under ask-ahead a step is asked
long before anything binds, and files/13 §11.3 lets that answer be
*discarded* if a later extraction invalidates the step. Counting a pending
step would let ask-ahead inflate coverage with data the engine may be about
to throw away. ``UNCLEAR`` is a recorded gap (files/13 §11.1
``data_gaps[]``), which is the opposite of coverage.

The ratio is a :class:`~decimal.Decimal` — files/13 §9.5, "no floats
anywhere" — quantised to four places and rounded **down**, so the figure can
never overstate coverage of the set files/13 §9.4 calls the one thing the
turn budget may not silently drop. An empty obligation set yields ``None``
rather than 1: a session that owed nothing and a session that answered
everything are different facts, and an L2 gate that averages across sessions
has to be able to tell them apart.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_DOWN, Decimal

from clinical_schemas.common import FrozenModel
from clinical_schemas.session import AnswerState
from protocols.triage.expr import Truth
from pydantic import Field

__all__ = ["COVERED_STATES", "MustAskCoverage", "must_ask_coverage"]

COVERED_STATES = frozenset(
    {
        AnswerState.ASKED_PRESENT,
        AnswerState.ASKED_ABSENT,
        AnswerState.DECLINED,
        AnswerState.CONTESTED,
    }
)
"""Answer states that resolve a must-ask obligation (see the module docstring)."""

_QUANTUM = Decimal("0.0001")


class MustAskCoverage(FrozenModel):
    """One session's ``protocol.must_ask_coverage`` reading."""

    obliged: tuple[str, ...] = Field(
        default=(),
        description="must_ask steps whose gate is TRUE or UNKNOWN (files/13 §9.4), sorted.",
    )
    covered: tuple[str, ...] = Field(
        default=(), description="Obliged steps in a resolving answer state, sorted."
    )
    outstanding: tuple[str, ...] = Field(
        default=(), description="Obliged steps still unresolved, sorted."
    )
    ratio: Decimal | None = Field(
        default=None,
        description="covered / obliged, four places rounded down; None when nothing "
        "was obliged — never 1 by convention.",
    )


def must_ask_coverage(
    *, states: Mapping[str, AnswerState], gates: Mapping[str, Truth]
) -> MustAskCoverage:
    """Compute coverage over the ``must_ask`` steps described by ``states``.

    Every key of ``states`` is taken to be a ``must_ask`` step; the caller
    does the filtering, so this stays a pure function of two maps and can be
    exercised over states the engine cannot yet reach on its own.
    """
    obliged = sorted(
        step_id for step_id in states if gates.get(step_id, Truth.TRUE) is not Truth.FALSE
    )
    covered = [step_id for step_id in obliged if states[step_id] in COVERED_STATES]
    outstanding = [step_id for step_id in obliged if states[step_id] not in COVERED_STATES]
    ratio = (
        (Decimal(len(covered)) / Decimal(len(obliged))).quantize(_QUANTUM, rounding=ROUND_DOWN)
        if obliged
        else None
    )
    return MustAskCoverage(
        obliged=tuple(obliged),
        covered=tuple(covered),
        outstanding=tuple(outstanding),
        ratio=ratio,
    )
