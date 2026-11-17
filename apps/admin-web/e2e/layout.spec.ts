/**
 * INT-459 refresh — the console's layout over the shell (`app/native-layout.css`).
 *
 * - **A dense twelve-column grid at desktop width.** From 1024 px a band's
 *   grid has twelve columns and packs densely; at 1280 px and up (the owner's
 *   1440 px screen) a card spans four, a card holding a table six, a calm
 *   unknown card three, and the wide tiles the whole row (half when unknown).
 *   Eight unread SLOs fill two rows with no hole.
 * - **Cells wrap; they never clip.** console.css keeps `white-space: nowrap`
 *   on cells (the audit's console.css:186); the layout lets them wrap, and an
 *   id in a cell may break anywhere, so a narrow card shows the whole value.
 *   Nothing breaks a Turkish word mid-word.
 * - **Sticky table headers.** A table scrolls inside its card past 40rem, and
 *   its header row stays in view.
 *
 * Each property has its near-miss beside it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CicdConsole } from "../src/cicd/console";
import { renderCicd, type CicdPayload } from "../src/cicd/module";
import { OverviewConsole } from "../src/overview/console";
import { renderOverview, type ReliabilityPayload } from "../src/overview/module";
import { allRules, rulesOf, selectorsOf, type Rule } from "./support/css";

const LAYOUT = rulesOf("native-layout.css");
const DESK = "@media (min-width: 1024px)";
const WIDE = "@media (min-width: 1280px)";

function rule(selector: string, at: string[] = []): Record<string, string> {
  const found = LAYOUT.find(
    (r) => selectorsOf(r).includes(selector) && r.at.join("|") === at.join("|"),
  );
  expect(found, `${selector} ${at.join(" ")}`).toBeDefined();
  return found!.decls;
}

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(__dirname, "fixtures", name), "utf8")) as T;
}

function dom(tree: ReactElement): Document {
  return new JSDOM(renderToStaticMarkup(tree)).window.document;
}

/** The span a card takes at 1280 px and up, by the layer's own precedence
 * (each later entry is more specific than the one before it). */
const SPANS_AT_WIDE: [string, number][] = [
  [".grid > *", 4],
  [".grid > .tile:has(table)", 6],
  [".grid > .tile-unknown", 3],
];

function spanAtWide(card: Element, spans: [string, number][] = SPANS_AT_WIDE): number {
  const wide = rule(".grid > .tile.tile-wide", [WIDE])["grid-column"];
  const wideUnknown = rule(".grid > .tile.tile-wide.tile-unknown", [WIDE])["grid-column"];
  if (card.matches(".tile-wide.tile-unknown")) return Number(/span (\d+)/.exec(wideUnknown!)![1]);
  if (card.matches(".tile-wide")) return wide === "1 / -1" ? 12 : 0;
  let span = 0;
  for (const [selector, n] of spans) {
    expect(rule(selector, [WIDE])["grid-column"], selector).toBe(`span ${n}`);
    if (card.matches(selector.replace(".grid > ", ""))) span = n;
  }
  return span;
}

/** A selector's specificity as one number (ids, classes, types; `:has()`
 * counts its argument, CSS Selectors 4), enough for the layer's selectors. */
function specificity(selector: string): number {
  const inner = [...selector.matchAll(/:has\(([^)]*)\)/g)].map((m) => m[1]!).join(" ");
  const outer = selector.replace(/:has\([^)]*\)/g, "");
  const count = (s: string, re: RegExp): number => (s.match(re) ?? []).length;
  const all = `${outer} ${inner}`;
  const ids = count(all, /#[\w-]+/g);
  const classes = count(all, /\.[\w-]+|\[[^\]]+\]|:(?!has)[\w-]+/g);
  const types = count(all.replace(/[.#][\w-]+|\[[^\]]+\]|:[\w-]+/g, ""), /\b[a-z][\w-]*/g);
  return ids * 10000 + classes * 100 + types;
}

function band(doc: Document, id: string): Element[] {
  return [...doc.querySelectorAll(`section[aria-labelledby="${id}"] > .grid > *`)];
}

function overview(file: string): Document {
  const api = read<Record<string, { status: number; body: unknown }>>("overview.api.json");
  const view = renderOverview(read<ReliabilityPayload>(file), { ok: true, ...api["readyz"]! });
  return dom(createElement(OverviewConsole, { state: { kind: "console", view }, lang: "en" }));
}

describe("a dense twelve-column grid at desktop width", () => {
  it("from 1024 px a band's grid has twelve columns and packs densely", () => {
    const grid = rule(".grid", [DESK]);
    expect(grid["grid-template-columns"]).toBe("repeat(12, minmax(0, 1fr))");
    expect(grid["grid-auto-flow"]).toBe("row dense");
  });

  it("at 1280 px a card spans 4, a table card 6, a calm unknown card 3, a wide tile the row", () => {
    expect(rule(".grid > *", [WIDE])["grid-column"]).toBe("span 4");
    expect(rule(".grid > .tile:has(table)", [WIDE])["grid-column"]).toBe("span 6");
    expect(rule(".grid > .tile-unknown", [WIDE])["grid-column"]).toBe("span 3");
    expect(rule(".grid > .tile.tile-wide", [WIDE])["grid-column"]).toBe("1 / -1");
    expect(rule(".grid > .tile.tile-wide.tile-unknown", [WIDE])["grid-column"]).toBe("span 6");
    expect(rule(".grid > .tile.tile-wide.tile-unknown:only-child", [WIDE])["grid-column"]).toBe(
      "1 / -1",
    );
  });

  it("a wide tile that holds a table still takes the whole row (it out-ranks the table rule)", () => {
    expect(specificity(".grid > .tile.tile-wide")).toBeGreaterThan(
      specificity(".grid > .tile:has(table)"),
    );
  });

  it("near-miss: the first draft's `.grid > .tile-wide` lost to the table rule", () => {
    expect(specificity(".grid > .tile-wide")).toBeLessThan(specificity(".grid > .tile:has(table)"));
  });

  it("eight unread SLOs fill exactly two rows of the band", () => {
    const cards = band(overview("reliability.unconfigured.payload.json"), "band-slos");
    expect(cards.length).toBe(8);
    expect(cards.map((card) => spanAtWide(card)).reduce((a, b) => a + b, 0)).toBe(24);
  });

  it("two unread wide tiles share one row (CI/CD runs and gates on the synthetic host)", () => {
    const payload = read<CicdPayload>("cicd.unconfigured.payload.json");
    const doc = dom(
      createElement(CicdConsole, {
        state: { kind: "console", view: renderCicd(payload) },
        lang: "en",
        result: null,
      }),
    );
    expect(band(doc, "band-ci").map((card) => spanAtWide(card))).toEqual([6, 6]);
  });

  it("near-miss: without the calm span, the same eight cards leave a hole in the last row", () => {
    const cards = band(overview("reliability.unconfigured.payload.json"), "band-slos");
    const withoutCalm = SPANS_AT_WIDE.filter(([s]) => s !== ".grid > .tile-unknown");
    const total = cards.map((card) => spanAtWide(card, withoutCalm)).reduce((a, b) => a + b, 0);
    expect(total % 12).not.toBe(0);
  });
});

/** The last rule in cascade order that sets `prop` on exactly `selector`. */
function last(rules: Rule[], selector: string, prop: string): string | undefined {
  return rules
    .filter((r) => r.at.length === 0 && selectorsOf(r).includes(selector))
    .map((r) => r.decls[prop])
    .filter((v): v is string => v !== undefined)
    .at(-1);
}

describe("cells wrap; they never clip", () => {
  it("near-miss: console.css still sets nowrap on every cell", () => {
    expect(last(rulesOf("console.css"), "td", "white-space")).toBe("nowrap");
  });

  it("the layout lets every header and cell wrap", () => {
    expect(last(allRules(), "th", "white-space")).toBe("normal");
    expect(last(allRules(), "td", "white-space")).toBe("normal");
  });

  it("an id in a cell, a fact or a note may break anywhere; prose may not", () => {
    for (const selector of ["td code", "th code", ".facts code", ".unknown code"]) {
      expect(last(allRules(), selector, "overflow-wrap"), selector).toBe("anywhere");
    }
    expect(last(allRules(), "td", "overflow-wrap")).toBeUndefined();
  });
});

describe("sticky table headers", () => {
  it("a table scrolls inside its card past 40rem", () => {
    const box = rule(".scroll");
    expect(box["max-height"]).toBe("40rem");
    expect(box["overflow"]).toBe("auto");
  });

  it("its header row stays in view, on the card's own fill", () => {
    const head = rule("thead th");
    expect(head["position"]).toBe("sticky");
    expect(head["top"]).toBe("0");
    expect(head["background"]).toBe("var(--surface)");
    expect(Number(head["z-index"])).toBeGreaterThan(0);
  });
});
