/**
 * The capture session (INT-559): the microphone stream into the bounded
 * buffer, segments handed out at the cap, everything zeroed on finish, on
 * discard, and the moment the dialogue closes.
 *
 * Why a port and a `closed` function: the dialogue closes when a RED the
 * patient sees stands, and a RED can land while the platform is still
 * bringing the input up (INT-551's finding, CLAUDE.md invariants 9 and 21).
 * So the session reads `closed()` after every await and on every chunk, and a
 * closed dialogue ends the capture where it stands — stream stopped, buffer
 * zeroed, nothing handed out. The stream arrives as `PcmStreamPort`, so all
 * of this runs in node (session.test.ts); the one simulator this repo has
 * records silence.
 *
 * Invariant 3: the buffer is allocated at the cap (`MAX_CAPTURE_SECONDS`)
 * from the format the platform actually delivers, a chunk that would cross
 * the cap hands a cap-sized segment out first, and no sample is ever dropped
 * or kept past the trigger that ends the turn.
 */
import { MAX_CAPTURE_SECONDS, capacityFor, createBoundedPcmBuffer } from "./boundedBuffer";
import type { BoundedPcmBuffer } from "./boundedBuffer";
import { levelDbfs } from "./level";
import type { PcmChunk, PcmSegment, PcmStreamPort } from "./types";

export interface CaptureSessionOptions {
  stream: PcmStreamPort;
  /** The dialogue has closed (a RED, a leave, a terminal turn): read before every act. */
  closed: () => boolean;
  /** A cap-sized segment, handed the moment the buffer is full. The samples are the callee's. */
  onSegment: (segment: PcmSegment) => void;
  /** The window, in seconds; never more than `MAX_CAPTURE_SECONDS`. */
  maxSeconds?: number;
}

export interface CaptureSession {
  /**
   * Open the microphone, unless the dialogue closes first. Resolves to
   * whether it is capturing. A platform failure rejects.
   */
  open(): Promise<boolean>;
  readonly capturing: boolean;
  /** The level of the chunk that arrived last, or undefined before the first one. */
  levelDbfs(): number | undefined;
  /** Seconds of audio held right now (at most the window). */
  secondsBuffered(): number;
  /** Every sample this session has heard, across hand-outs; never reset. */
  samplesHeard(): number;
  /**
   * Stop the stream and hand out what is held, zeroed behind it. Null when
   * nothing arrived, or when the session is not capturing.
   */
  finish(): PcmSegment | null;
  /** Stop the stream and zero everything; nothing is handed out. */
  discard(): void;
  /** True when no sample is held — the resting state and the state after every trigger. */
  zeroed(): boolean;
}

const BYTES_PER_SAMPLE = 2;

export function createCaptureSession(options: CaptureSessionOptions): CaptureSession {
  const { stream, closed, onSegment } = options;
  const maxSeconds = Math.min(options.maxSeconds ?? MAX_CAPTURE_SECONDS, MAX_CAPTURE_SECONDS);

  let capturing = false;
  let unsubscribe: (() => void) | null = null;
  let buffer: BoundedPcmBuffer | null = null;
  let sampleRate = 0;
  let channels = 0;
  let lastLevel: number | undefined;
  let samplesHeard = 0;

  const stopStream = () => {
    if (unsubscribe !== null) {
      unsubscribe();
      unsubscribe = null;
    }
    stream.stop();
  };

  const zeroEverything = () => {
    buffer?.clear();
    lastLevel = undefined;
  };

  const discard = () => {
    const wasOpen = capturing || unsubscribe !== null;
    capturing = false;
    if (wasOpen) {
      stopStream();
    }
    zeroEverything();
  };

  const handOut = (samples: Int16Array) => {
    onSegment({ samples, sampleRate, channels });
  };

  const onChunk = (chunk: PcmChunk) => {
    if (!capturing) {
      return;
    }
    if (closed()) {
      discard();
      return;
    }
    const wholeSamples = Math.floor(chunk.data.byteLength / BYTES_PER_SAMPLE);
    if (wholeSamples === 0) {
      return;
    }
    const samples = new Int16Array(chunk.data, 0, wholeSamples);
    if (buffer === null) {
      sampleRate = chunk.sampleRate;
      channels = chunk.channels;
      buffer = createBoundedPcmBuffer(capacityFor(maxSeconds, sampleRate, channels));
    }
    lastLevel = levelDbfs(samples);
    samplesHeard += samples.length;
    let offset = 0;
    while (offset < samples.length) {
      const overflow = buffer.push(samples.subarray(offset));
      offset = samples.length - overflow;
      if (buffer.length === buffer.capacity) {
        handOut(buffer.take());
      }
    }
  };

  return {
    async open() {
      if (capturing) {
        return true;
      }
      if (closed()) {
        return false;
      }
      unsubscribe = stream.onBuffer(onChunk);
      try {
        await stream.start();
      } catch (error) {
        unsubscribe();
        unsubscribe = null;
        throw error;
      }
      if (closed()) {
        // The RED landed while the platform brought the input up.
        stopStream();
        zeroEverything();
        return false;
      }
      capturing = true;
      return true;
    },
    get capturing() {
      return capturing;
    },
    levelDbfs: () => lastLevel,
    secondsBuffered() {
      if (buffer === null || sampleRate === 0 || channels === 0) {
        return 0;
      }
      return buffer.length / (sampleRate * channels);
    },
    samplesHeard: () => samplesHeard,
    finish() {
      if (!capturing) {
        return null;
      }
      capturing = false;
      stopStream();
      lastLevel = undefined;
      if (buffer === null || buffer.length === 0) {
        zeroEverything();
        return null;
      }
      return { samples: buffer.take(), sampleRate, channels };
    },
    discard,
    zeroed: () => buffer === null || buffer.isZeroed(),
  };
}
