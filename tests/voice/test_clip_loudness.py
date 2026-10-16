"""INT-497 — ``voice_clips.loudness``: one loudness for every clip of a turn.

Measured on the cast E04 set (docs/evidence/INT-497.md): the acknowledgements
sit about 3 LU under the questions they lead into and the whole set spans 9 LU,
so a lead-in and its question sound like two recordings. The cure is ITU-R
BS.1770 integrated loudness plus a gain to one target, capped by the sample
peak.

The device does this in TypeScript (apps/mobile/src/lib/dialogue/loudness.ts)
and offline renders and the joins harness do it here. Both are pinned to the
standard's own reference values rather than to each other: a 997 Hz sine at
full scale reads -3.01 LUFS at 48 kHz, and the 48 kHz K-weighting
coefficients are BS.1770-4's Table 1 and Table 2. Identical constants are
asserted across the two files so neither can drift alone.

Agent speech only — nothing here reads, writes or keeps a file (invariant 3).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from voice_clips.audio import Pcm
from voice_clips.loudness import (
    LOUDNESS_TARGET_LUFS,
    PEAK_CEILING_DBFS,
    integrated_loudness,
    k_weighting,
    loudness_gain_db,
    normalise_loudness,
    sample_peak_dbfs,
)

REPO = Path(__file__).resolve().parents[2]
TS_LOUDNESS = REPO / "apps" / "mobile" / "src" / "lib" / "dialogue" / "loudness.ts"


def sine(rate: int, seconds: float, amplitude: float, hz: float = 997.0) -> NDArray[np.int16]:
    t = np.arange(round(rate * seconds)) / rate
    return np.round(amplitude * 32767 * np.sin(2 * np.pi * hz * t)).astype(np.int16)


class TestReference:
    def test_the_48k_coefficients_are_the_standards_tables(self) -> None:
        shelf, high_pass = k_weighting(48_000)
        np.testing.assert_allclose(
            shelf.b, [1.53512485958697, -2.69169618940638, 1.19839281085285], atol=1e-6
        )
        np.testing.assert_allclose(shelf.a, [1.0, -1.69065929318241, 0.73248077421585], atol=1e-6)
        np.testing.assert_allclose(high_pass.b, [1.0, -2.0, 1.0], atol=1e-12)
        np.testing.assert_allclose(
            high_pass.a, [1.0, -1.99004745483398, 0.99007225036621], atol=1e-6
        )

    def test_a_full_scale_997_hz_sine_reads_minus_3_01_lufs(self) -> None:
        assert integrated_loudness(Pcm(sine(48_000, 2, 1.0), 48_000)) == pytest.approx(
            -3.01, abs=0.05
        )

    def test_half_scale_reads_six_db_lower(self) -> None:
        assert integrated_loudness(Pcm(sine(48_000, 2, 0.5), 48_000)) == pytest.approx(
            -9.03, abs=0.05
        )

    def test_the_clips_own_24k_rate_reads_within_a_tenth(self) -> None:
        assert integrated_loudness(Pcm(sine(24_000, 2, 0.5), 24_000)) == pytest.approx(
            -9.03, abs=0.05
        )

    def test_silence_has_no_loudness(self) -> None:
        assert integrated_loudness(Pcm(np.zeros(24_000, dtype=np.int16), 24_000)) is None

    def test_an_empty_clip_has_no_loudness(self) -> None:
        assert integrated_loudness(Pcm(np.zeros(0, dtype=np.int16), 24_000)) is None

    def test_a_clip_under_one_block_is_measured_as_one_block(self) -> None:
        # Outside the standard (the module says so); within an LU of the long tone.
        short = integrated_loudness(Pcm(sine(24_000, 0.3, 0.5), 24_000))
        assert short == pytest.approx(-9.03, abs=1.0)

    def test_a_whisper_under_the_absolute_gate_has_no_loudness(self) -> None:
        # One least-significant bit of tone sits far under -70 LUFS.
        assert integrated_loudness(Pcm(sine(24_000, 1, 1 / 32767), 24_000)) is None

    def test_padding_barely_moves_the_level(self) -> None:
        tone = sine(24_000, 4, 0.5)
        padded = np.concatenate([np.zeros(24_000, np.int16), tone, np.zeros(24_000, np.int16)])
        bare = integrated_loudness(Pcm(tone, 24_000))
        framed = integrated_loudness(Pcm(padded, 24_000))
        assert bare is not None and framed is not None
        assert 0.0 <= bare - framed < 0.5


class TestGain:
    def test_a_quiet_clip_is_raised_to_the_target(self) -> None:
        assert loudness_gain_db(-21.0, -9.0) == pytest.approx(LOUDNESS_TARGET_LUFS + 21.0)

    def test_a_loud_clip_is_lowered_to_the_target(self) -> None:
        assert loudness_gain_db(-12.0, -0.5) == pytest.approx(LOUDNESS_TARGET_LUFS + 12.0)

    def test_the_peak_ceiling_stops_the_gain_before_it_clips(self) -> None:
        assert loudness_gain_db(-24.0, -3.0) == pytest.approx(PEAK_CEILING_DBFS + 3.0)

    def test_an_unmeasurable_clip_is_left_alone(self) -> None:
        assert loudness_gain_db(None, -3.0) == 0.0

    def test_a_silent_clip_has_no_peak_and_gets_no_gain(self) -> None:
        silent = np.zeros(2_400, dtype=np.int16)
        assert sample_peak_dbfs(silent) == float("-inf")
        assert sample_peak_dbfs(np.zeros(0, dtype=np.int16)) == float("-inf")
        assert loudness_gain_db(-20.0, sample_peak_dbfs(silent)) == 0.0
        out = normalise_loudness(Pcm(silent, 24_000))
        np.testing.assert_array_equal(out.samples, silent)

    def test_two_clips_land_within_half_an_lu(self) -> None:
        quiet = normalise_loudness(Pcm(sine(24_000, 1, 0.08), 24_000))
        loud = normalise_loudness(Pcm(sine(24_000, 1, 0.6), 24_000))
        a = integrated_loudness(quiet)
        b = integrated_loudness(loud)
        assert a is not None and b is not None
        assert abs(a - b) < 0.5
        assert a == pytest.approx(LOUDNESS_TARGET_LUFS, abs=0.5)

    def test_no_sample_ends_above_the_ceiling(self) -> None:
        out = normalise_loudness(Pcm(sine(24_000, 1, 0.05), 24_000))
        assert sample_peak_dbfs(out.samples) <= PEAK_CEILING_DBFS + 0.01

    def test_the_input_is_never_modified(self) -> None:
        samples = sine(24_000, 1, 0.1)
        before = samples.copy()
        normalise_loudness(Pcm(samples, 24_000))
        np.testing.assert_array_equal(samples, before)


class TestParityWithTheDevice:
    """The constants are stated twice, once per language. Pin them equal."""

    @staticmethod
    def _ts_constant(name: str) -> float:
        match = re.search(rf"export const {name} = (-?[0-9.]+);", TS_LOUDNESS.read_text())
        assert match is not None, f"{name} not found in {TS_LOUDNESS}"
        return float(match.group(1))

    def test_the_target_is_the_same_on_the_device(self) -> None:
        assert self._ts_constant("LOUDNESS_TARGET_LUFS") == LOUDNESS_TARGET_LUFS

    def test_the_ceiling_is_the_same_on_the_device(self) -> None:
        assert self._ts_constant("PEAK_CEILING_DBFS") == PEAK_CEILING_DBFS
