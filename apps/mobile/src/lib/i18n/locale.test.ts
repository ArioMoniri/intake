/**
 * INT-296 — the session locale, mobile half.
 *
 * `index.ts` (INT-130) is the dev shell's catalogue lookup and stays what it
 * is. What lands here is the layer above it: which locales this build may
 * OFFER, on what two separate conditions, and a resolver that has no way to
 * reach for Turkish when the string it was asked for is missing.
 *
 * Several assertions read `locale.ts` as text rather than calling it. That is
 * deliberate and it is the point of the issue: a fallback parameter that is
 * unused today is passed tomorrow, and the review that would have caught it
 * reads a diff, not a test run. The resolver may not *have* a default to
 * reach for.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOCALE,
  LOCALE_REGISTRY,
  MissingLocaleString,
  catalogueComplaints,
  confirmLocaleSwitch,
  defaultSessionLocale,
  offerLocaleSwitch,
  offerableAppLocales,
  offerableIntakeLocales,
  registration,
  resolveMessage,
} from "./locale";

const HERE = __dirname;
const MOBILE = join(HERE, "..", "..", "..");
const SRC = join(MOBILE, "src");
const LOCALE_SOURCE = readFileSync(join(HERE, "locale.ts"), "utf8");

/** `locale.ts` with comments and string literals removed. Several assertions
 * below are about what the module can DO, and prose that discusses a fallback
 * is not a fallback — but an identifier named `fallback` is. */
const LOCALE_CODE_ONLY = LOCALE_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/(^|[^:])\/\/.*$/gm, "$1")
  .replace(/`(?:[^`\\]|\\.)*`/g, "``")
  .replace(/"(?:[^"\\]|\\.)*"/g, '""');

function sources(root: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(root)) {
    const path = join(root, entry);
    if (statSync(path).isDirectory()) {
      found.push(...sources(path));
    } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      found.push(path);
    }
  }
  return found;
}

/* ------------------------------------------------------------------ */
/* 1 — one locale per session, and only `tr` is registered             */
/* ------------------------------------------------------------------ */

describe("the registry", () => {
  it("holds exactly Turkish — HB-O5 names the rest, HB-C19 signs them", () => {
    expect(Object.keys(LOCALE_REGISTRY)).toEqual(["tr"]);
    expect(DEFAULT_LOCALE).toBe("tr");
  });

  it("keeps UI completeness and clinical sign-off as two separate fields", () => {
    const turkish = registration("tr");
    expect(turkish.uiCatalogueComplete).toBe(true);
    expect(turkish.clinicalSignoff).not.toBeNull();
    // Two conditions, two fields — never one flag.
    expect(Object.keys(turkish).sort()).toEqual(
      ["clinicalSignoff", "code", "endonym", "uiCatalogueComplete"].sort(),
    );
  });

  it("names the blockers a widening edit has to read first", () => {
    for (const blocker of ["HB-O5", "HB-C19"]) {
      expect(LOCALE_SOURCE).toContain(blocker);
    }
  });

  it("refuses an unregistered code without echoing what was typed", () => {
    const typedByAPatient = "Kurmancî lütfen, ben Ayşe";
    expect(() => registration(typedByAPatient)).toThrow();
    try {
      registration(typedByAPatient);
    } catch (error) {
      expect(String(error)).not.toContain(typedByAPatient);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 2 — a locale is offered only when it is complete AND signed         */
/* ------------------------------------------------------------------ */

describe("the chooser", () => {
  it("offers exactly the registered, complete, signed set", () => {
    expect(offerableAppLocales()).toEqual(["tr"]);
    expect(offerableIntakeLocales()).toEqual(["tr"]);
  });

  it("drops an incomplete locale rather than falling back to Turkish", () => {
    const incomplete = {
      code: "xx",
      endonym: "Xx",
      uiCatalogueComplete: false,
      clinicalSignoff: null,
    } as const;
    expect(offerableAppLocales({ xx: incomplete })).toEqual([]);
    expect(offerableIntakeLocales({ xx: incomplete })).toEqual([]);
  });

  it("lets a UI-complete but unsigned locale render the app and not run an intake", () => {
    const uiOnly = {
      code: "xx",
      endonym: "Xx",
      uiCatalogueComplete: true,
      clinicalSignoff: null,
    } as const;
    expect(offerableAppLocales({ xx: uiOnly })).toEqual(["xx"]);
    expect(offerableIntakeLocales({ xx: uiOnly })).toEqual([]);
  });

  it("is what the Me screen actually renders — no hardcoded language list", () => {
    const me = readFileSync(join(SRC, "app", "(tabs)", "me", "index.tsx"), "utf8");
    expect(me).toMatch(/offerableAppLocales\(\)/);
    expect(me).not.toMatch(/\["tr",\s*"en"\]\s*as\s*const/);
  });
});

/* ------------------------------------------------------------------ */
/* 3 — completeness is a build property                                */
/* ------------------------------------------------------------------ */

describe("catalogueComplaints", () => {
  it("fails a key missing from an enabled locale", () => {
    const complaints = catalogueComplaints({
      tr: { a: "bir", b: "iki" },
      xx: { a: "one" },
    });
    expect(complaints.join(" ")).toContain("xx");
    expect(complaints.join(" ")).toContain("b");
  });

  it("fails a missing tr catalogue — invariant 5 is not weakened", () => {
    expect(catalogueComplaints({ xx: { a: "one" } }).join(" ")).toContain("tr");
  });

  it("treats an empty value as missing", () => {
    expect(catalogueComplaints({ tr: { a: "bir" }, xx: { a: "  " } })).not.toEqual([]);
  });

  it("passes a complete pair", () => {
    expect(catalogueComplaints({ tr: { a: "bir" }, xx: { a: "one" } })).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* 4 — no per-string fallback, asserted over the module's own source   */
/* ------------------------------------------------------------------ */

describe("resolveMessage", () => {
  it("takes exactly catalogues, locale and key — nothing optional", () => {
    expect(resolveMessage.length).toBe(3);
    expect(LOCALE_SOURCE).not.toMatch(/function resolveMessage[^)]*\?:/);
    expect(LOCALE_SOURCE).not.toMatch(/function resolveMessage[^)]*=\s*DEFAULT_LOCALE/);
  });

  it("resolves a present key", () => {
    expect(resolveMessage({ tr: { a: "bir" }, xx: { a: "one" } }, "xx", "a")).toBe("one");
  });

  it("throws on a missing key rather than reaching for Turkish", () => {
    expect(() => resolveMessage({ tr: { a: "bir" }, xx: {} }, "xx", "a")).toThrow(
      MissingLocaleString,
    );
  });

  it("throws on an unknown locale rather than reaching for Turkish", () => {
    expect(() => resolveMessage({ tr: { a: "bir" } }, "zz", "a")).toThrow(MissingLocaleString);
  });

  it("names no patient input in the failure that reaches a log", () => {
    const typedByAPatient = "Arabic please — Ayşe, 0532 000 00 00";
    try {
      resolveMessage({ tr: { a: "bir" } }, typedByAPatient, "a");
      expect.unreachable("resolveMessage should have thrown");
    } catch (error) {
      expect(String(error)).not.toContain(typedByAPatient);
    }
  });

  it("has no fallback operator anywhere in the module", () => {
    // `??` and `||` are the two shapes a per-string fallback takes in TS.
    expect(LOCALE_CODE_ONLY).not.toContain("??");
    expect(LOCALE_CODE_ONLY).not.toMatch(/\|\|/);
  });

  it("has no fallback-shaped identifier anywhere in the module", () => {
    expect(LOCALE_CODE_ONLY).not.toMatch(/\b(fallback|fallbackLocale|orElse|onMissing)\b/);
  });
});

/* ------------------------------------------------------------------ */
/* 5 — no turn can be assembled from two languages                     */
/* ------------------------------------------------------------------ */

describe("one language per turn", () => {
  it("no shipped screen pins a literal locale onto a single string", () => {
    const offenders: string[] = [];
    for (const path of sources(SRC)) {
      const text = readFileSync(path, "utf8");
      const hits = text.match(/\bt\(\s*"[^"]+"\s*,\s*"(?:tr|en)"\s*\)/g);
      if (hits) {
        offenders.push(`${path}: ${hits.join(", ")}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});

/* ------------------------------------------------------------------ */
/* 6 — chosen, never detected; and unreachable during a RED script     */
/* ------------------------------------------------------------------ */

describe("the switch offer", () => {
  it("is unreachable while a red-flag script is in flight", () => {
    expect(() =>
      offerLocaleSwitch({
        current: defaultSessionLocale(),
        suggested: "tr",
        redScriptInFlight: true,
      }),
    ).toThrow(/red/i);
  });

  it("changes nothing when the patient declines", () => {
    const offer = offerLocaleSwitch({
      current: defaultSessionLocale(),
      suggested: "tr",
      redScriptInFlight: false,
    });
    expect(confirmLocaleSwitch(offer, false)).toEqual({
      code: "tr",
      source: "default",
    });
  });

  it("records a confirmed offer as a patient act", () => {
    const offer = offerLocaleSwitch({
      current: defaultSessionLocale(),
      suggested: "tr",
      redScriptInFlight: false,
    });
    expect(confirmLocaleSwitch(offer, true)).toEqual({
      code: "tr",
      source: "patient_confirmed_offer",
    });
  });

  it("reaches no language detector", () => {
    expect(LOCALE_CODE_ONLY).not.toMatch(
      /\b(detectLanguage|guessLocale|inferLocale|langid|franc|cld[0-9])\b/,
    );
  });
});
