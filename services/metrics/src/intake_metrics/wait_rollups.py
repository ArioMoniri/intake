"""INT-241 — wait-time rollups (files/08 §4 group G).

Same shape as the INT-240 satisfaction rollups, and deliberately the same
floor: :data:`MIN_COHORT` is **imported** from :mod:`intake_metrics.rollups`,
never redefined. Two k-anonymity floors in one service is one floor that gets
lowered by accident.

**A figure is a measurement, never a property (invariant 20).** Every rollup
carries the :class:`~intake_metrics.rollups.Cohort` it measured, the window
that cohort covered and the instant the measurement was taken. There is no way
to hold "the wait time" detached from the cohort and window that produced it.

**Counts and durations only (invariant 6).** The reader projects
``events.payload`` — the column declared id-shaped and PHI-free — straight
into :class:`WaitObservation`, which has a duration and a closed enumeration
and nowhere to put anything else. The session id used to honour the
aggregation opt-out is consumed inside the reader and never reaches a rollup.

**Small cohorts are suppressed, and breakdowns are suppressed whole.**
files/08 §0c F9: an operational aggregate carrying a time filter and a clinic
filter identifies individuals, and the k >= 10 helper has to apply to console
reads too. Two rules follow, and the second is the one usually missed:

1. below the floor, nothing but ``n`` survives — not a mean, not a
   distribution, because a five-response mean re-identifies as readily as a
   five-response list;
2. a per-``document_type`` breakdown publishes **only when every one of its
   cells clears the floor**. Publishing the total plus all-but-one cell hands
   the reader the missing cell by subtraction, so the whole breakdown goes
   rather than the small cell alone.

**No minimum and no maximum, at any cohort size.** They are not aggregates:
each one is a single patient's actual wait, wearing a summary's clothes. The
type has nowhere to put one.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from clinical_schemas.events import DocumentKind, WaitKind, WaitV1
from intake_platform.consent import ConsentTextCatalog, is_scope_allowed
from intake_platform.db.models import Event, IntakeSession
from intake_platform.wait_times import WAIT_EVENT_TYPE, wait_source
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from intake_metrics.rollups import MIN_COHORT, Cohort

__all__ = [
    "AGGREGATION_SCOPE",
    "MIN_COHORT",
    "WaitCell",
    "WaitObservation",
    "WaitRollup",
    "labelled_durations",
    "roll_up_wait",
    "wait_observations",
    "wait_rollup",
]

#: files/06 §2: the de-identified-aggregate purpose (k >= 10, files/06 §8),
#: "an opt-out purpose whose refusal costs no feature". A wait-time rollup is
#: exactly that aggregate, so a patient who refused it is not in it.
AGGREGATION_SCOPE = "learning:service_improvement"


@dataclass(frozen=True)
class WaitObservation:
    """One completed interval, reduced to what an aggregate may see."""

    duration_ms: int
    document_type: DocumentKind | None = None


@dataclass(frozen=True)
class WaitCell:
    """One breakdown cell. A count and a mean — never an extremum."""

    n: int
    mean_ms: float


@dataclass(frozen=True)
class WaitRollup:
    """One wait metric over one cohort."""

    cohort: Cohort
    kind: WaitKind
    n: int
    suppressed: bool
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    mean_ms: float | None = None
    by_document_type: Mapping[DocumentKind, WaitCell] | None = None


def _mean(values: Sequence[int]) -> float:
    return sum(values) / len(values)


def labelled_durations(
    observations: Sequence[WaitObservation],
) -> list[tuple[DocumentKind, int]] | None:
    """``(document_type, duration_ms)`` for every observation, or ``None``.

    ``None`` means the set cannot be broken down at all: either nothing
    carries a label, or some do and some do not — and a partly-labelled set
    has an unlabelled remainder that is itself a derivable cell.
    """
    pairs = [
        (obs.document_type, obs.duration_ms)
        for obs in observations
        if obs.document_type is not None
    ]
    if not pairs or len(pairs) != len(observations):
        return None
    return pairs


def _breakdown(
    observations: Sequence[WaitObservation],
) -> Mapping[DocumentKind, WaitCell] | None:
    """Per-``document_type`` cells, or ``None`` when any cell would leak."""
    pairs = labelled_durations(observations)
    if pairs is None:
        return None
    cells: dict[DocumentKind, list[int]] = {}
    for document_type, duration_ms in pairs:
        cells.setdefault(document_type, []).append(duration_ms)
    if any(len(durations) < MIN_COHORT for durations in cells.values()):
        return None
    return {
        document_type: WaitCell(n=len(durations), mean_ms=_mean(durations))
        for document_type, durations in sorted(cells.items())
    }


def roll_up_wait(
    observations: Sequence[WaitObservation], *, cohort: Cohort, kind: WaitKind
) -> WaitRollup:
    n = len(observations)
    if n < MIN_COHORT:
        return WaitRollup(cohort=cohort, kind=kind, n=n, suppressed=True)
    return WaitRollup(
        cohort=cohort,
        kind=kind,
        n=n,
        suppressed=False,
        mean_ms=_mean([obs.duration_ms for obs in observations]),
        by_document_type=_breakdown(observations),
    )


async def wait_observations(
    session: AsyncSession,
    *,
    cohort: Cohort,
    kind: WaitKind,
    catalog: ConsentTextCatalog,
) -> list[WaitObservation]:
    """Read the cohort's observations, minus the patients who refused.

    The consent decision comes from the platform evaluator the API guard also
    uses (``is_scope_allowed`` wraps ``consent_state``), so a stale grant is
    treated here exactly as a route treats it. It is asked once per distinct
    patient, not once per row.

    An unobservable kind short-circuits to an empty list rather than querying:
    there is nothing to find, and a query that returns nothing looks
    indistinguishable from a quiet week.
    """
    if not wait_source(kind).observable:
        return []
    rows = (
        await session.execute(
            select(Event.payload, IntakeSession.patient_id)
            .join(IntakeSession, IntakeSession.id == Event.session_id)
            .where(
                Event.tenant_id == cohort.tenant_id,
                Event.event_type == WAIT_EVENT_TYPE,
                Event.created_at >= cohort.window_start,
                Event.created_at < cohort.window_end,
            )
        )
    ).all()
    allowed: dict[uuid.UUID, bool] = {}
    observations: list[WaitObservation] = []
    for payload, patient_id in rows:
        event = WaitV1.model_validate(dict(payload))
        if event.kind is not kind:
            continue
        if patient_id not in allowed:
            allowed[patient_id] = await is_scope_allowed(
                session,
                tenant_id=cohort.tenant_id,
                patient_id=patient_id,
                scope=AGGREGATION_SCOPE,
                catalog=catalog,
            )
        if not allowed[patient_id]:
            continue
        observations.append(
            WaitObservation(duration_ms=event.duration_ms, document_type=event.document_type)
        )
    return observations


async def wait_rollup(
    session: AsyncSession,
    *,
    cohort: Cohort,
    kind: WaitKind,
    catalog: ConsentTextCatalog,
) -> WaitRollup:
    observations = await wait_observations(session, cohort=cohort, kind=kind, catalog=catalog)
    return roll_up_wait(observations, cohort=cohort, kind=kind)
