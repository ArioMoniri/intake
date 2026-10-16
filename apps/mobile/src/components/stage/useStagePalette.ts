/**
 * The stage palette for the screen being drawn (ADR-039 S6 and S7).
 *
 * It follows the app's resolved scheme, Increase Contrast, and Reduce
 * Transparency: without Liquid Glass the wash is flat and every glass surface
 * a solid stage fill.
 */
import { useGlassMode } from "@/components/glassMode";
import { useScheme } from "@/components/Themed";
import { useIncreasedContrast } from "@/lib/a11y/prefs";
import { stagePalette, type StagePalette } from "@/lib/stage/palette";

export function useStagePalette(): StagePalette {
  const mode = useGlassMode();
  const scheme = useScheme();
  const increasedContrast = useIncreasedContrast() === "high";
  return stagePalette(scheme, { reduceTransparency: mode !== "liquid", increasedContrast });
}
