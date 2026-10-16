"""INT-546 — the onset anchor by cause: a hedge resolves at once, and the close reaches it.

GitHub #925 applies INT-519's verified D18 decisions (CD-04 round 3, CD-05
round 3) to the INT-540 runtime, on both profiles, over the committed
``base.intake`` and the committed active ``base.life_threat`` rules:

1. **Item 5.** The anchor's follow-up bound is CD-04's
   ``tense_anchor_follow_up_tr_asks``, by cause: a hedge (a CD-04 entry read
   on the anchor, alone or beside a choice) takes no follow-up — the anchor is
   UNCLEAR on that Work, CD-05 resolves it to the reference day, the rules
   engine evaluates that Work, and K2 fires through the existing RED path. The
   near miss: an answer that binds no choice keeps its one follow-up.
2. **Item 8.** A hedge beside a choice keeps the leaned-to choice on the
   record as ``hedged_choice`` and never binds it: the resolved day is the
   reference day, not the band the patient leaned to.
3. **Item 9.** A plain 'yok' to the onset question is UNCLEAR with cause
   no_choice — never ASKED_ABSENT — and never retracts ``chest_pain.present``;
   the near miss is 'yok' to ``chest_pain.present`` itself, ASKED_ABSENT.
4. **Item 10.** An anchor never asked when the session closes, while
   ``chest_pain.present`` reads true (the anchor's own gate is open), stays
   NOT_ASKED and nothing is bound; the rules engine evaluates it once at close
   as the reference day (``never_asked_at_close``). The near miss is
   ``chest_pain.present = hayır``: the gate is shut, nothing is evaluated.
5. **Item 11.** Asked and never answered at close: the record carries the
   ``session_closed`` label.
6. Every unresolved anchor is handed, once, to the hook INT-547's CD-08
   ``chest_pain_arms_unresolved`` item plugs into
   (:class:`~intake_voice_runtime.clinical_agent.anchors.AnchorUnresolvedHook`),
   with the label of its cause; a session composed without one still keeps
   the record. The item itself is INT-547's, not built here.

The gateway is a table keyed by what the patient said; nothing dials a model.
The transcripts are synthetic (files/04 §7).
"""

from __future__ import annotations

import copy
from collections.abc import Mapping

import pytest
import test_anchor_unclear as int540
import test_onset_anchor as int522
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation
from intake_voice_runtime.clinical_agent.anchors import (
    AnchorUnresolved,
    UnclearCause,
)
from intake_voice_runtime.profiles import VoiceProfile
from protocols.anchor_choices import AnchorBasis
from protocols.answer_states import AnswerStateTable, answer_state_table
from protocols.clinical_decisions import REGISTER_DIR, load_decision

K2 = int522.K2
ONSET = int522.ONSET
PRESENT = int522.PRESENT
SUBJECT = int522.SUBJECT
CHARACTER = int522.CHARACTER
RADIATION = int522.RADIATION
OLDER = int522.OLDER
KIND = "chest_pain_arms_unresolved"
BY_CD04 = ("CD-04", "CD-08")
BY_CD05 = ("CD-05", "CD-08")

#: Hedges to the onset question: (said, the model's onset value, its flag).
HEDGES: Mapping[str, tuple[str, JsonValue | None, bool]] = {
    "bilmiyorum-no-slot-no-flag": ("Bilmiyorum.", None, False),
    "emin-degilim-flagged": ("Emin değilim.", None, True),
    "hedge-beside-a-guessed-choice": ("Emin değilim, galiba üç günden önceydi.", OLDER, False),
}
#: Answers that bind no choice and that no CD-04 entry reads.
NO_CHOICE: Mapping[str, tuple[str, bool]] = {
    "narrative-flagged": ("Dün akşam olmuştu.", True),
    "plain-yok": ("Yok.", False),
    "plain-olmadi": ("Olmadı.", False),
}
STILL_UNFIT = int540.STILL_UNFIT


class RecordingHook:
    """Stands where INT-547's CD-08 item plugs in; records what it is handed."""

    def __init__(self) -> None:
        self.triggers: list[AnchorUnresolved] = []

    def anchor_unresolved(self, trigger: AnchorUnresolved) -> None:
        self.triggers.append(trigger)


def _model(
    character: str = "baskı",
    lines: Mapping[str, Mapping[str, JsonValue]] | None = None,
    clarify: tuple[str, ...] = (),
) -> int522.SpokenModel:
    by_line: dict[str, Mapping[str, JsonValue]] = {
        STILL_UNFIT: {},
        int522.SAID_ONSET[OLDER]: {ONSET: OLDER},
    }
    for said, value, _ in HEDGES.values():
        by_line[said] = {} if value is None else {ONSET: value}
    for said, _ in NO_CHOICE.values():
        by_line[said] = {}
    by_line.update(lines or {})
    flagged = tuple(s for s, _, f in HEDGES.values() if f) + tuple(
        s for s, f in NO_CHOICE.values() if f
    )
    return int522._model(character, "yok", extra=by_line, clarify=flagged + clarify)


def _rig(
    profile: VoiceProfile,
    model: int522.SpokenModel,
    *,
    location: RedLocation = RedLocation.REMOTE,
    answer_states: AnswerStateTable | None = None,
) -> tuple[int522.Rig, RecordingHook]:
    hook = RecordingHook()
    rig = int522._rig(
        profile, model, location=location, answer_states=answer_states, anchor_unresolved=hook
    )
    return rig, hook


def _trigger(label: str, decisions: tuple[str, ...] = BY_CD04) -> AnchorUnresolved:
    return AnchorUnresolved(anchor=ONSET, label=label, kind=KIND, decision_ids=decisions)


def _assert_resolved(rig: int522.Rig, label: str, hedged_choice: str | None = None) -> None:
    engine = rig.stack.engine
    assert engine.state_of(ONSET) is AnswerState.UNCLEAR
    assert engine.value_of(ONSET) is None  # nothing is bound to the slot
    assert rig.anchors is not None
    resolution = rig.anchors.record[ONSET]
    assert (resolution.basis, resolution.label, resolution.choice_tr) == (
        AnchorBasis.UNRESOLVED,
        label,
        None,
    )
    assert resolution.resolved_on == int522._day(0)
    assert resolution.hedged_choice == hedged_choice


# --- 1 · item 5: a hedge resolves at once; no choice keeps its one follow-up -------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
@pytest.mark.parametrize("hedge", list(HEDGES))
def test_anchor_hedge_resolves_at_once(
    profile: VoiceProfile, location: RedLocation, hedge: str
) -> None:
    """No follow-up for a hedge: the Work that read it is the one evaluated,
    and K2 reaches the clinic at its register and the session's location."""
    rig, hook = _rig(profile, _model(), location=location)
    int522._lead(rig)
    work_id = int522._say(rig, ONSET, HEDGES[hedge][0])
    assert [s for s in rig.stack.engine.follow_ups if s.startswith(ONSET)] == []
    leaned = OLDER if HEDGES[hedge][1] is not None else None
    _assert_resolved(rig, UnclearCause.HEDGE.value, hedged_choice=leaned)
    assert rig.triage.evaluated[-1] == work_id
    int540._assert_k2_reached_the_clinic(rig, work_id, location)
    assert rig.anchors is not None
    assert rig.anchors.unresolved_triggers == [_trigger("hedge")] == hook.triggers


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("answer", list(NO_CHOICE))
def test_near_miss_a_no_choice_answer_keeps_its_one_follow_up(
    profile: VoiceProfile, answer: str
) -> None:
    rig, hook = _rig(profile, _model())
    int522._lead(rig)
    first = int522._say(rig, ONSET, NO_CHOICE[answer][0])
    int540._assert_the_follow_up_is_queued_once(rig)
    assert first not in rig.triage.evaluated
    assert hook.triggers == [] and rig.clinic.notifications == []
    last = int522._say(rig, int522._reentry(rig), STILL_UNFIT)
    _assert_resolved(rig, UnclearCause.NO_CHOICE.value)
    int540._assert_k2_reached_the_clinic(rig, last, RedLocation.REMOTE)
    assert hook.triggers == [_trigger("no_choice")]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_hedge_to_the_follow_up_resolves_on_that_answer(profile: VoiceProfile) -> None:
    """A no-choice answer used the follow-up; a hedge to it resolves there,
    labelled by the cause that resolved it."""
    rig, hook = _rig(profile, _model())
    int522._lead(rig)
    int522._say(rig, ONSET, NO_CHOICE["plain-yok"][0])
    last = int522._say(rig, int522._reentry(rig), "Bilmiyorum.")
    _assert_resolved(rig, UnclearCause.HEDGE.value)
    int540._assert_k2_reached_the_clinic(rig, last, RedLocation.REMOTE)
    assert hook.triggers == [_trigger("hedge")]


def _with_cause_bounds(hedge: int, no_choice: int) -> AnswerStateTable:
    decision = load_decision(REGISTER_DIR / "CD-04.yaml")
    value = copy.deepcopy(decision.value)
    value["tense_anchor_follow_up_tr_asks"] = {"hedge": hedge, "no_choice": no_choice}
    return answer_state_table(decision.model_copy(update={"value": value}))


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_bound_is_the_decisions_by_cause_so_an_amendment_changes_data(
    profile: VoiceProfile,
) -> None:
    """A CD-04 that gave a hedge one follow-up and a no-choice answer none would
    run that way with no code change: the runtime reads the per-cause key."""
    rig, _ = _rig(profile, _model(), answer_states=_with_cause_bounds(1, 0))
    int522._lead(rig)
    int522._say(rig, ONSET, "Bilmiyorum.")
    int540._assert_the_follow_up_is_queued_once(rig)
    rig, _ = _rig(profile, _model(), answer_states=_with_cause_bounds(1, 0))
    int522._lead(rig)
    int522._say(rig, ONSET, NO_CHOICE["plain-yok"][0])
    _assert_resolved(rig, UnclearCause.NO_CHOICE.value)


def test_the_engine_ceiling_for_the_anchor_is_the_larger_cause_bound() -> None:
    for profile in VoiceProfile:
        rig, _ = _rig(profile, _model())
        assert rig.stack.engine.clarification_bound(ONSET) == 1
        assert rig.anchors is not None
        assert rig.anchors.follow_up_bound(UnclearCause.HEDGE) == 0
        assert rig.anchors.follow_up_bound(UnclearCause.NO_CHOICE) == 1


# --- 2 · item 8: the leaned-to choice is kept, never bound --------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_hedged_choice_is_kept_not_bound(profile: VoiceProfile) -> None:
    said = HEDGES["hedge-beside-a-guessed-choice"][0]
    rig, _ = _rig(profile, _model())
    int522._lead(rig)
    int522._say(rig, ONSET, said)
    _assert_resolved(rig, "hedge", hedged_choice=OLDER)
    assert rig.anchors is not None
    [reading] = rig.anchors.unclear
    shown = f"{reading!r} {reading} {rig.anchors.record[ONSET]!r}"
    assert OLDER not in shown  # invariant 6: ids and labels only


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_same_band_said_plainly_binds_its_own_day_and_stays_quiet(
    profile: VoiceProfile,
) -> None:
    rig, hook = _rig(profile, _model())
    int522._lead(rig)
    int522._say(rig, ONSET, int522.SAID_ONSET[OLDER])
    assert rig.stack.engine.value_of(ONSET) == int522._day(3)
    assert rig.anchors is not None
    resolution = rig.anchors.record[ONSET]
    assert (resolution.basis, resolution.hedged_choice, resolution.label) == (
        AnchorBasis.DECIDED,
        None,
        None,
    )
    assert rig.clinic.notifications == [] and hook.triggers == []


# --- 3 · item 9: a plain 'yok' to the onset question is not absent ---------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_plain_negative_to_onset_is_not_absent(profile: VoiceProfile) -> None:
    rig, _ = _rig(profile, _model())
    int522._lead(rig)
    int522._say(rig, ONSET, "Yok.")
    engine = rig.stack.engine
    assert engine.state_of(ONSET) is AnswerState.ASKED_PENDING  # its one follow-up
    assert rig.anchors is not None
    assert [(u.anchor, u.cause) for u in rig.anchors.unclear] == [(ONSET, UnclearCause.NO_CHOICE)]
    # it never retracts the affirmed pain
    assert (engine.state_of(PRESENT), engine.value_of(PRESENT)) == (AnswerState.ASKED_PRESENT, True)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_yok_to_chest_pain_present_is_absent(profile: VoiceProfile) -> None:
    rig, _ = _rig(profile, _model(lines={"Yok.": {PRESENT: False}}))
    int522._say(rig, SUBJECT, int522.SAID[SUBJECT])
    int522._say(rig, PRESENT, "Yok.")
    engine = rig.stack.engine
    assert engine.state_of(PRESENT) is AnswerState.ASKED_ABSENT
    assert engine.gate_open(ONSET) is False


# --- 4 · item 10: never asked at close, with chest pain affirmed -------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
def test_never_asked_anchor_evaluated_at_close(
    profile: VoiceProfile, location: RedLocation
) -> None:
    """The session ends between the chest-pain answers and the onset question.
    The anchor stays NOT_ASKED and nothing binds; the close is evaluated with
    it read as the reference day, and K2 reaches the clinic by the path every
    RED takes."""
    rig, hook = _rig(profile, _model(), location=location)
    int522._lead(rig)
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    engine = rig.stack.engine
    assert engine.state_of(ONSET) is AnswerState.NOT_ASKED  # "Sorulmadı"
    assert engine.value_of(ONSET) is None and ONSET not in engine.data_gaps
    assert rig.anchors is not None
    resolution = rig.anchors.record[ONSET]
    assert (resolution.basis, resolution.label, resolution.choice_tr) == (
        AnchorBasis.NEVER_ASKED_AT_CLOSE,
        "never_asked_at_close",
        None,
    )
    assert resolution.resolved_on == int522._day(0)
    assert rig.triage.evaluated[-1] == ticket.work_id
    int540._assert_k2_reached_the_clinic(rig, ticket.work_id, location)
    assert hook.triggers == [_trigger("never_asked_at_close", BY_CD05)]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_chest_pain_denied_the_never_asked_anchor_is_not_evaluated(
    profile: VoiceProfile,
) -> None:
    """``chest_pain.present = hayır``: the anchor's gate is shut, so the close
    reads nothing into it, records nothing, raises nothing, and nothing fires."""
    rig, hook = _rig(profile, _model(lines={"Hayır, yok.": {PRESENT: False}}))
    int522._say(rig, SUBJECT, int522.SAID[SUBJECT])
    int522._say(rig, PRESENT, "Hayır, yok.")
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    assert rig.stack.engine.state_of(ONSET) is AnswerState.NOT_ASKED
    assert rig.anchors is not None and rig.anchors.record == {}
    assert ONSET not in rig.triage.context(rig.stack.engine).answers
    assert ticket.work_id not in rig.triage.evaluated
    assert hook.triggers == [] and rig.clinic.notifications == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_chest_pain_never_answered_the_anchor_is_not_evaluated(
    profile: VoiceProfile,
) -> None:
    """``chest_pain.present`` unanswered reads Unknown: CD-05 applies only when
    it reads true, and CD-04's own trigger covers an UNCLEAR present."""
    rig, hook = _rig(profile, _model())
    int522._say(rig, SUBJECT, int522.SAID[SUBJECT])
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    assert rig.anchors is not None and rig.anchors.record == {}
    assert hook.triggers == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_never_asked_anchor_with_a_non_cardiac_answer_is_evaluated_and_stays_quiet(
    profile: VoiceProfile,
) -> None:
    """The reading dates the anchor; it does not open K2's gate."""
    rig, hook = _rig(profile, _model(character="başka bir his"))
    int522._lead(rig)
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    assert rig.anchors is not None
    assert rig.anchors.record[ONSET].basis is AnchorBasis.NEVER_ASKED_AT_CLOSE
    assert rig.clinic.notifications == [] and rig.stack.agent.sealed is False
    assert hook.triggers == [_trigger("never_asked_at_close", BY_CD05)]


# --- 5 · item 11: asked, never answered at close ------------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_asked_unanswered_at_close_carries_the_session_closed_label(profile: VoiceProfile) -> None:
    rig, hook = _rig(profile, _model())
    int522._lead(rig)
    rig.stack.session.ask_ledger.note_asked(ONSET)
    rig.stack.agent.run_pending()
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    _assert_resolved(rig, UnclearCause.SESSION_CLOSED.value)
    int540._assert_k2_reached_the_clinic(rig, ticket.work_id, RedLocation.REMOTE)
    assert hook.triggers == [_trigger("session_closed")]


# --- 6 · the hook --------------------------------------------------------------------------


def test_both_roots_hand_the_hook_to_the_session_anchors() -> None:
    for profile in VoiceProfile:
        rig, hook = _rig(profile, _model())
        assert rig.anchors is not None and rig.anchors.hook is hook


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_without_a_hook_the_record_is_still_kept(profile: VoiceProfile) -> None:
    rig = int522._rig(profile, _model())
    int522._lead(rig)
    int522._say(rig, ONSET, "Bilmiyorum.")
    assert rig.anchors is not None and rig.anchors.hook is None
    assert rig.anchors.unresolved_triggers == [_trigger("hedge")]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_an_anchor_is_handed_to_the_hook_once(profile: VoiceProfile) -> None:
    """Resolved by a hedge, then the session closes: the close finds nothing
    pending and nothing never-asked, so nothing is raised twice."""
    rig, hook = _rig(profile, _model(character="başka bir his"))
    int522._lead(rig)
    int522._say(rig, ONSET, "Bilmiyorum.")
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    assert hook.triggers == [_trigger("hedge")]


def test_a_trigger_names_ids_and_labels_only() -> None:
    trigger = _trigger("hedge")
    shown = f"{trigger!r} {trigger}"
    assert ONSET in shown and "hedge" in shown and KIND in shown
