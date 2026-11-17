/**
 * INT-587 — the share slot of the consent ledger (lib/consent/ledger.ts
 * re-exports everything here; import it from there).
 *
 * `share:previsit_note` is the parameterised share purpose the server checks
 * when a note is sent and a Doctor Link is issued. It has no İzinleriniz row
 * (purposes.ts says why) and the server's snapshot reports no standing for it,
 * so the slot holds the share TEXT the loader serves and what THIS phone did
 * with it in this session: `unknown` until the patient grants or withdraws.
 *
 * A grant is asked at every send (share.tr.md: "Paylaşım onayı, notunuzu
 * gönderirken ayrıca istenir"), binds the text shown, queues one op like any
 * other grant, and returns a receipt for ONE note — the only thing the note
 * outbox (lib/intake/delivery) queues or releases a note against. A grant for
 * note B can never send note C; and every withdrawal (direct, or through core)
 * records its instant, so a note granted before it stays parked until it gets
 * a grant of its own (INT-587 legal review B1).
 *
 * Pure. The ledger types are imported as types only, so there is no runtime
 * cycle between the two modules.
 */
import type { DisplayState, LedgerState, QueuedOp, TextEntry } from "./ledger";

/** The parameterised share scope a sent note is checked against
 * (services/api notes.SHARE_SCOPE; pinned by e2e/noteDelivery.spec.ts). */
export const SHARE_SCOPE = "share:previsit_note";
export type ShareScope = typeof SHARE_SCOPE;

/** What this phone knows of the share consent in this session. */
export type ShareStanding = "unknown" | "granted" | "withdrawn";

export interface ShareState {
  /** The docs/legal share text, as the loader served it (invariant 18). */
  text: TextEntry;
  standing: ShareStanding;
  boundVersion: string | null;
  boundHash: string | null;
  /**
   * When the share consent was last withdrawn on this phone (directly, or by
   * a core withdrawal). A later grant does not erase it: a note granted before
   * this instant was granted under a consent the patient has since taken back,
   * and only a grant for THAT note releases it.
   */
  withdrawnAt: string | null;
}

declare const receiptBrand: unique symbol;

/**
 * Proof that the patient granted the share consent against a loaded text, in
 * this session, for ONE note at one instant. Only `grantShare` makes one.
 */
export interface ShareGrantReceipt {
  readonly scope: ShareScope;
  readonly version: string;
  readonly textHash: string;
  /** The note this grant was given for. */
  readonly visitId: string;
  readonly atIso: string;
  readonly [receiptBrand]: true;
}

export function freshShare(): ShareState {
  return {
    text: { status: "missing" },
    standing: "unknown",
    boundVersion: null,
    boundHash: null,
    withdrawnAt: null,
  };
}

export function withdrawnShare(share: ShareState, atIso: string): ShareState {
  return {
    ...share,
    standing: "withdrawn",
    boundVersion: null,
    boundHash: null,
    withdrawnAt: atIso,
  };
}

/** Merge the loader's share text. Like `applyTexts`, a text can make a grant
 * stale but never re-grants. */
export function applyShareText(state: LedgerState, text: TextEntry): LedgerState {
  return { ...state, share: { ...state.share, text } };
}

export interface ShareView {
  display: DisplayState;
  standing: ShareStanding;
  text: TextEntry;
  /** True once a text is loaded: the share is asked at every send. */
  grantable: boolean;
  /** True unless withdrawn here already — the server may hold a grant from
   * an earlier session, so "this phone never saw one" is not "nothing to stop". */
  withdrawable: boolean;
}

export function shareView(state: LedgerState): ShareView {
  const { share } = state;
  const loaded = share.text.status === "loaded";
  let display: DisplayState;
  if (share.standing === "granted") {
    const current = share.text.status === "loaded" ? share.text.text.textHash : null;
    display = current !== null && share.boundHash !== current ? "stale" : "on";
  } else if (!loaded) {
    display = "pending_text";
  } else {
    display = "off";
  }
  return {
    display,
    standing: share.standing,
    text: share.text,
    grantable: loaded,
    withdrawable: share.standing !== "withdrawn",
  };
}

/**
 * Grant the share consent against the CURRENTLY loaded share text, for one
 * note. Fails closed — state unchanged, no receipt — when no text is loaded
 * (invariant 18). A grant is recorded every time it is given, never assumed
 * from an earlier one: each send is its own consent.
 */
export function grantShare(
  state: LedgerState,
  atIso: string,
  visitId: string,
): { state: LedgerState; receipt: ShareGrantReceipt | null } {
  const entry = state.share.text;
  if (entry.status !== "loaded") {
    return { state, receipt: null };
  }
  const { version, textHash } = entry.text;
  const op: QueuedOp = { kind: "grant", scope: SHARE_SCOPE, version, textHash, atIso };
  const receipt = { scope: SHARE_SCOPE, version, textHash, visitId, atIso } as ShareGrantReceipt;
  return {
    state: {
      ...state,
      share: { ...state.share, standing: "granted", boundVersion: version, boundHash: textHash },
      queue: [...state.queue, op],
    },
    receipt,
  };
}

/** Withdraw the share consent: instant here, one op for the server, which
 * revokes every live share and Doctor Link in the same pass (consents.py). */
export function withdrawShare(
  state: LedgerState,
  atIso: string,
): { state: LedgerState; changed: boolean } {
  if (state.share.standing === "withdrawn") {
    return { state, changed: false };
  }
  const op: QueuedOp = { kind: "withdraw", scope: SHARE_SCOPE, atIso };
  return {
    state: { ...state, share: withdrawnShare(state.share, atIso), queue: [...state.queue, op] },
    changed: true,
  };
}
