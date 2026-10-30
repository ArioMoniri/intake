/**
 * INT-565 — the Protocols page's server-side loader.
 *
 * The order every rendered console page keeps (`../ops/load`): no API base or
 * no bearer means nothing is dialled; `GET /admin/protocols` with the caller's
 * bearer is the one authorising call, and the API's INT-180 gate (role matrix,
 * IP allow-list, audit) decides who sees anything. A body the view-model
 * refuses — an L0 pack counted as coverage, an author approving their own
 * proposal, a clip under `typed` — is `unavailable`, never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { admitAndRender, type FetchLike, type RefusedState } from "../ops/load";
import { renderProtocolsModule, type ProtocolsPresentation } from "./module";

export type ProtocolsState = RefusedState | { kind: "console"; view: ProtocolsPresentation };

export function loadProtocols(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<ProtocolsState> {
  return admitAndRender(args, "/admin/protocols", renderProtocolsModule);
}
