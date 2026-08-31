"""A conforming observer lane — the positive half of the compile-time gate.

``tests/lanes/test_isolation.py`` type-checks this file under ``mypy --strict``
together with :mod:`tests.lanes.fixtures.writing_lane`. This one must come back
clean, because a checker that rejects everything proves nothing about the
checker that rejects the lane which tries to write.
"""

from __future__ import annotations

from clinical_schemas.observers import Lane
from intake_voice_runtime.observers import (
    InteractionDelta,
    LaneContext,
    LaneObservation,
    Observer,
)


class ReadOnlyLane:
    """Reads the window it is handed and returns a value. That is all it can do."""

    @property
    def lane(self) -> Lane:
        return Lane.ENGAGEMENT

    async def observe(self, context: LaneContext) -> LaneObservation:
        frame_count = context.window.frame_count
        return LaneObservation(
            interaction=InteractionDelta(pace="slow" if frame_count > 4 else "normal"),
            markers={"frames_read": frame_count},
            confidence=0.8,
            dropped_frames_in_window=context.dropped_frames_in_window,
        )


#: The protocol accepts it, which is the whole positive claim.
CONFORMING: Observer = ReadOnlyLane()
