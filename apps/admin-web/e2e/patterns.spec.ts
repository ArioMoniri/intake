/**
 * INT-459 follow-up — the patterns mined from the owner's libraries, on the
 * console's own pages.
 *
 * Ported from MIT sources (licence hashes in docs/evidence/INT-459.md §9):
 * - **Astryx `Skeleton`**: the loading bones take a `--skeleton` token, wait a
 *   second, then pulse in a staggered wave. They deepen toward the ink under
 *   increased contrast, and paint GrayText at full opacity under forced
 *   colours.
 * - **beUI `SkeletonRows`**: the skeleton table. A figure's column gets a
 *   short right-aligned bar, and a text column gets two thirds.
 * - **Astryx `referenceLine`**: each SLO's burn rates are drawn against their
 *   alert threshold.
 * - **Astryx `ChartLegend` / `ChartSwatch`** and **EvilCharts' area fade**:
 *   the CI/CD run chart gets a legend and a trend line per workflow.
 *
 * Rebuilt from scratch (ideas only; Kobra and Reverse UI are proprietary,
 * Kinetics has no licence, Transitions.dev has its own):
 * - the overview's component status strip;
 * - the CI/CD runs grouped by workflow, folding into cards on a narrow
 *   screen;
 * - empty states and refusals that say why, and what to do next.
 *
 * Not built: the "KPI goal line". A target beside a figure turns a
 * measurement into a claim (invariant 20), so the console prints none.
 *
 * Every property has its near-miss; every page state passes axe.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AccessConsole } from "../src/access/console";
import { COPY as ACCESS_COPY } from "../src/access/copy";
import { renderAccessReview, type AccessReviewPayload } from "../src/access/module";
import { CicdConsole } from "../src/cicd/console";
import { COPY as CICD_COPY } from "../src/cicd/copy";
import { renderCicd, type CicdPayload, type CicdView } from "../src/cicd/module";
import { OpsConsole } from "../src/ops/console";
import type { RefusedState } from "../src/ops/load";
import { OverviewConsole } from "../src/overview/console";
import { COPY as OVERVIEW_COPY } from "../src/overview/copy";
import { renderOverview, type OverviewView, type ReliabilityPayload } from "../src/overview/module";
import { NEXT_STEPS } from "../src/ui/next-steps";
import { LoadingView } from "../src/ui/states";
import { VoiceConsole } from "../src/voice/console";
import { documentFor, violations } from "./support/axe";
import { nativeRules, selectorsOf, type Rule } from "./support/css";

const FIXTURES = join(__dirname, "fixtures");
const NATIVE = nativeRules();
const DARK = "@media (prefers-color-scheme: dark)";

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

function dom(tree: ReactElement): Document {
  return new JSDOM(renderToStaticMarkup(tree)).window.document;
}

function rule(selector: string, at: readonly string[] = []): Record<string, string> {
  const found = NATIVE.find(
    (r: Rule) => selectorsOf(r).includes(selector) && r.at.join("|") === at.join("|"),
  );
  expect(found, `${selector} ${at.join(" ")}`).toBeDefined();
  return found!.decls;
}

function overviewView(): OverviewView {
  const api = read<Record<string, { status: number; body: unknown }>>("overview.api.json");
  return renderOverview(read<ReliabilityPayload>("reliability.payload.json"), {
    ok: true,
    ...api["readyz"]!,
  });
}

function overview(view: OverviewView, lang: "tr" | "en" = "tr"): ReactElement {
  return createElement(OverviewConsole, { state: { kind: "console", view }, lang });
}

function cicdView(): CicdView {
  return renderCicd(read<CicdPayload>("cicd.payload.json"));
}

function cicd(view: CicdView, lang: "tr" | "en" = "tr"): ReactElement {
  return createElement(CicdConsole, { state: { kind: "console", view }, lang, result: null });
}

const text = (el: Element | null): string => (el?.textContent ?? "").replace(/\s+/g, " ").trim();

// --- loading: Astryx's skeleton, beUI's skeleton rows -----------------------

describe("loading: the bones follow Astryx's skeleton", () => {
  const light = rule(":root");
  const dark = rule(":root", [DARK]);

  it("paint a --skeleton token that both themes define", () => {
    expect(light["--skeleton"]).toMatch(/^#[0-9a-f]{6}$/i);
    expect(dark["--skeleton"]).toMatch(/^#[0-9a-f]{6}$/i);
    expect(dark["--skeleton"]).not.toBe(light["--skeleton"]);
    expect(rule(".bone")["background"]).toBe("var(--skeleton)");
  });

  it("wait a second before pulsing, then pulse in a staggered wave of at most five steps", () => {
    expect(rule(".bone")["animation-delay"]).toBe("1000ms");
    const steps = NATIVE.filter((r) => /^\.bone:nth-child\(\d+\)$/.test(r.selector));
    expect(steps.map((r) => r.decls["animation-delay"])).toEqual([
      "1100ms",
      "1200ms",
      "1300ms",
      "1400ms",
    ]);
  });

  it("deepen toward the ink under increased contrast", () => {
    expect(rule(".bone", ["@media (prefers-contrast: more)"])["background"]).toBe(
      "color-mix(in srgb, var(--skeleton), var(--ink) 30%)",
    );
  });

  it("paint GrayText at full opacity under forced colours", () => {
    const forced = rule(".bone", ["@media (forced-colors: active)"]);
    expect(forced["background"]).toBe("GrayText");
    expect(forced["opacity"]).toBe("1");
  });

  it("stand still, and stay visible, under reduced motion (near-miss: the resting opacity is faint)", () => {
    const resting = Number(rule(".bone")["opacity"]);
    const still = Number(rule(".bone", ["@media (prefers-reduced-motion: reduce)"])["opacity"]);
    expect(resting).toBeLessThan(0.5);
    expect(still).toBeGreaterThanOrEqual(0.6);
  });
});

describe("loading: the skeleton table follows beUI's SkeletonRows", () => {
  const doc = dom(createElement(LoadingView));
  const table = doc.querySelector("table.skeleton-table");

  it("is decoration, inside the hidden skeleton", () => {
    expect(table).not.toBeNull();
    expect(table!.closest('[aria-hidden="true"]')).not.toBeNull();
  });

  it("has five rows: two thirds of a bar per text column, a short bar ending a figure's", () => {
    const rows = [...table!.querySelectorAll("tbody tr")];
    expect(rows).toHaveLength(5);
    for (const row of rows) {
      const cells = [...row.querySelectorAll("td")];
      expect(cells.length).toBeGreaterThanOrEqual(3);
      expect(cells.slice(0, -1).every((td) => td.querySelector(".bone-text"))).toBe(true);
      expect(cells.at(-1)!.querySelector(".bone-num")).not.toBeNull();
    }
    expect(rule(".bone-text")["width"]).toBe("66%");
    expect(rule(".bone-num")["margin-inline-start"]).toBe("auto");
  });
});

// --- overview: the component status strip ----------------------------------

describe("overview: one status cell per component, and a count by health", () => {
  const view = overviewView();
  const c = OVERVIEW_COPY.tr;

  it("lists every component in table order, each with its name and health word", () => {
    const doc = dom(overview(view));
    const cells = [...doc.querySelectorAll("ul.status-strip > li")];
    const rows = view.dependencies.components.rows;
    expect(doc.querySelector("ul.status-strip")!.getAttribute("aria-label")).toBe(c.deps.strip);
    expect(cells).toHaveLength(rows.length);
    cells.forEach((cell, i) => {
      expect(text(cell)).toContain(rows[i]!.component);
      expect(text(cell)).toContain(c.health[rows[i]!.health] ?? rows[i]!.health);
      expect(cell.querySelector(".status-cell")!.getAttribute("aria-hidden")).toBe("true");
    });
  });

  it("counts by each health word the table prints, readings first, with no verdict", () => {
    const rows = view.dependencies.components.rows;
    const words = [...new Set(["healthy", "degraded", "unhealthy", ...rows.map((r) => r.health)])];
    const expected = words
      .map((h) => [h, rows.filter((r) => r.health === h).length] as const)
      .filter(([, n]) => n > 0)
      .map(([h, n]) => `${n} ${c.health[h] ?? h}`)
      .join(" · ");
    const summary = text(dom(overview(view)).querySelector(".status-summary"));
    expect(summary).toBe(expected);
    expect(summary).not.toMatch(/tüm|hepsi|hedef|iyi|kötü/i);
  });

  it("a component with no reading is an outlined cell, counted under its own word (near-miss)", () => {
    const known = ["healthy", "degraded", "unhealthy"];
    const bent: OverviewView = structuredClone(view);
    expect(known).toContain(bent.dependencies.components.rows[0]!.health);
    bent.dependencies.components.rows[0]!.health = "no_result";
    const before = view.dependencies.components.rows.filter((r) => r.health === "no_result");
    const doc = dom(overview(bent));
    const first = doc.querySelector("ul.status-strip > li")!;
    expect(first.getAttribute("data-health")).toBe("unread");
    expect(text(first)).toContain(c.health["no_result"]);
    expect(text(doc.querySelector(".status-summary"))).toContain(
      `${before.length + 1} ${c.health["no_result"]}`,
    );
    expect(rule('.status-cell[data-health="unread"]')["background"]).toBe("none");
    expect(rule('.status-cell[data-health="degraded"]')["background"]).toMatch(
      /^repeating-linear-gradient\(/,
    );
  });

  it("an unknown components tile draws no strip (invariant 17)", () => {
    const bent: OverviewView = structuredClone(view);
    bent.dependencies.components = { state: "unknown", reason: "no_series", rows: [] };
    expect(dom(overview(bent)).querySelector(".status-strip")).toBeNull();
  });
});

// --- overview: burn rate against its threshold ---------------------------

describe("overview: each SLO's burn rates are drawn against their alert threshold", () => {
  const view = overviewView();

  it("one marked row per lane and window, the threshold named in the image", () => {
    const doc = dom(overview(view));
    for (const t of view.slos.tiles.filter((s) => s.state === "ok" && s.lanes.length > 0)) {
      const chart = doc.querySelector(`[data-chart="burn-${t.key}"]`);
      expect(chart, t.key).not.toBeNull();
      expect(chart!.querySelectorAll(".bar-row")).toHaveLength(t.lanes.length * 2);
      expect(chart!.querySelectorAll("line.bar-mark")).toHaveLength(t.lanes.length * 2);
      expect(chart!.getAttribute("aria-label")).toContain(OVERVIEW_COPY.tr.slo.thresholdWord);
    }
  });

  it("near-miss: an unknown SLO tile draws no chart, and nothing is toned as a verdict", () => {
    const doc = dom(overview(view));
    for (const t of view.slos.tiles.filter((s) => s.state === "unknown")) {
      expect(doc.querySelector(`[data-chart="burn-${t.key}"]`)).toBeNull();
    }
    const tones = [...doc.querySelectorAll('[data-chart^="burn-"] .bar-row')].map((r) =>
      r.getAttribute("data-tone"),
    );
    expect(new Set(tones)).toEqual(new Set(["data"]));
  });
});

// --- CI/CD: runs grouped by workflow, folding on a narrow card ---------------

describe("CI/CD: the runs are grouped by workflow and fold into cards when narrow", () => {
  const view = cicdView();
  const c = CICD_COPY.tr;
  const doc = dom(cicd(view));
  const table = doc.querySelector('[data-tile="pipelines"] .fold table');

  it("one row group per workflow, headed by its name, its run count and its conclusions", () => {
    const groups = [...table!.querySelectorAll("tbody[data-group]")];
    const workflows = view.pipelines.workflows.filter((w) => w.runs.length > 0);
    expect(groups.map((g) => g.getAttribute("data-group"))).toEqual(
      workflows.map((w) => w.workflow),
    );
    groups.forEach((group, i) => {
      const w = workflows[i]!;
      const head = group.querySelector("tr.group-head > th[scope='rowgroup']");
      expect(head).not.toBeNull();
      expect(text(head)).toContain(w.workflow);
      expect(text(head)).toContain(`${w.runs.length} ${c.groups.runs}`);
      for (const code of new Set(w.runs.map((r) => r.conclusion))) {
        const n = w.runs.filter((r) => r.conclusion === code).length;
        expect(text(head)).toContain(`${n} ${code}`);
      }
    });
  });

  it("every run cell carries its column's name, for the folded card", () => {
    const headers = [...table!.querySelectorAll("thead th")].map(text);
    for (const row of table!.querySelectorAll("tbody tr:not(.group-head)")) {
      const labels = [...row.querySelectorAll("td")].map((td) => td.getAttribute("data-label"));
      expect(labels).toEqual(headers);
    }
  });

  it("folds below 40rem of card: the label precedes each value and the header is only hidden visually", () => {
    const fold = "@container (max-width: 40rem)";
    expect(rule(".fold")["container-type"]).toBe("inline-size");
    expect(rule(".fold td::before", [fold])["content"]).toBe('attr(data-label) / ""');
    const thead = rule(".fold thead", [fold]);
    expect(thead["display"]).toBeUndefined();
    expect(thead["clip-path"]).toBe("inset(50%)");
  });

  it("near-miss: only the runs table folds", () => {
    expect(doc.querySelectorAll(".fold")).toHaveLength(1);
  });

  it("a legend names each conclusion's colour, and a trend line runs per workflow, oldest first", () => {
    const legend = doc.querySelector('[data-tile="pipelines"] ul.legend');
    const codes = [
      ...new Set(view.pipelines.workflows.flatMap((w) => w.runs.map((r) => r.conclusion))),
    ];
    expect([...legend!.querySelectorAll("li")].map(text).sort()).toEqual(
      [...codes, c.charts.trend].sort(),
    );
    for (const w of view.pipelines.workflows.filter((x) => x.runs.length > 1)) {
      const spark = doc.querySelector(`[data-chart="trend-${w.workflow}"]`);
      expect(spark, w.workflow).not.toBeNull();
      const oldest = w.runs.at(-1)!.runNumber;
      expect(spark!.getAttribute("aria-label")).toMatch(new RegExp(`: #${oldest} `));
    }
  });
});

// --- empty states and refusals that say why ------------------------------

describe("an empty list says why it is empty", () => {
  const c = CICD_COPY.tr;

  it("no release yet: an inset state with its reason, not a bare word", () => {
    const view = cicdView();
    view.releases = { ...view.releases, rows: [] };
    const empty = dom(cicd(view)).querySelector('[data-tile="releases"] .empty');
    expect(empty!.getAttribute("data-empty")).toBe("releases");
    expect(text(empty)).toBe(`${c.empty.releases.title} ${c.empty.releases.why}`);
  });

  it("no pending request: one row across the table that says what would appear", () => {
    const view = cicdView();
    view.pending = { ...view.pending, actions: [] };
    const doc = dom(cicd(view));
    const headers = doc.querySelectorAll('[data-tile="pending"] thead th').length;
    const row = doc.querySelector('[data-tile="pending"] tbody tr.empty-row');
    expect(row!.querySelector("td")!.getAttribute("colspan")).toBe(String(headers));
    expect(text(row)).toBe(`${c.empty.pending.title} ${c.empty.pending.why}`);
  });

  it("near-miss: a list with rows shows no empty state", () => {
    expect(dom(cicd(cicdView())).querySelector(".empty")).toBeNull();
  });

  it("no open offboarding: the access review says what would appear", () => {
    const view = renderAccessReview(read<AccessReviewPayload>("access.payload.json"), "gün");
    const o = ACCESS_COPY.tr.offboardings;
    const doc = dom(
      createElement(AccessConsole, {
        state: { kind: "console", view: { ...view, offboardings: [] } },
        lang: "tr",
      }),
    );
    const empty = doc.querySelector('[data-tile="offboardings"] .empty');
    expect(text(empty)).toBe(`${o.none} ${o.noneWhy}`);
  });
});

const REFUSED: RefusedState[] = [
  { kind: "not_admitted", reason: "no_credentials" },
  { kind: "not_admitted", reason: "token_refused" },
  { kind: "not_admitted", reason: "role_not_permitted" },
  { kind: "not_admitted", reason: "source_ip_refused" },
  { kind: "not_admitted", reason: "console_unconfigured" },
  { kind: "unavailable", reason: "api_base_unconfigured" },
  { kind: "unavailable", reason: "api_unreachable" },
  { kind: "unavailable", reason: "payload_refused" },
];

function refusedPages(state: RefusedState, lang: "tr" | "en"): Record<string, ReactElement> {
  return {
    ops: createElement(OpsConsole, { state, lang }),
    overview: createElement(OverviewConsole, { state, lang }),
    voice: createElement(VoiceConsole, { state, lang, result: null }),
    cicd: createElement(CicdConsole, { state, lang, result: null }),
    access: createElement(AccessConsole, { state, lang }),
  };
}

describe("a refusal says why, and what to do next", () => {
  it("every page, every reason, both languages: the next step follows the reason", () => {
    for (const lang of ["tr", "en"] as const) {
      for (const state of REFUSED) {
        for (const [page, tree] of Object.entries(refusedPages(state, lang))) {
          const doc = dom(tree);
          const next = doc.querySelector(".next-step");
          expect(next, `${page} ${state.reason}`).not.toBeNull();
          expect(next!.getAttribute("data-next-step")).toBe(state.reason);
          expect(text(next)).toContain(NEXT_STEPS[lang].reasons[state.reason]);
          expect(next!.previousElementSibling!.classList.contains("refusal")).toBe(true);
        }
      }
    }
  });

  it("an unreachable API offers one retry link to the same page, in the same language", () => {
    const state: RefusedState = { kind: "unavailable", reason: "api_unreachable" };
    for (const [page, tree] of Object.entries(refusedPages(state, "en"))) {
      const links = [...dom(tree).querySelectorAll(".next-step a")];
      expect(links.map((a) => a.getAttribute("href"))).toEqual([`/${page}?lang=en`]);
      expect(text(links[0]!)).toBe(NEXT_STEPS.en.retry);
    }
  });

  it("near-miss: a refusal of the caller offers no retry, because retrying cannot help", () => {
    const state: RefusedState = { kind: "not_admitted", reason: "role_not_permitted" };
    for (const tree of Object.values(refusedPages(state, "tr"))) {
      expect(dom(tree).querySelectorAll(".next-step a")).toHaveLength(0);
    }
  });

  it("tr is the source: every reason has both languages, and they differ", () => {
    const reasons = REFUSED.map((s) => s.reason);
    for (const r of reasons) {
      expect(NEXT_STEPS.tr.reasons[r]).toBeTruthy();
      expect(NEXT_STEPS.en.reasons[r]).toBeTruthy();
      expect(NEXT_STEPS.tr.reasons[r]).not.toBe(NEXT_STEPS.en.reasons[r]);
    }
  });
});

describe("the new states pass axe", () => {
  // One page per test: each axe run takes a second or two in jsdom.
  it("an empty CI/CD page (grouped runs, legend, trend, empty states)", async () => {
    const view = cicdView();
    view.pending = { ...view.pending, actions: [] };
    view.releases = { ...view.releases, rows: [] };
    expect(await violations(documentFor(cicd(view), "tr"))).toEqual([]);
  });

  it("a refusal with its next step", async () => {
    const tree = createElement(OpsConsole, { state: REFUSED[2]!, lang: "tr" });
    expect(await violations(documentFor(tree, "tr"))).toEqual([]);
  });

  it("an unreachable API with its retry link", async () => {
    const tree = createElement(OverviewConsole, { state: REFUSED[6]!, lang: "en" });
    expect(await violations(documentFor(tree, "en"))).toEqual([]);
  });

  it("the overview with its status strip and burn charts", async () => {
    expect(await violations(documentFor(overview(overviewView(), "en"), "en"))).toEqual([]);
  });
});
