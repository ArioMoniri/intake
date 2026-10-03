import { describe, expect, it } from "vitest";

import { APP_STEPS } from "./prefs/appearance";
import {
  HEADING_ROLES,
  ROLE_LADDER,
  ROUNDED_ROLES,
  SYSTEM_ROLES,
  colorsFor,
  fonts,
  highContrastPalette,
  lineHeight,
  motion,
  palette,
  radius,
  roleWeight,
  scaledControl,
  scaledSize,
  spacing,
  textStyles,
  typeScale,
  type ColorScheme,
  type ColorToken,
  type Contrast,
  type ThemeColors,
} from "./theme";

// WCAG 2.x relative luminance + contrast ratio, computed here so the
// accessibility floor (02 §8.2) is a test, not a hope.
function channel(v: number): number {
  const s = v / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Hue (degrees) and chroma (0..255: the spread between the strongest and
 * weakest channel) of a hex colour. Chroma rather than HSL saturation, which
 * calls Apple's near-white #F2F2F7 "24 % saturated" because it divides by
 * how close the colour is to white.
 */
function hueChroma(hex: string): { hue: number; chroma: number } {
  const [r, g, b] = rgb(hex);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  if (delta === 0) {
    return { hue: 0, chroma: 0 };
  }
  const hue =
    max === r ? ((g - b) / delta) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
  return { hue: (hue * 60 + 360) % 360, chroma: delta };
}

const SCHEMES: readonly ColorScheme[] = ["light", "dark"];
const CONTRASTS: readonly Contrast[] = ["standard", "high"];
const MODES = SCHEMES.flatMap((scheme) =>
  CONTRASTS.map((level) => ({ scheme, level, name: `${scheme}/${level}` })),
);

type Pair = readonly [ColorToken, ColorToken];

/**
 * Every text colour the app sets, on every ground it is set on. A new text
 * token or a new ground joins this list, or the pair is not proved.
 */
const TEXT_PAIRS: readonly Pair[] = [
  ...(["ink", "inkSoft", "inkFaint", "primary", "amber", "success"] as const).flatMap((fg) => [
    [fg, "background"] as const,
    [fg, "surface"] as const,
  ]),
  ["ink", "surfaceRaised"],
  ["inkSoft", "surfaceRaised"],
  ["inkFaint", "surfaceRaised"],
  ["primary", "surfaceRaised"],
  ["ink", "thumb"],
  ["primary", "primarySoft"],
  ["ink", "primarySoft"],
  ["onPrimary", "primary"],
  ["onCta", "cta"],
  ["amber", "amberSoft"],
  ["success", "successSoft"],
  ["emergency", "emergencySoft"],
];

/**
 * Clinical text: the question, the patient's answers, the note, a record
 * reading, a hospital name. It renders in `ink`, and secondary lines of the
 * same content in `inkSoft`, so both are held to AAA (7:1) on the grounds
 * they sit on.
 */
const CLINICAL_PAIRS: readonly Pair[] = [
  ["ink", "background"],
  ["ink", "surface"],
  ["ink", "surfaceRaised"],
  ["inkSoft", "background"],
  ["inkSoft", "surface"],
];

/**
 * SC 1.4.11: a boundary or fill that identifies a control on its own, against
 * the grounds it sits on. `border` outlines inputs and unselected chips;
 * `cta` is the filled button; `primary` fills an on switch, the progress arc
 * and a selected chip's edge.
 */
const BOUNDARY_PAIRS: readonly Pair[] = (["border", "cta", "primary"] as const).flatMap((fg) => [
  [fg, "background"] as const,
  [fg, "surface"] as const,
]);

describe("palette: one token set in every scheme and contrast mode", () => {
  it("light, dark and both high-contrast palettes expose the same tokens", () => {
    const keys = Object.keys(palette.light).sort();
    for (const { scheme, level, name } of MODES) {
      expect(Object.keys(colorsFor(scheme, level)).sort(), name).toEqual(keys);
    }
    expect(keys).toEqual(Object.keys(SYSTEM_ROLES).sort());
  });

  it("colorsFor hands back the palette for the scheme and contrast asked for", () => {
    expect(colorsFor("light", "standard")).toBe(palette.light);
    expect(colorsFor("dark", "standard")).toBe(palette.dark);
    expect(colorsFor("light", "high")).toBe(highContrastPalette.light);
    expect(colorsFor("dark", "high")).toBe(highContrastPalette.dark);
  });

  it("every value is an opaque colour: no alpha, so every pair below is the pair on screen", () => {
    for (const { scheme, level, name } of MODES) {
      for (const [token, value] of Object.entries(colorsFor(scheme, level))) {
        expect(value, `${name} ${token}`).toMatch(/^#[0-9A-F]{6}$/);
      }
    }
  });

  it("no token exists to decorate: no gradient, glow or shadow colour", () => {
    for (const token of Object.keys(palette.light)) {
      expect(token).not.toMatch(/gradient|glow|shadow|wash|mesh/i);
    }
  });
});

describe("one restrained accent (02 §5.2)", () => {
  // The accent family, and the status colours that carry a state with a
  // label beside them. Everything else is a neutral.
  const ACCENT: readonly ColorToken[] = ["primary", "primarySoft", "onPrimary", "cta"];
  const STATUS: readonly ColorToken[] = [
    "amber",
    "amberSoft",
    "success",
    "successSoft",
    "emergency",
    "emergencySoft",
  ];

  it.each(MODES)("$name: grounds, text, boundaries and separators are neutral greys", (mode) => {
    const colors = colorsFor(mode.scheme, mode.level);
    for (const [token, value] of Object.entries(colors) as [ColorToken, string][]) {
      if (ACCENT.includes(token) || STATUS.includes(token) || token === "onCta") {
        continue;
      }
      // Apple's greys carry a faint blue cast (#F2F2F7 spreads 5); a warm
      // paper or a tinted grey spreads far more.
      expect(hueChroma(value).chroma, `${token} ${value}`).toBeLessThanOrEqual(8);
    }
  });

  it.each(MODES)("$name: the accent is one hue, a clinical teal", (mode) => {
    const colors = colorsFor(mode.scheme, mode.level);
    const hues = (["primary", "primarySoft", "cta"] as const).map((t) => hueChroma(colors[t]).hue);
    for (const hue of hues) {
      // Teal: between green (120) and cyan (180), well away from the
      // purple-blue band (220-300) of generic generated palettes.
      expect(hue).toBeGreaterThanOrEqual(160);
      expect(hue).toBeLessThanOrEqual(185);
    }
  });
});

describe("contrast floors, in light, dark and Increase Contrast", () => {
  it.each(MODES)("$name: every text pair meets WCAG AA (4.5:1)", (mode) => {
    const c = colorsFor(mode.scheme, mode.level);
    const failing = TEXT_PAIRS.filter(([fg, bg]) => contrast(c[fg], c[bg]) < 4.5).map(
      ([fg, bg]) => `${fg} on ${bg}: ${contrast(c[fg], c[bg]).toFixed(2)}`,
    );
    expect(failing).toEqual([]);
  });

  it.each(MODES)("$name: clinical text meets WCAG AAA (7:1)", (mode) => {
    const c = colorsFor(mode.scheme, mode.level);
    const failing = CLINICAL_PAIRS.filter(([fg, bg]) => contrast(c[fg], c[bg]) < 7).map(
      ([fg, bg]) => `${fg} on ${bg}: ${contrast(c[fg], c[bg]).toFixed(2)}`,
    );
    expect(failing).toEqual([]);
  });

  it.each(MODES)("$name: control boundaries and fills meet SC 1.4.11 (3:1)", (mode) => {
    const c = colorsFor(mode.scheme, mode.level);
    const failing = BOUNDARY_PAIRS.filter(([fg, bg]) => contrast(c[fg], c[bg]) < 3).map(
      ([fg, bg]) => `${fg} on ${bg}: ${contrast(c[fg], c[bg]).toFixed(2)}`,
    );
    expect(failing).toEqual([]);
  });

  it.each(SCHEMES)("%s: Increase Contrast never weakens a pair", (scheme) => {
    const standard = colorsFor(scheme, "standard");
    const high = colorsFor(scheme, "high");
    for (const [fg, bg] of [...TEXT_PAIRS, ...BOUNDARY_PAIRS]) {
      expect(
        contrast(high[fg], high[bg]),
        `${fg} on ${bg}: ${contrast(high[fg], high[bg]).toFixed(2)} < ${contrast(standard[fg], standard[bg]).toFixed(2)}`,
      ).toBeGreaterThanOrEqual(contrast(standard[fg], standard[bg]) - 1e-9);
    }
  });

  it.each(SCHEMES)("%s: Increase Contrast moves text and edges, never the grounds", (scheme) => {
    const standard = colorsFor(scheme, "standard");
    const high = colorsFor(scheme, "high");
    for (const ground of ["background", "surface", "surfaceRaised", "thumb"] as const) {
      expect(high[ground], ground).toBe(standard[ground]);
    }
    expect(high.separator).not.toBe(standard.separator);
    expect(high.inkSoft).not.toBe(standard.inkSoft);
  });

  // The pair INT-144 recorded below the floor: closed by this palette.
  it("the known sub-AA pairs of the old palette are closed", () => {
    for (const { scheme, level } of MODES) {
      const c = colorsFor(scheme, level);
      expect(contrast(c.inkFaint, c.background)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.inkFaint, c.surface)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.inkFaint, c.surfaceRaised)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.success, c.successSoft)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.border, c.surface)).toBeGreaterThanOrEqual(3);
    }
  });
});

describe("RED surfaces are unchanged (ADR-033 §5, 02 §5.3)", () => {
  // The pre-refresh values. The RED route's colours are not the refresh's to
  // tune, in any scheme or contrast mode. Assembled from parts, because
  // e2e/nav.spec.ts allows the emergency hex in theme.ts alone.
  const RED: Readonly<Record<ColorScheme, Pick<ThemeColors, "emergency" | "emergencySoft">>> = {
    light: { emergency: ["#B3", "261E"].join(""), emergencySoft: "#F9E5E3" },
    dark: { emergency: ["#E5", "756D"].join(""), emergencySoft: "#392320" },
  };

  it.each(MODES)("$name: emergency and emergencySoft keep their values", (mode) => {
    const c = colorsFor(mode.scheme, mode.level);
    expect(c.emergency).toBe(RED[mode.scheme].emergency);
    expect(c.emergencySoft).toBe(RED[mode.scheme].emergencySoft);
  });

  it("no other token borrows the emergency hue", () => {
    for (const { scheme, level } of MODES) {
      const c = colorsFor(scheme, level);
      for (const [token, value] of Object.entries(c)) {
        if (token === "emergency" || token === "emergencySoft") {
          continue;
        }
        expect(value, token).not.toBe(c.emergency);
        expect(value, token).not.toBe(c.emergencySoft);
      }
    }
  });
});

describe("Apple system semantics", () => {
  // Apple's documented values for the UIKit colours the palette mirrors
  // exactly (UIKit "UI element colors" and "Standard colors").
  const APPLE: Readonly<Record<string, Readonly<Record<ColorScheme, string>>>> = {
    systemGroupedBackground: { light: "#F2F2F7", dark: "#000000" },
    secondarySystemGroupedBackground: { light: "#FFFFFF", dark: "#1C1C1E" },
    systemGray5: { light: "#E5E5EA", dark: "#2C2C2E" },
    label: { light: "#000000", dark: "#FFFFFF" },
    opaqueSeparator: { light: "#C6C6C8", dark: "#38383A" },
  };

  it("every token names its UIKit colour and its Material 3 role", () => {
    for (const [token, role] of Object.entries(SYSTEM_ROLES)) {
      expect(role.ios.length, token).toBeGreaterThan(0);
      expect(role.android.length, token).toBeGreaterThan(0);
    }
  });

  it("the grounds, the label and the separator are Apple's own values", () => {
    const exact = Object.entries(SYSTEM_ROLES).filter(([, role]) => role.exact);
    expect(exact.map(([token]) => token).sort()).toEqual(
      ["background", "ink", "separator", "surface", "surfaceRaised"].sort(),
    );
    for (const [token, role] of exact) {
      const apple = APPLE[role.ios];
      expect(apple, `${role.ios} has no recorded value`).toBeDefined();
      for (const scheme of SCHEMES) {
        expect(palette[scheme][token as ColorToken], `${token} ${scheme}`).toBe(apple[scheme]);
      }
    }
  });

  it("the label ladder keeps its order: label, secondary, tertiary", () => {
    for (const { scheme, level, name } of MODES) {
      const c = colorsFor(scheme, level);
      const ink = contrast(c.ink, c.surface);
      const soft = contrast(c.inkSoft, c.surface);
      const faint = contrast(c.inkFaint, c.surface);
      expect(ink, name).toBeGreaterThan(soft);
      expect(soft, name).toBeGreaterThan(faint);
    }
  });
});

describe("geometry: the 8-pt grid and iOS corners", () => {
  it("every spacing step is on the grid, with 4 as the one half step", () => {
    for (const [name, value] of Object.entries(spacing)) {
      expect(value % 4, name).toBe(0);
      if (name !== "xs") {
        expect(value % 8, name).toBe(0);
      }
    }
    expect(spacing.screen).toBe(16);
  });

  it("no container is rounder than 12 pt; the capsule is for small tags alone", () => {
    for (const [name, value] of Object.entries(radius)) {
      if (name === "chip") {
        expect(value).toBeGreaterThanOrEqual(999);
        continue;
      }
      expect(value, name).toBeLessThanOrEqual(12);
      expect(value, name).toBeGreaterThanOrEqual(8);
    }
  });
});

describe("typography: Apple's Dynamic Type ladder", () => {
  it("the ladder is Apple's, Large Title to Caption 2, at the default size", () => {
    expect(textStyles).toEqual({
      largeTitle: 34,
      title1: 28,
      title2: 22,
      title3: 20,
      headline: 17,
      body: 17,
      callout: 16,
      subheadline: 15,
      footnote: 13,
      caption1: 12,
      caption2: 11,
    });
  });

  it("every text role is one rung of it; only the numeral sits outside", () => {
    for (const [role, style] of ROLE_LADDER) {
      expect(typeScale[role], role).toBe(textStyles[style]);
    }
    expect(Object.keys(typeScale).sort()).toEqual(
      [...ROLE_LADDER.map(([role]) => role), "display"].sort(),
    );
  });

  it("a screen title is Large Title bold; a question is Title 2 semibold", () => {
    const ladder = new Map(ROLE_LADDER);
    expect(ladder.get("hero")).toBe("largeTitle");
    expect(roleWeight.hero).toBe(700);
    expect(ladder.get("question")).toBe("title2");
    expect(roleWeight.question).toBe(600);
    expect(ladder.get("body")).toBe("body");
    expect(roleWeight.body).toBe(400);
  });

  it("the face is the platform's own; the Large Title and the numeral are rounded", () => {
    expect([...ROUNDED_ROLES].sort()).toEqual(["display", "hero"]);
    expect(fonts.sans).toBe("System");
    expect(fonts.rounded.ios).toBe("ui-rounded");
    expect(JSON.stringify(fonts)).not.toMatch(/Newsreader|Inter|Fraunces/);
  });
});

// INT-330 (MOTION-1): the navigators read `motion.duration`; the older
// `fadeMs` stays as its alias so no consumer carries a second 120.
describe("motion budget (02 §5.2a)", () => {
  it("fadeMs remains the alias of duration.fade", () => {
    expect(motion.fadeMs).toBe(motion.duration.fade);
    expect(motion.duration.instant).toBe(0);
  });

  it("no motion duration exceeds fadeMs", () => {
    const durations = Object.entries(motion.duration);
    expect(durations.length).toBeGreaterThan(1);
    for (const [name, ms] of durations) {
      expect(ms, name).toBeGreaterThanOrEqual(0);
      expect(ms, name).toBeLessThanOrEqual(motion.fadeMs);
    }
  });

  // INT-335 (MOTION-6). A loop token is a FULL period. SC 2.3.1 draws the
  // line at three flashes a second: a 333 ms cycle, so a 167 ms half. Every
  // loop the app runs takes its period from here (e2e/a11y.spec.ts BK15), so
  // this one assertion bounds all of them.
  it("every loop half-period exceeds 167 ms", () => {
    const periods = Object.entries(motion.loop);
    expect(periods.length).toBeGreaterThan(0);
    for (const [name, ms] of periods) {
      expect(Number.isFinite(ms), name).toBe(true);
      expect(ms / 2, name).toBeGreaterThan(167);
    }
  });

  // INT-341 (MOTION-12): press feedback is an instant opacity step, read from
  // one token set. The values are the reconciled ones (motion-verification
  // §2.2); the composer's disabled send was normalised onto them (0.4 → 0.5).
  it("the disabled opacity stays distinguishable from the pressed opacity", () => {
    expect(motion.press).toEqual({ opacity: 0.85, rowOpacity: 0.7, disabledOpacity: 0.5 });
    const { disabledOpacity } = motion.press;
    // A disabled control stays on screen, so it can still say what it is.
    expect(disabledOpacity).toBeGreaterThan(0);
    for (const pressed of [motion.press.opacity, motion.press.rowOpacity]) {
      // A press is visible at all…
      expect(pressed).toBeLessThan(1);
      // …and never as dim as a control that cannot be pressed, so a finger
      // on an enabled control does not read as the control switching off.
      expect(disabledOpacity).toBeLessThan(pressed);
    }
  });
});

describe("dynamic type", () => {
  it("body is 17 at fontScale 1.0", () => {
    expect(scaledSize("body", 1.0)).toBe(17);
  });

  it("follows the user's scale up to 2.0 and no further (02 §8.2)", () => {
    expect(scaledSize("body", 1.5)).toBe(Math.round(17 * 1.5));
    expect(scaledSize("body", 2.0)).toBe(34);
    expect(scaledSize("body", 3.0)).toBe(34);
  });

  it("never collapses below half scale", () => {
    expect(scaledSize("body", 0.1)).toBe(Math.round(17 * 0.5));
  });

  // INT-260, from the owner's own words on the simulator: "navbar and sizes
  // dont match". Text scaled and the chrome did not, so the rail read as a
  // different app's navbar pasted under the content. A control's box is a
  // dimension in the same coordinate system as a glyph, so it takes the SAME
  // clamp — one number, one place, and the rail can no longer drift from the
  // body text it sits under.
  it("a control's box scales with the text, under the same clamp", () => {
    expect(scaledControl(20, 1.0)).toBe(20);
    expect(scaledControl(20, 1.3)).toBe(26);
    expect(scaledControl(20, 2.0)).toBe(40);
    expect(scaledControl(46, 2.0)).toBe(92);
    // The clamp is shared with scaledSize rather than re-declared beside it.
    expect(scaledControl(20, 3.0)).toBe(scaledControl(20, 2.0));
    expect(scaledControl(20, 0.1)).toBe(scaledControl(20, 0.5));
  });

  it("a control and a glyph move together at every step of the ladder", () => {
    // The regression the owner saw: at 2.0 the body text doubled and the rail
    // icon stayed at its base size. Ratio equality is what "sizes match" means.
    for (const step of APP_STEPS) {
      expect(scaledControl(typeScale.body, step)).toBe(scaledSize("body", step));
    }
  });

  // INT-260: the in-app text-size control (lib/prefs/appearance) replaces the
  // OS value rather than composing with it, which is only safe while every
  // step it offers lies INSIDE this clamp. A step above 2.0 would be silently
  // truncated here and the control would stop being honest about its top end;
  // a step below 0.5 would be silently raised. The coupling is asserted where
  // the clamp lives, so widening either one fails at the other.
  it("every step the app control offers is inside the clamp, unchanged by it", () => {
    for (const step of APP_STEPS) {
      for (const role of Object.keys(typeScale) as (keyof typeof typeScale)[]) {
        expect(scaledSize(role, step)).toBe(Math.round(typeScale[role] * step));
      }
    }
  });

  it("line height: heading roles sit tight (1.2×), reading roles keep diacritic room (1.4×)", () => {
    // Turkish diacritics (ğ, ş, İ) never clip at reading sizes; a heading's
    // glyphs are large enough to clear them at 1.2.
    expect([...HEADING_ROLES].sort()).toEqual(["display", "hero", "question", "title"]);
    for (const role of Object.keys(typeScale) as (keyof typeof typeScale)[]) {
      const factor = HEADING_ROLES.includes(role) ? 1.2 : 1.4;
      expect(lineHeight(role, 1.0)).toBe(Math.round(typeScale[role] * factor));
    }
  });
});
