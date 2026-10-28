/**
 * INT-563 (ADR-043) — the console's half of the four-eyes step-up: no client
 * script, two server routes, and the API decides everything.
 *
 * 1. `POST /step-up/start` (an **Onayla** form on a pending row): refuses a
 *    cross-site post, asks `POST /admin/step-up` to open a ceremony for that
 *    one pending action, and redirects the browser to the authorization URL
 *    it answers — only when that URL is the configured Keycloak origin's
 *    authorization endpoint for the step-up client with `prompt=login` and
 *    `max_age=0`. Anything else is refused rather than followed: the console
 *    is not an open redirect.
 * 2. `GET /step-up/callback` (Keycloak's redirect back): relays `state` and
 *    `code` to `POST /admin/step-up/complete`, receives a one-time grant and
 *    the action's `DangerousAction` id, and presents the grant on that
 *    action's approve route (`./approvals`). The page comes back with one
 *    code.
 *
 * The callback cannot be forged into an approval: the ceremony is bound by the
 * API to the caller's own Keycloak subject and session, the code to the PKCE
 * verifier the API never lets out, and the grant to the one action. The
 * console holds none of them. Every outcome is a code (`./results`).
 */
import type { OpsConfig } from "../ops/access";
import type { FetchLike } from "../ops/load";
import { ACTION_ID, GRANT, approvalFor, isPage, type Page } from "./approvals";
import { apiResult, type StepUpResult } from "./results";

export const ENV_STEP_UP_ORIGIN = "INTAKE_ADMIN_STEP_UP_ORIGIN";
export const STEP_UP_CLIENT_ID = "admin-web-stepup";

const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]"]);
const STATE = /^[A-Za-z0-9_-]{16,128}$/;
const CODE = /^[A-Za-z0-9._~-]{1,4096}$/;
const TIMEOUT_MS = 10_000;

/**
 * Keycloak's origin, which the CSP's `form-action` admits beside `'self'` so
 * the start form may be redirected there — or `null`, and no step-up starts.
 * https only, except a loopback host in development; an origin and nothing
 * more.
 */
export function stepUpOriginFromEnv(env: Record<string, string | undefined>): string | null {
  const raw = env[ENV_STEP_UP_ORIGIN]?.trim();
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  const secure =
    url.protocol === "https:" || (url.protocol === "http:" && LOOPBACK.has(url.hostname));
  if (!secure || url.username || url.password || url.search || url.hash) return null;
  if (url.pathname !== "/" && url.pathname !== "") return null;
  return url.origin;
}

/** The authorization URL the API answered, only if it is the one ADR-043 describes. */
export function checkedAuthorizeUrl(value: unknown, origin: string): string | null {
  if (typeof value !== "string" || value.length > 4096) return null;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  const query = url.searchParams;
  const ok =
    url.origin === origin &&
    /^\/realms\/[A-Za-z0-9_-]+\/protocol\/openid-connect\/auth$/.test(url.pathname) &&
    query.get("client_id") === STEP_UP_CLIENT_ID &&
    query.get("response_type") === "code" &&
    query.get("prompt") === "login" &&
    query.get("max_age") === "0" &&
    query.get("code_challenge_method") === "S256" &&
    STATE.test(query.get("state") ?? "") &&
    !url.hash &&
    !url.username;
  return ok ? url.href : null;
}

export type Begun =
  | { kind: "redirect"; location: string; page: Page }
  | { kind: "result"; code: StepUpResult; page: Page };

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

async function json(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

async function post(
  fetch: FetchLike,
  config: OpsConfig,
  authorization: string,
  path: string,
  body: Record<string, string>,
): Promise<Response | null> {
  try {
    return await fetch(`${config.apiBase}${path}`, {
      method: "POST",
      headers: { authorization, accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return null;
  }
}

/** `POST /step-up/start`: where the browser goes next. */
export async function beginStepUp(args: {
  config: OpsConfig | null;
  origin: string | null;
  authorization: string | null;
  fetchSite: string | null;
  form: FormData;
  fetch: FetchLike;
}): Promise<Begun> {
  const { config, origin, authorization, fetchSite, form, fetch } = args;
  const from = field(form, "from");
  const page: Page = isPage(from) ? from : "step-up";
  const result = (code: StepUpResult): Begun => ({ kind: "result", code, page });
  if (fetchSite !== "same-origin") return result("cross_site_refused");
  if (config === null) return result("api_base_unconfigured");
  if (origin === null) return result("step_up_unconfigured");
  if (authorization === null) return result("no_credentials");
  const actionId = field(form, "action_id");
  if (!ACTION_ID.test(actionId)) return result("action_unknown");
  const response = await post(fetch, config, authorization, "/admin/step-up", {
    action_id: actionId,
  });
  if (response === null) return result("api_unreachable");
  const body = await json(response);
  if (response.status === 401) return result("token_refused");
  if (response.status !== 200) return result(apiResult(body));
  const location = checkedAuthorizeUrl(
    body !== null && typeof body === "object"
      ? (body as Record<string, unknown>)["authorize_url"]
      : null,
    origin,
  );
  return location === null ? result("api_refused") : { kind: "redirect", location, page };
}

/** `GET /step-up/callback`: one code, and the page to show it on. */
export async function completeStepUp(args: {
  config: OpsConfig | null;
  authorization: string | null;
  query: URLSearchParams;
  fallback: Page;
  fetch: FetchLike;
}): Promise<{ code: StepUpResult; page: Page }> {
  const { config, authorization, query, fallback, fetch } = args;
  const result = (code: StepUpResult, page: Page = fallback) => ({ code, page });
  // Keycloak's answer when the approver cancels, or the login fails
  if (query.has("error")) return result("step_up_cancelled");
  if (config === null) return result("api_base_unconfigured");
  if (authorization === null) return result("no_credentials");
  const state = query.get("state") ?? "";
  const code = query.get("code") ?? "";
  if (!STATE.test(state) || !CODE.test(code)) return result("step_up_unknown");
  const completed = await post(fetch, config, authorization, "/admin/step-up/complete", {
    state,
    code,
  });
  if (completed === null) return result("api_unreachable");
  const body = await json(completed);
  if (completed.status === 401) return result("token_refused");
  if (completed.status !== 200) return result(apiResult(body));
  const record = body !== null && typeof body === "object" ? (body as Record<string, unknown>) : {};
  const grant = record["grant"];
  const actionId = record["action_id"];
  const approval = approvalFor(record["action"]);
  if (
    approval === null ||
    typeof grant !== "string" ||
    !GRANT.test(grant) ||
    typeof actionId !== "string" ||
    !ACTION_ID.test(actionId)
  ) {
    return result("action_unknown");
  }
  const approved = await post(fetch, config, authorization, approval.path(actionId), {
    step_up_grant: grant,
  });
  if (approved === null) return result("api_unreachable", approval.page);
  if (approved.status === 200) return result("approved", approval.page);
  if (approved.status === 401) return result("token_refused", approval.page);
  return result(apiResult(await json(approved)), approval.page);
}
