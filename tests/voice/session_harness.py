"""Real session stacks for the INT-182 session-router suites.

The kill switch is only proven if the runtime's own session-start path builds
the session — so the builders here call the shipped composition roots,
``build_residency_tr_session`` and ``build_typed_session``, over the same
doubles the INT-096 parity suite drives (``talker_harness``). Nothing here
dials anything: the clock is virtual and the extraction gateway is a table.

Everything is synthetic (files/04 §7): two scripted steps in one section, no
clinical content.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from intake_voice_runtime.composition import (
    SessionStack,
    build_residency_tr_session,
    build_typed_session,
)
from intake_voice_runtime.extraction.gateway import Completion, ExtractionCall
from intake_voice_runtime.profiles import VoiceProfile
from protocols.addressing import Addressing
from protocols.compile.resolve import ResolvedProtocol, ResolvedSection, ResolvedSlot
from protocols.dsl import Slot
from protocols.types import Delivery, SlotType
from red_harness import RecordingClinicNotifier
from talker_harness import (
    FakeClock,
    InMemoryPatientMemory,
    RecordedClipStore,
    RecordingScreen,
    RecordingSink,
    RecordingSynthesizer,
)

HASH = "d" * 64
NOW = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
VOICE_ID = "residency-tr-01"
STEP_IDS = ("oyku.birinci", "oyku.ikinci")
ASK_TR = {
    "oyku.birinci": "Sentetik birinci soru.",
    "oyku.ikinci": "Sentetik ikinci soru.",
}
#: A chip set per step: a numeric slot without one has no typed affordance at
#: all (invariant 22), and a session that cannot be finished on a keyboard is
#: not a kill-switch target.
CHIPS = ("bir tane", "iki tane", "uc tane")

Builders = dict[VoiceProfile, Callable[[], SessionStack]]


def _slot(ask_tr: str) -> Slot:
    return Slot.model_validate(
        {
            "type": SlotType.INTEGER,
            "required": True,
            "must_ask": True,
            "ask_tr": {"tr": ask_tr},
            "follow_up_tr": {"tr": f"{ask_tr} Tekrar eder misiniz?"},
            "choices_tr": {"tr": list(CHIPS)},
        }
    )


def protocol() -> ResolvedProtocol:
    """Two scripted steps in one section. Nothing here is clinical."""
    return ResolvedProtocol(
        pack_id="base.sentetik_int182",
        version="1.0.0",
        chain=("base.sentetik_int182",),
        resolved_protocol_hash=HASH,
        sections=(
            ResolvedSection(
                id="oyku",
                delivery=Delivery.VOICE,
                allow_paraphrase=False,
                slots=tuple(
                    ResolvedSlot(
                        section_id="oyku",
                        key=step_id.split(".", 1)[1],
                        fhir_link_id=step_id,
                        slot=_slot(ASK_TR[step_id]),
                        delivery=Delivery.VOICE,
                    )
                    for step_id in STEP_IDS
                ),
            ),
        ),
    )


class TableGateway:
    """One completion per call, from a table — the CI stand-in for row 9."""

    def __init__(self, answers: Mapping[str, object]) -> None:
        self.answers = dict(answers)

    def complete(self, call: ExtractionCall) -> Completion:
        body = {
            "slots": {
                ref: {"value": value, "confidence": 0.95} for ref, value in self.answers.items()
            },
            "candidate_flags": [],
            "clarification_needed": False,
        }
        return Completion(text=json.dumps(body), input_tokens=7, output_tokens=9)


def builders(
    *,
    tenant_id: str,
    session_id: str,
    clock: FakeClock,
    screen: RecordingScreen | None = None,
    voice_screen: bool = True,
) -> Builders:
    """Both composition roots for one session, as the worker would hand them.

    ``voice_screen=False`` builds the voice session with no screen bound — a
    deployment that cannot fall back, which INT-096 says the switch refuses
    rather than silencing (``KillSwitchNotArmed``).
    """
    surface = screen or RecordingScreen()
    answers = {step_id: index + 1 for index, step_id in enumerate(STEP_IDS)}

    def voice() -> SessionStack:
        return build_residency_tr_session(
            protocol=protocol(),
            addressing=Addressing.SELF,
            reference_time=NOW,
            session_id=session_id,
            voice_id=VOICE_ID,
            protocol_hash=HASH,
            clock=clock,
            gateway=TableGateway(answers),
            synthesizer=RecordingSynthesizer(),
            clip_store=RecordedClipStore(),
            sink=RecordingSink(clock=clock),
            memory=InMemoryPatientMemory(),
            tenant_id=tenant_id,
            clinic=RecordingClinicNotifier(),
            screen=surface if voice_screen else None,
        )

    def typed() -> SessionStack:
        return build_typed_session(
            protocol=protocol(),
            addressing=Addressing.SELF,
            reference_time=NOW,
            session_id=session_id,
            protocol_hash=HASH,
            clock=clock,
            gateway=TableGateway(answers),
            memory=InMemoryPatientMemory(),
            tenant_id=tenant_id,
            clinic=RecordingClinicNotifier(),
            screen=surface,
        )

    return {VoiceProfile.RESIDENCY_TR: voice, VoiceProfile.TYPED: typed}


def turn(stack: SessionStack, transcript: str | None) -> Any:
    """One turn with Layer B's loop pumped, inside a running event loop."""

    async def main() -> Any:
        outcome = await stack.session.take_turn(transcript)
        stack.agent.run_pending()
        return outcome

    return main()
