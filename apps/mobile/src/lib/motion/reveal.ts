/**
 * Content reveal (INT-342, MOTION-13;
 * docs/design/motion/motion-verification.md §1.2 P6 and P7 as revised, §2.2
 * `reveal.skeletonDelayMs`, §4 MOTION-13).
 *
 * Pure — no React Native or Reanimated import — so the plan is node-testable.
 * A screen hands `skeleton` to <Skeleton> and `enter` to the Reanimated
 * adapter (native/reanimated.ts), and writes no number of its own.
 *
 * A screen that waits for its data gives it one slot, whose two branches are
 * one conditional:
 * - while the data is on its way, a static skeleton. It is on the tree from
 *   the commit that starts the wait, hidden, and steps in (opacity 0 → 1, no
 *   fade) once `motion.reveal.skeletonDelayMs` has passed, so a load that
 *   lands inside the delay never shows it. It never changes again: no loop,
 *   no shimmer, no translate;
 * - the content, from the commit that brings it. That commit also removes the
 *   skeleton: there is no exit, and nothing waits for an animation to end
 *   (intake §3.4: "never chain app logic to an animation callback").
 *
 * Content that was already there in the commit that mounted the slot never
 * animates. Content that arrives fades in once, with the one fade (fade.ts):
 * opacity, `motion.duration.fade`, delay 0. Nothing is sequenced or
 * staggered: the rejected two-slot sequence of P6 is a stagger, and Records
 * holds lab values.
 *
 * Reduce-motion keeps the delay and drops the fade. The delay is a wait, not
 * a movement, and dropping it would flash a skeleton for every fast load,
 * which is more change on screen, not less.
 */
import { motion } from "../theme";
import { enterFor, type FadeContext, type FadeSpec } from "./fade";

export interface RevealContext extends FadeContext {
  /** The content was on hand in the commit that mounted the slot. */
  readonly availableAtMount: boolean;
}

/** What stands in for the content while it is on its way. */
export interface SkeletonPlan {
  /** Hidden this long after it mounts. A wait, not motion: the same under reduce-motion. */
  readonly delayMs: typeof motion.reveal.skeletonDelayMs;
  /** Then shown in one step, with no fade. */
  readonly stepMs: typeof motion.duration.instant;
  /** Gone in the commit that brings the content: no exit, and so no callback. */
  readonly exitMs: typeof motion.duration.instant;
  /** Literal types: a skeleton that repeats, or sweeps a highlight, does not compile. */
  readonly loop: false;
  readonly shimmer: false;
}

/** One slot: the skeleton while the content is on its way, the content once it is there. */
export interface RevealPlan {
  readonly skeleton: SkeletonPlan;
  /** The content's entrance: `undefined` when it was already there, or under reduce-motion. */
  readonly enter: FadeSpec | undefined;
}

const SKELETON: SkeletonPlan = {
  delayMs: motion.reveal.skeletonDelayMs,
  stepMs: motion.duration.instant,
  exitMs: motion.duration.instant,
  loop: false,
  shimmer: false,
};

/** The plan for one slot, taken once, when the slot mounts. */
export function revealPlan({ availableAtMount, reduce }: RevealContext): RevealPlan {
  return {
    skeleton: SKELETON,
    enter: availableAtMount ? undefined : enterFor({ reduce }),
  };
}
