/**
 * Touch-target floor (INT-144).
 *
 * WCAG 2.2 SC 2.5.8 Target Size (Minimum) is Level AA and asks for 24×24 CSS
 * px. Both platform guidelines ask for more — 44×44 pt (Apple HIG) and 48×48
 * dp (Android) — and this app targets the higher of the three it can express
 * in one number, so `MIN_TAP` is 44 and every interactive element clears SC
 * 2.5.8 with room rather than by a hair.
 *
 * Two ways to reach it, and the choice is a design question, not a
 * conformance one:
 *
 * - **Grow the box** (`minHeight: MIN_TAP`) where the element owns its
 *   vertical space — buttons, list rows, cards.
 * - **Grow the target only** (`verticalSlop`) where the box is a small pill
 *   inside a dense row that six measured design passes converged on. RN's
 *   `hitSlop` enlarges the real pointer target without moving a pixel, which
 *   is exactly what SC 2.5.8 measures. Horizontal slop is deliberately NOT
 *   offered: adjacent chips sit 4–8 pt apart, and overlapping horizontal
 *   slop would make the second chip of a pair unreachable — trading one
 *   failure for a worse one.
 */

/** The app's own floor, above SC 2.5.8's 24 and at Apple's 44. */
export const MIN_TAP = 44;

/**
 * Vertical `hitSlop` that lifts an element of `laidOutHeight` to `MIN_TAP`.
 * Returns zeros once the element already clears the floor, so applying it
 * unconditionally is safe and the number in the source is always the honest
 * one rather than a guess.
 */
export function verticalSlop(laidOutHeight: number): { top: number; bottom: number } {
  const missing = Math.max(0, MIN_TAP - Math.max(0, laidOutHeight));
  const half = Math.ceil(missing / 2);
  return { top: half, bottom: half };
}

/** The target height an element of `laidOutHeight` reaches with that slop. */
export function slopped(laidOutHeight: number): number {
  const slop = verticalSlop(laidOutHeight);
  return Math.max(0, laidOutHeight) + slop.top + slop.bottom;
}
