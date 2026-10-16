"""INT-521 — the live session evaluates triage on every bound answer, so a RED fires.

The defect (GitHub #887, from INT-518): after INT-518 every base.intake code
slot binds in a live session, but no production module called
``protocols.triage.evaluate_triage`` during a session and no handler set
``triage_update``. The answers bound and nothing evaluated them, so a
chest-pain RED could not fire from the conversation: the RED path in
``work_queue`` and ``red_path`` was fed only by tests.

What this suite holds, on both profiles, over the committed ``base.intake``
and the committed active ``base.life_threat`` rules:

1. Every completed Work that binds a slot a served red-flag rule reads is
   evaluated by ``packages/protocols/triage`` and by nothing else
   (invariant 1); a Work that binds nothing, or binds only slots no rule
   reads, is not.
2. Each of the six cardiac literals of ``rf.chest_pain_cardiac_features``,
   answered alone, reaches the existing RED path under each of the three
   locations: the queue derives ``preempt`` from the rules-engine RED and
   seals, the clinician route is told, the Talker drains it, cancels its audio
   and triggers the rule's own pre-positioned action for that location over
   the data channel, at the rule's register, and asks nothing more
   (invariants 9, 21). Under ON_SITE that action offers no 112. Every other
   pair of committed choices binds, is evaluated and stays quiet.
3. The Talker never awaits the evaluation (fake clock) and keeps exactly its
   six tools.
4. A session that can fire a RED cannot be composed without the means to
   deliver one, and a draft rule cannot be pinned into a session.

``chest_pain.onset_at`` — the K2 rule's tense anchor — is answered here as a
patient answers it, with the authored choice 'şu anda var', and binds the day
CD-05 resolves it to against the session's reference time (INT-522, #888;
``tests/voice/test_onset_anchor.py``). Before INT-522 this suite's recorded
completion carried an ISO date the model was never given the means to compute.

The gateway is a table standing in for the model; nothing dials a model. The
transcripts are synthetic (files/04 §7). Script ids are synthetic test data in
the rule-plus-location shape the INT-446 catalogue uses.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest
import test_extraction_valuesets as int518
from clinic_item_harness import RecordingClinicItems
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import (
    RedLocation,
    RedRegister,
    RuleFire,
    RulesTriageResult,
    TriageLevel,
)
from intake_voice_runtime.clinical_agent import live_triage
from intake_voice_runtime.clinical_agent.live_triage import SessionTriage, served_rules
from intake_voice_runtime.clinical_agent.work_queue import (
    BackendAgent,
    StateContext,
    StateEffect,
)
from intake_voice_runtime.composition import (
    RedWiring,
    RedWiringMissing,
    SessionStack,
    build_residency_tr_session,
    build_typed_session,
    protocol_slots,
)
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.ports import (
    QueueSealed,
    WorkRequest,
    WorkState,
    WorkTicket,
    WorkType,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.delivery import DeliveryClass
from intake_voice_runtime.talker.preemption import BackendResult, Presentation, Priority
from intake_voice_runtime.talker.red_path import (
    MappingRedScriptIndex,
    RedPathNotWired,
    RedPathViolation,
    RedPreemption,
    RedTriggerMessage,
    RedViolation,
)
from intake_voice_runtime.talker.registry import assert_six_tool_surface
from intake_voice_runtime.talker.session import TalkerSession, TurnHold
from intake_voice_runtime.talker.tools import build_talker_tools
from prometheus_client import REGISTRY
from protocols.compile.resolve import ResolvedProtocol
from protocols.dsl import LocationAction, RedFlagRule, UnknownAction
from protocols.triage import DraftRuleError, SlotAnswer, TriageContext, evaluate_triage
from protocols.triage.engine import TriageEvaluation
from protocols.types import EK4Level
from protocols.valuesets import load_committed_valuesets
from red_harness import MediaPlane, RecordingClinicNotifier, RecordingDataChannel
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingScreen,
    RecordingSink,
    RecordingSynthesizer,
    StalledBackend,
    build_session,
    scripted_step,
)

K2 = int518.K2
SARI = "rf.chest_pain_no_cardiac_history"
CHARACTER = int518.CHARACTER
RADIATION = int518.RADIATION
PRESENT = "chest_pain.present"
ONSET = "chest_pain.onset_at"
SUBJECT = "identity_check.subject_role"
STEPS = tuple(step_id for step_id, _ in int518.TRANSCRIPTS)
READ_STEPS = (PRESENT, CHARACTER, RADIATION, ONSET)


# --- the served session ---------------------------------------------------------------


def _served_rules() -> tuple[RedFlagRule, ...]:
    """The committed rules a served bundle would carry today: base.life_threat's
    two active rules. Its two drafts are never compiled into a served pack
    (files/04 §8.1 rule 3), and every base.intake rule is a draft."""
    return int518._active_life_threat_rules()


def _served_protocol(rules: Sequence[RedFlagRule] | None = None) -> ResolvedProtocol:
    """base.intake with the served rules pinned beside it, as files/12 §1
    carries the sibling set: never merged into the pack's own rules."""
    pinned = tuple(_served_rules() if rules is None else rules)
    return int518._base_intake().model_copy(update={"life_threat_rules": pinned})


def _own_action(rule: RedFlagRule, location: RedLocation) -> LocationAction | UnknownAction:
    """The rule's own frozen action object for one location, from the committed file."""
    assert rule.action is not None
    if location is RedLocation.REMOTE:
        return rule.action.remote
    if location is RedLocation.ON_SITE:
        return rule.action.on_site
    return rule.action.unknown


def _catalogue() -> dict[str, LocationAction | UnknownAction]:
    """What the device holds, pre-positioned: script id → the served RED rule's
    own action for that location. The id shape is INT-446's catalogue key
    (rule plus lower-case location); the ids are test data, the actions are
    the committed rule's own objects."""
    return {
        f"{rule.id}.{location.value.lower()}": _own_action(rule, location)
        for rule in _served_rules()
        if rule.level.is_red
        for location in RedLocation
    }


def _scripts() -> MappingRedScriptIndex:
    """The index over that catalogue: which held script addresses each rule."""
    return MappingRedScriptIndex(
        entries={
            (rule.id, location): f"{rule.id}.{location.value.lower()}"
            for rule in _served_rules()
            if rule.level.is_red
            for location in RedLocation
        }
    )


@dataclass
class Rig:
    """One composed session and the doubles it was composed with."""

    stack: SessionStack
    clock: FakeClock
    channel: RecordingDataChannel
    clinic: RecordingClinicNotifier
    sink: RecordingSink | None
    synthesizer: RecordingSynthesizer | None
    screen: RecordingScreen

    @property
    def triage(self) -> SessionTriage:
        triage = self.stack.agent.triage
        assert triage is not None
        return triage


def _rig(
    profile: VoiceProfile,
    answers: Mapping[str, JsonValue],
    *,
    location: RedLocation = RedLocation.REMOTE,
    protocol: ResolvedProtocol | None = None,
    gateway: int518.AnswerTable | None = None,
) -> Rig:
    clock = FakeClock()
    channel = RecordingDataChannel(clock=clock)
    clinic = RecordingClinicNotifier()
    screen = RecordingScreen()
    red = RedWiring(location=location, channel=channel, scripts=_scripts())
    model = gateway or int518.AnswerTable(answers)
    if profile is VoiceProfile.TYPED:
        stack = build_typed_session(
            protocol=protocol or _served_protocol(),
            reference_time=int518.NOW,
            session_id=int518.SESSION,
            protocol_hash=int518.HASH,
            gateway=model,
            screen=screen,
            memory=InMemoryPatientMemory(),
            tenant_id=int518.TENANT,
            clinic=clinic,
            clock=clock,
            red=red,
            clinic_items=RecordingClinicItems(),
        )
        return Rig(stack, clock, channel, clinic, None, None, screen)
    sink = RecordingSink(clock=clock)
    synthesizer = RecordingSynthesizer()
    stack = build_residency_tr_session(
        protocol=protocol or _served_protocol(),
        reference_time=int518.NOW,
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
        clinic_items=RecordingClinicItems(),
    )
    return Rig(stack, clock, channel, clinic, sink, synthesizer, screen)


def _drive(rig: Rig, steps: Sequence[str] = STEPS) -> dict[str, str]:
    """Ask each question and send its answer, the way INT-518's test does.

    The ask goes through the Talker's ask ledger and the answer through its
    ``submit_utterance`` tool; Layer B's pump then applies the ask and runs
    the Work. Returns ``{step_id: work_id}``.
    """
    transcripts = dict(int518.TRANSCRIPTS)
    work_ids: dict[str, str] = {}
    for step_id in steps:
        rig.stack.session.ask_ledger.note_asked(step_id)
        work_ids[step_id] = rig.stack.session.submit_utterance(
            step_id, transcripts.get(step_id, f"Sentetik yanıt, {step_id}.")
        ).work_id
        rig.stack.agent.run_pending()
    return work_ids


#: What the patient says next, in every turn after a question: synthetic
#: (files/04 §7). The recorded model answers by the declared slot, not by this.
NEXT_ANSWER = "Sentetik bir yanıt daha."


def _turn(rig: Rig, transcript: str | None = NEXT_ANSWER) -> object:
    """One Talker turn. It carries the patient's next answer by default: the
    turn that delivers a RED is the one the patient speaks in (INT-521 round 2:
    a RED that sealed the queue must not be stranded behind that answer)."""
    return rig.clock.run(rig.stack.session.take_turn(transcript))


#: What the patient says to each chest-pain question (INT-518's synthetic lines).
SAID = dict(int518.TRANSCRIPTS)


class _Spoken(int518.AnswerTable):
    """The model answers from what the patient said, and only that.

    In the canonical loop a Work declares its own step and every step still
    awaiting, so a table keyed by slot would answer a question before the
    patient heard it. Keyed by the transcript, each line answers its own
    question: the onset binds in the turn the patient answers the onset.
    """

    def __init__(self, by_line: Mapping[str, Mapping[str, JsonValue]]) -> None:
        super().__init__({})
        self.by_line = {line: dict(values) for line, values in by_line.items()}

    def complete(self, call: ExtractionCall) -> Completion:
        self.calls.append(call)
        declared = call.json_schema["properties"]["slots"]["properties"]
        said = self.by_line.get(call.data.text, {})
        values = {ref: said[ref] for ref in declared if ref in said}
        return Completion(text=int518._completion(values), input_tokens=11, output_tokens=13)


def _spoken_rig(
    profile: VoiceProfile,
    character: str,
    radiation: str,
    *,
    location: RedLocation = RedLocation.REMOTE,
) -> Rig:
    answers = int518._model_answers(character, radiation)
    model = _Spoken({SAID[step]: {step: answers[step]} for step in STEPS})
    return _rig(profile, answers, location=location, gateway=model)


def _converse_until_asked(rig: Rig, step_id: str, *, limit: int = 80) -> list[str | None]:
    """The canonical loop, ``session_harness.turn``'s shape: ``take_turn(transcript)``
    then Layer B's pump, until the Talker has spoken ``step_id``. Every turn after
    the first carries the patient's answer to the question asked in the turn
    before it. Returns the step each turn asked."""
    asked: list[str | None] = []
    transcript: str | None = None
    for _ in range(limit):
        outcome = rig.clock.run(rig.stack.session.take_turn(transcript))
        rig.stack.agent.run_pending()
        asked.append(outcome.step_id)
        transcript = SAID.get(outcome.step_id or "", NEXT_ANSWER)
        if outcome.step_id == step_id:
            return asked
    raise AssertionError(f"{step_id} was never asked")


# --- 1 · every Work that binds a read slot is evaluated, by the rules engine only -----


def test_the_served_rules_are_the_pinned_protocols_own() -> None:
    protocol = _served_protocol()
    assert served_rules(protocol) == (*protocol.red_flags, *protocol.life_threat_rules)
    assert {rule.id for rule in served_rules(protocol)} == {K2, SARI}


def test_the_slots_the_served_rules_read_are_the_chest_pain_set() -> None:
    """Scope pin, from the committed rules: K2 and its SARI sibling read these
    seven step ids, the tense anchor included (files/12 §2.4)."""
    triage = SessionTriage.for_protocol(
        _served_protocol(), location=RedLocation.REMOTE, reference_time=int518.NOW
    )
    assert triage.reads == frozenset(
        {
            PRESENT,
            CHARACTER,
            RADIATION,
            ONSET,
            "associated.diaphoresis",
            "associated.dyspnoea",
            "trauma.recent",
        }
    )


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_every_work_that_binds_a_read_slot_is_evaluated_and_no_other(
    profile: VoiceProfile,
) -> None:
    rig = _rig(profile, int518._model_answers("başka bir his", "yok"))
    work_ids = _drive(rig)
    assert [rig.stack.agent.record(work_ids[step]).state for step in STEPS] == [
        WorkState.COMPLETED
    ] * len(STEPS)
    # subject_role binds too, and no served rule reads it: no evaluation
    assert rig.stack.engine.state_of(SUBJECT) is AnswerState.ASKED_PRESENT
    assert rig.triage.evaluated == [work_ids[step] for step in READ_STEPS]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_work_that_binds_nothing_is_not_evaluated(profile: VoiceProfile) -> None:
    """The model answers no onset: the Work completes and binds nothing, so
    the rules engine is not run for it, and the undated RED cannot fire yet.
    It is not left silently pending either (INT-540, the INT-522 review's F1):
    an asked anchor with no choice recorded is UNCLEAR at once and CD-04's one
    scripted follow-up is queued (tests/voice/test_anchor_unclear.py)."""
    answers = {
        ref: value for ref, value in int518._model_answers("baskı", "yok").items() if ref != ONSET
    }
    rig = _rig(profile, answers)
    work_ids = _drive(rig)
    assert rig.stack.agent.record(work_ids[ONSET]).state is WorkState.COMPLETED
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    assert rig.stack.engine.follow_ups == (f"{ONSET}/clarify/1",)
    assert work_ids[ONSET] not in rig.triage.evaluated
    assert rig.triage.evaluated == [work_ids[step] for step in (PRESENT, CHARACTER, RADIATION)]
    assert rig.stack.session.preempts == ()
    assert rig.stack.agent.sealed is False


class _Failing(int518.AnswerTable):
    """The gateway refuses the onset call outright: the Work fails."""

    def complete(self, call: ExtractionCall) -> Completion:
        if ONSET in call.json_schema["properties"]["slots"]["properties"]:
            raise ConnectionError("synthetic endpoint refusal")
        return super().complete(call)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_failed_work_bound_nothing_and_is_not_evaluated(
    profile: VoiceProfile,
) -> None:
    answers = int518._model_answers("baskı", "yok")
    rig = _rig(profile, answers, gateway=_Failing(answers))
    work_ids = _drive(rig)
    assert rig.stack.agent.record(work_ids[ONSET]).state is WorkState.FAILED
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PENDING
    assert work_ids[ONSET] not in rig.triage.evaluated
    assert rig.stack.agent.sealed is False


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_each_determination_is_the_rules_engines_own(profile: VoiceProfile) -> None:
    """The result each evaluated Work carries is ``evaluate_triage`` over the
    engine's answer state, verbatim: nothing in the runtime computes a level."""
    rig = _rig(profile, int518._model_answers("baskı", "yok"))
    _drive(rig)
    drained = [
        result
        for result in rig.stack.agent.drain_results()
        if isinstance(result, BackendResult) and result.presentation.triage_update is not None
    ]
    assert [result.presentation.triage_update.level for result in drained] == [  # type: ignore[union-attr]
        TriageLevel.GREEN,
        TriageLevel.GREEN,
        TriageLevel.GREEN,
        TriageLevel.RED,
    ]
    assert drained[-1].presentation.triage_update == int518._triage(rig.stack).result


def test_the_evaluation_reads_only_value_bearing_answers() -> None:
    """A pending, unclear or never-asked slot reads Unknown, as files/12 §1.1
    and ``protocols.triage.context`` read it; only a bound answer is a value."""
    rig = _rig(VoiceProfile.TYPED, int518._model_answers("baskı", "yok"))
    _drive(rig, STEPS[:-1])
    context = rig.triage.context(rig.stack.engine)
    assert set(context.answers) == {PRESENT, CHARACTER, RADIATION}
    assert context.reference_time == int518.NOW
    assert context.answers[CHARACTER].values == ("baskı",)


# --- 2 · a cardiac answer alone fires the RED, and it reaches the RED path ----------


#: The six cardiac literals of ``rf.chest_pain_cardiac_features``. Each is
#: answered alone: a cardiac character with a radiation outside the rule's
#: set, or a cardiac radiation with a character outside it. Sweating and
#: breathlessness are never asked.
CARDIAC_CHARACTERS = ("baskı", "sıkışma", "ağırlık")
CARDIAC_RADIATIONS = ("kol", "çene", "sırt")
#: Every other committed choice of the two slots.
OTHER_CHARACTERS = ("yanma", "başka bir his")
OTHER_RADIATIONS = ("boyun", "omuz", "başka bir yer", "yok")

CARDIAC = [
    *(
        pytest.param(character, "yok", id=f"character={character}")
        for character in CARDIAC_CHARACTERS
    ),
    *(
        pytest.param("başka bir his", radiation, id=f"radiation={radiation}")
        for radiation in CARDIAC_RADIATIONS
    ),
]
NEAR_MISSES = [
    pytest.param(character, radiation, id=f"{character}+{radiation}")
    for character in OTHER_CHARACTERS
    for radiation in OTHER_RADIATIONS
]


def test_the_six_literals_are_the_rules_own_and_the_near_misses_the_rest() -> None:
    """Scope pin, read from the committed files: the six literals are exactly
    the K2 gate's two sets, and the near misses are every other committed
    choice of the two slots."""
    k2 = next(rule for rule in _served_rules() if rule.id == K2)
    gate = " ".join(k2.when.split())
    assert 'chest_pain.character in {"baskı", "sıkışma", "ağırlık"}' in gate
    assert 'chest_pain.radiation in {"kol", "çene", "sırt"}' in gate
    members = load_committed_valuesets().member_map()
    assert set(members["vs.chest_pain_character"]) == {*CARDIAC_CHARACTERS, *OTHER_CHARACTERS}
    assert set(members["vs.chest_pain_radiation"]) == {*CARDIAC_RADIATIONS, *OTHER_RADIATIONS}


def _independent_evaluation(stack: SessionStack, location: RedLocation) -> TriageEvaluation:
    """The rules engine over the engine's answer state, with the context built
    here rather than by ``SessionTriage`` — INT-518's reading, at ``location``."""
    engine = stack.engine
    answers: dict[str, SlotAnswer] = {}
    for step_id in protocol_slots(int518._base_intake()):
        state = engine.state_of(step_id)
        if state in (AnswerState.ASKED_PRESENT, AnswerState.ASKED_ABSENT):
            answers[step_id] = SlotAnswer(state=state, values=(engine.value_of(step_id),))
    context = TriageContext(reference_time=engine.reference_time, answers=answers)
    return evaluate_triage(_served_rules(), context, location)


def _texts(action: LocationAction) -> list[str]:
    """Every patient-facing string of one location's action, in Turkish."""
    texts = [*action.do_nots_tr.get("tr", ())]
    for text in (action.action_tr, action.why_tr):
        if text is not None:
            texts.append(text["tr"])
    return texts


def _assert_the_rules_own_action(
    held: LocationAction | UnknownAction, k2: RedFlagRule, location: RedLocation
) -> None:
    """files/02 §5.3 Axis 3, against the committed rule's own action block."""
    assert k2.action is not None
    if location is RedLocation.REMOTE:
        assert isinstance(held, LocationAction)
        assert held == k2.action.remote
        assert (held.primary, held.show_112) == ("CALL_112", True)
        assert held.action_tr is not None and "112" in held.action_tr["tr"]
    elif location is RedLocation.ON_SITE:
        assert isinstance(held, LocationAction)
        assert held == k2.action.on_site
        # under ON_SITE the 112 affordance is absent, not de-emphasised (invariant 21)
        assert (held.primary, held.show_112) == ("GO_TO_IN_HOUSE_ACIL", False)
        assert held.notify_staff_immediate is True
        assert not any("112" in text for text in _texts(held))
    else:
        assert isinstance(held, UnknownAction)
        assert held == k2.action.unknown
        # exactly one question, then the rule's own branch targets
        assert (held.on_yes, held.on_no, held.on_no_answer) == ("ON_SITE", "REMOTE", "REMOTE")
        assert "112" not in held.ask_one_tr["tr"]


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
@pytest.mark.parametrize(("character", "radiation"), CARDIAC)
def test_a_cardiac_answer_alone_fires_the_red_from_the_conversation(
    profile: VoiceProfile, location: RedLocation, character: str, radiation: str
) -> None:
    """Six literals × three locations × two profiles, through the live path.

    The location is the caller's, derived from the visit lifecycle (files/02
    §5.3 Axis 3); the register is the rule's, and the location never changes
    it. The script the trigger addresses is the committed rule's own action for
    that location, and it is the action the rules engine resolves.
    """
    rig = _rig(profile, int518._model_answers(character, radiation), location=location)
    work_ids = _drive(rig)
    engine = rig.stack.engine
    k2 = next(rule for rule in _served_rules() if rule.id == K2)

    # the answer bound, alone
    assert (engine.value_of(CHARACTER), engine.value_of(RADIATION)) == (character, radiation)
    assert engine.state_of("associated.diaphoresis") is AnswerState.NOT_ASKED
    assert engine.state_of("associated.dyspnoea") is AnswerState.NOT_ASKED

    # Layer B: the rules engine's RED, derived to preempt, the clinician told, sealed
    assert rig.stack.agent.sealed is True
    assert [(n.work_id, n.rule_ids, n.register, n.location) for n in rig.clinic.notifications] == [
        (work_ids[ONSET], (K2,), RedRegister.ALERT, location)
    ]

    # Layer A: the next turn drains it and delivers it before asking anything
    outcome = _turn(rig)
    assert outcome.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert outcome.spoken_text == ""  # type: ignore[attr-defined]
    assert outcome.step_id is None  # type: ignore[attr-defined]
    [red] = rig.stack.session.preempts
    assert (red.work_id, red.priority) == (work_ids[ONSET], Priority.PREEMPT)
    evaluation = _independent_evaluation(rig.stack, location)
    triage = red.presentation.triage_update
    assert triage == evaluation.result
    assert isinstance(triage, RulesTriageResult)
    assert triage.level is TriageLevel.RED
    assert evaluation.ek4 is EK4Level.KIRMIZI_K2
    assert [fire.id for fire in triage.rules] == [K2]
    assert (triage.register, triage.location) == (RedRegister.ALERT, location)

    # the pre-positioned script, triggered over the data channel
    assert rig.channel.published == [
        RedTriggerMessage(
            rule_id=K2,
            register=RedRegister.ALERT,
            location=location,
            script_id=f"{K2}.{location.value.lower()}",
        )
    ]
    held = _catalogue()[rig.channel.published[0].script_id]
    assert held == evaluation.action
    _assert_the_rules_own_action(held, k2, location)

    # the RED path touches no media transport: nothing synthesised, rendered or played
    if rig.synthesizer is not None and rig.sink is not None:
        assert rig.synthesizer.requests == []
        assert rig.sink.played == []
        assert rig.sink.cancels == 1
    assert rig.screen.rendered == []
    assert rig.stack.session.red_stopped is True
    assert {n.work_id for n in rig.clinic.notifications} == {work_ids[ONSET]}

    # the intake stays stopped
    after = _turn(rig)
    assert after.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert len(rig.channel.published) == 1


@pytest.mark.parametrize("location", list(RedLocation))
def test_near_miss_the_same_script_at_another_location_is_another_action(
    location: RedLocation,
) -> None:
    """The positive test's ON_SITE assertions can fail: the REMOTE action of the
    same rule offers 112, and ON_SITE's does not."""
    k2 = next(rule for rule in _served_rules() if rule.id == K2)
    others = [other for other in RedLocation if other is not location]
    for other in others:
        with pytest.raises(AssertionError):
            _assert_the_rules_own_action(_own_action(k2, other), k2, location)


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize(("character", "radiation"), NEAR_MISSES)
def test_near_miss_a_non_cardiac_answer_is_evaluated_and_does_not_fire(
    profile: VoiceProfile, character: str, radiation: str
) -> None:
    """Every pair of the other committed choices: bound, evaluated, quiet."""
    rig = _rig(profile, int518._model_answers(character, radiation))
    work_ids = _drive(rig)
    assert (rig.stack.engine.value_of(CHARACTER), rig.stack.engine.value_of(RADIATION)) == (
        character,
        radiation,
    )
    assert rig.triage.evaluated == [work_ids[step] for step in READ_STEPS]
    outcome = _turn(rig)
    assert rig.channel.published == []
    assert rig.clinic.notifications == []
    assert rig.stack.session.preempts == ()
    assert rig.stack.session.red_stopped is False
    assert rig.stack.agent.sealed is False
    # the intake carries on: this turn asks the next question
    assert outcome.held is None  # type: ignore[attr-defined]
    assert outcome.step_id is not None  # type: ignore[attr-defined]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_the_cardiac_answer_without_its_onset_does_not_fire(
    profile: VoiceProfile,
) -> None:
    """The K2 rule is ``when ∧ anchor``: an undated cardiac character reads
    Unknown and does not fire (files/12 §2.4). The four Works before the onset
    are evaluated; the RED needs the anchor too."""
    rig = _rig(profile, int518._model_answers("baskı", "yok"))
    _drive(rig, STEPS[:-1])
    _turn(rig)
    assert rig.channel.published == []
    assert rig.stack.session.red_stopped is False


# --- 3 · the canonical loop: the RED is delivered in the turn the patient speaks --------


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize("location", list(RedLocation))
@pytest.mark.parametrize(
    ("character", "radiation"),
    [
        pytest.param("baskı", "yok", id="character-alone"),
        pytest.param("başka bir his", "kol", id="radiation-alone"),
    ],
)
def test_the_canonical_loop_delivers_the_red_and_asks_nothing_after_it(
    profile: VoiceProfile, location: RedLocation, character: str, radiation: str
) -> None:
    """``take_turn(transcript)`` then the pump, every turn, as the worker runs it.

    The Talker itself asks every question up to the onset, the patient answers
    each in the next turn, and Layer B evaluates behind. The RED settles and
    seals the queue after the onset answer; the next turn — in which the
    patient is speaking again — delivers it before it submits that answer,
    asks nothing, and every later turn stays stopped. Before INT-521 round 2
    that turn raised ``QueueSealed`` and the RED stayed in the queue.
    """
    rig = _spoken_rig(profile, character, radiation, location=location)
    asked = _converse_until_asked(rig, ONSET)
    assert [step for step in asked if step in READ_STEPS] == list(READ_STEPS)
    session, agent = rig.stack.session, rig.stack.agent

    answering = rig.clock.run(session.take_turn(SAID[ONSET]))  # the onset answer
    agent.run_pending()  # Layer B: the onset Work binds, the engine says RED, the queue seals
    assert answering.work_id is not None
    assert agent.record(answering.work_id).state is WorkState.COMPLETED
    assert agent.sealed is True
    assert rig.channel.published == []
    played = len(rig.sink.played) if rig.sink is not None else 0
    rendered = len(rig.screen.rendered)

    delivering = _turn(rig)  # the patient speaks again; nothing is submitted
    assert delivering.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert (delivering.step_id, delivering.spoken_text) == (None, "")  # type: ignore[attr-defined]
    assert delivering.work_id is None  # type: ignore[attr-defined]
    assert rig.channel.published == [
        RedTriggerMessage(
            rule_id=K2,
            register=RedRegister.ALERT,
            location=location,
            script_id=f"{K2}.{location.value.lower()}",
        )
    ]
    [red] = session.preempts
    assert red.work_id == answering.work_id
    assert session.red_stopped is True
    # nothing asked, spoken or rendered after it; on voice the audio was cancelled
    for _ in range(2):
        assert _turn(rig).held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert len(rig.screen.rendered) == rendered
    if rig.sink is not None:
        assert len(rig.sink.played) == played
        assert rig.sink.cancels == 1
    assert len(rig.channel.published) == 1
    assert {n.work_id for n in rig.clinic.notifications} == {answering.work_id}


@dataclass
class _RacingBackend:
    """The real queue, with Layer B finishing a Work between the Talker's drain
    and its submit — the order a worker thread can produce. ``_settle`` puts a
    RED in the results before ``_seal``, so the submit that follows is refused
    with the RED already waiting."""

    agent: BackendAgent

    def submit(self, request: WorkRequest) -> WorkTicket:
        return self.agent.submit(request)

    def cancel(self, work_id: str, reason: str) -> WorkTicket:
        return self.agent.cancel(work_id, reason)

    def note_asked(self, step_id: str) -> None:
        self.agent.note_asked(step_id)

    def drain_results(self) -> tuple[object, ...]:
        drained = self.agent.drain_results()
        self.agent.run_pending()
        return drained


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_red_that_seals_between_the_drain_and_the_submit_is_still_delivered(
    profile: VoiceProfile,
) -> None:
    rig = _rig(profile, int518._model_answers("baskı", "yok"))
    _drive(rig, STEPS[:-1])
    session, agent = rig.stack.session, rig.stack.agent
    session.ask_ledger.note_asked(ONSET)
    session.submit_utterance(ONSET, dict(int518.TRANSCRIPTS)[ONSET])  # queued, not run
    session.backend = _RacingBackend(agent)
    outcome = _turn(rig)
    assert agent.sealed is True
    assert outcome.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert [message.rule_id for message in rig.channel.published] == [K2]
    assert session.red_stopped is True


def test_near_miss_a_seal_with_no_red_behind_it_is_raised() -> None:
    """The Talker catches ``QueueSealed`` only to deliver the RED that sealed
    the queue. A seal with nothing behind it is a defect, and is raised."""

    @dataclass
    class _Sealed:
        def submit(self, request: WorkRequest) -> WorkTicket:
            raise QueueSealed("sealed with no RED in the results")

        def cancel(self, work_id: str, reason: str) -> WorkTicket:
            return WorkTicket(work_id=work_id, state=WorkState.CANCELLED)

        def drain_results(self) -> tuple[object, ...]:
            return ()

    clock = FakeClock()
    session = build_session(clock, steps=[scripted_step()], backend=_Sealed())
    with pytest.raises(QueueSealed):
        clock.run(session.take_turn(NEXT_ANSWER))


# --- 4 · the Talker never awaits the evaluation, and keeps six tools --------------------


def _stalled_turns(
    profile: VoiceProfile, stall_s: float
) -> tuple[Rig, object, list[str], object, float]:
    """The canonical loop up to the onset question; then the turn that carries
    the onset answer runs while Layer B is stalled ``stall_s`` of virtual time
    before it runs that Work; then the patient's next turn."""
    rig = _spoken_rig(profile, "baskı", "yok")
    _converse_until_asked(rig, ONSET)
    session, agent = rig.stack.session, rig.stack.agent
    started_at = rig.clock.now_ms()

    async def layer_b() -> None:
        await rig.clock.sleep(stall_s)
        agent.run_pending()

    async def scenario() -> tuple[object, list[str], object]:
        backend = asyncio.ensure_future(layer_b())
        during = await session.take_turn(SAID[ONSET])  # the onset answer
        evaluated_during = list(rig.triage.evaluated)
        await backend
        after = await session.take_turn(NEXT_ANSWER)  # the patient speaks again
        return during, evaluated_during, after

    during, evaluated_during, after = rig.clock.run(scenario())
    return rig, during, evaluated_during, after, started_at


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_talker_never_awaits_the_evaluation(profile: VoiceProfile) -> None:
    """With Layer B stalled thirty virtual seconds before it evaluates, the
    turn that carries the answer costs exactly what it costs with Layer B
    instant; the evaluation has not run when it returns; the patient's next
    turn delivers the RED."""
    fast, fast_turn, _, _, fast_start = _stalled_turns(profile, 0.0)
    slow, slow_turn, evaluated_during, slow_after, slow_start = _stalled_turns(profile, 30.0)
    assert slow_turn.elapsed_ms == fast_turn.elapsed_ms  # type: ignore[attr-defined]
    assert slow_turn.held is None  # type: ignore[attr-defined]
    assert slow_turn.work_id is not None  # type: ignore[attr-defined]
    assert len(evaluated_during) == len(READ_STEPS) - 1
    assert len(slow.triage.evaluated) == len(READ_STEPS)
    assert slow_after.held is TurnHold.INTAKE_STOPPED  # type: ignore[attr-defined]
    assert [message.rule_id for message in slow.channel.published] == [K2]
    # the budget is measured from the evaluation, after the stall
    [red] = slow.stack.session.preempts
    assert red.evaluated_at_ms == slow_start + 30_000.0
    assert fast.stack.session.preempts[0].evaluated_at_ms == fast_start


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_red_drained_late_is_delivered_and_its_budget_breach_is_loud(
    profile: VoiceProfile,
) -> None:
    """The budgets run from the evaluation, not from the drain (files/02 §8.2).

    The Talker drains Layer B only when it takes a turn. Two virtual seconds
    pass between the evaluation and the patient's next turn here: the RED is
    still delivered in that turn and the intake still stops, and the path then
    raises with both budgets breached, because the two seconds are on the RED's
    clock. A Talker that stamped the RED on arrival would report it in budget.
    """
    rig = _spoken_rig(profile, "baskı", "yok")
    _converse_until_asked(rig, ONSET)
    rig.clock.run(rig.stack.session.take_turn(SAID[ONSET]))  # the onset answer
    rig.stack.agent.run_pending()
    evaluated_at = rig.clock.now_ms()
    rig.clock.run(rig.clock.sleep(2.0))
    with pytest.raises(RedPathViolation) as breach:
        _turn(rig)
    outcome = breach.value.outcome
    [red] = rig.stack.session.preempts
    assert outcome.evaluated_at_ms == red.evaluated_at_ms == evaluated_at
    assert outcome.e2e_ms is not None and outcome.e2e_ms >= 2_000.0
    assert set(breach.value.violations) == {RedViolation.STOP_BUDGET, RedViolation.E2E_BUDGET}
    assert [message.rule_id for message in rig.channel.published] == [K2]
    assert rig.stack.session.red_stopped is True


def test_the_talker_holds_no_evaluator() -> None:
    """Structural half: the rules engine is not reachable from Layer A."""
    source = inspect.getsource(TalkerSession)
    for name in ("evaluate_triage", "SessionTriage", "live_triage", "run_pending"):
        assert name not in source
    assert "triage" not in {name for name in vars(TalkerSession) if not name.startswith("_")}


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_composed_talker_keeps_exactly_six_tools(profile: VoiceProfile) -> None:
    rig = _rig(profile, {})
    assert_six_tool_surface(build_talker_tools(rig.stack.session))


# --- 4 · composition: a session that can fire a RED can deliver one -----------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_session_with_served_rules_and_no_red_wiring_cannot_be_composed(
    profile: VoiceProfile,
) -> None:
    clock = FakeClock()
    with pytest.raises(RedWiringMissing, match=r"rf\.chest_pain_cardiac_features"):
        if profile is VoiceProfile.TYPED:
            build_typed_session(
                protocol=_served_protocol(),
                reference_time=int518.NOW,
                session_id=int518.SESSION,
                protocol_hash=int518.HASH,
                gateway=int518.AnswerTable({}),
                screen=RecordingScreen(),
                memory=InMemoryPatientMemory(),
                tenant_id=int518.TENANT,
                clinic=RecordingClinicNotifier(),
                clock=clock,
            )
        else:
            build_residency_tr_session(
                protocol=_served_protocol(),
                reference_time=int518.NOW,
                session_id=int518.SESSION,
                voice_id=int518.VOICE_ID,
                protocol_hash=int518.HASH,
                gateway=int518.AnswerTable({}),
                synthesizer=RecordingSynthesizer(),
                clip_store=RecordedClipStore(),
                sink=RecordingSink(clock=clock),
                memory=InMemoryPatientMemory(),
                tenant_id=int518.TENANT,
                clinic=RecordingClinicNotifier(),
                clock=clock,
            )


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_session_with_no_served_rules_composes_as_before(
    profile: VoiceProfile,
) -> None:
    """INT-518's composition, unchanged: no rules, no evaluator, no RED path."""
    stack = int518._compose(profile, protocol=int518._base_intake(), gateway=int518.AnswerTable({}))
    assert stack.agent.triage is None
    assert stack.session.preemption is None


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_red_path_is_bound_and_the_served_rules_are_authorised(
    profile: VoiceProfile,
) -> None:
    """The preempt gate authorises the pinned protocol's own rules even when the
    caller passes no rule ids: a RED the evaluator can produce is never refused
    as foreign, which would fail the Work and drop the RED."""
    rig = _rig(profile, {})
    assert isinstance(rig.stack.session.preemption, RedPreemption)
    assert rig.stack.session.preemption.channel is rig.channel
    assert rig.stack.session.preemption.clinic is rig.clinic
    assert {K2, SARI} <= rig.stack.agent.rule_ids
    assert rig.stack.session.config.rule_ids == rig.stack.agent.rule_ids
    assert rig.triage.location is RedLocation.REMOTE


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_draft_rule_cannot_be_pinned_into_a_session(profile: VoiceProfile) -> None:
    """The committed drafts (HB-C1) refuse at composition, before a patient is
    asked anything: the engine refuses them, so a session pinned to one would
    fail at its first evaluation instead (files/04 §8.1 rule 3)."""
    from protocols.compile.life_threat import load_life_threat_set

    every = tuple(entry.rule for entry in load_life_threat_set(int518.LIFE_THREAT).rules)
    with pytest.raises(DraftRuleError, match="rf.paediatric_airway_obstruction"):
        _rig(profile, {}, protocol=_served_protocol(every))


# --- the queue and the Talker, unit level ---------------------------------------------------


def _failures(kind: str) -> float:
    value = REGISTRY.get_sample_value("triage_live_evaluation_failures_total", {"kind": kind})
    return value or 0.0


def _handing(rig: Rig, handed: Callable[[StateContext], RulesTriageResult | None]) -> None:
    """Wrap the production handler so it also returns a determination of its own."""
    inner = rig.stack.agent.state_handlers[WorkType.EXTRACT_SLOTS]

    def handler(context: StateContext) -> StateEffect:
        inner(context)
        return StateEffect(triage_update=handed(context))

    rig.stack.agent.register_state(WorkType.EXTRACT_SLOTS, handler)


GREEN = RulesTriageResult(level=TriageLevel.GREEN)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_handlers_green_cannot_mask_the_engines_red(
    profile: VoiceProfile, caplog: pytest.LogCaptureFixture
) -> None:
    """A handler that says GREEN on the onset Work is checked against the rules
    engine; the engine's RED stands, is delivered, and the disagreement pages."""
    rig = _rig(profile, int518._model_answers("baskı", "yok"))
    _handing(rig, lambda _: GREEN)
    before = _failures("conflict")
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.clinical_agent.work_queue"):
        work_ids = _drive(rig)
    assert _failures("conflict") - before == 1  # the four GREENs agreed; the onset did not
    [conflict] = [r for r in caplog.records if r.getMessage() == "triage determination conflict"]
    assert (conflict.session_id, conflict.work_id) == (int518.SESSION, work_ids[ONSET])  # type: ignore[attr-defined]
    assert rig.stack.agent.sealed is True
    _turn(rig)
    [red] = rig.stack.session.preempts
    assert red.work_id == work_ids[ONSET]
    assert [message.rule_id for message in rig.channel.published] == [K2]


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_handlers_determination_that_disagrees_is_refused_for_the_engines(
    profile: VoiceProfile,
) -> None:
    """A handler's YELLOW where the engine says GREEN: the engine's stands,
    even on a Work that bound nothing a rule reads."""
    rig = _rig(profile, int518._model_answers("başka bir his", "yok"))
    handed = RulesTriageResult(
        level=TriageLevel.YELLOW, rules=(RuleFire(id=SARI, evidence="sentetik"),)
    )
    _handing(rig, lambda _: handed)
    before = _failures("conflict")
    _drive(rig, (SUBJECT, PRESENT))
    results = [r for r in rig.stack.agent.drain_results() if isinstance(r, BackendResult)]
    assert [r.presentation.triage_update for r in results] == [GREEN, GREEN]
    assert _failures("conflict") - before == 2


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_handlers_determination_that_agrees_raises_nothing(
    profile: VoiceProfile,
) -> None:
    rig = _rig(profile, int518._model_answers("baskı", "yok"))
    _handing(
        rig,
        lambda context: (
            rig.triage.context(context.engine)
            and _independent_evaluation(rig.stack, RedLocation.REMOTE).result
        ),
    )
    before = _failures("conflict")
    _drive(rig)
    assert _failures("conflict") == before
    assert rig.stack.agent.sealed is True


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_an_evaluation_fault_fails_the_work_pages_and_is_owed(
    profile: VoiceProfile, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The engine raises on the onset Work: that Work fails, the fault pages
    with ids only, and the next state Work evaluates although it binds no slot
    a rule reads — so the RED fires there instead of being lost."""
    rig = _rig(profile, int518._model_answers("baskı", "yok"))
    real = live_triage.evaluate_triage
    calls = {"n": 0}

    def flaky(*args: Any, **kwargs: Any) -> TriageEvaluation:
        calls["n"] += 1
        if calls["n"] == len(READ_STEPS):  # the onset Work's evaluation
            raise ArithmeticError("synthetic evaluation fault")
        return real(*args, **kwargs)

    monkeypatch.setattr(live_triage, "evaluate_triage", flaky)
    before = _failures("fault")
    with caplog.at_level(logging.ERROR, logger="intake_voice_runtime.clinical_agent.work_queue"):
        work_ids = _drive(rig)
    agent = rig.stack.agent
    assert agent.record(work_ids[ONSET]).state is WorkState.FAILED
    assert agent.record(work_ids[ONSET]).error == "ArithmeticError"
    assert rig.stack.engine.state_of(ONSET) is AnswerState.ASKED_PRESENT  # bound, unevaluated
    assert _failures("fault") - before == 1
    [fault] = [r for r in caplog.records if r.getMessage() == "triage evaluation failed"]
    assert {key: getattr(fault, key) for key in ("session_id", "work_id", "error")} == {
        "session_id": int518.SESSION,
        "work_id": work_ids[ONSET],
        "error": "ArithmeticError",
    }
    assert agent.sealed is False
    # the next Work binds nothing a rule reads, and still evaluates: the RED fires
    retry = _drive(rig, ("identity_check.consent_recap_confirmed",))
    assert rig.stack.engine.state_of("identity_check.consent_recap_confirmed") is (
        AnswerState.ASKED_PENDING
    )
    assert agent.sealed is True
    _turn(rig)
    [red] = rig.stack.session.preempts
    assert red.work_id == retry["identity_check.consent_recap_confirmed"]
    assert [message.rule_id for message in rig.channel.published] == [K2]


def test_a_fault_preparing_the_evaluation_fails_closed_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read-slot snapshot taken before the handler raises: the Work fails
    loudly and the handler does not run, rather than the pump crashing."""
    rig = _rig(VoiceProfile.TYPED, int518._model_answers("baskı", "yok"))

    def broken(self: SessionTriage, engine: object) -> object:
        raise LookupError("synthetic snapshot fault")

    monkeypatch.setattr(SessionTriage, "bound", broken)
    before = _failures("fault")
    work_ids = _drive(rig, (SUBJECT,))
    assert rig.stack.agent.record(work_ids[SUBJECT]).state is WorkState.FAILED
    assert rig.stack.engine.state_of(SUBJECT) is AnswerState.ASKED_PENDING  # handler never ran
    assert _failures("fault") - before == 1


def _deferred_rule() -> RedFlagRule:
    """A synthetic copy of K2 at DEFERRED_CLINICIAN: same gate, same anchor."""
    k2 = next(rule for rule in _served_rules() if rule.id == K2)
    return k2.model_copy(
        update={"id": "rf.sentetik_deferred", "register": RedRegister.DEFERRED_CLINICIAN}
    )


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_a_deferred_clinician_red_leaves_the_queue_open_and_is_raised_once(
    profile: VoiceProfile,
) -> None:
    """The real queue: a DEFERRED_CLINICIAN RED tells the clinic, changes
    nothing on the patient's surface and does not seal, so the intake's later
    answers are still taken. A re-evaluation that finds the same RED does not
    raise it again (files/02 §5.3; files/03 §15b)."""
    answers = {**int518._model_answers("baskı", "yok"), "associated.diaphoresis": False}
    rig = _rig(profile, answers, protocol=_served_protocol((_deferred_rule(),)))
    work_ids = _drive(rig)
    agent, session = rig.stack.agent, rig.stack.session
    assert agent.sealed is False
    assert [(n.work_id, n.register) for n in rig.clinic.notifications] == [
        (work_ids[ONSET], RedRegister.DEFERRED_CLINICIAN)
    ]

    outcome = _turn(rig)  # delivered: no trigger, the intake runs on, the answer is taken
    assert rig.channel.published == []
    assert session.red_stopped is False
    assert outcome.held is None  # type: ignore[attr-defined]
    assert outcome.work_id is not None  # type: ignore[attr-defined]
    assert outcome.step_id is not None  # type: ignore[attr-defined]
    [red] = session.preempts
    assert red.work_id == work_ids[ONSET]

    # a later answer a rule reads binds and is evaluated; the same RED is not raised twice
    evaluations = len(rig.triage.evaluated)
    later = _drive(rig, ("associated.diaphoresis",))
    while agent.run_pending():  # the turn's own submission ran first; finish the queue
        continue
    assert agent.record(later["associated.diaphoresis"]).state is WorkState.COMPLETED
    assert rig.stack.engine.state_of("associated.diaphoresis") is AnswerState.ASKED_ABSENT
    assert len(rig.triage.evaluated) == evaluations + 1
    assert agent.sealed is False
    _turn(rig)
    assert len(session.preempts) == 1
    assert {n.work_id for n in rig.clinic.notifications} == {work_ids[ONSET]}


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_red_that_stops_the_intake_seals_the_queue(profile: VoiceProfile) -> None:
    rig = _rig(profile, int518._model_answers("baskı", "yok"))
    _drive(rig)
    assert rig.stack.agent.sealed is True
    with pytest.raises(QueueSealed):
        rig.stack.session.submit_utterance(SUBJECT, NEXT_ANSWER)


def test_a_non_red_result_carries_no_evaluation_stamp() -> None:
    rig = _rig(VoiceProfile.TYPED, int518._model_answers("başka bir his", "yok"))
    _drive(rig)
    drained = rig.stack.agent.drain_results()
    assert drained
    assert all(
        isinstance(result, BackendResult) and result.evaluated_at_ms is None for result in drained
    )


def test_a_stamp_is_refused_on_a_result_that_does_not_preempt() -> None:
    with pytest.raises(ValueError, match="evaluated_at_ms"):
        BackendResult(
            work_id="w_routine",
            state=WorkState.COMPLETED,
            delivery_class=DeliveryClass.ROUTINE,
            presentation=Presentation(),
            evaluated_at_ms=1.0,
        )


def _unstamped_red() -> BackendResult:
    return BackendResult(
        work_id="w_red_unstamped",
        state=WorkState.COMPLETED,
        delivery_class=DeliveryClass.RED,
        presentation=Presentation(
            triage_update=RulesTriageResult(
                level=TriageLevel.RED,
                rules=(RuleFire(id=K2, evidence="sentetik"),),
                register=RedRegister.ALERT,
                location=RedLocation.REMOTE,
            )
        ),
        priority=Priority.PREEMPT,
    )


def test_a_drained_red_from_another_backend_is_still_delivered() -> None:
    """A RED with no evaluation stamp did not come from this session's queue;
    the Talker delivers it anyway, measured from the drain, because a patient
    shown nothing is the one outcome the RED path must never produce."""
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=0.0)
    session = build_session(
        clock, steps=[scripted_step()], backend=backend, rule_ids=frozenset({K2})
    )
    media = MediaPlane(clock=clock)
    channel = RecordingDataChannel(clock=clock)
    session.preemption = RedPreemption(
        canceller=media,
        channel=channel,
        clinic=RecordingClinicNotifier(),
        scripts=_scripts(),
        clock=clock,
    )
    backend._ready.append(_unstamped_red())
    outcome = clock.run(session.take_turn(None))
    assert outcome.held is TurnHold.INTAKE_STOPPED
    assert [message.script_id for message in channel.published] == [f"{K2}.remote"]
    assert session.preemption.delivered_work_ids == ("w_red_unstamped",)


def test_a_drained_red_with_no_red_path_bound_refuses_rather_than_asking_on() -> None:
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=0.0)
    session = build_session(
        clock, steps=[scripted_step()], backend=backend, rule_ids=frozenset({K2})
    )
    backend._ready.append(_unstamped_red())
    with pytest.raises(RedPathNotWired):
        clock.run(session.take_turn(None))


def test_a_deferred_clinician_red_is_delivered_and_the_intake_runs_on() -> None:
    """DEFERRED_CLINICIAN changes nothing on the patient's surface (files/02
    §5.3): the drained RED goes to the path, nothing is triggered, and the turn
    asks its question."""
    clock = FakeClock()
    backend = StalledBackend(clock=clock, stall_s=0.0)
    session = build_session(
        clock, steps=[scripted_step()], backend=backend, rule_ids=frozenset({K2})
    )
    channel = RecordingDataChannel(clock=clock)
    clinic = RecordingClinicNotifier()
    session.preemption = RedPreemption(
        canceller=MediaPlane(clock=clock),
        channel=channel,
        clinic=clinic,
        scripts=_scripts(),
        clock=clock,
    )
    deferred = _unstamped_red()
    triage = deferred.presentation.triage_update
    assert isinstance(triage, RulesTriageResult)
    backend._ready.append(
        deferred.model_copy(
            update={
                "presentation": Presentation(
                    triage_update=triage.model_copy(
                        update={"register": RedRegister.DEFERRED_CLINICIAN}
                    )
                )
            }
        )
    )
    outcome = clock.run(session.take_turn(None))
    assert channel.published == []
    assert len(clinic.notifications) == 1
    assert session.red_stopped is False
    assert outcome.held is None
    assert outcome.step_id == "s1"


# --- SessionTriage itself ---------------------------------------------------------------------


def test_a_bare_spelling_reads_the_same_slot_as_the_dotted_one() -> None:
    """files/12 §2.4: a read is ``<section>.<slot>`` or bare ``<slot>``. The K2
    gate re-spelled bare fires on the same answers; it is a synthetic copy."""
    k2 = next(rule for rule in _served_rules() if rule.id == K2)
    bare = k2.model_copy(
        update={
            "id": "rf.sentetik_bare",
            "when": k2.when.replace("chest_pain.", "").replace("associated.", ""),
            "tense_anchor": "onset_at",
        }
    )
    triage = SessionTriage.for_protocol(
        _served_protocol((bare,)), location=RedLocation.REMOTE, reference_time=int518.NOW
    )
    assert triage.reads >= {CHARACTER, RADIATION, ONSET}
    rig = _rig(VoiceProfile.TYPED, int518._model_answers("baskı", "yok"))
    _drive(rig)
    result = triage.evaluate(rig.stack.engine, work_id="w_bare")
    assert result.level is TriageLevel.RED
    assert [fire.id for fire in result.rules] == ["rf.sentetik_bare"]
    assert triage.evaluated == ["w_bare"]


def test_near_miss_a_bare_spelling_two_sections_share_reads_nothing() -> None:
    """An ambiguous bare name is not guessed at: it resolves to no slot, so it
    reads Unknown and the rule cannot fire on it."""
    spelled = live_triage.step_spellings(
        frozenset({"present", "chest_pain.present"}),
        frozenset({"chest_pain.present", "other.present"}),
    )
    assert spelled == {"chest_pain.present": "chest_pain.present"}


def test_an_unparseable_rule_cannot_be_pinned() -> None:
    k2 = next(rule for rule in _served_rules() if rule.id == K2)
    broken = k2.model_copy(update={"when": "chest_pain.present ==="})
    with pytest.raises(live_triage.UnreadableRule, match=K2):
        SessionTriage.for_protocol(
            _served_protocol((broken,)), location=RedLocation.REMOTE, reference_time=int518.NOW
        )


def test_the_engine_is_the_only_producer_of_the_level() -> None:
    """The module evaluates through ``protocols.triage`` alone (invariant 1):
    it names no level and builds no result of its own."""
    source = inspect.getsource(live_triage)
    assert "evaluate_triage(" in source
    for forbidden in ("TriageLevel.", "RulesTriageResult(", "EK4Level.", "RuleFire("):
        assert forbidden not in source
