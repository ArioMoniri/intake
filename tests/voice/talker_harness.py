"""Deterministic doubles for the Talker suite (INT-091).

Everything the Talker talks to is a typed port (``voice_runtime.ports``); the
doubles below are the recorded-fixture side of that boundary, and they live
here — in tests — because CLAUDE.md invariant 17 puts mocks nowhere else. No
double dials a network, loads a model, or starts a LiveKit room.

The one non-obvious piece is :class:`FakeClock`: a virtual-time clock with a
driver that only advances the clock when every task is parked. That is what
makes "the Talker never awaits Backend Work" measurable rather than asserted
— a backend stalled for ten seconds and one stalled for three hours produce
the *same* virtual turn latency, because the Talker's own waiters always come
due first and the driver stops the moment the turn is finished.
"""

from __future__ import annotations

import asyncio
import heapq
import itertools
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any

from intake_voice_runtime.ports import (
    EngineSnapshot,
    PatientRecord,
    WorkRequest,
    WorkState,
    WorkTicket,
    work_key,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import Step, StepKind
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.insertion import YELLOW_DEADLINES, DeliveryDeadlines
from intake_voice_runtime.talker.preemption import BackendResult
from intake_voice_runtime.talker.session import TalkerConfig, TalkerSession

# --- virtual time ------------------------------------------------------------------

#: How many event-loop turns the driver drains before it declares every task
#: parked. Ready callbacks are scheduled one loop-turn apart, so a handful of
#: yields is enough for any chain the Talker builds; the number is a constant
#: rather than a heuristic so the harness stays deterministic.
_DRAIN_TURNS = 16


class FakeClock:
    """Virtual monotonic time. ``sleep`` parks; :meth:`run` advances."""

    def __init__(self) -> None:
        self._now_s = 0.0
        self._seq = itertools.count()
        self._waiters: list[tuple[float, int, asyncio.Future[None]]] = []

    def now_ms(self) -> float:
        return self._now_s * 1000.0

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        heapq.heappush(self._waiters, (self._now_s + seconds, next(self._seq), future))
        await future

    def run(self, main: Coroutine[Any, Any, Any]) -> Any:
        """Drive ``main`` to completion in virtual time, in zero wall time."""

        async def driver() -> Any:
            task = asyncio.ensure_future(main)
            while not task.done():
                for _ in range(_DRAIN_TURNS):
                    if task.done():
                        break
                    await asyncio.sleep(0)
                if task.done() or not self._waiters:
                    break
                when, _, future = heapq.heappop(self._waiters)
                self._now_s = max(self._now_s, when)
                if not future.done():
                    future.set_result(None)
            if not task.done():
                task.cancel()
            return await task

        return asyncio.run(driver())


# --- engine (Layer B read side) ----------------------------------------------------


class FakeEngine:
    """Publishes an immutable snapshot; ``protocol_next`` reads it lock-free."""

    def __init__(self, steps: list[Step]) -> None:
        self._steps = list(steps)
        self._version = 1
        self.snapshot_reads = 0

    @property
    def snapshot(self) -> EngineSnapshot:
        self.snapshot_reads += 1
        return EngineSnapshot(
            version=self._version,
            next_step=self._steps[0] if self._steps else None,
            awaiting=(),
            invalidated=(),
        )

    def advance(self) -> None:
        if self._steps:
            self._steps.pop(0)
        self._version += 1

    def invalidate(self, step_id: str) -> None:
        self._version += 1
        self._invalidated = (step_id,)


# --- backend (Layer B work side) ---------------------------------------------------


@dataclass
class StalledBackend:
    """A Backend Agent that takes ``stall_s`` of virtual time to answer.

    ``submit`` is synchronous and returns a ticket immediately — the port has
    no awaitable member, which is the structural half of invariant 9. The
    ``work`` coroutine is what a real Layer B would be doing meanwhile; the
    Talker never awaits it.
    """

    clock: FakeClock
    stall_s: float = 10.0
    results: list[BackendResult] = field(default_factory=list)
    submitted: list[WorkRequest] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    _ready: list[BackendResult] = field(default_factory=list)

    def submit(self, request: WorkRequest) -> WorkTicket:
        self.submitted.append(request)
        return WorkTicket(work_id=work_key(request), state=WorkState.QUEUED)

    def cancel(self, work_id: str, reason: str) -> WorkTicket:
        self.cancelled.append(work_id)
        return WorkTicket(work_id=work_id, state=WorkState.CANCELLED)

    def drain_results(self) -> tuple[BackendResult, ...]:
        drained = tuple(self._ready)
        self._ready.clear()
        return drained

    async def work(self) -> None:
        """The stall. Nothing in the Talker awaits this coroutine."""
        await self.clock.sleep(self.stall_s)
        self._ready.extend(self.results)


# --- speech egress -----------------------------------------------------------------


@dataclass
class RecordingSink:
    """Collects agent speech in memory. Nothing here has a write path."""

    clock: FakeClock
    played: list[tuple[str, int]] = field(default_factory=list)
    cancels: int = 0
    #: virtual milliseconds of playback charged per byte of agent speech
    ms_per_byte: float = 1.0

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.played.append((label, len(frames)))
        await self.clock.sleep(len(frames) * self.ms_per_byte / 1000.0)

    async def cancel(self) -> None:
        self.cancels += 1


@dataclass
class RecordedClipStore:
    """The clip cache stand-in: deterministic synthetic agent speech."""

    served: list[str] = field(default_factory=list)

    def fetch(self, clip_id: str) -> bytes:
        self.served.append(clip_id)
        return clip_id.encode("utf-8")[:32]


@dataclass
class RecordingSynthesizer:
    """The TTS gateway stand-in: records what it was asked to speak."""

    requests: list[str] = field(default_factory=list)

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        self.requests.append(text_tr)
        return f"{voice_id}:{text_tr}".encode()[:32]


@dataclass
class InMemoryPatientMemory:
    """Bounded, non-clinical patient memory."""

    store: dict[str, str] = field(default_factory=dict)

    def recall(self, key: str) -> PatientRecord | None:
        value = self.store.get(key)
        return None if value is None else PatientRecord(key=key, value=value)

    def remember(self, key: str, value: str) -> PatientRecord:
        self.store[key] = value
        return PatientRecord(key=key, value=value)

    def forget(self, key: str) -> None:
        self.store.pop(key, None)


# --- convenience -------------------------------------------------------------------

#: The one production voice profile's dev voice id (invariant 19).
VOICE_ID = "residency-tr-01"


def scripted_step(step_id: str = "s1", text_tr: str = "Nereniz ağrıyor?") -> Step:
    return Step(step_id=step_id, kind=StepKind.SCRIPTED, text_tr=text_tr)


def build_session(
    clock: FakeClock,
    *,
    steps: list[Step],
    backend: StalledBackend | None = None,
    catalogue: ClipCatalogue | None = None,
    clip_store: RecordedClipStore | None = None,
    synthesizer: RecordingSynthesizer | None = None,
    sink: RecordingSink | None = None,
    memory: InMemoryPatientMemory | None = None,
    rule_ids: frozenset[str] = frozenset(),
) -> TalkerSession:
    """One fully wired Talker over doubles — the shape services/voice-runtime
    will be given by its LiveKit Agents entrypoint once INT-095 lands."""
    return TalkerSession(
        config=TalkerConfig(
            session_id="11111111-2222-4333-8444-555555555555",
            voice_id=VOICE_ID,
            profile=VoiceProfile.RESIDENCY_TR,
            protocol_hash="a" * 64,
            rule_ids=rule_ids,
            deadlines=DeliveryDeadlines(triage_yellow=YELLOW_DEADLINES),
        ),
        engine=FakeEngine(steps),
        backend=backend or StalledBackend(clock=clock, stall_s=10.0),
        catalogue=catalogue or ClipCatalogue.empty(VOICE_ID),
        clip_store=clip_store or RecordedClipStore(),
        synthesizer=synthesizer or RecordingSynthesizer(),
        sink=sink or RecordingSink(clock=clock),
        memory=memory or InMemoryPatientMemory(),
        clock=clock,
    )
