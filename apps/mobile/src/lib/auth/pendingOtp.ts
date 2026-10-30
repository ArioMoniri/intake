/**
 * INT-578: the request id the server answered the last OTP request with.
 *
 * A code is bound to it (and to this device's attestation key), so the verify
 * call has to send it back. It lives in module memory only — never
 * SecureStore, never a log line: it is good for the five minutes a code is,
 * and an app restart in between simply means asking for a new code. A
 * malformed id clears what was held rather than leaving a stale one to fail
 * later.
 */

const REQUEST_ID = /^[0-9a-f]{32}$/;

let pending: string | null = null;

/** Keep the id from an OTP request's 202 body (or clear it if the body has none). */
export function rememberOtpRequest(body: unknown): void {
  const candidate =
    typeof body === "object" && body !== null
      ? (body as { request_id?: unknown }).request_id
      : undefined;
  pending = typeof candidate === "string" && REQUEST_ID.test(candidate) ? candidate : null;
}

/** The id the live code is bound to, or null when there is none. */
export function pendingOtpRequestId(): string | null {
  return pending;
}

/** Drop it once the code is spent. */
export function forgetOtpRequest(): void {
  pending = null;
}
