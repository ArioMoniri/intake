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
 *
 * The section sheet, the app's one RN `Modal` (INT-338, MOTION-9;
 * motion-verification.md §1.1 C12, §1.2 P15, §2.1 #3 and #16):
 *
 * - the platform never animates it. React Native's `"fade"` is a UIKit
 *   cross-dissolve on iOS, whose length UIKit owns and no prop sets
 *   (`RCTModalHostViewComponentView.mm`), and a window animation of
 *   `config_shortAnimTime` on Android (`catalyst_fade_in.xml`, 200 ms in
 *   AOSP). Neither fits the 120 ms budget, so `animationType` is always
 *   `"none"`, which presents and dismisses unanimated on both;
 * - the app owns the entrance: the sheet's content, backdrop and panel
 *   together, fades in with the one fade (`enterFor`), and not at all under
 *   reduce-motion;
 * - every exit is instant, whatever closes the sheet: the patient, a privacy
 *   hide or a presented RED. A fading privacy surface stays readable while it
 *   fades, and a fading exit is a second animated element (§2.1 #3). Because
 *   the type is `"none"` from the moment the sheet opens, the commit before
 *   `visible` turns false already carries it (C12), with nothing to switch.
 *   Whether a RED closes the sheet at all is ./sheetOnRed's decision.
 */
import { modalAnimation, motionMs, screenAnimation, type ScreenAnimation } from "../a11y/motion";
import { motion } from "../theme";
import { enterFor, type FadeSpec } from "./fade";

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

/** What an owned RN `Modal` takes. Each field is a literal type where it pins a rule. */
export interface ModalTransition {
  /** RN's `animationType`: the platform presents and dismisses it unanimated. */
  readonly animationType: "none";
  /** The content's entrance: the one fade, or none under reduce-motion. */
  readonly enter: FadeSpec | undefined;
  /** No exit animation: the content is gone in the commit that closes it. */
  readonly exitMs: typeof motion.duration.instant;
}

/** Every reason a sheet closes. */
export const SHEET_CLOSE_REASONS = ["user", "privacy", "red"] as const;

/**
 * - `user`: the close control, a tap on the backdrop, or Android back;
 * - `privacy`: the "gizle" control or the third-party auto-hide (02 §5.2a rule 6);
 * - `red`: a RED the patient is shown (./sheetOnRed).
 */
export type SheetCloseReason = (typeof SHEET_CLOSE_REASONS)[number];

/** How a sheet leaves the screen. */
export interface SheetClose {
  readonly reason: SheetCloseReason;
  /** The type the platform dismisses with, already in place before the close. */
  readonly animationType: ModalTransition["animationType"];
  readonly exitMs: ModalTransition["exitMs"];
}

/** The platform's answer for a modal the app owns: the still one, at every setting. */
const OWNED = true;

/** An owned RN `Modal`'s transition: `animationType` and the content's entrance. */
export function modalTransition({ reduce }: TransitionContext): ModalTransition {
  return {
    animationType: modalAnimation(OWNED),
    enter: enterFor({ reduce }),
    exitMs: motion.duration.instant,
  };
}

/**
 * A sheet's close, for any reason, at any reduce-motion setting: the
 * transition it opened with, which never animates out. The reason changes
 * nothing about the motion; it is typed so a new kind of close is a decision.
 */
export function sheetClose(reason: SheetCloseReason, context: TransitionContext): SheetClose {
  const { animationType, exitMs } = modalTransition(context);
  return { reason, animationType, exitMs };
}
