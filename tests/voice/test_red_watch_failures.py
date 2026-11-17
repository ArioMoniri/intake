"""INT-531 round 2 — nothing starts after a RED, and a RED the watch fails is never silent.

The runtime review of round 1 blocked on two defects and named two more ways
a RED could be lost. The reviewer's probes are lifted here, each with the
assertion the fix makes true.

- **B1 (invariant 21).** Layer B's own speech could start *after* the RED
  script. An INTERJECT item cancels the non-RED playback first and then
  emits; a RED latched during that cancel used to be followed by the YELLOW
  (reproduced: script at 50 065 ms, YELLOW playing from 50 120 ms, no
  violation). Every egress start is now gated on the latch, and a work id is
  never reported delivered when nothing was spoken.
- **B2.** An unexpected error on the RED path — a data channel that raises,
  say — ended the watch task. Its work id was already marked seen and the
  intake already latched, so the next turn returned stopped without draining:
  the patient could be shown nothing, with no log, count or raise. Now the
  watch logs it by id and error class, counts it, keeps watching, and the
  next turn retries the RED and raises.
- **The session ending mid-delivery** (or the event loop going away) used to
  cancel the delivery between the stop and the trigger. The delivery is now
  shielded from the watch's cancellation, and a delivery the loop itself
  cancels is recorded and retried like B2.
- **The clinician route raising** skipped the stop and the device trigger.
  It is now logged and counted the way Layer B's route is, and the trigger
  still goes.

Everything is synthetic (files/04 §7) and the clock is virtual.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import pytest
import test_red_preemption as int093
from clinical_schemas.triage import RuleFire, RulesTriageResult, TriageLevel
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.steps import NextStep
from intake_voice_runtime.talker import session as talker_session
from intake_voice_runtime.talker.delivery import DeliveryClass, DuplexState
from intake_voice_runtime.talker.preemption import BackendResult, Presentation
from intake_voice_runtime.talker.red_path import RedNotification, RedPreemption
from intake_voice_runtime.talker.red_push import RedMailbox
from intake_voice_runtime.talker.session import TalkerSession, TurnHold
from prometheus_client import REGISTRY
from red_harness import MediaPlane, RecordingClinicNotifier, RecordingDataChannel
from talker_harness import (
    FakeClock,
    RecordingSynthesizer,
    StalledBackend,
    build_session,
    scripted_step,
)

RULE = int093.RULE_A


def _red(work_id: str = "w_red", *, evaluated_at_ms: float = 0.0) -> BackendResult:
    return int093.red_result(work_id=work_id).model_copy(
        update={"evaluated_at_ms": evaluated_at_ms}
    )


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _watch_failures(kind: str) -> float:
    return _sample("red_watch_failures_total", {"kind": kind})


@dataclass
class Timeline:
    """What started when, on the session clock: agent playback and RED scripts."""

    events: list[tuple[str, str, float]] = field(default_factory=list)
    latched_at_ms: list[float] = field(default_factory=list)

    def starts(self, kind: str) -> list[tuple[str, float]]:
        return [(label, at) for event, label, at in self.events if event == kind]


@dataclass
class Rig:
    clock: FakeClock
    session: TalkerSession
    media: MediaPlane
    channel: RecordingDataChannel
    clinic: Any
    timeline: Timeline
    backend: StalledBackend


def _failed() -> type[Exception]:
    """The turn's raise for a RED the watch could not deliver. Looked up when
    used, so this suite collects (and fails on behaviour) on a tree without it."""
    failed: type[Exception] = talker_session.RedDeliveryFailed  # type: ignore[attr-defined]
    return failed


def _rig(
    *,
    cancel_cost_ms: float = 5.0,
    publish_raises: Exception | None = None,
    clinic: Any = None,
    backend_results: list[BackendResult] | None = None,
) -> Rig:
    """A Talker over doubles with the RED path and the mailbox bound, and a
    timeline of every playback start, script start and latch."""
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=0.0)
    backend.results = list(backend_results or [])
    media = MediaPlane(clock=clock, cancel_cost_ms=cancel_cost_ms, ms_per_byte=100.0)
    channel = RecordingDataChannel(clock=clock, publish_raises=publish_raises)
    route = clinic if clinic is not None else RecordingClinicNotifier()
    session = build_session(
        clock,
        rule_ids=int093.PACK_RULES,
        sink=media,
        steps=[scripted_step()],
        synthesizer=RecordingSynthesizer(),
        backend=backend,
    )
    session.preemption = RedPreemption(
        canceller=media, channel=channel, clinic=route, scripts=int093.SCRIPTS, clock=clock
    )
    session.red_mailbox = RedMailbox()
    timeline = Timeline()

    played = media.play

    async def play(frames: bytes, *, label: str = "") -> None:
        timeline.events.append(("play", label, clock.now_ms()))
        await played(frames, label=label)

    media.play = play  # type: ignore[method-assign]
    published = channel.publish

    async def publish(message: Any) -> Any:
        ack = await published(message)
        timeline.events.append(("script", message.rule_id, ack.script_started_at_ms))
        return ack

    channel.publish = publish  # type: ignore[method-assign]
    deliver = session.deliver_preempt

    async def latch_noted(result: BackendResult, *, evaluated_at_ms: float) -> Any:
        timeline.latched_at_ms.append(clock.now_ms())
        return await deliver(result, evaluated_at_ms=evaluated_at_ms)

    session.deliver_preempt = latch_noted  # type: ignore[method-assign]
    return Rig(clock, session, media, channel, route, timeline, backend)


def _push(rig: Rig, work_id: str = "w_red") -> None:
    assert rig.session.red_mailbox is not None
    rig.session.red_mailbox.push(_red(work_id, evaluated_at_ms=rig.clock.now_ms()))


# --- B1 · nothing starts after the RED ---------------------------------------------------------


def _yellow() -> BackendResult:
    return BackendResult(
        work_id="w_yellow",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.TRIAGE_YELLOW,
        presentation=Presentation(
            speech_tr="Sentetik sarı bilgilendirme.",
            triage_update=RulesTriageResult(
                level=TriageLevel.YELLOW, rules=(RuleFire(id=RULE, evidence="sentetik"),)
            ),
        ),
    )


@pytest.mark.parametrize(
    "cancel_cost_ms",
    [2_000.0, 120.0],
    ids=["slow-sink-past-the-stop-budget", "sink-inside-the-stop-budget"],
)
def test_backend_speech_cancelled_for_an_interject_never_starts_after_the_red(
    cancel_cost_ms: float,
) -> None:
    """The reviewer's two variants, through ``take_turn``. A YELLOW waits past
    its hard deadline and is delivered at INTERJECT, which cancels the
    agent's playback first. The RED is pushed 10 ms into that cancel. No
    playback starts at or after the latch, the YELLOW is not reported
    delivered, the turn stops, and the script went out once."""
    rig = _rig(cancel_cost_ms=cancel_cost_ms, backend_results=[_yellow()])
    rig.session.observe_duplex(
        DuplexState(
            patient_silence_ms=0.0,
            talker_idle=True,
            pending_response=False,
            at_sentence_boundary=True,
            patient_speaking=True,
        )
    )

    async def layer_b() -> None:
        await rig.clock.sleep(0.01)
        _push(rig)

    async def scenario() -> tuple[Any, Any]:
        await rig.backend.work()
        first = await rig.session.take_turn(None)  # the patient holds the floor
        await rig.clock.sleep(50.0)  # past the YELLOW's 45 s hard deadline
        pushing = asyncio.ensure_future(layer_b())
        second = await rig.session.take_turn(None)
        await pushing
        await rig.clock.sleep(5.0)
        return first, second

    first, second = rig.clock.run(scenario())
    assert first.held is TurnHold.PATIENT_HOLDS_FLOOR
    [latched_at] = rig.timeline.latched_at_ms
    assert [label for label, at in rig.timeline.starts("play") if at >= latched_at] == []
    assert rig.timeline.starts("play") == []  # the YELLOW never started
    assert [rule for rule, _ in rig.timeline.starts("script")] == [RULE]
    assert second.held is TurnHold.INTAKE_STOPPED
    assert second.delivered_work_ids == ()
    assert (second.step_id, second.spoken_text) == (None, "")


def test_after_the_latch_no_question_and_no_bridge_starts() -> None:
    """The gate is on the egress itself, so every start is covered: a step's
    question and the safe bridge emit nothing once the intake has stopped."""
    rig = _rig()
    rig.session.config = rig.session.config.model_copy(
        update={"safe_bridge_clip_id": "sentetik-kopru"}
    )

    async def scenario() -> tuple[Any, Any]:
        rig.session.ensure_red_watch()
        _push(rig)
        await rig.clock.sleep(1.0)
        step = rig.session.engine.snapshot.next_step
        assert step is not None
        offered = NextStep.of(step, 1)
        question = await rig.session.speak_step(offered)
        bridge = await rig.session._speak_bridge(offered, rig.clock.now_ms())
        return question, bridge

    question, bridge = rig.clock.run(scenario())
    assert rig.session.red_stopped is True
    assert (question.spoken_text, bridge.spoken_text) == ("", "")
    assert rig.media.played == []
    assert rig.session.playback_intervals == ()


# --- B2 · an unexpected failure on the push route is loud and retried ----------------------------


def test_a_raising_data_channel_on_the_push_route_is_logged_counted_retried_and_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The reviewer's probe: the data channel raises on the push route. The
    watch logs the RED by id and error class only, counts it and keeps
    watching (a second RED is delivered). The next turn retries the first RED
    ahead of the stopped-intake return and raises ``RedDeliveryFailed``; the
    turn after it is stopped and raises nothing."""
    rig = _rig(publish_raises=ConnectionError("sentetik kanal arizasi"))
    before = _watch_failures("delivery")
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.session.ensure_red_watch()
        assert watch is not None
        await rig.clock.sleep(0.5)
        _push(rig, "w_1")
        await rig.clock.sleep(0.5)
        state["watch_alive"] = not watch.done()
        rig.channel.publish_raises = None
        _push(rig, "w_2")
        await rig.clock.sleep(0.5)
        with pytest.raises(_failed()) as failed:
            await rig.session.take_turn("sentetik")
        state["failed"] = failed.value
        state["after"] = await rig.session.take_turn("sentetik")

    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.talker.session"):
        rig.clock.run(scenario())
    assert state["watch_alive"] is True
    assert _watch_failures("delivery") == before + 1
    [logged] = [r for r in caplog.records if r.message == "pushed red delivery failed"]
    assert logged.__dict__["work_id"] == "w_1"
    assert logged.__dict__["error"] == "ConnectionError"
    assert "sentetik kanal arizasi" not in caplog.text
    failed = state["failed"]
    assert failed.work_ids == ("w_1",)
    assert isinstance(failed.__cause__, ConnectionError)
    # w_1 tried on the watch (raised), w_2 delivered by the watch, w_1 retried on the turn
    assert [m.rule_id for m in rig.channel.published] == [RULE, RULE, RULE]
    assert set(rig.session.preemption.delivered_work_ids) == {"w_1", "w_2"}  # type: ignore[union-attr]
    assert state["after"].held is TurnHold.INTAKE_STOPPED


def test_a_watch_that_exits_unexpectedly_is_logged_counted_and_restarted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = _rig()
    assert rig.session.red_mailbox is not None

    async def broken_take() -> tuple[BackendResult, ...]:
        raise RuntimeError("sentetik posta kutusu arizasi")

    rig.session.red_mailbox.take = broken_take  # type: ignore[method-assign]
    before = _watch_failures("exit")

    async def scenario() -> tuple[bool, bool]:
        first = rig.session.ensure_red_watch()
        assert first is not None
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        exited = first.done()
        again = rig.session.ensure_red_watch()
        return exited, again is not first

    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.talker.session"):
        exited, restarted = rig.clock.run(scenario())
    assert (exited, restarted) == (True, True)
    assert _watch_failures("exit") >= before + 1
    exits = [r for r in caplog.records if r.message == "red watch exited"]
    assert exits and exits[0].__dict__["error"] == "RuntimeError"
    assert "sentetik posta kutusu arizasi" not in caplog.text


def test_near_miss_a_cancelled_watch_is_not_an_unexpected_exit() -> None:
    rig = _rig()
    before = _watch_failures("exit")

    async def scenario() -> None:
        rig.session.ensure_red_watch()
        await asyncio.sleep(0)
        rig.session.stop_red_watch()
        await asyncio.sleep(0)

    rig.clock.run(scenario())
    assert _watch_failures("exit") == before


# --- the session ending, or the loop going away, mid-delivery ------------------------------------


def test_ending_the_session_mid_delivery_still_triggers_the_device() -> None:
    """The reviewer's probe: the session ends 50 ms into a 100 ms stop. The
    watch is cancelled, the delivery is not: the script still goes out."""
    rig = _rig(cancel_cost_ms=100.0)
    state: dict[str, Any] = {}

    async def scenario() -> None:
        rig.session.ensure_red_watch()
        await rig.clock.sleep(0.5)
        _push(rig)
        await rig.clock.sleep(0.05)
        rig.session.stop_red_watch()
        await rig.clock.sleep(1.0)
        state["after"] = await rig.session.take_turn("sentetik")

    rig.clock.run(scenario())
    assert [m.rule_id for m in rig.channel.published] == [RULE]
    assert rig.session.preemption.delivered_work_ids == ("w_red",)  # type: ignore[union-attr]
    assert rig.session.red_stopped is True
    assert state["after"].held is TurnHold.INTAKE_STOPPED


def test_a_delivery_the_event_loop_cancels_is_recorded_and_retried_on_the_next_turn(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The loop goes away 50 ms into the stop (here: the run ends), which
    cancels every task, the delivery included. That is counted and logged by
    id, and the next turn — on the next loop — delivers the RED and raises."""
    rig = _rig(cancel_cost_ms=100.0)
    before = _watch_failures("cancelled")

    async def cut_short() -> None:
        rig.session.ensure_red_watch()
        await rig.clock.sleep(0.5)
        _push(rig)
        await rig.clock.sleep(0.05)

    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.talker.session"):
        rig.clock.run(cut_short())
    assert rig.channel.published == []
    assert _watch_failures("cancelled") == before + 1
    [logged] = [r for r in caplog.records if r.message == "pushed red delivery cancelled"]
    assert logged.__dict__["work_id"] == "w_red"
    with pytest.raises(_failed()) as failed:
        rig.clock.run(rig.session.take_turn("sentetik"))
    assert failed.value.work_ids == ("w_red",)
    assert [m.rule_id for m in rig.channel.published] == [RULE]
    assert rig.clock.run(rig.session.take_turn(None)).held is TurnHold.INTAKE_STOPPED


# --- the clinician route raising does not cost the patient the RED -------------------------------


@dataclass
class _RaisingClinic:
    calls: list[RedNotification] = field(default_factory=list)

    def notify(self, notification: RedNotification) -> None:
        self.calls.append(notification)
        raise ConnectionError("sentetik gelen kutusu arizasi")


def test_a_clinician_route_that_raises_costs_neither_the_stop_nor_the_trigger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = int093.Rig()
    rig.path.clinic = _RaisingClinic()
    before = _sample("clinic_red_inbox_route_failures_total", {})
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.red_path"):
        outcome = rig.trigger(int093.red_result(), evaluated_at_ms=0.0)
    assert rig.media.calls == ["cancel"]
    assert len(rig.channel.published) == 1
    assert outcome.notified_clinician is False
    assert outcome.violations == ()
    assert _sample("clinic_red_inbox_route_failures_total", {}) == before + 1
    [logged] = [r for r in caplog.records if r.message == "red clinic route failed"]
    assert logged.__dict__["work_id"] == "w_red"
    assert "sentetik gelen kutusu arizasi" not in caplog.text


def test_near_miss_a_clinician_route_that_answers_is_recorded_as_told() -> None:
    rig = int093.Rig()
    outcome = rig.trigger(int093.red_result(), evaluated_at_ms=0.0)
    assert outcome.notified_clinician is True
    assert len(rig.clinic.notifications) == 1
