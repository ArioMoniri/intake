"""Deterministic doubles for the lane-framework suite (INT-110).

Everything a lane touches is a typed, read-only surface
(:mod:`intake_voice_runtime.observers`), so the doubles here are small: a
consent probe, two observers, and a frame generator. No double dials a
network, loads a model or opens a file — CLAUDE.md invariant 17 puts mocks in
tests and nowhere else.

**Why the Talker doubles are loaded by path.** The "lanes stalled 30 s → turn
latency unchanged" proof runs a *real* ``TalkerSession`` turn, and it has to
run on the *same* virtual clock as the turn it measures — so it needs INT-091's
``tests/voice/talker_harness.py`` rather than a second copy of it, which would
prove the property about a copy of the Talker instead of about the Talker.

It is loaded with an explicit ``spec_from_file_location`` under its own module
name, and this file deliberately does **not** put ``tests/voice`` on
``sys.path``. Two files in ``tests/voice`` do ``from conftest import …``, and
``tests/research`` does the same; a directory inserted into ``sys.path`` — or a
second top-level ``conftest`` module in this package — changes which
``conftest`` those resolve to, and makes a passing suite depend on the order
the directories were named on the command line. Loading one file by its path
has no such reach.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Coroutine
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

from clinical_schemas.observers import Lane
from intake_voice_runtime.observers import (
    ConsentReading,
    Frame,
    LaneBudget,
    LaneContext,
    LaneObservation,
    LaneSpec,
)

__all__ = [
    "FakeClock",
    "GrantingConsentProbe",
    "RecordingObserver",
    "SlowObserver",
    "VirtualClock",
    "build_session",
    "frames",
    "lane_spec",
    "scripted_step",
]


def _load_talker_harness() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "voice" / "talker_harness.py"
    spec = importlib.util.spec_from_file_location("intake_lanes_talker_harness", path)
    if spec is None or spec.loader is None:  # pragma: no cover - a missing file is a hard stop
        raise ImportError(f"INT-091's Talker doubles are not where INT-110 expects them: {path}")
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: ``@dataclass`` resolves its own module out of
    # ``sys.modules`` while the class body runs, and a module that is not there
    # yet makes the decorator fail on an unrelated-looking AttributeError.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_TALKER = _load_talker_harness()

#: INT-091's virtual clock: ``sleep`` parks, ``run`` advances only when every
#: task is parked. A backend stalled 10 s and one stalled 3 h therefore produce
#: the same virtual turn latency — and so must a lane stalled 30 s.
FakeClock: Any = _TALKER.FakeClock
build_session: Any = _TALKER.build_session
scripted_step: Any = _TALKER.scripted_step


class VirtualClock(Protocol):
    """What the lane doubles need of the clock they were handed."""

    def now_ms(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...

    def run(self, main: Coroutine[Any, Any, Any]) -> Any: ...


@dataclass
class GrantingConsentProbe:
    """Grants exactly the scopes it was given, at a stated version.

    Synchronous by construction: the probe is read on the frame-offer path,
    which is the speech path's own thread of control, so an awaitable member
    here would be a way for a lane consent check to delay speech.
    """

    granted_scopes: dict[str, str] = field(default_factory=dict)
    reads: list[str] = field(default_factory=list)

    def granted(self, scope: str) -> ConsentReading | None:
        self.reads.append(scope)
        version = self.granted_scopes.get(scope)
        if version is None:
            return None
        return ConsentReading(scope=scope, version=version)


@dataclass
class RecordingObserver:
    """A read-only lane that records the contexts it was handed."""

    lane_id: Lane
    contexts: list[LaneContext] = field(default_factory=list)
    observation: LaneObservation = field(default_factory=lambda: LaneObservation(confidence=1.0))

    @property
    def lane(self) -> Lane:
        return self.lane_id

    async def observe(self, context: LaneContext) -> LaneObservation:
        self.contexts.append(context)
        return self.observation.model_copy(
            update={"dropped_frames_in_window": context.dropped_frames_in_window}
        )


@dataclass
class SlowObserver:
    """A lane that takes ``stall_s`` of virtual time to answer.

    This is the shape invariant 11's fake-clock test needs: a lane that is
    genuinely stalled, not one that merely returns late.
    """

    lane_id: Lane
    clock: VirtualClock
    stall_s: float = 30.0
    started: int = 0
    finished: int = 0

    @property
    def lane(self) -> Lane:
        return self.lane_id

    async def observe(self, context: LaneContext) -> LaneObservation:
        del context
        self.started += 1
        await self.clock.sleep(self.stall_s)
        self.finished += 1
        return LaneObservation(confidence=1.0)


def lane_spec(
    lane: Lane,
    *,
    window_ms: float = 20.0,
    max_queued_frames: int = 4,
    deadline_ms: float = 200.0,
) -> LaneSpec:
    """One lane's manifest, with the invariant-29 intended purpose supplied.

    The string is the test's own — a lane's real ``intended_purpose`` is
    reviewed regulatory text that ships with the lane (INT-111 ff.), and the
    framework's job is only to make its absence unrepresentable.
    """
    return LaneSpec(
        lane=lane,
        intended_purpose=f"test double for the {lane.value} lane",
        budget=LaneBudget(
            window_ms=window_ms,
            max_queued_frames=max_queued_frames,
            deadline_ms=deadline_ms,
            sampling_rate_hz=50.0,
        ),
    )


def frames(count: int, *, duration_ms: float = 10.0, start_seq: int = 0) -> list[Frame]:
    """``count`` decoded frames already in the session, each carrying bytes."""
    return [
        Frame(
            seq=start_seq + i,
            t_monotonic_ms=(start_seq + i) * duration_ms,
            duration_ms=duration_ms,
            samples=bytearray(b"\x01\x02\x03\x04"),
        )
        for i in range(count)
    ]
