/**
 * INT-139 — the share-centre seam over INT-150's patient-side Doctor Link
 * routes (`services/api/src/intake_api/doctor_link/router.py`).
 *
 * Transport only; every rule about what a grant MEANS lives in `./links.ts`
 * so it stays testable without a network.
 *
 * **Three routes, and the reason the set stops there.** All three are
 * declared under the `core` consent purpose ALONE in INT-150's router — list,
 * revoke and the access log — which is what makes them reachable to a patient
 * who has withdrawn `share:previsit_note`. The two this module deliberately
 * omits enforce that purpose: `POST …/doctor-links` issues a grant and
 * returns the one body that carries a 128-bit bearer credential, and
 * `POST …/{id}/otp` mints an opening code whose delivery channel does not
 * exist (HB-O7). Neither is in INT-139's acceptance, and calling either would
 * put a credential in a patient app and imply a channel in the copy around
 * it. The absence is asserted in `e2e/shares.spec.ts`, not assumed.
 *
 * **Failure posture follows the INT-140 DSAR seam.** An unreachable route or
 * a refusal resolves to `null`, and the caller says so rather than showing an
 * empty list. "No one has access to your record" and "we could not ask" are
 * different sentences, and only one of them is safe to print when it is not
 * true.
 */
import { authedFetch } from "@/lib/auth/api";

import {
  parseAccessLog,
  parseShareLink,
  parseShareLinks,
  type AccessEntry,
  type ShareLink,
} from "./links";

const POST: RequestInit = { method: "POST", headers: { "Content-Type": "application/json" } };

function base(visitId: string): string {
  return `/v1/visits/${encodeURIComponent(visitId)}/note/doctor-links`;
}

async function body(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** Every grant over this visit's note — live, finished and stopped. */
export async function fetchShareLinks(visitId: string): Promise<ShareLink[] | null> {
  try {
    const response = await authedFetch(base(visitId));
    return response.ok ? parseShareLinks(await body(response)) : null;
  } catch {
    return null;
  }
}

/**
 * Stop one grant. The response IS the authoritative row, so the caller needs
 * no second read — which is the whole of this client's contribution to the
 * acceptance's revocation clause: no round trip of its own between the tap
 * and the state the redemption path checks.
 *
 * Null means the request did not land. It never means "stopped".
 */
export async function revokeShareLink(visitId: string, linkId: string): Promise<ShareLink | null> {
  try {
    const response = await authedFetch(
      `${base(visitId)}/${encodeURIComponent(linkId)}/revoke`,
      POST,
    );
    return response.ok ? parseShareLink(await body(response)) : null;
  } catch {
    return null;
  }
}

/** The patient's own access log for this note: roles, never identities. */
export async function fetchAccessLog(visitId: string): Promise<AccessEntry[] | null> {
  try {
    const response = await authedFetch(`${base(visitId)}/access-log`);
    return response.ok ? parseAccessLog(await body(response)) : null;
  } catch {
    return null;
  }
}
