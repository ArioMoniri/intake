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

Two of the four gaps have an owning issue (INT-150 for the Doctor Link open,
INT-163 for connector check-in). Two do not: no issue in the backlog claims
the intake lifecycle instants — `sessions.started_at`, the first question
reaching the patient, `sessions.completed_at` — so `blocked_by` is honestly
`None` there and the ask is recorded in docs/evidence/INT-241.md rather than
attributed to an issue that never promised it.

Today exactly one interval has both instants: document processing begins and
ends inside a single request handler (`intake_api.documents.ingest_content`).
The other four are named, gated and empty — build the mechanism, wire the
gate, make it fail closed, leave the content empty (CLAUDE.md).

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
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Protocol

from clinical_schemas.events import DocumentKind, WaitKind, WaitV1

from intake_platform.db.models import Event
from intake_platform.documents import ALLOWED_CONTENT_TYPES

__all__ = [
    "DOCUMENT_KIND_BY_CONTENT_TYPE",
    "WAIT_EVENT_TYPE",
    "WAIT_SOURCES",
    "Elapsed",
    "WaitSource",
    "WaitSourceUnavailableError",
    "document_kind",
    "measure_ms",
    "observable_wait_kinds",
    "record_wait",
    "wait_source",
]

#: The ``events.event_type`` value, in the short form the table already uses
#: for csat.v1 / nps.v1 (the pydantic ``schema_id`` keeps the long form).
WAIT_EVENT_TYPE = "wait.v1"


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
    #: The backlog issue that would land it, when one claims it. ``None`` is
    #: honest where no issue does; it is not a synonym for "unknown".
    blocked_by: str | None = None

    def __post_init__(self) -> None:
        if self.observable and (self.missing_instant or self.blocked_by is not None):
            raise ValueError(f"{self.kind}: an observable source is missing nothing")
        if not self.observable and not self.missing_instant.strip():
            raise ValueError(
                f"{self.kind}: a source that cannot be measured must say which instant "
                'is absent — "blocked" is a status with an ask, not an excuse'
            )


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
            "the end: there is no clinician-facing share-redemption route and no "
            "share-access row, so nothing records an open"
        ),
        blocked_by="INT-150",
    ),
    WaitSource(
        kind=WaitKind.CHECKIN_TO_SEEN,
        metric_id="wait.checkin_to_seen_min",
        metric_name="wait_checkin_to_seen_min",
        unit="min",
        start_moment="desk check-in recorded by the hospital connector",
        end_moment="the encounter starting, as the connector reports it",
        observable=False,
        missing_instant=(
            "both: files/08 §4 G scopes this to connector tenants and "
            "packages/connectors does not exist"
        ),
        blocked_by="INT-163",
    ),
    WaitSource(
        kind=WaitKind.RECORDS_PROCESSING,
        metric_id="wait.records_processing_s",
        metric_name="wait_records_processing_s",
        unit="s",
        start_moment="the uploaded bytes arriving at the ingest handler",
        end_moment="the scan-and-promote pipeline returning a verdict",
        observable=True,
    ),
)

_BY_KIND: Mapping[WaitKind, WaitSource] = {source.kind: source for source in WAIT_SOURCES}


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
