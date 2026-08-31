"""The ``linguistic`` lane itself — INT-112, the first lane in the framework.

files/03 §4.7.5, the row this module implements:

    ``linguistic`` (M2) · input: final transcripts + STT word timestamps ·
    method: deterministic Turkish lexicons (negative affect, hopelessness,
    anhedonia, somatic worry), speech-rate and pause statistics from
    timestamps … · output: ``linguistic_markers{}``

and the clause that is *not* this object's: *"crisis lexicon hits bypass the
lane"* — :mod:`.crisis` is reached without a lane, without a scheduler and
without a consent scope, because files/04 §4.2 defect 3 requires a
consent-independent crisis response.

What the lane does per window: drains the transcript feed, folds each final
turn into the aggregate for **its own section**, and returns the sections it
touched. Nothing else. It holds no clock, no sink, no submitter and no model,
and it reads none of the audio the framework offers it.

**Aggregates per section, and the section comes from the transcript.**
:class:`~intake_voice_runtime.observers.context.LaneContext` carries no section
and this issue does not widen it: the engine already tags each final transcript
with the section it was spoken in, so ``TranscriptTurn.section_ref`` is the
existing fact rather than a second one to keep in step.

**What is empty, and what "empty" looks like from outside.** Both lexicons are
unauthored (HB-C8). The aggregate therefore reports
``lexicon_status: "unauthored"`` and **no** category counts at all — because
``hopelessness: 0`` from a list nobody has written is a measurement nobody
made, and a reader has to be able to tell "none found" from "never looked".
The prosody statistics are unaffected: timestamps are timestamps, and they
need no clinician's phrase list.
"""

from __future__ import annotations

from typing import Final

from clinical_schemas.common import FrozenModel, JsonScalar, JsonValue
from clinical_schemas.observers import Lane
from pydantic import Field

from intake_voice_runtime.observers.budget import LaneBudget
from intake_voice_runtime.observers.context import LaneContext, LaneObservation
from intake_voice_runtime.observers.linguistic.lexicon import (
    Lexicon,
    LexiconStatus,
    MarkerCategory,
    UnauthoredNote,
)
from intake_voice_runtime.observers.linguistic.prosody import ProsodyTotals, render_measure
from intake_voice_runtime.observers.linguistic.refusals import RefusalCode
from intake_voice_runtime.observers.linguistic.transcript import TranscriptFeed
from intake_voice_runtime.observers.module_boundary import MODULE_INTENDED_PURPOSE, LaneModule
from intake_voice_runtime.observers.spec import LaneSpec

__all__ = [
    "LINGUISTIC_INTENDED_PURPOSE",
    "SECTION_MARKER_PREFIX",
    "LinguisticLane",
    "LinguisticLexicons",
    "linguistic_lane_spec",
    "unauthored_lexicons",
]

#: Invariant 29 wants a *reviewed* intended-purpose string, and files/03 §4.7.1
#: already carries one for M2, reviewed as regulatory text. It is reused
#: verbatim rather than paraphrased: this lane is the whole of M2's
#: signposting half, and a second wording would be a second claim.
LINGUISTIC_INTENDED_PURPOSE: Final[str] = MODULE_INTENDED_PURPOSE[LaneModule.CLINICAL_SIGNALS]

#: Marker keys are ``section:<section_ref>``, so one lane's aggregate holds one
#: entry per section and merging two windows updates rather than appends.
SECTION_MARKER_PREFIX: Final[str] = "section:"

#: The cadence at which this lane's aggregate is refreshed. Not a clinical
#: value — it is a buffer size, bounded by invariant 3's 60 s ceiling, and the
#: only thing it changes is how often a section's totals are re-emitted.
LINGUISTIC_WINDOW_MS: Final[float] = 5_000.0


class LinguisticLexicons(FrozenModel):
    """The two lists this lane is configured with, each with its own state."""

    crisis: Lexicon = Field(description="The bypass's list (files/04 §4.2). HB-C8.")
    markers: Lexicon = Field(description="The four files/03 §4.7.5 marker lexicons.")


def unauthored_lexicons() -> LinguisticLexicons:
    """What this repository ships: two lists nobody has written, that say so.

    HUMAN_BLOCKERS rule 2 — build the mechanism, wire the gate, make it fail
    closed, leave the content empty. Scanning either one refuses and names
    HB-C8; neither can be mistaken for a list that simply found nothing.
    """
    return LinguisticLexicons(
        crisis=Lexicon(
            ref="lexicon.crisis.tr",
            status=LexiconStatus.UNAUTHORED,
            unauthored=UnauthoredNote(
                blocker_ref="HB-C8", refusal_code=RefusalCode.CRISIS_LEXICON_UNAUTHORED
            ),
        ),
        markers=Lexicon(
            ref="lexicon.markers.tr",
            status=LexiconStatus.UNAUTHORED,
            unauthored=UnauthoredNote(
                blocker_ref="HB-C8", refusal_code=RefusalCode.MARKER_LEXICON_UNAUTHORED
            ),
        ),
    )


def linguistic_lane_spec(
    *,
    window_ms: float = LINGUISTIC_WINDOW_MS,
    max_queued_frames: int = 600,
    deadline_ms: float = 200.0,
    sampling_rate_hz: float = 50.0,
) -> LaneSpec:
    """This lane's manifest (invariant 29), with the M2 intended purpose."""
    return LaneSpec(
        lane=Lane.LINGUISTIC,
        intended_purpose=LINGUISTIC_INTENDED_PURPOSE,
        budget=LaneBudget(
            window_ms=window_ms,
            max_queued_frames=max_queued_frames,
            deadline_ms=deadline_ms,
            sampling_rate_hz=sampling_rate_hz,
        ),
    )


class LinguisticLane:
    """Reads final transcripts, returns per-section markers. Nothing else.

    Satisfies :class:`~intake_voice_runtime.observers.context.Observer`, so
    the framework's guarantees hold unchanged: the context hands it no writer,
    the observation has no carrier for a slot or a triage result, and the
    scheduler races it against its own deadline off the speech path.
    """

    def __init__(self, *, transcript: TranscriptFeed, lexicons: LinguisticLexicons) -> None:
        self._transcript = transcript
        self._lexicons = lexicons
        self._sections: dict[str, ProsodyTotals] = {}

    @property
    def lane(self) -> Lane:
        return Lane.LINGUISTIC

    async def observe(self, context: LaneContext) -> LaneObservation:
        """One window: fold the finals that arrived, emit the sections touched.

        ``confidence`` is stated as ``1.0`` because there is nothing here to be
        uncertain about — counting tokens and subtracting timestamps is
        arithmetic, and no model sits in the path (files/03 §4.8 property 3
        still reads ``dropped_frames_in_window`` from the context).
        """
        touched: list[str] = []
        for turn in self._transcript.take():
            totals = self._sections.setdefault(turn.section_ref, ProsodyTotals())
            totals.add_turn(turn)
            self._count_markers(turn.tokens(), totals)
            if turn.section_ref not in touched:
                touched.append(turn.section_ref)

        markers: dict[str, JsonValue] = {
            f"{SECTION_MARKER_PREFIX}{section_ref}": self._section_markers(section_ref)
            for section_ref in sorted(touched)
        }
        return LaneObservation(
            markers=markers,
            confidence=1.0,
            dropped_frames_in_window=context.dropped_frames_in_window,
        )

    def _count_markers(self, tokens: tuple[str, ...], totals: ProsodyTotals) -> None:
        """Count marker hits — only while there is a list to count against."""
        if self._lexicons.markers.status is LexiconStatus.UNAUTHORED:
            return
        for match in self._lexicons.markers.scan(tokens):
            if match.category is not None:
                totals.count_marker(match.category.value)

    def _section_markers(self, section_ref: str) -> dict[str, JsonScalar]:
        """One section's aggregate: measurements, their renders, and a status.

        Every numeric value is paired with its rendered atom on the same
        section — invariant 22's *"no numeric slot value … without a matching
        ``inline`` render"*, at the boundary this lane's numbers cross.
        """
        totals = self._sections[section_ref]
        aggregate: dict[str, JsonScalar] = {}
        for measurement in totals.measurements():
            value = measurement.value
            aggregate[measurement.name] = value if isinstance(value, int) else float(value)
            aggregate[f"{measurement.name}_render"] = render_measure(value, measurement.unit)

        aggregate["lexicon_status"] = self._lexicons.markers.status.value
        if self._lexicons.markers.status is LexiconStatus.AUTHORED:
            for category in MarkerCategory:
                count = totals.markers.get(category.value, 0)
                aggregate[f"marker.{category.value}"] = count
                aggregate[f"marker.{category.value}_render"] = render_measure(count, None)
        return aggregate
