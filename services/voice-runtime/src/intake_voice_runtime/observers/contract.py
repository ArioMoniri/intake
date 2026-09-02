"""What an observer lane is, and what it is structurally unable to say.

CLAUDE.md invariant 11: the lanes *"write ``ObserverState`` only, never slots
or triage"*. This module is where that stops being a rule and becomes a shape.
Three locks stack, and each closes a different door:

1. **A lane is handed nothing it could write through.** :class:`LaneContext`
   has four fields — the lane, the session id, a bounded window of frames, and
   a cancellation token. There is no engine, no ``WorkSubmitter``, no store.
   This is INT-092's ``ReadOnlyContext`` move applied one layer out.
2. **A lane's answer has no field a slot value or a triage level could
   occupy.** :class:`LaneObservation` is closed (``extra="forbid"``), so
   ``LaneObservation(triage_update=...)`` is a ``mypy`` error *and* a
   ``ValidationError``; and its ``markers`` map takes ``float`` values only, so
   neither ``"RED"`` nor a Turkish slot answer has a carrier even inside the
   open part of the payload.
3. **``triage_update`` and ``slot_updates`` exist as read-only constants.**
   The shape is INT-172's ``CandidateRedFlag``: a ``ClassVar`` (excluded from
   the field set, so not a constructor argument) behind a property with no
   setter, so the forbidden assignment raises rather than being silently
   clamped — and, under ``mypy --strict``, does not compile.

The fourth lock is static and lives in the tests: no module in this package
imports the engine, the Work queue, the Talker or a triage type, so there is
no path to a slot write, not merely no call.

Module boundaries (files/03 §4.7.1, MDCG 2019-11 §3.4): each lane names the
module it belongs to, and each module ships its own intended-purpose string —
one statement per module, not one for the product (invariant 29).
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import ClassVar, Final, Protocol

from clinical_schemas.common import FrozenModel
from clinical_schemas.observers import Lane
from pydantic import Field

__all__ = [
    "INTENDED_PURPOSE",
    "LANE_SPECS",
    "MAX_WINDOW_SECONDS",
    "LaneBudget",
    "LaneContext",
    "LaneObservation",
    "LaneSpec",
    "LaneWindow",
    "Module",
    "ObserverField",
    "ObserverLane",
]

#: CLAUDE.md invariant 3: audio-derived memory buffers are ≤ 60 s. A lane
#: window is such a buffer, so the ceiling is enforced where the budget is
#: declared rather than trusted at the call site.
MAX_WINDOW_SECONDS: Final[float] = 60.0


class Module(enum.StrEnum):
    """files/03 §4.7.1's module boundary. ``M0 intake_core`` holds no lane."""

    M1_INTERACTION_SIGNALS = "M1"
    M2_CLINICAL_SIGNALS = "M2"
    M3_ACOUSTIC = "M3"


#: The intended-purpose statement each module files in the technical file,
#: verbatim from files/03 §4.7.1's table (invariant 29). These are regulatory
#: strings, not patient copy: they are quoted, never composed here.
INTENDED_PURPOSE: Final[Mapping[Module, str]] = {
    Module.M1_INTERACTION_SIGNALS: (
        "to adapt the pace, register and input modality of a data-collection conversation"
    ),
    Module.M2_CLINICAL_SIGNALS: (
        "to route deterministic safety signposting, and to schedule validated instruments"
    ),
    Module.M3_ACOUSTIC: (
        "to compute a voice-derived depression/anxiety score within a registered "
        "clinical investigation only"
    ),
}


class ObserverField(enum.StrEnum):
    """Where a lane's aggregate lands — a closed set, declared per lane.

    Two members are destinations that are deliberately *not* ``ObserverState``:

    - ``M1_INTERNAL`` — ``affect``. Invariant 22: nothing but the closed
      ``InteractionState`` crosses the M1 boundary, so ``ObserverState`` has no
      ``affect`` field and the store writes nothing. The emotion inference
      exists inside M1 and dies there (files/03 §4.7.1).
    - ``SEALED_RESEARCH`` — ``acoustic``. files/03 §4.7.4: the output goes to a
      sealed research store, never to a treating clinician, never into the
      pre-visit note, never into an ``Observation``. The store refuses it.
    """

    LINGUISTIC_MARKERS = "linguistic_markers"
    ASR_QUALITY = "asr_quality"
    ENGAGEMENT = "engagement"
    M1_INTERNAL = "m1_internal"
    SEALED_RESEARCH = "sealed_research"


@dataclass(frozen=True, slots=True)
class LaneBudget:
    """One lane's compute budget: how much audio it may hold, and at what rate.

    files/03 §4.7.6: *"lanes run as asyncio tasks with per-lane CPU/GPU budgets
    …, sampling rates adapt to load, and ``lane.dropped_frames`` is a tracked
    metric"*. The budget is what makes backpressure a number rather than a
    hope: the ring holds :attr:`capacity` frames and every frame beyond that is
    dropped, never queued.
    """

    window_s: float
    frame_ms: float

    def __post_init__(self) -> None:
        if not 0.0 < self.window_s <= MAX_WINDOW_SECONDS:
            raise ValueError(
                f"a lane window is bounded by {MAX_WINDOW_SECONDS} s "
                "(CLAUDE.md invariant 3: audio buffers ≤ 60 s)"
            )
        if self.frame_ms <= 0.0:
            raise ValueError("frame_ms must be positive")

    @property
    def capacity(self) -> int:
        """How many frames the window holds before the oldest is dropped."""
        return max(1, int(self.window_s * 1000.0 / self.frame_ms))

    @property
    def sampling_rate_hz(self) -> float:
        """Frames per second at this budget (files/03 §4.8 sampling_rate_hz)."""
        return 1000.0 / self.frame_ms


@dataclass(frozen=True, slots=True)
class LaneSpec:
    """A lane's declaration: module, destination and budget. Declared, never
    inferred — a destination chosen at runtime would be a guess about whether
    the output may reach a clinician."""

    lane: Lane
    module: Module
    field: ObserverField
    budget: LaneBudget


@dataclass(frozen=True, slots=True)
class LaneWindow:
    """The bounded slice of audio a lane may look at, and nothing else.

    ``frames`` are the ring's own ``bytearray`` objects, moved out rather than
    copied, so :meth:`zeroize` reaches the only bytes that exist. The runtime
    zeroizes on every trigger — after the lane returns, on cancellation, on
    consent withdrawal and on close (files/06 §3; invariant 3).
    """

    window_id: str
    frames: tuple[bytearray, ...]
    sampling_rate_hz: float
    dropped_frames: int
    duration_s: float

    def zeroize(self) -> None:
        for buffer in self.frames:
            for index in range(len(buffer)):
                buffer[index] = 0


@dataclass(frozen=True, slots=True)
class LaneContext:
    """Everything a lane receives. There is no mutator here, of any kind.

    ``is_cancelled`` is the cooperative token files/12 §7.1 gives concurrent
    work — a lane that is withdrawn mid-window stops rather than being killed
    mid-write, and its answer is discarded either way.
    """

    lane: Lane
    session_id: str
    window: LaneWindow
    is_cancelled: Callable[[], bool]


class LaneObservation(FrozenModel):
    """What a lane may say. Closed, numeric, and incapable of naming a level.

    ``markers`` is ``dict[str, float]`` deliberately. A triage level is the
    string ``"RED"``; a slot value is Turkish text or a coded term. Neither
    fits in a float, so the open part of this payload is closed to both without
    a rule that has to be remembered.
    """

    lane: Lane = Field(description="The lane that produced this observation.")
    window_id: str = Field(min_length=1, description="The window it was computed over.")
    seq: int = Field(
        ge=0,
        description="Consumption order — signals apply by seq at decision points, never "
        "by wall time (files/03 §4.8 property 2).",
    )
    markers: dict[str, float] = Field(
        default_factory=dict,
        description="The lane's numeric aggregate for this window (files/03 §4.7.5).",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="files/03 §4.8 confidence.")
    sampling_rate_hz: float = Field(ge=0.0, description="files/03 §4.8 sampling_rate_hz.")
    dropped_frames_in_window: int = Field(
        ge=0,
        description="Recorded, not eliminated: replaying a degraded session must "
        "reproduce the degraded decision (files/03 §4.8 property 3).",
    )

    #: The two things a lane may never produce, as ``ClassVar`` constants —
    #: which ``pydantic`` excludes from the field set, so neither is a
    #: constructor argument. The properties below have no setter, so the
    #: forbidden assignment is an ``AttributeError`` at runtime and an error
    #: under ``mypy --strict``. INT-172's ``CandidateRedFlag`` uses exactly
    #: this shape to make ``level`` unsettable.
    _TRIAGE_UPDATE: ClassVar[None] = None
    _SLOT_UPDATES: ClassVar[tuple[()]] = ()

    @property
    def triage_update(self) -> None:
        """Always ``None``. Invariant 1: only ``packages/protocols/triage``
        produces a level, and a lane is not it."""
        return self._TRIAGE_UPDATE

    @property
    def slot_updates(self) -> tuple[()]:
        """Always empty. A lane signal is an *input* to the engine, never a
        computation of it (files/03 §4.8)."""
        return self._SLOT_UPDATES


class ObserverLane(Protocol):
    """The lane contract: a spec, and one coroutine that reads a window.

    ``observe`` is a coroutine because a lane may run a model; the *ingress*
    (``LaneRuntime.offer``) is an ordinary function, and that asymmetry is what
    keeps the lane off the speech critical path.
    """

    spec: LaneSpec

    async def observe(self, context: LaneContext) -> LaneObservation | None: ...


def _spec(lane: Lane, module: Module, field: ObserverField, budget: LaneBudget) -> LaneSpec:
    return LaneSpec(lane=lane, module=module, field=field, budget=budget)


#: Every lane of invariant 11, with its module, its destination and its budget.
#: The map is total over :class:`Lane`: a lane missing from it could not be
#: routed, and a module inferred at runtime would be a guess about
#: qualification. Windows: one second for the three that read events or
#: transcripts, thirty for ``acoustic``, whose gate needs ≥ 30.0 s contiguous
#: single-speaker audio (files/03 §4.7.3) — still inside the 60 s ceiling.
LANE_SPECS: Final[Mapping[Lane, LaneSpec]] = {
    Lane.AFFECT: _spec(
        Lane.AFFECT,
        Module.M1_INTERACTION_SIGNALS,
        ObserverField.M1_INTERNAL,
        LaneBudget(window_s=1.0, frame_ms=20.0),
    ),
    Lane.ACOUSTIC: _spec(
        Lane.ACOUSTIC,
        Module.M3_ACOUSTIC,
        ObserverField.SEALED_RESEARCH,
        LaneBudget(window_s=30.0, frame_ms=20.0),
    ),
    Lane.LINGUISTIC: _spec(
        Lane.LINGUISTIC,
        Module.M2_CLINICAL_SIGNALS,
        ObserverField.LINGUISTIC_MARKERS,
        LaneBudget(window_s=1.0, frame_ms=20.0),
    ),
    Lane.ASR_QUALITY: _spec(
        Lane.ASR_QUALITY,
        Module.M1_INTERACTION_SIGNALS,
        ObserverField.ASR_QUALITY,
        LaneBudget(window_s=1.0, frame_ms=20.0),
    ),
    Lane.ENGAGEMENT: _spec(
        Lane.ENGAGEMENT,
        Module.M1_INTERACTION_SIGNALS,
        ObserverField.ENGAGEMENT,
        LaneBudget(window_s=1.0, frame_ms=20.0),
    ),
}
