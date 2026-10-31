/**
 * INT-563 (ADR-043) — `POST /step-up/start`, where every **Onayla** form lands.
 *
 * Server-side only. `beginStepUp` refuses a cross-site post or a missing
 * bearer, asks the admin API to open a ceremony for the one pending action,
 * and answers the Keycloak authorization URL only when it is the one ADR-043
 * describes on the configured origin. The browser is redirected there (303),
 * with a short cookie naming the page it came from; a refusal goes straight
 * back to that page with a code — never text, never a submitted value.
 */
import { bearerFrom, opsConfigFromEnv } from "../../../src/ops/access";
import type { Lang } from "../../../src/ops/copy";
import { beginStepUp, stepUpOriginFromEnv, type Begun } from "../../../src/step-up/flow";
import { destination, returnCookie } from "../../../src/step-up/return";

export async function POST(request: Request): Promise<Response> {
  let lang: Lang = "tr";
  let begun: Begun;
  try {
    const form = await request.formData();
    lang = form.get("lang") === "en" ? "en" : "tr";
    begun = await beginStepUp({
      config: opsConfigFromEnv(process.env),
      origin: stepUpOriginFromEnv(process.env),
      authorization: bearerFrom(request.headers),
      fetchSite: request.headers.get("sec-fetch-site"),
      form,
      fetch: (url, init) => fetch(url, init),
    });
  } catch {
    begun = { kind: "result", code: "action_unknown", page: "step-up" };
  }
  if (begun.kind === "result") {
    return Response.redirect(destination(request.url, begun.page, lang, begun.code), 303);
  }
  const secure =
    request.url.startsWith("https:") || request.headers.get("x-forwarded-proto") === "https";
  return new Response(null, {
    status: 303,
    headers: { location: begun.location, "set-cookie": returnCookie(begun.page, lang, secure) },
  });
}
