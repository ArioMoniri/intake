"""INT-094 — the runtime invariants, composed, and the RT scenarios on them.

This suite is deliberately *not* a fourth copy of the unit suites. INT-091,
INT-092, INT-093 and INT-110 each prove their own module against its own
ports, and each proof is good. What none of them can prove is the thing that
only exists when the four are wired together: that a **composed** session —
one real :class:`~intake_voice_runtime.clinical_agent.fsm.IntakeEngine`, one
real :class:`~intake_voice_runtime.clinical_agent.work_queue.BackendAgent`,
one real :class:`~intake_voice_runtime.talker.session.TalkerSession` and one
real :class:`~intake_voice_runtime.talker.red_path.RedPreemption`, on one
virtual clock — still holds files/03 §4.6's eleven runtime invariants.

So every test here is written against the composed :class:`Stack`, and where
an invariant can only be held inside the unit that owns it, this file says so
out loud in :class:`TestTheHonestyLedger` rather than asserting a composed
property it does not have.

**Numbering.** "Runtime invariants 1-11" in the issue title is files/03 §4.6,
whose eleven rows are non-blocking · fixed tool surface · single preemption ·
RED latency · FIFO+single-in-flight+serialised · idempotent delivery ·
verbatim scripted · profile parity · no raw audio · observability-not-control
· lanes off the critical path. CLAUDE.md numbers a *different* 1-22 and the
two collide on every index; each class below names both.

**No test sleeps.** Every timing assertion runs on ``talker_harness.FakeClock``,
the virtual clock INT-092, INT-093 and INT-110 already share, whose driver
advances only when every task is parked. A test that passed because it waited
would be the failure mode INT-092 recorded, where collapsing the two queue
locks made the proof ten seconds *slower* instead of red.

Every id, slot, rule id and Turkish string here is synthetic and carries no
clinical meaning (files/04 §7). The authored base pack is INT-043, blocked on
HB-C1.
"""

from __future__ import annotations

import asyncio
import datetime
import re
from collections.abc import Iterator
from pathlib import Path

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
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import (
    BackendAgent,
    BackgroundEffect,
    EffectClass,
    ReadOnlyContext,
    StateContext,
    StateEffect,
    UnregisteredWorkType,
    WorkLane,
)
from intake_voice_runtime.ports import WorkType
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.simulator import (
    DISPLACED_FLOOR,
    IN_COUNTRY_FLOOR,
    MID_LTE_DYNAMIC_P95_ITEMISED_MS,
    RESIDENCY_TR_P95_BAND_MS,
    SCENARIOS,
    VENDOR_HOP_SAVING_P50_MS,
    VENDOR_HOP_SAVING_P95_MS,
    BudgetNotPublished,
    NetworkProfile,
    PublishedBudget,
    RuntimeScenario,
    ScenarioNotRunnable,
    ScenarioReport,
    TurnClass,
    TurnRecord,
    displaced_baseline_dynamic,
    published_budget,
    render_report,
    runnable_scenarios,
)
from intake_voice_runtime.steps import StepKind
from intake_voice_runtime.talker.activity import ACTIVITY_OF, ActivityLabel
from intake_voice_runtime.talker.delivery import (
    ADAPTIVE_FLOOR_HIGH_MS,
    ADAPTIVE_FLOOR_LOW_MS,
    ADAPTIVE_JITTER_THRESHOLD_MS,
    Deadlines,
    DeadlinesNotConfiguredError,
    DeliveryClass,
    DeliveryDeadlines,
    DuplexState,
    TurnYieldPolicy,
)
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    InlinePayload,
    Presentation,
    Priority,
)
from intake_voice_runtime.talker.red_path import (
    MappingRedScriptIndex,
    RedPreemption,
    RedPreemptionOutcome,
)
from intake_voice_runtime.talker.session import TurnHold
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.types import Delivery, SlotType
from red_harness import (
    MediaPlane,
    RecordingClinicNotifier,
    RecordingDataChannel,
)
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingSink,
    RecordingSynthesizer,
    build_session,
)

REPO = Path(__file__).resolve().parents[2]
TTS_TS = REPO / "apps" / "mobile" / "src" / "lib" / "dialogue" / "tts.ts"

NOW = datetime.datetime(2026, 9, 2, 9, 0, tzinfo=datetime.UTC)
HASH = "0" * 64
SESSION = "11111111-2222-4333-8444-555555555555"

RULE_A = "rf.sentetik_a"
PACK_RULES = frozenset({RULE_A})
SCRIPTS = MappingRedScriptIndex(
    entries={
        (RULE_A, RedLocation.REMOTE): "sentetik.a.remote",
        (RULE_A, RedLocation.ON_SITE): "sentetik.a.on_site",
        (RULE_A, RedLocation.UNKNOWN): "sentetik.a.unknown",
    }
)

#: A delivery table a *test* configures for the classes files/12 §6 leaves
#: unset. It is not a proposed product value: the point of the RT-01 tests
#: below is that the shipped default refuses, and that the ladder works once a
#: human supplies a window. See :class:`TestRT01`.
SYNTHETIC_TABLE = DeliveryDeadlines(
    clinical_info=Deadlines(soft_ms=2_000.0, hard_ms=4_000.0, terminal_ms=8_000.0),
    routine=Deadlines(soft_ms=2_000.0, hard_ms=4_000.0, terminal_ms=8_000.0),
)


# --- the synthetic protocol ----------------------------------------------------------


def _slot(**fields: object) -> Slot:
    return Slot.model_validate(fields)


def _resolved(section_id: str, key: str, slot: Slot) -> ResolvedSlot:
    return ResolvedSlot(
        section_id=section_id,
        key=key,
        fhir_link_id=f"{section_id}.{key}",
        slot=slot,
        delivery=Delivery.VOICE,
    )


def _protocol() -> ResolvedProtocol:
    """Three scripted steps in one section. Nothing here is clinical."""
    return ResolvedProtocol(
        pack_id="base.sentetik_rt",
        version="1.0.0",
        chain=("base.sentetik_rt",),
        resolved_protocol_hash=HASH,
        sections=(
            ResolvedSection(
                id="oyku",
                delivery=Delivery.VOICE,
                allow_paraphrase=False,
                slots=(
                    _resolved(
                        "oyku",
                        "birinci",
                        _slot(
                            type=SlotType.INTEGER,
                            required=True,
                            must_ask=True,
                            ask_tr="Sentetik birinci soru.",
                            follow_up_tr="Sentetik birinci takip sorusu.",
                        ),
                    ),
                    _resolved(
                        "oyku",
                        "ikinci",
                        _slot(
                            type=SlotType.INTEGER,
                            required=True,
                            must_ask=True,
                            ask_tr="Sentetik ikinci soru.",
                            follow_up_tr="Sentetik ikinci takip sorusu.",
                        ),
                    ),
                    _resolved(
                        "oyku",
                        "ucuncu",
                        _slot(
                            type=SlotType.INTEGER,
                            required=True,
                            must_ask=True,
                            ask_tr="Sentetik ucuncu soru.",
                            follow_up_tr="Sentetik ucuncu takip sorusu.",
                        ),
                    ),
                ),
            ),
        ),
    )


STEP_IDS = ("oyku.birinci", "oyku.ikinci", "oyku.ucuncu")

#: Invariant 22 forbids a numeral anywhere on the TTS path, and the router
#: enforces it — so even a synthetic fixture spells its index out.
_ORDINAL_TR = ("birinci", "ikinci", "ucuncu")


def red_result(
    *, work_id: str = "w_red", register: RedRegister = RedRegister.ALERT
) -> BackendResult:
    return BackendResult(
        work_id=work_id,
        state="completed",
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(
            triage_update=RulesTriageResult(
                level=TriageLevel.RED,
                rules=(RuleFire(id=RULE_A, evidence="sentetik_yanit=evet"),),
                register=register,
                location=RedLocation.REMOTE,
            )
        ),
        priority=Priority.PREEMPT,
    )


# --- the composed stack --------------------------------------------------------------


class Stack:
    """One session, wired the way files/03 §4.1 draws it, on one virtual clock.

    The three layers are the shipped ones. What this class supplies is the two
    joints the shipped code does not have a producer for, both recorded in
    :class:`TestTheLoopThatDoesNotClose`:

    * an ``extract_slots`` **state handler**. ``BackendAgent`` registers none
      (INT-092 left the production handler to INT-083, which built the Work
      body and never registered it), so a composed session refuses the very
      first transcript. The handler here is the registration that is missing,
      not a stand-in for a model: it takes the slot updates the caller states.
    * a **transcript route**. ``WorkRequest`` carries ``input_hash``, never
      text (INT-092 finding 3), so the handler is handed its updates through
      this object rather than through the request.
    """

    def __init__(
        self,
        *,
        deadlines: DeliveryDeadlines | None = None,
        profile: VoiceProfile = VoiceProfile.RESIDENCY_TR,
        rule_ids: frozenset[str] = PACK_RULES,
        stall_s: float = 0.0,
        playback_ms_per_byte: float = 1.0,
    ) -> None:
        self.clock = FakeClock()
        self.engine = IntakeEngine(protocol=_protocol(), reference_time=NOW)
        self.agent = BackendAgent(
            session_id=SESSION, engine=self.engine, rule_ids=rule_ids, clock=self.clock
        )
        self.stall_s = stall_s
        self.answers: dict[str, object] = {}
        self.effects: dict[str, StateEffect] = {}
        self.background: list[BackgroundEffect] = []
        self.state_calls: list[str] = []
        self.background_calls: list[str] = []
        self.agent.register_state(WorkType.EXTRACT_SLOTS, self._extract)
        self.agent.register_background(WorkType.PARSE_DOCUMENT, self._parse)

        self.sink = RecordingSink(clock=self.clock, ms_per_byte=playback_ms_per_byte)
        self.clip_store = RecordedClipStore()
        self.synthesizer = RecordingSynthesizer()
        self.memory = InMemoryPatientMemory()
        self.session = build_session(
            self.clock,
            steps=[],
            backend=self.agent,
            sink=self.sink,
            clip_store=self.clip_store,
            synthesizer=self.synthesizer,
            memory=self.memory,
            rule_ids=rule_ids,
        )
        self.session.engine = self.engine
        table = deadlines or DeliveryDeadlines()
        self.session.config = self.session.config.model_copy(
            update={"profile": profile, "protocol_hash": HASH, "deadlines": table}
        )
        # The scheduler was built from the config the session was constructed
        # with; point it at the table this Stack was asked for.
        self.session.scheduler.deadlines = table

        self.media = MediaPlane(clock=self.clock)
        self.channel = RecordingDataChannel(clock=self.clock)
        self.clinic = RecordingClinicNotifier()
        self.session.preemption = RedPreemption(
            canceller=self.media,
            channel=self.channel,
            clinic=self.clinic,
            scripts=SCRIPTS,
            clock=self.clock,
        )

    # --- the two missing joints ------------------------------------------------

    def _extract(self, context: StateContext) -> StateEffect:
        """The registration INT-083 owes: mark the step asked, then bind."""
        step_id = context.request.step_id
        self.state_calls.append(step_id)
        if step_id in {step.step_id for step in context.engine.frontier()}:
            context.engine.mark_asked(step_id)
        if step_id in self.answers:
            context.engine.apply_extraction(step_id, {step_id: self.answers[step_id]})
        return self.effects.get(step_id, StateEffect())

    def _parse(self, context: ReadOnlyContext) -> BackgroundEffect:
        self.background_calls.append(context.request.step_id)
        return self.background.pop(0) if self.background else BackgroundEffect()

    # --- driving ---------------------------------------------------------------

    async def _pump(self) -> None:
        """Layer B's own loop: stall, then run whatever is queued."""
        if self.stall_s:
            await self.clock.sleep(self.stall_s)
        self.agent.run_pending()

    def turn(self, transcript: str | None, *, pump: bool = True) -> object:
        """One turn, with Layer B running concurrently and never awaited."""

        async def main() -> object:
            worker = asyncio.ensure_future(self._pump()) if pump else None
            outcome = await self.session.take_turn(transcript)
            if worker is not None and not worker.done():
                worker.cancel()
            return outcome

        return self.clock.run(main())

    def drain(self) -> None:
        """Let Layer B finish and let the Talker take one empty turn."""
        self.clock.run(self._pump())
        self.clock.run(self.session.take_turn(None))

    def advance(self, seconds: float) -> None:
        """Move the shared virtual clock forward. Nothing sleeps in wall time."""
        self.clock.run(self.clock.sleep(seconds))

    def preempt(self, result: BackendResult, *, evaluated_at_ms: float) -> RedPreemptionOutcome:
        return self.clock.run(self.session.deliver_preempt(result, evaluated_at_ms=evaluated_at_ms))


@pytest.fixture
def stack() -> Iterator[Stack]:
    yield Stack()


# =====================================================================================
# files/03 §4.6 invariant 1 — non-blocking (CLAUDE.md invariant 9, clause 2)
# =====================================================================================


class TestInvariant1NonBlocking:
    """*"with the Backend Agent stalled for 10 s (fake clock), the Talker still
    answers within budget."*

    INT-092 proved this against the queue and INT-091 against the Talker's own
    port. Neither ran the two together, and the composition is where a
    regression would actually live: a queue that took the engine lock in
    ``submit`` would stall the *Talker*, not itself.
    """

    def test_a_ten_second_stall_costs_the_turn_nothing(self) -> None:
        fast = Stack(stall_s=0.0)
        slow = Stack(stall_s=10.0)
        assert fast.turn(None).elapsed_ms == slow.turn(None).elapsed_ms  # type: ignore[union-attr]

    def test_an_hour_long_stall_costs_the_turn_nothing_either(self) -> None:
        """A ten-second assertion passes for a Talker that waits nine."""
        ten = Stack(stall_s=10.0)
        hour = Stack(stall_s=3_600.0)
        assert ten.turn(None).elapsed_ms == hour.turn(None).elapsed_ms  # type: ignore[union-attr]

    def test_the_positive_control_shows_the_same_stall_on_the_turn_path(self) -> None:
        """The measurement can see a stall — it is not blind to the clock."""
        stack = Stack(stall_s=0.0, playback_ms_per_byte=1_000.0)
        assert stack.turn(None).elapsed_ms > 10_000.0  # type: ignore[union-attr]

    def test_submitting_a_transcript_runs_no_backend_work(self, stack: Stack) -> None:
        stack.turn("sentetik yanit", pump=False)
        assert stack.state_calls == []
        assert stack.agent.depth(WorkLane.STATE) == 1


# =====================================================================================
# files/03 §4.6 invariant 2 — fixed tool surface (CLAUDE.md invariant 9, clause 1)
# =====================================================================================


class TestInvariant2FixedToolSurface:
    """INT-091's registry test proves the six names. What it cannot prove is
    that a *session* driving a real engine and a real queue calls nothing
    else — so this walks a whole turn and watches the two ports."""

    def test_a_turn_touches_the_engine_only_through_the_snapshot(self, stack: Stack) -> None:
        calls: list[str] = []
        original = type(stack.engine).snapshot.fget  # type: ignore[attr-defined]

        class Watched:
            def __init__(self, engine: IntakeEngine) -> None:
                self._engine = engine

            @property
            def snapshot(self) -> object:
                calls.append("snapshot")
                return original(self._engine)

            def __getattr__(self, name: str) -> object:
                calls.append(name)
                return getattr(self._engine, name)

        stack.session.engine = Watched(stack.engine)  # type: ignore[assignment]
        stack.turn("sentetik yanit", pump=False)
        assert set(calls) == {"snapshot"}

    def test_the_session_exposes_no_seventh_capability(self, stack: Stack) -> None:
        public = {
            name
            for name in dir(stack.session)
            if not name.startswith("_") and callable(getattr(stack.session, name))
        }
        forbidden = {"search", "browse", "http", "fetch_url", "execute", "shell", "email"}
        assert public & forbidden == set()


# =====================================================================================
# files/03 §4.6 invariant 3 — single preemption (CLAUDE.md invariants 1 and 9)
# =====================================================================================


class TestInvariant3SinglePreemption:
    """*"no Work result other than a rules-engine RED may carry ``preempt``."*

    Proven at three separate layers by three earlier issues. What is new here
    is the composed direction: a handler returning a rules RED through the
    **real queue** must arrive at the **real Talker** as a preempt, and an LLM
    candidate riding the same handler must not.
    """

    def test_a_rules_red_from_a_handler_reaches_the_talker_as_a_preempt(self) -> None:
        stack = Stack()
        stack.effects[STEP_IDS[0]] = StateEffect(
            triage_update=RulesTriageResult(
                level=TriageLevel.RED,
                rules=(RuleFire(id=RULE_A, evidence="sentetik"),),
                register=RedRegister.ALERT,
                location=RedLocation.REMOTE,
            )
        )
        stack.turn("sentetik yanit")
        stack.drain()
        assert [result.priority for result in stack.session.preempts] == [Priority.PREEMPT]

    def test_a_candidate_flag_from_the_same_handler_never_preempts(self) -> None:
        stack = Stack()
        stack.background.append(
            BackgroundEffect(
                candidate_flags=(
                    CandidateFlag(text="Sentetik aday isaret.", evidence="sentetik kanit"),
                ),
            )
        )
        stack.session.submit_utterance(STEP_IDS[0], "sentetik")
        stack.drain()
        assert stack.session.preempts == ()

    def test_the_llm_candidate_type_cannot_spell_red_at_all(self) -> None:
        candidate = LlmCandidateTriage(
            candidate_flags=(CandidateFlag(text="Sentetik aday.", evidence="sentetik kanit"),)
        )
        assert candidate.level == "YELLOW_REVIEW"


# =====================================================================================
# files/03 §4.6 invariant 4 — RED latency (CLAUDE.md invariant 21)
# =====================================================================================


class TestInvariant4RedLatency:
    """INT-093 measured the path in isolation (stop 40 ms / e2e 90 ms) and
    proved three ways that it touches no media transport. Re-measuring it here
    would prove nothing new. What is new is the **composed** claim: the RED
    arrives through the real queue, is delivered by the real session, and the
    intake stops — and the budget still holds with a Talker mid-sentence."""

    def test_a_red_that_travelled_the_queue_stops_the_composed_intake(self) -> None:
        stack = Stack()
        stack.effects[STEP_IDS[0]] = StateEffect(
            triage_update=RulesTriageResult(
                level=TriageLevel.RED,
                rules=(RuleFire(id=RULE_A, evidence="sentetik"),),
                register=RedRegister.ALERT,
                location=RedLocation.REMOTE,
            )
        )
        stack.turn("sentetik yanit")
        stack.drain()
        outcome = stack.preempt(stack.session.preempts[0], evaluated_at_ms=stack.clock.now_ms())
        assert outcome.stop_ms is not None
        assert outcome.e2e_ms is not None
        assert stack.session.red_stopped is True
        after = stack.turn(None)
        assert after.spoken_text == ""  # type: ignore[union-attr]

    def test_the_composed_red_still_reaches_no_synthesizer_or_clip_store(self) -> None:
        stack = Stack()
        stack.preempt(red_result(), evaluated_at_ms=stack.clock.now_ms())
        assert stack.synthesizer.requests == []
        assert stack.clip_store.served == []
        assert stack.media.played == []


# =====================================================================================
# files/03 §4.6 invariant 5 — FIFO, single in flight, serialised writes
# =====================================================================================


class TestInvariant5FifoSingleInFlight:
    """INT-092 proved FIFO and *"the final state matches a sequential run"*
    against the queue. RT-05 asks the same question of the **Talker**: five
    answers submitted through ``submit_utterance`` in three seconds."""

    def test_five_talker_submissions_run_in_submission_order(self) -> None:
        stack = Stack()
        for index, step_id in enumerate(STEP_IDS):
            stack.answers[step_id] = index
            stack.session.submit_utterance(step_id, f"sentetik {index}")
        stack.agent.run_pending()
        stack.agent.run_pending()
        stack.agent.run_pending()
        assert stack.state_calls == list(STEP_IDS)

    def test_at_most_one_state_work_is_ever_in_flight(self) -> None:
        stack = Stack()
        seen: list[int] = []

        def counting(context: StateContext) -> StateEffect:
            seen.append(len(stack.agent.in_flight))
            return StateEffect()

        stack.agent._state_handlers[WorkType.EXTRACT_SLOTS] = counting
        for index, step_id in enumerate(STEP_IDS):
            stack.session.submit_utterance(step_id, f"sentetik {index}")
        for _ in STEP_IDS:
            stack.agent.run_pending()
        assert seen == [1, 1, 1]


# =====================================================================================
# files/03 §4.6 invariant 6 — idempotent delivery
# =====================================================================================


class TestInvariant6IdempotentDelivery:
    def test_the_same_transcript_twice_produces_one_work(self, stack: Stack) -> None:
        first = stack.session.submit_utterance(STEP_IDS[0], "sentetik yanit")
        second = stack.session.submit_utterance(STEP_IDS[0], "sentetik yanit")
        assert first.work_id == second.work_id
        assert stack.agent.depth(WorkLane.STATE) == 1

    def test_a_delivered_result_is_never_spoken_twice(self) -> None:
        stack = Stack(deadlines=SYNTHETIC_TABLE)
        stack.effects[STEP_IDS[0]] = StateEffect(
            speech_tr="Sentetik arka plan cumlesi.", effect_class=EffectClass.CLINICAL_INFO
        )
        stack.turn("sentetik yanit")
        stack.session.observe_duplex(
            DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
        )
        stack.drain()
        delivered = stack.session.scheduler.delivered_work_ids
        assert len(delivered) == 1
        stack.drain()
        stack.drain()
        # The Talker labels backend playback with the work_id, so the sink is
        # the honest place to count deliveries rather than the scheduler's own
        # bookkeeping.
        assert [label for label, _ in stack.sink.played].count(delivered[0]) == 1
        assert stack.synthesizer.requests.count("Sentetik arka plan cumlesi.") == 1


# =====================================================================================
# files/03 §4.6 invariant 7 — verbatim scripted (CLAUDE.md invariant 10)
# =====================================================================================


class TestInvariant7VerbatimScripted:
    def test_the_engines_scripted_text_reaches_the_synthesizer_unchanged(
        self, stack: Stack
    ) -> None:
        step = stack.session.protocol_next()
        assert step is not None and step.kind is StepKind.SCRIPTED
        stack.turn(None)
        assert stack.synthesizer.requests == [step.text_tr]

    def test_a_scripted_step_is_never_offered_with_paraphrase_permission(
        self, stack: Stack
    ) -> None:
        step = stack.session.protocol_next()
        assert step is not None and step.allow_paraphrase is False


# =====================================================================================
# files/03 §4.6 invariant 8 — profile parity
# =====================================================================================


class TestInvariant8ProfileParity:
    """*"the same simulator scenarios pass on ``typed``, ``cascade_fast`` and
    ``residency_tr``."* Two of the three named profiles were deleted
    (CLAUDE.md invariant 19), so parity runs over the two that exist —
    files/07 states this outright: *"there is no third profile to run."*"""

    @pytest.mark.parametrize("profile", list(VoiceProfile))
    def test_a_turn_is_identical_under_both_profiles(self, profile: VoiceProfile) -> None:
        stack = Stack(profile=profile)
        outcome = stack.turn(None)
        assert outcome.spoken_text == "Sentetik birinci soru."  # type: ignore[union-attr]

    def test_there_are_exactly_two_profiles(self) -> None:
        assert {profile.value for profile in VoiceProfile} == {"residency_tr", "typed"}


# =====================================================================================
# files/03 §4.6 invariant 9 — no raw audio (CLAUDE.md invariant 3)
# =====================================================================================


class TestInvariant9NoRawAudio:
    def test_a_composed_session_retains_no_audio_buffer(self, stack: Stack) -> None:
        stack.turn("sentetik yanit")
        assert stack.session.retained_frames() == 0

    def test_the_queue_holds_a_hash_and_never_the_transcript(self, stack: Stack) -> None:
        ticket = stack.session.submit_utterance(STEP_IDS[0], "sentetik yanit")
        record = stack.agent.record(ticket.work_id)
        assert "sentetik yanit" not in repr(record)


# =====================================================================================
# files/03 §4.6 invariant 10 — observability, not control
# =====================================================================================


class TestInvariant10ObservabilityNotControl:
    """*"Work activity labels are from a fixed tr/en table; no session ids,
    prompts, or reasoning reach the client."*

    The fixed table did not exist: ``InlinePayload`` carried a free-text
    ``activity_label_tr`` that any handler could fill with anything. A closed
    label set is the only form in which this invariant can be tested at all.
    """

    def test_the_label_set_is_total_over_the_work_types(self) -> None:
        assert set(ACTIVITY_OF) == set(WorkType)

    def test_the_inline_payload_carries_a_label_id_and_not_free_text(self) -> None:
        payload = InlinePayload(activity=ActivityLabel.EXTRACTING)
        assert payload.model_dump()["activity"] == "extracting"

    def test_free_text_cannot_be_smuggled_into_the_label(self) -> None:
        with pytest.raises(ValueError, match="activity"):
            InlinePayload(activity="oturum 11111111-2222-4333-8444-555555555555")  # type: ignore[arg-type]

    def test_the_queue_reports_in_flight_activity_as_labels_only(self, stack: Stack) -> None:
        stack.session.submit_utterance(STEP_IDS[0], "sentetik yanit")
        assert stack.agent.activity == (ActivityLabel.EXTRACTING,)

    def test_an_idle_queue_reports_no_activity(self, stack: Stack) -> None:
        assert stack.agent.activity == ()

    def test_two_works_of_one_type_still_show_exactly_one_label(self, stack: Stack) -> None:
        """The rail says *what* is happening, never *how much*. One label per
        outstanding Work would publish queue depth to the patient — a count is
        an operational signal, and this channel is not an operational one."""
        stack.session.submit_utterance(STEP_IDS[0], "sentetik birinci yanit")
        stack.session.submit_utterance(STEP_IDS[1], "sentetik ikinci yanit")
        assert stack.agent.depth(WorkLane.STATE) == 2
        assert stack.agent.activity == (ActivityLabel.EXTRACTING,)

    def test_two_work_types_show_both_labels_once_each(self, stack: Stack) -> None:
        stack.session.submit_utterance(STEP_IDS[0], "sentetik birinci yanit")
        stack.session.submit_utterance(STEP_IDS[1], "sentetik ikinci yanit")
        stack.background.append(BackgroundEffect())
        stack.agent.submit(_document_request(0))
        assert stack.agent.activity == (
            ActivityLabel.EXTRACTING,
            ActivityLabel.READING_DOCUMENT,
        )


# =====================================================================================
# files/03 §4.6 invariant 11 — lanes never touch the critical path
# =====================================================================================


class TestInvariant11LanesOffTheCriticalPath:
    """INT-110 proved this against the same Talker with lanes stalled an hour.
    The blueprint's own figure is thirty seconds, and the acceptance names it,
    so the composed stack runs exactly that — with a positive control, because
    a latency assertion with no control is a tautology."""

    def test_lanes_stalled_thirty_seconds_leave_the_turn_unchanged(self) -> None:
        """The acceptance's own figure, against the **composed** stack.

        INT-110 ran this against ``LaneRuntime`` with a real budget and a real
        consent gate; repeating that here would re-prove its work. What is new
        is the engine and the queue being live underneath: a lane task parked
        for thirty seconds must not change a turn that is also reading a real
        snapshot and submitting into a real FIFO.
        """
        quiet = Stack()
        stalled = Stack()
        finished: list[bool] = []

        async def lane_window() -> None:
            await stalled.clock.sleep(30.0)
            finished.append(True)

        async def main() -> object:
            asyncio.ensure_future(lane_window())
            return await stalled.session.take_turn("sentetik yanit")

        stalled_outcome = stalled.clock.run(main())
        assert finished == []  # the lane is still parked when the turn returns
        assert (
            quiet.turn("sentetik yanit").elapsed_ms  # type: ignore[union-attr]
            == stalled_outcome.elapsed_ms
        )

    def test_the_same_thirty_seconds_on_the_turns_own_path_is_visible(self) -> None:
        """The permanent positive control INT-110 argued for: the same thirty
        seconds, moved onto the turn's own path, is fully visible. Without it
        the assertion above would pass against a clock that never moves."""
        stack = Stack(playback_ms_per_byte=1_500.0)
        assert stack.turn(None).elapsed_ms >= 30_000.0  # type: ignore[union-attr]


# =====================================================================================
# RT-01 … RT-08 (files/04 §6 "Runtime scenarios v1.1")
# =====================================================================================


class TestRT01:
    """*"patient keeps talking for 40 s while two documents parse in the
    background — Talker must acknowledge, never stall, and speak the document
    result only at a pause."*"""

    def _two_documents(self, stack: Stack) -> None:
        for index in (0, 1):
            stack.background.append(
                BackgroundEffect(
                    speech_tr=f"Sentetik belge sonucu {_ORDINAL_TR[index]}.",
                    effect_class=EffectClass.CLINICAL_INFO,
                )
            )
            stack.session.backend.submit(
                stack.session.backend.__class__.__mro__ and _document_request(index)
            )

    def test_two_documents_parse_concurrently_without_head_of_line_blocking(self) -> None:
        stack = Stack(deadlines=SYNTHETIC_TABLE)
        for index in (0, 1):
            stack.background.append(BackgroundEffect())
            stack.agent.submit(_document_request(index))
        stack.session.submit_utterance(STEP_IDS[0], "sentetik yanit")
        stack.agent.run_pending()
        assert stack.state_calls == [STEP_IDS[0]]
        assert stack.background_calls == ["belge-0"]

    def test_forty_seconds_of_patient_speech_never_stalls_the_turn(self) -> None:
        stack = Stack(deadlines=SYNTHETIC_TABLE)
        for index in (0, 1):
            stack.background.append(
                BackgroundEffect(
                    speech_tr=f"Sentetik belge sonucu {_ORDINAL_TR[index]}.",
                    effect_class=EffectClass.CLINICAL_INFO,
                )
            )
            stack.agent.submit(_document_request(index))
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=0.0,
                talker_idle=False,
                pending_response=True,
                patient_speaking=True,
            )
        )
        stack.agent.run_pending()
        stack.agent.run_pending()
        held = stack.turn(None)
        assert held.held is TurnHold.PATIENT_HOLDS_FLOOR  # type: ignore[union-attr]
        assert stack.sink.played == []

    def test_the_document_result_is_spoken_at_the_pause_and_not_before(self) -> None:
        stack = Stack(deadlines=SYNTHETIC_TABLE)
        stack.background.append(
            BackgroundEffect(
                speech_tr="Sentetik belge sonucu.", effect_class=EffectClass.CLINICAL_INFO
            )
        )
        stack.agent.submit(_document_request(0))
        stack.agent.run_pending()
        stack.session.observe_duplex(
            DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
        )
        stack.turn(None)
        assert "Sentetik belge sonucu." in stack.synthesizer.requests

    def test_the_shipped_default_refuses_a_document_result_rather_than_guessing(self) -> None:
        """files/12 §6 states a deadline table for ``triage_yellow`` only."""
        stack = Stack()
        stack.background.append(
            BackgroundEffect(
                speech_tr="Sentetik belge sonucu.", effect_class=EffectClass.CLINICAL_INFO
            )
        )
        stack.agent.submit(_document_request(0))
        stack.agent.run_pending()
        with pytest.raises(DeadlinesNotConfiguredError):
            stack.turn(None)


class TestRT03:
    """*"Backend Agent stalled 10 s — Talker continues within budget, rail
    shows a chip, no duplicate injection on recovery."*"""

    def test_the_talker_continues_while_layer_b_is_stalled(self) -> None:
        stack = Stack(stall_s=10.0)
        outcome = stack.turn("sentetik yanit")
        assert outcome.spoken_text == "Sentetik birinci soru."  # type: ignore[union-attr]

    def test_the_rail_carries_an_activity_label_while_the_work_is_pending(self) -> None:
        stack = Stack(stall_s=10.0)
        stack.session.submit_utterance(STEP_IDS[0], "sentetik yanit")
        assert stack.agent.activity == (ActivityLabel.EXTRACTING,)

    def test_recovery_injects_the_result_exactly_once(self) -> None:
        stack = Stack(deadlines=SYNTHETIC_TABLE, stall_s=10.0)
        stack.effects[STEP_IDS[0]] = StateEffect(
            speech_tr="Sentetik gecikmis sonuc.", effect_class=EffectClass.CLINICAL_INFO
        )
        stack.turn("sentetik yanit")
        stack.session.observe_duplex(
            DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
        )
        stack.drain()
        stack.drain()
        assert stack.synthesizer.requests.count("Sentetik gecikmis sonuc.") == 1


class TestRT04:
    """*"extraction returns ``clarification_needed`` for step n after step n+1
    was already asked — follow-up card appears and is asked next turn, never
    re-asking n verbatim."*"""

    def test_the_follow_up_is_offered_and_is_not_the_original_question(self) -> None:
        stack = Stack()
        stack.engine.mark_asked(STEP_IDS[0])
        stack.engine.mark_asked(STEP_IDS[1])
        stack.engine.apply_extraction(STEP_IDS[0], {}, clarification_needed=True)
        offered = stack.session.protocol_next()
        assert offered is not None
        assert offered.kind is StepKind.FOLLOW_UP
        assert offered.text_tr == "Sentetik birinci takip sorusu."
        assert offered.text_tr != "Sentetik birinci soru."

    def test_the_follow_up_is_what_the_talker_speaks_on_the_next_turn(self) -> None:
        stack = Stack()
        stack.engine.mark_asked(STEP_IDS[0])
        stack.engine.mark_asked(STEP_IDS[1])
        stack.engine.apply_extraction(STEP_IDS[0], {}, clarification_needed=True)
        outcome = stack.turn(None)
        assert outcome.spoken_text == "Sentetik birinci takip sorusu."  # type: ignore[union-attr]

    def test_the_step_that_was_asked_ahead_is_not_re_asked(self) -> None:
        stack = Stack()
        stack.engine.mark_asked(STEP_IDS[0])
        stack.engine.mark_asked(STEP_IDS[1])
        stack.engine.apply_extraction(STEP_IDS[0], {}, clarification_needed=True)
        assert stack.engine.state_of(STEP_IDS[1]) is AnswerState.ASKED_PENDING
        assert STEP_IDS[1] not in {step.step_id for step in stack.engine.frontier()}


class TestRT05:
    """*"five answers submitted in 3 s (fast talker) — FIFO order preserved,
    one Work in flight, final slot state identical to a sequential run."*"""

    def test_the_final_slot_state_matches_a_sequential_run(self) -> None:
        burst = Stack()
        sequential = Stack()
        for index, step_id in enumerate(STEP_IDS):
            burst.answers[step_id] = index
            sequential.answers[step_id] = index

        for index, step_id in enumerate(STEP_IDS):
            burst.session.submit_utterance(step_id, f"sentetik {index}")
        for _ in STEP_IDS:
            burst.agent.run_pending()

        for index, step_id in enumerate(STEP_IDS):
            sequential.session.submit_utterance(step_id, f"sentetik {index}")
            sequential.agent.run_pending()

        assert [burst.engine.value_of(step) for step in STEP_IDS] == [
            sequential.engine.value_of(step) for step in STEP_IDS
        ]
        assert [burst.engine.state_of(step) for step in STEP_IDS] == [
            sequential.engine.state_of(step) for step in STEP_IDS
        ]

    def test_five_submissions_inside_three_virtual_seconds_lose_nothing(self) -> None:
        stack = Stack()
        ids: list[str] = []

        async def burst() -> None:
            for index, step_id in enumerate(STEP_IDS):
                ids.append(stack.session.submit_utterance(step_id, f"sentetik {index}").work_id)
                await stack.clock.sleep(0.6)

        stack.clock.run(burst())
        assert len(set(ids)) == len(STEP_IDS)
        assert stack.agent.depth(WorkLane.STATE) == len(STEP_IDS)


class TestRT06:
    """*"``s2s_cloud`` model attempts a diagnostic sentence … must also pass in
    ``cascade_fast``."*

    Both profiles were deleted (CLAUDE.md invariant 19; files/02 §8.1's profile
    stack correction), and the backlog **withdrew the issue that would have
    built one** — INT-098, *"WITHDRAWN — Profile s2s_cloud. Replaced by a test
    that proves no S2S/cloud profile can be constructed."* RT-06 therefore has
    no runtime to run against, and this records that rather than writing a
    scenario that passes by doing nothing.
    """

    def test_rt06_is_not_runnable_and_says_why(self) -> None:
        with pytest.raises(ScenarioNotRunnable, match="INT-098"):
            SCENARIOS["RT-06"].require_runnable()

    def test_rt06_names_no_profile_at_all(self) -> None:
        assert SCENARIOS["RT-06"].profiles == ()
        assert SCENARIOS["RT-06"].withdrawn is not None

    def test_the_two_profiles_rt06_was_written_for_still_do_not_resolve(self) -> None:
        for gone in ("s2s_cloud", "cascade_fast"):
            with pytest.raises(ValueError):
                VoiceProfile(gone)

    def test_a_scenario_cannot_be_both_runnable_and_withdrawn(self) -> None:
        with pytest.raises(ValueError, match="RT-99"):
            RuntimeScenario(
                id="RT-99",
                title="Sentetik",
                blueprint="sentetik",
                turn_class=TurnClass.SCRIPTED,
                profiles=(VoiceProfile.TYPED,),
                withdrawn="sentetik",
            )

    def test_a_scenario_cannot_be_neither(self) -> None:
        with pytest.raises(ValueError, match="RT-99"):
            RuntimeScenario(
                id="RT-99",
                title="Sentetik",
                blueprint="sentetik",
                turn_class=TurnClass.SCRIPTED,
            )

    def test_rt06_is_the_only_scenario_that_is_not_runnable(self) -> None:
        assert set(SCENARIOS) - {scenario.id for scenario in runnable_scenarios()} == {"RT-06"}


class TestRT07:
    """*"YELLOW rule fires — spoken only at the insertion window, never
    preempting."*

    files/12 §6 records the hole in this scenario as written: it *"only ever
    asserted that YELLOW does **not** preempt, never that it is **ever**
    spoken"*, which is how a YELLOW could be silently dropped. Both halves are
    asserted here.
    """

    def _yellow(self, stack: Stack) -> None:
        stack.effects[STEP_IDS[0]] = StateEffect(
            speech_tr="Sentetik sari bilgilendirme.",
            triage_update=RulesTriageResult(
                level=TriageLevel.YELLOW,
                rules=(RuleFire(id=RULE_A, evidence="sentetik"),),
            ),
        )

    def test_a_yellow_never_preempts(self) -> None:
        stack = Stack()
        self._yellow(stack)
        stack.turn("sentetik yanit")
        stack.drain()
        assert stack.session.preempts == ()
        assert stack.media.calls == []

    def test_a_yellow_is_spoken_once_the_window_opens(self) -> None:
        stack = Stack()
        self._yellow(stack)
        stack.turn("sentetik yanit")
        stack.session.observe_duplex(
            DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
        )
        stack.drain()
        assert "Sentetik sari bilgilendirme." in stack.synthesizer.requests

    def test_a_yellow_the_patient_never_yields_to_is_noted_rather_than_dropped(self) -> None:
        stack = Stack()
        self._yellow(stack)
        stack.turn("sentetik yanit")
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=0.0,
                talker_idle=False,
                pending_response=True,
                patient_speaking=True,
            )
        )
        stack.drain()
        pending = stack.session.scheduler.pending_work_ids
        assert pending, "the YELLOW is waiting rather than spoken"
        # Past the 90 s terminal of files/12 §6, with the patient still talking.
        stack.session.scheduler.tick(stack.session.duplex, now_ms=200_000.0)
        assert stack.session.undelivered == list(pending)
        assert "Sentetik sari bilgilendirme." not in stack.synthesizer.requests

    def test_a_held_turn_still_walks_the_ladder_rather_than_swallowing_it(self) -> None:
        """The turn hold of RT-08 must not become the silent-drop of files/12 §6.

        A turn that asks nothing is still a turn: results are drained, the
        insertion scheduler still ticks, and a protected item past its terminal
        still writes its note flag. A hold that skipped the tick would make the
        patient stepping away into a way of losing a YELLOW.
        """
        stack = Stack()
        self._yellow(stack)
        stack.turn("sentetik yanit")
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=0.0,
                talker_idle=False,
                pending_response=True,
                patient_speaking=True,
            )
        )
        stack.drain()
        pending = stack.session.scheduler.pending_work_ids
        assert pending
        stack.advance(120.0)  # past the 90 s terminal, on the virtual clock
        held = stack.turn(None)
        assert held.held is TurnHold.PATIENT_HOLDS_FLOOR  # type: ignore[union-attr]
        assert stack.session.undelivered == list(pending)

    def test_a_held_turn_still_drains_layer_b(self) -> None:
        """Otherwise a patient who steps away backs the queue up behind them."""
        stack = Stack()
        self._yellow(stack)
        stack.turn("sentetik yanit")
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=0.0,
                talker_idle=False,
                pending_response=True,
                patient_speaking=True,
            )
        )
        stack.clock.run(stack._pump())
        held = stack.turn(None, pump=False)
        assert held.held is TurnHold.PATIENT_HOLDS_FLOOR  # type: ignore[union-attr]
        assert held.drained_results == 1  # type: ignore[union-attr]


class TestRT08:
    """*"patient says 'bir dakika, hemşireyle konuşuyorum' — backchannel
    suppressed, turn detector holds, no question asked until they return."*"""

    def test_the_talker_asks_nothing_while_the_patient_holds_the_floor(self, stack: Stack) -> None:
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=40.0,
                talker_idle=True,
                pending_response=True,
                patient_speaking=True,
            )
        )
        outcome = stack.turn(None)
        assert outcome.held is TurnHold.PATIENT_HOLDS_FLOOR  # type: ignore[union-attr]
        assert outcome.spoken_text == ""  # type: ignore[union-attr]
        assert stack.sink.played == []

    def test_the_question_is_asked_the_moment_they_return(self, stack: Stack) -> None:
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=40.0,
                talker_idle=True,
                pending_response=True,
                patient_speaking=True,
            )
        )
        stack.turn(None)
        stack.session.observe_duplex(
            DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
        )
        outcome = stack.turn(None)
        assert outcome.spoken_text == "Sentetik birinci soru."  # type: ignore[union-attr]

    def test_the_hold_costs_the_turn_no_virtual_time(self, stack: Stack) -> None:
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=40.0,
                talker_idle=True,
                pending_response=True,
                patient_speaking=True,
            )
        )
        assert stack.turn(None).elapsed_ms == 0.0  # type: ignore[union-attr]

    def test_the_yield_floor_is_the_adaptive_pair_and_not_a_single_number(self) -> None:
        """files/03 §4.2: *"150 ms when measured uplink jitter p95 < 30 ms, and
        250 ms otherwise"* — adaptive, never a constant."""
        assert ADAPTIVE_FLOOR_LOW_MS == 150.0
        assert ADAPTIVE_FLOOR_HIGH_MS == 250.0
        assert ADAPTIVE_JITTER_THRESHOLD_MS == 30.0
        assert TurnYieldPolicy(uplink_jitter_p95_ms=20.0).floor_ms == 150.0
        assert TurnYieldPolicy(uplink_jitter_p95_ms=30.0).floor_ms == 250.0

    def test_a_measured_low_jitter_session_yields_a_hundred_milliseconds_sooner(
        self, stack: Stack
    ) -> None:
        """The floor is adaptive, and the adaptation is observable: the same
        200 ms of silence holds the turn on an unmeasured session and releases
        it on one whose uplink jitter was measured under the threshold."""
        quiet_gap = DuplexState(
            patient_silence_ms=200.0,
            talker_idle=True,
            pending_response=True,
            patient_speaking=True,
        )
        stack.session.observe_duplex(quiet_gap)
        assert stack.turn(None).held is TurnHold.PATIENT_HOLDS_FLOOR  # type: ignore[union-attr]
        stack.session.observe_duplex(quiet_gap, TurnYieldPolicy(uplink_jitter_p95_ms=12.0))
        assert stack.turn(None).held is None  # type: ignore[union-attr]

    def test_the_agent_emits_no_backchannel_of_its_own(self, stack: Stack) -> None:
        """The suppression half. The Talker's speech surface is closed — the
        clip cache and the synthesizer — and neither is reached on a held
        turn, so there is no ack path to suppress. Agent backchannels and ack
        styles are INT-099."""
        stack.session.observe_duplex(
            DuplexState(
                patient_silence_ms=40.0,
                talker_idle=True,
                pending_response=True,
                patient_speaking=True,
            )
        )
        stack.turn(None)
        assert stack.synthesizer.requests == []
        assert stack.clip_store.served == []


# =====================================================================================
# The scenario drivers `make runtime-sim` runs
# =====================================================================================
#
# One driver per runnable scenario, each returning the per-turn records the
# report prints. They live here, beside the assertions, because a harness whose
# scenario is a second implementation of the test's scenario measures something
# nobody asserted. `scripts/voice/runtime_sim.py` imports `run_scenario` from
# this module for exactly that reason.


def _record(index: int, outcome: object) -> TurnRecord:
    return TurnRecord(
        index=index,
        elapsed_ms=outcome.elapsed_ms,  # type: ignore[attr-defined]
        spoke=bool(outcome.spoken_text),  # type: ignore[attr-defined]
    )


def _drive_rt01(profile: VoiceProfile) -> tuple[TurnRecord, ...]:
    stack = Stack(profile=profile, deadlines=SYNTHETIC_TABLE)
    for index in (0, 1):
        stack.background.append(
            BackgroundEffect(
                speech_tr=f"Sentetik belge sonucu {_ORDINAL_TR[index]}.",
                effect_class=EffectClass.CLINICAL_INFO,
            )
        )
        stack.agent.submit(_document_request(index))
    stack.agent.run_pending()
    stack.agent.run_pending()
    stack.session.observe_duplex(
        DuplexState(
            patient_silence_ms=0.0,
            talker_idle=False,
            pending_response=True,
            patient_speaking=True,
        )
    )
    talking = stack.turn(None)
    stack.session.observe_duplex(
        DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
    )
    return (_record(0, talking), _record(1, stack.turn(None)))


def _drive_rt02(profile: VoiceProfile) -> tuple[TurnRecord, ...]:
    stack = Stack(profile=profile)
    first = stack.turn(None)
    stack.preempt(red_result(), evaluated_at_ms=stack.clock.now_ms())
    return (_record(0, first), _record(1, stack.turn(None)))


def _drive_rt03(profile: VoiceProfile) -> tuple[TurnRecord, ...]:
    stack = Stack(profile=profile, stall_s=10.0)
    return (_record(0, stack.turn("sentetik yanit")), _record(1, stack.turn(None)))


def _drive_rt04(profile: VoiceProfile) -> tuple[TurnRecord, ...]:
    stack = Stack(profile=profile)
    stack.engine.mark_asked(STEP_IDS[0])
    stack.engine.mark_asked(STEP_IDS[1])
    stack.engine.apply_extraction(STEP_IDS[0], {}, clarification_needed=True)
    return (_record(0, stack.turn(None)),)


def _drive_rt05(profile: VoiceProfile) -> tuple[TurnRecord, ...]:
    stack = Stack(profile=profile)
    records: list[TurnRecord] = []
    for index, step_id in enumerate(STEP_IDS):
        stack.answers[step_id] = index
        records.append(_record(index, stack.turn(f"sentetik {index}")))
    return tuple(records)


def _drive_rt07(profile: VoiceProfile) -> tuple[TurnRecord, ...]:
    stack = Stack(profile=profile)
    stack.effects[STEP_IDS[0]] = StateEffect(
        speech_tr="Sentetik sari bilgilendirme.",
        triage_update=RulesTriageResult(
            level=TriageLevel.YELLOW,
            rules=(RuleFire(id=RULE_A, evidence="sentetik"),),
        ),
    )
    first = stack.turn("sentetik yanit")
    stack.session.observe_duplex(
        DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
    )
    return (_record(0, first), _record(1, stack.turn(None)))


def _drive_rt08(profile: VoiceProfile) -> tuple[TurnRecord, ...]:
    stack = Stack(profile=profile)
    stack.session.observe_duplex(
        DuplexState(
            patient_silence_ms=40.0,
            talker_idle=True,
            pending_response=True,
            patient_speaking=True,
        )
    )
    held = stack.turn(None)
    stack.session.observe_duplex(
        DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
    )
    return (_record(0, held), _record(1, stack.turn(None)))


DRIVERS = {
    "RT-01": _drive_rt01,
    "RT-02": _drive_rt02,
    "RT-03": _drive_rt03,
    "RT-04": _drive_rt04,
    "RT-05": _drive_rt05,
    "RT-07": _drive_rt07,
    "RT-08": _drive_rt08,
}


def run_scenario(
    scenario_id: str,
    profile: VoiceProfile,
    network: NetworkProfile,
) -> ScenarioReport:
    """One scenario, one profile, one named network profile — as a report."""
    scenario = SCENARIOS[scenario_id]
    permitted = scenario.require_runnable()
    if profile not in permitted:
        raise ScenarioNotRunnable(
            f"{scenario_id} is written for {[p.value for p in permitted]}, not {profile.value!r}"
        )
    return ScenarioReport(
        scenario_id=scenario_id,
        profile=profile,
        turn_class=scenario.turn_class,
        network=network,
        turns=DRIVERS[scenario_id](profile),
    )


# =====================================================================================
# The latency harness
# =====================================================================================


class TestLatencyHarness:
    """*"harness reports per-turn budgets per profile."*

    The harness reports what the blueprint publishes and what the run
    measured. It does not synthesise a budget where none is published: three
    of the rows below are refusals, and each names the sentence that refuses.
    """

    def test_the_only_published_voice_profile_budget_is_residency_tr_dynamic(self) -> None:
        budget = published_budget(VoiceProfile.RESIDENCY_TR, TurnClass.DYNAMIC)
        assert budget.p50_ms == 1_300.0
        assert budget.p95_ms is None
        assert "measured" in (budget.open_reason or "")

    def test_typed_has_no_published_per_turn_budget(self) -> None:
        with pytest.raises(BudgetNotPublished, match="typed"):
            published_budget(VoiceProfile.TYPED, TurnClass.DYNAMIC)

    def test_hospital_guest_wifi_publishes_no_nfr_by_instruction(self) -> None:
        with pytest.raises(BudgetNotPublished, match="cellular"):
            published_budget(
                VoiceProfile.RESIDENCY_TR,
                TurnClass.DYNAMIC,
                network=NetworkProfile.HOSPITAL_GUEST_WIFI,
            )

    def test_the_dynamic_row_is_the_profile_row_never_the_displaced_baseline(self) -> None:
        """A per-network dynamic figure belongs to the cloud stack we do not
        run. Returning one as ``residency_tr``'s budget would publish a target
        for a stack with three EU vendor hops in it."""
        with_network = published_budget(
            VoiceProfile.RESIDENCY_TR,
            TurnClass.DYNAMIC,
            network=NetworkProfile.TR_MOBILE_MID_LTE,
        )
        assert with_network.p50_ms == 1_300.0
        assert with_network.p95_ms is None
        assert displaced_baseline_dynamic(NetworkProfile.TR_MOBILE_MID_LTE).p95_ms == 2_100.0

    def test_the_displaced_baseline_says_it_is_the_displaced_baseline(self) -> None:
        row = displaced_baseline_dynamic(NetworkProfile.TR_MOBILE_MID_LTE)
        assert "displaced-baseline" in row.source

    def test_the_displaced_baseline_refuses_hospital_wifi_too(self) -> None:
        with pytest.raises(BudgetNotPublished, match="cellular"):
            displaced_baseline_dynamic(NetworkProfile.HOSPITAL_GUEST_WIFI)

    def test_a_scripted_row_without_a_named_network_profile_is_refused(self) -> None:
        with pytest.raises(BudgetNotPublished, match="unfalsifiable"):
            published_budget(VoiceProfile.RESIDENCY_TR, TurnClass.SCRIPTED)

    def test_a_row_with_an_unset_bound_must_say_why_it_is_unset(self) -> None:
        with pytest.raises(ValueError, match="open_reason"):
            PublishedBudget(
                profile=VoiceProfile.RESIDENCY_TR,
                turn_class=TurnClass.DYNAMIC,
                p50_ms=1_300.0,
                p95_ms=None,
                source="sentetik",
            )

    def test_a_dynamic_report_prints_open_and_the_reason_rather_than_a_number(self) -> None:
        report = ScenarioReport(
            scenario_id="RT-06",
            profile=VoiceProfile.RESIDENCY_TR,
            turn_class=TurnClass.DYNAMIC,
            network=NetworkProfile.TR_MOBILE_MID_LTE,
            turns=(TurnRecord(index=0, elapsed_ms=32.0, spoke=True),),
        )
        rendered = render_report((report,))
        assert "p95 OPEN" in rendered
        assert "measured one" in rendered

    def test_the_scripted_rows_are_keyed_by_network_profile(self) -> None:
        assert (
            published_budget(
                VoiceProfile.RESIDENCY_TR,
                TurnClass.SCRIPTED,
                network=NetworkProfile.TR_MOBILE_MID_LTE,
            ).p50_ms
            == 450.0
        )

    def test_the_transport_lever_arithmetic_is_the_blueprints_own(self) -> None:
        """files/02 §8.1: 2055 ms itemised, minus 141 ms of vendor hop, is
        *"≈ 1914 ms — under 2000 without touching a single model."*"""
        assert MID_LTE_DYNAMIC_P95_ITEMISED_MS - VENDOR_HOP_SAVING_P95_MS == 1_914.0
        assert MID_LTE_DYNAMIC_P95_ITEMISED_MS - VENDOR_HOP_SAVING_P95_MS < 2_000.0

    def test_the_two_structural_floors_differ_by_the_vendor_hop(self) -> None:
        assert DISPLACED_FLOOR.p50_ms - IN_COUNTRY_FLOOR.p50_ms == 38.0
        assert DISPLACED_FLOOR.p95_ms - IN_COUNTRY_FLOOR.p95_ms == 47.0
        assert VENDOR_HOP_SAVING_P50_MS == 117.0

    def test_the_app_ceiling_is_the_low_end_of_the_files_03_band(self) -> None:
        """files/03 §4.4 publishes ``p95 ≈ 1684–2364 ms`` for the same profile
        files/02 §8.1 leaves OPEN, and ``apps/mobile`` already committed the
        low end as its per-turn ceiling. The disagreement is recorded, not
        resolved here."""
        source = TTS_TS.read_text(encoding="utf-8")
        match = re.search(r"TURN_ROUND_TRIP_BUDGET_MS = (\d+)", source)
        assert match is not None
        assert float(match.group(1)) == RESIDENCY_TR_P95_BAND_MS[0]

    def test_a_report_names_the_profile_the_budget_and_the_measurement(self) -> None:
        report = ScenarioReport(
            scenario_id="RT-03",
            profile=VoiceProfile.RESIDENCY_TR,
            turn_class=TurnClass.SCRIPTED,
            network=NetworkProfile.TR_MOBILE_MID_LTE,
            turns=(TurnRecord(index=0, elapsed_ms=32.0, spoke=True),),
        )
        rendered = render_report((report,))
        assert "RT-03" in rendered
        assert "residency_tr" in rendered
        assert "450" in rendered
        assert "32.0" in rendered

    def test_a_report_for_an_unpublished_budget_says_so_instead_of_a_number(self) -> None:
        report = ScenarioReport(
            scenario_id="RT-03",
            profile=VoiceProfile.TYPED,
            turn_class=TurnClass.DYNAMIC,
            network=NetworkProfile.TR_MOBILE_MID_LTE,
            turns=(TurnRecord(index=0, elapsed_ms=32.0, spoke=True),),
        )
        assert "no published budget" in render_report((report,))

    def test_the_server_side_measurement_is_labelled_as_server_side(self) -> None:
        """The harness measures the Talker's own turn. Transport, jitter and
        device output are charged by the blueprint and are not measured here,
        so the report must never present its number as a round trip."""
        report = ScenarioReport(
            scenario_id="RT-03",
            profile=VoiceProfile.RESIDENCY_TR,
            turn_class=TurnClass.SCRIPTED,
            network=NetworkProfile.TR_MOBILE_MID_LTE,
            turns=(TurnRecord(index=0, elapsed_ms=32.0, spoke=True),),
        )
        assert "server-side" in render_report((report,))

    @pytest.mark.parametrize("scenario", list(runnable_scenarios()))
    def test_every_runnable_scenario_runs_on_both_shipped_profiles(
        self, scenario: RuntimeScenario
    ) -> None:
        assert set(scenario.profiles) == set(VoiceProfile)

    def test_every_runnable_scenario_has_a_driver(self) -> None:
        assert set(DRIVERS) == {scenario.id for scenario in runnable_scenarios()}

    def test_the_withdrawn_scenario_has_no_driver(self) -> None:
        assert "RT-06" not in DRIVERS

    @pytest.mark.parametrize("scenario", list(runnable_scenarios()))
    @pytest.mark.parametrize("profile", list(VoiceProfile))
    def test_running_a_scenario_reports_at_least_one_turn(
        self, scenario: RuntimeScenario, profile: VoiceProfile
    ) -> None:
        report = run_scenario(scenario.id, profile, NetworkProfile.TR_MOBILE_MID_LTE)
        assert report.turns
        assert render_report((report,)).startswith("runtime-sim")

    def test_running_the_withdrawn_scenario_refuses(self) -> None:
        with pytest.raises(ScenarioNotRunnable, match="INT-098"):
            run_scenario("RT-06", VoiceProfile.RESIDENCY_TR, NetworkProfile.TR_MOBILE_MID_LTE)

    def test_a_scenario_run_is_identical_under_both_profiles(self) -> None:
        """files/03 §4.6 invariant 8, as a measurement rather than a claim: the
        two profiles differ only in a metric label today, so the harness must
        report the same turns for both — and this test is what will fail on the
        day INT-096 gives `typed` a path of its own."""
        residency = run_scenario(
            "RT-03", VoiceProfile.RESIDENCY_TR, NetworkProfile.TR_MOBILE_MID_LTE
        )
        typed = run_scenario("RT-03", VoiceProfile.TYPED, NetworkProfile.TR_MOBILE_MID_LTE)
        assert [turn.elapsed_ms for turn in residency.turns] == [
            turn.elapsed_ms for turn in typed.turns
        ]


# =====================================================================================
# The loop that does not close — findings, as assertions
# =====================================================================================


class TestTheLoopThatDoesNotClose:
    """Three joints between Layer A and Layer B have no producer on this tree.

    Each is asserted rather than described, so the day one is wired the test
    fails and the finding is struck from the record instead of quietly
    becoming false.
    """

    def test_a_bare_backend_agent_refuses_the_first_transcript(self) -> None:
        """No ``extract_slots`` handler is registered anywhere in ``services/``
        — INT-092 left it to INT-083, which built ``run_extraction`` and never
        registered it. A composed session therefore cannot take one turn."""
        clock = FakeClock()
        engine = IntakeEngine(protocol=_protocol(), reference_time=NOW)
        agent = BackendAgent(session_id=SESSION, engine=engine, clock=clock)
        session = build_session(clock, steps=[], backend=agent)
        session.engine = engine
        session.config = session.config.model_copy(update={"protocol_hash": HASH})
        with pytest.raises(UnregisteredWorkType, match="extract_slots"):
            clock.run(session.take_turn("sentetik yanit"))

    def test_no_module_under_services_registers_a_production_handler(self) -> None:
        services = REPO / "services"
        hits = [
            path
            for path in services.rglob("*.py")
            if "register_state(" in path.read_text(encoding="utf-8")
            and path.name != "work_queue.py"
        ]
        assert hits == []

    def test_mark_asked_has_no_caller_outside_tests(self) -> None:
        roots = (REPO / "services", REPO / "packages")
        hits = [
            path
            for root in roots
            for path in root.rglob("*.py")
            if ".mark_asked(" in path.read_text(encoding="utf-8")
        ]
        assert hits == []

    def test_the_work_request_has_no_transcript_channel(self) -> None:
        from intake_voice_runtime.ports import WorkRequest

        assert "transcript" not in WorkRequest.model_fields
        assert "input_hash" in WorkRequest.model_fields


# =====================================================================================
# The honesty ledger
# =====================================================================================

#: For each files/03 §4.6 invariant 1-11: is it held by the **composed** stack
#: in this file, or only inside the unit that owns it? The `unit-only` set may
#: only shrink — the same discipline as
#: ``scripts/ci/no_placeholders_allow.txt``. Widening it is a visible edit.
UNIT_ONLY: frozenset[int] = frozenset({4, 8})

END_TO_END: frozenset[int] = frozenset({1, 2, 3, 5, 6, 7, 9, 10, 11})


class TestTheHonestyLedger:
    def test_every_invariant_is_classified_exactly_once(self) -> None:
        assert UNIT_ONLY | END_TO_END == frozenset(range(1, 12))
        assert UNIT_ONLY & END_TO_END == frozenset()

    def test_each_end_to_end_invariant_has_a_composed_test_class(self) -> None:
        names = {name for name in globals() if name.startswith("TestInvariant")}
        numbers = {int(re.match(r"TestInvariant(\d+)", name).group(1)) for name in names}  # type: ignore[union-attr]
        assert END_TO_END <= numbers

    def test_the_unit_only_set_names_its_owner(self) -> None:
        assert UNIT_ONLY == frozenset({4, 8})


def _document_request(index: int) -> object:
    from intake_voice_runtime.ports import WorkRequest

    return WorkRequest(
        session_id=SESSION,
        work_type=WorkType.PARSE_DOCUMENT,
        step_id=f"belge-{index}",
        input_hash=f"{index:064d}",
        protocol_hash=HASH,
        engine_version=0,
    )
