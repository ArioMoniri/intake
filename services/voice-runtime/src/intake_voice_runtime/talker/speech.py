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

**Invariant 22 — no numeral reaches any TTS model.**
:func:`~intake_voice_runtime.talker.orthography.assert_no_numeral` is the
runtime backstop for the compiler's Turkish expansion, and it guards this
router's one entry into synthesis. It is re-exported here — every caller that
had it from this module still does — but it *lives* in
:mod:`intake_voice_runtime.talker.orthography`, which imports no media port at
all, so the RED preemption path can use the same refusal without acquiring a
route to a synthesiser (files/03 §4.6 invariant 4; INT-093).
"""

from __future__ import annotations

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.ports import AudioSink, ClipStore, SpeechSynthesizer
from intake_voice_runtime.steps import NextStep
from intake_voice_runtime.talker.orthography import NumeralOnTtsPathError, assert_no_numeral

__all__ = [
    "NumeralOnTtsPathError",
    "ParaphraseNotPermittedError",
    "SpeechRouter",
    "SpokenSpeech",
    "assert_no_numeral",
]


class ParaphraseNotPermittedError(ValueError):
    """A paraphrase was offered for a step that must be spoken verbatim."""


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
