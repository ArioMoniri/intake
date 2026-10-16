/**
 * The navigators' theme, built from the app's own scheme and palette.
 *
 * Pure, so the node suite can hold it; app/_layout.tsx merges it over React
 * Navigation's default fonts and hands it to `ThemeProvider`.
 *
 * Why it exists: the native stack passes its theme's `dark` flag to every
 * native header as the bar's user-interface style. Without a provider the
 * flag is React Navigation's default, `false`, so on a dark screen each bar
 * was forced to the light style. On iOS 26 the back button's chevron follows
 * that style's label colour, not `headerTintColor`, and it drew black on the
 * black page (INT-433's dark-chevron report, confirmed on INT451-16e).
 *
 * `notification` (React Navigation's badge colour) is the accent: the RED
 * colour is reserved for the RED route (invariant 21) and never reaches the
 * navigators.
 */
import type { ColorScheme, ThemeColors } from "./theme";

export interface NavigationThemeColors {
  readonly primary: string;
  readonly background: string;
  readonly card: string;
  readonly text: string;
  readonly border: string;
  readonly notification: string;
}

export interface NavigationThemeSpec {
  readonly dark: boolean;
  readonly colors: NavigationThemeColors;
}

export function navigationThemeFor(scheme: ColorScheme, colors: ThemeColors): NavigationThemeSpec {
  return {
    dark: scheme === "dark",
    colors: {
      primary: colors.primary,
      background: colors.background,
      card: colors.background,
      text: colors.ink,
      border: colors.separator,
      notification: colors.primary,
    },
  };
}
