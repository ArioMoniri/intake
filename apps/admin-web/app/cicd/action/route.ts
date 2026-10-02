/**
 * INT-187 — `POST /cicd/action`, where the CI/CD page's forms land.
 *
 * Server-side only: the form is read here, `submitCicdAction` refuses a
 * cross-site post, a missing bearer or a value the API would refuse, forwards
 * the rest to the admin API with the caller's bearer, and the browser is
 * redirected back to `/cicd` with a result *code* — never text, never a
 * submitted value (invariant 6). 303, so a reload does not re-post.
 */
import { submitCicdAction, type ResultCode } from "../../../src/cicd/actions";
import { bearerFrom, opsConfigFromEnv } from "../../../src/ops/access";

export async function POST(request: Request): Promise<Response> {
  let code: ResultCode;
  let lang: string | null = null;
  try {
    const form = await request.formData();
    lang = form.get("lang") === "en" ? "en" : null;
    ({ code } = await submitCicdAction({
      config: opsConfigFromEnv(process.env),
      authorization: bearerFrom(request.headers),
      fetchSite: request.headers.get("sec-fetch-site"),
      form,
      fetch: (url, init) => fetch(url, init),
    }));
  } catch {
    code = "action_unknown";
  }
  const target = new URL("/cicd", request.url);
  target.searchParams.set("result", code);
  if (lang !== null) target.searchParams.set("lang", lang);
  return Response.redirect(target, 303);
}
