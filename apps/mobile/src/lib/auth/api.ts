/**
 * Auth API client (INT-131): challenge → attested OTP request → attested
 * verify with a DPoP proof → DPoP-bound session; refresh with rotation.
 *
 * Every error surfaces as a typed, GENERIC kind (02 §8.2: generic errors;
 * the UI maps kinds to tr copy) — no server narrative is ever rendered.
 * Tokens go through tokens.ts (SecureStore); nothing here logs a phone, a
 * code or a token.
 *
 * INT-328: the base comes from the one resolver (apiBase.ts via
 * expoApiBase.ts). A release build uses only its configured https base and
 * throws `ApiBaseUnconfigured` (kind `unconfigured`) without one; a dev build
 * walks the LAN exactly as before.
 */
import { buildAttestation } from "./attestation";
import { dpopProof } from "./dpop";
import { AuthApiError } from "./errors";
import { buildApiBase } from "./expoApiBase";
import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  savePatientId,
  saveRefreshToken,
  setAccessToken,
} from "./tokens";

export { ApiBaseUnconfigured } from "./apiBase";
export { AuthApiError, type AuthErrorKind } from "./errors";

let cachedBase: string | null = null;

export async function apiBase(): Promise<string> {
  if (cachedBase !== null) {
    return cachedBase;
  }
  const base = await buildApiBase();
  if (base === null) {
    throw new AuthApiError("network"); // dev: no LAN host answered
  }
  cachedBase = base;
  return base;
}

interface ErrorBody {
  error?: string;
  retry_after_s?: number;
}

function mapError(status: number, body: ErrorBody): AuthApiError {
  const code = body.error ?? "";
  if (status === 429 || code === "otp_limited") {
    return new AuthApiError("limited", body.retry_after_s ?? null);
  }
  if (code === "phone_invalid") {
    return new AuthApiError("phone");
  }
  if (code === "otp_invalid") {
    return new AuthApiError("code");
  }
  if (code.startsWith("attestation") || code === "challenge_invalid") {
    return new AuthApiError("attestation");
  }
  if (code === "refresh_reused" || status === 401) {
    return new AuthApiError("session");
  }
  return new AuthApiError("generic");
}

async function parseBody(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

async function fetchChallenge(base: string): Promise<string> {
  const response = await fetch(`${base}/v1/auth/attest/challenge`, { method: "POST" });
  if (!response.ok) {
    throw mapError(response.status, await parseBody(response));
  }
  const body = await parseBody(response);
  if (typeof body.challenge !== "string") {
    throw new AuthApiError("generic");
  }
  return body.challenge;
}

async function attestationHeader(base: string): Promise<Record<string, string>> {
  const nonce = await fetchChallenge(base);
  const payload = await buildAttestation(nonce);
  if (payload === null) {
    throw new AuthApiError("attestation");
  }
  return { "X-Intake-Attestation": payload };
}

export interface OtpRequestResult {
  resendAfterS: number;
}

export async function requestOtp(phoneE164: string): Promise<OtpRequestResult> {
  const base = await apiBase();
  const response = await fetch(`${base}/v1/auth/otp/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(await attestationHeader(base)) },
    body: JSON.stringify({ phone: phoneE164 }),
  });
  const body = await parseBody(response);
  if (!response.ok) {
    throw mapError(response.status, body as ErrorBody);
  }
  const resend = body.resend_after_s;
  return { resendAfterS: typeof resend === "number" ? resend : 60 };
}

interface TokenBundleBody {
  access_token?: string;
  refresh_token?: string;
  patient_id?: string;
}

async function storeBundle(body: TokenBundleBody): Promise<string> {
  if (
    typeof body.access_token !== "string" ||
    typeof body.refresh_token !== "string" ||
    typeof body.patient_id !== "string"
  ) {
    throw new AuthApiError("generic");
  }
  setAccessToken(body.access_token);
  await saveRefreshToken(body.refresh_token);
  await savePatientId(body.patient_id);
  return body.patient_id;
}

/** Verify the code; on success the session is stored and the patient row id
 * is returned (the server created the account when it did not exist). */
export async function verifyOtp(phoneE164: string, code: string): Promise<string> {
  const base = await apiBase();
  const url = `${base}/v1/auth/otp/verify`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(await attestationHeader(base)),
      DPoP: await dpopProof({ method: "POST", url }),
    },
    body: JSON.stringify({ phone: phoneE164, code }),
  });
  const body = await parseBody(response);
  if (!response.ok) {
    throw mapError(response.status, body as ErrorBody);
  }
  return storeBundle(body as TokenBundleBody);
}

/** Rotate the refresh family; false = session gone (re-onboard via OTP). */
export async function refreshSession(): Promise<boolean> {
  const refresh = await getRefreshToken();
  if (refresh === null) {
    return false;
  }
  const base = await apiBase();
  const url = `${base}/v1/auth/token/refresh`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      DPoP: await dpopProof({ method: "POST", url }),
    },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  const body = await parseBody(response);
  if (!response.ok) {
    await clearSession();
    return false;
  }
  await storeBundle(body as TokenBundleBody);
  return true;
}

/** Authenticated fetch: DPoP scheme + per-request proof with the token
 * hash; one silent refresh on 401, then the caller re-onboards. */
export async function authedFetch(path: string, init?: RequestInit): Promise<Response> {
  const base = await apiBase();
  const url = `${base}${path}`;
  const method = init?.method ?? "GET";

  const attempt = async (): Promise<Response> => {
    const token = getAccessToken();
    if (token === null) {
      throw new AuthApiError("session");
    }
    return fetch(url, {
      ...init,
      headers: {
        ...(init?.headers as Record<string, string> | undefined),
        Authorization: `DPoP ${token}`,
        DPoP: await dpopProof({ method, url, accessToken: token }),
      },
    });
  };

  if (getAccessToken() === null && !(await refreshSession())) {
    throw new AuthApiError("session");
  }
  const first = await attempt();
  if (first.status !== 401) {
    return first;
  }
  if (!(await refreshSession())) {
    throw new AuthApiError("session");
  }
  return attempt();
}

/** Dev-tier convenience behind the SERVER's INTAKE_DEV_OTP_PEEK gate: the
 * endpoint is 404 unless the operator set explicit-yes; __DEV__ callers only. */
export async function devPeekOtp(phoneE164: string): Promise<string | null> {
  const base = await apiBase();
  const response = await fetch(
    `${base}/v1/auth/dev/otp-peek?phone=${encodeURIComponent(phoneE164)}`,
  );
  if (!response.ok) {
    return null;
  }
  const body = await parseBody(response);
  return typeof body.code === "string" ? body.code : null;
}

/**
 * One visit as the hospital feed returns it, already in the shell's visit
 * shape (structurally a `VisitFixture`). Declared here rather than imported
 * from lib/dev, so the auth client's source names no dev module (INT-328):
 * the feed carries no taxonomy branch, visit type or note state, so those are
 * null by type.
 */
export interface SyncedVisit {
  id: string;
  hospital: string;
  department: string;
  branchId: null;
  visitType: null;
  date: string | null;
  noteStatus: null;
}

/**
 * INT-318: pull the signed-in patient's upcoming visits from the hospital feed
 * after OTP verification. The phone is sent once, over the DPoP-bound session,
 * and the server refuses it unless it tokenizes to this same caller — so it is
 * never a way to read another patient's visits. Maps the API rows to the
 * shell's visit shape. A failure returns [] rather than throwing: a patient
 * with no matched appointment still gets a working home screen.
 */
export async function syncVisits(
  phoneE164: string,
): Promise<{ patientName: string | null; visits: SyncedVisit[] }> {
  try {
    const response = await authedFetch("/v1/visits/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: phoneE164 }),
    });
    if (!response.ok) {
      return { patientName: null, visits: [] };
    }
    const data = (await response.json()) as {
      outcome: string;
      patient_name: string | null;
      visits: Array<{
        id: string;
        hospital: string;
        department: string;
        date: string | null;
        time: string | null;
      }>;
    };
    return {
      patientName: data.patient_name ?? null,
      visits: data.visits.map((v) => ({
        id: v.id,
        hospital: v.hospital,
        department: v.time ? `${v.department} · ${v.time}` : v.department,
        branchId: null,
        visitType: null,
        date: v.date,
        noteStatus: null,
      })),
    };
  } catch {
    return { patientName: null, visits: [] };
  }
}
