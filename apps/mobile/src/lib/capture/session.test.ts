/**
 * INT-559 — the capture session: a microphone stream into the bounded
 * buffer, segments handed at the cap, everything zeroed on finish, discard,
 * and the moment the dialogue closes (CLAUDE.md invariant 3; INT-551's
 * closed-after-every-await pattern for invariant 9/21).
 *
 * The stream arrives as a port, so every interleaving is node-tested without
 * a microphone — the one simulator this repo has records silence.
 */
import { describe, expect, it } from "vitest";

import { createCaptureSession } from "./session";
import type { PcmChunk, PcmSegment, PcmStreamPort } from "./types";

interface FakeStream {
  port: PcmStreamPort;
  calls: string[];
  emit(samples: Int16Array, sampleRate?: number, channels?: number): void;
  emitBytes(bytes: Uint8Array, sampleRate?: number, channels?: number): void;
  release(): void;
  listeners(): number;
}

function fakeStream(options: { gateStart?: boolean; failStart?: boolean } = {}): FakeStream {
  const listeners = new Set<(chunk: PcmChunk) => void>();
  const calls: string[] = [];
  let release: () => void = () => undefined;
  return {
    port: {
      start: () => {
        calls.push("start");
        if (options.failStart) {
          return Promise.reject(new Error("mic_busy"));
        }
        if (options.gateStart) {
          return new Promise<void>((resolve) => {
            release = resolve;
          });
        }
        return Promise.resolve();
      },
      stop: () => {
        calls.push("stop");
      },
      onBuffer: (listener) => {
        listeners.add(listener);
        calls.push("subscribe");
        return () => {
          listeners.delete(listener);
          calls.push("unsubscribe");
        };
      },
    },
    calls,
    emit(samples, sampleRate = 16_000, channels = 1) {
      const data = samples.buffer.slice(
        samples.byteOffset,
        samples.byteOffset + samples.byteLength,
      ) as ArrayBuffer;
      for (const listener of listeners) {
        listener({ data, sampleRate, channels });
      }
    },
    emitBytes(bytes, sampleRate = 16_000, channels = 1) {
      const data = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
      for (const listener of listeners) {
        listener({ data: data as ArrayBuffer, sampleRate, channels });
      }
    },
    release: () => release(),
    listeners: () => listeners.size,
  };
}

function ramp(length: number, from = 1): Int16Array {
  const samples = new Int16Array(length);
  for (let index = 0; index < length; index += 1) {
    samples[index] = from + index;
  }
  return samples;
}

const RATE = 1_000;

describe("opening the microphone", () => {
  it("subscribes, starts the stream and reports capturing", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    expect(session.capturing).toBe(false);
    expect(await session.open()).toBe(true);
    expect(session.capturing).toBe(true);
    expect(stream.calls).toEqual(["subscribe", "start"]);
    expect(session.levelDbfs()).toBeUndefined();
    expect(session.zeroed()).toBe(true);
  });

  it("a closed dialogue never starts it", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => true,
      onSegment: () => undefined,
    });
    expect(await session.open()).toBe(false);
    expect(session.capturing).toBe(false);
    expect(stream.calls).toEqual([]);
    expect(stream.listeners()).toBe(0);
  });

  it("a dialogue that closes while the stream starts is left stopped and silent", async () => {
    const stream = fakeStream({ gateStart: true });
    let closed = false;
    const handed: PcmSegment[] = [];
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => closed,
      onSegment: (segment) => handed.push(segment),
    });
    const opening = session.open();
    closed = true; // the RED lands while the platform is bringing the input up
    stream.release();
    expect(await opening).toBe(false);
    expect(session.capturing).toBe(false);
    expect(stream.calls).toEqual(["subscribe", "start", "unsubscribe", "stop"]);
    expect(stream.listeners()).toBe(0);
    expect(handed).toEqual([]);
  });

  it("a platform failure to start leaves nothing subscribed and rejects", async () => {
    const stream = fakeStream({ failStart: true });
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    await expect(session.open()).rejects.toThrow("mic_busy");
    expect(session.capturing).toBe(false);
    expect(stream.listeners()).toBe(0);
    expect(stream.calls).toEqual(["subscribe", "start", "unsubscribe"]);
  });

  it("opens once: a second open while capturing changes nothing", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    await session.open();
    expect(await session.open()).toBe(true);
    expect(stream.calls).toEqual(["subscribe", "start"]);
  });
});

describe("while capturing", () => {
  it("accumulates the chunks and reads the level of the latest one", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    await session.open();
    stream.emit(new Int16Array(500).fill(0), RATE);
    expect(session.secondsBuffered()).toBeCloseTo(0.5, 6);
    expect(session.levelDbfs()).toBe(-160);
    stream.emit(new Int16Array(500).fill(16_384), RATE);
    expect(session.secondsBuffered()).toBeCloseTo(1, 6);
    expect(session.levelDbfs()).toBeCloseTo(-6.02, 1);
    expect(session.zeroed()).toBe(false);
  });

  it("hands a segment the moment the cap is reached and keeps capturing", async () => {
    const stream = fakeStream();
    const handed: PcmSegment[] = [];
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: (segment) => handed.push(segment),
      maxSeconds: 2,
    });
    await session.open();
    stream.emit(ramp(800, 1), RATE);
    stream.emit(ramp(800, 801), RATE);
    expect(handed).toEqual([]);
    stream.emit(ramp(800, 1601), RATE);
    // 2400 samples in: exactly one cap-sized segment out, 400 still buffered
    expect(handed).toHaveLength(1);
    expect(handed[0].samples.length).toBe(2_000);
    expect(handed[0].sampleRate).toBe(RATE);
    expect(handed[0].channels).toBe(1);
    expect(Array.from(handed[0].samples)).toEqual(Array.from(ramp(2_000, 1)));
    expect(session.secondsBuffered()).toBeCloseTo(0.4, 6);
    expect(session.capturing).toBe(true);
    const tail = session.finish();
    expect(tail).not.toBeNull();
    expect(Array.from(tail!.samples)).toEqual(Array.from(ramp(400, 2_001)));
  });

  it("a chunk larger than the whole window is handed in cap-sized segments", async () => {
    const stream = fakeStream();
    const handed: PcmSegment[] = [];
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: (segment) => handed.push(segment),
      maxSeconds: 1,
    });
    await session.open();
    stream.emit(ramp(2_500), RATE);
    expect(handed.map((segment) => segment.samples.length)).toEqual([1_000, 1_000]);
    expect(session.secondsBuffered()).toBeCloseTo(0.5, 6);
  });

  it("the window is never wider than sixty seconds, whatever is asked", async () => {
    const stream = fakeStream();
    const handed: PcmSegment[] = [];
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: (segment) => handed.push(segment),
      maxSeconds: 600,
    });
    await session.open();
    stream.emit(new Int16Array(61 * RATE).fill(1), RATE);
    expect(handed).toHaveLength(1);
    expect(handed[0].samples.length).toBe(60 * RATE);
  });

  it("sizes the window from the format the platform actually delivers", async () => {
    const stream = fakeStream();
    const handed: PcmSegment[] = [];
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: (segment) => handed.push(segment),
      maxSeconds: 1,
    });
    await session.open();
    // asked for 16 kHz mono; the hardware delivers 48 kHz stereo
    stream.emit(new Int16Array(96_000).fill(3), 48_000, 2);
    expect(handed).toHaveLength(1);
    expect(handed[0].samples.length).toBe(96_000);
    expect(handed[0].sampleRate).toBe(48_000);
    expect(handed[0].channels).toBe(2);
  });

  it("counts every sample heard, across hand-outs and after the turn ends", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
      maxSeconds: 1,
    });
    expect(session.samplesHeard()).toBe(0);
    await session.open();
    expect(session.samplesHeard()).toBe(0);
    stream.emit(ramp(1_500), RATE); // hands 1000 out, keeps 500
    expect(session.samplesHeard()).toBe(1_500);
    session.finish();
    expect(session.samplesHeard()).toBe(1_500);
    session.discard();
    expect(session.samplesHeard()).toBe(1_500);
  });

  it("ignores a trailing odd byte rather than reading it as a sample", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    await session.open();
    stream.emitBytes(new Uint8Array([1, 0, 2, 0, 9]), RATE);
    expect(session.secondsBuffered()).toBeCloseTo(2 / RATE, 9);
  });

  it("a dialogue that closes mid-capture discards on the next chunk", async () => {
    const stream = fakeStream();
    let closed = false;
    const handed: PcmSegment[] = [];
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => closed,
      onSegment: (segment) => handed.push(segment),
    });
    await session.open();
    stream.emit(ramp(500), RATE);
    closed = true;
    stream.emit(ramp(500), RATE);
    expect(session.capturing).toBe(false);
    expect(session.secondsBuffered()).toBe(0);
    expect(session.zeroed()).toBe(true);
    expect(session.levelDbfs()).toBeUndefined();
    expect(handed).toEqual([]);
    expect(stream.calls).toEqual(["subscribe", "start", "unsubscribe", "stop"]);
  });
});

describe("finishing", () => {
  it("stops the stream and hands the tail out, zeroed behind it", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    await session.open();
    stream.emit(ramp(300), RATE);
    const tail = session.finish();
    expect(tail).not.toBeNull();
    expect(Array.from(tail!.samples)).toEqual(Array.from(ramp(300)));
    expect(tail!.sampleRate).toBe(RATE);
    expect(session.capturing).toBe(false);
    expect(session.secondsBuffered()).toBe(0);
    expect(session.zeroed()).toBe(true);
    expect(session.levelDbfs()).toBeUndefined();
    expect(stream.calls).toEqual(["subscribe", "start", "unsubscribe", "stop"]);
  });

  it("hands nothing when nothing arrived, and still stops the stream", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    await session.open();
    expect(session.finish()).toBeNull();
    expect(stream.calls).toEqual(["subscribe", "start", "unsubscribe", "stop"]);
  });

  it("is single-shot, and a chunk after it is dropped", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    await session.open();
    stream.emit(ramp(10), RATE);
    session.finish();
    expect(session.finish()).toBeNull();
    stream.emit(ramp(10), RATE);
    expect(session.secondsBuffered()).toBe(0);
    expect(stream.calls.filter((call) => call === "stop")).toHaveLength(1);
  });

  it("finish before open hands nothing and touches no stream", () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    expect(session.finish()).toBeNull();
    expect(stream.calls).toEqual([]);
  });
});

describe("discarding", () => {
  it("stops the stream, zeroes the buffer and hands nothing out", async () => {
    const stream = fakeStream();
    const handed: PcmSegment[] = [];
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: (segment) => handed.push(segment),
    });
    await session.open();
    stream.emit(ramp(900), RATE);
    session.discard();
    expect(handed).toEqual([]);
    expect(session.capturing).toBe(false);
    expect(session.secondsBuffered()).toBe(0);
    expect(session.zeroed()).toBe(true);
    expect(session.levelDbfs()).toBeUndefined();
    expect(stream.calls).toEqual(["subscribe", "start", "unsubscribe", "stop"]);
    expect(session.finish()).toBeNull();
  });

  it("is safe before open and after finish", async () => {
    const stream = fakeStream();
    const session = createCaptureSession({
      stream: stream.port,
      closed: () => false,
      onSegment: () => undefined,
    });
    session.discard();
    expect(stream.calls).toEqual([]);
    await session.open();
    session.finish();
    session.discard();
    expect(stream.calls.filter((call) => call === "stop")).toHaveLength(1);
  });
});
