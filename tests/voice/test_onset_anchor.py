"""INT-522 — the onset binds from its closed choice, so the K2 anchor is known live.

GitHub #888, from INT-518 (#884). ``chest_pain.onset_at`` is the tense anchor
of ``rf.chest_pain_cardiac_features`` (KIRMIZI_K2) and its SARI sibling: a
``date`` slot the patient answers with one of four closed choices. Extraction
offered the model ``{"type": "string", "format": "date"}``, gave it no
reference date and told it not to infer one — rightly — so a spoken choice
bound nothing, the anchor read Unknown, and K2 could not fire from a real
conversation. INT-518's and INT-521's suites passed only because their recorded
completion carried an ISO date no model could honestly produce.

What this suite holds, on both profiles, over the committed ``base.intake`` and
the committed active ``base.life_threat`` rules:

1. The model is offered the authored choices and nothing else for the anchor:
   no date format, no reference date anywhere in the call. A date the model
   supplies anyway is refused and binds nothing (invariant 14: speech is data;
   the model picks a choice, it never computes a day).
2. Each choice binds CD-05's day, computed from the session's own reference
   time — injected at composition, the one ``temporal_within`` compares
   against — never from a wall clock and never from the model. The record
   keeps the patient's choice beside the resolved day, and labels the
   twelve-to-seventy-two-hour band's resolution as CD-05's while-draft one.
3. A spoken choice plus a cardiac character answer fires K2 at the rule's
   register and location through the live RED path; 'üç günden daha önce' is
   evaluated and does not; the SARI sibling reads the same resolution.
4. A hedged answer binds nothing: the anchor stays Unknown, the rule's Unknown
   branch holds (``when ∧ anchor`` is Unknown, nothing fires) and the scripted
   follow-up is asked. An answer that never fits a choice ends UNCLEAR once
   CD-04's one follow-up is spent (INT-540; it was the engine's generic two
   before), and CD-05 resolves it to the reference day.
5. A closed-choice date slot with no decided resolution cannot be composed.

The gateway is a table standing in for the model; nothing dials a model. The
transcripts are synthetic (files/04 §7).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
import test_extraction_valuesets as int518
import test_live_triage as int521
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, RulesTriageResult, TriageLevel
from intake_voice_runtime.clinical_agent.anchors import SessionAnchors
from intake_voice_runtime.composition import (
    RedWiring,
    build_residency_tr_session,
    build_typed_session,
    protocol_slots,
)
from intake_voice_runtime.extraction.errors import AnchorChoicesUnresolved
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.extraction.result import FlagReason
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.red_path import RedTriggerMessage
from intake_voice_runtime.talker.session import TurnHold
from protocols.anchor_choices import (
    AnchorBasis,
    AnchorChoiceError,
    AnchorChoiceTable,
    load_anchor_choice_table,
)
from protocols.answer_states import AnswerStateTable, load_answer_state_table
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.triage import evaluate_triage
from protocols.triage.engine import rule_truth
from protocols.triage.expr import Truth
from protocols.types import EK4Level
from red_harness import RecordingClinicNotifier, RecordingDataChannel
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingScreen,
    RecordingSink,
    RecordingSynthesizer,
)

K2 = int518.K2
SARI = int521.SARI
ONSET = int521.ONSET
PRESENT = int521.PRESENT
CHARACTER = int518.CHARACTER
RADIATION = int518.RADIATION
SUBJECT = int521.SUBJECT
NOW = int518.NOW

NOW_CHOICE = "şu anda var"
TWELVE_HOURS = "son on iki saat içinde"
TWELVE_TO_72 = "on iki saatten önce ama son üç gün içinde"
OLDER = "üç günden daha önce"

#: CD-05, choice → (days before the reference day, the record's basis).
CD05: Mapping[str, tuple[int, AnchorBasis]] = {
    NOW_CHOICE: (0, AnchorBasis.DECIDED),
    TWELVE_HOURS: (0, AnchorBasis.DECIDED),
    TWELVE_TO_72: (0, AnchorBasis.WHILE_DRAFT),
    OLDER: (3, AnchorBasis.DECIDED),
}
FIRING = (NOW_CHOICE, TWELVE_HOURS, TWELVE_TO_72)

#: What the patient says to the onset question for each choice. Synthetic.
SAID_ONSET: Mapping[str, str] = {
    NOW_CHOICE: "Şu anda da var, geçmedi.",
    TWELVE_HOURS: "Bu sabah olmuştu, şimdi geçti.",
    TWELVE_TO_72: "Dünden önceki akşam olmuştu.",
    OLDER: "Geçen hafta olmuştu, o günden beri yok.",
}
#: Answers that fit no choice: the model answers none and asks to clarify.
HEDGED = ("Emin değilim, tam hatırlamıyorum.", "Bilmiyorum.", "Gerçekten hatırlayamıyorum.")

#: The non-onset steps, as INT-518 drives them, and what the patient says.
LEAD_STEPS: tuple[str, ...] = (SUBJECT, PRESENT, CHARACTER, RADIATION)
SAID = dict(int518.TRANSCRIPTS)


# --- the model double -----------------------------------------------------------------


class SpokenModel:
    """The model's answer, recorded by what the patient said, and only that.

    Each line answers its own question: ``values`` for the declared slots, and
    ``clarify`` where the line fits no choice. A real constrained decoder could
    emit nothing the call's schema does not declare, so neither can this.
    """

    def __init__(
        self,
        by_line: Mapping[str, Mapping[str, JsonValue]],
        clarify: Sequence[str] = (),
    ) -> None:
        self.by_line = {line: dict(values) for line, values in by_line.items()}
        self.clarify = frozenset(clarify)
        self.calls: list[ExtractionCall] = []

    def complete(self, call: ExtractionCall) -> Completion:
        self.calls.append(call)
        declared = call.json_schema["properties"]["slots"]["properties"]
        said = self.by_line.get(call.data.text, {})
        body = {
            "slots": {
                ref: {"value": value, "confidence": 0.93}
                for ref, value in said.items()
                if ref in declared
            },
            "candidate_flags": [],
            "clarification_needed": call.data.text in self.clarify,
        }
        return Completion(
            text=json.dumps(body, ensure_ascii=False), input_tokens=11, output_tokens=13
        )


def _model(
    character: str,
    radiation: str,
    onset: Mapping[str, JsonValue] | None = None,
    *,
    clarify: Sequence[str] = (),
    extra: Mapping[str, Mapping[str, JsonValue]] | None = None,
) -> SpokenModel:
    answers = int518._model_answers(character, radiation)
    by_line: dict[str, Mapping[str, JsonValue]] = {
        SAID[step]: {step: answers[step]} for step in LEAD_STEPS
    }
    by_line.update(onset or {})
    by_line.update(extra or {})
    return SpokenModel(by_line, clarify=clarify)


def _onset(choice: str) -> dict[str, Mapping[str, JsonValue]]:
    return {SAID_ONSET[choice]: {ONSET: choice}}


# --- the composed session -------------------------------------------------------------


@dataclass
class Rig(int521.Rig):
    anchors: SessionAnchors | None = None


def _rig(
    profile: VoiceProfile,
    model: SpokenModel,
    *,
    location: RedLocation = RedLocation.REMOTE,
    reference_time: datetime = NOW,
    anchor_choices: AnchorChoiceTable | None = None,
    answer_states: AnswerStateTable | None = None,
) -> Rig:
    """INT-521's composition, with the reference time, the CD-05 table and
    the CD-04 table (INT-540) the caller's to inject."""
    clock = FakeClock()
    channel = RecordingDataChannel(clock=clock)
    clinic = RecordingClinicNotifier()
    screen = RecordingScreen()
    red = RedWiring(location=location, channel=channel, scripts=int521._scripts())
    if profile is VoiceProfile.TYPED:
        stack = build_typed_session(
            protocol=int521._served_protocol(),
            reference_time=reference_time,
            session_id=int518.SESSION,
            protocol_hash=int518.HASH,
            gateway=model,
            screen=screen,
            memory=InMemoryPatientMemory(),
            tenant_id=int518.TENANT,
            clinic=clinic,
            clock=clock,
            red=red,
            anchor_choices=anchor_choices,
            answer_states=answer_states,
        )
        return Rig(stack, clock, channel, clinic, None, None, screen, stack.anchors)
    sink = RecordingSink(clock=clock)
    synthesizer = RecordingSynthesizer()
    stack = build_residency_tr_session(
        protocol=int521._served_protocol(),
        reference_time=reference_time,
        session_id=int518.SESSION,
        voice_id=int518.VOICE_ID,
        protocol_hash=int518.HASH,
        gateway=model,
        synthesizer=synthesizer,
        clip_store=RecordedClipStore(),
        sink=sink,
        memory=InMemoryPatientMemory(),
        tenant_id=int518.TENANT,
        clinic=clinic,
        clock=clock,
        screen=screen,
        red=red,
        anchor_choices=anchor_choices,
        answer_states=answer_states,
    )
    return Rig(stack, clock, channel, clinic, sink, synthesizer, screen, stack.anchors)


def _say(rig: Rig, step_id: str, line: str) -> str:
    """Put one question and send its answer the way ``take_turn`` does; the
    Backend pump then applies the ask and runs the Work. Returns the work id."""
    rig.stack.session.ask_ledger.note_asked(step_id)
    work_id = rig.stack.session.submit_utterance(step_id, line).work_id
    rig.stack.agent.run_pending()
    return work_id


def _lead(rig: Rig) -> dict[str, str]:
    return {step: _say(rig, step, SAID[step]) for step in LEAD_STEPS}


def _reentry(rig: Rig) -> str:
    """The clarification the engine queued for the onset: the next thing asked."""
    [reentry] = [step for step in rig.stack.engine.follow_ups if step.startswith(ONSET)]
    return reentry


def _day(days: int, reference_time: datetime = NOW) -> str:
    return (reference_time.date() - timedelta(days=days)).isoformat()


# --- 1 · the model picks a choice; it is offered no date --------------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_model_is_offered_the_authored_choices_and_no_date(profile: VoiceProfile) -> None:
    model = _model("baskı", "yok", _onset(NOW_CHOICE))
    rig = _rig(profile, model)
    _lead(rig)
    _say(rig, ONSET, SAID_ONSET[NOW_CHOICE])
    [call] = [c for c in model.calls if ONSET in c.json_schema["properties"]["slots"]["properties"]]
    shape = call.json_schema["properties"]["slots"]["properties"][ONSET]["properties"]["value"]
    choices = protocol_slots(int521._served_protocol())[ONSET].choices_tr
    assert choices is not None
    assert shape == {"type": "string", "enum": list(choices[TR])}
    assert "format" not in shape
    # no reference date reaches the model, so it has none to compute from
    blob = call.instructions + json.dumps(call.json_schema, ensure_ascii=False)
    for days in range(0, 8):
        assert _day(days) not in blob
    assert str(NOW.year) not in blob


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_date_the_model_supplies_is_refused_and_binds_nothing(profile: VoiceProfile) -> None:
    """INT-518's recorded completion carried an ISO date. No model can honestly
    produce one without a reference date, and this one is given none: the
    answer is outside the closed set, so it is flagged and binds nothing."""
    model = _model("baskı", "yok", {SAID_ONSET[NOW_CHOICE]: {ONSET: _day(0)}})
    rig = _rig(profile, model)
    _lead(rig)
    work_id = _say(rig, ONSET, SAID_ONSET[NOW_CHOICE])
    assert rig.stack.agent.record(work_id).state is WorkState.COMPLETED
    [outcome] = [o for o in rig.stack.handler.outcomes if o.record.case_id.startswith(ONSET)]
    assert outcome.result is not None
    assert [(flag.ref, flag.reason) for flag in outcome.result.flags] == [
        (ONSET, FlagReason.VALUESET_VIOLATION)
    ]
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    assert rig.anchors is not None and rig.anchors.record == {}
    assert work_id not in rig.triage.evaluated
    assert rig.stack.agent.sealed is False
    # INT-540: refused is not silently pending — CD-04's one follow-up is asked
    assert _reentry(rig) == f"{ONSET}/clarify/1"


# --- 2 · each choice binds CD-05's day from the session's own clock -------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("choice", list(CD05))
def test_each_spoken_choice_binds_its_cd05_day(profile: VoiceProfile, choice: str) -> None:
    rig = _rig(profile, _model("başka bir his", "yok", _onset(choice)))
    _lead(rig)
    work_id = _say(rig, ONSET, SAID_ONSET[choice])
    days, basis = CD05[choice]
    assert rig.stack.agent.record(work_id).state is WorkState.COMPLETED
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PRESENT
    assert rig.stack.engine.value_of(ONSET) == _day(days)
    assert rig.anchors is not None
    resolution = rig.anchors.record[ONSET]
    # the record keeps the patient's choice beside the resolved day
    assert (resolution.choice_tr, resolution.resolved_on, resolution.basis) == (
        choice,
        _day(days),
        basis,
    )
    assert resolution.decision_id == "CD-05"
    assert rig.triage.evaluated[-1] == work_id


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_choice_for_a_question_never_asked_binds_and_records_nothing(
    profile: VoiceProfile,
) -> None:
    """Nothing binds to a question that was not asked (files/13 §9.6), and the
    record holds only what bound: a choice the engine dropped is not on it."""
    rig = _rig(profile, _model("baskı", "yok", _onset(NOW_CHOICE)))
    _lead(rig)
    rig.stack.session.submit_utterance(ONSET, SAID_ONSET[NOW_CHOICE])  # never asked
    rig.stack.agent.run_pending()
    assert rig.stack.engine.state_of(ONSET) is AnswerState.NOT_ASKED
    assert rig.anchors is not None and rig.anchors.record == {}
    assert rig.stack.agent.sealed is False


ISTANBUL = timezone(timedelta(hours=3))


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize(
    "reference_time",
    [
        pytest.param(datetime(2031, 2, 28, 23, 30, tzinfo=ISTANBUL), id="another-year"),
        pytest.param(datetime(2026, 10, 16, 0, 0, 1, tzinfo=ISTANBUL), id="just-after-midnight"),
        pytest.param(datetime(2026, 10, 15, 23, 59, 59, tzinfo=ISTANBUL), id="just-before-it"),
    ],
)
def test_the_day_comes_from_the_sessions_injected_clock_and_nothing_else(
    profile: VoiceProfile, reference_time: datetime
) -> None:
    """Fake clock. The reference time is stamped once, at composition (files/13
    §9.2), and is the only time the resolution reads: a session composed in
    another year binds that year's days, the day turns at the reference time's
    own midnight, and two virtual days of session time passing before the
    answer move nothing — the tense windows measure against the same stamp."""
    for choice in (NOW_CHOICE, OLDER):
        rig = _rig(
            profile, _model("başka bir his", "yok", _onset(choice)), reference_time=reference_time
        )
        _lead(rig)
        rig.clock.advance(2 * 24 * 3600)  # virtual time; the session's stamp is fixed
        _say(rig, ONSET, SAID_ONSET[choice])
        days, _ = CD05[choice]
        assert rig.stack.engine.value_of(ONSET) == _day(days, reference_time)
        assert rig.stack.engine.reference_time == reference_time


# --- 3 · a spoken choice and a cardiac answer fire K2 through the live path -------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
@pytest.mark.parametrize("choice", FIRING)
def test_a_spoken_onset_choice_and_a_cardiac_answer_fire_k2(
    profile: VoiceProfile, location: RedLocation, choice: str
) -> None:
    """No recorded ISO date anywhere: the patient says the band, the model picks
    the authored choice, the runtime binds CD-05's day, the rules engine says
    RED, and the next turn delivers the rule's own pre-positioned action for the
    session's location over the data channel, at the rule's register."""
    rig = _rig(profile, _model("baskı", "yok", _onset(choice)), location=location)
    _lead(rig)
    onset_work = _say(rig, ONSET, SAID_ONSET[choice])
    k2 = next(rule for rule in int521._served_rules() if rule.id == K2)

    assert rig.stack.agent.sealed is True
    assert [(n.work_id, n.rule_ids, n.register, n.location) for n in rig.clinic.notifications] == [
        (onset_work, (K2,), RedRegister.ALERT, location)
    ]

    outcome = int521._turn(rig)
    assert outcome.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    [red] = rig.stack.session.preempts
    triage = red.presentation.triage_update
    evaluation = int521._independent_evaluation(rig.stack, location)
    assert isinstance(triage, RulesTriageResult)
    assert triage == evaluation.result
    assert triage.level is TriageLevel.RED and evaluation.ek4 is EK4Level.KIRMIZI_K2
    assert [fire.id for fire in triage.rules] == [K2]
    assert (triage.register, triage.location) == (RedRegister.ALERT, location)
    # the evidence the clinician reads carries the resolved day, not the choice
    [fire] = triage.rules
    anchor_evidence = [slot for slot in fire.evidence_slots if slot.slot == ONSET]
    assert [slot.values for slot in anchor_evidence] == [(_day(0),)]

    assert rig.channel.published == [
        RedTriggerMessage(
            rule_id=K2,
            register=RedRegister.ALERT,
            location=location,
            script_id=f"{K2}.{location.value.lower()}",
        )
    ]
    held = int521._catalogue()[rig.channel.published[0].script_id]
    assert held == evaluation.action
    int521._assert_the_rules_own_action(held, k2, location)
    if rig.synthesizer is not None and rig.sink is not None:
        assert rig.synthesizer.requests == []
        assert rig.sink.played == []
    assert rig.stack.session.red_stopped is True


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
def test_near_miss_a_choice_outside_the_window_is_evaluated_and_does_not_fire(
    profile: VoiceProfile, location: RedLocation
) -> None:
    """'üç günden daha önce' binds the reference day minus three: outside K2's
    now window by three days, and outside the SARI sibling's today window, so
    the same cardiac answer that fires above stays quiet (CD-05; NICE CG95
    1.2.1.10 sends that patient to detailed assessment, not 112)."""
    rig = _rig(profile, _model("baskı", "yok", _onset(OLDER)), location=location)
    _lead(rig)
    onset_work = _say(rig, ONSET, SAID_ONSET[OLDER])
    assert rig.stack.engine.value_of(ONSET) == _day(3)
    assert rig.triage.evaluated[-1] == onset_work
    k2 = next(rule for rule in int521._served_rules() if rule.id == K2)
    assert rule_truth(k2, rig.triage.context(rig.stack.engine)) is Truth.FALSE
    outcome = int521._turn(rig)
    assert rig.channel.published == []
    assert rig.clinic.notifications == []
    assert rig.stack.session.preempts == ()
    assert rig.stack.agent.sealed is False
    assert outcome.held is None  # type: ignore[attr-defined]
    assert outcome.step_id is not None  # type: ignore[attr-defined]


#: The SARI sibling's gate: a non-cardiac character, no radiation, no sweating,
#: no breathlessness, no recent trauma.
SARI_STEPS: tuple[tuple[str, str, JsonValue], ...] = (
    ("associated.diaphoresis", "Hayır, terlemedim.", False),
    ("associated.dyspnoea", "Hayır, nefesim daralmadı.", False),
    ("trauma.recent", "Hayır, darbe almadım.", False),
)


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("choice", list(CD05))
def test_the_today_tensed_sibling_reads_the_same_resolution(
    profile: VoiceProfile, choice: str
) -> None:
    """``rf.chest_pain_no_cardiac_history`` anchors on the same slot with tense
    today (CD-05 anchors). The first three bands sit on the reference day and
    the sibling fires its SARI_K1; 'üç günden daha önce' does not."""
    extra = {line: {step: value} for step, line, value in SARI_STEPS}
    rig = _rig(profile, _model("yanma", "yok", _onset(choice), extra=extra))
    _lead(rig)
    for step, line, _ in SARI_STEPS:
        _say(rig, step, line)
    _say(rig, ONSET, SAID_ONSET[choice])
    evaluation = evaluate_triage(
        int521._served_rules(), rig.triage.context(rig.stack.engine), RedLocation.REMOTE
    )
    if choice == OLDER:
        assert evaluation.result.level is TriageLevel.GREEN
    else:
        assert evaluation.result.level is TriageLevel.YELLOW
        assert evaluation.ek4 is EK4Level.SARI_K1
        assert [fire.id for fire in evaluation.result.rules] == [SARI]
    assert rig.channel.published == []


# --- 4 · a hedged answer stays Unknown; one that never fits ends UNCLEAR -----------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_hedged_answer_binds_nothing_and_the_rules_unknown_branch_holds(
    profile: VoiceProfile,
) -> None:
    """The model picks no choice for 'emin değilim' and asks to clarify. The
    anchor stays pending, so it reads Unknown: K2's ``when`` is True on the
    cardiac answer and ``when ∧ anchor`` is Unknown, which does not fire. The
    scripted follow-up — verbatim from the pack — is queued, nothing is
    evaluated for that Work, and nothing is resolved."""
    rig = _rig(profile, _model("baskı", "yok", clarify=HEDGED[:1]))
    _lead(rig)
    work_id = _say(rig, ONSET, HEDGED[0])
    engine = rig.stack.engine
    assert engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    assert work_id not in rig.triage.evaluated
    context = rig.triage.context(engine)
    assert ONSET not in context.answers
    k2 = next(rule for rule in int521._served_rules() if rule.id == K2)
    assert rule_truth(k2, context) is Truth.UNKNOWN
    assert evaluate_triage(int521._served_rules(), context, RedLocation.REMOTE).result.level is (
        TriageLevel.GREEN
    )
    reentry = _reentry(rig)
    slot = protocol_slots(int521._served_protocol())[ONSET]
    assert slot.follow_up_tr is not None
    assert engine.frontier()[0].text_tr == slot.follow_up_tr[TR]
    assert reentry == f"{ONSET}/clarify/1"
    assert rig.anchors is not None and rig.anchors.record == {}
    assert rig.stack.agent.sealed is False


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_hedged_answer_then_a_clear_older_band_binds_the_older_day(
    profile: VoiceProfile,
) -> None:
    """The follow-up answered with a choice binds that choice's day — the
    hedge does not linger as an acute reading once the patient has answered."""
    rig = _rig(profile, _model("baskı", "yok", _onset(OLDER), clarify=HEDGED[:1]))
    _lead(rig)
    _say(rig, ONSET, HEDGED[0])
    _say(rig, _reentry(rig), SAID_ONSET[OLDER])
    assert rig.stack.engine.value_of(ONSET) == _day(3)
    assert rig.anchors is not None
    assert rig.anchors.record[ONSET].basis is AnchorBasis.DECIDED
    int521._turn(rig)
    assert rig.channel.published == []
    assert rig.stack.agent.sealed is False


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
def test_an_answer_that_never_fits_a_choice_is_unclear_and_resolves_to_the_reference_day(
    profile: VoiceProfile, location: RedLocation
) -> None:
    """CD-05 ``unresolved_answer``: an answer that fits no choice, or
    'bilmiyorum', is recorded UNCLEAR and resolved to the more acute reading,
    the reference day. The engine records UNCLEAR when CD-04's one follow-up
    is spent (INT-540; files/13 §11.1's generic two before); that Work is
    evaluated, and with a cardiac character K2 fires at its register and the
    session's location."""
    rig = _rig(profile, _model("baskı", "yok", clarify=HEDGED), location=location)
    _lead(rig)
    first = _say(rig, ONSET, HEDGED[0])
    assert rig.stack.agent.sealed is False
    last = _say(rig, _reentry(rig), HEDGED[1])
    engine = rig.stack.engine
    assert engine.state_of(ONSET) is AnswerState.UNCLEAR
    assert ONSET in engine.data_gaps
    assert first not in rig.triage.evaluated
    assert rig.triage.evaluated[-1] == last
    assert rig.anchors is not None
    resolution = rig.anchors.record[ONSET]
    assert (resolution.choice_tr, resolution.resolved_on, resolution.basis) == (
        None,
        _day(0),
        AnchorBasis.UNRESOLVED,
    )
    assert rig.stack.agent.sealed is True
    assert [(n.work_id, n.rule_ids, n.register, n.location) for n in rig.clinic.notifications] == [
        (last, (K2,), RedRegister.ALERT, location)
    ]
    int521._turn(rig)
    assert [message.rule_id for message in rig.channel.published] == [K2]
    assert rig.stack.session.red_stopped is True


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_an_unclear_onset_with_a_non_cardiac_answer_does_not_fire(
    profile: VoiceProfile,
) -> None:
    """The resolution dates the anchor; it does not open the gate. The same
    two unfitting answers with no cardiac feature stay quiet."""
    rig = _rig(profile, _model("başka bir his", "yok", clarify=HEDGED))
    _lead(rig)
    _say(rig, ONSET, HEDGED[0])
    last = _say(rig, _reentry(rig), HEDGED[1])
    assert rig.stack.engine.state_of(ONSET) is AnswerState.UNCLEAR
    assert rig.triage.evaluated[-1] == last
    assert rig.stack.agent.sealed is False
    assert rig.clinic.notifications == []


def test_an_unclear_slot_that_is_not_an_anchor_still_reads_unknown() -> None:
    """Only CD-05's anchors resolve an UNCLEAR answer. Any other read slot in
    UNCLEAR is absent from the context and reads Unknown (files/12 §1.1)."""
    character_unclear = (
        "Tarif edemiyorum.",
        "Bilemiyorum.",
        "Anlatamıyorum.",
    )
    answers = int518._model_answers("baskı", "yok")
    by_line: dict[str, Mapping[str, JsonValue]] = {
        SAID[step]: {step: answers[step]} for step in (SUBJECT, PRESENT)
    }
    model = SpokenModel(by_line, clarify=character_unclear)
    rig = _rig(VoiceProfile.TYPED, model)
    _say(rig, SUBJECT, SAID[SUBJECT])
    _say(rig, PRESENT, SAID[PRESENT])
    _say(rig, CHARACTER, character_unclear[0])
    for line in character_unclear[1:]:
        [reentry] = [s for s in rig.stack.engine.follow_ups if s.startswith(CHARACTER)]
        _say(rig, reentry, line)
    assert rig.stack.engine.state_of(CHARACTER) is AnswerState.UNCLEAR
    assert CHARACTER not in rig.triage.context(rig.stack.engine).answers


# --- 5 · a closed-choice date with no decided resolution cannot be composed -------------


def _table_without_anchor() -> AnchorChoiceTable:
    table = load_anchor_choice_table()
    return AnchorChoiceTable(
        decision_id=table.decision_id,
        anchors=frozenset(),
        question_tr=table.question_tr,
        choices=table.choices,
        unresolved_days_before_reference=table.unresolved_days_before_reference,
    )


def _table_missing_a_choice() -> AnchorChoiceTable:
    table = load_anchor_choice_table()
    return AnchorChoiceTable(
        decision_id=table.decision_id,
        anchors=table.anchors,
        question_tr=table.question_tr,
        choices=table.choices[:-1],
        unresolved_days_before_reference=table.unresolved_days_before_reference,
    )


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize(
    "table",
    [
        pytest.param(_table_without_anchor, id="no-resolution-for-the-slot"),
        pytest.param(_table_missing_a_choice, id="a-choice-with-no-day"),
    ],
)
def test_a_closed_choice_date_with_no_decided_resolution_cannot_be_composed(
    profile: VoiceProfile, table: Callable[[], AnchorChoiceTable]
) -> None:
    """A choice the runtime cannot turn into a day could never bind, so the
    anchor would read Unknown for the whole session and the rule could never
    fire. Refused when composed, naming the slot, before a patient is asked
    anything."""
    with pytest.raises(AnchorChoicesUnresolved, match=ONSET):
        _rig(profile, _model("baskı", "yok"), anchor_choices=table())


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_committed_decision_composes_and_is_the_one_used(
    profile: VoiceProfile,
) -> None:
    rig = _rig(profile, _model("baskı", "yok"))
    assert rig.anchors is not None
    assert rig.anchors.table == load_anchor_choice_table()
    assert rig.stack.handler.anchors is rig.anchors
    assert rig.triage.anchors is rig.anchors


def test_only_the_anchors_choice_is_replaced_and_anything_else_there_is_refused() -> None:
    """The handler's seam, alone: the anchor's authored choice becomes its day
    and every other update passes through untouched; a value at the anchor
    that is not an authored choice — a boolean, a date, a near spelling — is
    refused rather than bound (the Work fails, loudly), never guessed."""
    anchors = SessionAnchors(load_anchor_choice_table(), load_answer_state_table())
    updates, [resolution] = anchors.resolve_choices({ONSET: OLDER, CHARACTER: "baskı"}, NOW)
    assert updates == {ONSET: _day(3), CHARACTER: "baskı"}
    assert (resolution.anchor, resolution.choice_tr) == (ONSET, OLDER)
    assert anchors.record == {}  # recorded only once the engine binds it
    for wrong in (True, _day(0), "Şu anda var"):
        with pytest.raises(AnchorChoiceError):
            anchors.resolve_choices({ONSET: wrong}, NOW)
