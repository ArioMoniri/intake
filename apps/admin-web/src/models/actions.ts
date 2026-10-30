/**
 * INT-564 — the Models page's one control: trigger a benchmark lane for one
 * registry row (`POST /admin/models/{component}/benchmark`, the tier-1
 * `admin.models.benchmark.run`, INT-183).
 *
 * The page is script-free, so the control is a plain form posting to this
 * app's own `/models/action`, which forwards to the admin API with the
 * caller's bearer. This module decides only what may be sent:
 *
 * - **Same origin only.** A post whose `Sec-Fetch-Site` is not `same-origin`
 *   is refused before anything is read.
 * - **A registry id and a lane, nothing else.** The component must be
 *   id-shaped (the registry decides whether it exists) and the lane one of
 *   `latency` or `quality`; the body is exactly `{kind}`. The quality lane is
 *   offered only where the API marks it enabled, and today it refuses
 *   (`no_named_corpus`, HB-C10) — a figure over an unnamed set is the accuracy
 *   claim invariant 20 forbids.
 *
 * The outcome is always a code from {@link BENCHMARK_RESULTS} — never the
 * API's prose and never a submitted value (invariant 6).
 */
import type { OpsConfig } from "../ops/access";
import type { FetchLike } from "../ops/load";
import { REASON } from "../ops/guards";

export const BENCHMARK_KINDS = ["latency", "quality"] as const;
export type BenchmarkKindName = (typeof BENCHMARK_KINDS)[number];

/** A registry component id: the API's own `{component}` path segment shape. */
export const COMPONENT = /^[a-z0-9][a-z0-9_.-]{0,63}$/;

export const BENCHMARK_RESULTS = [
  "benchmark_requested",
  "cross_site_refused",
  "api_base_unconfigured",
  "no_credentials",
  "action_unknown",
  "api_unreachable",
  "api_refused",
  "token_refused",
  "forbidden",
  "unknown_component",
  "unknown_kind",
  "unexpected_field",
  "no_named_corpus",
] as const;
export type BenchmarkResult = (typeof BENCHMARK_RESULTS)[number];

function isResult(value: unknown): value is BenchmarkResult {
  return typeof value === "string" && (BENCHMARK_RESULTS as readonly string[]).includes(value);
}

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value : "";
}

async function apiCode(response: Response): Promise<BenchmarkResult> {
  try {
    const body = (await response.json()) as unknown;
    if (body !== null && typeof body === "object") {
      const record = body as Record<string, unknown>;
      const nested = record["detail"];
      const code =
        record["error"] ??
        (nested !== null && typeof nested === "object"
          ? (nested as Record<string, unknown>)["error"]
          : undefined);
      if (typeof code === "string" && REASON.test(code) && isResult(code)) return code;
    }
  } catch {
    return "api_refused";
  }
  return "api_refused";
}

const TIMEOUT_MS = 30_000;

export async function submitBenchmark(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetchSite: string | null;
  form: FormData;
  fetch: FetchLike;
}): Promise<{ code: BenchmarkResult }> {
  const { config, authorization, fetchSite, form, fetch } = args;
  if (fetchSite !== "same-origin") return { code: "cross_site_refused" };
  if (config === null) return { code: "api_base_unconfigured" };
  if (authorization === null) return { code: "no_credentials" };
  const component = field(form, "component");
  const kind = field(form, "kind");
  if (!COMPONENT.test(component) || !(BENCHMARK_KINDS as readonly string[]).includes(kind)) {
    return { code: "action_unknown" };
  }
  let response: Response;
  try {
    response = await fetch(`${config.apiBase}/admin/models/${component}/benchmark`, {
      method: "POST",
      headers: { authorization, accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify({ kind }),
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    return { code: "api_unreachable" };
  }
  if (response.status === 200) return { code: "benchmark_requested" };
  if (response.status === 401) return { code: "token_refused" };
  return { code: await apiCode(response) };
}
