"""The latency harness: per-turn budgets per profile, on a virtual clock (INT-094).

``make runtime-sim SCENARIO=<id> PROFILE=<residency_tr|typed>`` is the entry
point CLAUDE.md names; this module is the thing behind it. It drives a **real**
intake — the production compiler's resolved pack, the real ``IntakeEngine``,
the real ``TalkerSession`` and ``TypedSession``, the real
``ObserverScheduler`` — over recorded doubles, and reports what each turn cost
on INT-091's ``FakeClock``.

**What it measures.** Virtual milliseconds charged to the session clock per
turn, split into the part the harness itself put there (agent playback, at a
declared rate) and the remainder, which is every await the runtime performs
that is not playback. That remainder is the number worth reporting: a stalled
Backend Agent, a stalled observer lane or a slow consent probe would land in
it, and invariants 9 and 11 say they must not.

**What it does not measure, and why the distinction matters.** There is no
GPU, no model, no microphone and no media transport in this container, so
there is no ASR, no LLM, no TTS, no jitter buffer and no device output in any
number here. files/02 §8.1's measurement point — *"last patient speech sample
→ first agent audio sample, on device, client clock"* — is not what this
computes, and :meth:`TurnBudgetReport.verdict` raises rather than pretend
otherwise. Publishing an orchestration figure as a latency would be a
fabricated measurement under CLAUDE.md invariant 20.

**Why the doubles are local.** ``tests/lanes/harness.py`` loads INT-091's
Talker doubles by path because its proof is *about* the Talker and had to run
on the same clock object. The proof here is about the ``ObserverScheduler``
and the ``TalkerSession``, both of which are the real production classes, so
the lane doubles below are small local ones rather than a second copy of that
module loaded under a second name — which would give this file two distinct
``FakeClock`` classes and one very confusing failure.

Everything here is synthetic (files/04 §7) and nothing dials a network, loads
a model or opens a file (CLAUDE.md invariant 17).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from clinical_schemas.observers import Lane
from intake_voice_runtime.budgets import (
    VIRTUAL_MS_PLACES,
    TurnBudgetReport,
    TurnKind,
    TurnObservation,
)
from intake_voice_runtime.clinical_agent import IntakeEngine, MustAskCoverage
from intake_voice_runtime.observers import (
    ConsentReading,
    Frame,
    LaneAdmission,
    LaneBudget,
    LaneContext,
    LaneObservation,
    LaneSpec,
    ObserverScheduler,
    consent_scope_for,
)
from intake_voice_runtime.profiles import VoiceProfile
from talker_harness import FakeClock, StalledBackend
from typed_harness import (
    REFERENCE_TIME,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingSynthesizer,
    Reply,
    Script,
    build_talker,
    build_typed,
    origin_of,
    parity_protocol,
)

__all__ = [
    "LANE_STALL_S",
    "HarnessRun",
    "MeteredSink",
    "run_profile",
]

#: The stall invariant 11's own test uses, reused here so the two numbers
#: cannot drift apart: *"lanes stalled 30 s → turn latency unchanged"*.
LANE_STALL_S = 30.0

#: Virtual milliseconds of playback charged per byte of agent speech. A
#: declared harness input, subtracted back out before anything is reported —
#: it is not a property of any synthesiser and no number derived from it is.
_PLAYBACK_MS_PER_BYTE = 1.0

#: A runaway guard, not a turn budget: files/02 §2's turn budget is an open
#: clinical decision (HUMAN_BLOCKERS HB-C5) and nothing here asserts one.
_MAX_TURNS = 200

_STEP_REASON = "ziyaret.basvuru_nedeni"
_STEP_DURATION = "ziyaret.sure_dakika"
_STEP_COLOUR = "ziyaret.renk_secimi"
_STEP_SCREEN = "tarama.sessiz_soru"
_STEP_ANCHOR = "ziyaret.olay_tarihi"
_ANCHOR_DATE = "2026-08-30"

_MEASURES = (
    "virtual milliseconds charged to the session clock per turn",
    "the modelled agent playback the harness itself introduces, declared and subtracted back out",
    "every await the runtime performs that is not playback",
)

_DOES_NOT_MEASURE = (
    "ASR / speech-to-text: no model and no GPU runs in this container",
    "LLM time to first token: the Talker holds no model; dynamic text arrives "
    "as a string from Layer B",
    "TTS first byte: the synthesiser is a recorded double returning opaque bytes",
    "network transport, jitter buffer and device output: no media transport exists here",
    "PolicyGuard wall time: the guard reports its own perf_counter figure, which "
    "this harness reads from no report and asserts nowhere",
)


# --- speech egress -------------------------------------------------------------------


@dataclass
class MeteredSink:
    """Records agent speech and meters the playback it models.

    ``lag_ms`` is the mutation control: virtual time spent inside ``play``
    that is *not* declared playback shows up as orchestration, which is what
    proves the meter can move at all. A meter stuck at zero proves nothing.
    """

    clock: FakeClock
    lag_ms: float = 0.0
    played: list[tuple[str, int]] = field(default_factory=list)
    cancels: int = 0
    playback_ms: float = 0.0

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.played.append((label, len(frames)))
        charge = len(frames) * _PLAYBACK_MS_PER_BYTE
        self.playback_ms += charge
        await self.clock.sleep(charge / 1000.0)
        if self.lag_ms:
            await self.clock.sleep(self.lag_ms / 1000.0)

    async def cancel(self) -> None:
        self.cancels += 1


# --- lane doubles ---------------------------------------------------------------------


@dataclass
class _GrantingConsentProbe:
    """Grants one scope at one version. Synchronous: it sits on the offer path."""

    scope: str
    version: str = "v1"

    def granted(self, scope: str) -> ConsentReading | None:
        if scope != self.scope:
            return None
        return ConsentReading(scope=scope, version=self.version)


@dataclass
class _StallingObserver:
    """A lane that takes ``stall_s`` of virtual time to answer a window."""

    lane_id: Lane
    clock: FakeClock
    stall_s: float
    started: int = 0
    finished: int = 0

    @property
    def lane(self) -> Lane:
        return self.lane_id

    async def observe(self, context: LaneContext) -> LaneObservation:
        del context
        self.started += 1
        if self.stall_s:
            await self.clock.sleep(self.stall_s)
        self.finished += 1
        return LaneObservation(confidence=1.0)


def _lane_spec(lane: Lane) -> LaneSpec:
    """One lane manifest. The deadline is deliberately unreachable: a lane the
    scheduler times out would advance the virtual clock by its own deadline and
    perturb the very measurement this harness takes."""
    return LaneSpec(
        lane=lane,
        intended_purpose=f"harness double for the {lane.value} lane",
        budget=LaneBudget(
            window_ms=20.0,
            max_queued_frames=4,
            deadline_ms=1_000_000.0,
            sampling_rate_hz=50.0,
        ),
    )


def _frames(count: int, *, start_seq: int) -> list[Frame]:
    return [
        Frame(
            seq=start_seq + i,
            t_monotonic_ms=(start_seq + i) * 10.0,
            duration_ms=10.0,
            samples=bytearray(b"\x01\x02\x03\x04"),
        )
        for i in range(count)
    ]


# --- the script ------------------------------------------------------------------------


def _script() -> Script:
    """One complete answer stream — every step answered first time.

    The same shape INT-096's parity suite uses, restated here rather than
    imported because a shared mutable script would couple two suites' runs.
    """
    return Script(
        replies={
            _STEP_REASON: (
                Reply(entry="sentetik yanıtı", slot_updates={_STEP_REASON: "sentetik"}),
            ),
            _STEP_DURATION: (Reply(entry="sentetik kısa", slot_updates={_STEP_DURATION: 15}),),
            _STEP_COLOUR: (Reply(entry="mavi", slot_updates={_STEP_COLOUR: "mavi"}),),
            _STEP_ANCHOR: (Reply(entry="bugün", slot_updates={_STEP_ANCHOR: _ANCHOR_DATE}),),
            _STEP_SCREEN: (Reply(entry="hayır", slot_updates={_STEP_SCREEN: False}),),
        }
    )


# --- the run ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HarnessRun:
    """One profile's run: the report, and the clinical state it reached."""

    report: TurnBudgetReport
    asked: tuple[str, ...]
    spoken: tuple[str, ...]
    coverage: MustAskCoverage
    lane_ran: bool
    background_works: int


def run_profile(
    profile: VoiceProfile,
    *,
    scenario_id: str,
    backend_stall_s: float = 0.0,
    lane_stall_s: float | None = None,
    sink_lag_ms: float = 0.0,
    background_works: int = 0,
    max_turns: int | None = None,
) -> HarnessRun:
    """Drive one intake in ``profile`` and report every turn it took.

    ``lane_stall_s`` registers a real ``ObserverScheduler`` with one lane that
    stalls for that long; ``backend_stall_s`` and ``background_works`` model
    Layer B work still running. None of the three may change a reported number.
    """
    if not isinstance(profile, VoiceProfile):
        raise ValueError(
            f"{profile!r} is not a voice profile. There are two and there is no "
            f"third: {sorted(member.value for member in VoiceProfile)} "
            "(CLAUDE.md invariant 19)."
        )

    protocol = parity_protocol()
    engine = IntakeEngine(protocol=protocol, reference_time=REFERENCE_TIME)
    clock = FakeClock()
    sink = MeteredSink(clock=clock, lag_ms=sink_lag_ms)
    backend = StalledBackend(clock=clock, stall_s=backend_stall_s)
    memory = InMemoryPatientMemory()
    script = _script()
    voiced = profile is VoiceProfile.RESIDENCY_TR

    talker = (
        build_talker(
            engine,
            protocol,
            clip_store=RecordedClipStore(),
            synthesizer=RecordingSynthesizer(),
            sink=sink,
            backend=backend,
            memory=memory,
            clock=clock,
        )
        if voiced
        else None
    )
    typed = build_typed(engine, protocol, backend=backend, memory=memory, clock=clock)

    scheduler: ObserverScheduler | None = None
    observer: _StallingObserver | None = None
    if lane_stall_s is not None:
        scope = consent_scope_for(Lane.AFFECT)
        scheduler = ObserverScheduler(
            session_ref="harness", clock=clock, consent=_GrantingConsentProbe(scope=scope)
        )
        observer = _StallingObserver(lane_id=Lane.AFFECT, clock=clock, stall_s=lane_stall_s)
        admission = scheduler.register(_lane_spec(Lane.AFFECT), observer)
        if admission is not LaneAdmission.ADMITTED:
            raise RuntimeError(f"the harness lane was refused: {admission.value}")

    asked: list[str] = []
    spoken: list[str] = []
    observations: list[TurnObservation] = []
    attempts: dict[str, int] = {}
    limit = _MAX_TURNS if max_turns is None else max_turns

    async def drive() -> None:
        pump: asyncio.Task[None] | None = None
        loads = [asyncio.ensure_future(backend.work()) for _ in range(background_works)]
        if scheduler is not None:
            pump = asyncio.ensure_future(_pump_forever(scheduler, clock))
        try:
            seq = 0
            while len(asked) < limit:
                step = talker.protocol_next() if talker else typed.protocol_next()
                if step is None:
                    break
                engine.mark_asked(step.step_id)
                asked.append(step.step_id)

                if scheduler is not None:
                    for frame in _frames(4, start_seq=seq):
                        scheduler.offer(frame)
                    seq += 4
                    await asyncio.sleep(0)

                charged_at = clock.now_ms()
                playback_at = sink.playback_ms
                if talker is not None:
                    outcome = await talker.speak_step(step)
                    spoken.append(outcome.spoken_text)
                else:
                    spoken.append(typed.prompt(step).text_tr)
                charged = round(clock.now_ms() - charged_at, VIRTUAL_MS_PLACES)
                observations.append(
                    TurnObservation(
                        index=len(asked) - 1,
                        step_id=step.step_id,
                        turn_kind=TurnKind.of(step.kind),
                        charged_ms=charged,
                        modelled_playback_ms=round(
                            sink.playback_ms - playback_at, VIRTUAL_MS_PLACES
                        ),
                    )
                )

                attempt = attempts.get(origin_of(step.step_id), 0)
                attempts[origin_of(step.step_id)] = attempt + 1
                reply = script.reply_for(step.step_id, attempt)
                if talker is not None:
                    talker.submit_utterance(step.step_id, reply.entry)
                else:
                    typed.submit_utterance(step.step_id, reply.entry)
                engine.apply_extraction(
                    step.step_id, reply.slot_updates, reply.clarification_needed
                )
        finally:
            for load in loads:
                load.cancel()
            if pump is not None:
                pump.cancel()

    clock.run(drive())

    return HarnessRun(
        report=TurnBudgetReport(
            profile=profile,
            scenario_id=scenario_id,
            measures=_MEASURES,
            does_not_measure=_DOES_NOT_MEASURE,
            turns=tuple(observations),
        ),
        asked=tuple(asked),
        spoken=tuple(spoken),
        coverage=engine.must_ask_coverage(),
        lane_ran=observer is not None and observer.started > 0,
        background_works=background_works,
    )


async def _pump_forever(scheduler: ObserverScheduler, clock: FakeClock) -> None:
    """The lanes' own task. Nothing on the speech path awaits this."""
    while True:
        await scheduler.pump()
        await clock.sleep(0.005)
