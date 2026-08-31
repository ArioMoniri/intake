"""Per-lane budgets and the reasons a frame is dropped (files/03 §4.7.6).

files/03 §4.7.6: *"lanes run as asyncio tasks with per-lane CPU/GPU budgets
(or a separate worker pool), sampling rates adapt to load, and
``lane.dropped_frames`` is a tracked metric that is also a recorded field on
every lane signal"*. Invariant 11 says what happens when a budget is exceeded:
*"under backpressure they drop frames, never delay speech"*.

:data:`MAX_WINDOW_MS` is CLAUDE.md invariant 3 as a type refusal rather than a
review comment — *"Memory buffers ≤ 60 s"*. A budget that asks for a longer
window does not construct, so there is no configuration through which a lane
could hold a minute and a half of a patient's voice.
"""

from __future__ import annotations

import enum
from typing import Final

from clinical_schemas.common import FrozenModel
from pydantic import Field

__all__ = ["MAX_WINDOW_MS", "DropReason", "LaneBudget"]

#: CLAUDE.md invariant 3: memory buffers ≤ 60 s.
MAX_WINDOW_MS: Final[float] = 60_000.0


class DropReason(enum.StrEnum):
    """Why a frame or a window was shed. A closed set, because it is a metric
    label and a label is an enumeration or an id, never free text (invariant 6)."""

    #: The lane's buffer was full — the speech path shed load at the offer.
    BACKPRESSURE = "backpressure"
    #: The lane did not answer inside its deadline; its window is discarded.
    LANE_OVERRAN = "lane_overran"
    #: The lane consent went away (files/06 §2.2).
    CONSENT_WITHDRAWN = "consent_withdrawn"
    #: The lane was stopped — by the operator, or because it breached its
    #: module boundary and is not trusted with a second window.
    LANE_DISABLED = "lane_disabled"


class LaneBudget(FrozenModel):
    """One lane's compute and memory envelope.

    ``deadline_ms`` is what makes "never delay speech" survive a lane that is
    merely slow rather than stalled: the pump races the lane against its own
    deadline and discards the window, and neither branch is on the speech
    path in the first place.
    """

    window_ms: float = Field(
        gt=0.0,
        le=MAX_WINDOW_MS,
        description="How much audio or transcript makes one analysis window. "
        f"Capped at {MAX_WINDOW_MS:.0f} ms by CLAUDE.md invariant 3.",
    )
    max_queued_frames: int = Field(
        ge=1,
        description="Buffer depth. Once it is full the next frame is dropped, "
        "which is the whole of the backpressure policy (invariant 11).",
    )
    deadline_ms: float = Field(
        gt=0.0, description="How long one window may take before it is discarded."
    )
    sampling_rate_hz: float = Field(
        gt=0.0,
        description="The sampling rate in effect — recorded on every signal so a "
        "degraded session replays as degraded (files/03 §4.8 property 3).",
    )
