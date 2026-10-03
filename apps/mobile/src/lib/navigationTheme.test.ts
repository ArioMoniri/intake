/**
 * The navigators' theme follows the app's scheme (INT-451 follow-up; the dark
 * back chevron INT-433 reported).
 *
 * The native stack hands its theme's `dark` flag to every native header as
 * `experimental_userInterfaceStyle`. With no theme provided, React
 * Navigation's default is light, so on a dark screen each navigation bar was
 * forced to the light style. On iOS 26 the back button's chevron takes that
 * style's label colour and ignores `headerTintColor`: black on the black page,
 * present and tappable, but invisible. Captured on INT451-16e (iOS 26.1),
 * where a red `headerTintColor` did not change the chevron at all.
 */
import { describe, expect, it } from "vitest";

import { navigationThemeFor } from "./navigationTheme";
import { colorsFor, type ColorScheme, type Contrast } from "./theme";

const MODES: readonly (readonly [ColorScheme, Contrast])[] = [
  ["light", "standard"],
  ["dark", "standard"],
  ["light", "high"],
  ["dark", "high"],
];

describe("navigationThemeFor", () => {
  it.each(MODES)("%s / %s: the native bars take the app's style", (scheme, contrast) => {
    const theme = navigationThemeFor(scheme, colorsFor(scheme, contrast));
    expect(theme.dark).toBe(scheme === "dark");
  });

  it.each(MODES)("%s / %s: the navigators paint the app's own tokens", (scheme, contrast) => {
    const colors = colorsFor(scheme, contrast);
    expect(navigationThemeFor(scheme, colors).colors).toEqual({
      primary: colors.primary,
      background: colors.background,
      card: colors.background,
      text: colors.ink,
      border: colors.separator,
      notification: colors.primary,
    });
  });

  it("near miss: the library default is light, which is the defect on a dark screen", () => {
    const dark = navigationThemeFor("dark", colorsFor("dark", "standard"));
    expect(dark.dark).not.toBe(false);
    expect(dark.colors.text).not.toBe("#000000");
  });

  it("RED's reserved colour is never a navigator colour", () => {
    for (const [scheme, contrast] of MODES) {
      const colors = colorsFor(scheme, contrast);
      const values = Object.values(navigationThemeFor(scheme, colors).colors);
      expect(values).not.toContain(colors.emergency);
      expect(values).not.toContain(colors.emergencySoft);
    }
  });
});
