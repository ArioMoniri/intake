"""The lane scheduler — parallel, backpressured, and never on the speech path.

files/03 §4.7 in one sentence: *"Psychiatric and affect analysis must not wait
in [the clinical Work] queue — it runs continuously in parallel observer lanes
that read the same audio/transcript stream, write only to ``ObserverState``,
and merge into the Backend Agent at section boundaries."*

The split that makes invariant 11 structural rather than remembered is the
same one ``work_queue.py`` uses for ADR-009:

- :meth:`ObserverScheduler.offer` is what the **speech path** calls, once per
  frame. It is an ordinary function. It appends to bounded buffers, counts
  what does not fit, and returns. There is no awaitable member on this class
  except :meth:`pump`, so there is no expression by which a turn could wait
  for a lane;
- :meth:`ObserverScheduler.pump` belongs to the **lane tasks' own** thread of
  control. It races each lane against its own deadline on the injected clock,
  and a lane that overruns has its window discarded rather than its caller
  delayed.

``tests/lanes/test_isolation.py`` proves the consequence on INT-091's virtual
clock: a real Talker turn costs exactly the same with lanes stalled 30 s (and
an hour) as with no lanes at all.

Four more properties, each fail-closed:

- **consent is checked on every read**, not once per session. KVKK-6 says
  every lane *read* checks a scope, so a grant that disappears between windows
  stops the lane at the next window and zeroizes its buffer (files/06 §2.2).
- **`acoustic` is gated by the study assertion, never by a consent scope** —
  files/06 §2.4 made it an ICF — and its observations are handed back to the
  caller for the sealed research store rather than merged into
  ``ObserverState`` (files/03 §4.7.4).
- **frames are zeroized when the last lane holding them is done.** The same
  frame is offered to every admitted lane, so the scheduler reference-counts
  it: invariant 3's *"zeroed on every trigger"* has to mean the bytes, once,
  and not one lane blanking another lane's window.
- **a lane that breaches its module boundary or raises is disabled**, not
  obeyed and not allowed to take the pump down with it. Its window is dropped
  and counted like any other shed load.
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Iterable
from dataclasses import dataclass, field

from clinical_schemas.observers import Lane, ObserverState

from intake_voice_runtime.observers.budget import DropReason
from intake_voice_runtime.observers.buffer import (
    Frame,
    WindowBuffer,
    ZeroizeTrigger,
    zeroize_frames,
)
from intake_voice_runtime.observers.consent import (
    ConsentProbe,
    LaneConsentUndeclaredError,
    consent_scope_for,
)
from intake_voice_runtime.observers.context import LaneContext, LaneObservation, Observer
from intake_voice_runtime.observers.metrics import DropLedger
from intake_voice_runtime.observers.module_boundary import LANE_MODULE, LaneModule
from intake_voice_runtime.observers.spec import LaneSpec
from intake_voice_runtime.observers.state import ObserverStateBuilder, ObserverStateRefusedError
from intake_voice_runtime.observers.study import StudyGate
from intake_voice_runtime.ports import Clock

__all__ = ["FrameOffer", "LaneAdmission", "LaneOutcome", "ObserverScheduler"]


class LaneAdmission(enum.StrEnum):
    """Whether a lane may run, and if not, which gate refused it."""

    ADMITTED = "admitted"
    #: No human has decided this lane's consent purpose (files/06 §2).
    REFUSED_NO_CONSENT_SCOPE = "refused_no_consent_scope"
    #: The purpose exists and the patient has not granted it.
    REFUSED_CONSENT_NOT_GRANTED = "refused_consent_not_granted"
    #: M3 outside a registered investigation, or after an amendment (inv. 23).
    REFUSED_STUDY_ASSERTION = "refused_study_assertion"


@dataclass(frozen=True, slots=True, eq=False)
class FrameOffer:
    """What one frame did: which lanes took it, and which shed it and why."""

    seq: int
    accepted: tuple[Lane, ...]
    dropped: tuple[tuple[Lane, DropReason], ...]


@dataclass(frozen=True, slots=True, eq=False)
class LaneOutcome:
    """What one window did. ``recorded_in_state`` is false for M3, always."""

    lane: Lane
    observation: LaneObservation | None
    dropped: DropReason | None
    recorded_in_state: bool


@dataclass
class _Registration:
    spec: LaneSpec
    observer: Observer
    buffer: WindowBuffer
    scope: str | None
    consent_version: str


@dataclass
class ObserverScheduler:
    """One session's observer lanes. The speech path holds this object."""

    session_ref: str
    clock: Clock
    consent: ConsentProbe
    study_gate: StudyGate | None = None

    _lanes: dict[Lane, _Registration] = field(default_factory=dict, init=False)
    _holders: dict[int, int] = field(default_factory=dict, init=False)
    _drops: DropLedger = field(default_factory=DropLedger, init=False)
    _windows: int = field(default=0, init=False)
    _state: ObserverStateBuilder = field(init=False)

    def __post_init__(self) -> None:
        self._state = ObserverStateBuilder(session_ref=self.session_ref)

    # --- reads ---------------------------------------------------------------------------

    @property
    def lanes(self) -> frozenset[Lane]:
        """The lanes actually running. A refused lane is absent, not disabled."""
        return frozenset(self._lanes)

    @property
    def drops(self) -> DropLedger:
        return self._drops

    def observer_state(self) -> ObserverState:
        """The only thing the lanes have written (invariant 11)."""
        return self._state.state()

    def retained_bytes(self) -> int:
        """Sample bytes still held across every lane buffer (invariant 3)."""
        return sum(registration.buffer.retained_bytes() for registration in self._lanes.values())

    # --- registration --------------------------------------------------------------------

    def register(self, spec: LaneSpec, observer: Observer) -> LaneAdmission:
        """Admit a lane, or refuse it and say which gate said no.

        Every refusal is a *non-registration*: the lane is never added, so
        :meth:`offer` cannot reach it and :meth:`pump` has nothing to run. A
        lane that is merely flagged off is a lane one edit away from running.
        """
        if LANE_MODULE[spec.lane] is LaneModule.ACOUSTIC:
            gate = self.study_gate
            if gate is None or gate.assertion is None or not gate.admits:
                return LaneAdmission.REFUSED_STUDY_ASSERTION
            self._admit(spec, observer, scope=None, version=gate.assertion.icf_version)
            return LaneAdmission.ADMITTED

        try:
            scope = consent_scope_for(spec.lane)
        except LaneConsentUndeclaredError:
            return LaneAdmission.REFUSED_NO_CONSENT_SCOPE
        reading = self.consent.granted(scope)
        if reading is None:
            return LaneAdmission.REFUSED_CONSENT_NOT_GRANTED
        self._admit(spec, observer, scope=scope, version=reading.version)
        return LaneAdmission.ADMITTED

    def _admit(
        self, spec: LaneSpec, observer: Observer, *, scope: str | None, version: str
    ) -> None:
        self._lanes[spec.lane] = _Registration(
            spec=spec,
            observer=observer,
            buffer=WindowBuffer(budget=spec.budget),
            scope=scope,
            consent_version=version,
        )

    # --- the speech path's surface (no member here is awaitable) -------------------------

    def offer(self, frame: Frame) -> FrameOffer:
        """Hand one frame to every admitted lane. Never blocks, never raises.

        A lane whose buffer is full sheds the frame: invariant 11's *"under
        backpressure they drop frames, never delay speech"*, at the one place
        the speech path and the lanes actually touch.
        """
        accepted: list[Lane] = []
        dropped: list[tuple[Lane, DropReason]] = []
        for lane, registration in self._lanes.items():
            if registration.buffer.append(frame):
                accepted.append(lane)
                self._holders[frame.seq] = self._holders.get(frame.seq, 0) + 1
            else:
                self._drops.record(lane, DropReason.BACKPRESSURE)
                dropped.append((lane, DropReason.BACKPRESSURE))
        return FrameOffer(seq=frame.seq, accepted=tuple(accepted), dropped=tuple(dropped))

    def disable(self, lane: Lane, trigger: ZeroizeTrigger, reason: DropReason) -> int:
        """Stop one lane: drain its buffer, zeroize, count. Returns frames zeroed."""
        registration = self._lanes.pop(lane, None)
        if registration is None:
            return 0
        held = registration.buffer.drain()
        self._drops.record(lane, reason, len(held))
        return self._release(held, trigger)

    def withdraw(self, scope: str) -> tuple[Lane, ...]:
        """files/06 §2.2 — withdrawal is effective at the lane boundary.

        Every lane riding the withdrawn scope stops, its buffer is zeroized
        and the zeroization is asserted by the caller's own count.
        """
        stopped = tuple(
            lane
            for lane, registration in self._lanes.items()
            if registration.scope is not None and registration.scope == scope
        )
        for lane in stopped:
            self.disable(lane, ZeroizeTrigger.CONSENT_WITHDRAWN, DropReason.CONSENT_WITHDRAWN)
        return stopped

    def end_session(self) -> int:
        """Stop every lane and zeroize everything held. Returns frames zeroed."""
        return sum(
            self.disable(lane, ZeroizeTrigger.SESSION_END, DropReason.LANE_DISABLED)
            for lane in tuple(self._lanes)
        )

    # --- the lane tasks' own entry point --------------------------------------------------

    async def pump(self) -> tuple[LaneOutcome, ...]:
        """Run every ready window. The only coroutine on this class.

        Nothing on the speech path calls it: it is the lanes' own task, exactly
        as ``WorkQueue.run_pending`` is Layer B's and is not on the port the
        Talker holds.
        """
        outcomes: list[LaneOutcome] = []
        for lane, registration in tuple(self._lanes.items()):
            if not self._consent_still_holds(lane, registration):
                continue
            while True:
                current = self._lanes.get(lane)
                if current is None or not current.buffer.ready:
                    break
                outcome = await self._run_window(lane, current)
                outcomes.append(outcome)
                if outcome.dropped is not None:
                    break
        return tuple(outcomes)

    async def _run_window(self, lane: Lane, registration: _Registration) -> LaneOutcome:
        view, taken = registration.buffer.take_window()
        self._windows += 1
        context = LaneContext(
            lane=lane,
            module=registration.spec.module,
            session_ref=self.session_ref,
            window_id=f"w{self._windows:06d}",
            seq=self._windows,
            t_monotonic_ms=self.clock.now_ms(),
            consent_version=registration.consent_version,
            gate_state=self._gate_state(registration),
            window=view,
            dropped_frames_in_window=registration.buffer.take_dropped(),
        )

        work = asyncio.ensure_future(registration.observer.observe(context))
        deadline_s = registration.spec.budget.deadline_ms / 1000.0
        timer = asyncio.ensure_future(self.clock.sleep(deadline_s))
        done, _pending = await asyncio.wait({work, timer}, return_when=asyncio.FIRST_COMPLETED)

        if work not in done:
            work.cancel()
            self._drops.record(lane, DropReason.LANE_OVERRAN, len(taken))
            self._release(taken, ZeroizeTrigger.GATE_REJECTED)
            return LaneOutcome(
                lane=lane,
                observation=None,
                dropped=DropReason.LANE_OVERRAN,
                recorded_in_state=False,
            )

        timer.cancel()
        self._release(taken, ZeroizeTrigger.WINDOW_CONSUMED)
        try:
            observation = work.result()
        except Exception:  # noqa: BLE001 - the lane is contained, not trusted
            self.disable(lane, ZeroizeTrigger.LANE_DISABLED, DropReason.LANE_DISABLED)
            return LaneOutcome(
                lane=lane,
                observation=None,
                dropped=DropReason.LANE_DISABLED,
                recorded_in_state=False,
            )
        return self._record(lane, observation)

    def _record(self, lane: Lane, observation: LaneObservation) -> LaneOutcome:
        if LANE_MODULE[lane] is LaneModule.ACOUSTIC:
            # files/03 §4.7.4: to the sealed research store and the investigator
            # per protocol — never here. The caller takes it from the outcome.
            return LaneOutcome(
                lane=lane, observation=observation, dropped=None, recorded_in_state=False
            )
        try:
            self._state.apply(lane, observation)
        except ObserverStateRefusedError:
            self.disable(lane, ZeroizeTrigger.LANE_DISABLED, DropReason.LANE_DISABLED)
            return LaneOutcome(
                lane=lane,
                observation=observation,
                dropped=DropReason.LANE_DISABLED,
                recorded_in_state=False,
            )
        return LaneOutcome(lane=lane, observation=observation, dropped=None, recorded_in_state=True)

    # --- gates ----------------------------------------------------------------------------

    def _consent_still_holds(self, lane: Lane, registration: _Registration) -> bool:
        """KVKK-6: *every* lane read checks a scope, not the first one.

        For M3 the check is the study assertion, because files/06 §2.4 gives it
        an ICF rather than a scope — and the assertion is re-read so an
        amendment mid-session closes the gate at the next window.
        """
        if registration.scope is None:
            gate = self.study_gate
            if gate is not None and gate.admits:
                return True
            self.disable(lane, ZeroizeTrigger.GATE_REJECTED, DropReason.LANE_DISABLED)
            return False
        reading = self.consent.granted(registration.scope)
        if reading is None:
            self.disable(lane, ZeroizeTrigger.CONSENT_WITHDRAWN, DropReason.CONSENT_WITHDRAWN)
            return False
        registration.consent_version = reading.version
        return True

    def _gate_state(self, registration: _Registration) -> str:
        if registration.scope is None:
            gate = self.study_gate
            return gate.state.value if gate is not None else "no_assertion"
        return "consent_granted"

    # --- frame lifetime -------------------------------------------------------------------

    def _release(self, held: Iterable[Frame], trigger: ZeroizeTrigger) -> int:
        """Zeroize each frame once the last lane holding it is finished with it."""
        zeroed = 0
        for frame in held:
            remaining = self._holders.get(frame.seq, 1) - 1
            if remaining > 0:
                self._holders[frame.seq] = remaining
                continue
            self._holders.pop(frame.seq, None)
            zeroed += zeroize_frames((frame,), trigger)
        return zeroed
