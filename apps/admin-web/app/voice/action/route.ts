/**
 * INT-182 — `POST /voice/action`, where the Voice page's forms land.
 *
 * Server-side only: the form is read here, `submitVoiceAction` refuses a
 * cross-site post, a missing bearer or a value the API would refuse, forwards
 * the rest to the admin API with the caller's bearer, and the browser is
 * redirected back to `/voice` with a result *code* — never text, never a
 * submitted value (invariant 6). 303, so a reload does not re-post.
 */
import { bearerFrom, opsConfigFromEnv } from "../../../src/ops/access";
import { submitVoiceAction, type ResultCode } from "../../../src/voice/actions";

export async function POST(request: Request): Promise<Response> {
  let code: ResultCode;
  let lang: string | null = null;
  try {
    const form = await request.formData();
    lang = form.get("lang") === "en" ? "en" : null;
    ({ code } = await submitVoiceAction({
      config: opsConfigFromEnv(process.env),
      authorization: bearerFrom(request.headers),
      fetchSite: request.headers.get("sec-fetch-site"),
      form,
      fetch: (url, init) => fetch(url, init),
    }));
  } catch {
    code = "action_unknown";
  }
  const target = new URL("/voice", request.url);
  target.searchParams.set("result", code);
  if (lang !== null) target.searchParams.set("lang", lang);
  return Response.redirect(target, 303);
}
