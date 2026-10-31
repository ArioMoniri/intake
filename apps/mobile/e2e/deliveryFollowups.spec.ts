/**
 * INT-589 — the delivery follow-ups from the INT-587 legal review (GitHub #990).
 *
 * (1) A note delivered before a share-consent withdrawal can be shared again
 *     on a fresh grant for it, and `shares.issue.error.notShared` is true.
 * (2) Sign-out warns while a note is still on the phone, and lets the patient
 *     open it to send it or keep it by staying signed in.
 * (3) The review summary's "until when" matches the server's share lifetime
 *     (services/api share_lifetime.py; the server half is
 *     tests/api/test_share_lifetime.py).
 * (4) The review summary's "who" names who can open the note: whoever the
 *     patient shows the link and code to. It never names a hospital, which
 *     receives nothing.
 * (5) A withdrawal the server refuses is shown as not done.
 *
 * N1 and N2 of the review are for counsel and change nothing here.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";

const MOBILE = join(__dirname, "..");
const read = (...segments: string[]) => readFileSync(join(MOBILE, ...segments), "utf8");
const REVIEW = () => read("src", "app", "(tabs)", "visits", "[visitId]", "review.tsx");
const DELIVERY = () => read("src", "components", "NoteDelivery.tsx");
const ME = () => read("src", "app", "(tabs)", "me", "index.tsx");
const CONSENT_CONTROL = () => read("src", "components", "ShareConsentControl.tsx");
const SHARE_LIB = () => read("src", "lib", "intake", "share.ts");

describe("(1) re-share after a withdrawal, and a true notShared line", () => {
  it("the issue screen's notShared line says what is true in every case", () => {
    expect(tr["shares.issue.error.notShared"]).toBe(
      "Bu not şu anda paylaşılmıyor, bu yüzden bağlantı oluşturulamadı.",
    );
    expect(en["shares.issue.error.notShared"]).toBe(
      "This note is not being shared right now, so the link could not be created.",
    );
    // near miss: a delivered note cannot be "sent first" — the old line was false
    for (const value of [tr["shares.issue.error.notShared"], en["shares.issue.error.notShared"]]) {
      expect(value).not.toMatch(/Önce notu gönderin|henüz paylaşılmadı|Send the note first/i);
    }
  });

  it("the review screen hands every frozen note to NoteDelivery, delivered ones included", () => {
    const review = REVIEW();
    expect(review).toMatch(/\{frozen && visitId \? \(\s*<NoteDelivery/);
    // near miss: gating it on an unconfirmed delivery hid the re-share step
    expect(review).not.toMatch(/frozen && !delivered && visitId \? \(\s*<NoteDelivery/);
  });

  it("NoteDelivery offers the re-share only when the note needs one, on a grant for it", () => {
    const card = DELIVERY();
    expect(card).toContain("needsReshare(item, ledger.share.withdrawnAt)");
    expect(card).toContain("reshareDelivery(visitId, payload.body, receipt)");
    expect(card).toContain('t("delivery.reshare.body")');
    // the legal text is the served one, rendered the same way as for the first send
    expect(card.split("<ShareText text={share.text.text} />").length - 1).toBe(2);
    // near miss: the first send's body line says the note stays on the phone,
    // which is false for a delivered note, so the re-share card never shows it
    const reshareCard = card.slice(
      card.indexOf("if (reshareNeeded) {"),
      card.indexOf("const reopen"),
    );
    expect(reshareCard).not.toContain('t("delivery.consent.body")');
    expect(reshareCard).not.toContain('t("delivery.consent.pendingBody")');
    expect(reshareCard).not.toContain('t("delivery.edit")');
  });

  it("the re-share copy is tr first, siz, with an en mirror", () => {
    expect(tr["delivery.reshare.title"]).toBe("Yeniden paylaşım");
    expect(tr["delivery.reshare.body"]).toBe(
      "Paylaşım onayınızı geri çektiğiniz için bu notun bağlantıları kapandı. Yeniden paylaşmak isterseniz, bu not için onayınızı yeniden verebilirsiniz.",
    );
    expect(tr["delivery.reshare.declined"]).toBe("Bu not şu anda kimseyle paylaşılmıyor.");
    expect(tr["delivery.reshare.pending"]).toBe(
      "Paylaşım metni hazır olduğunda bu notu yeniden paylaşabilirsiniz.",
    );
    for (const key of [
      "delivery.reshare.title",
      "delivery.reshare.body",
      "delivery.reshare.declined",
      "delivery.reshare.pending",
    ] as const) {
      expect(en[key].trim().length, key).toBeGreaterThan(0);
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
    }
  });
});

describe("(2) sign-out warns while a note is still on the phone", () => {
  it("the sign-out reads the outbox and warns before it shreds anything", () => {
    const me = ME();
    expect(me).toContain("unsentItems(deliveries)");
    expect(me).toContain('t("me.signOut.unsent")');
    expect(me).toMatch(/unsent\.length > 0 \? setConfirmingSignOut\(true\) : signOut\(\)/);
    // near miss: the "Çıkış yapın" button no longer signs out straight away;
    // only the warning's "Yine de çıkış yapın" does
    expect(me).not.toMatch(/label=\{t\("me\.signOut"\)\}\s*onPress=\{signOut\}/);
    expect(me).toMatch(/label=\{t\("me\.signOut\.anyway"\)\}\s*onPress=\{signOut\}/);
  });

  it("the warning lets the patient open the note, stay, or sign out anyway", () => {
    const me = ME();
    for (const key of ["me.signOut.openNote", "me.signOut.stay", "me.signOut.anyway"]) {
      expect(me, key).toContain(`t("${key}")`);
    }
    expect(me).toMatch(/visits\/\$\{unsent\[0\]\.visitId\}\/review/);
  });

  it("says what a sign-out does to the note, and nothing it does not", () => {
    expect(tr["me.signOut.unsent"]).toBe(
      "Henüz gönderilmemiş notunuz var. Çıkış yaparsanız not bu telefondan silinir ve hekiminize gitmez.",
    );
    expect(tr["me.signOut.openNote"]).toBe("Notu açın");
    expect(tr["me.signOut.stay"]).toBe("Oturumda kalın");
    expect(tr["me.signOut.anyway"]).toBe("Yine de çıkış yapın");
    expect(en["me.signOut.unsent"]).toMatch(/not been sent/);
  });
});

describe("(3) 'until when' says what the server does", () => {
  it("states the visit window, and the send window for a late send", () => {
    expect(tr["review.consent.untilValue"]).toBe(
      "Paylaşım en geç randevunuzdan üç gün sonra kendiliğinden kapanır. Notu randevudan sonra gönderirseniz, gönderdiğiniz andan üç gün sonra kapanır.",
    );
    expect(tr["review.consent.untilValueNoDate"]).toBe(
      "Bu vizitin tarihi olmadığı için paylaşım, notu gönderdiğiniz andan üç gün sonra kendiliğinden kapanır.",
    );
    for (const key of ["review.consent.untilValue", "review.consent.untilValueNoDate"] as const) {
      // a rule, never a computed instant (02 §2): no numeral in either language
      expect(tr[key], key).not.toMatch(/\d/);
      expect(en[key], key).not.toMatch(/\d/);
    }
  });

  it("the review screen picks the line by whether the visit has a date", () => {
    expect(REVIEW()).toContain(
      'visit?.date ? "review.consent.untilValue" : "review.consent.untilValueNoDate"',
    );
  });
});

describe("(4) 'who' names who can open the note, never a hospital", () => {
  it("the summary names the link holder as an anchor, with no hospital in it", () => {
    const lib = SHARE_LIB();
    expect(lib).toContain('export const SHARE_OPENER = "link_holder" as const;');
    expect(lib).not.toMatch(/hospital/);
  });

  it("the review screen renders that line and no hospital or department under it", () => {
    const review = REVIEW();
    expect(review).toContain('t("review.consent.recipient")');
    expect(review).toContain('t("review.consent.recipientValue")');
    // near miss: the old row printed the visit's hospital, which receives nothing
    expect(review).not.toContain("summary.recipient");
  });

  it("the line matches share.tr.md's 'Kimler görür'", () => {
    expect(tr["review.consent.recipient"]).toBe("Kim açabilir");
    expect(tr["review.consent.recipientValue"]).toBe(
      "Oluşturacağınız bağlantıyı ve açma kodunu gösterdiğiniz kişi.",
    );
    const text = read("..", "..", "docs", "legal", "synthetic", "consents", "share.tr.md");
    expect(text).toMatch(/Bağlantıyı ve kodu kimde varsa, notunuzu o kişi açabilir/);
    expect(tr["review.consent.recipientValue"]).not.toMatch(/hastane|hospital/i);
  });
});

describe("(5) a refused withdrawal is shown as not done", () => {
  it("the control has a refused outcome with its own line", () => {
    const control = CONSENT_CONTROL();
    expect(control).toContain('type Outcome = "none" | "landed" | "unsent" | "refused";');
    expect(control).toContain('t("shares.consent.refused")');
    // only a landed withdrawal says done
    expect(control).toMatch(/if \(result === "landed"\) \{\s*onWithdrawn\(\);/);
  });

  it("the refused line says it was not done, and does not claim the links closed", () => {
    expect(tr["shares.consent.refused"]).toBe(
      "Geri çekme isteğiniz kabul edilmedi. Bağlantılar açık kalmış olabilir.",
    );
    expect(en["shares.consent.refused"]).toBe(
      "Your withdrawal was not accepted. Links may still be open.",
    );
    // near miss: the done line is exactly what a refusal must never show
    expect(tr["shares.consent.refused"]).not.toContain(tr["shares.consent.done"]);
  });
});
