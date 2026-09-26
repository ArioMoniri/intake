/**
 * INT-301 — the language chooser, pure half.
 *
 * INT-296 landed the registry (which locales this build may OFFER, on two
 * separate conditions) and a resolver with no fallback. This module is the
 * layer the chooser UI reads: the offerable set turned into displayable
 * choices — each language in its OWN name and script (its endonym) and with
 * the writing direction its script implies — plus the one rule that a chooser
 * with a single option is worse than none, and the sanctioned switch that
 * refuses while a red-flag script is in flight.
 *
 * The registry holds exactly `tr` (INT-296). So the two assertions that
 * matter most here read the REAL registry and expect the chooser to be
 * ABSENT: a one-item chooser teaches a patient the feature does not work
 * (acceptance 4). Everything that proves the mechanism renders a real choice
 * runs against a SYNTHETIC registry — this issue adds no locale.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  appLocaleChooser,
  chooseFromChooser,
  intakeLocaleChooser,
  present,
  toChoices,
} from "./chooser";
import { localeDirection } from "./direction";
import { LocaleNotOffered, RedScriptInFlight, type LocaleRegistration } from "../i18n/locale";

const HERE = __dirname;
const CHOOSER_SOURCE = readFileSync(join(HERE, "chooser.ts"), "utf8");

/** chooser.ts with comments and string literals stripped — the same trick
 * locale.test.ts uses so a claim about what the module can DO is not fooled
 * by prose that merely discusses it. */
const CHOOSER_CODE_ONLY = CHOOSER_SOURCE.replace(/\/\*[\s\S]*?\*\//g, "")
  .replace(/(^|[^:])\/\/.*$/gm, "$1")
  .replace(/`(?:[^`\\]|\\.)*`/g, "``")
  .replace(/"(?:[^"\\]|\\.)*"/g, '""');

/** A second locale, invented ONLY for the test — never for the registry. */
function reg(
  code: string,
  endonym: string,
  uiCatalogueComplete: boolean,
  signed: boolean,
): LocaleRegistration {
  return {
    code,
    endonym,
    uiCatalogueComplete,
    clinicalSignoff: signed
      ? { signerRole: "test", signerReadsLocale: true, recordedIn: "test" }
      : null,
  };
}

/* ------------------------------------------------------------------ */
/* 1 — each language in its own name and script                        */
/* ------------------------------------------------------------------ */

describe("toChoices", () => {
  it("shows a language in its own endonym, from the registry", () => {
    expect(toChoices(["tr"])).toEqual([{ code: "tr", endonym: "Türkçe", direction: "ltr" }]);
  });

  it("carries the writing direction the script implies, not a per-screen flag", () => {
    const registry = {
      tr: reg("tr", "Türkçe", true, true),
      ar: reg("ar", "العربية", true, true),
    };
    const choices = toChoices(["tr", "ar"], registry);
    expect(choices.find((c) => c.code === "tr")?.direction).toBe("ltr");
    expect(choices.find((c) => c.code === "ar")?.direction).toBe("rtl");
    // The direction is derived, never stored on the row by hand.
    expect(choices.find((c) => c.code === "ar")?.direction).toBe(localeDirection("ar"));
  });

  it("refuses a code the registry does not know rather than inventing an endonym", () => {
    expect(() => toChoices(["zz"])).toThrow(LocaleNotOffered);
  });
});

/* ------------------------------------------------------------------ */
/* 2 — a chooser with one choice is worse than none (acceptance 4)     */
/* ------------------------------------------------------------------ */

describe("present — the absent-when-one rule", () => {
  it("drops a single-option chooser to nothing", () => {
    expect(present(toChoices(["tr"]))).toEqual([]);
  });

  it("drops an empty chooser to nothing", () => {
    expect(present([])).toEqual([]);
  });

  it("keeps a chooser once there are two real choices", () => {
    const registry = { tr: reg("tr", "Türkçe", true, true), ar: reg("ar", "العربية", true, true) };
    expect(present(toChoices(["tr", "ar"], registry))).toHaveLength(2);
  });
});

/* ------------------------------------------------------------------ */
/* 3 — with only `tr` the chooser is absent, not a one-item list       */
/* ------------------------------------------------------------------ */

describe("the real build", () => {
  it("offers no app chooser — only tr is registered", () => {
    expect(appLocaleChooser()).toEqual([]);
  });

  it("offers no intake chooser — only tr is registered", () => {
    expect(intakeLocaleChooser()).toEqual([]);
  });

  it("adds no second locale of its own — no locale literal hides in the module", () => {
    // Invariant 17 / acceptance 4: the mechanism ships empty. A hardcoded
    // "ar"/"en"/"fa"/… would be a fabricated locale.
    expect(CHOOSER_CODE_ONLY).not.toMatch(/\b(ar|en|fa|de|ru|ku|he|ur)\b/);
  });
});

/* ------------------------------------------------------------------ */
/* 4 — complete AND signed, for the pack in play                       */
/* ------------------------------------------------------------------ */

describe("appLocaleChooser", () => {
  it("lists a UI-complete locale (rendering the app needs no clinical sign-off)", () => {
    const registry = {
      tr: reg("tr", "Türkçe", true, true),
      xx: reg("xx", "Xxязык", true, false), // UI complete, unsigned
    };
    expect(appLocaleChooser(registry).map((c) => c.code)).toEqual(["tr", "xx"]);
  });

  it("drops an incomplete locale rather than rendering half a screen", () => {
    const registry = {
      tr: reg("tr", "Türkçe", true, true),
      xx: reg("xx", "Xx", false, false),
    };
    expect(appLocaleChooser(registry)).toEqual([]); // only tr survives -> absent
  });
});

describe("intakeLocaleChooser", () => {
  it("lists only complete AND signed locales — an intake speaks clinical text", () => {
    const registry = {
      tr: reg("tr", "Türkçe", true, true),
      xx: reg("xx", "Xxязык", true, false), // UI complete, NOT signed
    };
    expect(intakeLocaleChooser({ registry })).toEqual([]); // only tr signed -> absent
  });

  it("narrows to the pack in play: a signed locale absent from the pack is not offered", () => {
    const registry = {
      tr: reg("tr", "Türkçe", true, true),
      ar: reg("ar", "العربية", true, true),
    };
    // Both signed at the registry, but the pack carries signed content for tr only.
    expect(intakeLocaleChooser({ registry, packSignedLocales: ["tr"] })).toEqual([]);
    // The pack carries both -> the chooser has two real choices.
    expect(
      intakeLocaleChooser({ registry, packSignedLocales: ["tr", "ar"] }).map((c) => c.code),
    ).toEqual(["tr", "ar"]);
  });
});

/* ------------------------------------------------------------------ */
/* 5 — the switch refuses while a red-flag script is in flight         */
/* ------------------------------------------------------------------ */

describe("chooseFromChooser", () => {
  it("refuses during a red-flag script with the same refusal barge-in uses", () => {
    expect(() => chooseFromChooser("tr", { redScriptInFlight: true })).toThrow(RedScriptInFlight);
  });

  it("records a clear choice as a patient act when no red script is in flight", () => {
    expect(chooseFromChooser("tr", { redScriptInFlight: false })).toEqual({
      code: "tr",
      source: "patient_choice",
    });
  });

  it("refuses an unregistered target rather than switching into a void", () => {
    expect(() => chooseFromChooser("zz", { redScriptInFlight: false })).toThrow(LocaleNotOffered);
  });

  it("does not echo patient input in the red-script refusal", () => {
    const typed = "Arapça lütfen — Ayşe 0532";
    try {
      chooseFromChooser(typed, { redScriptInFlight: true });
      expect.unreachable("should have refused");
    } catch (error) {
      expect(String(error)).not.toContain(typed);
    }
  });
});

/* ------------------------------------------------------------------ */
/* 6 — chosen, never detected; and no per-string fallback             */
/* ------------------------------------------------------------------ */

describe("the module's shape", () => {
  it("reaches no language detector", () => {
    expect(CHOOSER_CODE_ONLY).not.toMatch(
      /\b(detectLanguage|guessLocale|inferLocale|langid|franc|cld[0-9])\b/,
    );
  });

  it("carries no per-string fallback of its own", () => {
    expect(CHOOSER_CODE_ONLY).not.toMatch(/\b(fallback|fallbackLocale|orElse|onMissing)\b/);
  });
});
