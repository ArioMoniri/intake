/**
 * INT-351 — the ops page's server-side loader.
 *
 * Runs only on the server (the App Router page calls it during render), so the
 * browser never names a datasource and never holds more than the page
 * (files/08 §0b F1). The order is the control:
 *
 * 1. no configured API base → `unavailable`, and nothing is dialled;
 * 2. no bearer → `not_admitted`, and nothing is dialled;
 * 3. `GET /admin/ops` with the bearer — the API's admin gate answers. Any
 *    refusal is rendered as a refusal, with **no** further call: a caller the
 *    gate refused does not learn the API's health either;
 * 4. only then `/healthz`, `/readyz`, `/version` of the same base, each of
 *    which may independently be unknown.
 *
 * A payload the view-model refuses is `unavailable` — never half-painted.
 */
import type { OpsConfig } from "./access";
import {
  OpsPayloadRefused,
  renderOps,
  type HealthResponses,
  type OpsPayload,
  type OpsView,
  type Probe,
} from "./module";

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

export type RefusalReason =
  | "no_credentials"
  | "token_refused"
  | "role_not_permitted"
  | "source_ip_refused"
  | "console_unconfigured";

export type UnavailableReason = "api_base_unconfigured" | "api_unreachable" | "payload_refused";

/** Why a console page shows no tile at all — shared by every rendered page. */
export type RefusedState =
  | { kind: "not_admitted"; reason: RefusalReason }
  | { kind: "unavailable"; reason: UnavailableReason };

export type OpsConsoleState = RefusedState | { kind: "console"; view: OpsView };

const TIMEOUT_MS = 5000;

async function errorCode(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (detail !== null && typeof detail === "object" && "error" in detail) {
        const code = (detail as { error: unknown }).error;
        return typeof code === "string" ? code : null;
      }
    }
  } catch {
    return null;
  }
  return null;
}

async function refusal(response: Response): Promise<RefusedState> {
  if (response.status === 401) return { kind: "not_admitted", reason: "token_refused" };
  const code = await errorCode(response);
  if (response.status === 403) {
    return {
      kind: "not_admitted",
      reason: code === "source_ip_refused" ? "source_ip_refused" : "role_not_permitted",
    };
  }
  if (response.status === 503 && code === "admin_console_unconfigured") {
    return { kind: "not_admitted", reason: "console_unconfigured" };
  }
  return { kind: "unavailable", reason: "api_unreachable" };
}

/** One unauthenticated health endpoint of the admitted API base. */
export async function probe(fetch: FetchLike, url: string): Promise<Probe> {
  try {
    const response = await fetch(url, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    return { ok: true, status: response.status, body };
  } catch {
    return { ok: false, reason: "unreachable" };
  }
}

/**
 * Steps 1-3 of the order above for any admin read: no base or no bearer means
 * nothing is dialled; otherwise the one authorising call, whose refusal ends
 * the load. Only an admitted caller gets the body — and the base to read the
 * health endpoints from.
 */
export async function admit(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
  path: `/admin/${string}`;
}): Promise<RefusedState | { kind: "admitted"; apiBase: string; body: unknown }> {
  const { config, authorization, fetch, path } = args;
  if (config === null) return { kind: "unavailable", reason: "api_base_unconfigured" };
  if (authorization === null) return { kind: "not_admitted", reason: "no_credentials" };

  let response: Response;
  try {
    response = await fetch(`${config.apiBase}${path}`, {
      headers: { authorization, accept: "application/json" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS * 4),
    });
  } catch {
    return { kind: "unavailable", reason: "api_unreachable" };
  }
  if (response.status !== 200) return refusal(response);

  try {
    return { kind: "admitted", apiBase: config.apiBase, body: (await response.json()) as unknown };
  } catch {
    return { kind: "unavailable", reason: "payload_refused" };
  }
}

export async function loadOpsConsole(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<OpsConsoleState> {
  const { fetch } = args;
  const admitted = await admit({ ...args, path: "/admin/ops" });
  if (admitted.kind !== "admitted") return admitted;
  const payload = admitted.body as OpsPayload;
  const base = admitted.apiBase;

  const [healthz, readyz, version] = await Promise.all([
    probe(fetch, `${base}/healthz`),
    probe(fetch, `${base}/readyz`),
    probe(fetch, `${base}/version`),
  ]);
  const health: HealthResponses = { healthz, readyz, version };
  try {
    return { kind: "console", view: renderOps(payload, health) };
  } catch (error) {
    if (error instanceof OpsPayloadRefused || error instanceof TypeError) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}
