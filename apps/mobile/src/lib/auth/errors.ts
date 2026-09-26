/**
 * The auth client's typed error (INT-131), kept apart from api.ts so the pure
 * modules that throw it (apiBase.ts, INT-328) stay node-testable without an
 * expo import. api.ts re-exports it; every caller imports it from there.
 *
 * Every error surfaces as a typed, GENERIC kind (02 §8.2: generic errors; the
 * UI maps kinds to tr copy) — no server narrative is ever rendered.
 */
import type { AttestationFailure } from "./attestationPlan";

export type AuthErrorKind =
  "limited" | "phone" | "code" | "attestation" | "network" | "session" | "unconfigured" | "generic";

export class AuthApiError extends Error {
  readonly kind: AuthErrorKind;
  readonly retryAfterS: number | null;
  /** why the device could not be attested, when the client knows (INT-344) */
  readonly attestation: AttestationFailure | null;

  constructor(
    kind: AuthErrorKind,
    retryAfterS: number | null = null,
    attestation: AttestationFailure | null = null,
  ) {
    super(kind); // the kind IS the message — codes, never narrative
    this.kind = kind;
    this.retryAfterS = retryAfterS;
    this.attestation = attestation;
  }
}
