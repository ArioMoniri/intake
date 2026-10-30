/**
 * INT-564 — the Models & self-hosting registry page's server-side loader.
 *
 * The same order as every rendered console page (`../ops/load`): no API base
 * or no bearer means nothing is dialled; `GET /admin/models` with the caller's
 * bearer is the one authorising call (platform-scope roles), and its refusal
 * ends the load. A payload that claims a clear release over a blocking row is
 * refused by the view-model (`InconsistentReleaseState`) and the page is
 * `unavailable` — a green console bought by a stale or tampered body is worse
 * than none.
 */
import type { OpsConfig } from "../ops/access";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import { BENCHMARK_RESULTS, type BenchmarkResult } from "./actions";
import { UnlabelledMeasurement } from "./measurement";
import {
  InconsistentReleaseState,
  renderModelsModule,
  type ModelsPayload,
  type ModelsPresentation,
} from "./module";

export type ModelsState = RefusedState | { kind: "console"; view: ModelsPresentation };

export async function loadModels(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<ModelsState> {
  const admitted = await admit({ ...args, path: "/admin/models" });
  if (admitted.kind !== "admitted") return admitted;
  try {
    return { kind: "console", view: renderModelsModule(admitted.body as ModelsPayload) };
  } catch (error) {
    if (
      error instanceof InconsistentReleaseState ||
      error instanceof UnlabelledMeasurement ||
      error instanceof TypeError
    ) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}

/** The `?result=` a benchmark post came back with, only when it is one of ours. */
export function benchmarkResultFrom(value: string | string[] | undefined): BenchmarkResult | null {
  return typeof value === "string" && (BENCHMARK_RESULTS as readonly string[]).includes(value)
    ? (value as BenchmarkResult)
    : null;
}
