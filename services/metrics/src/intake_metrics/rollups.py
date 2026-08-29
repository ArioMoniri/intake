"""INT-240 — satisfaction rollups (files/08 §4 group F).

**A figure is a measurement, never a property (invariant 20).** Every rollup
type carries the cohort it measured, the window it covered and the moment it
was taken; :class:`Cohort` refuses a window that does not move forward or a
bound without a timezone. There is no way to hold "the CSAT score" detached
from the cohort and date that produced it, which is the whole point.

**A rollup carries counts and scores, never words (invariant 6).** The readers
select ``events.payload`` — the column declared id-shaped and PHI-free — and
project it immediately into :class:`CsatPoint` / a plain ``int``. Those types
have no text field, so a payload that somehow acquired one is dropped at the
boundary rather than filtered somewhere downstream where a later refactor could
forget. The ``csat_texts`` table, where the patient's actual sentence lives
under an envelope, is joined by nothing in this module.

**Small cohorts are suppressed, not reported.** The `experience` threat row's
control line names the k >= 10 floor (files/06 §8; files/08 §0c F9: *"the k >= 10
helper applies to every aggregate carrying a time filter and a clinic filter"*),
and a satisfaction rollup is exactly that shape. Suppression is total: below the
floor nothing but the count survives, because a five-response distribution
re-identifies as readily as a five-response mean.

Nothing here invents a cadence, a sampling rate or a retention window. The
caller names the window; the blueprint states no survey schedule and this
module does not guess one (INT-242 owns cadence).
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from clinical_schemas.events import ClinicianPulseV1, CsatReason, CsatV1, NpsV1
from intake_platform.analytics import K_ANONYMITY_FLOOR
from intake_platform.db.models import Event
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "MIN_COHORT",
    "Cohort",
    "CsatPoint",
    "CsatRollup",
    "NpsRollup",
    "PulseRollup",
    "csat_rollup",
    "nps_rollup",
    "pulse_rollup",
    "roll_up_csat",
    "roll_up_nps",
    "roll_up_pulse",
]

#: files/06 §8 and files/08 §0c F9, quoted by the `experience` threat row:
#: "k-anonymity floor on aggregates (k >= 10)". Not a tuning knob — a floor,
#: and since INT-171 a floor stated in exactly one place: two copies of a
#: privacy threshold are two chances for one of them to drift down.
MIN_COHORT = K_ANONYMITY_FLOOR

#: The standard NPS bands (0-10). ``nps.v1`` states "Standard NPS 0-10 scale",
#: and the promoter/passive/detractor split is that scale's definition, not a
#: threshold this repo chose.
_PROMOTER_FLOOR = 9
_PASSIVE_FLOOR = 7


@dataclass(frozen=True)
class Cohort:
    """Who was measured, and over what window. Invariant 20's "named cohort on
    a date", made a precondition of constructing any figure at all."""

    tenant_id: uuid.UUID
    window_start: datetime
    window_end: datetime

    def __post_init__(self) -> None:
        for name, bound in (("window_start", self.window_start), ("window_end", self.window_end)):
            if bound.tzinfo is None or bound.utcoffset() is None:
                raise ValueError(f"{name} must carry a timezone (a window is an instant range)")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be strictly after window_start")


@dataclass(frozen=True)
class CsatPoint:
    """One CSAT response, reduced to what an aggregate may see.

    The type is the guarantee: it has no ``text`` member, so the projection in
    :func:`_csat_points` is where a free-text fragment stops — before any
    counting, publishing or serialising can carry it further.
    """

    score: int
    reason: CsatReason


@dataclass(frozen=True)
class _Measurement:
    cohort: Cohort
    n: int
    suppressed: bool
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class CsatRollup(_Measurement):
    """``csat.score`` distribution + ``csat.reason`` counts for one cohort."""

    mean_score: float | None = None
    score_counts: Mapping[int, int] = field(default_factory=dict)
    reason_counts: Mapping[CsatReason, int] = field(default_factory=dict)


@dataclass(frozen=True)
class NpsRollup(_Measurement):
    """``nps.monthly`` for one cohort, with the split that produced it."""

    promoters: int | None = None
    passives: int | None = None
    detractors: int | None = None
    nps: float | None = None


@dataclass(frozen=True)
class PulseRollup(_Measurement):
    """``clinician.pulse`` for one cohort. Clinicians appear as counts only —
    ``clinician_ref`` is never carried into an aggregate (invariant 6)."""

    mean_score: float | None = None
    score_counts: Mapping[int, int] = field(default_factory=dict)


# --- pure rollups -------------------------------------------------------------------


def roll_up_csat(points: Sequence[CsatPoint], *, cohort: Cohort) -> CsatRollup:
    n = len(points)
    if n < MIN_COHORT:
        return CsatRollup(cohort=cohort, n=n, suppressed=True)
    scores = [point.score for point in points]
    return CsatRollup(
        cohort=cohort,
        n=n,
        suppressed=False,
        mean_score=sum(scores) / n,
        score_counts=dict(sorted(Counter(scores).items())),
        reason_counts=dict(Counter(point.reason for point in points)),
    )


def roll_up_nps(scores: Sequence[int], *, cohort: Cohort) -> NpsRollup:
    n = len(scores)
    if n < MIN_COHORT:
        return NpsRollup(cohort=cohort, n=n, suppressed=True)
    promoters = sum(1 for score in scores if score >= _PROMOTER_FLOOR)
    detractors = sum(1 for score in scores if score < _PASSIVE_FLOOR)
    return NpsRollup(
        cohort=cohort,
        n=n,
        suppressed=False,
        promoters=promoters,
        passives=n - promoters - detractors,
        detractors=detractors,
        nps=(promoters - detractors) / n * 100,
    )


def roll_up_pulse(scores: Sequence[int], *, cohort: Cohort) -> PulseRollup:
    n = len(scores)
    if n < MIN_COHORT:
        return PulseRollup(cohort=cohort, n=n, suppressed=True)
    return PulseRollup(
        cohort=cohort,
        n=n,
        suppressed=False,
        mean_score=sum(scores) / n,
        score_counts=dict(sorted(Counter(scores).items())),
    )


# --- readers ------------------------------------------------------------------------


async def _payloads(session: AsyncSession, *, event_type: str, cohort: Cohort) -> list[dict]:  # type: ignore[type-arg]
    rows = await session.scalars(
        select(Event.payload).where(
            Event.tenant_id == cohort.tenant_id,
            Event.event_type == event_type,
            Event.created_at >= cohort.window_start,
            Event.created_at < cohort.window_end,
        )
    )
    return [dict(row) for row in rows]


def _csat_points(payloads: Sequence[Mapping[str, object]]) -> list[CsatPoint]:
    """Validate against the committed schema, then drop everything an
    aggregate may not see. Both halves matter: validation refuses a malformed
    row instead of counting it, and the projection is where free text dies."""
    points: list[CsatPoint] = []
    for payload in payloads:
        event = CsatV1.model_validate(payload)
        points.append(CsatPoint(score=event.score, reason=event.reason))
    return points


async def csat_rollup(session: AsyncSession, *, cohort: Cohort) -> CsatRollup:
    payloads = await _payloads(session, event_type="csat.v1", cohort=cohort)
    return roll_up_csat(_csat_points(payloads), cohort=cohort)


async def nps_rollup(session: AsyncSession, *, cohort: Cohort) -> NpsRollup:
    payloads = await _payloads(session, event_type="nps.v1", cohort=cohort)
    return roll_up_nps([NpsV1.model_validate(p).score for p in payloads], cohort=cohort)


async def pulse_rollup(session: AsyncSession, *, cohort: Cohort) -> PulseRollup:
    payloads = await _payloads(session, event_type="clinician_pulse.v1", cohort=cohort)
    return roll_up_pulse(
        [ClinicianPulseV1.model_validate(p).score for p in payloads], cohort=cohort
    )
