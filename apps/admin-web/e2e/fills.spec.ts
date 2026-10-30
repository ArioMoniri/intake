/**
 * INT-459 refresh — the designed empty places (`src/ui/fills.ts`,
 * `src/ui/unknown.tsx`).
 *
 * - **An unknown tile is calm and says what fills it.** The word, the cause in
 *   plain language, the one condition that makes it read (an environment
 *   variable or a path set in monospace), and the reason code last, in
 *   monospace and muted. Still no figure (invariant 17).
 * - **Every reason a tile can show has its line**, in tr (the source of
 *   truth, invariant 5) and en; no line names a target (invariant 20).
 * - **An empty table keeps its header and says what puts a row there.**
 *
 * Each property has its near-miss beside it.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { createElement, type ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AccessConsole } from "../src/access/console";
import { renderAccessReview, type AccessReviewPayload } from "../src/access/module";
import { CicdConsole } from "../src/cicd/console";
import { COPY as CICD } from "../src/cicd/copy";
import { renderCicd, type CicdPayload } from "../src/cicd/module";
import { ModelLanesConsole } from "../src/model-lanes/console";
import { COPY as LANES } from "../src/model-lanes/copy";
import { renderModelLanes, type ModelLanesPayload } from "../src/model-lanes/module";
import { OpsConsole } from "../src/ops/console";
import { COPY as OPS } from "../src/ops/copy";
import { renderOps, type OpsPayload } from "../src/ops/module";
import { Tile } from "../src/ops/tiles";
import { OverviewConsole } from "../src/overview/console";
import { COPY as OVERVIEW } from "../src/overview/copy";
import { renderOverview, type ReliabilityPayload } from "../src/overview/module";
import { EMPTIES, FILLS, type EmptyKind } from "../src/ui/fills";
import { VoiceConsole } from "../src/voice/console";
import { COPY as VOICE } from "../src/voice/copy";
import { renderVoice, type VoicePayload } from "../src/voice/module";
import { withUsage } from "./model-lanes.fixture";
import { nativeRules } from "./support/css";

const FIXTURES = join(__dirname, "fixtures");

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

function dom(tree: ReactElement): Document {
  return new JSDOM(renderToStaticMarkup(tree)).window.document;
}

const text = (el: Element | null): string => (el?.textContent ?? "").replace(/\s+/g, " ").trim();

function health() {
  const h = read<Record<string, { status: number; body: unknown }>>("ops.health.json");
  return {
    healthz: { ok: true as const, ...h["healthz"]! },
    readyz: { ok: true as const, ...h["readyz"]! },
    version: { ok: true as const, ...h["version"]! },
  };
}

function readyz() {
  const api = read<Record<string, { status: number; body: unknown }>>("overview.api.json");
  return { ok: true as const, ...api["readyz"]! };
}

/** Every page as the synthetic host renders it today: nothing wired. */
function hostLike(lang: "tr" | "en"): Record<string, Document> {
  const admitted = { kind: "console" as const };
  return {
    overview: dom(
      createElement(OverviewConsole, {
        state: {
          ...admitted,
          view: renderOverview(
            read<ReliabilityPayload>("reliability.unconfigured.payload.json"),
            readyz(),
          ),
        },
        lang,
      }),
    ),
    ops: dom(
      createElement(OpsConsole, {
        state: {
          ...admitted,
          view: renderOps(read<OpsPayload>("ops.unconfigured.payload.json"), health()),
        },
        lang,
      }),
    ),
    voice: dom(
      createElement(VoiceConsole, {
        state: {
          ...admitted,
          view: renderVoice(read<VoicePayload>("voice.unconfigured.payload.json")),
        },
        lang,
        result: null,
      }),
    ),
    cicd: dom(
      createElement(CicdConsole, {
        state: {
          ...admitted,
          view: renderCicd(read<CicdPayload>("cicd.unconfigured.payload.json")),
        },
        lang,
        result: null,
      }),
    ),
    lanes: dom(
      createElement(ModelLanesConsole, {
        state: {
          ...admitted,
          view: renderModelLanes(read<ModelLanesPayload>("model-lanes.payload.json")),
        },
        lang,
        result: null,
      }),
    ),
  };
}

describe("an unknown tile is calm and says what fills it", () => {
  const c = OVERVIEW.en;
  const doc = dom(
    createElement(Tile, {
      id: "probe",
      title: "Prometheus",
      state: "unknown",
      reason: "prometheus_unconfigured",
      c,
    }),
  );
  const note = doc.querySelector(".unknown[data-reason='prometheus_unconfigured']");

  it("says the word and the cause on its first line", () => {
    expect(text(note!.querySelector(".unknown-head strong"))).toBe("Unknown");
    expect(text(note!.querySelector(".unknown-cause"))).toBe("Prometheus URL not configured");
  });

  it("names what fills it, the variable in monospace", () => {
    const fill = note!.querySelector(".unknown-fill");
    expect(text(fill)).toBe(
      "Shows here once INTAKE_OPS_PROMETHEUS_URL gives the API a Prometheus address.",
    );
    expect(text(fill!.querySelector("code"))).toBe("INTAKE_OPS_PROMETHEUS_URL");
  });

  it("keeps the reason code last, in monospace", () => {
    const code = note!.lastElementChild!;
    expect(code.matches("code.unknown-code")).toBe(true);
    expect(text(code)).toBe("prometheus_unconfigured");
  });

  it("still carries no figure (invariant 17)", () => {
    expect(doc.querySelector("[data-tile='probe']")!.getAttribute("data-tile-state")).toBe(
      "unknown",
    );
    expect(text(doc.body)).not.toMatch(/\d+(\.\d+)?\s?%/);
  });

  it("near-miss: a reason with no line keeps the cause and the code, and no empty fill", () => {
    const bare = dom(
      createElement(Tile, { id: "x", title: "x", state: "unknown", reason: "brand_new", c }),
    );
    expect(bare.querySelector(".unknown-fill")).toBeNull();
    expect(text(bare.querySelector(".unknown-code"))).toBe("brand_new");
  });

  it("the layer draws the unknown card calm: a dashed edge, no shadow", () => {
    const calm = nativeRules().find((r) => r.selector === ".tile-unknown" && !r.at.length);
    expect(calm?.decls["border-style"]).toBe("dashed");
    expect(calm?.decls["box-shadow"]).toBe("none");
  });
});

describe("every reason a tile can show has its line, in tr and en", () => {
  const tileReasons = [OPS, OVERVIEW, VOICE, CICD].flatMap((copy) => Object.keys(copy.tr.reasons));
  const laneReasons = Object.keys(LANES.tr.reasons).filter((r) =>
    /^(model_lanes_|prometheus_|no_series$|label_not_id_shaped$|unexpected_label$)/.test(r),
  );

  it("each page's tile reasons, and the model-lane source reasons", () => {
    for (const reason of new Set([...tileReasons, ...laneReasons])) {
      expect(FILLS.tr[reason as keyof typeof FILLS.tr], `tr ${reason}`).toBeTruthy();
      expect(FILLS.en[reason as keyof typeof FILLS.en], `en ${reason}`).toBeTruthy();
    }
  });

  it("every unknown note on the synthetic host's pages carries one", () => {
    for (const lang of ["tr", "en"] as const) {
      for (const [page, doc] of Object.entries(hostLike(lang))) {
        const notes = [...doc.querySelectorAll(".unknown[data-reason]")];
        expect(notes.length, page).toBeGreaterThan(0);
        for (const note of notes)
          expect(
            note.querySelector(".unknown-fill"),
            `${page} ${note.getAttribute("data-reason")}`,
          ).not.toBeNull();
      }
    }
  });

  it("en mirrors tr key for key, and no line names a target (invariant 20)", () => {
    expect(Object.keys(FILLS.en).sort()).toEqual(Object.keys(FILLS.tr).sort());
    for (const line of [...Object.values(FILLS.tr), ...Object.values(FILLS.en)])
      expect(line).not.toMatch(/hedef|target|goal|%/i);
  });
});

/** Render a page whose view has one table emptied, and find its empty row. */
function emptied(tree: ReactElement, kind: EmptyKind, lang: "tr" | "en"): Element | null {
  const row = dom(tree).querySelector(`tr.empty-row [data-empty="${kind}"]`);
  if (row !== null) {
    expect(text(row.querySelector(".empty-title"))).toBe(EMPTIES[lang][kind].title);
  }
  return row;
}

describe("an empty table keeps its header and says what puts a row there", () => {
  const lang = "en" as const;
  const overview = renderOverview(read<ReliabilityPayload>("reliability.payload.json"), readyz());
  const ops = renderOps(read<OpsPayload>("ops.payload.json"), health());
  const voice = renderVoice(read<VoicePayload>("voice.payload.json"));
  const cicd = renderCicd(read<CicdPayload>("cicd.payload.json"));
  const lanes = renderModelLanes(withUsage());
  const access = renderAccessReview(read<AccessReviewPayload>("access.payload.json"), "days");
  const d = overview.dependencies;
  const t = ops.tiles;

  const cases: [EmptyKind, ReactElement][] = [
    [
      "probes",
      createElement(OverviewConsole, {
        state: {
          kind: "console",
          view: { ...overview, probeMatrix: { ...overview.probeMatrix, rows: [] } },
        },
        lang,
      }),
    ],
    [
      "components",
      createElement(OverviewConsole, {
        state: {
          kind: "console",
          view: { ...overview, dependencies: { ...d, components: { ...d.components, rows: [] } } },
        },
        lang,
      }),
    ],
    [
      "vendors",
      createElement(OverviewConsole, {
        state: {
          kind: "console",
          view: { ...overview, dependencies: { ...d, vendors: { ...d.vendors, rows: [] } } },
        },
        lang,
      }),
    ],
    [
      "readiness",
      createElement(OverviewConsole, {
        state: {
          kind: "console",
          view: {
            ...overview,
            dependencies: { ...d, apiReadiness: { ...d.apiReadiness, checks: [] } },
          },
        },
        lang,
      }),
    ],
    [
      "models",
      createElement(OpsConsole, {
        state: {
          kind: "console",
          view: { ...ops, tiles: { ...t, models: { ...t.models, rows: [] } } },
        },
        lang,
      }),
    ],
    [
      "gpuHosts",
      createElement(OpsConsole, {
        state: { kind: "console", view: { ...ops, tiles: { ...t, gpu: { ...t.gpu, hosts: [] } } } },
        lang,
      }),
    ],
    [
      "modelUsage",
      createElement(OpsConsole, {
        state: {
          kind: "console",
          view: { ...ops, tiles: { ...t, modelUsage: { ...t.modelUsage, lanes: [] } } },
        },
        lang,
      }),
    ],
    [
      "workflows",
      createElement(OpsConsole, {
        state: {
          kind: "console",
          view: { ...ops, tiles: { ...t, cicd: { ...t.cicd, workflows: [] } } },
        },
        lang,
      }),
    ],
    [
      "sessions",
      createElement(VoiceConsole, {
        state: { kind: "console", view: { ...voice, sessions: { ...voice.sessions, rows: [] } } },
        lang,
        result: null,
      }),
    ],
    [
      "turns",
      createElement(VoiceConsole, {
        state: {
          kind: "console",
          view: {
            ...voice,
            turnLatency: { ...voice.turnLatency, state: "ok", reason: null, rows: [] },
          },
        },
        lang,
        result: null,
      }),
    ],
    [
      "speech",
      createElement(VoiceConsole, {
        state: {
          kind: "console",
          view: { ...voice, speechErrors: { ...voice.speechErrors, rows: [] } },
        },
        lang,
        result: null,
      }),
    ],
    [
      "failovers",
      createElement(VoiceConsole, {
        state: { kind: "console", view: { ...voice, failovers: { ...voice.failovers, rows: [] } } },
        lang,
        result: null,
      }),
    ],
    [
      "breakers",
      createElement(VoiceConsole, {
        state: { kind: "console", view: { ...voice, breakers: { ...voice.breakers, rows: [] } } },
        lang,
        result: null,
      }),
    ],
    [
      "tenants",
      createElement(VoiceConsole, {
        state: {
          kind: "console",
          view: { ...voice, controls: { ...voice.controls, tenants: [] } },
        },
        lang,
        result: null,
      }),
    ],
    [
      "pending",
      createElement(VoiceConsole, {
        state: { kind: "console", view: { ...voice, pending: { ...voice.pending, actions: [] } } },
        lang,
        result: null,
      }),
    ],
    [
      "runs",
      createElement(CicdConsole, {
        state: {
          kind: "console",
          view: {
            ...cicd,
            pipelines: {
              ...cicd.pipelines,
              workflows: cicd.pipelines.workflows.map((w) => ({ ...w, runs: [] })),
            },
          },
        },
        lang,
        result: null,
      }),
    ],
    [
      "refs",
      createElement(CicdConsole, {
        state: { kind: "console", view: { ...cicd, gates: { ...cicd.gates, refs: [] } } },
        lang,
        result: null,
      }),
    ],
    [
      "deployments",
      createElement(CicdConsole, {
        state: {
          kind: "console",
          view: { ...cicd, deployments: { ...cicd.deployments, rows: [] } },
        },
        lang,
        result: null,
      }),
    ],
    [
      "holders",
      createElement(AccessConsole, {
        state: { kind: "console", view: { ...access, holders: [] } },
        lang,
      }),
    ],
  ];

  for (const [kind, tree] of cases) {
    it(`${kind}: one empty row under the kept header, with what fills it`, () => {
      const row = emptied(tree, kind, lang);
      expect(row, kind).not.toBeNull();
      expect(text(row!.querySelector(".empty-why"))).toBe(
        EMPTIES[lang][kind].why.replace(/`/g, ""),
      );
      const table = row!.closest("table")!;
      expect(table.querySelectorAll("thead th").length).toBeGreaterThan(1);
      const cell = row!.closest("td")!;
      expect(Number(cell.getAttribute("colspan"))).toBe(table.querySelectorAll("thead th").length);
    });
  }

  it("model lanes: no call in the window is an empty state with what fills it", () => {
    const quiet = { ...lanes, lanes: lanes.lanes.map((l) => ({ ...l, usage: [] })) };
    const doc = dom(
      createElement(ModelLanesConsole, {
        state: { kind: "console", view: quiet },
        lang,
        result: null,
      }),
    );
    const tile = doc.querySelector("[data-tile='usage']")!;
    expect(tile.getAttribute("data-tile-state")).toBe("ok");
    expect(text(tile.querySelector("[data-empty='laneCalls'] .empty-title"))).toBe(
      EMPTIES[lang].laneCalls.title,
    );
  });

  it("near-miss: a table with rows draws no empty row", () => {
    expect(
      emptied(
        createElement(OpsConsole, { state: { kind: "console", view: ops }, lang }),
        "models",
        lang,
      ),
    ).toBeNull();
  });

  it("en mirrors tr key for key", () => {
    expect(Object.keys(EMPTIES.en).sort()).toEqual(Object.keys(EMPTIES.tr).sort());
  });
});
