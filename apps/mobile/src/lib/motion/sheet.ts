/**
 * ADR-038 A3: the in-tree detent sheet (INT-473).
 *
 * Pure, so lib/motion/sheet.test.ts pins every rule; components/DetentSheet
 * draws the sheet and native/sheetMotion.ts runs the spring, and neither
 * writes a number of its own.
 *
 * - Detents: medium is half the frame; large sits just under the screen's
 *   own bar. An in-tree sheet lives below the native header, so the large
 *   detent stops there rather than covering it.
 * - A release goes where the throw points (the position projected a short
 *   time ahead), or closes past the dismiss threshold.
 * - Presenting and settling use A1's critically damped spring, which cannot
 *   overshoot. A patient's dismissal settles with it too. A privacy close and
 *   a RED close are instant at every setting: RED never waits for a sheet.
 * - Reduce Motion: the 120 ms fade on presenting, an instant close, and a
 *   release that snaps without a spring. The drag itself still follows the
 *   finger, because that is direct manipulation, not motion the app adds.
 */
import { BUBBLE_SPRING } from "./bubbles";
import { fadeSpec, type FadeSpec } from "./fade";

export type Detent = "medium" | "large";

/** A1's spring: ζ ≈ 1.0005, overshoot clamped. */
export const SHEET_SPRING = BUBBLE_SPRING;

/** The gap, in points, between the screen's own bar and the large detent. */
export const SHEET_LARGE_GAP = 8;

/** How far ahead a release is projected, in seconds, to read the throw. */
const PROJECTION_S = 0.12;

/** The frame the sheet lives in: its height, and where the screen's bar ends. */
export interface SheetFrame {
  readonly height: number;
  readonly top: number;
}

/** Each detent as the sheet's top edge, in points from the frame's top. */
export function detentOffsets({ height, top }: SheetFrame): Record<Detent, number> {
  const medium = Math.round(height / 2);
  return { medium, large: Math.min(top + SHEET_LARGE_GAP, medium) };
}

/**
 * Where a release goes. `y` is the sheet's top edge at release and `velocity`
 * the finger's, in points per millisecond (React Native's PanResponder unit).
 */
export function settleTarget({
  offsets,
  height,
  y,
  velocity,
}: {
  readonly offsets: Record<Detent, number>;
  readonly height: number;
  readonly y: number;
  readonly velocity: number;
}): Detent | "closed" {
  const projected = y + velocity * PROJECTION_S * 1000;
  const dismissAt = offsets.medium + (height - offsets.medium) / 2;
  if (projected >= dismissAt) {
    return "closed";
  }
  const toLarge = Math.abs(projected - offsets.large);
  const toMedium = Math.abs(projected - offsets.medium);
  return toLarge < toMedium ? "large" : "medium";
}

/** The furthest a release may move, in points, and still count as a tap. */
const TAP_SLOP = 4;

/**
 * A tap on the grabber moves to the other detent: the single-pointer
 * alternative to the drag (SC 2.5.7), as UIKit's own grabber does.
 */
export function nextDetent(detent: Detent): Detent {
  return detent === "medium" ? "large" : "medium";
}

/** A release that barely moved is a tap, not a drag. */
export function isTap({ dx, dy }: { readonly dx: number; readonly dy: number }): boolean {
  return Math.abs(dx) <= TAP_SLOP && Math.abs(dy) <= TAP_SLOP;
}

export type SheetPresent =
  | { readonly kind: "spring"; readonly spring: typeof SHEET_SPRING }
  | { readonly kind: "fade"; readonly fade: FadeSpec };

export function sheetPresent({ reduce }: { readonly reduce: boolean }): SheetPresent {
  if (reduce) {
    // The fade is the full one: under Reduce Motion it is what remains, as
    // A1 keeps it for a bubble.
    return { kind: "fade", fade: fadeSpec({ reduce: false }) };
  }
  return { kind: "spring", spring: SHEET_SPRING };
}

export function sheetSettle({ reduce }: { readonly reduce: boolean }): "spring" | "snap" {
  return reduce ? "snap" : "spring";
}

export type SheetCloseReason = "patient" | "privacy" | "red";

export function sheetClose(
  reason: SheetCloseReason,
  { reduce }: { readonly reduce: boolean },
): "spring" | "instant" {
  if (reason !== "patient" || reduce) {
    return "instant";
  }
  return "spring";
}
