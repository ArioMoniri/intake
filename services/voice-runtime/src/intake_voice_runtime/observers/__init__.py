"""Observer lanes (INT-110; CLAUDE.md invariant 11; files/03 §4.7, ADR-012).

The five lanes — ``affect``, ``acoustic``, ``linguistic``, ``asr_quality``,
``engagement`` — run in parallel to the conversation, write ``ObserverState``
and nothing else, drop frames under backpressure rather than delaying speech,
and are each admitted (or not) on their own consent. This package is the
framework: the contract a lane must fit, the store that is its only write
surface, the consent and study gates that decide whether a lane exists at all,
and the runtime that carries frames to it without ever standing on the speech
path.

No lane *model* lives here. ``affect`` is INT-111, ``linguistic`` INT-112,
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

__all__ = [
    "INTENDED_PURPOSE",
    "LANE_CONSENT_SCOPE",
    "LANE_SPECS",
    "MAX_WINDOW_SECONDS",
    "AcousticAdmission",
    "AcousticAssertion",
    "ApprovalDateMismatchError",
    "IcfVersionUnrecordedError",
    "LaneBudget",
    "LaneConsentUndeclared",
    "LaneContext",
    "LaneObservation",
    "LaneRuntime",
    "LaneSpec",
    "LaneWindow",
    "Module",
    "ObserverField",
    "ObserverLane",
    "ObserverStore",
    "ProtocolAmendedError",
    "SealedDestinationRefused",
    "SealedResearchStore",
    "StudyAssertionRefused",
    "admit_acoustic",
    "consented_lanes",
]
