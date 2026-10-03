/**
 * INT-459 — the console's empty, loading and error states.
 *
 * - **Loading** (`app/loading.tsx`): a static skeleton of the shell,
 *   announced as busy in tr and en, with no figure. Under it every page
 *   streams, and React parks a late SVG segment (a chart that finishes after
 *   its card) in `<svg aria-hidden="true" style="display:none">` until its
 *   script moves it into place. The CSP admits exactly that one attribute
 *   value by its hash (owner decision, 3 Oct 2026). The spec derives the value
 *   from React's own streamed markup and from the renderer Next.js ships, and
 *   pins the hash path; its near-misses show every other inline style, and a
 *   `<style>` element with the same text, still refused.
 * - **Not found** (`app/not-found.tsx`): an empty state with one way back.
 * - **Refused and unavailable** pages keep their markup (INT-181/351) and are
 *   laid out by the layer as a centred state view with a symbol.
 * - **Empty** — an unknown tile — keeps its word, its reason and no figure
 *   (invariant 17); the layer gives it an inset with a symbol.
 *
 * Every state passes axe; each property has its near-miss.
 */
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { PassThrough } from "node:stream";
import { JSDOM } from "jsdom";
import { createElement, Suspense, use, type ReactElement } from "react";
import { renderToPipeableStream, renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

/** `connection()` outside a request: record the call instead. */
const connections = vi.hoisted((): string[] => []);
vi.mock("next/server", () => ({
  connection: async (): Promise<void> => {
    connections.push("connection");
  },
}));

import Loading from "../app/loading";
import NotFound from "../app/not-found";
import { OpsConsole } from "../src/ops/console";
import { buildCsp } from "../src/ops/csp";
import { LoadingView, NotFoundView } from "../src/ui/states";
import { documentFor, violations } from "./support/axe";
import { nativeRules, selectorsOf } from "./support/css";
import {
  admitsStyleAttribute,
  admitsStyleElement,
  directivesOf,
  hashSource,
  unsafeSources,
} from "./support/csp";

const NATIVE = nativeRules();

function ruleFor(selector: string): Record<string, string> {
  const rule = NATIVE.find((r) => r.at.length === 0 && selectorsOf(r).includes(selector));
  expect(rule, selector).toBeDefined();
  return rule!.decls;
}

/** Stream a tree the way the App Router streams a page under a Suspense
 * boundary, and return every byte. */
function streamed(tree: ReactElement): Promise<string> {
  return new Promise((resolve, reject) => {
    const sink = new PassThrough();
    let html = "";
    sink.on("data", (chunk: Buffer) => (html += chunk.toString("utf8")));
    sink.on("end", () => resolve(html));
    const stream = renderToPipeableStream(tree, {
      onShellReady: () => stream.pipe(sink),
      onShellError: reject,
    });
  });
}

function later<T>(value: T, ms: number): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

/** What a route-level loading.tsx does to the overview: the page streams
 * under the boundary, a chart's SVG finishes after its card, and React parks
 * the late segment in a hidden `<svg>` until its script moves it into place
 * (INT-459 evidence, red run 3). */
function lateChartSegment(): Promise<string> {
  const card = later("card", 5);
  const bars = later("bars", 30);
  function Bars(): ReactElement {
    use(bars);
    return createElement("rect", { className: "bar", width: 2, height: 8 });
  }
  function Card(): ReactElement {
    use(card);
    return createElement(
      "svg",
      { role: "img", "aria-label": "x" },
      createElement("g", null, "key"),
      createElement(Bars),
    );
  }
  return streamed(
    createElement(
      "main",
      null,
      createElement(Suspense, { fallback: createElement("p", null, "…") }, createElement(Card)),
    ),
  );
}

/** Every distinct inline style attribute value in a stretch of markup. */
function styleAttributes(html: string): string[] {
  return [...new Set([...html.matchAll(/\sstyle="([^"]*)"/g)].map((m) => m[1]!))].sort();
}

/** The fixed style values (a `property:value` between the quotes) in the
 * renderer Next.js runs for App Router pages in production, webpack and
 * Turbopack builds. The bundles' only other `style="` is the open quote for a
 * `style` prop, and the console sets none (asserted per page elsewhere). */
function shippedSegmentStyles(): string[] {
  const next = dirname(createRequire(import.meta.url).resolve("next/package.json"));
  const found = new Set<string>();
  for (const bundle of ["app-page.runtime.prod.js", "app-page-turbo.runtime.prod.js"]) {
    const source = readFileSync(join(next, "dist", "compiled", "next-server", bundle), "utf8");
    for (const m of source.matchAll(/style="([a-z-]+:[^"'\\]+)"/g)) found.add(m[1]!);
  }
  return [...found].sort();
}

const NONCE = "bm9uY2U=";
const POLICY = buildCsp(NONCE, "production");

describe("loading: a skeleton of the shell, busy in both languages", () => {
  const html = renderToStaticMarkup(createElement(LoadingView));

  it("app/loading.tsx renders the skeleton view", () => {
    expect(renderToStaticMarkup(Loading())).toBe(html);
  });

  it("is one main region, marked busy, that says so in tr and en", () => {
    expect(html).toMatch(/^<main[^>]*class="ops"[^>]*aria-busy="true"/);
    expect(html).toMatch(/<h1[^>]*>Yükleniyor<\/h1>/);
    expect(html).toMatch(/role="status"/);
    expect(html).toMatch(/lang="en"[^>]*>Loading/);
  });

  it("shows no figure, no link and no style attribute", () => {
    const text = new JSDOM(html).window.document.body.textContent ?? "";
    expect(text).not.toMatch(/\d/);
    expect(html).not.toContain("<a ");
    expect(html).not.toMatch(/\sstyle=/);
  });

  it("its skeleton is decoration, hidden from assistive technology", () => {
    const doc = new JSDOM(html).window.document;
    const bones = [...doc.querySelectorAll(".bone")];
    expect(bones.length).toBeGreaterThan(0);
    for (const bone of bones) expect(bone.closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it("passes axe", async () => {
    expect(await violations(documentFor(createElement(LoadingView), "tr"))).toEqual([]);
  });
});

describe("loading: the CSP admits React's streamed segment style by its hash, and nothing else", () => {
  it("React parks a late chart segment in a style attribute; the policy admits exactly that value", async () => {
    const streamedStyles = styleAttributes(await lateChartSegment());
    expect(streamedStyles.length).toBe(1);
    for (const value of streamedStyles) expect(admitsStyleAttribute(POLICY, value)).toBe(true);
    expect(directivesOf(POLICY).get("style-src-attr")).toEqual([
      "'unsafe-hashes'",
      ...streamedStyles.map(hashSource),
    ]);
  });

  it("the renderer Next.js ships parks segments in the same one value", async () => {
    expect(shippedSegmentStyles()).toEqual(styleAttributes(await lateChartSegment()));
  });

  it("the only unsafe keyword is 'unsafe-hashes', and only for style attributes", () => {
    expect(unsafeSources(POLICY)).toEqual(["style-src-attr 'unsafe-hashes'"]);
    expect(POLICY).not.toMatch(/unsafe-inline/);
    expect(directivesOf(POLICY).get("style-src")).toEqual(["'self'", `'nonce-${NONCE}'`]);
    expect(directivesOf(buildCsp(NONCE, "development")).get("style-src-attr")).toEqual(
      directivesOf(POLICY).get("style-src-attr"),
    );
  });

  it("near-miss: any other inline style is still refused", async () => {
    const [admitted] = styleAttributes(await lateChartSegment());
    const others = [
      "color:red",
      "display:block",
      `${admitted!};`,
      ` ${admitted!}`,
      admitted!.toUpperCase(),
      admitted!.replace(":", ": "),
      `${admitted!}!important`,
    ];
    for (const value of others) expect(admitsStyleAttribute(POLICY, value), value).toBe(false);
  });

  it("near-miss: the hash admits the attribute only; a <style> with the same text is refused", async () => {
    const [admitted] = styleAttributes(await lateChartSegment());
    expect(admitsStyleElement(POLICY, `svg{${admitted!}}`)).toBe(false);
    expect(admitsStyleElement(POLICY, admitted!)).toBe(false);
    expect(admitsStyleElement(POLICY, `svg{${admitted!}}`, NONCE)).toBe(true);
  });

  it("near-miss: without 'unsafe-hashes' a browser ignores the hash for an attribute", async () => {
    const [admitted] = styleAttributes(await lateChartSegment());
    const withoutKeyword = POLICY.replace("'unsafe-hashes' ", "");
    expect(withoutKeyword).not.toBe(POLICY);
    expect(admitsStyleAttribute(withoutKeyword, admitted!)).toBe(false);
  });
});

describe("not found: an empty state with one way back", () => {
  const html = renderToStaticMarkup(createElement(NotFoundView));

  it("the route file renders the view, per request (so its scripts get the nonce)", async () => {
    connections.length = 0;
    expect(renderToStaticMarkup(await NotFound())).toBe(html);
    expect(connections).toEqual(["connection"]);
  });

  it("says so in tr and en and links to the overview only", () => {
    expect(html).toMatch(/<h1[^>]*>Sayfa bulunamadı<\/h1>/);
    expect(html).toMatch(/lang="en"[^>]*>Page not found/);
    expect([...html.matchAll(/href="([^"]+)"/g)].map((m) => m[1])).toEqual(["/overview"]);
  });

  it("its symbol is decoration", () => {
    expect(html).toMatch(/<svg[^>]*aria-hidden="true"[^>]*focusable="false"/);
  });

  it("passes axe", async () => {
    expect(await violations(documentFor(createElement(NotFoundView), "tr"))).toEqual([]);
  });
});

describe("refused and unavailable pages read as a centred state view", () => {
  it("a page with no header (a refusal) is centred, and its notice carries a symbol", () => {
    const page = ruleFor(".ops:not(:has(> .page-head))");
    expect(page["place-content"]).toBe("center");
    expect(page["min-height"]).toMatch(/dvh|vh/);
    expect(ruleFor(".refusal::before")["content"]).toMatch(/^"!"/);
  });

  it("the refusal markup itself is unchanged: a heading and the reason, no navigation", () => {
    const html = renderToStaticMarkup(
      createElement(OpsConsole, {
        state: { kind: "not_admitted", reason: "no_credentials" },
        lang: "tr",
      }),
    );
    expect(html).toMatch(/^<main[^>]*class="ops"[^>]*><h1>/);
    expect(html).toContain('data-refusal="no_credentials"');
    expect(html).not.toContain("<nav");
  });

  it("near-miss: an admitted page, which has a header, is not laid out as a state view", () => {
    const refused = renderToStaticMarkup(
      createElement(OpsConsole, {
        state: { kind: "unavailable", reason: "api_unreachable" },
        lang: "en",
      }),
    );
    const doc = new JSDOM(
      `<body>${refused}<main class="ops"><header class="page-head"></header></main></body>`,
    ).window.document;
    const centred = [...doc.querySelectorAll(".ops:not(:has(> .page-head))")];
    expect(centred.length).toBe(1);
    expect(centred[0]!.querySelector("[data-unavailable]")).not.toBeNull();
  });
});

describe("an unknown tile is an inset empty state, still without a figure", () => {
  it("the layer gives the unknown notice an inset and a symbol", () => {
    const inset = ruleFor(".unknown");
    expect(inset["background"]).toBe("var(--surface-2)");
    expect(ruleFor(".unknown::before")["content"]).toMatch(/^"\?"/);
  });
});
