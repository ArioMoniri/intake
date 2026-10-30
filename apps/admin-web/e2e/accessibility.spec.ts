/**
 * INT-450 — accessibility and motion over every rendered console page.
 *
 * **axe.** Each page is rendered from the committed recordings (the same
 * fixtures the module specs use) to static markup, loaded into jsdom, and
 * audited with axe-core against WCAG 2.0/2.1 A and AA plus best practice. jsdom
 * has no layout, so axe's colour-contrast rule cannot run there; contrast is
 * computed instead from the stylesheet's own tokens, in both themes.
 *
 * **Motion and the CSP.** The stylesheets carry a `prefers-reduced-motion`
 * block that removes every animation and transition; the only repeating motion
 * is the halo on a blocked release badge; and nothing in them reaches another
 * origin (`@import`, `url(`), so the CSP's `style-src 'self'` stays whole.
 *
 * Each property has its near-miss beside it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import axe from "axe-core";
import { JSDOM } from "jsdom";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AccessConsole } from "../src/access/console";
import { renderAccessReview, type AccessReviewPayload } from "../src/access/module";
import { CicdConsole } from "../src/cicd/console";
import { renderCicd, type CicdPayload } from "../src/cicd/module";
import { OpsConsole } from "../src/ops/console";
import { buildCsp } from "../src/ops/csp";
import { renderOps, type OpsPayload } from "../src/ops/module";
import { OverviewConsole } from "../src/overview/console";
import { renderOverview, type ReliabilityPayload } from "../src/overview/module";
import { SafetyQueueConsole } from "../src/safety-queue/console";
import { renderSafetyQueue, type SafetyQueuePayload } from "../src/safety-queue/module";
import { VoiceConsole } from "../src/voice/console";
import { renderVoice, type VoicePayload } from "../src/voice/module";
import { AXE_TIMEOUT_MS } from "./support/axe";
import { SHEETS } from "./support/css";

const FIXTURES = join(__dirname, "fixtures");
const APP = join(__dirname, "..", "app");

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

type Lang = "tr" | "en";

function pages(lang: Lang): Record<string, ReactElement> {
  const h = read<Record<string, { status: number; body: unknown }>>("ops.health.json");
  const health = {
    healthz: { ok: true as const, ...h["healthz"]! },
    readyz: { ok: true as const, ...h["readyz"]! },
    version: { ok: true as const, ...h["version"]! },
  };
  const api = read<Record<string, { status: number; body: unknown }>>("overview.api.json");
  return {
    overview: createElement(OverviewConsole, {
      state: {
        kind: "console",
        view: renderOverview(read<ReliabilityPayload>("reliability.payload.json"), {
          ok: true,
          ...api["readyz"]!,
        }),
      },
      lang,
    }),
    overview_stale: createElement(OverviewConsole, {
      state: {
        kind: "console",
        view: renderOverview(read<ReliabilityPayload>("reliability.stale.payload.json"), {
          ok: true,
          ...api["readyz"]!,
        }),
      },
      lang,
    }),
    ops: createElement(OpsConsole, {
      state: { kind: "console", view: renderOps(read<OpsPayload>("ops.payload.json"), health) },
      lang,
    }),
    ops_unconfigured: createElement(OpsConsole, {
      state: {
        kind: "console",
        view: renderOps(read<OpsPayload>("ops.unconfigured.payload.json"), health),
      },
      lang,
    }),
    cicd: createElement(CicdConsole, {
      state: { kind: "console", view: renderCicd(read<CicdPayload>("cicd.payload.json")) },
      lang,
      result: null,
    }),
    voice: createElement(VoiceConsole, {
      state: { kind: "console", view: renderVoice(read<VoicePayload>("voice.payload.json")) },
      lang,
      result: null,
    }),
    access: createElement(AccessConsole, {
      state: {
        kind: "console",
        view: renderAccessReview(read<AccessReviewPayload>("access.payload.json"), "gün"),
      },
      lang,
    }),
    safety_queue: createElement(SafetyQueueConsole, {
      state: {
        kind: "console",
        view: renderSafetyQueue(read<SafetyQueuePayload>("safety-queue.payload.json")),
      },
      lang,
      result: null,
    }),
    refused: createElement(OpsConsole, {
      state: { kind: "not_admitted", reason: "no_credentials" },
      lang,
    }),
  };
}

function documentFor(tree: ReactElement, lang: Lang): string {
  const body = renderToStaticMarkup(tree);
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8"><title>INTAKE admin</title></head><body>${body}</body></html>`;
}

async function audit(html: string): Promise<axe.Result[]> {
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  const window = dom.window as unknown as { eval: (src: string) => void; axe: typeof axe };
  window.eval(axe.source);
  const results = await window.axe.run(dom.window.document, {
    runOnly: {
      type: "tag",
      values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"],
    },
    rules: { "color-contrast": { enabled: false } },
  });
  dom.window.close();
  return results.violations;
}

function summary(violations: axe.Result[]): string[] {
  return violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

describe("every rendered console page passes axe (WCAG 2.1 A/AA + best practice)", () => {
  for (const lang of ["tr", "en"] as const) {
    for (const [name, tree] of Object.entries(pages(lang))) {
      it(
        `${name} (${lang})`,
        async () => {
          const html = documentFor(tree, lang);
          expect(html).not.toContain("style=");
          expect(summary(await audit(html))).toEqual([]);
        },
        AXE_TIMEOUT_MS,
      );
    }
  }

  it("near-miss: the harness does fail an inaccessible chart (a nameless image)", async () => {
    const html = documentFor(
      createElement(
        "main",
        null,
        createElement("h1", null, "x"),
        createElement("div", { role: "img" }),
      ),
      "en",
    );
    expect(summary(await audit(html)).some((line) => line.startsWith("role-img-alt"))).toBe(true);
  });

  it("every chart on the pages is a named image", () => {
    const html = documentFor(pages("en")["ops"]!, "en");
    const charts = [
      ...html.matchAll(/data-chart="[^"]+"[^>]*role="img"[^>]*aria-label="([^"]*)"/g),
    ];
    expect(charts.length).toBeGreaterThanOrEqual(5);
    for (const [, label] of charts) expect(label!.length).toBeGreaterThan(3);
  });
});

// --- the stylesheets --------------------------------------------------------------

// Comments are prose (the refresh layer's header names what it forbids), so
// every check below reads the rules alone.
const STYLES = SHEETS.map((f) =>
  readFileSync(join(APP, f), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
);
const CSS = STYLES.join("\n");

type Theme = Record<string, string>;

function tokens(block: string): Theme {
  const out: Theme = {};
  for (const m of block.matchAll(/(--[a-z-]+):\s*(#[0-9a-f]{6})\b/gi))
    out[m[1]!] = m[2]!.toLowerCase();
  return out;
}

function themes(): { light: Theme; dark: Theme } {
  let light: Theme = {};
  let dark: Theme = {};
  for (const css of STYLES) {
    const darkAt = css.indexOf("@media (prefers-color-scheme: dark)");
    const end = css.indexOf("\n}\n", darkAt);
    light = { ...light, ...tokens(darkAt < 0 ? css : css.slice(0, darkAt)) };
    if (darkAt >= 0) dark = { ...dark, ...tokens(css.slice(darkAt, end)) };
  }
  return { light, dark: { ...light, ...dark } };
}

function channel(hex: string, i: number): number {
  return parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16);
}

function blend(fg: string, bg: string, alpha: number): string {
  const mix = [0, 1, 2].map((i) =>
    Math.round(channel(fg, i) * alpha + channel(bg, i) * (1 - alpha)),
  );
  return `#${mix.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = [0, 1, 2].map((i) => {
    const s = channel(hex, i) / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

describe("colour contrast, computed from the tokens in both themes", () => {
  const TEXT = ["--ink", "--muted", "--ok", "--warn", "--bad", "--unknown"];
  const MARKS = ["--data", "--ok", "--warn", "--bad", "--unknown"];
  const stopFrom = Number(/\.stop-from\s*\{\s*stop-opacity:\s*([0-9.]+)/.exec(CSS)![1]);

  for (const [name, t] of Object.entries(themes())) {
    it(`${name}: text on every surface it sits on is at least 4.5:1`, () => {
      for (const fg of TEXT) {
        for (const bg of ["--surface", "--bg", "--row-hover"]) {
          expect(contrast(t[fg]!, t[bg]!), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5);
        }
      }
      expect(contrast(t["--muted"]!, t["--rail"]!), "nav on its rail").toBeGreaterThanOrEqual(4.5);
    });

    it(`${name}: a state pill's text on its own tint is at least 4.5:1`, () => {
      for (const fg of ["--ok", "--warn", "--bad", "--unknown"]) {
        const pill = blend(t[fg]!, t["--surface"]!, 0.1);
        expect(contrast(t[fg]!, pill), `${fg} pill`).toBeGreaterThanOrEqual(4.5);
      }
    });

    it(`${name}: every bar, even its faintest end, is at least 3:1 on its track`, () => {
      for (const fg of MARKS) {
        const faint = blend(t[fg]!, t["--track"]!, stopFrom);
        expect(contrast(faint, t["--track"]!), `${fg} bar`).toBeGreaterThanOrEqual(3);
      }
      expect(contrast(t["--focus"]!, t["--bg"]!), "focus ring").toBeGreaterThanOrEqual(3);
    });
  }

  it("near-miss: a gradient faded to 0.55 would fail the 3:1 floor", () => {
    const t = themes().light;
    expect(contrast(blend(t["--data"]!, t["--track"]!, 0.55), t["--track"]!)).toBeLessThan(3);
  });
});

describe("motion stays calm and optional", () => {
  it("prefers-reduced-motion removes every animation and transition", () => {
    const block = /@media \(prefers-reduced-motion: reduce\) \{([\s\S]*?)\n\}/.exec(CSS);
    expect(block).not.toBeNull();
    expect(block![1]).toContain("animation: none !important");
    expect(block![1]).toContain("transition: none !important");
    expect(block![1]).toMatch(/\*,\s*\*::before,\s*\*::after/);
  });

  it("the only repeating motion is the halo on a blocked release badge", () => {
    const infinite = [...CSS.matchAll(/([^{}]+)\{[^{}]*\binfinite\b[^{}]*\}/g)].map((m) =>
      m[1]!.trim(),
    );
    expect(infinite).toEqual(['.badge[data-state="blocked"]::before']);
  });

  it("every one-shot animation runs under a second", () => {
    const durations = new Map(
      [...CSS.matchAll(/(--duration-[a-z]+):\s*([0-9.]+m?s);/g)].map((m) => [m[1]!, m[2]!]),
    );
    const found = [...CSS.matchAll(/animation:\s*([a-z-]+)\s+(var\((--[a-z-]+)\)|[0-9.]+m?s)/g)];
    expect(found.length).toBeGreaterThanOrEqual(5);
    for (const m of found) {
      const raw = m[3] === undefined ? m[2]! : durations.get(m[3])!;
      const ms = raw.endsWith("ms") ? Number(raw.slice(0, -2)) : Number(raw.slice(0, -1)) * 1000;
      if (m[1] !== "halo") expect(ms, `${m[1]}`).toBeLessThan(1000);
    }
  });
});

describe("text ships as written (files/00_STATE: Turkish casing; 07 checklist)", () => {
  it("no case transform, no ellipsis truncation, no break-all anywhere in the stylesheets", () => {
    expect(CSS).not.toMatch(/text-transform\s*:/);
    expect(CSS).not.toMatch(/text-overflow\s*:\s*ellipsis/);
    expect(CSS).not.toMatch(/word-break\s*:\s*break-all/);
  });

  it("near-miss: the scan sees a planted uppercase label", () => {
    expect(`${CSS}\n.x { text-transform: uppercase; }`).toMatch(/text-transform\s*:/);
  });
});

describe("the CSP stays whole", () => {
  it("no stylesheet reaches another origin or imports another sheet", () => {
    expect(CSS).not.toMatch(/@import/);
    expect(CSS).not.toMatch(/url\(/);
    expect(CSS).not.toMatch(/https?:/);
  });

  it("the layout imports only the console's own stylesheets", () => {
    const layout = readFileSync(join(APP, "layout.tsx"), "utf8");
    const imports = [...layout.matchAll(/^import\s+(?:[^"]+from\s+)?"([^"]+)";/gm)].map(
      (m) => m[1],
    );
    expect(imports.filter((i) => i!.endsWith(".css"))).toEqual(SHEETS.map((s) => `./${s}`));
    expect(imports.every((i) => i === "next" || i === "react" || i!.startsWith("./"))).toBe(true);
  });

  it("the production policy names no external origin and no unsafe source", () => {
    const csp = buildCsp("bm9uY2U=", "production");
    expect(csp).not.toMatch(/https?:|unsafe-|\*/);
    expect(csp).toContain("style-src 'self' 'nonce-bm9uY2U='");
  });
});
