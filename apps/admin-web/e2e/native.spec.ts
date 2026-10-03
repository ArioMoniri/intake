/**
 * INT-459 — the Apple-native layer (`app/native-tokens.css`,
 * `app/native-shell.css`, `app/native-content.css`) as a contract.
 *
 * - **One token set per theme.** Light and dark come from the same names, and
 *   the layer redefines every token the earlier sheets set per theme, so no
 *   stray value from console.css or refresh.css leaks into either theme.
 * - **WCAG AA, computed from the tokens.** Text on every solid surface, the
 *   accent button's label, and text on the glass chrome composited over the
 *   worst backdrop that can scroll beneath it — and over its solid fallback.
 * - **Glass only on chrome.** Only the sidebar, the top bar and a sheet may
 *   carry a backdrop filter; content keeps opaque fills. Each
 *   glass surface has a solid fallback under prefers-reduced-transparency,
 *   prefers-contrast: more, and a browser without backdrop-filter.
 * - **Motion is a spring, and never on a critical control.** Every rule that
 *   animates or transitions is evaluated against the rendered four-eyes forms:
 *   none may match a form, button, input, select, textarea or anything inside a
 *   form.
 *
 * Each property has its near-miss beside it.
 */
import { createElement, type ReactElement } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { describe, expect, it } from "vitest";

import { CicdConsole } from "../src/cicd/console";
import { renderCicd, type CicdPayload } from "../src/cicd/module";
import { VoiceConsole } from "../src/voice/console";
import { renderVoice, type VoicePayload } from "../src/voice/module";
import {
  APP,
  allRules,
  blend,
  contrast,
  NATIVE_SHEETS,
  nativeRules,
  rulesOf,
  selectorsOf,
  sheet,
  SHEETS,
  type Rule,
} from "./support/css";

const NATIVE = nativeRules();
const DARK_MEDIA = "@media (prefers-color-scheme: dark)";

type Theme = Record<string, string>;

function tokensOf(rules: Rule[]): Theme {
  const out: Theme = {};
  for (const r of rules)
    for (const [k, v] of Object.entries(r.decls)) if (k.startsWith("--")) out[k] = v;
  return out;
}

function themes(rules: Rule[] = NATIVE): { light: Theme; dark: Theme } {
  return {
    light: tokensOf(rules.filter((r) => r.selector === ":root" && r.at.length === 0)),
    dark: tokensOf(rules.filter((r) => r.selector === ":root" && r.at.join() === DARK_MEDIA)),
  };
}

/** A colour (or a glass share) the light theme sets that dark leaves unset, or
 * a token dark sets that light never declares. */
function colourGaps(light: Theme, dark: Theme): string[] {
  const colour = /^(#[0-9a-f]{6}|\d{1,3}%)$/i;
  return [
    ...Object.keys(light)
      .filter((k) => colour.test(light[k]!) && dark[k] === undefined)
      .map((k) => `dark lacks ${k}`),
    ...Object.keys(dark)
      .filter((k) => light[k] === undefined)
      .map((k) => `light lacks ${k}`),
  ];
}

function hex(t: Theme, name: string): string {
  const v = t[name];
  expect(v, name).toMatch(/^#[0-9a-f]{6}$/i);
  return v!.toLowerCase();
}

function share(t: Theme, name: string): number {
  const v = t[name];
  expect(v, name).toMatch(/^\d{1,3}%$/);
  return Number(v!.slice(0, -1)) / 100;
}

const REQUIRED = [
  "--bg",
  "--surface",
  "--surface-2",
  "--row-hover",
  "--field",
  "--field-border",
  "--ink",
  "--muted",
  "--line",
  "--hairline",
  "--ok",
  "--warn",
  "--bad",
  "--unknown",
  "--accent",
  "--accent-fill",
  "--accent-fill-active",
  "--on-accent",
  "--data",
  "--track",
  "--rail",
  "--focus",
  "--chrome",
  "--chrome-mix",
  "--chrome-edge",
  "--nav-selected",
];

describe("one token set per theme", () => {
  const t = themes();

  it("light and dark each define every required token, and every colour in both", () => {
    for (const name of REQUIRED) {
      expect(t.light[name], `light ${name}`).toBeDefined();
      expect(t.dark[name], `dark ${name}`).toBeDefined();
    }
    expect(colourGaps(t.light, t.dark)).toEqual([]);
  });

  it("the layer redefines every token an earlier sheet sets per theme", () => {
    const earlier = SHEETS.filter((s) => !s.startsWith("native-")).flatMap((s) =>
      rulesOf(s).filter((r) => r.selector === ":root" && r.at.join() === DARK_MEDIA),
    );
    expect(Object.keys(tokensOf(earlier)).length).toBeGreaterThan(10);
    for (const name of Object.keys(tokensOf(earlier))) {
      expect(t.light[name], `light ${name}`).toBeDefined();
      expect(t.dark[name], `dark ${name}`).toBeDefined();
    }
  });

  it("content surfaces are opaque colours", () => {
    for (const theme of [t.light, t.dark]) {
      for (const name of ["--bg", "--surface", "--surface-2", "--field", "--chrome"])
        hex(theme, name);
    }
  });

  it("near-miss: a dark block missing one colour is caught", () => {
    const rest = Object.fromEntries(Object.entries(t.dark).filter(([k]) => k !== "--muted"));
    expect(colourGaps(t.light, rest)).toEqual(["dark lacks --muted"]);
  });
});

// --- contrast -------------------------------------------------------------------

/** What can sit beneath the glass: every solid surface and data colour, and a
 * line of text as the blur spreads it (30 % ink over its card). */
function backdrops(t: Theme): string[] {
  const solid = [
    "--bg",
    "--surface",
    "--surface-2",
    "--track",
    "--data",
    "--ok",
    "--warn",
    "--bad",
    "--unknown",
  ].map((n) => hex(t, n));
  return [...solid, blend(hex(t, "--ink"), hex(t, "--surface"), 0.3)];
}

describe("WCAG AA contrast, computed from the tokens in both themes", () => {
  const all = themes();
  for (const [name, t] of [
    ["light", all.light],
    ["dark", all.dark],
  ] as const) {
    it(`${name}: text on every solid surface is at least 4.5:1`, () => {
      for (const fg of ["--ink", "--muted", "--ok", "--warn", "--bad", "--unknown", "--accent"]) {
        for (const bg of ["--bg", "--surface", "--surface-2", "--row-hover", "--field"]) {
          expect(contrast(hex(t, fg), hex(t, bg)), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    });

    it(`${name}: the accent button's label is at least 4.5:1, pressed too`, () => {
      for (const fill of ["--accent-fill", "--accent-fill-active"]) {
        expect(contrast(hex(t, "--on-accent"), hex(t, fill)), fill).toBeGreaterThanOrEqual(4.5);
      }
    });

    it(`${name}: chrome text over glass stays at least 4.5:1 over its worst backdrop`, () => {
      const mix = share(t, "--chrome-mix");
      for (const under of backdrops(t)) {
        const glass = blend(hex(t, "--chrome"), under, mix);
        for (const fg of ["--ink", "--muted"]) {
          expect(contrast(hex(t, fg), glass), `${fg} over ${under}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    });

    it(`${name}: the solid fallback and the selected row are at least 4.5:1`, () => {
      for (const fg of ["--ink", "--muted"]) {
        expect(contrast(hex(t, fg), hex(t, "--chrome")), `${fg} on chrome`).toBeGreaterThanOrEqual(
          4.5,
        );
      }
      expect(contrast(hex(t, "--ink"), hex(t, "--nav-selected"))).toBeGreaterThanOrEqual(4.5);
    });

    it(`${name}: the focus ring is at least 3:1 on every surface it can sit on`, () => {
      for (const bg of ["--bg", "--surface", "--chrome", "--field"]) {
        expect(contrast(hex(t, "--focus"), hex(t, bg)), bg).toBeGreaterThanOrEqual(3);
      }
    });
  }

  it("near-miss: Apple's own dark systemBlue under white text fails AA", () => {
    expect(contrast("#ffffff", "#0a84ff")).toBeLessThan(4.5);
  });

  it("near-miss: a 70 % glass would fail over the light theme's red", () => {
    const t = all.light;
    const glass = blend(hex(t, "--chrome"), hex(t, "--bad"), 0.7);
    expect(contrast(hex(t, "--muted"), glass)).toBeLessThan(4.5);
  });
});

// --- glass ------------------------------------------------------------------------

/** Chrome that may be glass: the sidebar, the top bar's backing layer, a sheet.
 * The language switch sits on the sidebar and stays solid (no glass on glass). */
const CHROME = [/^\.console-nav$/, /^\.page-head::before$/, /^\.sheet$/];

function glassy(rule: Rule): boolean {
  return ["backdrop-filter", "-webkit-backdrop-filter"].some(
    (p) => rule.decls[p] !== undefined && rule.decls[p] !== "none",
  );
}

function offChrome(rules: Rule[]): string[] {
  return rules
    .filter(glassy)
    .flatMap(selectorsOf)
    .filter((s) => !CHROME.some((re) => re.test(s)));
}

describe("translucent glass sits only on chrome", () => {
  it("every backdrop filter belongs to the sidebar, the top bar or a sheet", () => {
    expect(allRules().filter(glassy).flatMap(selectorsOf).sort()).toEqual([
      ".console-nav",
      ".page-head::before",
    ]);
    expect(offChrome(allRules())).toEqual([]);
  });

  it("a glass background is the chrome tint mixed with transparency, nothing else", () => {
    for (const rule of NATIVE.filter(glassy)) {
      expect(rule.decls["background"], rule.selector).toBe(
        "color-mix(in srgb, var(--chrome) var(--chrome-mix), transparent)",
      );
    }
  });

  it("no content surface has a translucent fill", () => {
    const content =
      /(^|[\s>+~(])(\.tile|\.grid|\.band|table|t[dhr]|\.refusal|\.facts|main|\.ops)\b/;
    for (const rule of allRules()) {
      const bg = rule.decls["background"] ?? rule.decls["background-color"];
      if (bg === undefined || !selectorsOf(rule).some((s) => content.test(s))) continue;
      if (selectorsOf(rule).every((s) => /::(before|after)$/.test(s))) continue;
      expect(bg, rule.selector).not.toMatch(/transparent|\/\s*0?\.\d|\/\s*\d{1,2}%/);
    }
  });

  it("near-miss: a planted glass card is caught", () => {
    const planted = rulesOf("planted.css", ".tile { backdrop-filter: blur(8px); }");
    expect(offChrome(planted)).toEqual([".tile"]);
  });
});

describe("every glass surface has a solid fallback", () => {
  const glassSelectors = NATIVE.filter(glassy).flatMap(selectorsOf);
  const fallbacks: Record<string, string> = {
    "reduced transparency": "@media (prefers-reduced-transparency: reduce)",
    "increased contrast": "@media (prefers-contrast: more)",
    "no backdrop-filter":
      "@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))",
  };

  for (const [name, at] of Object.entries(fallbacks)) {
    it(`${name}: each glass surface turns solid`, () => {
      const inside = NATIVE.filter((r) => r.at.join() === at);
      expect(inside.length, at).toBeGreaterThan(0);
      for (const selector of glassSelectors) {
        const rule = inside.find((r) => selectorsOf(r).includes(selector));
        expect(rule, `${selector} under ${at}`).toBeDefined();
        expect(rule!.decls["background"]).toBe("var(--chrome)");
        expect(rule!.decls["backdrop-filter"]).toBe("none");
        expect(rule!.decls["-webkit-backdrop-filter"]).toBe("none");
      }
    });
  }

  it("increased contrast also draws an edge on the chrome", () => {
    const inside = NATIVE.filter((r) => r.at.join() === fallbacks["increased contrast"]);
    for (const selector of glassSelectors) {
      const rule = inside.find((r) => selectorsOf(r).includes(selector));
      expect(rule!.decls["border-color"] ?? rule!.decls["box-shadow"], selector).toMatch(
        /var\(--line\)|var\(--ink\)/,
      );
    }
  });
});

// --- motion -------------------------------------------------------------------------

function springStops(t: Theme, name: string): number[] {
  const v = t[name];
  expect(v, name).toMatch(/^linear\(/);
  return v!
    .slice("linear(".length, -1)
    .split(",")
    .map((s) => Number(s.trim().split(/\s+/)[0]));
}

/** A control, anything inside a form, and anything that holds a control (an
 * animated card would carry the button inside it along). */
const CRITICAL = [
  "form",
  "form *",
  "button",
  "input",
  "select",
  "textarea",
  ":has(button)",
  ":has(input)",
  ":has(select)",
  ":has(textarea)",
].join(", ");

function controlsDocument(): Document {
  const voice = createElement(VoiceConsole, {
    state: {
      kind: "console",
      view: renderVoice(
        JSON.parse(
          readFileSync(join(__dirname, "fixtures", "voice.payload.json"), "utf8"),
        ) as VoicePayload,
      ),
    },
    lang: "en",
    result: null,
  });
  const cicd = createElement(CicdConsole, {
    state: {
      kind: "console",
      view: renderCicd(
        JSON.parse(
          readFileSync(join(__dirname, "fixtures", "cicd.payload.json"), "utf8"),
        ) as CicdPayload,
      ),
    },
    lang: "en",
    result: null,
  });
  const body = [voice, cicd].map((tree: ReactElement) => renderToStaticMarkup(tree)).join("");
  return new JSDOM(`<!doctype html><html><body>${body}</body></html>`).window.document;
}

function moving(rule: Rule): boolean {
  if (rule.at.some((a) => a.includes("prefers-reduced-motion"))) return false;
  return ["animation", "animation-name", "transition", "transition-property"].some((p) => {
    const v = rule.decls[p];
    return v !== undefined && !/^none\b/.test(v);
  });
}

function animatedControls(rules: Rule[], doc: Document): string[] {
  const controls = [...doc.querySelectorAll(CRITICAL)];
  expect(controls.length).toBeGreaterThan(20);
  const hits: string[] = [];
  for (const rule of rules.filter(moving)) {
    for (const selector of selectorsOf(rule)) {
      const element = selector.replace(/::?(before|after)$/, "");
      if (controls.some((c) => c.matches(element))) hits.push(`${rule.sheet}: ${selector}`);
    }
  }
  return hits;
}

describe("motion is a spring, and none of it is on a critical control", () => {
  const t = themes().light;

  it("both springs are linear() curves from 0 to 1 with a soft finish", () => {
    for (const name of ["--spring-smooth", "--spring-snappy"]) {
      const stops = springStops(t, name);
      expect(stops.length, name).toBeGreaterThanOrEqual(16);
      expect(stops[0]).toBe(0);
      expect(stops.at(-1)).toBe(1);
      expect(Math.max(...stops), name).toBeLessThanOrEqual(1.05);
    }
    const smooth = springStops(t, "--spring-smooth");
    expect(smooth.every((v, i) => i === 0 || v >= smooth[i - 1]!)).toBe(true);
  });

  it("every transition and animation in the layer runs on a spring", () => {
    const moves = NATIVE.filter(moving);
    expect(moves.length).toBeGreaterThanOrEqual(3);
    for (const rule of moves) {
      const timing = [
        rule.decls["transition"],
        rule.decls["animation"],
        rule.decls["animation-timing-function"],
      ]
        .filter((v) => v !== undefined)
        .join(" ");
      expect(timing, rule.selector).toMatch(/var\(--spring-(smooth|snappy)\)/);
    }
  });

  it("no rule in any stylesheet animates a form, a button, an input, a select or a textarea", () => {
    expect(animatedControls(allRules(), controlsDocument())).toEqual([]);
  });

  it("near-miss: a tile entrance that also matches the four-eyes forms is caught", () => {
    const planted = rulesOf("planted.css", ".grid > .tile { animation: rise 400ms ease both; }");
    expect(animatedControls(planted, controlsDocument())).toEqual(["planted.css: .grid > .tile"]);
  });
});

describe("the layer stays inside the CSP and ships text as written", () => {
  const css = NATIVE_SHEETS.map((name) => sheet(name)).join("\n");

  it("no import, no url(), no origin", () => {
    expect(css).not.toMatch(/@import|url\(|https?:/);
  });

  it("no case transform, no ellipsis, no break-all (Turkish casing)", () => {
    expect(css).not.toMatch(
      /text-transform\s*:|text-overflow\s*:\s*ellipsis|word-break\s*:\s*break-all/,
    );
  });

  it("the layout imports the console's sheets with the layer's three last", () => {
    const layout = readFileSync(join(APP, "layout.tsx"), "utf8");
    const imports = [...layout.matchAll(/^import\s+"([^"]+\.css)";/gm)].map((m) => m[1]);
    expect(imports).toEqual(SHEETS.map((s) => `./${s}`));
  });
});
