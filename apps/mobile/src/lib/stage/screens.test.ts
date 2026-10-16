/**
 * INT-499 (GitHub #849): the still stage on the remaining screens, the visits
 * list, documents, the share centre and settings (ADR-039 amendment;
 * docs/design/liquid-glass-research.md).
 *
 * The pure half: which screens hold capture protection, when a screen may
 * mount Liquid Glass at all, the surface its content sits on, the share
 * centre's solid bar, and AA for the system text colours the shared rows
 * draw on the stage grounds. e2e/stageScreens.spec.ts holds the wiring.
 */
import { describe, expect, it } from "vitest";

import type { GlassMode } from "../a11y/glass";
import { colorsFor, type Contrast } from "../theme";

import { stagePalette } from "./palette";
import {
  STAGE_SCREENS,
  stageScreenChrome,
  stageSurface,
  withProtectedStageBar,
  type StageScreen,
} from "./screens";
import { STAGE_RADIUS } from "./shape";

const MODES: readonly GlassMode[] = ["liquid", "blur", "solid"];
const SCREENS = Object.keys(STAGE_SCREENS) as StageScreen[];

describe("the four screens, and which of them hold capture protection", () => {
  it("names exactly the visits list, documents, the share centre and settings", () => {
    expect(SCREENS.sort()).toEqual(["records", "settings", "shares", "visits"]);
    expect(STAGE_SCREENS.visits.route).toBe("(tabs)/visits/index");
    expect(STAGE_SCREENS.records.route).toBe("(tabs)/records");
    expect(STAGE_SCREENS.shares.route).toBe("(tabs)/visits/[visitId]/shares");
    expect(STAGE_SCREENS.settings.route).toBe("(tabs)/me/index");
  });

  it("documents and the share centre are capture-protected (INT-131, INT-477); the other two are not", () => {
    expect(STAGE_SCREENS.records.captureProtected).toBe(true);
    expect(STAGE_SCREENS.shares.captureProtected).toBe(true);
    expect(STAGE_SCREENS.visits.captureProtected).toBe(false);
    expect(STAGE_SCREENS.settings.captureProtected).toBe(false);
  });
});

describe("stageScreenChrome: glass only on an unprotected screen with system glass", () => {
  it("an unprotected screen with Liquid Glass draws the wash and glass actions", () => {
    expect(
      stageScreenChrome({ mode: "liquid", captureProtected: false, increasedContrast: false }),
    ).toEqual({ glass: true, backdrop: true, flat: false });
  });

  it("a capture-protected screen never mounts glass or the wash, in any mode or contrast", () => {
    for (const mode of MODES) {
      for (const increasedContrast of [false, true]) {
        expect(stageScreenChrome({ mode, captureProtected: true, increasedContrast })).toEqual({
          glass: false,
          backdrop: false,
          flat: true,
        });
      }
    }
  });

  it("near miss: the same inputs without protection give glass", () => {
    const inputs = { mode: "liquid", increasedContrast: false } as const;
    expect(stageScreenChrome({ ...inputs, captureProtected: true }).glass).toBe(false);
    expect(stageScreenChrome({ ...inputs, captureProtected: false }).glass).toBe(true);
  });

  it("Reduce Transparency (or an OS with no answer) is solid and flat", () => {
    for (const captureProtected of [false, true]) {
      expect(
        stageScreenChrome({ mode: "solid", captureProtected, increasedContrast: false }),
      ).toEqual({ glass: false, backdrop: false, flat: true });
    }
  });

  it("without system Liquid Glass the actions are solid stage fills, never a blur", () => {
    expect(
      stageScreenChrome({ mode: "blur", captureProtected: false, increasedContrast: false }),
    ).toEqual({ glass: false, backdrop: false, flat: true });
  });

  it("Increase Contrast draws solid actions with a boundary; the wash stays, held to AA", () => {
    expect(
      stageScreenChrome({ mode: "liquid", captureProtected: false, increasedContrast: true }),
    ).toEqual({ glass: false, backdrop: true, flat: false });
  });

  it("glass implies the wash, and the wash implies an unprotected screen", () => {
    for (const mode of MODES) {
      for (const captureProtected of [false, true]) {
        for (const increasedContrast of [false, true]) {
          const chrome = stageScreenChrome({ mode, captureProtected, increasedContrast });
          if (chrome.glass) {
            expect(chrome.backdrop).toBe(true);
          }
          if (chrome.backdrop) {
            expect(captureProtected).toBe(false);
            expect(chrome.flat).toBe(false);
          }
        }
      }
    }
  });
});

describe("stageSurface: content sits on the solid stage card", () => {
  it("is the stage card at the stage corner (ADR-039 S5: 22 pt)", () => {
    for (const scheme of ["light", "dark"] as const) {
      const p = stagePalette(scheme, { reduceTransparency: false, increasedContrast: false });
      expect(stageSurface(p)).toEqual({ card: p.card, corner: STAGE_RADIUS.card, border: null });
      expect(stageSurface(p).corner).toBe(22);
    }
  });

  it("Increase Contrast gives every card its boundary (ADR-039 S6)", () => {
    const p = stagePalette("light", { reduceTransparency: false, increasedContrast: true });
    expect(stageSurface(p).border).toBe(p.cardBorder);
    expect(stageSurface(p).border).not.toBeNull();
  });

  it("is solid whatever the glass: never a translucent fill", () => {
    for (const scheme of ["light", "dark"] as const) {
      for (const reduceTransparency of [false, true]) {
        const p = stagePalette(scheme, { reduceTransparency, increasedContrast: false });
        expect(stageSurface(p).card).toMatch(/^#[0-9A-F]{6}$/i);
      }
    }
  });
});

describe("withProtectedStageBar: the share centre's bar is solid", () => {
  const BASE = {
    headerShown: true,
    title: "Paylaşımlarınız",
    headerStyle: { backgroundColor: "#F2F2F7" },
    headerTintColor: "#000000",
    headerBackButtonDisplayMode: "minimal" as const,
  };

  it("is opaque, in the flat stage base, with no material and no scroll-edge effect", () => {
    for (const scheme of ["light", "dark"] as const) {
      const p = stagePalette(scheme, { reduceTransparency: true, increasedContrast: false });
      const options = withProtectedStageBar(BASE, p);
      expect(options.headerTransparent).toBe(false);
      expect(options.headerStyle).toEqual({ backgroundColor: p.base });
      expect(options.headerShadowVisible).toBe(false);
      expect(options.scrollEdgeEffects).toEqual({
        top: "hidden",
        bottom: "hidden",
        left: "hidden",
        right: "hidden",
      });
      expect("headerBlurEffect" in options).toBe(false);
      expect("headerBackground" in options).toBe(false);
    }
  });

  it("shows only the back chevron in the stage ink; the title stays for the back menu", () => {
    const p = stagePalette("dark", { reduceTransparency: true, increasedContrast: false });
    const options = withProtectedStageBar(BASE, p);
    expect(options.headerTitle).toBe("");
    expect(options.title).toBe(BASE.title);
    expect(options.headerTintColor).toBe(p.ink);
  });
});

/* ------------------------------------------------------------------ */
/* AA for the shared rows' system colours on the stage grounds          */
/* ------------------------------------------------------------------ */

function channel(c: number): number {
  const s = c / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const v = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(v.slice(i, i + 2), 16));
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * The list rows, kickers, footers, guidance blocks and empty states keep the
 * system text colours (they are shared with the screens that stay on the
 * system ground); on these four screens they sit on the stage wash, its base
 * and the stage card. Increase Contrast moves both palettes together.
 */
const PAIRS: readonly { contrast: Contrast; increasedContrast: boolean }[] = [
  { contrast: "standard", increasedContrast: false },
  { contrast: "high", increasedContrast: true },
];

describe("the system text colours stay AA on every stage ground", () => {
  it.each(["light", "dark"] as const)("%s: ink, secondary, tertiary and tint, 4.5:1", (scheme) => {
    const failures: string[] = [];
    for (const pair of PAIRS) {
      const theme = colorsFor(scheme, pair.contrast);
      for (const reduceTransparency of [false, true]) {
        const p = stagePalette(scheme, {
          reduceTransparency,
          increasedContrast: pair.increasedContrast,
        });
        const grounds = [...new Set([...p.wash, p.base, p.card])];
        for (const ground of grounds) {
          for (const token of ["ink", "inkSoft", "inkFaint", "primary"] as const) {
            const ratio = contrast(theme[token], ground);
            if (ratio < 4.5) {
              failures.push(`${pair.contrast} ${token} on ${ground}: ${ratio.toFixed(2)}`);
            }
          }
        }
      }
    }
    expect(failures).toEqual([]);
  });

  it("near miss: the check fails a colour that is not AA", () => {
    expect(contrast("#8E8E93", "#F4F1EB")).toBeLessThan(4.5);
  });
});
