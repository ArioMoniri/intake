"""INT-430 — the verifier never blocks a turn, never delays RED, and lands late safely.

ADR-036 and both challenger reviews: primary extraction feeds triage exactly as
before; the verifier runs afterwards as Backend Work on the event loop, behind
budget and admission control; a verdict that lands after the session ended,
or after a RED sealed the queue, becomes a clinician addendum and re-runs
triage. Measured on :class:`talker_harness.FakeClock`, in virtual time.
"""

from __future__ import annotations

import asyncio
from typing import Any

from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from council_harness import (
    BELIRTI,
    HASH,
    IKINCI,
    OLCUM,
    SESSION,
    answer,
    desk_rig,
    document,
    meter,
    policy,
    reading,
)
from intake_voice_runtime.clinical_agent.council.desk import (
    AddendumReason,
    AdmissionGate,
    DeskOutcome,
    RerunReason,
    VerifierDesk,
)
from intake_voice_runtime.clinical_agent.council.ledger import EventKind
from intake_voice_runtime.clinical_agent.council.readings import Reading
from intake_voice_runtime.clinical_agent.council.scope import verifier_scope
from intake_voice_runtime.clinical_agent.work_queue import StateContext, StateEffect
from intake_voice_runtime.extraction.boundary import PatientData
from intake_voice_runtime.ports import WorkRequest, WorkType
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import Priority
from session_harness import builders
from session_harness import protocol as two_step_protocol
from talker_harness import FakeClock

SAID = "Sentetik belirtim yok, bazen var gibi."
PRESENT_DOC = document(reading(BELIRTI, Reading.QUALIFIED_PRESENT, SAID, "bazen var gibi"))
RULE = "sentetik.kural.430"


def _request(step_id: str, data: PatientData, *, engine_version: int = 1) -> WorkRequest:
    return WorkRequest(
        session_id=SESSION,
        work_type=WorkType.EXTRACT_SLOTS,
        step_id=step_id,
        input_hash=data.sha256,
        protocol_hash=HASH,
        engine_version=engine_version,
    )


# --- 30 s stall: the Talker and the deterministic order -------------------------------------


def _session_run(*, council: bool, stall_s: float) -> tuple[list[float], list[str | None], Any]:
    clock = FakeClock()
    stack = builders(tenant_id="sentetik-kiraci", session_id=SESSION, clock=clock)[
        VoiceProfile.RESIDENCY_TR
    ]()
    desk: VerifierDesk | None = None
    if council:
        # The verifier is wired onto the composed stack's own queue and engine.
        desk = desk_rig(
            clock,
            texts={-1: '{"readings": []}'},
            stall_s=stall_s,
            policy_=policy(deadline_ms=60_000),
            agent_=stack.agent,
            scope_=verifier_scope(two_step_protocol()),
        ).desk
        stack.handler.verifier = desk

    async def scenario() -> tuple[list[float], list[str | None]]:
        stop = asyncio.Event()

        async def backend() -> None:
            while not stop.is_set():
                if desk is None or await desk.pump_once() is None:
                    await clock.sleep(0.05)

        loop = asyncio.ensure_future(backend())
        elapsed: list[float] = []
        spoken: list[str | None] = []
        for transcript in (None, "bir", "iki"):
            outcome = await stack.session.take_turn(transcript)
            stack.agent.run_pending()
            elapsed.append(outcome.elapsed_ms)
            spoken.append(outcome.step_id)
        stop.set()
        loop.cancel()
        return elapsed, spoken

    elapsed, spoken = clock.run(scenario())
    return elapsed, spoken, stack


class TestStalledCouncil:
    def test_council_stalled_30s_leaves_turn_latency_and_order_unchanged(self) -> None:
        off_latency, off_order, off_stack = _session_run(council=False, stall_s=0.0)
        on_latency, on_order, on_stack = _session_run(council=True, stall_s=30.0)
        assert on_latency == off_latency
        assert on_order == off_order
        # The intake kept moving: every answer is bound while the council stalls.
        for step in ("oyku.birinci", "oyku.ikinci"):
            assert on_stack.engine.state_of(step) is AnswerState.ASKED_PRESENT
            assert on_stack.engine.value_of(step) == off_stack.engine.value_of(step)

    def test_near_miss_an_answering_council_also_changes_neither(self) -> None:
        off_latency, off_order, _ = _session_run(council=False, stall_s=0.0)
        on_latency, on_order, _ = _session_run(council=True, stall_s=0.0)
        assert (on_latency, on_order) == (off_latency, off_order)


class TestRedNeverWaits:
    def _red_effect(self, context: StateContext) -> StateEffect:
        return StateEffect(
            triage_update=RulesTriageResult(
                level=TriageLevel.RED,
                rules=(RuleFire(id=RULE, evidence="sentetik kanıt"),),
                register=RedRegister.CALM,
                location=RedLocation.REMOTE,
            )
        )

    def _red_at(self, *, stalled: bool) -> float:
        clock = FakeClock()
        rig = desk_rig(clock, texts={-1: PRESENT_DOC}, stall_s=30.0 if stalled else 0.0)
        rig.agent.rule_ids = frozenset({RULE})
        data = PatientData(text=SAID)

        def primary(context: StateContext) -> StateEffect:
            if stalled:
                rig.desk.request_verification(context.request, data)
            return self._red_effect(context)

        rig.agent.register_state(WorkType.EXTRACT_SLOTS, primary)

        async def scenario() -> float:
            pump = asyncio.ensure_future(rig.desk.pump_once())
            rig.agent.submit(_request(BELIRTI, data))
            rig.agent.run_pending()
            (result,) = rig.agent.drain_results()
            assert result.priority is Priority.PREEMPT
            assert result.delivery_class is DeliveryClass.RED
            at = clock.now_ms()
            await pump
            return at

        landed: float = clock.run(scenario())
        return landed

    def test_lexicon_red_with_council_stalled_30s(self) -> None:
        """The rules RED lands at the same virtual instant with the council stalled.

        The deterministic red-flag lexicon itself is clinical content (split
        row in ADR-036); what this proves is the property the review needs
        from it: a rules-engine RED on the primary path waits on no verifier.
        """
        assert self._red_at(stalled=True) == 0.0

    def test_near_miss_red_with_no_council_lands_at_the_same_instant(self) -> None:
        assert self._red_at(stalled=False) == self._red_at(stalled=True)

    def test_a_verdict_after_a_red_seal_becomes_an_addendum(self) -> None:
        clock = FakeClock()
        rig = desk_rig(
            clock, texts={-1: PRESENT_DOC}, stall_s=30.0, policy_=policy(deadline_ms=60_000)
        )
        rig.agent.rule_ids = frozenset({RULE})
        answer(rig.engine, BELIRTI, False)
        data = PatientData(text=SAID)
        rig.agent.register_state(WorkType.EXTRACT_SLOTS, self._red_effect)

        async def scenario() -> DeskOutcome | None:
            rig.desk.request_verification(_request(BELIRTI, data), data)
            pump = asyncio.ensure_future(rig.desk.pump_once())
            rig.agent.submit(_request(BELIRTI, data))
            rig.agent.run_pending()
            return await pump

        assert clock.run(scenario()) is DeskOutcome.LATE
        assert [a.reason for a in rig.inbox.addenda] == [AddendumReason.LATE_RED_FLAG_EVIDENCE]
        assert rig.triage.reasons == [RerunReason.VERIFICATION_LATE]


# --- landing, late landing, admission and budget ----------------------------------------------


def _armed_rig(clock: FakeClock, **kwargs: Any) -> Any:
    rig = desk_rig(clock, texts={-1: PRESENT_DOC}, **kwargs)
    answer(rig.engine, BELIRTI, False)
    data = PatientData(text=SAID)
    rig.desk.request_verification(_request(BELIRTI, data), data)
    return rig


class TestLanding:
    def test_late_landing_after_end_creates_inbox_addendum(self) -> None:
        clock = FakeClock()
        rig = _armed_rig(clock)
        rig.desk.end_session()
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.LATE
        (addendum,) = rig.inbox.addenda
        assert addendum.ref == BELIRTI
        assert addendum.reason is AddendumReason.LATE_RED_FLAG_EVIDENCE
        assert rig.triage.reasons == [RerunReason.VERIFICATION_LATE]
        assert rig.engine.next_step() is None or "/verify/" not in rig.engine.next_step().step_id

    def test_near_miss_an_on_time_landing_appends_and_reruns_triage(self) -> None:
        clock = FakeClock()
        rig = _armed_rig(clock)
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SUBMITTED
        assert rig.agent.run_pending() == 1
        head = rig.engine.next_step()
        assert head is not None and head.step_id == f"{BELIRTI}/verify/1"
        assert rig.inbox.addenda == []
        assert rig.triage.reasons == [RerunReason.VERIFICATION_LANDED]
        assert rig.engine.value_of(BELIRTI) is False  # never overwritten

    def test_a_patient_correction_before_landing_drops_the_stale_append(self) -> None:
        clock = FakeClock()
        rig = _armed_rig(clock)
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SUBMITTED
        rig.engine.append_verification(BELIRTI, *_reask(rig))  # an earlier verdict's re-ask
        rig.engine.mark_asked(f"{BELIRTI}/verify/1")
        rig.engine.apply_extraction(f"{BELIRTI}/verify/1", {BELIRTI: True})
        rig.agent.run_pending()
        assert rig.engine.value_of(BELIRTI) is True
        assert [e.code for e in rig.desk.ledger.events if e.kind is EventKind.ACTION] == [
            "reask_positive:stale_revision"
        ]

    def test_text_only_answers_never_reach_a_member(self) -> None:
        clock = FakeClock()
        rig = desk_rig(clock, texts={-1: PRESENT_DOC})
        data = PatientData(text="Sentetik güvenlik yanıtı.")
        rig.desk.request_verification(_request("guvenlik.sentetik_guvenlik", data), data)
        assert rig.desk.pending == 0
        assert rig.transport.calls == []

    def test_near_miss_a_voice_answer_is_queued(self) -> None:
        clock = FakeClock()
        rig = desk_rig(clock, texts={-1: PRESENT_DOC})
        data = PatientData(text=SAID)
        rig.desk.request_verification(_request(OLCUM, data), data)
        assert rig.desk.pending == 1


def _reask(rig: Any) -> tuple[Any, int]:
    from intake_voice_runtime.clinical_agent.fsm import VerificationKind

    return VerificationKind.REASK, rig.engine.slot_revision(BELIRTI)


class TestAdmission:
    def test_gpu_saturation_sheds_instead_of_queueing(self) -> None:
        clock = FakeClock()
        gate = AdmissionGate(max_in_flight=1)
        assert gate.try_enter()  # another session holds the only slot
        rig = _armed_rig(clock, gate=gate)
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SHED_SATURATED
        assert rig.transport.calls == []

    def test_near_miss_a_free_slot_admits_and_is_released(self) -> None:
        clock = FakeClock()
        gate = AdmissionGate(max_in_flight=1)
        rig = _armed_rig(clock, gate=gate)
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SUBMITTED
        assert gate.try_enter()

    def test_budget_refusal_while_hb_o8_is_open(self) -> None:
        clock = FakeClock()
        rig = _armed_rig(clock, meter_=meter(cap=None))
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.REFUSED_BUDGET
        assert rig.transport.calls == []

    def test_near_miss_a_declared_cap_admits_and_is_charged(self) -> None:
        clock = FakeClock()
        the_meter = meter(cap=10_000.0)
        rig = _armed_rig(clock, meter_=the_meter)
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SUBMITTED
        assert sum(the_meter.totals().values()) == 3 * (11 + 7)

    def test_stragglers_time_out_at_the_deadline(self) -> None:
        clock = FakeClock()
        rig = _armed_rig(clock, stall_s=30.0, policy_=policy(deadline_ms=2_000))
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SUBMITTED
        assert clock.now_ms() == 2_000.0
        codes = {e.code for e in rig.desk.ledger.events if e.kind is EventKind.DRAW_WITHOUT_READING}
        assert codes == {"timed_out"}

    def test_each_session_gets_its_own_cache_salt(self) -> None:
        clock = FakeClock()
        one, two = desk_rig(clock, texts={}), desk_rig(clock, texts={})
        assert one.desk.cache_salt != two.desk.cache_salt
        assert len(one.desk.cache_salt) == 32


class TestApplication:
    def test_a_candidate_flag_reaches_the_clinician_and_changes_no_priority(self) -> None:
        clock = FakeClock()
        said = "İkinci sentetik şikayetim de var."
        rig = desk_rig(
            clock, texts={-1: document(reading(IKINCI, Reading.PRESENT, said, "şikayetim de var"))}
        )
        data = PatientData(text=said)
        rig.desk.request_verification(_request(OLCUM, data), data)
        assert clock.run(rig.desk.pump_once()) is DeskOutcome.SUBMITTED
        rig.agent.run_pending()
        (result,) = rig.agent.drain_results()
        candidates = rig.desk.ledger.llm_candidates()
        assert candidates is not None and candidates.level == "YELLOW_REVIEW"
        assert [flag.text for flag in candidates.candidate_flags] == [
            f"council.narrative_evidence:{IKINCI}"
        ]
        assert result.presentation.candidate_flags == ()  # the device never sees it
        assert result.priority is Priority.NORMAL
        assert result.delivery_class is DeliveryClass.ROUTINE
        assert result.presentation.triage_update is None
        assert result.presentation.speech_tr is None

    def test_near_miss_a_verdict_with_no_action_carries_no_flag(self) -> None:
        clock = FakeClock()
        rig = desk_rig(clock, texts={-1: '{"readings": []}'})
        data = PatientData(text=SAID)
        rig.desk.request_verification(_request(OLCUM, data), data)
        clock.run(rig.desk.pump_once())
        rig.agent.run_pending()
        (result,) = rig.agent.drain_results()
        assert rig.desk.ledger.llm_candidates() is None
        assert result.delivery_class is DeliveryClass.ROUTINE

    def test_the_confirmation_ceiling_caps_numeric_confirm_backs_only(self) -> None:
        clock = FakeClock()
        doc = document(
            reading(BELIRTI, Reading.HEDGED, SAID, "bazen var gibi"),
            reading(OLCUM, Reading.PRESENT, SAID, "bazen", number="99"),
        )
        rig = desk_rig(clock, texts={-1: doc})
        rig.handler.confirmation_ceiling = 0
        answer(rig.engine, BELIRTI, False)
        answer(rig.engine, OLCUM, 12)
        data = PatientData(text=SAID)
        rig.desk.request_verification(_request(OLCUM, data), data)
        clock.run(rig.desk.pump_once())
        rig.agent.run_pending()
        codes = [e.code for e in rig.desk.ledger.events if e.kind is EventKind.ACTION]
        assert codes == ["reask_positive:appended", "confirm_back:ceiling"]

    def test_near_miss_an_unsigned_ceiling_withholds_no_confirm_back(self) -> None:
        clock = FakeClock()
        doc = document(reading(OLCUM, Reading.PRESENT, SAID, "bazen", number="99"))
        rig = desk_rig(clock, texts={-1: doc})
        assert rig.handler.confirmation_ceiling is None
        answer(rig.engine, OLCUM, 12)
        data = PatientData(text=SAID)
        rig.desk.request_verification(_request(OLCUM, data), data)
        clock.run(rig.desk.pump_once())
        rig.agent.run_pending()
        codes = [e.code for e in rig.desk.ledger.events if e.kind is EventKind.ACTION]
        assert codes == ["confirm_back:appended"]
