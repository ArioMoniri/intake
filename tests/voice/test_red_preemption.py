"""INT-093 — the RED preemption path, timed on a fake clock.

Acceptance, verbatim: *"only rules-engine RED carries priority preempt;
playback cancel and script start measured on fake clock"*.

INT-091 built the authorisation half and ``tests/voice/test_red_preempt_only.py``
pins it: the shape gate on :class:`BackendResult` (only a ``RulesTriageResult``
whose level is ``RED``) and the provenance gate in :func:`authorise_preempt`
(the rule ids must come from the session's pinned pack). INT-092 calls that
gate before any engine write. **None of that is re-proved here.** What this
file adds is the path those gates guard, and the two numbers on it:

- **playback stop ≤ 150 ms** and **end-to-end script start ≤ 300 ms**
  (files/03 §4.6 invariant 4), both read off :class:`FakeClock`. A wall clock
  in a latency assertion is a flake; virtual time makes the number a property
  of the code under test rather than of the machine running it.
- **the measurement is real.** Every budget assertion goes through
  :func:`_assert_within_budget`, and two mutation controls inject a delay past
  the budget and assert that the *same* helper raises. A timing test that
  would still pass with the timing deleted proves nothing.
- **the register × location matrix.** "Preempt" is not one behaviour
  (files/02 §5.3): ``SILENT`` and ``DEFERRED_CLINICIAN`` must produce no
  audible interrupt at all, and under ``ON_SITE`` the 112 affordance is
  absent — not de-emphasised.
- **no media transport.** files/03 §4.6 invariant 4, in its own words: the RED
  script is pre-positioned on the device and triggered over the data channel,
  and *"the test changes too: it must assert the RED path touches no media
  transport"*. That is asserted structurally — an import closure and an AST
  walk over the module — as well as behaviourally.

Every Turkish string below is synthetic test copy (files/04 §7); no clinical
value, threshold or patient-facing script is authored here.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.triage import (
    CandidateFlag,
    LlmCandidateTriage,
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.delivery import DeliveryClass, DuplexState
from intake_voice_runtime.talker.preemption import (
    BackendResult,
    PreemptRefused,
    Presentation,
    Priority,
)
from intake_voice_runtime.talker.red_path import (
    E2E_BUDGET_MS,
    STOP_BUDGET_MS,
    RedPathNotWired,
    RedPreemption,
    RedPreemptOutcome,
    RedPreemptRefused,
    RedTrigger,
    red_delivery,
)
from intake_voice_runtime.talker.red_script import (
    RedScriptKind,
    RedScriptMismatch,
    RedScriptRef,
    RedScriptUnavailable,
    script_ref_for_action,
)
from protocols.dsl import REGISTER_AUDIO, LocationAction, UnknownAction
from pydantic import ValidationError
from talker_harness import (
    FakeClock,
    RecordedClipStore,
    RecordingSink,
    RecordingSynthesizer,
    build_session,
    scripted_step,
)

# --- the pinned pack, and the scripts pre-positioned for it ---------------------------

RULE_ID = "rf.gogus_agrisi_akut"
PACK_RULES = frozenset({RULE_ID, "rf.kanama"})

#: Synthetic Turkish (files/04 §7). Numerals are already expanded, which is
#: what a compiled pack guarantees (CLAUDE.md invariant 22).
REMOTE_ACTION = LocationAction(
    primary="CALL_112",
    secondary="NEAREST_ACIL_ADDRESS_AS_TEXT",
    show_112=True,
    action_tr="Yüz on ikiyi arayın.",
    do_nots_tr=("Tek başınıza gitmeyin.",),
    why_tr="Bu belirtilerin hemen değerlendirilmesi gerekir.",
)
ON_SITE_ACTION = LocationAction(
    primary="GO_TO_IN_HOUSE_ACIL",
    show_112=False,
    action_tr="Acil Servis'e gidin. Randevunuzu beklemeyin.",
    do_nots_tr=("Poliklinik sırasında beklemeyin.",),
    notify_staff_immediate=True,
)
UNKNOWN_ACTION = UnknownAction(
    ask_one_tr="Şu anda hastanede misiniz?",
    on_yes="ON_SITE",
    on_no="REMOTE",
    on_no_answer="REMOTE",
)
ACTIONS: dict[RedLocation, LocationAction | UnknownAction] = {
    RedLocation.REMOTE: REMOTE_ACTION,
    RedLocation.ON_SITE: ON_SITE_ACTION,
    RedLocation.UNKNOWN: UNKNOWN_ACTION,
}


def script_for(register: RedRegister, location: RedLocation) -> RedScriptRef:
    return script_ref_for_action(
        rule_id=RULE_ID, register=register, location=location, action=ACTIONS[location]
    )


def red_result(
    register: RedRegister = RedRegister.ALERT,
    location: RedLocation = RedLocation.REMOTE,
    *,
    rule_id: str = RULE_ID,
    script: RedScriptRef | None | object = ...,
    work_id: str = "w_red",
) -> BackendResult:
    """One rules-engine RED, carrying the ref of its pre-positioned script."""
    resolved = script_for(register, location) if script is ... else script
    return BackendResult(
        work_id=work_id,
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(
            triage_update=RulesTriageResult(
                level=TriageLevel.RED,
                rules=(RuleFire(id=rule_id, evidence="gogus_agrisi=evet"),),
                register=register,
                location=location,
            ),
            red_script=resolved,  # type: ignore[arg-type]
        ),
        priority=Priority.PREEMPT,
    )


# --- doubles: the two egress ports the RED path may touch -------------------------------


@dataclass
class RecordingPlaybackStop:
    """Stop in-flight agent playback. This double cannot play — it has no
    ``play`` member at all, which is the point (files/03 §4.6 invariant 4)."""

    clock: FakeClock
    delay_ms: float = 0.0
    cancels: int = 0

    async def cancel(self) -> None:
        self.cancels += 1
        await self.clock.sleep(self.delay_ms / 1000.0)


@dataclass
class RecordingDataChannel:
    """The reliable, ordered data channel (SCTP-over-DTLS). Not media."""

    clock: FakeClock
    delay_ms: float = 0.0
    sent: list[RedTrigger] = field(default_factory=list)

    async def trigger(self, message: RedTrigger) -> None:
        await self.clock.sleep(self.delay_ms / 1000.0)
        self.sent.append(message)


@dataclass
class ReadyBackend:
    """A Layer B whose results are already finished. ``submit`` returns a
    ticket synchronously; nothing here is awaitable (invariant 9)."""

    results: list[BackendResult] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    def submit(self, request: object) -> Any:
        from intake_voice_runtime.ports import WorkTicket

        return WorkTicket(work_id="w_submitted", state=WorkState.QUEUED)

    def cancel(self, work_id: str, reason: str) -> Any:
        from intake_voice_runtime.ports import WorkTicket

        self.cancelled.append(work_id)
        return WorkTicket(work_id=work_id, state=WorkState.CANCELLED)

    def drain_results(self) -> tuple[BackendResult, ...]:
        drained = tuple(self.results)
        self.results.clear()
        return drained


def build_red_path(
    clock: FakeClock,
    *,
    stop: RecordingPlaybackStop | None = None,
    channel: RecordingDataChannel | None = None,
    rule_ids: frozenset[str] = PACK_RULES,
    profile: VoiceProfile = VoiceProfile.RESIDENCY_TR,
) -> tuple[RedPreemption, RecordingPlaybackStop, RecordingDataChannel]:
    playback = stop or RecordingPlaybackStop(clock=clock)
    data_channel = channel or RecordingDataChannel(clock=clock)
    path = RedPreemption(
        clock=clock,
        playback=playback,
        channel=data_channel,
        rule_ids=rule_ids,
        profile=profile,
    )
    return path, playback, data_channel


def fire(clock: FakeClock, path: RedPreemption, result: BackendResult) -> RedPreemptOutcome:
    return clock.run(path.trigger(result))  # type: ignore[no-any-return]


# --- the budget assertion, and the control that proves it bites -------------------------


def _assert_within_budget(outcome: RedPreemptOutcome) -> None:
    """The single place either budget is asserted.

    Both mutation controls below drive an over-budget outcome through *this*
    function and assert it raises, which is what makes every green budget
    assertion above evidence rather than decoration.
    """
    if outcome.stop_ms is not None:
        assert outcome.stop_ms <= STOP_BUDGET_MS, (
            f"playback stop took {outcome.stop_ms} ms, over the {STOP_BUDGET_MS} ms "
            "budget of files/03 §4.6 invariant 4"
        )
        assert outcome.within_stop_budget
    if outcome.script_start_ms is not None:
        assert outcome.script_start_ms <= E2E_BUDGET_MS, (
            f"script start took {outcome.script_start_ms} ms, over the {E2E_BUDGET_MS} ms "
            "end-to-end budget of files/03 §4.6 invariant 4"
        )
        assert outcome.within_e2e_budget


# ==========================================================================================
# A. The gate, re-run against the timed path (near-miss negative controls)
# ==========================================================================================


def test_the_budgets_are_the_blueprints_numbers() -> None:
    """files/03 §4.6 invariant 4: *"end-to-end RED preemption ≤ 300 ms;
    playback cancel ≤ 150 ms"*."""
    assert STOP_BUDGET_MS == 150.0
    assert E2E_BUDGET_MS == 300.0


def test_a_non_red_claiming_preempt_never_reaches_the_timed_path() -> None:
    """INT-091's shape gate, restated where it matters: the result cannot even
    be constructed, so there is no object to hand the timed path."""
    with pytest.raises(ValidationError, match="RED"):
        BackendResult(
            work_id="w_yellow",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.TRIAGE_YELLOW,
            presentation=Presentation(
                triage_update=RulesTriageResult(
                    level=TriageLevel.YELLOW,
                    rules=(RuleFire(id="rf.kanama", evidence="kanama=evet"),),
                )
            ),
            priority=Priority.PREEMPT,
        )


def test_an_llm_originated_result_claiming_preempt_never_reaches_the_timed_path() -> None:
    """CLAUDE.md invariant 1: the candidate type cannot spell RED."""
    with pytest.raises(ValidationError, match="RED"):
        BackendResult(
            work_id="w_llm",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.RED,
            presentation=Presentation(
                triage_update=LlmCandidateTriage(
                    candidate_flags=(CandidateFlag(text="olası kanama", evidence="ifade"),)
                )
            ),
            priority=Priority.PREEMPT,
        )


def test_a_red_naming_a_rule_outside_the_pinned_pack_stops_nothing_and_sends_nothing() -> None:
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    forged = red_result(rule_id="rf.uydurma_kural")
    with pytest.raises(PreemptRefused, match="rf.uydurma_kural"):
        fire(clock, path, forged)
    assert stop.cancels == 0, "a refused RED must not cut the patient off"
    assert channel.sent == []


def test_an_unpinned_session_triggers_nothing() -> None:
    clock = FakeClock()
    path, stop, channel = build_red_path(clock, rule_ids=frozenset())
    with pytest.raises(PreemptRefused, match="no rule ids"):
        fire(clock, path, red_result())
    assert stop.cancels == 0
    assert channel.sent == []


def test_a_normal_priority_result_is_refused_by_the_timed_path() -> None:
    """The RED path is not a general delivery channel: only ``preempt``."""
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    routine = BackendResult(
        work_id="w_routine",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.ROUTINE,
        presentation=Presentation(speech_tr="Belgeniz okundu."),
    )
    with pytest.raises(RedPreemptRefused):
        fire(clock, path, routine)
    assert stop.cancels == 0
    assert channel.sent == []


def test_the_timed_path_refuses_a_non_red_that_bypassed_the_shape_gate() -> None:
    """Defence in depth, proved rather than asserted.

    ``model_construct`` skips the ``BackendResult`` validator, which is the
    only way to reach this branch — and the point of the branch is that a
    future producer bypassing that validator still cannot interrupt a patient.
    """
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    smuggled = BackendResult.model_construct(
        work_id="w_smuggled",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(
            triage_update=RulesTriageResult(
                level=TriageLevel.YELLOW,
                rules=(RuleFire(id=RULE_ID, evidence="gogus_agrisi=evet"),),
            )
        ),
        priority=Priority.PREEMPT,
    )
    with pytest.raises(RedPreemptRefused, match="only a rules-engine RED"):
        fire(clock, path, smuggled)
    assert stop.cancels == 0
    assert channel.sent == []


def test_the_timed_path_refuses_a_red_that_reached_it_without_both_axes() -> None:
    """CLAUDE.md invariant 21 has no permitted default, so the path refuses
    rather than picking one. There is no ``or ALERT`` anywhere on it."""
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    axeless = BackendResult.model_construct(
        work_id="w_axeless",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation.model_construct(
            triage_update=RulesTriageResult.model_construct(
                level=TriageLevel.RED,
                rules=(RuleFire(id=RULE_ID, evidence="gogus_agrisi=evet"),),
                register=None,
                location=None,
            ),
            red_script=None,
        ),
        priority=Priority.PREEMPT,
    )
    with pytest.raises(RedPreemptRefused, match="no permitted default"):
        fire(clock, path, axeless)
    assert stop.cancels == 0
    assert channel.sent == []


# ==========================================================================================
# B. The two budgets, on the fake clock
# ==========================================================================================


def test_playback_stop_is_measured_and_within_the_150_ms_budget() -> None:
    clock = FakeClock()
    path, stop, channel = build_red_path(
        clock,
        stop=RecordingPlaybackStop(clock=clock, delay_ms=40.0),
        channel=RecordingDataChannel(clock=clock, delay_ms=25.0),
    )
    outcome = fire(clock, path, red_result())
    assert stop.cancels == 1
    assert outcome.stop_ms == pytest.approx(40.0)
    assert outcome.script_start_ms == pytest.approx(65.0)
    assert len(channel.sent) == 1
    _assert_within_budget(outcome)


def test_end_to_end_script_start_is_measured_and_within_the_300_ms_budget() -> None:
    """Stop first, then the data-channel trigger — the e2e number covers both."""
    clock = FakeClock()
    path, _, channel = build_red_path(
        clock,
        stop=RecordingPlaybackStop(clock=clock, delay_ms=120.0),
        channel=RecordingDataChannel(clock=clock, delay_ms=25.0),
    )
    outcome = fire(clock, path, red_result())
    assert outcome.stop_ms == pytest.approx(120.0)
    assert outcome.script_start_ms == pytest.approx(145.0)
    assert len(channel.sent) == 1
    _assert_within_budget(outcome)


def test_the_stop_happens_before_the_script_is_triggered() -> None:
    """files/03 §4.6 invariant 4: *"cancelling the in-flight playback has to
    happen first"*."""
    clock = FakeClock()
    path, _, _ = build_red_path(
        clock,
        stop=RecordingPlaybackStop(clock=clock, delay_ms=60.0),
        channel=RecordingDataChannel(clock=clock, delay_ms=30.0),
    )
    outcome = fire(clock, path, red_result())
    assert outcome.stop_ms == pytest.approx(60.0)
    assert outcome.script_start_ms == pytest.approx(90.0)
    assert outcome.stop_ms < outcome.script_start_ms


def test_a_slow_stop_breaks_the_budget_assertion() -> None:
    """Mutation control. An injected 400 ms stop must make the *same* helper
    that guards every green case above fail — otherwise the number is not
    being measured at all."""
    clock = FakeClock()
    path, _, _ = build_red_path(clock, stop=RecordingPlaybackStop(clock=clock, delay_ms=400.0))
    outcome = fire(clock, path, red_result())
    assert outcome.stop_ms == pytest.approx(400.0)
    assert outcome.within_stop_budget is False
    with pytest.raises(AssertionError, match="playback stop took"):
        _assert_within_budget(outcome)


def test_a_slow_data_channel_breaks_the_end_to_end_assertion() -> None:
    """The second mutation control, on the other half of the path."""
    clock = FakeClock()
    path, _, _ = build_red_path(
        clock,
        stop=RecordingPlaybackStop(clock=clock, delay_ms=100.0),
        channel=RecordingDataChannel(clock=clock, delay_ms=350.0),
    )
    outcome = fire(clock, path, red_result())
    assert outcome.script_start_ms == pytest.approx(450.0)
    assert outcome.within_stop_budget is True, "the stop itself was inside its own budget"
    assert outcome.within_e2e_budget is False
    with pytest.raises(AssertionError, match="script start took"):
        _assert_within_budget(outcome)


def test_an_over_budget_red_still_fires() -> None:
    """A late RED is a late RED, not a cancelled one. The budget is measured
    and reported; it is never a reason to withhold an emergency instruction."""
    clock = FakeClock()
    path, stop, channel = build_red_path(
        clock, channel=RecordingDataChannel(clock=clock, delay_ms=900.0)
    )
    outcome = fire(clock, path, red_result())
    assert stop.cancels == 1
    assert len(channel.sent) == 1
    assert outcome.within_e2e_budget is False


def test_the_budget_runs_from_acceptance_not_from_the_trigger_call() -> None:
    """The session stamps the clock when the RED is accepted, so time spent
    between acceptance and the trigger is charged to the budget."""
    clock = FakeClock()
    path, _, _ = build_red_path(clock)

    async def main() -> RedPreemptOutcome:
        accepted_at_ms = clock.now_ms()
        await clock.sleep(0.4)
        return await path.trigger(red_result(), accepted_at_ms=accepted_at_ms)

    outcome = clock.run(main())
    assert outcome.stop_ms == pytest.approx(400.0)
    assert outcome.script_start_ms == pytest.approx(400.0)
    assert outcome.within_stop_budget is False
    assert outcome.within_e2e_budget is False
    with pytest.raises(AssertionError, match="playback stop took"):
        _assert_within_budget(outcome)


# ==========================================================================================
# C. The register x location matrix (CLAUDE.md invariant 21; files/02 §5.3)
# ==========================================================================================


@pytest.mark.parametrize("register", list(RedRegister))
@pytest.mark.parametrize("location", list(RedLocation))
def test_the_register_and_location_matrix_resolves_for_every_cell(
    register: RedRegister, location: RedLocation
) -> None:
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    outcome = fire(clock, path, red_result(register, location))

    audible = REGISTER_AUDIO[register].spoken
    patient_facing = register is not RedRegister.DEFERRED_CLINICIAN

    assert outcome.audible is audible
    assert outcome.playback_stopped is audible
    assert stop.cancels == (1 if audible else 0)
    assert outcome.patient_script_triggered is patient_facing
    assert len(channel.sent) == (1 if patient_facing else 0)
    if patient_facing:
        assert channel.sent[0].register is register
        assert channel.sent[0].location is location
        assert channel.sent[0].audio == REGISTER_AUDIO[register]


@pytest.mark.parametrize("location", list(RedLocation))
def test_a_silent_red_produces_no_audible_interrupt(location: RedLocation) -> None:
    """files/02 §5.3: SILENT is *"Screen only … No audio, ever"* — so nothing
    is cut off mid-sentence either. An abrupt cut is itself an audible event,
    and the register exists for rooms where that is the harm."""
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    outcome = fire(clock, path, red_result(RedRegister.SILENT, location))
    assert outcome.audible is False
    assert outcome.playback_stopped is False
    assert outcome.stop_ms is None
    assert stop.cancels == 0
    assert len(channel.sent) == 1 and channel.sent[0].audible is False


@pytest.mark.parametrize("location", list(RedLocation))
def test_a_deferred_clinician_red_leaves_the_patient_path_untouched(
    location: RedLocation,
) -> None:
    """files/02 §5.3: *"Patient screen unchanged. Finding routes to the
    clinician only."* Layer A therefore does nothing at all — the clinician
    route is the unconditional server-side effect of §5.3, not a Talker one."""
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    outcome = fire(clock, path, red_result(RedRegister.DEFERRED_CLINICIAN, location))
    assert outcome.playback_stopped is False
    assert outcome.patient_script_triggered is False
    assert stop.cancels == 0
    assert channel.sent == []


def test_under_on_site_the_112_affordance_is_absent() -> None:
    """CLAUDE.md invariant 21: absent, not de-emphasised."""
    clock = FakeClock()
    path, _, channel = build_red_path(clock)
    fire(clock, path, red_result(RedRegister.ALERT, RedLocation.ON_SITE))
    assert channel.sent[0].show_112 is False
    assert channel.sent[0].notify_staff is True


def test_an_on_site_script_ref_cannot_be_built_with_the_112_affordance() -> None:
    """The refusal is on the ref, not only on the message it produces."""
    with pytest.raises(ValidationError, match="ON_SITE"):
        RedScriptRef(
            rule_id=RULE_ID,
            kind=RedScriptKind.ACTION,
            register=RedRegister.ALERT,
            location=RedLocation.ON_SITE,
            script_id=f"red.{RULE_ID}.on_site",
            script_hash="a" * 64,
            show_112=True,
            notify_staff=True,
        )


def _ref_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "rule_id": RULE_ID,
        "kind": RedScriptKind.ACTION,
        "register": RedRegister.ALERT,
        "location": RedLocation.REMOTE,
        "script_id": f"red.{RULE_ID}.remote",
        "script_hash": "a" * 64,
        "show_112": False,
        "notify_staff": False,
    }
    return base | overrides


def test_an_unknown_location_ref_may_not_name_an_action_script() -> None:
    """files/02 §5.3 Axis 3: UNKNOWN resolves to one question. Modelling it as
    an action with weaker content is how the guess gets made."""
    with pytest.raises(ValidationError, match="one question"):
        RedScriptRef(
            **_ref_kwargs(  # type: ignore[arg-type]
                location=RedLocation.UNKNOWN,
                kind=RedScriptKind.ACTION,
                script_id=f"red.{RULE_ID}.unknown",
            )
        )


def test_an_unknown_location_ref_may_not_render_112_before_the_question() -> None:
    with pytest.raises(ValidationError, match="until the one question"):
        RedScriptRef(
            **_ref_kwargs(  # type: ignore[arg-type]
                location=RedLocation.UNKNOWN,
                kind=RedScriptKind.LOCATION_QUESTION,
                script_id=f"red.{RULE_ID}.unknown",
                show_112=True,
            )
        )


@pytest.mark.parametrize("location", [RedLocation.REMOTE, RedLocation.ON_SITE])
def test_a_resolved_location_ref_may_not_name_the_one_question(
    location: RedLocation,
) -> None:
    with pytest.raises(ValidationError, match="action script"):
        RedScriptRef(
            **_ref_kwargs(  # type: ignore[arg-type]
                location=location,
                kind=RedScriptKind.LOCATION_QUESTION,
                script_id=f"red.{RULE_ID}.{location.value.lower()}",
            )
        )


def test_a_ref_whose_script_id_is_not_the_derived_key_is_refused() -> None:
    """The device looks the script up by the derived key; a hand-written id
    resolves to nothing on the bundle, which is a silent no-op at the worst
    possible moment."""
    with pytest.raises(ValidationError, match="derived key"):
        RedScriptRef(**_ref_kwargs(script_id="red.something.else"))  # type: ignore[arg-type]


def test_a_location_that_disagrees_with_the_resolved_action_type_is_refused() -> None:
    with pytest.raises(ValueError, match="does not match the resolved action type"):
        script_ref_for_action(
            rule_id=RULE_ID,
            register=RedRegister.ALERT,
            location=RedLocation.UNKNOWN,
            action=REMOTE_ACTION,
        )
    with pytest.raises(ValueError, match="does not match the resolved action type"):
        script_ref_for_action(
            rule_id=RULE_ID,
            register=RedRegister.ALERT,
            location=RedLocation.REMOTE,
            action=UNKNOWN_ACTION,
        )


def test_a_remote_red_may_carry_the_112_affordance() -> None:
    clock = FakeClock()
    path, _, channel = build_red_path(clock)
    fire(clock, path, red_result(RedRegister.ALERT, RedLocation.REMOTE))
    assert channel.sent[0].show_112 is True
    assert channel.sent[0].notify_staff is False


def test_the_unknown_location_triggers_the_one_question_not_an_action_script() -> None:
    """files/02 §5.3 Axis 3: *"Ask exactly one question … Never guess"*, and
    112 is not rendered until the answer comes back."""
    clock = FakeClock()
    path, _, channel = build_red_path(clock)
    fire(clock, path, red_result(RedRegister.ALERT, RedLocation.UNKNOWN))
    assert channel.sent[0].kind is RedScriptKind.LOCATION_QUESTION
    assert channel.sent[0].show_112 is False


def test_the_typed_profile_has_no_audible_red_and_stops_no_playback() -> None:
    """ADR-010 / invariant 19: the typed lane has no audio port at all, so no
    register can produce an audible interrupt on it."""
    clock = FakeClock()
    path, stop, channel = build_red_path(clock, profile=VoiceProfile.TYPED)
    outcome = fire(clock, path, red_result(RedRegister.ALERT, RedLocation.REMOTE))
    assert outcome.audible is False
    assert outcome.playback_stopped is False
    assert stop.cancels == 0
    assert len(channel.sent) == 1 and channel.sent[0].audible is False


def test_red_delivery_reads_the_blueprint_register_table() -> None:
    """The audibility of a register is transcribed once, in
    ``protocols.dsl.REGISTER_AUDIO``, and read from there — never restated."""
    for register in RedRegister:
        delivery = red_delivery(register, VoiceProfile.RESIDENCY_TR)
        assert delivery.audible is REGISTER_AUDIO[register].spoken
        assert delivery.audio == REGISTER_AUDIO[register]


# ==========================================================================================
# D. No media transport (files/03 §4.6 invariant 4, its own wording)
# ==========================================================================================

RED_PATH_MODULES = (
    "intake_voice_runtime.talker.red_path",
    "intake_voice_runtime.talker.red_script",
)
#: Modules that construct, fetch or stream agent audio. None may appear in the
#: RED path's import closure.
MEDIA_MODULES = frozenset(
    {
        "intake_voice_runtime.talker.speech",
        "intake_voice_runtime.talker.clips",
        "intake_voice_runtime.talker.insertion",
        "intake_voice_runtime.talker.session",
    }
)
#: Names whose presence would mean the path can reach a synthesiser, a clip
#: store or an audio sink.
MEDIA_NAMES = frozenset(
    {
        "AudioSink",
        "ClipCatalogue",
        "ClipStore",
        "SpeechRouter",
        "SpeechSynthesizer",
        "SpokenSpeech",
        "clip_id_for",
    }
)
#: Methods that would put a byte of audio on the wire.
MEDIA_CALLS = frozenset({"play", "speak", "synthesize", "fetch"})


def _module_path(name: str) -> Path:
    module = sys.modules.get(name)
    if module is None:
        __import__(name)
        module = sys.modules[name]
    source = getattr(module, "__file__", None)
    assert source is not None, f"{name} has no source file"
    return Path(source)


def _imported_modules(tree: ast.Module) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            yield node.module


def _import_closure(roots: tuple[str, ...], package: str) -> set[str]:
    """Every ``package`` module reachable from ``roots`` by a static import."""
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        tree = ast.parse(_module_path(name).read_text(encoding="utf-8"))
        for imported in _imported_modules(tree):
            if imported.startswith(package) and imported not in seen:
                stack.append(imported)
    return seen


def test_the_red_path_import_closure_contains_no_media_module() -> None:
    closure = _import_closure(RED_PATH_MODULES, "intake_voice_runtime")
    assert not (closure & MEDIA_MODULES), (
        f"the RED path can reach {sorted(closure & MEDIA_MODULES)} — files/03 §4.6 "
        "invariant 4 requires it to touch no media transport"
    )


def test_the_red_path_imports_no_media_name() -> None:
    for name in RED_PATH_MODULES:
        tree = ast.parse(_module_path(name).read_text(encoding="utf-8"))
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom | ast.Import)
            for alias in node.names
        }
        assert not (imported & MEDIA_NAMES), f"{name} imports {sorted(imported & MEDIA_NAMES)}"


def test_the_red_path_calls_no_synthesis_or_playback_method() -> None:
    for name in RED_PATH_MODULES:
        tree = ast.parse(_module_path(name).read_text(encoding="utf-8"))
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not (called & MEDIA_CALLS), f"{name} calls {sorted(called & MEDIA_CALLS)}"


def test_a_red_through_a_wired_session_asks_the_sink_to_play_nothing() -> None:
    """The behavioural half: a full RED through the Talker never reaches the
    clip store, the synthesiser or the sink's play path."""
    clock = FakeClock()
    sink = RecordingSink(clock=clock)
    clip_store = RecordedClipStore()
    synthesizer = RecordingSynthesizer()
    channel = RecordingDataChannel(clock=clock)
    session = build_session(
        clock,
        steps=[],
        backend=ReadyBackend(results=[red_result()]),  # type: ignore[arg-type]
        clip_store=clip_store,
        synthesizer=synthesizer,
        sink=sink,
        rule_ids=PACK_RULES,
        red_channel=channel,
    )
    outcomes = clock.run(session.take_turn(None))
    assert outcomes.red_preempts == 1
    assert len(channel.sent) == 1
    assert sink.played == []
    assert clip_store.served == []
    assert synthesizer.requests == []


# ==========================================================================================
# E. The script itself: verbatim, hash-bound, and carrying no numeral
# ==========================================================================================


def test_a_script_carrying_a_bare_numeral_is_refused() -> None:
    """CLAUDE.md invariant 22: the compiler expands every digit to Turkish
    orthography, so a numeral here means an upstream invariant already failed."""
    with pytest.raises(ValueError, match="numeral"):
        script_ref_for_action(
            rule_id=RULE_ID,
            register=RedRegister.ALERT,
            location=RedLocation.REMOTE,
            action=LocationAction(primary="CALL_112", show_112=True, action_tr="112'yi arayın."),
        )


@pytest.mark.parametrize(
    "action",
    [
        pytest.param(
            LocationAction(
                primary="CALL_112",
                show_112=True,
                action_tr="Yüz on ikiyi arayın.",
                do_nots_tr=("2 saat beklemeyin.",),
            ),
            id="do_nots_tr",
        ),
        pytest.param(
            LocationAction(
                primary="CALL_112",
                show_112=True,
                action_tr="Yüz on ikiyi arayın.",
                why_tr="Son 3 saatte artmış olabilir.",
            ),
            id="why_tr",
        ),
    ],
)
def test_the_numeral_refusal_reaches_every_turkish_carrier_on_the_action(
    action: LocationAction,
) -> None:
    with pytest.raises(ValueError, match="numeral"):
        script_ref_for_action(
            rule_id=RULE_ID,
            register=RedRegister.ALERT,
            location=RedLocation.REMOTE,
            action=action,
        )


def test_the_unknown_question_is_numeral_checked_too() -> None:
    with pytest.raises(ValueError, match="numeral"):
        script_ref_for_action(
            rule_id=RULE_ID,
            register=RedRegister.ALERT,
            location=RedLocation.UNKNOWN,
            action=UnknownAction(
                ask_one_tr="Şu anda 1 hastanede misiniz?",
                on_yes="ON_SITE",
                on_no="REMOTE",
                on_no_answer="REMOTE",
            ),
        )


def test_the_script_hash_binds_the_pre_positioned_copy_to_the_compiled_action() -> None:
    """Invariant 10 is verbatim delivery; the runtime never holds the text, so
    the hash is what refuses a device copy that has drifted from the pack."""
    original = script_for(RedRegister.ALERT, RedLocation.REMOTE)
    edited = script_ref_for_action(
        rule_id=RULE_ID,
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
        action=REMOTE_ACTION.model_copy(update={"why_tr": "Başka bir açıklama."}),
    )
    assert original.script_hash != edited.script_hash
    assert original.script_id == edited.script_id


def test_the_script_ref_and_the_trigger_carry_no_patient_text() -> None:
    """The RED script is pre-positioned on the device; only its identity
    travels. That also keeps clinical Turkish off the trigger path entirely."""
    clock = FakeClock()
    path, _, channel = build_red_path(clock)
    fire(clock, path, red_result())
    payload = channel.sent[0].model_dump_json()
    for text in (
        REMOTE_ACTION.action_tr,
        REMOTE_ACTION.why_tr,
        *REMOTE_ACTION.do_nots_tr,
    ):
        assert text is not None and text not in payload


# ==========================================================================================
# F. Fails closed rather than dropping, or inventing, a RED
# ==========================================================================================


def test_a_preempt_with_no_pre_positioned_script_is_refused_loudly() -> None:
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    with pytest.raises(RedScriptUnavailable):
        fire(clock, path, red_result(script=None))
    assert stop.cancels == 0, "a RED that cannot be delivered must not cut the patient off"
    assert channel.sent == []


def test_a_script_whose_axes_disagree_with_the_determination_is_refused() -> None:
    """A script resolved for another location or register is not this RED's
    script — swapping one in is the copy-a-RED-shape attack, one level down."""
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    mismatched = red_result(
        RedRegister.ALERT,
        RedLocation.ON_SITE,
        script=script_for(RedRegister.ALERT, RedLocation.REMOTE),
    )
    with pytest.raises(RedScriptMismatch):
        fire(clock, path, mismatched)
    assert stop.cancels == 0
    assert channel.sent == []


def test_a_script_naming_another_rule_than_the_determination_is_refused() -> None:
    clock = FakeClock()
    path, stop, channel = build_red_path(clock)
    other = script_ref_for_action(
        rule_id="rf.kanama",
        register=RedRegister.ALERT,
        location=RedLocation.REMOTE,
        action=REMOTE_ACTION,
    )
    with pytest.raises(RedScriptMismatch):
        fire(clock, path, red_result(script=other))
    assert stop.cancels == 0
    assert channel.sent == []


def test_a_session_with_no_data_channel_refuses_rather_than_dropping_a_red() -> None:
    clock = FakeClock()
    session = build_session(
        clock,
        steps=[],
        backend=ReadyBackend(results=[red_result()]),  # type: ignore[arg-type]
        rule_ids=PACK_RULES,
    )
    with pytest.raises(RedPathNotWired):
        clock.run(session.take_turn(None))


# ==========================================================================================
# G. Invariant 9, both halves: the ordinary result waits, the RED does not
# ==========================================================================================


def test_an_ordinary_result_waits_for_the_window_and_the_red_does_not() -> None:
    """One session, one closed insertion window, two results."""
    clock = FakeClock()
    channel = RecordingDataChannel(clock=clock)
    yellow = BackendResult(
        work_id="w_yellow",
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
    session = build_session(
        clock,
        steps=[],
        backend=ReadyBackend(results=[yellow, red_result()]),  # type: ignore[arg-type]
        rule_ids=PACK_RULES,
        red_channel=channel,
    )
    # The patient is mid-sentence: no natural, relaxed or interject window.
    session.observe_duplex(
        DuplexState(
            patient_silence_ms=0.0,
            talker_idle=False,
            pending_response=True,
            at_sentence_boundary=False,
        )
    )
    outcome = clock.run(session.take_turn(None))
    assert outcome.delivered_work_ids == (), "the YELLOW must wait for a safe window"
    assert session.scheduler.pending_work_ids == ("w_yellow",)
    assert outcome.red_preempts == 1, "the RED does not wait for a window"
    assert len(channel.sent) == 1


def test_the_red_fires_before_the_turns_next_step_is_spoken() -> None:
    """The channel is given a 20 ms cost so the two stamps cannot coincide:
    the trigger is stamped strictly before the step's playback begins."""
    clock = FakeClock()
    channel = RecordingDataChannel(clock=clock, delay_ms=20.0)
    sink = RecordingSink(clock=clock)
    session = build_session(
        clock,
        steps=[scripted_step()],
        backend=ReadyBackend(results=[red_result()]),  # type: ignore[arg-type]
        sink=sink,
        rule_ids=PACK_RULES,
        red_channel=channel,
    )
    outcome = clock.run(session.take_turn(None))
    assert outcome.red_preempts == 1
    assert sink.played, "the turn did speak its step, so the ordering is real"
    assert channel.sent[0].sent_at_ms < session.playback_intervals[0][0]


def test_the_session_measures_the_red_from_the_moment_it_accepted_it() -> None:
    clock = FakeClock()
    channel = RecordingDataChannel(clock=clock, delay_ms=30.0)
    session = build_session(
        clock,
        steps=[],
        backend=ReadyBackend(results=[red_result()]),  # type: ignore[arg-type]
        rule_ids=PACK_RULES,
        red_channel=channel,
    )
    clock.run(session.take_turn(None))
    assert len(session.red_outcomes) == 1
    outcome = session.red_outcomes[0]
    assert outcome.script_start_ms == pytest.approx(30.0)
    _assert_within_budget(outcome)
