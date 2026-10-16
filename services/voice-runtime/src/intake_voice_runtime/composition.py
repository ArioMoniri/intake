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

**A session that can fire a RED is composed with the means to deliver one**
(INT-521, GitHub #887). The served red-flag rules are the pinned protocol's
own — its pack rules and the sibling ``base.life_threat`` set
(:func:`~intake_voice_runtime.clinical_agent.live_triage.served_rules`). Where
there are any, three things are bound together or the composition is refused
with :class:`RedWiringMissing`:

- a :class:`~intake_voice_runtime.clinical_agent.live_triage.SessionTriage`
  on the ``BackendAgent``, so every Work that binds a slot one of those rules
  reads is evaluated by ``packages/protocols/triage`` (invariant 1);
- the RED preemption path on the ``TalkerSession`` — the caller's data
  channel and pre-positioned script index (:class:`RedWiring`), the clinician
  route, and the agent's own audio sink as the canceller (a ``typed`` session
  has no outbound audio, so its cancel stops nothing) — so the RED the queue
  derives is delivered over the data channel the turn it is drained
  (invariant 21);
- the pinned rule ids, widened by the served rules' own, so the preempt gate
  never refuses a RED the session's own rules produced, which would fail the
  Work and drop the RED.

Wherever the RED path is bound, one
:class:`~intake_voice_runtime.talker.red_push.RedMailbox` joins the two
layers between turns (INT-531): the ``BackendAgent`` posts each RED it
settles, and the ``TalkerSession``'s own watch takes it and hands it to the
path at once, so a RED evaluated while no turn is running still reaches the
patient within files/02 §8.2's 300 ms. The Talker starts the watch on its
first turn; a worker may start it earlier with
:meth:`~intake_voice_runtime.talker.session.TalkerSession.ensure_red_watch`.

The location axis is the caller's (:attr:`RedWiring.location`), derived from
the visit lifecycle and the mode (files/02 §5.3 Axis 3) and never defaulted.
A protocol that serves no rule composes exactly as before: no evaluator, and
``TalkerSession.preemption`` stays ``None`` unless a :class:`RedWiring` is
handed in, so a RED reaching it from elsewhere raises ``RedPathNotWired``
rather than continuing the intake past a life threat. Today every compiled
pack is in that state: the life-threat set is unsigned (HB-C1) and not served.

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

**The onset anchor always resolves** (INT-540, GitHub #913). Wherever CD-05's
anchors are composed, CD-04 is too (``answer_states``, the committed register
by default): the handler reads an asked anchor's unfit answer as UNCLEAR at
once, and the engine is handed CD-04's follow-up bound for each anchor, so the
scripted ``follow_up_tr`` is asked that many times before CD-05 resolves the
anchor. ``close_session`` is registered on every session beside
``extract_slots``, and :meth:`SessionStack.close` submits it: an anchor still
asked and unanswered when the session ends is recorded UNCLEAR, resolved and
evaluated by the rules engine like any other answer.

**The clinic hears of unresolved chest-pain arms** (INT-547). Wherever a
served rule reads a CD-04 chest-pain slot, both roots require a
``clinic_items`` route (:class:`ClinicItemRouteMissing` otherwise) and wrap
``extract_slots`` and ``close_session`` in a
:class:`~intake_voice_runtime.clinical_agent.clinic_items.ClinicItemWatch`:
CD-04's ``chest_pain_arms_unresolved`` reaches the clinic inbox once, by ids,
and never touches the Work's determination. The production route is
:class:`~intake_voice_runtime.safety_inbox.ClinicItemNotifier`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from clinical_schemas.overlay import PatientOverlay
from clinical_schemas.triage import RedLocation
from protocols.anchor_choices import AnchorChoiceTable, load_anchor_choice_table
from protocols.answer_states import AnswerStateTable, load_answer_state_table
from protocols.compile.resolve import ResolvedProtocol
from protocols.dsl import Slot
from protocols.valuesets import ValueSetTable, load_committed_valuesets

from intake_voice_runtime.adapters.pins import ModelPin, ModelStackRow, resolve_pin
from intake_voice_runtime.clinical_agent.anchors import SessionAnchors
from intake_voice_runtime.clinical_agent.clinic_items import (
    ClinicItemRoute,
    ClinicItemRouteMissing,
    ClinicItemWatch,
)
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine
from intake_voice_runtime.clinical_agent.live_triage import SessionTriage, served_rules
from intake_voice_runtime.clinical_agent.session_close import SessionCloseHandler, close_request
from intake_voice_runtime.clinical_agent.work_queue import BackendAgent
from intake_voice_runtime.extraction.gateway import ExtractionGateway
from intake_voice_runtime.extraction.handler import ExtractSlotsHandler
from intake_voice_runtime.extraction.schema import closed_choice_dates
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
    QueueSealed,
    ScreenSink,
    SpeechSynthesizer,
    SystemClock,
    WorkTicket,
    WorkType,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.delivery import DeliveryDeadlines
from intake_voice_runtime.talker.red_path import (
    ClinicNotifier,
    PlaybackCanceller,
    RedDataChannel,
    RedPreemption,
    RedScriptIndex,
)
from intake_voice_runtime.talker.red_push import RedMailbox
from intake_voice_runtime.talker.session import TalkerConfig, TalkerSession
from intake_voice_runtime.transcript import SessionTranscripts
from intake_voice_runtime.typed.affordance import SlotFacts, slot_facts

__all__ = [
    "ClinicItemRouteMissing",
    "RedWiring",
    "RedWiringMissing",
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


class RedWiringMissing(ValueError):
    """A session whose pinned protocol serves red-flag rules, composed without
    the means to deliver the RED one of them can produce (INT-521)."""


@dataclass(frozen=True)
class RedWiring:
    """What a session over served red-flag rules needs to fire one (INT-521).

    Required, with no default, wherever the pinned protocol serves a rule:
    the session can then produce a RED, and must be able to deliver it.
    """

    #: files/02 §5.3 Axis 3: derived by the caller from the visit lifecycle and
    #: the mode — ``REMOTE``, ``ON_SITE`` or ``UNKNOWN`` — never guessed here.
    location: RedLocation
    #: The reliable, ordered data channel the trigger travels (invariant 21:
    #: the RED path touches no media transport).
    channel: RedDataChannel
    #: Which pre-positioned script addresses each rule at each location, from
    #: the pack the device already holds.
    scripts: RedScriptIndex


@dataclass(frozen=True)
class _NoOutboundAudio:
    """The ``typed`` profile's canceller: it has no outbound audio to stop.

    The RED path cancels the agent's audio first. A typed session synthesises
    and plays nothing (files/03 §4.4), so stopping it is complete the moment it
    is asked for; the intake still stops through the Talker's own latch.
    """

    async def cancel(self) -> None:
        return None


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
    #: CD-05 at runtime (INT-522): each closed onset choice's day, and the
    #: record of the choice beside the day it bound. ``None`` where the pinned
    #: protocol declares no date answered by a closed choice.
    anchors: SessionAnchors | None = None
    #: CD-08's chest-pain items (INT-547): what the session raised and
    #: on which route. ``None`` where no served rule reads a chest-pain slot.
    clinic_items: ClinicItemWatch | None = None

    @property
    def profile(self) -> VoiceProfile:
        """Which transport is in force — read from the session, never stored
        beside it, because the kill switch changes it mid-run."""
        return self.session.config.profile

    def close(self) -> WorkTicket | None:
        """The session is over: queue its close behind its last answers (INT-540).

        Returns at once with the close's ticket — the same one however often
        it is asked for — and the Backend pump runs it in FIFO order. ``None``
        when a RED already sealed the queue: the session's escalation has been
        made and nothing more is admitted (files/12 §7.1).
        """
        request = close_request(
            session_id=self.agent.session_id, protocol_hash=self.session.config.protocol_hash
        )
        try:
            return self.agent.submit(request)
        except QueueSealed:
            return None


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
    red: RedWiring | None = None,
    anchor_choices: AnchorChoiceTable | None = None,
    answer_states: AnswerStateTable | None = None,
    clinic_items: ClinicItemRoute | None = None,
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

    ``red`` is required wherever the pinned protocol serves a red-flag rule: a
    session that could fire a RED and not deliver it is not composed
    (:class:`RedWiringMissing`, INT-521).

    ``anchor_choices`` omitted is CD-05 read from the committed register
    (:func:`protocols.anchor_choices.load_anchor_choice_table`, INT-522),
    loaded wherever the protocol declares a date answered by a closed choice.
    Handed one, it is used as given; either way a closed-choice date with no
    decided day for every choice refuses the composition.

    ``answer_states`` omitted is CD-04 read from the committed register
    (:func:`protocols.answer_states.load_answer_state_table`, INT-540), loaded
    wherever CD-05's anchors are; handed one, it is used as given.

    ``clinic_items`` is required wherever a served rule reads a CD-01
    chest-pain slot: CD-08's items are never dropped, so a session that could
    raise one and has no route for it is not composed
    (:class:`ClinicItemRouteMissing`, INT-547).
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
        red=red,
        anchor_choices=anchor_choices,
        answer_states=answer_states,
        clinic_items=clinic_items,
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
    red: RedWiring | None = None,
    anchor_choices: AnchorChoiceTable | None = None,
    answer_states: AnswerStateTable | None = None,
    clinic_items: ClinicItemRoute | None = None,
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
    (INT-518). ``anchor_choices`` likewise: a tapped onset choice binds its
    CD-05 day through the same handler (INT-522), and ``answer_states``: an
    unfit typed onset answer is UNCLEAR at once, as a spoken one is (INT-540).
    ``clinic_items`` too: a tapped hedge leaves an arm as unresolved as a
    spoken one, so the CD-08 items are raised on both lanes (INT-547).

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
        red=red,
        anchor_choices=anchor_choices,
        answer_states=answer_states,
        clinic_items=clinic_items,
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
    red: RedWiring | None = None,
    anchor_choices: AnchorChoiceTable | None = None,
    answer_states: AnswerStateTable | None = None,
    clinic_items: ClinicItemRoute | None = None,
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
    slots = protocol_slots(protocol)
    # INT-522: CD-05 wherever a date is answered by a closed choice. The
    # handler refuses one whose choices are not all resolved to a day.
    # INT-540: CD-04 beside it — the hedges and the follow-up bound.
    anchors = _session_anchors(slots, anchor_choices, answer_states)
    handler = ExtractSlotsHandler(
        transcripts=transcripts,
        gateway=gateway,
        slots=slots,
        pin=pin,
        clock=ticking,
        tenant_id=tenant_id,
        valuesets=table.member_map(),
        anchors=anchors,
    )
    engine = IntakeEngine(
        protocol=protocol,
        reference_time=reference_time,
        overlay_facts=overlay_facts,
        valuesets=table,
        clarification_bounds=anchors.follow_up_bounds(slots) if anchors is not None else None,
    )
    # INT-521: the evaluator over the served rules, refused here (before the
    # session is counted) when the session could not deliver the RED it finds.
    triage = _session_triage(protocol, reference_time=reference_time, red=red, anchors=anchors)
    # INT-547: CD-08's chest-pain items wherever a served rule reads a
    # chest-pain slot, refused here when there is no route to raise them on.
    watch = ClinicItemWatch.for_protocol(protocol, route=clinic_items, session_id=session_id)
    pinned = rule_ids | {rule.id for rule in served_rules(protocol)}
    if meter is not None:
        # INT-190: the session is counted where it is composed, by the meter
        # whose labels its usage series carry, so the per-session divisor and
        # the quantities it divides describe the same sessions. Counted only
        # once composition can no longer refuse (INT-518).
        meter.count_session()
    # INT-531: the between-turn push, wherever there is a RED path to push to.
    mailbox = RedMailbox() if red is not None else None
    agent = BackendAgent(
        session_id=session_id,
        engine=engine,
        rule_ids=pinned,
        clock=ticking,
        clinic=clinic,
        triage=triage,
        red_push=mailbox,
    )
    close = SessionCloseHandler(anchors=anchors, steps=frozenset(slots))
    agent.register_state(WorkType.EXTRACT_SLOTS, handler if watch is None else watch.wrap(handler))
    agent.register_state(WorkType.CLOSE_SESSION, close if watch is None else watch.wrap(close))

    session = TalkerSession(
        config=config.model_copy(update={"rule_ids": pinned}),
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
        preemption=_red_path(red, sink=sink, clinic=clinic, clock=ticking),
        red_mailbox=mailbox,
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
        anchors=anchors,
        clinic_items=watch,
    )


def _session_anchors(
    slots: Mapping[str, Slot],
    anchor_choices: AnchorChoiceTable | None,
    answer_states: AnswerStateTable | None,
) -> SessionAnchors | None:
    """CD-05 and CD-04 for this session, or ``None`` where no date is a closed choice.

    Handed a table, it is used as given; otherwise the committed register's
    decision is read (provenance-checked) only when the protocol needs it.
    """
    if anchor_choices is None and not closed_choice_dates(slots):
        return None
    return SessionAnchors(
        table=load_anchor_choice_table() if anchor_choices is None else anchor_choices,
        answer_states=load_answer_state_table() if answer_states is None else answer_states,
    )


def _session_triage(
    protocol: ResolvedProtocol,
    *,
    reference_time: datetime,
    red: RedWiring | None,
    anchors: SessionAnchors | None,
) -> SessionTriage | None:
    """The evaluator over the protocol's served rules, or ``None`` if it serves none.

    A protocol that serves a rule, composed without a :class:`RedWiring`, is
    refused, naming the rules: the session could produce a RED and not
    deliver it.
    """
    served = served_rules(protocol)
    if not served:
        return None
    if red is None:
        named = ", ".join(sorted(rule.id for rule in served))
        raise RedWiringMissing(
            f"the pinned protocol serves red-flag rules ({named}) and no RedWiring was "
            "handed in: a session that can fire a RED needs its location, data channel "
            "and pre-positioned scripts to deliver one (invariant 21; INT-521)"
        )
    return SessionTriage.for_protocol(
        protocol, location=red.location, reference_time=reference_time, anchors=anchors
    )


def _red_path(
    red: RedWiring | None, *, sink: AudioSink | None, clinic: ClinicNotifier, clock: Clock
) -> RedPreemption | None:
    """The RED preemption path, bound wherever a :class:`RedWiring` was handed in.

    The clinician route is the one Layer B already tells: the Safety inbox
    entry is keyed by the RED's content-addressed work id, so the path's own
    notification lands on the same entry (INT-406).
    """
    if red is None:
        return None
    canceller: PlaybackCanceller = sink if sink is not None else _NoOutboundAudio()
    return RedPreemption(
        canceller=canceller, channel=red.channel, clinic=clinic, scripts=red.scripts, clock=clock
    )
