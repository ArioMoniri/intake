/**
 * INT-311 — issuing a Doctor Link from the patient's phone: the transport.
 *
 * The share centre (INT-139) lists, revokes and audits grants but deliberately
 * refused to ISSUE one, because issuing renders a bearer credential and, while
 * INT-150 was the only owner of the two share-purpose-gated routes, no surface
 * owned the act. This module is that owner, and it is the ONLY place in the app
 * that calls either route — a fact `e2e/shares.spec.ts` §2 asserts over the
 * whole tree.
 *
 * The act is two steps, and the order is the disclosure policy:
 *
 *   1. `POST …/note/doctor-links` mints the grant and returns the 128-bit
 *      token ONCE (`DoctorLinkIssued`);
 *   2. `POST …/{link_id}/otp` mints the opening code over the SAME
 *      authenticated session.
 *
 * Step 2 is the delivery channel that EXISTS. The channel files/10 §2 names —
 * the phone or e-mail the patient chose — has no recorded destination in this
 * repo and no contracted vendor (HB-O7), so the public delivery route refuses
 * rather than faking one. Nothing here is sent anywhere: the patient shows the
 * screen. So this module invents no channel, and the screen above it must not
 * either.
 *
 * The credential is RETURNED to the caller and held nowhere else. This module
 * reads no store, writes none, logs nothing (invariant 6), and puts neither the
 * token nor the recipient in a URL — both routes are POST and carry their
 * payload in the body, exactly as the server's own contract requires.
 */
import { authedFetch } from "@/lib/auth/api";
import { withStepUp } from "@/lib/auth/passkey/stepUp";

/** The one bundle a screen may render, and only while it is mounted. */
export interface IssuedCredential {
  /** The patient's own label for who they are sharing with (the watermark). */
  recipient: string;
  /** The 128-bit link token — shown once, on this screen, then gone. */
  token: string;
  /** The opening code minted over this session; the clinician enters both. */
  code: string;
  /** When the grant stops opening; the server owns this instant. */
  expiresAt: string;
}

/** Why an attempt did not produce a credential — one reason per true sentence. */
export type IssueFailure =
  | "not_shared"
  | "date_unknown"
  | "recipient_invalid"
  | "limited"
  | "unavailable"
  | "unreachable"
  // INT-582 (D36): the passkey step-up was refused (a person can review it)
  // or the patient closed the passkey sheet themselves
  | "step_up"
  | "step_up_cancelled";

export type IssueResult =
  { ok: true; credential: IssuedCredential } | { ok: false; reason: IssueFailure };

/** Mirrors ``intake_platform.doctor_link.MAX_RECIPIENT_CHARS`` (120). */
const MAX_RECIPIENT_CHARS = 120;

/** A C0 control or DEL — refused in a watermark label, the server's own rule. */
function hasControlChar(label: string): boolean {
  for (let i = 0; i < label.length; i += 1) {
    const point = label.charCodeAt(i);
    if (point < 0x20 || point === 0x7f) {
      return true;
    }
  }
  return false;
}

/**
 * The recipient label, validated the way the server validates it, so an
 * obviously-bad label never costs a round trip. Refused rather than sanitised:
 * a watermark is evidence of who a document was released to, and quietly
 * rewriting it changes what the evidence says.
 */
export function validateRecipient(raw: string): string | null {
  const label = raw.trim();
  if (label.length === 0 || label.length > MAX_RECIPIENT_CHARS || hasControlChar(label)) {
    return null;
  }
  return label;
}

interface IssuedGrant {
  token: string;
  linkId: string;
  recipient: string;
  expiresAt: string;
}

function nonEmpty(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

/** The issued grant, or null. Null is never a half-built credential. */
export function parseIssued(payload: unknown): IssuedGrant | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const row = payload as Record<string, unknown>;
  if (
    !nonEmpty(row.token) ||
    !nonEmpty(row.link_id) ||
    !nonEmpty(row.recipient) ||
    !nonEmpty(row.expires_at)
  ) {
    return null;
  }
  return {
    token: row.token,
    linkId: row.link_id,
    recipient: row.recipient,
    expiresAt: row.expires_at,
  };
}

/** The opening code, or null. */
export function parseCode(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const code = (payload as Record<string, unknown>).code;
  return nonEmpty(code) ? code : null;
}

function linksPath(visitId: string): string {
  return `/v1/visits/${encodeURIComponent(visitId)}/note/doctor-links`;
}

async function errorCode(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: unknown };
    return typeof body.error === "string" ? body.error : "";
  } catch {
    return "";
  }
}

/** A server refusal → the one reason that lets the screen say a true sentence. */
function failureFor(status: number, error: string): IssueFailure {
  if (error === "note_not_shared") {
    return "not_shared";
  }
  if (error === "visit_date_unknown") {
    return "date_unknown";
  }
  if (error === "recipient_invalid") {
    return "recipient_invalid";
  }
  if (status === 429 || error === "otp_limited") {
    return "limited";
  }
  if (status === 503 || error === "doctor_link_unconfigured") {
    return "unavailable";
  }
  return "unreachable";
}

async function jsonOrNull(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

/**
 * Issue a grant over this visit's live share, then mint its opening code.
 * Returns the credential to hold in memory, or the reason it could not.
 *
 * The two POSTs are sequential on purpose: the code is minted only for a grant
 * that was actually issued, so a failure to issue never mints a stray code.
 */
export async function issueDoctorLink(visitId: string, rawRecipient: string): Promise<IssueResult> {
  const recipient = validateRecipient(rawRecipient);
  if (recipient === null) {
    return { ok: false, reason: "recipient_invalid" };
  }
  try {
    // INT-582 (D36): issuing steps up to the patient's passkey when the
    // server asks for it; a patient without one is answered directly
    const sent = await withStepUp("doctor_link_issue", (headers) =>
      authedFetch(linksPath(visitId), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ recipient }),
      }),
    );
    if (sent.kind === "refused") {
      return { ok: false, reason: "step_up" };
    }
    if (sent.kind === "cancelled") {
      return { ok: false, reason: "step_up_cancelled" };
    }
    const issued = sent.response;
    if (!issued.ok) {
      const code = sent.error ?? (await errorCode(issued));
      return { ok: false, reason: failureFor(issued.status, code) };
    }
    const grant = parseIssued(await jsonOrNull(issued));
    if (grant === null) {
      return { ok: false, reason: "unreachable" };
    }
    const otpPath = `${linksPath(visitId)}/${encodeURIComponent(grant.linkId)}/otp`;
    const minted = await authedFetch(otpPath, { method: "POST" });
    if (!minted.ok) {
      return { ok: false, reason: failureFor(minted.status, await errorCode(minted)) };
    }
    const code = parseCode(await jsonOrNull(minted));
    if (code === null) {
      return { ok: false, reason: "unreachable" };
    }
    return {
      ok: true,
      credential: {
        recipient: grant.recipient,
        token: grant.token,
        code,
        expiresAt: grant.expiresAt,
      },
    };
  } catch {
    // A DPoP/session error or a dropped connection — never a credential.
    return { ok: false, reason: "unreachable" };
  }
}
