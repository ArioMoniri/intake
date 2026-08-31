"""The one writer: lane observations → ``ObserverState`` (invariant 11).

*"Observer lanes are read-only: they write ``ObserverState`` only, never slots
or triage."* The first half of that is a type property
(:mod:`intake_voice_runtime.observers.context`); the second half is this
module, which is the only place in the framework that writes anything at all —
and what it writes is an ``ObserverState``, a frozen schema from INT-031 with
no slot field and no triage field on it.

The routing table is files/03 §4.7.5's output column, read literally:

===============  ==================================================
lane             where its output goes
===============  ==================================================
``affect``       ``InteractionState`` **only** — *"no label, no
                 score, no text"*. Markers are refused: the emotion
                 inference exists inside M1 and dies there.
``engagement``   ``engagement{}`` → ``pace`` / ``break_offer``
``asr_quality``  ``asr_quality{}`` → ``confirm_by_card``
``linguistic``   ``linguistic_markers{}``
``acoustic``     nowhere here. Its output is an ordinal severity
                 band to a sealed research store (files/03 §4.7.4).
===============  ==================================================

Two refusals rather than filters, because a filter drops a breach quietly and
a refusal reports it: an observation from **M3** and an ``InteractionState``
field from a lane outside **M1** both raise. The second is invariant 22
(``interaction_state_closed_domain``) at the write side, and files/03 §4.7.1
calls that test *"evidence in the technical file"* for MDCG 2019-11's
non-interference requirement.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from clinical_schemas.common import JsonValue
from clinical_schemas.observers import InteractionState, Lane, ObserverState

from intake_voice_runtime.observers.context import LaneObservation
from intake_voice_runtime.observers.module_boundary import LANE_MODULE, LaneModule

__all__ = [
    "MARKER_TARGET",
    "NO_SIGNAL_INTERACTION",
    "ObserverStateBuilder",
    "ObserverStateRefusedError",
]

#: Which ``ObserverState`` aggregate each lane's markers land in. ``affect``
#: and ``acoustic`` are absent, and their absence is the point.
MARKER_TARGET: Final[Mapping[Lane, str]] = MappingProxyType(
    {
        Lane.LINGUISTIC: "linguistic_markers",
        Lane.ASR_QUALITY: "asr_quality",
        Lane.ENGAGEMENT: "engagement",
    }
)

#: The interaction record before any lane has said anything: ordinary pace,
#: whatever modality the session opened in, nothing offered and nothing
#: observed. Not a clinical value — it is the absence of a signal, and it is a
#: constructor argument so a ``typed`` session can open on its own modality.
NO_SIGNAL_INTERACTION: Final[InteractionState] = InteractionState(
    pace="normal",
    modality="voice",
    break_offer=False,
    confirm_by_card=False,
    repeat_request=False,
    third_party_present=False,
)


class ObserverStateRefusedError(RuntimeError):
    """An observation that would cross a module boundary. Refused, not filtered."""


class ObserverStateBuilder:
    """Accumulates lane observations into one session's ``ObserverState``."""

    def __init__(self, session_ref: str, initial: InteractionState = NO_SIGNAL_INTERACTION) -> None:
        self._session_ref = session_ref
        self._interaction = initial
        self._markers: dict[str, dict[str, JsonValue]] = {
            target: {} for target in MARKER_TARGET.values()
        }

    def apply(self, lane: Lane, observation: LaneObservation) -> None:
        """Merge one observation, or refuse it by naming the boundary it crossed."""
        module = LANE_MODULE[lane]
        if module is LaneModule.ACOUSTIC:
            raise ObserverStateRefusedError(
                "the acoustic lane is module M3, whose output goes to the sealed "
                "research store and to the investigator per protocol — never into "
                "ObserverState, the note or an Observation (files/03 §4.7.4)"
            )
        if observation.interaction is not None and module is not LaneModule.INTERACTION_SIGNALS:
            raise ObserverStateRefusedError(
                f"the {lane.value} lane is module {module.value}, and only an M1 lane "
                "may set an InteractionState field — that record is M1's boundary "
                "(files/03 §4.7.1, invariant 22)"
            )
        if observation.markers:
            target = MARKER_TARGET.get(lane)
            if target is None:
                raise ObserverStateRefusedError(
                    f"the {lane.value} lane has no marker egress: its output is the "
                    "closed InteractionState only — no label, no score, no text. The "
                    "emotion inference exists inside M1 and dies there (files/03 §4.7.5)"
                )
            self._markers[target].update(observation.markers)
        if observation.interaction is not None:
            self._interaction = self._interaction.model_copy(
                update=observation.interaction.model_dump(exclude_none=True)
            )

    def state(self) -> ObserverState:
        """The current aggregate. A value, so a caller cannot write through it."""
        return ObserverState(
            session_id=self._session_ref,
            interaction=self._interaction,
            linguistic_markers=dict(self._markers["linguistic_markers"]),
            asr_quality=dict(self._markers["asr_quality"]),
            engagement=dict(self._markers["engagement"]),
        )
