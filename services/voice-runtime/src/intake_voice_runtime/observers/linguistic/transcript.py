"""What this lane reads: final transcripts and their word timestamps.

files/03 §4.7.5 gives the ``linguistic`` lane one input — *"final transcripts +
STT word timestamps"* — and it is deliberately **not** audio. The framework
still offers this lane audio frames, because
:meth:`~intake_voice_runtime.observers.scheduler.ObserverScheduler.offer` offers
every frame to every admitted lane; this lane reads none of them, so there is
no path from a sample byte into a marker (``tests/lanes/test_crisis_bypass.py``
asserts the package never names ``samples``).

:class:`TranscriptFeed` is a port in exactly the sense
:class:`~intake_voice_runtime.observers.consent.ConsentProbe` is: the runtime
holds the transcript, the lane holds a reader, and the lane package therefore
imports no store, no session and no client. It is **not awaitable**, for the
same reason the consent probe is not: awaiting inside a lane would be a way
for transcript arrival to pace something, and a lane paces nothing.

The turns are values in flight. The lane consumes them, aggregates counts and
timings, and keeps nothing: a lane that accumulated utterances would be a
second transcript store with none of the controls the first one has.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel, Ref
from pydantic import Field, model_validator

from intake_voice_runtime.observers.linguistic.lexicon import tokenize_tr

__all__ = ["TranscriptFeed", "TranscriptTurn", "TranscriptWord"]


class TranscriptWord(FrozenModel):
    """One recognised word and the two timestamps the STT gave it."""

    text: str = Field(min_length=1, description="The recognised word. Never emitted.")
    start_ms: float = Field(ge=0.0, description="Word onset, monotonic ms.")
    end_ms: float = Field(ge=0.0, description="Word offset, monotonic ms.")

    @model_validator(mode="after")
    def _ordered(self) -> TranscriptWord:
        if self.end_ms < self.start_ms:
            raise ValueError("a word cannot end before it starts")
        return self

    @property
    def duration_ms(self) -> float:
        return self.end_ms - self.start_ms


class TranscriptTurn(FrozenModel):
    """One final transcript, tagged with the section it was spoken in.

    ``section_ref`` is what makes *"markers aggregate per section"* possible
    without widening :class:`~intake_voice_runtime.observers.context.LaneContext`:
    the section travels with the transcript, which is where the engine already
    knows it, rather than being a second thing the lane has to be told.
    """

    turn_ref: Ref = Field(description="The turn's id (invariant 6: an id, not text).")
    section_ref: Ref = Field(description="The protocol section this turn belongs to.")
    words: tuple[TranscriptWord, ...] = Field(
        default=(), description="Words in spoken order, with STT timestamps."
    )

    def tokens(self) -> tuple[str, ...]:
        """The turn as normalised Turkish tokens, in order."""
        return tuple(token for word in self.words for token in tokenize_tr(word.text))


@runtime_checkable
class TranscriptFeed(Protocol):
    """Final transcripts the runtime has not yet handed to this lane.

    **Not awaitable.** ``take`` drains: a turn is handed over once, and the
    lane owns no queue the runtime could inspect for what a patient said.
    """

    def take(self) -> tuple[TranscriptTurn, ...]: ...
