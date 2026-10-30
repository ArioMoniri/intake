/**
 * INT-562 — the Safety queue, the console side (files/08 §3 "Safety queue",
 * §0c F19; invariant 49), over `GET /admin/safety-queue` (INT-406).
 *
 * A pure projection of the recorded body into what the page paints. It
 * decides nothing the server did not: the order is the inbox's (unacknowledged
 * first, oldest first; then the answered ones, newest answer first), and a
 * body out of that order is refused rather than re-sorted. What it adds are
 * refusals that mirror the platform's invariants:
 *
 * - **Ids and clocks only** (`SafetyQueueLeaked`, invariant 6). An entry id
 *   outside `sx_` + 32 hex, a tenant, session, visit, rule or subject that is
 *   not id-shaped, is the shape of a name or a patient's words reappearing on
 *   a console, so it is refused.
 * - **The vocabularies are sealed** (`SafetyQueueVocabularyRefused`). The
 *   kinds, the RED registers (invariant 21) and the age bands are the inbox's
 *   enums; a value outside them is a drifted or tampered body. Only a RED is
 *   told in a register.
 * - **The order is the inbox's** (`SafetyQueueOrderRefused`).
 *
 * Numbers leave as strings (invariant 22): minutes as integers, joined to
 * their unit by the console.
 */
import { ID, ISO, OpsPayloadRefused } from "../ops/guards";

export class SafetyQueuePayloadRefused extends OpsPayloadRefused {}
export class SafetyQueueLeaked extends SafetyQueuePayloadRefused {}
export class SafetyQueueVocabularyRefused extends SafetyQueuePayloadRefused {}
export class SafetyQueueOrderRefused extends SafetyQueuePayloadRefused {}

/** The inbox's entry kinds (`intake_platform.safety_inbox.EntryKind`). */
export const KINDS = ["red", "red_on_site", "visit_rescheduled", "visit_cancelled"] as const;
export type EntryKind = (typeof KINDS)[number];

/** How a RED was told (`clinical_schemas.triage.RedRegister`; invariant 21). */
export const REGISTERS = ["ALERT", "CALM", "SILENT", "DEFERRED_CLINICIAN"] as const;
export type RedRegister = (typeof REGISTERS)[number];

/** Where an open entry stands against its tenant's SLA (`AgeBand`). */
export const AGE_BANDS = ["within_sla", "past_sla"] as const;
export type AgeBand = (typeof AGE_BANDS)[number];

const ENTRY_ID = /^sx_[0-9a-f]{32}$/;

/** One row of `GET /admin/safety-queue` (services/api `safety_queue._row`). */
export interface QueueRowPayload {
  entry_id: string;
  tenant_id: string;
  session_id: string;
  visit_id: string;
  kind: string;
  rule_ids: string[];
  register: string | null;
  created_at: string;
  acknowledged: boolean;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  sla_minutes: number;
  elapsed_minutes: number;
  age_band: string | null;
}

export interface SafetyQueuePayload {
  entries: QueueRowPayload[];
}

export interface QueueRowView {
  entryId: string;
  tenantId: string;
  sessionId: string;
  visitId: string;
  kind: EntryKind;
  ruleIds: string[];
  register: RedRegister | null;
  createdAt: string;
  acknowledged: boolean;
  acknowledgedAt: string | null;
  acknowledgedBy: string | null;
  /** Minutes, as the integer the API gave (invariant 22: no grouping). */
  slaMinutes: string;
  elapsedMinutes: string;
  ageBand: AgeBand | null;
}

export interface SafetyQueueView {
  rows: QueueRowView[];
  /** Entries still waiting, and how many of those are past their SLA. */
  open: number;
  pastSla: number;
}

function id(value: unknown, what: string): string {
  if (typeof value !== "string" || !ID.test(value)) {
    throw new SafetyQueueLeaked("value_not_id_shaped", `${what} is not id-shaped (invariant 6)`);
  }
  return value;
}

function optionalId(value: unknown, what: string): string | null {
  return value === null ? null : id(value, what);
}

function entryId(value: unknown): string {
  if (typeof value !== "string" || !ENTRY_ID.test(value)) {
    throw new SafetyQueueLeaked("entry_id_not_shaped", "an entry id is sx_ + 32 hex");
  }
  return value;
}

function instant(value: unknown, what: string): string {
  if (typeof value !== "string" || !ISO.test(value)) {
    throw new SafetyQueueLeaked("instant_not_iso", `${what} is not an ISO instant`);
  }
  return value;
}

function minutes(value: unknown, what: string): string {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new SafetyQueueLeaked("minutes_not_a_count", `${what} is not a count of minutes`);
  }
  return String(value);
}

function sealed<T extends string>(value: unknown, vocabulary: readonly T[], what: string): T {
  if (typeof value !== "string" || !(vocabulary as readonly string[]).includes(value)) {
    throw new SafetyQueueVocabularyRefused(
      "outside_sealed_vocabulary",
      `${what} is outside the inbox's vocabulary`,
    );
  }
  return value as T;
}

function row(raw: QueueRowPayload): QueueRowView {
  const kind = sealed(raw.kind, KINDS, "kind");
  const register = raw.register === null ? null : sealed(raw.register, REGISTERS, "register");
  if (register !== null && kind !== "red") {
    throw new SafetyQueueVocabularyRefused(
      "register_on_a_non_red",
      "only a RED entry records a register",
    );
  }
  if (!Array.isArray(raw.rule_ids) || raw.rule_ids.length === 0) {
    throw new SafetyQueueLeaked("rule_ids_missing", "an entry names at least one rule");
  }
  const acknowledgedAt = raw.acknowledged_at === null ? null : instant(raw.acknowledged_at, "ack");
  const acknowledgedBy = optionalId(raw.acknowledged_by, "acknowledged_by");
  const acknowledged = raw.acknowledged === true;
  if (acknowledged !== (acknowledgedAt !== null) || acknowledged !== (acknowledgedBy !== null)) {
    throw new SafetyQueueLeaked(
      "acknowledgement_half_recorded",
      "an acknowledgement carries its instant and its subject, or neither",
    );
  }
  const ageBand = raw.age_band === null ? null : sealed(raw.age_band, AGE_BANDS, "age_band");
  if (acknowledged === (ageBand !== null)) {
    throw new SafetyQueueVocabularyRefused(
      "age_band_on_the_wrong_entry",
      "an open entry has an age band; an answered one has none",
    );
  }
  return {
    entryId: entryId(raw.entry_id),
    tenantId: id(raw.tenant_id, "tenant_id"),
    sessionId: id(raw.session_id, "session_id"),
    visitId: id(raw.visit_id, "visit_id"),
    kind,
    ruleIds: raw.rule_ids.map((rule) => id(rule, "rule id")),
    register,
    createdAt: instant(raw.created_at, "created_at"),
    acknowledged,
    acknowledgedAt,
    acknowledgedBy,
    slaMinutes: minutes(raw.sla_minutes, "sla_minutes"),
    elapsedMinutes: minutes(raw.elapsed_minutes, "elapsed_minutes"),
    ageBand,
  };
}

/** The inbox's order (INT-406; INT-553 F3 on the API), asserted, never applied. */
function assertOrder(rows: QueueRowView[]): void {
  const firstAnswered = rows.findIndex((r) => r.acknowledged);
  const open = firstAnswered < 0 ? rows : rows.slice(0, firstAnswered);
  const answered = firstAnswered < 0 ? [] : rows.slice(firstAnswered);
  if (answered.some((r) => !r.acknowledged)) {
    throw new SafetyQueueOrderRefused(
      "open_after_answered",
      "an open entry follows an answered one",
    );
  }
  for (let i = 1; i < open.length; i += 1) {
    if (open[i]!.createdAt < open[i - 1]!.createdAt) {
      throw new SafetyQueueOrderRefused("open_not_oldest_first", "open entries are oldest first");
    }
  }
  for (let i = 1; i < answered.length; i += 1) {
    if (answered[i]!.acknowledgedAt! > answered[i - 1]!.acknowledgedAt!) {
      throw new SafetyQueueOrderRefused(
        "answered_not_newest_first",
        "answered entries are newest answer first",
      );
    }
  }
}

export function renderSafetyQueue(payload: SafetyQueuePayload): SafetyQueueView {
  if (!Array.isArray(payload.entries)) {
    throw new SafetyQueueLeaked("entries_missing", "the queue is a list of entries");
  }
  const rows = payload.entries.map(row);
  assertOrder(rows);
  return {
    rows,
    open: rows.filter((r) => !r.acknowledged).length,
    pastSla: rows.filter((r) => r.ageBand === "past_sla").length,
  };
}
