/**
 * INT-582 (D36) — what a passkey ceremony on this phone may be asked to do.
 *
 * The relying party is D34's domain-bound host: the iOS associated domain
 * `webcredentials:3-211-2-143.sslip.io` (INT-580 adds it to app.json). The
 * server sends the WebAuthn options; this module refuses any that name another
 * relying party, skip user verification, ask for an attestation, or offer no
 * ES256 — so a compromised or mistaken server cannot steer the phone into
 * minting a passkey for somebody else, or a weaker one. iOS enforces the
 * associated domain as well; this is the app's own check in front of it.
 *
 * Pure: no native module, no network, no store (vitest is node-only).
 */

/** D34's synthetic host. The production domain is revisited at real launch. */
export const PASSKEY_RP_ID = "3-211-2-143.sslip.io";

/** The four D36 actions, and the mechanism's own three (add while one is active, remove, cancel recovery). */
export const STEP_UP_ACTIONS = [
  "doctor_link_issue",
  "phone_change",
  "data_export",
  "data_delete",
  "passkey_add",
  "passkey_remove",
  "recovery_cancel",
] as const;
export type StepUpAction = (typeof STEP_UP_ACTIONS)[number];

/** The header the server's gate reads the single-use grant from. */
export const STEP_UP_GRANT_HEADER = "X-Intake-Step-Up-Grant";

const ES256 = -7;
const B64URL = /^[A-Za-z0-9_-]+$/;

export interface CredentialDescriptor {
  type: "public-key";
  id: string;
}

/** The creation options the native create() receives (WebAuthn JSON form). */
export interface CreationOptions {
  rp: { id: string; name: string };
  user: { id: string; name: string; displayName: string };
  challenge: string;
  pubKeyCredParams: { type: "public-key"; alg: number }[];
  timeout?: number;
  excludeCredentials: CredentialDescriptor[];
  authenticatorSelection: {
    authenticatorAttachment: "platform";
    residentKey: "required";
    userVerification: "required";
  };
  attestation: "none";
}

/** The request options the native get() receives. */
export interface RequestOptions {
  challenge: string;
  rpId: string;
  allowCredentials: CredentialDescriptor[];
  userVerification: "required";
  timeout?: number;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function b64(value: unknown): value is string {
  return typeof value === "string" && B64URL.test(value);
}

function descriptors(value: unknown): CredentialDescriptor[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const out: CredentialDescriptor[] = [];
  for (const item of value) {
    const row = record(item);
    if (row === null || row.type !== "public-key" || !b64(row.id)) {
      return null;
    }
    out.push({ type: "public-key", id: row.id });
  }
  return out;
}

/** The server's creation options, or null when anything is off. */
export function guardCreationOptions(raw: unknown): CreationOptions | null {
  const options = record(record(raw)?.publicKey);
  const rp = record(options?.rp);
  const user = record(options?.user);
  const selection = record(options?.authenticatorSelection);
  const params = options?.pubKeyCredParams;
  const excluded = descriptors(options?.excludeCredentials ?? []);
  if (
    options === null ||
    rp === null ||
    user === null ||
    selection === null ||
    excluded === null ||
    rp.id !== PASSKEY_RP_ID ||
    typeof rp.name !== "string" ||
    !b64(user.id) ||
    typeof user.name !== "string" ||
    typeof user.displayName !== "string" ||
    !b64(options.challenge) ||
    options.attestation !== "none" ||
    selection.userVerification !== "required" ||
    selection.authenticatorAttachment !== "platform" ||
    selection.residentKey !== "required" ||
    !Array.isArray(params) ||
    !params.some((param) => record(param)?.alg === ES256 && record(param)?.type === "public-key")
  ) {
    return null;
  }
  return {
    rp: { id: rp.id, name: rp.name },
    user: { id: user.id, name: user.name, displayName: user.displayName },
    challenge: options.challenge,
    pubKeyCredParams: [{ type: "public-key", alg: ES256 }],
    timeout: typeof options.timeout === "number" ? options.timeout : undefined,
    excludeCredentials: excluded,
    authenticatorSelection: {
      authenticatorAttachment: "platform",
      residentKey: "required",
      userVerification: "required",
    },
    attestation: "none",
  };
}

/** What the server answered for a step-up: the options, or "not enrolled". */
export type StepUpOffer =
  | { enrolled: true; options: RequestOptions }
  | { enrolled: false; enrolment: "offered" | "unavailable" };

/** The server's step-up answer, or null when anything is off. */
export function guardStepUpOffer(raw: unknown): StepUpOffer | null {
  const body = record(raw);
  if (body === null) {
    return null;
  }
  if (body.enrolled === false) {
    if (body.tier !== "otp_session") {
      return null;
    }
    return {
      enrolled: false,
      enrolment: body.enrolment === "offered" ? "offered" : "unavailable",
    };
  }
  const options = record(body.publicKey);
  const allowed = descriptors(options?.allowCredentials);
  if (
    body.enrolled !== true ||
    options === null ||
    allowed === null ||
    options.rpId !== PASSKEY_RP_ID ||
    options.userVerification !== "required" ||
    !b64(options.challenge)
  ) {
    return null;
  }
  return {
    enrolled: true,
    options: {
      challenge: options.challenge,
      rpId: options.rpId,
      allowCredentials: allowed,
      userVerification: "required",
      timeout: typeof options.timeout === "number" ? options.timeout : undefined,
    },
  };
}
