"""INT-531 — the push from Layer B to Layer A, and the bounded RED stop.

``tests/voice/test_red_between_turns.py`` holds the behaviour end to end over
the served session. This suite holds the parts, each with its near miss:

- **The port.** ``RedPush`` has one member and it is not awaitable, so Layer B
  can only post a RED; it can never call into the Talker or wait on it. The
  mailbox takes a rules-engine RED and nothing else, from any thread, and wakes
  the Talker's own loop without running anything on it.
- **Layer B.** The queue pushes a RED once it has settled it (and sealed, where
  the register stops the intake). A YELLOW, a GREEN, a candidate flag and a RED
  the preempt gate refused are never pushed. A push that raises costs the RED
  nothing: it is settled and the next turn's drain delivers it.
- **The Talker's watch.** It refuses to run without a RED path; it starts once
  per event loop; it refuses a pushed RED the session's pinned rules do not
  name (and keeps watching); a violation on the push route is counted, logged
  by id and the watch keeps serving; a RED pushed while the turn is delivering
  Layer B's own speech cuts it and the turn asks nothing.
- **The bounded stop** (INT-520 item 1). The path waits for the agent's audio
  to stop only until the stop budget runs out, then triggers; the cancel keeps
  running behind the trigger and still cuts the playback.
- **Composition.** Wherever a RED path is bound, both ends share one mailbox.

Everything is synthetic (files/04 §7); the clock is virtual unless a test
needs a second thread, and then it waits on nothing longer than a bounded
``asyncio.wait_for``.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import test_extraction_valuesets as int518
import test_invariants as int_rt
import test_live_triage as int521
import test_red_preemption as int093
import test_session_router as int182
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.clinical_agent.work_queue import BackgroundEffect, StateEffect
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.session_router import VoiceSessionRouter
from intake_voice_runtime.talker.delivery import DeliveryClass, DuplexState
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    PreemptRefused,
    Presentation,
    Priority,
)
from intake_voice_runtime.talker.red_path import (
    GENERIC_RED_SCRIPT_IDS,
    STOP_BUDGET_MS,
    MappingRedScriptIndex,
    RedPathNotWired,
    RedPathViolation,
    RedPreemption,
    RedViolation,
)
from intake_voice_runtime.talker.red_push import RedMailbox, RedPush
from intake_voice_runtime.talker.registry import assert_six_tool_surface
from intake_voice_runtime.talker.session import TalkerSession, TurnHold
from intake_voice_runtime.talker.tools import build_talker_tools
from prometheus_client import REGISTRY
from red_harness import (
    BLUEPRINT_DEVICE_OUTPUT_MS,
    BLUEPRINT_DOWNLINK_MS,
    MediaPlane,
    RecordingClinicNotifier,
    RecordingDataChannel,
)
from talker_harness import (
    FakeClock,
    RecordingSynthesizer,
    StalledBackend,
    build_session,
    scripted_step,
)

SRC = Path(__file__).resolve().parents[2] / "services" / "voice-runtime" / "src"
RUNTIME = SRC / "intake_voice_runtime"
RULE = int093.RULE_A
TRIGGER_LEG_MS = BLUEPRINT_DOWNLINK_MS + BLUEPRINT_DEVICE_OUTPUT_MS


def _red(
    work_id: str = "w_red",
    *,
    register: RedRegister = RedRegister.ALERT,
    rule_id: str = RULE,
    evaluated_at_ms: float = 0.0,
) -> BackendResult:
    """A rules-engine RED as Layer B settles it: stamped with its evaluation."""
    return int093.red_result(work_id=work_id, register=register, rule_id=rule_id).model_copy(
        update={"evaluated_at_ms": evaluated_at_ms}
    )


def _violations(violation: RedViolation) -> float:
    value = REGISTRY.get_sample_value(
        "preempt_red_violations_total", {"violation": violation.value}
    )
    return value or 0.0


# --- the port -------------------------------------------------------------------------------


def test_the_push_port_has_one_member_and_it_is_not_awaitable() -> None:
    """ADR-009's structural trick, the other way round: Layer B can post a
    RED and do nothing else — there is no member that could wait on the
    Talker or hand it a coroutine to run."""
    members = {
        name: value
        for name, value in vars(RedPush).items()
        if callable(value) and not name.startswith("_")
    }
    assert set(members) == {"push"}
    assert not inspect.iscoroutinefunction(members["push"])
    assert not inspect.iscoroutinefunction(RedMailbox.push)
    assert isinstance(RedMailbox(), RedPush)


@pytest.mark.parametrize(
    "module",
    [
        RUNTIME / "talker" / "red_push.py",
        RUNTIME / "clinical_agent" / "work_queue.py",
    ],
    ids=["red_push", "work_queue"],
)
def test_neither_end_of_the_push_can_reach_the_talker(module: Path) -> None:
    """No Backend coroutine calls into the Talker: neither the mailbox nor
    the queue imports or names the Talker's session."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("intake_voice_runtime.talker.session") for name in imported)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "TalkerSession" not in names


def _wired_session(clock: FakeClock, **kwargs: Any) -> tuple[TalkerSession, MediaPlane, Any]:
    """A Talker over doubles with the RED path and the mailbox bound."""
    media = MediaPlane(clock=clock)
    channel = RecordingDataChannel(clock=clock)
    session = build_session(clock, rule_ids=int093.PACK_RULES, sink=media, **kwargs)
    session.preemption = RedPreemption(
        canceller=media,
        channel=channel,
        clinic=RecordingClinicNotifier(),
        scripts=int093.SCRIPTS,
        clock=clock,
    )
    session.red_mailbox = RedMailbox()
    return session, media, channel


def test_a_push_returns_at_once_and_runs_nothing_on_the_talker() -> None:
    clock = FakeClock()
    session, media, channel = _wired_session(clock, steps=[scripted_step()])
    assert session.red_mailbox is not None
    session.red_mailbox.push(_red())
    assert clock.now_ms() == 0.0
    assert channel.published == []
    assert media.calls == []
    assert session.preempts == ()
    assert session.red_stopped is False


def test_a_push_from_another_thread_wakes_the_talkers_loop() -> None:
    """Layer B's pump may run on a worker thread: the post crosses into the
    Talker's loop without the thread touching anything that loop owns."""
    mailbox = RedMailbox()
    red = _red()

    async def main() -> tuple[BackendResult, ...]:
        taking = asyncio.ensure_future(mailbox.take())
        await asyncio.sleep(0)  # parked on the mailbox
        pusher = threading.Thread(target=mailbox.push, args=(red,))
        pusher.start()
        try:
            return await asyncio.wait_for(taking, timeout=5.0)
        finally:
            pusher.join(timeout=5.0)

    assert asyncio.run(main()) == (red,)


def test_a_red_pushed_before_the_watch_started_is_taken_at_once() -> None:
    mailbox = RedMailbox()
    first, second = _red("w_1"), _red("w_2")
    mailbox.push(first)
    mailbox.push(second)

    async def main() -> tuple[BackendResult, ...]:
        return await asyncio.wait_for(mailbox.take(), timeout=5.0)

    assert asyncio.run(main()) == (first, second)


def test_a_red_pushed_after_its_loop_closed_waits_for_the_next_loop() -> None:
    """A post to a loop that has gone is kept, never raised into Layer B."""
    mailbox = RedMailbox()

    async def take() -> tuple[BackendResult, ...]:
        return await asyncio.wait_for(mailbox.take(), timeout=5.0)

    mailbox.push(_red("w_1"))
    assert [r.work_id for r in asyncio.run(take())] == ["w_1"]
    mailbox.push(_red("w_2"))  # the first loop is closed now
    assert [r.work_id for r in asyncio.run(take())] == ["w_2"]


def test_a_stale_wake_up_with_nothing_posted_parks_the_next_take() -> None:
    """Near miss for the wake: two posts wake the loop twice and the first
    take empties the mailbox, so the second wake-up finds nothing. The next
    take parks until a RED is really there; it neither returns empty nor
    spins."""
    mailbox = RedMailbox()

    async def main() -> tuple[list[str], bool, list[str]]:
        first = asyncio.ensure_future(mailbox.take())
        await asyncio.sleep(0)  # parked: the mailbox is bound to this loop
        mailbox.push(_red("w_1"))
        mailbox.push(_red("w_2"))  # two wake-ups on their way
        taken = await asyncio.wait_for(first, timeout=5.0)
        for _ in range(4):
            await asyncio.sleep(0)  # the second wake-up lands on an empty mailbox
        parked = asyncio.ensure_future(mailbox.take())
        for _ in range(4):
            await asyncio.sleep(0)
        still_parked = not parked.done()
        mailbox.push(_red("w_3"))
        later = await asyncio.wait_for(parked, timeout=5.0)
        return [r.work_id for r in taken], still_parked, [r.work_id for r in later]

    taken, still_parked, later = asyncio.run(main())
    assert taken == ["w_1", "w_2"]
    assert still_parked is True
    assert later == ["w_3"]


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


def _green() -> BackendResult:
    return BackendResult(
        work_id="w_green",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.ROUTINE,
        presentation=Presentation(triage_update=RulesTriageResult(level=TriageLevel.GREEN)),
    )


def _forged_candidate_preempt() -> BackendResult:
    """An LLM candidate dressed as a preempt — unconstructable through the
    validator, so built around it, the way a bypass would have to be."""
    return BackendResult.model_construct(
        work_id="w_forged",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(
            triage_update=LlmCandidateTriage(
                candidate_flags=(CandidateFlag(text="Sentetik aday.", evidence="sentetik"),)
            )
        ),
        priority=Priority.PREEMPT,
        evaluated_at_ms=0.0,
    )


def _forged_yellow_preempt() -> BackendResult:
    return BackendResult.model_construct(
        work_id="w_forged_yellow",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=_yellow().presentation,
        priority=Priority.PREEMPT,
        evaluated_at_ms=0.0,
    )


@pytest.mark.parametrize(
    "result",
    [_yellow(), _green(), _forged_candidate_preempt(), _forged_yellow_preempt()],
    ids=["yellow", "green", "llm-candidate-as-preempt", "yellow-as-preempt"],
)
def test_near_miss_the_mailbox_takes_only_a_rules_engine_red(result: BackendResult) -> None:
    mailbox = RedMailbox()
    with pytest.raises(PreemptRefused):
        mailbox.push(result)

    async def main() -> bool:
        taking = asyncio.ensure_future(mailbox.take())
        for _ in range(4):
            await asyncio.sleep(0)
        parked = not taking.done()
        taking.cancel()
        return parked

    assert asyncio.run(main()) is True  # nothing was posted


# --- Layer B ---------------------------------------------------------------------------------


@dataclass
class _RecordingPush:
    """Layer B's end of the port, recording what was pushed and the queue's
    state at that moment."""

    agent: Any
    pushed: list[BackendResult] = field(default_factory=list)
    sealed_when_pushed: list[bool] = field(default_factory=list)

    def push(self, result: BackendResult) -> None:
        self.pushed.append(result)
        self.sealed_when_pushed.append(self.agent.sealed)


def _rules_red(register: RedRegister = RedRegister.ALERT) -> RulesTriageResult:
    return RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id=int_rt.RULE_A, evidence="sentetik"),),
        register=register,
        location=RedLocation.REMOTE,
    )


def _queue_stack(effect: StateEffect | None = None, **kwargs: Any) -> tuple[Any, _RecordingPush]:
    stack = int_rt.Stack(**kwargs)
    push = _RecordingPush(agent=stack.agent)
    stack.agent.red_push = push
    if effect is not None:
        stack.effects[int_rt.STEP_IDS[0]] = effect
    return stack, push


def test_layer_b_pushes_a_red_once_it_has_settled_and_sealed() -> None:
    stack, push = _queue_stack(StateEffect(triage_update=_rules_red()))
    ticket = stack.session.submit_utterance(int_rt.STEP_IDS[0], "sentetik yanit")
    stack.clock.run(stack.clock.sleep(0.25))
    stack.agent.run_pending()
    [pushed] = push.pushed
    assert pushed.work_id == ticket.work_id
    assert pushed.priority is Priority.PREEMPT
    assert pushed.evaluated_at_ms == 250.0
    assert push.sealed_when_pushed == [True]
    assert stack.agent.record(ticket.work_id).state is WorkState.COMPLETED
    # the same settlement is still in the results for the turn's drain
    assert [r.work_id for r in stack.agent.drain_results()] == [ticket.work_id]


def test_a_deferred_clinician_red_is_pushed_and_reaches_the_clinician_only() -> None:
    """A rules-engine RED whatever its register: the push carries it, and the
    path's register table decides what it does — the clinician is told, the
    patient surface is unchanged, the intake runs on. Because the intake runs
    on, the next turn drains the same RED: it is not handed to the path again."""
    stack = int_rt.Stack()
    stack.effects[int_rt.STEP_IDS[0]] = StateEffect(
        triage_update=_rules_red(RedRegister.DEFERRED_CLINICIAN)
    )
    mailbox = RedMailbox()
    stack.agent.red_push = mailbox
    stack.session.red_mailbox = mailbox
    stack.session.submit_utterance(int_rt.STEP_IDS[0], "sentetik yanit")

    async def scenario() -> None:
        assert stack.session.ensure_red_watch() is not None
        stack.agent.run_pending()
        await stack.clock.sleep(1.0)

    stack.clock.run(scenario())
    assert stack.agent.sealed is False
    assert [r.priority for r in stack.session.preempts] == [Priority.PREEMPT]
    assert stack.channel.published == []
    assert stack.media.calls == []
    assert len(stack.clinic.notifications) == 1
    assert stack.session.red_stopped is False
    after = stack.turn(None)  # drains the same settled RED
    assert after.drained_results == 1  # type: ignore[attr-defined]
    assert after.held is not TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert len(stack.session.preempts) == 1
    assert len(stack.clinic.notifications) == 1


@pytest.mark.parametrize(
    "effect",
    [
        StateEffect(
            speech_tr="Sentetik sarı bilgilendirme.",
            triage_update=RulesTriageResult(
                level=TriageLevel.YELLOW, rules=(RuleFire(id=int_rt.RULE_A, evidence="s"),)
            ),
        ),
        StateEffect(triage_update=RulesTriageResult(level=TriageLevel.GREEN)),
        StateEffect(),
    ],
    ids=["yellow", "green", "no-determination"],
)
def test_near_miss_layer_b_pushes_nothing_that_is_not_a_red(effect: StateEffect) -> None:
    stack, push = _queue_stack(effect, deadlines=int_rt.SYNTHETIC_TABLE)
    stack.session.submit_utterance(int_rt.STEP_IDS[0], "sentetik yanit")
    stack.agent.run_pending()
    assert push.pushed == []
    assert stack.agent.sealed is False


def test_near_miss_a_candidate_flag_from_the_background_lane_is_never_pushed() -> None:
    stack, push = _queue_stack()
    stack.background.append(
        BackgroundEffect(
            candidate_flags=(CandidateFlag(text="Sentetik aday işaret.", evidence="sentetik"),)
        )
    )
    stack.agent.submit(int_rt._document_request(0))
    stack.agent.run_pending()
    assert push.pushed == []


def test_near_miss_a_red_the_preempt_gate_refuses_is_never_pushed() -> None:
    """A RED naming a rule outside the session's pinned pack fails its Work at
    the queue's own gate; it never reaches the push."""
    stack, push = _queue_stack(
        StateEffect(triage_update=_rules_red()), rule_ids=frozenset({"rf.sentetik_baska"})
    )
    ticket = stack.session.submit_utterance(int_rt.STEP_IDS[0], "sentetik yanit")
    stack.agent.run_pending()
    assert push.pushed == []
    assert stack.agent.record(ticket.work_id).state is WorkState.FAILED


def test_a_push_that_raises_never_costs_the_red(caplog: pytest.LogCaptureFixture) -> None:
    """The push is the fast route, not the only one: a RED whose push raised
    is settled and sealed, logged by id alone, and the next turn delivers it."""

    @dataclass
    class _Raising:
        def push(self, result: BackendResult) -> None:
            raise RuntimeError("sentetik push arizasi")

    stack = int_rt.Stack()
    stack.agent.red_push = _Raising()
    stack.effects[int_rt.STEP_IDS[0]] = StateEffect(triage_update=_rules_red())
    ticket = stack.session.submit_utterance(int_rt.STEP_IDS[0], "sentetik yanit")
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.clinical_agent.work_queue"):
        stack.agent.run_pending()
    assert stack.agent.record(ticket.work_id).state is WorkState.COMPLETED
    assert stack.agent.sealed is True
    [record] = [r for r in caplog.records if r.message == "red push failed"]
    assert record.__dict__["work_id"] == ticket.work_id
    assert record.__dict__["error"] == "RuntimeError"
    assert "sentetik push arizasi" not in caplog.text
    after = stack.turn("sentetik yanit")
    assert after.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert [m.rule_id for m in stack.channel.published] == [int_rt.RULE_A]


# --- the Talker's watch ----------------------------------------------------------------------


def test_the_watch_refuses_to_run_without_a_red_path() -> None:
    clock = FakeClock()
    session, _, _ = _wired_session(clock, steps=[scripted_step()])
    session.preemption = None
    with pytest.raises(RedPathNotWired):
        clock.run(session.watch_reds())
    session, _, _ = _wired_session(clock, steps=[scripted_step()])
    session.red_mailbox = None
    with pytest.raises(RedPathNotWired):
        clock.run(session.watch_reds())


def test_the_watch_starts_once_per_loop_and_not_at_all_unwired() -> None:
    clock = FakeClock()
    session, _, _ = _wired_session(clock, steps=[scripted_step()])

    async def twice() -> tuple[object, object]:
        return session.ensure_red_watch(), session.ensure_red_watch()

    first, again = clock.run(twice())
    assert first is not None and first is again
    later, _ = clock.run(twice())
    assert later is not None and later is not first  # a new loop, a new watch
    unwired = build_session(clock, steps=[scripted_step()])

    async def none() -> object:
        return unwired.ensure_red_watch()

    assert clock.run(none()) is None


def test_a_turn_starts_the_watch() -> None:
    clock = FakeClock()
    session, _, _ = _wired_session(clock, steps=[scripted_step()])

    async def scenario() -> bool:
        await session.take_turn(None)
        watch = session.ensure_red_watch()
        return watch is not None and not watch.done()

    assert clock.run(scenario()) is True


def test_the_watch_stops_when_the_session_ends() -> None:
    """The watch never returns on its own. The router's end of a session
    cancels it, so an ended session leaves nothing parked on its mailbox;
    stopping twice, or ending a session the router does not know, is a no-op."""
    store = int182._store()
    int182._set(store, int518.TENANT, default_profile="residency_tr")
    rig = int521._rig(VoiceProfile.RESIDENCY_TR, {})
    router = VoiceSessionRouter(controls=store, clock=rig.clock)
    router.start(
        tenant_id=int518.TENANT,
        session_id=int518.SESSION,
        builders={profile: (lambda: rig.stack) for profile in VoiceProfile},
    )
    session = rig.stack.session

    async def scenario() -> tuple[bool, bool, bool]:
        watch = session.ensure_red_watch()
        assert watch is not None
        await asyncio.sleep(0)
        running = not watch.done()
        router.end(int518.SESSION)
        await asyncio.sleep(0)
        ended_by_the_router = watch.cancelled()
        router.end("bilinmeyen-oturum")
        session.stop_red_watch()  # again: a no-op
        return running, ended_by_the_router, router.live() == ()

    assert rig.clock.run(scenario()) == (True, True, True)


def _push_after(session: TalkerSession, clock: FakeClock, *reds: BackendResult) -> None:
    """Start the watch, push each RED in turn, let each land."""
    assert session.red_mailbox is not None
    mailbox = session.red_mailbox

    async def scenario() -> None:
        session.ensure_red_watch()
        for red in reds:
            await clock.sleep(1.0)
            mailbox.push(red.model_copy(update={"evaluated_at_ms": clock.now_ms()}))
        await clock.sleep(1.0)

    clock.run(scenario())


def test_a_pushed_red_naming_a_rule_outside_the_pack_is_refused_and_the_watch_serves_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The Talker's own provenance gate runs on the push route too: a RED the
    session's pinned rules do not name is refused — nothing stopped, nothing
    triggered — and logged by id; the next RED is still delivered."""
    clock = FakeClock()
    session, media, channel = _wired_session(clock, steps=[scripted_step()])
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.talker.session"):
        _push_after(session, clock, _red("w_foreign", rule_id="rf.sentetik_disari"), _red("w_ok"))
    [refused] = [r for r in caplog.records if r.message == "pushed red refused"]
    assert refused.__dict__["work_id"] == "w_foreign"
    assert [m.rule_id for m in channel.published] == [RULE]
    assert [r.work_id for r in session.preempts] == ["w_ok"]
    assert media.calls == ["cancel"]


def test_a_violation_on_the_push_route_is_counted_and_the_watch_serves_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """With nothing pre-positioned, the path shows the generic RED and raises
    SCRIPT_UNADDRESSABLE after delivering. The watch has no caller to raise
    to: it logs the violation by id and value, the count rises, and the next
    RED is delivered."""
    clock = FakeClock()
    session, _, channel = _wired_session(clock, steps=[scripted_step()])
    assert session.preemption is not None
    session.preemption.scripts = MappingRedScriptIndex(entries={})
    before = _violations(RedViolation.SCRIPT_UNADDRESSABLE)
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.talker.session"):
        _push_after(
            session, clock, _red("w_1"), _red("w_2", register=RedRegister.DEFERRED_CLINICIAN)
        )
    assert _violations(RedViolation.SCRIPT_UNADDRESSABLE) == before + 1
    [logged] = [r for r in caplog.records if r.message == "red path violation"]
    assert logged.__dict__["work_id"] == "w_1"
    assert logged.__dict__["violations"] == [RedViolation.SCRIPT_UNADDRESSABLE.value]
    assert [m.script_id for m in channel.published] == [GENERIC_RED_SCRIPT_IDS[RedLocation.REMOTE]]
    assert [r.work_id for r in session.preempts] == ["w_1", "w_2"]


def test_a_red_pushed_mid_backend_speech_cuts_it_and_the_turn_asks_nothing() -> None:
    """The turn is speaking Layer B's own YELLOW at its window when the RED is
    pushed: the playback is cut, the trigger goes, and the turn returns stopped
    without asking the question it would have asked next."""
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=0.0)
    backend.results = [_yellow()]
    synthesizer = RecordingSynthesizer()
    session, media, channel = _wired_session(
        clock, steps=[scripted_step()], backend=backend, synthesizer=synthesizer
    )
    media.ms_per_byte = 100.0  # 3.2 s of playback for the YELLOW
    session.observe_duplex(
        DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
    )
    assert session.red_mailbox is not None
    mailbox = session.red_mailbox

    async def layer_b() -> None:
        await clock.sleep(1.0)
        mailbox.push(_red(evaluated_at_ms=clock.now_ms()))

    async def scenario() -> Any:
        await backend.work()
        pushing = asyncio.ensure_future(layer_b())
        outcome = await session.take_turn(None)
        await pushing
        await clock.sleep(1.0)
        return outcome

    outcome = clock.run(scenario())
    assert outcome.held is TurnHold.INTAKE_STOPPED
    assert outcome.delivered_work_ids == ("w_yellow",)
    assert outcome.step_id is None and outcome.spoken_text == ""
    assert synthesizer.requests == ["Sentetik sarı bilgilendirme."]
    assert media.interrupted == ["w_yellow"]
    assert [m.rule_id for m in channel.published] == [RULE]


def test_the_composed_talker_with_the_push_keeps_exactly_six_tools() -> None:
    for profile in VoiceProfile:
        rig = int521._rig(profile, {})
        assert rig.stack.session.red_mailbox is not None
        assert_six_tool_surface(build_talker_tools(rig.stack.session))


# --- the bounded stop (INT-520 item 1) -------------------------------------------------------


def test_a_slow_cancel_cannot_hold_the_trigger_past_the_stop_budget() -> None:
    rig = int093.Rig(cancel_cost_ms=10_000.0)
    before = _violations(RedViolation.STOP_BUDGET)
    with pytest.raises(RedPathViolation) as breach:
        rig.trigger(int093.red_result(), evaluated_at_ms=0.0)
    outcome = breach.value.outcome
    assert breach.value.violations == (RedViolation.STOP_BUDGET,)
    assert outcome.stop_overran is True
    assert outcome.stopped_at_ms is None
    assert outcome.script_started_at_ms == pytest.approx(STOP_BUDGET_MS + TRIGGER_LEG_MS)
    assert len(rig.channel.published) == 1
    assert rig.media.calls == ["cancel"]
    assert _violations(RedViolation.STOP_BUDGET) == before + 1


def test_near_miss_a_cancel_inside_the_budget_is_waited_for() -> None:
    rig = int093.Rig(cancel_cost_ms=100.0)
    outcome = rig.trigger(int093.red_result(), evaluated_at_ms=0.0)
    assert outcome.stop_overran is False
    assert outcome.stop_ms == pytest.approx(100.0)
    assert outcome.script_started_at_ms == pytest.approx(100.0 + TRIGGER_LEG_MS)
    assert outcome.violations == ()


def test_a_red_already_past_its_stop_budget_triggers_without_waiting_for_the_cancel() -> None:
    """Delivered a second after its evaluation, the stop budget is already
    spent: the path starts the cancel and triggers at once rather than
    adding the cancel's 40 ms to a RED that is already late."""
    rig = int093.Rig(cancel_cost_ms=40.0)

    async def scenario() -> Any:
        await rig.clock.sleep(1.0)
        return await rig.path.trigger(int093.red_result(), evaluated_at_ms=0.0)

    with pytest.raises(RedPathViolation) as breach:
        rig.clock.run(scenario())
    outcome = breach.value.outcome
    assert outcome.stop_overran is True
    assert outcome.script_started_at_ms == pytest.approx(1_000.0 + TRIGGER_LEG_MS)
    assert set(breach.value.violations) == {RedViolation.STOP_BUDGET, RedViolation.E2E_BUDGET}


def test_the_cancel_still_runs_behind_the_trigger_and_cuts_the_playback() -> None:
    """The trigger does not wait for a slow cancel, and does not abandon it
    either: the agent's audio is still stopped when the cancel returns."""
    rig = int093.Rig(cancel_cost_ms=2_000.0)

    async def scenario() -> Any:
        playing = asyncio.ensure_future(rig.media.play(b"x" * 20_000, label="s1"))
        await rig.clock.sleep(0.1)
        with pytest.raises(RedPathViolation) as breach:
            await rig.path.trigger(int093.red_result(), evaluated_at_ms=rig.clock.now_ms())
        triggered_at = rig.clock.now_ms()
        await playing
        return breach.value.outcome, triggered_at, rig.clock.now_ms()

    outcome, triggered_at, cut_at = rig.clock.run(scenario())
    assert outcome.script_started_at_ms == pytest.approx(100.0 + STOP_BUDGET_MS + TRIGGER_LEG_MS)
    assert triggered_at == pytest.approx(outcome.script_started_at_ms)
    assert rig.media.interrupted == ["s1"]
    assert cut_at == pytest.approx(100.0 + 2_000.0)


# --- composition ----------------------------------------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_both_ends_of_the_push_share_one_mailbox_wherever_a_red_path_is(
    profile: VoiceProfile,
) -> None:
    rig = int521._rig(profile, {})
    assert isinstance(rig.stack.session.red_mailbox, RedMailbox)
    assert rig.stack.agent.red_push is rig.stack.session.red_mailbox


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_no_red_path_no_push(profile: VoiceProfile) -> None:
    stack = int518._compose(profile, protocol=int518._base_intake(), gateway=int518.AnswerTable({}))
    assert stack.session.preemption is None
    assert stack.session.red_mailbox is None
    assert stack.agent.red_push is None
