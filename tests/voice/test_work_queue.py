"""INT-092 — the Backend Agent's FIFO Work queue (files/03 §4.3, §4.6).

Acceptance, verbatim from ``docs/backlog/issues.yaml``:

    "one Work in flight per session; results {inline,speech_tr,priority};
    duplicates impossible (test)"

files/03 §4.3 is the sentence the queue implements: *"One persistent agent
context per session … fed a **FIFO Work queue**; only **one Work in flight per
session**; all writes to ``SessionState`` serialised (queue lock + engine lock
— qwen-audio-agent's 'double guard')."*

The four clauses of CLAUDE.md invariant 9 are already pinned by
``test_six_tools``, ``test_talker_never_awaits``, ``test_red_preempt_only`` and
``test_talker_session``; this suite asserts the *Backend* half of each of them
holds once a real queue is on the other side of the port:

- the queue is Layer B, so serving it costs the Talker no seventh tool and no
  awaitable member;
- FIFO, one in flight, and no lost or reordered slot write (files/03 §4.6
  invariant 5);
- delivery is idempotent on ``work_id`` — the same Work never runs twice and
  never speaks twice, including when two pumps race (invariant 6);
- only a rules-engine RED may carry ``preempt``, with the two near-miss
  negative controls: a non-RED result claiming it, and an LLM-originated
  result claiming RED;
- a numeric value spoken without its ``inline`` render is **refused**, not
  repaired (CLAUDE.md invariant 22; files/03 §4.6 invariant 30);
- scripts cross the queue byte-for-byte (invariant 10);
- the public Work record carries no transcript and no session id (invariants 6
  and files/03 §4.6 invariant 10), and the queue retains no audio (invariant 3).

Every handler here is a test double. The extraction model is INT-095 and the
queue takes its handlers by injection, so nothing in the shipped module
pretends to be one (CLAUDE.md invariant 17).
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Awaitable, Callable

import pytest
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.ports import (
    EngineSnapshot,
    WorkRequest,
    WorkState,
    WorkSubmitter,
    WorkType,
    work_key,
)
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.insertion import DuplexState
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    InlinePayload,
    Priority,
)
from intake_voice_runtime.talker.registry import assert_six_tool_surface
from intake_voice_runtime.talker.tools import build_talker_tools
from intake_voice_runtime.work_queue import (
    ACTIVITY_LABELS_TR,
    RED_SEALED_WORK_TYPES,
    QueueSealedError,
    ReadOnlyContext,
    WorkFailure,
    WorkOutcome,
    WorkQueue,
    WorkRecord,
)
from talker_harness import FakeClock, build_session, scripted_step

SESSION_ID = "11111111-2222-4333-8444-555555555555"
PROTOCOL_HASH = "a" * 64
PACK_RULES = frozenset({"rf.gogus_agrisi_akut", "rf.kanama"})

#: A red-flag action script, already tr-expanded by the compiler (invariant
#: 22): no numeral reaches a TTS model, so "112" is spelled out.
RED_SCRIPT_TR = "Telefonu bırakmayın. Hemen yüz on ikiyi arayın."

RULES_RED = RulesTriageResult(
    level=TriageLevel.RED,
    rules=(RuleFire(id="rf.gogus_agrisi_akut", evidence="gogus_agrisi=evet"),),
    register=RedRegister.ALERT,
    location=RedLocation.REMOTE,
)
RULES_RED_UNPINNED = RulesTriageResult(
    level=TriageLevel.RED,
    rules=(RuleFire(id="rf.uydurma_kural", evidence="gogus_agrisi=evet"),),
    register=RedRegister.ALERT,
    location=RedLocation.REMOTE,
)
RULES_YELLOW = RulesTriageResult(
    level=TriageLevel.YELLOW,
    rules=(RuleFire(id="rf.kanama", evidence="kanama=evet"),),
)
LLM_CANDIDATE = LlmCandidateTriage(
    candidate_flags=(CandidateFlag(text="olası kanama", evidence="hastanın ifadesi"),)
)


# --- doubles -------------------------------------------------------------------------


class FakeEngine:
    """The Layer-B write side, recorded. Structurally an IntakeEngine."""

    def __init__(self) -> None:
        self.applied: list[tuple[str, dict[str, object], bool]] = []
        self.states: dict[str, AnswerState] = {}
        self._version = 1
        #: Set while ``apply_extraction`` is running, so a test can prove the
        #: engine is never re-entered concurrently.
        self.inside = 0
        self.max_inside = 0

    @property
    def snapshot(self) -> EngineSnapshot:
        return EngineSnapshot(version=self._version, next_step=None)

    def apply_extraction(
        self,
        step_id: str,
        slot_updates: object,
        clarification_needed: bool = False,
    ) -> None:
        self.inside += 1
        self.max_inside = max(self.max_inside, self.inside)
        updates = dict(slot_updates)  # type: ignore[call-overload]
        self.applied.append((step_id, updates, clarification_needed))
        for key in updates:
            self.states[key] = AnswerState.ASKED_PRESENT
        self._version += 1
        self.inside -= 1


Handler = Callable[[ReadOnlyContext, WorkRequest], Awaitable[WorkOutcome]]


def request(
    step_id: str = "s1",
    transcript: str = "iki gündür ağrıyor",
    work_type: WorkType = WorkType.EXTRACT_SLOTS,
) -> WorkRequest:
    return WorkRequest(
        session_id=SESSION_ID,
        work_type=work_type,
        step_id=step_id,
        input_hash=hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        protocol_hash=PROTOCOL_HASH,
        engine_version=1,
    )


def outcome(**overrides: object) -> WorkOutcome:
    fields: dict[str, object] = {"delivery_class": DeliveryClass.TRIAGE_YELLOW}
    fields.update(overrides)
    return WorkOutcome(**fields)  # type: ignore[arg-type]


def constant_handler(result: WorkOutcome) -> Handler:
    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        return result

    return handler


def build_queue(
    *,
    clock: FakeClock | None = None,
    engine: FakeEngine | None = None,
    handlers: dict[WorkType, Handler] | None = None,
    rule_ids: frozenset[str] = PACK_RULES,
) -> tuple[WorkQueue, FakeEngine, FakeClock]:
    the_clock = clock or FakeClock()
    the_engine = engine or FakeEngine()
    queue = WorkQueue(
        session_id=SESSION_ID,
        engine=the_engine,
        clock=the_clock,
        handlers={WorkType.EXTRACT_SLOTS: constant_handler(outcome())}
        if handlers is None
        else handlers,
        rule_ids=rule_ids,
    )
    return queue, the_engine, the_clock


# --- the queue is Layer B ---------------------------------------------------------------


def test_the_queue_satisfies_the_work_submitter_port() -> None:
    queue, _, _ = build_queue()
    assert isinstance(queue, WorkSubmitter)


def test_no_member_the_talker_calls_is_awaitable() -> None:
    """ADR-009: the Talker never awaits Backend Work, so the three members it
    reaches must be ordinary functions even on the real queue."""
    for name in ("submit", "cancel", "drain_results"):
        member = getattr(WorkQueue, name)
        assert not inspect.iscoroutinefunction(member), (
            f"WorkQueue.{name} is a coroutine — the Talker could await Backend Work "
            "(CLAUDE.md invariant 9)"
        )


def test_serving_the_queue_costs_the_talker_no_seventh_tool() -> None:
    clock = FakeClock()
    queue, _, _ = build_queue(clock=clock)
    session = build_session(clock, steps=[scripted_step()], backend=queue)
    assert_six_tool_surface(build_talker_tools(session))


# --- FIFO, one in flight, serialised writes (files/03 §4.6 invariant 5) -----------------


def test_work_runs_in_submission_order() -> None:
    order: list[str] = []

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        order.append(req.step_id)
        return outcome(slot_updates={req.step_id: "evet"})

    queue, engine, clock = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    for step_id in ("s1", "s2", "s3", "s4"):
        queue.submit(request(step_id=step_id))

    asyncio.run(queue.run_pending())

    assert order == ["s1", "s2", "s3", "s4"]
    assert [step for step, _, _ in engine.applied] == ["s1", "s2", "s3", "s4"]


def test_only_one_work_is_ever_in_flight() -> None:
    seen: list[int] = []

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        seen.append(len(queue.in_flight_work_ids))
        await asyncio.sleep(0)
        seen.append(len(queue.in_flight_work_ids))
        return outcome()

    queue, _, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    for step_id in ("s1", "s2", "s3"):
        queue.submit(request(step_id=step_id))

    asyncio.run(queue.run_pending())

    assert seen == [1, 1, 1, 1, 1, 1]


def test_two_pumps_racing_never_run_two_works_at_once() -> None:
    concurrent = 0
    peak = 0

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        nonlocal concurrent, peak
        concurrent += 1
        peak = max(peak, concurrent)
        await asyncio.sleep(0)
        concurrent -= 1
        return outcome(slot_updates={req.step_id: "evet"})

    queue, engine, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    for index in range(8):
        queue.submit(request(step_id=f"s{index}"))

    async def scenario() -> None:
        await asyncio.gather(queue.run_pending(), queue.run_pending(), queue.run_pending())

    asyncio.run(scenario())

    assert peak == 1, "two Works were in flight for one session"
    assert engine.max_inside == 1, "SessionState was written from two places at once"
    assert [step for step, _, _ in engine.applied] == [f"s{index}" for index in range(8)]


def test_no_slot_update_is_lost_or_reordered_under_interleaved_submission() -> None:
    """files/03 §4.6 invariant 5, as a property over interleaved submissions."""

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        await asyncio.sleep(0)
        return outcome(slot_updates={req.step_id: req.engine_version})

    queue, engine, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    expected = [f"s{index}" for index in range(25)]

    async def scenario() -> None:
        pump = asyncio.ensure_future(queue.run_pending())
        for step_id in expected:
            queue.submit(request(step_id=step_id))
            await asyncio.sleep(0)
        await pump
        await queue.run_pending()

    asyncio.run(scenario())

    assert [step for step, _, _ in engine.applied] == expected
    assert set(engine.states) == set(expected)


# --- duplicates impossible ------------------------------------------------------------


def test_the_same_work_submitted_twice_runs_once() -> None:
    runs = 0

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        nonlocal runs
        runs += 1
        return outcome(speech_tr="Anladım.")

    queue, _, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    first = queue.submit(request())
    second = queue.submit(request())

    assert first.work_id == second.work_id == work_key(request())

    asyncio.run(queue.run_pending())

    assert runs == 1
    assert len(queue.drain_results()) == 1


def test_concurrently_submitted_duplicates_run_once_and_deliver_once() -> None:
    runs = 0

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        nonlocal runs
        runs += 1
        await asyncio.sleep(0)
        return outcome(speech_tr="Anladım.")

    queue, _, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})

    async def scenario() -> None:
        async def submitter() -> None:
            for _ in range(5):
                queue.submit(request())
                await asyncio.sleep(0)

        await asyncio.gather(
            submitter(),
            submitter(),
            queue.run_pending(),
            queue.run_pending(),
        )
        await queue.run_pending()

    asyncio.run(scenario())

    assert runs == 1, "the same work_id ran more than once"
    results = queue.drain_results()
    assert [result.work_id for result in results] == [work_key(request())]


def test_a_resubmitted_transcript_after_restart_does_not_run_again() -> None:
    """files/12 §7.5: ``work_id`` is derived, not minted, so the dedupe works
    across a restart instead of guaranteeing a duplicate on every one."""
    runs = 0

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        nonlocal runs
        runs += 1
        return outcome(speech_tr="Anladım.")

    queue, _, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    queue.submit(request())
    asyncio.run(queue.run_pending())

    ticket = queue.submit(request())
    asyncio.run(queue.run_pending())

    assert runs == 1
    assert ticket.state is WorkState.COMPLETED


def test_each_result_drains_exactly_once() -> None:
    queue, _, _ = build_queue(
        handlers={WorkType.EXTRACT_SLOTS: constant_handler(outcome(speech_tr="Anladım."))}
    )
    queue.submit(request())
    asyncio.run(queue.run_pending())

    assert len(queue.drain_results()) == 1
    assert queue.drain_results() == ()


# --- result shape {inline, speech_tr, priority} -----------------------------------------


def test_a_completed_work_carries_inline_speech_and_priority() -> None:
    inline = InlinePayload(section_progress={"sikayet": 2}, numeric_values={"sure_gun": "iki"})
    queue, _, _ = build_queue(
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(
                    inline=inline,
                    speech_tr="Şikâyetiniz iki gündür sürüyor, doğru mu?",
                    speech_numerics=("sure_gun",),
                )
            )
        }
    )
    queue.submit(request())
    asyncio.run(queue.run_pending())

    (result,) = queue.drain_results()
    assert isinstance(result, BackendResult)
    assert result.presentation.inline == inline
    assert result.presentation.speech_tr == "Şikâyetiniz iki gündür sürüyor, doğru mu?"
    assert result.priority is Priority.NORMAL
    assert result.state is WorkState.COMPLETED


# --- preemption: only a rules-engine RED (invariant 9 clause 4) --------------------------


def test_a_rules_engine_red_from_the_pinned_pack_may_preempt() -> None:
    queue, _, _ = build_queue(
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(
                    delivery_class=DeliveryClass.RED,
                    speech_tr=RED_SCRIPT_TR,
                    triage_update=RULES_RED,
                    priority=Priority.PREEMPT,
                )
            )
        }
    )
    queue.submit(request())
    asyncio.run(queue.run_pending())

    (result,) = queue.drain_results()
    assert result.priority is Priority.PREEMPT


@pytest.mark.parametrize(
    ("triage", "why"),
    [
        (RULES_YELLOW, "a rules-engine YELLOW is not a RED"),
        (None, "no determination at all"),
        (LLM_CANDIDATE, "an LLM candidate tops out at YELLOW_REVIEW"),
    ],
)
def test_a_non_red_result_claiming_preempt_is_refused(triage: object, why: str) -> None:
    """The near-miss negative control: the same shape, one field different."""
    queue, _, _ = build_queue(
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(
                    delivery_class=DeliveryClass.RED,
                    speech_tr=RED_SCRIPT_TR,
                    triage_update=triage,
                    priority=Priority.PREEMPT,
                )
            )
        }
    )
    ticket = queue.submit(request())
    asyncio.run(queue.run_pending())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.FAILED, why
    assert record.failure is WorkFailure.RESULT_REFUSED
    assert queue.drain_results() == (), "a refused preempt must not be delivered"


def test_an_llm_originated_result_cannot_even_spell_red() -> None:
    """CLAUDE.md invariant 1 at type level: ``LlmCandidateTriage`` has exactly
    one level and it is not RED, so the refusal above is structural."""
    assert LLM_CANDIDATE.level == "YELLOW_REVIEW"
    assert LLM_CANDIDATE.level != TriageLevel.RED
    assert LLM_CANDIDATE.source == "llm_candidate"


def test_a_red_naming_a_rule_outside_the_pinned_pack_is_refused() -> None:
    queue, _, _ = build_queue(
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(
                    delivery_class=DeliveryClass.RED,
                    speech_tr=RED_SCRIPT_TR,
                    triage_update=RULES_RED_UNPINNED,
                    priority=Priority.PREEMPT,
                )
            )
        }
    )
    ticket = queue.submit(request())
    asyncio.run(queue.run_pending())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.FAILED
    assert record.failure is WorkFailure.PREEMPT_REFUSED
    assert queue.drain_results() == ()


def test_an_unpinned_session_authorises_no_preempt() -> None:
    queue, _, _ = build_queue(
        rule_ids=frozenset(),
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(
                    delivery_class=DeliveryClass.RED,
                    speech_tr=RED_SCRIPT_TR,
                    triage_update=RULES_RED,
                    priority=Priority.PREEMPT,
                )
            )
        },
    )
    ticket = queue.submit(request())
    asyncio.run(queue.run_pending())

    assert queue.record(ticket.work_id).failure is WorkFailure.PREEMPT_REFUSED


# --- invariant 22: numbers never cross a boundary unguarded -------------------------------


def test_speech_stating_a_number_with_no_inline_render_is_refused() -> None:
    queue, engine, _ = build_queue(
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(
                    slot_updates={"sure_gun": 2},
                    speech_tr="Şikâyetiniz iki gündür sürüyor.",
                    speech_numerics=("sure_gun",),
                )
            )
        }
    )
    ticket = queue.submit(request())
    asyncio.run(queue.run_pending())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.FAILED
    assert record.failure is WorkFailure.RESULT_REFUSED
    assert queue.drain_results() == ()
    assert engine.applied == [], "a refused result is refused whole, never repaired"


def test_the_same_speech_with_its_inline_render_is_accepted() -> None:
    queue, engine, _ = build_queue(
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(
                    slot_updates={"sure_gun": 2},
                    inline=InlinePayload(numeric_values={"sure_gun": "iki"}),
                    speech_tr="Şikâyetiniz iki gündür sürüyor.",
                    speech_numerics=("sure_gun",),
                )
            )
        }
    )
    queue.submit(request())
    asyncio.run(queue.run_pending())

    (result,) = queue.drain_results()
    assert result.presentation.inline is not None
    assert result.presentation.inline.numeric_values == {"sure_gun": "iki"}
    assert engine.applied == [("s1", {"sure_gun": 2}, False)]


# --- invariant 10: scripts cross the queue verbatim ----------------------------------------


@pytest.mark.parametrize(
    "script",
    [
        RED_SCRIPT_TR,
        "Hemen en yakın acil servise gidin.",
        "Son iki haftada kendinizi üzgün ya da umutsuz hissettiniz mi?",
    ],
)
def test_the_queue_carries_a_script_through_byte_for_byte(script: str) -> None:
    """CLAUDE.md invariant 10: the queue is a conduit, never a rewriter — it
    does not paraphrase, trim, normalise or re-case what it carries."""
    queue, _, _ = build_queue(
        handlers={WorkType.EXTRACT_SLOTS: constant_handler(outcome(speech_tr=script))}
    )
    queue.submit(request())
    asyncio.run(queue.run_pending())

    (result,) = queue.drain_results()
    assert result.presentation.speech_tr == script


# --- cancellation and restart (files/03 §4.3; files/12 §7.1) -------------------------------


def test_a_queued_work_is_dequeued_synchronously_on_cancel() -> None:
    runs = 0

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        nonlocal runs
        runs += 1
        return outcome()

    queue, _, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    keep = queue.submit(request(step_id="s1"))
    drop = queue.submit(request(step_id="s2"))

    ticket = queue.cancel(drop.work_id, reason="patient retracted")

    assert ticket.state is WorkState.CANCELLED
    assert queue.pending_work_ids == (keep.work_id,)

    asyncio.run(queue.run_pending())
    assert runs == 1


def test_a_running_work_is_never_aborted_mid_write_and_completes_suppressed() -> None:
    """files/12 §7.1: *"running state-lane work is never aborted mid-write —
    if it has committed, the write stands … and the effect is
    ``COMPLETED_SUPPRESSED``, so a patient retraction becomes a supersession,
    not a deletion."*"""
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        started.set()
        await release.wait()
        return outcome(slot_updates={"sure_gun": 2}, speech_tr="Anladım.")

    queue, engine, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    ticket = queue.submit(request())

    async def scenario() -> None:
        pump = asyncio.ensure_future(queue.run_pending())
        await started.wait()
        queue.cancel(ticket.work_id, reason="patient retracted")
        release.set()
        await pump

    asyncio.run(scenario())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.COMPLETED_SUPPRESSED
    assert engine.applied == [("s1", {"sure_gun": 2}, False)], "the committed write must stand"
    assert queue.drain_results() == (), "a suppressed result is never spoken"


def test_cancelling_an_unknown_work_id_raises() -> None:
    queue, _, _ = build_queue()
    with pytest.raises(LookupError):
        queue.cancel("w_nope", reason="typo")


def test_restart_fails_active_work_with_a_closed_reason() -> None:
    """files/03 §4.3: *"active Work becomes ``failed(reason=restart)``;
    completed results and delivery state are persisted."*"""
    queue, _, _ = build_queue()
    done = queue.submit(request(step_id="s1"))
    asyncio.run(queue.run_pending())
    queued = queue.submit(request(step_id="s2"))

    failed = queue.fail_active_work_on_restart()

    assert failed == (queued.work_id,)
    assert queue.record(queued.work_id).failure is WorkFailure.RESTART
    assert queue.record(done.work_id).state is WorkState.COMPLETED
    assert queue.pending_work_ids == ()


def test_red_seals_the_queue() -> None:
    """files/12 §7.1: on RED the queue is sealed after cancelling queued work.
    The three work types the seal admits — ``note_finalize``,
    ``clinic_notify``, ``audit_flush`` — do not exist on this branch, so the
    allow-list is empty and the seal refuses everything (fail closed)."""
    queue, _, _ = build_queue()
    queued = queue.submit(request(step_id="s2"))

    cancelled = queue.seal_for_red()

    assert cancelled == (queued.work_id,)
    assert queue.record(queued.work_id).state is WorkState.CANCELLED
    assert RED_SEALED_WORK_TYPES == frozenset()
    with pytest.raises(QueueSealedError):
        queue.submit(request(step_id="s3"))


# --- failure paths -------------------------------------------------------------------------


def test_a_missing_handler_fails_the_work_with_a_closed_reason() -> None:
    queue, _, _ = build_queue(handlers={})
    ticket = queue.submit(request())
    asyncio.run(queue.run_pending())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.FAILED
    assert record.failure is WorkFailure.NO_HANDLER
    assert queue.drain_results() == ()


def test_a_handler_error_fails_the_work_and_carries_no_detail() -> None:
    transcript = "iki gündür göğsümde baskı var"

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        raise RuntimeError(transcript)

    queue, _, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    ticket = queue.submit(request(transcript=transcript))
    asyncio.run(queue.run_pending())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.FAILED
    assert record.failure is WorkFailure.HANDLER_ERROR
    assert transcript not in record.model_dump_json()


def test_a_work_for_another_session_is_refused() -> None:
    queue, _, _ = build_queue()
    foreign = WorkRequest(
        session_id="99999999-2222-4333-8444-555555555555",
        work_type=WorkType.EXTRACT_SLOTS,
        step_id="s1",
        input_hash="0" * 64,
        protocol_hash=PROTOCOL_HASH,
        engine_version=1,
    )
    with pytest.raises(ValueError, match="session"):
        queue.submit(foreign)


def test_a_document_parse_may_not_write_slots() -> None:
    """files/12 §7.4: a document's facts reach the record through a confirm
    step, never through a write from the work that read the document."""
    queue, engine, _ = build_queue(
        handlers={
            WorkType.PARSE_DOCUMENT: constant_handler(
                outcome(slot_updates={"hemoglobin": "10,2"}, speech_tr="Belgeyi okudum.")
            )
        }
    )
    ticket = queue.submit(request(work_type=WorkType.PARSE_DOCUMENT))
    asyncio.run(queue.run_pending())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.FAILED
    assert record.failure is WorkFailure.RESULT_REFUSED
    assert engine.applied == []


# --- invariants 3, 6 and files/03 §4.6 invariant 10 ------------------------------------------


def test_the_public_work_record_carries_no_transcript_and_no_session_id() -> None:
    transcript = "iki gündür göğsümde baskı var"
    queue, _, _ = build_queue()
    ticket = queue.submit(request(transcript=transcript))
    asyncio.run(queue.run_pending())

    record = queue.record(ticket.work_id)
    rendered = record.model_dump_json()
    assert transcript not in rendered
    assert SESSION_ID not in rendered
    assert "session_id" not in set(WorkRecord.model_fields)


def test_the_activity_label_table_is_fixed_and_only_the_blueprint_fills_it() -> None:
    """files/03 §4.6 invariant 10: labels come from a fixed table. Only the
    string files/03 §4.3 states verbatim is in it; the rest is patient-facing
    copy no human has signed off, so it stays unset rather than invented."""
    assert ACTIVITY_LABELS_TR == {WorkType.PARSE_DOCUMENT: "belge okunuyor"}

    queue, _, _ = build_queue()
    ticket = queue.submit(request())
    assert queue.record(ticket.work_id).activity_label_tr is None


def test_the_queue_retains_no_audio() -> None:
    queue, _, _ = build_queue()
    queue.submit(request())
    asyncio.run(queue.run_pending())
    assert queue.retained_frames() == 0


def test_the_queue_has_no_observer_lane_surface() -> None:
    """CLAUDE.md invariant 11: lanes write ``ObserverState`` only. There is no
    work type, handler slot or method on this queue through which a lane could
    write a slot or a triage."""
    assert {member.value for member in WorkType} == {
        "extract_slots",
        "plan_follow_ups",
        "parse_document",
    }
    surface = {name for name in dir(WorkQueue) if not name.startswith("_")}
    assert not {name for name in surface if "lane" in name or "observer" in name}
    assert not hasattr(WorkOutcome, "triage_level")


def test_a_lane_stalled_thirty_seconds_does_not_delay_the_queue() -> None:
    """CLAUDE.md invariant 11 on the fake clock: a lane parked for 30 s leaves
    the queue's completion time exactly where it was without one."""

    def elapsed(with_lane: bool) -> float:
        clock = FakeClock()
        queue, _, _ = build_queue(clock=clock)
        queue.submit(request())

        async def scenario() -> float:
            lane = asyncio.ensure_future(clock.sleep(30.0)) if with_lane else None
            await queue.run_pending()
            finished = clock.now_ms()
            if lane is not None:
                lane.cancel()
            return finished

        return float(clock.run(scenario()))

    assert elapsed(with_lane=True) == elapsed(with_lane=False)


# --- delivery, through the real Talker ---------------------------------------------------------


def test_a_result_reaches_the_patient_only_at_a_safe_insertion_window() -> None:
    """files/03 §4.3: ``inline`` goes out at once; ``speech_tr`` waits for the
    window. The Talker drains the queue on its own turn and never awaits it."""
    clock = FakeClock()
    queue, _, _ = build_queue(
        clock=clock,
        handlers={
            WorkType.EXTRACT_SLOTS: constant_handler(
                outcome(speech_tr="Anladığım kadarıyla ağrı iki gündür sürüyor.")
            )
        },
    )
    session = build_session(clock, steps=[scripted_step()], backend=queue)
    session.observe_duplex(
        DuplexState(patient_silence_ms=0.0, talker_idle=False, pending_response=True)
    )

    async def scenario() -> tuple[int, int]:
        await session.take_turn("iki gündür ağrıyor")
        await queue.run_pending()
        closed = await session.take_turn(None)
        session.observe_duplex(
            DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
        )
        opened = await session.take_turn(None)
        return len(closed.delivered_work_ids), len(opened.delivered_work_ids)

    while_closed, while_open = clock.run(scenario())

    assert while_closed == 0, "Backend speech interrupted the patient"
    assert while_open == 1


def test_the_turn_budget_survives_a_queue_whose_handler_stalls() -> None:
    """ADR-009 with a real queue behind the port instead of a double."""

    def turn_latency(stall_s: float) -> float:
        clock = FakeClock()

        async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
            await clock.sleep(stall_s)
            return outcome(speech_tr="Anladım.")

        queue, _, _ = build_queue(clock=clock, handlers={WorkType.EXTRACT_SLOTS: handler})
        session = build_session(clock, steps=[scripted_step()], backend=queue)

        async def scenario() -> float:
            pump = asyncio.ensure_future(queue.run_pending())
            turn = await session.take_turn("iki gündür ağrıyor")
            pump.cancel()
            return float(turn.elapsed_ms)

        return float(clock.run(scenario()))

    assert turn_latency(10.0) == turn_latency(10_000.0) == turn_latency(0.0)
    assert turn_latency(10.0) > 0.0


def test_cancelling_a_completed_work_returns_its_terminal_state() -> None:
    """A terminal Work is terminal: a late cancel neither resurrects it nor
    rewrites its receipt (files/03 §4.3 state machine)."""
    queue, _, _ = build_queue()
    ticket = queue.submit(request())
    asyncio.run(queue.run_pending())

    late = queue.cancel(ticket.work_id, reason="patient retracted")

    assert late.state is WorkState.COMPLETED
    assert queue.record(ticket.work_id).state is WorkState.COMPLETED


def test_a_restart_is_not_undone_by_the_handler_that_was_still_running() -> None:
    """The restart marks the in-flight Work ``failed(reason=restart)``; the
    handler finishing afterwards must not walk it back to ``completed``."""
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(context: ReadOnlyContext, req: WorkRequest) -> WorkOutcome:
        started.set()
        await release.wait()
        return outcome(speech_tr="Anladım.")

    queue, _, _ = build_queue(handlers={WorkType.EXTRACT_SLOTS: handler})
    ticket = queue.submit(request())

    async def scenario() -> None:
        pump = asyncio.ensure_future(queue.run_pending())
        await started.wait()
        queue.fail_active_work_on_restart()
        release.set()
        await pump

    asyncio.run(scenario())

    record = queue.record(ticket.work_id)
    assert record.state is WorkState.FAILED
    assert record.failure is WorkFailure.RESTART
    assert queue.drain_results() == (), "a restarted Work must not speak afterwards"


def test_the_receipts_read_back_in_submission_order() -> None:
    queue, _, _ = build_queue()
    tickets = [queue.submit(request(step_id=f"s{index}")) for index in range(3)]
    assert [record.work_id for record in queue.records()] == [t.work_id for t in tickets]
    assert not queue.sealed


def test_reading_the_receipt_of_an_unknown_work_id_raises() -> None:
    queue, _, _ = build_queue()
    with pytest.raises(LookupError):
        queue.record("w_nope")
