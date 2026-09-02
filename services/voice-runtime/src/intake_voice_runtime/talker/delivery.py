"""The delivery vocabulary: classes, stages, deadlines, duplex state.

Its own module because both :mod:`intake_voice_runtime.talker.preemption` (a
result declares the class it is delivered under) and
:mod:`intake_voice_runtime.talker.insertion` (the scheduler walks the stages)
need it, and neither should have to import the other.

files/12 §6 is the source for every value here. It states the ladder for all
classes and the deadlines for exactly one: *"``TRIAGE_YELLOW`` uses 20 / 45 /
90 s"*. The other classes therefore have **no** default — see
:class:`DeliveryDeadlines`.
"""

from __future__ import annotations

import enum

from clinical_schemas.common import FrozenModel
from pydantic import Field

__all__ = [
    "ADAPTIVE_FLOOR_HIGH_MS",
    "ADAPTIVE_FLOOR_LOW_MS",
    "ADAPTIVE_JITTER_THRESHOLD_MS",
    "YELLOW_DEADLINES",
    "DeadlinesNotConfiguredError",
    "Deadlines",
    "DeliveryClass",
    "DeliveryDeadlines",
    "DeliveryStage",
    "DuplexState",
    "NoteFlagFailed",
    "TurnYieldPolicy",
]


class DeadlinesNotConfiguredError(LookupError):
    """A delivery class with no deadline table reached the scheduler."""


class NoteFlagFailed(RuntimeError):
    """The undelivered-note write failed; the item must stay PENDING."""


class DeliveryClass(enum.StrEnum):
    """What kind of thing is waiting to be said."""

    RED = "red"
    TRIAGE_YELLOW = "triage_yellow"
    CLINICAL_INFO = "clinical_info"
    ROUTINE = "routine"

    @classmethod
    def protected(cls) -> frozenset[DeliveryClass]:
        """files/12 §6: ``{RED, TRIAGE_YELLOW, CLINICAL_INFO}`` — the classes
        whose expiry must be written into the note inside the same
        transaction. Routine speech may simply expire."""
        return frozenset({cls.RED, cls.TRIAGE_YELLOW, cls.CLINICAL_INFO})


class DeliveryStage(enum.StrEnum):
    """The four-stage ladder of files/12 §6, evaluated on a 100 ms tick."""

    NATURAL = "natural"
    RELAXED = "relaxed"
    INTERJECT = "interject"
    EXPIRED = "expired"


class Deadlines(FrozenModel):
    """soft / hard / terminal, in milliseconds since the item was enqueued."""

    soft_ms: float = Field(gt=0.0)
    hard_ms: float = Field(gt=0.0)
    terminal_ms: float = Field(gt=0.0)

    def stage_at(self, waited_ms: float) -> DeliveryStage:
        if waited_ms < self.soft_ms:
            return DeliveryStage.NATURAL
        if waited_ms < self.hard_ms:
            return DeliveryStage.RELAXED
        if waited_ms < self.terminal_ms:
            return DeliveryStage.INTERJECT
        return DeliveryStage.EXPIRED


#: The only deadline set the blueprint states (files/12 §6).
YELLOW_DEADLINES = Deadlines(soft_ms=20_000.0, hard_ms=45_000.0, terminal_ms=90_000.0)


class DeliveryDeadlines(FrozenModel):
    """Per-class deadline table.

    Only ``triage_yellow`` has a committed default, because files/12 §6 states
    only that row. ``clinical_info`` and ``routine`` are left unset on purpose:
    how long a document result or an ordinary acknowledgement may wait before
    it interrupts a patient is a clinical delivery decision, not an
    engineering one, and CLAUDE.md forbids inventing a value to unblock
    ourselves. An unset class raises :class:`DeadlinesNotConfiguredError` at
    enqueue — the mechanism is built and the gate fails closed while the
    content is empty. The ask is recorded in docs/evidence/INT-091.md.
    """

    triage_yellow: Deadlines = Field(default=YELLOW_DEADLINES)
    clinical_info: Deadlines | None = Field(default=None)
    routine: Deadlines | None = Field(default=None)

    def for_class(self, delivery_class: DeliveryClass) -> Deadlines:
        if delivery_class is DeliveryClass.RED:
            raise DeadlinesNotConfiguredError(
                "RED never walks the ladder: it preempts over the data channel "
                "with the script pre-positioned on the device (files/03 §4.6 "
                "invariant 4; INT-093 owns that path)"
            )
        table = {
            DeliveryClass.TRIAGE_YELLOW: self.triage_yellow,
            DeliveryClass.CLINICAL_INFO: self.clinical_info,
            DeliveryClass.ROUTINE: self.routine,
        }
        deadlines = table[delivery_class]
        if deadlines is None:
            raise DeadlinesNotConfiguredError(
                f"no delivery deadlines configured for {delivery_class.value!r}; "
                "files/12 §6 states 20/45/90 s for triage_yellow and nothing for the "
                "other classes, so this fails closed rather than guessing a window"
            )
        return deadlines


#: files/03 §4.2 / §4.5b: ``min_silence_duration`` is **adaptive** — *"150 ms
#: when measured uplink jitter p95 < 30 ms, and 250 ms otherwise"*. Two
#: constants and a threshold rather than one number, because §4.5.2 is explicit
#: that the drop is conditional: *"you do not cut patients off in the waiting
#: room."*
ADAPTIVE_FLOOR_LOW_MS = 150.0
ADAPTIVE_FLOOR_HIGH_MS = 250.0
ADAPTIVE_JITTER_THRESHOLD_MS = 30.0


class TurnYieldPolicy(FrozenModel):
    """How much silence counts as the patient handing the floor back.

    The turn detector reports the boundary; this is the floor underneath it,
    and it is the *same* quantity §4.2 calls ``min_silence_duration``. It lives
    beside :class:`DuplexState` rather than inside the Talker so that the two
    consumers — the turn loop and any future adaptive controller — read one
    definition.
    """

    uplink_jitter_p95_ms: float = Field(
        ge=0.0,
        description="The measured figure §4.2 keys the floor off. Unmeasured "
        "sessions pass 0.0 only if something measured it as 0.0; the caller has "
        "no default here for the same reason the register has none.",
    )

    @property
    def floor_ms(self) -> float:
        return (
            ADAPTIVE_FLOOR_LOW_MS
            if self.uplink_jitter_p95_ms < ADAPTIVE_JITTER_THRESHOLD_MS
            else ADAPTIVE_FLOOR_HIGH_MS
        )


class DuplexState(FrozenModel):
    """The conversation, as the scheduler sees it at one tick."""

    patient_silence_ms: float = Field(ge=0.0)
    talker_idle: bool
    pending_response: bool = Field(
        description="A question is outstanding — under ask-ahead this is usually true."
    )
    at_sentence_boundary: bool = Field(
        default=False, description="The agent's current utterance can be cut here."
    )
    patient_speaking: bool = Field(
        default=False,
        description="The turn detector has an OPEN patient turn — they started and "
        "have not yielded. Distinct from `patient_silence_ms == 0`, which is also "
        "true at session start when nobody has spoken at all.",
    )

    def patient_holds_floor(self, policy: TurnYieldPolicy) -> bool:
        """True while an open patient turn has not yet yielded (files/03 §4.4b).

        *"A handover gap must be treated as a turn boundary, never as silence
        and never as an answer — this is the failure mode that silently
        corrupts data rather than visibly breaking."* Asking the next question
        over a patient who is mid-aside is the same failure from the other
        side: it produces an answer bound to a question they did not hear.

        Both conjuncts are load-bearing. Without ``patient_speaking`` a session
        that has not started yet — zero milliseconds of silence because nobody
        has said anything — would look identical to a patient mid-sentence, and
        the Talker would never ask its first question.
        """
        return self.patient_speaking and self.patient_silence_ms < policy.floor_ms
