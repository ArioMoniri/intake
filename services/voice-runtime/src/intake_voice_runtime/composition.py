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
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from clinical_schemas.overlay import PatientOverlay
from protocols.compile.resolve import ResolvedProtocol
from protocols.dsl import Slot

from intake_voice_runtime.adapters.pins import ModelPin, ModelStackRow, resolve_pin
from intake_voice_runtime.clinical_agent.fsm import IntakeEngine
from intake_voice_runtime.clinical_agent.work_queue import BackendAgent
from intake_voice_runtime.extraction.gateway import ExtractionGateway
from intake_voice_runtime.extraction.handler import ExtractSlotsHandler
from intake_voice_runtime.ports import (
    AudioSink,
    ClipStore,
    Clock,
    PatientMemoryStore,
    SpeechSynthesizer,
    SystemClock,
    WorkType,
)
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.clips import ClipCatalogue
from intake_voice_runtime.talker.delivery import DeliveryDeadlines
from intake_voice_runtime.talker.session import TalkerConfig, TalkerSession
from intake_voice_runtime.transcript import SessionTranscripts

__all__ = ["ResidencyStack", "build_residency_tr_session", "protocol_slots"]


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
class ResidencyStack:
    """One composed session: the three layers, and the joints between them."""

    engine: IntakeEngine
    agent: BackendAgent
    session: TalkerSession
    transcripts: SessionTranscripts
    handler: ExtractSlotsHandler
    extraction_pin: ModelPin
    profile: VoiceProfile = VoiceProfile.RESIDENCY_TR


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
    clock: Clock | None = None,
    catalogue: ClipCatalogue | None = None,
    deadlines: DeliveryDeadlines | None = None,
    rule_ids: frozenset[str] = frozenset(),
    valuesets: Mapping[str, tuple[str, ...]] | None = None,
    overlay_facts: PatientOverlay | None = None,
    extraction_row: ModelStackRow = ModelStackRow.TALKER_LLM,
) -> ResidencyStack:
    """Compose one ``residency_tr`` session and close the three joints.

    ``extraction_row`` defaults to files/03 §4.9.1 **row 7** rather than row 9.
    That is a recorded fact about the bridge, not a preference: §4.9.1 row 9
    pins ``Qwen/Qwen3.6-35B-A3B`` for extraction, no registry row carries it,
    and the served OpenAI-compatible endpoint on the dev bridge is the row-7
    Talker model. §4.9.2(a) already notes that consolidating extraction onto
    the Talker family is *"also an operational win: one model family to
    version, pin and hash"* — but which row serves extraction in production is
    a decision for the issue that sizes the GPU tier, and the parameter exists
    so it is made explicitly rather than inherited from this default.
    """
    ticking = clock or SystemClock()
    engine = IntakeEngine(
        protocol=protocol, reference_time=reference_time, overlay_facts=overlay_facts
    )
    agent = BackendAgent(session_id=session_id, engine=engine, rule_ids=rule_ids, clock=ticking)
    transcripts = SessionTranscripts()
    pin = resolve_pin(extraction_row)
    handler = ExtractSlotsHandler(
        transcripts=transcripts,
        gateway=gateway,
        slots=protocol_slots(protocol),
        pin=pin,
        clock=ticking,
        tenant_id=tenant_id,
        valuesets=dict(valuesets or {}),
    )
    agent.register_state(WorkType.EXTRACT_SLOTS, handler)

    session = TalkerSession(
        config=TalkerConfig(
            session_id=session_id,
            voice_id=voice_id,
            profile=VoiceProfile.RESIDENCY_TR,
            protocol_hash=protocol_hash,
            rule_ids=rule_ids,
            deadlines=deadlines or DeliveryDeadlines(),
        ),
        engine=engine,
        backend=agent,
        catalogue=catalogue or ClipCatalogue.empty(voice_id),
        clip_store=clip_store,
        synthesizer=synthesizer,
        sink=sink,
        memory=memory,
        clock=ticking,
        transcripts=transcripts,
    )
    return ResidencyStack(
        engine=engine,
        agent=agent,
        session=session,
        transcripts=transcripts,
        handler=handler,
        extraction_pin=pin,
    )
