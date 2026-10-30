/**
 * INT-559 — the level the barge-in watch reads (INT-291's detector takes a
 * dBFS scalar). With the recorder gone there is no platform meter to read, so
 * the level is computed from the chunk that just arrived and nothing is kept
 * to compute it from later.
 */
import { describe, expect, it } from "vitest";

import { SILENCE_DBFS, levelDbfs } from "./level";

function constant(value: number, length = 1600): Int16Array {
  return new Int16Array(length).fill(value);
}

function sine(amplitude: number, length = 1600): Int16Array {
  const samples = new Int16Array(length);
  for (let index = 0; index < length; index += 1) {
    samples[index] = Math.round(amplitude * Math.sin((2 * Math.PI * index) / 16));
  }
  return samples;
}

describe("levelDbfs", () => {
  it("reads silence as the same floor expo-audio's meter reported", () => {
    expect(SILENCE_DBFS).toBe(-160);
    expect(levelDbfs(new Int16Array(0))).toBe(SILENCE_DBFS);
    expect(levelDbfs(constant(0))).toBe(SILENCE_DBFS);
  });

  it("reads a full-scale square as 0 dBFS and never above it", () => {
    expect(levelDbfs(constant(32_767))).toBeCloseTo(0, 2);
    expect(levelDbfs(constant(-32_768))).toBeLessThanOrEqual(0);
  });

  it("reads half scale as about minus six", () => {
    expect(levelDbfs(constant(16_384))).toBeCloseTo(-6.02, 1);
  });

  it("is an RMS reading: a sine sits three decibels under a square of the same peak", () => {
    const square = levelDbfs(constant(16_384));
    const wave = levelDbfs(sine(16_384));
    expect(square - wave).toBeCloseTo(3.01, 1);
  });

  it("is monotonic in amplitude", () => {
    const levels = [100, 1_000, 5_000, 20_000].map((amplitude) => levelDbfs(sine(amplitude)));
    for (let index = 1; index < levels.length; index += 1) {
      expect(levels[index]).toBeGreaterThan(levels[index - 1]);
    }
  });

  it("stays finite for a single sample", () => {
    expect(Number.isFinite(levelDbfs(new Int16Array([1])))).toBe(true);
  });
});
