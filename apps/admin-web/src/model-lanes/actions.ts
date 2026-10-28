/**
 * INT-428 — the Model lanes page's form handler: one planner, one submit.
 *
 * The page is server-rendered with no client script (the CSP carries no
 * `unsafe-inline`), so a control is a plain HTML form posting to this app's
 * own `/model-lanes/action`, which forwards to the admin API with the caller's
 * bearer. The API's gate, role matrix, ADR-035 guard, four-eyes ceremony and
 * write-ahead audit decide; this module decides only what may be *sent*:
 *
 * - **Same origin only.** A post whose `Sec-Fetch-Site` is not `same-origin`
 *   is refused before anything is read.
 * - **The five controls and nothing else.** Disable hosted lanes and switch to
 *   the GPU lanes (tier 1, one key, the safe direction); request a hosted
 *   release, a route switch for a lane or role, or a provider key (tier 2 —
 *   each only a *request* for a second key). Approval is not posted here:
 *   it goes through the INT-563 step-up (`../step-up`, ADR-043), a fresh
 *   WebAuthn re-authentication the API verifies (files/08 §2.3).
 * - **Only values the API would accept.** A reason class outside the closed
 *   set, a lane, role, route or provider outside theirs (there is no `mock`
 *   route), a model key that is not key-shaped or a provider key that is not
 *   key-shaped is refused here, without a dial.
 *
 * **The provider key.** It is read from the form once, into the one request
 * body, and goes nowhere else: not into the outcome, not into a code, not
 * into an error. What comes back is the API's own `last4` for the staged
 * key, and only when it is four key characters.
 *
 * The outcome is always a code from {@link RESULT_CODES} — never the API's
 * prose and never a submitted value (invariant 6).
 */
import type { OpsConfig } from "../ops/access";
import { REASON } from "../ops/guards";
import type { FetchLike } from "../ops/load";
import {
  LANES,
  LAST4,
  MODEL_KEY,
  PROVIDERS,
  REASON_CLASSES,
  ROLE,
  ROUTES,
  type ProviderId,
} from "./payload";
import { RESULT_CODES, type ResultCode } from "./results";

export { RESULT_CODES, type ResultCode } from "./results";

export const MODEL_LANES_ACTIONS = [
  "hosted_disable",
  "self_hosted_engage",
  "hosted_release",
  "route_switch",
  "key_set",
] as const;
export type ModelLanesAction = (typeof MODEL_LANES_ACTIONS)[number];

/** A provider API key's shape (`intake_platform.model_lanes.keys._KEY_SHAPE`). */
export const API_KEY = /^[A-Za-z0-9_.-]{20,512}$/;

export function isResultCode(value: unknown): value is ResultCode {
  return typeof value === "string" && (RESULT_CODES as readonly string[]).includes(value);
}

export type ActionPlan =
  | {
      ok: true;
      action: ModelLanesAction;
      method: "POST" | "PUT";
      path: `/admin/model-lanes/${string}`;
      body: Record<string, unknown>;
    }
  | { ok: false; code: ResultCode };

/** A key staged for its second key: the provider and the API's last four. */
export interface StagedKey {
  provider: ProviderId;
  last4: string;
}

const MAX_JUSTIFICATION = 2000;

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

function inSet<T extends string>(value: string, allowed: readonly T[]): value is T {
  return (allowed as readonly string[]).includes(value);
}

/** An optional select: empty is `null`, anything else must be key-shaped. */
function optionalKey(form: FormData, name: string): string | null | false {
  const value = field(form, name);
  if (value === "") return null;
  return MODEL_KEY.test(value) ? value : false;
}

function planRouteSwitch(form: FormData, reason: Record<string, string>): ActionPlan {
  const role = field(form, "role");
  if (!ROLE.test(role)) return { ok: false, code: "model_role_unknown" };
  const route = field(form, "route");
  if (!inSet(route, ROUTES)) return { ok: false, code: "model_lanes_route_unknown" };
  const fallbackRaw = field(form, "fallback");
  if (fallbackRaw !== "" && !inSet(fallbackRaw, PROVIDERS)) {
    return { ok: false, code: "model_lanes_provider_unknown" };
  }
  const model = optionalKey(form, "model");
  const fallbackModel = optionalKey(form, "fallback_model");
  if (model === false || fallbackModel === false) return { ok: false, code: "model_key_malformed" };
  return {
    ok: true,
    action: "route_switch",
    method: "PUT",
    path: `/admin/model-lanes/route/${role}`,
    body: {
      ...reason,
      route,
      model,
      fallback: fallbackRaw === "" ? null : fallbackRaw,
      fallback_model: fallbackModel,
    },
  };
}

function planKeySet(form: FormData, reason: Record<string, string>): ActionPlan {
  const provider = field(form, "provider");
  if (!inSet(provider, PROVIDERS)) return { ok: false, code: "model_lanes_provider_unknown" };
  const apiKey = form.get("api_key");
  if (typeof apiKey !== "string" || !API_KEY.test(apiKey)) {
    return { ok: false, code: "model_lanes_key_malformed" };
  }
  return {
    ok: true,
    action: "key_set",
    method: "PUT",
    path: `/admin/model-lanes/keys/${provider}`,
    body: { ...reason, api_key: apiKey },
  };
}

/** What one submitted form would send — or why it sends nothing. */
export function planModelLanesAction(form: FormData): ActionPlan {
  const action = field(form, "action");
  if (!inSet(action, MODEL_LANES_ACTIONS)) return { ok: false, code: "action_unknown" };
  const reasonClass = field(form, "reason_class");
  if (!inSet(reasonClass, REASON_CLASSES)) {
    return { ok: false, code: "model_lanes_reason_class_unknown" };
  }
  const reason = {
    reason_class: reasonClass,
    justification: field(form, "justification").slice(0, MAX_JUSTIFICATION),
  };
  switch (action) {
    case "hosted_disable":
      return {
        ok: true,
        action,
        method: "POST",
        path: "/admin/model-lanes/hosted/disable",
        body: reason,
      };
    case "hosted_release":
      return {
        ok: true,
        action,
        method: "POST",
        path: "/admin/model-lanes/hosted/release",
        body: reason,
      };
    case "self_hosted_engage": {
      const lanes = [...new Set(form.getAll("lanes"))];
      if (lanes.length === 0 || !lanes.every((l) => typeof l === "string" && inSet(l, LANES))) {
        return { ok: false, code: "model_lanes_lane_unknown" };
      }
      return {
        ok: true,
        action,
        method: "POST",
        path: "/admin/model-lanes/self-hosted",
        body: { ...reason, lanes },
      };
    }
    case "route_switch":
      return planRouteSwitch(form, reason);
    case "key_set":
      return planKeySet(form, reason);
  }
}

async function json(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function apiCode(body: unknown): ResultCode {
  const top = record(body);
  const code = top?.["error"] ?? record(top?.["detail"])?.["error"];
  if (typeof code === "string" && REASON.test(code) && isResultCode(code)) return code;
  return "api_refused";
}

function staged(provider: ProviderId, body: unknown): StagedKey | undefined {
  const key = record(record(body)?.["key"]);
  const last4 = key?.["last4"];
  if (key?.["state"] !== "staged" || typeof last4 !== "string" || !LAST4.test(last4)) {
    return undefined;
  }
  return { provider, last4 };
}

function success(plan: Extract<ActionPlan, { ok: true }>, body: unknown): Outcome {
  switch (plan.action) {
    case "hosted_disable":
    case "self_hosted_engage":
      return { code: record(body)?.["changed"] === false ? "unchanged" : "applied" };
    case "key_set": {
      const provider = plan.path.slice("/admin/model-lanes/keys/".length) as ProviderId;
      const key = staged(provider, body);
      return key === undefined ? { code: "staged" } : { code: "staged", staged: key };
    }
    default:
      return { code: "requested" };
  }
}

export interface Outcome {
  code: ResultCode;
  staged?: StagedKey;
}

const TIMEOUT_MS = 10_000;

/** Validate, forward with the caller's bearer, and answer one code. */
export async function submitModelLanesAction(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetchSite: string | null;
  form: FormData;
  fetch: FetchLike;
}): Promise<Outcome> {
  const { config, authorization, fetchSite, form, fetch } = args;
  if (fetchSite !== "same-origin") return { code: "cross_site_refused" };
  if (config === null) return { code: "api_base_unconfigured" };
  if (authorization === null) return { code: "no_credentials" };
  const plan = planModelLanesAction(form);
  if (!plan.ok) return { code: plan.code };

  let response: Response;
  try {
    response = await fetch(`${config.apiBase}${plan.path}`, {
      method: plan.method,
      headers: {
        authorization,
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify(plan.body),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { code: "api_unreachable" };
  }
  const body = await json(response);
  if (response.status === 200) return success(plan, body);
  if (response.status === 401) return { code: "token_refused" };
  return { code: apiCode(body) };
}

/**
 * The one-shot cookie that carries a staged key's last four back to the page
 * after the redirect: never the query string (which lands in history and
 * access logs), HttpOnly, this page only, two minutes.
 */
export const STAGED_COOKIE = "model_lanes_staged";

export function stagedCookie(key: StagedKey): string {
  return `${STAGED_COOKIE}=${key.provider}.${key.last4}; Path=/model-lanes; Max-Age=120; HttpOnly; SameSite=Strict; Secure`;
}
