/**
 * Reconnect policy (INT-103 acceptance: "reconnect resumes session"). Pure,
 * with the clock and the jitter both injected, so every delay this produces
 * is asserted exactly rather than slept through.
 *
 * The interesting constraint is the token, not the backoff. INT-090 caps room
 * tokens at 600 s (`TOKEN_TTL_S`), which is SHORTER than a bad-network outage
 * can easily be. So a resume has two distinct shapes:
 *
 *   - `resume`  — the held token is still valid with margin; rejoin with it.
 *   - `remint`  — the token has expired or is about to; fetch a fresh one
 *                 from the API first, then rejoin.
 *
 * Getting this wrong is what makes a reconnect loop that never succeeds:
 * retrying a dead token forever, each attempt failing for a reason no amount
 * of backoff fixes. The margin below exists so we re-mint slightly early
 * rather than racing the expiry.
 *
 * The session is resumed, never restarted: the room name is derived from the
 * session id (`intake-<session uuid>`), so a fresh token rejoins the SAME
 * room and the server-side Talker keeps its state. The client contributes no
 * dialogue state to the resume — invariant 9 keeps that server-side.
 */

/** Base delay before the first retry. */
export const BASE_DELAY_MS = 500;
/** Ceiling on any single delay — a patient mid-intake is waiting. */
export const MAX_DELAY_MS = 8_000;
/** After this many consecutive failures we stop and fall back honestly. */
export const MAX_ATTEMPTS = 6;
/**
 * Re-mint this far before the token actually expires. Covers the round trip
 * to the API plus clock skew between phone and server.
 */
export const TOKEN_REFRESH_MARGIN_MS = 30_000;

export type ReconnectDecision =
  | { readonly action: "resume"; readonly attempt: number; readonly delayMs: number }
  | { readonly action: "remint"; readonly attempt: number; readonly delayMs: number }
  | { readonly action: "give_up"; readonly attempt: number };

export interface ReconnectInput {
  /** 1 for the first retry after a drop. */
  readonly attempt: number;
  /** Epoch millis the held token expires at. */
  readonly tokenExpiresAtMs: number;
  /** Epoch millis now. */
  readonly nowMs: number;
  /** Deterministic in tests; Math.random in wiring. Must return [0,1). */
  readonly jitter: () => number;
}

/**
 * Exponential backoff with FULL jitter (delay is uniform in [0, capped]),
 * which is what keeps a fleet of phones on a flapping network from
 * synchronising their retries into a thundering herd.
 */
export function backoffDelayMs(attempt: number, jitter: () => number): number {
  const capped = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * 2 ** (attempt - 1));
  return Math.floor(capped * jitter());
}

export function nextReconnect(input: ReconnectInput): ReconnectDecision {
  const { attempt, tokenExpiresAtMs, nowMs, jitter } = input;
  if (attempt > MAX_ATTEMPTS) {
    // Honest stop. The caller surfaces the typed fallback rather than
    // pretending a session is still alive (invariant 17: no silent fake).
    return { action: "give_up", attempt };
  }
  const delayMs = backoffDelayMs(attempt, jitter);
  const stale = tokenExpiresAtMs - nowMs <= TOKEN_REFRESH_MARGIN_MS;
  return { action: stale ? "remint" : "resume", attempt, delayMs };
}

/** True when a held token should be replaced before the next join attempt. */
export function tokenNeedsRemint(tokenExpiresAtMs: number, nowMs: number): boolean {
  return tokenExpiresAtMs - nowMs <= TOKEN_REFRESH_MARGIN_MS;
}
