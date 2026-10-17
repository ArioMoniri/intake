/**
 * INT-459 — the console's empty, loading and error states.
 *
 * - **Loading** has no route-level boundary. A `loading.tsx` was built (a
 *   static skeleton of the shell) and withdrawn: under it the page streams,
 *   and React parks a late chart segment in `<svg style="display:none">`,
 *   which the console's CSP (no `unsafe-inline` style) refuses. The spec keeps
 *   that from coming back, with the mechanism reproduced as its near-miss.
 *   While a page loads, the previous page stays up and the browser shows its
 *   own progress.
 * - **Not found** (`app/not-found.tsx`): an empty state with one way back.
 * - **Refused and unavailable** pages keep their markup (INT-181/351) and are
 *   laid out by the layer as a centred state view with a symbol.
 * - **Empty** — an unknown tile — keeps its word, its reason and no figure
 *   (invariant 17); the layer gives it an inset with a symbol.
 *
 * Every state passes axe; each property has its near-miss.
 */
import { readdirSync } from "node:fs";
import { join } from "node:path";
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

import NotFound from "../app/not-found";
import { OpsConsole } from "../src/ops/console";
import { NotFoundView } from "../src/ui/states";
import { documentFor, violations } from "./support/axe";
import { APP, nativeRules, selectorsOf } from "./support/css";

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

describe("loading: no route-level boundary, because the CSP refuses what it streams", () => {
  it("there is no app/loading.tsx (nor a loading file under any route)", () => {
    const loading = readdirSync(join(APP), { recursive: true }).filter((f) =>
      /(^|\/)loading\.(tsx|ts|jsx|js)$/.test(String(f)),
    );
    expect(loading).toEqual([]);
  });

  it("near-miss: a chart that streams in under a boundary arrives in a style attribute", async () => {
    // What a route-level loading.tsx did to the overview in production: the
    // page streams under the boundary, a chart's SVG finishes after its card,
    // and React parks the late segment in `<svg style="display:none">`, which
    // `style-src 'self' 'nonce-…'` blocks (INT-459 evidence, red run 3).
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
    const html = await streamed(
      createElement(
        "main",
        null,
        createElement(Suspense, { fallback: createElement("p", null, "…") }, createElement(Card)),
      ),
    );
    expect(html).toMatch(/<svg aria-hidden="true" style="display:none" id="S:\d+">/);
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
