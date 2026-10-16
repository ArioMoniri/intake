/**
 * INT-492: the segmented question capsule, as data (GitHub #839).
 *
 * The owner asked for the "Soru N / M" progress to be redesigned after
 * spaceui.one. The owner then kept the within-bounds parts and declined the
 * rolling number (16 Oct 2026), so the capsule ships with a still count. This
 * suite holds the parts that are rules rather than looks:
 *
 * - one segment per section of the flow (the HPI dimensions, medicines and
 *   allergies, the history block, the closing note), each as wide as its
 *   share of the questions, so the filled length is exactly the old bar's
 *   fraction and a section change is the next segment becoming current;
 * - the count is display-only (invariant 22): one non-breaking atom, never
 *   grouped, and refused by the TTS guard if it ever travelled there;
 * - a screen reader hears ONE value, worded, never digit by digit.
 */
import { describe, expect, it } from "vitest";

import { assertSpeakableTr } from "../dialogue/tts";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import { colorsFor, type ColorScheme, type Contrast } from "../theme";
import {
  MAX_SEGMENTS,
  NBSP,
  capsuleChrome,
  capsuleCount,
  capsuleTrack,
  countParts,
  type CapsuleItem,
} from "./progressCapsule";
import { positionSpoken, questionPosition } from "./questionScreen";

const item = (id: string, section?: CapsuleItem["section"]): CapsuleItem =>
  section === undefined ? { id } : { id, section };

/** HPI ×4, medicines and allergies ×3, history ×2, the closing note ×1. */
const FLOW: readonly CapsuleItem[] = [
  item("a"),
  item("b"),
  item("c"),
  item("d"),
  item("m1", "meds_allergies"),
  item("m2", "meds_allergies"),
  item("m3", "meds_allergies"),
  item("h1", "pmh_fh_sh"),
  item("h2", "pmh_fh_sh"),
  item("extra"),
];

const at = (id: string, flow: readonly CapsuleItem[] = FLOW, grows = false) =>
  questionPosition(flow, id, grows);

describe("one segment per section, as wide as its share", () => {
  it("groups consecutive questions by section, the closing note on its own", () => {
    const track = capsuleTrack(FLOW, at("a"));
    expect(track.kind).toBe("segments");
    if (track.kind !== "segments") return;
    expect(track.segments.map((s) => s.weight)).toEqual([4, 3, 2, 1]);
  });

  it("marks done, current and upcoming, and fills the current one up to the question", () => {
    const track = capsuleTrack(FLOW, at("m2"));
    if (track.kind !== "segments") throw new Error("expected segments");
    expect(track.segments.map((s) => s.state)).toEqual(["done", "current", "upcoming", "upcoming"]);
    expect(track.segments.map((s) => s.fill)).toEqual([1, 2 / 3, 0, 0]);
  });

  it("the filled length is exactly the old bar's fraction, at every question", () => {
    for (const q of FLOW) {
      const position = at(q.id);
      const track = capsuleTrack(FLOW, position);
      if (track.kind !== "segments") throw new Error("expected segments");
      const total = track.segments.reduce((sum, s) => sum + s.weight, 0);
      const filled = track.segments.reduce((sum, s) => sum + s.weight * s.fill, 0);
      expect(filled / total, q.id).toBeCloseTo(position.fraction, 10);
    }
  });

  it("a section change is the next segment becoming current", () => {
    const before = capsuleTrack(FLOW, at("d"));
    const after = capsuleTrack(FLOW, at("m1"));
    if (before.kind !== "segments" || after.kind !== "segments") throw new Error("segments");
    expect(before.segments.map((s) => s.state)).toEqual([
      "current",
      "upcoming",
      "upcoming",
      "upcoming",
    ]);
    expect(after.segments.map((s) => s.state)).toEqual(["done", "current", "upcoming", "upcoming"]);
  });

  it("keys a segment by its section and place, so the same flow keeps its keys", () => {
    const one = capsuleTrack(FLOW, at("a"));
    const two = capsuleTrack(FLOW, at("h2"));
    if (one.kind !== "segments" || two.kind !== "segments") throw new Error("segments");
    expect(one.segments.map((s) => s.key)).toEqual(two.segments.map((s) => s.key));
    expect(new Set(one.segments.map((s) => s.key)).size).toBe(one.segments.length);
  });

  it("an id outside the list sits at the first place, as the bar does", () => {
    const track = capsuleTrack(FLOW, at("gated-out"));
    if (track.kind !== "segments") throw new Error("expected segments");
    expect(track.segments[0]).toMatchObject({ state: "current", fill: 1 / 4 });
  });

  it("a flow of one section is one segment, never an empty track", () => {
    const flow = [item("a"), item("b")];
    const track = capsuleTrack(flow, at("a", flow));
    if (track.kind !== "segments") throw new Error("expected segments");
    expect(track.segments).toEqual([
      expect.objectContaining({ weight: 2, fill: 1 / 2, state: "current" }),
    ]);
  });

  it("more sections than the capsule holds fall back to one continuous track", () => {
    const flow: CapsuleItem[] = [];
    for (let i = 0; i <= MAX_SEGMENTS; i += 1) {
      flow.push(item(`h${i}`), item(`m${i}`, "meds_allergies"));
    }
    const position = at("m0", flow);
    expect(capsuleTrack(flow, position)).toEqual({
      kind: "continuous",
      fraction: position.fraction,
    });
    // Near miss: exactly MAX_SEGMENTS sections still segment.
    const fits = flow.slice(0, MAX_SEGMENTS);
    expect(capsuleTrack(fits, at("h0", fits)).kind).toBe("segments");
  });
});

describe("the count is display-only (invariant 22)", () => {
  const word = tr["intake.progress.question"];

  it("reads Soru N / M as one non-breaking atom", () => {
    const count = capsuleCount(at("m2"), word);
    expect(count).toBe(`Soru${NBSP}6${NBSP}/${NBSP}10`);
    expect(NBSP).toBe("\u00A0");
    // No breakable space anywhere: the word, the numbers and the slash
    // wrap together or not at all.
    expect(count).not.toMatch(/[ \t\n\r\u1680\u2000-\u200B\u2028\u2029\u205F\u3000]/);
  });

  it("is the catalogue word plus the two numbers, in either language", () => {
    const flow = Array.from({ length: 9 }, (_, i) => item(`q${i}`));
    const position = questionPosition(flow, "q2", false);
    expect(capsuleCount(position, word)).toBe(`Soru${NBSP}3${NBSP}/${NBSP}9`);
    expect(capsuleCount(position, en["intake.progress.question"])).toBe(
      `Question${NBSP}3${NBSP}/${NBSP}9`,
    );
  });

  it("never groups digits, in either catalogue (useGrouping: false)", () => {
    const flow = Array.from({ length: 12345 }, (_, i) => item(`q${i}`));
    const position = questionPosition(flow, "q1233", false);
    expect(capsuleCount(position, word)).toBe(`Soru${NBSP}1234${NBSP}/${NBSP}12345`);
    expect(capsuleCount(position, en["intake.progress.question"])).not.toMatch(/\d[.,']\d/);
  });

  it("splits into two weights at a non-breaking space, so the halves never part", () => {
    const { head, tail } = countParts(capsuleCount(at("m2"), word));
    expect(head).toBe(`Soru${NBSP}6`);
    expect(tail).toBe(`${NBSP}/${NBSP}10`);
    expect(tail.startsWith(NBSP)).toBe(true);
    // Near miss: a count without the slash stays whole.
    expect(countParts("Soru")).toEqual({ head: "Soru", tail: "" });
  });

  it("is refused by the TTS guard, so it can only ever be shown", () => {
    const count = capsuleCount(at("a"), word);
    expect(() => assertSpeakableTr(count)).toThrow("tts_numeral_blocked");
  });
});

describe("a screen reader hears one value", () => {
  const word = tr["intake.progress.question"];
  const of = tr["intake.progress.of"];

  it("is the worded value the bar already announces, whole numbers, no slash", () => {
    const spoken = positionSpoken(at("m2"), word, of);
    expect(spoken).toBe("Soru 6, toplam 10");
    expect(spoken).not.toContain("/");
  });

  it("near miss: a digit-by-digit rendering is not that value", () => {
    const flow = Array.from({ length: 18 }, (_, i) => item(`q${i}`));
    const spoken = positionSpoken(questionPosition(flow, "q11", false), word, of);
    expect(spoken).toBe("Soru 12, toplam 18");
    expect(spoken).not.toBe("Soru 1 2, toplam 1 8");
  });
});

describe("the capsule's colours clear their floors", () => {
  function luminance(hex: string): number {
    const channel = (i: number) => {
      const c = parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
  }
  const ratio = (a: string, b: string) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const MODES = (["light", "dark"] as const).flatMap((scheme: ColorScheme) =>
    (["standard", "high"] as const).map((level: Contrast) => ({ scheme, level })),
  );

  it.each(MODES)("$scheme / $level: the count is AA, the fill is 3:1 on its track", (m) => {
    const colors = colorsFor(m.scheme, m.level);
    const chrome = capsuleChrome(colors);
    expect(ratio(chrome.countInk, chrome.countFill)).toBeGreaterThanOrEqual(4.5);
    expect(ratio(chrome.fill, chrome.track)).toBeGreaterThanOrEqual(3);
    expect(ratio(chrome.fill, chrome.ground)).toBeGreaterThanOrEqual(3);
  });

  it("the capsule is solid: every colour is an opaque theme hex, never a material", () => {
    const chrome = capsuleChrome(colorsFor("light", "standard"));
    for (const value of Object.values(chrome)) {
      expect(value).toMatch(/^#[0-9A-F]{6}$/i);
    }
  });
});
