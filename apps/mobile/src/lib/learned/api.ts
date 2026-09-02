/**
 * INT-140 — the overlay seam (INT-170's `/v1/me/learned`).
 *
 * Transport only. Three verbs, and deliberately not a fourth: `POST` is the
 * confirmation card, and a card needs the origin and the observed instant
 * that produced the candidate. The ledger holds neither — `GET` returns the
 * confirmed fact, not the candidate behind it — so a confirmation posted from
 * here would have to invent a provenance. Invariant 12 says a fact needs
 * patient or clinician confirmation; a confirmation with a made-up origin is
 * not one. Re-confirmation therefore happens where the origin exists: in the
 * visit that asks about the fact.
 *
 * Failure posture matches the consent and DSAR seams: unreachable or refused
 * resolves to `null`/`false`, and no server narrative reaches the patient.
 */
import { authedFetch } from "@/lib/auth/api";

import { parseLearnedFacts, type LedgerFact } from "./facts";

function path(key: string): string {
  // The key is a dotted ref, but it reaches a path segment, so it is escaped
  // rather than trusted: a key with a slash in it must not become a route.
  return `/v1/me/learned/${encodeURIComponent(key)}`;
}

/** The patient's own overlay. Null = unreachable; the caller claims nothing. */
export async function fetchLearnedFacts(): Promise<LedgerFact[] | null> {
  try {
    const response = await authedFetch("/v1/me/learned");
    if (!response.ok) {
      return null;
    }
    return parseLearnedFacts(await response.json());
  } catch {
    return null;
  }
}

/** Turn one field's share scope (files/09 §3). False = it did not land. */
export async function pushFactShared(key: string, shared: boolean): Promise<boolean> {
  try {
    const response = await authedFetch(path(key), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shared }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Delete one fact. A 404 counts as done: the record does not hold the fact,
 * which is the state the patient asked for. Anything else is not done, and
 * the caller keeps the fact on screen rather than implying it is gone.
 */
export async function forgetRecordFact(key: string): Promise<boolean> {
  try {
    const response = await authedFetch(path(key), { method: "DELETE" });
    return response.ok || response.status === 404;
  } catch {
    return false;
  }
}
