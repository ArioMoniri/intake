"""Recorded-fixture doubles for the simulator's mock-voice lane (INT-082).

Everything the Talker talks to is a typed port
(:mod:`intake_voice_runtime.ports`); the doubles below are the recorded side
of that boundary and they live here — in tests — because CLAUDE.md invariant
17 puts mocks nowhere else. No double dials a network, loads a model, starts
a LiveKit room, or opens a file.

Two of them exist to make an invariant *measurable* rather than asserted:

- :class:`RecordingSink` keeps a length and a label, never the frames. The
  simulator asserts afterwards that neither the session nor any double holds
  a bytes-like attribute (CLAUDE.md invariant 3 — audio must not be
  *reachable*, not merely not written).
- :func:`record_disk_writes` wraps ``builtins.open``, ``io.open`` and
  ``os.open`` for the duration of a run and records every write-mode call. Invariant 3 says raw
  audio is never written to disk; the honest way to test that of a run is to
  watch the syscall surface a Python process can write through, not to trust
  that no code path exists.

:class:`RecordedBackend` is the Layer-B stand-in. ``submit`` is an ordinary
function returning a ticket immediately and ``drain_results`` never blocks —
ADR-009's *"the Talker never awaits Backend Work"* is structural in the port,
and the simulator records that it never awaited one.
"""

from __future__ import annotations

import builtins
import io
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from intake_voice_runtime.ports import (
    PatientMemoryKey,
    PatientRecord,
    WorkRequest,
    WorkState,
    WorkTicket,
    work_key,
)

__all__ = [
    "SIM_VOICE_ID",
    "InMemoryPatientMemory",
    "RecordedBackend",
    "RecordedClipStore",
    "RecordingSink",
    "RecordingSynthesizer",
    "StepClock",
    "record_disk_writes",
    "retained_byte_fields",
]

SIM_VOICE_ID = "residency-tr-sentetik"
"""The one production voice profile's synthetic voice id (invariant 19)."""

_WRITE_MODES = frozenset("wxa+")


class StepClock:
    """A deterministic clock: one millisecond per read, no wall clock.

    The simulator asserts state, not latency — the fake-clock latency harness
    is ``make runtime-sim`` — so the only property needed here is that time
    moves forward reproducibly.
    """

    def __init__(self) -> None:
        self._ms = 0.0

    def now_ms(self) -> float:
        self._ms += 1.0
        return self._ms

    async def sleep(self, seconds: float) -> None:
        self._ms += max(seconds, 0.0) * 1000.0


@dataclass
class RecordedBackend:
    """Layer B, seen from Layer A. No member of this port is awaitable."""

    submitted: list[WorkRequest] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    def submit(self, request: WorkRequest) -> WorkTicket:
        self.submitted.append(request)
        return WorkTicket(work_id=work_key(request), state=WorkState.QUEUED)

    def cancel(self, work_id: str, reason: str) -> WorkTicket:
        self.cancelled.append(work_id)
        return WorkTicket(work_id=work_id, state=WorkState.CANCELLED)

    def drain_results(self) -> tuple[object, ...]:
        return ()


@dataclass
class RecordedClipStore:
    """The clip cache stand-in. Clips are synthetic *agent* speech, never
    patient audio (files/03 §4.6 invariant 9)."""

    served: list[str] = field(default_factory=list)

    def fetch(self, clip_id: str) -> bytes:
        self.served.append(clip_id)
        return clip_id.encode("utf-8")[:32]


@dataclass
class RecordingSynthesizer:
    """The TTS gateway stand-in: records the text, returns opaque frames."""

    requests: list[str] = field(default_factory=list)

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        self.requests.append(text_tr)
        return f"{voice_id}:{len(text_tr)}".encode()[:32]


@dataclass
class RecordingSink:
    """Where agent speech goes. Keeps a label and a length — never frames."""

    played: list[tuple[str, int]] = field(default_factory=list)
    cancels: int = 0

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.played.append((label, len(frames)))

    async def cancel(self) -> None:
        self.cancels += 1


@dataclass
class InMemoryPatientMemory:
    """Bounded, non-clinical patient memory (files/03 §4.2 closed key set)."""

    store: dict[str, str] = field(default_factory=dict)

    def recall(self, key: str) -> PatientRecord | None:
        value = self.store.get(key)
        return None if value is None else PatientRecord(key=PatientMemoryKey(key), value=value)

    def remember(self, key: str, value: str) -> PatientRecord:
        self.store[key] = value
        return PatientRecord(key=PatientMemoryKey(key), value=value)

    def forget(self, key: str) -> None:
        self.store.pop(key, None)


def retained_byte_fields(*objects: object) -> int:
    """How many bytes-like attributes these objects still hold.

    Zero by construction for every double above; counted rather than asserted
    so a future field that *did* retain audio would be caught (invariant 3).
    """
    total = 0
    for obj in objects:
        state = getattr(obj, "__dict__", None)
        if state is None:
            continue
        total += sum(1 for value in state.values() if isinstance(value, bytes | bytearray))
    return total


@contextmanager
def record_disk_writes() -> Iterator[list[str]]:
    """Record every write-mode file open made inside the block.

    Three entry points are wrapped, because a write can reach the filesystem
    through any of them: ``builtins.open`` (what application code calls),
    ``io.open`` (what ``pathlib`` calls, and it is a *separate* module
    attribute even though it is the same function object), and ``os.open``
    (the descriptor-level route). Calls are *recorded*, not refused —
    refusing would break the harness that reads the recording.
    """
    writes: list[str] = []
    real_open = builtins.open
    real_io_open = io.open
    real_os_open = os.open

    def watched_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if _WRITE_MODES & set(mode):
            writes.append(f"open:{file}:{mode}")
        return real_io_open(file, mode, *args, **kwargs)

    def watched_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND):
            writes.append(f"os.open:{path}:{flags}")
        return real_os_open(path, flags, *args, **kwargs)

    builtins.open = watched_open
    io.open = watched_open
    os.open = watched_os_open
    try:
        yield writes
    finally:
        builtins.open = real_open
        io.open = real_io_open
        os.open = real_os_open
