/**
 * INT-420 — the app ships as Önvizit (GitHub #712).
 *
 * The owner renamed the product and carried the rename on int-demo
 * (0115c60b, 82c1a1e6): the app name, a localized CFBundleDisplayName, the
 * V-logo icon with the stale `ios.icon` template override dropped, the
 * registered bundle id, and the purpose strings. This spec pins that identity
 * on main as config facts, so a later edit cannot quietly undo it.
 *
 * Two identifiers deliberately do NOT change, and are pinned so they stay:
 * - the bundle id `com.ariomoniri.intakemobile` is the App Store Connect
 *   record's identity (and services/api's App Attest `IOS_BUNDLE_ID`); a new
 *   bundle id would be a new app, not a rename;
 * - the URL scheme gains `onvizit` as its primary and keeps `intake`, so a link
 *   already issued with the old scheme still opens the app.
 *
 * The repo-wide guard against the old name, and the checks that the scheme
 * and redirect URIs still match each other, are in tests/release (check-py and
 * check-i18n).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { ExpoConfig } from "expo/config";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";

const MOBILE = join(__dirname, "..");
const BRAND = "Önvizit";
const ASCII = "onvizit";
const BUNDLE_ID = "com.ariomoniri.intakemobile";

const read = (...segments: string[]) => readFileSync(join(MOBILE, ...segments), "utf8");

function appJson(): ExpoConfig {
  return (JSON.parse(read("app.json")) as { expo: ExpoConfig }).expo;
}

function plist(locale: "tr" | "en"): Record<string, string> {
  return JSON.parse(read("src", "locales", `app-${locale}.json`)) as Record<string, string>;
}

/** Width and height from a PNG's IHDR chunk (bytes 16..24). */
function pngSize(path: string): { width: number; height: number } {
  const bytes = readFileSync(join(MOBILE, path));
  expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

function healthKitPlugin(): Record<string, unknown> {
  const entry = (appJson().plugins ?? []).find(
    (p) => Array.isArray(p) && p[0] === "@kingstinct/react-native-healthkit",
  ) as [string, Record<string, unknown>] | undefined;
  expect(entry, "the HealthKit plugin is registered").toBeDefined();
  return (entry as [string, Record<string, unknown>])[1];
}

describe("the name a patient sees is Önvizit", () => {
  it("names the app Önvizit in app.json", () => {
    expect(appJson().name).toBe(BRAND);
  });

  it("localizes the home-screen name in both catalogues (CFBundleDisplayName)", () => {
    expect(plist("tr").CFBundleDisplayName).toBe(BRAND);
    expect(plist("en").CFBundleDisplayName).toBe(BRAND);
  });

  it("uses one name across the config and the in-app catalogues", () => {
    expect(tr["app.name"]).toBe(appJson().name);
    expect(en["app.name"]).toBe(appJson().name);
  });

  it("gives the voice agent the product's name, in both languages", () => {
    expect(tr["a11y.speaker.agent"]).toBe(BRAND);
    expect(en["a11y.speaker.agent"]).toBe(BRAND);
    expect(tr["a11y.dialogue.speaking"]).toBe(`${BRAND} konuşuyor`);
    expect(en["a11y.dialogue.speaking"]).toBe(`${BRAND} is speaking`);
  });

  it("names Önvizit in every catalogue line that names the product", () => {
    for (const key of ["app.disclaimer", "welcome.body", "me.learnedEmpty"] as const) {
      expect(tr[key].startsWith(BRAND), `tr ${key}`).toBe(true);
      expect(en[key].startsWith(BRAND), `en ${key}`).toBe(true);
    }
    // The Turkish case suffix of a name ending in a voiceless -t: -'te. The
    // accusative -'i lived only in consent.basis.service, which INT-537
    // deleted: core is a consent with a switch, so that copy has no reader.
    expect(tr["consent.firstRun.body"].startsWith(`${BRAND}'te `)).toBe(true);
    expect(Object.keys(tr)).not.toContain("consent.basis.service");
  });

  it("names Önvizit in the HealthKit purpose string App Review reads", () => {
    const why = healthKitPlugin().NSHealthShareUsageDescription;
    expect(typeof why === "string" && why.startsWith(`${BRAND};`)).toBe(true);
  });
});

/*
 * INT-592 (#1000). Apple rejected build 6 with ITMS-90683: the HealthKit
 * library links write APIs, so the bundle must carry
 * NSHealthUpdateUsageDescription even though the app requests no write type.
 * INT-420 had set it to `false`, which writes no key at all. The key now holds
 * a string, and that string has to be true: the app writes nothing to Apple
 * Health. The oracle below accepts a string only if it carries the denial and,
 * once the negated verbs are taken out, no write verb is left.
 */
type Lang = "tr" | "en";

/** The denial each language must state. */
const WRITE_DENIAL: Record<Lang, RegExp> = {
  tr: /(?<!\p{L})yazmaz(?!\p{L})/u,
  en: /\b(never writes|does not write)\b/iu,
};

/**
 * A write verb that is not negated. Turkish negates in the verb (-maz/-mez),
 * so a stem followed by the negative suffix is a denial, not a claim. English
 * negates with a preceding word, which is stripped first.
 */
const WRITE_CLAIM: Record<Lang, RegExp> = {
  tr: /(?<!\p{L})(yaz|kaydet|kayded|güncelle|ekle|değiştir|sil)(?!m[ae]z)/iu,
  en: /\b(writ(e|es|ing|ten)|sav(e|es|ed|ing)|updat(e|es|ed|ing)|add(s|ed|ing)?|chang(e|es|ed|ing)|modif(y|ies|ied|ying)|delet(e|es|ed|ing))\b/iu,
};
const EN_NEGATED_VERB = /\b(never|does not|do not|doesn't|will not|won't)\s+\w+/giu;

function deniesWriting(text: unknown, lang: Lang): boolean {
  if (typeof text !== "string" || text.trim() === "") {
    return false;
  }
  const rest = lang === "en" ? text.replace(EN_NEGATED_VERB, " ") : text;
  return WRITE_DENIAL[lang].test(text) && !WRITE_CLAIM[lang].test(rest);
}

describe("INT-592: the HealthKit write purpose string is present and true", () => {
  it("accepts only a string that denies writing (near misses)", () => {
    // The shape INT-420 shipped: `false` writes no key, and Apple rejects it.
    expect(deniesWriting(false, "tr")).toBe(false);
    expect(deniesWriting("", "tr")).toBe(false);
    expect(deniesWriting("   ", "en")).toBe(false);
    // The library's own default, which the plugin writes when given no string.
    expect(deniesWriting(`${BRAND} wants to update your health data`, "en")).toBe(false);
    expect(deniesWriting(`${BRAND}; adım verilerinizi Sağlık uygulamasına yazar.`, "tr")).toBe(
      false,
    );
    // Says nothing about writing at all.
    expect(deniesWriting(`${BRAND}; sağlık verilerinizi okur.`, "tr")).toBe(false);
    // Denies one write and claims another.
    expect(
      deniesWriting(
        `${BRAND}; Sağlık uygulamasına hiçbir veri yazmaz ama uyku verilerinizi kaydeder.`,
        "tr",
      ),
    ).toBe(false);
    expect(deniesWriting(`${BRAND} never writes to Health but saves your sleep data.`, "en")).toBe(
      false,
    );
    // A word that only contains a stem ("bekle" holds "ekle") is not a claim.
    expect(deniesWriting(`${BRAND}; hiçbir veri yazmaz, sizi bekletmez.`, "tr")).toBe(true);
  });

  it("declares a non-empty write string in the base Info.plist (ITMS-90683)", () => {
    const why = healthKitPlugin().NSHealthUpdateUsageDescription;
    expect(typeof why).toBe("string");
    expect((why as string).startsWith(`${BRAND};`)).toBe(true);
    expect(deniesWriting(why, "tr")).toBe(true);
  });

  it("keeps tr the source: the plugin strings are the Turkish catalogue's", () => {
    for (const key of ["NSHealthShareUsageDescription", "NSHealthUpdateUsageDescription"]) {
      expect(healthKitPlugin()[key], key).toBe(plist("tr")[key]);
    }
  });

  it("localises both health strings, and the English one denies writing too", () => {
    for (const key of ["NSHealthShareUsageDescription", "NSHealthUpdateUsageDescription"]) {
      expect(plist("en")[key]?.startsWith(BRAND), key).toBe(true);
      expect(plist("en")[key], key).not.toBe(plist("tr")[key]);
    }
    expect(deniesWriting(plist("tr").NSHealthUpdateUsageDescription, "tr")).toBe(true);
    expect(deniesWriting(plist("en").NSHealthUpdateUsageDescription, "en")).toBe(true);
  });

  it("names in both share strings exactly the three kinds the connector reads", () => {
    const connector = read("src", "lib", "health", "healthKitConnector.ts");
    const start = connector.indexOf("toRead:");
    expect(start).toBeGreaterThan(-1);
    const toRead = connector.slice(start, connector.indexOf("]", start));
    expect(toRead.match(/"HK[A-Za-z]+"/g)).toEqual([
      '"HKQuantityTypeIdentifierStepCount"',
      '"HKQuantityTypeIdentifierRestingHeartRate"',
      '"HKCategoryTypeIdentifierSleepAnalysis"',
    ]);
    const share = {
      tr: plist("tr").NSHealthShareUsageDescription,
      en: plist("en").NSHealthShareUsageDescription,
    };
    for (const word of [/adım/u, /nabız/u, /uyku/u]) {
      expect(share.tr).toMatch(word);
    }
    for (const word of [/\bstep/iu, /\bheart rate\b/iu, /\bsleep\b/iu]) {
      expect(share.en).toMatch(word);
    }
  });

  it("stays true in code: the connector asks to read and never to write", () => {
    const connector = read("src", "lib", "health", "healthKitConnector.ts");
    expect(connector).toContain("toRead:");
    expect(connector).not.toMatch(/toShare|\.save[A-Z]|\.delete[A-Z]/u);
  });
});

describe("the icon is the owner's V-logo, not the Expo template", () => {
  it("drops the ios.icon override, so iOS builds from icon.png", () => {
    expect(appJson().ios?.icon).toBeUndefined();
    expect(appJson().icon).toBe("./assets/images/icon.png");
  });

  it("ships a 1024 × 1024 PNG as the store icon", () => {
    expect(pngSize("assets/images/icon.png")).toEqual({ width: 1024, height: 1024 });
  });

  it("keeps the vector source beside it, labelled with the product's name", () => {
    const svg = read("assets", "images", `${ASCII}-logo.svg`);
    expect(svg).toContain(`aria-label="${BRAND}"`);
    expect(svg).toContain('viewBox="0 0 1024 1024"');
  });
});

describe("identifiers: what changes and what must not", () => {
  it("declares the registered bundle id, the one App Attest verifies", () => {
    expect(appJson().ios?.bundleIdentifier).toBe(BUNDLE_ID);
  });

  it("opens onvizit:// links first and still opens links already issued as intake://", () => {
    expect(appJson().scheme).toEqual([ASCII, "intake"]);
  });

  it("keeps the Expo project slug, which the EAS project id is bound to", () => {
    expect(appJson().slug).toBe("intake-mobile");
  });
});
