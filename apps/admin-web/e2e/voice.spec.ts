/**
 * INT-182 — the Voice module: per-profile metrics, the kill switch, the profile
 * switch and canary weights (files/08 §3 "Voice runtime", §8.2).
 *
 * **What this runs against.** `voice.payload.json` and
 * `voice.unconfigured.payload.json` are recordings, in tests only, made by
 * `scripts/dev/record_voice_fixture.py` with the shipped composite
 * (`intake_api.admin.voice_console`) — `tests/admin/test_voice_console.py`
 * fails if they drift from it. The spec drives the page's own server-side
 * loader through an injected `fetch`, renders the page's own React tree to
 * static markup, and drives the form handler's own planner.
 *
 * **The properties, each with a near-miss.** Admission is the API's gate;
 * every tile fails closed to unknown on its own; only the two profiles that
 * exist are painted or offered (CLAUDE.md invariant 19); a canary weight is an
 * integer 0..100; a tenant shown on voice while its kill switch is engaged is
 * refused, not painted; the kill switch is one key and every move toward voice
 * is a request for a second; nothing leaves a form without the page's own
 * origin and the caller's bearer; ids only (invariant 6); no target beside a
 * figure (invariant 20).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { opsConfigFromEnv } from "../src/ops/access";
import { NBSP } from "../src/ops/guards";
import type { FetchLike } from "../src/ops/load";
import {
  OpsLabelLeaked,
  OpsSchemaMismatch,
  OpsTargetRendered,
  OpsUnknownCarriesFigure,
} from "../src/ops/module";
import { planVoiceAction, submitVoiceAction, type ResultCode } from "../src/voice/actions";
import { VoiceConsole } from "../src/voice/console";
import { loadVoice, resultFrom, type VoiceState } from "../src/voice/load";
import {
  VoiceControlIncoherent,
  VoiceProfileOutsideSet,
  VoiceWeightOutOfBounds,
  renderVoice,
  type VoicePayload,
} from "../src/voice/module";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";

function read<T>(name: string): T {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as T;
}

const payload = (): VoicePayload => read<VoicePayload>("voice.payload.json");
const unconfigured = (): VoicePayload => read<VoicePayload>("voice.unconfigured.payload.json");

interface Recorded {
  status: number;
  body: unknown;
}

interface Call {
  url: string;
  method: string;
  authorization: string | null;
  body: unknown;
}

function recordedFetch(routes: Record<string, Recorded | "network_error">): {
  fetch: FetchLike;
  calls: Call[];
} {
  const calls: Call[] = [];
  const fetch: FetchLike = async (url, init) => {
    const headers = new Headers(init?.headers);
    calls.push({
      url,
      method: init?.method ?? "GET",
      authorization: headers.get("authorization"),
      body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null,
    });
    const answer = routes[new URL(url).pathname];
    if (answer === undefined || answer === "network_error") throw new TypeError("fetch failed");
    return new Response(JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, calls };
}

async function load(
  body: unknown,
  authorization: string | null = "Bearer kc:sre_oncall",
  status = 200,
): Promise<{ state: VoiceState; calls: Call[] }> {
  const { fetch, calls } = recordedFetch({ "/admin/voice": { status, body } });
  const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
  return { state: await loadVoice({ config, authorization, fetch }), calls };
}

function html(
  state: VoiceState,
  lang: "tr" | "en" = "en",
  result: ResultCode | null = null,
): string {
  return renderToStaticMarkup(createElement(VoiceConsole, { state, lang, result }));
}

async function page(body: VoicePayload, lang: "tr" | "en" = "en"): Promise<string> {
  const { state } = await load(body);
  expect(state.kind).toEqual("console");
  return html(state, lang);
}

function tileState(markup: string, tile: string): string | undefined {
  return new RegExp(`data-tile="${tile}"[^>]*data-tile-state="(ok|unknown)"`).exec(markup)?.[1];
}

type Tiles = VoicePayload["tiles"];

function withTile<K extends keyof Tiles>(
  key: K,
  patch: (tile: Tiles[K]) => Tiles[K],
  base = payload(),
): VoicePayload {
  return { ...base, tiles: { ...base.tiles, [key]: patch(base.tiles[key]) } };
}

const PROM_TILES = [
  "sessions",
  "kill_switch_activity",
  "turn_latency",
  "speech_errors",
  "failovers",
  "breakers",
] as const;

// ------------------------------------------------------------------ admission

describe("admission (the API's admin gate decides; HB-A16 fails closed)", () => {
  it("admits nobody without a bearer and never dials the API", async () => {
    const { state, calls } = await load(payload(), null);
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(calls).toEqual([]);
    expect(html(state)).not.toContain("data-tile");
  });

  it("forwards the bearer once to GET /admin/voice", async () => {
    const { state, calls } = await load(payload());
    expect(state.kind).toEqual("console");
    expect(calls.map((c) => [c.method, new URL(c.url).pathname, c.authorization])).toEqual([
      ["GET", "/admin/voice", "Bearer kc:sre_oncall"],
    ]);
  });

  it("a 403 from the gate is a refusal, not a page", async () => {
    const { state } = await load({ detail: { error: "role_not_permitted" } }, undefined, 403);
    expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
    expect(html(state)).not.toContain("<form");
  });

  it("a payload the view-model refuses is unavailable, never half-painted", async () => {
    const { state } = await load({ ...payload(), schema: "intake.admin.voice.v0" });
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

// ------------------------------------------------------------------ the tiles

describe("per-profile tiles — each fails closed on its own", () => {
  it("renders every tile, and latency with no emitter as unknown, not zero", async () => {
    const markup = await page(payload());
    for (const tile of ["controls", "pending", ...PROM_TILES]) {
      expect(tileState(markup, tile), tile).toBeDefined();
    }
    expect(tileState(markup, "sessions")).toEqual("ok");
    expect(tileState(markup, "breakers")).toEqual("ok");
    expect(tileState(markup, "turn_latency")).toEqual("unknown");
    expect(markup).toContain('data-reason="no_series"');
  });

  it("paints sessions per profile and route reason", () => {
    const view = renderVoice(payload());
    expect(view.sessions.rows).toContainEqual({
      profile: "typed",
      reason: "kill_switch",
      sessions: "58",
    });
    expect(new Set(view.sessions.rows.map((r) => r.profile))).toEqual(
      new Set(["residency_tr", "typed"]),
    );
  });

  it("paints speech errors as a ratio next to the counts it came from, no grouping", async () => {
    const view = renderVoice(payload());
    const tts = view.speechErrors.rows.find((r) => r.component === "voxcpm2-tts")!;
    expect(tts).toEqual({
      component: "voxcpm2-tts",
      kind: "tts",
      calls: "5161",
      failures: "41",
      errorRatio: `0.79${NBSP}%`,
    });
    const markup = await page(payload());
    expect(markup).toContain("5161");
    expect(markup).not.toContain("5,161");
    expect(markup).not.toContain("5.161");
  });

  it("paints INT-100's breakers and failovers by registry component", () => {
    const view = renderVoice(payload());
    expect(view.breakers.rows).toEqual([
      { component: "freya-tts", state: "half_open" },
      { component: "voxcpm2-tts", state: "closed" },
    ]);
    expect(view.failovers.rows).toContainEqual({ from: "freya-tts", to: "typed", count: "2" });
  });

  it("with nothing configured, every tile is unknown with its reason and no figure", async () => {
    const markup = await page(unconfigured());
    for (const tile of PROM_TILES) expect(tileState(markup, tile), tile).toEqual("unknown");
    expect(tileState(markup, "controls")).toEqual("unknown");
    expect(markup).toContain('data-reason="prometheus_unconfigured"');
    expect(markup).toContain('data-reason="voice_control_unconfigured"');
  });
});

// ------------------------------------------------------------------ the refusals

describe("what the view-model refuses rather than paints", () => {
  it("a document of another schema", () => {
    expect(() => renderVoice({ ...payload(), schema: "x" } as never)).toThrow(OpsSchemaMismatch);
  });

  it("a profile that does not exist, anywhere in the payload (near miss: the two that do)", () => {
    const bent = withTile("sessions", (t) => ({
      ...t,
      rows: [{ profile: "fast_voice", reason: "default", sessions: 3 }],
    }));
    expect(() => renderVoice(bent)).toThrow(VoiceProfileOutsideSet);
    expect(() => renderVoice({ ...payload(), profiles: ["residency_tr", "typed", "s2s"] })).toThrow(
      VoiceProfileOutsideSet,
    );
    expect(() => renderVoice(payload())).not.toThrow();
  });

  it("a canary weight outside 0..100 (near miss: 100 itself)", () => {
    const at = (weight: number): VoicePayload =>
      withTile("controls", (t) => ({
        ...t,
        tenants: t.tenants.map((row) =>
          row.tenant_id === "tenant-c" ? { ...row, canary_weight: weight } : row,
        ),
      }));
    expect(() => renderVoice(at(101))).toThrow(VoiceWeightOutOfBounds);
    expect(() => renderVoice(at(12.5))).toThrow(VoiceWeightOutOfBounds);
    expect(() => renderVoice(at(100))).not.toThrow();
  });

  it("a tenant shown on voice while its kill switch is engaged", () => {
    const bent = withTile("controls", (t) => ({
      ...t,
      tenants: t.tenants.map((row) =>
        row.tenant_id === "tenant-a" ? { ...row, effective_profile: "residency_tr" } : row,
      ),
    }));
    expect(() => renderVoice(bent)).toThrow(VoiceControlIncoherent);
  });

  it("an unknown tile that still carries a figure", () => {
    const bent = withTile("failovers", (t) => ({ ...t, state: "unknown", reason: "no_series" }));
    expect(() => renderVoice(bent)).toThrow(OpsUnknownCarriesFigure);
  });

  it("a tenant id that is not id-shaped", () => {
    const bent = withTile("controls", (t) => ({
      ...t,
      tenants: t.tenants.map((row, i) => (i === 0 ? { ...row, tenant_id: "Hastane A" } : row)),
    }));
    expect(() => renderVoice(bent)).toThrow(OpsLabelLeaked);
  });

  it("a target beside a figure (invariant 20)", () => {
    const bent = withTile("turn_latency", (t) => ({ ...t, target: "p95 < 1 s" }) as never);
    expect(() => renderVoice(bent)).toThrow(OpsTargetRendered);
  });
});

// ------------------------------------------------------------------ controls

describe("the controls — asymmetric, and only among profiles that exist", () => {
  it("shows each tenant's switch, default, canary and who changed it", () => {
    const rows = renderVoice(payload()).controls.tenants;
    const a = rows.find((r) => r.tenantId === "tenant-a")!;
    expect(a).toMatchObject({ killSwitch: true, effectiveProfile: "typed" });
    expect(a.changedBy).toEqual("kc-sub-sre-oncall-1");
    const c = rows.find((r) => r.tenantId === "tenant-c")!;
    // number and unit are one no-break atom (invariant 22)
    expect(c.canary).toEqual(`residency_tr · 10${NBSP}%`);
  });

  it("offers a form for each of the four controls, posting to the page's own handler", async () => {
    const markup = await page(payload());
    for (const action of [
      "kill_switch_engage",
      "kill_switch_release",
      "default_profile",
      "canary",
    ]) {
      expect(markup).toContain(`name="action" value="${action}"`);
    }
    expect(markup.match(/<form /g)?.length).toEqual(4);
    expect(markup.match(/action="\/voice\/action" method="post"/g)?.length).toEqual(4);
  });

  it("names the tier and the second key for each control", async () => {
    const markup = await page(payload());
    expect(markup).toContain('data-control="kill_switch_engage" data-tier="1"');
    expect(markup).toContain('data-control="canary" data-tier="2"');
  });

  it("offers exactly the two profiles and a weight bounded 0..100 in whole steps", async () => {
    const markup = await page(payload());
    const options = [...markup.matchAll(/<option value="([^"]+)">/g)].map((m) => m[1]);
    const profiles = new Set(options.filter((o) => o === "residency_tr" || o === "typed"));
    expect(profiles).toEqual(new Set(["residency_tr", "typed"]));
    expect(options).not.toContain("s2s");
    expect(markup).toContain('type="number" min="0" max="100" step="1"');
  });

  it("lists pending ceremonies with the requester's role, and approval needs the step-up", async () => {
    const markup = await page(payload());
    expect(markup).toContain("01jbq0voicerecordedprofile01");
    expect(markup).toContain("clinical_lead");
    expect(markup).toMatch(/<button[^>]*disabled=""[^>]*data-reason="step_up_unwired"/);
  });

  it("shows a result code it knows and nothing it does not", async () => {
    const { state } = await load(payload());
    expect(html(state, "en", resultFrom("engaged"))).toContain('data-result="engaged"');
    expect(resultFrom("<script>")).toBeNull();
    expect(resultFrom("an arbitrary sentence")).toBeNull();
    expect(resultFrom(["engaged", "requested"])).toBeNull();
    expect(resultFrom("voice_profile_unknown")).toEqual("voice_profile_unknown");
  });
});

// ------------------------------------------------------------------ the form handler

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

const REASON = {
  reason_class: "incident_mitigation",
  justification: "TTS lane degraded on the bridge; typed until it recovers.",
};

async function submit(
  fields: Record<string, string>,
  opts: { site?: string | null; authorization?: string | null; answer?: Recorded } = {},
): Promise<{ code: string; calls: Call[] }> {
  const answer = opts.answer ?? { status: 200, body: { changed: true } };
  const { fetch, calls } = recordedFetch({
    "/admin/voice/kill-switch": answer,
    "/admin/voice/kill-switch/release": answer,
    "/admin/voice/profile/tenant-c": answer,
    "/admin/voice/canary/tenant-c": answer,
  });
  const outcome = await submitVoiceAction({
    config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
    authorization: opts.authorization === undefined ? "Bearer kc:sre_oncall" : opts.authorization,
    fetchSite: opts.site === undefined ? "same-origin" : opts.site,
    form: form(fields),
    fetch,
  });
  return { code: outcome.code, calls };
}

describe("the form handler — nothing reaches the API that the API would refuse", () => {
  it("pulls the kill switch with one POST, the bearer, and the closed body", async () => {
    const { code, calls } = await submit({
      action: "kill_switch_engage",
      tenant: "tenant-a",
      ...REASON,
    });
    expect(code).toEqual("engaged");
    expect(calls).toEqual([
      {
        url: `${API}/admin/voice/kill-switch`,
        method: "POST",
        authorization: "Bearer kc:sre_oncall",
        body: { tenant: "tenant-a", ...REASON },
      },
    ]);
  });

  it("an engaged switch pulled again is reported unchanged", async () => {
    const { code } = await submit(
      { action: "kill_switch_engage", tenant: "tenant-a", ...REASON },
      { answer: { status: 200, body: { changed: false } } },
    );
    expect(code).toEqual("unchanged");
  });

  it("a canary request is a PUT with an integer weight, and is only a request", async () => {
    const { code, calls } = await submit(
      { action: "canary", tenant: "tenant-c", profile: "residency_tr", weight: "25", ...REASON },
      { answer: { status: 200, body: { action_id: "a1", state: "pending" } } },
    );
    expect(code).toEqual("requested");
    expect(calls[0]).toMatchObject({
      method: "PUT",
      url: `${API}/admin/voice/canary/tenant-c`,
      body: { profile: "residency_tr", weight: 25, ...REASON },
    });
  });

  it("refuses a cross-site post before anything is dialled (near miss: same-origin)", async () => {
    for (const site of ["cross-site", "same-site", "none", null]) {
      const { code, calls } = await submit(
        { action: "kill_switch_engage", tenant: "tenant-a", ...REASON },
        { site },
      );
      expect(code).toEqual("cross_site_refused");
      expect(calls).toEqual([]);
    }
  });

  it("refuses without a bearer before anything is dialled", async () => {
    const { code, calls } = await submit(
      { action: "kill_switch_engage", tenant: "tenant-a", ...REASON },
      { authorization: null },
    );
    expect(code).toEqual("no_credentials");
    expect(calls).toEqual([]);
  });

  it.each([
    [{ action: "approve", tenant: "tenant-a" }, "action_unknown"],
    [
      { action: "default_profile", tenant: "tenant-c", profile: "fast_voice" },
      "voice_profile_unknown",
    ],
    [{ action: "default_profile", tenant: "tenant-c", profile: "TYPED" }, "voice_profile_unknown"],
    [
      { action: "canary", tenant: "tenant-c", profile: "residency_tr", weight: "101" },
      "voice_canary_weight_out_of_bounds",
    ],
    [
      { action: "canary", tenant: "tenant-c", profile: "residency_tr", weight: "12.5" },
      "voice_canary_weight_out_of_bounds",
    ],
    [
      { action: "canary", tenant: "tenant-c", profile: "residency_tr", weight: "" },
      "voice_canary_weight_out_of_bounds",
    ],
    [{ action: "kill_switch_engage", tenant: "Hastane A" }, "voice_tenant_invalid"],
  ])("refuses %j as %s without dialling", async (fields, expected) => {
    const { code, calls } = await submit({ ...REASON, ...fields });
    expect(code).toEqual(expected);
    expect(calls).toEqual([]);
  });

  it("carries the API's refusal code back, and only a code", async () => {
    const { code } = await submit(
      { action: "kill_switch_release", tenant: "tenant-a", ...REASON },
      { answer: { status: 409, body: { error: "voice_kill_switch_not_engaged" } } },
    );
    expect(code).toEqual("voice_kill_switch_not_engaged");
    const { code: prose } = await submit(
      { action: "kill_switch_release", tenant: "tenant-a", ...REASON },
      { answer: { status: 409, body: { error: "Ayşe could not be switched" } } },
    );
    expect(prose).toEqual("api_refused");
  });

  it("plans exactly the four controls and nothing that approves", () => {
    expect(
      planVoiceAction(form({ action: "kill_switch_engage", tenant: "t-1", ...REASON })),
    ).toEqual({
      ok: true,
      method: "POST",
      path: "/admin/voice/kill-switch",
      body: { tenant: "t-1", ...REASON },
    });
    expect(
      planVoiceAction(
        form({ action: "default_profile", tenant: "t-1", profile: "typed", ...REASON }),
      ),
    ).toMatchObject({
      ok: true,
      method: "PUT",
      path: "/admin/voice/profile/t-1",
    });
  });
});
