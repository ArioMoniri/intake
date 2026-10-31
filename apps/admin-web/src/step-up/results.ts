/**
 * INT-563 (ADR-043) — the closed set of outcomes a step-up can come back with.
 *
 * The start and callback routes redirect with `?step_up=<code>`; a page shows
 * the code's sentence only when the code is one of these. Anything else is
 * dropped — a query string is attacker-writable, and the page reflects codes,
 * never text (invariant 6).
 */
import { REASON } from "../ops/guards";

const LOCAL = [
  "approved",
  "step_up_cancelled",
  "cross_site_refused",
  "api_base_unconfigured",
  "no_credentials",
  "action_unknown",
  "api_unreachable",
  "api_refused",
  "token_refused",
] as const;

/** Codes the admin API answers a step-up or an approval with. */
const API = [
  "step_up_unknown",
  "step_up_not_fresh",
  "step_up_without_webauthn",
  "step_up_token_refused",
  "step_up_replayed",
  "step_up_exchange_failed",
  "step_up_unconfigured",
  "step_up_body_refused",
  "four_eyes_self_approval",
  "four_eyes_approver_role",
  "four_eyes_shared_credential",
  "four_eyes_shared_session",
  "four_eyes_shared_organisation",
  "four_eyes_expired",
  "four_eyes_already_decided",
  "four_eyes_assertion_reused",
  "not_found",
  "forbidden",
  "source_ip_refused",
  "admin_console_unconfigured",
] as const;

export const STEP_UP_RESULTS = [...LOCAL, ...API] as const;
export type StepUpResult = (typeof STEP_UP_RESULTS)[number];

export function isStepUpResult(value: unknown): value is StepUpResult {
  return typeof value === "string" && (STEP_UP_RESULTS as readonly string[]).includes(value);
}

/** The `?step_up=` a page was redirected back with, or `null`. */
export function stepUpResultFrom(value: string | string[] | undefined): StepUpResult | null {
  return isStepUpResult(value) ? value : null;
}

/** The API's refusal as one of the codes above; anything else is `api_refused`. */
export function apiResult(body: unknown): StepUpResult {
  if (body !== null && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const nested = record["detail"];
    const code =
      record["error"] ??
      (nested !== null && typeof nested === "object"
        ? (nested as Record<string, unknown>)["error"]
        : undefined);
    if (typeof code === "string" && REASON.test(code) && isStepUpResult(code)) return code;
  }
  return "api_refused";
}
