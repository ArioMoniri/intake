/**
 * INT-423: the conversation's rhythm (docs/design/chat-rhythm.md).
 *
 * Consecutive turns from one speaker sit together as a group, and only the
 * group's last bubble carries the tail. A change of speaker opens the full
 * turn gap. A bubble keeps a readable measure, and at the large-text scale it
 * takes the whole width so a long Turkish word at an accessibility size never
 * breaks inside itself.
 */
import { describe, expect, it } from "vitest";

import { LARGE_TEXT_SCALE } from "@/lib/prefs/appearance";
import { spacing } from "@/lib/theme";

import {
  BUBBLE_SHARE,
  GROUP_GAP,
  GROUPED_MARGIN,
  MEASURE_MAX,
  TURN_GAP,
  bubbleMaxWidth,
  placeTurns,
  sideOf,
} from "./rhythm";

describe("grouping consecutive turns", () => {
  it("a run from one speaker sits together, and only its last bubble has the tail", () => {
    expect(placeTurns(["agent", "agent", "patient", "patient", "patient", "agent"])).toEqual([
      { grouped: false, tail: false },
      { grouped: true, tail: true },
      { grouped: false, tail: false },
      { grouped: true, tail: false },
      { grouped: true, tail: true },
      { grouped: false, tail: true },
    ]);
  });

  it("near miss: alternating speakers never group, and every bubble keeps its tail", () => {
    const placed = placeTurns(["agent", "patient", "agent", "patient"]);
    expect(placed.every((p) => !p.grouped && p.tail)).toBe(true);
  });

  it("an empty transcript places nothing, and a lone turn has its tail", () => {
    expect(placeTurns([])).toEqual([]);
    expect(placeTurns(["agent"])).toEqual([{ grouped: false, tail: true }]);
  });

  it("the grouped gap is the 4 pt half step, taken out of the 16 pt turn gap", () => {
    expect(TURN_GAP).toBe(spacing.md);
    expect(GROUP_GAP).toBe(spacing.xs);
    expect(GROUPED_MARGIN).toBe(GROUP_GAP - TURN_GAP);
    expect(GROUPED_MARGIN).toBeLessThan(0);
  });

  it("agent turns of every kind are one speaker; the patient's words are the other", () => {
    expect(sideOf({ kind: "agent_question", questionId: "q" })).toBe("agent");
    expect(sideOf({ kind: "agent_confirm", questionId: "q", values: [] })).toBe("agent");
    expect(sideOf({ kind: "agent_unclear", questionId: "q" })).toBe("agent");
    expect(sideOf({ kind: "patient", workId: 1, status: "text", text: "x" })).toBe("patient");
    expect(sideOf({ kind: "patient", workId: 2, status: "transcribing", text: "" })).toBe(
      "patient",
    );
  });
});

describe("a readable measure", () => {
  it("a bubble takes most of a phone's width, so the two speakers stay distinct", () => {
    expect(bubbleMaxWidth(358, 1.0)).toBe(Math.round(358 * BUBBLE_SHARE));
    expect(BUBBLE_SHARE).toBeGreaterThan(0.7);
    expect(BUBBLE_SHARE).toBeLessThan(0.9);
  });

  it("a wide window caps the line, so landscape text never runs past a readable measure", () => {
    expect(bubbleMaxWidth(812, 1.0)).toBe(MEASURE_MAX);
    // About 70 characters of 17 pt body text.
    expect(MEASURE_MAX).toBeLessThanOrEqual(600);
  });

  it("from the large-text scale up, a bubble takes the whole width", () => {
    for (const scale of [LARGE_TEXT_SCALE, 1.8, 2.0, 3.1]) {
      expect(bubbleMaxWidth(343, scale), `at ${scale}`).toBe(343);
    }
    // Near miss: one step below, the measure still applies.
    expect(bubbleMaxWidth(343, 1.3)).toBeLessThan(343);
  });
});
