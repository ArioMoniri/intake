/**
 * INT-562 — `POST /safety-queue/action`, where the acknowledgement form lands.
 *
 * Server-side only: the form is read here, `submitAcknowledge` refuses a
 * cross-site post, a missing bearer or an entry id the API would refuse,
 * forwards the id alone to the admin API with the caller's bearer, and the
 * browser is redirected back to `/safety-queue` with a result *code* — never
 * text, never a submitted value (invariant 6). 303, so a reload does not
 * re-post.
 */
import { bearerFrom, opsConfigFromEnv } from "../../../src/ops/access";
import { submitAcknowledge, type ResultCode } from "../../../src/safety-queue/actions";

export async function POST(request: Request): Promise<Response> {
  let code: ResultCode;
  let lang: string | null = null;
  try {
    const form = await request.formData();
    lang = form.get("lang") === "en" ? "en" : null;
    ({ code } = await submitAcknowledge({
      config: opsConfigFromEnv(process.env),
      authorization: bearerFrom(request.headers),
      fetchSite: request.headers.get("sec-fetch-site"),
      form,
      fetch: (url, init) => fetch(url, init),
    }));
  } catch {
    code = "action_unknown";
  }
  const target = new URL("/safety-queue", request.url);
  target.searchParams.set("result", code);
  if (lang !== null) target.searchParams.set("lang", lang);
  return Response.redirect(target, 303);
}
