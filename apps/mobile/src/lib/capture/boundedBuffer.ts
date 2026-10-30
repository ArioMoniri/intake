/**
 * The bounded PCM buffer (INT-559; CLAUDE.md invariant 3: memory buffers
 * ≤ 60 s, zeroed on every trigger).
 *
 * This is the only place patient samples rest between the microphone and the
 * upload. It is allocated once at its cap, filled from the front, handed out
 * as a copy, and zeroed — by `take` and by `clear` alike — with `fill(0)` over
 * the whole backing array, not only the part that was used. A JS heap cannot
 * be mlocked; what the app can do is keep the resident window small and
 * short-lived, and that is what the cap and the zeroing are for.
 */

/** The longest run of audio the app may hold in memory, in seconds. */
export const MAX_CAPTURE_SECONDS = 60;

/**
 * Samples needed to hold `seconds` of audio at `sampleRate` × `channels`,
 * never more than the cap allows.
 */
export function capacityFor(seconds: number, sampleRate: number, channels: number): number {
  if (!(seconds > 0) || !(sampleRate > 0) || !(channels > 0)) {
    throw new RangeError("capacityFor: seconds, sampleRate and channels must be positive");
  }
  const window = Math.min(seconds, MAX_CAPTURE_SECONDS);
  return Math.ceil(window * sampleRate) * Math.floor(channels);
}

export interface BoundedPcmBuffer {
  /** Samples the buffer can hold. Fixed at creation. */
  readonly capacity: number;
  /** Samples currently held. */
  readonly length: number;
  /** Copies as many samples as fit; returns how many did NOT fit. */
  push(samples: Int16Array): number;
  /** Hands the held samples out as a fresh copy and zeroes the buffer. */
  take(): Int16Array;
  /** Zeroes the buffer and hands nothing out. */
  clear(): void;
  /** True when every sample in the backing array is zero. */
  isZeroed(): boolean;
}

export function createBoundedPcmBuffer(capacity: number): BoundedPcmBuffer {
  if (!(capacity > 0) || !Number.isFinite(capacity)) {
    throw new RangeError("createBoundedPcmBuffer: capacity must be a positive finite number");
  }
  const backing = new Int16Array(Math.floor(capacity));
  let length = 0;

  const zero = () => {
    backing.fill(0);
    length = 0;
  };

  return {
    get capacity() {
      return backing.length;
    },
    get length() {
      return length;
    },
    push(samples) {
      const free = backing.length - length;
      const fit = Math.min(free, samples.length);
      if (fit > 0) {
        backing.set(samples.subarray(0, fit), length);
        length += fit;
      }
      return samples.length - fit;
    },
    take() {
      const copy = Int16Array.from(backing.subarray(0, length));
      zero();
      return copy;
    },
    clear() {
      zero();
    },
    isZeroed() {
      return backing.every((sample) => sample === 0);
    },
  };
}
