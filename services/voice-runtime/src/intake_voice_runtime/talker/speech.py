"""The one path from text to audio — and the refusal on it.

Every sentence the agent *speaks* passes through :class:`SpeechRouter`, the
``residency_tr`` half of :class:`~intake_voice_runtime.talker.egress.
TurnEgress`. Since INT-096 it is one of two transports rather than the only
one, and the split is worth stating: the rule that a scripted step is
delivered verbatim moved **above** the seam into
:func:`~intake_voice_runtime.talker.egress.text_for`, because it governs both
transports; the rule below stays here, because it governs exactly one.

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

It is **not** applied on the typed transport, and that is the point of putting
it here rather than in :mod:`intake_voice_runtime.talker.egress`. A screen has
no normaliser to mislead, and invariant 22's other half asks a magnitude to be
*displayed* — with no grouping and bound to its unit — which
:mod:`intake_voice_runtime.typed.render` does. The two profiles deliver the
same ``text_tr``, which the compiler already expanded, so the refusal never
has anything to fire on in practice; what differs is which failure each
transport is able to have.
"""

from __future__ import annotations

import unicodedata

from intake_voice_runtime.ports import AudioSink, ClipStore, SpeechSynthesizer
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.egress import (
    EgressChannel,
    Emission,
    ParaphraseNotPermittedError,
    text_for,
)

__all__ = [
    "NumeralOnTtsPathError",
    "ParaphraseNotPermittedError",
    "SpeechRouter",
    "assert_no_numeral",
    "text_for",
]


class NumeralOnTtsPathError(ValueError):
    """Text carrying a numeral reached the speech path (invariant 22)."""


def assert_no_numeral(text: str) -> None:
    """Refuse any Unicode decimal digit. The compiler expanded them all."""
    offenders = sorted({character for character in text if unicodedata.category(character) == "Nd"})
    if offenders:
        raise NumeralOnTtsPathError(
            f"{offenders} in {text!r} — no numeral reaches a TTS model; the protocol "
            "compiler expands every digit to Turkish orthography and the models' "
            "own normalisers are disabled (CLAUDE.md invariant 22; files/03 §4.9.6)"
        )


class SpeechRouter:
    """Clip cache first, verbatim TTS second, a numeral never.

    The ``residency_tr`` implementation of
    :class:`~intake_voice_runtime.talker.egress.TurnEgress`. The clip cache is
    preferred (≈ 0 ms TTS); a cache miss falls through to TTS **with the same
    string**, because invariant 10 says "clip cache or TTS", not "clip cache,
    else improvise".
    """

    #: The transport this router is. A read-only attribute rather than a
    #: constructor argument: a SpeechRouter *is* the speaking profile, and a
    #: caller that could set it could build a router that lied about itself.
    profile = VoiceProfile.RESIDENCY_TR

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

    async def emit(self, text_tr: str, *, clip_id: str | None, label: str = "") -> Emission:
        """Play a cached clip, or synthesise the same text verbatim."""
        assert_no_numeral(text_tr)
        if clip_id is not None:
            frames = self._clip_store.fetch(clip_id)
            await self._sink.play(frames, label=label)
            return Emission(
                text_tr=text_tr,
                channel=EgressChannel.AUDIO,
                from_clip=True,
                clip_id=clip_id,
                frame_count=len(frames),
            )
        frames = self._synthesizer.synthesize(text_tr, self.voice_id)
        await self._sink.play(frames, label=label)
        return Emission(text_tr=text_tr, channel=EgressChannel.AUDIO, frame_count=len(frames))

    async def cancel(self) -> None:
        """Stop the in-flight playback — barge-in and the polite interject."""
        await self._sink.cancel()
