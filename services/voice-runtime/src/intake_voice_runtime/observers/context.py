"""What a lane is handed, and what it may hand back (invariant 11, type-level).

This is the module the acceptance's *"(compile-time)"* rests on.

**:class:`LaneContext` hands a lane no writer.** It is a frozen record of a
window and some ids. There is no engine on it, no Work submitter, no audio
sink, no store, no session and no callable of any kind — so "a lane that
writes a slot" is not an attempt the framework rejects, it is an expression a
lane cannot compose. ``mypy --strict`` reports the attribute that does not
exist, and ``tests/lanes/test_isolation.py`` runs the checker over a lane that
tries all four ways and asserts it names every one.

**:class:`LaneObservation` has no carrier for clinical state.** Four fields:
a closed :class:`InteractionDelta`, an aggregate marker map, a confidence and
the window's dropped-frame count. No ``slot_updates``, no ``triage_update``,
no ``candidate_flags``, no ``priority`` — the same posture INT-091 took for
RED preemption and INT-172 took for learning proposals, where the safety
property is that the forbidden thing has no field to live in.

:class:`InteractionDelta` is files/03 §4.7.1's ``InteractionState``, field for
field, with every field optional because a lane contributes what it observed
and nothing else. *"No emotion label, no confidence score, no numeric affect
value and no free text crosses it"* — so there is nowhere here to put one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel, JsonValue
from clinical_schemas.observers import Lane
from pydantic import Field

from intake_voice_runtime.observers.buffer import WindowView
from intake_voice_runtime.observers.module_boundary import LaneModule

__all__ = ["InteractionDelta", "LaneContext", "LaneObservation", "Observer"]


class InteractionDelta(FrozenModel):
    """A lane's contribution to M1's closed egress record (files/03 §4.7.1).

    Six optional fields and no seventh. ``extra="forbid"`` on
    :class:`~clinical_schemas.common.FrozenModel` is what makes the closure
    real: an emotion label offered here is a validation error, not a field
    somebody later notices.
    """

    pace: Literal["slow", "normal"] | None = Field(default=None)
    modality: Literal["voice", "typed", "keypad"] | None = Field(default=None)
    break_offer: bool | None = Field(default=None)
    confirm_by_card: bool | None = Field(default=None)
    repeat_request: bool | None = Field(default=None)
    third_party_present: bool | None = Field(default=None)


class LaneObservation(FrozenModel):
    """Everything a lane may return. Nothing here can name clinical state."""

    interaction: InteractionDelta | None = Field(
        default=None,
        description="M1's closed record. Refused from a lane outside M1 (inv. 22).",
    )
    markers: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="The lane's per-section aggregate — ``linguistic_markers{}``, "
        "``asr_quality{}`` or ``engagement{}`` (files/03 §4.7.5). Never raw audio, "
        "never a transcript.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Stated, not defaulted: the gate reads confidence >= tau AND "
        "dropped_frames_in_window <= D (files/03 §4.8 property 3).",
    )
    dropped_frames_in_window: int = Field(
        default=0, ge=0, description="Recorded non-determinism (files/03 §4.8)."
    )


@dataclass(frozen=True, slots=True, eq=False)
class LaneContext:
    """One window, as the lane sees it. Data only — there is nothing to call."""

    lane: Lane
    module: LaneModule
    session_ref: str
    window_id: str
    seq: int
    t_monotonic_ms: float
    consent_version: str
    gate_state: str
    window: WindowView
    dropped_frames_in_window: int


@runtime_checkable
class Observer(Protocol):
    """A lane. It reads a context and returns an observation — that is all.

    The signature is the boundary: anything else a lane might want to do has
    no argument to do it with and no return type to do it through.
    """

    @property
    def lane(self) -> Lane: ...

    async def observe(self, context: LaneContext) -> LaneObservation: ...
