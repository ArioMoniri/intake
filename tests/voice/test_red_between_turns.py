"""INT-531 — a RED evaluated between turns reaches the patient within the 300 ms budget.

The defect (GitHub #898; INT-521 residual 1): the Talker drained Layer B only
when it took a turn. A rules-engine RED that Layer B evaluated while no turn
was running — the patient silent, the patient still talking, the agent's own
question still playing — waited for the next turn, and when that turn was late
the path delivered and then raised a budget violation measured from the
evaluation. files/02 §8.2's *"RED preemption ≤ 300 ms from rule evaluation"*
held only when a turn happened to follow the evaluation promptly.

What this suite holds, on both profiles, over INT-521's served session (the
committed ``base.intake`` with the committed active ``base.life_threat`` rules,
the composition roots, the real queue and the real RED path):

1. A RED that Layer B evaluates mid-silence, or while the patient is speaking,
   reaches the RED path with no turn taken: the agent's audio is stopped
   within 150 ms and the rule's pre-positioned script starts within 300 ms of
   the evaluation, over the data channel. A RED does not wait for the patient
   to yield the floor (barge-in, for a RED only).
2. A RED evaluated while the agent's next question is going out cuts it (on
   voice the playback is interrupted), triggers inside the same budgets, and
   the turn that was speaking stops without recording the cut question as
   asked.
3. A slow media plane cannot hold the trigger: the path waits for the cancel
   only until the stop budget runs out (INT-520 item 1).
4. Exactly once: one trigger and one preempt whether the push or the next
   turn's drain sees the RED first.
5. Near miss: a non-cardiac answer pair (GREEN) is evaluated between turns and
   reaches nothing.
6. Observer lanes stalled 30 s leave the RED's timing unchanged (invariant
   11), and the Talker's between-turn watch costs a turn nothing (invariant 9).

The transport and device legs are charged the blueprint's own figures
(``red_harness``); the clock is virtual; nothing dials anything. Transcripts,
ids and script ids are synthetic (files/04 §7).
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import test_extraction_valuesets as int518
import test_live_triage as int521
from clinical_schemas.observers import InteractionState, Lane
from clinical_schemas.triage import RedLocation, RedRegister
from intake_voice_runtime.composition import (
    RedWiring,
    SessionStack,
    build_residency_tr_session,
    build_typed_session,
)
from intake_voice_runtime.observers import LaneRuntime
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.delivery import DuplexState
from intake_voice_runtime.talker.red_path import (
    E2E_BUDGET_MS,
    STOP_BUDGET_MS,
    RedTriggerAck,
    RedTriggerMessage,
)
from intake_voice_runtime.talker.session import TurnHold
from red_harness import (
    BLUEPRINT_DEVICE_OUTPUT_MS,
    BLUEPRINT_DOWNLINK_MS,
    MediaPlane,
    RecordingClinicNotifier,
    RecordingDataChannel,
)
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingSynthesizer,
)

_LANE_SUITE = Path(__file__).resolve().parents[1] / "lanes"
if str(_LANE_SUITE) not in sys.path:
    sys.path.append(str(_LANE_SUITE))

from lane_harness import frame, granted, lane_double  # noqa: E402

K2 = int521.K2
ONSET = int521.ONSET
SAID = int521.SAID
NEXT_ANSWER = int521.NEXT_ANSWER
#: The trigger leg the blueprint charges once the cancel has returned
#: (files/03 §4.6 invariant 4: one downlink one-way plus device output).
TRIGGER_LEG_MS = BLUEPRINT_DOWNLINK_MS + BLUEPRINT_DEVICE_OUTPUT_MS
#: When Layer B runs the onset Work, counted from the start of the turn that
#: carries the onset answer. That turn speaks the next question in well under
#: this on both profiles at the default charges, so the RED lands in silence.
QUIET_S = 1.5


# --- doubles that also note when things happened -----------------------------------------


@dataclass
class _TimedChannel(RecordingDataChannel):
    """The data channel, also noting when each pre-positioned script started."""

    started_at_ms: list[float] = field(default_factory=list)

    async def publish(self, message: RedTriggerMessage) -> RedTriggerAck:
        ack = await super().publish(message)
        self.started_at_ms.append(ack.script_started_at_ms)
        return ack


@dataclass
class _TimedMedia(MediaPlane):
    """The agent's audio plane, also noting when each cancel returned."""

    stopped_at_ms: list[float] = field(default_factory=list)

    async def cancel(self) -> None:
        await super().cancel()
        self.stopped_at_ms.append(self.clock.now_ms())


@dataclass
class _Screen:
    """The typed egress: the data channel the client renders. ``render_s`` is
    the virtual time one sentence takes to go out, so a typed turn can be in
    flight when a RED lands."""

    clock: FakeClock
    render_s: float = 0.0
    rendered: list[tuple[str, str]] = field(default_factory=list)

    async def render(self, text_tr: str, *, label: str = "") -> None:
        self.rendered.append((label, text_tr))
        if self.render_s:
            await self.clock.sleep(self.render_s)


@dataclass
class _Ledger:
    """The ask ledger, recording which steps the Talker said it asked."""

    inner: Any
    noted: list[str] = field(default_factory=list)

    def note_asked(self, step_id: str) -> None:
        self.noted.append(step_id)
        self.inner.note_asked(step_id)


@dataclass
class Rig:
    """One composed session over the served rules, and its doubles."""

    stack: SessionStack
    clock: FakeClock
    channel: _TimedChannel
    clinic: RecordingClinicNotifier
    media: _TimedMedia | None
    screen: _Screen


def _rig(
    profile: VoiceProfile,
    character: str = "baskı",
    radiation: str = "yok",
    *,
    location: RedLocation = RedLocation.REMOTE,
) -> Rig:
    clock = FakeClock()
    channel = _TimedChannel(clock=clock)
    clinic = RecordingClinicNotifier()
    screen = _Screen(clock=clock)
    answers = int518._model_answers(character, radiation)
    common: dict[str, Any] = {
        "protocol": int521._served_protocol(),
        "reference_time": int518.NOW,
        "session_id": int518.SESSION,
        "protocol_hash": int518.HASH,
        "gateway": int521._Spoken({SAID[step]: {step: answers[step]} for step in int521.STEPS}),
        "memory": InMemoryPatientMemory(),
        "tenant_id": int518.TENANT,
        "clinic": clinic,
        "clock": clock,
        "screen": screen,
        "red": RedWiring(location=location, channel=channel, scripts=int521._scripts()),
    }
    if profile is VoiceProfile.TYPED:
        return Rig(build_typed_session(**common), clock, channel, clinic, None, screen)
    media = _TimedMedia(clock=clock)
    stack = build_residency_tr_session(
        **common,
        voice_id=int518.VOICE_ID,
        synthesizer=RecordingSynthesizer(),
        clip_store=RecordedClipStore(),
        sink=media,
    )
    return Rig(stack, clock, channel, clinic, media, screen)


During = Callable[[Rig], Awaitable[object]]


@dataclass(frozen=True)
class Between:
    """What the answering turn did, and when the rules engine said RED."""

    answering: Any
    during: object
    evaluated_at_ms: float


def _answer_onset_then(
    rig: Rig,
    *,
    layer_b_at_s: float = QUIET_S,
    during: During | None = None,
    tail_s: float = 3.0,
) -> Between:
    """The canonical loop up to the onset question; then, in one run of the
    session clock: the turn that carries the onset answer (it asks the next
    question), ``during`` (what the patient does next), Layer B running the
    onset Work ``layer_b_at_s`` after that turn began, and ``tail_s`` in which
    no turn is taken at all."""
    int521._converse_until_asked(rig, ONSET)
    session, agent = rig.stack.session, rig.stack.agent

    async def layer_b() -> None:
        await rig.clock.sleep(layer_b_at_s)
        agent.run_pending()  # Layer B's own pump: the onset Work binds; the engine says RED

    async def scenario() -> tuple[Any, object]:
        pump = asyncio.ensure_future(layer_b())
        answering = await session.take_turn(SAID[ONSET])
        happened = await during(rig) if during is not None else None
        await pump
        await rig.clock.sleep(tail_s)
        return answering, happened

    answering, happened = rig.clock.run(scenario())
    assert answering.work_id is not None
    record = agent.record(answering.work_id)
    assert record.finished_ms is not None
    return Between(answering=answering, during=happened, evaluated_at_ms=record.finished_ms)


def _the_rules_own_trigger(location: RedLocation) -> RedTriggerMessage:
    return RedTriggerMessage(
        rule_id=K2,
        register=RedRegister.ALERT,
        location=location,
        script_id=f"{K2}.{location.value.lower()}",
    )


def _assert_reached_within_budget(rig: Rig, between: Between) -> None:
    """One trigger, the rule's own script, inside both budgets from the evaluation."""
    location = rig.stack.agent.triage.location if rig.stack.agent.triage else None
    assert location is not None
    assert rig.channel.published == [_the_rules_own_trigger(location)]
    [started_at] = rig.channel.started_at_ms
    assert started_at - between.evaluated_at_ms <= E2E_BUDGET_MS
    if rig.media is not None:
        stopped_at = rig.media.stopped_at_ms[0]
        assert stopped_at - between.evaluated_at_ms <= STOP_BUDGET_MS
        assert started_at == pytest.approx(stopped_at + TRIGGER_LEG_MS)
    else:
        # typed has no outbound audio: nothing to stop, the trigger leg only
        assert started_at - between.evaluated_at_ms == pytest.approx(TRIGGER_LEG_MS)
    assert rig.stack.session.red_stopped is True
    [red] = rig.stack.session.preempts
    assert red.evaluated_at_ms == between.evaluated_at_ms


def _assert_nothing_after(rig: Rig, between: Between) -> None:
    """The next turn — the patient speaks again — is stopped, and the RED the
    push delivered is not delivered a second time by the turn's own drain."""
    rendered = len(rig.screen.rendered)
    played = len(rig.media.played) if rig.media is not None else 0
    after = int521._turn(rig)
    assert after.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert (after.step_id, after.work_id) == (None, None)  # type: ignore[attr-defined]
    assert len(rig.channel.published) == 1
    assert len(rig.stack.session.preempts) == 1
    assert len(rig.screen.rendered) == rendered
    if rig.media is not None:
        assert len(rig.media.played) == played
    assert {n.work_id for n in rig.clinic.notifications} == {between.answering.work_id}


# --- 1 · between turns: the patient silent, the patient speaking -------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
def test_a_red_evaluated_mid_silence_reaches_the_patient_with_no_turn_taken(
    profile: VoiceProfile, location: RedLocation
) -> None:
    """The patient answered the onset and fell silent; the Talker asked the
    next question and is waiting. Layer B evaluates 1.5 s later. Nothing takes
    a turn, and the RED is on the device inside the budget."""
    rig = _rig(profile, location=location)

    async def silence(rig: Rig) -> None:
        rig.stack.session.observe_duplex(
            DuplexState(patient_silence_ms=0.0, talker_idle=True, pending_response=True)
        )

    between = _answer_onset_then(rig, during=silence)
    assert between.answering.held is None
    _assert_reached_within_budget(rig, between)
    _assert_nothing_after(rig, between)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_red_evaluated_mid_patient_speech_does_not_wait_for_the_floor(
    profile: VoiceProfile,
) -> None:
    """The patient started talking again and has not yielded. A turn taken
    then holds — Backend speech and the next question wait for the window —
    but the RED is evaluated while they are still talking and reaches them
    within the budget all the same."""
    rig = _rig(profile)

    async def talking(rig: Rig) -> object:
        session = rig.stack.session
        session.observe_duplex(
            DuplexState(
                patient_silence_ms=0.0,
                talker_idle=True,
                pending_response=True,
                patient_speaking=True,
            )
        )
        await rig.clock.sleep(1.0)
        return await session.take_turn(None)

    between = _answer_onset_then(rig, during=talking)
    assert between.during.held is TurnHold.PATIENT_HOLDS_FLOOR  # type: ignore[attr-defined]
    assert rig.stack.session.duplex.patient_speaking is True  # never yielded
    _assert_reached_within_budget(rig, between)
    _assert_nothing_after(rig, between)


# --- 2 · mid-egress: the agent's own question is going out ---------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_red_evaluated_mid_question_cuts_it_and_the_turn_stops(profile: VoiceProfile) -> None:
    """The turn that carries the onset answer asks the next question, and that
    question takes 3 s to go out (3.2 s of playback on voice, a slow render on
    typed). Layer B evaluates 1 s in. The RED does not wait for the turn: on
    voice the playback is cut, then the trigger goes; the turn that was
    speaking returns stopped and does not record the cut question as asked."""
    rig = _rig(profile)
    int521._converse_until_asked(rig, ONSET)
    session, agent = rig.stack.session, rig.stack.agent
    ledger = _Ledger(session.ask_ledger)
    session.ask_ledger = ledger
    # only the measured question is slow: 3.2 s of playback, or a 3 s render
    if rig.media is not None:
        rig.media.ms_per_byte = 100.0
    else:
        rig.screen.render_s = 3.0

    async def layer_b() -> None:
        await rig.clock.sleep(1.0)
        agent.run_pending()

    async def scenario() -> Any:
        pump = asyncio.ensure_future(layer_b())
        answering = await session.take_turn(SAID[ONSET])
        await pump
        await rig.clock.sleep(3.0)
        return answering

    started = rig.clock.now_ms()
    answering = rig.clock.run(scenario())
    assert answering.work_id is not None
    finished = agent.record(answering.work_id).finished_ms
    assert finished is not None
    between = Between(answering=answering, during=None, evaluated_at_ms=finished)
    assert between.evaluated_at_ms == pytest.approx(started + 1_000.0)
    _assert_reached_within_budget(rig, between)
    assert answering.held is TurnHold.INTAKE_STOPPED
    assert answering.step_id is not None and answering.step_id != ONSET
    assert ledger.noted == []  # the cut question is not recorded as asked
    [started_at] = rig.channel.started_at_ms
    if rig.media is not None:
        assert rig.media.interrupted == [answering.step_id]
        assert answering.elapsed_ms < 1_000.0 + STOP_BUDGET_MS
    else:
        # a screen has no cancel: the render already going out completes, after
        # the trigger, and nothing more is rendered
        assert started_at < started + 3_000.0
    _assert_nothing_after(rig, between)


# --- 3 · a slow media plane cannot hold the trigger ------------------------------------------


def test_a_slow_media_plane_cannot_hold_the_trigger_past_the_budget() -> None:
    """A live SFU tearing the room down over HTTP can take seconds to cancel
    (INT-520 item 1). The path waits for the cancel only until the stop budget
    runs out, then triggers; the cancel finishes behind it. ``typed`` has no
    outbound audio (files/03 §4.4), so this case exists on voice only."""
    rig = _rig(VoiceProfile.RESIDENCY_TR)
    assert rig.media is not None
    rig.media.cancel_cost_ms = 2_000.0
    between = _answer_onset_then(rig)
    assert rig.channel.published == [_the_rules_own_trigger(RedLocation.REMOTE)]
    [started_at] = rig.channel.started_at_ms
    assert started_at - between.evaluated_at_ms == pytest.approx(STOP_BUDGET_MS + TRIGGER_LEG_MS)
    assert started_at - between.evaluated_at_ms <= E2E_BUDGET_MS
    # the cancel was started first and still ran to its end, after the trigger
    assert rig.media.calls.count("cancel") == 1
    [stopped_at] = rig.media.stopped_at_ms
    assert stopped_at == pytest.approx(between.evaluated_at_ms + 2_000.0)
    assert rig.stack.session.red_stopped is True


# --- 4 · exactly once --------------------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_red_the_next_turn_drains_first_is_still_delivered_once(profile: VoiceProfile) -> None:
    """Layer B settles the RED and the patient's next turn starts in the same
    instant, before the Talker's watch has run: the turn's drain delivers it,
    and the push that arrives behind is not delivered again."""
    rig = _rig(profile)
    int521._converse_until_asked(rig, ONSET)
    session, agent = rig.stack.session, rig.stack.agent

    async def scenario() -> Any:
        await session.take_turn(SAID[ONSET])
        await rig.clock.sleep(QUIET_S)
        agent.run_pending()  # settled and pushed; nothing has run on the Talker yet
        after = await session.take_turn(NEXT_ANSWER)
        await rig.clock.sleep(1.0)
        return after

    after = rig.clock.run(scenario())
    assert after.held is TurnHold.INTAKE_STOPPED
    assert rig.channel.published == [_the_rules_own_trigger(RedLocation.REMOTE)]
    assert len(session.preempts) == 1
    assert int521._turn(rig).held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert len(rig.channel.published) == 1


# --- 5 · near miss: a determination that is not RED reaches nothing ----------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_green_evaluated_between_turns_reaches_nothing(profile: VoiceProfile) -> None:
    """The same conversation with a non-cardiac character and no radiation:
    Layer B evaluates the onset Work between turns, the engine says GREEN, and
    nothing is stopped, triggered or told; the next turn asks on."""
    rig = _rig(profile, "başka bir his", "yok")
    between = _answer_onset_then(rig)
    assert rig.stack.agent.triage is not None
    assert between.answering.work_id in rig.stack.agent.triage.evaluated
    assert rig.channel.published == []
    assert rig.clinic.notifications == []
    assert rig.stack.session.red_stopped is False
    assert rig.stack.session.preempts == ()
    if rig.media is not None:
        assert "cancel" not in rig.media.calls
    after = int521._turn(rig)
    assert after.held is not TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]


# --- 6 · invariants 11 and 9: nothing on the side changes the RED or the turn -----------------


_NEUTRAL = InteractionState(
    pace="normal",
    modality="voice",
    break_offer=False,
    confirm_by_card=False,
    repeat_request=False,
    third_party_present=False,
)


def _timing_with_lanes(profile: VoiceProfile, stall_s: float | None) -> tuple[float, float, bool]:
    """The mid-silence RED, with observer lanes stalled ``stall_s`` beside it
    (``None``: no lanes at all). Returns the e2e, the answering turn's cost,
    and whether the lane pump was still parked when the RED was on the device."""
    rig = _rig(profile)
    runtime = (
        None
        if stall_s is None
        else LaneRuntime.admit(
            session_id=int518.SESSION,
            implementations=[
                lane_double(Lane.AFFECT, rig.clock, stall_s=stall_s),
                lane_double(Lane.LINGUISTIC, rig.clock, stall_s=stall_s),
            ],
            consent=granted("lane:affect", "lane:linguistic"),
            interaction=_NEUTRAL,
        )
    )
    parked: list[bool] = []

    async def lanes(rig: Rig) -> None:
        if runtime is None:
            return
        for index in range(8):
            runtime.offer(frame(index))
        pump = asyncio.ensure_future(runtime.pump())
        await rig.clock.sleep(QUIET_S + 0.5)  # past the RED's delivery
        parked.append(not pump.done())

    between = _answer_onset_then(rig, during=lanes, tail_s=1.0)
    if runtime is not None:
        runtime.close()
    [started_at] = rig.channel.started_at_ms
    return (
        started_at - between.evaluated_at_ms,
        float(between.answering.elapsed_ms),
        all(parked),
    )


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_observer_lanes_stalled_thirty_seconds_leave_the_red_unchanged(
    profile: VoiceProfile,
) -> None:
    without = _timing_with_lanes(profile, None)
    instant = _timing_with_lanes(profile, 0.0)
    stalled = _timing_with_lanes(profile, 30.0)
    assert without[:2] == instant[:2] == stalled[:2]
    assert stalled[2] is True  # the lanes were still parked when the RED landed
    assert stalled[0] <= E2E_BUDGET_MS


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_between_turn_watch_costs_a_turn_nothing(profile: VoiceProfile) -> None:
    """The Talker's watch parks on the push; a turn that runs beside it costs
    what a turn costs without one, with Layer B stalled 10 s or 30 s (the RED
    lands after the turn either way, so only the watch differs)."""

    def answering_cost(*, watched: bool, stall_s: float) -> float:
        rig = _rig(profile)
        if not watched:
            rig.stack.session.red_mailbox = None
        int521._converse_until_asked(rig, ONSET)
        session, agent = rig.stack.session, rig.stack.agent

        async def layer_b() -> None:
            await rig.clock.sleep(stall_s)
            agent.run_pending()

        async def scenario() -> float:
            pump = asyncio.ensure_future(layer_b())
            outcome = await session.take_turn(SAID[ONSET])
            pump.cancel()
            return float(outcome.elapsed_ms)

        return float(rig.clock.run(scenario()))

    costs = {
        answering_cost(watched=watched, stall_s=stall_s)
        for watched in (True, False)
        for stall_s in (10.0, 30.0)
    }
    assert len(costs) == 1
