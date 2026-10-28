/**
 * INT-562 — the Safety queue's one form: acknowledge an entry.
 *
 * The page is server-rendered with no client script (the CSP carries no
 * `unsafe-inline`), so the control is a plain HTML form posting to this app's
 * own `/safety-queue/action`, which forwards to the admin API with the
 * caller's bearer. The API's gate, role matrix and write-ahead audit decide
 * (INT-406: tier 1, one key, the tenant's clinical responsible's alone, once);
 * this module decides only what may be *sent*:
 *
 * - **Same origin only.** A post whose `Sec-Fetch-Site` is not `same-origin`
 *   is refused before anything is read.
 * - **One id, nothing else.** The entry id must be `sx_` + 32 hex; the API
 *   takes no body, so none is sent.
 *
 * The outcome is always a code from {@link RESULT_CODES} — never the API's
 * prose and never a submitted value (invariant 6).
 */
import type { OpsConfig } from "../ops/access";
import { REASON } from "../ops/guards";
import type { FetchLike } from "../ops/load";

const ENTRY_ID = /^sx_[0-9a-f]{32}$/;

const LOCAL_REFUSALS = [
  "cross_site_refused",
  "api_base_unconfigured",
  "no_credentials",
  "action_unknown",
  "safety_entry_invalid",
  "api_unreachable",
  "api_refused",
  "token_refused",
] as const;

/** Codes the admin API answers the acknowledgement with (services/api safety_queue). */
const API_REFUSALS = [
  "forbidden",
  "source_ip_refused",
  "admin_console_unconfigured",
  "tenant_required",
  "safety_entry_not_found",
  "safety_entry_already_acknowledged",
  "safety_inbox_unconfigured",
  "safety_inbox_unreachable",
  "safety_inbox_contended",
  "body_not_json",
  "unexpected_field",
] as const;

const SUCCESSES = ["acknowledged"] as const;

export const RESULT_CODES = [...SUCCESSES, ...LOCAL_REFUSALS, ...API_REFUSALS] as const;
export type ResultCode = (typeof RESULT_CODES)[number];

export function isResultCode(value: unknown): value is ResultCode {
  return typeof value === "string" && (RESULT_CODES as readonly string[]).includes(value);
}

export type AcknowledgePlan =
  { ok: true; path: `/admin/safety-queue/${string}/acknowledge` } | { ok: false; code: ResultCode };

/** What one submitted form would send — or why it sends nothing. */
export function planAcknowledge(form: FormData): AcknowledgePlan {
  const entryId = form.get("entry_id");
  if (typeof entryId !== "string" || !ENTRY_ID.test(entryId)) {
    return { ok: false, code: "safety_entry_invalid" };
  }
  return { ok: true, path: `/admin/safety-queue/${entryId}/acknowledge` };
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
export async function submitAcknowledge(args: {
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
  const plan = planAcknowledge(form);
  if (!plan.ok) return { code: plan.code };

  let response: Response;
  try {
    response = await fetch(`${config.apiBase}${plan.path}`, {
      method: "POST",
      headers: { authorization, accept: "application/json" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { code: "api_unreachable" };
  }
  const body = await json(response);
  if (response.status === 200) return { code: "acknowledged" };
  if (response.status === 401) return { code: "token_refused" };
  return { code: apiCode(body) };
}
