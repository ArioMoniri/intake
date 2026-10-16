"""INT-545 — a RED the session close raises reaches the patient's device.

GitHub #921, from the runtime review of the #920 merge (INT-531 + INT-540),
17 Oct 2026. ``VoiceSessionRouter.end()`` queued the session's close
(INT-540) and then stopped the Talker's between-turn RED watch (INT-531) at
once, so a RED the close raised — or a last answer still queued ahead of it —
reached the clinician route and never the device. Reproduced on both
profiles: 'Bilmiyorum.' to the onset question, the follow-up asked, ``end()``,
the pump runs the close → the clinic told of K2, nothing published.

What this suite holds, on both profiles, over the committed ``base.intake``
and the committed active ``base.life_threat`` rules (the reviewer's probe,
lifted, plus what review of the design found):

1. **The watch outlives the close.** After ``end()`` the watch is still
   running; the pump runs the close, K2 fires at the session's location, and
   the pre-positioned script starts within the 300 ms budget of the
   evaluation. The router releases the watch only once the close has been
   settled on two consecutive polls and the watch is idle: one poll leaves it
   running, the second cancels it and nothing is left closing.
2. **Near misses.** A quiet close releases the watch after two polls and
   triggers nothing. A session already sealed by a delivered RED stops its
   watch at ``end()``. A close that has not run holds the watch through any
   number of polls.
3. **The seal is not the delivery.** A RED sealed the queue in the same
   synchronous step as ``end()`` — posted, not yet taken — or the Backend is
   still inside the Work that sealed it (its engine lock held): either way the
   watch is held until it is idle, and the RED reaches the device.
4. **The clinician is told when the device was not reached.** A notification
   now states the device delivery, not only the register's intent: pending
   ahead of the trigger, withheld under ``DEFERRED_CLINICIAN``, and — when the
   session ends with a RED its watch could not deliver — not reached, by work
   id, counted and logged.
5. **The contract.** A watch that was never started is started by ``end()``
   or the next poll; a session id still closing cannot be started again.

Everything is synthetic (files/04 §7); the clock is virtual.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest
import test_anchor_unclear as int540
import test_invariants as int_rt
import test_onset_anchor as int522
import test_red_preemption as int093
import test_red_push as int531_push
import test_red_watch_failures as int531
import test_session_router as int182
from clinical_schemas.triage import RedLocation, RedRegister
from intake_platform.voice_control import VoiceControlReader
from intake_voice_runtime.clinical_agent.work_queue import StateEffect
from intake_voice_runtime.ports import WorkState, WorkType
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.session_router import VoiceSessionRouter
from intake_voice_runtime.talker.red_path import (
    E2E_BUDGET_MS,
    DeviceDelivery,
    RedNotification,
    RedPreemptionOutcome,
)
from intake_voice_runtime.talker.red_push import RedMailbox
from prometheus_client import REGISTRY
from pydantic import ValidationError
from red_harness import RecordingClinicNotifier
from talker_harness import FakeClock, build_session, scripted_step

K2 = int522.K2
ONSET = int522.ONSET
TENANT = int522.int518.TENANT
SESSION = int522.int518.SESSION


def _controls(profile: VoiceProfile) -> VoiceControlReader:
    """A control that routes the session onto ``profile``: an unreadable one
    starts it typed, a tenant defaulted to voice starts it on voice."""
    if profile is VoiceProfile.TYPED:
        return int540._Unreadable()
    store = int182._store()
    int182._set(store, TENANT, default_profile="residency_tr")
    return store


def _routed(
    profile: VoiceProfile,
    *,
    location: RedLocation = RedLocation.REMOTE,
    character: str = "baskı",
    first: str = "bilmiyorum-no-slot-no-flag",
) -> tuple[int522.Rig, VoiceSessionRouter]:
    rig = int522._rig(profile, int540._model(character, first), location=location)
    router = VoiceSessionRouter(controls=_controls(profile), clock=rig.clock)
    routed = router.start(
        tenant_id=TENANT,
        session_id=SESSION,
        builders={p: (lambda: rig.stack) for p in VoiceProfile},
    )
    assert routed.stack.profile is profile
    return rig, router


def _hedge_then_follow_up(rig: int522.Rig) -> None:
    """INT-540's abandonment: 'Bilmiyorum.', the follow-up spoken, then gone."""
    int522._lead(rig)
    int522._say(rig, ONSET, "Bilmiyorum.")
    rig.stack.session.ask_ledger.note_asked(int522._reentry(rig))


def _published(rig: int522.Rig) -> list[tuple[str, RedLocation]]:
    return [(m.rule_id, m.location) for m in rig.channel.published]


def _outcome(rig: int522.Rig, work_id: str) -> RedPreemptionOutcome:
    path = rig.stack.session.preemption
    assert path is not None
    return path._delivered[work_id]


def _deliveries(rig: int522.Rig) -> list[tuple[str, tuple[str, ...], DeviceDelivery]]:
    return [(n.work_id, n.rule_ids, n.delivery) for n in rig.clinic.notifications]


def _first_evaluation(rig: int522.Rig) -> float:
    return rig.clinic.notifications[0].evaluated_at_ms


def _watch_failures(kind: str) -> float:
    return REGISTRY.get_sample_value("red_watch_failures_total", {"kind": kind}) or 0.0


# --- 1 · the watch outlives the close ------------------------------------------------


@pytest.mark.parametrize("location", list(RedLocation))
@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_red_the_close_raises_after_end_reaches_the_device(
    profile: VoiceProfile, location: RedLocation
) -> None:
    rig, router = _routed(profile, location=location)
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.stack.session.ensure_red_watch()
        assert watch is not None
        _hedge_then_follow_up(rig)
        router.end(SESSION)
        await rig.clock.sleep(0)
        state["after_end"] = (not watch.done(), router.closing(), router.live())
        await rig.clock.sleep(0.5)
        rig.stack.agent.run_pending()  # the Backend pump runs the close
        state["evaluated"] = rig.clock.now_ms()
        await rig.clock.sleep(1.0)
        state["published"] = _published(rig)
        router.poll()
        await rig.clock.sleep(0)
        state["after_one_poll"] = (not watch.done(), router.closing())
        router.poll()
        await rig.clock.sleep(0)
        state["after_two_polls"] = (watch.cancelled(), router.closing())

    rig.clock.run(scenario())
    assert state["after_end"] == (True, (SESSION,), ())
    assert state["published"] == [(K2, location)]
    [red] = rig.stack.session.preempts
    assert rig.stack.agent.record(red.work_id).request.work_type is WorkType.CLOSE_SESSION
    outcome = _outcome(rig, red.work_id)
    assert outcome.evaluated_at_ms == state["evaluated"]
    assert outcome.script_started_at_ms is not None
    assert outcome.script_started_at_ms - state["evaluated"] <= E2E_BUDGET_MS
    assert outcome.violations == ()
    assert state["after_one_poll"] == (True, (SESSION,))
    assert state["after_two_polls"] == (True, ())
    # Layer B at the determination, the path before its trigger: both pending,
    # and nothing says the device was not reached, because it was.
    assert _deliveries(rig) == [
        (red.work_id, (K2,), DeviceDelivery.PENDING),
        (red.work_id, (K2,), DeviceDelivery.PENDING),
    ]


# --- 2 · near misses -------------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_quiet_close_releases_the_watch_after_two_polls(
    profile: VoiceProfile,
) -> None:
    """'başka bir his' with the onset asked and unanswered: the close resolves
    the anchor exactly as it does for 'baskı', and nothing fires."""
    rig, router = _routed(profile, character="başka bir his", first="no-slot-no-flag")
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.stack.session.ensure_red_watch()
        assert watch is not None
        int522._lead(rig)
        rig.stack.session.ask_ledger.note_asked(ONSET)
        router.end(SESSION)
        rig.stack.agent.run_pending()
        router.poll()
        await rig.clock.sleep(0)
        state["one"] = (watch.done(), router.closing())
        router.poll()
        await rig.clock.sleep(0)
        state["two"] = (watch.cancelled(), router.closing())

    rig.clock.run(scenario())
    assert state == {"one": (False, (SESSION,)), "two": (True, ())}
    int540._assert_resolved_unclear(rig)
    assert rig.channel.published == [] and rig.clinic.notifications == []
    assert rig.stack.agent.sealed is False


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_session_sealed_and_delivered_stops_the_watch_at_end(
    profile: VoiceProfile,
) -> None:
    """K2 fired at a first close and reached the device; the queue is sealed,
    so ``end()`` has nothing to queue and nothing left to wait for."""
    rig, router = _routed(profile, first="no-slot-no-flag")
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.stack.session.ensure_red_watch()
        assert watch is not None
        int522._lead(rig)
        rig.stack.session.ask_ledger.note_asked(ONSET)
        assert rig.stack.close() is not None
        rig.stack.agent.run_pending()  # K2 at the close: the queue seals
        await rig.clock.sleep(1.0)
        state["delivered"] = _published(rig)
        router.end(SESSION)
        await rig.clock.sleep(0)
        state["at_end"] = (watch.cancelled(), router.closing(), router.live())

    rig.clock.run(scenario())
    assert rig.stack.agent.sealed is True
    assert state == {"delivered": [(K2, RedLocation.REMOTE)], "at_end": (True, (), ())}


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_close_that_has_not_run_holds_the_watch_through_any_poll(
    profile: VoiceProfile,
) -> None:
    rig, router = _routed(profile)
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.stack.session.ensure_red_watch()
        assert watch is not None
        _hedge_then_follow_up(rig)
        router.end(SESSION)
        for _ in range(5):
            router.poll()
            await rig.clock.sleep(1.0)
        state["queued"] = (not watch.done(), router.closing())
        rig.stack.agent.run_pending()
        await rig.clock.sleep(1.0)
        router.poll()
        router.poll()
        await rig.clock.sleep(0)
        state["released"] = (watch.cancelled(), router.closing(), _published(rig))

    rig.clock.run(scenario())
    assert state == {
        "queued": (True, (SESSION,)),
        "released": (True, (), [(K2, RedLocation.REMOTE)]),
    }


# --- 3 · the seal is not the delivery -------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_red_that_sealed_the_queue_in_the_same_step_as_end_still_reaches_the_device(
    profile: VoiceProfile,
) -> None:
    """The pump runs on the Talker's loop and the worker ends the session in
    the same synchronous step: K2 is settled, the queue sealed and the RED
    posted, but the watch has not woken to take it. Stopping the watch at
    ``end()`` because the queue is sealed would leave the RED in the mailbox
    and the device unreached; the router holds it until it is idle."""
    rig, router = _routed(profile, first="no-slot-no-flag")
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.stack.session.ensure_red_watch()
        assert watch is not None
        await rig.clock.sleep(0)
        int522._lead(rig)
        rig.stack.session.ask_ledger.note_asked(ONSET)
        assert rig.stack.close() is not None
        rig.stack.agent.run_pending()  # sealed and posted ...
        router.end(SESSION)  # ... and ended before the watch woke
        state["at_end"] = (not watch.done(), router.closing(), rig.stack.close())
        await rig.clock.sleep(1.0)
        state["published"] = _published(rig)
        router.poll()
        await rig.clock.sleep(0)
        state["one"] = not watch.done()
        router.poll()
        await rig.clock.sleep(0)
        state["two"] = (watch.cancelled(), router.closing())

    rig.clock.run(scenario())
    assert state == {
        "at_end": (True, (SESSION,), None),
        "published": [(K2, RedLocation.REMOTE)],
        "one": True,
        "two": (True, ()),
    }


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_polls_while_the_closes_red_is_still_posted_hold_the_watch(
    profile: VoiceProfile,
) -> None:
    """The close has settled, twice over, but its RED is still in the mailbox,
    and then still in delivery (the trigger's downlink and device output):
    settled is not idle, so the watch is held until the RED has gone."""
    rig, router = _routed(profile)
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.stack.session.ensure_red_watch()
        assert watch is not None
        _hedge_then_follow_up(rig)
        router.end(SESSION)
        rig.stack.agent.run_pending()
        router.poll()
        router.poll()
        router.poll()
        state["posted"] = (not watch.done(), router.closing())
        await rig.clock.sleep(0.01)
        mailbox = rig.stack.session.red_mailbox
        assert mailbox is not None and mailbox.empty  # taken, not yet on the device
        router.poll()
        router.poll()
        state["in_delivery"] = (not watch.done(), router.closing(), _published(rig))
        await rig.clock.sleep(1.0)
        state["published"] = _published(rig)
        router.poll()
        await rig.clock.sleep(0)
        state["released"] = (watch.cancelled(), router.closing())

    rig.clock.run(scenario())
    on_the_wire = [(K2, RedLocation.REMOTE)]  # published, the script not yet started
    assert state == {
        "posted": (True, (SESSION,)),
        "in_delivery": (True, (SESSION,), on_the_wire),
        "published": on_the_wire,
        "released": (True, ()),
    }


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_sealed_session_whose_backend_is_still_inside_its_work_is_held(
    profile: VoiceProfile,
) -> None:
    """On a worker-thread pump the queue is sealed before the RED is posted,
    both inside the one state-lane Work that holds the engine lock. While it is
    held, a sealed queue's RED may still be on its way to the mailbox, so the
    watch is held; once it is free, the release rule applies."""
    rig, router = _routed(profile, first="no-slot-no-flag")
    state: dict[str, Any] = {}

    async def scenario() -> None:
        watch = rig.stack.session.ensure_red_watch()
        assert watch is not None
        int522._lead(rig)
        rig.stack.session.ask_ledger.note_asked(ONSET)
        assert rig.stack.close() is not None
        rig.stack.agent.run_pending()
        await rig.clock.sleep(1.0)
        lock = rig.stack.agent.engine_lock
        assert lock.acquire(blocking=False)
        try:
            router.end(SESSION)
            router.poll()
            router.poll()
            await rig.clock.sleep(0)
            state["while_held"] = (not watch.done(), router.closing())
        finally:
            lock.release()
        router.poll()
        await rig.clock.sleep(0)
        state["once_free"] = (watch.cancelled(), router.closing())

    rig.clock.run(scenario())
    assert state == {"while_held": (True, (SESSION,)), "once_free": (True, ())}


# --- 4 · the clinician is told when the device was not reached ------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_close_red_the_device_was_not_reached_with_is_told_to_the_clinician(
    profile: VoiceProfile, caplog: pytest.LogCaptureFixture
) -> None:
    """The data channel fails under the close's RED. Before the session ended
    the next turn would have retried it; after, nothing will. So the release
    tells the clinician route, by work id, that the device was not reached,
    counts it and logs it by id."""
    rig, router = _routed(profile)
    rig.channel.publish_raises = ConnectionError("sentetik veri kanali arizasi")
    before = _watch_failures("unreached")
    state: dict[str, Any] = {}

    async def scenario() -> None:
        assert rig.stack.session.ensure_red_watch() is not None
        _hedge_then_follow_up(rig)
        router.end(SESSION)
        rig.stack.agent.run_pending()
        await rig.clock.sleep(1.0)
        state["before_release"] = _deliveries(rig)
        router.poll()
        router.poll()
        await rig.clock.sleep(0)
        state["closing"] = router.closing()

    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.talker.session"):
        rig.clock.run(scenario())
    [red] = rig.stack.session.preempts
    pending = (red.work_id, (K2,), DeviceDelivery.PENDING)
    assert state["before_release"] == [pending, pending]
    assert _deliveries(rig) == [pending, pending, (red.work_id, (K2,), DeviceDelivery.NOT_REACHED)]
    told = rig.clinic.notifications[-1]
    assert (told.register, told.location, told.patient_facing, told.silent_generic) == (
        RedRegister.ALERT,
        RedLocation.REMOTE,
        True,
        False,
    )
    assert told.evaluated_at_ms == _first_evaluation(rig)
    assert state["closing"] == ()
    assert _watch_failures("unreached") == before + 1
    [logged] = [r for r in caplog.records if r.message == "red never reached the device"]
    assert logged.__dict__["work_id"] == red.work_id
    assert "sentetik veri kanali arizasi" not in caplog.text


def test_near_miss_a_red_the_watch_delivered_is_never_told_unreached() -> None:
    """Ending the RED watch with nothing left undelivered tells nobody anything."""
    rig = int531._rig()

    async def scenario() -> tuple[str, ...]:
        rig.session.ensure_red_watch()
        await asyncio.sleep(0)
        _post(rig, "w_ok")
        await rig.clock.sleep(1.0)
        return rig.session.end_red_watch()

    assert rig.clock.run(scenario()) == ()
    assert [m.rule_id for m in rig.channel.published] == [int093.RULE_A]
    assert [n.delivery for n in rig.clinic.notifications] == [DeviceDelivery.PENDING]


def test_ending_the_watch_twice_tells_the_clinician_once() -> None:
    rig = int531._rig(publish_raises=ConnectionError("sentetik"))

    async def scenario() -> tuple[tuple[str, ...], tuple[str, ...]]:
        rig.session.ensure_red_watch()
        await asyncio.sleep(0)
        _post(rig, "w_lost")
        await rig.clock.sleep(1.0)
        return rig.session.end_red_watch(), rig.session.end_red_watch()

    assert rig.clock.run(scenario()) == (("w_lost",), ())
    assert [(n.work_id, n.delivery) for n in rig.clinic.notifications] == [
        ("w_lost", DeviceDelivery.PENDING),
        ("w_lost", DeviceDelivery.NOT_REACHED),
    ]


def _ahead_of_the_trigger(register: RedRegister) -> DeviceDelivery:
    if register is RedRegister.DEFERRED_CLINICIAN:
        return DeviceDelivery.WITHHELD
    return DeviceDelivery.PENDING


@pytest.mark.parametrize("register", list(RedRegister))
def test_the_path_tells_the_clinician_pending_or_withheld_ahead_of_its_trigger(
    register: RedRegister,
) -> None:
    """``patient_facing`` is the register's intent; ``delivery`` is what the
    device has been given. Ahead of the trigger nothing has been: a register
    that triggers the device is pending, ``DEFERRED_CLINICIAN`` is withheld."""
    rig = int093.Rig()
    rig.trigger(int093.red_result(register=register), evaluated_at_ms=0.0)
    [notice] = rig.clinic.notifications
    assert (notice.delivery, notice.patient_facing) == (
        _ahead_of_the_trigger(register),
        register is not RedRegister.DEFERRED_CLINICIAN,
    )


@pytest.mark.parametrize("register", list(RedRegister))
def test_layer_b_tells_the_clinician_pending_or_withheld_at_the_determination(
    register: RedRegister,
) -> None:
    stack = int_rt.Stack()
    clinic = RecordingClinicNotifier()
    stack.agent.clinic = clinic
    stack.effects[int_rt.STEP_IDS[0]] = StateEffect(triage_update=int531_push._rules_red(register))
    stack.session.submit_utterance(int_rt.STEP_IDS[0], "sentetik yanit")
    stack.agent.run_pending()
    [notice] = clinic.notifications
    assert (notice.delivery, notice.patient_facing) == (
        _ahead_of_the_trigger(register),
        register is not RedRegister.DEFERRED_CLINICIAN,
    )


def test_not_reached_is_told_only_for_a_register_that_triggers_the_device() -> None:
    """``DEFERRED_CLINICIAN`` is withheld by design: there is no device delivery
    to have failed, so ``not_reached`` tells nothing."""
    rig = int093.Rig()
    rig.path.not_reached(
        int093.red_result(register=RedRegister.DEFERRED_CLINICIAN), evaluated_at_ms=0.0
    )
    assert rig.clinic.notifications == []
    rig.path.not_reached(int093.red_result(register=RedRegister.CALM), evaluated_at_ms=7.0)
    [notice] = rig.clinic.notifications
    assert (notice.delivery, notice.register, notice.evaluated_at_ms, notice.patient_facing) == (
        DeviceDelivery.NOT_REACHED,
        RedRegister.CALM,
        7.0,
        True,
    )


def test_a_clinician_route_that_raises_on_not_reached_is_counted_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = int093.Rig()

    class _Raising:
        def notify(self, notification: RedNotification) -> None:
            raise ConnectionError("sentetik gelen kutusu arizasi")

    rig.path.clinic = _Raising()
    before = REGISTRY.get_sample_value("clinic_red_inbox_route_failures_total", {}) or 0.0
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.red_path"):
        rig.path.not_reached(int093.red_result(work_id="w_x"), evaluated_at_ms=0.0)
    after = REGISTRY.get_sample_value("clinic_red_inbox_route_failures_total", {}) or 0.0
    assert after == before + 1
    [logged] = [r for r in caplog.records if r.message == "red clinic route failed"]
    assert logged.__dict__["work_id"] == "w_x"
    assert "sentetik gelen kutusu arizasi" not in caplog.text


def _notification(**fields: Any) -> RedNotification:
    base: dict[str, Any] = {
        "work_id": "w_red",
        "rule_ids": (int093.RULE_A,),
        "register": RedRegister.ALERT,
        "location": RedLocation.REMOTE,
        "evaluated_at_ms": 0.0,
        "patient_facing": True,
        "delivery": DeviceDelivery.PENDING,
    }
    base.update(fields)
    return RedNotification(**base)


def test_the_delivery_has_no_default_and_agrees_with_the_register() -> None:
    _notification()
    _notification(delivery=DeviceDelivery.NOT_REACHED)
    _notification(
        register=RedRegister.DEFERRED_CLINICIAN,
        patient_facing=False,
        delivery=DeviceDelivery.WITHHELD,
    )
    _notification(register=RedRegister.SILENT, silent_generic=True)
    unset = {
        "work_id": "w_red",
        "rule_ids": (int093.RULE_A,),
        "register": RedRegister.ALERT,
        "location": RedLocation.REMOTE,
        "evaluated_at_ms": 0.0,
        "patient_facing": True,
    }
    with pytest.raises(ValidationError):
        RedNotification(**unset)
    for refused in (
        {"delivery": DeviceDelivery.WITHHELD},
        {"patient_facing": False},
        {"patient_facing": False, "delivery": DeviceDelivery.NOT_REACHED},
        {"silent_generic": True, "delivery": DeviceDelivery.NOT_REACHED},
    ):
        with pytest.raises(ValidationError):
            _notification(**refused)


# --- 5 · the contract -----------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_end_on_the_loop_starts_a_watch_that_was_never_started(profile: VoiceProfile) -> None:
    """No turn ran on this loop, so no watch: ``end()`` on the loop starts one,
    and the close's RED reaches the device in budget."""
    rig, router = _routed(profile)

    async def scenario() -> list[tuple[str, RedLocation]]:
        _hedge_then_follow_up(rig)
        router.end(SESSION)
        rig.stack.agent.run_pending()
        await rig.clock.sleep(1.0)
        return _published(rig)

    assert rig.clock.run(scenario()) == [(K2, RedLocation.REMOTE)]
    [red] = rig.stack.session.preempts
    assert _outcome(rig, red.work_id).violations == ()


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_session_ended_off_the_loop_is_watched_from_the_next_poll(
    profile: VoiceProfile,
) -> None:
    """``end()`` called where no event loop runs cannot start a watch; the
    router's poll, which runs on the loop, does."""
    rig, router = _routed(profile)
    _hedge_then_follow_up(rig)
    router.end(SESSION)
    assert rig.stack.session.red_watch_idle is True  # nothing posted yet, no watch

    async def scenario() -> tuple[list[tuple[str, RedLocation]], tuple[str, ...]]:
        rig.stack.agent.run_pending()
        router.poll()
        await rig.clock.sleep(1.0)
        router.poll()
        router.poll()
        await rig.clock.sleep(0)
        return _published(rig), router.closing()

    assert rig.clock.run(scenario()) == ([(K2, RedLocation.REMOTE)], ())


def test_a_session_id_still_closing_cannot_be_started_again() -> None:
    rig, router = _routed(VoiceProfile.TYPED)
    _hedge_then_follow_up(rig)
    router.end(SESSION)
    assert router.closing() == (SESSION,)
    with pytest.raises(ValueError, match="already been started"):
        router.start(
            tenant_id=TENANT,
            session_id=SESSION,
            builders={p: (lambda: rig.stack) for p in VoiceProfile},
        )


def test_a_cancelled_close_is_settled() -> None:
    """The release rule waits for the close to finish, not to succeed:
    CANCELLED (and FAILED) settle it as COMPLETED does."""
    rig, router = _routed(VoiceProfile.TYPED)
    _hedge_then_follow_up(rig)
    router.end(SESSION)
    ticket = rig.stack.close()  # content-addressed: the close end() queued
    assert ticket is not None
    rig.stack.agent.cancel(ticket.work_id, "sentetik")
    assert rig.stack.agent.record(ticket.work_id).state is WorkState.CANCELLED
    router.poll()
    assert router.closing() == (SESSION,)
    router.poll()
    assert router.closing() == ()


# --- the parts ----------------------------------------------------------------------------


def test_the_mailbox_says_whether_anything_waits_to_be_taken() -> None:
    mailbox = RedMailbox()
    assert mailbox.empty is True
    mailbox.push(int093.red_result())
    assert mailbox.empty is False

    async def take() -> int:
        return len(await mailbox.take())

    assert asyncio.run(take()) == 1
    assert mailbox.empty is True


def test_the_watch_is_idle_only_with_nothing_posted_and_nothing_in_delivery() -> None:
    rig = int531._rig(cancel_cost_ms=100.0)
    seen: list[bool] = []

    async def scenario() -> None:
        rig.session.ensure_red_watch()
        await asyncio.sleep(0)
        seen.append(rig.session.red_watch_idle)
        _post(rig, "w_red")
        seen.append(rig.session.red_watch_idle)  # posted, not taken
        await rig.clock.sleep(0.05)
        seen.append(rig.session.red_watch_idle)  # taken, mid-stop
        await rig.clock.sleep(1.0)
        seen.append(rig.session.red_watch_idle)  # delivered

    rig.clock.run(scenario())
    assert seen == [True, False, False, True]
    assert [m.rule_id for m in rig.channel.published] == [int093.RULE_A]


def test_a_session_with_no_red_path_is_always_idle_and_ends_with_nothing_to_tell() -> None:
    session = build_session(FakeClock(), steps=[scripted_step()])
    assert session.red_mailbox is None and session.red_watch_idle is True
    assert session.end_red_watch() == ()


def _post(rig: int531.Rig, work_id: str) -> None:
    mailbox = rig.session.red_mailbox
    assert isinstance(mailbox, RedMailbox)
    mailbox.push(
        int093.red_result(work_id=work_id).model_copy(
            update={"evaluated_at_ms": rig.clock.now_ms()}
        )
    )
