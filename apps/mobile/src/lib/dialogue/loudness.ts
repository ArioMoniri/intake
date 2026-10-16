/**
 * Integrated loudness (ITU-R BS.1770-4) and one loudness for every clip
 * (INT-497).
 *
 * The owner asked for joins nobody can hear. Dead air is one half of a join;
 * LEVEL is the other: measured on the cast E04 set (docs/evidence/INT-497.md)
 * the acknowledgements sit ~3 LU under the questions they lead into, and the
 * set spans 9 LU, so "Teşekkürler." and the question after it sound like two
 * recordings. Peak or RMS matching would not fix that — they ignore how the
 * ear weights frequency — which is what BS.1770's K-weighting is for.
 *
 * The method, exactly as the standard gives it for one channel:
 *   1. K-weight: a high shelf (+4 dB above ~1.7 kHz) then a high-pass (~38 Hz).
 *      The coefficients are derived for the clip's own rate from the analog
 *      prototype, in the form libebur128 uses; at 48 kHz they reproduce the
 *      standard's tables (loudness.test.ts pins them).
 *   2. Mean square over 400 ms blocks overlapping by 75 %.
 *   3. Gate: drop blocks under -70 LUFS, then blocks more than 10 LU under the
 *      mean of what is left. A clip's padding is therefore not part of its level.
 *   4. L = -0.691 + 10·log10(mean of the kept blocks).
 * A clip shorter than one block is measured as one block — outside the
 * standard, stated here, and no clip the dialogue speaks is that short.
 *
 * The same function, pinned to the same reference values, is in
 * packages/voice-clips (voice_clips.loudness) for offline renders.
 *
 * Agent speech only: these are the clip store's scripted clips (invariant 3
 * governs patient audio, which never reaches this module). Gain changes level,
 * never words (invariant 10).
 */

/**
 * The level every clip is brought to. Spoken-word practice for small
 * speakers sits around -16 to -19 LUFS; -18 is where the measured E04
 * questions (median ≈ -16) come DOWN to and the acknowledgements (median
 * ≈ -19.3) come UP to without reaching the peak ceiling.
 */
export const LOUDNESS_TARGET_LUFS = -18;

/** No sample is ever raised above this. Gain stops here rather than clip. */
export const PEAK_CEILING_DBFS = -1;

const BLOCK_S = 0.4;
const STEP_S = 0.1;
const ABSOLUTE_GATE_LUFS = -70;
const RELATIVE_GATE_LU = 10;
const OFFSET = -0.691;

export interface Biquad {
  readonly b: readonly [number, number, number];
  readonly a: readonly [number, number, number];
}

/** The K-weighting pair for a sample rate (BS.1770-4 §2.1, libebur128 form). */
export function kWeightingCoefficients(rate: number): { shelf: Biquad; highPass: Biquad } {
  // Stage 1: the shelf, from its analog prototype.
  let f0 = 1681.974450955533;
  const gainDb = 3.999843853973347;
  let q = 0.7071752369554196;
  let k = Math.tan((Math.PI * f0) / rate);
  const vh = Math.pow(10, gainDb / 20);
  const vb = Math.pow(vh, 0.4996667741545416);
  const a0 = 1 + k / q + k * k;
  const shelf: Biquad = {
    b: [
      (vh + (vb * k) / q + k * k) / a0,
      (2 * (k * k - vh)) / a0,
      (vh - (vb * k) / q + k * k) / a0,
    ],
    a: [1, (2 * (k * k - 1)) / a0, (1 - k / q + k * k) / a0],
  };
  // Stage 2: the high-pass (RLB weighting).
  f0 = 38.13547087602444;
  q = 0.5003270373238773;
  k = Math.tan((Math.PI * f0) / rate);
  const d = 1 + k / q + k * k;
  const highPass: Biquad = {
    b: [1, -2, 1],
    a: [1, (2 * (k * k - 1)) / d, (1 - k / q + k * k) / d],
  };
  return { shelf, highPass };
}

function filter(input: Float64Array, { b, a }: Biquad): Float64Array {
  const out = new Float64Array(input.length);
  let x1 = 0;
  let x2 = 0;
  let y1 = 0;
  let y2 = 0;
  for (let i = 0; i < input.length; i += 1) {
    const x0 = input[i];
    const y0 = b[0] * x0 + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2;
    x2 = x1;
    x1 = x0;
    y2 = y1;
    y1 = y0;
    out[i] = y0;
  }
  return out;
}

/**
 * Integrated loudness of mono 16-bit samples, in LUFS — or null when every
 * block is under the absolute gate (a silent clip has no loudness to report,
 * and inventing one would set a gain on nothing).
 */
export function integratedLoudness(samples: Int16Array, rate: number): number | null {
  const x = new Float64Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    x[i] = samples[i] / 32768;
  }
  const { shelf, highPass } = kWeightingCoefficients(rate);
  const y = filter(filter(x, shelf), highPass);

  const block = Math.round(BLOCK_S * rate);
  const step = Math.round(STEP_S * rate);
  const energies: number[] = [];
  const meanSquare = (from: number, length: number) => {
    let sum = 0;
    for (let i = from; i < from + length; i += 1) {
      sum += y[i] * y[i];
    }
    return length > 0 ? sum / length : 0;
  };
  if (y.length < block) {
    energies.push(meanSquare(0, y.length));
  } else {
    for (let start = 0; start + block <= y.length; start += step) {
      energies.push(meanSquare(start, block));
    }
  }
  const loudnessOf = (z: number) => OFFSET + 10 * Math.log10(z);
  const aboveAbsolute = energies.filter((z) => z > 0 && loudnessOf(z) > ABSOLUTE_GATE_LUFS);
  if (aboveAbsolute.length === 0) {
    return null;
  }
  const mean = (values: number[]) => values.reduce((s, v) => s + v, 0) / values.length;
  const relativeGate = loudnessOf(mean(aboveAbsolute)) - RELATIVE_GATE_LU;
  const kept = aboveAbsolute.filter((z) => loudnessOf(z) > relativeGate);
  return loudnessOf(mean(kept));
}

/** The highest sample's level in dBFS (-Infinity for silence). */
export function samplePeakDbfs(samples: Int16Array): number {
  let peak = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const magnitude = Math.abs(samples[i]);
    if (magnitude > peak) {
      peak = magnitude;
    }
  }
  return peak === 0 ? Number.NEGATIVE_INFINITY : 20 * Math.log10(peak / 32768);
}

/**
 * The gain, in dB, that brings a clip to the target without lifting its peak
 * past the ceiling. A clip that could not be measured is left alone.
 */
export function loudnessGainDb(measuredLufs: number | null, peakDbfs: number): number {
  if (measuredLufs === null || !Number.isFinite(peakDbfs)) {
    return 0;
  }
  return Math.min(LOUDNESS_TARGET_LUFS - measuredLufs, PEAK_CEILING_DBFS - peakDbfs);
}

/** A mono clip at the target loudness. Pure: a new buffer, the input untouched. */
export function normaliseLoudness<T extends { sampleRate: number; samples: Int16Array }>(
  clip: T,
): T {
  const gainDb = loudnessGainDb(
    integratedLoudness(clip.samples, clip.sampleRate),
    samplePeakDbfs(clip.samples),
  );
  const gain = Math.pow(10, gainDb / 20);
  const out = new Int16Array(clip.samples.length);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = Math.max(-32768, Math.min(32767, Math.round(clip.samples[i] * gain)));
  }
  return { ...clip, samples: out };
}
