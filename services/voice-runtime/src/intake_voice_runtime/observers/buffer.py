"""Bounded lane buffers, and the zeroization triggers of files/10 §3.

CLAUDE.md invariant 3: *"Raw audio is never written to disk, DB, object store
or logs … Memory buffers ≤ 60 s, mlocked, zeroed on every trigger."* Two of
those three are this module's job and the third is not:

- **≤ 60 s** is enforced twice — by :class:`~intake_voice_runtime.observers.
  budget.LaneBudget`, which will not construct a longer window, and by
  :meth:`WindowBuffer.append`, which refuses a frame that would push the held
  duration past the cap whatever the frame depth allows.
- **zeroed on every trigger** is :class:`ZeroizeTrigger` plus
  :func:`zeroize_frames`. Frames hold ``bytearray`` rather than ``bytes``
  precisely so the bytes can be overwritten in place: an immutable ``bytes``
  object cannot be zeroed, only dropped, and "dropped" is a claim about the
  allocator rather than about the memory.
- **mlocked, and unreachable through a core dump or a swap page**, is *not*
  here. Those are process-level controls — ``RLIMIT_CORE``, ``mlock``,
  ``kernel.yama.ptrace_scope`` — specified in files/10 §3 and asserted by
  invariants 16–19 and 28. A lane package that could call ``mlock`` would need
  a process capability, and invariant 13 says lanes have none; the hardening
  belongs to the worker that hosts them.

Windows are handed to a lane as :class:`WindowView`, whose ``samples()`` are
**read-only** memoryviews. A lane reads the audio it is scoring and cannot
alter it, which keeps "read-only lane" true of the frames as well as of the
clinical state.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass, field

from intake_voice_runtime.observers.budget import MAX_WINDOW_MS, LaneBudget

__all__ = ["Frame", "WindowBuffer", "WindowView", "ZeroizeTrigger", "zeroize_frames"]


class ZeroizeTrigger(enum.StrEnum):
    """Every trigger files/10 §3 names, as invariant 18 enumerates them.

    ``SHUTDOWN`` covers the blueprint's *"``atexit``, SIGTERM/SIGINT"* — one
    member rather than three, because they are one event from the buffer's
    point of view and three names would invite a caller to handle two of them.
    """

    WINDOW_CONSUMED = "window_consumed"
    GATE_REJECTED = "gate_rejected"
    LANE_DISABLED = "lane_disabled"
    CONSENT_WITHDRAWN = "consent_withdrawn"
    SESSION_END = "session_end"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True, eq=False)
class Frame:
    """One decoded frame already in the session (files/03 §4.7.5).

    ``samples`` is a ``bytearray`` so :func:`zeroize_frames` can overwrite it.
    The frame is otherwise immutable: a lane cannot renumber it, retime it or
    re-length it.
    """

    seq: int
    t_monotonic_ms: float
    duration_ms: float
    samples: bytearray


@dataclass(frozen=True, slots=True, eq=False)
class WindowView:
    """What a lane sees of a window: counts, timings and read-only samples."""

    frame_count: int
    duration_ms: float
    first_seq: int
    last_seq: int
    _views: tuple[memoryview, ...] = field(default=(), repr=False)

    def samples(self) -> tuple[memoryview, ...]:
        """Read-only views of the frames, in order. Writing through one raises."""
        return self._views


def zeroize_frames(frames: Iterable[Frame], trigger: ZeroizeTrigger) -> int:
    """Overwrite every frame's samples with zeros. Returns how many were zeroed.

    ``trigger`` is required and unused by the arithmetic on purpose: invariant
    18 is a claim about *which occasions* zeroize, so every call site has to
    name its occasion and the enum can be tested exhaustively.
    """
    del trigger  # named by every call site, unused by the arithmetic
    zeroed = 0
    for frame in frames:
        length = len(frame.samples)
        if length:
            frame.samples[:] = bytes(length)
        zeroed += 1
    return zeroed


class WindowBuffer:
    """One lane's bounded frame queue. Full means drop, never block."""

    def __init__(self, budget: LaneBudget) -> None:
        self._budget = budget
        self._frames: list[Frame] = []
        self._duration_ms = 0.0
        self._dropped_since_window = 0

    # --- reads ------------------------------------------------------------------------

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def duration_ms(self) -> float:
        return self._duration_ms

    @property
    def ready(self) -> bool:
        """A window is ready once the held audio reaches the budget's window."""
        return self._duration_ms >= self._budget.window_ms and bool(self._frames)

    def retained_bytes(self) -> int:
        """How many bytes of sample data this buffer still holds.

        Counted rather than asserted, so a field that started retaining audio
        would be caught rather than argued about (CLAUDE.md invariant 3).
        """
        return sum(len(frame.samples) for frame in self._frames)

    def take_dropped(self) -> int:
        """Frames dropped since the last window, and reset.

        files/03 §4.8 property 3: non-determinism is recorded, not eliminated —
        this number rides on the signal so a degraded session replays degraded.
        """
        dropped = self._dropped_since_window
        self._dropped_since_window = 0
        return dropped

    # --- writes (the runtime's, never a lane's) ---------------------------------------

    def append(self, frame: Frame) -> bool:
        """Take one frame, or drop it. Never blocks, never raises.

        Two independent bounds: the budget's frame depth, and invariant 3's
        60-second ceiling on held audio. Either one being reached is a drop.
        """
        if len(self._frames) >= self._budget.max_queued_frames:
            self._dropped_since_window += 1
            return False
        if self._duration_ms + frame.duration_ms > MAX_WINDOW_MS:
            self._dropped_since_window += 1
            return False
        self._frames.append(frame)
        self._duration_ms += frame.duration_ms
        return True

    def take_window(self) -> tuple[WindowView, tuple[Frame, ...]]:
        """Pull the frames that make up one window, with a read-only view of them.

        The frames come back too, because zeroizing them is the caller's job:
        the same frame may be held by more than one lane, and the scheduler is
        the only thing that knows when the last holder is finished.
        """
        taken: list[Frame] = []
        held = 0.0
        while self._frames and held < self._budget.window_ms:
            frame = self._frames.pop(0)
            held += frame.duration_ms
            taken.append(frame)
        self._duration_ms = max(0.0, self._duration_ms - held)
        return self._view(tuple(taken)), tuple(taken)

    def drain(self) -> tuple[Frame, ...]:
        """Everything still held, and the buffer is left empty."""
        drained = tuple(self._frames)
        self._frames = []
        self._duration_ms = 0.0
        return drained

    def zeroize(self, trigger: ZeroizeTrigger) -> int:
        """Drain and zero. For a buffer whose frames it alone holds."""
        return zeroize_frames(self.drain(), trigger)

    # --- internals ---------------------------------------------------------------------

    @staticmethod
    def _view(frames: tuple[Frame, ...]) -> WindowView:
        return WindowView(
            frame_count=len(frames),
            duration_ms=sum(frame.duration_ms for frame in frames),
            first_seq=frames[0].seq if frames else -1,
            last_seq=frames[-1].seq if frames else -1,
            _views=tuple(memoryview(frame.samples).toreadonly() for frame in frames),
        )
