/**
 * INT-563 (ADR-043) — where the approver lands when the step-up comes back.
 *
 * Keycloak returns to `/step-up/callback`, which knows the action (and so the
 * page) only once the API has completed the ceremony. For the answers that
 * come before that — a cancelled login, an unreachable API — the start route
 * leaves a five-minute cookie naming the page the form was on and the
 * language: two closed values, no id, nothing the API needs. A cookie that is
 * missing or not one of those values lands on `/step-up` in Turkish.
 */
import type { Lang } from "../ops/copy";
import { isPage, type Page } from "./approvals";
import type { StepUpResult } from "./results";

export const RETURN_COOKIE = "intake_step_up_return";
const MAX_AGE_S = 300;

export function returnCookie(page: Page, lang: Lang, secure: boolean): string {
  const flags = `Path=/step-up; Max-Age=${MAX_AGE_S}; HttpOnly; SameSite=Lax`;
  return `${RETURN_COOKIE}=${page}.${lang}; ${flags}${secure ? "; Secure" : ""}`;
}

export function returnFrom(cookieHeader: string | null): { page: Page; lang: Lang } {
  for (const part of (cookieHeader ?? "").split(";")) {
    const [name, value] = part.trim().split("=", 2);
    if (name !== RETURN_COOKIE || value === undefined) continue;
    const [page, lang] = value.split(".", 2);
    if (isPage(page) && (lang === "tr" || lang === "en")) return { page, lang };
  }
  return { page: "step-up", lang: "tr" };
}

/** The page URL a step-up outcome is shown on (same origin as `base`). */
export function destination(base: string, page: Page, lang: Lang, code: StepUpResult): URL {
  const target = new URL(`/${page}`, base);
  target.searchParams.set("step_up", code);
  if (lang === "en") target.searchParams.set("lang", "en");
  return target;
}
