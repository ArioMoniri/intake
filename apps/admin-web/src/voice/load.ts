/**
 * INT-182 — the Voice page's server-side loader.
 *
 * The same admission step as the ops console and the overview (`../ops/load`):
 * no configured API base or no bearer means nothing is dialled; `GET
 * /admin/voice` with the caller's bearer is the one authorising call, and its
 * refusal ends the load. A payload the view-model refuses is `unavailable` —
 * never half-painted.
 */
import type { OpsConfig } from "../ops/access";
import { OpsPayloadRefused } from "../ops/guards";
import { admit, type FetchLike, type RefusedState } from "../ops/load";
import { isResultCode, type ResultCode } from "./actions";
import { renderVoice, type VoicePayload, type VoiceView } from "./module";

export type VoiceState = RefusedState | { kind: "console"; view: VoiceView };

export async function loadVoice(args: {
  config: OpsConfig | null;
  authorization: string | null;
  fetch: FetchLike;
}): Promise<VoiceState> {
  const admitted = await admit({ ...args, path: "/admin/voice" });
  if (admitted.kind !== "admitted") return admitted;
  try {
    return { kind: "console", view: renderVoice(admitted.body as VoicePayload) };
  } catch (error) {
    if (error instanceof OpsPayloadRefused || error instanceof TypeError) {
      return { kind: "unavailable", reason: "payload_refused" };
    }
    throw error;
  }
}

/**
 * The `?result=` a form post redirected back with — shown only when it is one
 * of the codes the handler can produce. Anything else is dropped: a query
 * string is attacker-writable, and the page reflects codes, never text.
 */
export function resultFrom(value: string | string[] | undefined): ResultCode | null {
  return typeof value === "string" && isResultCode(value) ? value : null;
}
