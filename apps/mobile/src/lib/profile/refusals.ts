/**
 * INT-133 — the guardian/age refusals, and the profile capabilities they
 * come with. Pure: no transport, so the rules are unit-testable without a
 * network client (the seam itself is `./api.ts`).
 *
 * The server's refusal body is `{error, scope}` and nothing else — no age,
 * no band, no reason (invariant 6). So the copy the patient reads comes from
 * the catalogue here, keyed by the code, and never from the server
 * (invariant 5).
 *
 * The guardian refusals are TERMINAL on the device. There is no in-app
 * remedy to offer: the guardian flow needs a persisted guardian↔minor link
 * whose lawful basis and proof standard are both open questions with Turkish
 * counsel (HUMAN_BLOCKERS HB-L20 — `guardian_link_basis`,
 * `guardian_relationship_proof`), so the `guardian_link` gate is shut and the
 * app says so plainly rather than opening a form it cannot complete. It
 * never shows the question ids: those are server-side reasoning, and
 * printing one would tell the room that this patient is a minor.
 */
import type { MessageKey } from "@/lib/i18n/tr";

import { ATTRIBUTIONS, type Attribution } from "./attribution";

export interface ProfileCapabilities {
  attributions: Attribution[];
  proxyAcknowledgementRequired: boolean;
  /** False today, and it is the honest answer: see the module header. */
  guardianFlowAvailable: boolean;
}

/**
 * What the app may assume when the route cannot be reached. Fail closed on
 * both axes: the acknowledgement is still required, and no guardian flow is
 * offered.
 */
export const PROFILE_FALLBACK: ProfileCapabilities = {
  attributions: [...ATTRIBUTIONS],
  proxyAcknowledgementRequired: true,
  guardianFlowAvailable: false,
};

/** The refusals INT-223's age gate can produce, plus the INT-133 one. */
export type ProfileRefusal =
  | "guardian_consent_required"
  | "dob_unverified"
  | "jurisdiction_unsupported"
  | "proxy_acknowledgement_required";

const REFUSAL_COPY: Record<ProfileRefusal, MessageKey> = {
  guardian_consent_required: "companion.refusal.guardian",
  dob_unverified: "companion.refusal.dobUnverified",
  jurisdiction_unsupported: "companion.refusal.jurisdiction",
  proxy_acknowledgement_required: "companion.refusal.ack",
};

const REFUSALS: readonly ProfileRefusal[] = [
  "guardian_consent_required",
  "dob_unverified",
  "jurisdiction_unsupported",
  "proxy_acknowledgement_required",
];

/**
 * The refusal code carried by a `{error, scope}` body, or null. An unknown
 * code is NOT guessed at — it falls through to the generic path rather than
 * borrowing another refusal's copy.
 */
export function refusalOf(body: unknown): ProfileRefusal | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const code = (body as Record<string, unknown>).error;
  return REFUSALS.find((refusal) => refusal === code) ?? null;
}

/** The tr/en copy for a refusal. */
export function refusalCopyKey(refusal: ProfileRefusal): MessageKey {
  return REFUSAL_COPY[refusal];
}

/**
 * True when the refusal is terminal on the device — nothing the patient can
 * tap fixes it, because the answer is with counsel. Only the missing proxy
 * acknowledgement is recoverable in-app.
 */
export function isTerminalRefusal(refusal: ProfileRefusal): boolean {
  return refusal !== "proxy_acknowledgement_required";
}

/** Defensive parse of the `/v1/me/profile` body; null when unusable. */
export function parseProfile(raw: unknown): ProfileCapabilities | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const body = raw as Record<string, unknown>;
  const listed = Array.isArray(body.attributions) ? body.attributions : [];
  // keep only values this build knows: an unknown attribution means a server
  // we are older than, and rendering a chip we cannot explain is worse than
  // omitting it
  const attributions = ATTRIBUTIONS.filter((value) => listed.includes(value));
  if (attributions.length === 0) {
    return null;
  }
  return {
    attributions: [...attributions],
    // absent reads as required: the safe direction (files/06 §6)
    proxyAcknowledgementRequired: body.proxy_acknowledgement_required !== false,
    // absent reads as unavailable: the gate is shut until told otherwise
    guardianFlowAvailable: body.guardian_flow_available === true,
  };
}
