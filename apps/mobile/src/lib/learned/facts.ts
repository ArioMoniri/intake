/**
 * INT-140 — the ledger view of *Me → Hakkımda öğrendikleri*.
 *
 * files/09 §3 asks for four things on this screen: every learned fact shows
 * "where from", the patient can correct or delete it, the share scope is
 * per-field, and a fact older than twelve months is re-confirmed before use.
 * This module is the shape those four things are read into.
 *
 * Two boundaries are enforced by the type rather than by discipline.
 *
 * **Invariant 12.** `LedgerFact.source` is `CarriedFactSource` — the closed
 * three-member CONFIRMED vocabulary shared with `intake/carriedFacts` and
 * with `clinical_schemas.overlay.LearnedFactSource`. There is no unconfirmed
 * member to hold, so a row arriving with one is dropped rather than rendered
 * with a hedge: a fact nobody confirmed is not a fact about this patient, and
 * showing it with a caveat would still be showing it.
 *
 * **Invariant 22.** A held value becomes patient copy only when it already IS
 * a phrase the patient said. A bare number reaching this screen has neither a
 * unit nor the question it answered, so it is not printed as text; the row
 * keeps its provenance, its scope and its delete control and takes a
 * catalogue label instead. Rendering `12` as a sentence would be a number
 * crossing a representation boundary with nothing to guard it.
 */
import type { CarriedFact, CarriedFactSource } from "../intake/carriedFacts";

/**
 * The three confirmed provenances, as a value. Written out rather than
 * derived so the union and the runtime list cannot drift apart.
 */
export const CONFIRMED_SOURCES: readonly CarriedFactSource[] = [
  "confirmed_intake_extraction",
  "clinician_accepted_note",
  "confirmed_imported_record",
];

/**
 * Where a fact is held. The distinction is the patient's, not an
 * implementation detail: `record` travels with them between visits and
 * clinicians, `device` exists on this phone and nowhere else.
 */
export type LedgerOrigin = "record" | "device";

export interface LedgerFact {
  /** The overlay key for a record fact; the carried id for a device one. */
  id: string;
  origin: LedgerOrigin;
  /** The recorded phrase, or null when the held value has no reading. */
  text: string | null;
  source: CarriedFactSource;
  recordedAt: string;
  /**
   * Per-field share scope (files/09 §3). `null` on a device-held fact: the
   * phone holds no scope for it, and inventing one would be a claim about
   * the record rather than a reading of it.
   */
  shared: boolean | null;
  /** The server's twelve-month verdict — never a clock on this device. */
  needsReconfirmation: boolean;
}

/** The reading of a held value, or null when it has none. */
export function readableValue(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/** One row of `GET /v1/me/learned`, or null when it is not one this app reads. */
export function parseLearnedFact(raw: unknown): LedgerFact | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const row = raw as Record<string, unknown>;
  const id = typeof row.key === "string" && row.key.trim().length > 0 ? row.key : null;
  const source = CONFIRMED_SOURCES.find((candidate) => candidate === row.source) ?? null;
  const sourceRef =
    typeof row.source_ref === "string" && row.source_ref.trim().length > 0 ? row.source_ref : null;
  const recordedAt =
    typeof row.confirmed_at === "string" && row.confirmed_at.trim().length > 0
      ? row.confirmed_at
      : null;
  if (
    id === null ||
    source === null ||
    sourceRef === null ||
    recordedAt === null ||
    typeof row.shared !== "boolean" ||
    typeof row.needs_reconfirmation !== "boolean"
  ) {
    return null;
  }
  return {
    id,
    origin: "record",
    text: readableValue(row.value),
    source,
    recordedAt,
    shared: row.shared,
    needsReconfirmation: row.needs_reconfirmation,
  };
}

/** The route's envelope. A malformed one is no facts, never a partial claim. */
export function parseLearnedFacts(raw: unknown): LedgerFact[] {
  if (typeof raw !== "object" || raw === null) {
    return [];
  }
  const facts = (raw as Record<string, unknown>).facts;
  if (!Array.isArray(facts)) {
    return [];
  }
  return facts.map(parseLearnedFact).filter((fact): fact is LedgerFact => fact !== null);
}

/** A fact this device carries out of an earlier visit (INT-247). */
export function ledgerFactFromCarried(fact: CarriedFact): LedgerFact {
  return {
    id: fact.id,
    origin: "device",
    text: fact.text,
    source: fact.source,
    recordedAt: fact.assertedAt,
    shared: null,
    needsReconfirmation: false,
  };
}

/** One fact's scope turned, the rest untouched and identical by reference. */
export function withSharedFact(
  facts: readonly LedgerFact[],
  id: string,
  shared: boolean,
): LedgerFact[] {
  return facts.map((fact) => (fact.id === id ? { ...fact, shared } : fact));
}

export function withoutFact(facts: readonly LedgerFact[], id: string): LedgerFact[] {
  return facts.filter((fact) => fact.id !== id);
}
