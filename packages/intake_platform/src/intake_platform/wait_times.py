"""INT-241 — wait-time observation: the source registry and the writer.

files/08 §4 group G names six wait ids and INT-241's acceptance enumerates
five of them. Naming a metric is not the same as being able to measure it, and
the difference is what this module makes mechanical.

**The source registry is the honest statement of what exists.** Each kind
declares the two instants its interval runs between and whether *this repo*
records both of them today. A kind that does not is `observable=False`, says
in `missing_instant` exactly which end is absent, names the issue that would
land it where one exists, keeps `status: planned` in the catalogue (invariant
13 — do not promote to live what nothing exposes), and makes
:func:`record_wait` **raise** rather than mint an observation whose endpoints
do not exist. Three artefacts, one fact: the registry, the catalogue status
and the writer cannot drift apart, and the day an instant lands,
`tests/experience/test_wait_metrics.py` fails until all three move together.

One of the four original gaps had an owning issue — INT-163 for connector
check-in — and it is now landed: `packages/connectors` mints a signed check-in
payload (its `iat` is the check-in instant) and records the wait at desk
verification, so both instants live in the repo. Three gaps remain: no issue in
the backlog claims the intake lifecycle instants — `sessions.started_at`, the
first question reaching the patient, `sessions.completed_at` — and INT-150
delivered the Doctor Link redemption route without the interval, for the reason
its `missing_instant` states. So `blocked_by` is honestly `None` on all three
and the ask is recorded in docs/evidence/INT-241.md and docs/evidence/INT-150.md
rather than attributed to an issue that never promised it.

Today two intervals have both instants: document processing begins and ends
inside a single request handler (`intake_api.documents.ingest_content`), and
connector check-in runs from the payload's signed `iat` to desk verification
(INT-163). The other three are named, gated and empty — build the mechanism,
wire the gate, make it fail closed, leave the content empty (CLAUDE.md).

**A missing instant and a missing writer are different sentences (INT-307).**
Until INT-307 the only publisher was bound to the one labelled family, so a
group G id that carries no label had a catalogue row, a registry entry, an
admin column and no way to be written even once its instants landed — which
is why INT-150 declined to add ``shares.first_opened_at`` rather than land an
instant into a gap. The writer is now generic over the label set (declared
here in ``labels``) and over the catalogued unit, and every entry states
``publisher`` or the issue that owes one. So the four gaps are gaps in
*measurement*, said once, in ``missing_instant``.

**What an observation carries.** A duration in milliseconds and, for the
records kind, a closed content-type enumeration. Not two instants: an instant
plus a session id is a queue position that correlates to a person, a duration
is not. Not a name, not a note, not a branch — the aggregate that reads these
rows is published to an operations console, and files/08 §0c F9 is explicit
that a clinic filter plus a time filter on such an aggregate identifies
individuals.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from clinical_schemas.events import DocumentKind, WaitKind, WaitV1

from intake_platform.db.models import Event
from intake_platform.documents import ALLOWED_CONTENT_TYPES
from intake_platform.slo import MetricsCatalog

__all__ = [
    "DOCUMENT_KIND_BY_CONTENT_TYPE",
    "MS_PER_UNIT",
    "UNACCOUNTED",
    "UNREGISTERED_WAIT_SERIES",
    "WAIT_EVENT_TYPE",
    "WAIT_LABEL_SETS",
    "WAIT_PUBLISHER",
    "WAIT_SOURCES",
    "Elapsed",
    "UnpublishedSeries",
    "WaitSource",
    "WaitSourceUnavailableError",
    "document_kind",
    "measure_ms",
    "ms_to_unit",
    "observable_wait_kinds",
    "record_wait",
    "unpublished_wait_series",
    "wait_source",
]

#: The ``events.event_type`` value, in the short form the table already uses
#: for csat.v1 / nps.v1 (the pydantic ``schema_id`` keeps the long form).
WAIT_EVENT_TYPE = "wait.v1"


#: Milliseconds in one of the units files/08 §4 group G states. The catalogue
#: gives every wait id a unit and the observations are all milliseconds, so
#: every wait figure crosses one representation boundary on its way out — into
#: a Prometheus family named ``_h``, into an SDS-01 cell, into a console. One
#: table does that conversion for all of them (invariant 22: a number never
#: crosses a boundary unguarded), and a unit nobody catalogued raises rather
#: than falling through to milliseconds-as-seconds.
MS_PER_UNIT: Mapping[str, float] = {
    "s": 1_000.0,
    "min": 60_000.0,
    "h": 3_600_000.0,
}

#: The label sets a group G family may carry. files/08 §4 G states exactly one
#: label anywhere in the group — ``wait.records_processing_s`` "by document
#: type" — so a wait family is either unlabelled or labelled by document type.
#: A third shape is a data-inventory decision under invariant 18, not a
#: keyword argument, and the registry refuses one.
WAIT_LABEL_SETS: tuple[tuple[str, ...], ...] = ((), ("document_type",))

#: Catalogued ``wait.*`` ids deliberately outside :data:`WAIT_SOURCES`, each
#: with the reason it is outside. The point is that the reason is *written
#: down*: a catalogued series nothing writes is reported by
#: :func:`unpublished_wait_series` either way, and the difference between a
#: recorded decision and an oversight is this table.
UNREGISTERED_WAIT_SERIES: Mapping[str, str] = {
    "wait.answer_latency_s": (
        "files/08 §4 G calls this context for design and no acceptance names it; "
        "it stays catalogued as planned, with no source entry and no writer"
    ),
}


def ms_to_unit(duration_ms: float, unit: str) -> float:
    """A millisecond duration in one of the catalogued units.

    Raises ``KeyError`` for a unit the catalogue does not state, because the
    alternative — assuming seconds — publishes an hour-scaled figure into a
    series named ``_h`` and nobody finds out from the number itself.
    """
    return duration_ms / MS_PER_UNIT[unit]


class WaitSourceUnavailableError(RuntimeError):
    """A wait kind whose two instants this repo does not both record.

    Raised instead of writing, so that "we cannot measure this yet" can never
    be mistaken for "nobody has waited yet" — a zero and a gap mean opposite
    things to whoever reads the console.
    """


@dataclass(frozen=True)
class WaitSource:
    """One files/08 §4 group G interval and where its two ends come from."""

    kind: WaitKind
    #: The files/08 §4 group G id, verbatim.
    metric_id: str
    #: Its Prometheus form (dots to underscores), as catalogued.
    metric_name: str
    unit: str
    start_moment: str
    end_moment: str
    #: True only when BOTH instants are recorded somewhere in this repo today.
    observable: bool
    #: Which end of the interval this repo does not record. Required — and
    #: only meaningful — when the source is not observable.
    missing_instant: str = ""
    #: The backlog issue that would land the missing INSTANT, when one claims
    #: it. ``None`` is honest where no issue does; it is not a synonym for
    #: "unknown". Nothing to do with the publisher: a series can have a writer
    #: and still have nothing to write.
    blocked_by: str | None = None
    #: The label names this series' Prometheus family carries, one of
    #: :data:`WAIT_LABEL_SETS`. The writer dispatches on this, so it is the
    #: single statement of whether the family is labelled — held against the
    #: catalogue row's ``labels`` by test.
    labels: tuple[str, ...] = ()
    #: The dotted name of the code that writes this series into its family.
    #: Required unless :attr:`publisher_owed_by` names the issue that owes
    #: one: a catalogued series with neither is how a row ends up permanently
    #: empty, and an empty series reads as measured-and-zero.
    publisher: str | None = None
    #: The issue that owes a publisher, when there is none. Exactly one of
    #: this and :attr:`publisher` is set.
    publisher_owed_by: str | None = None

    def __post_init__(self) -> None:
        if self.observable and (self.missing_instant or self.blocked_by is not None):
            raise ValueError(f"{self.kind}: an observable source is missing nothing")
        if not self.observable and not self.missing_instant.strip():
            raise ValueError(
                f"{self.kind}: a source that cannot be measured must say which instant "
                'is absent — "blocked" is a status with an ask, not an excuse'
            )
        if self.unit not in MS_PER_UNIT:
            raise ValueError(
                f"{self.kind}: unit {self.unit!r} is not one files/08 §4 G states "
                f"({sorted(MS_PER_UNIT)}) — a wait figure has no way out of milliseconds"
            )
        if self.labels not in WAIT_LABEL_SETS:
            raise ValueError(
                f"{self.kind}: label set {self.labels!r} is not one of {WAIT_LABEL_SETS} — "
                "a new wait label is a data-inventory decision (inv. 18), not an argument"
            )
        if self.publisher and self.publisher_owed_by:
            raise ValueError(
                f"{self.kind}: names both a publisher and an issue owing one — "
                "one of them is wrong and the reader cannot tell which"
            )
        if not self.publisher and not self.publisher_owed_by:
            raise ValueError(
                f"{self.kind}: names neither its publisher nor the issue that owes one — "
                "a catalogued series nothing can write reads as measured-and-zero"
            )


#: The one entry point that writes a wait series into its Prometheus family.
#: INT-307 made it generic over the label set the source declares and over the
#: catalogued unit, so every group G id has a writer whether or not it carries
#: a label — what four of them still lack is an instant, which is a different
#: sentence and is said in ``missing_instant``.
WAIT_PUBLISHER = "intake_metrics.metrics.publish_wait"

#: files/08 §4 group G, in the order the section lists them, restricted to the
#: five ids INT-241's acceptance enumerates. ``wait.answer_latency_s`` is group
#: G's sixth id and is deliberately absent: the acceptance does not name it and
#: files/08 calls it "context for design", so it stays catalogued as planned
#: and unmeasured rather than being swept in here.
WAIT_SOURCES: tuple[WaitSource, ...] = (
    WaitSource(
        kind=WaitKind.TIME_TO_FIRST_QUESTION,
        metric_id="wait.time_to_first_question_s",
        metric_name="wait_time_to_first_question_s",
        unit="s",
        start_moment="sessions.started_at — when the voice/typed intake began",
        end_moment="the instant the first protocol question reaches the patient",
        observable=False,
        missing_instant=(
            "both: the Talker holds the turn in memory and writes no lifecycle row, "
            "and sessions.started_at has no writer outside the test harness"
        ),
        publisher=WAIT_PUBLISHER,
    ),
    WaitSource(
        kind=WaitKind.NOTE_READY_AFTER_WRAPUP,
        metric_id="wait.note_ready_after_wrapup_s",
        metric_name="wait_note_ready_after_wrapup_s",
        unit="s",
        start_moment="sessions.completed_at — the end of the intake",
        end_moment="notes.created_at — the note becoming readable",
        observable=False,
        missing_instant=(
            "the start: notes.created_at exists, but nothing transitions a session to "
            "COMPLETED, so sessions.completed_at is never written"
        ),
        publisher=WAIT_PUBLISHER,
    ),
    WaitSource(
        kind=WaitKind.DOCTOR_LINK_FIRST_OPEN,
        metric_id="wait.doctor_link_first_open_h",
        metric_name="wait_doctor_link_first_open_h",
        unit="h",
        start_moment="shares.created_at — the Doctor Link being sent",
        end_moment="the clinician's first open of that share",
        observable=False,
        missing_instant=(
            "the end: INT-150 landed the redemption route, and every open is written "
            "to the hash-chained audit log — which is EVIDENCE, not an analytics "
            "source, and is never mined for aggregates. No share-access row and no "
            "first_opened_at column exist. INT-307 built the unlabelled path this "
            "series needed, so the writer is no longer what is missing: landing a "
            "first-open instant on the share is, and no issue claims it"
        ),
        blocked_by=None,
        publisher=WAIT_PUBLISHER,
    ),
    WaitSource(
        kind=WaitKind.CHECKIN_TO_SEEN,
        metric_id="wait.checkin_to_seen_min",
        metric_name="wait_checkin_to_seen_min",
        unit="min",
        start_moment="the patient's check-in, signed into the payload's iat by the connector",
        end_moment="desk verification of that payload, when the connector admits the patient",
        observable=True,
        publisher=WAIT_PUBLISHER,
    ),
    WaitSource(
        kind=WaitKind.RECORDS_PROCESSING,
        metric_id="wait.records_processing_s",
        metric_name="wait_records_processing_s",
        unit="s",
        start_moment="the uploaded bytes arriving at the ingest handler",
        end_moment="the scan-and-promote pipeline returning a verdict",
        observable=True,
        labels=("document_type",),
        publisher=WAIT_PUBLISHER,
    ),
)

_BY_KIND: Mapping[WaitKind, WaitSource] = {source.kind: source for source in WAIT_SOURCES}


@dataclass(frozen=True)
class UnpublishedSeries:
    """A catalogued ``wait.*`` series nothing in this repo can write."""

    metric_id: str
    #: Why, in one sentence: the issue that owes a publisher, the recorded
    #: decision to leave the id out of the registry, or — the case that fails
    #: a build — that nobody has said anything at all.
    reason: str


#: The prefix :func:`unpublished_wait_series` reports for an id nobody has
#: accounted for. Grep-able on purpose: a test asserts no live catalogue entry
#: carries it.
UNACCOUNTED = "unaccounted: no source registry entry and no recorded reason"


def unpublished_wait_series(
    catalog: MetricsCatalog, *, sources: Sequence[WaitSource] = WAIT_SOURCES
) -> tuple[UnpublishedSeries, ...]:
    """Every catalogued ``wait.*`` id that no writer can reach, with the reason.

    Invariant 13 from its second side. The first side — nothing is emitted
    that the catalogue does not carry — is enforced by
    tests/observability/test_metrics_catalog.py. This is the other: a
    catalogue row whose series nothing writes is *reported by id*, because on
    a console an empty series and a measured zero render identically, and the
    reader has no way to tell "nobody waited" from "nobody can measure".
    """
    by_id = {source.metric_id: source for source in sources}
    reported: list[UnpublishedSeries] = []
    for metric in catalog.metrics:
        if not metric.spec_id.startswith("wait."):
            continue
        source = by_id.get(metric.spec_id)
        if source is not None and source.publisher:
            continue
        if source is not None:
            reason = f"no publisher; {source.publisher_owed_by} owes one"
        else:
            reason = UNREGISTERED_WAIT_SERIES.get(metric.spec_id, UNACCOUNTED)
        reported.append(UnpublishedSeries(metric_id=metric.spec_id, reason=reason))
    return tuple(sorted(reported, key=lambda entry: entry.metric_id))


def wait_source(kind: WaitKind) -> WaitSource:
    return _BY_KIND[kind]


def observable_wait_kinds() -> tuple[WaitKind, ...]:
    return tuple(source.kind for source in WAIT_SOURCES if source.observable)


#: files/08 §4 G asks for records processing "by document type". The domain is
#: the ingest allow-list this repo already enforces, renamed to a label value;
#: a clinical document taxonomy is not invented here. The map is held total
#: against ALLOWED_CONTENT_TYPES by test, so a newly allowed type fails the
#: build rather than silently landing in an unlabelled bucket.
DOCUMENT_KIND_BY_CONTENT_TYPE: Mapping[str, DocumentKind] = {
    "application/pdf": DocumentKind.PDF,
    "image/jpeg": DocumentKind.JPEG,
    "image/png": DocumentKind.PNG,
}


def document_kind(content_type: str) -> DocumentKind:
    """The label value for an allow-listed content type.

    Raises ``KeyError`` for anything else: an ingest that got past
    ALLOWED_CONTENT_TYPES with an unmapped type is a defect, and a catch-all
    "other" bucket would hide it.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise KeyError(content_type)
    return DOCUMENT_KIND_BY_CONTENT_TYPE[content_type]


@dataclass
class Elapsed:
    """Filled in when :func:`measure_ms` exits."""

    duration_ms: int = field(default=0)


@contextmanager
def measure_ms() -> Iterator[Elapsed]:
    """Time a block on the monotonic clock.

    Monotonic rather than wall-clock on purpose: an NTP step during a slow
    scan would otherwise produce a negative or absurd duration, and the schema
    would reject it at the worst moment.
    """
    elapsed = Elapsed()
    started = time.monotonic_ns()
    try:
        yield elapsed
    finally:
        elapsed.duration_ms = (time.monotonic_ns() - started) // 1_000_000


class _Adder(Protocol):
    """The one thing :func:`record_wait` needs from a session, so the
    fail-closed path can be proven without a database."""

    def add(self, instance: object, _warn: bool = ..., /) -> None: ...


async def record_wait(
    session: _Adder,
    *,
    tenant_id: uuid.UUID,
    kind: WaitKind,
    duration_ms: int,
    session_id: uuid.UUID | None = None,
    document_type: DocumentKind | None = None,
) -> None:
    """Append one completed wait interval to the append-only event log.

    The source registry is consulted **before** anything is written, so an
    unobservable kind cannot leave a row behind on its way to raising.

    ``session_id`` links the observation to the intake it came from. That link
    is what makes the patient's ``learning:service_improvement`` refusal
    honourable at rollup time (files/06 §2 — the de-identified-aggregate
    purpose, whose refusal must cost no feature); it never travels into a
    rollup, an export or a metric label.
    """
    source = wait_source(kind)
    if not source.observable:
        raise WaitSourceUnavailableError(
            f"{kind.value}: {source.missing_instant}"
            + (f" (blocked by {source.blocked_by})" if source.blocked_by else "")
        )
    event = WaitV1(
        tenant_id=tenant_id,
        kind=kind,
        duration_ms=duration_ms,
        document_type=document_type,
    )
    session.add(
        Event(
            tenant_id=tenant_id,
            session_id=session_id,
            event_type=WAIT_EVENT_TYPE,
            payload=event.model_dump(mode="json"),
        )
    )
