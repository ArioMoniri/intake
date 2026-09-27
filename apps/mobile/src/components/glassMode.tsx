/**
 * The material every glass surface renders (docs/design/apple-native/spec.md
 * §1.1): the one place that asks expo-glass-effect whether system Liquid Glass
 * exists, combined with the OS Reduce Transparency answer by the pure policy in
 * lib/a11y/glass.ts.
 *
 * The availability check runs once, at module load. The answer is a property
 * of the build and the OS (SDK, compiler, Info.plist), and neither changes
 * while the app runs. Reduce Transparency can change, so it comes from the
 * shared store and re-renders every surface when the patient flips it.
 */
import { isLiquidGlassAvailable } from "expo-glass-effect";

import { glassMode, type GlassMode } from "@/lib/a11y/glass";
import { useReducedTransparency } from "@/lib/a11y/prefs";

let liquidGlass = false;
try {
  liquidGlass = isLiquidGlassAvailable();
} catch {
  liquidGlass = false;
}

export function useGlassMode(): GlassMode {
  return glassMode({ liquidGlass, reduceTransparency: useReducedTransparency() });
}
