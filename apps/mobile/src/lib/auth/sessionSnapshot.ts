/**
 * The restorable session snapshot (INT-131 restore) — pure shape + codec.
 *
 * A signed-in OTP patient's home screen is built from two things the shell
 * learns at verify time and nowhere else: their hospital display name and the
 * upcoming visits read from the Acıbadem feed (INT-318). Both are set from the
 * ONE call the app makes with the verified phone in hand; on a relaunch that
 * phone is gone (session.tsx never keeps the raw number — a deliberate privacy
 * choice), so without this the name reverts to the mask and the visits empty.
 *
 * This module holds only the encoded shape and its defensive decoder; the
 * SecureStore I/O lives in sessionSnapshotStore.ts, so this file (and any test
 * that imports it) never touches a native module — the appearance.ts pattern.
 *
 * Data inventory (invariant 6 / 18) for the one record this stores:
 *   category   patient display identity (masked phone, tokenized id, hospital
 *              name) + upcoming appointments (hospital, department, date)
 *   purpose    keep the signed-in patient's home screen intact across an app
 *              relaunch without re-reading the hospital feed
 *   basis      the core-scope, consented, audited sync that produced it
 *   retention  until sign-out, family revocation, or app uninstall
 *   recipients none — device-only, Keychain/Keystore-encrypted, never synced
 *              or backed up (WHEN_UNLOCKED_THIS_DEVICE_ONLY in the store)
 * The raw phone is masked upstream (auth/phone.maskPhone) before it ever
 * reaches this record, and is never a field here (invariant 14: tokenized ids
 * only; the raw number is never persisted).
 */
import { ALL_VISIT_TYPE_IDS, type VisitTypeId } from "../taxonomy/branches";
import type { NoteStatus, VisitFixture } from "../dev/accounts";

/** Bumped whenever the stored shape changes, so an old record is never read. */
export const SESSION_SNAPSHOT_SLOT = "intake.session.snapshot.v1";

/** What restore needs to rebuild the signed-in OTP account after a relaunch. */
export interface RestorableSession {
  /** Tokenized patient id (invariant 14) — the same one tokens.ts persists. */
  patientId: string;
  /** The masked phone (auth/phone.maskPhone) — never the raw number. */
  maskedPhone: string;
  /** The Acıbadem display name, or null until the feed has supplied it. */
  displayName: string | null;
  /** The mapped upcoming visits (INT-318), as the shell renders them. */
  visits: VisitFixture[];
}

const VISIT_TYPES = new Set<string>(ALL_VISIT_TYPE_IDS);
const NOTE_STATUSES = new Set<NoteStatus>(["draft", "sent", "viewed", "filed"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function optionalString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function visitType(value: unknown): VisitTypeId | null {
  return typeof value === "string" && VISIT_TYPES.has(value) ? (value as VisitTypeId) : null;
}

function noteStatus(value: unknown): NoteStatus | null {
  return typeof value === "string" && NOTE_STATUSES.has(value as NoteStatus)
    ? (value as NoteStatus)
    : null;
}

/** One stored row → a VisitFixture, or null when it is too broken to render. */
function decodeVisit(value: unknown): VisitFixture | null {
  if (!isRecord(value)) {
    return null;
  }
  if (
    !nonEmptyString(value.id) ||
    !nonEmptyString(value.hospital) ||
    !nonEmptyString(value.department)
  ) {
    return null;
  }
  return {
    id: value.id,
    hospital: value.hospital,
    department: value.department,
    branchId: optionalString(value.branchId),
    visitType: visitType(value.visitType),
    date: optionalString(value.date),
    noteStatus: noteStatus(value.noteStatus),
  };
}

function encodeVisit(visit: VisitFixture): VisitFixture {
  // Rebuilt field-by-field so a future extra field on VisitFixture is never
  // silently written into the encrypted record without a review here.
  return {
    id: visit.id,
    hospital: visit.hospital,
    department: visit.department,
    branchId: visit.branchId,
    visitType: visit.visitType,
    date: visit.date,
    noteStatus: visit.noteStatus,
  };
}

export function encodeSnapshot(snapshot: RestorableSession): string {
  return JSON.stringify({
    patientId: snapshot.patientId,
    maskedPhone: snapshot.maskedPhone,
    displayName: snapshot.displayName,
    visits: snapshot.visits.map(encodeVisit),
  });
}

/**
 * A device-local record is the only copy, so it must never be able to put the
 * shell into a state it cannot show: an absent, unreadable or foreign record —
 * or one missing the identity restore is built on — reads as null (no session
 * restored), and a malformed visit is dropped rather than rendered.
 */
export function decodeSnapshot(raw: string | null): RestorableSession | null {
  if (raw === null || raw === "") {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(parsed)) {
    return null;
  }
  if (!nonEmptyString(parsed.patientId) || !nonEmptyString(parsed.maskedPhone)) {
    return null;
  }
  const visits = Array.isArray(parsed.visits)
    ? parsed.visits.map(decodeVisit).filter((v): v is VisitFixture => v !== null)
    : [];
  return {
    patientId: parsed.patientId,
    maskedPhone: parsed.maskedPhone,
    displayName: optionalString(parsed.displayName),
    visits,
  };
}
