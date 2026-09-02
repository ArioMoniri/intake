"""The headless driver: one persona, one scenario, one session (INT-082).

The simulator drives the **real** components — the INT-081 ``IntakeEngine``,
the INT-091 ``TalkerSession``, and ``protocols.triage.evaluate_triage`` — over
recorded fixtures. There is no LLM, no model, no network, no LiveKit room and
no clock but the session's own ``reference_time``. The persona supplies what
an extraction Work would have returned; :mod:`doubles` supplies the speech
egress; nothing else is faked.

**Where the simulated patient stops.** The driver is the only module in the
package that may reach the triage engine, and it reaches it exactly once, at
the end, over the resolved pack's own rules and the engine's own answer
states. It cannot pass a level in, because :func:`evaluate_triage` does not
take one (CLAUDE.md invariant 1).

**Typed and mock voice are the same session.** Both lanes drive one
``IntakeEngine`` through one loop; the mock-voice lane additionally plugs that
engine into a ``TalkerSession`` and speaks each step through the six tools.
The suite asserts the two lanes reach identical slot state — ADR-010's
keyboard *parity*, tested rather than assumed.

**Hızlı and Detaylı are two resolutions, not two code paths.** files/02 §2
heads its own table *"same engine, different protocol profile"*, so ``mode``
selects which pack the registry resolves and nothing below reads it again.
It has to work that way: ``IntakeEngine`` takes no mode, and files/13 §9.5's
GuardExpr whitelist — where a ``mode`` gate would live — is refused at plan
build (INT-081).

**What the engine drops, the driver computes.** An update the engine declines
to bind leaves no state, no gap and no event, so a patient who volunteers a
red-flag answer three turns late and a patient who never says it produce
identical sessions. :func:`_reconcile` therefore reads each referenced step's
state either side of ``apply_extraction`` and returns the difference as
:class:`UnboundUpdate` — by reference and reason, never by value.

**Nothing here writes anything.** The whole run happens inside
:func:`~doubles.record_disk_writes`, so "raw audio never touches disk"
(invariant 3) is a measurement of the run rather than a claim about the code.
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Mapping, Sequence

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.session import AnswerState
from clinical_schemas.triage import RedLocation
from doubles import (
    SIM_VOICE_ID,
    InMemoryPatientMemory,
    RecordedBackend,
    RecordedClipStore,
    RecordingSink,
    RecordingSynthesizer,
    StepClock,
    record_disk_writes,
    retained_byte_fields,
)
from intake_voice_runtime.clinical_agent import EngineError, IntakeEngine, MustAskCoverage
from intake_voice_runtime.ports import EngineSnapshot
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import NextStep, Step, StepKind
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.insertion import DeliveryDeadlines
from intake_voice_runtime.talker.session import TalkerConfig, TalkerSession
from intake_voice_runtime.talker.tools import RepeatReason, build_talker_tools
from personas import Persona, ScriptedAnswer
from protocol import REFERENCE_TIME, IntakeMode, sim_protocol
from protocols.compile.resolve import ResolvedProtocol
from protocols.triage import SlotAnswer, TriageContext, evaluate_triage
from protocols.triage.engine import TriageEvaluation
from protocols.types import SlotType
from pydantic import Field
from scenarios import Scenario

__all__ = [
    "MAX_TURNS",
    "SimResult",
    "SimTurn",
    "SpokenTurn",
    "Termination",
    "UnboundReason",
    "UnboundUpdate",
    "UnknownSlotInScript",
    "free_text_critical_path_steps",
    "run_scenario",
]

MAX_TURNS = 200
"""Runaway guard, not a turn budget.

files/02 §2's ≤ 18-turn budget collides with its own content list and is an
open **clinical** decision (HUMAN_BLOCKERS HB-C5), so the simulator asserts no
budget at all. This number exists only so a non-terminating engine fails as a
test rather than as a hang, and the suite asserts every scenario ended because
the frontier emptied — never because the guard tripped.
"""

_SESSION_ID = "11111111-2222-4333-8444-555555555555"
_PROTOCOL_HASH_FALLBACK = "0" * 64


class Termination(enum.StrEnum):
    """Why the loop stopped."""

    FRONTIER_EMPTY = "frontier_empty"
    GUARD_TRIPPED = "guard_tripped"


class UnknownSlotInScript(LookupError):
    """A persona named a slot this resolved protocol does not have.

    ``apply_extraction`` ignores an unknown reference in silence, which is
    correct for it — an extraction is untrusted input — and useless here: a
    persona is a fixture, and a fixture whose answer goes nowhere would make
    every assertion built on it pass for the wrong reason.
    """


class UnboundReason(enum.StrEnum):
    """Why an offered slot value did not become session state.

    The set is closed and every member is reached by a persona, because the
    simulator's job on this axis is to say *which* of files/13's rules
    dropped a value rather than that one did. Four of the five are drops;
    :attr:`PREFILL_REOPENED` is the one designed outcome in the list.
    """

    #: The step was never asked, so nothing binds to it (files/13 §9.6 — the
    #: engine under-binds by construction; absorbing a neighbouring answer is
    #: how a note comes to read as elicited what was inferred).
    NEVER_ASKED = "never_asked"
    #: The step's own question already closed with an answer. A later
    #: disclosure or a reversal lands here, and ``AnswerState.CONTESTED`` —
    #: which files/13 §9.3 defines for exactly this and ``coverage`` counts as
    #: covering — is never assigned by anything.
    ALREADY_RESOLVED = "already_resolved"
    #: The engine gave up on the step after two clarifications (files/13
    #: §11.1). An ``UNCLEAR`` slot has left the frontier, so a clear answer
    #: arriving afterwards has nowhere to go.
    ABANDONED = "abandoned"
    #: The step's gate closed while it was pending, so files/13 §11.3
    #: discards the answer rather than storing it. This one is the blueprint
    #: working as written.
    INVALIDATED = "invalidated"
    #: A confirm step was contradicted, so files/09 §3's "full HPI only on
    #: change" re-opened the full ask instead of binding to the confirm. Not
    #: a drop: the question is put again and the answer binds then.
    PREFILL_REOPENED = "prefill_reopened"


class UnboundUpdate(FrozenModel):
    """One offered value that the engine did not record, and why.

    Carries references and a comparison, never the value itself: this object
    is projected into the run record, and CLAUDE.md invariant 6 keeps slot
    values out of anything log-shaped.
    """

    asked_step_id: str = Field(min_length=1, description="The step being answered.")
    ref: str = Field(min_length=1, description="The slot the value was offered for.")
    reason: UnboundReason
    differs_from_bound: bool = Field(
        default=False,
        description="True when the step already held a DIFFERENT value — a "
        "contradiction rather than a repetition.",
    )


class SpokenTurn(FrozenModel):
    """One sentence the agent spoke, as the mock-voice lane recorded it."""

    step_id: str = Field(min_length=1)
    origin_id: str = Field(min_length=1, description="Step id with the re-entry suffix removed.")
    kind: StepKind
    text_tr: str = Field(min_length=1)
    choices_tr: tuple[str, ...] = Field(default=())
    from_clip: bool = Field(default=False)


class RepeatRecord(FrozenModel):
    """One ``request_repeat_or_clarify`` call and what it returned."""

    step_id: str = Field(min_length=1)
    original_text_tr: str = Field(min_length=1)
    text_tr: str = Field(min_length=1)


class SimTurn(FrozenModel):
    """One driver turn: at most one question asked, then what came back."""

    index: int = Field(ge=0)
    asked: str | None = Field(default=None, description="Step id asked this turn, if any.")
    spoken: tuple[SpokenTurn, ...] = Field(default=())
    replies: tuple[ScriptedAnswer, ...] = Field(default=())
    reconciled: tuple[str, ...] = Field(default=())
    work_remaining: int = Field(
        ge=0,
        description="files/13 §9.5's own measure at the end of the turn: unasked plan "
        "steps that are not invalidated, plus queued re-entries not yet put.",
    )


class SimResult(FrozenModel):
    """Everything one scenario run produced. Ids only — never a name, never a
    transcript (CLAUDE.md invariant 6)."""

    scenario_id: str
    persona_id: str
    profile: VoiceProfile
    mode: IntakeMode = Field(
        default=IntakeMode.FAST,
        description="Which protocol profile the registry resolved (files/02 §2).",
    )
    location: RedLocation
    termination: Termination
    turns: tuple[SimTurn, ...] = Field(default=())
    asked: tuple[str, ...] = Field(default=())
    asked_kinds: tuple[StepKind, ...] = Field(default=())
    played: tuple[SpokenTurn, ...] = Field(default=())
    repeats: tuple[RepeatRecord, ...] = Field(default=())
    states: dict[str, AnswerState] = Field(default_factory=dict)
    values: dict[str, JsonValue] = Field(default_factory=dict)
    data_gaps: tuple[str, ...] = Field(default=())
    invalidated: tuple[str, ...] = Field(default=())
    section_done: tuple[str, ...] = Field(default=())
    coverage: MustAskCoverage
    triage: TriageEvaluation
    final_snapshot: EngineSnapshot
    delta_mode: str = Field(default="off")
    proxy_reported: bool = Field(default=False)
    third_party_present: bool = Field(default=False)
    unbound_updates: tuple[UnboundUpdate, ...] = Field(
        default=(),
        description="Values the patient offered that the engine did not record. "
        "Computed by the simulator, because a dropped update leaves no trace in "
        "the engine at all.",
    )
    tool_calls: tuple[str, ...] = Field(default=())
    tool_surface: frozenset[str] = Field(default=frozenset())
    work_ids: tuple[str, ...] = Field(default=())
    awaited_backend: bool = Field(default=False)
    clip_fetches: tuple[str, ...] = Field(default=())
    synthesized: tuple[str, ...] = Field(default=())
    disk_writes: tuple[str, ...] = Field(default=())
    retained_frames: int = Field(default=0, ge=0)
    retained_bytes_in_doubles: int = Field(default=0, ge=0)
    log: tuple[str, ...] = Field(default=())


def free_text_critical_path_steps(protocol: ResolvedProtocol) -> tuple[str, ...]:
    """Steps on the clinical critical path that can only be answered by typing.

    files/02 §3 requires the low-literacy path to run with *"no free text
    anywhere on the critical path"*, and CLAUDE.md invariant 22 forbids free
    numeric text entry there outright. "Critical path" is read here as a slot
    a clinician marked ``must_ask`` or the pack marked ``required`` — the set
    a session cannot legitimately finish without.
    """
    offenders: list[str] = []
    for section in protocol.sections:
        for resolved in section.slots:
            slot = resolved.slot
            if not (slot.must_ask or slot.required):
                continue
            if slot.type not in (SlotType.STRING, SlotType.DECIMAL, SlotType.INTEGER):
                continue
            if slot.choices_tr:
                continue
            offenders.append(f"{section.id}.{resolved.key}")
    return tuple(offenders)


# --- the run ----------------------------------------------------------------


class _Recorder:
    """Mutable bookkeeping for one run; projected into a frozen SimResult."""

    def __init__(self) -> None:
        self.turns: list[SimTurn] = []
        self.asked: list[str] = []
        self.asked_kinds: list[StepKind] = []
        self.played: list[SpokenTurn] = []
        self.repeats: list[RepeatRecord] = []
        self.tool_calls: list[str] = []
        self.work_ids: list[str] = []
        self.unbound: list[UnboundUpdate] = []
        self.log: list[str] = []

    def note(self, event: str, **ids: object) -> None:
        """One log line, built from ids only (CLAUDE.md invariant 6)."""
        rendered = " ".join(f"{key}={value}" for key, value in ids.items())
        self.log.append(f"{event} {rendered}".strip())


def _origin(step_id: str) -> str:
    return step_id.split("/clarify/", 1)[0]


def _plan_step_ids(protocol: ResolvedProtocol) -> tuple[str, ...]:
    return tuple(
        f"{section.id}.{resolved.key}"
        for section in protocol.sections
        for resolved in section.slots
    )


def _work_remaining(engine: IntakeEngine, step_ids: Sequence[str]) -> int:
    invalidated = set(engine.snapshot.invalidated)
    unasked = sum(
        1
        for step_id in step_ids
        if engine.state_of(step_id) is AnswerState.NOT_ASKED and step_id not in invalidated
    )
    queued = sum(1 for step in engine.frontier() if step.kind is StepKind.FOLLOW_UP)
    return unasked + queued


def _triage_context(engine: IntakeEngine, step_ids: Sequence[str]) -> TriageContext:
    """Project the engine's answer state onto what a rule may read.

    Only ``ASKED_PRESENT`` / ``ASKED_ABSENT`` carry a readable value; every
    other state reads Unknown, which is the same three-valued reading
    ``protocols.triage.context`` applies (files/12 §1.1).
    """
    answers: dict[str, SlotAnswer] = {}
    for step_id in step_ids:
        state = engine.state_of(step_id)
        if state in (AnswerState.ASKED_PRESENT, AnswerState.ASKED_ABSENT):
            answers[step_id] = SlotAnswer(state=state, values=(engine.value_of(step_id),))
    return TriageContext(reference_time=engine.reference_time, answers=answers)


def _build_session(
    engine: IntakeEngine,
    protocol: ResolvedProtocol,
    *,
    clip_store: RecordedClipStore,
    synthesizer: RecordingSynthesizer,
    sink: RecordingSink,
    backend: RecordedBackend,
) -> TalkerSession:
    return TalkerSession(
        config=TalkerConfig(
            session_id=_SESSION_ID,
            voice_id=SIM_VOICE_ID,
            profile=VoiceProfile.RESIDENCY_TR,
            protocol_hash=protocol.resolved_protocol_hash or _PROTOCOL_HASH_FALLBACK,
            rule_ids=frozenset(
                rule.id for rule in (*protocol.red_flags, *protocol.life_threat_rules)
            ),
            deadlines=DeliveryDeadlines(),
        ),
        engine=engine,
        backend=backend,
        catalogue=ClipCatalogue.empty(SIM_VOICE_ID),
        clip_store=clip_store,
        synthesizer=synthesizer,
        sink=sink,
        memory=InMemoryPatientMemory(),
        clock=StepClock(),
    )


async def _speak(session: TalkerSession, persona: Persona, step: NextStep, rec: _Recorder) -> None:
    """Speak one step through the Talker, honouring a repeat request."""
    if _origin(step.step_id) in persona.repeat_steps:
        rec.tool_calls.append("request_repeat_or_clarify")
        directive = session.request_repeat_or_clarify(RepeatReason.NOT_HEARD)
        rec.repeats.append(
            RepeatRecord(
                step_id=step.step_id,
                original_text_tr=step.text_tr,
                text_tr=directive.text_tr,
            )
        )
    outcome = await session.speak_step(step)
    rec.played.append(
        SpokenTurn(
            step_id=step.step_id,
            origin_id=_origin(step.step_id),
            kind=step.kind,
            text_tr=outcome.spoken_text,
            choices_tr=step.choices_tr,
            from_clip=outcome.from_clip,
        )
    )


async def _drive(
    *,
    engine: IntakeEngine,
    persona: Persona,
    session: TalkerSession | None,
    rec: _Recorder,
    step_ids: Sequence[str],
) -> Termination:
    """The loop. Ask the frontier head, reconcile, repeat until it empties."""
    held: list[tuple[str, ScriptedAnswer]] = []
    order = {step_id: index for index, step_id in enumerate(persona.reconcile_order)}
    termination = Termination.GUARD_TRIPPED

    while len(rec.turns) < MAX_TURNS:
        offered: Step | NextStep | None
        if session is not None:
            rec.tool_calls.append("protocol_next")
            offered = session.protocol_next()
        else:
            frontier = engine.frontier()
            offered = frontier[0] if frontier else None

        if offered is not None:
            step_id = offered.step_id
            engine.mark_asked(step_id)
            rec.asked.append(step_id)
            rec.asked_kinds.append(offered.kind)
            rec.note("asked", step=step_id, kind=offered.kind.value)
            spoken: tuple[SpokenTurn, ...] = ()
            if session is not None and isinstance(offered, NextStep):
                await _speak(session, persona, offered, rec)
                spoken = (rec.played[-1],)
            reply = persona.reply(step_id)
            if session is not None:
                rec.tool_calls.append("submit_utterance")
                rec.work_ids.append(session.submit_utterance(step_id, reply.transcript_tr).work_id)
            reconciled: tuple[str, ...] = ()
            if _origin(step_id) in persona.hold_reconcile:
                held.append((step_id, reply))
                rec.note("held", step=step_id)
            else:
                rec.unbound.extend(_reconcile(engine, step_id, reply, rec))
                reconciled = (step_id,)
            rec.turns.append(
                SimTurn(
                    index=len(rec.turns),
                    asked=step_id,
                    spoken=spoken,
                    replies=(reply,),
                    reconciled=reconciled,
                    work_remaining=_work_remaining(engine, step_ids),
                )
            )
            continue

        if held:
            held.sort(key=lambda item: order.get(_origin(item[0]), len(order)))
            step_id, reply = held.pop(0)
            rec.unbound.extend(_reconcile(engine, step_id, reply, rec))
            rec.turns.append(
                SimTurn(
                    index=len(rec.turns),
                    replies=(reply,),
                    reconciled=(step_id,),
                    work_remaining=_work_remaining(engine, step_ids),
                )
            )
            continue

        termination = Termination.FRONTIER_EMPTY
        break

    return termination


def _same_value(left: JsonValue, right: JsonValue) -> bool:
    """The engine's own equality: identity of value *and* type.

    ``True == 1`` in Python, and reporting a boolean reversal as "the same
    value offered twice" would hide the contradiction this records.
    """
    return type(left) is type(right) and bool(left == right)


def _unbound_reason(*, before: AnswerState, invalidated: bool, prefilled: bool) -> UnboundReason:
    """Why an offered value did not become state, from the state it met.

    ``invalidated`` is read first and without regard to *when* the step was
    invalidated: files/13 §11.3 discards every answer for a step whose gate
    closed, including the one that arrives several turns later, and reporting
    that as "never asked" would lose the reason it was thrown away.
    """
    if invalidated:
        return UnboundReason.INVALIDATED
    if before is AnswerState.ASKED_PENDING:
        # The only remaining way a pending step refuses a value: it was
        # pre-filled and the answer contradicts the pre-fill, so files/09 §3
        # re-opens the full ask rather than binding to a confirm question.
        # Anything else means the engine's binding rules moved, and a wrong
        # label here would be worse than a failure.
        if not prefilled:
            raise RuntimeError(
                "a pending step refused a value without a pre-fill and without "
                "being invalidated; IntakeEngine's binding rules changed"
            )
        return UnboundReason.PREFILL_REOPENED
    if before is AnswerState.NOT_ASKED:
        return UnboundReason.NEVER_ASKED
    if before is AnswerState.UNCLEAR:
        return UnboundReason.ABANDONED
    return UnboundReason.ALREADY_RESOLVED


def _reconcile(
    engine: IntakeEngine, step_id: str, reply: ScriptedAnswer, rec: _Recorder
) -> tuple[UnboundUpdate, ...]:
    """Layer B's half: apply the recorded extraction. A decline binds nothing.

    ``declines`` deliberately does *not* map to ``AnswerState.DECLINED``: the
    IntakeEngine has no API that reaches it, and inventing one here would be
    the simulator testing a second implementation of the engine.

    Returns what the engine **did not** record. That half is not observable
    from the engine — an update it drops leaves no state, no gap and no event
    — so the simulator computes it by reading each referenced step's state
    either side of the call. Without it, a patient volunteering a red-flag
    answer three turns late and a patient never saying it produce identical
    sessions, and only one of those is a fact about the product.
    """
    updates: Mapping[str, JsonValue] = (
        {} if (reply.declines or reply.clarification_needed) else reply.slot_updates
    )
    before: dict[str, AnswerState] = {}
    prior: dict[str, JsonValue] = {}
    prefilled: dict[str, bool] = {}
    for ref in updates:
        try:
            before[ref] = engine.state_of(ref)
        except EngineError as exc:
            raise UnknownSlotInScript(
                f"{step_id}: the script offers {ref!r}, which this resolved protocol "
                "has no step for — apply_extraction would ignore it in silence"
            ) from exc
        prior[ref] = engine.value_of(ref)
        prefilled[ref] = any(fill.slot_ref == ref for fill in engine.delta.prefills)

    engine.apply_extraction(step_id, updates, reply.clarification_needed)

    unbound: list[UnboundUpdate] = []
    invalidated = set(engine.snapshot.invalidated)
    for ref, offered in updates.items():
        state = engine.state_of(ref)
        if state in (AnswerState.ASKED_PRESENT, AnswerState.ASKED_ABSENT) and _same_value(
            engine.value_of(ref), offered
        ):
            continue
        unbound.append(
            UnboundUpdate(
                asked_step_id=step_id,
                ref=ref,
                reason=_unbound_reason(
                    before=before[ref],
                    invalidated=ref in invalidated,
                    prefilled=prefilled[ref],
                ),
                differs_from_bound=prior[ref] is not None and not _same_value(prior[ref], offered),
            )
        )
    # Rendered as 0/1 rather than True/False: a log line is compared against
    # every bound slot value in the suite, and a boolean slot answer spelled
    # the same way as a flag would make that comparison meaningless. The
    # dropped updates are logged by REF and REASON only, never by value.
    rec.note(
        "reconciled",
        step=step_id,
        clarify=int(reply.clarification_needed),
        declined=int(reply.declines),
        unbound=len(unbound),
    )
    for update in unbound:
        rec.note("update_dropped", step=step_id, ref=update.ref, reason=update.reason.value)
    return tuple(unbound)


def run_scenario(
    scenario: Scenario,
    persona: Persona,
    *,
    profile: VoiceProfile,
    location: RedLocation | None = None,
    mode: IntakeMode = IntakeMode.FAST,
) -> SimResult:
    """Run one scenario over one persona, headless, in one profile and mode.

    ``mode`` selects which pack the registry resolves — files/02 §2's *"same
    engine, different protocol profile"* — and nothing else. There is no
    branch below that reads it, because the engine has no mode to read.
    """
    protocol = sim_protocol(mode)  # cached before the probe: resolving reads files
    step_ids = _plan_step_ids(protocol)
    resolved_location = scenario.location if location is None else location
    rec = _Recorder()
    rec.note("session_start", scenario=scenario.scenario_id, persona=persona.persona_id)

    engine = IntakeEngine(
        protocol=protocol,
        reference_time=REFERENCE_TIME,
        overlay_facts=persona.overlay,
    )
    clip_store = RecordedClipStore()
    synthesizer = RecordingSynthesizer()
    sink = RecordingSink()
    backend = RecordedBackend()
    session: TalkerSession | None = None
    if profile is VoiceProfile.RESIDENCY_TR:
        session = _build_session(
            engine,
            protocol,
            clip_store=clip_store,
            synthesizer=synthesizer,
            sink=sink,
            backend=backend,
        )

    with record_disk_writes() as writes:
        termination = asyncio.run(
            _drive(
                engine=engine,
                persona=persona,
                session=session,
                rec=rec,
                step_ids=step_ids,
            )
        )

    triage = evaluate_triage(
        [*protocol.red_flags, *protocol.life_threat_rules],
        _triage_context(engine, step_ids),
        resolved_location,
    )
    rec.note("session_end", termination=termination.value, turns=len(rec.turns))

    return SimResult(
        scenario_id=scenario.scenario_id,
        persona_id=persona.persona_id,
        profile=profile,
        mode=mode,
        location=resolved_location,
        termination=termination,
        turns=tuple(rec.turns),
        asked=tuple(rec.asked),
        asked_kinds=tuple(rec.asked_kinds),
        played=tuple(rec.played),
        repeats=tuple(rec.repeats),
        states={step_id: engine.state_of(step_id) for step_id in step_ids},
        values={
            step_id: engine.value_of(step_id)
            for step_id in step_ids
            if engine.value_of(step_id) is not None
        },
        data_gaps=engine.data_gaps,
        invalidated=engine.snapshot.invalidated,
        section_done=engine.section_done,
        coverage=engine.must_ask_coverage(),
        triage=triage,
        final_snapshot=engine.snapshot,
        delta_mode=engine.delta.mode.value,
        proxy_reported=persona.proxy_reported,
        third_party_present=persona.third_party_present,
        unbound_updates=tuple(rec.unbound),
        tool_calls=tuple(rec.tool_calls),
        tool_surface=build_talker_tools(session).names if session else frozenset(),
        work_ids=tuple(rec.work_ids),
        awaited_backend=_awaited_backend(backend),
        clip_fetches=tuple(clip_store.served),
        synthesized=tuple(synthesizer.requests),
        disk_writes=tuple(writes),
        retained_frames=session.retained_frames() if session else 0,
        retained_bytes_in_doubles=retained_byte_fields(clip_store, synthesizer, sink, backend),
        log=tuple(rec.log),
    )


def _awaited_backend(backend: RecordedBackend) -> bool:
    """Whether any Backend Work port member could have been awaited.

    ADR-009 makes this structural: no member of ``WorkSubmitter`` is a
    coroutine function, so there is no expression the Talker could write that
    would wait on Backend Work. Recorded per run so the simulator states it
    rather than assuming it.
    """
    members = (backend.submit, backend.cancel, backend.drain_results)
    return any(asyncio.iscoroutinefunction(member) for member in members)
