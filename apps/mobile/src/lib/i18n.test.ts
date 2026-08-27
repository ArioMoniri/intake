import { afterEach, describe, expect, it } from "vitest";

import { availableLocales, getLocale, setLocale, t } from "./i18n";
import { en } from "./i18n/en";
import { tr, type MessageKey } from "./i18n/tr";

afterEach(() => setLocale("tr"));

describe("catalogs", () => {
  it("en mirrors tr key-for-key (tr is the source of truth)", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(tr).sort());
  });

  it("no catalog value is empty", () => {
    for (const key of Object.keys(tr) as MessageKey[]) {
      expect(tr[key].trim().length, key).toBeGreaterThan(0);
      expect(en[key].trim().length, key).toBeGreaterThan(0);
    }
  });

  it("no ALL-CAPS strings — Turkish İ/ı casing rule (00 §2)", () => {
    for (const key of Object.keys(tr) as MessageKey[]) {
      const value = tr[key];
      const letters = value.replace(/[^a-zçğıöşüA-ZÇĞİÖŞÜ]/gu, "");
      if (letters.length >= 4) {
        expect(value, key).not.toBe(value.toLocaleUpperCase("tr-TR"));
      }
    }
  });

  it("tr register: patient-facing prose uses siz forms, never sen", () => {
    for (const key of Object.keys(tr) as MessageKey[]) {
      // Word-boundary check for the bare pronoun and rude imperatives.
      expect(tr[key], key).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
    }
  });
});

describe("t()", () => {
  it("defaults to Turkish", () => {
    expect(getLocale()).toBe("tr");
    expect(t("tabs.today")).toBe("Bugün");
  });

  it("switches locale globally and per call", () => {
    setLocale("en");
    expect(t("tabs.today")).toBe("Today");
    expect(t("tabs.today", "tr")).toBe("Bugün");
  });

  it("exposes exactly tr and en", () => {
    expect(availableLocales).toEqual(["tr", "en"]);
  });
});
