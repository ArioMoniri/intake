"""INT-171 — the analytics views Loop 2 is allowed to read (files/09 §4, §7).

**What these views are not: de-identified free text.** They contain no
narrative at all — not redacted narrative, not pseudonymised narrative, none —
and the reason is recorded rather than assumed. files/10 §3 states it plainly:
spaCy ships no Turkish model, realistic recall on conversational Turkish runs
0.85-0.95 for names and addresses because the language is agglutinative and
names appear in oblique cases (*Ahmet'in*, *Ayşe'ye*), and at 3-8 direct
identifiers per four-minute intake that is roughly 0.3-1.0 expected leaks per
session. files/HUMAN_BLOCKERS.md HB-L6 records the same finding from the other
direction: the "de-identified" claim that would justify staff read paths over
patient content *"is one Turkish NLP cannot support"*.

So a view that would need narrative to be useful is not built. ``notes``,
``documents``, ``csat_texts`` and ``slots.value`` are absent from every
definition in ``migrations/versions/0009_int171_analytics_views.py``, and
``svc_learning_reader`` holds no grant that could reach them. What is left is
worth having on its own: which protocol ran, which step was answered, who
answered (self / proxy / assisted), and how the session ended — counted.

**Nor are they pseudonymised row exports.** Every view is already aggregated:
the projection carries the quasi-identifiers, a distinct-subject count and a
distinct-tenant count, and no ``patient_id``, ``session_id`` or ``tenant_id``
survives the ``GROUP BY``. A pseudonym is personal data under KVKK; a count of
pseudonyms, at or above the floor, is not.

**The Loop-2 opt-out is applied before anything is counted.** files/06 §2
makes ``learning:service_improvement`` an opt-out purpose and files/09 §5
promises the opt-out "costs no feature" — costing the patient nothing means
their sessions are not in the aggregate. Every view reads
``analytics.v_loop2_sessions``, which excludes any patient whose latest
recorded decision on that scope is a withdrawal (invariant 4: every read of
clinical data checks a consent scope). That base view is not granted to
``svc_learning_reader``.

**The k floor is enforced here, at the query layer** (the INT-171 acceptance
says so in those words) by :func:`intake_platform.analytics.materialise`. The
grant on the views is the *narrative* boundary; the gate is the *small-cell*
boundary. They are different controls and the split is deliberate: a principal
that reads a view directly rather than through :func:`materialise_view` has
still never been able to reach a patient's words, which is why the credentials
for these views are issued only to the sandboxed, read-only learning job
(files/10 §7).

The ISO-week bucket is not a grain chosen here: files/09 §4 runs Loop 2
"weekly as an Inspector → Architect pipeline" and asks for effect direction
"stable over 2 weeks", so the week is the unit the consumer already reasons
in.

Every figure these views produce is a measurement of a named cohort over a
stated window (invariant 20) — :class:`~intake_platform.analytics.Cohort` is a
required argument of every read, so an unattributed number cannot be
constructed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, TableClause, column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:  # pragma: no cover - import cycle broken for type checking only
    from intake_platform.analytics.k_anonymity import Cell, Cohort, Measurement

__all__ = [
    "ANALYTICS_SCHEMA",
    "ANALYTICS_VIEWS",
    "ATTRIBUTION_MIX",
    "SESSION_OUTCOMES",
    "STEP_COVERAGE",
    "AnalyticsView",
    "cells_from_rows",
    "cells_query",
    "materialise_view",
    "read_cells",
]

#: The Postgres schema the views live in; nothing else is created there.
ANALYTICS_SCHEMA = "analytics"


@dataclass(frozen=True)
class AnalyticsView:
    """One aggregate view, and the promises it makes about its own columns.

    ``dimensions`` are the quasi-identifiers — the combination a re-identifier
    would cross. ``subject_column`` counts distinct people (the floor applies
    to it, never to a row count) and ``tenant_column`` counts distinct clinics,
    which files/09 §4 wants as a stability criterion and which must never
    become a label.
    """

    name: str
    relation: str
    dimensions: tuple[str, ...]
    measures: tuple[str, ...]
    cohort_description: str
    narrative_exclusion: str
    window_column: str = "week_start"
    subject_column: str = "subjects"
    tenant_column: str = "tenants"

    @property
    def columns(self) -> tuple[str, ...]:
        """Everything the view projects, in select order."""
        return (*self.dimensions, self.subject_column, self.tenant_column, *self.measures)


SESSION_OUTCOMES = AnalyticsView(
    name="learning.session_outcomes",
    relation=f"{ANALYTICS_SCHEMA}.v_session_outcomes",
    dimensions=("protocol_id", "protocol_version", "week_start"),
    measures=("sessions", "completed", "cancelled"),
    cohort_description=(
        "intake sessions grouped by the protocol pack and version that ran and "
        "the ISO week they were created in"
    ),
    narrative_exclusion=(
        "session lifecycle counts only; the note payload and every slot value "
        "are outside the view and outside the learning reader's grants"
    ),
)

STEP_COVERAGE = AnalyticsView(
    name="learning.step_coverage",
    relation=f"{ANALYTICS_SCHEMA}.v_step_coverage",
    dimensions=("protocol_id", "slot_id", "week_start"),
    measures=("sessions_answered",),
    cohort_description=(
        "protocol steps that received an answer, grouped by pack, slot id and "
        "the ISO week of the session"
    ),
    narrative_exclusion=(
        "the slot id names the question asked; the answer itself is never "
        "projected — files/09 §4 asks for skip rates, not for what was said"
    ),
)

ATTRIBUTION_MIX = AnalyticsView(
    name="learning.attribution_mix",
    relation=f"{ANALYTICS_SCHEMA}.v_attribution_mix",
    dimensions=("protocol_id", "attribution", "week_start"),
    measures=("sessions",),
    cohort_description=(
        "who produced the answers (self / proxy / assisted self report), "
        "grouped by pack and ISO week"
    ),
    narrative_exclusion=(
        "a three-valued enumeration and a count; nothing identifies the "
        "companion, and no relationship is inferred (files/06 §7)"
    ),
)

ANALYTICS_VIEWS: Mapping[str, AnalyticsView] = {
    view.name: view for view in (SESSION_OUTCOMES, STEP_COVERAGE, ATTRIBUTION_MIX)
}


def _relation(view: AnalyticsView) -> TableClause:
    schema, _, relation = view.relation.partition(".")
    return table(relation, *(column(name) for name in view.columns), schema=schema)


def cells_query(
    view: AnalyticsView,
    *,
    cohort: Cohort,
    where: Mapping[str, str] | None = None,
) -> Select[Any]:
    """The SELECT the reader runs: declared columns only, window-bounded.

    Filter values are bound parameters, and filter keys must name a declared
    dimension — a caller cannot reach a column the view does not project, and
    cannot smuggle SQL through a dimension value.
    """
    relation = _relation(view)
    if where:
        unknown = sorted(set(where) - set(view.dimensions))
        if unknown:
            raise ValueError(f"{unknown} is not a dimension of {view.name!r}")
    window = relation.c[view.window_column]
    statement = select(*(relation.c[name] for name in view.columns)).where(
        window >= cohort.window_start.date(),
        window < cohort.window_end.date(),
    )
    for name, value in (where or {}).items():
        statement = statement.where(relation.c[name] == value)
    return statement.order_by(*(relation.c[name] for name in view.dimensions))


def _render(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def cells_from_rows(view: AnalyticsView, rows: Iterable[Mapping[Any, Any]]) -> tuple[Cell, ...]:
    """Project result rows onto :class:`~intake_platform.analytics.Cell`.

    A missing declared column raises ``KeyError`` rather than defaulting: a
    view whose shape has drifted from the registry must stop the read, not
    silently produce a cell with a hole in its quasi-identifier set.
    """
    from intake_platform.analytics.k_anonymity import Cell

    return tuple(
        Cell(
            dimensions={name: _render(row[name]) for name in view.dimensions},
            subjects=row[view.subject_column],
            tenants=row[view.tenant_column],
            measures={name: row[name] for name in view.measures},
        )
        for row in rows
    )


async def read_cells(
    session: AsyncSession,
    view: AnalyticsView,
    *,
    cohort: Cohort,
    where: Mapping[str, str] | None = None,
) -> tuple[Cell, ...]:
    """Run :func:`cells_query` and project the rows. Applies no floor — callers
    go through :func:`materialise_view`."""
    result = await session.execute(cells_query(view, cohort=cohort, where=where))
    return cells_from_rows(view, result.mappings().all())


async def materialise_view(
    session: AsyncSession,
    view: AnalyticsView,
    *,
    cohort: Cohort,
    k: int,
    where: Mapping[str, str] | None = None,
) -> Measurement:
    """Read a view and gate it. The sanctioned path, and the only one that
    produces a :class:`~intake_platform.analytics.Measurement`."""
    from intake_platform.analytics.k_anonymity import materialise

    cells = await read_cells(session, view, cohort=cohort, where=where)
    return materialise(view, cells, cohort=cohort, k=k)
