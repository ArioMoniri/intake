"""INT-540 — a slot's clarification bound can be the decision's, and a session can close.

Two engine mechanisms the onset anchor needs, and nothing clinical:

1. **A per-step clarification bound.** files/13 §11.1 bounds every
   clarification at two attempts (``MAX_CLARIFICATION_ATTEMPTS``). CD-04
   decides that an UNCLEAR answer to a scripted red-flag question triggers
   the slot's ``follow_up_tr`` *once*; composition hands the engine that bound
   for the tense anchor (INT-540). The engine takes a bound per step, at or
   below its own ceiling, and every step it is not given keeps the default.
   A bound of 0 records UNCLEAR on the first unclear answer — the shape the
   D18 amendment open on INT-519 item 5 would take.
2. **Closing an asked, unanswered step.** When the session ends with a step
   asked and unanswered (``ASKED_PENDING``, a clarification still pending
   included), :meth:`IntakeEngine.close_unanswered` records files/13 §11.1's
   give-up state, UNCLEAR, and its gap — exactly what a spent clarification
   records — and nothing else. A step that was never asked, or was answered,
   is refused: nothing binds to a question that was not asked.

The protocol is ``test_fsm``'s synthetic one; every id and string is
synthetic (files/04 §7).
"""

from __future__ import annotations

import pytest
from clinical_schemas.session import AnswerState
from intake_voice_runtime.clinical_agent import EngineError, IntakeEngine
from intake_voice_runtime.clinical_agent.fsm import (
    MAX_CLARIFICATION_ATTEMPTS,
    AppendOutcome,
    VerificationKind,
)
from test_fsm import NOW, _protocol

DURATION = "oyku.sure_gun"
SYMPTOM = "oyku.belirti_var"


def _engine(bounds: dict[str, int] | None = None) -> IntakeEngine:
    return IntakeEngine(protocol=_protocol(), reference_time=NOW, clarification_bounds=bounds)


def _asked_duration(bounds: dict[str, int] | None = None) -> IntakeEngine:
    engine = _engine(bounds)
    engine.mark_asked(SYMPTOM)
    engine.apply_extraction(SYMPTOM, {SYMPTOM: True})
    engine.mark_asked(DURATION)
    return engine


# --- 1 · the per-step bound -----------------------------------------------------------


def test_a_bound_of_one_asks_the_follow_up_once_then_records_unclear() -> None:
    engine = _asked_duration({DURATION: 1})
    engine.apply_extraction(DURATION, {}, clarification_needed=True)
    assert engine.follow_ups == (f"{DURATION}/clarify/1",)
    assert engine.state_of(DURATION) is AnswerState.ASKED_PENDING
    engine.mark_asked(f"{DURATION}/clarify/1")
    engine.apply_extraction(f"{DURATION}/clarify/1", {}, clarification_needed=True)
    assert engine.follow_ups == ()
    assert engine.state_of(DURATION) is AnswerState.UNCLEAR
    assert engine.data_gaps == (DURATION,)
    assert f"{DURATION}/clarify/2" not in [step.step_id for step in engine.frontier()]


def test_a_bound_of_zero_records_unclear_on_the_first_unclear_answer() -> None:
    engine = _asked_duration({DURATION: 0})
    engine.apply_extraction(DURATION, {}, clarification_needed=True)
    assert engine.follow_ups == ()
    assert engine.state_of(DURATION) is AnswerState.UNCLEAR
    assert engine.data_gaps == (DURATION,)


def test_near_miss_a_step_given_no_bound_keeps_files_13s_two() -> None:
    engine = _asked_duration({SYMPTOM: 1})
    assert engine.clarification_bound(DURATION) == MAX_CLARIFICATION_ATTEMPTS == 2
    assert engine.clarification_bound(SYMPTOM) == 1
    engine.apply_extraction(DURATION, {}, clarification_needed=True)
    engine.mark_asked(f"{DURATION}/clarify/1")
    engine.apply_extraction(f"{DURATION}/clarify/1", {}, clarification_needed=True)
    assert engine.follow_ups == (f"{DURATION}/clarify/2",)
    assert engine.state_of(DURATION) is AnswerState.ASKED_PENDING


def test_the_follow_up_answered_binds_whatever_the_bound() -> None:
    engine = _asked_duration({DURATION: 1})
    engine.apply_extraction(DURATION, {}, clarification_needed=True)
    engine.mark_asked(f"{DURATION}/clarify/1")
    engine.apply_extraction(f"{DURATION}/clarify/1", {DURATION: 3})
    assert engine.state_of(DURATION) is AnswerState.ASKED_PRESENT
    assert engine.value_of(DURATION) == 3
    assert engine.data_gaps == ()


def test_a_verification_append_shares_the_steps_bound() -> None:
    """ADR-036: appends share the clarification bound — the step's own one."""
    engine = _asked_duration({DURATION: 1})
    engine.apply_extraction(DURATION, {DURATION: 3})
    revision = engine.slot_revision(DURATION)
    assert engine.append_verification(DURATION, VerificationKind.REASK, revision) is (
        AppendOutcome.APPENDED
    )
    engine.mark_asked(f"{DURATION}/verify/1")
    engine.apply_extraction(f"{DURATION}/verify/1", {DURATION: 4})
    assert engine.append_verification(
        DURATION, VerificationKind.REASK, engine.slot_revision(DURATION)
    ) is (AppendOutcome.EXHAUSTED)


@pytest.mark.parametrize(
    "bounds",
    [
        pytest.param({"oyku.yok": 1}, id="not-a-step"),
        pytest.param({DURATION: -1}, id="negative"),
        pytest.param({DURATION: MAX_CLARIFICATION_ATTEMPTS + 1}, id="above-the-ceiling"),
        pytest.param({DURATION: True}, id="a-boolean"),
    ],
)
def test_a_bound_the_engine_cannot_honour_is_refused_when_it_is_built(
    bounds: dict[str, int],
) -> None:
    """files/13 §11.1's two attempts are a ceiling: a bound may tighten it,
    never lift it, and a bound for a step the plan does not hold is a wiring
    defect rather than something to ignore."""
    with pytest.raises(EngineError):
        _engine(bounds)


# --- 1b · a tighter bound for one answer (INT-546) --------------------------------------
#
# CD-04 round 3 (INT-519 item 5) splits the tense anchor's bound by the cause of
# the UNCLEAR: none for a hedge, one for an answer that binds no choice. The
# step keeps one ceiling (the larger); the caller hands the cause's bound with
# the answer, and the engine honours it if it is no looser than the step's.


def test_a_tighter_bound_for_one_answer_records_unclear_at_once() -> None:
    engine = _asked_duration({DURATION: 1})
    engine.clarify(DURATION, bound=0)
    assert engine.follow_ups == ()
    assert engine.state_of(DURATION) is AnswerState.UNCLEAR
    assert engine.data_gaps == (DURATION,)


def test_near_miss_the_steps_own_bound_handed_in_asks_the_follow_up() -> None:
    engine = _asked_duration({DURATION: 1})
    engine.clarify(DURATION, bound=1)
    assert engine.follow_ups == (f"{DURATION}/clarify/1",)
    assert engine.state_of(DURATION) is AnswerState.ASKED_PENDING


def test_a_tighter_bound_after_the_follow_up_was_asked_records_unclear() -> None:
    """One follow-up spent on an answer that bound no choice; a hedge to it
    (bound zero) records UNCLEAR rather than queueing a second."""
    engine = _asked_duration({DURATION: 1})
    engine.clarify(DURATION, bound=1)
    engine.mark_asked(f"{DURATION}/clarify/1")
    engine.clarify(f"{DURATION}/clarify/1", bound=0)
    assert engine.follow_ups == ()
    assert engine.state_of(DURATION) is AnswerState.UNCLEAR


@pytest.mark.parametrize(
    "bound",
    [pytest.param(-1, id="negative"), pytest.param(2, id="looser"), pytest.param(True, id="bool")],
)
def test_a_bound_looser_than_the_steps_is_refused_and_changes_nothing(bound: int) -> None:
    engine = _asked_duration({DURATION: 1})
    version = engine.snapshot.version
    with pytest.raises(EngineError):
        engine.clarify(DURATION, bound=bound)
    assert engine.state_of(DURATION) is AnswerState.ASKED_PENDING
    assert engine.follow_ups == () and engine.snapshot.version == version


def test_clarifications_left_counts_the_steps_bound_down() -> None:
    engine = _asked_duration({DURATION: 1})
    assert engine.clarifications_left(DURATION) == 1
    engine.apply_extraction(DURATION, {}, True)
    assert engine.clarifications_left(DURATION) == 0
    # near miss: a step given no bound keeps files/13 §11.1's two
    assert engine.clarifications_left(SYMPTOM) == MAX_CLARIFICATION_ATTEMPTS
    with pytest.raises(EngineError):
        engine.clarifications_left("oyku.yok")


def test_the_origin_of_a_re_entry_is_its_step() -> None:
    engine = _asked_duration({DURATION: 1})
    engine.apply_extraction(DURATION, {}, clarification_needed=True)
    assert engine.origin_of(f"{DURATION}/clarify/1") == DURATION
    assert engine.origin_of(DURATION) == DURATION
    with pytest.raises(EngineError):
        engine.origin_of("oyku.yok/clarify/1")


# --- 2 · closing an asked, unanswered step --------------------------------------------


def test_closing_an_asked_unanswered_step_records_unclear_and_its_gap() -> None:
    engine = _asked_duration()
    version = engine.snapshot.version
    revision = engine.slot_revision(DURATION)
    engine.close_unanswered(DURATION)
    assert engine.state_of(DURATION) is AnswerState.UNCLEAR
    assert engine.data_gaps == (DURATION,)
    assert engine.value_of(DURATION) is None
    assert engine.snapshot.version == version + 1
    assert engine.slot_revision(DURATION) == revision + 1
    assert DURATION not in engine.snapshot.awaiting


def test_closing_mid_clarification_drops_the_pending_follow_up() -> None:
    engine = _asked_duration({DURATION: 1})
    engine.apply_extraction(DURATION, {}, clarification_needed=True)
    engine.mark_asked(f"{DURATION}/clarify/1")
    engine.close_unanswered(DURATION)
    assert engine.follow_ups == ()
    assert engine.state_of(DURATION) is AnswerState.UNCLEAR
    # a late answer to the dropped follow-up cannot bind
    with pytest.raises(EngineError):
        engine.apply_extraction(f"{DURATION}/clarify/1", {DURATION: 3})
    engine.apply_extraction(DURATION, {DURATION: 3})
    assert engine.state_of(DURATION) is AnswerState.UNCLEAR


@pytest.mark.parametrize(
    ("setup", "state"),
    [
        pytest.param("never-asked", AnswerState.NOT_ASKED, id="never-asked"),
        pytest.param("answered", AnswerState.ASKED_PRESENT, id="answered"),
        pytest.param("unclear", AnswerState.UNCLEAR, id="already-unclear"),
    ],
)
def test_near_miss_only_an_asked_unanswered_step_can_be_closed(
    setup: str, state: AnswerState
) -> None:
    """Nothing binds to a question that was not asked (files/13 §9.6), and an
    answer the patient gave is not overwritten by the session ending."""
    engine = _engine()
    if setup != "never-asked":
        engine.mark_asked(SYMPTOM)
        engine.apply_extraction(
            SYMPTOM, {SYMPTOM: True} if setup == "answered" else {}, setup == "unclear"
        )
        if setup == "unclear":
            for attempt in (1, 2):
                engine.mark_asked(f"{SYMPTOM}/clarify/{attempt}")
                engine.apply_extraction(f"{SYMPTOM}/clarify/{attempt}", {}, True)
    assert engine.state_of(SYMPTOM) is state
    with pytest.raises(EngineError):
        engine.close_unanswered(SYMPTOM)
    assert engine.state_of(SYMPTOM) is state
