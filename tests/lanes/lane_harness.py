"""Deterministic lane doubles for the INT-110 suite.

Every double lives here because CLAUDE.md invariant 17 puts mocks in tests and
nowhere else. None of them loads a model: there is no Turkish vocal-biomarker
model and no Turkish-evaluated open SER model (files/00 §2, HB-C11), so a lane
double that pretended to score anything would be inventing the one thing the
blockers say does not exist. These lanes return fixed numeric markers and take
a stated amount of virtual time to do it, which is all the framework's own
properties need.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import _voice_suite  # noqa: F401  (puts tests/voice on sys.path first)
from clinical_schemas.observers import Lane
from intake_platform.consent import ConsentDecision, resolve_scope
from intake_voice_runtime.observers import (
    LANE_SPECS,
    AcousticAdmission,
    LaneContext,
    LaneObservation,
    LaneSpec,
)
from talker_harness import FakeClock, build_session, scripted_step

__all__ = [
    "SYNTHETIC_TURKISH",
    "FakeClock",
    "LaneFault",
    "RecordingSealedStore",
    "StallingLane",
    "build_session",
    "frame",
    "granted",
    "lane_double",
    "refused",
    "scripted_step",
]

#: A synthetic Turkish utterance (files/04 §7 — nothing here is clinical
#: content). Used as frame bytes so that any code path that logged its input
#: would put this sentence in a log record and fail the invariant-6 sweep.
SYNTHETIC_TURKISH = "iki gündür göğsümde bir sıkışma var"


def frame(index: int) -> bytes:
    """One synthetic audio frame carrying the sentence and its index."""
    return f"{SYNTHETIC_TURKISH}#{index}".encode()


class LaneFault(RuntimeError):
    """What a lane failing looks like from the runtime's side."""


@dataclass
class StallingLane:
    """An observer lane that takes ``stall_s`` of virtual time to answer.

    ``raises`` and ``silent`` are the two other things a real lane does: fault,
    and decline to answer a window it could not use (a gate rejection, a window
    too short, a model that returned nothing).
    """

    spec: LaneSpec
    clock: FakeClock
    stall_s: float = 0.0
    raises: bool = False
    silent: bool = False
    seen_windows: list[str] = field(default_factory=list)
    observations: int = 0

    async def observe(self, context: LaneContext) -> LaneObservation | None:
        self.seen_windows.append(context.window.window_id)
        if self.stall_s > 0:
            await self.clock.sleep(self.stall_s)
        if self.raises:
            raise LaneFault(bytes(context.window.frames[0]).decode("utf-8"))
        if self.silent or context.is_cancelled():
            return None
        self.observations += 1
        return LaneObservation(
            lane=self.spec.lane,
            window_id=context.window.window_id,
            seq=self.observations,
            markers={"frames_seen": float(len(context.window.frames))},
            confidence=0.5,
            sampling_rate_hz=context.window.sampling_rate_hz,
            dropped_frames_in_window=context.window.dropped_frames,
        )


def lane_double(
    lane: Lane,
    clock: FakeClock,
    *,
    stall_s: float = 0.0,
    raises: bool = False,
    silent: bool = False,
) -> StallingLane:
    return StallingLane(
        spec=LANE_SPECS[lane], clock=clock, stall_s=stall_s, raises=raises, silent=silent
    )


@dataclass
class RecordingSealedStore:
    """Stands in for the sealed research store INT-115 owns. In memory, and
    reachable only through an :class:`AcousticAdmission`."""

    recorded: list[tuple[str, LaneObservation]] = field(default_factory=list)

    def record(self, admission: AcousticAdmission, observation: LaneObservation) -> None:
        self.recorded.append((admission.study_id, observation))


def _decision(scope: str, *, allowed: bool, reason: str) -> ConsentDecision:
    return ConsentDecision(
        scope=scope,
        purpose=resolve_scope(scope).id,
        allowed=allowed,
        reason=reason,  # type: ignore[arg-type]
    )


def granted(*scopes: str) -> tuple[ConsentDecision, ...]:
    """Decisions as the ONE evaluator produces them (intake_platform.consent).

    The framework consumes these verdicts; it never computes ``allowed``.
    """
    return tuple(_decision(scope, allowed=True, reason="granted") for scope in scopes)


def refused(*scopes: str) -> tuple[ConsentDecision, ...]:
    return tuple(_decision(scope, allowed=False, reason="absent") for scope in scopes)
