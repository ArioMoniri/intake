"""INT-172 — the Inspector half of files/09 §4's Inspector → Architect pipeline.

files/09 §4: "Inspectors write case-level findings on de-identified traces".
"De-identified traces" is the phrase, and it is worth being exact about what
this repository is willing to mean by it. files/HUMAN_BLOCKERS.md HB-L6 records
that the de-identification claim Turkish NLP would have to support does not
hold, and INT-171 acted on that: the analytics layer carries no narrative at
all, only counts over id-shaped quasi-identifiers, gated at k >= 10.

So an Inspector here reads :class:`~intake_platform.analytics.Measurement`
values and nothing else. There is no argument that could carry a session, a
transcript or a row, which is why the "no identifiable data in a proposal"
half of files/09 §4 needs no scrubber: the pipeline's input alphabet is
already the gate's output alphabet.

**A Finding is issued, never constructed.** The constructor is sealed against
callers outside this module (:data:`_ISSUED_BY_INSPECTOR`). Every id inside a
Finding came out of a Measurement's cells, and INT-171 has already refused
those unless they are id-shaped; a hand-built Finding would be an id nothing
vetted, and it would reach a PR branch name and a PR body.

sec_row: `learning-loops`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from intake_platform.analytics import SESSION_OUTCOMES, STEP_COVERAGE, AnalyticsView, Measurement
from prometheus_client import Counter

from intake_learning.proposals import Signal

__all__ = [
    "LEARNING_FINDINGS",
    "Finding",
    "Signal",
    "inspect_session_outcomes",
    "inspect_step_coverage",
]

LEARNING_FINDINGS = Counter(
    "learning_findings_total",
    "Case-level findings written by a Loop 2 Inspector, by signal. Counts "
    "only: no cohort, no pack and no clinic appears as a label (inv. 6).",
    ["signal"],
)

#: The seal. Module-private by convention, which is the strongest form Python
#: offers and the same one ``ToolRegistry.seal()`` relies on in the Talker
#: (INT-091). It is not a cryptographic barrier; it is a statement that the
#: only supported way to obtain a Finding is to run an Inspector over a gated
#: Measurement, and it makes an accidental hand-build fail loudly.
_ISSUED_BY_INSPECTOR: Final = object()


@dataclass(frozen=True)
class Finding:
    """One week of one signal, as counts.

    ``numerator``/``denominator`` rather than a rate: invariant 20 wants a
    measurement of a named cohort, and a bare float detached from its
    denominator is exactly the shape a "product property" takes. :attr:`rate`
    derives one for a comparison and is not what is carried anywhere.
    """

    signal: Signal
    view: str
    pack_id: str
    slot_id: str | None
    week_start: str
    subjects: int
    tenants: int
    numerator: int
    denominator: int
    issued_by: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.issued_by is not _ISSUED_BY_INSPECTOR:
            raise TypeError(
                "a Finding is issued by an Inspector in "
                "intake_learning.inspector, never constructed directly: every "
                "id in one came out of a k-gated Measurement (INT-171), and a "
                "hand-built Finding carries an id nothing has vetted"
            )
        if self.denominator <= 0:
            raise ValueError("a finding needs a population to be a fraction of")

    @property
    def rate(self) -> float:
        return self.numerator / self.denominator

    @property
    def key(self) -> tuple[str, str, str | None]:
        """What "the same finding, again next week" means."""
        return (self.signal.value, self.pack_id, self.slot_id)


def _require_view(measurement: Measurement, expected: AnalyticsView) -> None:
    if measurement.view != expected.name:
        raise ValueError(
            f"this inspector reads {expected.name!r}; it was handed "
            f"{measurement.view!r}. Views are not interchangeable — their "
            "quasi-identifier sets differ, and reading one as the other would "
            "cross cells that were never gated together"
        )


def _issue(
    *,
    signal: Signal,
    view: str,
    pack_id: str,
    slot_id: str | None,
    week_start: str,
    subjects: int,
    tenants: int,
    numerator: int,
    denominator: int,
) -> Finding:
    """The one place :data:`_ISSUED_BY_INSPECTOR` is handed over."""
    finding = Finding(
        signal=signal,
        view=view,
        pack_id=pack_id,
        slot_id=slot_id,
        week_start=week_start,
        subjects=subjects,
        tenants=tenants,
        numerator=numerator,
        denominator=denominator,
        issued_by=_ISSUED_BY_INSPECTOR,
    )
    LEARNING_FINDINGS.labels(signal=finding.signal.value).inc()
    return finding


def _sessions_by_pack_week(sessions: Measurement) -> Mapping[tuple[str, str], int]:
    """(protocol_id, week_start) -> sessions, summed over protocol versions.

    Summing across versions is deliberate: a pack that shipped a new version
    mid-window would otherwise split its own denominator and look like two
    thin cohorts. The k floor was applied per cell before this, so the sum is
    of already-safe numbers.
    """
    totals: dict[tuple[str, str], int] = {}
    for cell in sessions.cells:
        key = (cell.dimensions["protocol_id"], cell.dimensions["week_start"])
        totals[key] = totals.get(key, 0) + cell.measures["sessions"]
    return totals


def inspect_step_coverage(*, sessions: Measurement, steps: Measurement) -> tuple[Finding, ...]:
    """files/09 §4, "per protocol step — … skip rate".

    A step's skip rate is the sessions that ran the pack minus the sessions
    that answered the step, over the sessions that ran the pack. Both halves
    come from gated views, and a step week with no matching pack week yields
    nothing rather than a finding with a guessed denominator.
    """
    _require_view(sessions, SESSION_OUTCOMES)
    _require_view(steps, STEP_COVERAGE)

    denominators = _sessions_by_pack_week(sessions)
    findings: list[Finding] = []
    for cell in steps.cells:
        pack_id = cell.dimensions["protocol_id"]
        week_start = cell.dimensions["week_start"]
        denominator = denominators.get((pack_id, week_start))
        if denominator is None:
            continue
        answered = cell.measures["sessions_answered"]
        findings.append(
            _issue(
                signal=Signal.STEP_SKIP_RATE,
                view=steps.view,
                pack_id=pack_id,
                slot_id=cell.dimensions["slot_id"],
                week_start=week_start,
                subjects=cell.subjects,
                tenants=cell.tenants,
                numerator=max(denominator - answered, 0),
                denominator=denominator,
            )
        )
    return tuple(findings)


def inspect_session_outcomes(sessions: Measurement) -> tuple[Finding, ...]:
    """files/09 §4, "per protocol step — … abandonment".

    Cancelled sessions over sessions, per pack and week. Sessions and
    cancellations are *summed* across protocol versions, for the reason
    :func:`_sessions_by_pack_week` gives; the protocol version stays out of the
    finding because a proposal is about a pack, and naming a version would
    invite a proposal that targets one build.

    ``subjects`` and ``tenants`` are the **maximum** across versions, not the
    sum. They are distinct-entity counts, and the same person may appear under
    two versions — summing would claim a cohort larger than the one that
    existed, which is the direction that matters when the number is what a
    threshold is compared against. The maximum is the guaranteed lower bound.
    """
    _require_view(sessions, SESSION_OUTCOMES)

    totals: dict[tuple[str, str], list[int]] = {}
    for cell in sessions.cells:
        key = (cell.dimensions["protocol_id"], cell.dimensions["week_start"])
        row = totals.setdefault(key, [0, 0, 0, 0])
        row[0] += cell.measures["cancelled"]
        row[1] += cell.measures["sessions"]
        row[2] = max(row[2], cell.subjects)
        row[3] = max(row[3], cell.tenants)

    return tuple(
        _issue(
            signal=Signal.SESSION_ABANDONMENT,
            view=sessions.view,
            pack_id=pack_id,
            slot_id=None,
            week_start=week_start,
            subjects=subjects,
            tenants=tenants,
            numerator=cancelled,
            denominator=total,
        )
        for (pack_id, week_start), (cancelled, total, subjects, tenants) in sorted(totals.items())
    )
