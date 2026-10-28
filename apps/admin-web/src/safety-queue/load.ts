/**
 * INT-562 — the Safety queue page's server-side loader.
 *
 * The same order as every rendered console page (`../ops/load.ts`): no
 * configured API base or no bearer means nothing is dialled; `GET
 * /admin/safety-queue` with the caller's bearer is the one authorising call,
 * and the API's INT-180 gate decides who sees anything. The inbox's own 503s
 * are this page's own and are named rather than folded into "unreachable":
 * no inbox wired, the store unreachable, or the store contended. None of them
 * is ever an empty queue, which would read as "nobody is waiting" (INT-406).
 *
 * A payload the view-model refuses is `unavailable` — never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { refusal, type FetchLike, type RefusedState } from "../ops/load";
import { isResultCode, type ResultCode } from "./actions";
import {
  SafetyQueuePayloadRefused,
  renderSafetyQueue,
  type SafetyQueuePayload,
  type SafetyQueueView,
} from "./module";

export const INBOX_UNAVAILABLE = [
  "safety_inbox_unconfigured",
  "safety_inbox_unreachable",
  "safety_inbox_contended",
] as const;
export type InboxUnavailable = (typeof INBOX_UNAVAILABLE)[number];

export type SafetyQueueState =
  | RefusedState
  | { kind: "inbox_unavailable"; reason: InboxUnavailable }
  | { kind: "console"; view: SafetyQueueView };

const TIMEOUT_MS = 20000;

/** The API's machine code: `{"error": code}`. */
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

function isInboxUnavailable(code: string | null): code is InboxUnavailable {
  return code !== null && (INBOX_UNAVAILABLE as readonly string[]).includes(code);
}

export async function loadSafetyQueue(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<SafetyQueueState> {
  const { config, authorization, fetch } = args;
  if (config === null) return { kind: "unavailable", reason: "api_base_unconfigured" };
  if (authorization === null) return { kind: "not_admitted", reason: "no_credentials" };
  let response: Response;
  try {
    response = await fetch(`${config.apiBase}/admin/safety-queue`, {
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
    if (isInboxUnavailable(code)) return { kind: "inbox_unavailable", reason: code };
  }
  if (response.status !== 200) return refusal(response);
  try {
    const payload = (await response.json()) as SafetyQueuePayload;
    return { kind: "console", view: renderSafetyQueue(payload) };
  } catch (error) {
    if (
      error instanceof SafetyQueuePayloadRefused ||
      error instanceof TypeError ||
      error instanceof SyntaxError
    ) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}

/** The `?result=` the form handler redirected back with — a code or nothing. */
export function resultFrom(value: string | string[] | undefined): ResultCode | null {
  return typeof value === "string" && isResultCode(value) ? value : null;
}
