/**
 * The fade policy (INT-335, MOTION-6;
 * docs/design/motion/motion-verification.md §2.2, §2.3, §4 MOTION-6).
 *
 * Every app-authored fade has one shape: opacity only, no delay, the one
 * ease-out curve, and no longer than the 02 §5.2a budget. Under reduce-motion
 * it collapses to nothing at all — "collapse to zero, not to a shorter
 * movement" (INT-144). There is no exit fade: exits are instant
 * (motion-verification.md §2.1 #3).
 *
 * The three shapes the module hands out are asserted together, because each
 * reaches a different Reanimated surface and each could drift on its own:
 * `fadeSpec` (the numbers), `enterFor` (a mount's layout animation) and
 * `cssFade` (a CSS transition on a view that is already mounted).
 */
import { describe, expect, it } from "vitest";

import { motion, type Bezier } from "../theme";
import { cssFade, cubicBezierCss, enterFor, fadeSpec, type FadeSpec } from "./fade";

const SETTINGS = [{ reduce: false }, { reduce: true }] as const;

/** Reanimated's own shorthand split: whitespace outside parentheses. */
function shorthandParts(value: string): string[] {
  return value.trim().split(/\s+(?![^()]*\))/);
}

/** `cubic-bezier(a, b, c, d)` → [a, b, c, d]; null when it is not that shape. */
function controlPoints(css: string): number[] | null {
  const m = /^cubic-bezier\(([^()]*)\)$/.exec(css);
  if (m === null) {
    return null;
  }
  return m[1].split(",").map((part) => Number(part.trim()));
}

/** `120ms` → 120; NaN for anything else. */
function ms(value: string): number {
  return /^\d+(\.\d+)?ms$/.test(value) ? Number(value.slice(0, -2)) : Number.NaN;
}

/**
 * An ease-out curve front-loads the change: both control points sit on or
 * above the diagonal. An ease-in would put them below it, and no ease-in
 * exists in the app.
 */
function isEaseOut(b: Bezier): boolean {
  const [x1, y1, x2, y2] = b;
  return y1 >= x1 && y2 >= x2 && (y1 > x1 || y2 > x2);
}

function expectFadeShape(spec: FadeSpec, label: string): void {
  expect(spec.property, label).toBe("opacity");
  expect(spec.delayMs, label).toBe(0);
  expect(spec.easing, label).toEqual(motion.easing.out);
  expect(spec.durationMs, label).toBeGreaterThanOrEqual(0);
  expect(spec.durationMs, label).toBeLessThanOrEqual(motion.fadeMs);
}

describe("fades (02 §5.2a: opacity only, one curve, within the budget)", () => {
  it("every fade is opacity-only, delay 0, out-eased and ≤ fadeMs", () => {
    expect(isEaseOut(motion.easing.out)).toBe(true);

    for (const context of SETTINGS) {
      const label = `reduce=${context.reduce}`;
      expectFadeShape(fadeSpec(context), `fadeSpec ${label}`);

      const enter = enterFor(context);
      if (enter !== undefined) {
        expectFadeShape(enter, `enterFor ${label}`);
      }

      const css = cssFade(context);
      expect(css.transitionProperty, `cssFade ${label}`).toBe("opacity");
      expect(css.transitionDelay, `cssFade ${label}`).toBe("0ms");
      expect(ms(css.transitionDuration), `cssFade ${label}`).toBeLessThanOrEqual(motion.fadeMs);

      // The shorthand carries the curve — the one string form Reanimated's
      // native side parses a cubic-bezier from — and it must say exactly
      // what the longhands say: property, duration, curve, delay.
      const [property, duration, curve, delay, ...rest] = shorthandParts(css.transition);
      expect(rest, `cssFade ${label}`).toEqual([]);
      expect(property).toBe(css.transitionProperty);
      expect(duration).toBe(css.transitionDuration);
      expect(delay).toBe(css.transitionDelay);
      expect(controlPoints(curve)).toEqual([...motion.easing.out]);
    }

    // With motion allowed, a fade is the full token, not a shorter one: the
    // budget is one number however it is spelled.
    expect(fadeSpec({ reduce: false }).durationMs).toBe(motion.duration.fade);
    expect(enterFor({ reduce: false })).toEqual(fadeSpec({ reduce: false }));
    expect(ms(cssFade({ reduce: false }).transitionDuration)).toBe(motion.duration.fade);
  });

  it("every fade collapses to 0 under reduce-motion", () => {
    expect(fadeSpec({ reduce: true }).durationMs).toBe(0);
    // A mount under reduce-motion registers no layout animation at all: the
    // element simply exists on the next frame.
    expect(enterFor({ reduce: true })).toBeUndefined();
  });

  it("cssFade returns 0 ms under reduce-motion", () => {
    const css = cssFade({ reduce: true });
    expect(css.transitionDuration).toBe("0ms");
    expect(shorthandParts(css.transition)[1]).toBe("0ms");
  });

  it("cubicBezierCss renders four control points", () => {
    for (const [name, curve] of Object.entries(motion.easing)) {
      const rendered = cubicBezierCss(curve);
      expect(controlPoints(rendered), name).toEqual([...curve]);
      expect(controlPoints(rendered), name).toHaveLength(4);
    }
    expect(cubicBezierCss([0.23, 1, 0.32, 1])).toBe("cubic-bezier(0.23, 1, 0.32, 1)");
  });
});
