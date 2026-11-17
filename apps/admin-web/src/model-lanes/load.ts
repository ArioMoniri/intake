/**
 * INT-428 — the Model lanes page's server-side loader.
 *
 * The same admission step as every rendered console page (`../ops/load`): no
 * configured API base or no bearer means nothing is dialled; `GET
 * /admin/model-lanes` with the caller's bearer is the one authorising call,
 * and its refusal ends the load. A payload the view-model refuses is
 * `unavailable` — never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { OpsPayloadRefused } from "../ops/guards";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import { isResultCode, type ResultCode, type StagedKey } from "./actions";
import { renderModelLanes, type ModelLanesPayload, type ModelLanesView } from "./module";
import { LAST4, PROVIDERS, type ProviderId } from "./payload";

export type ModelLanesState = RefusedState | { kind: "console"; view: ModelLanesView };

export async function loadModelLanes(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<ModelLanesState> {
  const admitted = await admit({ ...args, path: "/admin/model-lanes" });
  if (admitted.kind !== "admitted") return admitted;
  try {
    return { kind: "console", view: renderModelLanes(admitted.body as ModelLanesPayload) };
  } catch (error) {
    if (error instanceof OpsPayloadRefused || error instanceof TypeError) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}

/**
 * The `?result=` a form post redirected back with — shown only when it is one
 * of the codes the handler can produce. A query string is attacker-writable,
 * and the page reflects codes, never text.
 */
export function resultFrom(value: string | string[] | undefined): ResultCode | null {
  return typeof value === "string" && isResultCode(value) ? value : null;
}

/** The staged-key cookie (`./actions` `stagedCookie`), when it is exactly a
 * provider and four key characters; anything else is dropped. */
export function stagedFrom(value: string | undefined): StagedKey | null {
  if (typeof value !== "string") return null;
  const dot = value.indexOf(".");
  const provider = value.slice(0, dot);
  const last4 = value.slice(dot + 1);
  if (dot < 1 || !(PROVIDERS as readonly string[]).includes(provider) || !LAST4.test(last4)) {
    return null;
  }
  return { provider: provider as ProviderId, last4 };
}
