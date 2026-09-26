/**
 * The fade policy (INT-335, MOTION-6;
 * docs/design/motion/motion-verification.md §2.2, §2.3, §4 MOTION-6).
 *
 * Pure — no React Native or Reanimated import — so every fade the app can
 * author is node-testable, and a Reanimated consumer spreads an answer from
 * here instead of writing its own numbers.
 *
 * One shape, 02 §5.2a: opacity only, no delay, `motion.easing.out`, and
 * `motion.duration.fade` at most. Under reduce-motion it collapses to zero,
 * not to a shorter movement (INT-144). There is no exit fade: exits are
 * instant, because a fading exit is a second animated element whenever
 * something replaces it, and a fading privacy surface stays readable while
 * it fades (motion-verification.md §2.1 #3).
 *
 * Three surfaces, three helpers:
 * - `fadeSpec`: the numbers themselves;
 * - `enterFor`: what a mount's layout animation takes, or nothing at all
 *   under reduce-motion, so the element simply exists on the next frame;
 * - `cssFade`: the Reanimated CSS transition props for an opacity change on
 *   a view that is already mounted. It is the only writer of a CSS
 *   transition in src (e2e/motion.spec.ts).
 */
import { motionMs } from "../a11y/motion";
import { motion, type Bezier } from "../theme";

export interface FadeContext {
  /** The patient's reduce-motion answer (`useReducedMotion`). */
  readonly reduce: boolean;
}

export interface FadeSpec {
  readonly property: "opacity";
  readonly durationMs: number;
  /** A literal type: no fade is ever delayed. */
  readonly delayMs: 0;
  readonly easing: Bezier;
}

type Milliseconds = `${number}ms`;

/** Reanimated CSS transition props, spread into a style. */
export interface CssFade {
  readonly transitionProperty: "opacity";
  readonly transitionDuration: Milliseconds;
  readonly transitionDelay: "0ms";
  /**
   * The same fade as the shorthand. It carries the curve because Reanimated's
   * native side parses a `cubic-bezier(…)` only from the shorthand (a
   * `transitionTimingFunction` string must be a keyword there), and a pure
   * module cannot build its easing object. The longhands say the same.
   */
  readonly transition: string;
}

/** `cubic-bezier(x1, y1, x2, y2)`: a curve token as CSS writes it. */
export function cubicBezierCss(curve: Bezier): string {
  return `cubic-bezier(${curve.join(", ")})`;
}

/** Every app-authored fade, in numbers. */
export function fadeSpec({ reduce }: FadeContext): FadeSpec {
  return {
    property: "opacity",
    durationMs: motionMs(reduce, motion.duration.fade),
    delayMs: 0,
    easing: motion.easing.out,
  };
}

/**
 * A mount's entrance. `undefined` means no layout animation is registered:
 * under reduce-motion the element is simply there.
 */
export function enterFor(context: FadeContext): FadeSpec | undefined {
  const spec = fadeSpec(context);
  return spec.durationMs > 0 ? spec : undefined;
}

/** An opacity change on a mounted view, as a Reanimated CSS transition. */
export function cssFade(context: FadeContext): CssFade {
  const spec = fadeSpec(context);
  const duration: Milliseconds = `${spec.durationMs}ms`;
  const delay = "0ms";
  return {
    transitionProperty: spec.property,
    transitionDuration: duration,
    transitionDelay: delay,
    transition: `${spec.property} ${duration} ${cubicBezierCss(spec.easing)} ${delay}`,
  };
}
