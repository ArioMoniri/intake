"""INT-540 — the onset anchor always resolves, so K2 cannot stay silent.

GitHub #913, from the INT-522 clinical review (#888), findings F1 and F2.
``chest_pain.onset_at`` is the tense anchor of ``rf.chest_pain_cardiac_features``
(KIRMIZI_K2) and its SARI sibling. After INT-522 a closed choice bound its
CD-05 day — but an answer that fitted no choice could leave the anchor
``ASKED_PENDING`` for the whole session:

- **F1.** The extraction instructions never said when to set
  ``clarification_needed``. For 'bilmiyorum' or a narrative the model could
  return no slot and no flag; the engine binds nothing and queues nothing on
  that, so the anchor stayed pending, read Unknown, and K2 never fired. The
  same if the session was abandoned between the first 'bilmiyorum' and the
  last answer.
- **F2.** CD-04 (active, verified) makes 'bilmiyorum' / 'emin değilim' UNCLEAR
  at once and asks the slot's ``follow_up_tr`` once; for a tense anchor CD-05
  resolves the UNCLEAR to the reference day. The build waited for the
  engine's generic two follow-ups, and trusted a model that guessed a choice
  over the patient's hedge.

What this suite holds, on both profiles, over the committed ``base.intake``
and the committed active ``base.life_threat`` rules:

1. For the asked anchor, a CD-04 hedge (read from the decision, beating a
   choice the model guessed), an off-choice narrative ('dün akşam'), and a
   completion with no slot and no flag are each UNCLEAR at once. Since INT-546
   (CD-04 round 3, INT-519 item 5) the bound is per cause: a hedge takes no
   follow-up and resolves on the Work that read it; an answer that bound no
   choice has the scripted ``follow_up_tr`` asked verbatim, once, and reads
   Unknown meanwhile. An answer to it that is still unfit records UNCLEAR,
   CD-05 resolves the anchor to the reference day, the rules engine evaluates
   that Work, and K2 fires at its register and the session's location through
   the existing RED path (invariants 1, 9, 21).
2. The bound is CD-04's ``tense_anchor_follow_up_tr_asks``, read from the
   decision by cause: a table that says 0 or 2 changes the session with no
   code change (INT-546; ``tests/voice/test_int546_anchor_causes.py`` holds the
   per-cause cases).
3. A pending anchor cannot outlive the session. Closing the session — from
   the router's ``end`` or directly — queues one state-lane Work behind the
   patient's last answers; an anchor still asked and unanswered (mid-
   clarification included) is recorded UNCLEAR, resolved by CD-05, evaluated
   by the rules engine alone, and a RED reaches the clinic and the device by
   the path every other RED takes.
4. Near misses: a choice answered on the follow-up binds its own day ('üç
   günden daha önce' stays quiet, even when it is the last thing said before
   the session closes); an unclear onset with a non-cardiac answer resolves
   and stays quiet; a hedge to a slot that is not an anchor resolves to no
   date and is not closed. (An anchor never asked when the session closes is
   INT-546's ``never_asked_anchor_evaluated_at_close``.)

The gateway is a table keyed by what the patient said; nothing dials a model.
The clock is the harness's fake one; the reference time is injected at
composition. The transcripts are synthetic (files/04 §7).
"""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Mapping

import pytest
import test_live_triage as int521
import test_onset_anchor as int522
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, TriageLevel
from intake_platform.voice_control import TenantVoiceControl, VoiceControlUnavailable
from intake_voice_runtime.clinical_agent.anchors import SessionAnchors, UnclearCause
from intake_voice_runtime.composition import protocol_slots
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.ports import WorkState, WorkType
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.session_router import VoiceSessionRouter
from intake_voice_runtime.talker.session import TurnHold
from protocols.anchor_choices import AnchorBasis, load_anchor_choice_table
from protocols.answer_states import AnswerStateTable, answer_state_table, load_answer_state_table
from protocols.clinical_decisions import REGISTER_DIR, load_decision
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.triage import evaluate_triage
from session_harness import builders
from talker_harness import FakeClock

K2 = int522.K2
ONSET = int522.ONSET
CHARACTER = int522.CHARACTER
OLDER = int522.OLDER
NOW_CHOICE = int522.NOW_CHOICE
FREE_DATE = "hpi.onset_date"

#: Answers to the onset question that fit no authored choice, as the patient
#: says them, with how the model reads each: what it records for the anchor
#: (``None`` = nothing) and whether it sets ``clarification_needed``.
UNFIT: Mapping[str, tuple[str, JsonValue | None, bool, UnclearCause, str | None]] = {
    # id: (said, the model's onset value, its flag, the cause recorded, CD-04 qualifier)
    "bilmiyorum-no-slot-no-flag": ("Bilmiyorum.", None, False, UnclearCause.HEDGE, "unknown"),
    "emin-degilim-model-guessed-a-choice": (
        "Emin değilim, galiba üç günden önceydi.",
        OLDER,
        False,
        UnclearCause.HEDGE,
        "unsure",
    ),
    "dun-aksam-narrative-flagged": (
        "Dün akşam olmuştu.",
        None,
        True,
        UnclearCause.NO_CHOICE,
        None,
    ),
    "no-slot-no-flag": ("Hı hı, işte öyle.", None, False, UnclearCause.NO_CHOICE, None),
}
#: INT-546 (CD-04 round 3): a hedge resolves at once; only these keep a follow-up.
NO_CHOICE_UNFIT = tuple(key for key, row in UNFIT.items() if row[3] is UnclearCause.NO_CHOICE)
HEDGE_UNFIT = tuple(key for key, row in UNFIT.items() if row[3] is UnclearCause.HEDGE)
#: The answer to the follow-up that is still unfit: a hedge CD-04 does not
#: list, which the model leaves unrecorded and unflagged (CD-04: an unmatched
#: hedge is UNCLEAR; CD-05: an answer fitting no choice).
STILL_UNFIT = "Hatırlamıyorum ki."
SAID_OLDER = int522.SAID_ONSET[OLDER]


def _model(
    character: str,
    first: str,
    *,
    extra: Mapping[str, Mapping[str, JsonValue]] | None = None,
) -> int522.SpokenModel:
    said, value, flag, _, _ = UNFIT[first]
    lines: dict[str, Mapping[str, JsonValue]] = {
        said: {} if value is None else {ONSET: value},
        STILL_UNFIT: {},
        SAID_OLDER: {ONSET: OLDER},
    }
    lines.update(extra or {})
    return int522._model(character, "yok", extra=lines, clarify=(said,) if flag else ())


def _follow_up_text() -> str:
    slot = protocol_slots(int521._served_protocol())[ONSET]
    assert slot.follow_up_tr is not None
    return slot.follow_up_tr[TR]


def _assert_the_follow_up_is_queued_once(rig: int522.Rig) -> None:
    engine = rig.stack.engine
    assert engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    assert [s for s in engine.follow_ups if s.startswith(ONSET)] == [f"{ONSET}/clarify/1"]
    head = engine.frontier()[0]
    assert (head.step_id, head.text_tr) == (f"{ONSET}/clarify/1", _follow_up_text())


def _assert_k2_reached_the_clinic(rig: int522.Rig, work_id: str, location: RedLocation) -> None:
    assert rig.stack.agent.sealed is True
    assert [(n.work_id, n.rule_ids, n.register, n.location) for n in rig.clinic.notifications] == [
        (work_id, (K2,), RedRegister.ALERT, location)
    ]


def _assert_resolved_unclear(rig: int522.Rig) -> None:
    engine = rig.stack.engine
    assert engine.state_of(ONSET) is AnswerState.UNCLEAR
    assert ONSET in engine.data_gaps
    assert rig.anchors is not None
    resolution = rig.anchors.record[ONSET]
    assert (resolution.choice_tr, resolution.resolved_on, resolution.basis) == (
        None,
        int522._day(0),
        AnchorBasis.UNRESOLVED,
    )


# --- 1 · an unfit answer is UNCLEAR at once; the follow-up is asked once --------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("first", NO_CHOICE_UNFIT)
def test_an_unfit_onset_answer_asks_the_follow_up_once_and_reads_unknown_meanwhile(
    profile: VoiceProfile, first: str
) -> None:
    """CD-04: UNCLEAR reads Unknown and triggers the slot's follow_up_tr once —
    for an answer that bound no choice (CD-04 round 3). Whatever the model did
    with it — nothing, or a flag — the anchor is not left silently pending."""
    said, _, _, cause, qualifier = UNFIT[first]
    rig = int522._rig(profile, _model("baskı", first))
    int522._lead(rig)
    work_id = int522._say(rig, ONSET, said)
    assert rig.stack.agent.record(work_id).state is WorkState.COMPLETED
    _assert_the_follow_up_is_queued_once(rig)
    assert ONSET not in rig.triage.context(rig.stack.engine).answers
    assert work_id not in rig.triage.evaluated
    assert rig.clinic.notifications == [] and rig.stack.agent.sealed is False
    assert rig.anchors is not None and rig.anchors.record == {}
    [unclear] = rig.anchors.unclear
    assert (unclear.anchor, unclear.cause, unclear.qualifier) == (ONSET, cause, qualifier)


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("first", HEDGE_UNFIT)
def test_an_unfit_onset_hedge_resolves_on_the_first_work(profile: VoiceProfile, first: str) -> None:
    """INT-546 (CD-04 round 3, INT-519 item 5): a hedge — alone, or beside a
    choice the model guessed — takes no follow-up. The Work that read it is
    the one evaluated, and with a cardiac character K2 fires on it."""
    said, _, _, cause, qualifier = UNFIT[first]
    rig = int522._rig(profile, _model("baskı", first))
    int522._lead(rig)
    work_id = int522._say(rig, ONSET, said)
    assert [s for s in rig.stack.engine.follow_ups if s.startswith(ONSET)] == []
    _assert_resolved_unclear(rig)
    assert rig.triage.evaluated[-1] == work_id
    _assert_k2_reached_the_clinic(rig, work_id, RedLocation.REMOTE)
    assert rig.anchors is not None
    [unclear] = rig.anchors.unclear
    assert (unclear.anchor, unclear.cause, unclear.qualifier) == (ONSET, cause, qualifier)


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
@pytest.mark.parametrize("first", NO_CHOICE_UNFIT)
def test_still_unfit_after_the_one_follow_up_resolves_and_fires_k2(
    profile: VoiceProfile, location: RedLocation, first: str
) -> None:
    """The follow-up is spent: the anchor is UNCLEAR, CD-05 resolves it to the
    reference day, that Work is evaluated, and with a cardiac character K2
    reaches the clinic and the device at the rule's register and location."""
    said = UNFIT[first][0]
    rig = int522._rig(profile, _model("baskı", first), location=location)
    int522._lead(rig)
    first_work = int522._say(rig, ONSET, said)
    last = int522._say(rig, int522._reentry(rig), STILL_UNFIT)
    _assert_resolved_unclear(rig)
    assert rig.stack.engine.follow_ups == ()
    assert first_work not in rig.triage.evaluated and rig.triage.evaluated[-1] == last
    _assert_k2_reached_the_clinic(rig, last, location)
    outcome = int521._turn(rig, None)
    assert outcome.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert [(m.rule_id, m.location) for m in rig.channel.published] == [(K2, location)]
    assert rig.stack.session.red_stopped is True
    if rig.synthesizer is not None:
        assert rig.synthesizer.requests == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_follow_up_answered_with_an_older_band_binds_it_and_stays_quiet(
    profile: VoiceProfile,
) -> None:
    """The unfit answer does not linger once the patient has answered: 'üç
    günden daha önce' on the follow-up binds the reference day minus three,
    and K2 and its sibling stay quiet."""
    rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"))
    int522._lead(rig)
    int522._say(rig, ONSET, UNFIT["no-slot-no-flag"][0])
    last = int522._say(rig, int522._reentry(rig), SAID_OLDER)
    assert rig.stack.engine.value_of(ONSET) == int522._day(3)
    assert rig.anchors is not None and rig.anchors.record[ONSET].basis is AnchorBasis.DECIDED
    assert rig.triage.evaluated[-1] == last
    int521._turn(rig)
    assert rig.channel.published == [] and rig.clinic.notifications == []


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_an_unclear_onset_with_a_non_cardiac_answer_resolves_and_stays_quiet(
    profile: VoiceProfile,
) -> None:
    """The resolution dates the anchor; it does not open K2's gate."""
    rig = int522._rig(profile, _model("başka bir his", "no-slot-no-flag"))
    int522._lead(rig)
    int522._say(rig, ONSET, UNFIT["no-slot-no-flag"][0])
    last = int522._say(rig, int522._reentry(rig), STILL_UNFIT)
    _assert_resolved_unclear(rig)
    assert rig.triage.evaluated[-1] == last
    assert rig.clinic.notifications == [] and rig.stack.agent.sealed is False


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_hedge_to_a_slot_that_is_not_an_anchor_resolves_to_no_date(
    profile: VoiceProfile,
) -> None:
    """'Bilmiyorum.' to the free complaint-onset date and to the chest-pain
    character: neither is a CD-05 anchor, so neither is resolved to a day,
    neither is recorded, and neither is closed when the session ends."""
    rig = int522._rig(profile, _model("baskı", "bilmiyorum-no-slot-no-flag"))
    int522._say(rig, int522.SUBJECT, int522.SAID[int522.SUBJECT])
    int522._say(rig, int522.PRESENT, int522.SAID[int522.PRESENT])
    int522._say(rig, CHARACTER, "Bilmiyorum.")
    int522._say(rig, FREE_DATE, "Bilmiyorum.")
    engine = rig.stack.engine
    for slot in (CHARACTER, FREE_DATE):
        assert engine.value_of(slot) is None
        assert engine.state_of(slot) is AnswerState.ASKED_PENDING
    assert CHARACTER not in rig.triage.context(engine).answers
    assert rig.anchors is not None and rig.anchors.unclear == [] and rig.anchors.record == {}
    assert rig.stack.close() is not None
    rig.stack.agent.run_pending()
    for slot in (CHARACTER, FREE_DATE):
        assert engine.state_of(slot) is AnswerState.ASKED_PENDING
    # INT-546 (CD-05 round 3 item 10): the onset itself was never asked while
    # chest pain was affirmed, so the close reads it; neither non-anchor is
    assert set(rig.anchors.record) == {ONSET}
    assert rig.anchors.record[ONSET].basis is AnchorBasis.NEVER_ASKED_AT_CLOSE


# --- 2 · the bound is the decision's, so an amendment changes data -------------------


def _with_bound(asks: int) -> AnswerStateTable:
    """CD-04 with both of the anchor's cause bounds set to ``asks`` (INT-546:
    the anchor reads ``tense_anchor_follow_up_tr_asks``, not the decision-wide
    ``unclear_follow_up_tr_asks``)."""
    decision = load_decision(REGISTER_DIR / "CD-04.yaml")
    value = copy.deepcopy(decision.value)
    value["tense_anchor_follow_up_tr_asks"] = {"hedge": asks, "no_choice": asks}
    return answer_state_table(decision.model_copy(update={"value": value}))


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_cd04_table_that_says_zero_resolves_the_first_unfit_answer_at_once(
    profile: VoiceProfile,
) -> None:
    """As data: no follow-up for either cause, so an answer that bound no
    choice resolves the anchor and K2 fires on that Work."""
    rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"))
    rig = _recompose(rig, profile, _with_bound(0))
    int522._lead(rig)
    work_id = int522._say(rig, ONSET, UNFIT["no-slot-no-flag"][0])
    assert rig.stack.engine.follow_ups == ()
    _assert_resolved_unclear(rig)
    _assert_k2_reached_the_clinic(rig, work_id, RedLocation.REMOTE)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_cd04_table_that_says_two_asks_the_follow_up_twice(profile: VoiceProfile) -> None:
    rig = _recompose(
        int522._rig(profile, _model("baskı", "no-slot-no-flag")), profile, _with_bound(2)
    )
    int522._lead(rig)
    int522._say(rig, ONSET, UNFIT["no-slot-no-flag"][0])
    int522._say(rig, int522._reentry(rig), STILL_UNFIT)
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    assert int522._reentry(rig) == f"{ONSET}/clarify/2"
    last = int522._say(rig, int522._reentry(rig), STILL_UNFIT)
    _assert_resolved_unclear(rig)
    _assert_k2_reached_the_clinic(rig, last, RedLocation.REMOTE)


def _recompose(rig: int522.Rig, profile: VoiceProfile, table: AnswerStateTable) -> int522.Rig:
    """The same session composed again with another CD-04 table handed in."""
    model = rig.stack.handler.gateway
    assert isinstance(model, int522.SpokenModel)
    return int522._rig(profile, model, answer_states=table)


def test_the_committed_decision_is_the_table_both_roots_compose_with() -> None:
    for profile in VoiceProfile:
        rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"))
        assert rig.anchors is not None
        assert rig.anchors.answer_states == load_answer_state_table()
        assert rig.stack.engine.clarification_bound(ONSET) == 1
        # every other slot keeps files/13 §11.1's two
        assert rig.stack.engine.clarification_bound(CHARACTER) == 2


# --- 3 · a pending anchor cannot outlive the session ------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
def test_abandoned_mid_clarification_the_anchor_resolves_and_k2_reaches_the_clinic(
    profile: VoiceProfile, location: RedLocation
) -> None:
    """An answer that bound no choice, the follow-up asked, and the patient is
    gone. Closing the
    session records the anchor UNCLEAR, CD-05 resolves it, the rules engine
    evaluates the close, and the RED is handed to the clinician route at once
    — and to the device by its pre-positioned script if it is still there."""
    rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"), location=location)
    int522._lead(rig)
    int522._say(rig, ONSET, UNFIT["no-slot-no-flag"][0])
    rig.stack.session.ask_ledger.note_asked(int522._reentry(rig))  # the follow-up is spoken
    ticket = rig.stack.close()
    assert ticket is not None and rig.stack.agent.record(ticket.work_id).state is WorkState.QUEUED
    rig.stack.agent.run_pending()
    assert rig.stack.agent.record(ticket.work_id).state is WorkState.COMPLETED
    _assert_resolved_unclear(rig)
    assert rig.stack.engine.follow_ups == ()
    assert rig.triage.evaluated[-1] == ticket.work_id
    _assert_k2_reached_the_clinic(rig, ticket.work_id, location)
    assert rig.anchors is not None
    assert [u.cause for u in rig.anchors.unclear] == [
        UnclearCause.NO_CHOICE,
        UnclearCause.SESSION_CLOSED,
    ]
    int521._turn(rig, None)
    assert [(m.rule_id, m.location) for m in rig.channel.published] == [(K2, location)]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_session_end_with_the_onset_asked_and_never_answered_resolves_it(
    profile: VoiceProfile,
) -> None:
    rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"))
    int522._lead(rig)
    rig.stack.session.ask_ledger.note_asked(ONSET)
    rig.stack.agent.run_pending()
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    _assert_resolved_unclear(rig)
    _assert_k2_reached_the_clinic(rig, ticket.work_id, RedLocation.REMOTE)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_last_answer_runs_before_the_close_and_an_older_band_stays_quiet(
    profile: VoiceProfile,
) -> None:
    """The close is queued behind the answers already submitted (FIFO), so an
    'üç günden daha önce' said just before the patient left binds its own day
    first; the close then finds nothing pending, changes nothing, and nothing
    fires."""
    rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"))
    int522._lead(rig)
    rig.stack.session.ask_ledger.note_asked(ONSET)
    answer = rig.stack.session.submit_utterance(ONSET, SAID_OLDER).work_id
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    rig.stack.agent.run_pending()
    assert rig.stack.agent.record(answer).state is WorkState.COMPLETED
    assert rig.stack.agent.record(ticket.work_id).state is WorkState.COMPLETED
    assert rig.stack.engine.value_of(ONSET) == int522._day(3)
    assert ticket.work_id not in rig.triage.evaluated
    assert rig.clinic.notifications == [] and rig.stack.agent.sealed is False


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_closing_twice_is_one_close_and_a_sealed_session_has_nothing_to_close(
    profile: VoiceProfile,
) -> None:
    rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"))
    int522._lead(rig)
    rig.stack.session.ask_ledger.note_asked(ONSET)
    first, second = rig.stack.close(), rig.stack.close()
    assert first is not None and second is not None and first.work_id == second.work_id
    rig.stack.agent.run_pending()
    assert rig.stack.agent.sealed is True  # K2 fired at the close
    assert rig.stack.close() is None
    assert len(rig.clinic.notifications) == 1


def test_the_close_is_layer_b_work_the_talker_cannot_submit() -> None:
    """The close runs in the state lane under the engine lock; the Talker's
    only submission is ``extract_slots`` (invariant 9: six tools, unchanged)."""
    from intake_voice_runtime.clinical_agent.work_queue import LANE_OF, WorkLane

    assert LANE_OF[WorkType.CLOSE_SESSION] is WorkLane.STATE
    rig = int522._rig(VoiceProfile.TYPED, _model("baskı", "no-slot-no-flag"))
    assert WorkType.CLOSE_SESSION in rig.stack.agent.state_handlers


class _Unreadable:
    def read(self, tenant_id: str) -> TenantVoiceControl:
        raise VoiceControlUnavailable("voice_control_unreachable")


def test_ending_a_routed_session_closes_it() -> None:
    """The router's ``end`` is the runtime's session end: it queues the close
    behind the session's last answers before forgetting the session."""
    typed = int522._rig(VoiceProfile.TYPED, _model("baskı", "no-slot-no-flag"))
    voice = int522._rig(VoiceProfile.RESIDENCY_TR, _model("baskı", "no-slot-no-flag"))
    router = VoiceSessionRouter(controls=_Unreadable(), clock=FakeClock())
    routed = router.start(
        tenant_id=int522.int518.TENANT,
        session_id=int522.int518.SESSION,
        builders={
            VoiceProfile.TYPED: lambda: typed.stack,
            VoiceProfile.RESIDENCY_TR: lambda: voice.stack,
        },
    )
    assert routed.stack is typed.stack
    int522._lead(typed)
    int522._say(typed, ONSET, UNFIT["no-slot-no-flag"][0])
    router.end(int522.int518.SESSION)
    assert router.live() == ()
    typed.stack.agent.run_pending()
    _assert_resolved_unclear(typed)
    assert [n.rule_ids for n in typed.clinic.notifications] == [(K2,)]


# --- the determination stays the rules engine's -------------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_close_determination_is_the_rules_engines_own(profile: VoiceProfile) -> None:
    """Invariant 1: what the close settles is ``evaluate_triage`` over the
    engine's answers with the anchor read as CD-05 decides — nothing in the
    runtime computes a level."""
    rig = int522._rig(profile, _model("baskı", "no-slot-no-flag"))
    int522._lead(rig)
    rig.stack.session.ask_ledger.note_asked(ONSET)
    ticket = rig.stack.close()
    assert ticket is not None
    rig.stack.agent.run_pending()
    [red] = [r for r in rig.stack.agent.drain_results() if r.work_id == ticket.work_id]
    expected = evaluate_triage(
        int521._served_rules(), rig.triage.context(rig.stack.engine), RedLocation.REMOTE
    ).result
    assert red.presentation.triage_update == expected
    assert expected.level is TriageLevel.RED


def test_session_anchors_refuse_a_cd04_table_with_a_present_qualified_anchor() -> None:
    """A tense anchor is a date: a CD-04 table that gives it a PRESENT_QUALIFIED
    reading is a decision this runtime cannot follow, refused when composed."""
    from protocols.answer_states import AnswerStateError, HedgeBasis, HedgeEntry, HedgeState

    table = load_answer_state_table()
    wrong = HedgeEntry(
        surface_tr="sentetik",
        tokens=("sentetik",),
        state=HedgeState.PRESENT_QUALIFIED,
        qualifier="sentetik",
        slots=frozenset({ONSET}),
        basis=HedgeBasis.DECIDED,
    )
    bad = dataclasses.replace(table, entries=(*table.entries, wrong))
    with pytest.raises(AnswerStateError, match=ONSET):
        SessionAnchors(load_anchor_choice_table(), bad)


# --- the seams around it --------------------------------------------------------------


class _Garbled(int522.SpokenModel):
    """The model answers one line with a document that is not JSON."""

    def __init__(self, base: int522.SpokenModel, garbled: str) -> None:
        super().__init__(base.by_line, base.clarify)
        self.garbled = garbled

    def complete(self, call: ExtractionCall) -> Completion:
        if call.data.text == self.garbled:
            self.calls.append(call)
            return Completion(text="not a document", input_tokens=1, output_tokens=1)
        return super().complete(call)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_refused_document_for_the_asked_anchor_is_no_choice_and_asks_the_follow_up(
    profile: VoiceProfile,
) -> None:
    """A completion the parser refuses records nothing at all, so for the asked
    anchor no authored choice was recorded: UNCLEAR, the follow-up asked. A
    second refused document spends the bound and CD-05 resolves the anchor."""
    said = "Şey, o zaman, bilemedim işte."
    rig = int522._rig(profile, _Garbled(_model("baskı", "no-slot-no-flag"), said))
    int522._lead(rig)
    first = int522._say(rig, ONSET, said)
    [refused] = [o for o in rig.stack.handler.outcomes if o.record.case_id.startswith(ONSET)]
    assert refused.result is None and refused.refusal is not None
    assert rig.stack.agent.record(first).state is WorkState.COMPLETED
    _assert_the_follow_up_is_queued_once(rig)
    last = int522._say(rig, int522._reentry(rig), said)
    _assert_resolved_unclear(rig)
    _assert_k2_reached_the_clinic(rig, last, RedLocation.REMOTE)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_an_answer_attributed_to_no_step_is_not_the_anchors_answer(
    profile: VoiceProfile,
) -> None:
    """A Work naming a step the engine does not hold fails as it always did
    (``EngineError``), and is not read as the pending anchor's answer: no
    follow-up, nothing recorded."""
    rig = int522._rig(profile, _model("baskı", "bilmiyorum-no-slot-no-flag"))
    int522._lead(rig)
    rig.stack.session.ask_ledger.note_asked(ONSET)
    rig.stack.agent.run_pending()
    work_id = rig.stack.session.submit_utterance("chest_pain.yok", "Bilmiyorum.").work_id
    rig.stack.agent.run_pending()
    assert rig.stack.agent.record(work_id).state is WorkState.FAILED
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    assert rig.stack.engine.follow_ups == ()
    assert rig.anchors is not None and rig.anchors.unclear == []


def test_an_unclear_reading_shows_no_qualifier() -> None:
    """invariant 6: the record names the anchor, the cause and the decision,
    never what the patient's answer was taken to mean."""
    rig = int522._rig(VoiceProfile.TYPED, _model("baskı", "emin-degilim-model-guessed-a-choice"))
    int522._lead(rig)
    int522._say(rig, ONSET, UNFIT["emin-degilim-model-guessed-a-choice"][0])
    assert rig.anchors is not None
    [unclear] = rig.anchors.unclear
    shown = f"{unclear!r} {unclear}"
    assert "unsure" not in shown and "emin" not in shown
    assert ONSET in shown and UnclearCause.HEDGE.value in shown and "CD-04" in shown


def test_a_session_with_no_anchor_closes_and_changes_nothing() -> None:
    """The close is registered on every session; over a protocol with no
    closed-choice date there is nothing to resolve and nothing is evaluated."""
    clock = FakeClock()
    stack = builders(tenant_id=int522.int518.TENANT, session_id="s-540", clock=clock)[
        VoiceProfile.TYPED
    ]()
    assert stack.anchors is None
    ticket = stack.close()
    assert ticket is not None
    stack.agent.run_pending()
    assert stack.agent.record(ticket.work_id).state is WorkState.COMPLETED
    assert stack.engine.data_gaps == ()


def test_ending_a_session_the_router_does_not_hold_is_a_no_op() -> None:
    router = VoiceSessionRouter(controls=_Unreadable(), clock=FakeClock())
    router.end("never-started")
    assert router.live() == ()


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_refused_follow_up_answer_consumes_that_follow_up(profile: VoiceProfile) -> None:
    """Under a bound of two, a refused document answering the first follow-up
    consumes it: exactly one follow-up is queued next, never a stale one
    beside it."""
    said = "Şey, o zaman, bilemedim işte."
    model = _Garbled(_model("baskı", "no-slot-no-flag"), said)
    rig = int522._rig(profile, model, answer_states=_with_bound(2))
    int522._lead(rig)
    int522._say(rig, ONSET, said)
    int522._say(rig, int522._reentry(rig), said)
    assert [s for s in rig.stack.engine.follow_ups if s.startswith(ONSET)] == [f"{ONSET}/clarify/2"]
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PENDING
