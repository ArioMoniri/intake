/**
 * INT-140 — the data-subject-rights seam (INT-037's `/v1/me/dsar/*`).
 *
 * Transport only; every rule about what a request MEANS lives in
 * `./requests.ts` so it stays testable without a network.
 *
 * Failure posture follows the INT-132 consent seam and the INT-141 preference
 * seam: an unreachable route or a refusal resolves to `null`, and the caller
 * says the request has not been sent. Nothing here fakes a filing — an
 * obligation the controller never received is not an obligation, and showing
 * one would tell the patient their m.11 clock is running when it is not. No
 * server narrative ever reaches the screen (02 §8.2).
 *
 * `GET /v1/me/dsar/export/{id}` is deliberately absent. It is the DELIVERY of
 * the answer, and issuing it marks the m.13 obligation completed — while the
 * document itself cannot render until the fixed strings exist in
 * `docs/legal/` (invariant 18; INT-210), and this app has no path that hands
 * a file to the patient. Calling it would record an answer nobody received.
 * `e2e/me.spec.ts` asserts the absence.
 */
import { authedFetch } from "@/lib/auth/api";
import type { PasskeyPorts } from "@/lib/auth/passkey/ceremony";
import { defaultPasskeyPorts, withStepUp } from "@/lib/auth/passkey/stepUp";

import { parseRequest, parseRequests, type DsarRequest } from "./requests";

const POST: RequestInit = { method: "POST", headers: { "Content-Type": "application/json" } };

export interface ErasureFiling {
  request: DsarRequest;
  /**
   * Whether filing the erasure closed any live share (files/06 §2.3). A FACT,
   * not a count: the screen says shares were closed and never prints a
   * numeral, so no number crosses into patient copy (invariant 22).
   */
  sharesCancelled: boolean;
}

async function body(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** File an access request. Null = the controller did not receive it. */
export async function fileExportRequest(): Promise<DsarRequest | null> {
  try {
    const response = await authedFetch("/v1/me/dsar/export", POST);
    return response.ok ? parseRequest(await body(response)) : null;
  } catch {
    return null;
  }
}

/**
 * What filing an erasure ended as. INT-582 (D36): data delete steps up to
 * the patient's passkey, so beside "filed" and "unsent" there are two more
 * true sentences — the step-up was refused (a person can review it: the
 * manual path), or the patient cancelled the passkey sheet themselves.
 */
export type ErasureOutcome =
  | { kind: "filed"; filing: ErasureFiling }
  | { kind: "unsent" }
  | { kind: "step_up_refused" }
  | { kind: "cancelled" };

/** File an erasure, stepping up to the passkey when the server asks for it. */
export async function fileErasureWithStepUp(
  ports: PasskeyPorts = defaultPasskeyPorts,
): Promise<ErasureOutcome> {
  try {
    const sent = await withStepUp(
      "data_delete",
      (headers) =>
        authedFetch("/v1/me/dsar/delete", {
          ...POST,
          headers: { "Content-Type": "application/json", ...headers },
        }),
      ports,
    );
    if (sent.kind === "refused") {
      return { kind: "step_up_refused" };
    }
    if (sent.kind === "cancelled") {
      return { kind: "cancelled" };
    }
    if (!sent.response.ok) {
      return { kind: "unsent" };
    }
    const payload = await body(sent.response);
    const request = parseRequest(payload);
    if (request === null) {
      return { kind: "unsent" };
    }
    const cancelled = (payload as Record<string, unknown>).shares_cancelled;
    return {
      kind: "filed",
      filing: { request, sharesCancelled: typeof cancelled === "number" && cancelled > 0 },
    };
  } catch {
    return { kind: "unsent" };
  }
}

/** File an erasure. The server starts the files/06 §3 grace and closes shares. */
export async function fileErasureRequest(
  ports: PasskeyPorts = defaultPasskeyPorts,
): Promise<ErasureFiling | null> {
  const outcome = await fileErasureWithStepUp(ports);
  return outcome.kind === "filed" ? outcome.filing : null;
}

/** Take a scheduled erasure back, inside its grace. Null = it still stands. */
export async function withdrawErasureRequest(id: string): Promise<DsarRequest | null> {
  try {
    const response = await authedFetch(`/v1/me/dsar/delete/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    return response.ok ? parseRequest(await body(response)) : null;
  } catch {
    return null;
  }
}

/** The patient's own m.13 clocks. Null = unreachable; claim nothing. */
export async function fetchDsarRequests(): Promise<DsarRequest[] | null> {
  try {
    const response = await authedFetch("/v1/me/dsar/requests");
    return response.ok ? parseRequests(await body(response)) : null;
  } catch {
    return null;
  }
}
