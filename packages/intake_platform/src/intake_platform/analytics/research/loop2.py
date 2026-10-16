"""INT-490 — the release as INT-171 measurements, for Loop-2 evidence only.

CLAUDE.md invariant 12: learning is proposal-only, and what it may carry into
a proposal is evidence. This module is the whole of the bridge: it maps each
SHOWN view of a :class:`~.release.Release` to an INT-171
:class:`~intake_platform.analytics.AnalyticsView` and
:class:`~intake_platform.analytics.Measurement`, so that
``intake_learning.evidence.EvidenceBundle.build`` re-gates it through
:func:`~intake_platform.analytics.materialise` on the way into a bundle. A
withheld view has nothing to map; Loop 2 sees exactly what the panel shows and
nothing the cross-view check refused, so the two together disclose no more
than the panel alone.

Zero cells are left out, as INT-171 leaves them out: its gate refuses a cell
under the floor, and a materialised INT-171 view already reads an absent row
as an empty one.

Every view here is computed in-process; ``relation`` names no SQL relation and
these views are never handed to :func:`~intake_platform.analytics.cells_query`.
The prose they carry is committed here, byte for byte, which is the only prose
an evidence bundle accepts.
"""

from __future__ import annotations

from typing import Final

from intake_platform.analytics.k_anonymity import Cell, Cohort, Measurement
from intake_platform.analytics.research.catalogue import VIEW_SPECS, ViewKind
from intake_platform.analytics.research.release import Release
from intake_platform.analytics.views import AnalyticsView

__all__ = ["RESEARCH_VIEWS", "release_measurements"]

_POPULATION: Final[dict[ViewKind, str]] = {
    ViewKind.FUNNEL: "people with an intake of one protocol version opened in one ISO week, "
    "by the furthest funnel stage reached by the end of that week",
    ViewKind.TRIAGE: "people whose intake of one protocol version in one ISO week finished, "
    "by the rules-engine level on record",
    ViewKind.LOCALE: "people with an intake of one protocol version opened in one ISO week, "
    "by the language they were asked in",
    ViewKind.PLATFORM: "people with an intake of one protocol version opened in one ISO week, "
    "by the platform they used",
    ViewKind.QUESTION_OUTCOME: "people who reached one question of one protocol version in one "
    "ISO week, by how the question ended",
    ViewKind.QUESTION_MODE: "people who answered one question of one protocol version in one "
    "ISO week, by whether the answer was typed or spoken",
    ViewKind.QUESTION_REPEAT: "people who reached one question of one protocol version in one "
    "ISO week, by whether they asked for a repeat or clarification",
    ViewKind.QUESTION_TIME: "people who answered one question of one protocol version in one "
    "ISO week, by the band of time the answer took",
    ViewKind.QUESTION_ASR: "people who answered one question of one protocol version by voice in "
    "one ISO week, by the measured recognition-quality band of that answer",
}

_EXCLUSION: Final = (
    "counts of distinct people only, at least ten per cell, each person once per protocol "
    "version per week; no answer, note, document, transcript or identifier is read or carried"
)


def _view(kind: ViewKind) -> AnalyticsView:
    spec = VIEW_SPECS[kind]
    fixed: tuple[str, ...] = ("period", "protocol", "protocol_version")
    if spec.scope == "question":
        fixed = (*fixed, "question")
    return AnalyticsView(
        name=f"research.{kind.value}",
        relation="research.release",
        dimensions=(*fixed, spec.partition),
        measures=(),
        cohort_description=_POPULATION[kind],
        narrative_exclusion=_EXCLUSION,
    )


#: One INT-171 view per kind, committed — never built from data.
RESEARCH_VIEWS: Final[dict[ViewKind, AnalyticsView]] = {kind: _view(kind) for kind in ViewKind}


def release_measurements(
    release: Release,
) -> tuple[tuple[AnalyticsView, tuple[Measurement, ...]], ...]:
    """Per view kind with something shown: its view and one measurement per
    shown view of that kind (one per protocol version, or per question)."""
    grouped: dict[ViewKind, list[Measurement]] = {}
    for item in release.shown:
        view = RESEARCH_VIEWS[item.id.kind]
        cells = tuple(
            Cell(
                dimensions={
                    "period": release.period.id,
                    **item.id.dimensions(),
                    item.id.partition: cell.value,
                },
                subjects=cell.subjects,
                tenants=cell.tenants,
                measures={},
            )
            for cell in item.cells
            if cell.subjects
        )
        cohort = Cohort(
            description=view.cohort_description,
            window_start=release.period.start,
            window_end=release.period.end,
        )
        grouped.setdefault(item.id.kind, []).append(
            Measurement(
                view=view.name,
                cohort=cohort,
                k=release.k,
                cells=cells,
                measured_at=release.measured_at,
            )
        )
    return tuple(
        (RESEARCH_VIEWS[kind], tuple(measurements))
        for kind, measurements in sorted(
            grouped.items(), key=lambda item: VIEW_SPECS[item[0]].priority
        )
    )
