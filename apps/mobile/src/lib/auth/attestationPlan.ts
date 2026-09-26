/**
 * Device attestation, the decisions (INT-344) — pure and node-testable.
 *
 * Release builds on iOS prove each OTP call with Apple App Attest: one
 * ATTESTATION registers a Secure Enclave key with the server
 * (POST /v1/auth/attest/key), and every OTP call then carries an ASSERTION
 * from that key over `attestationClientData(purpose, challenge)` — the exact
 * string services/api rebuilds, so a proof made for one call and one
 * single-use challenge cannot be spent on another.
 *
 * Outside __DEV__ the client never sends `dev-unattested`. Android release
 * builds are refused with a reason of their own: the server has no Play
 * Integrity decoder until the Play Console organisation account exists
 * (files/HUMAN_BLOCKERS.md HB-A3), and a token nobody can verify is not sent.
 *
 * Everything that touches a native module or SecureStore arrives through
 * `AttestationPorts` (built in attestation.ts), so the key lifecycle below runs
 * under vitest against in-memory ports. Failures are typed and map to tr/en
 * copy; no server narrative is ever shown.
 */
import type { MessageKey } from "@/lib/i18n";

import { b64url } from "./jws";

export const CLIENT_DATA_VERSION = "intake.attest.v1";

export type AttestPurpose = "attest.key" | "otp.request" | "otp.verify";

export function attestationClientData(purpose: AttestPurpose, challenge: string): string {
  return `${CLIENT_DATA_VERSION}|${purpose}|${challenge}`;
}

// --- which mode ------------------------------------------------------------------------------

export type AttestationUnavailable = "unsupported" | "pending" | "no-platform";

export type AttestationMode =
  | { kind: "dev-unattested" }
  | { kind: "app-attest" }
  | { kind: "unavailable"; reason: AttestationUnavailable };

export interface AttestationEnvironment {
  isDev: boolean;
  platform: string;
  appAttestSupported: boolean;
}

export function selectAttestationMode(env: AttestationEnvironment): AttestationMode {
  if (env.platform !== "ios" && env.platform !== "android") {
    return { kind: "unavailable", reason: "no-platform" };
  }
  if (env.isDev) {
    return { kind: "dev-unattested" };
  }
  if (env.platform === "android") {
    return { kind: "unavailable", reason: "pending" };
  }
  return env.appAttestSupported
    ? { kind: "app-attest" }
    : { kind: "unavailable", reason: "unsupported" };
}

// --- what goes on the wire ----------------------------------------------------------------

export interface KeyRegistration {
  platform: "ios";
  key_id: string;
  attestation: string;
  challenge: string;
}

export function appAttestHeader(input: {
  keyId: string;
  assertion: string;
  challenge: string;
  deviceId: string;
}): string {
  return JSON.stringify({
    platform: "ios",
    mode: "app-attest",
    token: input.assertion,
    key_id: input.keyId,
    device_id: input.deviceId,
    nonce: input.challenge,
  });
}

/** The dev tier's payload: it says what it is, and the server's dev verifier
 * accepts it only under INTAKE_DEV_ALLOW_UNATTESTED=explicit-yes. */
export function devUnattestedHeader(input: {
  platform: "ios" | "android";
  deviceId: string;
  challenge: string;
}): string {
  return JSON.stringify({
    platform: input.platform,
    mode: "dev-unattested",
    token: b64url(new TextEncoder().encode("intake-dev-attest")),
    device_id: input.deviceId,
    nonce: input.challenge,
  });
}

// --- the stored key slot (versioned; anything else reads as absent) -----------------------

export interface StoredAttestKey {
  keyId: string;
  registered: boolean;
}

const SLOT_VERSION = 1;
const MAX_KEY_ID_CHARS = 64;

export function encodeAttestKey(key: StoredAttestKey): string {
  return JSON.stringify({ v: SLOT_VERSION, keyId: key.keyId, registered: key.registered });
}

export function decodeAttestKey(raw: string | null): StoredAttestKey | null {
  if (raw === null) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) {
    return null;
  }
  const { v, keyId, registered } = parsed as Record<string, unknown>;
  if (
    v !== SLOT_VERSION ||
    typeof keyId !== "string" ||
    keyId.length === 0 ||
    keyId.length > MAX_KEY_ID_CHARS ||
    typeof registered !== "boolean"
  ) {
    return null;
  }
  return { keyId, registered };
}

// --- failures ----------------------------------------------------------------------------------

export type AttestationFailure = "unsupported" | "pending" | "service" | "rejected" | "invalid-key";

export class AttestationFailureError extends Error {
  readonly failure: AttestationFailure;

  constructor(failure: AttestationFailure) {
    super(failure); // the failure IS the message — a code, never narrative
    this.failure = failure;
  }
}

/** @expo/app-integrity's iOS error codes (IntegrityErrorCodes.swift, SDK 57). */
export function nativeFailure(code: unknown): AttestationFailure {
  switch (code) {
    case "ERR_APP_INTEGRITY_FEATURE_UNSUPPORTED":
      return "unsupported";
    case "ERR_APP_INTEGRITY_SERVER_UNAVAILABLE":
      return "service";
    case "ERR_APP_INTEGRITY_INVALID_KEY":
      return "invalid-key";
    default:
      return "rejected";
  }
}

export function attestationMessageKey(failure: AttestationFailure | null): MessageKey {
  switch (failure) {
    case "unsupported":
      return "auth.error.attestationUnsupported";
    case "pending":
      return "auth.error.attestationPending";
    case "service":
      return "auth.error.attestationService";
    default:
      return "auth.error.attestation";
  }
}

/** The server's attestation refusals (403 attestation_* / challenge_invalid). */
export function isAttestationRefusal(status: number, errorCode: string | undefined): boolean {
  return (
    status === 403 &&
    errorCode !== undefined &&
    (errorCode.startsWith("attestation") || errorCode === "challenge_invalid")
  );
}

/** One retry with a freshly attested key, and only when the server refused an
 * App Attest assertion — its record of the key may have aged out. */
export function shouldReattest(input: {
  status: number;
  errorCode: string | undefined;
  attempt: number;
  mode: AttestationMode["kind"];
}): boolean {
  return (
    input.attempt === 0 &&
    input.mode === "app-attest" &&
    input.status === 403 &&
    input.errorCode === "attestation_unverified"
  );
}

// --- the key lifecycle ------------------------------------------------------------------------

export interface AttestationPorts {
  mode: AttestationMode;
  platform: "ios" | "android";
  deviceId(): Promise<string>;
  /** a fresh single-use server challenge */
  challenge(): Promise<string>;
  /** POST /v1/auth/attest/key; throws AttestationFailureError("rejected") on refusal */
  registerKey(body: KeyRegistration): Promise<void>;
  store: {
    load(): Promise<string | null>;
    save(raw: string): Promise<void>;
    forget(): Promise<void>;
  };
  appAttest: {
    generateKey(): Promise<string>;
    attestKey(keyId: string, clientData: string): Promise<string>;
    generateAssertion(keyId: string, clientData: string): Promise<string>;
  };
}

function failureOf(error: unknown): AttestationFailure {
  if (error instanceof AttestationFailureError) {
    return error.failure;
  }
  const code =
    typeof error === "object" && error !== null && "code" in error ? error.code : undefined;
  return nativeFailure(code);
}

async function native<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new AttestationFailureError(failureOf(error));
  }
}

function isInvalidKey(error: unknown): boolean {
  return error instanceof AttestationFailureError && error.failure === "invalid-key";
}

/** The registered key id, attesting and registering one first when needed. A
 * key the Secure Enclave will not attest is replaced once; a key the server
 * refused is forgotten so the next attempt starts clean. */
async function registeredKeyId(ports: AttestationPorts): Promise<string> {
  for (let attempt = 0; ; attempt += 1) {
    const stored = decodeAttestKey(await ports.store.load());
    if (stored?.registered) {
      return stored.keyId;
    }
    const keyId = stored?.keyId ?? (await native(() => ports.appAttest.generateKey()));
    if (stored === null) {
      await ports.store.save(encodeAttestKey({ keyId, registered: false }));
    }
    const challenge = await ports.challenge();
    let attestation: string;
    try {
      attestation = await native(() =>
        ports.appAttest.attestKey(keyId, attestationClientData("attest.key", challenge)),
      );
    } catch (error) {
      if (attempt === 0 && isInvalidKey(error)) {
        await ports.store.forget();
        continue;
      }
      throw error;
    }
    try {
      await ports.registerKey({ platform: "ios", key_id: keyId, attestation, challenge });
    } catch (error) {
      if (error instanceof AttestationFailureError) {
        await ports.store.forget();
      }
      throw error;
    }
    await ports.store.save(encodeAttestKey({ keyId, registered: true }));
    return keyId;
  }
}

/** The X-Intake-Attestation header for one OTP call. */
export async function buildAttestationHeader(
  purpose: Exclude<AttestPurpose, "attest.key">,
  ports: AttestationPorts,
): Promise<string> {
  const { mode } = ports;
  if (mode.kind === "unavailable") {
    throw new AttestationFailureError(mode.reason === "pending" ? "pending" : "unsupported");
  }
  if (mode.kind === "dev-unattested") {
    const challenge = await ports.challenge();
    return devUnattestedHeader({
      platform: ports.platform,
      deviceId: await ports.deviceId(),
      challenge,
    });
  }
  for (let attempt = 0; ; attempt += 1) {
    const keyId = await registeredKeyId(ports);
    const challenge = await ports.challenge();
    try {
      const assertion = await native(() =>
        ports.appAttest.generateAssertion(keyId, attestationClientData(purpose, challenge)),
      );
      return appAttestHeader({ keyId, assertion, challenge, deviceId: await ports.deviceId() });
    } catch (error) {
      // the enclave no longer holds the key (a reinstall keeps the Keychain
      // entry but not the key): attest a fresh one, once
      if (attempt === 0 && isInvalidKey(error)) {
        await ports.store.forget();
        continue;
      }
      throw error;
    }
  }
}
