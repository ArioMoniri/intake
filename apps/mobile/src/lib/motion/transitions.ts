/**
 * Navigator transition policy (INT-330, MOTION-1;
 * docs/design/motion/motion-verification.md §3 S-1, §4 MOTION-1).
 *
 * Pure — no React Native import — so the whole policy is node-testable and
 * every navigator spreads the same answer instead of writing its own.
 *
 * Why the duration is part of the policy and not left to the platform:
 * a native stack that names only `fade` runs iOS's default of 500 ms, and
 * react-native-screens defers a push or pop requested while a transition is
 * in flight until that transition completes. An unpinned stack could
 * therefore hold a RED behind it past 02 §8.1's 300 ms preemption budget.
 * Pinning every stack to the fade token bounds that wait at 120 ms. Android
 * ignores the duration and fades for its own fixed 150 ms; that is a
 * platform fact, not a token.
 *
 * The classes:
 * - `hierarchy`: ordinary navigation — a fade of `motion.duration.fade`;
 * - `auth`: onboarding and sign-in — the same fade, no shake, no haptic;
 * - `intake`: the same fade, and the back-swipe is off, because a patient
 *   mid-answer must not lose the visit to a stray edge gesture. The header
 *   back control stays as the explicit exit;
 * - `legal`: routes that render the docs/legal payload never animate, in
 *   either direction, at any reduce-motion setting (invariant 18: hash-bound
 *   text does not move on screen, and a fade would bias consent dwell).
 *
 * Reduce-motion removes every transition that remains (INT-144, SC 2.2.2),
 * through the kept primitives `screenAnimation` and `motionMs`.
 */
import { motionMs, screenAnimation, type ScreenAnimation } from "../a11y/motion";
import { motion } from "../theme";

export const ROUTE_CLASSES = ["hierarchy", "auth", "intake", "legal"] as const;

export type RouteClass = (typeof ROUTE_CLASSES)[number];

export interface TransitionContext {
  /** The patient's reduce-motion answer (`useReducedMotion`). */
  readonly reduce: boolean;
}

/** What a native-stack screen spreads into its options. */
export interface StackTransition {
  readonly animation: ScreenAnimation;
  /** iOS only; without it a fade runs 500 ms. */
  readonly animationDuration: number;
  /** Present, and false, only where the back-swipe is locked. */
  readonly gestureEnabled?: false;
}

/** What a JS tab screen spreads into its options. */
export interface TabTransition {
  readonly animation: ScreenAnimation;
  readonly transitionSpec: {
    readonly animation: "timing";
    readonly config: { readonly duration: number };
  };
}

/**
 * Routes whose screen renders the docs/legal payload (the consent ledger's
 * `LoadedText`). transitions.test.ts discovers those routes from the source
 * and fails when one is missing here.
 */
const LEGAL_ROUTES: ReadonlySet<string> = new Set([
  "(auth)/consent",
  "(tabs)/me/consents/index",
  "(tabs)/me/consents/[purpose]",
  // INT-587: Review & send renders the share consent text at the send.
  "(tabs)/visits/[visitId]/review",
]);

const INTAKE_ROUTES: ReadonlySet<string> = new Set(["(tabs)/visits/[visitId]/intake"]);

const AUTH_GROUP = "(auth)";

/**
 * The class of a route, by its path under `src/app` without the extension,
 * exactly as expo-router names it: `(auth)/consent`,
 * `(tabs)/me/consents/[purpose]`, `(tabs)/visits/[visitId]/intake`. A
 * navigator builds that path from its own directory and `route.name`.
 */
export function routeClassOf(name: string): RouteClass {
  if (LEGAL_ROUTES.has(name)) {
    return "legal";
  }
  if (INTAKE_ROUTES.has(name)) {
    return "intake";
  }
  if (name === AUTH_GROUP || name.startsWith(`${AUTH_GROUP}/`)) {
    return "auth";
  }
  return "hierarchy";
}

/**
 * The one decision both navigator kinds share. Legal text is still at every
 * setting, so for it reduce-motion has nothing left to remove.
 */
function fadeOf(cls: RouteClass, { reduce }: TransitionContext) {
  const still = cls === "legal";
  return {
    animation: screenAnimation(still || reduce),
    ms: still ? motion.duration.instant : motionMs(reduce, motion.duration.fade),
  };
}

/** A native-stack screen's transition: spread it into `screenOptions`. */
export function transitionFor(cls: RouteClass, context: TransitionContext): StackTransition {
  const { animation, ms } = fadeOf(cls, context);
  const base = { animation, animationDuration: ms };
  return cls === "intake" ? { ...base, gestureEnabled: false } : base;
}

/** A JS tab screen's transition: spread it into the tabs' `screenOptions`. */
export function tabTransition(cls: RouteClass, context: TransitionContext): TabTransition {
  const { animation, ms } = fadeOf(cls, context);
  return { animation, transitionSpec: { animation: "timing", config: { duration: ms } } };
}
