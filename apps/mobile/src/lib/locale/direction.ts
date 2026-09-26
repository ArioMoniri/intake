/**
 * INT-301 — writing direction, derived from the locale and nowhere else.
 *
 * Right-to-left is a property of a language's SCRIPT, not a decision a screen
 * makes. This module is the single source of that property: the shared screen
 * anatomy (components/Themed.tsx) reads it once and the whole tree inherits
 * the layout direction, so a locale added tomorrow flips coherently without a
 * per-screen edit.
 *
 * The registry holds exactly `tr` (INT-296), which is left-to-right, so this
 * changes nothing that renders today. It exists so that RTL is already a
 * layout property when HB-O5 names a right-to-left language (Arabic, Persian)
 * rather than a scramble of `left`/`right` fixes when one arrives.
 *
 * A note on the trap: Kurmanji — one of HB-O5's candidates — is written in
 * LATIN script in Türkiye and is left-to-right; only Sorani Kurdish uses the
 * Arabic script. So Kurdish is NOT in the RTL language set below; a `-Arab`
 * subtag is the only thing that makes any Kurdish tag right-to-left, and the
 * explicit script subtag always wins.
 */

export type TextDirection = "ltr" | "rtl";

/** ISO 15924 script subtags written right-to-left. An explicit script tag is
 * the authoritative signal — `ku-Arab` is RTL, `ku-Latn` is LTR. */
const RTL_SCRIPTS: ReadonlySet<string> = new Set([
  "Arab", // Arabic
  "Hebr", // Hebrew
  "Syrc", // Syriac
  "Thaa", // Thaana (Dhivehi)
  "Nkoo", // N'Ko
  "Rohg", // Hanifi Rohingya
]);

/** Languages whose default script is right-to-left, keyed by the primary
 * subtag. Deliberately does NOT include `ku` (Kurmanji is Latin in Türkiye). */
const RTL_LANGUAGES: ReadonlySet<string> = new Set([
  "ar", // Arabic
  "fa", // Persian / Farsi
  "he", // Hebrew
  "ur", // Urdu
  "ps", // Pashto
  "sd", // Sindhi
  "ug", // Uyghur
  "yi", // Yiddish
  "dv", // Dhivehi
]);

/**
 * The writing direction of a BCP-47 locale tag.
 *
 * An explicit script subtag (`ku-Arab`, `az-Arab`) is decisive; otherwise the
 * primary language subtag decides. Anything not known to be right-to-left is
 * left-to-right — the safe default, and the correct one for every locale this
 * build offers.
 */
export function localeDirection(code: string): TextDirection {
  const parts = code.split("-");
  const script = parts.find((part) => /^[A-Z][a-z]{3}$/.test(part));
  if (script !== undefined) {
    return RTL_SCRIPTS.has(script) ? "rtl" : "ltr";
  }
  const language = (parts[0] ?? "").toLowerCase();
  return RTL_LANGUAGES.has(language) ? "rtl" : "ltr";
}
