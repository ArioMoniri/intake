/**
 * The sign-in screens' native bar on the stage (ADR-039 S7, INT-464).
 *
 * The bar stays SOLID: phone and OTP are gates, and nothing on a gate scrolls
 * under a material (INT-451). It is painted in the wash's first stop, so it
 * meets the stage backdrop without a seam, and shows only the back chevron:
 * the step title is a heading in the content. The title is kept on the
 * screen for the system's back menu.
 */
import { describe, expect, it } from "vitest";

import { withSolidStageBar } from "./nav";
import { stagePalette } from "./palette";

const BASE = {
  headerShown: true,
  title: "Telefonla giriş",
  headerStyle: { backgroundColor: "#F2F2F7" },
  headerTintColor: "#000000",
  headerBackButtonDisplayMode: "minimal" as const,
};

describe("withSolidStageBar", () => {
  it("paints the bar in the wash's first stop, so it meets the backdrop without a seam", () => {
    for (const scheme of ["light", "dark"] as const) {
      const p = stagePalette(scheme, { reduceTransparency: false, increasedContrast: false });
      const options = withSolidStageBar(BASE, p);
      expect(options.headerStyle).toEqual({ backgroundColor: p.wash[0] });
      expect(options.headerShadowVisible).toBe(false);
    }
  });

  it("is never transparent: nothing on a gate scrolls under a material", () => {
    const p = stagePalette("light", { reduceTransparency: false, increasedContrast: false });
    const options = withSolidStageBar(BASE, p);
    expect(options.headerTransparent).toBe(false);
    expect("scrollEdgeEffects" in options).toBe(false);
  });

  it("shows only the back chevron, drawn in the stage ink; the title stays for the back menu", () => {
    const p = stagePalette("dark", { reduceTransparency: false, increasedContrast: false });
    const options = withSolidStageBar(BASE, p);
    expect(options.headerTitle).toBe("");
    expect(options.title).toBe(BASE.title);
    expect(options.headerTintColor).toBe(p.ink);
    expect(options.headerBackButtonDisplayMode).toBe("minimal");
  });

  it("under Reduce Transparency the wash is flat, so the bar is the base", () => {
    const p = stagePalette("light", { reduceTransparency: true, increasedContrast: false });
    expect(withSolidStageBar(BASE, p).headerStyle).toEqual({ backgroundColor: p.base });
  });
});
