"""INT-430 — the asymmetric adjudication rule and the engine's compare-and-swap.

ADR-036: one arming reading re-asks, no count of absent readings clears, a
numeric doubt appends the slot's own confirm-back, and every append lands
only at the slot revision the verifier read. Each must-have test from the two
challenger reviews carries a near-miss negative control. Synthetic throughout.
"""

from __future__ import annotations

import itertools

from clinical_schemas.overlay import LearnedFact, LearnedFactSource, PatientOverlay
from clinical_schemas.session import AnswerState
from council_harness import (
    BELIRTI,
    IKINCI,
    NOW,
    OLCUM,
    answer,
    engine,
    ok,
    protocol,
    reading,
    round_of,
    scope,
    view,
)
from intake_voice_runtime.clinical_agent.council.adjudicate import (
    ActionKind,
    Agreement,
    adjudicate,
    views_of,
)
from intake_voice_runtime.clinical_agent.council.orchestrator import MemberOutcome, MemberResult
from intake_voice_runtime.clinical_agent.council.readings import Reading
from intake_voice_runtime.clinical_agent.fsm import (
    AppendOutcome,
    IntakeEngine,
    VerificationKind,
)
from intake_voice_runtime.steps import StepKind

SAID = "Sentetik belirtim yok, ölçüm on iki, bazen var gibi."


def _present(member: str = "m1", sample: int = 0) -> MemberResult:
    return ok(member, reading(BELIRTI, Reading.PRESENT, SAID, "bazen var gibi"), sample=sample)


def _absent(member: str = "m1", sample: int = 0) -> MemberResult:
    return ok(member, reading(BELIRTI, Reading.ABSENT, SAID, "belirtim yok"), sample=sample)


# --- the rule ------------------------------------------------------------------------------


class TestAsymmetry:
    def test_council_cannot_clear_rf_gate(self) -> None:
        views = {BELIRTI: view(BELIRTI, AnswerState.ASKED_PRESENT, True)}
        unanimous_absent = round_of(*(_absent("m1", sample) for sample in range(5)))
        verdict = adjudicate(unanimous_absent, views, scope())
        assert verdict.actions == ()
        assert verdict.contested == ()

    def test_near_miss_one_present_against_a_direct_absent_reasks(self) -> None:
        views = {BELIRTI: view(BELIRTI, AnswerState.ASKED_ABSENT, False)}
        verdict = adjudicate(round_of(_absent("m1", 0), _present("m1", 1)), views, scope())
        assert [(a.kind, a.ref) for a in verdict.actions] == [(ActionKind.REASK_POSITIVE, BELIRTI)]
        assert verdict.contested[0].direct_state is AnswerState.ASKED_ABSENT

    def test_a_majority_absent_never_outvotes_one_arming_reading(self) -> None:
        views = {BELIRTI: view(BELIRTI, AnswerState.ASKED_ABSENT, False)}
        draws = [_absent("m1", sample) for sample in range(7)] + [_present("m1", 7)]
        assert adjudicate(round_of(*draws), views, scope()).actions[0].kind is (
            ActionKind.REASK_POSITIVE
        )

    def test_narrative_never_yields_asked_absent(self) -> None:
        views = {BELIRTI: view(BELIRTI, AnswerState.NOT_ASKED)}
        verdict = adjudicate(round_of(_absent("m1"), _absent("m1", 1)), views, scope())
        assert verdict.actions == () and verdict.narrative_refs == ()
        fresh = engine()
        assert fresh.state_of(BELIRTI) is AnswerState.NOT_ASKED

    def test_near_miss_a_direct_scripted_absent_does_bind(self) -> None:
        fresh = engine()
        answer(fresh, BELIRTI, False)
        assert fresh.state_of(BELIRTI) is AnswerState.ASKED_ABSENT

    def test_asr_flip_yok_cok_still_confirmed(self) -> None:
        """ "çok" heard as "yok": the primary bound absent; one draw read present."""
        heard = "Sentetik belirtim yok, çok değil."
        draws = round_of(
            ok("m1", reading(BELIRTI, Reading.ABSENT, heard, "belirtim yok")),
            ok("m1", reading(BELIRTI, Reading.QUALIFIED_PRESENT, heard, "çok değil"), sample=1),
        )
        views = {BELIRTI: view(BELIRTI, AnswerState.ASKED_ABSENT, False)}
        assert adjudicate(draws, views, scope()).actions[0].kind is ActionKind.REASK_POSITIVE

    def test_near_miss_agreeing_draws_on_a_bound_present_do_nothing(self) -> None:
        views = {BELIRTI: view(BELIRTI, AnswerState.ASKED_PRESENT, True)}
        verdict = adjudicate(round_of(_present("m1"), _present("m1", 1)), views, scope())
        assert verdict.actions == ()
        assert verdict.agreement == (("m1", Agreement.AGREE),)

    def test_arming_narrative_on_an_open_unasked_step_is_recorded_not_reordered(self) -> None:
        views = {BELIRTI: view(BELIRTI, AnswerState.NOT_ASKED, gate_open=True)}
        verdict = adjudicate(round_of(_present()), views, scope())
        assert verdict.actions == ()
        assert verdict.narrative_refs == (BELIRTI,)

    def test_candidate_flags_add_only(self) -> None:
        said = "İkinci sentetik şikayetim de var."
        draws = round_of(ok("m1", reading(IKINCI, Reading.PRESENT, said, "şikayetim de var")))
        views = {IKINCI: view(IKINCI, AnswerState.NOT_ASKED, gate_open=False)}
        verdict = adjudicate(draws, views, scope())
        assert [a.kind for a in verdict.actions] == [ActionKind.CANDIDATE_FLAG]
        (flag,) = verdict.candidate_flags
        assert flag.text == f"council.narrative_evidence:{IKINCI}"
        assert said not in flag.text and said not in flag.evidence

    def test_near_miss_an_absent_narrative_raises_no_flag_and_lowers_nothing(self) -> None:
        said = "İkinci sentetik şikayetim yok."
        draws = round_of(ok("m1", reading(IKINCI, Reading.ABSENT, said, "şikayetim yok")))
        views = {IKINCI: view(IKINCI, AnswerState.NOT_ASKED, gate_open=False)}
        assert adjudicate(draws, views, scope()).candidate_flags == ()


class TestNumericConfirmBack:
    def test_a_different_number_appends_a_confirm_back(self) -> None:
        draws = round_of(ok("m1", reading(OLCUM, Reading.PRESENT, SAID, "on iki", number="21")))
        views = {OLCUM: view(OLCUM, AnswerState.ASKED_PRESENT, 12)}
        verdict = adjudicate(draws, views, scope())
        assert [a.kind for a in verdict.actions] == [ActionKind.CONFIRM_BACK]
        assert verdict.contested[0].readings == (("m1", Reading.PRESENT, "21"),)

    def test_near_miss_the_same_number_in_another_carrier_agrees(self) -> None:
        draws = round_of(ok("m1", reading(OLCUM, Reading.PRESENT, SAID, "on iki", number="12.0")))
        views = {OLCUM: view(OLCUM, AnswerState.ASKED_PRESENT, 12)}
        assert adjudicate(draws, views, scope()).actions == ()

    def test_a_doubtful_reading_without_a_number_still_confirms(self) -> None:
        draws = round_of(ok("m1", reading(OLCUM, Reading.HEDGED, SAID, "on iki")))
        views = {OLCUM: view(OLCUM, AnswerState.ASKED_PRESENT, 12)}
        assert adjudicate(draws, views, scope()).actions[0].kind is ActionKind.CONFIRM_BACK


class TestDeterminism:
    def test_the_verdict_ignores_draw_order(self) -> None:
        views = {
            BELIRTI: view(BELIRTI, AnswerState.ASKED_ABSENT, False),
            OLCUM: view(OLCUM, AnswerState.ASKED_PRESENT, 12),
        }
        results = [
            _present("m1"),
            _absent("m2"),
            ok("m3", reading(OLCUM, Reading.PRESENT, SAID, "on iki", number="13")),
            MemberResult(member_id="m4", sample=0, outcome=MemberOutcome.TIMED_OUT),
        ]
        verdicts = {
            repr(adjudicate(round_of(*order), views, scope()))
            for order in itertools.permutations(results)
        }
        assert len(verdicts) == 1

    def test_the_verdict_is_reproducible_across_rotations_of_many_draws(self) -> None:
        views = {BELIRTI: view(BELIRTI, AnswerState.ASKED_ABSENT, False)}
        draws = [_absent(f"m{i}") for i in range(6)] + [_present("m9")]
        orders = [draws[shift:] + draws[:shift] for shift in range(len(draws))]
        orders += [list(reversed(order)) for order in orders]
        seen = {repr(adjudicate(round_of(*order), views, scope())) for order in orders}
        assert len(seen) == 1

    def test_near_miss_a_timed_out_member_abstains_rather_than_agreeing(self) -> None:
        silent = MemberResult(member_id="m4", sample=0, outcome=MemberOutcome.TIMED_OUT)
        verdict = adjudicate(round_of(silent), {}, scope())
        assert verdict.agreement == (("m4", Agreement.ABSTAIN),)


# --- the engine side --------------------------------------------------------------------


class TestCompareAndSwap:
    def test_cas_patient_corrects_mid_flight(self) -> None:
        live = engine()
        answer(live, BELIRTI, False)
        read_at = live.slot_revision(BELIRTI)
        # An earlier re-ask is answered "present" before this verdict lands.
        live.append_verification(BELIRTI, VerificationKind.REASK, read_at)
        live.mark_asked(f"{BELIRTI}/verify/1")
        live.apply_extraction(f"{BELIRTI}/verify/1", {BELIRTI: True})
        stale = live.append_verification(BELIRTI, VerificationKind.REASK, read_at)
        assert stale is AppendOutcome.STALE_REVISION
        assert live.value_of(BELIRTI) is True

    def test_near_miss_a_verdict_at_the_current_revision_appends(self) -> None:
        live = engine()
        answer(live, BELIRTI, False)
        outcome = live.append_verification(
            BELIRTI, VerificationKind.REASK, live.slot_revision(BELIRTI)
        )
        assert outcome is AppendOutcome.APPENDED
        head = live.next_step()
        assert head is not None and head.step_id == f"{BELIRTI}/verify/1"
        assert head.text_tr == "Sentetik belirtiniz var mı?"  # the positive question, verbatim
        assert head.kind is StepKind.SCRIPTED

    def test_council_never_overwrites_asked_answer(self) -> None:
        live = engine()
        answer(live, BELIRTI, False)
        live.append_verification(BELIRTI, VerificationKind.REASK, live.slot_revision(BELIRTI))
        assert live.state_of(BELIRTI) is AnswerState.ASKED_ABSENT
        assert live.value_of(BELIRTI) is False

    def test_near_miss_the_patients_own_reask_answer_does_rebind(self) -> None:
        live = engine()
        answer(live, BELIRTI, False)
        live.append_verification(BELIRTI, VerificationKind.REASK, live.slot_revision(BELIRTI))
        live.mark_asked(f"{BELIRTI}/verify/1")
        live.apply_extraction(f"{BELIRTI}/verify/1", {BELIRTI: True})
        assert live.state_of(BELIRTI) is AnswerState.ASKED_PRESENT

    def test_a_confirm_back_speaks_the_slots_own_confirm_text(self) -> None:
        live = engine()
        answer(live, OLCUM, 12)
        live.append_verification(OLCUM, VerificationKind.CONFIRM_BACK, live.slot_revision(OLCUM))
        head = live.next_step()
        assert head is not None and head.kind is StepKind.CONFIRM
        assert head.text_tr == "Sentetik ölçümü doğru anladım mı?"

    def test_appends_are_bounded_and_never_target_an_unanswered_slot(self) -> None:
        live = engine()
        assert (
            live.append_verification(OLCUM, VerificationKind.CONFIRM_BACK, 0)
            is AppendOutcome.NOT_ANSWERED
        )
        answer(live, OLCUM, 12)
        revision = live.slot_revision(OLCUM)
        assert live.append_verification(OLCUM, VerificationKind.CONFIRM_BACK, revision) is (
            AppendOutcome.APPENDED
        )
        assert live.append_verification(OLCUM, VerificationKind.CONFIRM_BACK, revision) is (
            AppendOutcome.ALREADY_QUEUED
        )
        live.mark_asked(f"{OLCUM}/verify/1")
        live.apply_extraction(f"{OLCUM}/verify/1", {OLCUM: 12})
        live.append_verification(OLCUM, VerificationKind.CONFIRM_BACK, live.slot_revision(OLCUM))
        live.mark_asked(f"{OLCUM}/verify/2")
        live.apply_extraction(f"{OLCUM}/verify/2", {OLCUM: 12})
        assert (
            live.append_verification(
                OLCUM, VerificationKind.CONFIRM_BACK, live.slot_revision(OLCUM)
            )
            is AppendOutcome.EXHAUSTED
        )

    def test_a_slot_with_no_confirm_text_gets_no_improvised_step(self) -> None:
        live = engine()
        answer(live, BELIRTI, True)
        answer(live, IKINCI, True)
        outcome = live.append_verification(
            IKINCI, VerificationKind.CONFIRM_BACK, live.slot_revision(IKINCI)
        )
        assert outcome is AppendOutcome.NO_SCRIPT

    def test_views_read_the_engine_without_writing_it(self) -> None:
        live = engine()
        answer(live, OLCUM, 12)
        version = live.snapshot.version
        views = views_of(live, scope())
        assert views[OLCUM].state is AnswerState.ASKED_PRESENT
        assert views[IKINCI].gate_open is False
        assert live.snapshot.version == version


def _walk(live: IntakeEngine, answers: dict[str, object], *, verify: bool) -> list[str]:
    """Answer every offered step; with ``verify`` arm a re-ask on the first absent."""
    asked: list[str] = []
    armed = False
    while (step := live.next_step()) is not None and len(asked) < 20:
        asked.append(step.step_id)
        live.mark_asked(step.step_id)
        origin = step.step_id.split("/")[0]
        value = answers.get(origin, True) if "/verify/" not in step.step_id else True
        live.apply_extraction(step.step_id, {origin: value})
        if verify and not armed and value is False:
            armed = True
            live.append_verification(origin, VerificationKind.REASK, live.slot_revision(origin))
    return asked


class TestOrder:
    ANSWERS = {BELIRTI: False, OLCUM: 12}

    def test_asked_order_identical_council_on_off(self) -> None:
        off = _walk(engine(), self.ANSWERS, verify=False)
        on_without_evidence = _walk(engine(), {**self.ANSWERS, BELIRTI: True}, verify=True)
        off_present = _walk(engine(), {**self.ANSWERS, BELIRTI: True}, verify=False)
        assert on_without_evidence == off_present
        assert not any("/verify/" in step for step in off)

    def test_near_miss_an_armed_reask_is_an_insertion_and_nothing_else(self) -> None:
        off = _walk(engine(), self.ANSWERS, verify=False)
        on = _walk(engine(), self.ANSWERS, verify=True)
        inserted = [step for step in on if "/verify/" in step]
        assert inserted == [f"{BELIRTI}/verify/1"]
        without = [step for step in on if "/verify/" not in step]
        # The re-ask's "present" opens the gated step the "absent" kept shut;
        # every step the off-run asked is still asked, in the same order.
        assert [step for step in without if step in off] == off


class TestNoConfirmClearsRedFlag:
    def _overlay(self, key: str, value: object) -> PatientOverlay:
        fact = LearnedFact(
            key=key,
            value=value,
            source=LearnedFactSource.CONFIRMED_INTAKE_EXTRACTION,
            source_ref="sentetik-kaynak",
            confidence=1.0,
            confirmed_at=NOW,
        )
        return PatientOverlay(patient_ref="sentetik-hasta", version=1, facts=(fact,))

    def test_no_confirm_yes_clears_rf(self) -> None:
        live = IntakeEngine(
            protocol=protocol(), reference_time=NOW, overlay_facts=self._overlay(BELIRTI, False)
        )
        assert live.delta.prefills == ()
        assert live.delta.safety_full_ask_fact_keys == (BELIRTI,)
        offered = {step.step_id: step for step in live.frontier()}
        assert offered[BELIRTI].kind is not StepKind.CONFIRM

    def test_near_miss_a_numeric_non_rf_fact_still_prefills_as_confirm(self) -> None:
        live = IntakeEngine(
            protocol=protocol(), reference_time=NOW, overlay_facts=self._overlay(OLCUM, 12)
        )
        assert [p.slot_ref for p in live.delta.prefills] == [OLCUM]
