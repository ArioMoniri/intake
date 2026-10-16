/**
 * ADR-038 A1: how a new message bubble enters (INT-462).
 *
 * Pure, so lib/motion/bubbles.test.ts pins every number; native/
 * bubbleEntering.ts turns the answer into Reanimated's entrance and writes no
 * number of its own.
 *
 * The arbiter (./transients.ts, INT-337) still decides whether a bubble moves:
 * an agent bubble is the `content` class, and only the element it grants
 * enters with motion. A granted bubble rises 8 pt on ADR-037 P1's critically
 * damped spring (ζ = 1, overshoot clamped, so it never bounces) under the one
 * 120 ms opacity fade. There is no scale: scaled text blurs while it moves.
 *
 * - Reduce Motion: no rise, and the 120 ms fade stays, Apple's dissolve
 *   substitution for a slide. This is ADR-038's one deliberate exception to
 *   ADR-033's "reduce motion collapses every duration".
 * - RED: while a RED is presented no bubble moves, at any setting.
 * - The patient's own bubbles keep INT-337's instant render: they answer the
 *   patient's own action, and the next question arriving in the same commit
 *   keeps the slot.
 */
import { fadeSpec, type FadeSpec } from "./fade";
import type { DialogueMotion } from "./transients";

/** The rise, in points: the bubble starts this far below its place. */
export const BUBBLE_RISE = 8;

/** ADR-037 P1's spring: ζ = 77.5 / (2 · √1500) ≈ 1.0005, critically damped. */
export const BUBBLE_SPRING = {
  stiffness: 1500,
  damping: 77.5,
  mass: 1,
  overshootClamping: true,
} as const;

export type BubbleEntrance =
  | { readonly kind: "none" }
  | { readonly kind: "fade"; readonly fade: FadeSpec }
  | {
      readonly kind: "spring";
      readonly rise: typeof BUBBLE_RISE;
      readonly spring: typeof BUBBLE_SPRING;
      readonly fade: FadeSpec;
    };

export function bubbleEntrance({
  granted,
  redPresented,
  reduce,
}: {
  /** The arbiter granted this bubble its entrance (`bubbleGranted`). */
  readonly granted: boolean;
  /** An ALERT, CALM or SILENT RED is on screen. */
  readonly redPresented: boolean;
  readonly reduce: boolean;
}): BubbleEntrance {
  if (redPresented || !granted) {
    return { kind: "none" };
  }
  // The fade is always the full one: under Reduce Motion it is what remains.
  const fade = fadeSpec({ reduce: false });
  if (reduce) {
    return { kind: "fade", fade };
  }
  return { kind: "spring", rise: BUBBLE_RISE, spring: BUBBLE_SPRING, fade };
}

/**
 * Whether the arbiter granted `id` its entrance in this commit.
 *
 * Without Reduce Motion that is the arbiter's running element. With it the
 * arbiter frees the slot in the same commit (nothing of its own moves), so
 * the grant is read from how the element arrived; an `entering` animation
 * only plays on mount, so a later render cannot replay it.
 */
export function bubbleGranted(m: DialogueMotion, id: string, reduce: boolean): boolean {
  if (reduce) {
    return m.entered[id] === "animate";
  }
  return m.arbiter.running?.id === id;
}
