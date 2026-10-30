/**
 * INT-583 — the device-sessions seam: which devices are signed in to this
 * account, signing one or all of the others out, and "that sign-in wasn't
 * me".
 *
 * The fetch is injected (the screen passes `authedFetch`, which adds the DPoP
 * scheme and proof), so this module imports nothing native and every answer
 * the contract names is proved in node. Every outcome is a typed result the
 * screen maps to catalogue copy; no server sentence is ever rendered (02
 * §8.2, generic errors), and nothing here logs an id.
 *
 * One rule is stricter than it looks: a list the app cannot fully read is not
 * shown at all. Dropping the one row that did not parse could hide exactly
 * the device the patient came here to find.
 */

/** `authedFetch`'s shape: a path on the API base, signed for this session. */
export type AuthedFetch = (path: string, init?: RequestInit) => Promise<Response>;

const SESSIONS = "/v1/auth/sessions";
const SIGN_OUT_OTHERS = "/v1/auth/sessions/sign-out-others";

/** A session id as the server issues it: 32 lowercase hex characters. */
const SESSION_ID = /^[0-9a-f]{32}$/;

export interface DeviceSession {
  sessionId: string;
  /** This device. */
  current: boolean;
  /** ISO-8601 instant the device signed in. */
  signedInAt: string;
  /** Whether that device is registered for new-sign-in notices. */
  push: boolean;
}

export interface SessionList {
  sessions: DeviceSession[];
  /** Null: this device may sign the others out now. Otherwise the instant it may. */
  signOutOthersAfter: string | null;
  /**
   * Whether the server has a push channel wired. False: no notice reaches
   * any device, whatever is registered, so the screen does not say "on".
   */
  noticesOn: boolean;
}

export type Unreachable = { ok: false; error: "unreachable" };
export type TooNew = { ok: false; error: "session_too_new"; retryAfterS: number | null };
export type ListResult = { ok: true; list: SessionList } | Unreachable;
export type RevokeResult = { ok: true } | { ok: false; error: "not_found" } | TooNew | Unreachable;
export type SignOutOthersResult = { ok: true; signedOut: number | null } | TooNew | Unreachable;

export interface SessionsApi {
  list(): Promise<ListResult>;
  /** Sign one device out. The current device's own id signs this device out. */
  revoke(sessionId: string): Promise<RevokeResult>;
  /** `notMe` is the patient saying the other sign-in was not theirs. */
  signOutOthers(notMe: boolean): Promise<SignOutOthersResult>;
}

const UNREACHABLE: Unreachable = { ok: false, error: "unreachable" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isInstant(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

async function body(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/** The error object of a refusal. The API flattens every refusal to the
 *  machine-readable `{"error": <code>, ...}` (services/api errors.py), the
 *  same shape auth/api.ts reads. */
export async function errorDetail(response: Response): Promise<Record<string, unknown>> {
  const parsed = await body(response);
  return isRecord(parsed) && typeof parsed.error === "string" ? parsed : {};
}

function tooNew(detail: Record<string, unknown>): TooNew | null {
  if (detail.error !== "session_too_new") {
    return null;
  }
  const retry = detail.retry_after_s;
  const usable = typeof retry === "number" && Number.isFinite(retry) && retry >= 0;
  return { ok: false, error: "session_too_new", retryAfterS: usable ? retry : null };
}

function parseSession(raw: unknown): DeviceSession | null {
  if (!isRecord(raw)) {
    return null;
  }
  const { session_id, current, signed_in_at, push } = raw;
  if (
    typeof session_id !== "string" ||
    !SESSION_ID.test(session_id) ||
    typeof current !== "boolean" ||
    !isInstant(signed_in_at) ||
    typeof push !== "boolean"
  ) {
    return null;
  }
  return { sessionId: session_id, current, signedInAt: signed_in_at, push };
}

function parseList(raw: unknown): SessionList | null {
  if (!isRecord(raw) || !Array.isArray(raw.sessions)) {
    return null;
  }
  const after = raw.sign_out_others_after;
  if (after !== null && !isInstant(after)) {
    return null;
  }
  const noticesOn = raw.notices_on;
  if (typeof noticesOn !== "boolean") {
    return null;
  }
  const sessions: DeviceSession[] = [];
  for (const row of raw.sessions) {
    const session = parseSession(row);
    if (session === null) {
      return null;
    }
    sessions.push(session);
  }
  return { sessions, signOutOthersAfter: after, noticesOn };
}

function parseCount(raw: unknown): number | null {
  if (!isRecord(raw)) {
    return null;
  }
  const count = raw.signed_out;
  return typeof count === "number" && Number.isInteger(count) && count >= 0 ? count : null;
}

export function createSessionsApi(fetcher: AuthedFetch): SessionsApi {
  return {
    async list() {
      try {
        const response = await fetcher(SESSIONS);
        if (!response.ok) {
          return UNREACHABLE;
        }
        const list = parseList(await body(response));
        return list === null ? UNREACHABLE : { ok: true, list };
      } catch {
        return UNREACHABLE;
      }
    },

    async revoke(sessionId) {
      if (!SESSION_ID.test(sessionId)) {
        return { ok: false, error: "not_found" };
      }
      try {
        const response = await fetcher(`/v1/auth/sessions/${sessionId}`, { method: "DELETE" });
        if (response.ok) {
          return { ok: true };
        }
        const detail = await errorDetail(response);
        if (response.status === 404 && detail.error === "not_found") {
          return { ok: false, error: "not_found" };
        }
        return (response.status === 403 ? tooNew(detail) : null) ?? UNREACHABLE;
      } catch {
        return UNREACHABLE;
      }
    },

    async signOutOthers(notMe) {
      try {
        const response = await fetcher(SIGN_OUT_OTHERS, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ not_me: notMe }),
        });
        if (response.ok) {
          return { ok: true, signedOut: parseCount(await body(response)) };
        }
        if (response.status === 403) {
          return tooNew(await errorDetail(response)) ?? UNREACHABLE;
        }
        return UNREACHABLE;
      } catch {
        return UNREACHABLE;
      }
    },
  };
}
