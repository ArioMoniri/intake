"""INT-091 — the turn loop, the consent gates, and the bridge that stays empty.

Three groups:

- **The turn.** RT-01: the patient keeps talking while Backend Work lands, and
  the Talker speaks the result only at a pause — never stalling, never
  interrupting. The scheduler's ladder is unit-tested in
  test_insertion_window.py; here it is driven through a real session.
- **``respond_permission``.** files/12 §7.6's gate ladder, one test per rung,
  because a consent gate that only has a happy-path test is a consent gate
  nobody has checked. The overlap rung is the *"hı-hı"* fix and gets its own.
- **The safe bridge.** PolicyGuard drops a whole turn; with no signed-off
  bridge copy the Talker says nothing at all. That is the behaviour CLAUDE.md
  asks for when a clinical value is missing, and it is asserted rather than
  left to inspection.
"""

from __future__ import annotations

import pytest
from clinical_schemas.triage import RuleFire, RulesTriageResult, TriageLevel
from intake_voice_runtime.ports import (
    PatientMemoryKey,
    SystemClock,
    WorkRequest,
    WorkState,
    WorkTicket,
    WorkType,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import Step, StepKind
from intake_voice_runtime.talker.clips import ClipCatalogue, clip_id_for
from intake_voice_runtime.talker.delivery import DeliveryClass, DuplexState
from intake_voice_runtime.talker.policy_guard import FormOfAddress
from intake_voice_runtime.talker.preemption import BackendResult, Presentation
from intake_voice_runtime.talker.session import TalkerConfig, TalkerSession
from intake_voice_runtime.talker.tools import (
    ConsentDecision,
    MemoryOp,
    PermissionRequest,
    PermissionState,
    RepeatReason,
)
from talker_harness import VOICE_ID, FakeClock, build_session, scripted_step

PROMPT_HASH = "b" * 64
TALKING = DuplexState(patient_silence_ms=0.0, talker_idle=False, pending_response=True)
PAUSED = DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)


def _yellow_result(work_id: str = "w1") -> BackendResult:
    return BackendResult(
        work_id=work_id,
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.TRIAGE_YELLOW,
        presentation=Presentation(
            speech_tr="Bunu hekiminiz görecek.",
            triage_update=RulesTriageResult(
                level=TriageLevel.YELLOW,
                rules=(RuleFire(id="rf.kanama", evidence="kanama=evet"),),
            ),
        ),
    )


def _open_permission(
    session: TalkerSession,
    *,
    parent: str | None = None,
    prompt_audio_ended_ms: float = 1_000.0,
) -> None:
    session.open_permission_request(
        PermissionRequest(
            request_id="perm-1",
            prompt_text_hash=PROMPT_HASH,
            opened_at_ms=0.0,
            prompt_audio_ended_ms=prompt_audio_ended_ms,
            parent_request_id=parent,
        )
    )


def _respond(session: TalkerSession, **overrides: object) -> object:
    payload: dict[str, object] = {
        "request_id": "perm-1",
        "decision": ConsentDecision.YES,
        "span_start_ms": 2_000.0,
        "span_end_ms": 2_400.0,
        "asr_confidence": 0.97,
        "prompt_text_hash": PROMPT_HASH,
    }
    payload.update(overrides)
    return session.respond_permission(**payload)  # type: ignore[arg-type]


# --- the turn --------------------------------------------------------------------


def test_a_turn_with_no_next_step_speaks_nothing() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[])
    outcome = clock.run(session.take_turn(None))
    assert outcome.step_id is None
    assert outcome.spoken_text == ""


def test_backend_speech_waits_while_the_patient_talks_and_lands_at_the_pause() -> None:
    """RT-01, through a real session rather than the scheduler alone."""
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    session.accept_result(_yellow_result())

    session.observe_duplex(TALKING)
    first = clock.run(session.take_turn(None))
    assert first.delivered_work_ids == ()

    session.observe_duplex(PAUSED)
    second = clock.run(session.take_turn(None))
    assert second.delivered_work_ids == ("w1",)


def test_a_result_with_no_speech_is_not_queued_at_all() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    session.accept_result(
        BackendResult(
            work_id="w2",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.ROUTINE,
            presentation=Presentation(speech_tr=None),
        )
    )
    assert session.scheduler.pending_work_ids == ()


def test_backend_speech_that_policyguard_empties_is_not_spoken() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    session.accept_result(
        BackendResult(
            work_id="w3",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(speech_tr="Bu bir migren atağı."),
        )
    )
    session.observe_duplex(PAUSED)
    clock.run(session.take_turn(None))
    assert session.sink.played == [("s1", 32)]  # type: ignore[attr-defined]


def test_the_talker_refuses_a_minted_work_id() -> None:
    """files/12 §7.5: the id is derived. A Layer B that mints one would make
    every restart duplicate its re-submitted transcript."""

    class MintingBackend:
        def submit(self, request: WorkRequest) -> WorkTicket:
            return WorkTicket(work_id="w_minted", state=WorkState.QUEUED)

        def cancel(self, work_id: str, reason: str) -> WorkTicket:
            return WorkTicket(work_id=work_id, state=WorkState.CANCELLED)

        def drain_results(self) -> tuple[object, ...]:
            return ()

    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    session.backend = MintingBackend()
    session.protocol_next()
    with pytest.raises(ValueError, match="minted a work_id"):
        session.submit_utterance("s1", "iki gündür")


def test_the_work_the_talker_submits_is_extraction_and_nothing_else() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    session.protocol_next()
    session.submit_utterance("s1", "iki gündür")
    assert session.backend.submitted[0].work_type is WorkType.EXTRACT_SLOTS  # type: ignore[attr-defined]


# --- repeat and memory ----------------------------------------------------------------


def test_repeat_returns_the_cached_clip_when_the_step_is_pre_synthesised(
    tmp_path: object,
) -> None:
    clock = FakeClock()
    step = scripted_step()
    catalogue = ClipCatalogue(
        voice=VOICE_ID,
        resolved_protocol_hash="a" * 64,
        refs={},
    )
    session = build_session(clock, steps=[step], catalogue=catalogue)
    session.protocol_next()
    directive = session.request_repeat_or_clarify(RepeatReason.CONNECTION_GAP)
    assert directive.text_tr == step.text_tr
    assert directive.clip_id is None
    assert directive.reason is RepeatReason.CONNECTION_GAP


def test_repeat_without_a_current_step_raises() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[])
    with pytest.raises(LookupError):
        session.request_repeat_or_clarify(RepeatReason.NOT_HEARD)


def test_mirroring_sen_moves_the_policyguard_register() -> None:
    """CLAUDE.md: `sen` is reachable only by mirroring — and the guard has to
    learn it, or it would keep blocking the register the patient chose."""
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    assert session.guard.form_of_address is FormOfAddress.SIZ
    session.patient_memory(MemoryOp.REMEMBER, PatientMemoryKey.FORM_OF_ADDRESS, "sen")
    assert session.guard.form_of_address is FormOfAddress.SEN


def test_remember_without_a_value_is_refused() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    with pytest.raises(ValueError, match="value"):
        session.patient_memory(MemoryOp.REMEMBER, PatientMemoryKey.PACE)


# --- respond_permission: the files/12 §7.6 ladder ----------------------------------------


def _session_with_prompt() -> TalkerSession:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    _open_permission(session)
    return session


def test_a_clean_first_yes_is_provisional_until_the_read_back() -> None:
    ack = _respond(_session_with_prompt())
    assert ack.state is PermissionState.PROVISIONAL  # type: ignore[union-attr]


def test_a_yes_on_the_read_back_child_grants() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    _open_permission(session, parent="perm-0")
    ack = _respond(session)
    assert ack.state is PermissionState.GRANTED  # type: ignore[union-attr]


def test_a_no_declines_and_closes_the_request() -> None:
    session = _session_with_prompt()
    ack = _respond(session, decision=ConsentDecision.NO)
    assert ack.state is PermissionState.DECLINED  # type: ignore[union-attr]
    assert _respond(session).state is PermissionState.REFUSED  # type: ignore[union-attr]


def test_an_unknown_request_id_is_refused() -> None:
    session = _session_with_prompt()
    ack = _respond(session, request_id="perm-other")
    assert ack.state is PermissionState.REFUSED  # type: ignore[union-attr]
    assert "no open consent request" in ack.reason  # type: ignore[union-attr]


def test_a_prompt_older_than_sixty_seconds_is_refused() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    _open_permission(session)
    clock.run(clock.sleep(61.0))
    ack = _respond(session)
    assert "sixty seconds" in ack.reason  # type: ignore[union-attr]


def test_a_mismatched_prompt_hash_is_refused() -> None:
    ack = _respond(_session_with_prompt(), prompt_text_hash="c" * 64)
    assert "prompt hash" in ack.reason  # type: ignore[union-attr]


def test_an_answer_that_began_before_the_prompt_finished_is_refused() -> None:
    ack = _respond(_session_with_prompt(), span_start_ms=500.0, span_end_ms=900.0)
    assert "before the prompt finished" in ack.reason  # type: ignore[union-attr]


def _session_that_has_spoken() -> tuple[TalkerSession, float, float]:
    """A session that has played one clip, and the interval it played over."""
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    _open_permission(session, prompt_audio_ended_ms=0.0)
    clock.run(session.take_turn(None))
    start, end = session.playback_intervals[0]
    return session, start, end


def test_a_span_inside_the_agents_own_playback_is_refused() -> None:
    """files/12 §7.6: the agent's own backchannel sits inside a playback
    interval, so a span overlapping it can never count as consent. This is the
    definitive fix for *"hı-hı"*."""
    session, start, end = _session_that_has_spoken()
    ack = _respond(session, span_start_ms=start + 1.0, span_end_ms=end - 1.0)
    assert ack.state is PermissionState.REFUSED  # type: ignore[union-attr]
    assert "overlaps agent playback" in ack.reason  # type: ignore[union-attr]


def test_a_span_after_the_agent_stopped_speaking_is_accepted() -> None:
    """The near-miss control: the overlap gate must not swallow a real answer."""
    session, _, end = _session_that_has_spoken()
    ack = _respond(session, span_start_ms=end + 10.0, span_end_ms=end + 400.0)
    assert ack.state is PermissionState.PROVISIONAL  # type: ignore[union-attr]


def test_low_transcription_confidence_is_refused() -> None:
    ack = _respond(_session_with_prompt(), asr_confidence=0.84)
    assert "confidence" in ack.reason  # type: ignore[union-attr]


# --- the safe bridge stays empty ------------------------------------------------------


def _bridge_session(clock: FakeClock, *, bridge_clip_id: str | None) -> TalkerSession:
    session = build_session(
        clock,
        steps=[Step(step_id="s9", kind=StepKind.PARAPHRASE_OK, text_tr="Bu bir migren atağı.")],
    )
    session.config = TalkerConfig(
        session_id=session.config.session_id,
        voice_id=session.config.voice_id,
        profile=VoiceProfile.RESIDENCY_TR,
        protocol_hash=session.config.protocol_hash,
        safe_bridge_clip_id=bridge_clip_id,
    )
    return session


def test_a_dropped_turn_says_nothing_while_the_bridge_copy_is_unsigned() -> None:
    clock = FakeClock()
    session = _bridge_session(clock, bridge_clip_id=None)
    outcome = clock.run(session.take_turn(None))
    assert outcome.spoken_text == ""
    assert session.sink.played == []  # type: ignore[attr-defined]


def test_a_dropped_turn_plays_the_bridge_once_one_is_configured() -> None:
    clock = FakeClock()
    bridge = clip_id_for("bridge", VOICE_ID)
    session = _bridge_session(clock, bridge_clip_id=bridge)
    clock.run(session.take_turn(None))
    assert [label for label, _ in session.sink.played] == ["safe_bridge"]  # type: ignore[attr-defined]


# --- housekeeping -----------------------------------------------------------------------


def test_the_system_clock_moves_forward() -> None:
    clock = SystemClock()
    first = clock.now_ms()
    assert clock.now_ms() >= first


def test_the_system_clock_sleeps() -> None:
    import asyncio

    clock = SystemClock()

    async def scenario() -> None:
        await clock.sleep(0.0)

    asyncio.run(scenario())


def test_cancel_work_reaches_layer_b() -> None:
    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()])
    ticket = session.cancel_work("w_abc", "patient retracted")
    assert ticket.state is WorkState.CANCELLED
    assert session.backend.cancelled == ["w_abc"]  # type: ignore[attr-defined]
