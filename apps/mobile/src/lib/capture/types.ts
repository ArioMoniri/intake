/**
 * The shapes the capture library speaks (INT-559).
 *
 * Patient audio exists in this app as `PcmChunk`s arriving from the
 * platform's microphone stream, a bounded in-memory buffer, and `PcmSegment`s
 * on their way to the dev ASR daemon. Nothing here is a path, a handle or a
 * name: CLAUDE.md invariant 3 allows no file, and no dev exception.
 */

/** One buffer of interleaved signed 16-bit little-endian samples, as the platform delivers it. */
export interface PcmChunk {
  readonly data: ArrayBuffer;
  /** The rate the platform actually delivers, which may differ from the one asked for. */
  readonly sampleRate: number;
  readonly channels: number;
}

/** A run of samples handed out of the buffer: at most the cap, then zeroed behind it. */
export interface PcmSegment {
  readonly samples: Int16Array;
  readonly sampleRate: number;
  readonly channels: number;
}

/** The format the capture asks the platform for. */
export interface PcmFormat {
  readonly sampleRate: number;
  readonly channels: number;
}

/**
 * What the dev ASR daemon takes natively (16 kHz mono); asking the platform
 * for it keeps the window small and spares the daemon a resample.
 */
export const CAPTURE_FORMAT: PcmFormat = { sampleRate: 16_000, channels: 1 };

/**
 * The microphone stream as the session reaches it. The real one is
 * expo-audio's AudioStream behind a lazy import (expoStream.ts); tests hand
 * in a fake, so every interleaving runs in node.
 */
export interface PcmStreamPort {
  /** Begin delivering chunks. Rejects when the platform cannot open the input. */
  start(): Promise<void>;
  /** Stop delivering and release the native input. Safe to call more than once. */
  stop(): void;
  /** Subscribe to chunks; returns the unsubscribe. */
  onBuffer(listener: (chunk: PcmChunk) => void): () => void;
}
