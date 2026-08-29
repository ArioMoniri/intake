"""The Talker's typed ports (ADR-006; CLAUDE.md §How we work).

Everything Layer A touches that is not Layer A is a Protocol here, so a model
or profile swap is a config change proven by contract tests rather than an
edit at every call site. Three of these ports have no production
implementation on this branch and are wired fail-closed by
:mod:`intake_voice_runtime.app`:

- :class:`ClipStore` — the clip byte store is ``packages/voice-clips``
  (INT-060), which is not on ``main``;
- :class:`SpeechSynthesizer` — the self-hosted streaming TTS adapter is
  INT-095 (files/03 §4.9.1 rows 10–12);
- the room-token HTTP route the worker needs to join its session room —
  ``intake_platform.room_tokens`` mints the JWT (INT-090) but no route serves
  it (INT-103's finding).

The single most load-bearing line in this module is that
:class:`WorkSubmitter` has **no awaitable member**. ADR-009 says the Talker
"never awaits Backend Work"; making every member of the port an ordinary
function is how that becomes structural rather than a rule someone remembers.
``tests/voice/test_talker_never_awaits.py`` asserts it by introspection, and
the fake-clock latency test asserts the consequence.
"""

from __future__ import annotations

import enum
import hashlib
import time
from collections.abc import Awaitable
from typing import Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.steps import Step

__all__ = [
    "AudioSink",
    "Clock",
    "ClipStore",
    "EngineSnapshot",
    "EngineSnapshotSource",
    "PatientMemoryKey",
    "PatientMemoryStore",
    "PatientRecord",
    "RoomTokenSource",
    "SpeechSynthesizer",
    "SystemClock",
    "WorkRequest",
    "WorkState",
    "WorkSubmitter",
    "WorkTicket",
    "WorkType",
    "work_key",
]


# --- time ---------------------------------------------------------------------------


@runtime_checkable
class Clock(Protocol):
    """Injectable time, so a turn budget is measured rather than believed."""

    def now_ms(self) -> float: ...

    def sleep(self, seconds: float) -> Awaitable[None]: ...


class SystemClock:
    """The real clock. ``perf_counter`` because turn budgets are durations."""

    def now_ms(self) -> float:
        return time.perf_counter() * 1000.0

    def sleep(self, seconds: float) -> Awaitable[None]:
        import asyncio

        return asyncio.sleep(seconds)


# --- Layer B: the read side ------------------------------------------------------------


class EngineSnapshot(FrozenModel):
    """The immutable snapshot the engine publishes after every commit.

    files/12 §7.2: ``protocol_next`` was a Layer-B read that could neither
    take the Layer-B lock (blocking the Talker, violating invariant 1) nor
    read outside it (torn state). The engine publishes this instead, and
    ``protocol_next`` is a lock-free atomic attribute read of it.
    """

    version: int = Field(ge=0, description="Monotonic commit counter.")
    next_step: Step | None = Field(default=None, description="What to ask next, if anything.")
    awaiting: tuple[str, ...] = Field(
        default=(), description="Steps asked and not yet reconciled (ask-ahead)."
    )
    invalidated: tuple[str, ...] = Field(
        default=(),
        description="Steps a skip_if has invalidated; an answer may not bind to one, "
        "and its transcript survives as unbound narrative (files/12 §9 inv. 13).",
    )


@runtime_checkable
class EngineSnapshotSource(Protocol):
    """Publishes :class:`EngineSnapshot`. Reading it takes no lock."""

    @property
    def snapshot(self) -> EngineSnapshot: ...


# --- Layer B: the work side --------------------------------------------------------------


class WorkType(enum.StrEnum):
    """The Work the Talker may submit.

    files/12 §7.3 deletes ``EVALUATE_TRIAGE`` from the registry entirely —
    triage runs synchronously inside ``apply_extraction`` — so there is no
    member for it here either. The Talker submits transcripts and document
    reads; it cannot ask for a triage, a note or a share (files/03 §4.2).
    """

    EXTRACT_SLOTS = "extract_slots"
    PLAN_FOLLOW_UPS = "plan_follow_ups"
    PARSE_DOCUMENT = "parse_document"


class WorkState(enum.StrEnum):
    """files/03 §4.3: queued → running → completed | failed | cancelled."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkRequest(FrozenModel):
    """One unit of Backend Work, addressed by content (files/12 §7.5)."""

    session_id: str = Field(min_length=1)
    work_type: WorkType
    step_id: str = Field(min_length=1)
    input_hash: str = Field(min_length=1, description="sha256 of the transcript or payload.")
    protocol_hash: str = Field(min_length=1, description="The session's pinned protocol hash.")
    engine_version: int = Field(ge=0, description="files/12 §7.2 — carried back to Layer B.")


class WorkTicket(FrozenModel):
    """What ``submit_utterance`` returns — immediately, always."""

    work_id: str = Field(min_length=1)
    state: WorkState


def work_key(request: WorkRequest) -> str:
    """``sha256(session_id, work_type, step_id, input_hash, protocol_hash)``.

    files/12 §7.5: the id is *derived*, not minted, so a restart re-submitting
    the same transcript produces the same ``work_id`` and the existing dedupe
    starts working instead of guaranteeing a duplicate on every restart.
    """
    digest = hashlib.sha256(
        "\x00".join(
            (
                request.session_id,
                request.work_type.value,
                request.step_id,
                request.input_hash,
                request.protocol_hash,
            )
        ).encode("utf-8")
    ).hexdigest()
    return f"w_{digest[:32]}"


@runtime_checkable
class WorkSubmitter(Protocol):
    """Layer B, seen from Layer A. **No member of this port is awaitable.**

    ADR-009: ``submit_utterance`` returns a ``work_id`` immediately. Results
    arrive by polling :meth:`drain_results`, which returns whatever is ready
    and never blocks — so there is no expression the Talker could write that
    would wait on Backend Work.
    """

    def submit(self, request: WorkRequest) -> WorkTicket: ...

    def cancel(self, work_id: str, reason: str) -> WorkTicket: ...

    def drain_results(self) -> tuple[object, ...]: ...


# --- speech egress -------------------------------------------------------------------------


@runtime_checkable
class ClipStore(Protocol):
    """Fetch one pre-synthesised clip's frames by id.

    The production implementation is ``packages/voice-clips`` (INT-060, MinIO,
    keyed ``sha256(text_tr, voice_id)``), which is not on this branch — see the
    module docstring. Clips are **synthetic agent speech**, never patient
    audio (files/03 §4.6 invariant 9).
    """

    def fetch(self, clip_id: str) -> bytes: ...


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """The TTS gateway (ADR-006). Never handed a numeral (invariant 22)."""

    def synthesize(self, text_tr: str, voice_id: str) -> bytes: ...


@runtime_checkable
class AudioSink(Protocol):
    """Where agent speech goes. Outbound only — the Talker holds no inbound
    frames at all, which is why invariant 3 has nothing to reach here."""

    def play(self, frames: bytes, *, label: str = "") -> Awaitable[None]: ...

    def cancel(self) -> Awaitable[None]: ...


class RoomTokenSource(Protocol):
    """Mints the worker's join token for one session room (INT-090)."""

    def __call__(self, session_id: str) -> str: ...


# --- patient memory ---------------------------------------------------------------------------


class PatientMemoryKey(enum.StrEnum):
    """The closed key set files/03 §4.2 names: *"name, form of address
    (siz/sen), pace, language — nothing clinical"*. A key outside this enum is
    refused, which is what keeps ``patient_memory`` from becoming a slot
    editor by the back door."""

    DISPLAY_NAME = "display_name"
    FORM_OF_ADDRESS = "form_of_address"
    PACE = "pace"
    LANGUAGE = "language"


class PatientRecord(FrozenModel):
    """The bounded record ``patient_memory`` returns."""

    key: PatientMemoryKey
    value: str = Field(min_length=1, max_length=64)


@runtime_checkable
class PatientMemoryStore(Protocol):
    def recall(self, key: str) -> PatientRecord | None: ...

    def remember(self, key: str, value: str) -> PatientRecord: ...

    def forget(self, key: str) -> None: ...
