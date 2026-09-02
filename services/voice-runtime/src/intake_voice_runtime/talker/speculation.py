"""``preemptive_generation`` — speculate the LLM, never the TTS.

INT-095's acceptance: *"preemptive_generation speculates the LLM only; TTS
buffered until EOU is confirmed."* The reason is a hazard, not an
optimisation. Starting the dynamic-turn LLM on a partial utterance buys back
its time-to-first-token; starting the **synthesiser** on the same partial
would put agent audio into the room for a sentence the patient had not
finished — which files/03 §4.4b names as the failure that *"silently corrupts
data rather than visibly breaking"*, because the patient then answers a
question they were talked over.

The property is held **structurally** rather than by review:
:class:`PreemptiveGeneration` takes one collaborator, a text producer, and has
no parameter, attribute or method through which a
:class:`~intake_voice_runtime.ports.SpeechSynthesizer`, a
:class:`~intake_voice_runtime.ports.ClipStore` or an
:class:`~intake_voice_runtime.ports.AudioSink` could reach it. There is no
expression a caller could write that makes this class produce sound. What it
produces is a :class:`Speculation` — a step id and a string — and only
:meth:`release` hands one over, and only after
:meth:`confirm_end_of_utterance`.

The lifecycle is three states and one rule:

``speculate`` → buffered, unconfirmed → ``confirm_end_of_utterance`` → released
                                     ↘ ``resume_speech`` → discarded

**Discard, never store.** A speculation the patient talked over is dropped,
not kept for the next window: it was generated against a partial utterance
that has since continued, so it answers something the patient did not finish
saying. This is the same discipline files/13 §11.3 applies to an ask-ahead
answer whose gate closed — *"the ask-ahead race is closed by discarding, never
by storing"*.

**A release still has to pass invariant 10.** ``TalkerSession`` speaks a
released speculation through ``speak_step(step, paraphrase=…)``, which routes
it through ``SpeechRouter.text_for`` — so a speculation for a scripted step
raises ``ParaphraseNotPermittedError`` rather than being spoken. Speculation
buys latency on the turns the protocol already permits paraphrase for, and on
no others.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

__all__ = ["PreemptiveGeneration", "Speculation"]


@dataclass(frozen=True)
class Speculation:
    """One speculated dynamic turn: which step it is for, and its text.

    Frozen and two-field. There is no ``audio``, no ``clip_id`` and no
    ``frames``: the type a speculator produces cannot carry sound.
    """

    step_id: str
    text_tr: str


@dataclass
class PreemptiveGeneration:
    """The speculator. Holds a text producer and nothing that makes sound."""

    #: ``(step_id, partial_transcript) -> text_tr``. The Talker's small model
    #: behind ADR-006's gateway; a plain callable here so this module has no
    #: opinion about which model, and no way to reach a speech one.
    generate: Callable[[str, str], str]
    _buffered: Speculation | None = field(default=None, init=False)
    _confirmed: bool = field(default=False, init=False)
    speculations: int = field(default=0, init=False)
    discards: int = field(default=0, init=False)

    def speculate(self, step_id: str, partial_transcript: str) -> Speculation:
        """Run the LLM against a partial utterance and buffer the answer.

        Replaces any earlier unreleased speculation: the newer partial is a
        superset of the older one, so the older answer is stale by
        construction.
        """
        text = self.generate(step_id, partial_transcript)
        self._buffered = Speculation(step_id=step_id, text_tr=text)
        self._confirmed = False
        self.speculations += 1
        return self._buffered

    def confirm_end_of_utterance(self) -> None:
        """The turn detector says the patient finished. The buffer may go."""
        if self._buffered is not None:
            self._confirmed = True

    def resume_speech(self) -> None:
        """The patient kept talking. Discard rather than store."""
        if self._buffered is not None:
            self.discards += 1
        self._buffered = None
        self._confirmed = False

    def release(self) -> Speculation | None:
        """Hand over a confirmed speculation exactly once, or ``None``."""
        if not self._confirmed or self._buffered is None:
            return None
        released, self._buffered, self._confirmed = self._buffered, None, False
        return released

    @property
    def buffered(self) -> Speculation | None:
        """What is held, released or not. A read, never a release."""
        return self._buffered
