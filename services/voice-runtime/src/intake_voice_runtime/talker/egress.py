"""The one seam a profile is allowed to move (INT-096).

files/03 §4.4 gives ``typed`` a single row and every cell but the first is a
dash: *"keyboard · — (Backend only) · — · — · n/a · — · always on"*. Read as a
specification that is unusually precise — **the profile changes where a turn's
Turkish goes, and nothing else.** Not the state machine, not the gates, not
the slots, not the reconcile-behind, not PolicyGuard, not the insertion
ladder, not the derived ``work_id``.

So this module is the boundary that statement is true *of*. Everything above
it is written once in :class:`~intake_voice_runtime.talker.session.TalkerSession`
and reached by both profiles; everything below it is a transport. The
alternative — a second session class for the keyboard — was built once (see
docs/evidence/INT-096.md) and is what parity is not: it makes "the two lanes
agree" a thing the suite has to *prove*, repeatedly, for every rule that was
copied, instead of a thing that cannot be otherwise.

:func:`text_for` lives here rather than in either transport for the same
reason. CLAUDE.md invariant 10 governs *"scripted protocol questions, red-flag
action scripts and validated instruments"*; it says "spoken" because the lane
it was written for speaks, and displaying an improvised rewording of an
authored Turkish question is the same defect through a different output
device. One function, above the seam, means the permission cannot be granted
on one transport and withheld on the other.

What is deliberately **not** here: :func:`~intake_voice_runtime.talker.speech.
assert_no_numeral`. That gate belongs to the TTS transport and only to it —
files/03 §4.9.6 is about what a *speech model's normaliser* does to ``2.5 mg``,
and a screen showing ``2,5 mg`` is invariant 22's inline clause being
satisfied rather than broken. The two halves of invariant 22 are enforced in
the two places they apply: :mod:`intake_voice_runtime.talker.speech` refuses a
numeral on the way to TTS, and :mod:`intake_voice_runtime.typed.render` writes
the one form a magnitude may be displayed in.
"""

from __future__ import annotations

import enum
from typing import Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.steps import NextStep

__all__ = [
    "EgressChannel",
    "Emission",
    "ParaphraseNotPermittedError",
    "TurnEgress",
    "text_for",
]


class ParaphraseNotPermittedError(ValueError):
    """A paraphrase was offered for a step that must be delivered verbatim."""


class EgressChannel(enum.StrEnum):
    """Where a turn's Turkish went. Two members, because there are two
    profiles and the profile registry is closed (ADR-010)."""

    #: Opus frames to the media transport — clip cache or TTS.
    AUDIO = "audio"
    #: Text to the reliable, ordered data channel the client renders.
    SCREEN = "screen"


class Emission(FrozenModel):
    """What one turn's Turkish did on its way out, for either transport.

    ``frame_count`` is zero on the screen channel because a rendered sentence
    moves no audio frames — a measurement, not an unfilled field. It exists so
    that :meth:`~intake_voice_runtime.talker.session.TalkerSession.retained_frames`
    has one shape to count over rather than two.
    """

    text_tr: str = Field(description="Exactly the bytes the patient received.")
    channel: EgressChannel
    from_clip: bool = Field(default=False, description="True when the clip cache served it.")
    clip_id: str | None = Field(default=None)
    frame_count: int = Field(default=0, ge=0, description="Frames handed on, then released.")


@runtime_checkable
class TurnEgress(Protocol):
    """Where a turn's Turkish leaves Layer A.

    Three members and no more. Anything a caller could want beyond them —
    which step this is, whether it may be reworded, when it may be said — is
    decided above the seam, which is what keeps the two implementations from
    being two policies.
    """

    @property
    def profile(self) -> VoiceProfile:
        """The profile this transport *is*. Read, never set."""
        ...

    async def emit(self, text_tr: str, *, clip_id: str | None, label: str = "") -> Emission: ...

    async def cancel(self) -> None:
        """Stop whatever is in flight, if anything can be."""
        ...


def text_for(step: NextStep, paraphrase: str | None) -> str:
    """The string that may be delivered for this step (invariant 10).

    Offering a paraphrase for a step whose ``kind`` does not permit one raises
    rather than being ignored: a silently discarded paraphrase is how a caller
    learns the wrong lesson about which steps are open to rewording.
    """
    if paraphrase is None:
        return step.text_tr
    if not step.allow_paraphrase:
        raise ParaphraseNotPermittedError(
            f"step {step.step_id!r} is kind={step.kind.value} — scripted questions, "
            "red-flag action scripts and validated instruments are delivered verbatim "
            "from text_tr, on every transport (CLAUDE.md invariant 10)"
        )
    return paraphrase
