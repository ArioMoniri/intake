/**
 * INT-587 — the share consent the app asks for when a note is sent.
 *
 * `share:previsit_note` is the parameterised share purpose (files/06 §2). It
 * has no İzinleriniz row on purpose — a bare share toggle would be the bundled
 * consent files/06 §2 forbids — so it lives in its own slot of the ledger and
 * is granted in context, at the send, against the docs/legal share text the
 * server serves (invariant 18). The server snapshot reports no standing for a
 * parameterised purpose, so what this phone knows is only what it did in this
 * session: unknown until the patient grants or withdraws.
 */
import { describe, expect, it } from "vitest";

import {
  SHARE_SCOPE,
  applyShareText,
  freshLedger,
  grantShare,
  shareView,
  withdraw,
  withdrawShare,
  type TextEntry,
} from "./ledger";

const SHARE_TEXT: TextEntry = {
  status: "loaded",
  text: { version: "2026-10-28.syn1", textHash: "c".repeat(64), body: "Deneme metni." },
};
const AT = "2026-10-29T10:00:00Z";

describe("the share text is the only thing a share grant can bind to", () => {
  it("a fresh ledger has no share text and nothing can be granted (invariant 18)", () => {
    const state = freshLedger();
    expect(shareView(state).display).toBe("pending_text");
    const result = grantShare(state, AT);
    expect(result.receipt).toBeNull();
    expect(result.state).toBe(state);
    expect(state.queue).toEqual([]);
  });

  it("a grant binds the version and hash that were shown, and queues one grant op", () => {
    const loaded = applyShareText(freshLedger(), SHARE_TEXT);
    const result = grantShare(loaded, AT);
    expect(result.receipt).toMatchObject({
      scope: SHARE_SCOPE,
      version: "2026-10-28.syn1",
      textHash: "c".repeat(64),
    });
    expect(result.state.queue).toEqual([
      {
        kind: "grant",
        scope: SHARE_SCOPE,
        version: "2026-10-28.syn1",
        textHash: "c".repeat(64),
        atIso: AT,
      },
    ]);
    expect(shareView(result.state).display).toBe("on");
  });

  it("is asked at every send: a second grant is recorded again, never assumed", () => {
    const once = grantShare(applyShareText(freshLedger(), SHARE_TEXT), AT).state;
    const twice = grantShare(once, AT);
    expect(twice.receipt).not.toBeNull();
    expect(twice.state.queue).toHaveLength(2);
  });

  it("a moved text makes the grant stale — the receipt no longer stands", () => {
    const granted = grantShare(applyShareText(freshLedger(), SHARE_TEXT), AT).state;
    const moved = applyShareText(granted, {
      status: "loaded",
      text: { version: "2026-11-01.syn2", textHash: "d".repeat(64), body: "Yeni metin." },
    });
    expect(shareView(moved).display).toBe("stale");
    expect(shareView(moved).standing).toBe("granted");
  });
});

describe("the patient can take it back", () => {
  it("withdrawal is instant locally and queues exactly one op for the server", () => {
    const granted = grantShare(applyShareText(freshLedger(), SHARE_TEXT), AT).state;
    const result = withdrawShare(granted, AT);
    expect(result.changed).toBe(true);
    expect(shareView(result.state).standing).toBe("withdrawn");
    expect(result.state.queue.at(-1)).toEqual({ kind: "withdraw", scope: SHARE_SCOPE, atIso: AT });
  });

  it("is offered even when this phone never saw the grant — the server may hold one", () => {
    const state = applyShareText(freshLedger(), SHARE_TEXT);
    expect(shareView(state).standing).toBe("unknown");
    expect(shareView(state).withdrawable).toBe(true);
    expect(withdrawShare(state, AT).changed).toBe(true);
  });

  it("is not queued twice", () => {
    const once = withdrawShare(applyShareText(freshLedger(), SHARE_TEXT), AT).state;
    const twice = withdrawShare(once, AT);
    expect(twice.changed).toBe(false);
    expect(twice.state).toBe(once);
  });

  it("a core withdrawal takes the share down with it, as the server cascades", () => {
    const granted = grantShare(applyShareText(freshLedger(), SHARE_TEXT), AT).state;
    const result = withdraw(granted, "core", AT);
    expect(shareView(result.state).standing).toBe("withdrawn");
    // one op for the root only: the server derives the cascade itself
    expect(result.state.queue.filter((op) => op.kind === "withdraw")).toEqual([
      { kind: "withdraw", scope: "core", atIso: AT },
    ]);
  });

  it("a grant after a withdrawal re-opens it against the current text", () => {
    const withdrawn = withdrawShare(applyShareText(freshLedger(), SHARE_TEXT), AT).state;
    const regranted = grantShare(withdrawn, AT);
    expect(regranted.receipt).not.toBeNull();
    expect(shareView(regranted.state).standing).toBe("granted");
  });
});

describe("the scope is the server's", () => {
  it("is the parameterised share purpose notes.py enforces", () => {
    expect(SHARE_SCOPE).toBe("share:previsit_note");
  });
});
