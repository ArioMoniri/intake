"""INT-092 — the Backend Agent's Work queue (files/03 §4.3; files/12 §6, §7).

The issue's acceptance has three clauses and this module is organised around
them, plus the two CLAUDE.md invariants the queue is the load-bearing part of:

1. **"one Work in flight per session"** — :class:`TestFifoAndSingleInFlight`
   and :class:`TestSerializedSessionState`. files/03 §4.3: *"fed a FIFO Work
   queue; only one Work in flight per session; all writes to ``SessionState``
   serialised (queue lock + engine lock …)"*, amended by files/12 §7.4's lane
   split, which is what makes the clause mean *one slot-writing Work* rather
   than *one Work of any kind* — see docs/evidence/INT-092.md.
2. **"results {inline, speech_tr, priority}"** — :class:`TestResultShape`.
3. **"duplicates impossible (test)"** — :class:`TestIdempotent`, over both
   duplicate classes: a re-submitted transcript and a re-drained result.

- **Invariant 9 clause 2, the Talker never awaits Backend Work** —
  :class:`TestNeverOnTheSpeechCriticalPath`. The queue is the thing that could
  break it, so the proof is here as well as in INT-091's suite.
- **Invariant 9 clause 4, only a rules-engine RED may carry
  ``priority: preempt``** — :class:`TestPreemptIsDerivedNeverRequested`. The
  queue's answer is that no handler can *ask* for a priority: the effect types
  have no such field, and the background effect type cannot even express a
  triage determination.
- **Invariant 6, no PHI in logs, traces or metrics** —
  :class:`TestTheQueueHoldsNoPhi`.

Every id, slot and Turkish string here is synthetic and carries no clinical
meaning (files/04 §7). No test sleeps: contention is produced with barriers
and events, and virtual time comes from the INT-091 fake clock.
"""

from __future__ import annotations

import datetime
import inspect
import threading
from dataclasses import fields as dataclass_fields
from typing import Final

import pytest
from clinical_schemas.triage import (
    CandidateFlag,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from intake_voice_runtime.clinical_agent import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import (
    LANE_OF,
    BackendAgent,
    BackgroundEffect,
    EffectClass,
    QueueSealed,
    ReadOnlyContext,
    StateContext,
    StateEffect,
    UnregisteredWorkType,
    WorkLane,
    WorkRecord,
)
from intake_voice_runtime.ports import (
    WorkRequest,
    WorkState,
    WorkSubmitter,
    WorkType,
    work_key,
)
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import InlinePayload, Priority
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.types import Delivery, SlotType
from talker_harness import FakeClock, build_session, scripted_step

NOW = datetime.datetime(2026, 8, 30, 9, 0, tzinfo=datetime.UTC)
HASH: Final[str] = "0" * 64
SESSION = "11111111-2222-4333-8444-555555555555"
PINNED_RULE = "sentetik.kural.1"

#: A synthetic patient sentence. It exists only so a test can assert that it
#: never reaches the queue — the port carries ``input_hash``, not text.
TRANSCRIPT = "sentetik hasta cümlesi"

# --- the synthetic protocol -------------------------------------------------
#
# Four independent boolean slots in one section. Independence is the point:
# the FIFO tests need writes whose *order* is observable without a gate
# reordering them, and the engine binds nothing to a step that was not asked
# (INT-081), so each step is marked asked before its answer is submitted.


def _slot(**fields: object) -> Slot:
    return Slot.model_validate(fields)


def _resolved(key: str, slot: Slot) -> ResolvedSlot:
    return ResolvedSlot(
        section_id="oyku",
        key=key,
        fhir_link_id=f"oyku.{key}",
        slot=slot,
        delivery=Delivery.VOICE,
    )


STEP_IDS: Final[tuple[str, ...]] = (
    "oyku.a",
    "oyku.b",
    "oyku.c",
    "oyku.d",
    "oyku.e",
)


def _protocol() -> ResolvedProtocol:
    section = ResolvedSection(
        id="oyku",
        delivery=Delivery.VOICE,
        allow_paraphrase=False,
        slots=tuple(
            _resolved(
                step_id.split(".", 1)[1],
                _slot(
                    type=SlotType.INTEGER,
                    ask_tr=f"Sentetik soru {step_id}.",
                    follow_up_tr=f"Sentetik takip {step_id}.",
                ),
            )
            for step_id in STEP_IDS
        ),
    )
    return ResolvedProtocol(
        pack_id="base.sentetik_kuyruk",
        version="1.0.0",
        chain=("base.sentetik_kuyruk",),
        sections=(section,),
        resolved_protocol_hash=HASH,
    )


def _engine() -> IntakeEngine:
    return IntakeEngine(protocol=_protocol(), reference_time=NOW)


def _request(
    step_id: str = "oyku.a",
    *,
    work_type: WorkType = WorkType.EXTRACT_SLOTS,
    input_hash: str = "a" * 64,
    session_id: str = SESSION,
) -> WorkRequest:
    return WorkRequest(
        session_id=session_id,
        work_type=work_type,
        step_id=step_id,
        input_hash=input_hash,
        protocol_hash=HASH,
        engine_version=0,
    )


def _red(rule_id: str = PINNED_RULE) -> RulesTriageResult:
    return RulesTriageResult(
        level=TriageLevel.RED,
        rules=(RuleFire(id=rule_id, evidence="sentetik kanıt"),),
        register=RedRegister.CALM,
        location=RedLocation.REMOTE,
    )


def _agent(
    *,
    engine: IntakeEngine | None = None,
    rule_ids: frozenset[str] = frozenset({PINNED_RULE}),
) -> BackendAgent:
    return BackendAgent(session_id=SESSION, engine=engine or _engine(), rule_ids=rule_ids)


def _binding_agent(order: list[str] | None = None) -> BackendAgent:
    """An agent whose one state handler binds the step's answer to the engine.

    The bound value is the step's arrival index, so a reordered or lost write
    is visible in the engine's final state rather than only in a log.
    """
    agent = _agent()
    seen: list[str] = order if order is not None else []

    def bind(context: StateContext) -> StateEffect:
        seen.append(context.request.step_id)
        agent.engine.apply_extraction(context.request.step_id, {context.request.step_id: len(seen)})
        return StateEffect(inline=InlinePayload(section_progress={"oyku": len(seen)}))

    agent.register_state(WorkType.EXTRACT_SLOTS, bind)
    return agent


def _ask(engine: IntakeEngine, step_id: str) -> None:
    """Put the step into ASKED_PENDING so an answer may bind to it."""
    engine.mark_asked(step_id)


# ---------------------------------------------------------------------------
# 1. "one Work in flight per session"
# ---------------------------------------------------------------------------


class TestFifoAndSingleInFlight:
    """files/03 §4.6 invariant 5, and its files/12 §7.4 amendment."""

    def test_the_lane_of_every_work_type_is_declared(self) -> None:
        """A work type with no lane could not be routed, and a lane assigned at
        runtime would be a guess. files/12 §7.4 names both lanes."""
        assert set(LANE_OF) == set(WorkType)
        assert LANE_OF[WorkType.EXTRACT_SLOTS] is WorkLane.STATE
        assert LANE_OF[WorkType.PLAN_FOLLOW_UPS] is WorkLane.STATE
        assert LANE_OF[WorkType.PARSE_DOCUMENT] is WorkLane.BACKGROUND

    def test_state_work_runs_in_submission_order(self) -> None:
        order: list[str] = []
        agent = _binding_agent(order)
        for step_id in STEP_IDS[:3]:
            _ask(agent.engine, step_id)
            agent.submit(_request(step_id, input_hash=step_id))
        while agent.run_pending():
            pass
        assert order == list(STEP_IDS[:3])

    def test_at_most_one_state_work_is_in_flight(self) -> None:
        """The handler asks the agent, from inside itself, what is running."""
        agent = _agent()
        observed: list[tuple[str, ...]] = []

        def watcher(context: StateContext) -> StateEffect:
            observed.append(agent.in_flight)
            return StateEffect()

        agent.register_state(WorkType.EXTRACT_SLOTS, watcher)
        for step_id in STEP_IDS[:3]:
            agent.submit(_request(step_id, input_hash=step_id))
        while agent.run_pending():
            pass
        assert observed == [
            (work_key(_request(step_id, input_hash=step_id)),) for step_id in STEP_IDS[:3]
        ]

    def test_a_pump_re_entered_from_inside_a_handler_runs_nothing(self) -> None:
        """Re-entrancy is the single-threaded shape of contention."""
        agent = _agent()
        reentrant: list[int] = []

        def reenter(context: StateContext) -> StateEffect:
            reentrant.append(agent.run_pending())
            return StateEffect()

        agent.register_state(WorkType.EXTRACT_SLOTS, reenter)
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.submit(_request("oyku.b", input_hash="b"))
        agent.run_pending()
        assert reentrant == [0], "a nested pump ran a second state Work"

    def test_contention_refuses_and_leaves_the_head_of_the_queue_untouched(self) -> None:
        """The loser refuses; it never drops the item and never reorders it."""
        agent = _binding_agent()
        for step_id in STEP_IDS[:2]:
            _ask(agent.engine, step_id)
            agent.submit(_request(step_id, input_hash=step_id))

        with agent.engine_lock:
            assert agent.run_pending() == 0
            assert agent.depth(WorkLane.STATE) == 2
            assert agent.record(work_key(_request("oyku.a", input_hash="oyku.a"))).state is (
                WorkState.QUEUED
            )

        while agent.run_pending():
            pass
        assert agent.engine.value_of("oyku.a") == 1
        assert agent.engine.value_of("oyku.b") == 2

    def test_concurrent_submissions_lose_nothing(self) -> None:
        """files/03 §4.6 invariant 5 — RT-05's fast talker, as threads."""
        agent = _binding_agent()
        for step_id in STEP_IDS:
            _ask(agent.engine, step_id)
        barrier = threading.Barrier(len(STEP_IDS), timeout=10.0)

        def submit(step_id: str) -> None:
            barrier.wait()
            agent.submit(_request(step_id, input_hash=step_id))

        threads = [threading.Thread(target=submit, args=(step_id,)) for step_id in STEP_IDS]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10.0)

        assert agent.depth(WorkLane.STATE) == len(STEP_IDS)
        while agent.run_pending():
            pass
        assert sorted(agent.engine.value_of(step_id) for step_id in STEP_IDS) == [1, 2, 3, 4, 5]

    def test_a_background_work_does_not_head_of_line_block_the_state_lane(self) -> None:
        """files/12 §7.4: ``parse_document`` no longer participates."""
        agent = _binding_agent()
        ran: list[str] = []

        def read_only(context: ReadOnlyContext) -> BackgroundEffect:
            ran.append(context.request.step_id)
            return BackgroundEffect()

        agent.register_background(WorkType.PARSE_DOCUMENT, read_only)
        agent.submit(_request("oyku.e", work_type=WorkType.PARSE_DOCUMENT, input_hash="doc"))
        _ask(agent.engine, "oyku.a")
        agent.submit(_request("oyku.a", input_hash="oyku.a"))

        assert agent.run_pending() == 2, "the two lanes did not advance together"
        assert ran == ["oyku.e"]
        assert agent.engine.value_of("oyku.a") == 1

    def test_a_handler_may_only_be_registered_on_its_declared_lane(self) -> None:
        agent = _agent()
        with pytest.raises(ValueError, match="background lane"):
            agent.register_state(WorkType.PARSE_DOCUMENT, lambda _: StateEffect())
        with pytest.raises(ValueError, match="state lane"):
            agent.register_background(WorkType.EXTRACT_SLOTS, lambda _: BackgroundEffect())

    def test_work_with_no_registered_handler_is_refused_at_submit(self) -> None:
        """Fail closed: an unhandled Work would sit in the queue for ever."""
        agent = _agent()
        with pytest.raises(UnregisteredWorkType):
            agent.submit(_request("oyku.a"))

    def test_a_request_for_another_session_is_refused(self) -> None:
        agent = _binding_agent()
        with pytest.raises(ValueError, match="another session"):
            agent.submit(_request("oyku.a", session_id="99999999-2222-4333-8444-555555555555"))


class TestSerializedSessionState:
    """ "all writes to ``SessionState`` serialised" (files/03 §4.3)."""

    def test_background_work_cannot_reach_the_engine_at_all(self) -> None:
        """files/12 §9 invariant 21, as a shape rather than a rule.

        ``ReadOnlyContext`` has no mutator and no engine: a background handler
        cannot write a slot because it is never handed anything that could.
        """
        names = {field.name for field in dataclass_fields(ReadOnlyContext)}
        assert "engine" not in names
        assert names == {"request", "snapshot", "is_cancelled"}
        assert not any(
            name for name in vars(ReadOnlyContext) if name.startswith(("apply", "set", "write"))
        )

    def test_the_engine_is_only_touched_while_the_engine_lock_is_held(self) -> None:
        agent = _agent()
        held: list[bool] = []

        def probe(context: StateContext) -> StateEffect:
            held.append(agent.engine_lock.locked())
            return StateEffect()

        agent.register_state(WorkType.EXTRACT_SLOTS, probe)
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        assert held == [True]

    def test_submitting_never_waits_on_a_running_handler(self) -> None:
        """The queue lock and the engine lock are two locks, not one.

        If ``submit`` took the engine lock, the Talker would block for the
        whole of Layer B's work — invariant 9's second clause, broken by the
        queue rather than by the Talker.
        """
        agent = _agent()
        entered = threading.Event()
        release = threading.Event()

        def blocker(context: StateContext) -> StateEffect:
            entered.set()
            assert release.wait(timeout=10.0)
            return StateEffect()

        agent.register_state(WorkType.EXTRACT_SLOTS, blocker)
        first = agent.submit(_request("oyku.a", input_hash="a"))
        pump = threading.Thread(target=agent.run_pending)
        pump.start()
        try:
            assert entered.wait(timeout=10.0)
            ticket = agent.submit(_request("oyku.b", input_hash="b"))
            assert ticket.state is WorkState.QUEUED
            # The blocker is *still* inside its handler. Had ``submit`` taken
            # the engine lock it could only have returned after the handler
            # finished, and this would be empty.
            assert agent.in_flight == (first.work_id,)
        finally:
            release.set()
            pump.join(timeout=10.0)

    def test_the_final_state_matches_a_sequential_run(self) -> None:
        """RT-05: *"five answers submitted in 3 s … final slot state identical
        to sequential run"* (files/04 §7 runtime scenarios)."""
        sequential = _binding_agent()
        for step_id in STEP_IDS:
            _ask(sequential.engine, step_id)
            sequential.submit(_request(step_id, input_hash=step_id))
            sequential.run_pending()

        concurrent = _binding_agent()
        for step_id in STEP_IDS:
            _ask(concurrent.engine, step_id)
        barrier = threading.Barrier(len(STEP_IDS), timeout=10.0)

        def submit(step_id: str) -> None:
            barrier.wait()
            concurrent.submit(_request(step_id, input_hash=step_id))

        threads = [threading.Thread(target=submit, args=(step_id,)) for step_id in STEP_IDS]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10.0)
        while concurrent.run_pending():
            pass

        assert {step_id: concurrent.engine.state_of(step_id) for step_id in STEP_IDS} == {
            step_id: sequential.engine.state_of(step_id) for step_id in STEP_IDS
        }
        assert sorted(
            int(concurrent.engine.value_of(step_id) or 0) for step_id in STEP_IDS
        ) == sorted(int(sequential.engine.value_of(step_id) or 0) for step_id in STEP_IDS)


# ---------------------------------------------------------------------------
# 2. "results {inline, speech_tr, priority}"
# ---------------------------------------------------------------------------


class TestResultShape:
    def test_a_completed_result_carries_inline_speech_and_priority(self) -> None:
        agent = _agent()

        def answer(context: StateContext) -> StateEffect:
            return StateEffect(
                inline=InlinePayload(section_progress={"oyku": 1}),
                speech_tr="Sentetik geri bildirim.",
                effect_class=EffectClass.CLINICAL_INFO,
            )

        agent.register_state(WorkType.EXTRACT_SLOTS, answer)
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()

        assert result.state is WorkState.COMPLETED
        assert result.presentation.inline is not None
        assert result.presentation.speech_tr == "Sentetik geri bildirim."
        assert result.priority is Priority.NORMAL
        assert result.delivery_class is DeliveryClass.CLINICAL_INFO

    def test_a_yellow_is_delivered_as_triage_yellow_and_never_preempts(self) -> None:
        agent = _agent()
        yellow = RulesTriageResult(
            level=TriageLevel.YELLOW, rules=(RuleFire(id=PINNED_RULE, evidence="sentetik"),)
        )
        agent.register_state(WorkType.EXTRACT_SLOTS, lambda _: StateEffect(triage_update=yellow))
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.delivery_class is DeliveryClass.TRIAGE_YELLOW
        assert result.priority is Priority.NORMAL

    def test_a_failing_handler_produces_a_failed_receipt_not_an_exception(self) -> None:
        """files/03 §4.3: records are delivery receipts. One malformed result
        may not block the ones behind it."""
        agent = _agent()

        def boom(context: StateContext) -> StateEffect:
            raise RuntimeError("sentetik hata")

        agent.register_state(WorkType.EXTRACT_SLOTS, boom)
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.state is WorkState.FAILED
        assert result.presentation.speech_tr is None
        assert agent.record(result.work_id).error is not None

    def test_a_failing_background_handler_also_produces_a_receipt(self) -> None:
        """The background lane fails the same way the state lane does — one
        malformed document read may not stop the next one."""
        agent = _agent()

        def boom(context: ReadOnlyContext) -> BackgroundEffect:
            raise RuntimeError("sentetik belge hatası")

        agent.register_background(WorkType.PARSE_DOCUMENT, boom)
        agent.submit(_request("oyku.a", work_type=WorkType.PARSE_DOCUMENT, input_hash="doc"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.state is WorkState.FAILED
        assert agent.record(result.work_id).error == "RuntimeError"

    def test_a_receipt_is_refused_for_work_this_session_never_saw(self) -> None:
        agent = _binding_agent()
        with pytest.raises(LookupError):
            agent.record("w_yok")

    def test_a_spoken_number_without_its_inline_render_fails_the_work(self) -> None:
        """CLAUDE.md invariant 22, arriving through the queue rather than
        around it: the ``Presentation`` validator refuses, and the queue turns
        that refusal into a receipt instead of a crashed pump."""
        agent = _agent()
        agent.register_state(
            WorkType.EXTRACT_SLOTS,
            lambda _: StateEffect(speech_tr="Sentetik.", speech_numerics=("oyku.a",)),
        )
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.state is WorkState.FAILED

    def test_a_work_record_is_a_receipt_and_not_a_mirror_of_reasoning(self) -> None:
        agent = _binding_agent()
        _ask(agent.engine, "oyku.a")
        agent.submit(_request("oyku.a", input_hash="oyku.a"))
        agent.run_pending()
        record = agent.record(work_key(_request("oyku.a", input_hash="oyku.a")))
        assert isinstance(record, WorkRecord)
        assert {field.name for field in dataclass_fields(WorkRecord)} == {
            "request",
            "state",
            "enqueued_ms",
            "started_ms",
            "finished_ms",
            "error",
        }


# ---------------------------------------------------------------------------
# 3. "duplicates impossible"
# ---------------------------------------------------------------------------


class TestIdempotent:
    def test_the_same_transcript_submitted_twice_queues_once(self) -> None:
        """files/12 §7.5: ``work_id`` is derived, so a restart re-submitting the
        same transcript hits the dedupe instead of guaranteeing a duplicate."""
        agent = _binding_agent()
        _ask(agent.engine, "oyku.a")
        first = agent.submit(_request("oyku.a", input_hash="oyku.a"))
        second = agent.submit(_request("oyku.a", input_hash="oyku.a"))
        assert first.work_id == second.work_id
        assert agent.depth(WorkLane.STATE) == 1

    def test_a_completed_work_is_never_re_executed(self) -> None:
        agent = _binding_agent()
        _ask(agent.engine, "oyku.a")
        agent.submit(_request("oyku.a", input_hash="oyku.a"))
        agent.run_pending()
        agent.drain_results()

        ticket = agent.submit(_request("oyku.a", input_hash="oyku.a"))
        assert ticket.state is WorkState.COMPLETED
        assert agent.run_pending() == 0
        assert agent.drain_results() == ()
        assert agent.engine.value_of("oyku.a") == 1

    def test_each_result_is_drained_exactly_once(self) -> None:
        agent = _agent()
        agent.register_state(WorkType.EXTRACT_SLOTS, lambda _: StateEffect())
        for step_id in STEP_IDS[:3]:
            agent.submit(_request(step_id, input_hash=step_id))
        while agent.run_pending():
            pass
        assert len(agent.drain_results()) == 3
        assert agent.drain_results() == ()

    @settings(max_examples=60, deadline=None)
    @given(
        script=st.lists(
            st.tuples(
                st.sampled_from(STEP_IDS),
                st.sampled_from(("submit", "run", "drain")),
            ),
            min_size=1,
            max_size=40,
        )
    )
    def test_no_work_id_ever_executes_or_is_delivered_twice(
        self, script: list[tuple[str, str]]
    ) -> None:
        """The property behind *"duplicates impossible"*, over interleavings."""
        agent = _agent()
        executed: list[str] = []
        agent.register_state(
            WorkType.EXTRACT_SLOTS,
            lambda context: (executed.append(context.request.step_id), StateEffect())[1],
        )
        delivered: list[str] = []
        for step_id, action in script:
            if action == "submit":
                agent.submit(_request(step_id, input_hash=step_id))
            elif action == "run":
                agent.run_pending()
            else:
                delivered.extend(result.work_id for result in agent.drain_results())
        while agent.run_pending():
            pass
        delivered.extend(result.work_id for result in agent.drain_results())

        assert len(executed) == len(set(executed))
        assert len(delivered) == len(set(delivered))
        assert set(delivered) == {
            work_key(_request(step_id, input_hash=step_id)) for step_id in executed
        }


# ---------------------------------------------------------------------------
# invariant 9 clause 4 — only a rules-engine RED may carry preempt
# ---------------------------------------------------------------------------


class TestPreemptIsDerivedNeverRequested:
    def test_no_effect_type_has_a_priority_field(self) -> None:
        """A handler cannot ask for a priority, so no handler can ask for
        ``preempt``. The queue derives it from the determination instead."""
        assert "priority" not in StateEffect.model_fields
        assert "priority" not in BackgroundEffect.model_fields

    def test_a_background_effect_cannot_express_a_triage_determination(self) -> None:
        """files/12 §7.4: the background effect type cannot write state. It has
        no ``triage_update`` field at all, so the RED branch is unreachable
        from the lane that runs concurrently."""
        assert "triage_update" not in BackgroundEffect.model_fields
        assert "candidate_flags" in BackgroundEffect.model_fields
        assert "candidate_flags" not in StateEffect.model_fields

    def test_only_a_rules_engine_red_derives_preempt(self) -> None:
        agent = _agent()
        agent.register_state(WorkType.EXTRACT_SLOTS, lambda _: StateEffect(triage_update=_red()))
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.priority is Priority.PREEMPT
        assert result.delivery_class is DeliveryClass.RED

    def test_a_green_determination_never_preempts(self) -> None:
        agent = _agent()
        agent.register_state(
            WorkType.EXTRACT_SLOTS,
            lambda _: StateEffect(triage_update=RulesTriageResult(level=TriageLevel.GREEN)),
        )
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.priority is Priority.NORMAL

    def test_llm_candidate_flags_never_reach_preempt(self) -> None:
        agent = _agent()
        agent.register_background(
            WorkType.PARSE_DOCUMENT,
            lambda _: BackgroundEffect(
                candidate_flags=(CandidateFlag(text="sentetik aday", evidence="sentetik kanıt"),),
                speech_tr="Sentetik belge sonucu.",
            ),
        )
        agent.submit(_request("oyku.a", work_type=WorkType.PARSE_DOCUMENT, input_hash="doc"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.priority is Priority.NORMAL
        assert result.delivery_class is DeliveryClass.ROUTINE

    def test_a_red_naming_an_unpinned_rule_fails_the_work_and_speaks_nothing(self) -> None:
        """The provenance gate of files/03 §4.3, enforced before delivery.

        Downgrading it to ``normal`` would speak a RED as routine; the queue
        fails the Work instead, which is the fail-closed direction.
        """
        agent = _agent(rule_ids=frozenset({"sentetik.kural.baska"}))
        agent.register_state(WorkType.EXTRACT_SLOTS, lambda _: StateEffect(triage_update=_red()))
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.state is WorkState.FAILED
        assert result.priority is Priority.NORMAL
        assert result.presentation.speech_tr is None
        assert agent.sealed is False

    def test_an_unpinned_session_cannot_preempt_at_all(self) -> None:
        agent = _agent(rule_ids=frozenset())
        agent.register_state(WorkType.EXTRACT_SLOTS, lambda _: StateEffect(triage_update=_red()))
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.state is WorkState.FAILED


class TestRedSealsTheQueue:
    """files/12 §7.1 and §9 invariant 32."""

    def test_a_red_cancels_queued_work_and_refuses_new_submissions(self) -> None:
        agent = _agent()
        agent.register_state(
            WorkType.EXTRACT_SLOTS,
            lambda context: (
                StateEffect(triage_update=_red())
                if context.request.step_id == "oyku.a"
                else StateEffect()
            ),
        )
        agent.register_background(WorkType.PARSE_DOCUMENT, lambda _: BackgroundEffect())
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.submit(_request("oyku.b", input_hash="b"))
        queued_doc = agent.submit(
            _request("oyku.c", work_type=WorkType.PARSE_DOCUMENT, input_hash="doc")
        )

        agent.run_pending()

        assert agent.sealed is True
        assert agent.depth(WorkLane.STATE) == 0
        assert agent.depth(WorkLane.BACKGROUND) == 0
        assert agent.record(queued_doc.work_id).state is WorkState.CANCELLED
        with pytest.raises(QueueSealed):
            agent.submit(_request("oyku.d", input_hash="d"))

    def test_the_red_result_itself_survives_the_seal(self) -> None:
        agent = _agent()
        agent.register_state(WorkType.EXTRACT_SLOTS, lambda _: StateEffect(triage_update=_red()))
        agent.submit(_request("oyku.a", input_hash="a"))
        agent.run_pending()
        (result,) = agent.drain_results()
        assert result.priority is Priority.PREEMPT


class TestCancellation:
    """files/12 §7.1 — ``cancel_work`` makes ``cancelled`` reachable."""

    def test_a_queued_work_is_dequeued_synchronously(self) -> None:
        agent = _binding_agent()
        _ask(agent.engine, "oyku.a")
        ticket = agent.submit(_request("oyku.a", input_hash="oyku.a"))
        cancelled = agent.cancel(ticket.work_id, "hasta vazgeçti")
        assert cancelled.state is WorkState.CANCELLED
        assert agent.depth(WorkLane.STATE) == 0
        assert agent.run_pending() == 0
        assert agent.engine.value_of("oyku.a") is None

    def test_cancelling_is_idempotent(self) -> None:
        agent = _binding_agent()
        ticket = agent.submit(_request("oyku.a", input_hash="oyku.a"))
        agent.cancel(ticket.work_id, "bir")
        again = agent.cancel(ticket.work_id, "iki")
        assert again.state is WorkState.CANCELLED

    def test_cancelling_unknown_work_is_refused_rather_than_invented(self) -> None:
        agent = _binding_agent()
        with pytest.raises(LookupError):
            agent.cancel("w_yok", "sebep")

    def test_a_committed_state_write_stands_and_only_the_speech_is_suppressed(self) -> None:
        """files/12 §7.1: *"running state-lane work is never aborted mid-write
        — if it has committed, the write stands (you cannot un-know a red
        flag) and the effect is ``COMPLETED_SUPPRESSED``"*."""
        agent = _agent()
        entered = threading.Event()
        release = threading.Event()

        def commit_then_wait(context: StateContext) -> StateEffect:
            agent.engine.apply_extraction("oyku.a", {"oyku.a": 7})
            entered.set()
            assert release.wait(timeout=10.0)
            return StateEffect(
                inline=InlinePayload(section_progress={"oyku": 1}),
                speech_tr="Sentetik konuşma.",
            )

        agent.register_state(WorkType.EXTRACT_SLOTS, commit_then_wait)
        _ask(agent.engine, "oyku.a")
        ticket = agent.submit(_request("oyku.a", input_hash="oyku.a"))
        pump = threading.Thread(target=agent.run_pending)
        pump.start()
        try:
            assert entered.wait(timeout=10.0)
            running = agent.cancel(ticket.work_id, "hasta düzeltti")
            assert running.state is WorkState.RUNNING
        finally:
            release.set()
            pump.join(timeout=10.0)

        (result,) = agent.drain_results()
        assert agent.engine.value_of("oyku.a") == 7, "a committed write was rolled back"
        assert result.state is WorkState.COMPLETED
        assert result.presentation.speech_tr is None, "suppressed speech was still delivered"
        assert result.presentation.inline is not None, "the rail lost a committed update"

    def test_cancelling_cannot_suppress_a_rules_engine_red(self) -> None:
        """You cannot un-know a red flag (files/12 §7.1)."""
        agent = _agent()
        entered = threading.Event()
        release = threading.Event()

        def red_then_wait(context: StateContext) -> StateEffect:
            entered.set()
            assert release.wait(timeout=10.0)
            return StateEffect(triage_update=_red(), speech_tr="Sentetik kırmızı.")

        agent.register_state(WorkType.EXTRACT_SLOTS, red_then_wait)
        ticket = agent.submit(_request("oyku.a", input_hash="a"))
        pump = threading.Thread(target=agent.run_pending)
        pump.start()
        try:
            assert entered.wait(timeout=10.0)
            agent.cancel(ticket.work_id, "hasta vazgeçti")
        finally:
            release.set()
            pump.join(timeout=10.0)

        (result,) = agent.drain_results()
        assert result.priority is Priority.PREEMPT
        assert result.presentation.speech_tr == "Sentetik kırmızı."

    def test_a_cancelled_background_work_sees_the_cooperative_token(self) -> None:
        """files/12 §7.1: *"running background work honours a cooperative
        token"* — the token is the only cancellation channel it has."""
        agent = _agent()
        entered = threading.Event()
        release = threading.Event()
        observed: list[bool] = []

        def cooperative(context: ReadOnlyContext) -> BackgroundEffect:
            entered.set()
            assert release.wait(timeout=10.0)
            observed.append(context.is_cancelled())
            return BackgroundEffect()

        agent.register_background(WorkType.PARSE_DOCUMENT, cooperative)
        ticket = agent.submit(
            _request("oyku.a", work_type=WorkType.PARSE_DOCUMENT, input_hash="doc")
        )
        pump = threading.Thread(target=agent.run_pending)
        pump.start()
        try:
            assert entered.wait(timeout=10.0)
            agent.cancel(ticket.work_id, "hasta vazgeçti")
        finally:
            release.set()
            pump.join(timeout=10.0)
        assert observed == [True]


# ---------------------------------------------------------------------------
# invariant 9 clause 2 — the Talker never awaits Backend Work
# ---------------------------------------------------------------------------


class TestNeverOnTheSpeechCriticalPath:
    def test_the_agent_satisfies_the_work_port_with_no_awaitable_member(self) -> None:
        agent = _binding_agent()
        assert isinstance(agent, WorkSubmitter)
        for name in ("submit", "cancel", "drain_results", "run_pending"):
            assert not inspect.iscoroutinefunction(getattr(agent, name)), (
                f"BackendAgent.{name} is a coroutine — the Talker could await Backend Work"
            )

    def test_submitting_runs_nothing(self) -> None:
        agent = _agent()
        ran: list[str] = []
        agent.register_state(
            WorkType.EXTRACT_SLOTS,
            lambda context: (ran.append(context.request.step_id), StateEffect())[1],
        )
        agent.submit(_request("oyku.a", input_hash="a"))
        assert ran == []

    def test_a_deep_queue_does_not_change_the_turn(self) -> None:
        """RT-03 with the backlog rather than the stall: a thousand queued
        Works cost the Talker's turn exactly nothing, because nothing on the
        turn path pumps the queue."""

        def latency(pending: int) -> float:
            clock = FakeClock()
            agent = _agent()
            agent.register_state(WorkType.EXTRACT_SLOTS, lambda _: StateEffect())
            agent.register_background(WorkType.PARSE_DOCUMENT, lambda _: BackgroundEffect())
            for index in range(pending):
                agent.submit(
                    _request("oyku.a", work_type=WorkType.PARSE_DOCUMENT, input_hash=f"doc-{index}")
                )
            session = build_session(clock, steps=[scripted_step()], backend=agent)
            outcome = clock.run(session.take_turn(TRANSCRIPT))
            return float(outcome.elapsed_ms)

        assert latency(0) == latency(1_000)
        assert latency(0) > 0.0


# ---------------------------------------------------------------------------
# invariant 6 — no PHI in logs, traces or metrics
# ---------------------------------------------------------------------------


class TestTheQueueHoldsNoPhi:
    def test_the_work_record_carries_a_hash_and_never_the_transcript(self) -> None:
        """``WorkRequest`` carries ``input_hash``; the text never crosses the
        port, so the queue is PHI-free by construction rather than by
        redaction."""
        assert "transcript" not in WorkRequest.model_fields
        agent = _binding_agent()
        _ask(agent.engine, "oyku.a")
        ticket = agent.submit(_request("oyku.a", input_hash="oyku.a"))
        agent.run_pending()
        record = agent.record(ticket.work_id)
        assert TRANSCRIPT not in repr(record)
        assert TRANSCRIPT not in repr(agent.drain_results())

    def test_nothing_is_logged_that_is_not_an_id_or_a_closed_enum(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        agent = _binding_agent()
        _ask(agent.engine, "oyku.a")
        with caplog.at_level("DEBUG"):
            ticket = agent.submit(_request("oyku.a", input_hash="oyku.a"))
            agent.run_pending()
            agent.drain_results()
            agent.cancel(ticket.work_id, TRANSCRIPT)
        for record in caplog.records:
            assert TRANSCRIPT not in record.getMessage()
            assert "oyku.a" not in record.getMessage() or record.name.startswith(
                "intake_voice_runtime"
            )

    def test_metric_labels_are_closed_work_type_values(self) -> None:
        """CLAUDE.md invariant 6 and 13 together: the only label the queue can
        emit is a ``WorkType`` member, which is a closed enumeration."""
        from intake_voice_runtime import metrics

        for family in (
            metrics.WORK_QUEUE_DEPTH,
            metrics.WORK_LATENCY_MS,
            metrics.WORK_FAILED_TOTAL,
        ):
            assert family._labelnames == ("type",)
        agent = _binding_agent()
        _ask(agent.engine, "oyku.a")
        agent.submit(_request("oyku.a", input_hash="oyku.a"))
        agent.run_pending()
        observed = {
            sample.labels.get("type")
            for metric in metrics.WORK_QUEUE_DEPTH.collect()
            for sample in metric.samples
        }
        assert observed <= {work_type.value for work_type in WorkType}
