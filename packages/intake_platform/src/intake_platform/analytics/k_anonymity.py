"""INT-171 — the k-anonymity gate for aggregate analytics (files/09 §6).

**This is a gate, not a helper.** ``materialise`` is the only way to turn a set
of aggregate cells into a figure a caller may hold, and it refuses rather than
returning something smaller. Nothing here suppresses a cell and carries on: a
reader who receives every cell but one, together with any wider aggregate over
the same population, recovers the missing cell by subtraction. So the artefact
is atomic — the whole view materialises or none of it does.

Four properties are worth stating because each of them is a way a small cohort
would otherwise escape:

1. **Subjects, not rows.** ``Cell.subjects`` is a distinct-person count. A
   chronic patient with forty follow-ups is one person wearing forty rows, and
   the floor is applied to the person.
2. **The threshold is supplied, never assumed.** ``k`` is keyword-only with no
   default, so a caller states the claim it is making. :data:`K_ANONYMITY_FLOOR`
   is the floor the blueprint states (files/06 §8, files/09 §4/§6, files/10 §9
   learning row, and the INT-171 acceptance all say k >= 10); a caller may
   raise the bar and may not lower it.
3. **The refusal is not an oracle.** It names the view, the threshold and a
   reason class — never which cell failed, never how many subjects it held.
   An empty result refuses with the same message as a single-subject result,
   because distinguishing "nobody was there" from "someone was there, but
   fewer than k" is itself the disclosure.
4. **No free text, structurally.** Dimension values must be id-shaped and
   measures must be counts; anything else stops the view. "No free-text
   outside the review UI" is then a property of the type rather than of a
   reviewer's attention — and the refusal never echoes the text it refused
   (invariant 6).

Refusals and materialisations are metered (files/10 §9 learning row: signal
"k-anonymity refusals"). The labels are the view name and the reason class and
nothing else: labelling a refusal with the offending branch or week would
publish to Prometheus exactly the cell the refusal withheld.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from prometheus_client import Counter

from intake_platform.analytics.views import AnalyticsView

__all__ = [
    "ANALYTICS_VIEW_MATERIALISED",
    "ANALYTICS_VIEW_REFUSED",
    "K_ANONYMITY_FLOOR",
    "Cell",
    "Cohort",
    "KAnonymityRefusal",
    "Measurement",
    "RefusalReason",
    "ThresholdBelowFloor",
    "materialise",
]

#: The floor the blueprint states, in four places that agree: files/06 §8
#: ("de-identified service-improvement aggregates (opt-out, k >= 10)"),
#: files/09 §4 ("aggregated, de-identified, k >= 10 per pattern"), files/09 §6
#: ("aggregate tables refuse patterns with n < 10") and the files/10 §9
#: learning row. Not a tuning knob: callers pass their own ``k`` and this is
#: the value below which the gate refuses to accept one.
K_ANONYMITY_FLOOR = 10

#: A dimension value is an identifier or an enumeration member, never prose.
#: Deliberately ASCII-only and short: Turkish narrative fails it on the first
#: space or the first ``ı``, which is the point (files/10 §3 — Turkish clinical
#: text is not de-identifiable to a standard this repo will assert).
_ID_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")

ANALYTICS_VIEW_REFUSED = Counter(
    "analytics_view_refused_total",
    "De-identified analytics views that refused to materialise, by view and "
    "reason class. Labels carry no cohort value (inv. 6).",
    ["view", "reason"],
)

ANALYTICS_VIEW_MATERIALISED = Counter(
    "analytics_view_materialised_total",
    "De-identified analytics views that cleared their k-anonymity threshold "
    "and were served, by view.",
    ["view"],
)


class RefusalReason(enum.StrEnum):
    """Why a view refused. A class, never a cohort."""

    #: at least one cell holds fewer than ``k`` distinct subjects — or the
    #: result holds no cell at all, which demonstrates nothing and is refused
    #: with the same message so the two cannot be told apart
    BELOW_K = "below_k"
    #: a dimension value is not id-shaped, i.e. it may be free text
    DIMENSION_NOT_ID_SHAPED = "dimension_not_id_shaped"
    #: a cell's dimension keys are not the view's declared quasi-identifiers
    DIMENSION_SET_MISMATCH = "dimension_set_mismatch"
    #: a measure is not a count
    MEASURE_NOT_A_COUNT = "measure_not_a_count"


class ThresholdBelowFloor(ValueError):
    """A caller asked for a threshold under :data:`K_ANONYMITY_FLOOR`."""


class KAnonymityRefusal(Exception):
    """The view did not materialise.

    Carries the view name, the threshold and the reason class — and nothing
    else. There is deliberately no way to ask which cell failed: an analyst who
    needs a figure widens the window or coarsens the dimensions and asks again.
    """

    def __init__(self, *, view: str, k: int, reason: RefusalReason) -> None:
        super().__init__(f"analytics view {view!r} refused to materialise: {reason} (k={k})")
        self.view = view
        self.k = k
        self.reason = reason


@dataclass(frozen=True)
class Cohort:
    """Who was measured, and over what window.

    Invariant 20 made a precondition of holding a figure at all: there is no
    constructor for a number detached from the population and the window that
    produced it.
    """

    description: str
    window_start: datetime
    window_end: datetime

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("a cohort needs a description: who was measured")
        for name, bound in (
            ("window_start", self.window_start),
            ("window_end", self.window_end),
        ):
            if bound.tzinfo is None or bound.utcoffset() is None:
                raise ValueError(f"{name} must carry a timezone (a window is an instant range)")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be strictly after window_start")


@dataclass(frozen=True)
class Cell:
    """One aggregate cell: a quasi-identifier combination and its counts.

    ``subjects`` is the distinct-person count and is what the floor is applied
    to. ``tenants`` is a count for the same reason files/09 §4 wants "at least
    2 clinics" — a stability criterion, never a clinic label.
    """

    dimensions: Mapping[str, str]
    subjects: int
    tenants: int
    measures: Mapping[str, int]


@dataclass(frozen=True)
class Measurement:
    """A figure, inseparable from the cohort and window that produced it."""

    view: str
    cohort: Cohort
    k: int
    cells: tuple[Cell, ...]
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def provenance(self) -> str:
        """The invariant-20 sentence: a measurement of a named cohort over a
        stated window, taken at a stated instant — never a property of the
        product."""
        return (
            f"Measured {self.view} for cohort {self.cohort.description!r} over "
            f"{self.cohort.window_start.isoformat()} to "
            f"{self.cohort.window_end.isoformat()}; taken "
            f"{self.measured_at.isoformat()}; suppressed below k={self.k}."
        )


def _refuse(view: str, k: int, reason: RefusalReason) -> KAnonymityRefusal:
    ANALYTICS_VIEW_REFUSED.labels(view=view, reason=reason.value).inc()
    return KAnonymityRefusal(view=view, k=k, reason=reason)


def _matches(cell: Cell, where: Mapping[str, str]) -> bool:
    return all(cell.dimensions.get(name) == value for name, value in where.items())


def _check_shape(view: AnalyticsView, cell: Cell, k: int) -> None:
    if set(cell.dimensions) != set(view.dimensions):
        raise _refuse(view.name, k, RefusalReason.DIMENSION_SET_MISMATCH)
    for value in cell.dimensions.values():
        if not isinstance(value, str) or _ID_SHAPE.match(value) is None:
            raise _refuse(view.name, k, RefusalReason.DIMENSION_NOT_ID_SHAPED)
    if set(cell.measures) != set(view.measures):
        raise _refuse(view.name, k, RefusalReason.MEASURE_NOT_A_COUNT)
    counts: Iterable[object] = (*cell.measures.values(), cell.subjects, cell.tenants)
    for count in counts:
        if isinstance(count, bool) or not isinstance(count, int):
            raise _refuse(view.name, k, RefusalReason.MEASURE_NOT_A_COUNT)


def materialise(
    view: AnalyticsView,
    cells: Sequence[Cell],
    *,
    cohort: Cohort,
    k: int,
    where: Mapping[str, str] | None = None,
) -> Measurement:
    """Serve ``cells`` as a :class:`Measurement`, or refuse the whole view.

    :param k: keyword-only, no default. Below :data:`K_ANONYMITY_FLOOR` raises
        :class:`ThresholdBelowFloor`; a caller may raise the bar.
    :raises KAnonymityRefusal: any cell holds fewer than ``k`` distinct
        subjects, the result is empty, or a cell is not the shape the view
        declared.
    """
    if k < K_ANONYMITY_FLOOR:
        raise ThresholdBelowFloor(
            f"k={k} is below the blueprint floor of {K_ANONYMITY_FLOOR} "
            "(files/06 §8; files/09 §4; files/10 §9 learning row)"
        )
    selected = tuple(cells)
    if where:
        unknown = sorted(set(where) - set(view.dimensions))
        if unknown:
            raise ValueError(f"{unknown} is not a dimension of {view.name!r}")
        selected = tuple(cell for cell in selected if _matches(cell, where))

    for cell in selected:
        _check_shape(view, cell, k)
    # An empty result and a below-floor result refuse identically: telling them
    # apart would disclose the existence of a patient in a cell just withheld.
    if not selected or any(cell.subjects < k for cell in selected):
        raise _refuse(view.name, k, RefusalReason.BELOW_K)

    ANALYTICS_VIEW_MATERIALISED.labels(view=view.name).inc()
    return Measurement(view=view.name, cohort=cohort, k=k, cells=selected)
