"""The one path from text to audio — and the two refusals on it.

Every sentence the agent speaks passes through :class:`SpeechRouter`, which is
what makes the two rules below hold everywhere rather than at the call sites
someone remembered:

**Invariant 10 — verbatim.** A step whose ``kind`` does not permit paraphrase
is spoken as ``text_tr`` and nothing else. The clip cache is preferred (≈ 0 ms
TTS); a cache miss falls through to TTS **with the same string**, because
invariant 10 says "clip cache or TTS", not "clip cache, else improvise".
Offering a paraphrase for such a step raises rather than being ignored — a
silently discarded paraphrase is how a caller learns the wrong lesson.

**Invariant 22 — no numeral reaches any TTS model.** The compiler expands
every digit, unit, dose form and drug name at compile time
(``protocols.compile.tr_orthography``) precisely because both candidate TTS
models ship a Turkish-hostile normaliser: Freya reads ``2.5 mg`` as *"yirmi
beş"* — a silent ten-fold dose error — and VoxCPM2 routes Turkish through its
English branch. :func:`assert_no_numeral` is the runtime backstop for that
compile-time guarantee, and it refuses rather than sanitising: a numeral here
means an upstream invariant has already failed, and rewriting it would hide
which one.

The check is over Unicode ``Nd``, not ASCII ``0-9``. An Eastern-Arabic ``٣``
in a hospital-supplied string is exactly the kind of digit that would slip a
``[0-9]`` regex and reach a normaliser that has never seen it.
"""

from __future__ import annotations

import unicodedata

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.ports import AudioSink, ClipStore, SpeechSynthesizer
from intake_voice_runtime.steps import NextStep

__all__ = [
    "NumeralOnTtsPathError",
    "ParaphraseNotPermittedError",
    "SpeechRouter",
    "SpokenSpeech",
    "assert_no_numeral",
]


class NumeralOnTtsPathError(ValueError):
    """Text carrying a numeral reached the speech path (invariant 22)."""


class ParaphraseNotPermittedError(ValueError):
    """A paraphrase was offered for a step that must be spoken verbatim."""


def assert_no_numeral(text: str) -> None:
    """Refuse any Unicode decimal digit. The compiler expanded them all."""
    offenders = sorted({character for character in text if unicodedata.category(character) == "Nd"})
    if offenders:
        raise NumeralOnTtsPathError(
            f"{offenders} in {text!r} — no numeral reaches a TTS model; the protocol "
            "compiler expands every digit to Turkish orthography and the models' "
            "own normalisers are disabled (CLAUDE.md invariant 22; files/03 §4.9.6)"
        )


class SpokenSpeech(FrozenModel):
    """What was said, how it was produced, and how long it took."""

    text_tr: str = Field(description="Exactly the bytes the patient heard, as text.")
    from_clip: bool = Field(description="True when the clip cache served it (0 ms TTS).")
    clip_id: str | None = Field(default=None)
    frame_count: int = Field(ge=0, description="Frames handed to the sink and then released.")


class SpeechRouter:
    """Clip cache first, verbatim TTS second, a numeral never."""

    def __init__(
        self,
        *,
        voice_id: str,
        clip_store: ClipStore,
        synthesizer: SpeechSynthesizer,
        sink: AudioSink,
    ) -> None:
        self.voice_id = voice_id
        self._clip_store = clip_store
        self._synthesizer = synthesizer
        self._sink = sink

    def text_for(self, step: NextStep, paraphrase: str | None) -> str:
        """The string that may be spoken for this step (invariant 10)."""
        if paraphrase is None:
            return step.text_tr
        if not step.allow_paraphrase:
            raise ParaphraseNotPermittedError(
                f"step {step.step_id!r} is kind={step.kind.value} — scripted questions, "
                "red-flag action scripts and validated instruments are spoken verbatim "
                "from text_tr (CLAUDE.md invariant 10)"
            )
        return paraphrase

    async def speak(self, text_tr: str, *, clip_id: str | None, label: str = "") -> SpokenSpeech:
        """Play a cached clip, or synthesise the same text verbatim."""
        assert_no_numeral(text_tr)
        if clip_id is not None:
            frames = self._clip_store.fetch(clip_id)
            await self._sink.play(frames, label=label)
            return SpokenSpeech(
                text_tr=text_tr, from_clip=True, clip_id=clip_id, frame_count=len(frames)
            )
        frames = self._synthesizer.synthesize(text_tr, self.voice_id)
        await self._sink.play(frames, label=label)
        return SpokenSpeech(text_tr=text_tr, from_clip=False, frame_count=len(frames))
