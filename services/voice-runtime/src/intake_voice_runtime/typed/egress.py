"""The typed transport: the same Turkish, to a screen (INT-096).

The ``typed`` implementation of
:class:`~intake_voice_runtime.talker.egress.TurnEgress`, and the whole of what
the profile changes. It holds a :class:`~intake_voice_runtime.ports.
ScreenSink` and nothing else — no clip store, no synthesizer, no audio sink —
which is how CLAUDE.md invariant 3 becomes a property of the typed path's
*type* rather than a claim about its behaviour: there is no buffer to zero
because there is no object that could hold one.

Two refusals, and both are the fail-closed direction:

- **A ``clip_id`` reaching here raises.** The clip cache is pre-synthesised
  agent *audio* (files/03 §4.2), and a screen cannot play one. It would be
  easy to ignore the argument instead, and that is precisely the failure —
  a session whose catalogue was wired by mistake would then look like it was
  serving cached content while showing text, and nobody would learn.
- **:meth:`cancel` is a no-op, deliberately and once.** files/03 §4.6
  invariant 4's cancellation is of *playback*: cutting audio within 150 ms.
  A sentence already drawn on a screen has not been in flight since the frame
  it was drawn in, so there is nothing to stop. The insertion scheduler still
  asks — it is the same scheduler, running the same files/12 §6 ladder — and
  the answer here is "nothing was playing", which is true rather than skipped.

files/04 §272 states the consequence for RED in the accessibility suite's own
words: *"the RED design is defined in terms of cutting playback within 150 ms,
which is meaningless in typed mode."* That does not weaken invariant 21 here,
because the RED script never travelled this path in either profile: it is
pre-positioned on the device and triggered over the data channel (files/03
§4.6 invariant 4), which is the one part of the design that does not change
when the audio goes away.
"""

from __future__ import annotations

from dataclasses import dataclass

from intake_voice_runtime.ports import ScreenSink
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.egress import EgressChannel, Emission

__all__ = ["ClipOnTypedEgress", "TypedEgress"]


class ClipOnTypedEgress(LookupError):
    """A cached audio clip was offered to a screen (invariant 3, files/03 §4.2)."""


@dataclass
class TypedEgress:
    """Text out, over the reliable ordered channel. No audio anywhere."""

    screen: ScreenSink

    #: The transport this renderer is. A read-only attribute for the same
    #: reason ``SpeechRouter.profile`` is one: the object *is* the profile.
    profile = VoiceProfile.TYPED

    async def emit(self, text_tr: str, *, clip_id: str | None, label: str = "") -> Emission:
        """Render one sentence verbatim. Nothing is synthesised, ever."""
        if clip_id is not None:
            raise ClipOnTypedEgress(
                f"clip {clip_id!r} was offered to the typed transport, which has no "
                "player: clips are pre-synthesised agent audio (files/03 §4.2) and a "
                "typed session carries an empty catalogue by construction. Refusing "
                "rather than ignoring the argument — a session that reached here with "
                "a clip has been mis-wired, and that is worth knowing"
            )
        await self.screen.render(text_tr, label=label)
        return Emission(text_tr=text_tr, channel=EgressChannel.SCREEN)

    async def cancel(self) -> None:
        """Nothing is in flight on a screen. See the module docstring."""
        return None
