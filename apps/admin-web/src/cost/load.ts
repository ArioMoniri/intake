/**
 * INT-565 — the Cost page's server-side loader.
 *
 * `GET /admin/cost` with the caller's bearer is the one authorising call
 * (`../ops/load` order: no base or no bearer, nothing is dialled). A body the
 * view-model refuses — a figure without a price or without observed usage, a
 * partial total, an unsound budget verdict — is `unavailable`, never
 * half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { admitAndRender, type FetchLike, type RefusedState } from "../ops/load";
import { renderCostModule, type CostPresentation } from "./module";

export type CostState = RefusedState | { kind: "console"; view: CostPresentation };

export function loadCost(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<CostState> {
  return admitAndRender(args, "/admin/cost", renderCostModule);
}
