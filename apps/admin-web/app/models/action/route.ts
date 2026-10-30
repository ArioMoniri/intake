/**
 * INT-564 — `POST /models/action`, where a registry row's benchmark lane lands.
 *
 * Server-side only: `submitBenchmark` refuses a cross-site post, a missing
 * bearer or a component or lane the API would refuse, forwards the rest to
 * `POST /admin/models/{component}/benchmark` with the caller's bearer, and the
 * browser is redirected back to `/models` with a result *code* — never text,
 * never a submitted value (invariant 6). 303, so a reload does not re-post.
 */
import { submitBenchmark, type BenchmarkResult } from "../../../src/models/actions";
import { bearerFrom, opsConfigFromEnv } from "../../../src/ops/access";

export async function POST(request: Request): Promise<Response> {
  let code: BenchmarkResult;
  let lang: string | null = null;
  try {
    const form = await request.formData();
    lang = form.get("lang") === "en" ? "en" : null;
    ({ code } = await submitBenchmark({
      config: opsConfigFromEnv(process.env),
      authorization: bearerFrom(request.headers),
      fetchSite: request.headers.get("sec-fetch-site"),
      form,
      fetch: (url, init) => fetch(url, init),
    }));
  } catch {
    code = "action_unknown";
  }
  const target = new URL("/models", request.url);
  target.searchParams.set("result", code);
  if (lang !== null) target.searchParams.set("lang", lang);
  return Response.redirect(target, 303);
}
