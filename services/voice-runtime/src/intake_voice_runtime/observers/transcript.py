"""What the ``linguistic`` lane reads: a transcript segment, framed (INT-112).

files/03 §4.7.5 gives this lane a different input from the audio lanes —
*"final transcripts + STT word timestamps"* — and INT-110's ring carries
``bytes``. So the lane owns its own frame codec, and the ring carries the
serialised segment exactly as it carries a PCM frame: bounded by the same
budget, dropped under the same backpressure, and **zeroized on every trigger**
(CLAUDE.md invariant 3; files/06 §3). That is the point of putting the
transcript through the ring rather than beside it: a transcript is PHI, and
the one buffer in this service that is already proven to zero itself is the
one it should live in.

Two properties this module owes the rest of the system:

- **Nothing here reaches a log.** :class:`TranscriptFrameError` names the
  failure and the byte length, never the bytes — an error message that quoted
  a malformed frame would quote the patient (invariant 6).
- **A word carries only what a timestamp is.** ``text``, ``start_ms``,
  ``end_ms``. There is no confidence, no speaker label and no slot: a lane
  signal is an input to the engine, never a computation of it (files/03 §4.8).
"""

from __future__ import annotations

import json
from typing import Annotated

from clinical_schemas.common import FrozenModel
from pydantic import Field, StringConstraints, ValidationError, model_validator

__all__ = [
    "SectionId",
    "TranscriptFrameError",
    "TranscriptSegment",
    "Word",
    "decode_segment",
    "encode_segment",
]

#: A protocol section name (``screening``, ``expectations_wrapup``). Not a
#: :data:`~clinical_schemas.common.Ref` because section names carry
#: underscores, and not free text because it becomes a marker key.
SectionId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.]*$", max_length=64)]


class TranscriptFrameError(ValueError):
    """A frame the lane could not read. Never carries the frame's content."""


class Word(FrozenModel):
    """One STT token with its timestamps — the whole of the lane's input."""

    text: str = Field(min_length=1, description="The token as the STT produced it.")
    start_ms: int = Field(ge=0, description="Token onset, ms from session start.")
    end_ms: int = Field(ge=0, description="Token offset, ms from session start.")

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Word:
        if self.end_ms < self.start_ms:
            raise ValueError("a word cannot end before it starts")
        return self


class TranscriptSegment(FrozenModel):
    """One final transcript segment, tagged with the section it was said in.

    The section travels *with the segment* because ``LaneContext`` carries no
    section and must not start to: INT-110 asserts its four fields, and a lane
    that could read the engine's position would be a lane with a view of
    clinical state.
    """

    section_id: SectionId = Field(description="The protocol section in flight.")
    seq: int = Field(ge=0, description="Segment order within the session (files/03 §4.8).")
    words: tuple[Word, ...] = Field(min_length=1, description="Tokens with timestamps.")
    final: bool = Field(
        default=True,
        description="files/03 §4.7.5 gives this lane FINAL transcripts; an interim "
        "one is the asr_quality lane's input (INT-113).",
    )

    @property
    def text(self) -> str:
        """The segment as one string, for whole-token lexicon matching."""
        return " ".join(word.text for word in self.words)


def encode_segment(segment: TranscriptSegment) -> bytes:
    """Serialise one segment into a ring frame.

    ``ensure_ascii=False`` deliberately: the bytes then *are* the Turkish
    sentence, so the invariant-6 sweep catches a leak by plain substring as
    well as after decoding escapes. Hiding ``göğsümde`` behind ``\\u0308``
    would make the test weaker, not the product safer.
    """
    return json.dumps(segment.model_dump(), ensure_ascii=False, sort_keys=True).encode("utf-8")


def decode_segment(raw: bytes | bytearray) -> TranscriptSegment:
    """Read one ring frame back, or refuse it without quoting it."""
    try:
        payload = json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranscriptFrameError(
            f"frame of {len(raw)} bytes is not a UTF-8 transcript segment ({type(exc).__name__})"
        ) from None
    if not isinstance(payload, dict):
        raise TranscriptFrameError(f"frame of {len(raw)} bytes is not a segment mapping")
    try:
        return TranscriptSegment.model_validate(payload)
    except ValidationError as exc:
        raise TranscriptFrameError(
            f"frame of {len(raw)} bytes failed the segment schema ({exc.error_count()} error(s))"
        ) from None
