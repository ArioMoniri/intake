"""INT-172 — the weekly run: read, inspect, propose, bundle, sign.

files/09 §4: "``services/learning`` runs weekly as an **Inspector → Architect**
pipeline". This module is that run, composed from the parts and holding no
policy of its own.

**Reading is INT-171's, not ours.** :func:`read_view` goes through
:func:`intake_platform.analytics.materialise_view`, which applies the k floor
at the query layer — never through ``read_cells``, which projects rows without
one. The cohort description is taken from the view registry rather than
supplied, which is the same rule :class:`~intake_learning.evidence.EvidenceBundle`
enforces on the way out: the only prose in a bundle is prose already committed
to ``intake_platform.analytics.views``, so a caller cannot name the cohort.

**The credentials are read-only, and the code cannot make them otherwise.** The
session handed to :func:`run_weekly` is expected to be
:data:`LEARNING_READER_ROLE` — INT-171's ``svc_learning_reader``, which holds
``CONNECT``, ``USAGE`` on the ``analytics`` schema and ``SELECT`` on three
aggregate views, and nothing else
(``migrations/versions/0009_int171_analytics_views.py``; the integration lane
in ``tests/learning/test_analytics_views_db.py`` proves the grant reaches no
base table). This module issues no statement of its own: it calls one
INT-171 function per view and never composes SQL, so a write is not something
it declines to do — it is something it has no expression for.

**Nothing is written and nothing is dispatched.** :func:`run_weekly` returns a
tuple of :class:`ProposalPackage` values. Opening a pull request is
:mod:`intake_learning.publisher`'s shape, and it refuses while files/09 §4's
evidence artefacts are unavailable — which is every bundle today.

sec_row: `learning-loops`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from intake_platform.analytics import (
    SESSION_OUTCOMES,
    STEP_COVERAGE,
    AnalyticsView,
    Cohort,
    Measurement,
    materialise_view,
)

from intake_learning.architect import PromotionThresholds, Proposal, propose
from intake_learning.evidence import EvidenceBundle, EvidenceSource
from intake_learning.inspector import Finding, inspect_session_outcomes, inspect_step_coverage
from intake_learning.signing import SignedBundle, sign_bundle

if TYPE_CHECKING:  # pragma: no cover - annotation only; see the module docstring
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "LEARNING_READER_ROLE",
    "RUN_CITATIONS",
    "ProposalPackage",
    "read_view",
    "run_weekly",
]

#: The Postgres role INT-171 created for this job. Named here so an operator
#: wiring the sandbox can grep for it; the grant itself lives in the migration
#: and is the actual control.
LEARNING_READER_ROLE: Final = "svc_learning_reader"

#: What every bundle this run produces cites. Fixed, because the reasoning it
#: points at is the same every week: files/09 §4 is the loop, files/09 §7 is the
#: sandbox, invariant 12 is the proposal-only rule, invariant 20 is why the
#: figures are phrased as measurements, and INT-171 is where the numbers came
#: from.
RUN_CITATIONS: Final[tuple[EvidenceSource, ...]] = (
    EvidenceSource.FILES_09_S4,
    EvidenceSource.FILES_09_S7,
    EvidenceSource.CLAUDE_INVARIANT_12,
    EvidenceSource.CLAUDE_INVARIANT_20,
    EvidenceSource.INT_171_ANALYTICS,
)


@dataclass(frozen=True)
class ProposalPackage:
    """One proposal and the signed evidence for it. Data, all the way down."""

    proposal: Proposal
    evidence: SignedBundle


async def read_view(
    session: AsyncSession,
    view: AnalyticsView,
    *,
    window_start: datetime,
    window_end: datetime,
    k: int,
) -> Measurement:
    """One gated read of one view.

    The cohort description is the registry's, not the caller's: a run cannot
    name the population it measured, which is what keeps the description a
    committed string rather than an input.
    """
    cohort = Cohort(
        description=view.cohort_description,
        window_start=window_start,
        window_end=window_end,
    )
    return await materialise_view(session, view, cohort=cohort, k=k)


def _package(
    proposals: Sequence[Proposal],
    *,
    view: AnalyticsView,
    measurements: Sequence[Measurement],
    k: int,
    key: bytes,
    key_id: str,
) -> tuple[ProposalPackage, ...]:
    return tuple(
        ProposalPackage(
            proposal=proposal,
            evidence=sign_bundle(
                EvidenceBundle.build(
                    view=view,
                    measurements=measurements,
                    citations=RUN_CITATIONS,
                    k=k,
                ),
                key=key,
                key_id=key_id,
            ),
        )
        for proposal in proposals
    )


async def run_weekly(
    session: AsyncSession,
    *,
    window_start: datetime,
    window_end: datetime,
    k: int,
    thresholds: PromotionThresholds,
    key: bytes,
    key_id: str,
) -> tuple[ProposalPackage, ...]:
    """The whole loop, once.

    ``thresholds`` is a required argument with no default, for the reason
    :meth:`PromotionThresholds.from_blueprint` raises: files/09 §4 states no
    effect-size floor, and a scheduled run cannot supply one that nobody has
    signed off. ``k`` is required for INT-171's reason — a caller states the
    claim it is making — and cannot be below the blueprint floor.

    :raises intake_platform.analytics.KAnonymityRefusal: a view could not be
        served at ``k``. The run stops rather than proposing from a thinner
        cohort than it claimed.
    """
    sessions = await read_view(
        session, SESSION_OUTCOMES, window_start=window_start, window_end=window_end, k=k
    )
    steps = await read_view(
        session, STEP_COVERAGE, window_start=window_start, window_end=window_end, k=k
    )

    findings: tuple[Finding, ...] = (
        *inspect_step_coverage(sessions=sessions, steps=steps),
        *inspect_session_outcomes(sessions),
    )
    return _package(
        propose(findings, thresholds=thresholds),
        view=STEP_COVERAGE,
        measurements=(steps,),
        k=k,
        key=key,
        key_id=key_id,
    )
