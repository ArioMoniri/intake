/**
 * ADR-039 S5: the stage's shapes. Controls are capsules, so their radius is
 * half their height, which keeps them concentric as Apple's design system
 * asks. Cards and messages use 22 pt. Nothing on the stage is rounder than a
 * capsule, and every other screen keeps INT-422's 12 pt ceiling
 * (designSystem.spec).
 */
import { describe, expect, it } from "vitest";

import { MIN_TAP } from "@/lib/a11y/target";

import { ORB_STATES } from "@/lib/motion/orb";

import { STAGE_RADIUS, STAGE_SIZE, capsule, stageOrbSize } from "./shape";

describe("stage shapes (ADR-039 S5)", () => {
  it("cards and messages are 22 pt", () => {
    expect(STAGE_RADIUS).toEqual({ card: 22, message: 22 });
  });

  it("a capsule's radius is half its height", () => {
    expect(capsule(52)).toBe(26);
    expect(capsule(MIN_TAP)).toBe(MIN_TAP / 2);
  });

  it("every control clears the 44 pt target floor (SC 2.5.8)", () => {
    for (const [name, size] of Object.entries(STAGE_SIZE)) {
      expect(size, name).toBeGreaterThanOrEqual(MIN_TAP);
    }
  });

  it("near miss: no stage radius is rounder than its own capsule", () => {
    for (const r of Object.values(STAGE_RADIUS)) {
      expect(r).toBeLessThanOrEqual(capsule(STAGE_SIZE.answer));
    }
  });
});

describe("the orb's size on the stage", () => {
  it("is largest while the patient talks, then while the agent speaks", () => {
    expect(stageOrbSize("listening", false)).toBeGreaterThan(stageOrbSize("speaking", false));
    expect(stageOrbSize("speaking", false)).toBeGreaterThan(stageOrbSize("thinking", false));
    expect(stageOrbSize("thinking", false)).toBeGreaterThan(stageOrbSize("idle", false));
  });

  it("is compact while answer cards or the keyboard need the room", () => {
    for (const state of ORB_STATES) {
      expect(stageOrbSize(state, true), state).toBe(stageOrbSize("idle", false));
    }
  });

  it("never draws smaller than a 44 pt target would, so it reads as one element", () => {
    for (const state of ORB_STATES) {
      expect(stageOrbSize(state, false), state).toBeGreaterThanOrEqual(MIN_TAP);
    }
  });
});
