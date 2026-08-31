"""The four-module boundary of files/03 §4.7.1 (MDCG 2019-11 §3.4).

MDCG 2019-11 §3.4, unchanged in Rev. 1: *"It is the obligation of the
manufacturer to identify the boundaries and the interfaces of the different
modules"* — with the companion obligation that the manufacturer prove the
non-medical modules do not compromise the medical ones. So the boundary is
data here, not prose: :data:`LANE_MODULE` says which module each lane belongs
to, and :data:`MODULE_INTENDED_PURPOSE` carries the intended-purpose statement
that goes in the technical file, verbatim from the §4.7.1 table.

Two consequences are encoded rather than commented, and both are enforced in
:mod:`intake_voice_runtime.observers.state`:

- only an **M1** lane may set an ``InteractionState`` field, because M1's
  boundary *is* that closed record (invariant 22);
- an **M3** observation has nowhere to go: its output belongs to a sealed
  research store (files/03 §4.7.4), and ``ObserverState`` is not it.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from clinical_schemas.observers import Lane

__all__ = ["LANE_MODULE", "MODULE_INTENDED_PURPOSE", "LaneModule"]


class LaneModule(enum.StrEnum):
    """The four modules of files/03 §4.7.1. There is no fifth."""

    #: transcription, slot capture, note assembly, transport — non-device.
    INTAKE_CORE = "M0"
    #: affect · engagement · asr_quality — non-device.
    INTERACTION_SIGNALS = "M1"
    #: linguistic (incl. crisis-lexicon signposting) + instrument scheduling.
    CLINICAL_SIGNALS = "M2"
    #: the voice biomarker — an investigational device module (files/03 §4.7.4).
    ACOUSTIC = "M3"


#: The intended-purpose statements of the files/03 §4.7.1 table, verbatim.
#:
#: Invariant 29 (``lane_intended_purpose_manifest``) calls these *"regulatory
#: text, not comments"* — they are what goes into the technical file — so they
#: are transcribed from the blueprint rather than paraphrased here.
MODULE_INTENDED_PURPOSE: Final[Mapping[LaneModule, str]] = MappingProxyType(
    {
        LaneModule.INTAKE_CORE: (
            "to collect, structure and transmit patient-reported information before a visit"
        ),
        LaneModule.INTERACTION_SIGNALS: (
            "to adapt the pace, register and input modality of a data-collection conversation"
        ),
        LaneModule.CLINICAL_SIGNALS: (
            "to route deterministic safety signposting, and to schedule validated instruments"
        ),
        LaneModule.ACOUSTIC: (
            "to compute a voice-derived depression/anxiety score within a registered "
            "clinical investigation only"
        ),
    }
)

#: Which module each of the five lanes sits in (files/03 §4.7.1, §4.7.5).
#:
#: Diarization is absent on purpose: files/03 §4.7.3 makes it a *gate*, not a
#: lane, and its product crosses M1 as ``InteractionState.third_party_present``.
LANE_MODULE: Final[Mapping[Lane, LaneModule]] = MappingProxyType(
    {
        Lane.AFFECT: LaneModule.INTERACTION_SIGNALS,
        Lane.ENGAGEMENT: LaneModule.INTERACTION_SIGNALS,
        Lane.ASR_QUALITY: LaneModule.INTERACTION_SIGNALS,
        Lane.LINGUISTIC: LaneModule.CLINICAL_SIGNALS,
        Lane.ACOUSTIC: LaneModule.ACOUSTIC,
    }
)
