/**
 * INT-603 — what a tap on a consent switch does, as pure facts.
 *
 * The design audit (2026-11, K1-K2) found the İzinleriniz state control was a
 * badge-like pill that withdrew on one tap when it said "Açık" and opened the
 * text when it said anything else, and that two rows read "Açık" on first run
 * under a body promising nothing that needs consent comes on.
 *
 * Pinned here:
 * - no consent-scope (açık rıza) row is checked before the patient acts, for a
 *   fresh ledger and for a real (otp) account's all-off seed;
 * - no row at all is checked on first run: legal review round 2 (the owner's
 *   KVKK approval, D43) turned the two learning rows off too,
 *   on the phone and in the server registry, until counsel records a basis;
 * - granting needs no confirmation: an unchecked switch opens the text, where
 *   the grant is made against it;
 * - withdrawing asks once, and the confirmation names what stops (the purpose
 *   and every granted purpose its cascade takes down) and says it takes effect
 *   immediately, through existing catalogue facts;
 * - the confirmation itself changes nothing: only the confirmed withdrawal
 *   queues the one op the server records and audits (invariant 4).
 */
import { describe, expect, it } from "vitest";

import { en } from "@/lib/i18n/en";
import { tr } from "@/lib/i18n/tr";

import {
  applyTexts,
  freshLedger,
  grant,
  seedFromSession,
  viewOf,
  withdraw,
  type LedgerState,
  type TextEntry,
} from "./ledger";
import { PURPOSES } from "./purposes";
import {
  DEFAULT_ON_AWAITING_COUNSEL,
  defaultOnViolations,
  isConsentScope,
  switchChecked,
  switchIntent,
  withdrawConfirmation,
} from "./switchIntent";

const loaded = (version: string, hash: string): TextEntry => ({
  status: "loaded",
  text: { version, textHash: hash, body: "Deneme metni — yalnızca test." },
});

const ALL_OFF = { core: false, voice: false, wellbeing: false, documents: false, health: false };

const viewFor = (state: LedgerState, id: string) => viewOf(state).find((v) => v.id === id)!;

function withVoiceAndAffect(): LedgerState {
  let state = applyTexts(freshLedger(), {
    voice: loaded("v1", "1".repeat(64)),
    "lane:affect": loaded("v1", "2".repeat(64)),
    "lane:linguistic": loaded("v1", "3".repeat(64)),
  });
  state = grant(state, "voice", "2026-11-17T00:00:00Z").state;
  state = grant(state, "lane:affect", "2026-11-17T00:00:01Z").state;
  return state;
}

describe("acceptance 1 — no consent row defaults on, checked by purpose id", () => {
  // Legal review round 1: the check reads purpose IDS, never the registry's
  // basis label, so relabelling a basis cannot make it pass. Round 2 emptied
  // the exception list (both learning rows are off until counsel records a
  // basis, HB-L27); it may only stay empty.
  it("no purpose id defaults on, and the exception list is empty", () => {
    expect(defaultOnViolations(PURPOSES)).toEqual([]);
    expect([...DEFAULT_ON_AWAITING_COUNSEL]).toEqual([]);
  });

  it("near miss: flipping a learning default on fails the check", () => {
    for (const id of ["learning:personal", "learning:service_improvement"]) {
      const flipped = PURPOSES.map((p) => (p.id === id ? { ...p, defaultGranted: true } : p));
      expect(defaultOnViolations(flipped), id).toEqual([id]);
    }
  });

  it("near miss: any id defaulting on fails", () => {
    const flipped = PURPOSES.map((p) => (p.id === "research" ? { ...p, defaultGranted: true } : p));
    expect(defaultOnViolations(flipped)).toEqual(["research"]);
    const core = PURPOSES.map((p) => (p.id === "core" ? { ...p, defaultGranted: true } : p));
    expect(defaultOnViolations(core)).toEqual(["core"]);
    const extra = [...PURPOSES, { id: "learning:other", defaultGranted: true }];
    expect(defaultOnViolations(extra)).toEqual(["learning:other"]);
  });

  it("no switch at all is checked on a fresh ledger or a real account's first run", () => {
    for (const state of [freshLedger(), seedFromSession(ALL_OFF)]) {
      expect(
        viewOf(state)
          .filter(switchChecked)
          .map((v) => v.id),
      ).toEqual([]);
    }
  });

  it("a consent scope is exactly an açık rıza purpose", () => {
    const scopes = PURPOSES.filter((p) => p.basis === "explicit_consent").map((p) => p.id);
    expect(
      viewOf(freshLedger())
        .filter(isConsentScope)
        .map((v) => v.id),
    ).toEqual(scopes);
    // every purpose, the learning ones included (legal review round 2)
    expect(scopes).toEqual(PURPOSES.map((p) => p.id));
  });

  it("on a fresh ledger no consent-scope switch is checked", () => {
    for (const view of viewOf(freshLedger()).filter(isConsentScope)) {
      expect(switchChecked(view), view.id).toBe(false);
    }
  });

  it("a real account's first run (every session consent off) checks none either", () => {
    for (const view of viewOf(seedFromSession(ALL_OFF)).filter(isConsentScope)) {
      expect(switchChecked(view), view.id).toBe(false);
    }
  });

  it("with every text loaded, still none is checked until the patient grants", () => {
    const texts: Record<string, TextEntry> = {};
    for (const p of PURPOSES) texts[p.id] = loaded("v1", "a".repeat(64));
    const state = applyTexts(freshLedger(), texts);
    for (const view of viewOf(state).filter(isConsentScope)) {
      expect(switchChecked(view), view.id).toBe(false);
    }
  });

  it("with every text loaded, the learning rows too stay off until the patient grants", () => {
    const texts: Record<string, TextEntry> = {};
    for (const p of PURPOSES) texts[p.id] = loaded("v1", "a".repeat(64));
    const state = applyTexts(freshLedger(), texts);
    expect(
      viewOf(state)
        .filter(switchChecked)
        .map((v) => v.id),
    ).toEqual([]);
  });

  it("near miss: a granted consent scope IS checked — the switch shows the real state", () => {
    expect(switchChecked(viewFor(withVoiceAndAffect(), "voice"))).toBe(true);
  });

  it("a stale grant is not shown as checked (it is not honoured)", () => {
    const bumped = applyTexts(withVoiceAndAffect(), { voice: loaded("v2", "9".repeat(64)) });
    expect(switchChecked(viewFor(bumped, "voice"))).toBe(false);
  });
});

describe("acceptance 2 — granting needs no confirmation; withdrawing asks once", () => {
  it("an unchecked switch opens the text, where the grant is made (no confirmation)", () => {
    const state = freshLedger();
    for (const id of ["core", "voice", "wellbeing", "documents", "research"]) {
      expect(switchIntent(viewFor(state, id)), id).toBe("open_detail");
      expect(withdrawConfirmation(viewOf(state), id as never), id).toBeNull();
    }
  });

  it("a pending or stale row opens the text too", () => {
    const bumped = applyTexts(withVoiceAndAffect(), { voice: loaded("v2", "9".repeat(64)) });
    expect(viewFor(freshLedger(), "wellbeing").display).toBe("pending_text");
    expect(switchIntent(viewFor(freshLedger(), "wellbeing"))).toBe("open_detail");
    // a stale grant is not honoured, so its switch is off; the detail holds
    // both the re-approval and its withdraw control
    expect(viewFor(bumped, "voice").display).toBe("stale");
    expect(switchIntent(viewFor(bumped, "voice"))).toBe("open_detail");
  });

  it("a checked consent asks for confirmation instead of withdrawing", () => {
    const state = withVoiceAndAffect();
    expect(switchIntent(viewFor(state, "voice"))).toBe("confirm_withdraw");
  });

  it("the confirmation names what stops: the purpose and its granted cascade", () => {
    const confirm = withdrawConfirmation(viewOf(withVoiceAndAffect()), "voice")!;
    expect(confirm.stopKeys).toEqual(["consent.voice", "consent.lane.affect"]);
    // lane:linguistic was never granted here and is not in the voice cascade
    expect(confirm.stopKeys).not.toContain("consent.lane.linguistic");
  });

  it("near miss: an ungranted cascade child is not listed as stopping", () => {
    let state = applyTexts(freshLedger(), { voice: loaded("v1", "1".repeat(64)) });
    state = grant(state, "voice", "2026-11-17T00:00:00Z").state;
    expect(withdrawConfirmation(viewOf(state), "voice")!.stopKeys).toEqual(["consent.voice"]);
  });

  it("withdrawing core lists every granted purpose the cascade takes down", () => {
    let state = applyTexts(freshLedger(), {
      core: loaded("v1", "c".repeat(64)),
      "learning:personal": loaded("v1", "d".repeat(64)),
    });
    expect(
      withdrawConfirmation(viewOf(grant(state, "core", "2026-11-17T00:00:00Z").state), "core")!
        .stopKeys,
    ).toEqual(["consent.core"]);
    state = grant(state, "core", "2026-11-17T00:00:00Z").state;
    state = grant(state, "learning:personal", "2026-11-17T00:00:01Z").state;
    expect(withdrawConfirmation(viewOf(state), "core")!.stopKeys).toEqual([
      "consent.core",
      "consent.learning.personal",
    ]);
    // the list is exactly what withdraw() flips — the two cannot drift
    const flipped = withdraw(state, "core", "2026-11-17T00:01:00Z").flipped;
    expect(flipped).toEqual(["core", "learning:personal"]);
  });

  it("a consent withdrawal says it takes effect immediately, through the existing fact", () => {
    const confirm = withdrawConfirmation(viewOf(withVoiceAndAffect()), "voice")!;
    expect(confirm.titleKey).toBe("consent.confirm.withdrawTitle");
    expect(confirm.noteKey).toBe("consent.detail.withdrawNote");
    expect(tr[confirm.noteKey]).toContain("hemen");
    expect(confirm.actionKey).toBe("consent.detail.withdraw");
    expect(confirm.cancelKey).toBe("consent.confirm.cancel");
  });

  it("a learning row starts off, so its switch opens the text like any other", () => {
    expect(switchIntent(viewFor(freshLedger(), "learning:personal"))).toBe("open_detail");
    expect(withdrawConfirmation(viewOf(freshLedger()), "learning:personal")).toBeNull();
  });

  it("a granted learning row withdraws as the consent it is (legal review round 2)", () => {
    // both learning purposes are açık rıza now, so their confirmation is the
    // consent withdrawal's: no separate opt-out wording exists any more
    for (const [id, label] of [
      ["learning:personal", "consent.learning.personal"],
      ["learning:service_improvement", "consent.learning.service"],
    ] as const) {
      let state = applyTexts(freshLedger(), { [id]: loaded("v1", "d".repeat(64)) });
      state = grant(state, id, "2026-11-17T00:00:00Z").state;
      expect(switchIntent(viewFor(state, id)), id).toBe("confirm_withdraw");
      const confirm = withdrawConfirmation(viewOf(state), id)!;
      expect(confirm.titleKey, id).toBe("consent.confirm.withdrawTitle");
      expect(confirm.noteKey, id).toBe("consent.detail.withdrawNote");
      expect(confirm.actionKey, id).toBe("consent.detail.withdraw");
      expect(confirm.stopKeys, id).toEqual([label]);
    }
  });

  it("asking changes nothing; only the confirmed withdrawal queues the one audited op", () => {
    const state = withVoiceAndAffect();
    const before = state.queue.length;
    withdrawConfirmation(viewOf(state), "voice");
    expect(state.queue.length).toBe(before);
    const after = withdraw(state, "voice", "2026-11-17T00:02:00Z").state;
    expect(after.queue.slice(before)).toEqual([
      { kind: "withdraw", scope: "voice", atIso: "2026-11-17T00:02:00Z" },
    ]);
  });
});

describe("acceptance 4 — the confirmation copy is catalogue chrome, tr first with an en mirror", () => {
  const KEYS = [
    "consent.confirm.withdrawTitle",
    "consent.confirm.stops",
    "consent.confirm.cancel",
  ] as const;

  it("the opt-out wording and the learning basis lines are gone (legal review round 2)", () => {
    for (const key of [
      "consent.basis.learningPersonal",
      "consent.basis.learningService",
      "consent.confirm.optoutTitle",
      "consent.confirm.optoutNote",
      "consent.confirm.optoutAction",
      "a11y.consent.optoutHint",
    ]) {
      expect(Object.keys(tr), key).not.toContain(key);
      expect(Object.keys(en), key).not.toContain(key);
    }
  });

  it("every new key exists in both catalogues", () => {
    for (const key of KEYS) {
      expect(tr[key].trim().length, key).toBeGreaterThan(0);
      expect(en[key].trim().length, key).toBeGreaterThan(0);
    }
  });

  it("the Turkish copy is the siz register, short and factual", () => {
    expect(tr["consent.confirm.withdrawTitle"]).toBe("Bu izni geri çekmek istiyor musunuz?");
    expect(tr["consent.confirm.stops"]).toBe("Şunlar durur:");
    expect(tr["consent.confirm.cancel"]).toBe("Vazgeçin");
    for (const key of KEYS) {
      expect(tr[key], key).not.toMatch(/\b(sen|senin|sana)\b/i);
      expect(tr[key].length, key).toBeLessThanOrEqual(90);
    }
  });

  it("no consent line says a row comes on (legal review round 2)", () => {
    // the group line that said the learning rows come on is gone, and the
    // basis sublabels no longer say "bu yüzden açık gelir"
    expect(Object.keys(tr)).not.toContain("consent.group.learning.hint");
    expect(Object.keys(en)).not.toContain("consent.group.learning.hint");
    for (const key of Object.keys(tr).filter((k) =>
      k.startsWith("consent."),
    ) as (keyof typeof tr)[]) {
      expect(tr[key], key).not.toMatch(/açık gelir/);
      expect(en[key], key).not.toMatch(/why it comes switched on|options come switched on/);
    }
  });

  it("the immediacy lines claim only what is true without a stored queue (item 4)", () => {
    // the consent queue is in memory (store.ts); persisting it is a new
    // on-device data category, a stop-and-ask, so the copy says what holds now
    const key = "consent.detail.withdrawNote";
    expect(tr[key].toLocaleLowerCase("tr"), key).toContain("bu cihazda hemen");
    expect(tr[key], key).toContain("internete bağlıyken");
    expect(en[key], key).toContain("on this device");
    expect(en[key], key).toContain("while you are online");
    expect(tr["consent.detail.withdrawNote"]).toBe(
      "Bu cihazda hemen geçerli olur; internete bağlıyken hemen gönderilir.",
    );
  });

  it("the açık rıza basis line says withdrawal is immediate on this device (round 2, item 5)", () => {
    expect(tr["consent.basis.explicit"]).toBe(
      "Açık rızanıza bağlıdır. İstediğiniz an geri çekebilirsiniz; geri çekmek bu cihazda hemen geçerli olur.",
    );
    expect(tr["consent.basis.explicit"]).toContain("bu cihazda hemen");
    expect(en["consent.basis.explicit"]).toBe(
      "Based on your explicit consent. You can withdraw it at any time; withdrawal takes effect on this device immediately.",
    );
  });

  it("the queue note says sending needs the app open (round 2, item 6)", () => {
    expect(tr["consent.queue.note"]).toBe(
      "Değişiklikleriniz bu cihazda uygulandı; uygulama açıkken bağlantı kurulunca iletilir.",
    );
    expect(en["consent.queue.note"]).toBe(
      "Your changes were applied on this device; they are sent once a connection is available while the app is open.",
    );
  });
});
