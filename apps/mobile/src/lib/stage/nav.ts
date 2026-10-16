/**
 * The sign-in screens' native bar on the stage (ADR-039 S7, INT-464).
 *
 * Phone and OTP entry are gates, and nothing on a gate scrolls under a
 * material (INT-451), so the bar stays solid. It is painted in the wash's
 * first stop, which is where the stage backdrop starts below it, so the two
 * meet without a seam; under Reduce Transparency the wash is flat and that
 * stop is the base. The bar shows only the back chevron, in the stage ink:
 * the step title is a heading in the content, and `title` stays set for the
 * system's back menu.
 */
import type { StagePalette } from "./palette";

export interface SolidStageBar {
  readonly headerTransparent: false;
  readonly headerStyle: { readonly backgroundColor: string };
  readonly headerShadowVisible: false;
  readonly headerTintColor: string;
  readonly headerTitle: string;
}

export function withSolidStageBar<T extends object>(
  options: T,
  palette: StagePalette,
): T & SolidStageBar {
  return {
    ...options,
    headerTransparent: false,
    headerStyle: { backgroundColor: palette.wash[0] },
    headerShadowVisible: false,
    headerTintColor: palette.ink,
    headerTitle: "",
  };
}
