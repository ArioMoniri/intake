"""What is metered, and in which unit — files/08 §4 group J's three quantities.

§4 J states the cost axes as *"`cost.per_session` by component · tokens/chars/
audio-seconds by vendor · GPU hours · forecast vs budget"*, and files/10 §5's
LLM10 row names the same three as the control: *"per-session token/char/audio
budgets"*. So there are exactly three components and exactly three units, and
the mapping between them is one-to-one rather than a free pairing — a
component that could be denominated in two units is a component whose totals
could be added up wrongly.

**"by vendor" is a vendor-era phrase.** Under CLAUDE.md invariant 19 every
model is self-hosted, so there is no vendor to split by; the axis that survives
is *component*, which is what ``cost.per_session`` is labelled by anyway. The
group B ``vendor`` label keeps its name (the catalogue's label set is pinned
against §4) and carries the constant ``self-hosted``, on the precedent
``intake_voice_runtime.talker.barge_in`` already set.

``GPU hours`` is deliberately **not** a component here. It is a property of the
serving host, not of a session, and no host exists to measure (HB-I4, HB-I5).
Adding a member for it would be a column nothing can ever fill.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Final

from intake_platform.cost.spend import ChargeClass as _ChargeClass

__all__ = [
    "UNIT_OF",
    "ChargeClass",
    "MeterUnit",
    "MeteredComponent",
]


class MeteredComponent(enum.StrEnum):
    """The three components a session spends against (files/08 §4 J)."""

    #: Speech-to-text. Denominated in audio seconds.
    ASR = "asr"
    #: Text-to-speech, the dynamic path only — a clip-cache hit synthesises
    #: nothing and therefore costs nothing (CLAUDE.md invariant 10).
    TTS = "tts"
    #: The ``extract_slots`` model call — files/03 §4.3 Layer B Work.
    LLM_EXTRACTION = "llm_extraction"


class MeterUnit(enum.StrEnum):
    """The three units. One per component; see :data:`UNIT_OF`."""

    TOKENS = "tokens"
    CHARS = "chars"
    AUDIO_SECONDS = "audio_seconds"


#: The one-to-one pairing. A :class:`~intake_voice_runtime.metering.budgets.
#: SessionBudget` whose unit disagrees with this table is refused at the schema.
UNIT_OF: Final[Mapping[MeteredComponent, MeterUnit]] = {
    MeteredComponent.ASR: MeterUnit.AUDIO_SECONDS,
    MeteredComponent.TTS: MeterUnit.CHARS,
    MeteredComponent.LLM_EXTRACTION: MeterUnit.TOKENS,
}


#: INT-439 moved the definition to :mod:`intake_platform.cost.spend` so the model
#: lanes and the voice runtime share one vocabulary; re-exported here unchanged.
ChargeClass = _ChargeClass
