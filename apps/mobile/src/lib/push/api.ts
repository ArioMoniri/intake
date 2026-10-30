/**
 * INT-583 — the push-token seam: register this device for new-sign-in
 * notices, and drop it again.
 *
 * The server keys the token to the device this session signed in from, so the
 * body names a platform and a token and nothing else: the client cannot
 * choose which device it is. iOS only — Android cannot sign in on a real
 * build (HB-A3), so no other platform is ever sent.
 *
 * The fetch is injected, so this module imports nothing native. A token that
 * does not have the APNs shape is refused here and never sent.
 */
import { errorDetail, type AuthedFetch } from "../sessions/api";
import { isApnsDeviceToken } from "./plan";

const PUSH_TOKEN = "/v1/auth/push-token";

export type PushTokenResult =
  { ok: true } | { ok: false; error: "session_unbound" | "invalid_token" | "unreachable" };

const UNREACHABLE: PushTokenResult = { ok: false, error: "unreachable" };

export async function putPushToken(fetcher: AuthedFetch, token: string): Promise<PushTokenResult> {
  if (!isApnsDeviceToken(token)) {
    return { ok: false, error: "invalid_token" };
  }
  try {
    const response = await fetcher(PUSH_TOKEN, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform: "ios", token }),
    });
    if (response.ok) {
      return { ok: true };
    }
    if (response.status === 422) {
      return { ok: false, error: "invalid_token" };
    }
    if (response.status === 409 && (await errorDetail(response)).error === "session_unbound") {
      return { ok: false, error: "session_unbound" };
    }
    return UNREACHABLE;
  } catch {
    return UNREACHABLE;
  }
}

/** Idempotent on the server: a device with no registration is already done. */
export async function deletePushToken(fetcher: AuthedFetch): Promise<PushTokenResult> {
  try {
    const response = await fetcher(PUSH_TOKEN, { method: "DELETE" });
    return response.ok ? { ok: true } : UNREACHABLE;
  } catch {
    return UNREACHABLE;
  }
}
