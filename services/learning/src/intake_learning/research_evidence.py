"""INT-490 — the research release as Loop-2 proposal evidence (invariant 12).

What Loop 2 may take from INT-490 is EVIDENCE: the views the admin panel
shows, each re-gated by :meth:`~intake_learning.evidence.EvidenceBundle.build`
at the INT-171 floor. Nothing here reads a table or a record — the input is an
already-gated :class:`~intake_platform.analytics.research.Release` — and
nothing here can name a proposal target, so the forbidden changes of
invariant 12 (red-flag levels, instruments, consent texts, the Talker tool
list, PolicyGuard, routing) have no path through it.

**Refused while LD-06's aggregate retention is undecided.** A bundle rides a
pull request, so it is KEPT for as long as the repository keeps it; LD-06
``retention.aggregates`` is the owner's undecided period, and the documented
fail-closed reading (``intake_platform.analytics.research.retention``) is that
nothing of that kind is kept until it is set.

sec_row: `observability-pipeline`.  legal: LD-06.
"""

from __future__ import annotations

from typing import Final

from intake_platform.analytics.research import (
    AnalyticsRetention,
    Release,
    release_measurements,
)

from intake_learning.evidence import EvidenceBundle, EvidenceSource

__all__ = ["RESEARCH_CITATIONS", "research_evidence_bundles"]

#: Every bundle from the release cites what makes it admissible.
RESEARCH_CITATIONS: Final = (
    EvidenceSource.INT_490_RESEARCH,
    EvidenceSource.LD_06,
    EvidenceSource.FILES_09_S4,
    EvidenceSource.CLAUDE_INVARIANT_12,
    EvidenceSource.CLAUDE_INVARIANT_20,
)


def research_evidence_bundles(
    release: Release, *, retention: AnalyticsRetention
) -> tuple[EvidenceBundle, ...]:
    """One bundle per view kind with something shown.

    :raises intake_platform.analytics.research.RetentionUndecided: the
        aggregate retention period is not set (LD-06, draft).
    """
    retention.require_keeping()
    return tuple(
        EvidenceBundle.build(
            view=view,
            measurements=measurements,
            citations=RESEARCH_CITATIONS,
            k=release.k,
        )
        for view, measurements in release_measurements(release)
    )
