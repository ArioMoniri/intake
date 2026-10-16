"""The composition root — where Layer A and Layer B are actually joined.

docs/evidence/INT-094.md's headline finding was that they were not: *"the
Layer A ↔ Layer B loop does not close on this tree, at three joints … a
composed session cannot take one turn carrying a transcript."* Each unit was
correct and each proof was good; nothing put them together, and so INT-095 had
no turn to smoke-test against real adapters.

This module is that join, and it is the **only** place in ``services/`` that
calls ``register_state``. That is deliberate and asserted: a queue that
registered its own handler would be a queue that chose a model, and a handler
that registered itself would make "which extraction is this session running?"
a question you answer by grepping rather than by reading one function.

What it wires, in the order the three joints were open:

1. **The handler.** ``WorkType.EXTRACT_SLOTS`` →
   :class:`~intake_voice_runtime.extraction.handler.ExtractSlotsHandler`,
   bound to a gateway, the session's transcript vault and a §4.9.1 pin.
2. **The ask ledger.** ``TalkerSession.ask_ledger`` resolves to the
   ``BackendAgent``, so the step the Talker speaks is marked ``ASKED_PENDING``
   by the Backend's own pump, under the engine lock, before the next Work runs.
3. **The transcript channel.** One :class:`SessionTranscripts` per session:
   the Talker holds its deposit half, the handler holds its source half, and
   the queue carries neither.

``parse_document`` is **not** registered. Its background handler is INT-121,
and ``UnregisteredWorkType`` at ``submit`` is the fail-closed state CLAUDE.md
asks for while it does not exist — build the mechanism, wire the gate, leave
the content empty.

**The RED path is not wired here either.** ``TalkerSession.preemption`` stays
``None``, so a rules-engine RED reaching this session raises
``RedPathNotWired`` rather than continuing the intake past a life threat
(invariant 21). Binding it needs the pre-positioned RED scripts, which are
compiled clinical content and blocked on HB-C1.

**The clinician route is wired, and it is required** (INT-406, invariant 49).
The clinic hearing of a RED must not wait on the scripts that tell the
patient, so ``clinic`` — the :class:`~intake_voice_runtime.talker.red_path.ClinicNotifier`
into the Safety inbox — is a required argument of both roots and is bound to
the ``BackendAgent``, which tells it of every rules-engine RED as it settles.
A session with no route to the clinic cannot be composed.

**Extraction gets the committed value-set table** (INT-518, GitHub #884).
Both roots used to hand the handler ``dict(valuesets or {})`` and no
production caller passed a table, so every Work that declared a code slot was
refused, and the slot then stayed awaiting, so every later Work was refused
too: a session bound nothing after its first question, and
``chest_pain.character`` / ``chest_pain.radiation``, the code inputs of the
active life-threat rules, never bound at all. Omitted, ``valuesets`` is now
:func:`protocols.valuesets.load_committed_valuesets`, handed to the engine
(whose plan build re-checks every gate against it) and to the handler (which
refuses a code slot with no set when the session is composed). A table passed
in is used as given, and is held to the same two checks.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from clinical_schemas.overlay import PatientOverlay
from protocols.compile.resolve import ResolvedProtocol
from protocols.dsl import Slot
from protocols.valuesets import ValueSetTable, load_committed_valuesets

from intake_voice_runtime.adapters.pins import ModelPin, ModelStackRow, resolve_pin
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import BackendAgent
from intake_voice_runtime.extraction.gateway import ExtractionGateway
from intake_voice_runtime.extraction.handler import ExtractSlotsHandler
from intake_voice_runtime.metering import (
    MeteredExtractionGateway,
    MeteredSpeechSynthesizer,
    SessionMeter,
)
from intake_voice_runtime.ports import (
    AudioSink,
    ClipStore,
    Clock,
    PatientMemoryStore,
    ScreenSink,
    SpeechSynthesizer,
    SystemClock,
    WorkType,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.delivery import DeliveryDeadlines
from intake_voice_runtime.talker.red_path import ClinicNotifier
from intake_voice_runtime.talker.session import TalkerConfig, TalkerSession
from intake_voice_runtime.transcript import SessionTranscripts
from intake_voice_runtime.typed.affordance import SlotFacts, slot_facts

__all__ = [
    "ResidencyStack",
    "SessionStack",
    "build_residency_tr_session",
    "build_typed_session",
    "protocol_slots",
]


def protocol_slots(protocol: ResolvedProtocol) -> dict[str, Slot]:
    """``{step_id: Slot}`` for every slot in a resolved protocol.

    The key is ``<section>.<slot>`` — the same dotted reference
    ``build_plan`` mints for a step id, a gate atom spells and a red-flag
    predicate spells (files/03 §6). One spelling everywhere is what lets the
    extraction schema's refs and the engine's binding refs be compared by
    equality rather than by prefix (files/03 §4.9.6 — ``üre`` is never
    substring-matched).
    """
    return {
        f"{section.id}.{resolved.key}": resolved.slot
        for section in protocol.sections
        for resolved in section.slots
    }


@dataclass
class SessionStack:
    """One composed session: the three layers, and the joints between them.

    **One dataclass for both profiles, and that is the parity claim in a
    type.** Every field here is profile-independent — the engine, the queue,
    the vault, the handler, the extraction pin — because a profile is a
    transport and a transport is inside ``session``. A ``TypedStack`` beside
    this one would be six identical fields and an invitation to make the
    seventh differ.
    """

    engine: IntakeEngine
    agent: BackendAgent
    session: TalkerSession
    transcripts: SessionTranscripts
    handler: ExtractSlotsHandler
    extraction_pin: ModelPin
    #: Every slot's typed affordance (INT-096). Carried on both profiles: a
    #: ``residency_tr`` session is a kill-switch target, so the question "can
    #: this pack be finished on a keyboard?" has to be answerable before the
    #: switch is pulled, not after.
    slot_affordances: Mapping[str, SlotFacts] = field(default_factory=dict)
    #: The session's cost ledger, or ``None`` where the caller supplied no
    #: meter (INT-101). ``None`` means *nothing is metered and nothing is
    #: refused* — the state of every caller that predates this issue — and it
    #: is a visible ``None`` rather than a meter this function invented,
    #: because the tenant and branch labels are the caller's to supply and a
    #: guessed label is a wrong dimension on a real series.
    meter: SessionMeter | None = None

    @property
    def profile(self) -> VoiceProfile:
        """Which transport is in force — read from the session, never stored
        beside it, because the kill switch changes it mid-run."""
        return self.session.config.profile


#: The name INT-095 gave the stack, kept so its evidence and its callers still
#: read true. There was only ever one shape; INT-096 gave it the name it has.
ResidencyStack = SessionStack


def build_residency_tr_session(
    *,
    protocol: ResolvedProtocol,
    reference_time: datetime,
    session_id: str,
    voice_id: str,
    protocol_hash: str,
    gateway: ExtractionGateway,
    synthesizer: SpeechSynthesizer,
    clip_store: ClipStore,
    sink: AudioSink,
    memory: PatientMemoryStore,
    tenant_id: str,
    clinic: ClinicNotifier,
    clock: Clock | None = None,
    catalogue: ClipCatalogue | None = None,
    deadlines: DeliveryDeadlines | None = None,
    rule_ids: frozenset[str] = frozenset(),
    valuesets: ValueSetTable | None = None,
    overlay_facts: PatientOverlay | None = None,
    extraction_row: ModelStackRow = ModelStackRow.TALKER_LLM,
    screen: ScreenSink | None = None,
    meter: SessionMeter | None = None,
) -> SessionStack:
    """Compose one ``residency_tr`` session and close the three joints.

    ``screen`` is optional and is what makes this session a **kill-switch
    target** (INT-096): without one, ``fall_back_to_typed`` refuses, because a
    session that took the audio away with nowhere to put the remaining
    questions has gone silent mid-intake. It is optional rather than required
    so that the many existing callers that never pull the switch are unchanged
    — and so that "this deployment cannot fall back" is a visible ``None``
    rather than a stub nobody notices.

    ``extraction_row`` defaults to files/03 §4.9.1 **row 7** rather than row 9.
    That is a recorded fact about the bridge, not a preference: §4.9.1 row 9
    pins ``Qwen/Qwen3.6-35B-A3B`` for extraction, its registry row (INT-124)
    records it as served by no host, and the served OpenAI-compatible endpoint
    on the dev bridge is the row-7 Talker model. §4.9.2(a) already notes that
    consolidating extraction onto the Talker family is *"also an operational
    win: one model family to version, pin and hash"* — but which row serves
    extraction in production is a decision for the issue that sizes the GPU
    tier, and the parameter exists so it is made explicitly rather than
    inherited from this default.

    ``valuesets`` omitted is the committed table
    (:func:`protocols.valuesets.load_committed_valuesets`, INT-518), and that
    is how every production caller composes. Handed one, it is used as given;
    either way a code slot with no set refuses the composition.
    """
    return _compose(
        protocol=protocol,
        reference_time=reference_time,
        session_id=session_id,
        protocol_hash=protocol_hash,
        gateway=gateway,
        memory=memory,
        tenant_id=tenant_id,
        clinic=clinic,
        clock=clock,
        deadlines=deadlines,
        rule_ids=rule_ids,
        valuesets=valuesets,
        overlay_facts=overlay_facts,
        extraction_row=extraction_row,
        config=TalkerConfig(
            session_id=session_id,
            voice_id=voice_id,
            profile=VoiceProfile.RESIDENCY_TR,
            protocol_hash=protocol_hash,
            rule_ids=rule_ids,
            deadlines=deadlines or DeliveryDeadlines(),
        ),
        catalogue=catalogue or ClipCatalogue.empty(voice_id),
        clip_store=clip_store,
        synthesizer=synthesizer,
        sink=sink,
        screen=screen,
        meter=meter,
    )


def build_typed_session(
    *,
    protocol: ResolvedProtocol,
    reference_time: datetime,
    session_id: str,
    protocol_hash: str,
    gateway: ExtractionGateway,
    screen: ScreenSink,
    memory: PatientMemoryStore,
    tenant_id: str,
    clinic: ClinicNotifier,
    clock: Clock | None = None,
    deadlines: DeliveryDeadlines | None = None,
    rule_ids: frozenset[str] = frozenset(),
    valuesets: ValueSetTable | None = None,
    overlay_facts: PatientOverlay | None = None,
    extraction_row: ModelStackRow = ModelStackRow.TALKER_LLM,
    meter: SessionMeter | None = None,
) -> SessionStack:
    """Compose one ``typed`` session — the same three joints, no audio.

    **Read this signature against ``build_residency_tr_session``'s.** Every
    parameter that decides clinical behaviour is present in both and spelled
    the same: the protocol, the reference time, the pinned hash, the rule ids,
    the valuesets, the overlay, the extraction row. What is absent is
    ``voice_id``, ``synthesizer``, ``clip_store``, ``sink`` and ``catalogue``,
    and what is added is ``screen``. That difference *is* the profile; if this
    signature ever grows a clinical parameter the other lacks, parity has been
    lost at the composition root and no test below it can restore it.

    ``valuesets`` omitted is the committed table, as it is for the voice
    root: the typed lane binds a tapped choice through the same handler, so a
    typed session without the table could not record a code answer either
    (INT-518).

    ``deadlines`` survives the change of channel deliberately. files/12 §6's
    ladder decides whether a YELLOW result is delivered or expires into the
    note, and a patient reading rather than listening does not change what a
    clinician must be told went undelivered.
    """
    return _compose(
        protocol=protocol,
        reference_time=reference_time,
        session_id=session_id,
        protocol_hash=protocol_hash,
        gateway=gateway,
        memory=memory,
        tenant_id=tenant_id,
        clinic=clinic,
        clock=clock,
        deadlines=deadlines,
        rule_ids=rule_ids,
        valuesets=valuesets,
        overlay_facts=overlay_facts,
        extraction_row=extraction_row,
        config=TalkerConfig(
            session_id=session_id,
            profile=VoiceProfile.TYPED,
            protocol_hash=protocol_hash,
            rule_ids=rule_ids,
            deadlines=deadlines or DeliveryDeadlines(),
        ),
        screen=screen,
        meter=meter,
    )


def _compose(
    *,
    protocol: ResolvedProtocol,
    reference_time: datetime,
    session_id: str,
    protocol_hash: str,
    gateway: ExtractionGateway,
    memory: PatientMemoryStore,
    tenant_id: str,
    clinic: ClinicNotifier,
    clock: Clock | None,
    deadlines: DeliveryDeadlines | None,
    rule_ids: frozenset[str],
    valuesets: ValueSetTable | None,
    overlay_facts: PatientOverlay | None,
    extraction_row: ModelStackRow,
    config: TalkerConfig,
    catalogue: ClipCatalogue | None = None,
    clip_store: ClipStore | None = None,
    synthesizer: SpeechSynthesizer | None = None,
    sink: AudioSink | None = None,
    screen: ScreenSink | None = None,
    meter: SessionMeter | None = None,
) -> SessionStack:
    """Both profiles, composed once.

    This function is where "the same protocol state machine, the same guards,
    the same slots, the same reconcile-behind" stops being a claim: there is
    one ``IntakeEngine``, one ``BackendAgent``, one ``SessionTranscripts``,
    one ``ExtractSlotsHandler`` and one ``register_state`` call, and the
    profile reaches none of them. It is also still the **only** place in
    ``services/`` that calls ``register_state`` — INT-095's rule, now holding
    across two profiles rather than one.
    """
    ticking = clock or SystemClock()
    # INT-101. Metering is added by composition, at the two seams a session
    # actually spends at — the model call and the synthesiser. Both wrappers
    # are synchronous and neither is on the Talker's await path (invariant 9).
    # The typed profile is handed no synthesiser at all, which is not an
    # omission: a typed session awaits no playback (INT-096) and therefore
    # spends no characters, so half of this budget is structurally zero for
    # half the sessions.
    if meter is not None:
        gateway = MeteredExtractionGateway(inner=gateway, meter=meter)
        if synthesizer is not None:
            synthesizer = MeteredSpeechSynthesizer(inner=synthesizer, meter=meter)
    # INT-518: the committed table unless one is handed in. The handler refuses
    # a code slot it has no members for; the engine re-checks every gate
    # against the table at plan build. Both refuse here, before a patient is
    # asked anything and before the session is counted.
    table = load_committed_valuesets() if valuesets is None else valuesets
    transcripts = SessionTranscripts()
    pin = resolve_pin(extraction_row)
    handler = ExtractSlotsHandler(
        transcripts=transcripts,
        gateway=gateway,
        slots=protocol_slots(protocol),
        pin=pin,
        clock=ticking,
        tenant_id=tenant_id,
        valuesets=table.member_map(),
    )
    engine = IntakeEngine(
        protocol=protocol,
        reference_time=reference_time,
        overlay_facts=overlay_facts,
        valuesets=table,
    )
    if meter is not None:
        # INT-190: the session is counted where it is composed, by the meter
        # whose labels its usage series carry, so the per-session divisor and
        # the quantities it divides describe the same sessions. Counted only
        # once composition can no longer refuse (INT-518).
        meter.count_session()
    agent = BackendAgent(
        session_id=session_id, engine=engine, rule_ids=rule_ids, clock=ticking, clinic=clinic
    )
    agent.register_state(WorkType.EXTRACT_SLOTS, handler)

    session = TalkerSession(
        config=config,
        engine=engine,
        backend=agent,
        memory=memory,
        clock=ticking,
        catalogue=catalogue,
        clip_store=clip_store,
        synthesizer=synthesizer,
        sink=sink,
        screen=screen,
        transcripts=transcripts,
    )
    return SessionStack(
        engine=engine,
        agent=agent,
        session=session,
        transcripts=transcripts,
        handler=handler,
        extraction_pin=pin,
        slot_affordances=slot_facts(protocol),
        meter=meter,
    )
