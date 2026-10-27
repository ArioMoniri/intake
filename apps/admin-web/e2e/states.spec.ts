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
 * - **Refused and unavailable** pages keep the console's shell (INT-569): the
 *   sidebar with this page marked current and the page's title, and the
 *   notice with its next step in a centred state view with a symbol. The
 *   audit found five of six pages rendered a dead end with no navigation.
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
import { AccessConsole } from "../src/access/console";
import { CicdConsole } from "../src/cicd/console";
import { ModelLanesConsole } from "../src/model-lanes/console";
import { OpsConsole } from "../src/ops/console";
import { CONSOLE_PAGES } from "../src/ops/nav";
import { OverviewConsole } from "../src/overview/console";
import { NotFoundView } from "../src/ui/states";
import { VoiceConsole } from "../src/voice/console";
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

/** Every console page in its refused and its unavailable state (INT-569). */
function refusedPages(lang: "tr" | "en"): Record<string, ReactElement> {
  const refused = { kind: "not_admitted" as const, reason: "no_credentials" as const };
  const down = { kind: "unavailable" as const, reason: "api_unreachable" as const };
  return {
    "overview refused": createElement(OverviewConsole, { state: refused, lang }),
    "overview unavailable": createElement(OverviewConsole, { state: down, lang }),
    "ops refused": createElement(OpsConsole, { state: refused, lang }),
    "ops unavailable": createElement(OpsConsole, { state: down, lang }),
    "voice refused": createElement(VoiceConsole, { state: refused, lang, result: null }),
    "voice unavailable": createElement(VoiceConsole, { state: down, lang, result: null }),
    "cicd refused": createElement(CicdConsole, { state: refused, lang, result: null }),
    "cicd unavailable": createElement(CicdConsole, { state: down, lang, result: null }),
    "model-lanes refused": createElement(ModelLanesConsole, {
      state: refused,
      lang,
      result: null,
    }),
    "model-lanes unavailable": createElement(ModelLanesConsole, {
      state: down,
      lang,
      result: null,
    }),
    "access refused": createElement(AccessConsole, { state: refused, lang }),
    "access unavailable": createElement(AccessConsole, { state: down, lang }),
  };
}

describe("refused and unavailable pages keep the console's shell (INT-569)", () => {
  for (const [name, tree] of Object.entries(refusedPages("tr"))) {
    const page = name.split(" ")[0]!;
    const doc = new JSDOM(renderToStaticMarkup(tree)).window.document;

    it(`${name}: the sidebar is there, with this page marked current`, () => {
      const nav = doc.querySelector("header.page-head > nav.console-nav");
      expect(nav).not.toBeNull();
      expect(nav!.querySelectorAll("[data-page-link]").length).toBe(CONSOLE_PAGES.length);
      expect(nav!.querySelector(`[aria-current="page"][data-page-link="${page}"]`)).not.toBeNull();
      expect(doc.querySelector(`main[data-page="${page}"] > header.page-head > h1`)).not.toBeNull();
    });

    it(`${name}: the notice and its next step sit in a centred state view`, () => {
      const view = doc.querySelector("main > .state-view");
      expect(view).not.toBeNull();
      expect(
        view!.querySelector(".refusal[data-refusal], .refusal[data-unavailable]"),
      ).not.toBeNull();
      expect(view!.querySelector(".next-step[data-next-step]")).not.toBeNull();
    });
  }

  it("the state view is centred in the content area, and its notice carries a symbol", () => {
    const view = ruleFor(".state-view");
    expect(view["place-content"]).toBe("center");
    expect(view["min-height"]).toMatch(/dvh|vh/);
    expect(ruleFor(".refusal::before")["content"]).toMatch(/^"!"/);
    expect(ruleFor(".state-view > .refusal::before")["left"]).toMatch(/50%/);
  });

  it("every refused and unavailable page passes axe, in both languages", async () => {
    for (const lang of ["tr", "en"] as const) {
      for (const [name, tree] of Object.entries(refusedPages(lang))) {
        expect(await violations(documentFor(tree, lang)), `${name} ${lang}`).toEqual([]);
      }
    }
  });

  it("near-miss: a console page has no state view, and the old dead end is gone", () => {
    const admitted = new JSDOM(
      `<main class="ops" data-page="ops"><header class="page-head"></header><div class="grid"></div></main>`,
    ).window.document;
    expect(admitted.querySelector(".state-view")).toBeNull();
    const dead = new JSDOM(
      `<main class="ops" data-page="ops"><h1>x</h1><p class="refusal" data-refusal="no_credentials">x</p></main>`,
    ).window.document;
    expect(dead.querySelector("nav.console-nav")).toBeNull();
    expect(NATIVE.some((r) => selectorsOf(r).includes(".ops:not(:has(> .page-head))"))).toBe(false);
  });
});

describe("an unknown tile is an inset empty state, still without a figure", () => {
  it("the layer gives the unknown notice an inset and a symbol", () => {
    const inset = ruleFor(".unknown");
    expect(inset["background"]).toBe("var(--surface-2)");
    expect(ruleFor(".unknown::before")["content"]).toMatch(/^"\?"/);
  });
});
