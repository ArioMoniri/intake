/**
 * INT-588 — a release-mode render carries no voice clause and no delivery
 * claim it cannot back.
 *
 * Voice ships only in a dev build: intake.tsx gates the voice lane and the
 * dictation button on `__DEV__`, and INT-421 strips the voice lanes from the
 * production profile. So in a release build every voice clause in patient copy
 * is false. These tests resolve every build-aware choice in release mode and
 * read the Turkish source and the English mirror for a voice clause; the near
 * misses prove the pattern bites (the dev variants DO carry the clause) and
 * that the typed invitation survives.
 *
 * The delivery half: since INT-587 a note is "sent" only once the server has
 * confirmed it. Every catalogue line that says so is listed here, and each is
 * pinned to a surface that renders only after a confirmed delivery
 * (e2e/noteDelivery.spec.ts holds the gates).
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { PURPOSES, purposeParam, type PurposeId } from "./consent/purposes";

import {
  BUILD_MODES,
  companionEffectKeys,
  currentBuildMode,
  openAnswerHintKey,
  startModeOffered,
  voiceShips,
  type BuildMode,
} from "./buildCopy";
import { en } from "./i18n/en";
import { tr, type MessageKey } from "./i18n/tr";
import type { AttributionOutcome } from "./profile/attribution";

/** A voice clause, in either catalogue: the act of speaking, or doing it aloud. */
const VOICE_CLAUSE = /söyleyebilir|sesli|konuşarak|sesle|by voice|say it|aloud|speak|dictat/i;

/** A claim that the note has left the phone or reached the doctor. */
const DELIVERY_CLAIM = /gönderildi|iletildi|ulaştı|was sent|has been sent|delivered|reached your/i;

function both(key: MessageKey): string[] {
  return [tr[key], en[key]];
}

const OUTCOMES: AttributionOutcome[] = [
  {
    attribution: "self_report",
    proxyReported: false,
    thirdPartyPresent: false,
    sensitiveTextOnly: false,
    safeguardingAsked: true,
    ready: true,
  },
  {
    attribution: "self_report",
    proxyReported: false,
    thirdPartyPresent: true,
    sensitiveTextOnly: true,
    safeguardingAsked: false,
    ready: true,
  },
  {
    attribution: "assisted_self_report",
    proxyReported: false,
    thirdPartyPresent: true,
    sensitiveTextOnly: true,
    safeguardingAsked: false,
    ready: true,
  },
  {
    attribution: "proxy_report",
    proxyReported: true,
    thirdPartyPresent: true,
    sensitiveTextOnly: true,
    safeguardingAsked: false,
    ready: true,
  },
];

/** Every key a release build resolves through a build-aware choice. */
function releaseKeys(): MessageKey[] {
  const mode: BuildMode = "release";
  return [
    openAnswerHintKey(mode, true),
    openAnswerHintKey(mode, false),
    ...OUTCOMES.flatMap((outcome) => companionEffectKeys(outcome, mode)),
  ];
}

describe("the build", () => {
  it("is release wherever __DEV__ is not set — the node lane included", () => {
    expect(currentBuildMode()).toBe("release");
    expect([...BUILD_MODES]).toEqual(["dev", "release"]);
  });

  it("ships voice in a dev build only", () => {
    expect(voiceShips("dev")).toBe(true);
    expect(voiceShips("release")).toBe(false);
  });
});

describe("a release-mode render carries no voice clause", () => {
  it("in any build-aware line, in Turkish or English", () => {
    for (const key of releaseKeys()) {
      for (const text of both(key)) {
        expect(text, key).not.toMatch(VOICE_CLAUSE);
      }
    }
  });

  it("even when the patient granted the voice consent", () => {
    expect(openAnswerHintKey("release", true)).toBe(openAnswerHintKey("release", false));
  });

  it("offers no voice start mode: the chooser is not shown", () => {
    expect(startModeOffered("release")).toBe(false);
  });

  it("lists no effect that is only a change where voice exists", () => {
    for (const outcome of OUTCOMES) {
      expect(companionEffectKeys(outcome, "release")).not.toContain("companion.effect.textOnly");
    }
  });

  it("in the lines made true for every build — no build switch needed", () => {
    for (const key of [
      "welcome.body",
      "auth.integrity.warnBody",
      "companion.thirdParty.footer",
    ] as const) {
      for (const text of both(key)) {
        expect(text, key).not.toMatch(VOICE_CLAUSE);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/* KVKK-10: the consent chrome says what the served text says           */
/* ------------------------------------------------------------------ */

const LEGAL = join(__dirname, "..", "..", "..", "..", "docs", "legal", "synthetic", "consents");

describe("the consent rows agree with the docs/legal texts the server serves", () => {
  const voiceText = readFileSync(join(LEGAL, "voice.tr.md"), "utf8");
  const affectText = readFileSync(join(LEGAL, "lane.affect.tr.md"), "utf8");

  it("the voice row makes no residency claim of its own", () => {
    // The served text processes the voice outside Türkiye on the synthetic
    // host; the row said the data stays in Türkiye. Where is the text's to say.
    expect(voiceText).toMatch(/Türkiye dışında işlenir/);
    for (const text of both("consent.who.voice")) {
      expect(text).not.toMatch(/Türkiye|Turkey|Türkiye'deki|in Türkiye/i);
    }
    expect(tr["consent.who.voice"]).toMatch(/izin metninde/);
  });

  it("the voice row repeats only what the text promises: no recording is kept", () => {
    expect(voiceText).toMatch(/Sesiniz hiçbir yere kaydedilmez/);
    expect(tr["consent.who.voice"]).toMatch(/hiçbir yere kaydedilmez/);
  });

  it("the affect row never says the doctor sees the cues — the text says the opposite", () => {
    expect(affectText).toMatch(/hekiminize bir değerlendirme olarak gönderilmez/);
    expect(affectText).toMatch(/Notunuza da yazılmaz/);
    expect(tr["consent.who.laneAffect"]).not.toMatch(/hekiminiz görür/i);
    expect(en["consent.who.laneAffect"]).not.toMatch(/doctor sees/i);
    expect(tr["consent.who.laneAffect"]).toMatch(/gönderilmez/);
  });

  it("the voice group hint speaks of no recording, because none is kept", () => {
    for (const text of both("consent.group.voice.hint")) {
      expect(text).not.toMatch(/kayd|recording/i);
    }
  });

  it("the affect row says no more than the text: not sent 'as an assessment'", () => {
    expect(tr["consent.who.laneAffect"]).toMatch(/bir değerlendirme olarak gönderilmez/);
    expect(en["consent.who.laneAffect"]).toMatch(/as an assessment/);
  });
});

/**
 * Who sees what, on İzinleriniz. A row may name a recipient — the doctor, the
 * clinic, its staff — only when the server serves a text for that purpose that
 * says so; with no text behind it the row is the only statement there is, and
 * a recipient named there is a claim nothing backs (KVKK m.10; INT-588 legal
 * re-check: lane:linguistic, whose text is awaiting-human under HB-C17).
 */
const RECIPIENT = /hekim|doktor|klinik|personel|doctor|clinic|staff/i;

function servedTextExists(purposeId: string): boolean {
  return existsSync(join(LEGAL, `${purposeParam(purposeId as PurposeId)}.tr.md`));
}

describe("a 'who' row names a recipient only where a served text stands behind it", () => {
  const withoutText = PURPOSES.filter((p) => !servedTextExists(p.id));
  const withText = PURPOSES.filter((p) => servedTextExists(p.id));

  it("reads the legal tree it is checking — both groups are non-empty", () => {
    expect(withoutText.map((p) => p.id)).toContain("lane:linguistic");
    expect(withText.map((p) => p.id)).toContain("core");
  });

  it("a purpose with no served text names no recipient, in tr or en", () => {
    for (const purpose of withoutText) {
      for (const text of both(purpose.whoKey)) {
        expect(text, purpose.id).not.toMatch(RECIPIENT);
      }
    }
  });

  it("the linguistic row defers to its text instead", () => {
    expect(tr["consent.who.laneLinguistic"]).toBe(
      "Yazıdan çıkan ipuçlarının kimlere gideceği, izin metni hazır olunca orada yazacak.",
    );
    expect(en["consent.who.laneLinguistic"]).toBe(
      "Who receives cues drawn from the text will be stated in the consent text once it is ready.",
    );
  });

  it("near miss: where a text IS served, the row may name the doctor — and core's does", () => {
    const core = PURPOSES.find((p) => p.id === "core");
    expect(core && servedTextExists(core.id)).toBe(true);
    expect(tr[core!.whoKey]).toMatch(RECIPIENT);
  });
});

describe("near misses — the pattern bites, and the dev build keeps its truth", () => {
  it("a dev build with the voice consent offers dictation, and says so", () => {
    const key = openAnswerHintKey("dev", true);
    expect(key).toBe("intake.open.hintVoice");
    for (const text of both(key)) {
      expect(text).toMatch(VOICE_CLAUSE);
    }
  });

  it("a dev build WITHOUT the voice consent shows no dictation button and no clause", () => {
    const key = openAnswerHintKey("dev", false);
    for (const text of both(key)) {
      expect(text).not.toMatch(VOICE_CLAUSE);
    }
  });

  it("the typed invitation is still an invitation to write", () => {
    expect(tr[openAnswerHintKey("release", false)]).toMatch(/yazabilirsiniz/);
    expect(en[openAnswerHintKey("release", false)]).toMatch(/write/i);
  });

  it("the dev build keeps the start-mode chooser and the text-only effect", () => {
    expect(startModeOffered("dev")).toBe(true);
    expect(companionEffectKeys(OUTCOMES[1], "dev")).toContain("companion.effect.textOnly");
    for (const text of both("companion.effect.textOnly")) {
      expect(text).toMatch(VOICE_CLAUSE);
    }
  });

  it("effects that hold in every build are listed in release too", () => {
    expect(companionEffectKeys(OUTCOMES[3], "release")).toEqual([
      "companion.effect.proxy",
      "companion.effect.noSafeguarding",
    ]);
    expect(companionEffectKeys(OUTCOMES[2], "release")).toEqual([
      "companion.effect.assisted",
      "companion.effect.noSafeguarding",
    ]);
    expect(companionEffectKeys(OUTCOMES[0], "release")).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* Delivery claims                                                      */
/* ------------------------------------------------------------------ */

const MOBILE = join(__dirname, "..", "..");
const SRC = join(MOBILE, "src");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const SHIPPED = walk(SRC)
  .filter((p) => /\.tsx?$/.test(p) && !p.includes(".test.") && !p.includes(`${sep}i18n${sep}`))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }));

/**
 * The lines that say the note left the phone, and the one place each may be
 * rendered: behind a confirmed delivery. `status.sent` is a ladder rung and a
 * card label — a state name the ladder marks reached or pending — rendered
 * from `effectiveStatus`, which needs the delivery (INT-587), or from the
 * visit's own server-side status.
 */
const CLAIM_SURFACES: Record<string, readonly string[]> = {
  "review.sentInfo": [
    "src/app/(tabs)/visits/[visitId]/review.tsx",
    "src/app/(tabs)/visits/[visitId]/index.tsx",
  ],
  "csat.optional": ["src/components/CsatPrompt.tsx"],
  "status.sent": ["src/components/StatusLadder.tsx", "src/components/StatusChip.tsx"],
};

describe("a delivery claim renders only behind a confirmed delivery", () => {
  it("the catalogue's claims are exactly the recorded ones", () => {
    const claims = (Object.keys(tr) as MessageKey[]).filter(
      (key) => DELIVERY_CLAIM.test(tr[key]) || DELIVERY_CLAIM.test(en[key]),
    );
    // delivery.held says the note has NOT reached the doctor: a negation
    const affirmative = claims.filter((key) => !/hasn't|has not|ulaşmadı/.test(en[key] + tr[key]));
    expect(affirmative.sort()).toEqual(Object.keys(CLAIM_SURFACES).sort());
  });

  it("each claim is referenced only from its delivery-gated surfaces", () => {
    for (const [key, allowed] of Object.entries(CLAIM_SURFACES)) {
      const users = SHIPPED.filter((f) => f.source.includes(`"${key}"`)).map((f) => f.name);
      expect(users.sort(), key).toEqual([...allowed].sort());
    }
  });

  it("near miss: the copy for a note still on the phone claims nothing", () => {
    for (const key of [
      "delivery.queued",
      "delivery.held",
      "delivery.consent.body",
      "delivery.consent.pendingBody",
      "delivery.refused.rejected",
    ] as const) {
      expect(tr[key], key).not.toMatch(/gönderildi|iletildi/i);
    }
    // and the pattern does bite on the line that is only shown after delivery
    expect(tr["review.sentInfo"]).toMatch(DELIVERY_CLAIM);
  });

  it("review.sentInfo promises only what a release build shows: when the note was opened", () => {
    // The status ladder's "Hekim görüntüledi" rung has no data source for a
    // real account; the share centre's access log does. The line points there.
    for (const text of both("review.sentInfo")) {
      expect(text).not.toMatch(/durumu burada|status here/i);
    }
    expect(tr["review.sentInfo"]).toMatch(/Paylaşımlarınız/);
    expect(en["review.sentInfo"]).toMatch(/Your shares/);
  });
});
