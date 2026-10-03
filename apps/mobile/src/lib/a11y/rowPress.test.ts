/**
 * Row press feedback (INT-451, docs/design/interaction-patterns.md §3.1).
 *
 * A grouped-list row shows a press the way a UIKit cell and a Material 3
 * list item do: its fill steps to a highlight, instantly, and its text stays
 * at full ink. Before INT-451 the whole row dimmed to `motion.press.rowOpacity`,
 * which also dims the words: the near miss below shows a sublabel falling
 * under AA while the finger is down.
 *
 * The step is a state swap, not an animation (ADR-033 §1: nothing here has a
 * duration, a curve or a transform), so it needs no reduce-motion branch.
 */
import { describe, expect, it } from "vitest";

import {
  colorsFor,
  motion,
  rowPressFill,
  switchTrackToken,
  SYSTEM_ROLES,
  type ColorScheme,
  type Contrast,
  type ThemeColors,
} from "../theme";

function channel(hex: string, at: number): number {
  const c = parseInt(hex.slice(at, at + 2), 16) / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  return 0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `fg` drawn at `alpha` over `bg`: what a dimmed row actually paints. */
function composite(fg: string, bg: string, alpha: number): string {
  const mix = (at: number): string =>
    Math.round(
      parseInt(fg.slice(at, at + 2), 16) * alpha + parseInt(bg.slice(at, at + 2), 16) * (1 - alpha),
    )
      .toString(16)
      .padStart(2, "0");
  return `#${mix(1)}${mix(3)}${mix(5)}`;
}

const MODES: readonly (readonly [ColorScheme, Contrast])[] = [
  ["light", "standard"],
  ["dark", "standard"],
  ["light", "high"],
  ["dark", "high"],
];

describe("a pressed row highlights; its words keep their ink", () => {
  it("the highlight is a fill the palette already pins: systemGray5 / surfaceContainerHighest", () => {
    expect(rowPressFill).toBe("surfaceRaised");
    expect(SYSTEM_ROLES[rowPressFill]).toMatchObject({
      ios: "systemGray5",
      android: "surfaceContainerHighest",
    });
  });

  it.each(MODES)("%s / %s: every row pair clears its floor on the pressed fill", (scheme, mode) => {
    const colors: ThemeColors = colorsFor(scheme, mode);
    const fill = colors[rowPressFill];
    // The row's label is clinical text: AAA.
    expect(contrast(colors.ink, fill)).toBeGreaterThanOrEqual(7);
    // Trailing values and sublabels: AA (SC 1.4.3).
    expect(contrast(colors.inkSoft, fill)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(colors.inkFaint, fill)).toBeGreaterThanOrEqual(4.5);
    // The leading glyph and the chevron: a graphic, 3:1 (SC 1.4.11).
    expect(contrast(colors.primary, fill)).toBeGreaterThanOrEqual(3);
  });

  it.each(MODES)("%s / %s: the press is visible against the resting cell", (scheme, mode) => {
    const colors = colorsFor(scheme, mode);
    // A step the eye sees as a change of fill. Apple's own cell highlight is
    // about 1.4:1 on white; systemGray5 is the gentler step this app already
    // uses for chips and tracks.
    expect(contrast(colors[rowPressFill], colors.surface)).toBeGreaterThanOrEqual(1.2);
  });

  it("near miss: dimming the row to rowOpacity dropped its sublabel under AA", () => {
    const colors = colorsFor("light", "standard");
    const dimmed = composite(colors.inkFaint, colors.surface, motion.press.rowOpacity);
    // At rest the sublabel clears AA, and on the highlight it still does…
    expect(contrast(colors.inkFaint, colors.surface)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(colors.inkFaint, colors[rowPressFill])).toBeGreaterThanOrEqual(4.5);
    // …but drawn at rowOpacity it measures about 3.1:1 while the finger is down.
    expect(contrast(dimmed, colors.surface)).toBeLessThan(4.5);
  });
});

/**
 * The switch row's own track (INT-451 follow-up, captured on INT451-16e).
 * The off track is `surfaceRaised`, which is also the pressed row's fill, so
 * while the finger was down the track vanished into the row and only the knob
 * was left. A UISwitch's off track is a translucent fill that is always a
 * step darker than whatever sits behind it; this track does the same with an
 * opaque token, stepping to `surface` on the pressed fill.
 */
describe("a switch row's off track stays visible when the row is pressed", () => {
  const cases = [
    [false, false],
    [false, true],
    [true, false],
    [true, true],
  ] as const;

  it("the track token for each state", () => {
    expect(switchTrackToken({ checked: false, pressed: false })).toBe("surfaceRaised");
    expect(switchTrackToken({ checked: false, pressed: true })).toBe("surface");
    expect(switchTrackToken({ checked: true, pressed: false })).toBe("primary");
    expect(switchTrackToken({ checked: true, pressed: true })).toBe("primary");
  });

  it.each(MODES)("%s / %s: the track steps off the row fill in every state", (scheme, mode) => {
    const colors = colorsFor(scheme, mode);
    for (const [checked, pressed] of cases) {
      const row = pressed ? colors[rowPressFill] : colors.surface;
      const track = colors[switchTrackToken({ checked, pressed })];
      // The same visible step the pressed row itself must make (1.2:1).
      expect(contrast(track, row), `${checked}/${pressed}`).toBeGreaterThanOrEqual(1.2);
    }
  });

  it.each(MODES)("%s / %s: the knob is a 3:1 graphic on its track (SC 1.4.11)", (scheme, mode) => {
    const colors = colorsFor(scheme, mode);
    for (const [checked, pressed] of cases) {
      const track = colors[switchTrackToken({ checked, pressed })];
      const knob = checked ? colors.onPrimary : colors.inkFaint;
      expect(contrast(knob, track), `${checked}/${pressed}`).toBeGreaterThanOrEqual(3);
    }
  });

  it("near miss: the old resting track on the pressed fill is the same colour", () => {
    const colors = colorsFor("light", "standard");
    expect(contrast(colors.surfaceRaised, colors[rowPressFill])).toBe(1);
  });
});
