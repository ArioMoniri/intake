/**
 * Room-token client (INT-103). The phone never mints a token: the signing
 * secret is server-side and the grants are not negotiable from here.
 * `intake_platform.room_tokens.mint_room_token` (INT-090) is the only minter,
 * and it caps every token at `TOKEN_TTL_S = 600` seconds.
 *
 * SERVER STATUS, STATED PLAINLY: `mint_room_token` exists and is tested
 * (tests/voice/test_room_tokens.py) but is NOT yet wired to an HTTP route —
 * its only importer today is that test. So the path below is the contract
 * this client is written against, not an endpoint that answers yet. That is a
 * cross-issue dependency on the voice-runtime lane, recorded in
 * docs/evidence/INT-103.md; it is deliberately NOT worked around here. There
 * is no stub token, no dev fallback and no synthesised JWT anywhere in this
 * file — a missing endpoint surfaces as `token_unavailable` and the session
 * refuses to start (invariant 17: a missing dependency is reported, never
 * faked).
 *
 * Invariant 6: the request carries the session uuid in the path and nothing
 * else; the response is stored as an opaque string. The token is never
 * decoded, never inspected for its claims and never logged — not even at
 * debug level, since its payload names the room and its signature is a
 * bearer credential (invariant 14).
 */
import type { RoomCredentials, TokenSource } from "./types";

/** Canonical lowercase UUID — the same id shape room_tokens.py enforces. */
const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** Room names are `intake-<session uuid>` and derive from ids only (INT-090). */
export const ROOM_PREFIX = "intake-";

/** The route this client calls. One session's token, minted per request. */
export function voiceTokenPath(sessionId: string): string {
  return `/v1/visits/${sessionId}/voice-token`;
}

export class RoomTokenError extends Error {}

/** What the API is expected to return. Validated before use — never trusted. */
interface TokenResponseBody {
  readonly url?: unknown;
  readonly token?: unknown;
  readonly room?: unknown;
  readonly expires_at_ms?: unknown;
}

/**
 * Validate a token response into credentials.
 *
 * Pure and exported so the contract is asserted in tests without a network.
 * Every field is checked: a response that omits the expiry, or names a room
 * that is not this session's, is refused rather than half-used — joining the
 * wrong room would put a patient into another patient's session.
 */
export function parseTokenResponse(sessionId: string, body: unknown): RoomCredentials {
  if (typeof body !== "object" || body === null) {
    throw new RoomTokenError("token response is not an object");
  }
  const { url, token, room, expires_at_ms: expiresAtMs } = body as TokenResponseBody;
  if (typeof url !== "string" || !url.startsWith("wss://")) {
    throw new RoomTokenError("token response url must be wss://");
  }
  if (typeof token !== "string" || token.length === 0) {
    throw new RoomTokenError("token response carries no token");
  }
  if (typeof expiresAtMs !== "number" || !Number.isFinite(expiresAtMs)) {
    throw new RoomTokenError("token response carries no usable expiry");
  }
  const expected = `${ROOM_PREFIX}${sessionId}`;
  if (typeof room !== "string" || room !== expected) {
    throw new RoomTokenError("token response names a different room");
  }
  return { url, token, room, expiresAtMs };
}

/** The fetch seam, so tests need neither auth state nor a network. */
export type AuthedFetch = (path: string, init?: RequestInit) => Promise<Response>;

export function createTokenSource(authedFetch: AuthedFetch): TokenSource {
  return {
    fetch: async (sessionId: string): Promise<RoomCredentials> => {
      if (!CANONICAL_UUID.test(sessionId)) {
        throw new RoomTokenError("sessionId must be a canonical lowercase uuid");
      }
      const response = await authedFetch(voiceTokenPath(sessionId), { method: "POST" });
      if (!response.ok) {
        // The status is the whole diagnosis. The body is not read into the
        // message: an error body can echo request context (invariant 6).
        throw new RoomTokenError(`voice token request failed: ${response.status}`);
      }
      return parseTokenResponse(sessionId, await response.json());
    },
  };
}
