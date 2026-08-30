"""The two-lane parity harness for INT-096.

``tests/sim`` (INT-082) already drives both profiles end to end and this file
does not duplicate that suite — it is not imported here and it is not edited.
What it cannot do is what INT-096 is about: ``tests/sim``'s ``typed`` lane is
*the absence of a Talker*, so it proves that the engine is channel-neutral
but says nothing about the typed lane's own surface — the displayed prompt,
the answer affordance, the kill switch. This harness drives the real
:class:`~intake_voice_runtime.typed.session.TypedSession` against a real
``TalkerSession`` over one shared ``IntakeEngine``, which is the only way the
mid-session switch can be exercised at all.

**The protocol is the committed compiler fixture**, resolved through the
production compiler — ``tests/fixtures/protocols/compile/tree``, the same tree
``conftest.py`` already builds the clip-cache bundle from. Nothing clinical is
authored here: every string in that tree is synthetic (files/04 §7), and the
one mutation this module makes is spelled out in
:func:`parity_protocol`.

Every double is in-memory and none of them opens a file, dials a network,
loads a model or starts a room (CLAUDE.md invariant 17 puts mocks in tests
only). :func:`record_disk_writes` watches the syscall surface for the whole
run, so *"raw audio is never written to disk"* is a measurement of the run
rather than a claim about the code.
"""

from __future__ import annotations

import asyncio
import builtins
import enum
import io
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation
from intake_voice_runtime.clinical_agent import IntakeEngine, MustAskCoverage
from intake_voice_runtime.ports import (
    EngineSnapshot,
    PatientMemoryKey,
    PatientRecord,
    WorkRequest,
    WorkState,
    WorkTicket,
    work_key,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import NextStep, StepKind
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.insertion import DeliveryDeadlines
from intake_voice_runtime.talker.policy_guard import PolicyGuard
from intake_voice_runtime.talker.session import TalkerConfig, TalkerSession
from intake_voice_runtime.typed.affordance import slot_facts
from intake_voice_runtime.typed.render import TypedPrompt
from intake_voice_runtime.typed.session import TypedConfig, TypedSession
from intake_voice_runtime.typed.switch import LaneSwitch, LaneSwitchReason, LaneSwitchRecord
from protocols.bindings import load_opt
from protocols.cli import load_registry
from protocols.compile import load_life_threat_set
from protocols.compile.resolve import (
    ResolvedProtocol,
    ResolvedSection,
    ResolvedSlot,
    resolve_protocol,
)
from protocols.dsl import Slot
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from protocols.triage.engine import TriageEvaluation
from protocols.types import Delivery, SlotType
from pydantic import Field

__all__ = [
    "ANCHOR_STEP",
    "MAX_TURNS",
    "NUMERIC_STEP",
    "RED_RULE_ID",
    "PARITY_SESSION_ID",
    "PARITY_VOICE_ID",
    "LaneOutcome",
    "Reply",
    "Script",
    "Termination",
    "free_numeric_protocol",
    "parity_protocol",
    "record_disk_writes",
    "retained_byte_fields",
    "run_lane",
]

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_FIXTURES = _REPO / "tests" / "fixtures" / "protocols" / "compile"
_TREE = _FIXTURES / "tree"
_LIFE_THREAT = _FIXTURES / "life_threat_signed.yaml"
_TEMPLATE = _REPO / "packages" / "protocols" / "openehr" / "previsit_intake.v1.opt"

PACK_ID = "base.derlenebilir"
PARITY_VOICE_ID = "residency-tr-sentetik"
PARITY_SESSION_ID = "11111111-2222-4333-8444-555555555555"
REFERENCE_TIME = datetime(2026, 8, 30, 9, 0, tzinfo=UTC)
"""The session's ``now`` (files/13 §9.2): stamped once, never a wall clock."""

MAX_TURNS = 200
"""A runaway guard, not a turn budget — files/02 §2's budget is an open
clinical decision (HUMAN_BLOCKERS HB-C5). Every run asserts it terminated
because the frontier emptied, never because this tripped."""

NUMERIC_STEP = "ziyaret.sure_dakika"
ANCHOR_STEP = "ziyaret.olay_tarihi"
RED_RULE_ID = "rf.sentetik_kirmizi"
_PROTOCOL_HASH_FALLBACK = "0" * 64


class Termination(enum.StrEnum):
    FRONTIER_EMPTY = "frontier_empty"
    GUARD_TRIPPED = "guard_tripped"


# --- the protocol ------------------------------------------------------------------


@lru_cache(maxsize=1)
def free_numeric_protocol() -> ResolvedProtocol:
    """The committed fixture, unmutated — and it is the negative control.

    ``ziyaret.sure_dakika`` is ``type: quantity``, ``required: true`` and
    carries no ``choices_tr``: a numeric slot on the clinical critical path
    whose only possible typed answer would be a number the patient types.
    CLAUDE.md invariant 22 forbids exactly that, so the typed lane must
    refuse to render it rather than fall back to a text field.
    """
    return resolve_protocol(
        pack_id=PACK_ID,
        registry=load_registry(_TREE),
        life_threat=load_life_threat_set(_LIFE_THREAT),
        template=load_opt(_TEMPLATE),
    )


@lru_cache(maxsize=1)
def parity_protocol() -> ResolvedProtocol:
    """The same document, with the two things the fixture cannot exercise fixed.

    Both mutations are mechanical and neither touches clinical semantics.

    1. **``ziyaret.sure_dakika`` gets two discrete answer labels.** That is
       what turns a free numeric field into the chip set files/00 §2 requires
       (*"doses use ``tam``/``yarım``/``çeyrek`` chips"*). The labels are
       synthetic fixture tokens in the same register as the rest of the tree
       ("Sentetik kırmızı kural", "mavi"/"yeşil") and carry no clinical
       meaning; a **real** pack's chip set for a numeric critical-path slot is
       clinical content awaiting sign-off (HUMAN_BLOCKERS HB-C6, which names
       ``weight_kg`` and its ``choices_tr[]`` explicitly, and HB-C11).

    2. **A dated tense anchor is added and the RED rule is re-anchored to
       it.** The committed rule declares ``tense_anchor: sure_dakika`` — a
       **bare** key that matches no slot reference in the pack, whose own
       slots are section-qualified — so files/12 §2.4's temporal guard reads
       Unknown for every session and ``rf.sentetik_kirmizi`` can never fire.
       Without a firing RED a near-miss negative control proves nothing, so
       the anchor is pointed at a synthetic ``date`` slot here. The rule's
       level, predicate, register, source and per-location actions are
       untouched. **The bare anchor in the committed fixture is a finding, not
       something this harness is entitled to fix** — see docs/evidence/INT-096.md.
    """
    base = free_numeric_protocol()
    anchor = ResolvedSlot(
        section_id="ziyaret",
        key="olay_tarihi",
        fhir_link_id="ziyaret.olay_tarihi",
        slot=Slot(
            type=SlotType.DATE,
            required=False,
            must_ask=False,
            ask_tr="Sentetik olay tarihi sorusu.",
            openehr_deferred_reason=(
                "synthetic anchor added by the INT-096 parity harness; it is never "
                "compiled, served or exported"
            ),
        ),
        delivery=Delivery.VOICE,
        openehr_deferred_reason=(
            "synthetic anchor added by the INT-096 parity harness; it is never "
            "compiled, served or exported"
        ),
    )
    sections = tuple(
        ResolvedSection(
            id=section.id,
            delivery=section.delivery,
            voice=section.voice,
            questionnaires=section.questionnaires,
            allow_paraphrase=section.allow_paraphrase,
            slots=(
                (*(_chipped(resolved) for resolved in section.slots), anchor)
                if section.id == "ziyaret"
                else section.slots
            ),
        )
        for section in base.sections
    )
    red_flags = tuple(
        rule.model_copy(update={"tense_anchor": ANCHOR_STEP}) if rule.id == RED_RULE_ID else rule
        for rule in base.red_flags
    )
    return base.model_copy(update={"sections": sections, "red_flags": red_flags})


def _chipped(resolved: ResolvedSlot) -> ResolvedSlot:
    """Give the numeric critical-path slot the discrete labels it lacks."""
    if f"{resolved.section_id}.{resolved.key}" != NUMERIC_STEP:
        return resolved
    return resolved.model_copy(
        update={
            "slot": resolved.slot.model_copy(
                update={"choices_tr": ("sentetik kısa", "sentetik uzun")}
            )
        }
    )


def plan_step_ids(protocol: ResolvedProtocol) -> tuple[str, ...]:
    return tuple(
        f"{section.id}.{resolved.key}"
        for section in protocol.sections
        for resolved in section.slots
    )


def slot_of(protocol: ResolvedProtocol, step_id: str) -> ResolvedSlot:
    for section in protocol.sections:
        for resolved in section.slots:
            if f"{section.id}.{resolved.key}" == step_id:
                return resolved
    raise LookupError(step_id)


# --- the answer script -------------------------------------------------------------


class Reply(FrozenModel):
    """One recorded extraction — what Layer B would have returned."""

    entry: str = Field(min_length=1, description="What the patient typed or said.")
    slot_updates: dict[str, JsonValue] = Field(default_factory=dict)
    clarification_needed: bool = Field(default=False)
    declines: bool = Field(default=False)


class Script(FrozenModel):
    """Origin step id → the replies it produces, in order.

    The last reply repeats, so a step asked a third time (it cannot be — two
    clarifications is the ceiling, files/13 §11.1) would still be defined.
    """

    replies: dict[str, tuple[Reply, ...]] = Field(default_factory=dict)
    default_entry: str = Field(default="sentetik yanıt")

    def reply_for(self, step_id: str, attempt: int) -> Reply:
        options = self.replies.get(origin_of(step_id))
        if not options:
            return Reply(entry=self.default_entry)
        return options[min(attempt, len(options) - 1)]


def origin_of(step_id: str) -> str:
    return step_id.split("/clarify/", 1)[0]


# --- doubles -----------------------------------------------------------------------


class StepClock:
    """Deterministic time: one millisecond per read, no wall clock."""

    def __init__(self) -> None:
        self._ms = 0.0

    def now_ms(self) -> float:
        self._ms += 1.0
        return self._ms

    async def sleep(self, seconds: float) -> None:
        self._ms += max(seconds, 0.0) * 1000.0


@dataclass
class RecordedBackend:
    """Layer B seen from Layer A. No member of this port is awaitable."""

    submitted: list[WorkRequest] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    def submit(self, request: WorkRequest) -> WorkTicket:
        self.submitted.append(request)
        return WorkTicket(work_id=work_key(request), state=WorkState.QUEUED)

    def cancel(self, work_id: str, reason: str) -> WorkTicket:
        self.cancelled.append(work_id)
        return WorkTicket(work_id=work_id, state=WorkState.CANCELLED)

    def drain_results(self) -> tuple[object, ...]:
        return ()


@dataclass
class RecordedClipStore:
    """Clips are synthetic *agent* speech, never patient audio (inv. 9)."""

    served: list[str] = field(default_factory=list)

    def fetch(self, clip_id: str) -> bytes:
        self.served.append(clip_id)
        return clip_id.encode("utf-8")[:32]


@dataclass
class RecordingSynthesizer:
    """The TTS gateway stand-in: records the text, returns opaque frames."""

    requests: list[str] = field(default_factory=list)

    def synthesize(self, text_tr: str, voice_id: str) -> bytes:
        self.requests.append(text_tr)
        return f"{voice_id}:{len(text_tr)}".encode()[:32]


@dataclass
class RecordingSink:
    """Where agent speech goes. Keeps a label and a length, never frames."""

    played: list[tuple[str, int]] = field(default_factory=list)
    cancels: int = 0

    async def play(self, frames: bytes, *, label: str = "") -> None:
        self.played.append((label, len(frames)))

    async def cancel(self) -> None:
        self.cancels += 1


@dataclass
class InMemoryPatientMemory:
    """The closed, non-clinical key set of files/03 §4.2."""

    store: dict[str, str] = field(default_factory=dict)

    def recall(self, key: str) -> PatientRecord | None:
        value = self.store.get(key)
        return None if value is None else PatientRecord(key=PatientMemoryKey(key), value=value)

    def remember(self, key: str, value: str) -> PatientRecord:
        self.store[key] = value
        return PatientRecord(key=PatientMemoryKey(key), value=value)

    def forget(self, key: str) -> None:
        self.store.pop(key, None)


def retained_byte_fields(*objects: object) -> int:
    """How many bytes-like attributes these objects still hold — counted, not
    asserted, so a future field that *did* retain audio would be caught."""
    total = 0
    for obj in objects:
        state = getattr(obj, "__dict__", None)
        if state is None:
            continue
        total += sum(1 for value in state.values() if isinstance(value, bytes | bytearray))
    return total


_WRITE_MODES = frozenset("wxa+")


@contextmanager
def record_disk_writes() -> Iterator[list[str]]:
    """Record every write-mode file open made inside the block.

    Three entry points, because a write reaches the filesystem through any of
    them: ``builtins.open``, ``io.open`` (what ``pathlib`` calls — a separate
    module attribute even though it is the same object) and ``os.open``.
    """
    writes: list[str] = []
    real_open = builtins.open
    real_io_open = io.open
    real_os_open = os.open

    def watched_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if _WRITE_MODES & set(mode):
            writes.append(f"open:{file}:{mode}")
        return real_io_open(file, mode, *args, **kwargs)

    def watched_os_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND):
            writes.append(f"os.open:{path}:{flags}")
        return real_os_open(path, flags, *args, **kwargs)

    builtins.open = watched_open
    io.open = watched_open
    os.open = watched_os_open
    try:
        yield writes
    finally:
        builtins.open = real_open
        io.open = real_io_open
        os.open = real_os_open


# --- the run -----------------------------------------------------------------------


class LaneOutcome(FrozenModel):
    """One run, projected. Ids only — never a transcript (invariant 6)."""

    started_as: VoiceProfile
    ended_as: VoiceProfile
    termination: Termination
    asked: tuple[str, ...] = Field(default=())
    asked_kinds: tuple[StepKind, ...] = Field(default=())
    prompts: tuple[TypedPrompt, ...] = Field(default=())
    played: tuple[str, ...] = Field(default=())
    synthesized: tuple[str, ...] = Field(default=())
    clip_fetches: tuple[str, ...] = Field(default=())
    states: dict[str, AnswerState] = Field(default_factory=dict)
    values: dict[str, JsonValue] = Field(default_factory=dict)
    data_gaps: tuple[str, ...] = Field(default=())
    coverage: MustAskCoverage
    triage: TriageEvaluation
    snapshot: EngineSnapshot
    tool_calls: tuple[str, ...] = Field(default=())
    work_ids: tuple[str, ...] = Field(default=())
    switch: LaneSwitchRecord | None = Field(default=None)
    disk_writes: tuple[str, ...] = Field(default=())
    retained_bytes: int = Field(default=0, ge=0)
    turns: int = Field(default=0, ge=0)

    @property
    def ek4_severity(self) -> int:
        """Position in the EK-4 lattice, so two runs can be compared without
        the suite re-deriving an acuity order of its own."""
        return self.triage.ek4.severity


def _triage_context(engine: IntakeEngine, step_ids: tuple[str, ...]) -> TriageContext:
    answers: dict[str, SlotAnswer] = {}
    for step_id in step_ids:
        state = engine.state_of(step_id)
        if state in (AnswerState.ASKED_PRESENT, AnswerState.ASKED_ABSENT):
            answers[step_id] = SlotAnswer(state=state, values=(engine.value_of(step_id),))
    return TriageContext(reference_time=engine.reference_time, answers=answers)


def build_talker(
    engine: IntakeEngine,
    protocol: ResolvedProtocol,
    *,
    clip_store: RecordedClipStore,
    synthesizer: RecordingSynthesizer,
    sink: RecordingSink,
    backend: RecordedBackend,
    memory: InMemoryPatientMemory,
    clock: StepClock,
) -> TalkerSession:
    return TalkerSession(
        config=TalkerConfig(
            session_id=PARITY_SESSION_ID,
            voice_id=PARITY_VOICE_ID,
            profile=VoiceProfile.RESIDENCY_TR,
            protocol_hash=protocol.resolved_protocol_hash or _PROTOCOL_HASH_FALLBACK,
            rule_ids=frozenset(
                rule.id for rule in (*protocol.red_flags, *protocol.life_threat_rules)
            ),
            deadlines=DeliveryDeadlines(),
        ),
        engine=engine,
        backend=backend,
        catalogue=ClipCatalogue.empty(PARITY_VOICE_ID),
        clip_store=clip_store,
        synthesizer=synthesizer,
        sink=sink,
        memory=memory,
        clock=clock,
    )


def build_typed(
    engine: IntakeEngine,
    protocol: ResolvedProtocol,
    *,
    backend: RecordedBackend,
    memory: InMemoryPatientMemory,
    clock: StepClock,
    policy_guard: PolicyGuard | None = None,
) -> TypedSession:
    return TypedSession(
        config=TypedConfig(
            session_id=PARITY_SESSION_ID,
            protocol_hash=protocol.resolved_protocol_hash or _PROTOCOL_HASH_FALLBACK,
            rule_ids=frozenset(
                rule.id for rule in (*protocol.red_flags, *protocol.life_threat_rules)
            ),
        ),
        engine=engine,
        backend=backend,
        memory=memory,
        clock=clock,
        facts=slot_facts(protocol),
        policy_guard=policy_guard,
    )


def run_lane(
    protocol: ResolvedProtocol,
    script: Script,
    *,
    profile: VoiceProfile,
    location: RedLocation = RedLocation.REMOTE,
    switch_after: int | None = None,
    switch_reason: LaneSwitchReason = LaneSwitchReason.ABORT_VOICE,
) -> LaneOutcome:
    """Drive one intake to the empty frontier in one (or two) lanes.

    ``switch_after`` flips the lane once, after that many asks — the kill
    switch, exercised mid-session. Both lanes drive the **same**
    ``IntakeEngine`` instance, which is why no bound slot value can be lost by
    the flip: there is nowhere for it to be lost from.
    """
    step_ids = plan_step_ids(protocol)
    engine = IntakeEngine(protocol=protocol, reference_time=REFERENCE_TIME)
    clock = StepClock()
    backend = RecordedBackend()
    memory = InMemoryPatientMemory()
    clip_store = RecordedClipStore()
    synthesizer = RecordingSynthesizer()
    sink = RecordingSink()
    switch = LaneSwitch(profile=profile)
    talker = (
        build_talker(
            engine,
            protocol,
            clip_store=clip_store,
            synthesizer=synthesizer,
            sink=sink,
            backend=backend,
            memory=memory,
            clock=clock,
        )
        if profile is VoiceProfile.RESIDENCY_TR
        else None
    )
    typed = build_typed(engine, protocol, backend=backend, memory=memory, clock=clock)

    asked: list[str] = []
    asked_kinds: list[StepKind] = []
    prompts: list[TypedPrompt] = []
    tool_calls: list[str] = []
    work_ids: list[str] = []
    attempts: dict[str, int] = {}
    termination = Termination.GUARD_TRIPPED
    turns = 0

    async def drive() -> Termination:
        nonlocal turns, termination
        while turns < MAX_TURNS:
            voiced = switch.profile is VoiceProfile.RESIDENCY_TR and talker is not None
            tool_calls.append("protocol_next")
            step: NextStep | None = (
                talker.protocol_next() if voiced and talker else typed.protocol_next()
            )
            if step is None:
                return Termination.FRONTIER_EMPTY
            engine.mark_asked(step.step_id)
            asked.append(step.step_id)
            asked_kinds.append(step.kind)
            if voiced and talker is not None:
                await talker.speak_step(step)
            else:
                prompts.append(typed.prompt(step))
            attempt = attempts.get(origin_of(step.step_id), 0)
            attempts[origin_of(step.step_id)] = attempt + 1
            reply = script.reply_for(step.step_id, attempt)
            tool_calls.append("submit_utterance")
            ticket = (
                talker.submit_utterance(step.step_id, reply.entry)
                if voiced and talker is not None
                else typed.submit_utterance(step.step_id, reply.entry)
            )
            work_ids.append(ticket.work_id)
            engine.apply_extraction(
                step.step_id,
                {} if reply.declines else reply.slot_updates,
                reply.clarification_needed,
            )
            turns += 1
            if switch_after is not None and len(asked) == switch_after:
                switch.to_typed(switch_reason, now_ms=clock.now_ms())
        return Termination.GUARD_TRIPPED

    with record_disk_writes() as writes:
        termination = asyncio.run(drive())

    triage = evaluate_triage(
        [*protocol.red_flags, *protocol.life_threat_rules],
        _triage_context(engine, step_ids),
        location,
    )
    return LaneOutcome(
        started_as=profile,
        ended_as=switch.profile,
        termination=termination,
        asked=tuple(asked),
        asked_kinds=tuple(asked_kinds),
        prompts=tuple(prompts),
        played=tuple(label for label, _ in sink.played),
        synthesized=tuple(synthesizer.requests),
        clip_fetches=tuple(clip_store.served),
        states={step_id: engine.state_of(step_id) for step_id in step_ids},
        values={
            step_id: engine.value_of(step_id)
            for step_id in step_ids
            if engine.value_of(step_id) is not None
        },
        data_gaps=engine.data_gaps,
        coverage=engine.must_ask_coverage(),
        triage=triage,
        snapshot=engine.snapshot,
        tool_calls=tuple(tool_calls),
        work_ids=tuple(work_ids),
        switch=switch.record,
        disk_writes=tuple(writes),
        retained_bytes=retained_byte_fields(typed, clip_store, synthesizer, sink, backend)
        + (retained_byte_fields(talker) if talker is not None else 0),
        turns=turns,
    )
