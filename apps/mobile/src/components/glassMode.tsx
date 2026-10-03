/**
 * The material every glass surface renders (docs/design/apple-native/spec.md
 * §1.1): the one place that asks expo-glass-effect whether system Liquid Glass
 * exists, combined with the OS Reduce Transparency answer and capture
 * protection by the pure policy in lib/a11y/glass.ts.
 *
 * The availability check runs once, at module load. The answer is a property
 * of the build and the OS (SDK, compiler, Info.plist), and neither changes
 * while the app runs. Reduce Transparency can change, so it comes from the
 * shared store and re-renders every surface when the patient flips it.
 *
 * Capture protection (INT-477; ADR-039 amendment, owner, 4 Oct 2026: "solid")
 * arrives two ways (lib/auth/captureProtection):
 * - the route a surface sits under, through `CaptureProtectedScope`, which the
 *   navigators wrap around every screen and the tab rail around its pill, so
 *   a protected screen is solid from its first frame;
 * - the window, from the screen guard's store, so the whole window stays solid
 *   while any screen holds protection, including one kept mounted behind
 *   another.
 */
import { isLiquidGlassAvailable } from "expo-glass-effect";
import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";

import { glassMode, type GlassMode } from "@/lib/a11y/glass";
import { useReducedTransparency } from "@/lib/a11y/prefs";
import { captureProtection, captureScope } from "@/lib/auth/captureProtection";

let liquidGlass = false;
try {
  liquidGlass = isLiquidGlassAvailable();
} catch {
  liquidGlass = false;
}

/** Whether the route this surface sits under is capture-protected. */
const CaptureScope = createContext(false);

/**
 * Scope a subtree by the route it renders, named as the navigators name it
 * (`(tabs)/visits/[visitId]/review`). A scope adds its route's protection to
 * its parent's and never removes it.
 */
export function CaptureProtectedScope({ route, children }: { route: string; children: ReactNode }) {
  const outer = useContext(CaptureScope);
  return (
    <CaptureScope.Provider value={captureScope(outer, route)}>{children}</CaptureScope.Provider>
  );
}

export function useGlassMode(): GlassMode {
  const routeProtected = useContext(CaptureScope);
  const windowProtected = useSyncExternalStore(
    captureProtection.subscribe,
    captureProtection.getSnapshot,
    captureProtection.getSnapshot,
  );
  return glassMode({
    liquidGlass,
    reduceTransparency: useReducedTransparency(),
    captureProtected: routeProtected || windowProtected,
  });
}
