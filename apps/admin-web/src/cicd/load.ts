/**
 * INT-187 — the CI/CD page's server-side loader.
 *
 * The same admission step as every rendered console page (`../ops/load`): no
 * configured API base or no bearer means nothing is dialled; `GET /admin/cicd`
 * with the caller's bearer is the one authorising call, and its refusal ends
 * the load. A payload the view-model refuses is `unavailable` — never
 * half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { OpsPayloadRefused } from "../ops/guards";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import { isResultCode, type ResultCode } from "./actions";
import { renderCicd, type CicdPayload, type CicdView } from "./module";

export type CicdState = RefusedState | { kind: "console"; view: CicdView };

export async function loadCicd(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<CicdState> {
  const admitted = await admit({ ...args, path: "/admin/cicd" });
  if (admitted.kind !== "admitted") return admitted;
  try {
    return { kind: "console", view: renderCicd(admitted.body as CicdPayload) };
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
