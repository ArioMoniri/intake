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
    // The Turkish case suffixes of a name ending in a voiceless -t: -'te, -'i.
    expect(tr["consent.firstRun.body"].startsWith(`${BRAND}'te `)).toBe(true);
    expect(tr["consent.basis.service"]).toContain(`${BRAND}'i kullanmayı`);
  });

  it("names Önvizit in the HealthKit purpose string App Review reads", () => {
    const why = healthKitPlugin().NSHealthShareUsageDescription;
    expect(typeof why === "string" && why.startsWith(`${BRAND};`)).toBe(true);
    // Unchanged by the rename: the app never writes to HealthKit.
    expect(healthKitPlugin().NSHealthUpdateUsageDescription).toBe(false);
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
