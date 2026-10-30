/**
 * INT-583, review round four — the app's sign-out ends this device's session
 * on the server as well: its refresh family (and with it every access token),
 * its push token and its place among the account's known devices, so its next
 * sign-in counts as new and the patient's other devices are told.
 *
 * The one place the sessions seam is bound to `authedFetch`, which reaches the
 * secure store; session.tsx loads this module lazily so the provider stays
 * node-importable. What the call does is proved in api.test.ts.
 */
import { authedFetch } from "@/lib/auth/api";

import { createSessionsApi, type RevokeResult } from "./api";

/** Best-effort: the caller never waits on it and never shows its result. */
export function endThisDeviceSession(): Promise<RevokeResult> {
  return createSessionsApi(authedFetch).signOutThisDevice();
}
