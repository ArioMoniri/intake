/**
 * INT-563 (ADR-043) — `GET /step-up/callback`, Keycloak's redirect back.
 *
 * Server-side only. `completeStepUp` relays `state` and `code` to the admin
 * API, which redeems the code with the PKCE verifier it holds and verifies the
 * ID token; the one-time grant it answers is presented on the action's own
 * approve route at once. The browser is sent (303) to the action's page with
 * one code, and the return cookie is cleared. Nothing in the query is echoed.
 *
 * A GET that approves is safe here only because nothing in it is the
 * console's to trust: the ceremony is bound to the caller's own Keycloak
 * subject and session, the code to a verifier the browser never held, and
 * the grant to one action — a forged callback carries none of them.
 */
import { bearerFrom, opsConfigFromEnv } from "../../../src/ops/access";
import type { Page } from "../../../src/step-up/approvals";
import { completeStepUp } from "../../../src/step-up/flow";
import type { StepUpResult } from "../../../src/step-up/results";
import { RETURN_COOKIE, destination, returnFrom } from "../../../src/step-up/return";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const back = returnFrom(request.headers.get("cookie"));
  let outcome: { code: StepUpResult; page: Page };
  try {
    outcome = await completeStepUp({
      config: opsConfigFromEnv(process.env),
      authorization: bearerFrom(request.headers),
      query: new URL(request.url).searchParams,
      fallback: back.page,
      fetch: (url, init) => fetch(url, init),
    });
  } catch {
    outcome = { code: "api_refused", page: back.page };
  }
  const headers = new Headers({
    location: destination(request.url, outcome.page, back.lang, outcome.code).href,
  });
  headers.append(
    "set-cookie",
    `${RETURN_COOKIE}=; Path=/step-up; Max-Age=0; HttpOnly; SameSite=Lax`,
  );
  return new Response(null, { status: 303, headers });
}
