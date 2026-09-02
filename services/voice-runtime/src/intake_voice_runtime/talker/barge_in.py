"""The patient interrupts by speaking, and the agent stops.

files/02 §8.2 states two stop budgets in one sentence — *"Barge-in stop
≤ 150 ms. RED preemption ≤ 300 ms from rule evaluation."* INT-093 built the
second. This module is the first, and it is a **safety** property rather than
a convenience: a patient who needs to correct the agent, or to stop it, must
be able to do so with their voice. Until this module existed the only way to
interrupt was to touch the screen, which is not something a person in pain,
holding a phone in one hand, reliably can do.

Three design decisions carry the whole module.

**It is not a preemption, and it must not be able to become one.**
CLAUDE.md invariant 9: *"only a rules-engine RED result may carry
``priority: preempt``"*. A barge-in is a patient-originated **transport**
event. It never enters the Work queue, never carries a priority, and is not
reachable from a backend result — so the six-tool boundary and the single
preemption both stay exactly as they were. The test suite asserts the absence
against this file's own parsed source, because a name that is merely unused
today is imported tomorrow.

**A missed budget is recorded, not raised.** INT-093 raises
``RedPathViolation`` after delivering, and it is right to: a missed RED budget
is a safety event and must be impossible to ignore. A barge-in that stopped
40 ms late is a *quality* event. Raising here would tear the session down over
a number, taking the conversation away from the patient who just asked for it,
so the violation travels on :class:`BargeInOutcome` and the caller decides.
The metric is emitted either way; that is what the percentile is for.

**RED outranks the patient's own voice.** CLAUDE.md invariant 21: inside RED
the register inverts to the bare imperative plural (*Tutun · Arayın ·
Bakmayın*) **because ambiguity is the harm**. A patient talking over those
three words must not silence them. So a barge-in arriving while a RED script
is in flight is *refused*, explicitly and on the record — never silently
dropped (invariant 17) — and the refusal lifts the moment the script is done.

**Invariant 3 has nothing to reach here.** The port carries an utterance id
and a timestamp. There is no field for frames, and :class:`PlaybackCanceller`
has one member that takes nothing — the same narrow type INT-093 defined so
that a path which must not speak cannot reach ``play``. Where the onset is
*detected* is a device or VAD concern; what arrives here is the fact that it
happened and when.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.metrics import BARGE_IN_STOP_MS
from intake_voice_runtime.ports import Clock

__all__ = [
    "STOP_BUDGET_MS",
    "BargeInOutcome",
    "BargeInPath",
    "BargeInRefusal",
    "PlaybackCanceller",
    "SpeechOnset",
]

logger = logging.getLogger("intake_voice_runtime.barge_in")

#: files/02 §8.2: *"Barge-in stop ≤ 150 ms."* Measured server-side, from the
#: moment patient speech was detected to the moment the outbound audio path
#: was cancelled. The device's own flush of already-buffered audio is what the
#: patient additionally hears, and it is on-hardware evidence rather than
#: something this path can honestly assert (CLAUDE.md invariant 20).
STOP_BUDGET_MS = 150.0


class BargeInRefusal(enum.StrEnum):
    """Why one barge-in did not do the obvious thing.

    One enumeration for both shapes — a stop that happened late and a stop
    that was declined — because both are *"the patient asked and did not get
    exactly what they asked for"*, and a caller that surfaces one should
    surface the other.
    """

    #: The cancel completed more than :data:`STOP_BUDGET_MS` after detection.
    STOP_BUDGET = "stop_budget"
    #: A RED script was playing. Invariant 21: those words are not interruptible.
    RED_IN_FLIGHT = "red_in_flight"


@runtime_checkable
class PlaybackCanceller(Protocol):
    """Stops the agent's outbound audio. One member, and it carries nothing.

    ``AudioSink`` satisfies this structurally, so production wiring is a pass;
    the narrow type is what stops this module *reaching* ``play``. It is the
    same protocol INT-093's RED path takes, deliberately: there is one way to
    stop the agent talking and two causes that use it.
    """

    def cancel(self) -> Awaitable[None]: ...


class SpeechOnset(FrozenModel):
    """The patient started talking. An id and a stamp — never audio, never words.

    ``utterance_id`` is what makes the stop idempotent: a detector that
    reports every frame above threshold must not become a stream of cancels,
    and a retried report of the same utterance is a no-op rather than a second
    interruption.
    """

    utterance_id: str = Field(min_length=1, description="One patient utterance, addressed by id.")
    detected_at_ms: float = Field(
        ge=0.0,
        description="When the onset was DETECTED on the session clock — not when "
        "this runtime heard about it. Measuring from arrival would silently "
        "discount the uplink hop from the budget being policed.",
    )


class BargeInOutcome(FrozenModel):
    """What one barge-in did, and what it cost on the session clock."""

    utterance_id: str = Field(min_length=1)
    detected_at_ms: float = Field(ge=0.0)
    stopped_at_ms: float | None = Field(
        default=None, description="None when the barge-in was refused."
    )
    refused_because: BargeInRefusal | None = Field(default=None)
    media_plane_unreachable: bool = Field(
        default=False,
        description="The cancel could not run. Usually nothing was playing — "
        "the patient spoke into a gap, which is not a failure.",
    )
    violations: tuple[BargeInRefusal, ...] = Field(default=())

    @property
    def stop_ms(self) -> float | None:
        if self.stopped_at_ms is None:
            return None
        return self.stopped_at_ms - self.detected_at_ms


@dataclass
class BargeInPath:
    """One session's barge-in path.

    ``red_in_flight`` is a plain attribute rather than a port because it is a
    fact the session already knows: INT-093's controller sets it when it
    triggers a script and clears it when the device acks. Modelling it as a
    query would invite a second source of truth for the one state where being
    wrong silences an emergency instruction.
    """

    canceller: PlaybackCanceller
    clock: Clock
    #: files/08 §4 group B fixes the per-turn label set for every `voice.*`
    #: series. All four are non-identifying by construction (invariant 6).
    labels: Mapping[str, str] = field(
        default_factory=lambda: {
            "tenant": "unknown",
            "profile": "residency_tr",
            "branch": "unknown",
            "vendor": "self-hosted",
        }
    )
    red_in_flight: bool = False
    _stopped: dict[str, BargeInOutcome] = field(default_factory=dict, init=False)

    async def on_speech_onset(self, onset: SpeechOnset) -> BargeInOutcome:
        """Stop the agent's audio because the patient started talking."""
        recorded = self._stopped.get(onset.utterance_id)
        if recorded is not None:
            return recorded

        if self.red_in_flight:
            refused = BargeInOutcome(
                utterance_id=onset.utterance_id,
                detected_at_ms=onset.detected_at_ms,
                refused_because=BargeInRefusal.RED_IN_FLIGHT,
                violations=(BargeInRefusal.RED_IN_FLIGHT,),
            )
            logger.info("barge-in refused: a RED script is in flight (invariant 21)")
            # Deliberately NOT recorded in ``_stopped``: the refusal is about
            # this instant, not about this utterance. When the script finishes,
            # a patient still talking must still be able to interrupt.
            return refused

        media_plane_unreachable = False
        try:
            await self.canceller.cancel()
        except Exception:  # the media plane is the least reliable thing here
            media_plane_unreachable = True
            logger.warning("barge-in stop found no reachable media plane", exc_info=False)
        stopped_at_ms = self.clock.now_ms()

        elapsed_ms = stopped_at_ms - onset.detected_at_ms
        BARGE_IN_STOP_MS.labels(**self.labels).observe(elapsed_ms)
        violations: tuple[BargeInRefusal, ...] = ()
        if elapsed_ms > STOP_BUDGET_MS:
            violations = (BargeInRefusal.STOP_BUDGET,)
            logger.warning(
                "barge-in stop took %.1f ms against a %.0f ms budget (files/02 §8.2)",
                elapsed_ms,
                STOP_BUDGET_MS,
            )

        outcome = BargeInOutcome(
            utterance_id=onset.utterance_id,
            detected_at_ms=onset.detected_at_ms,
            stopped_at_ms=stopped_at_ms,
            media_plane_unreachable=media_plane_unreachable,
            violations=violations,
        )
        self._stopped[onset.utterance_id] = outcome
        return outcome

    @property
    def stopped_utterance_ids(self) -> tuple[str, ...]:
        return tuple(self._stopped)
