/**
 * INT-423: every colour pair the conversation sets, in light, dark and the
 * OS Increase Contrast mode. Bubbles and text sit on solid fills, never on a
 * material, so each pair below is the pair on screen. e2e/chatRhythm.spec.ts
 * pins that DialogueIntake uses exactly these tokens.
 */
import { describe, expect, it } from "vitest";

import { colorsFor, type ColorToken } from "@/lib/theme";

function channel(v: number): number {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return (
    0.2126 * channel((n >> 16) & 0xff) +
    0.7152 * channel((n >> 8) & 0xff) +
    0.0722 * channel(n & 0xff)
  );
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** [text, fill, what it is]. */
const CHAT_PAIRS: readonly (readonly [ColorToken, ColorToken, string])[] = [
  ["ink", "surface", "the agent's question"],
  ["inkSoft", "surface", "the agent's aside and the lead-in line"],
  ["inkFaint", "surface", "the speaking and preparing state line"],
  ["ink", "surfaceRaised", "the patient's words"],
  ["inkSoft", "surfaceRaised", "the transcribing state line"],
  ["primary", "primarySoft", "the listening bubble's state"],
  ["inkFaint", "primarySoft", "the listening bubble's hint"],
  ["inkFaint", "background", "the voice-muted note above the transcript"],
];

/** The patient's and agent's own words are clinical text: AAA. */
const CLINICAL: readonly ColorToken[] = ["ink"];

const MODES = (["light", "dark"] as const).flatMap((scheme) =>
  (["standard", "high"] as const).map((level) => ({ scheme, level, name: `${scheme}/${level}` })),
);

describe("the conversation's colours", () => {
  it.each(MODES)("$name: every chat pair meets AA, and the words themselves AAA", (mode) => {
    const c = colorsFor(mode.scheme, mode.level);
    const failing = CHAT_PAIRS.filter(([fg, bg]) => {
      const floor = CLINICAL.includes(fg) ? 7 : 4.5;
      return contrast(c[fg], c[bg]) < floor;
    }).map(([fg, bg, use]) => `${use}: ${fg} on ${bg} ${contrast(c[fg], c[bg]).toFixed(2)}`);
    expect(failing).toEqual([]);
  });

  it("near miss: the old warm-paper faint ink on the listening wash would fail", () => {
    expect(contrast("#8A867A", "#EAF5F2")).toBeLessThan(4.5);
  });
});
