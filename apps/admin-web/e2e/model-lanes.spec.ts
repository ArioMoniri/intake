/**
 * INT-428 — the Model lanes module, read side: admission, the tiles, what the
 * page says when something is unknown, and what the view-model refuses
 * (files/08 §3; ADR-035). The controls and the form handler are
 * `model-lanes.actions.spec.ts`; both run the page's own loader through an
 * injected `fetch` and render the page's own React tree to static markup.
 *
 * **The properties, each with a near-miss.** Admission is the API's gate; a
 * document of an unknown shape or one carrying a credential is refused whole;
 * unknown is a word and a code, never a number (invariant 17) — a price
 * nobody configured reads "price not configured", a self-hosted call "not
 * metered"; a hosted lane never serves a real-PHI deployment and "clinical
 * evidence" never comes from one; ids only (invariant 6); no target beside a
 * figure (invariant 20); numbers ungrouped (invariant 22).
 */
import { describe, expect, it } from "vitest";

import {
  ModelLanesIncoherent,
  ModelLanesSecretLeaked,
  ModelLanesShapeRefused,
  renderModelLanes,
  type ModelLanesPayload,
} from "../src/model-lanes/module";
import {
  NBSP,
  OpsLabelLeaked,
  OpsSchemaMismatch,
  OpsTargetRendered,
  OpsUnknownCarriesFigure,
} from "../src/ops/guards";
import {
  html,
  load,
  mismatched,
  page,
  payload,
  realPhi,
  storeDown,
  unconfigured,
  withKeySet,
  withUsage,
} from "./model-lanes.fixture";

function tileState(markup: string, tile: string): string | undefined {
  return new RegExp(`data-tile="${tile}"[^>]*data-tile-state="(ok|unknown)"`).exec(markup)?.[1];
}

const DELETE = Symbol("delete");

/** A deep copy with one value set (or deleted) at `path`, so a near-miss
 * differs from what it controls by exactly one property. */
function bent(path: (string | number)[], value: unknown, base = payload()): ModelLanesPayload {
  const doc = structuredClone(base) as unknown;
  let node = doc as Record<string | number, unknown>;
  for (const key of path.slice(0, -1)) node = node[key] as Record<string | number, unknown>;
  const last = path[path.length - 1]!;
  if (value === DELETE) delete node[last];
  else node[last] = value;
  return doc as ModelLanesPayload;
}

// ------------------------------------------------------------------ admission

describe("admission (the API's admin gate decides)", () => {
  it("admits nobody without a bearer and never dials the API", async () => {
    const { state, calls } = await load(payload(), null);
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(calls).toEqual([]);
    expect(html(state)).not.toContain("data-tile");
  });

  it("forwards the bearer once to GET /admin/model-lanes", async () => {
    const { state, calls } = await load(payload());
    expect(state.kind).toEqual("console");
    expect(calls.map((c) => [c.method, new URL(c.url).pathname, c.authorization])).toEqual([
      ["GET", "/admin/model-lanes", "Bearer kc:platform_owner"],
    ]);
  });

  it("a 403 from the gate is a refusal, not a page", async () => {
    const { state } = await load({ detail: { error: "role_not_permitted" } }, undefined, 403);
    expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
    expect(html(state)).not.toContain("<form");
  });

  it("a payload the view-model refuses is unavailable, never half-painted", async () => {
    const { state } = await load({ ...payload(), schema: "intake.admin.model_lanes.v0" });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
    expect(html(state)).toContain('data-unavailable="payload_refused"');
  });
});

// ------------------------------------------------------------------ the tiles

describe("the tiles — recorded from the shipped composite", () => {
  it("renders the deployment, every lane and role, the options and the providers", async () => {
    const markup = await page(payload());
    for (const tile of ["deployment", "lanes", "pending", "options_llm", "options_asr"]) {
      expect(tileState(markup, tile), tile).toEqual("ok");
    }
    expect(tileState(markup, "providers")).toEqual("ok");
    for (const role of ["llm", "asr", "tts", "llm.council.chair"]) {
      expect(markup).toContain(`data-role="${role}"`);
    }
    expect(markup).toContain('data-declared="synthetic"');
    expect(markup).toContain('data-hosted-lanes="true"');
  });

  it("shows the configured route and model beside what serves now, and why", () => {
    const view = renderModelLanes(payload());
    const llm = view.lanes.find((row) => row.role === "llm")!;
    expect(llm.setting).toEqual({
      route: "hosted:openai",
      model: "gpt-4o-mini",
      fallback: null,
      fallbackModel: null,
    });
    expect(llm.serving).toMatchObject({ available: false, reason: "hosted_egress_not_listed" });
    expect(llm.selfHosted.identity).toEqual("unreachable");
    expect(llm.selfHosted.expected).toMatchObject({
      modelId: "Qwen/Qwen3.6-35B-A3B",
      shortVersion: "995ad96e",
      shortPin: "f2a760a0526b",
    });
  });

  it("lists each lane's options: attested rows selectable, unattested rows not", () => {
    const llm = renderModelLanes(payload()).options.find((o) => o.lane === "llm")!;
    expect(llm.selfHosted.map((o) => [o.component, o.selectable])).toEqual([
      ["qwen3.6-35b-a3b", true],
      ["qwen3.5-9b", false],
    ]);
    expect(llm.hosted[0]).toMatchObject({
      provider: "openai",
      isDefault: true,
      probe: { state: "skipped", reason: "hosted_egress_not_listed" },
      qualified: false,
    });
    expect(llm.hosted[0]!.model).toMatchObject({ modelId: "gpt-4o-mini", version: "2024-07-18" });
  });

  it("renders in Turkish, the source of truth, with the console link", async () => {
    const markup = await page(payload(), "tr");
    expect(markup).toContain("Model hatları");
    expect(markup).toContain('lang="tr"');
    expect(markup).toContain('href="/cicd"');
    expect(markup).toContain('<span aria-current="page">Model hatları</span>');
  });

  it("no number is grouped (invariant 22)", async () => {
    expect(await page(withUsage())).not.toMatch(/\d,\d{3}\b/);
  });
});

// ------------------------------------------------------------------ unknown is a word

describe("unknown is a state, rendered as words and a code (invariant 17)", () => {
  it("with Prometheus unconfigured, latency and cost are unknown with the reason", async () => {
    const markup = await page(payload());
    expect(tileState(markup, "usage")).toEqual("unknown");
    expect(markup).toContain('data-reason="prometheus_unconfigured"');
  });

  it("a price nobody configured and a self-hosted call read as words, never zero", async () => {
    const markup = await page(withUsage());
    expect(tileState(markup, "usage")).toEqual("ok");
    const unpriced = /data-cost-state="price_not_configured">([^<]*)</.exec(markup)?.[1];
    expect(unpriced).toEqual("price not configured");
    const unmetered = /data-cost-state="not_metered">([^<]*)</.exec(markup)?.[1];
    expect(unmetered).toMatch(/^not metered/);
    expect(unpriced).not.toMatch(/\d/);
    // near miss: a priced row does show its figure, as a figure with its unit
    expect(markup).toContain(`data-cost-state="known">0.0123${NBSP}USD<`);
    expect(markup).toContain(`413${NBSP}ms`);
  });

  it("a latency nobody measured is the word, not a number", async () => {
    const view = renderModelLanes(withUsage());
    const local = view.lanes[0]!.usage!.find((u) => u.route === "self_hosted")!;
    expect(local).toMatchObject({ p50: null, p95: null, calls: null });
    const markup = await page(withUsage());
    expect(markup).toMatch(/data-usage="llm\/self_hosted">(?:(?!<\/tr>).)*Unknown/);
  });

  it("with nothing wired, the page says so and offers no control", async () => {
    const markup = await page(unconfigured());
    expect(tileState(markup, "deployment")).toEqual("unknown");
    expect(tileState(markup, "lanes")).toEqual("unknown");
    expect(markup).toContain('data-reason="model_lanes_unconfigured"');
    expect(markup).not.toContain("<form");
  });

  it("with the control store down, the revision and the settings are the word", async () => {
    const markup = await page(storeDown());
    expect(markup).toContain('data-control-state="unknown"');
    expect(markup).toContain("model_lanes_unreachable");
    expect(markup).toContain('data-hosted-disabled="null"');
    const view = renderModelLanes(storeDown());
    expect(view.control).toMatchObject({ state: "unknown", revision: null, hostedDisabled: null });
    expect(view.lanes.every((row) => row.setting === null)).toBe(true);
  });

  it("a provider key reads unconfigured, unknown or not set — or set with its last four", async () => {
    expect(await page(payload())).toContain('data-key-state="unconfigured"');
    const markup = await page(withKeySet());
    expect(markup).toContain('data-key-state="set"');
    expect(markup).toContain("set · …<code>Zq9x</code>");
  });
});

// ------------------------------------------------------------------ banners

describe("the deployment's data class is stated, and a banner says what it forbids", () => {
  it("a synthetic deployment with hosted lanes carries no banner", async () => {
    expect(await page(payload())).not.toContain("data-banner");
  });

  it("a real-PHI deployment says hosted lanes are not part of it", async () => {
    const markup = await page(realPhi());
    expect(markup).toContain('data-banner="no_hosted_lanes"');
    expect(markup).toContain('data-banner="real_phi"');
    expect(renderModelLanes(realPhi()).routes).toEqual(["self_hosted"]);
  });

  it("a data class bound stricter than the image declares is a banner", async () => {
    const markup = await page(mismatched());
    expect(markup).toContain('data-banner="data_class_mismatch"');
    expect(markup).toContain('data-banner="real_phi"');
    expect(markup).not.toContain('data-banner="no_hosted_lanes"');
  });
});

// ------------------------------------------------------------------ refusals

describe("what the view-model refuses rather than paints", () => {
  it("a document of another schema", () => {
    expect(() => renderModelLanes({ ...payload(), schema: "x" } as never)).toThrow(
      OpsSchemaMismatch,
    );
  });

  it("an unknown shape: a field the schema does not have, or one it is missing", () => {
    expect(() => renderModelLanes(bent(["extra"], true))).toThrow(ModelLanesShapeRefused);
    expect(() => renderModelLanes(bent(["lanes", 0, "serving", "qualified"], DELETE))).toThrow(
      ModelLanesShapeRefused,
    );
    expect(() => renderModelLanes(bent(["lanes", 0, "usage"], {}))).toThrow(ModelLanesShapeRefused);
    expect(() => renderModelLanes(payload())).not.toThrow();
  });

  it("a key-bearing field anywhere, or a value shaped like a key (near miss: last4)", () => {
    const named = bent(["providers", 0, "key", "api_key"], "redacted");
    expect(() => renderModelLanes(named)).toThrow(ModelLanesSecretLeaked);
    const top = bent(["providers", 0, "api_key"], "redacted");
    expect(() => renderModelLanes(top)).toThrow(ModelLanesSecretLeaked);
    const shaped = bent(["lanes", 0, "setting", "model"], `sk-${"a".repeat(24)}`);
    expect(() => renderModelLanes(shaped)).toThrow(ModelLanesSecretLeaked);
    const extra = bent(["providers", 0, "key", "value"], "redacted");
    expect(() => renderModelLanes(extra)).toThrow(ModelLanesShapeRefused);
    expect(() => renderModelLanes(withKeySet())).not.toThrow();
  });

  it("a mock route, or any route outside the closed set", () => {
    for (const route of ["mock", "hosted:anthropic", "hosted"]) {
      const doc = bent(["lanes", 1, "setting", "route"], route);
      expect(() => renderModelLanes(doc), route).toThrow(OpsLabelLeaked);
    }
  });

  it("a hosted lane serving a real-PHI deployment", () => {
    const hostedServing = {
      available: true,
      reason: "configured",
      provider: "openai",
      route: "hosted:openai",
      fallback: false,
      model: payload().models.llm!.hosted[0]!.model,
      qualified: false,
      clinical_evidence: false,
    };
    const synthetic = bent(["lanes", 0, "serving"], hostedServing);
    expect(() => renderModelLanes(synthetic)).not.toThrow();
    const phi = bent(["lanes", 0, "serving"], hostedServing, mismatched());
    expect(() => renderModelLanes(phi)).toThrow(ModelLanesIncoherent);
  });

  it("clinical evidence from anything but a qualified self-hosted model on PHI", () => {
    const expected = payload().lanes[0]!.self_hosted.expected;
    const serving = {
      available: true,
      reason: "configured",
      provider: "self_hosted",
      route: "self_hosted",
      fallback: false,
      model: expected,
      qualified: true,
      clinical_evidence: true,
    };
    const onPhi = bent(["lanes", 0, "serving"], serving, realPhi());
    expect(() => renderModelLanes(onPhi)).not.toThrow();
    const onSynthetic = bent(["lanes", 0, "serving"], serving);
    expect(() => renderModelLanes(onSynthetic)).toThrow(ModelLanesIncoherent);
    const unqualified = bent(["lanes", 0, "serving"], { ...serving, qualified: false }, realPhi());
    expect(() => renderModelLanes(unqualified)).toThrow(ModelLanesIncoherent);
  });

  it("a hosted provider that is self-hostable or on the PHI path (invariant 19)", () => {
    expect(() => renderModelLanes(bent(["providers", 0, "phi_path"], true))).toThrow(
      ModelLanesIncoherent,
    );
    expect(() => renderModelLanes(bent(["providers", 0, "self_hostable"], true))).toThrow(
      ModelLanesIncoherent,
    );
  });

  it("hosted options or providers in a deployment without hosted lanes", () => {
    const options = bent(["models", "llm", "hosted"], payload().models.llm!.hosted, realPhi());
    expect(() => renderModelLanes(options)).toThrow(ModelLanesIncoherent);
    const providers = bent(["providers"], payload().providers, realPhi());
    expect(() => renderModelLanes(providers)).toThrow(ModelLanesIncoherent);
    expect(() => renderModelLanes(realPhi())).not.toThrow();
  });

  it("a figure beside an unknown: an unpriced cost, an unset key, an unmeasured window", () => {
    const priced = bent(["lanes", 0, "usage", 0, "cost", "usd"], 0, withUsage());
    expect(() => renderModelLanes(priced)).toThrow(OpsUnknownCarriesFigure);
    const unset = bent(["providers", 0, "key", "last4"], "Zq9x");
    expect(() => renderModelLanes(unset)).toThrow(OpsUnknownCarriesFigure);
    const blind = bent(["usage_reason"], "prometheus_unconfigured", withUsage());
    expect(() => renderModelLanes(blind)).toThrow(OpsUnknownCarriesFigure);
  });

  it("a self-hosted model without its pin (invariant 14)", () => {
    const unpinned = bent(["models", "llm", "self_hosted", 0, "model", "sha256"], null);
    expect(() => renderModelLanes(unpinned)).toThrow(ModelLanesIncoherent);
  });

  it("a label that is not id-shaped, or a ceremony this module does not open", () => {
    const named = bent(["models", "llm", "self_hosted", 0, "component"], "Ayşe's GPU");
    expect(() => renderModelLanes(named)).toThrow(OpsLabelLeaked);
    const foreign = bent(
      ["pending"],
      [
        {
          action_id: "pa-0002",
          dangerous_action_id: "admin.cicd.freeze.lift",
          tier: 2,
          state: "pending",
          expires_at: "2026-10-02T00:15:00+00:00",
          approver_role: null,
        },
      ],
    );
    expect(() => renderModelLanes(foreign)).toThrow(OpsLabelLeaked);
  });

  it("a target beside a figure (invariant 20)", () => {
    const doc = bent(["lanes", 0, "p95_target"], "800 ms");
    expect(() => renderModelLanes(doc)).toThrow(OpsTargetRendered);
  });
});
