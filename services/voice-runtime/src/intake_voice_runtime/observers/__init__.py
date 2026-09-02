"""Observer lanes (INT-110; CLAUDE.md invariant 11; files/03 §4.7, ADR-012).

The five lanes — ``affect``, ``acoustic``, ``linguistic``, ``asr_quality``,
``engagement`` — run in parallel to the conversation, write ``ObserverState``
and nothing else, drop frames under backpressure rather than delaying speech,
and are each admitted (or not) on their own consent. This package is the
framework: the contract a lane must fit, the store that is its only write
surface, the consent and study gates that decide whether a lane exists at all,
and the runtime that carries frames to it without ever standing on the speech
path.

``linguistic`` is the one lane implemented here (INT-112): a deterministic
lexicon matcher and threshold-free timing statistics over transcript
segments, aggregated per section. Its crisis half is deliberately **not** a
lane — files/03 §4.7.5 says crisis hits *"bypass the lane"*, so
:mod:`~intake_voice_runtime.observers.crisis` observes and something entitled
to decide reads the observation; there is no implementation of that port on
this branch (HB-C8, HB-L2). The lexicon itself ships empty (HB-C16, HB-C17).

The other lane *models* live elsewhere. ``affect`` is INT-111,
``asr_quality`` INT-113, ``engagement`` INT-114 and ``acoustic`` INT-115 —
and the last of those has no model to wire in any case: files/00 §2 records an
exhaustive search that found **no** Turkish vocal biomarker model, and D14
dropped Kintsugi DAM. The slot is left empty and failing closed rather than
filled with something that would have to be unpicked.
"""

from __future__ import annotations

from intake_voice_runtime.observers.consent import (
    LANE_CONSENT_SCOPE,
    LaneConsentUndeclared,
    consented_lanes,
)
from intake_voice_runtime.observers.contract import (
    INTENDED_PURPOSE,
    LANE_SPECS,
    MAX_WINDOW_SECONDS,
    LaneBudget,
    LaneContext,
    LaneObservation,
    LaneSpec,
    LaneWindow,
    Module,
    ObserverField,
    ObserverLane,
)
from intake_voice_runtime.observers.crisis import (
    CRISIS_FAMILY,
    CrisisBypass,
    CrisisLexicon,
    CrisisLexiconUnsigned,
    CrisisSignpostRouter,
    CrisisTermPresence,
)
from intake_voice_runtime.observers.linguistic import LinguisticLane, MarkerLexicon
from intake_voice_runtime.observers.prosody import (
    ProsodyAggregate,
    ProsodyStatistics,
    turkish_syllables,
)
from intake_voice_runtime.observers.runtime import LaneRuntime, SealedResearchStore
from intake_voice_runtime.observers.state import ObserverStore, SealedDestinationRefused
from intake_voice_runtime.observers.study import (
    AcousticAdmission,
    AcousticAssertion,
    ApprovalDateMismatchError,
    IcfVersionUnrecordedError,
    ProtocolAmendedError,
    StudyAssertionRefused,
    admit_acoustic,
)
from intake_voice_runtime.observers.transcript import (
    SectionId,
    TranscriptFrameError,
    TranscriptSegment,
    Word,
    decode_segment,
    encode_segment,
)

__all__ = [
    "INTENDED_PURPOSE",
    "LANE_CONSENT_SCOPE",
    "LANE_SPECS",
    "MAX_WINDOW_SECONDS",
    "CRISIS_FAMILY",
    "AcousticAdmission",
    "AcousticAssertion",
    "ApprovalDateMismatchError",
    "CrisisBypass",
    "CrisisLexicon",
    "CrisisLexiconUnsigned",
    "CrisisSignpostRouter",
    "CrisisTermPresence",
    "IcfVersionUnrecordedError",
    "LaneBudget",
    "LaneConsentUndeclared",
    "LaneContext",
    "LaneObservation",
    "LaneRuntime",
    "LaneSpec",
    "LaneWindow",
    "LinguisticLane",
    "MarkerLexicon",
    "Module",
    "ObserverField",
    "ObserverLane",
    "ObserverStore",
    "ProsodyAggregate",
    "ProsodyStatistics",
    "ProtocolAmendedError",
    "SealedDestinationRefused",
    "SealedResearchStore",
    "SectionId",
    "StudyAssertionRefused",
    "TranscriptFrameError",
    "TranscriptSegment",
    "Word",
    "admit_acoustic",
    "consented_lanes",
    "decode_segment",
    "encode_segment",
    "turkish_syllables",
]
