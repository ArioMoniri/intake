/**
 * ADR-038 A1: a new agent bubble springs in (INT-462).
 *
 * The arbiter (INT-337) still decides whether a bubble moves at all: only the
 * element it grants, as the `content` class, enters with motion, and every
 * other arrival renders at its end state. What changes is how a granted
 * bubble enters: an 8 pt rise on ADR-037 P1's critically damped spring,
 * under the same 120 ms opacity fade. Under Reduce Motion the rise is gone
 * and the fade stays (Apple's dissolve substitution). While a RED is
 * presented nothing moves at all.
 */
import { describe, expect, it } from "vitest";

import { motion } from "../theme";
import { BUBBLE_RISE, BUBBLE_SPRING, bubbleEntrance, bubbleGranted } from "./bubbles";
import { initialDialogueMotion, stepDialogueMotion, type DialogueScene } from "./transients";

const scene = (keys: readonly string[]): DialogueScene => ({
  entries: keys.map((key) => ({ key, kind: "agent" as const })),
  chips: null,
  working: false,
  strip: { filled: 0, total: 3 },
  windowOpen: true,
});

describe("ADR-038 A1 numbers", () => {
  it("the rise is 8 pt and the spring is critically damped, with overshoot clamped", () => {
    expect(BUBBLE_RISE).toBe(8);
    expect(BUBBLE_SPRING).toEqual({
      stiffness: 1500,
      damping: 77.5,
      mass: 1,
      overshootClamping: true,
    });
    const zeta =
      BUBBLE_SPRING.damping / (2 * Math.sqrt(BUBBLE_SPRING.stiffness * BUBBLE_SPRING.mass));
    expect(zeta).toBeGreaterThanOrEqual(1);
    expect(zeta).toBeLessThan(1.01);
  });

  it("near miss: kinetics' spring(320, 24) is underdamped and would overshoot", () => {
    const zeta = 24 / (2 * Math.sqrt(320));
    expect(zeta).toBeLessThan(1);
  });
});

describe("bubbleEntrance", () => {
  it("a granted bubble springs in under the one fade", () => {
    const entrance = bubbleEntrance({ granted: true, redPresented: false, reduce: false });
    expect(entrance).toEqual({
      kind: "spring",
      rise: BUBBLE_RISE,
      spring: BUBBLE_SPRING,
      fade: {
        property: "opacity",
        durationMs: motion.duration.fade,
        delayMs: 0,
        easing: motion.easing.out,
      },
    });
  });

  it("Reduce Motion: no rise, only the 120 ms opacity fade", () => {
    expect(bubbleEntrance({ granted: true, redPresented: false, reduce: true })).toEqual({
      kind: "fade",
      fade: {
        property: "opacity",
        durationMs: motion.duration.fade,
        delayMs: 0,
        easing: motion.easing.out,
      },
    });
  });

  it("a bubble the arbiter did not grant renders at its end state", () => {
    for (const reduce of [false, true]) {
      expect(bubbleEntrance({ granted: false, redPresented: false, reduce })).toEqual({
        kind: "none",
      });
    }
  });

  it("never on RED: a presented RED stills every bubble, at any setting", () => {
    for (const reduce of [false, true]) {
      for (const granted of [false, true]) {
        expect(bubbleEntrance({ granted, redPresented: true, reduce })).toEqual({ kind: "none" });
      }
    }
  });
});

describe("bubbleGranted reads the arbiter's answer", () => {
  const first = initialDialogueMotion(scene(["agent_question:q1:0"]));

  it("history on the first frame never moves", () => {
    for (const reduce of [false, true]) {
      expect(bubbleGranted(first, "agent_question:q1:0", reduce)).toBe(false);
    }
  });

  it("a new agent bubble is granted while it is the arbiter's running element", () => {
    const next = stepDialogueMotion(first, scene(["agent_question:q1:0", "agent_question:q2:0"]), {
      reduce: false,
    });
    expect(bubbleGranted(next, "agent_question:q2:0", false)).toBe(true);
    expect(bubbleGranted(next, "agent_question:q1:0", false)).toBe(false);
  });

  it("under Reduce Motion the arbiter frees the slot at once, and the grant still holds", () => {
    const next = stepDialogueMotion(first, scene(["agent_question:q1:0", "agent_question:q2:0"]), {
      reduce: true,
    });
    expect(next.arbiter.running).toBeNull();
    expect(bubbleGranted(next, "agent_question:q2:0", true)).toBe(true);
  });

  it("near miss: an equal arrival in the same commit is not granted, so two never move together", () => {
    const next = stepDialogueMotion(
      first,
      scene(["agent_question:q1:0", "agent_unclear:q1:0", "agent_question:q2:0"]),
      { reduce: false },
    );
    const granted = ["agent_unclear:q1:0", "agent_question:q2:0"].filter((key) =>
      bubbleGranted(next, key, false),
    );
    expect(granted).toHaveLength(1);
  });
});
