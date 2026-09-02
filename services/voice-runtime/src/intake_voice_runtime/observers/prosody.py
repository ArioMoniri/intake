"""Speech-rate and pause statistics, computed from timestamps alone (INT-112).

files/03 §4.7.5 gives the ``linguistic`` lane *"speech-rate and pause
statistics from timestamps"*, and files/03 §4.7.6 names what a clinician
eventually reads: *"speech rate (syllables/s), pause ratio, mean and SD of F0,
mean response latency"*. Two of those are deliberately absent here and the
absence is the design:

- **F0 needs audio.** Computing it would mean a second consumer of the PCM
  window and a pitch tracker that is not in files/03 §4.9.1's model table. A
  model that is not in that table is not pinned (CLAUDE.md), so there is
  nothing to compute it with, and inventing one would be inventing a pin.
- **Mean response latency is the ``engagement`` lane's** (files/03 §4.7.5,
  "timing events"), which is INT-114 and cannot be built at all: it has no
  declared consent purpose (HB-L22).

**There is no threshold in this module, and that is load-bearing.** The usual
definition of a "pause" is a silence longer than some number of milliseconds,
and that number is exactly the kind of value HUMAN_BLOCKERS rule 1 forbids an
agent from choosing — chosen once in a review, never revisited, and quietly
deciding what counts as disfluent speech in a language whose word-final
consonant clusters are not English's. So every statistic here is defined
*without* one: ratios and means over **every** inter-word gap. A test asserts
that this module declares no numeric constant at all.

**Syllables are counted as vowels**, which is exact for Turkish orthography
rather than an approximation of it: Turkish has no diphthongs and no syllabic
consonants, so every syllable contains exactly one vowel letter. That is a
property of the writing system, not a clinical judgement.

**Nothing here reads audio.** The whole module's input is
:class:`~intake_voice_runtime.observers.transcript.Word` timestamps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from clinical_schemas.common import FrozenModel
from pydantic import Field

from intake_voice_runtime.observers.transcript import Word

__all__ = ["ProsodyAggregate", "ProsodyStatistics", "turkish_syllables"]

#: The eight Turkish vowels, in both cases. ``I``/``ı`` and ``İ``/``i`` are
#: separate letters in Turkish and both pairs are here, so case never changes
#: a count.
_VOWELS = frozenset("aeıioöuüAEIİOÖUÜ")


def turkish_syllables(word: str) -> int:
    """Syllables in ``word``, counted as vowel letters.

    Exact for Turkish orthography: one vowel per syllable, no diphthongs, no
    syllabic consonants. A token with no vowel (a stray punctuation run, a
    foreign abbreviation) counts zero rather than being rounded up to one.
    """
    return sum(1 for character in word if character in _VOWELS)


class ProsodyStatistics(FrozenModel):
    """One section's timing aggregate. Every field is a measurement."""

    word_count: int = Field(ge=0, description="Tokens the statistics were computed over.")
    syllables: int = Field(ge=0, description="Vowel-counted syllables in those tokens.")
    span_ms: int = Field(ge=0, description="Summed segment spans: first onset to last offset.")
    speech_ms: int = Field(ge=0, description="Summed token durations inside those spans.")
    pause_ratio: float = Field(
        ge=0.0,
        le=1.0,
        description="Non-speech time as a fraction of span — threshold-free "
        "(files/03 §4.7.6 pause ratio).",
    )
    speech_rate_syllables_per_s: float = Field(
        ge=0.0, description="Syllables per second of span (files/03 §4.7.6 speech rate)."
    )
    articulation_rate_syllables_per_s: float = Field(
        ge=0.0, description="Syllables per second of speech, pauses excluded."
    )
    mean_inter_word_gap_ms: float = Field(
        ge=0.0, description="Mean of every inter-word gap, including the zero-length ones."
    )
    longest_inter_word_gap_ms: int = Field(ge=0, description="The largest inter-word gap.")

    @classmethod
    def of(cls, words: Sequence[Word]) -> ProsodyStatistics | None:
        """Statistics over one run of timestamped tokens, or ``None`` for none."""
        aggregate = ProsodyAggregate()
        aggregate.add(words)
        return aggregate.statistics()

    def as_markers(self) -> dict[str, float]:
        """The aggregate as the ``dict[str, float]`` a ``LaneObservation`` takes."""
        return {
            "word_count": float(self.word_count),
            "syllables": float(self.syllables),
            "span_ms": float(self.span_ms),
            "speech_ms": float(self.speech_ms),
            "pause_ratio": self.pause_ratio,
            "speech_rate_syllables_per_s": self.speech_rate_syllables_per_s,
            "articulation_rate_syllables_per_s": self.articulation_rate_syllables_per_s,
            "mean_inter_word_gap_ms": self.mean_inter_word_gap_ms,
            "longest_inter_word_gap_ms": float(self.longest_inter_word_gap_ms),
        }


@dataclass(slots=True)
class ProsodyAggregate:
    """A section's running counters. Integers and counts only — no text ever
    enters this object, so nothing derived from an utterance survives in it
    once the window is zeroized (CLAUDE.md invariant 3)."""

    word_count: int = 0
    syllables: int = 0
    span_ms: int = 0
    speech_ms: int = 0
    gap_count: int = 0
    gap_total_ms: int = 0
    longest_gap_ms: int = 0

    def add(self, words: Sequence[Word]) -> None:
        """Fold one segment's tokens into the section aggregate."""
        if not words:
            return
        self.word_count += len(words)
        self.span_ms += max(words[-1].end_ms - words[0].start_ms, 0)
        for word in words:
            self.syllables += turkish_syllables(word.text)
            self.speech_ms += word.end_ms - word.start_ms
        for previous, current in zip(words, words[1:], strict=False):
            gap = max(current.start_ms - previous.end_ms, 0)
            self.gap_count += 1
            self.gap_total_ms += gap
            self.longest_gap_ms = max(self.longest_gap_ms, gap)

    def as_markers(self) -> dict[str, float]:
        """The derived view as marker keys — empty when nothing was folded in.

        The consumer is branchless on purpose: a section that produced no
        statistics contributes no keys, rather than keys whose value is
        ``0.0``, which would read as *measured, none found*.
        """
        statistics = self.statistics()
        return {} if statistics is None else statistics.as_markers()

    def statistics(self) -> ProsodyStatistics | None:
        """The derived view, or ``None`` when nothing has been folded in."""
        if self.word_count == 0:
            return None
        span = self.span_ms
        speech = min(self.speech_ms, span) if span else self.speech_ms
        return ProsodyStatistics(
            word_count=self.word_count,
            syllables=self.syllables,
            span_ms=span,
            speech_ms=self.speech_ms,
            pause_ratio=(span - speech) / span if span else 0.0,
            speech_rate_syllables_per_s=self.syllables / (span / 1000.0) if span else 0.0,
            articulation_rate_syllables_per_s=(
                self.syllables / (self.speech_ms / 1000.0) if self.speech_ms else 0.0
            ),
            mean_inter_word_gap_ms=(self.gap_total_ms / self.gap_count if self.gap_count else 0.0),
            longest_inter_word_gap_ms=self.longest_gap_ms,
        )
