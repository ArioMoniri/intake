/**
 * Consent ledger reducer (INT-132) — the pure view-model behind İzinleriniz.
 * Fixture texts live HERE, inline, and nowhere else: docs/legal/consents is
 * INT-210's human deliverable and the production loader finds nothing until
 * it lands (the reducer must fail closed on that, which these tests pin).
 */
import { describe, expect, it } from "vitest";

import {
  applyServerScopes,
  applyTexts,
  freshLedger,
  grant,
  seedFromSession,
  shiftQueue,
  viewOf,
  withdraw,
  type TextEntry,
} from "./ledger";
import { purposeDef } from "./purposes";

const NOW = "2026-08-28T09:00:00Z";

const text = (version: string, fill: string): TextEntry => ({
  status: "loaded",
  text: {
    version,
    textHash: fill.repeat(64).slice(0, 64),
    body: `Deneme onay metni ${version} — yalnızca test dosyasında yaşar.`,
  },
});

const view = (state: ReturnType<typeof freshLedger>, id: string) =>
  viewOf(state).find((v) => v.id === id)!;

describe("fresh ledger (a new otp account)", () => {
  it("explicit purposes are off, learning purposes are default-on, queue empty", () => {
    const state = freshLedger();
    expect(view(state, "voice").allowed).toBe(false);
    expect(view(state, "wellbeing").allowed).toBe(false);
    expect(view(state, "research").allowed).toBe(false);
    expect(view(state, "learning:personal").allowed).toBe(true);
    expect(view(state, "learning:service_improvement").allowed).toBe(true);
    expect(state.queue).toEqual([]);
  });

  it("purposes without a text show the calm pending state", () => {
    const state = freshLedger();
    expect(view(state, "voice").display).toBe("pending_text");
    expect(view(state, "voice").grantable).toBe(false);
  });
});

describe("grant — fail closed without a text, hash-bound with one", () => {
  it("refuses while the text is missing (no text, no grant)", () => {
    const result = grant(freshLedger(), "voice", NOW);
    expect(result.flipped).toEqual([]);
    expect(result.state.queue).toEqual([]);
  });

  it("binds version and hash from the loaded text and queues the op", () => {
    const state = applyTexts(freshLedger(), { voice: text("2026-08-01", "a") });
    const result = grant(state, "voice", NOW);
    expect(result.flipped).toEqual(["voice"]);
    expect(result.state.records.voice.boundVersion).toBe("2026-08-01");
    expect(result.state.records.voice.boundHash).toBe("a".repeat(64));
    expect(result.state.queue).toEqual([
      {
        kind: "grant",
        scope: "voice",
        version: "2026-08-01",
        textHash: "a".repeat(64),
        atIso: NOW,
      },
    ]);
  });

  it("core is information: grant and withdraw both refuse", () => {
    const state = applyTexts(freshLedger(), { core: text("v1", "c") });
    expect(grant(state, "core", NOW).flipped).toEqual([]);
    expect(withdraw(state, "core", NOW).flipped).toEqual([]);
    expect(view(state, "core").display).toBe("info");
  });

  it("lane:affect rides the voice stream: not grantable while voice is off", () => {
    const state = applyTexts(freshLedger(), {
      "lane:affect": text("v1", "d"),
      voice: text("v1", "e"),
    });
    expect(grant(state, "lane:affect", NOW).flipped).toEqual([]);
    const voiced = grant(state, "voice", NOW).state;
    expect(grant(voiced, "lane:affect", NOW).flipped).toEqual(["lane:affect"]);
  });
});

describe("withdraw — instant, cascading, one queued op for the root", () => {
  const grantedVoiceStack = () => {
    let state = applyTexts(freshLedger(), {
      voice: text("v1", "1"),
      "lane:affect": text("v1", "2"),
      "lane:linguistic": text("v1", "3"),
    });
    state = grant(state, "voice", NOW).state;
    state = grant(state, "lane:affect", NOW).state;
    state = grant(state, "lane:linguistic", NOW).state;
    return state;
  };

  it("voice withdrawal drags lane:affect down; lane:linguistic is independent", () => {
    const result = withdraw(grantedVoiceStack(), "voice", NOW);
    expect(result.flipped).toEqual(["voice", "lane:affect"]);
    expect(view(result.state, "voice").allowed).toBe(false);
    expect(view(result.state, "lane:affect").allowed).toBe(false);
    expect(view(result.state, "lane:linguistic").allowed).toBe(true);
  });

  it("queues exactly one withdraw op — the server cascades the rest itself", () => {
    const result = withdraw(grantedVoiceStack(), "voice", NOW);
    const withdrawals = result.state.queue.filter((op) => op.kind === "withdraw");
    expect(withdrawals).toEqual([{ kind: "withdraw", scope: "voice", atIso: NOW }]);
  });

  it("opting out of a default-on purpose is withdrawable and leaves it off", () => {
    const result = withdraw(freshLedger(), "learning:service_improvement", NOW);
    expect(result.flipped).toEqual(["learning:service_improvement"]);
    expect(view(result.state, "learning:service_improvement").allowed).toBe(false);
    expect(result.state.queue).toEqual([
      { kind: "withdraw", scope: "learning:service_improvement", atIso: NOW },
    ]);
  });

  it("re-enabling an opted-out learning purpose needs a text like any grant", () => {
    const optedOut = withdraw(freshLedger(), "learning:personal", NOW).state;
    expect(grant(optedOut, "learning:personal", NOW).flipped).toEqual([]);
    expect(view(optedOut, "learning:personal").display).toBe("off");
    const withText = applyTexts(optedOut, { "learning:personal": text("v1", "f") });
    expect(grant(withText, "learning:personal", NOW).flipped).toEqual(["learning:personal"]);
  });
});

describe("versioning — stale on change, re-prompt, never a silent re-grant", () => {
  it("a text bump makes the grant stale: not honoured, shown for re-prompt", () => {
    let state = applyTexts(freshLedger(), { documents: text("v1", "a") });
    state = grant(state, "documents", NOW).state;
    const bumped = applyTexts(state, { documents: text("v2", "b") });
    expect(view(bumped, "documents").allowed).toBe(false);
    expect(view(bumped, "documents").display).toBe("stale");
    // the record itself is untouched — nothing was silently re-granted
    expect(bumped.records.documents.boundVersion).toBe("v1");
  });

  it("re-granting after a bump binds the NEW version and hash", () => {
    let state = applyTexts(freshLedger(), { documents: text("v1", "a") });
    state = grant(state, "documents", NOW).state;
    state = applyTexts(state, { documents: text("v2", "b") });
    const regranted = grant(state, "documents", "2026-08-28T10:00:00Z").state;
    expect(view(regranted, "documents").allowed).toBe(true);
    expect(regranted.records.documents.boundVersion).toBe("v2");
    expect(regranted.records.documents.boundHash).toBe("b".repeat(64));
  });

  it("dev-seeded session grants (hash NULL) go stale the moment a text exists", () => {
    const seeded = seedFromSession({
      core: true,
      voice: true,
      wellbeing: false,
      documents: false,
      health: false,
    });
    // before any text: the grant is unbound and honoured (server semantics)
    expect(view(seeded, "voice").allowed).toBe(true);
    const bound = applyTexts(seeded, { voice: text("v1", "9") });
    expect(view(bound, "voice").allowed).toBe(false);
    expect(view(bound, "voice").display).toBe("stale");
  });

  it("unbound grants are honoured but NEW grants stay impossible without texts", () => {
    const seeded = seedFromSession({
      core: true,
      voice: true,
      wellbeing: false,
      documents: false,
      health: false,
    });
    expect(view(seeded, "voice").allowed).toBe(true);
    expect(grant(seeded, "wellbeing", NOW).flipped).toEqual([]);
  });

  it("default-on learning purposes never go stale from a text landing", () => {
    // no açık rıza text governs a non-consent basis; text arrival must not
    // flip a default-on purpose into a re-prompt
    const state = applyTexts(freshLedger(), { "learning:personal": text("v1", "e") });
    expect(view(state, "learning:personal").allowed).toBe(true);
    expect(view(state, "learning:personal").display).toBe("on");
  });
});

describe("server snapshot reconciliation", () => {
  it("maps the guard reasons onto records", () => {
    const state = applyServerScopes(freshLedger(), [
      { scope: "voice", reason: "granted", version: "v3", textHash: "h".repeat(64) },
      { scope: "documents", reason: "stale", version: "v1", textHash: "x".repeat(64) },
      { scope: "wellbeing", reason: "withdrawn", version: null, textHash: null },
      { scope: "learning:personal", reason: "default_on", version: null, textHash: null },
    ]);
    expect(view(state, "voice").allowed).toBe(true);
    expect(view(state, "documents").allowed).toBe(false);
    expect(view(state, "documents").display).toBe("stale");
    expect(view(state, "wellbeing").allowed).toBe(false);
    expect(view(state, "learning:personal").allowed).toBe(true);
  });

  it("a server-declared stale is honoured even before the new text arrives", () => {
    const state = applyServerScopes(freshLedger(), [
      { scope: "voice", reason: "stale", version: "v1", textHash: "a".repeat(64) },
    ]);
    expect(view(state, "voice").allowed).toBe(false);
    expect(view(state, "voice").display).toBe("stale");
  });
});

describe("queue — honest offline semantics", () => {
  it("ops accumulate in order and shift off the front once pushed", () => {
    let state = applyTexts(freshLedger(), { voice: text("v1", "a") });
    state = grant(state, "voice", NOW).state;
    state = withdraw(state, "voice", "2026-08-28T09:05:00Z").state;
    expect(state.queue.map((op) => op.kind)).toEqual(["grant", "withdraw"]);
    const flushedOne = shiftQueue(state, 1);
    expect(flushedOne.queue.map((op) => op.kind)).toEqual(["withdraw"]);
    expect(shiftQueue(flushedOne, 1).queue).toEqual([]);
  });

  it("every queued grant carries the version and hash that were shown", () => {
    let state = applyTexts(freshLedger(), { satisfaction: text("v7", "b") });
    state = grant(state, "satisfaction", NOW).state;
    const op = state.queue[0];
    expect(op.kind).toBe("grant");
    if (op.kind === "grant") {
      expect(op.version).toBe("v7");
      expect(op.textHash).toBe("b".repeat(64));
    }
  });
});

describe("registry sanity used by the screens", () => {
  it("session mirror keys cover exactly the legacy ConsentState purposes", () => {
    expect(purposeDef("voice")!.sessionKey).toBe("voice");
    expect(purposeDef("wellbeing")!.sessionKey).toBe("wellbeing");
    expect(purposeDef("documents")!.sessionKey).toBe("documents");
    expect(purposeDef("core")!.sessionKey).toBe("core");
    expect(purposeDef("lane:affect")!.sessionKey).toBeNull();
    expect(purposeDef("research")!.sessionKey).toBeNull();
  });

  it("unknown scopes resolve to null, never to a guessed purpose", () => {
    expect(purposeDef("share")).toBeNull();
    expect(purposeDef("share:previsit_note")).toBeNull();
    expect(purposeDef("")).toBeNull();
  });
});
