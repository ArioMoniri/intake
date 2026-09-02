"""The ``linguistic`` lane: markers per section, and nothing else (INT-112).

files/03 §4.7.5 row 4. Input: *"final transcripts + STT word timestamps"*.
Method: *"deterministic Turkish lexicons …, speech-rate and pause statistics
from timestamps"*. Output: ``linguistic_markers{}``, *"per section,
aggregated"*.

This lane is built **on** INT-110 rather than beside it: it declares
``LANE_SPECS[Lane.LINGUISTIC]`` (M2, ``linguistic_markers``, a one-second
window), answers a :class:`~intake_voice_runtime.observers.contract.LaneContext`
that carries no engine, and returns a
:class:`~intake_voice_runtime.observers.contract.LaneObservation` whose markers
map is ``dict[str, float]``. Every one of INT-110's five locks still holds and
none is weakened here.

**The crisis family is not reachable from this module.** The lane's declared
input type is :class:`MarkerLexicon`, which has no ``match_crisis``. That is
the mechanical form of files/03 §4.7.5's *"crisis lexicon hits **bypass the
lane**"*: not a rule about what this code chooses to read, but a type that
cannot express the read. The crisis surface is
:mod:`intake_voice_runtime.observers.crisis`, which is not a lane at all.

**Aggregation is per section, and cumulative.** The lane keeps one
:class:`~intake_voice_runtime.observers.prosody.ProsodyAggregate` and one hit
counter per section id, and every observation reports the *section* total, not
the window's. So a consumer reading ``linguistic_markers`` at a section
boundary — which is where files/03 §4.7 merges lane signals in — reads the
section, however many windows it took.

**Nothing textual survives the window.** The accumulators hold integers.
After ``observe`` returns, ``LaneRuntime`` zeroizes the frames, and there is
no copy of the transcript anywhere in this object (CLAUDE.md invariant 3).

**A family that did not compile has no marker key**, rather than a key whose
value is ``0.0``. Zero reads as *measured, none found*; the shipped lexicon is
unsigned (HB-C16/HB-C17), and that is a different fact.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from clinical_schemas.observers import Lane

from intake_voice_runtime.observers.contract import (
    LANE_SPECS,
    LaneContext,
    LaneObservation,
    LaneSpec,
)
from intake_voice_runtime.observers.prosody import ProsodyAggregate
from intake_voice_runtime.observers.transcript import (
    TranscriptFrameError,
    TranscriptSegment,
    decode_segment,
)

__all__ = ["LinguisticLane", "MarkerLexicon"]


@runtime_checkable
class MarkerLexicon(Protocol):
    """The half of a compiled lexicon this lane is allowed to see.

    ``packages/protocols``' ``CompiledLexicon`` satisfies it structurally; the
    lane imports nothing from that package (INT-110's AST gate forbids it), so
    the seam is a shape rather than a dependency.
    """

    @property
    def marker_families(self) -> tuple[str, ...]: ...

    def match_markers(self, text: str) -> Mapping[str, int]: ...


class _SectionState:
    """One section's running totals. Integers only — never a word."""

    __slots__ = ("prosody", "hits")

    def __init__(self) -> None:
        self.prosody = ProsodyAggregate()
        self.hits: dict[str, int] = {}

    def add(self, segment: TranscriptSegment, matches: Mapping[str, int]) -> None:
        self.prosody.add(segment.words)
        for family, count in matches.items():
            self.hits[family] = self.hits.get(family, 0) + count


class LinguisticLane:
    """One session's ``linguistic`` lane."""

    def __init__(self, *, lexicon: MarkerLexicon, spec: LaneSpec | None = None) -> None:
        self.spec = spec if spec is not None else LANE_SPECS[Lane.LINGUISTIC]
        self._lexicon = lexicon
        self._sections: dict[str, _SectionState] = {}
        self._observations = 0

    @property
    def sections(self) -> tuple[str, ...]:
        """The sections this lane has seen, in a stable order."""
        return tuple(sorted(self._sections))

    async def observe(self, context: LaneContext) -> LaneObservation | None:
        """Fold this window's segments in, and report every section's totals.

        A frame that does not decode is dropped, not guessed: a malformed
        transcript is a degraded input, and files/03 §4.8 property 3 records
        degradation rather than repairing it. ``dropped_frames_in_window``
        carries the ring's own count so a replay reproduces the *degraded*
        decision.
        """
        read = 0
        for frame in context.window.frames:
            try:
                segment = decode_segment(frame)
            except TranscriptFrameError:
                continue
            state = self._sections.setdefault(segment.section_id, _SectionState())
            state.add(segment, self._lexicon.match_markers(segment.text))
            read += 1
        if read == 0 or context.is_cancelled():
            return None
        self._observations += 1
        return LaneObservation(
            lane=self.spec.lane,
            window_id=context.window.window_id,
            seq=self._observations,
            markers=self._markers(),
            # The lane runs no model. A whole-token count and arithmetic over
            # timestamps are exact, so the *measurement* is certain; that is
            # not a claim about the lexicon's content, which is unsigned. When
            # files/03 §4.7.5's "small classifier later" lands it brings its
            # own confidence, and this constant goes with it.
            confidence=1.0,
            sampling_rate_hz=context.window.sampling_rate_hz,
            dropped_frames_in_window=context.window.dropped_frames,
        )

    def _markers(self) -> dict[str, float]:
        markers: dict[str, float] = {}
        for section_id in sorted(self._sections):
            state = self._sections[section_id]
            for name, value in state.prosody.as_markers().items():
                markers[f"{section_id}.{name}"] = value
            for family in sorted(state.hits):
                markers[f"{section_id}.lexicon.{family}"] = float(state.hits[family])
        return markers
