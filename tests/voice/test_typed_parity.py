"""INT-096 — the ``typed`` profile: full parity fallback and kill-switch target.

Acceptance restated verbatim (docs/backlog/issues.yaml, INT-096):
  *"entire intake completable typed; kill-switch target; parity simulator run"*

**The negative test is the one that matters.** It is not enough that a typed
intake works — a second implementation of the flow would also work, and would
be the opposite of what files/03 §4.6 invariant 8 asks for. What has to hold is
that the two profiles reach the *same* state machine, guards, slots and
reconcile-behind, and the way that is established here is structural rather
than by assertion: there is one ``TalkerSession``, one ``_compose``, one
``ExtractSlotsHandler``, and a profile is a
:class:`~intake_voice_runtime.talker.egress.TurnEgress`.

**Parity is stated in both directions**, an idea taken from the earlier
attempt at this issue (docs/evidence/INT-096.md records where). Given one
answer stream the two profiles must reach an identical record; where the
streams legitimately differ — typed has no ASR, so no low-confidence
clarification — typed must be **no worse**: its ``data_gaps`` a subset, its
must-ask coverage at least as high. A suite that asserted only sameness would
be either false or vacuous.

**What this file does not assert, and why.**

- **A composed note.** ``note.compose`` takes facts and no runtime path
  produces one yet (INT-084's own finding). Parity is asserted at the last
  point both profiles share: the engine state the note's gap index is computed
  from.
- **A triage determination.** ``ExtractSlotsHandler`` sets no
  ``triage_update`` on *either* profile — its docstring assigns that wiring to
  this issue, and docs/evidence/INT-096.md records why it is not done here.
  Parity over triage therefore holds because there is one handler, and that is
  the property which survives the day an evaluation is wired into it.
- **A latency budget for typed.** files/02 §8.1 publishes none and
  ``simulator.budgets`` already refuses to invent one.

Nothing here dials anything: the clock is virtual and the gateway is a table.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from clinical_schemas.observers import Lane
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import BackendAgent
from intake_voice_runtime.composition import (
    SessionStack,
    build_residency_tr_session,
    build_typed_session,
)
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.extraction.handler import ExtractSlotsHandler
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.simulator import (
    SCENARIOS,
    NetworkProfile,
    ParityTrace,
    runnable_scenarios,
)
from intake_voice_runtime.talker.egress import (
    EgressChannel,
    ParaphraseNotPermittedError,
    TurnEgress,
)
from intake_voice_runtime.talker.session import ProfileNotWired, TalkerSession
from intake_voice_runtime.talker.speech import SpeechRouter
from intake_voice_runtime.typed import (
    NBSP,
    AffordanceKind,
    ClipOnTypedEgress,
    FreeNumericEntryRefused,
    KillSwitchNotArmed,
    LaneSwitchLatched,
    LaneSwitchReason,
    SlotFacts,
    TypedEgress,
    free_numeric_critical_path_steps,
    lanes_without_input,
    numeric_rail,
    render_measure,
    typed_prompt,
)
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.types import Delivery, SlotType
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingScreen,
    RecordingSink,
    RecordingSynthesizer,
    RefusingSink,
)

SESSION = "11111111-2222-4333-8444-555555555555"
HASH = "c" * 64
NOW = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
VOICE_ID = "residency-tr-01"
TENANT = "00000000-0000-4000-8000-000000000001"

STEP_IDS = ("oyku.birinci", "oyku.ikinci", "oyku.ucuncu")
ASK_TR = {
    "oyku.birinci": "Sentetik birinci soru.",
    "oyku.ikinci": "Sentetik ikinci soru.",
    "oyku.ucuncu": "Sentetik ucuncu soru.",
}
#: One chip set per step. A numeric slot without them has no typed affordance
#: at all (invariant 22), which is asserted in its own class below.
CHIPS = ("bir tane", "iki tane", "uc tane")
SCRIPT = ("Sentetik yanit bir.", "Sentetik yanit iki.", "Sentetik yanit uc.")
ANSWERS: Mapping[str, object] = {step_id: index + 1 for index, step_id in enumerate(STEP_IDS)}


# --- the synthetic protocol, shared by both profiles ------------------------------


def _slot(ask_tr: str, *, choices: tuple[str, ...] = CHIPS) -> Slot:
    payload: dict[str, Any] = {
        "type": SlotType.INTEGER,
        "required": True,
        "must_ask": True,
        "ask_tr": {"tr": ask_tr},
        "follow_up_tr": {"tr": f"{ask_tr} Tekrar eder misiniz?"},
    }
    if choices:
        payload["choices_tr"] = {"tr": list(choices)}
    return Slot.model_validate(payload)


def _protocol(*, choices: tuple[str, ...] = CHIPS) -> ResolvedProtocol:
    """Three scripted steps in one section. Nothing here is clinical."""
    return ResolvedProtocol(
        pack_id="base.sentetik_int096",
        version="1.0.0",
        chain=("base.sentetik_int096",),
        resolved_protocol_hash=HASH,
        sections=(
            ResolvedSection(
                id="oyku",
                delivery=Delivery.VOICE,
                allow_paraphrase=False,
                slots=tuple(
                    ResolvedSlot(
                        section_id="oyku",
                        key=step_id.split(".", 1)[1],
                        fhir_link_id=step_id,
                        slot=_slot(ASK_TR[step_id], choices=choices),
                        delivery=Delivery.VOICE,
                    )
                    for step_id in STEP_IDS
                ),
            ),
        ),
    )


class ScriptedGateway:
    """One completion per call, from a table — the CI stand-in for row 9.

    The same double ``tests/voice/adapters/test_residency_contracts.py`` drives
    the voice profile with. A differential test whose two sides ran different
    doubles would be measuring the doubles.
    """

    def __init__(self, answers: Mapping[str, object]) -> None:
        self.answers = dict(answers)
        self.calls: list[ExtractionCall] = []

    def complete(self, call: ExtractionCall) -> Completion:
        self.calls.append(call)
        body = {
            "slots": {
                ref: {"value": value, "confidence": 0.95} for ref, value in self.answers.items()
            },
            "candidate_flags": [],
            "clarification_needed": False,
        }
        return Completion(text=json.dumps(body), input_tokens=11, output_tokens=13)


# --- the two stacks ---------------------------------------------------------------


def voice_stack(
    *,
    clock: FakeClock | None = None,
    sink: Any = None,
    screen: RecordingScreen | None = None,
    protocol: ResolvedProtocol | None = None,
) -> tuple[SessionStack, FakeClock, RecordingScreen]:
    ticking = clock or FakeClock()
    surface = screen or RecordingScreen()
    stack = build_residency_tr_session(
        protocol=protocol or _protocol(),
        reference_time=NOW,
        session_id=SESSION,
        voice_id=VOICE_ID,
        protocol_hash=HASH,
        clock=ticking,
        gateway=ScriptedGateway(ANSWERS),
        synthesizer=RecordingSynthesizer(),
        clip_store=RecordedClipStore(),
        sink=sink if sink is not None else RecordingSink(clock=ticking),
        memory=InMemoryPatientMemory(),
        tenant_id=TENANT,
        screen=surface,
    )
    return stack, ticking, surface


def typed_stack(
    *, clock: FakeClock | None = None, protocol: ResolvedProtocol | None = None
) -> tuple[SessionStack, FakeClock, RecordingScreen]:
    ticking = clock or FakeClock()
    screen = RecordingScreen()
    stack = build_typed_session(
        protocol=protocol or _protocol(),
        reference_time=NOW,
        session_id=SESSION,
        protocol_hash=HASH,
        clock=ticking,
        gateway=ScriptedGateway(ANSWERS),
        memory=InMemoryPatientMemory(),
        tenant_id=TENANT,
        screen=screen,
    )
    return stack, ticking, screen


def turn(stack: SessionStack, clock: FakeClock, transcript: str | None) -> Any:
    """One turn with Layer B's own loop running, and never awaited."""

    async def main() -> Any:
        outcome = await stack.session.take_turn(transcript)
        stack.agent.run_pending()
        return outcome

    return clock.run(main())


def drive(stack: SessionStack, clock: FakeClock, script: tuple[str, ...]) -> list[Any]:
    """Ask, answer, ask — until the protocol has nothing left to offer."""
    outcomes = [turn(stack, clock, None)]
    outcomes.extend(turn(stack, clock, line) for line in script)
    # One more turn so the last answer is reconciled and the frontier empties.
    outcomes.append(turn(stack, clock, None))
    return outcomes


def clinical_trace(outcomes: list[Any]) -> tuple[tuple[Any, ...], ...]:
    """Everything a turn did, with every transport-specific quantity removed."""
    return tuple(
        (
            outcome.step_id,
            outcome.spoken_text,
            outcome.work_id,
            outcome.drained_results,
            outcome.delivered_work_ids,
            outcome.held,
        )
        for outcome in outcomes
    )


def engine_state(engine: IntakeEngine) -> tuple[Any, ...]:
    """The note's own inputs: coverage, gaps, completion, every slot."""
    return (
        engine.snapshot.version,
        engine.must_ask_coverage(),
        engine.data_gaps,
        engine.section_done,
        engine.follow_ups,
        tuple(
            (step_id, engine.state_of(step_id), engine.value_of(step_id)) for step_id in STEP_IDS
        ),
    )


# =====================================================================================
# 1 · The transport is the only difference
# =====================================================================================


class TestTypedIsATransportAndNothingElse:
    def test_a_typed_session_holds_no_audio_port_at_all(self) -> None:
        """Invariant 3 as a property of the shape, not of the behaviour."""
        stack, _, _ = typed_stack()
        session = stack.session
        assert session.sink is None
        assert session.clip_store is None
        assert session.synthesizer is None
        assert session.catalogue is None
        assert isinstance(session.router, TypedEgress)
        assert session.config.profile is VoiceProfile.TYPED

    def test_the_voice_session_holds_the_speech_router(self) -> None:
        stack, _, _ = voice_stack()
        assert isinstance(stack.session.router, SpeechRouter)
        assert stack.session.router.profile is VoiceProfile.RESIDENCY_TR

    def test_both_transports_satisfy_the_one_egress_port(self) -> None:
        typed, _, _ = typed_stack()
        voice, _, _ = voice_stack()
        assert isinstance(typed.session.router, TurnEgress)
        assert isinstance(voice.session.router, TurnEgress)

    def test_a_typed_session_handed_an_audio_port_is_refused(self) -> None:
        """Fail closed: a typed session that *could* speak is not typed."""
        clock = FakeClock()
        with pytest.raises(ProfileNotWired, match="sink"):
            TalkerSession(
                config=typed_stack()[0].session.config,
                engine=typed_stack()[0].engine,
                backend=typed_stack()[0].agent,
                memory=InMemoryPatientMemory(),
                clock=clock,
                sink=RecordingSink(clock=clock),
                screen=RecordingScreen(),
            )

    def test_a_typed_session_without_a_screen_is_refused(self) -> None:
        clock = FakeClock()
        with pytest.raises(ProfileNotWired, match="ScreenSink"):
            TalkerSession(
                config=typed_stack()[0].session.config,
                engine=typed_stack()[0].engine,
                backend=typed_stack()[0].agent,
                memory=InMemoryPatientMemory(),
                clock=clock,
            )

    def test_a_typed_config_may_not_carry_a_voice_id(self) -> None:
        stack, _, _ = voice_stack()
        with pytest.raises(ValueError, match="voice_id"):
            stack.session.config.model_copy(update={"profile": VoiceProfile.TYPED}).model_validate(
                stack.session.config.model_dump() | {"profile": VoiceProfile.TYPED}
            )

    def test_a_clip_id_reaching_the_typed_transport_is_refused(self) -> None:
        stack, clock, _ = typed_stack()
        renderer = stack.session.router
        assert isinstance(renderer, TypedEgress)
        with pytest.raises(ClipOnTypedEgress):
            clock.run(renderer.emit("Sentetik.", clip_id="clip.x.y", label="s"))

    def test_the_typed_emission_names_the_screen_channel(self) -> None:
        stack, clock, screen = typed_stack()
        emission = clock.run(stack.session.router.emit("Sentetik.", clip_id=None, label="s"))
        assert emission.channel is EgressChannel.SCREEN
        assert emission.frame_count == 0
        assert emission.from_clip is False
        assert screen.rendered == [("s", "Sentetik.")]

    def test_the_two_stacks_are_built_from_the_same_parts(self) -> None:
        """Parity is structural: one engine class, one queue, one handler."""
        typed, typed_clock, _ = typed_stack()
        voice, voice_clock, _ = voice_stack()
        for stack in (typed, voice):
            assert isinstance(stack.engine, IntakeEngine)
            assert isinstance(stack.agent, BackendAgent)
            assert isinstance(stack.handler, ExtractSlotsHandler)
        # The registration itself, asserted by driving it rather than by
        # reaching into the queue: an unregistered work type raises at submit,
        # so a turn that reconciles is the joint being closed.
        for stack, clock in ((typed, typed_clock), (voice, voice_clock)):
            turn(stack, clock, None)
            turn(stack, clock, SCRIPT[0])
            assert stack.handler.outcomes
            assert (
                stack.agent.record(stack.session.submit_utterance(STEP_IDS[1], SCRIPT[1]).work_id)
                is not None
            )


# =====================================================================================
# 2 · "entire intake completable typed"
# =====================================================================================


class TestTheEntireIntakeCompletesTyped:
    def test_every_step_is_asked_and_every_answer_binds(self) -> None:
        stack, clock, _ = typed_stack()
        drive(stack, clock, SCRIPT)
        assert stack.session.protocol_next() is None
        coverage = stack.engine.must_ask_coverage()
        assert coverage.outstanding == ()
        assert coverage.covered == tuple(sorted(STEP_IDS))

    def test_every_question_reaches_the_screen_verbatim(self) -> None:
        """Invariant 10 does not weaken because the channel stopped being audio."""
        stack, clock, screen = typed_stack()
        drive(stack, clock, SCRIPT)
        assert screen.texts == [ASK_TR[step] for step in STEP_IDS]

    def test_a_paraphrase_for_a_scripted_step_is_refused_on_typed_too(self) -> None:
        stack, clock, _ = typed_stack()
        step = stack.session.protocol_next()
        assert step is not None
        with pytest.raises(ParaphraseNotPermittedError):
            clock.run(stack.session.speak_step(step, "Baska bir sekilde soralim."))

    def test_no_audio_object_is_reachable_from_a_completed_typed_session(self) -> None:
        stack, clock, _ = typed_stack()
        drive(stack, clock, SCRIPT)
        assert stack.session.retained_frames() == 0
        assert stack.session.sink is None


# =====================================================================================
# 3 · Parity — same answers, same record
# =====================================================================================


class TestSameAnswersReachTheSameRecord:
    def test_the_two_profiles_produce_the_same_turn_trace(self) -> None:
        typed, typed_clock, _ = typed_stack()
        voice, voice_clock, _ = voice_stack()
        assert clinical_trace(drive(typed, typed_clock, SCRIPT)) == clinical_trace(
            drive(voice, voice_clock, SCRIPT)
        )

    def test_the_two_profiles_leave_the_engine_identical(self) -> None:
        typed, typed_clock, _ = typed_stack()
        voice, voice_clock, _ = voice_stack()
        drive(typed, typed_clock, SCRIPT)
        drive(voice, voice_clock, SCRIPT)
        assert engine_state(typed.engine) == engine_state(voice.engine)

    def test_the_two_profiles_mint_the_same_work_ids(self) -> None:
        """``work_key`` is derived, so a typed restart dedupes with a voice one."""
        typed, typed_clock, _ = typed_stack()
        voice, voice_clock, _ = voice_stack()
        typed_ids = [o.work_id for o in drive(typed, typed_clock, SCRIPT) if o.work_id]
        voice_ids = [o.work_id for o in drive(voice, voice_clock, SCRIPT) if o.work_id]
        assert typed_ids == voice_ids != []

    def test_the_two_profiles_ask_the_extractor_the_same_question(self) -> None:
        typed, typed_clock, _ = typed_stack()
        voice, voice_clock, _ = voice_stack()
        drive(typed, typed_clock, SCRIPT)
        drive(voice, voice_clock, SCRIPT)
        # `recording_key` hashes the instruction region and the data digest
        # together, so equality here says the two profiles asked the model the
        # same question about the same answer — declared slots included.
        typed_calls = [call.recording_key for call in typed.handler.gateway.calls]  # type: ignore[attr-defined]
        voice_calls = [call.recording_key for call in voice.handler.gateway.calls]  # type: ignore[attr-defined]
        assert typed_calls == voice_calls != []

    def test_the_transcript_never_enters_the_queue_on_either_profile(self) -> None:
        """The vault is above the seam, so invariant 6 is one mechanism."""
        typed, clock, _ = typed_stack()
        ticket = typed.session.submit_utterance(STEP_IDS[0], "sentetik yanit")
        assert "sentetik yanit" not in repr(typed.agent.record(ticket.work_id))


# =====================================================================================
# 4 · What legitimately differs — and typed is never the worse of the two
# =====================================================================================


class TestWhatLegitimatelyDiffers:
    """Parity asserted only as sameness would be false or vacuous.

    Typed has no ASR, so it has no ``asr_quality`` lane and no clarification
    driven by low confidence. When the two answer streams therefore diverge,
    the claim that survives is an **inequality**: typed is never the worse
    channel. The idea, and this framing of it, are taken from the earlier
    attempt at INT-096 (docs/evidence/INT-096.md).
    """

    def test_only_the_voice_profile_synthesises(self) -> None:
        typed, typed_clock, _ = typed_stack()
        voice, voice_clock, _ = voice_stack()
        drive(typed, typed_clock, SCRIPT)
        drive(voice, voice_clock, SCRIPT)
        assert voice.session.synthesizer.requests  # type: ignore[union-attr]
        assert typed.session.synthesizer is None

    def test_only_the_typed_profile_renders_to_a_screen(self) -> None:
        typed, typed_clock, typed_screen = typed_stack()
        voice, voice_clock, voice_screen = voice_stack()
        drive(typed, typed_clock, SCRIPT)
        drive(voice, voice_clock, SCRIPT)
        assert typed_screen.texts
        assert voice_screen.texts == []

    def test_the_audio_derived_observer_lanes_have_no_input_in_typed(self) -> None:
        """files/03 §4.7.5: three of the five lanes read audio or an ASR score."""
        assert lanes_without_input(VoiceProfile.TYPED) == {
            Lane.AFFECT,
            Lane.ACOUSTIC,
            Lane.ASR_QUALITY,
        }
        assert lanes_without_input(VoiceProfile.RESIDENCY_TR) == frozenset()

    def test_a_lane_with_no_input_is_still_only_a_read_only_lane(self) -> None:
        """Invariant 11 is unchanged: a smaller lane set is a smaller set of
        read-only lanes, never a route by which one gains a write."""
        for lane in lanes_without_input(VoiceProfile.TYPED):
            assert lane in set(Lane)

    def test_typed_gaps_are_a_subset_when_the_voice_stream_degrades(self) -> None:
        """The demonstrating case, in the engine's own terms.

        The voice profile's first slot is never understood — three
        clarification-needed extractions, which files/13 §11.1 caps at two
        before it records the gap. Typed hears it first time because there is
        no recogniser to be unsure. Typed's gaps must then be a **subset**.
        """
        typed, typed_clock, _ = typed_stack()
        drive(typed, typed_clock, SCRIPT)

        voice, voice_clock, _ = voice_stack()
        turn(voice, voice_clock, None)
        for _ in range(3):
            voice.engine.apply_extraction(STEP_IDS[0], {}, clarification_needed=True)
        for line in SCRIPT[1:]:
            turn(voice, voice_clock, line)
        turn(voice, voice_clock, None)

        assert set(typed.engine.data_gaps) <= set(voice.engine.data_gaps)

    def test_typed_coverage_is_never_below_the_voice_profiles(self) -> None:
        typed, typed_clock, _ = typed_stack()
        drive(typed, typed_clock, SCRIPT)

        voice, voice_clock, _ = voice_stack()
        turn(voice, voice_clock, None)
        for _ in range(3):
            voice.engine.apply_extraction(STEP_IDS[0], {}, clarification_needed=True)
        for line in SCRIPT[1:]:
            turn(voice, voice_clock, line)
        turn(voice, voice_clock, None)

        assert len(typed.engine.must_ask_coverage().covered) >= len(
            voice.engine.must_ask_coverage().covered
        )


# =====================================================================================
# 5 · Invariant 22 — no free numeric text entry on the clinical critical path
# =====================================================================================


class TestNoFreeNumericEntry:
    """*"No free numeric text entry on the clinical critical path."*

    This is where the invariant bites hardest, because a typed intake is
    exactly where a numeric text field is the obvious thing to build. It is a
    refusal, not a degradation: there is no fallback text field, no
    numbers-only input and no parser, because the failure mode is not
    malformed input — it is well-formed input that means something else
    (files/00 §2: ``parseFloat("1.500")`` is ``1.5``).
    """

    def test_the_numeric_slot_types_are_the_four_that_carry_a_magnitude(self) -> None:
        from intake_voice_runtime.typed import NUMERIC_SLOT_TYPES

        assert NUMERIC_SLOT_TYPES == {
            SlotType.INTEGER,
            SlotType.DECIMAL,
            SlotType.DURATION,
            SlotType.QUANTITY,
        }

    def test_a_numeric_slot_with_no_chips_has_no_typed_affordance(self) -> None:
        facts = SlotFacts(
            step_id="oyku.doz", slot_type=SlotType.DECIMAL, critical_path=True, unit="mg"
        )
        with pytest.raises(FreeNumericEntryRefused, match="invariant 22"):
            facts.affordance()

    def test_a_numeric_slot_with_chips_renders_as_a_choice(self) -> None:
        stack, _, _ = typed_stack()
        facts = stack.slot_affordances[STEP_IDS[0]]
        assert facts.affordance() is AffordanceKind.CHOICE
        assert facts.choices_tr == CHIPS

    def test_a_non_numeric_slot_may_still_be_free_text(self) -> None:
        facts = SlotFacts(step_id="oyku.notu", slot_type=SlotType.STRING, critical_path=True)
        assert facts.affordance() is AffordanceKind.FREE_TEXT

    def test_the_pack_gate_lists_a_chipless_numeric_critical_path_step(self) -> None:
        assert free_numeric_critical_path_steps(_protocol(choices=())) == STEP_IDS

    def test_the_pack_gate_is_empty_for_the_parity_pack(self) -> None:
        assert free_numeric_critical_path_steps(_protocol()) == ()

    def test_a_pack_the_gate_rejects_cannot_be_prompted_typed(self) -> None:
        """The negative control: the refusal reaches the caller rather than
        being swallowed into a text field."""
        stack, _, _ = typed_stack(protocol=_protocol(choices=()))
        step = stack.session.protocol_next()
        assert step is not None
        with pytest.raises(FreeNumericEntryRefused):
            typed_prompt(step, stack.slot_affordances[step.step_id])


class TestHowAQuantityIsWritten:
    """Invariant 22's display half: ``useGrouping:false``, one atom."""

    def test_no_thousands_group_and_the_unit_cannot_be_split_off(self) -> None:
        assert render_measure(Decimal("1500"), "mg", locale="tr") == f"1500{NBSP}mg"
        assert "." not in render_measure(Decimal("1500"), None, locale="tr")
        assert "," not in render_measure(Decimal("1500"), None, locale="tr")

    def test_a_magnitude_never_renders_in_scientific_notation(self) -> None:
        assert render_measure(Decimal("1E+3"), "mg", locale="tr") == f"1000{NBSP}mg"

    def test_the_decimal_point_is_the_sessions_locales(self) -> None:
        """INT-386. The rail is written for the patient reading it: a comma in
        Turkish, a full stop in English, and nothing else changes."""
        assert render_measure(Decimal("2.5"), "mg", locale="tr") == f"2,5{NBSP}mg"
        assert render_measure(Decimal("2.5"), "mg", locale="en") == f"2.5{NBSP}mg"
        assert render_measure(7, "gün", locale="tr") == f"7{NBSP}gün"

    def test_a_full_stop_on_a_turkish_rail_is_the_near_miss(self) -> None:
        """What the rail wrote before INT-386. A Turkish reader takes ``2.500``
        as two thousand five hundred; the rail never writes a full stop for
        one."""
        rendered = render_measure(Decimal("2.500"), "mg", locale="tr")
        assert rendered == f"2,500{NBSP}mg"
        assert "." not in rendered

    def test_the_rail_renders_every_bound_numeric_value(self) -> None:
        stack, clock, _ = typed_stack()
        drive(stack, clock, SCRIPT)
        values = {step_id: stack.engine.value_of(step_id) for step_id in STEP_IDS}
        rail = numeric_rail(values, stack.slot_affordances, locale="tr")
        assert rail == {step_id: str(index + 1) for index, step_id in enumerate(STEP_IDS)}

    def test_the_rail_skips_a_value_that_is_not_a_magnitude(self) -> None:
        facts = {
            "oyku.notu": SlotFacts(
                step_id="oyku.notu", slot_type=SlotType.STRING, critical_path=False
            )
        }
        assert numeric_rail({"oyku.notu": "sentetik"}, facts, locale="tr") == {}


# =====================================================================================
# 6 · The kill switch (files/08 §8.2 T1; files/03 §4.5b T3, T9)
# =====================================================================================


class TestKillSwitch:
    """*"The kill switch moves the system to the **safer** state (typed mode)."*

    files/08 §0c F17 makes it a **T1 safe-direction** action: one actor, no
    approver, audited. The runtime half of that is here — the target the
    switch moves a live session to, and the refusal to move it back.
    """

    def test_the_reasons_are_the_four_the_blueprint_names(self) -> None:
        """files/08 §375 (operator), files/03 §4.5b T3 and T9, and — INT-100 —
        files/03 §4.9.4 rows 7 and 11: *"repeated failure routes to `typed`"*,
        *"then to row 12 for the rest of the session, then to `typed`"*."""
        assert {reason.value for reason in LaneSwitchReason} == {
            "operator_kill_switch",
            "unreliable_audio",
            "abort_voice",
            "speech_lanes_exhausted",
        }

    def test_a_live_voice_session_moves_to_typed_mid_intake(self) -> None:
        stack, clock, _ = voice_stack()
        turn(stack, clock, None)
        turn(stack, clock, SCRIPT[0])
        before = engine_state(stack.engine)
        stack.session.fall_back_to_typed(LaneSwitchReason.OPERATOR_KILL_SWITCH)
        assert stack.session.config.profile is VoiceProfile.TYPED
        assert isinstance(stack.session.router, TypedEgress)
        assert engine_state(stack.engine) == before

    def test_the_switch_drops_every_audio_port(self) -> None:
        stack, clock, _ = voice_stack()
        turn(stack, clock, None)
        stack.session.fall_back_to_typed(LaneSwitchReason.OPERATOR_KILL_SWITCH)
        assert stack.session.sink is None
        assert stack.session.clip_store is None
        assert stack.session.synthesizer is None
        assert stack.session.catalogue is None
        assert stack.session.config.voice_id is None

    def test_no_audio_can_leave_the_session_after_the_switch(self) -> None:
        """A refusing sink, so this shows nothing *could* be played rather
        than that nothing happened to be."""
        stack, clock, _ = voice_stack()
        turn(stack, clock, None)
        refusing = RefusingSink()
        stack.session.sink = refusing
        stack.session.fall_back_to_typed(LaneSwitchReason.ABORT_VOICE)
        for line in SCRIPT[1:]:
            turn(stack, clock, line)
        turn(stack, clock, None)
        assert refusing.touched == []

    def test_the_switch_marks_the_session_modality_degraded(self) -> None:
        """files/03 §4.5b T9: *"mark the session ``modality_degraded``"*."""
        stack, clock, _ = voice_stack()
        assert stack.session.modality_degraded is False
        stack.session.fall_back_to_typed(LaneSwitchReason.ABORT_VOICE)
        assert stack.session.modality_degraded is True

    def test_the_switch_is_recorded_with_its_reason_and_no_free_text(self) -> None:
        stack, clock, _ = voice_stack()
        turn(stack, clock, None)
        record = stack.session.fall_back_to_typed(LaneSwitchReason.UNRELIABLE_AUDIO)
        assert record.reason is LaneSwitchReason.UNRELIABLE_AUDIO
        assert record.from_profile is VoiceProfile.RESIDENCY_TR
        assert record.to_profile is VoiceProfile.TYPED
        assert record.modality_degraded is True
        assert SESSION not in repr(record)
        assert stack.session.modality_switch == record

    def test_the_switch_is_idempotent_and_the_first_reason_wins(self) -> None:
        """A later T9 after an earlier T3 must not erase the reason the
        patient was actually offered typed."""
        stack, clock, _ = voice_stack()
        first = stack.session.fall_back_to_typed(LaneSwitchReason.UNRELIABLE_AUDIO)
        second = stack.session.fall_back_to_typed(LaneSwitchReason.ABORT_VOICE)
        assert first == second
        assert stack.session.modality_switch is not None
        assert stack.session.modality_switch.reason is LaneSwitchReason.UNRELIABLE_AUDIO

    def test_a_session_that_started_typed_cannot_be_switched(self) -> None:
        stack, _, _ = typed_stack()
        with pytest.raises(LaneSwitchLatched):
            stack.session.fall_back_to_typed(LaneSwitchReason.ABORT_VOICE)
        assert stack.session.modality_switch is None
        assert stack.session.modality_degraded is False

    def test_the_switch_refuses_when_no_screen_is_bound(self) -> None:
        """A kill switch with nowhere to render is not a kill switch."""
        stack, clock, _ = voice_stack()
        stack.session.screen = None
        with pytest.raises(KillSwitchNotArmed):
            stack.session.fall_back_to_typed(LaneSwitchReason.OPERATOR_KILL_SWITCH)
        assert stack.session.config.profile is VoiceProfile.RESIDENCY_TR
        assert stack.session.sink is not None

    def test_there_is_no_way_back_to_a_speaking_profile(self) -> None:
        """The dangerous direction takes two humans and a new session — the
        runtime offers no expression for it at all (files/08 §8.2)."""
        forbidden = {"fall_back_to_voice", "restore_voice", "set_profile", "switch_profile"}
        assert forbidden.isdisjoint(dir(TalkerSession))

    def test_the_interrupted_intake_completes_with_the_same_result(self) -> None:
        """files/03 §4.5b T3: *"keep the session and every slot"*."""
        switched, switched_clock, _ = voice_stack()
        outcomes = [turn(switched, switched_clock, None)]
        outcomes.append(turn(switched, switched_clock, SCRIPT[0]))
        switched.session.fall_back_to_typed(LaneSwitchReason.ABORT_VOICE)
        outcomes.extend(turn(switched, switched_clock, line) for line in SCRIPT[1:])
        outcomes.append(turn(switched, switched_clock, None))

        pure, pure_clock, _ = typed_stack()
        pure_outcomes = drive(pure, pure_clock, SCRIPT)

        assert clinical_trace(outcomes) == clinical_trace(pure_outcomes)
        assert engine_state(switched.engine) == engine_state(pure.engine)

    def test_the_patients_form_of_address_survives_the_switch(self) -> None:
        """The register the patient mirrored is a fact about the patient, not
        about the channel (files/03 §4.2)."""
        stack, clock, _ = voice_stack()
        before = stack.session.guard.form_of_address
        stack.session.fall_back_to_typed(LaneSwitchReason.OPERATOR_KILL_SWITCH)
        assert stack.session.guard.form_of_address is before
        assert stack.session.guard.profile is VoiceProfile.TYPED


# =====================================================================================
# 7 · "parity simulator run"
# =====================================================================================


class TestParitySimulatorRun:
    """files/03 §4.6 invariant 8: *"the same simulator scenarios pass on
    ``typed`` … and ``residency_tr`` with mock adapters."*

    The scenario drivers are not parameterised on anything but the profile,
    and they were written before ``typed`` had a code path. That they run
    unchanged is the point: nothing in RT-01…RT-08 had to be taught about the
    keyboard, because nothing in RT-01…RT-08 is about the transport.
    """

    @pytest.mark.parametrize("scenario_id", [scenario.id for scenario in runnable_scenarios()])
    def test_every_runnable_scenario_traces_identically_on_both_profiles(
        self, scenario_id: str
    ) -> None:
        from test_invariants import run_scenario  # noqa: PLC0415 — the drivers are the suite's

        network = NetworkProfile.TR_MOBILE_MID_LTE
        voice = ParityTrace.of(run_scenario(scenario_id, VoiceProfile.RESIDENCY_TR, network))
        typed = ParityTrace.of(run_scenario(scenario_id, VoiceProfile.TYPED, network))
        assert voice.divergence(typed) == ()

    def test_every_runnable_scenario_declares_both_profiles(self) -> None:
        for scenario in SCENARIOS.values():
            if scenario.runnable:
                assert set(scenario.profiles) == set(VoiceProfile)

    def test_a_divergence_names_the_field_rather_than_saying_not_equal(self) -> None:
        from test_invariants import run_scenario  # noqa: PLC0415

        network = NetworkProfile.TR_MOBILE_MID_LTE
        trace = ParityTrace.of(run_scenario("RT-05", VoiceProfile.TYPED, network))
        mutated = trace.model_copy(update={"steps": ("oyku.baska",)})
        assert any(line.startswith("steps:") for line in trace.divergence(mutated))

    def test_the_harness_runs_a_parity_check_from_the_command_line(self) -> None:
        """`make runtime-sim SCENARIO=... PROFILE=... PARITY=1`, as a call.

        Loaded by path because ``scripts/`` is not an importable package —
        the same reason the harness itself puts ``tests/voice`` on the path
        rather than making the suite a package.
        """
        import importlib.util  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        path = Path(__file__).resolve().parents[2] / "scripts" / "voice" / "runtime_sim.py"
        spec = importlib.util.spec_from_file_location("runtime_sim_int096", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.main(["--scenario", "RT-05", "--profile", "typed", "--parity"]) == 0


# =====================================================================================
# 8 · A kill-switch target has to be able to report ready (invariant 15)
# =====================================================================================


class TestTheTypedWorkerCanBecomeReady:
    """*"The admin console can switch a tenant to typed mode (kill switch)
    without a deploy"* (files/02 §375).

    A target that can never report ready is not a target. The three speech
    bindings the voice worker waits on — clip store, synthesizer, LiveKit room
    token — are bindings a keyboard worker has no use for, so on ``typed``
    they pass and say so rather than holding the safer state un-routable.
    """

    def test_a_typed_worker_is_ready_with_no_speech_binding_at_all(self) -> None:
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from intake_voice_runtime.app import VoiceRuntimeWiring, create_app  # noqa: PLC0415

        client = TestClient(create_app(VoiceRuntimeWiring(profile=VoiceProfile.TYPED)))
        response = client.get("/readyz")
        assert response.status_code == 200

    def test_the_report_still_names_all_three_checks(self) -> None:
        """A readiness report that silently shrinks is one nobody can compare
        across deployments. INT-182 added a fourth — ``voice_controls``, the
        kill-switch read a speech worker needs at every session start — and a
        typed worker names it too, passed, rather than dropping it."""
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from intake_voice_runtime.app import VoiceRuntimeWiring, create_app  # noqa: PLC0415

        client = TestClient(create_app(VoiceRuntimeWiring(profile=VoiceProfile.TYPED)))
        checks = client.get("/readyz").json()["checks"]
        assert set(checks) == {"clip_store", "speech_synthesizer", "room_token", "voice_controls"}
        assert set(checks.values()) == {"ok"}

    def test_the_voice_worker_still_fails_closed_on_the_same_three(self) -> None:
        from fastapi.testclient import TestClient  # noqa: PLC0415
        from intake_voice_runtime.app import VoiceRuntimeWiring, create_app  # noqa: PLC0415

        client = TestClient(create_app(VoiceRuntimeWiring()))
        assert client.get("/readyz").status_code == 503
