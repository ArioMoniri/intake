/**
 * Typed, dependency-free i18n (INT-130). Turkish is the source of truth
 * (invariant 5); English mirrors it key-for-key (enforced by test). No
 * interpolation yet — the first string that needs it adds a typed helper,
 * never template literals scattered through components.
 */
import { en } from "./en";
import { tr, type MessageKey } from "./tr";

export type Locale = "tr" | "en";
export type { MessageKey };

const catalogs: Record<Locale, Record<MessageKey, string>> = { tr, en };

let activeLocale: Locale = "tr";

export function setLocale(locale: Locale): void {
  activeLocale = locale;
}

export function getLocale(): Locale {
  return activeLocale;
}

export function t(key: MessageKey, locale?: Locale): string {
  return catalogs[locale ?? activeLocale][key];
}

export const availableLocales: readonly Locale[] = ["tr", "en"];
