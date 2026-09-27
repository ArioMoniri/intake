/**
 * INT-181 — the overview page's server-side loader.
 *
 * The same order as the ops console (INT-351, `../ops/load.ts`), through the
 * same admission step: no configured API base or no bearer means nothing is
 * dialled; `GET /admin/reliability` with the caller's bearer is the one
 * authorising call, and its refusal ends the load — a refused caller does not
 * learn the API's readiness either. Only then `/readyz` of the same base, for
 * the API-readiness tile, which may independently be unknown.
 *
 * A payload the view-model refuses is `unavailable` — never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { OpsPayloadRefused } from "../ops/guards";
import { admit, probe, type FetchLike, type RefusedState } from "../ops/load";
import { renderOverview, type OverviewView, type ReliabilityPayload } from "./module";

export type OverviewState = RefusedState | { kind: "console"; view: OverviewView };

export async function loadOverview(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<OverviewState> {
  const admitted = await admit({ ...args, path: "/admin/reliability" });
  if (admitted.kind !== "admitted") return admitted;
  const readyz = await probe(args.fetch, `${admitted.apiBase}/readyz`);
  try {
    return { kind: "console", view: renderOverview(admitted.body as ReliabilityPayload, readyz) };
  } catch (error) {
    if (error instanceof OpsPayloadRefused || error instanceof TypeError) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}
