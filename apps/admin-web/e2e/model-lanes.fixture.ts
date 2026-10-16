/**
 * INT-428 — what the two Model lanes specs share: the recorded payload, the
 * variants each property is checked against, a recording `fetch`, and the
 * page rendered to static markup.
 *
 * `model-lanes.payload.json` is a recording, in tests only, of the shipped
 * composite (`intake_api.admin.model_lanes_console.load_model_lanes_console`)
 * for a synthetic deployment with nothing configured: no egress row, no key
 * store, no GPU endpoint, no Prometheus. Every variant below is that recording
 * with one documented change, so a near-miss differs from what it controls by
 * exactly the property under test.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import type { ResultCode, StagedKey } from "../src/model-lanes/actions";
import { ModelLanesConsole } from "../src/model-lanes/console";
import { loadModelLanes, type ModelLanesState } from "../src/model-lanes/load";
import type { ModelLanesPayload, RoleRowPayload } from "../src/model-lanes/module";
import { opsConfigFromEnv } from "../src/ops/access";
import type { FetchLike } from "../src/ops/load";

export const API = "https://api.intake.test";

export function payload(): ModelLanesPayload {
  const raw = readFileSync(join(__dirname, "fixtures", "model-lanes.payload.json"), "utf8");
  return JSON.parse(raw) as ModelLanesPayload;
}

/** A key a person would type: derived, so no scanner reads it as a credential. */
export const TYPED_KEY = ["lane", "probe", "4f7e"].join("_").padStart(32, "k");

export interface Recorded {
  status: number;
  body: unknown;
}

export interface Call {
  url: string;
  method: string;
  authorization: string | null;
  body: unknown;
}

export function recordedFetch(routes: Record<string, Recorded>): {
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
    if (answer === undefined) throw new TypeError("fetch failed");
    return new Response(JSON.stringify(answer.body), {
      status: answer.status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, calls };
}

export async function load(
  body: unknown,
  authorization: string | null = "Bearer kc:platform_owner",
  status = 200,
): Promise<{ state: ModelLanesState; calls: Call[] }> {
  const { fetch, calls } = recordedFetch({ "/admin/model-lanes": { status, body } });
  const config = opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API });
  return { state: await loadModelLanes({ config, authorization, fetch }), calls };
}

export function html(
  state: ModelLanesState,
  lang: "tr" | "en" = "en",
  result: ResultCode | null = null,
  staged: StagedKey | null = null,
): string {
  return renderToStaticMarkup(createElement(ModelLanesConsole, { state, lang, result, staged }));
}

export async function page(body: ModelLanesPayload, lang: "tr" | "en" = "en"): Promise<string> {
  const { state } = await load(body);
  if (state.kind !== "console") throw new Error(`expected a console, got ${state.kind}`);
  return html(state, lang);
}

// --- variants ------------------------------------------------------------------

function laneRow(base: ModelLanesPayload, lane: string, patch: Partial<RoleRowPayload>) {
  return base.lanes.map((row) =>
    row.lane === lane && row.role === lane ? { ...row, ...patch } : row,
  );
}

/** Prometheus answering: a priced-nowhere hosted row, a self-hosted row, a priced one. */
export function withUsage(base = payload()): ModelLanesPayload {
  const lanes = laneRow(base, "llm", {
    usage: [
      {
        route: "hosted",
        provider: "openai",
        p50_ms: 412.5,
        p95_ms: 980.25,
        calls: 1520,
        cost: { state: "price_not_configured", usd: null },
      },
      {
        route: "self_hosted",
        provider: "none",
        p50_ms: null,
        p95_ms: null,
        calls: null,
        cost: { state: "not_metered", usd: null },
      },
    ],
  });
  const withAsr = laneRow({ ...base, lanes }, "asr", {
    usage: [
      {
        route: "hosted",
        provider: "openai",
        p50_ms: 300,
        p95_ms: 600,
        calls: 12,
        cost: { state: "known", usd: 0.0123 },
      },
    ],
  });
  return { ...base, usage_reason: null, lanes: withAsr };
}

/** A real-PHI deployment: the image carries no hosted lane, nothing hosted is offered. */
export function realPhi(base = payload()): ModelLanesPayload {
  const models = Object.fromEntries(
    Object.entries(base.models).map(([lane, m]) => [lane, { ...m, hosted: [] }]),
  );
  const lanes = base.lanes.map((row) => ({
    ...row,
    setting: { route: "self_hosted", model: null, fallback: null, fallback_model: null },
    serving: { ...row.serving, reason: "self_hosted_unhealthy" },
  }));
  return {
    ...base,
    deployment: {
      declared: "real_phi",
      bound: null,
      effective: "real_phi",
      hosted_lanes: false,
      data_class_mismatch: false,
    },
    lanes,
    models,
    providers: [],
  };
}

/** The control store bound `real_phi` on a synthetic image. */
export function mismatched(base = payload()): ModelLanesPayload {
  return {
    ...base,
    deployment: {
      declared: "synthetic",
      bound: "real_phi",
      effective: "real_phi",
      hosted_lanes: true,
      data_class_mismatch: true,
    },
  };
}

/** Exactly what the composite answers with no wiring at all. */
export function unconfigured(base = payload()): ModelLanesPayload {
  return {
    schema: base.schema,
    generated_at: base.generated_at,
    state: "unknown",
    reason: "model_lanes_unconfigured",
    deployment: null,
    control: { state: "unknown", reason: "model_lanes_unconfigured" },
    lanes: [],
    roles: [],
    models: {},
    providers: [],
    usage_window: "24h",
    usage_reason: "model_lanes_unconfigured",
    pending: [],
  };
}

/** The control store unreachable: no setting, nothing expected, control unknown. */
export function storeDown(base = payload()): ModelLanesPayload {
  return {
    ...base,
    state: "unknown",
    reason: "model_lanes_unreachable",
    control: { state: "unknown", reason: "model_lanes_unreachable" },
    roles: [],
    lanes: base.lanes.map((row) => ({
      ...row,
      setting: null,
      self_hosted: { identity: "unconfigured", expected: null },
    })),
  };
}

export function withKeySet(base = payload()): ModelLanesPayload {
  const [provider] = base.providers;
  return {
    ...base,
    providers: [
      {
        ...provider!,
        key: { state: "set", last4: "Zq9x", set_at: "2026-10-01T09:00:00+00:00" },
      },
    ],
  };
}

export function withPending(base = payload()): ModelLanesPayload {
  return {
    ...base,
    pending: [
      {
        action_id: "pa-0001",
        dangerous_action_id: "admin.model_lanes.route.switch",
        tier: 2,
        state: "pending",
        expires_at: "2026-10-02T00:15:00+00:00",
        approver_role: null,
      },
    ],
  };
}

export function withHostedDisabled(base = payload()): ModelLanesPayload {
  if (base.control.state !== "known") throw new Error("the recording's control is known");
  return {
    ...base,
    control: {
      ...base.control,
      revision: 4,
      hosted_disabled: true,
      changed_at: "2026-10-01T08:00:00+00:00",
      changed_by: "kc-sub-sre-oncall-1",
      last_change: "hosted_disable",
    },
  };
}
