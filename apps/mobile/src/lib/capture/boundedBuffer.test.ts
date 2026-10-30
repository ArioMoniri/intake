/**
 * INT-559 — the bounded PCM buffer (CLAUDE.md invariant 3: memory buffers
 * ≤ 60 s, zeroed on every trigger).
 *
 * The buffer is the only place patient samples rest between the microphone
 * and the upload. These tests pin the three facts that make it safe: it can
 * never hold more than the cap, handing the samples out zeroes it, and
 * clearing it zeroes it without handing anything out.
 */
import { describe, expect, it } from "vitest";

import { MAX_CAPTURE_SECONDS, capacityFor, createBoundedPcmBuffer } from "./boundedBuffer";

function ramp(length: number, from = 1): Int16Array {
  const samples = new Int16Array(length);
  for (let index = 0; index < length; index += 1) {
    samples[index] = from + index;
  }
  return samples;
}

describe("capacityFor", () => {
  it("is sixty seconds of samples at the asked rate and channel count", () => {
    expect(MAX_CAPTURE_SECONDS).toBe(60);
    expect(capacityFor(60, 16_000, 1)).toBe(960_000);
    expect(capacityFor(60, 48_000, 2)).toBe(5_760_000);
  });

  it("never exceeds the sixty-second cap, whatever is asked", () => {
    expect(capacityFor(90, 16_000, 1)).toBe(capacityFor(60, 16_000, 1));
    expect(capacityFor(Number.POSITIVE_INFINITY, 16_000, 1)).toBe(capacityFor(60, 16_000, 1));
  });

  it("allows a smaller window", () => {
    expect(capacityFor(0.5, 16_000, 2)).toBe(16_000);
  });

  it("refuses a format that cannot hold audio", () => {
    expect(() => capacityFor(60, 0, 1)).toThrow(RangeError);
    expect(() => capacityFor(60, 16_000, 0)).toThrow(RangeError);
    expect(() => capacityFor(0, 16_000, 1)).toThrow(RangeError);
    expect(() => capacityFor(60, Number.NaN, 1)).toThrow(RangeError);
  });
});

describe("createBoundedPcmBuffer", () => {
  it("rests zeroed", () => {
    const buffer = createBoundedPcmBuffer(8);
    expect(buffer.capacity).toBe(8);
    expect(buffer.length).toBe(0);
    expect(buffer.isZeroed()).toBe(true);
  });

  it("takes what fits and reports the rest", () => {
    const buffer = createBoundedPcmBuffer(8);
    expect(buffer.push(ramp(5))).toBe(0);
    expect(buffer.length).toBe(5);
    expect(buffer.isZeroed()).toBe(false);
    // 3 more fit; 2 do not
    expect(buffer.push(ramp(5, 100))).toBe(2);
    expect(buffer.length).toBe(8);
    expect(Array.from(buffer.take())).toEqual([1, 2, 3, 4, 5, 100, 101, 102]);
  });

  it("hands the samples out as a copy and is zeroed afterwards", () => {
    const buffer = createBoundedPcmBuffer(8);
    buffer.push(ramp(4));
    const taken = buffer.take();
    expect(Array.from(taken)).toEqual([1, 2, 3, 4]);
    expect(buffer.length).toBe(0);
    expect(buffer.isZeroed()).toBe(true);
    // the copy is the caller's: nothing it does reaches the buffer
    taken.fill(7);
    expect(buffer.isZeroed()).toBe(true);
    expect(buffer.take().length).toBe(0);
  });

  it("clear zeroes without handing anything out", () => {
    const buffer = createBoundedPcmBuffer(8);
    buffer.push(ramp(8));
    expect(buffer.isZeroed()).toBe(false);
    buffer.clear();
    expect(buffer.length).toBe(0);
    expect(buffer.isZeroed()).toBe(true);
    expect(buffer.take().length).toBe(0);
  });

  it("a full buffer refuses every further sample until taken", () => {
    const buffer = createBoundedPcmBuffer(4);
    expect(buffer.push(ramp(4))).toBe(0);
    expect(buffer.push(ramp(3))).toBe(3);
    expect(buffer.length).toBe(4);
    buffer.take();
    expect(buffer.push(ramp(3))).toBe(0);
    expect(buffer.length).toBe(3);
  });

  it("refuses a capacity that could not bound anything", () => {
    expect(() => createBoundedPcmBuffer(0)).toThrow(RangeError);
    expect(() => createBoundedPcmBuffer(-1)).toThrow(RangeError);
  });
});
