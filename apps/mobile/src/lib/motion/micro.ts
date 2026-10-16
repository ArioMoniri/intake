/**
 * The micro-interactions' motion (INT-492, GitHub #839), as numbers.
 *
 * Pure, so lib/motion/micro.test.ts pins every rule; the native half
 * (native/pressScale.ts) turns an answer from here into Reanimated and writes
 * no number of its own.
 *
 * - **The count swaps with the step.** The "Soru N / M" capsule moves
 *   nothing: on a step change the question's 120 ms fade is the one animated
 *   element (ADR-033 §2, C9). The owner declined a rolling number on
 *   16 Oct 2026, so none exists.
 * - **The press gives under the finger.** ADR-037 P1, ratified: 0.97 on the
 *   filled action, on the app's one critically damped spring (ADR-038 A1
 *   reuses it), only at a call site that opts in. Absent under Reduce Motion
 *   and on RED; the instant opacity step stays as the second cue.
 * - **The loading wait.** A platform spinner while motion is allowed, a still
 *   glyph under Reduce Motion, so nothing on the screen moves (ADR-033 §1:
 *   reduce motion makes every loop static).
 */
import { BUBBLE_SPRING } from "./bubbles";

/** ADR-037 P1: the filled action's scale while a finger is down. */
export const PRESS_SCALE = 0.97;

/** ADR-037 P1's spring, which ADR-038 A1 reuses: the app has one spring. */
export const PRESS_SPRING = BUBBLE_SPRING;

export type PressScale =
  | { readonly kind: "none" }
  | {
      readonly kind: "scale";
      readonly to: typeof PRESS_SCALE;
      readonly spring: typeof PRESS_SPRING;
    };

export function pressScale({
  enabled,
  reduce,
  redPresented,
}: {
  /** The call site opted in: the typed step's action or the send. */
  readonly enabled: boolean;
  readonly reduce: boolean;
  /** An ALERT, CALM or SILENT RED is on screen. */
  readonly redPresented: boolean;
}): PressScale {
  if (!enabled || reduce || redPresented) {
    return { kind: "none" };
  }
  return { kind: "scale", to: PRESS_SCALE, spring: PRESS_SPRING };
}

export type LoadingIndicator = "spinner" | "still";

export function loadingIndicator({ reduce }: { readonly reduce: boolean }): LoadingIndicator {
  return reduce ? "still" : "spinner";
}
