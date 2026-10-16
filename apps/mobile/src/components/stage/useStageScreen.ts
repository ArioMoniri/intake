/**
 * The stage for one of the remaining screens (ADR-039 amendment, INT-499):
 * its palette and its chrome, from the live glass mode, the app's resolved
 * scheme, Increase Contrast and whether the screen is capture-protected.
 *
 * The policy is lib/stage/screens.ts `stageScreenChrome`: a protected screen
 * is flat and solid whatever the OS offers (INT-477), and Reduce
 * Transparency, a missing system glass and Increase Contrast draw solid
 * actions. The palette is flat exactly when the chrome is.
 */
import { useGlassMode } from "@/components/glassMode";
import { useScheme } from "@/components/Themed";
import { useIncreasedContrast } from "@/lib/a11y/prefs";
import { stagePalette, type StagePalette } from "@/lib/stage/palette";
import {
  STAGE_SCREENS,
  stageScreenChrome,
  type StageScreen,
  type StageScreenChrome,
} from "@/lib/stage/screens";

export function useStageScreen(screen: StageScreen): {
  palette: StagePalette;
  chrome: StageScreenChrome;
} {
  const mode = useGlassMode();
  const scheme = useScheme();
  const increasedContrast = useIncreasedContrast() === "high";
  const chrome = stageScreenChrome({
    mode,
    captureProtected: STAGE_SCREENS[screen].captureProtected,
    increasedContrast,
  });
  const palette = stagePalette(scheme, { reduceTransparency: chrome.flat, increasedContrast });
  return { palette, chrome };
}
