"""INT-490 — the release: which views are shown, and why the others are not.

Three gates, in this order, each one LD-06's:

1. **A view is listed only if its population holds at least k people.** A
   listed view tells its reader the population exists; listing a view of
   three people, even withheld, would be the INT-171 oracle ("nobody was
   there" told apart from "fewer than k were"). An unlisted view and a view
   nobody fell into look the same: absent.
2. **Within a view, all its cells show or none do** (LD-06
   ``whole_views_only``). A listed view whose cells include one holding
   between 1 and k-1 people is withheld whole — no cell of it, large or
   small, is published, so no cell of it can be recovered by subtraction
   from its siblings. Zero is published, as INT-171's materialised views
   publish it by absence.
3. **Across views, nothing small is recoverable** (LD-06 ``across_views``).
   :func:`~intake_platform.analytics.research.audit.find_recoverable_small_set`
   runs over every shown cell together; while it finds a group of 1..k-1
   people that arithmetic over shown counts would reveal, the lowest-priority
   view the group runs through is withheld and the check runs again. It ends
   with a release the check cannot fault, or with nothing shown.

The floor is INT-171's :data:`~intake_platform.analytics.K_ANONYMITY_FLOOR`,
imported and never redeclared; ``k`` is keyword-only with no default and may
be raised, never lowered.

Metrics carry the view KIND and a reason class only — never a protocol, a
version, a question or a week, which would publish to Prometheus the very cell
a refusal withheld (invariant 6).
"""

from __future__ import annotations

import enum
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from prometheus_client import Counter

from intake_platform.analytics.k_anonymity import (
    _ID_SHAPE,
    K_ANONYMITY_FLOOR,
    ThresholdBelowFloor,
)
from intake_platform.analytics.research.audit import find_recoverable_small_set
from intake_platform.analytics.research.catalogue import (
    QUESTION_VIEW_KINDS,
    VIEW_SPECS,
    Period,
    ViewKind,
)
from intake_platform.analytics.research.records import QuestionRecord, SubjectRecord

__all__ = [
    "ANALYTICS_RESEARCH_VIEW_SHOWN",
    "ANALYTICS_RESEARCH_VIEW_WITHHELD",
    "NotCollected",
    "Release",
    "ReleasedCell",
    "ReleasedView",
    "ViewId",
    "WithheldReason",
    "WithheldView",
    "build_release",
]

ANALYTICS_RESEARCH_VIEW_SHOWN = Counter(
    "analytics_research_view_shown_total",
    "Research analytics views shown in a release, by view kind.",
    ["view"],
)
ANALYTICS_RESEARCH_VIEW_WITHHELD = Counter(
    "analytics_research_view_withheld_total",
    "Research analytics views withheld from a release, by view kind and reason class.",
    ["view", "reason"],
)


class WithheldReason(enum.StrEnum):
    #: a cell of the view holds between 1 and k-1 people
    BELOW_K = "below_k"
    #: showing the view would let a small group be recovered across views
    CROSS_VIEW = "cross_view"


@dataclass(frozen=True)
class ViewId:
    kind: ViewKind
    protocol: str
    protocol_version: str
    question: str | None = None

    @property
    def partition(self) -> str:
        return VIEW_SPECS[self.kind].partition

    def sort_key(self) -> tuple[int, str, str, str]:
        return (
            VIEW_SPECS[self.kind].priority,
            self.protocol,
            self.protocol_version,
            self.question or "",
        )

    def dimensions(self) -> dict[str, str]:
        """The view's fixed dimensions (the period is the release's)."""
        out = {"protocol": self.protocol, "protocol_version": self.protocol_version}
        if self.question is not None:
            out["question"] = self.question
        return out


@dataclass(frozen=True)
class ReleasedCell:
    value: str
    subjects: int
    #: distinct clinics among the cell's people: Loop 2's stability criterion
    #: (files/09 §4, "at least 2 clinics"), a count and never a label
    tenants: int


@dataclass(frozen=True)
class ReleasedView:
    id: ViewId
    cells: tuple[ReleasedCell, ...]

    @property
    def population(self) -> int:
        return sum(cell.subjects for cell in self.cells)


@dataclass(frozen=True)
class WithheldView:
    id: ViewId
    reason: WithheldReason


@dataclass(frozen=True)
class NotCollected:
    """A view kind with no source behind it, and the reason class why."""

    kind: ViewKind
    reason: str


@dataclass(frozen=True)
class Release:
    period: Period
    k: int
    shown: tuple[ReleasedView, ...]
    withheld: tuple[WithheldView, ...]
    not_collected: tuple[NotCollected, ...]
    measured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def lookup(self, view: ViewId) -> ReleasedView | WithheldView | None:
        for shown in self.shown:
            if shown.id == view:
                return shown
        for withheld in self.withheld:
            if withheld.id == view:
                return withheld
        return None


_Members = dict[str, set[Hashable]]


def _partition_value(kind: ViewKind, record: SubjectRecord, question: str | None) -> str | None:
    """The cell ``record`` falls in, or ``None`` when it is outside the view."""
    if kind is ViewKind.FUNNEL:
        return record.stage.value
    if kind is ViewKind.TRIAGE:
        return record.triage.value if record.triage is not None else None
    if kind is ViewKind.LOCALE:
        return record.locale
    if kind is ViewKind.PLATFORM:
        return record.platform.value if record.platform is not None else None
    answer: QuestionRecord | None = record.questions.get(question or "")
    if answer is None:
        return None
    if kind is ViewKind.QUESTION_OUTCOME:
        return answer.outcome.value
    if kind is ViewKind.QUESTION_REPEAT:
        return answer.repeat.value
    if kind is ViewKind.QUESTION_MODE:
        return answer.input_mode.value if answer.input_mode is not None else None
    if kind is ViewKind.QUESTION_TIME:
        return answer.time_band.value if answer.time_band is not None else None
    return answer.asr_band.value if answer.asr_band is not None else None


def _validate(records: tuple[SubjectRecord, ...]) -> None:
    seen: set[tuple[Hashable, str, str]] = set()
    for record in records:
        ids = (record.protocol, record.protocol_version, *record.questions)
        if any(_ID_SHAPE.match(value) is None for value in ids):
            # names the field class, never the value (invariant 6)
            raise ValueError("a protocol, version or question is not id-shaped")
        key = (record.subject, record.protocol, record.protocol_version)
        if key in seen:
            raise ValueError("a person counts once per protocol version per week")
        seen.add(key)


def _candidates(
    records: tuple[SubjectRecord, ...], collected: frozenset[ViewKind]
) -> dict[ViewId, tuple[_Members, dict[str, set[Hashable]]]]:
    families: dict[tuple[str, str], list[SubjectRecord]] = {}
    for record in records:
        families.setdefault(record.family, []).append(record)
    out: dict[ViewId, tuple[_Members, dict[str, set[Hashable]]]] = {}
    for (protocol, version), members in sorted(families.items()):
        questions = sorted({q for record in members for q in record.questions})
        for kind in sorted(collected, key=lambda kind: VIEW_SPECS[kind].priority):
            spec = VIEW_SPECS[kind]
            scoped: list[str | None] = list(questions) if kind in QUESTION_VIEW_KINDS else [None]
            for question in scoped:
                cells: _Members = {value: set() for value in spec.domain}
                clinics: dict[str, set[Hashable]] = {value: set() for value in spec.domain}
                for record in members:
                    value = _partition_value(kind, record, question)
                    if value is None:
                        continue
                    if value not in cells:
                        raise ValueError(f"a {spec.partition} value is outside the closed domain")
                    cells[value].add(record.subject)
                    clinics[value].add(record.tenant)
                out[ViewId(kind, protocol, version, question)] = (cells, clinics)
    return out


def build_release(
    records: Iterable[SubjectRecord],
    *,
    period: Period,
    k: int,
    collected: frozenset[ViewKind],
    not_collected: Mapping[ViewKind, str],
    measured_at: datetime | None = None,
) -> Release:
    """Count ``records`` into views and gate them. See the module docstring.

    ``collected`` and ``not_collected`` together name every view kind exactly
    once: a kind with no source is reported with its reason, never silently
    absent.
    """
    if k < K_ANONYMITY_FLOOR:
        raise ThresholdBelowFloor(
            f"k={k} is below the product floor of {K_ANONYMITY_FLOOR} (LD-06; INT-171)"
        )
    if set(collected) | set(not_collected) != set(ViewKind) or set(collected) & set(not_collected):
        raise ValueError("every view kind is either collected or not collected, exactly once")
    rows = tuple(records)
    _validate(rows)

    shown: dict[ViewId, tuple[_Members, dict[str, set[Hashable]]]] = {}
    withheld: dict[ViewId, WithheldReason] = {}
    for view, (cells, clinics) in _candidates(rows, collected).items():
        sizes = [len(people) for people in cells.values()]
        if sum(len(people) for people in cells.values()) < k:
            continue  # gate 1: not listed
        if any(0 < size < k for size in sizes):
            withheld[view] = WithheldReason.BELOW_K  # gate 2
            continue
        shown[view] = (cells, clinics)

    while shown:  # gate 3
        cell_map: dict[Hashable, frozenset[Hashable]] = {
            (view, value): frozenset(people)
            for view, (cells, _) in shown.items()
            for value, people in cells.items()
            if people
        }
        violation = find_recoverable_small_set(cell_map, k=k)
        if violation is None:
            break
        implicated = {cell[0] for cell in violation.cells if isinstance(cell, tuple)}
        victim = max(implicated & set(shown), key=ViewId.sort_key)
        del shown[victim]
        withheld[victim] = WithheldReason.CROSS_VIEW

    released = tuple(
        ReleasedView(
            id=view,
            cells=tuple(
                ReleasedCell(value=value, subjects=len(people), tenants=len(clinics[value]))
                for value, people in cells.items()
            ),
        )
        for view, (cells, clinics) in sorted(shown.items(), key=lambda item: item[0].sort_key())
    )
    for item in released:
        ANALYTICS_RESEARCH_VIEW_SHOWN.labels(view=item.id.kind.value).inc()
    for view, reason in withheld.items():
        ANALYTICS_RESEARCH_VIEW_WITHHELD.labels(view=view.kind.value, reason=reason.value).inc()
    return Release(
        period=period,
        k=k,
        shown=released,
        withheld=tuple(
            WithheldView(id=view, reason=reason)
            for view, reason in sorted(withheld.items(), key=lambda item: item[0].sort_key())
        ),
        not_collected=tuple(
            NotCollected(kind=kind, reason=reason)
            for kind, reason in sorted(
                not_collected.items(), key=lambda item: VIEW_SPECS[item[0]].priority
            )
        ),
        measured_at=measured_at if measured_at is not None else datetime.now(UTC),
    )
