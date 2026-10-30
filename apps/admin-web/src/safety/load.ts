/**
 * INT-565 — the Clinical quality & safety page's server-side loader.
 *
 * `GET /admin/quality-safety` with the caller's bearer is the one authorising
 * call (`../ops/load` order: no base or no bearer, nothing is dialled). A body
 * the view-model refuses — a routing count not from the rules engine, a
 * false-RED downgrade, a leaked transcript, a PolicyGuard count with no scrape
 * behind it — is `unavailable`, never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { admitAndRender, type FetchLike, type RefusedState } from "../ops/load";
import { renderQualitySafetyModule, type QualitySafetyPresentation } from "./module";

export type QualitySafetyState =
  RefusedState | { kind: "console"; view: QualitySafetyPresentation };

export function loadQualitySafety(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<QualitySafetyState> {
  return admitAndRender(args, "/admin/quality-safety", renderQualitySafetyModule);
}
