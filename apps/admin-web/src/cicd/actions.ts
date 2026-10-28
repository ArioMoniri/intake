/**
 * INT-187 — the CI/CD page's form handler: one planner, one submit.
 *
 * The page is server-rendered with no client script (the CSP carries no
 * `unsafe-inline`), so a control is a plain HTML form posting to this app's
 * own `/cicd/action`, which forwards to the admin API with the caller's
 * bearer. The API's gate, role matrix, four-eyes ceremony and write-ahead
 * audit decide; this module decides only what may be *sent*:
 *
 * - **Same origin only.** A post whose `Sec-Fetch-Site` is not `same-origin`
 *   is refused before anything is read.
 * - **The two controls and nothing else.** Freeze deploys (tier 1, one key)
 *   and request a lift (tier 2 — only a *request* for a second key). Approval
 *   is not posted here: it goes through the INT-563 step-up (`../step-up`,
 *   ADR-043), a fresh WebAuthn re-authentication (files/08 §2.3). There is no
 *   rollback form: no deploy controller exists for it to command (Argo CD is
 *   not deployed), and a button over nothing is not a control.
 * - **Only values the API would accept.** A reason class that is not a code is
 *   refused here, without a dial.
 *
 * The outcome is always a code from {@link RESULT_CODES} — never the API's
 * prose and never a submitted value (invariant 6).
 */
import type { OpsConfig } from "../ops/access";
import { REASON } from "../ops/guards";
import type { FetchLike } from "../ops/load";

export const CICD_ACTIONS = ["freeze_engage", "freeze_lift"] as const;
export type CicdAction = (typeof CICD_ACTIONS)[number];

const LOCAL_REFUSALS = [
  "cross_site_refused",
  "api_base_unconfigured",
  "no_credentials",
  "action_unknown",
  "api_unreachable",
  "api_refused",
  "token_refused",
] as const;

/** Codes the admin API answers a freeze write with (services/api cicd_routes). */
const API_REFUSALS = [
  "forbidden",
  "source_ip_refused",
  "admin_console_unconfigured",
  "tenant_scope_refused",
  "release_freeze_not_engaged",
  "release_freeze_changed",
  "release_freeze_role_ineligible",
  "release_freeze_unconfigured",
  "release_freeze_unreachable",
  "release_freeze_malformed",
  "release_freeze_unexpected_field",
  "release_freeze_body_not_json",
  "release_freeze_body_not_an_object",
  "release_freeze_reason_class_unknown",
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
      path: "/admin/cicd/freeze" | "/admin/cicd/freeze/lift";
      body: Record<string, string>;
    }
  | { ok: false; code: ResultCode };

const MAX_JUSTIFICATION = 2000;

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

/** What one submitted form would send — or why it sends nothing. */
export function planCicdAction(form: FormData): ActionPlan {
  const action = field(form, "action");
  if (!(CICD_ACTIONS as readonly string[]).includes(action)) {
    return { ok: false, code: "action_unknown" };
  }
  const reasonClass = field(form, "reason_class");
  if (!REASON.test(reasonClass)) return { ok: false, code: "release_freeze_reason_class_unknown" };
  const body = {
    reason_class: reasonClass,
    justification: field(form, "justification").slice(0, MAX_JUSTIFICATION),
  };
  return action === "freeze_engage"
    ? { ok: true, path: "/admin/cicd/freeze", body }
    : { ok: true, path: "/admin/cicd/freeze/lift", body };
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
export async function submitCicdAction(args: {
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
  const plan = planCicdAction(form);
  if (!plan.ok) return { code: plan.code };

  let response: Response;
  try {
    response = await fetch(`${config.apiBase}${plan.path}`, {
      method: "POST",
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
    if (plan.path === "/admin/cicd/freeze") {
      const changed =
        body !== null && typeof body === "object" && (body as Record<string, unknown>)["changed"];
      return { code: changed === false ? "unchanged" : "engaged" };
    }
    return { code: "requested" };
  }
  if (response.status === 401) return { code: "token_refused" };
  return { code: apiCode(body) };
}
