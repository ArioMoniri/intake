"""Integrated loudness (ITU-R BS.1770-4) and one loudness for every clip (INT-497).

**Agent speech only.** Like everything in this package the input is a
scripted clip, never patient audio (CLAUDE.md invariant 3; the header of
:mod:`voice_clips.audio` is the argument). This module opens no file and
imports no audio library: it takes samples already in memory and returns a
number or new samples.

Why loudness and not peak or RMS: measured on the cast E04 set
(docs/evidence/INT-497.md) the acknowledgements sit ~3 LU under the questions
they lead into and the set spans 9 LU, so a lead-in and its question sound
like two recordings. Peak and RMS ignore how the ear weights frequency, which
is the whole of what BS.1770's K-weighting adds.

The method, as the standard gives it for one channel:

1. **K-weight** — a high shelf (+4 dB above ~1.7 kHz), then a high-pass
   (~38 Hz). The biquads are derived for the clip's own rate from the analog
   prototype in the form libebur128 uses; at 48 kHz they reproduce the
   standard's Table 1 and Table 2 (tests/voice/test_clip_loudness.py).
   The cascade is applied by FFT convolution with its impulse response,
   truncated at :data:`IMPULSE_RESPONSE_S` — by then the slowest pole (the
   38 Hz high-pass) has decayed below double precision, so this is the
   recursive filter to the last bit, without a per-sample Python loop.
2. Mean square over 400 ms blocks overlapping by 75 %.
3. Gate: drop blocks under -70 LUFS, then those more than 10 LU under the
   mean of what is left — a clip's padding is not part of its level.
4. ``L = -0.691 + 10·log10(mean of the kept blocks)``.

A clip shorter than one block is measured as one block: outside the
standard, said here, and no clip the dialogue speaks is that short.

The device holds the same function in TypeScript
(``apps/mobile/src/lib/dialogue/loudness.ts``); both are pinned to the
standard's reference values and their constants are asserted equal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

import numpy as np
from numpy.typing import NDArray

from voice_clips.audio import Pcm

__all__ = [
    "IMPULSE_RESPONSE_S",
    "LOUDNESS_TARGET_LUFS",
    "PEAK_CEILING_DBFS",
    "Biquad",
    "integrated_loudness",
    "k_weighting",
    "loudness_gain_db",
    "normalise_loudness",
    "sample_peak_dbfs",
]

#: The level every clip is brought to. Spoken-word practice for small speakers
#: is -16 to -19 LUFS; -18 is where the measured E04 questions (median ≈ -16)
#: come DOWN to and the acknowledgements (median ≈ -19.3) come UP to without
#: reaching the peak ceiling. Asserted equal to the device's constant.
LOUDNESS_TARGET_LUFS: Final = -18.0

#: No sample is ever raised above this; the gain stops here rather than clip.
PEAK_CEILING_DBFS: Final = -1.0

#: Length of the K-weighting impulse response used for the convolution.
IMPULSE_RESPONSE_S: Final = 0.5

_BLOCK_S: Final = 0.4
_STEP_S: Final = 0.1
_ABSOLUTE_GATE_LUFS: Final = -70.0
_RELATIVE_GATE_LU: Final = 10.0
_OFFSET: Final = -0.691
_FULL_SCALE: Final = 32768.0


@dataclass(frozen=True)
class Biquad:
    """One second-order section, ``a[0]`` normalised to 1."""

    b: tuple[float, float, float]
    a: tuple[float, float, float]


def k_weighting(rate: int) -> tuple[Biquad, Biquad]:
    """The shelf and the high-pass for ``rate`` (BS.1770-4 §2.1, libebur128 form)."""
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = math.tan(math.pi * f0 / rate)
    vh = 10 ** (gain_db / 20)
    vb = vh**0.4996667741545416
    a0 = 1 + k / q + k * k
    shelf = Biquad(
        b=((vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0),
        a=(1.0, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0),
    )
    f0, q = 38.13547087602444, 0.5003270373238773
    k = math.tan(math.pi * f0 / rate)
    d = 1 + k / q + k * k
    high_pass = Biquad(b=(1.0, -2.0, 1.0), a=(1.0, 2 * (k * k - 1) / d, (1 - k / q + k * k) / d))
    return shelf, high_pass


def _run(section: Biquad, signal: list[float]) -> list[float]:
    b0, b1, b2 = section.b
    _, a1, a2 = section.a
    out: list[float] = []
    x1 = x2 = y1 = y2 = 0.0
    for x0 in signal:
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, x0, y1, y0
        out.append(y0)
    return out


@lru_cache(maxsize=8)
def _impulse_response(rate: int) -> NDArray[np.float64]:
    impulse = [0.0] * round(rate * IMPULSE_RESPONSE_S)
    impulse[0] = 1.0
    shelf, high_pass = k_weighting(rate)
    return np.asarray(_run(high_pass, _run(shelf, impulse)), dtype=np.float64)


def _k_weighted(signal: NDArray[np.float64], rate: int) -> NDArray[np.float64]:
    response = _impulse_response(rate)
    size = signal.size + response.size - 1
    nfft = 1 << (size - 1).bit_length()
    spectrum = np.fft.rfft(signal, nfft) * np.fft.rfft(response, nfft)
    weighted: NDArray[np.float64] = np.fft.irfft(spectrum, nfft)[: signal.size]
    return weighted


def integrated_loudness(pcm: Pcm) -> float | None:
    """Integrated loudness in LUFS, or ``None`` when every block is under the
    absolute gate — a silent clip has no loudness, and inventing one would set
    a gain on nothing."""
    if pcm.samples.size == 0:
        return None
    signal = pcm.samples.astype(np.float64) / _FULL_SCALE
    weighted = _k_weighted(signal, pcm.sample_rate_hz)
    block = round(_BLOCK_S * pcm.sample_rate_hz)
    step = round(_STEP_S * pcm.sample_rate_hz)
    squared = weighted * weighted
    if weighted.size < block:
        energies = np.asarray([squared.mean()])
    else:
        cumulative = np.concatenate([[0.0], np.cumsum(squared)])
        starts = np.arange(0, weighted.size - block + 1, step)
        energies = (cumulative[starts + block] - cumulative[starts]) / block
    positive = energies[energies > 0]
    if positive.size == 0:
        return None
    levels = _OFFSET + 10 * np.log10(positive)
    above = positive[levels > _ABSOLUTE_GATE_LUFS]
    if above.size == 0:
        return None
    relative_gate = _OFFSET + 10 * math.log10(float(above.mean())) - _RELATIVE_GATE_LU
    kept = above[_OFFSET + 10 * np.log10(above) > relative_gate]
    return _OFFSET + 10 * math.log10(float(kept.mean()))


def sample_peak_dbfs(samples: NDArray[np.int16]) -> float:
    """The highest sample's level in dBFS (``-inf`` for silence)."""
    if samples.size == 0:
        return -math.inf
    peak = float(np.abs(samples.astype(np.int32)).max())
    return -math.inf if peak == 0 else 20 * math.log10(peak / _FULL_SCALE)


def loudness_gain_db(measured_lufs: float | None, peak_dbfs: float) -> float:
    """The gain to the target, never lifting the peak past the ceiling. A clip
    that could not be measured is left alone."""
    if measured_lufs is None or not math.isfinite(peak_dbfs):
        return 0.0
    return min(LOUDNESS_TARGET_LUFS - measured_lufs, PEAK_CEILING_DBFS - peak_dbfs)


def normalise_loudness(pcm: Pcm) -> Pcm:
    """The clip at the target loudness. A new buffer; the input is untouched."""
    gain_db = loudness_gain_db(integrated_loudness(pcm), sample_peak_dbfs(pcm.samples))
    scaled = np.round(pcm.samples.astype(np.float64) * 10 ** (gain_db / 20))
    clipped = np.clip(scaled, -32768, 32767).astype(np.int16)
    return Pcm(samples=clipped, sample_rate_hz=pcm.sample_rate_hz)
