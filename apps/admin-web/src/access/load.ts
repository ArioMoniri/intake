/**
 * INT-366 — the access review page's server-side loader.
 *
 * The same order as every rendered console page (`../ops/load.ts`): no
 * configured API base or no bearer means nothing is dialled; `GET
 * /admin/access/review` with the caller's bearer is the one authorising call,
 * and the API's INT-180 gate decides who sees anything. Two 503s are this
 * page's own and are named rather than folded into "unreachable": the console
 * has no Keycloak/OpenBao admin access yet, or the directory could not be read.
 *
 * A payload the view-model refuses is `unavailable` — never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { refusal, type FetchLike, type RefusedState } from "../ops/load";
import {
  AccessPayloadRefused,
  renderAccessReview,
  type AccessReviewPayload,
  type AccessView,
} from "./module";

export type AccessUnconfigured = "access_review_unconfigured" | "directory_unavailable";

export type AccessState =
  | RefusedState
  | { kind: "identity_unavailable"; reason: AccessUnconfigured }
  | { kind: "console"; view: AccessView };

const TIMEOUT_MS = 20000;

/** The API's machine code: `{"error": code}` (services/api's exception
 * handler flattens `HTTPException.detail`). */
async function apiCode(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === "object" && "error" in body) {
      const code = (body as { error: unknown }).error;
      return typeof code === "string" ? code : null;
    }
  } catch {
    return null;
  }
  return null;
}

export async function loadAccessReview(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
  dayUnit: string;
}): Promise<AccessState> {
  const { config, authorization, fetch } = args;
  if (config === null) return { kind: "unavailable", reason: "api_base_unconfigured" };
  if (authorization === null) return { kind: "not_admitted", reason: "no_credentials" };
  let response: Response;
  try {
    response = await fetch(`${config.apiBase}/admin/access/review`, {
      headers: { authorization, accept: "application/json" },
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { kind: "unavailable", reason: "api_unreachable" };
  }
  if (response.status === 503) {
    const code = await apiCode(response.clone());
    if (code === "access_review_unconfigured" || code === "directory_unavailable") {
      return { kind: "identity_unavailable", reason: code };
    }
  }
  if (response.status !== 200) return refusal(response);
  try {
    const payload = (await response.json()) as AccessReviewPayload;
    return { kind: "console", view: renderAccessReview(payload, args.dayUnit) };
  } catch (error) {
    if (
      error instanceof AccessPayloadRefused ||
      error instanceof TypeError ||
      error instanceof SyntaxError
    ) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}
