"""The lane runtime: budgets, backpressure, and a hard wall against the speech path.

CLAUDE.md invariant 11's third clause is a latency property, so it is answered
with a shape rather than a promise. The audio path calls :meth:`LaneRuntime.offer`,
which is an **ordinary function** — it appends to a bounded ring and returns.
The lanes' own work happens in :meth:`LaneRuntime.pump`, a coroutine the
Backend worker drives, exactly as INT-092's ``run_pending`` drives the Work
queue. Because ``offer`` has nothing to await, a lane stalled for thirty
seconds cannot lengthen a turn: it is the ``WorkSubmitter``-has-no-awaitable
proof of invariant 9, reused one layer out and measured the same way, on the
virtual clock.

**Backpressure is a drop, never a wait** (files/03 §4.7.6: *"sampling rates
adapt to load, and ``lane.dropped_frames`` is a tracked metric"*; §4.5b's T2
lets the lanes stop consuming frames altogether under a poor network). Each
lane's ring holds :attr:`LaneBudget.capacity` frames; frame ``capacity + 1``
evicts and **zeroes** the oldest, counts the drop on ``lane.dropped_frames``,
and keeps the newest window — which is the contiguous one, and the one a
real-time lane wants. The count travels with the window as
``dropped_frames_in_window``, because files/03 §4.8 records non-determinism
rather than eliminating it: replaying a degraded session must reproduce the
*degraded* decision.

**Nothing derived from audio outlives the window** (invariant 3; files/06 §3:
lane windows are *"memory-only, zeroed after scoring and on gate rejection,
lane disable, consent withdrawal, session end and signal shutdown"*). The ring
owns ``bytearray`` frames and hands the objects themselves to the window, so
zeroization reaches the only bytes that exist — after every observation, on
every eviction, on withdrawal and on close. Page-locking those pages is a
platform control (files/10 §9.1 invariants 17 and 28, node and container
checks) and is not re-implemented here.

**A refused lane is absent, not idle.** Admission builds a ring, a spec and an
aggregate for the lanes consent (or, for ``acoustic``, a registered
investigation) permits — and for no others. ``depth`` and ``dropped`` raise for
a lane that was never admitted, because answering ``0`` would describe an idle
lane, and there is no lane.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from typing import Protocol

from clinical_schemas.observers import InteractionState, Lane
from intake_platform.consent import ConsentDecision

from intake_voice_runtime.metrics import LANE_DROPPED_FRAMES
from intake_voice_runtime.observers.consent import (
    LANE_CONSENT_SCOPE,
    LaneConsentUndeclared,
    consented_lanes,
)
from intake_voice_runtime.observers.contract import (
    LaneBudget,
    LaneContext,
    LaneObservation,
    LaneSpec,
    LaneWindow,
    ObserverLane,
)
from intake_voice_runtime.observers.state import ObserverStore
from intake_voice_runtime.observers.study import AcousticAdmission

__all__ = ["LANE_DROPPED_FRAMES", "LaneRuntime", "LaneSink", "SealedResearchStore"]

#: Where one lane's observations go. Chosen once, at admission, from the
#: lane's declared :class:`ObserverField` — never re-decided per observation,
#: because a destination picked at delivery time would be a place where an
#: ``acoustic`` band could take a wrong turn.
type LaneSink = Callable[[LaneObservation], None]

logger = logging.getLogger("intake_voice_runtime.observers")


class SealedResearchStore(Protocol):
    """Where an ``acoustic`` ordinal band goes, and the only place it may go.

    files/03 §4.7.4: *"Output goes to a sealed research store, and to the
    investigator per protocol. **Never** to a treating clinician at session
    time, **never** into the pre-visit note, **never** into an ``Observation``."*

    There is no implementation of this Protocol on this branch — the sealed
    store, its key, its retention clock and its access log are INT-115's, and
    the ordinal head that would fill it does not exist either (files/00 §2
    records an exhaustive search finding **no** Turkish vocal biomarker model;
    D14 dropped Kintsugi DAM). So the seam is declared and the gate fails
    closed: without a store the ``acoustic`` lane is not built at all, which is
    files/03 §4.7.4's *"genuinely unreachable, not merely unrendered"*.
    """

    def record(self, admission: AcousticAdmission, observation: LaneObservation) -> None: ...


class _FrameRing:
    """A bounded, zeroizing frame buffer. Full means drop, never block."""

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._frames: deque[bytearray] = deque()
        self._dropped = 0

    @property
    def depth(self) -> int:
        return len(self._frames)

    @property
    def dropped(self) -> int:
        return self._dropped

    @property
    def frames(self) -> tuple[bytearray, ...]:
        return tuple(self._frames)

    def offer(self, frame: bytes) -> bool:
        """Append one frame. Returns False when an older frame was dropped."""
        dropped = False
        while len(self._frames) >= self._capacity:
            evicted = self._frames.popleft()
            _zero(evicted)
            self._dropped += 1
            dropped = True
        self._frames.append(bytearray(frame))
        return not dropped

    def take(self) -> tuple[tuple[bytearray, ...], int] | None:
        """Move the window out. The ring keeps no reference to those bytes."""
        if not self._frames:
            return None
        frames = tuple(self._frames)
        dropped = self._dropped
        self._frames.clear()
        self._dropped = 0
        return frames, dropped

    def zeroize(self) -> None:
        for buffer in self._frames:
            _zero(buffer)
        self._frames.clear()


def _zero(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0


class LaneRuntime:
    """One session's admitted observer lanes."""

    def __init__(
        self,
        *,
        session_id: str,
        implementations: Mapping[Lane, ObserverLane],
        specs: Mapping[Lane, LaneSpec],
        sinks: Mapping[Lane, LaneSink],
        store: ObserverStore,
    ) -> None:
        self._session_id = session_id
        self._implementations = dict(implementations)
        self._specs = dict(specs)
        self._sinks = dict(sinks)
        self._store = store
        self._rings = {lane: _FrameRing(spec.budget.capacity) for lane, spec in specs.items()}
        self._windows = dict.fromkeys(specs, 0)
        self._lanes = frozenset(specs)

    # --- admission -----------------------------------------------------------------

    @classmethod
    def admit(
        cls,
        *,
        session_id: str,
        implementations: Iterable[ObserverLane],
        consent: Iterable[ConsentDecision],
        interaction: InteractionState,
        study: AcousticAdmission | None = None,
        sealed_store: SealedResearchStore | None = None,
        budget: LaneBudget | None = None,
    ) -> LaneRuntime:
        """Build the lanes this session is permitted, and only those.

        :param consent: the decisions
            :func:`intake_platform.consent.consent_state` produced — this
            runtime consumes verdicts and evaluates nothing (invariant 4).
        :param study: an :class:`AcousticAdmission`, which only
            :func:`~intake_voice_runtime.observers.study.admit_acoustic` mints.
        :param budget: a session-wide override for every admitted lane's
            budget. This is how files/03 §4.5b's degradation triggers narrow
            the lanes on a poor network; ``None`` keeps each lane's declared
            budget.

        There is deliberately no clock here. The runtime measures nothing:
        a stopwatch in this class would be a step taken on the speech path,
        and the property invariant 11 asks for is measured from the *Talker's*
        clock in tests/lanes/test_isolation.py.
        """
        permitted = consented_lanes(consent)
        store = ObserverStore(session_id=session_id, interaction=interaction)
        specs: dict[Lane, LaneSpec] = {}
        sinks: dict[Lane, LaneSink] = {}
        chosen: dict[Lane, ObserverLane] = {}
        for implementation in implementations:
            declared = implementation.spec
            lane = declared.lane
            spec = declared if budget is None else _rebudget(declared, budget)
            if lane is Lane.ACOUSTIC:
                if study is None or sealed_store is None:
                    # No registered investigation, or nowhere sealed to write:
                    # the lane is not built. files/03 §4.7.4 — unreachable,
                    # not merely unrendered, and there is no shadow mode.
                    continue
                sinks[lane] = _sealed_sink(sealed_store, study)
            elif lane in LANE_CONSENT_SCOPE:
                if lane not in permitted:
                    continue
                sinks[lane] = _state_sink(store, spec)
            else:
                raise LaneConsentUndeclared(
                    f"{lane.value!r} has no consent purpose in files/06 §2's closed list; "
                    "a lawful basis is a value a human states, never one this code picks "
                    "(files/HUMAN_BLOCKERS.md HB-L22)"
                )
            specs[lane] = spec
            chosen[lane] = implementation
        return cls(
            session_id=session_id,
            implementations=chosen,
            specs=specs,
            sinks=sinks,
            store=store,
        )

    # --- reads ---------------------------------------------------------------------

    @property
    def lanes(self) -> frozenset[Lane]:
        """The admitted lanes. A refused lane is not a member — it is absent."""
        return self._lanes

    @property
    def store(self) -> ObserverStore:
        return self._store

    def depth(self, lane: Lane) -> int:
        """Frames buffered for one admitted lane."""
        return self._ring(lane).depth

    def dropped(self, lane: Lane) -> int:
        """Frames dropped since this lane's last window was taken."""
        return self._ring(lane).dropped

    def buffered_frames(self, lane: Lane) -> tuple[bytearray, ...]:
        """The ring's own buffers — the witness that zeroization reaches the
        only copy of a frame that exists."""
        return self._ring(lane).frames

    def _ring(self, lane: Lane) -> _FrameRing:
        ring = self._rings.get(lane)
        if ring is None:
            raise LookupError(
                f"{lane.value!r} was not admitted for this session; there is no buffer to "
                "report on (a refused lane is absent, not idle)"
            )
        return ring

    # --- ingress: an ordinary function, on the audio path ---------------------------

    def offer(self, frame: bytes) -> None:
        """Hand one frame to every admitted lane. Never blocks, never waits.

        The frames are the ones already decoded in the session for VAD — one
        audio stream, no new capture (files/03 §4.7.2; invariants 12 and 13).
        """
        for lane, ring in self._rings.items():
            if not ring.offer(frame):
                LANE_DROPPED_FRAMES.labels(lane=lane.value).inc()

    def take_window(self, lane: Lane) -> LaneWindow | None:
        """Move one lane's buffered frames into a window, or ``None`` if empty."""
        ring = self._ring(lane)
        taken = ring.take()
        if taken is None:
            return None
        frames, dropped = taken
        spec = self._specs[lane]
        self._windows[lane] += 1
        return LaneWindow(
            window_id=f"{lane.value}-{self._windows[lane]}",
            frames=frames,
            sampling_rate_hz=spec.budget.sampling_rate_hz,
            dropped_frames=dropped,
            duration_s=len(frames) * spec.budget.frame_ms / 1000.0,
        )

    # --- the pump: off the speech path ----------------------------------------------

    async def pump(self) -> int:
        """Run one observation cycle across every lane that has frames.

        Returns how many lanes produced an observation. Called by the Backend
        worker loop, never from a turn — nothing on the speech path reaches it.
        """
        pending: list[tuple[Lane, LaneWindow]] = []
        for lane in sorted(self._lanes, key=lambda member: member.value):
            window = self.take_window(lane)
            if window is not None:
                pending.append((lane, window))
        if not pending:
            return 0
        outcomes = await asyncio.gather(*(self._observe(lane, window) for lane, window in pending))
        return sum(outcomes)

    async def _observe(self, lane: Lane, window: LaneWindow) -> int:
        context = LaneContext(
            lane=lane,
            session_id=self._session_id,
            window=window,
            is_cancelled=lambda: lane not in self._lanes,
        )
        try:
            observation = await self._implementations[lane].observe(context)
        except Exception as err:
            # A lane fault is a dropped window, never a stopped session — and
            # the class name only, never the message, which could quote input.
            logger.debug(
                "lane observation failed",
                extra={"lane": lane.value, "error": type(err).__name__},
            )
            return 0
        finally:
            window.zeroize()
        if observation is None or lane not in self._lanes:
            return 0
        self._sinks[lane](observation)
        return 1

    # --- withdrawal and shutdown -----------------------------------------------------

    def withdraw(self, lane: Lane) -> None:
        """files/06 §2.2 — effective at the lane boundary: the lane stops, its
        buffers are zeroized, and its live ``ObserverState`` entries are
        dropped. Already-emitted signals are tombstoned by the event log, not
        deleted here: deleting one would break the audit hash chain."""
        spec = self._specs.get(lane)
        if spec is None:
            raise LookupError(f"{lane.value!r} was not admitted for this session")
        self._lanes = self._lanes - {lane}
        self._rings[lane].zeroize()
        self._store.drop(spec)
        logger.debug("lane withdrawn", extra={"lane": lane.value})

    def close(self) -> None:
        """Session end: every buffered frame is zeroized (files/06 §3)."""
        for ring in self._rings.values():
            ring.zeroize()


def _rebudget(spec: LaneSpec, budget: LaneBudget) -> LaneSpec:
    return LaneSpec(lane=spec.lane, module=spec.module, field=spec.field, budget=budget)


def _state_sink(store: ObserverStore, spec: LaneSpec) -> LaneSink:
    """An ``ObserverState`` lane's destination: the store, under its own spec."""

    def sink(observation: LaneObservation) -> None:
        store.apply(spec, observation)

    return sink


def _sealed_sink(store: SealedResearchStore, admission: AcousticAdmission) -> LaneSink:
    """``acoustic``'s destination, bound to the admission that permitted it —
    so a band cannot be written under a study that did not authorise it."""

    def sink(observation: LaneObservation) -> None:
        store.record(admission, observation)

    return sink
