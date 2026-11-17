/**
 * INT-459 refresh — Palette B (owner, 17 Oct 2026): "the app's own warm paper
 * background with teal, so the admin panel and the app share one brand".
 *
 * - **One file.** Every colour the console paints, in both themes, is declared
 *   in `app/palette.css` and nowhere else in the native layer, so a palette
 *   change is a change to that file (and to the browser's theme colour, which
 *   this spec pins to it).
 * - **Pinned to the app.** Each shared token equals the app's own value in
 *   `apps/mobile/src/lib/theme.ts`, in both themes; a change on either side
 *   fails here until the other follows.
 * - **Shaded only where AA requires it.** Two light-theme text tokens take a
 *   deeper shade of the app's hue, because the app's value falls under 4.5:1
 *   on the raised surface the console sets text on. The spec proves the
 *   shortfall (the near-miss) and that the shade keeps the hue.
 * - **RED stays the app's.** The emergency colour is reserved for the RED
 *   route (02 §5.3); no console token reuses it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { appPalette, APP_THEME } from "./support/app-palette";
import { APP, contrast, NATIVE_SHEETS, rulesOf, type Rule } from "./support/css";

const DARK = "@media (prefers-color-scheme: dark)";
type Theme = Record<string, string>;
type Scheme = "light" | "dark";

/** The app's tokens this spec reads; the reader must find each one. */
const APP_KEYS = [
  "background",
  "surface",
  "surfaceRaised",
  "ink",
  "inkSoft",
  "inkFaint",
  "border",
  "primary",
  "primarySoft",
  "onPrimary",
  "amber",
  "success",
  "emergency",
  "emergencySoft",
] as const;
type AppKey = (typeof APP_KEYS)[number];

const APP_PALETTE = appPalette();

function appHex(scheme: Scheme, key: AppKey): string {
  const value = APP_PALETTE[scheme][key];
  expect(value, `app ${scheme}.${key}`).toMatch(/^#[0-9a-f]{6}$/);
  return value!;
}

function tokens(rules: Rule[], at: string): Theme {
  const out: Theme = {};
  for (const r of rules.filter((r) => r.selector === ":root" && r.at.join() === at))
    for (const [k, v] of Object.entries(r.decls)) if (k.startsWith("--")) out[k] = v;
  return out;
}

const PALETTE = rulesOf("palette.css");
const admin = { light: tokens(PALETTE, ""), dark: tokens(PALETTE, DARK) };

/** Console token -> the app token it shares, in both themes. */
const SHARED: Record<string, AppKey> = {
  "--bg": "background",
  "--surface": "surface",
  "--surface-2": "surfaceRaised",
  "--field": "surface",
  "--ink": "ink",
  "--muted": "inkSoft",
  "--line": "border",
  "--track": "border",
  "--field-border": "inkFaint",
  "--warn": "amber",
  "--accent-fill": "primary",
  "--data": "primary",
  "--focus": "primary",
  "--on-accent": "onPrimary",
  "--nav-selected": "primarySoft",
};

/** Shared in dark; one shade deeper in light (see DEEPENED). */
const SHARED_DARK_ONLY: Record<string, AppKey> = { "--ok": "success", "--accent": "primary" };

/** States the app has no token for: the console's own, never the RED hex. */
const CONSOLE_ONLY = ["--bad", "--unknown"];

function hex(t: Theme, name: string): string {
  const v = t[name];
  expect(v, name).toMatch(/^#[0-9a-f]{6}$/);
  return v!;
}

function hue(value: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(value.slice(i, i + 2), 16) / 255) as [
    number,
    number,
    number,
  ];
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  if (d === 0) return 0;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}

describe("Palette B: one file holds every colour", () => {
  it("palette.css declares every colour token of both themes, in lower-case hex", () => {
    for (const t of [admin.light, admin.dark]) {
      for (const name of [...Object.keys(SHARED), ...Object.keys(SHARED_DARK_ONLY)]) hex(t, name);
      for (const name of CONSOLE_ONLY) hex(t, name);
    }
  });

  it("no other sheet of the native layer declares a colour token", () => {
    const colour = /^#[0-9a-f]{3,8}$|rgb\(|color-mix\(/i;
    for (const sheet of NATIVE_SHEETS.filter((s) => s !== "palette.css")) {
      const declared = rulesOf(sheet)
        .filter((r) => r.selector === ":root")
        .flatMap((r) => Object.entries(r.decls))
        .filter(([k, v]) => k.startsWith("--") && colour.test(v))
        .map(([k]) => `${sheet} ${k}`);
      expect(declared).toEqual([]);
    }
  });

  it("the browser's theme colour is the palette's page background, per theme", () => {
    const layout = readFileSync(join(APP, "layout.tsx"), "utf8");
    const pairs = [
      ...layout.matchAll(/prefers-color-scheme: (light|dark)\)", color: "(#[0-9a-f]{6})"/g),
    ];
    expect(Object.fromEntries(pairs.map((m) => [m[1], m[2]]))).toEqual({
      light: admin.light["--bg"],
      dark: admin.dark["--bg"],
    });
  });
});

describe("Palette B: the console and the app share one brand", () => {
  for (const scheme of ["light", "dark"] as const) {
    it(`${scheme}: every shared token equals the app's value`, () => {
      const shared = scheme === "dark" ? { ...SHARED, ...SHARED_DARK_ONLY } : SHARED;
      for (const [name, key] of Object.entries(shared)) {
        expect(hex(admin[scheme], name), `${name} = app ${key}`).toBe(appHex(scheme, key));
      }
    });

    it(`${scheme}: no console colour is the app's RED-only emergency colour`, () => {
      expect(reusesEmergency(admin[scheme], scheme)).toEqual([]);
    });
  }

  it("near-miss: a --bad copied from the app's emergency red is caught", () => {
    const draft = { ...admin.light, "--bad": appHex("light", "emergency") };
    expect(reusesEmergency(draft, "light")).toEqual(["--bad"]);
  });
});

/** The console tokens that reuse the app's RED-only colours (02 §5.3). */
function reusesEmergency(t: Theme, scheme: Scheme): string[] {
  const reserved = [appHex(scheme, "emergency"), appHex(scheme, "emergencySoft")];
  return Object.entries(t)
    .filter(([, value]) => reserved.includes(value.toLowerCase()))
    .map(([name]) => name);
}

/** Light text tokens one shade deeper than the app, and why. */
const DEEPENED: Record<string, AppKey> = { "--ok": "success", "--accent": "primary" };

describe("Palette B: a shade changes only where AA requires it, and keeps the hue", () => {
  const raised = appHex("light", "surfaceRaised");

  for (const [name, key] of Object.entries(DEEPENED)) {
    it(`light ${name}: the app's ${key} falls under 4.5:1 on the raised surface (near-miss)`, () => {
      expect(contrast(appHex("light", key), raised)).toBeLessThan(4.5);
    });

    it(`light ${name}: the console's shade clears 4.5:1 there and keeps the app's hue`, () => {
      const shade = hex(admin.light, name);
      expect(contrast(shade, raised)).toBeGreaterThanOrEqual(4.5);
      expect(Math.abs(hue(shade) - hue(appHex("light", key)))).toBeLessThanOrEqual(6);
    });
  }
});

describe("the app's palette is read from its own source", () => {
  it("reads apps/mobile/src/lib/theme.ts and finds every token this spec uses", () => {
    expect(APP_THEME).toMatch(/apps\/mobile\/src\/lib\/theme\.ts$/);
    for (const scheme of ["light", "dark"] as const)
      for (const key of APP_KEYS) appHex(scheme, key);
  });

  it("near-miss: a palette without its dark block is refused, not read as empty", () => {
    const light = 'export const palette = {\n  light: {\n    ink: "#1C1B18",\n  },\n} as const;';
    expect(() => appPalette(light)).toThrow(/no dark block/);
  });
});
