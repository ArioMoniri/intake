/**
 * INT-428 — `POST /model-lanes/action`, where the Model lanes page's forms
 * land.
 *
 * Server-side only: the form is read here, `submitModelLanesAction` refuses a
 * cross-site post, a missing bearer or a value the API would refuse, forwards
 * the rest to the admin API with the caller's bearer, and the browser is
 * redirected back to `/model-lanes` with a result *code* — never text, never
 * a submitted value (invariant 6). A provider key lives in the form data and
 * the one request body built from it, and nowhere else: a staged key's last
 * four, as the API answered them, go back in a one-shot HttpOnly cookie
 * rather than the URL. 303, so a reload does not re-post.
 */
import {
  stagedCookie,
  submitModelLanesAction,
  type Outcome,
} from "../../../src/model-lanes/actions";
import { bearerFrom, opsConfigFromEnv } from "../../../src/ops/access";

export async function POST(request: Request): Promise<Response> {
  let outcome: Outcome;
  let lang: string | null = null;
  try {
    const form = await request.formData();
    lang = form.get("lang") === "en" ? "en" : null;
    outcome = await submitModelLanesAction({
      config: opsConfigFromEnv(process.env),
      authorization: bearerFrom(request.headers),
      fetchSite: request.headers.get("sec-fetch-site"),
      form,
      fetch: (url, init) => fetch(url, init),
    });
  } catch {
    outcome = { code: "action_unknown" };
  }
  const target = new URL("/model-lanes", request.url);
  target.searchParams.set("result", outcome.code);
  if (lang !== null) target.searchParams.set("lang", lang);
  const headers = new Headers({ location: target.toString() });
  if (outcome.staged !== undefined) headers.append("set-cookie", stagedCookie(outcome.staged));
  return new Response(null, { status: 303, headers });
}
