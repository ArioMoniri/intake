"""INT-518 — live extraction gets the committed value table, so a code slot binds.

The defect (GitHub #884, from the INT-441 clinical review): the composition
root built the extraction handler with ``valuesets=dict(valuesets or {})``
and no production caller passed a table. ``slot_output_schema`` refuses a
code slot whose members it was not given, so every Work that declared one
failed with ``ExtractionRefused``: ``identity_check.subject_role``, the first
question of the session, and ``chest_pain.character`` and
``chest_pain.radiation``, the two code inputs of the active life-threat
rules. ``rf.chest_pain_cardiac_features`` could fire from what a patient said
or typed only when sweating or breathlessness was reported too.

What this suite holds:

1. Both composition roots, called the way every production caller calls them
   (no table), hand extraction the committed table: every set, never empty.
2. Every code slot a red-flag rule reads binds from each of its authored
   choices. A slot with no committed set cannot be composed (the near miss).
3. End to end over the committed ``base.intake`` and ``base.life_threat``:
   answers go through the Talker's ``submit_utterance``, the session vault,
   the registered handler, the schema-constrained call and the engine, and
   ``protocols.triage.evaluate_triage`` then fires the K2 rule on the
   character answer alone, and on the radiation answer alone. The near misses
   (a non-cardiac character, a site outside the rule's set) bind and do not
   fire.

The gateway is a table standing in for the model's answer; nothing here dials
a model. The transcripts are synthetic (files/04 §7). No rule, level or
predicate is read from anywhere but the committed files (invariants 1, 7).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
from clinical_schemas.common import JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation, RedRegister, TriageLevel
from intake_voice_runtime.composition import (
    SessionStack,
    build_residency_tr_session,
    build_typed_session,
    protocol_slots,
)
from intake_voice_runtime.extraction import (
    CodeSlotUnbound,
    ExtractionRefused,
    FlagReason,
    parse_extraction,
    slot_output_schema,
    unbound_code_slots,
)
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.ports import WorkState
from intake_voice_runtime.profiles import VoiceProfile
from protocols.compile.life_threat import load_life_threat_set
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.compile.rule_reads import rule_reads
from protocols.dsl import RedFlagRule, Slot
from protocols.loader import load_pack
from protocols.locale_text import DEFAULT_LOCALE as TR
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from protocols.triage.engine import TriageEvaluation
from protocols.types import Delivery, EK4Level, RuleStatus, SlotType
from protocols.valuesets import ValueSetTable, load_committed_valuesets
from red_harness import RecordingClinicNotifier
from session_harness import builders
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingScreen,
    RecordingSink,
    RecordingSynthesizer,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_INTAKE = REPO_ROOT / "packages" / "protocols" / "base" / "intake.yaml"
LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
HASH = "e" * 64
SESSION = "51800000-0000-4000-8000-000000000518"
TENANT = "00000000-0000-4000-8000-000000000001"
VOICE_ID = "residency-tr-01"

K2 = "rf.chest_pain_cardiac_features"
CHARACTER = "chest_pain.character"
RADIATION = "chest_pain.radiation"


# --- the committed documents ---------------------------------------------------------


def _base_intake() -> ResolvedProtocol:
    """``base.intake`` projected section by section into the resolved shape.

    The compiler refuses this pack by design (L0, every pack red-flag family an
    unsourced draft, HB-C1), so the runtime is driven over its authored
    sections directly, as ``tests/engine/test_bare_gates.py`` does. Slots with
    no ``ask_tr`` cannot be a step (invariant 10) and are left out.
    """
    pack = load_pack(BASE_INTAKE)
    sections = tuple(
        ResolvedSection(
            id=section_id,
            delivery=section.delivery or Delivery.VOICE,
            allow_paraphrase=False,
            slots=tuple(
                ResolvedSlot(
                    section_id=section_id,
                    key=key,
                    fhir_link_id=f"{section_id}.{key}",
                    slot=slot,
                    delivery=slot.delivery or section.delivery or Delivery.VOICE,
                )
                for key, slot in section.slots.items()
                if slot.ask_tr is not None
            ),
        )
        for section_id, section in pack.sections.items()
    )
    return ResolvedProtocol(
        pack_id=pack.id,
        version=pack.version,
        chain=(pack.id,),
        sections=sections,
        resolved_protocol_hash=HASH,
    )


def _red_flag_rules() -> tuple[RedFlagRule, ...]:
    """Every red-flag rule: the sibling life-threat set and base.intake's own."""
    sibling = tuple(entry.rule for entry in load_life_threat_set(LIFE_THREAT).rules)
    return sibling + tuple(load_pack(BASE_INTAKE).red_flags)


def _active_life_threat_rules() -> tuple[RedFlagRule, ...]:
    rules = (entry.rule for entry in load_life_threat_set(LIFE_THREAT).rules)
    return tuple(rule for rule in rules if rule.status is RuleStatus.ACTIVE)


def _red_flag_code_slots() -> dict[str, Slot]:
    """Every base.intake code slot any red-flag rule reads, by step id.

    A read is spelled ``<section>.<slot>`` or bare ``<slot>`` (files/12 §2.4);
    both spellings are looked up so a bare read is not missed.
    """
    slots = protocol_slots(_base_intake())
    by_name: dict[str, str] = {}
    for ref in slots:
        by_name[ref] = ref
        by_name.setdefault(ref.split(".", 1)[1], ref)
    found: dict[str, Slot] = {}
    for rule in _red_flag_rules():
        reads = rule_reads(rule)
        assert reads is not None, f"{rule.id}: a rule whose reads cannot be listed"
        for name in reads.all:
            ref = by_name.get(name)
            if ref is not None and slots[ref].type is SlotType.CODE:
                found[ref] = slots[ref]
    return found


def _choices(slot: Slot) -> tuple[str, ...]:
    assert slot.choices_tr is not None
    return tuple(slot.choices_tr[TR])


def _members(table: ValueSetTable) -> dict[str, tuple[str, ...]]:
    return table.member_map()


def _without(table: ValueSetTable, valueset_id: str) -> ValueSetTable:
    """The committed table with one set taken out: the near miss."""
    kept = {key: value for key, value in table.valuesets.items() if key != valueset_id}
    return table.model_copy(update={"valuesets": kept})


def _completion(values: Mapping[str, JsonValue]) -> str:
    """One completion carrying ``values``, in the closed shape the schema allows."""
    body = {
        "slots": {ref: {"value": value, "confidence": 0.95} for ref, value in values.items()},
        "candidate_flags": [],
        "clarification_needed": False,
    }
    return json.dumps(body, ensure_ascii=False)


# --- a recorded model -----------------------------------------------------------------


class AnswerTable:
    """The model's answer, recorded: each declared slot it holds an answer for.

    It answers only what the call declares, because the schema is closed and a
    real constrained decoder could not emit anything else.
    """

    def __init__(self, answers: Mapping[str, JsonValue]) -> None:
        self.answers = dict(answers)
        self.calls: list[ExtractionCall] = []

    def complete(self, call: ExtractionCall) -> Completion:
        self.calls.append(call)
        declared = call.json_schema["properties"]["slots"]["properties"]
        values = {ref: self.answers[ref] for ref in declared if ref in self.answers}
        return Completion(text=_completion(values), input_tokens=11, output_tokens=13)


def _compose(
    profile: VoiceProfile,
    *,
    protocol: ResolvedProtocol,
    gateway: AnswerTable,
    valuesets: ValueSetTable | None = None,
) -> SessionStack:
    clock = FakeClock()
    if profile is VoiceProfile.TYPED:
        return build_typed_session(
            protocol=protocol,
            reference_time=NOW,
            session_id=SESSION,
            protocol_hash=HASH,
            gateway=gateway,
            screen=RecordingScreen(),
            memory=InMemoryPatientMemory(),
            tenant_id=TENANT,
            clinic=RecordingClinicNotifier(),
            clock=clock,
            valuesets=valuesets,
        )
    return build_residency_tr_session(
        protocol=protocol,
        reference_time=NOW,
        session_id=SESSION,
        voice_id=VOICE_ID,
        protocol_hash=HASH,
        gateway=gateway,
        synthesizer=RecordingSynthesizer(),
        clip_store=RecordedClipStore(),
        sink=RecordingSink(clock=clock),
        memory=InMemoryPatientMemory(),
        tenant_id=TENANT,
        clinic=RecordingClinicNotifier(),
        clock=clock,
        valuesets=valuesets,
    )


# --- 1 · production composition passes the committed table ----------------------------


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_the_builders_the_worker_hands_in_give_extraction_the_committed_table(
    profile: VoiceProfile,
) -> None:
    """``session_harness.builders`` calls both roots as the worker does: with no
    table. Before INT-518 the handler then held ``{}``."""
    stack = builders(tenant_id=TENANT, session_id=SESSION, clock=FakeClock())[profile]()
    committed = _members(load_committed_valuesets())
    assert committed, "the committed table is empty"
    assert dict(stack.handler.valuesets) == committed


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_base_intake_composes_with_every_code_slot_bound_to_its_committed_set(
    profile: VoiceProfile,
) -> None:
    stack = _compose(profile, protocol=_base_intake(), gateway=AnswerTable({}))
    code_slots = {
        ref: slot
        for ref, slot in protocol_slots(_base_intake()).items()
        if slot.type is SlotType.CODE
    }
    assert len(code_slots) == 10
    for ref, slot in code_slots.items():
        assert stack.handler.valuesets[slot.valueset or ""] == _choices(slot), ref


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_a_code_slot_with_no_committed_set_cannot_be_composed(
    profile: VoiceProfile,
) -> None:
    table = _without(load_committed_valuesets(), "vs.chest_pain_character")
    with pytest.raises(CodeSlotUnbound, match=r"chest_pain\.character.*vs\.chest_pain_character"):
        _compose(profile, protocol=_base_intake(), gateway=AnswerTable({}), valuesets=table)


@pytest.mark.parametrize("profile", list(VoiceProfile))
def test_near_miss_an_empty_table_cannot_be_composed_over_base_intake(
    profile: VoiceProfile,
) -> None:
    """The pre-INT-518 state, handed in explicitly: every code slot is named."""
    empty = load_committed_valuesets().model_copy(update={"valuesets": {}})
    with pytest.raises(CodeSlotUnbound) as refused:
        _compose(profile, protocol=_base_intake(), gateway=AnswerTable({}), valuesets=empty)
    for ref in (CHARACTER, RADIATION, "identity_check.subject_role"):
        assert ref in str(refused.value)


# --- 2 · every code slot a red-flag rule reads binds from an authored choice ----------


def test_the_code_slots_red_flag_rules_read_are_character_and_radiation() -> None:
    """A pin on today's scope. A new rule reading a code slot joins the binding
    test below on its own; this line only says which two exist now."""
    assert set(_red_flag_code_slots()) == {CHARACTER, RADIATION}


@pytest.mark.parametrize(
    ("ref", "choice"),
    [(ref, choice) for ref, slot in _red_flag_code_slots().items() for choice in _choices(slot)],
)
def test_every_red_flag_code_slot_binds_from_each_authored_choice(ref: str, choice: str) -> None:
    slot = _red_flag_code_slots()[ref]
    members = _members(load_committed_valuesets())
    schema = slot_output_schema({ref: slot}, members)
    assert schema["properties"]["slots"]["properties"][ref]["properties"]["value"]["enum"] == list(
        _choices(slot)
    )
    raw = _completion({ref: choice})
    result = parse_extraction(raw=raw, slots={ref: slot}, valuesets=members, step_id=ref)
    assert result.flags == ()
    assert [(update.ref, update.value) for update in result.slot_updates] == [(ref, choice)]


@pytest.mark.parametrize("ref", [CHARACTER, RADIATION])
def test_near_miss_without_its_committed_set_a_red_flag_code_slot_cannot_bind(ref: str) -> None:
    slot = _red_flag_code_slots()[ref]
    members = _members(_without(load_committed_valuesets(), slot.valueset or ""))
    with pytest.raises(ExtractionRefused, match="members were not supplied"):
        slot_output_schema({ref: slot}, members)
    raw = _completion({ref: _choices(slot)[0]})
    result = parse_extraction(raw=raw, slots={ref: slot}, valuesets=members, step_id=ref)
    assert result.slot_updates == ()
    assert [flag.reason for flag in result.flags] == [FlagReason.VALUESET_VIOLATION]


@pytest.mark.parametrize("members", [{}, {"vs.chest_pain_character": ()}], ids=["absent", "empty"])
def test_the_composition_check_refuses_exactly_what_the_schema_refuses(
    members: dict[str, tuple[str, ...]],
) -> None:
    slot = _red_flag_code_slots()[CHARACTER]
    assert unbound_code_slots({CHARACTER: slot}, members) == ((CHARACTER, slot.valueset),)
    with pytest.raises(ExtractionRefused):
        slot_output_schema({CHARACTER: slot}, members)


@pytest.mark.parametrize("near", ["baski", "Baskı", "baskı ", "bask"])
def test_near_miss_a_spelling_of_a_member_is_not_a_member(near: str) -> None:
    slot = _red_flag_code_slots()[CHARACTER]
    members = _members(load_committed_valuesets())
    raw = _completion({CHARACTER: near})
    result = parse_extraction(
        raw=raw, slots={CHARACTER: slot}, valuesets=members, step_id=CHARACTER
    )
    assert result.slot_updates == ()
    assert [flag.reason for flag in result.flags] == [FlagReason.VALUESET_VIOLATION]


# --- 3 · a chest-pain RED, end to end through extraction -----------------------------


#: What the patient says at each step, in the order the questions are put.
#: Synthetic Turkish; the model's answer for each step is in the case below.
TRANSCRIPTS: tuple[tuple[str, str], ...] = (
    ("identity_check.subject_role", "Kendim için soruyorum."),
    ("chest_pain.present", "Evet, göğsümde bir rahatsızlık var."),
    (CHARACTER, "Daha çok şöyle bir his."),
    (RADIATION, "Şuraya doğru gidiyor."),
    ("chest_pain.onset_at", "Şu anda var."),
)


def _drive(stack: SessionStack, steps: Sequence[tuple[str, str]]) -> list[WorkState]:
    """Put each question and send its answer the way ``take_turn`` does.

    The ask is recorded through the Talker's ask ledger and the answer through
    its ``submit_utterance`` tool; Layer B's pump applies the ask, then runs the
    Work: vault, registered handler, gateway, parser, engine. The Talker awaits
    none of it (invariant 9).
    """
    states: list[WorkState] = []
    for step_id, transcript in steps:
        stack.session.ask_ledger.note_asked(step_id)
        ticket = stack.session.submit_utterance(step_id, transcript)
        stack.agent.run_pending()
        states.append(stack.agent.record(ticket.work_id).state)
    return states


def _triage(stack: SessionStack) -> TriageEvaluation:
    """The rules engine over the engine's answer state, as the simulator reads it.

    Only ``ASKED_PRESENT`` / ``ASKED_ABSENT`` carry a value; every other state
    reads Unknown (files/12 §1.1). The level comes from
    ``protocols.triage`` alone (invariant 1).
    """
    engine = stack.engine
    answers: dict[str, SlotAnswer] = {}
    for step_id in protocol_slots(_base_intake()):
        state = engine.state_of(step_id)
        if state in (AnswerState.ASKED_PRESENT, AnswerState.ASKED_ABSENT):
            answers[step_id] = SlotAnswer(state=state, values=(engine.value_of(step_id),))
    context = TriageContext(reference_time=engine.reference_time, answers=answers)
    return evaluate_triage(_active_life_threat_rules(), context, RedLocation.REMOTE)


#: The onset is answered as the patient answers it: the authored choice for
#: "Şu anda var.", never a date (INT-522). The runtime binds CD-05's day for
#: it against the session's reference time; a recorded ISO date is refused.
ONSET_CHOICE = "şu anda var"


def _model_answers(character: str, radiation: str) -> dict[str, JsonValue]:
    return {
        "identity_check.subject_role": "kendim için",
        "chest_pain.present": True,
        CHARACTER: character,
        RADIATION: radiation,
        "chest_pain.onset_at": ONSET_CHOICE,
    }


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize(
    ("character", "radiation"),
    [
        pytest.param("baskı", "yok", id="character-alone"),
        pytest.param("başka bir his", "kol", id="radiation-alone"),
    ],
)
def test_a_cardiac_answer_fires_the_k2_red_through_extraction(
    profile: VoiceProfile, character: str, radiation: str
) -> None:
    """Sweating and breathlessness are never asked here: the RED comes from the
    code answer alone, which is exactly what could not bind before INT-518."""
    gateway = AnswerTable(_model_answers(character, radiation))
    stack = _compose(profile, protocol=_base_intake(), gateway=gateway)

    assert _drive(stack, TRANSCRIPTS) == [WorkState.COMPLETED] * len(TRANSCRIPTS)
    assert stack.engine.value_of(CHARACTER) == character
    assert stack.engine.value_of(RADIATION) == radiation
    assert stack.engine.state_of("associated.diaphoresis") is AnswerState.NOT_ASKED
    assert stack.engine.state_of("associated.dyspnoea") is AnswerState.NOT_ASKED

    evaluation = _triage(stack)
    assert evaluation.result.level is TriageLevel.RED
    assert evaluation.ek4 is EK4Level.KIRMIZI_K2
    assert [fire.id for fire in evaluation.result.rules] == [K2]
    assert evaluation.result.register is RedRegister.ALERT
    assert evaluation.result.location is RedLocation.REMOTE
    assert evaluation.action is not None


@pytest.mark.parametrize("profile", list(VoiceProfile))
@pytest.mark.parametrize(
    ("character", "radiation"),
    [
        pytest.param("başka bir his", "yok", id="no-cardiac-feature"),
        pytest.param("yanma", "omuz", id="burning-to-the-shoulder"),
    ],
)
def test_near_miss_a_non_cardiac_answer_binds_and_does_not_fire(
    profile: VoiceProfile, character: str, radiation: str
) -> None:
    """LT-01-N's shape: the same slots, the same pipeline, answers outside the
    rule's sets. Both bind, so the silence is the rule's, not the binder's."""
    gateway = AnswerTable(_model_answers(character, radiation))
    stack = _compose(profile, protocol=_base_intake(), gateway=gateway)

    assert _drive(stack, TRANSCRIPTS) == [WorkState.COMPLETED] * len(TRANSCRIPTS)
    assert stack.engine.value_of(CHARACTER) == character
    assert stack.engine.value_of(RADIATION) == radiation
    assert _triage(stack).result.level is not TriageLevel.RED


def test_the_schema_the_model_answers_is_the_committed_set_for_both_code_slots() -> None:
    """What the constrained decoder is handed for each red-flag code slot is
    the committed set, copied from the authored choices."""
    gateway = AnswerTable(_model_answers("baskı", "yok"))
    stack = _compose(VoiceProfile.TYPED, protocol=_base_intake(), gateway=gateway)
    _drive(stack, TRANSCRIPTS)
    enums: dict[str, list[str]] = {}
    for call in gateway.calls:
        for ref, entry in call.json_schema["properties"]["slots"]["properties"].items():
            value = entry["properties"]["value"]
            if "enum" in value:
                enums[ref] = value["enum"]
    slots = _red_flag_code_slots()
    assert enums[CHARACTER] == list(_choices(slots[CHARACTER]))
    assert enums[RADIATION] == list(_choices(slots[RADIATION]))
