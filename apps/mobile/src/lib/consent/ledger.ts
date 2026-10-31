/**
 * Consent ledger reducer (INT-132) — pure, node-testable state behind the
 * İzinleriniz screens. It mirrors the server's INT-038 semantics exactly:
 *
 * - grant: fail closed — no loaded text, no grant; a grant binds the version
 *   and SHA-256 hash of the text that was actually shown;
 * - state: a bound grant whose hash no longer matches the current text is
 *   `stale` — shown for re-prompt, not honoured; a grant recorded before any
 *   text existed (dev seeds, hash null) is `unbound` and honoured until the
 *   first text lands, at which instant it goes stale (the text IS the bump);
 * - withdraw: instant, cascading in the same pass (voice → lane:affect;
 *   lane:linguistic deliberately survives; core → every other purpose,
 *   the default-on learning ones included),
 *   one queued op for the root — the server re-derives the cascade itself;
 * - queue: ops that could not reach the server yet stay here, in memory, in
 *   order. Nothing is persisted to disk: the server ledger is the source of
 *   truth and reconciliation happens on the next snapshot.
 *
 * INT-587 adds the share slot (./shareConsent, re-exported here): the share
 * text, what this phone did with it, and the per-note grant receipt the note
 * outbox requires. A core withdrawal takes it down too, as the server cascades.
 */
import { PURPOSES, purposeDef, type LegalBasis, type PurposeId, type PurposeUi } from "./purposes";
import {
  SHARE_SCOPE,
  freshShare,
  withdrawnShare,
  type ShareScope,
  type ShareState,
} from "./shareConsent";

export {
  SHARE_SCOPE,
  applyShareText,
  grantShare,
  shareView,
  withdrawShare,
  type ShareGrantReceipt,
  type ShareScope,
  type ShareStanding,
  type ShareState,
  type ShareView,
} from "./shareConsent";

export interface LoadedText {
  version: string;
  /** SHA-256 hex over the exact docs/legal file bytes, from the loader. */
  textHash: string;
  /** The Turkish consent copy itself — loader payload, never a catalog key. */
  body: string;
}

export type TextEntry = { status: "loaded"; text: LoadedText } | { status: "missing" };

export interface PurposeRecord {
  granted: boolean;
  /** True while the registry default stands — no explicit decision yet. */
  defaultOn: boolean;
  boundVersion: string | null;
  boundHash: string | null;
  /** The server declared this grant stale (its text moved server-side). */
  serverStale: boolean;
}

export type QueuedOp =
  | {
      kind: "grant";
      scope: PurposeId | ShareScope;
      version: string;
      textHash: string;
      atIso: string;
    }
  | { kind: "withdraw"; scope: PurposeId | ShareScope; atIso: string };

export interface LedgerState {
  records: Record<PurposeId, PurposeRecord>;
  texts: Record<PurposeId, TextEntry>;
  share: ShareState;
  queue: readonly QueuedOp[];
}

export type DisplayState = "on" | "off" | "pending_text" | "stale";

export interface PurposeView {
  id: PurposeId;
  ui: PurposeUi;
  basis: LegalBasis;
  parent: PurposeId | null;
  labelKey: (typeof PURPOSES)[number]["labelKey"];
  whoKey: (typeof PURPOSES)[number]["whoKey"];
  basisKey: (typeof PURPOSES)[number]["basisKey"];
  display: DisplayState;
  /** Effective: granted AND not stale — what gates behaviour. */
  allowed: boolean;
  grantable: boolean;
  withdrawable: boolean;
}

export interface ChangeResult {
  state: LedgerState;
  /** Scopes whose local state this change touched, root first. */
  flipped: readonly PurposeId[];
}

function baseRecord(defaultGranted: boolean): PurposeRecord {
  return {
    granted: defaultGranted,
    defaultOn: true,
    boundVersion: null,
    boundHash: null,
    serverStale: false,
  };
}

function emptyRecords(): Record<PurposeId, PurposeRecord> {
  const records = {} as Record<PurposeId, PurposeRecord>;
  for (const def of PURPOSES) {
    records[def.id] = baseRecord(def.defaultGranted);
  }
  return records;
}

function emptyTexts(): Record<PurposeId, TextEntry> {
  const texts = {} as Record<PurposeId, TextEntry>;
  for (const def of PURPOSES) {
    texts[def.id] = { status: "missing" };
  }
  return texts;
}

/** A brand-new account: registry defaults, no texts, nothing queued. */
export function freshLedger(): LedgerState {
  return { records: emptyRecords(), texts: emptyTexts(), share: freshShare(), queue: [] };
}

/**
 * Seed from the session's legacy ConsentState (dev fixtures). A session-true
 * key becomes an explicit grant with a NULL hash — exactly the server's
 * dev-seed row, which is honoured while unbound and goes stale the moment a
 * real text lands. Seeding is state, never a decision: nothing is queued.
 */
export function seedFromSession(consents: {
  core: boolean;
  voice: boolean;
  wellbeing: boolean;
  documents: boolean;
  health: boolean;
}): LedgerState {
  const state = freshLedger();
  for (const def of PURPOSES) {
    const key = def.sessionKey;
    if (key !== null && key !== "health" && consents[key]) {
      state.records[def.id] = {
        granted: true,
        defaultOn: false,
        boundVersion: null,
        boundHash: null,
        serverStale: false,
      };
    }
  }
  return state;
}

function isStale(record: PurposeRecord, entry: TextEntry): boolean {
  if (record.serverStale) {
    return true;
  }
  if (!record.granted || record.defaultOn) {
    return false;
  }
  if (entry.status !== "loaded") {
    return false; // unbound: honoured until a text exists (server semantics)
  }
  return record.boundHash === null || record.boundHash !== entry.text.textHash;
}

function allowedOf(state: LedgerState, id: PurposeId): boolean {
  const record = state.records[id];
  return record.granted && !isStale(record, state.texts[id]);
}

function displayOf(state: LedgerState, id: PurposeId): DisplayState {
  const record = state.records[id];
  if (isStale(record, state.texts[id])) {
    return "stale";
  }
  if (record.granted) {
    return "on";
  }
  if (state.texts[id].status !== "loaded" && record.defaultOn) {
    return "pending_text"; // never decided, and cannot be until a text lands
  }
  return "off";
}

export function viewOf(state: LedgerState): PurposeView[] {
  return PURPOSES.map((def) => {
    const display = displayOf(state, def.id);
    const allowed = allowedOf(state, def.id);
    const textLoaded = state.texts[def.id].status === "loaded";
    const affectBlocked = def.id === "lane:affect" && !allowedOf(state, "voice");
    return {
      id: def.id,
      ui: def.ui,
      basis: def.basis,
      parent: def.parent,
      labelKey: def.labelKey,
      whoKey: def.whoKey,
      basisKey: def.basisKey,
      display,
      allowed,
      grantable: textLoaded && !affectBlocked && !allowedOf(state, def.id),
      withdrawable: state.records[def.id].granted,
    };
  });
}

/** Merge loader texts. Records are untouched by design: a text bump can make
 * a grant stale, but can never re-grant — only an explicit grant rebinds. */
export function applyTexts(
  state: LedgerState,
  texts: Partial<Record<PurposeId, TextEntry>>,
): LedgerState {
  return { ...state, texts: { ...state.texts, ...texts } };
}

export interface ServerScope {
  scope: PurposeId;
  reason: "granted" | "default_on" | "unbound" | "absent" | "withdrawn" | "stale";
  version: string | null;
  textHash: string | null;
}

/** Reconcile with the server's consent_state answers (it is the ledger of
 * record; local state yields to it wherever it speaks). */
export function applyServerScopes(state: LedgerState, scopes: readonly ServerScope[]): LedgerState {
  const records = { ...state.records };
  for (const item of scopes) {
    const def = purposeDef(item.scope);
    if (def === null) {
      continue; // outside the closed list — never guess
    }
    switch (item.reason) {
      case "granted":
      case "unbound":
        records[def.id] = {
          granted: true,
          defaultOn: false,
          boundVersion: item.version,
          boundHash: item.textHash,
          serverStale: false,
        };
        break;
      case "stale":
        records[def.id] = {
          granted: true,
          defaultOn: false,
          boundVersion: item.version,
          boundHash: item.textHash,
          serverStale: true,
        };
        break;
      case "default_on":
        records[def.id] = baseRecord(true);
        break;
      case "absent":
        records[def.id] = baseRecord(false);
        break;
      case "withdrawn":
        records[def.id] = {
          granted: false,
          defaultOn: false,
          boundVersion: null,
          boundHash: null,
          serverStale: false,
        };
        break;
    }
  }
  return { ...state, records };
}

/**
 * Grant one purpose against the CURRENTLY loaded text. Refuses — returning
 * the state unchanged — when the purpose is off the closed list, the text is
 * missing (fail closed, invariant 18), or lane:affect is asked for without a
 * standing voice consent (it rides the voice stream).
 */
export function grant(state: LedgerState, id: PurposeId, atIso: string): ChangeResult {
  const def = purposeDef(id);
  const entry = state.texts[id];
  if (
    def === null ||
    entry.status !== "loaded" ||
    (id === "lane:affect" && !allowedOf(state, "voice"))
  ) {
    return { state, flipped: [] };
  }
  const records = {
    ...state.records,
    [id]: {
      granted: true,
      defaultOn: false,
      boundVersion: entry.text.version,
      boundHash: entry.text.textHash,
      serverStale: false,
    },
  };
  const op: QueuedOp = {
    kind: "grant",
    scope: id,
    version: entry.text.version,
    textHash: entry.text.textHash,
    atIso,
  };
  return { state: { ...state, records, queue: [...state.queue, op] }, flipped: [id] };
}

/**
 * Withdraw one purpose, instantly, cascading its children in the same pass.
 * Exactly one op is queued — the root — because the server re-derives the
 * cascade itself (mirroring it here would let the two drift).
 *
 * Core's cascade reaches the two default-on learning purposes too: the server
 * writes each one's opt-out (INT-537, legal review B1), because the core text
 * tells the patient every other permission closes with it.
 */
export function withdraw(state: LedgerState, id: PurposeId, atIso: string): ChangeResult {
  const def = purposeDef(id);
  if (def === null) {
    return { state, flipped: [] };
  }
  const touched: PurposeId[] = [id, ...def.cascadeChildren];
  const flipped = touched.filter((scope) => state.records[scope].granted);
  if (flipped.length === 0 && !state.records[id].defaultOn) {
    return { state, flipped: [] }; // already explicitly off — nothing to do
  }
  const records = { ...state.records };
  for (const scope of touched) {
    records[scope] = {
      granted: false,
      defaultOn: false,
      boundVersion: null,
      boundHash: null,
      serverStale: false,
    };
  }
  const op: QueuedOp = { kind: "withdraw", scope: id, atIso };
  // core's server cascade reaches the share family too (registry
  // dependents_of(core)); mirrored locally with no op of its own
  const share = id === "core" ? withdrawnShare(state.share, atIso) : state.share;
  return { state: { ...state, records, share, queue: [...state.queue, op] }, flipped };
}

/** Drop the first `count` ops after they reached the server. */
export function shiftQueue(state: LedgerState, count: number): LedgerState {
  return { ...state, queue: state.queue.slice(count) };
}

/**
 * The server answered a queued op with a refusal a retry cannot change (a 4xx
 * such as 409 `consent_text_changed` or 422 `purpose_unknown`). The op is
 * dropped — held at the head of the queue it would stall every op behind it,
 * a later withdrawal included (INT-587 legal review N5) — and a refused GRANT
 * is undone here so the patient is asked again: the phone must not count a
 * consent the server never recorded. A refused purpose withdrawal changes
 * nothing locally; the withdrawal already stands on this phone.
 *
 * INT-589: a refused SHARE withdrawal is not done on the server, so the phone
 * stops counting the share as withdrawn (`unknown`) and the control offers the
 * withdrawal again. It keeps `withdrawnAt`, though, so a note granted before
 * that instant stays parked: the patient asked for no more sharing, and the
 * phone still holds to that.
 */
export function dropRefusedHead(state: LedgerState): LedgerState {
  const head = state.queue[0];
  if (head === undefined) {
    return state;
  }
  const queue = state.queue.slice(1);
  if (head.kind !== "grant") {
    if (head.scope === SHARE_SCOPE && state.share.standing === "withdrawn") {
      return { ...state, share: { ...state.share, standing: "unknown" }, queue };
    }
    return { ...state, queue };
  }
  if (head.scope === SHARE_SCOPE) {
    return {
      ...state,
      share: { ...state.share, standing: "unknown", boundVersion: null, boundHash: null },
      queue,
    };
  }
  const records = {
    ...state.records,
    [head.scope]: {
      granted: false,
      defaultOn: false,
      boundVersion: null,
      boundHash: null,
      serverStale: false,
    },
  };
  return { ...state, records, queue };
}
