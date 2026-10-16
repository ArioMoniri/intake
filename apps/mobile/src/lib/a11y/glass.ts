/**
 * Which material a glass surface renders (docs/design/apple-native/spec.md
 * §0 rule 2, §1.1). Pure, so the whole policy is node-testable. The inputs
 * are gathered by components/glassMode.tsx.
 *
 * - `liquid`: the system's Liquid Glass through expo-glass-effect (iOS 26 and
 *   later). The system adapts it to the user's glass look setting.
 * - `blur`: expo-blur under the `glassFallback` wash and a hairline
 *   (Android, iOS below 26, web).
 * - `solid`: the `surface` token with a hairline, from the palette whose
 *   contrast pairs theme.test.ts pins.
 *
 * Reduce Transparency outranks availability. `isLiquidGlassAvailable()` stays
 * true when the user has turned transparency down, so a policy that asked only
 * "is glass available?" would keep a see-through rail under a patient who
 * asked for none. An unknown answer (the OS has not replied, or refused) is
 * solid: the same fail-closed stance as reduce motion (INT-331).
 */
export type GlassMode = "liquid" | "blur" | "solid";

export interface GlassInputs {
  /** The system Liquid Glass components exist in this build and OS. */
  readonly liquidGlass: boolean;
  /** The OS Reduce Transparency setting; `null` until the OS has answered. */
  readonly reduceTransparency: boolean | null;
}

export function glassMode({ liquidGlass, reduceTransparency }: GlassInputs): GlassMode {
  if (reduceTransparency !== false) {
    return "solid";
  }
  return liquidGlass ? "liquid" : "blur";
}

/**
 * What a navigation bar over a scrolling screen draws behind its items.
 *
 * - `systemMaterial` (iOS 26): UIKit draws the bar's own chrome material
 *   (`headerBlurEffect: "systemChromeMaterial"`), which frosts the content
 *   that passes under the title and the back button and follows the bar's
 *   light or dark style. The app paints nothing.
 * - `blur`: the app's blur under the `glassFallback` wash (iOS below 26,
 *   Android, where the native-stack blur does not exist).
 * - `solid`: the page ground, for Reduce Transparency or an unanswered OS.
 *
 * Never Liquid Glass across the whole bar and never a clear bar. Both were
 * tried on the INT451-16e simulator (iOS 26.1, Expo Go): a full-bar GlassView
 * let scrolled content draw straight through the bar title and the back
 * chevron, and a clear bar asking UIKit for its scroll-edge effect did the
 * same, because the effect did not attach to the screen's scroller. The
 * system chrome material separated them in both schemes.
 */
export interface NavBarChrome {
  readonly background: "systemMaterial" | "blur" | "solid";
}

export function navBarChrome(mode: GlassMode): NavBarChrome {
  return { background: mode === "liquid" ? "systemMaterial" : mode };
}
