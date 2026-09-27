/**
 * Orientation (INT-360; WCAG 2.2 SC 1.3.4, Level AA).
 *
 * The app follows the device. app.json declares `"orientation": "default"`,
 * which writes all four interface orientations into iOS's
 * UISupportedInterfaceOrientations and `unspecified` into Android's activity.
 * Two things could still lock a screen behind that config's back, and the two
 * rules here answer them:
 *
 * - React Native presents a `<Modal>` on an iPhone portrait-only unless it is
 *   given `supportedOrientations` (RCTModalHostView: an empty list is
 *   UIInterfaceOrientationMaskPortrait on a phone). A sheet opened in
 *   landscape would turn the patient's screen under them. Every Modal names
 *   ALL_ORIENTATIONS; e2e/a11y.spec.ts fails on one that does not.
 * - A size read from the window is read from one axis. The width that bounds a
 *   portrait layout is the LONG side in landscape, so a figure sized from it
 *   grows past the height the patient can see. `shortSide` is the bound that
 *   holds both ways round, and in portrait it is the width, so no portrait
 *   layout moves.
 *
 * Pure, with no native import, so the node suite can hold both rules.
 */

export type Orientation =
  "portrait" | "portrait-upside-down" | "landscape-left" | "landscape-right";

/**
 * Every orientation app.json's "default" declares, in React Native Modal's own
 * terms. Frozen at run time; typed as the mutable array the Modal prop is
 * declared as, which a readonly tuple cannot be passed to.
 */
export const ALL_ORIENTATIONS = Object.freeze<Orientation[]>([
  "portrait",
  "portrait-upside-down",
  "landscape-left",
  "landscape-right",
]) as Orientation[];

export interface WindowSize {
  readonly width: number;
  readonly height: number;
}

/** The window's shorter side: what a figure may grow to in either orientation. */
export function shortSide(window: WindowSize): number {
  return Math.min(window.width, window.height);
}
