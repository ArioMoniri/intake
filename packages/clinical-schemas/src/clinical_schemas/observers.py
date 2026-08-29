"""ObserverState and lane signals (INT-031).

files/03 §4.7: observer lanes write only ``ObserverState`` — never slots,
never triage (invariant 11) — so every model here is frozen and closed.
``InteractionState`` is M1's entire egress, a closed six-field record
(files/03 §4.7.1): no emotion label, no confidence score, no free text
crosses the module boundary. ``LaneSignal`` is the recorded shape appended
to the hash-chained session event log (files/03 §4.8) — an *input* to the
engine, never a computation of it. There is no acoustic aggregate here:
that module's output goes to the sealed research store only (files/03
§4.7.4).
"""

from __future__ import annotations

import enum
from typing import Literal

from pydantic import AwareDatetime, Field

from clinical_schemas.common import FrozenModel, JsonValue, Ref, Sha256


class Lane(enum.StrEnum):
    """The five observer lanes (invariant 11; files/03 §4.7.5). Diarization
    is a gate, not a lane — its product crosses M1 as
    ``InteractionState.third_party_present`` (files/03 §4.7.3)."""

    AFFECT = "affect"
    ACOUSTIC = "acoustic"
    LINGUISTIC = "linguistic"
    ASR_QUALITY = "asr_quality"
    ENGAGEMENT = "engagement"


class InteractionState(FrozenModel):
    """M1's only egress — the closed record of files/03 §4.7.1, verbatim six
    fields. The emotion inference exists inside M1 and dies there."""

    pace: Literal["slow", "normal"] = Field(
        description="Conversation pacing (files/03 §4.7.1 InteractionState.pace)."
    )
    modality: Literal["voice", "typed", "keypad"] = Field(
        description="Input modality to offer (files/03 §4.7.1 InteractionState.modality)."
    )
    break_offer: bool = Field(
        description="Whether to offer a break (files/03 §4.7.1 InteractionState.break_offer)."
    )
    confirm_by_card: bool = Field(
        description="Confirm answers by card instead of voice (files/03 §4.7.1; fed by "
        "asr_quality, files/03 §4.7.5)."
    )
    repeat_request: bool = Field(
        description="A repeat was requested (files/03 §4.7.1 InteractionState.repeat_request)."
    )
    third_party_present: bool = Field(
        description="A second voice is audible — a fact, not an identity claim "
        "(files/03 §4.7.1; files/04 §4.3)."
    )


class LaneSignal(FrozenModel):
    """The recorded lane-signal shape of files/03 §4.8, field for field."""

    lane: Lane = Field(description="Which lane produced the signal (files/03 §4.8).")
    session_id: Ref = Field(description="Owning session (files/03 §4.8 LaneSignal.session_id).")
    seq: int = Field(
        ge=0,
        description="Consumption order — signals apply by seq at decision points, never "
        "by wall time (files/03 §4.8 property 2).",
    )
    t_monotonic_ms: int = Field(
        ge=0, description="Monotonic capture time in ms (files/03 §4.8 t_monotonic_ms)."
    )
    t_wall: AwareDatetime = Field(description="Wall-clock capture time (files/03 §4.8 t_wall).")
    window_id: Ref = Field(description="Analysis window id (files/03 §4.8 window_id).")
    payload: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Lane-specific aggregate payload (files/03 §4.8; §4.7.5 outputs are "
        "per-section aggregates, never raw audio).",
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="Signal confidence — the gate reads confidence >= tau AND "
        "dropped_frames_in_window <= D (files/03 §4.8 property 3).",
    )
    model_ref: str = Field(
        min_length=1,
        description="model_id@revision that produced the signal (files/03 §4.8: model "
        "revision in the log is IEC 62304 change control for free).",
    )
    model_sha256: Sha256 = Field(
        description="Pinned weight digest (files/03 §4.8 'model_id@revision + sha256'; "
        "invariant 14 pinning)."
    )
    sampling_rate_hz: float = Field(
        ge=0, description="Adaptive sampling rate in effect (files/03 §4.8 sampling_rate_hz)."
    )
    dropped_frames_in_window: int = Field(
        ge=0,
        description="Recorded, not eliminated, non-determinism (files/03 §4.8 property 3; "
        "lane.dropped_frames is also a metric, files/03 §4.7.6).",
    )
    gate_state: Ref = Field(
        description="State of the lane's admission gate when the window closed "
        "(files/03 §4.8 gate_state; §4.7.3 single-speaker gate)."
    )
    consent_version: str = Field(
        min_length=1,
        description="Version of the lane consent in force (files/03 §4.8 consent_version; "
        "each lane is a separate consent purpose, files/03 §4.7).",
    )
    tombstoned: bool = Field(
        default=False,
        description="Withdrawn signals are tombstoned, not deleted — deleting breaks the "
        "hash chain; tombstoned signals are non-consumable on replay (files/03 §4.8; "
        "files/06 §2.2).",
    )


class ObserverState(FrozenModel):
    """What the lanes may write — and the only thing they may write
    (invariant 11). Aggregates per files/03 §4.7.5; merged into the Backend
    Agent at section boundaries as a wellbeing_signal Work item (files/03
    §4.7)."""

    session_id: Ref = Field(description="Owning session (files/03 §4.7).")
    interaction: InteractionState = Field(
        description="M1's closed egress record (files/03 §4.7.1)."
    )
    linguistic_markers: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Deterministic lexicon/timing markers (files/03 §4.7.5 "
        "linguistic_markers{}); crisis lexicon hits bypass the lane entirely.",
    )
    asr_quality: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Transcript quality aggregates (files/03 §4.7.5 asr_quality{}).",
    )
    engagement: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Timing-event aggregates (files/03 §4.7.5 engagement{}).",
    )
