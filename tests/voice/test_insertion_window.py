"""INT-091 — Backend speech only at a safe insertion window (invariant 9 clause 3).

files/03 §4.3: *"``speech_tr`` is semantic material, not a script: the Talker
adapts it and speaks it only at a **safe duplex insertion window** (patient
silent ≥ 300 ms, Talker idle, no pending response). If the patient interrupts
or speaks, delivery waits and retries; injection is idempotent on ``work_id``
(never duplicated)."*

files/12 §6 replaces the unbounded wait with the four-stage ladder, because
*"RT-07 only ever asserted that YELLOW does not preempt, never that it is ever
spoken"* — and under ask-ahead *"no pending response"* is rarely true, so an
anxious patient could hold a YELLOW open forever. `TRIAGE_YELLOW` uses
20 / 45 / 90 s; the expiry of a protected class is transactional with its note
flag, and if the note write fails the item stays PENDING.
"""

from __future__ import annotations

import pytest
from clinical_schemas.triage import RuleFire, RulesTriageResult, TriageLevel
from intake_voice_runtime.talker.insertion import (
    YELLOW_DEADLINES,
    DeadlinesNotConfiguredError,
    DeliveryClass,
    DeliveryDeadlines,
    DeliveryStage,
    DuplexState,
    Expire,
    Hold,
    InsertionScheduler,
    NoteFlagFailed,
    PendingSpeech,
    Speak,
)
from intake_voice_runtime.talker.preemption import InlinePayload, Presentation

TALKING = DuplexState(patient_silence_ms=0.0, talker_idle=False, pending_response=True)
NATURAL = DuplexState(patient_silence_ms=400.0, talker_idle=True, pending_response=False)
RELAXED = DuplexState(patient_silence_ms=200.0, talker_idle=True, pending_response=True)
SENTENCE_BOUNDARY = DuplexState(
    patient_silence_ms=0.0, talker_idle=False, pending_response=True, at_sentence_boundary=True
)


def _yellow(work_id: str = "w1", speech: str = "Bunu hekiminiz görecek.") -> PendingSpeech:
    return PendingSpeech(
        work_id=work_id,
        delivery_class=DeliveryClass.TRIAGE_YELLOW,
        presentation=Presentation(
            speech_tr=speech,
            triage_update=RulesTriageResult(
                level=TriageLevel.YELLOW,
                rules=(RuleFire(id="rf.kanama", evidence="kanama=evet"),),
            ),
        ),
    )


class _RecordingNoteFlag:
    """Stands in for the transactional note write of files/12 §6."""

    def __init__(self) -> None:
        self.flagged: list[str] = []

    def __call__(self, work_id: str) -> None:
        self.flagged.append(work_id)


def _scheduler() -> InsertionScheduler:
    return InsertionScheduler(
        deadlines=DeliveryDeadlines(triage_yellow=YELLOW_DEADLINES),
        note_flag=_RecordingNoteFlag(),
    )


# --- the deadline table --------------------------------------------------------------


def test_the_yellow_deadlines_are_the_blueprint_numbers() -> None:
    assert YELLOW_DEADLINES.soft_ms == 20_000.0
    assert YELLOW_DEADLINES.hard_ms == 45_000.0
    assert YELLOW_DEADLINES.terminal_ms == 90_000.0


def test_a_class_without_a_configured_deadline_is_refused() -> None:
    """CLAUDE.md: never invent a value. files/12 §6 states 20/45/90 for
    TRIAGE_YELLOW and nothing for the other classes, so scheduling one
    without configuration fails closed rather than guessing a window."""
    scheduler = _scheduler()
    item = PendingSpeech(
        work_id="w9",
        delivery_class=DeliveryClass.CLINICAL_INFO,
        presentation=Presentation(speech_tr="Belgeniz okundu."),
    )
    with pytest.raises(DeadlinesNotConfiguredError, match="clinical_info"):
        scheduler.enqueue(item, now_ms=0.0)


# --- the window predicate ------------------------------------------------------------


def test_speech_is_held_while_the_patient_is_talking() -> None:
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    decisions = scheduler.tick(TALKING, now_ms=0.0)
    assert [type(d) for d in decisions] == [Hold]
    assert decisions[0].stage is DeliveryStage.NATURAL


def test_speech_lands_at_the_natural_window() -> None:
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    scheduler.tick(TALKING, now_ms=0.0)
    decisions = scheduler.tick(NATURAL, now_ms=1_000.0)
    assert [type(d) for d in decisions] == [Speak]
    assert decisions[0].stage is DeliveryStage.NATURAL
    assert decisions[0].item.work_id == "w1"


@pytest.mark.parametrize("silence_ms", [0.0, 150.0, 299.0])
def test_the_natural_window_needs_three_hundred_milliseconds_of_silence(
    silence_ms: float,
) -> None:
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    state = DuplexState(patient_silence_ms=silence_ms, talker_idle=True, pending_response=False)
    assert [type(d) for d in scheduler.tick(state, now_ms=0.0)] == [Hold]


def test_the_natural_window_needs_the_talker_idle() -> None:
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    state = DuplexState(patient_silence_ms=900.0, talker_idle=False, pending_response=False)
    assert [type(d) for d in scheduler.tick(state, now_ms=0.0)] == [Hold]


# --- the ladder ----------------------------------------------------------------------


def test_relaxed_drops_the_no_pending_response_conjunct() -> None:
    """files/12 §6: under ask-ahead 'no pending response' is rarely true."""
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    assert [type(d) for d in scheduler.tick(RELAXED, now_ms=0.0)] == [Hold]
    decisions = scheduler.tick(RELAXED, now_ms=25_000.0)
    assert [type(d) for d in decisions] == [Speak]
    assert decisions[0].stage is DeliveryStage.RELAXED


def test_interject_takes_the_next_sentence_boundary_and_prefixes_a_clip() -> None:
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    assert [type(d) for d in scheduler.tick(TALKING, now_ms=50_000.0)] == [Hold]
    decisions = scheduler.tick(SENTENCE_BOUNDARY, now_ms=50_000.0)
    assert [type(d) for d in decisions] == [Speak]
    assert decisions[0].stage is DeliveryStage.INTERJECT
    assert decisions[0].cancel_non_red_playback is True
    assert decisions[0].polite_interject is True


def test_a_yellow_the_patient_never_yields_to_expires_with_a_note_flag() -> None:
    """files/12 §9 invariant 17: every YELLOW terminates in SPEAK or EXPIRED,
    after walking the ladder. RT-07 with a patient who talks for 200 s."""
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    for now_ms in range(0, 200_000, 100):
        decisions = scheduler.tick(TALKING, now_ms=float(now_ms))
        if decisions and isinstance(decisions[0], Expire):
            assert now_ms >= YELLOW_DEADLINES.terminal_ms
            assert scheduler.note_flag.flagged == ["w1"]
            return
    raise AssertionError("a YELLOW walked past its terminal deadline without expiring")


def test_expiry_rolls_back_and_stays_pending_when_the_note_write_fails() -> None:
    """files/12 §6: the note write comes first, inside the same transaction —
    'if it fails, the transaction rolls back and the item stays PENDING'."""
    attempts: list[str] = []

    def failing_note(work_id: str) -> None:
        attempts.append(work_id)
        raise NoteFlagFailed(work_id)

    scheduler = InsertionScheduler(
        deadlines=DeliveryDeadlines(triage_yellow=YELLOW_DEADLINES), note_flag=failing_note
    )
    scheduler.enqueue(_yellow(), now_ms=0.0)
    decisions = scheduler.tick(TALKING, now_ms=95_000.0)
    assert [type(d) for d in decisions] == [Hold]
    assert attempts == ["w1"]
    assert scheduler.pending_work_ids == ("w1",)


def test_a_protected_class_never_expires_silently() -> None:
    assert DeliveryClass.TRIAGE_YELLOW in DeliveryClass.protected()
    assert DeliveryClass.RED in DeliveryClass.protected()
    assert DeliveryClass.CLINICAL_INFO in DeliveryClass.protected()
    assert DeliveryClass.ROUTINE not in DeliveryClass.protected()


# --- idempotency ----------------------------------------------------------------------


def test_delivery_is_idempotent_on_work_id() -> None:
    """files/03 §4.6 invariant 6: insertion-window retries never duplicate."""
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    scheduler.enqueue(_yellow(), now_ms=0.0)  # a retry of the same work
    first = scheduler.tick(NATURAL, now_ms=1_000.0)
    second = scheduler.tick(NATURAL, now_ms=2_000.0)
    assert [type(d) for d in first] == [Speak]
    assert second == ()
    assert scheduler.delivered_work_ids == ("w1",)


def test_re_enqueueing_a_delivered_work_id_is_a_no_op() -> None:
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    scheduler.tick(NATURAL, now_ms=1_000.0)
    scheduler.enqueue(_yellow(), now_ms=0.0)
    assert scheduler.tick(NATURAL, now_ms=3_000.0) == ()


def test_two_distinct_works_both_get_delivered_in_order() -> None:
    scheduler = _scheduler()
    scheduler.enqueue(_yellow("w1"), now_ms=0.0)
    scheduler.enqueue(_yellow("w2"), now_ms=0.0)
    decisions = scheduler.tick(NATURAL, now_ms=1_000.0)
    assert [d.item.work_id for d in decisions] == ["w1"]
    assert [d.item.work_id for d in scheduler.tick(NATURAL, now_ms=2_000.0)] == ["w2"]


# --- invariant 22: numbers never cross a boundary unguarded ---------------------------


def test_a_spoken_numeric_slot_value_requires_an_inline_render() -> None:
    """CLAUDE.md invariant 22 / files/03 §4.6 invariant 30: no numeric slot
    value is spoken without a matching `inline` render on the same work_id."""
    with pytest.raises(ValueError, match="inline"):
        Presentation(
            speech_tr="Tahlilinizde hemoglobin on virgül iki görünüyor.",
            speech_numerics=("hemoglobin",),
        )


def test_the_inline_render_on_the_same_work_id_satisfies_it() -> None:
    presentation = Presentation(
        speech_tr="Tahlilinizde hemoglobin on virgül iki görünüyor.",
        speech_numerics=("hemoglobin",),
        inline=InlinePayload(numeric_values={"hemoglobin": "10,2 g/dL"}),
    )
    assert presentation.speech_numerics == ("hemoglobin",)


def test_an_inline_render_of_a_different_slot_does_not_satisfy_it() -> None:
    with pytest.raises(ValueError, match="hemoglobin"):
        Presentation(
            speech_tr="Tahlilinizde hemoglobin on virgül iki görünüyor.",
            speech_numerics=("hemoglobin",),
            inline=InlinePayload(numeric_values={"kreatinin": "0,9 mg/dL"}),
        )


# --- the catalogued metric -------------------------------------------------------------


def test_the_insertion_wait_is_observed() -> None:
    from intake_voice_runtime.metrics import DELIVERY_INSERTION_WAIT_MS

    before = DELIVERY_INSERTION_WAIT_MS._sum.get()
    scheduler = _scheduler()
    scheduler.enqueue(_yellow(), now_ms=0.0)
    scheduler.tick(TALKING, now_ms=0.0)
    scheduler.tick(NATURAL, now_ms=1_500.0)
    assert DELIVERY_INSERTION_WAIT_MS._sum.get() == pytest.approx(before + 1_500.0)
