/**
 * The level the barge-in watch reads (INT-559, for INT-291's detector).
 *
 * expo-audio's file recorder reported the platform meter in dBFS; the
 * stream reports samples instead, so the same scalar is computed here from
 * the chunk that just arrived. RMS over the chunk, in dBFS, floored at the
 * value the meter used for silence. Nothing is retained to compute it from
 * later (invariant 3).
 */

/** What the platform meter reported for silence; the floor here too. */
export const SILENCE_DBFS = -160;

const FULL_SCALE = 32_768;

export function levelDbfs(samples: Int16Array): number {
  if (samples.length === 0) {
    return SILENCE_DBFS;
  }
  let sumOfSquares = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const normalised = samples[index] / FULL_SCALE;
    sumOfSquares += normalised * normalised;
  }
  const rms = Math.sqrt(sumOfSquares / samples.length);
  if (rms <= 0) {
    return SILENCE_DBFS;
  }
  return Math.max(SILENCE_DBFS, Math.min(0, 20 * Math.log10(rms)));
}
