/**
 * INT-497 — loudness, so two clips said one after the other sound like one
 * voice at one level.
 *
 * Measured on the E04 set (docs/evidence/INT-497.md): the acknowledgements sit
 * about 3 LU under the questions they lead into, and the whole set spans
 * 9 LU. A join between two clips of one turn is therefore a step in level the
 * patient hears every time. The fix is ITU-R BS.1770 integrated loudness and a
 * gain to one target, capped by the sample peak so nothing clips.
 *
 * The reference values are the standard's own: a 997 Hz sine at full scale
 * reads -3.01 LUFS at 48 kHz, and the 48 kHz K-weighting coefficients are
 * BS.1770-4's Table 1 and Table 2. packages/voice-clips holds the same
 * function in Python and is pinned to the same values.
 */
import { describe, expect, it } from "vitest";

import {
  LOUDNESS_TARGET_LUFS,
  PEAK_CEILING_DBFS,
  integratedLoudness,
  kWeightingCoefficients,
  loudnessGainDb,
  normaliseLoudness,
  samplePeakDbfs,
} from "./loudness";

function sine(rate: number, seconds: number, amplitude: number, hz = 997): Int16Array {
  const out = new Int16Array(Math.round(rate * seconds));
  for (let i = 0; i < out.length; i += 1) {
    out[i] = Math.round(amplitude * 32767 * Math.sin((2 * Math.PI * hz * i) / rate));
  }
  return out;
}

describe("kWeightingCoefficients — the standard's 48 kHz table", () => {
  it("reproduces BS.1770-4 Table 1 (the shelf) and Table 2 (the high-pass)", () => {
    const { shelf, highPass } = kWeightingCoefficients(48_000);
    const close = (a: readonly number[], b: readonly number[]) =>
      a.forEach((value, i) => expect(value).toBeCloseTo(b[i], 6));
    close(shelf.b, [1.53512485958697, -2.69169618940638, 1.19839281085285]);
    close(shelf.a, [1, -1.69065929318241, 0.73248077421585]);
    close(highPass.b, [1, -2, 1]);
    close(highPass.a, [1, -1.99004745483398, 0.99007225036621]);
  });
});

describe("integratedLoudness — the reference tone", () => {
  it("reads a full-scale 997 Hz sine at 48 kHz as -3.01 LUFS", () => {
    expect(integratedLoudness(sine(48_000, 2, 1), 48_000)).toBeCloseTo(-3.01, 1);
  });

  it("reads half scale 6 dB lower — loudness is level, not a lookup", () => {
    expect(integratedLoudness(sine(48_000, 2, 0.5), 48_000)).toBeCloseTo(-9.03, 1);
  });

  it("reads the clips' own 24 kHz rate within a tenth of an LU of 48 kHz", () => {
    expect(integratedLoudness(sine(24_000, 2, 0.5), 24_000)).toBeCloseTo(-9.03, 1);
  });

  it("gates silence out, so a clip's padding barely moves its level", () => {
    // Two seconds of silence around four of speech-level tone. Ungated, the
    // mean square would fall by 10·log10(4/6) = 1.76 LU; gated, only the few
    // 400 ms blocks straddling an edge still count, and they cost a fraction.
    const rate = 24_000;
    const tone = sine(rate, 4, 0.5);
    const padded = new Int16Array(tone.length + rate * 2);
    padded.set(tone, rate);
    const drop = integratedLoudness(tone, rate)! - integratedLoudness(padded, rate)!;
    expect(drop).toBeGreaterThanOrEqual(0);
    expect(drop).toBeLessThan(0.5);
  });

  it("says a silent clip has no loudness rather than inventing one", () => {
    expect(integratedLoudness(new Int16Array(24_000), 24_000)).toBeNull();
  });
});

describe("loudnessGainDb — to the target, and never past the peak ceiling", () => {
  it("raises a quiet clip to the target when the peak allows it", () => {
    expect(loudnessGainDb(-21, -9)).toBeCloseTo(LOUDNESS_TARGET_LUFS + 21, 6);
  });

  it("lowers a loud clip to the target", () => {
    expect(loudnessGainDb(-12, -0.5)).toBeCloseTo(LOUDNESS_TARGET_LUFS + 12, 6);
  });

  it("stops at the peak ceiling instead of clipping", () => {
    expect(loudnessGainDb(-24, -3)).toBeCloseTo(PEAK_CEILING_DBFS + 3, 6);
  });

  it("leaves a clip it cannot measure alone", () => {
    expect(loudnessGainDb(null, -3)).toBe(0);
  });
});

describe("normaliseLoudness — what the clip store does to every clip", () => {
  it("brings two clips a quiet and a loud one to within half an LU of each other", () => {
    const rate = 24_000;
    const quiet = normaliseLoudness({ sampleRate: rate, samples: sine(rate, 1, 0.08) });
    const loud = normaliseLoudness({ sampleRate: rate, samples: sine(rate, 1, 0.6) });
    const a = integratedLoudness(quiet.samples, rate)!;
    const b = integratedLoudness(loud.samples, rate)!;
    expect(Math.abs(a - b)).toBeLessThan(0.5);
    expect(a).toBeCloseTo(LOUDNESS_TARGET_LUFS, 0);
  });

  it("never puts a sample above the peak ceiling", () => {
    const rate = 24_000;
    const out = normaliseLoudness({ sampleRate: rate, samples: sine(rate, 1, 0.05) });
    expect(samplePeakDbfs(out.samples)).toBeLessThanOrEqual(PEAK_CEILING_DBFS + 0.01);
  });

  it("returns a new buffer and leaves the input untouched", () => {
    const rate = 24_000;
    const samples = sine(rate, 1, 0.1);
    const before = samples.slice();
    normaliseLoudness({ sampleRate: rate, samples });
    expect(samples).toEqual(before);
  });
});
