"""The lane drop counter — named, counted, and deliberately not emitted.

CLAUDE.md invariant 13: *"every emitted metric exists in
``metrics_catalog.yaml``"*. The catalogue holds no lane row today, so this
module does what ``work_queue.py`` did for the same reason: it counts in
process and constructs **no** Prometheus family, rather than serving a series
the catalogue does not know. ``tests/lanes/test_isolation.py`` asserts the
absence, so the day the row lands the change is a one-line edit here and a
test that already says what the name must be.

The name is not invented either. ``docs/security/threat-model.md``'s
``observer-lanes`` row already lists ``lane.dropped_frames`` as a signal that
lands with INT-110, and files/03 §4.7.6 calls it *"a tracked metric that is
also a recorded field on every lane signal"*. :data:`LANE_DROPPED_FRAMES_ID`
is that dotted OTel id; :data:`LANE_DROPPED_FRAMES_NAME` is its Prometheus
form, following the catalogue's own convention (dots become underscores, a
counter ends ``_total``).

Labels are ``(lane, reason)`` and both are closed enumerations — invariant 6
allows ids and enumerations as labels and nothing else, and a lane signal is
the last place a session id should turn up.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from clinical_schemas.observers import Lane

from intake_voice_runtime.observers.budget import DropReason

__all__ = [
    "LANE_DROPPED_FRAMES_ID",
    "LANE_DROPPED_FRAMES_LABELS",
    "LANE_DROPPED_FRAMES_NAME",
    "DropLedger",
]

#: files/03 §4.7.6 and the threat model's ``observer-lanes`` signals row.
LANE_DROPPED_FRAMES_ID: Final[str] = "lane.dropped_frames"

#: Its Prometheus form. The catalogue row this framework needs is recorded in
#: docs/evidence/INT-110.md; until it exists, nothing is emitted.
LANE_DROPPED_FRAMES_NAME: Final[str] = "lane_dropped_frames_total"

#: Closed enumerations only (invariant 6).
LANE_DROPPED_FRAMES_LABELS: Final[tuple[str, str]] = ("lane", "reason")


class DropLedger:
    """Frames shed, by ``(lane, reason)``. An in-process counter, not a series."""

    def __init__(self) -> None:
        self._counts: dict[tuple[Lane, DropReason], int] = {}

    def record(self, lane: Lane, reason: DropReason, count: int = 1) -> None:
        if count <= 0:
            return
        self._counts[lane, reason] = self._counts.get((lane, reason), 0) + count

    def count(self, *, lane: Lane | None = None, reason: DropReason | None = None) -> int:
        """Frames shed, optionally narrowed to one lane and/or one reason."""
        return sum(
            value
            for (key_lane, key_reason), value in self._counts.items()
            if (lane is None or key_lane is lane) and (reason is None or key_reason is reason)
        )

    def series(self) -> Mapping[tuple[str, str], int]:
        """The label tuples and values this would export, if it exported."""
        return {
            (key_lane.value, key_reason.value): value
            for (key_lane, key_reason), value in self._counts.items()
        }
