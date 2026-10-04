/**
 * The micro-interactions' motion (INT-492, GitHub #839), as numbers.
 *
 * Pure, so lib/motion/micro.test.ts pins every rule; the native halves
 * (native/numberRoll.ts, native/pressScale.ts) turn an answer from here into
 * Reanimated and write no number of their own.
 *
 * - **The count swaps with the step.** On a step change the question's
 *   120 ms fade is the one animated element (ADR-033 §2, C9), so the capsule
 *   and its number change in the same commit, instantly. The rolling number
 *   exists only behind its own flag, which is approval needed: ADR-033 §1
 *   forbids count-up numerals and tickers, and ADR-037 lists them as not
 *   proposed. Granted, it is the app's one 120 ms fade with ADR-038 A1's
 *   8 pt rise on a timing (no spring, so the spring allow-list does not grow
 *   for it). It is static under Reduce Motion and while a RED is presented.
 * - **The press gives under the finger.** ADR-037 P1, ratified: 0.97 on the
 *   filled action, on the app's one critically damped spring (ADR-038 A1
 *   reuses it), only at a call site that opts in. Absent under Reduce Motion
 *   and on RED; the instant opacity step stays as the second cue.
 * - **The loading wait.** Today a platform spinner. Under Reduce Motion the
 *   redesign shows a still glyph, so nothing on the screen moves (ADR-033 §1:
 *   reduce motion makes every loop static).
 */
import { BUBBLE_RISE, BUBBLE_SPRING } from "./bubbles";
import { fadeSpec, type FadeSpec } from "./fade";

/** The roll's rise, in points: ADR-038 A1's, so the app has one distance. */
export const ROLL_RISE = BUBBLE_RISE;

export type NumberRoll =
  | { readonly kind: "none" }
  | { readonly kind: "roll"; readonly rise: typeof ROLL_RISE; readonly fade: FadeSpec };

export function numberRoll({
  flags,
  reduce,
  redPresented,
}: {
  readonly flags: { readonly progressMicro: boolean; readonly progressNumberRoll: boolean };
  readonly reduce: boolean;
  /** An ALERT, CALM or SILENT RED is on screen. */
  readonly redPresented: boolean;
}): NumberRoll {
  if (!flags.progressMicro || !flags.progressNumberRoll || reduce || redPresented) {
    return { kind: "none" };
  }
  return { kind: "roll", rise: ROLL_RISE, fade: fadeSpec({ reduce: false }) };
}

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
  /** The call site opted in (the step's action, the send) under the flag. */
  readonly enabled: boolean;
  readonly reduce: boolean;
  readonly redPresented: boolean;
}): PressScale {
  if (!enabled || reduce || redPresented) {
    return { kind: "none" };
  }
  return { kind: "scale", to: PRESS_SCALE, spring: PRESS_SPRING };
}

export type LoadingIndicator = "spinner" | "still";

export function loadingIndicator({
  micro,
  reduce,
}: {
  /** The redesign flag (`progressMicro`). */
  readonly micro: boolean;
  readonly reduce: boolean;
}): LoadingIndicator {
  return micro && reduce ? "still" : "spinner";
}
