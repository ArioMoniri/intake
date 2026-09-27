/**
 * Reduced-motion policy (INT-144), as pure functions so the rules are
 * testable without a device.
 *
 * The app's motion budget (02 §5.2a) is already small — fades only, one
 * animated element at a time, 120 ms. Two things in it still need a
 * reduce-motion answer:
 *
 * - The dialogue's listening pulse is an INFINITE opacity loop that runs for
 *   the whole open-mic turn. WCAG 2.2 SC 2.2.2 (Level A) covers moving or
 *   blinking content that starts automatically and lasts more than five
 *   seconds: it must be pausable, stoppable or hideable. The pulse carries no
 *   information the adjacent text does not already carry ("Sizi dinliyorum"),
 *   so under reduce-motion it simply stops being a loop and becomes a static
 *   dot — hidden motion, which is the cheapest of the three permitted
 *   answers and the only one that does not add a control to a screen the
 *   patient is speaking into.
 * - Screen transitions and the transcript's auto-scroll are vestibular
 *   triggers for some users; under reduce-motion they become instantaneous.
 *
 * Nothing here decides *whether* the user asked for reduced motion — that is
 * the OS's answer, read by `useReducedMotion` in ./prefs. These functions
 * only say what the app does with the answer.
 */

/** Navigator transition when reduce-motion is on vs. off (02 §5.2a: fades). */
export type ScreenAnimation = "fade" | "none";

export function screenAnimation(reduceMotion: boolean): ScreenAnimation {
  return reduceMotion ? "none" : "fade";
}

/**
 * A duration in ms, collapsed to 0 under reduce-motion. 0 rather than "very
 * short": a 20 ms fade is still a fade, and the point is to remove the
 * movement, not to hurry it.
 */
export function motionMs(reduceMotion: boolean, ms: number): number {
  return reduceMotion ? 0 : Math.max(0, ms);
}

/**
 * Whether a decorative looping animation may run at all.
 *
 * `false` means the element renders in its resting state — it does NOT mean
 * the element disappears, because in every case the loop is decoration over
 * text that stays.
 */
export function loopingDecorationEnabled(reduceMotion: boolean): boolean {
  return !reduceMotion;
}

/** Whether a programmatic scroll should animate. */
export function scrollAnimated(reduceMotion: boolean): boolean {
  return !reduceMotion;
}

/**
 * Modal presentation: RN's `animationType` values. A modal the app owns
 * (INT-338, lib/motion/transitions.ts `modalTransition`) always asks for the
 * still answer, and the overload lets it keep the literal type.
 */
export function modalAnimation(reduceMotion: true): "none";
export function modalAnimation(reduceMotion: boolean): "fade" | "none";
export function modalAnimation(reduceMotion: boolean): "fade" | "none" {
  return reduceMotion ? "none" : "fade";
}
