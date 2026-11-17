/**
 * INT-182 — the Voice page's form handler: one planner, one submit.
 *
 * The page is server-rendered with no client script (the CSP carries no
 * `unsafe-inline`), so a control is a plain HTML form posting to this app's
 * own `/voice/action`, which forwards to the admin API with the caller's
 * bearer. The API's gate, role matrix, four-eyes ceremony and write-ahead
 * audit decide; this module decides only what may be *sent*:
 *
 * - **Same origin only.** A post whose `Sec-Fetch-Site` is not `same-origin`
 *   is refused before anything is read — an auth proxy that injects the
 *   bearer would otherwise make every cross-site form a console action.
 * - **The four controls and nothing else.** Pull the kill switch (tier 1, one
 *   key), request its release, a default-profile switch or a canary weight
 *   (tier 2 — each only a *request* for a second key). There is no approve
 *   form: approval needs a fresh single-use WebAuthn assertion (files/08
 *   §2.3), which a script-free page cannot mint.
 * - **Only values the API would accept.** A profile outside the two that exist
 *   (invariant 19), a weight that is not an integer 0..100, or a tenant that
 *   is not id-shaped is refused here, without a dial.
 *
 * The outcome is always a code from {@link RESULT_CODES} — never the API's
 * prose and never a submitted value (invariant 6).
 */
import type { OpsConfig } from "../ops/access";
import type { FetchLike } from "../ops/load";
import { REASON } from "../ops/guards";
import { TENANT_ID, isProfile } from "./module";
import { CANARY_WEIGHT_MAX } from "./payload";

export const VOICE_ACTIONS = [
  "kill_switch_engage",
  "kill_switch_release",
  "default_profile",
  "canary",
] as const;
export type VoiceAction = (typeof VOICE_ACTIONS)[number];

const LOCAL_REFUSALS = [
  "cross_site_refused",
  "api_base_unconfigured",
  "no_credentials",
  "action_unknown",
  "voice_tenant_invalid",
  "voice_reason_class_unknown",
  "voice_profile_unknown",
  "voice_canary_weight_out_of_bounds",
  "api_unreachable",
  "api_refused",
  "token_refused",
] as const;

/** Codes the admin API answers a voice write with (services/api voice_routes). */
const API_REFUSALS = [
  "forbidden",
  "source_ip_refused",
  "admin_console_unconfigured",
  "tenant_scope_refused",
  "voice_kill_switch_not_engaged",
  "voice_profile_unchanged",
  "voice_canary_is_default",
  "voice_control_changed",
  "voice_control_unconfigured",
  "voice_control_unreachable",
  "voice_unexpected_field",
  "voice_body_not_json",
  "voice_body_not_an_object",
  "flag_change_reason_missing",
  "flag_change_reason_too_short",
  "four_eyes_approver_role",
] as const;

const SUCCESSES = ["engaged", "unchanged", "requested"] as const;

export const RESULT_CODES = [...SUCCESSES, ...LOCAL_REFUSALS, ...API_REFUSALS] as const;
export type ResultCode = (typeof RESULT_CODES)[number];

export function isResultCode(value: unknown): value is ResultCode {
  return typeof value === "string" && (RESULT_CODES as readonly string[]).includes(value);
}

export type ActionPlan =
  | {
      ok: true;
      method: "POST" | "PUT";
      path: `/admin/voice/${string}`;
      body: Record<string, unknown>;
    }
  | { ok: false; code: ResultCode };

const WEIGHT = /^(0|[1-9][0-9]{0,2})$/;
const MAX_JUSTIFICATION = 2000;

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

/** What one submitted form would send — or why it sends nothing. */
export function planVoiceAction(form: FormData): ActionPlan {
  const action = field(form, "action");
  if (!(VOICE_ACTIONS as readonly string[]).includes(action)) {
    return { ok: false, code: "action_unknown" };
  }
  const tenant = field(form, "tenant");
  if (!TENANT_ID.test(tenant)) return { ok: false, code: "voice_tenant_invalid" };
  const reasonClass = field(form, "reason_class");
  if (!REASON.test(reasonClass)) return { ok: false, code: "voice_reason_class_unknown" };
  const reason = {
    reason_class: reasonClass,
    justification: field(form, "justification").slice(0, MAX_JUSTIFICATION),
  };
  switch (action as VoiceAction) {
    case "kill_switch_engage":
      return {
        ok: true,
        method: "POST",
        path: "/admin/voice/kill-switch",
        body: { tenant, ...reason },
      };
    case "kill_switch_release":
      return {
        ok: true,
        method: "POST",
        path: "/admin/voice/kill-switch/release",
        body: { tenant, ...reason },
      };
    case "default_profile": {
      const profile = field(form, "profile");
      if (!isProfile(profile)) return { ok: false, code: "voice_profile_unknown" };
      return {
        ok: true,
        method: "PUT",
        path: `/admin/voice/profile/${tenant}`,
        body: { profile, ...reason },
      };
    }
    case "canary": {
      const profile = field(form, "profile");
      if (!isProfile(profile)) return { ok: false, code: "voice_profile_unknown" };
      const raw = field(form, "weight");
      const weight = WEIGHT.test(raw) ? Number(raw) : Number.NaN;
      if (!(weight <= CANARY_WEIGHT_MAX)) {
        return { ok: false, code: "voice_canary_weight_out_of_bounds" };
      }
      return {
        ok: true,
        method: "PUT",
        path: `/admin/voice/canary/${tenant}`,
        body: { profile, weight, ...reason },
      };
    }
  }
}

async function json(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

function apiCode(body: unknown): ResultCode {
  if (body !== null && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const nested = record["detail"];
    const code =
      record["error"] ??
      (nested !== null && typeof nested === "object"
        ? (nested as Record<string, unknown>)["error"]
        : undefined);
    if (typeof code === "string" && REASON.test(code) && isResultCode(code)) return code;
  }
  return "api_refused";
}

const TIMEOUT_MS = 10_000;

/** Validate, forward with the caller's bearer, and answer one code. */
export async function submitVoiceAction(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetchSite: string | null;
  form: FormData;
  fetch: FetchLike;
}): Promise<{ code: ResultCode }> {
  const { config, authorization, fetchSite, form, fetch } = args;
  if (fetchSite !== "same-origin") return { code: "cross_site_refused" };
  if (config === null) return { code: "api_base_unconfigured" };
  if (authorization === null) return { code: "no_credentials" };
  const plan = planVoiceAction(form);
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
  if (response.status === 200) {
    if (plan.path === "/admin/voice/kill-switch") {
      const changed =
        body !== null && typeof body === "object" && (body as Record<string, unknown>)["changed"];
      return { code: changed === false ? "unchanged" : "engaged" };
    }
    return { code: "requested" };
  }
  if (response.status === 401) return { code: "token_refused" };
  return { code: apiCode(body) };
}
