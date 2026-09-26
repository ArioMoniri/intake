/**
 * Warmth pass — the patient-facing intake reads as a warm helper, not a
 * clinical interrogation, and it does so WITHOUT crossing PolicyGuard.
 *
 * The owner's ask was a softer, more natural register across the previsit:
 * a helper-tool opener ("Ben Önvizit… sizi kısaca dinlemek istiyorum"), an
 * invitation to speak freely, and the clipped HPI questions given their
 * subject back so none lands as a bare command. Turkish is the source of
 * truth (invariant 5); English mirrors it, and the mirror is warmed too.
 *
 * This file is BOTH controls the change needs:
 *
 *  - a POSITIVE control that pins the warmth actually present, so a future
 *    edit that quietly reverts the register fails here rather than silently;
 *  - a NEAR-MISS NEGATIVE control that re-derives the exact morphology
 *    PolicyGuard forbids (the `sen` address, the prognosis promise, the
 *    "bu bir …" diagnosis frame) and asserts the warmed strings match none
 *    of it. The Python catalogue gate
 *    (tests/voice/test_policyguard_precision.py) is the authority and scans
 *    every string; this is the fast, co-located twin that keeps a warmth
 *    tweak honest at the point it is written.
 *
 * The register/no-diagnosis rules are not re-listed as prose — they are the
 * regexes below, mirrored from the signed Turkish lexicon
 * (services/voice-runtime/.../guard_lexicons/tr.py) so a copy change and its
 * guardrail cannot drift apart in wording.
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr, type MessageKey } from "../i18n/tr";

/** The keys this pass warmed. Each is checked in tr and in the en mirror.
 * `dialogue.openInvite` was warmed too, then retired when INT-318 stopped
 * speaking the open-question aside on every turn (b2301f8e); the catalogue no
 * longer carries it. */
const WARMED_KEYS = [
  "dialogue.entryBody",
  "intake.progress.grows",
  "intake.q.complaint",
  "intake.q.onset",
  "intake.q.severity",
  "intake.q.side",
  "intake.q.extra",
] as const satisfies readonly MessageKey[];

/** Turkish words in a string, lower-cased. Split on anything that is not a
 * Unicode letter, because JavaScript's `\b`/`\w` are ASCII — they read `ı`,
 * `ş`, `ğ` as non-word characters and would cut `mısınız` (siz) right after
 * `mısın` (sen), reporting the polite plural as the singular it is not. The
 * Python guard gets this right precisely because its `\b` is Unicode-aware;
 * this tokeniser is how the mirror stays faithful to it. */
function words(value: string): string[] {
  return value
    .toLocaleLowerCase("tr-TR")
    .split(/[^\p{L}]+/u)
    .filter((w) => w.length > 0);
}

/** Positive evidence of the singular second person (the `sen` register the
 * spec forbids under `siz`), matched on whole tokens. The clitic is the
 * load-bearing near-miss: `mısınız` (siz) is a different token from `mısın`
 * (sen), which is exactly the boundary the warmed chief-complaint sits on. */
const SEN_PRONOUN = new Set(["sen", "sana", "seni", "senin", "sende", "senden", "seninle"]);
const SEN_CLITIC = new Set(["mısın", "misin", "musun", "müsün"]);
/** 2sg finite endings; the `siz`/1pl twins end in `-sınız`/`-siniz`/`-iz`, so
 * a whole-token `endsWith` never confuses the two. */
const SEN_FINITE_SUFFIX = ["yorsun", "acaksın", "eceksin", "malısın", "melisin", "rsın", "rsin"];

function inSenRegister(value: string): boolean {
  return words(value).some(
    (w) =>
      SEN_PRONOUN.has(w) ||
      SEN_CLITIC.has(w) ||
      SEN_FINITE_SUFFIX.some((suffix) => w.endsWith(suffix)),
  );
}

/** Mirrored prognosis and diagnosis frames PolicyGuard rejects. Reassuring a
 * patient about the outcome, or naming their condition, is never how warmth
 * is bought here. */
const PROGNOSIS = /(?:geçer|iyileşirsiniz|düzelir|merak\s+etmeyin|endişelen)/iu;
const DIAGNOSIS_FRAME = /bu\s+bir\s+\p{L}/iu;

describe("the previsit opens like a helper, not an interrogation", () => {
  it("the opener introduces the app by name and offers to listen, with no rush", () => {
    const body = tr["dialogue.entryBody"];
    // Bound to `app.name`, not a literal, so the Önvizit rebrand (and any
    // later one) cannot leave the opener introducing a retired name.
    expect(body).toContain(tr["app.name"]);
    expect(body.toLocaleLowerCase("tr-TR")).toContain("dinle");
    expect(body.toLocaleLowerCase("tr-TR")).toContain("acele");
    // INT-239's second-door promise survives the rewrite (speech.test.ts
    // also pins this — kept here so a warmth edit sees it locally too).
    expect(body.toLocaleLowerCase("tr-TR")).toContain("yazarak");
  });

  it("the en opener mirrors the same welcome", () => {
    expect(en["dialogue.entryBody"]).toContain(en["app.name"]);
    const body = en["dialogue.entryBody"].toLocaleLowerCase("en-US");
    expect(body).toContain("listen");
    expect(body).toContain("no rush");
    expect(body).toContain("typing");
  });

  it("the clipped HPI questions carry their subject now, not a bare command", () => {
    // Each names şikâyet, so "Nasıl başladı?" / "Hangi tarafta?" no longer
    // land as fragments a stranger barks at you.
    for (const key of ["intake.q.onset", "intake.q.severity", "intake.q.side"] as const) {
      expect(tr[key].toLocaleLowerCase("tr-TR"), key).toContain("şikâyet");
    }
  });

  it("the chief complaint invites the patient's own words", () => {
    expect(tr["intake.q.complaint"].toLocaleLowerCase("tr-TR")).toContain("kendi sözlerinizle");
    expect(en["intake.q.complaint"].toLocaleLowerCase("en-US")).toContain("your own words");
  });
});

describe("warmth never buys itself with a forbidden form (near-miss control)", () => {
  it("no warmed tr string slips into the sen register", () => {
    for (const key of WARMED_KEYS) {
      expect(inSenRegister(tr[key]), `${key}: sen register`).toBe(false);
    }
  });

  it("the chief-complaint question keeps the siz clitic, not the sen twin", () => {
    // The whole defect in one string: `anlatır mısınız?` (siz) must pass the
    // clitic rule where `anlatır mısın?` (sen) would trip it.
    expect(inSenRegister(tr["intake.q.complaint"])).toBe(false);
    expect(inSenRegister("Bugün sizi buraya getiren şeyi anlatır mısın?")).toBe(true);
  });

  it("no warmed string reassures about the outcome or names a condition", () => {
    for (const key of WARMED_KEYS) {
      expect(PROGNOSIS.test(tr[key]), `${key}: prognosis`).toBe(false);
      expect(DIAGNOSIS_FRAME.test(tr[key]), `${key}: diagnosis frame`).toBe(false);
    }
  });

  it("no warmed string reaches the TTS carrying a digit (invariant 22)", () => {
    for (const key of WARMED_KEYS) {
      expect(tr[key], key).not.toMatch(/\p{Nd}/u);
      expect(en[key], key).not.toMatch(/\p{Nd}/u);
    }
  });
});
