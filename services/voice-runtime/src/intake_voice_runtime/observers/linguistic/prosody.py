"""Prosody statistics from word timestamps — and the boundary they cross.

files/03 §4.7.5 asks this lane for *"speech-rate and pause statistics from
timestamps"*, and §4.7.6 says where they end up: an objective, non-interpretive
block under **"Konuşma özellikleri"**, *"reproducible, measurable, asserting no
clinical construct"*.

**No threshold is invented here.** A "pause" defined as a gap longer than *N*
milliseconds needs an *N* that no human has supplied, and HUMAN_BLOCKERS rule 1
is explicit that a plausible invented number is worse than a missing one
because there is no diff that makes it look wrong. So every statistic in this
module is threshold-free: ``pause_ratio`` is inter-word gap time over the
turn's span, and the rates are counts over durations. Nothing has a cut-off,
because nothing here needs one.

**Nothing here is a reference range either.** §4.7.6 wants each statistic
shown *"with a population reference range and a recording-condition caveat"*.
Those ranges are clinical values nobody has supplied, so the lane emits the
measurement and no range — a missing range is visible, an invented one is not.

**Invariant 22.** These numbers cross a representation boundary the moment
they leave the lane, so each one is emitted with a rendered atom beside it:
``useGrouping:false`` (no separators, no exponent) and number + unit joined by
a non-breaking space so the pair cannot be split. The rendering is the same one
``intake_voice_runtime.typed.render`` uses; it is re-derived here in two lines
rather than imported, because ``intake_platform.llm`` pulls an HTTP client into
a package that invariant 13 says has **no** network capability — and
``tests/lanes/test_crisis_bypass.py`` asserts the two agree byte for byte, so
the pair cannot drift apart in silence.

No numeral from here reaches TTS: a
:class:`~intake_voice_runtime.observers.context.LaneObservation` has no speech
carrier at all, and the lane holds no clip cache and no synthesiser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final

from intake_voice_runtime.observers.linguistic.lexicon import syllables_tr
from intake_voice_runtime.observers.linguistic.transcript import TranscriptTurn

__all__ = ["NBSP", "Measurement", "ProsodyTotals", "render_measure"]

#: Keeps a magnitude and its unit on one line (CLAUDE.md invariant 22).
NBSP: Final[str] = "\u00a0"

#: Three decimals, banker's rounding — one rule, so the same recording always
#: produces the same digits (files/03 §4.8: replay is exact).
_QUANTUM: Final[Decimal] = Decimal("0.001")

_MILLISECOND: Final[str] = "ms"
_SYLLABLES_PER_SECOND: Final[str] = "syl/s"


def render_measure(value: Decimal | int, unit: str | None) -> str:
    """One quantity, written the one way it may be written (invariant 22)."""
    rendered = str(value) if isinstance(value, int) else format(value, "f")
    return rendered if unit is None else f"{rendered}{NBSP}{unit}"


@dataclass(frozen=True, slots=True)
class Measurement:
    """One statistic: its name, its value and its unit. No range, no verdict."""

    name: str
    value: Decimal | int
    unit: str | None


def _quantized(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


@dataclass
class ProsodyTotals:
    """One section's running totals. Sums only — the ratios are derived on read.

    Accumulating sums rather than averages is what makes the aggregate
    order-independent and exactly reproducible: adding a turn twice in either
    order gives the same totals, and the same totals give the same digits.
    """

    turns: int = 0
    words: int = 0
    syllables: int = 0
    span_ms: float = 0.0
    phonation_ms: float = 0.0
    pause_ms: float = 0.0
    markers: dict[str, int] = field(default_factory=dict)

    def add_turn(self, turn: TranscriptTurn) -> None:
        """Fold one final transcript into the totals. Keeps no text."""
        if not turn.words:
            self.turns += 1
            return
        self.turns += 1
        self.words += len(turn.words)
        self.syllables += sum(syllables_tr(word.text) for word in turn.words)
        self.span_ms += turn.words[-1].end_ms - turn.words[0].start_ms
        self.phonation_ms += sum(word.duration_ms for word in turn.words)
        self.pause_ms += sum(
            max(0.0, following.start_ms - leading.end_ms)
            for leading, following in zip(turn.words, turn.words[1:], strict=False)
        )

    def count_marker(self, category: str) -> None:
        """Count one lexicon hit against a category. A count, never a phrase."""
        self.markers[category] = self.markers.get(category, 0) + 1

    def measurements(self) -> tuple[Measurement, ...]:
        """The statistics, quantized. Ratios are omitted when undefined.

        A rate over a zero-length span is not zero — it is undefined, and an
        omitted key says so where a ``0.0`` would quietly claim a measurement
        nobody could make.
        """
        span = Decimal(repr(self.span_ms))
        phonation = Decimal(repr(self.phonation_ms))
        pause = Decimal(repr(self.pause_ms))
        syllables = Decimal(self.syllables)

        stats = [
            Measurement("turns", self.turns, None),
            Measurement("words", self.words, None),
            Measurement("syllables", self.syllables, None),
            Measurement("span_ms", _quantized(span), _MILLISECOND),
            Measurement("phonation_ms", _quantized(phonation), _MILLISECOND),
            Measurement("pause_ms", _quantized(pause), _MILLISECOND),
        ]
        if span > 0:
            stats.append(Measurement("pause_ratio", _quantized(pause / span), None))
            stats.append(
                Measurement(
                    "speech_rate_syl_per_s",
                    _quantized(syllables * 1000 / span),
                    _SYLLABLES_PER_SECOND,
                )
            )
        if phonation > 0:
            stats.append(
                Measurement(
                    "articulation_rate_syl_per_s",
                    _quantized(syllables * 1000 / phonation),
                    _SYLLABLES_PER_SECOND,
                )
            )
        return tuple(stats)
