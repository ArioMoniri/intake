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
