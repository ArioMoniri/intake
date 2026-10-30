/**
 * INT-565 — the Security page's server-side loader.
 *
 * `GET /admin/security` with the caller's bearer is the one authorising call
 * (`../ops/load` order: no base or no bearer, nothing is dialled). A body the
 * view-model refuses — a SIEM count over an unwired feed, an egress count with
 * no scrape, a chain head on the console, a green chain with no anchor — is
 * `unavailable`, never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { admitAndRender, type FetchLike, type RefusedState } from "../ops/load";
import { renderSecurityModule, type SecurityPresentation } from "./module";

export type SecurityState = RefusedState | { kind: "console"; view: SecurityPresentation };

export function loadSecurity(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<SecurityState> {
  return admitAndRender(args, "/admin/security", renderSecurityModule);
}
