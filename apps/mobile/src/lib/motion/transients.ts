/**
 * Typed-lane motion (INT-339, MOTION-10;
 * docs/design/motion/motion-verification.md §4 MOTION-10, and C15 and C16 of
 * intake-voice-motion-spec.md).
 *
 * Pure — no React Native or Reanimated import — so the plans are
 * node-testable. The typed intake screen hands each plan's `enter` to the
 * Reanimated adapter (native/reanimated.ts) and writes no number of its own.
 *
 * Both surfaces are enter-only, and the shape is the one fade (fade.ts):
 * - `typedFallback`: the typed steps' container, when it replaces the voice
 *   lane (failure, hand-over, or "Yazarak devam edin"). The dialogue unmounts
 *   at 0 ms and the steps fade in over `motion.duration.fade`, so the switch
 *   is fully visible 120 ms after its commit, inside INT-135's 2 s at every
 *   setting;
 * - `typedStep`: one question's body. It is keyed by the question, so a step
 *   change removes the old body in the commit that mounts the next one, and
 *   only the next one fades in. No frame holds two questions. The progress
 *   row and the glass-bar CTA sit outside it and swap instantly (C9, C16).
 *
 * There is no exit: `exitMs` is the literal 0 (motion-verification.md §2.1
 * #3). A fading exit is a second animated element whenever something replaces
 * it, and it is the only thing that could keep a removed question on screen.
 * Under reduce-motion `enter` is undefined and the content is simply there.
 */
import { motion } from "../theme";
import { enterFor, type FadeContext, type FadeSpec } from "./fade";

/** A mount that may fade in and never fades out. */
export interface EnterOnly {
  /** A layout animation's entrance, or none: under reduce-motion there is nothing to register. */
  readonly enter: FadeSpec | undefined;
  /** The leaving element is gone in the commit that removes it. */
  readonly exitMs: typeof motion.duration.instant;
}

/** One typed question's body. */
export interface TypedStep extends EnterOnly {
  /** The React key: a new question is a new element, the same question the same one. */
  readonly key: string;
}

function enterOnly(context: FadeContext): EnterOnly {
  return { enter: enterFor(context), exitMs: motion.duration.instant };
}

/** The typed steps' container, entering in place of the voice lane (C15). */
export function typedFallback(context: FadeContext): EnterOnly {
  return enterOnly(context);
}

/** A question's body in the typed steps (C16). */
export function typedStep(questionId: string, context: FadeContext): TypedStep {
  return { key: questionId, ...enterOnly(context) };
}
