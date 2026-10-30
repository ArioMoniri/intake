/**
 * INT-587 — the step-up seam in front of Doctor Link issuance.
 *
 * Issuing a link releases the patient's note to whoever holds the link and
 * code, so it is a sensitive action. The owner's order of 28 Oct 2026 (D36,
 * INT-582, GitHub #981) steps sensitive actions up to a patient passkey, which
 * mitigates a SIM swap. Patients have no passkeys yet, so until INT-582 lands
 * the tier is the one that exists: the OTP-verified, DPoP-bound session
 * (INT-131) — the same proof the server's patient routes already require.
 *
 * The seam is typed rather than implied:
 *
 * - `issueDoctorLink` takes a `StepUpProof`, and only a `StepUp` makes one, so
 *   no screen can issue without passing through this gate;
 * - `StepUp` is the swap point: INT-582 supplies a passkey `StepUp` and
 *   nothing above or below it changes;
 * - `authorizeIssue` also refuses, before any network, when this phone has
 *   seen the share consent withdrawn — a revoked grant stops the link here as
 *   well as on the server, which refuses on its own record regardless.
 */
import type { ShareStanding } from "@/lib/consent/ledger";

/** Every tier the seam knows: today's, and the one D36 adds. */
export const STEP_UP_TIERS = ["otp_session", "passkey"] as const;
export type StepUpTier = (typeof STEP_UP_TIERS)[number];

declare const proofBrand: unique symbol;

/**
 * Evidence that the step-up for one sensitive act was passed. A `passkey`
 * proof carries the single-use grant the server minted for that act on this
 * device session (INT-582); it is sent once, in `X-Intake-Step-Up-Grant`,
 * and held nowhere else.
 */
export interface StepUpProof {
  readonly tier: StepUpTier;
  readonly grant?: string;
  readonly [proofBrand]: true;
}

/**
 * INT-582: why a passkey step-up produced no proof, when that is something
 * other than "no session". `step_up` — the passkey could not confirm the act
 * (the screen names the manual path, KVKK m.11(1)(g)); `step_up_cancelled` —
 * the patient closed the passkey sheet themselves.
 */
export interface StepUpRefusal {
  readonly refused: "step_up" | "step_up_cancelled";
}

export interface StepUp {
  readonly tier: StepUpTier;
  /** The proof; a refusal that names its reason; or null — no session. */
  prove(): Promise<StepUpProof | StepUpRefusal | null>;
}

/** The proof a passkey step-up mints (INT-582): its tier and its grant. */
export function passkeyProof(grant: string): StepUpProof {
  return { tier: "passkey", grant } as StepUpProof;
}

export function isStepUpRefusal(value: unknown): value is StepUpRefusal {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const refused = (value as { refused?: unknown }).refused;
  return refused === "step_up" || refused === "step_up_cancelled";
}

export function isStepUpProof(value: unknown): value is StepUpProof {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const tier = (value as { tier?: unknown }).tier;
  return STEP_UP_TIERS.some((known) => known === tier);
}

/**
 * The tier in force until INT-582: an OTP-verified session is present on this
 * device. `hasSession` is injected (./sessionStepUp reads the token custody),
 * so the rule is testable without a keychain. A check that throws is no proof.
 */
export function otpSessionStepUp(hasSession: () => Promise<boolean>): StepUp {
  return {
    tier: "otp_session",
    async prove() {
      try {
        return (await hasSession()) ? ({ tier: "otp_session" } as StepUpProof) : null;
      } catch {
        return null;
      }
    },
  };
}

export type IssueAuthority =
  | { ok: true; proof: StepUpProof }
  | { ok: false; reason: "consent" | "session" | "step_up" | "step_up_cancelled" };

/**
 * Everything that must hold before the issuing POST is attempted. A withdrawn
 * share consent refuses first and without asking the step-up anything; an
 * `unknown` standing goes on, because this phone not having seen a grant is
 * not a withdrawal — the server holds the record and checks it (invariant 4).
 */
export async function authorizeIssue(
  standing: ShareStanding,
  stepUp: StepUp,
): Promise<IssueAuthority> {
  if (standing === "withdrawn") {
    return { ok: false, reason: "consent" };
  }
  const proof = await stepUp.prove();
  if (proof === null) {
    return { ok: false, reason: "session" };
  }
  if (isStepUpRefusal(proof)) {
    return { ok: false, reason: proof.refused };
  }
  return { ok: true, proof };
}
