/**
 * INT-296 — session locale, mobile half.
 *
 * `index.ts` (INT-130) is the catalogue lookup and stays what it is. This
 * module is the layer above it: which locales this build may OFFER, on what
 * two separate conditions, and a resolver with no way to reach for Turkish
 * when the string it was asked for is missing.
 *
 * **The registry holds exactly `tr`.** That is the deliverable, not a stub.
 * Which languages this product supports is an owner decision (HB-O5) and what
 * they say clinically is a clinician's (HB-C19); registering a second locale
 * here would answer both on their owners' behalf. The mechanism ships, the
 * gate is wired, it fails closed, the content is left empty.
 *
 * Note what this means for `en.ts`: an English catalogue existing is not the
 * same thing as English being offered. It is the reviewer's mirror of the
 * Turkish source of truth (INT-253), and it is deliberately absent from this
 * registry — a language nobody has signed clinical text for cannot be a
 * language a patient is offered.
 *
 * **Invariant 5 is unchanged.** `tr` is the source of truth and the default.
 * Everything here is additive and fails closed.
 */

/** Invariant 5. Not a setting: the source of truth is not configurable. */
export const DEFAULT_LOCALE = "tr";

/**
 * HB-C19's answer for one language, verbatim: *who signs the clinical text
 * for that language, and do they read it*.
 *
 * This is NOT a second copy of a protocol pack's own `clinical_signoff` block.
 * That block is HB-C1 and the compiler's serve interlock is its gate. Both
 * must hold; neither substitutes for the other.
 */
export interface LocaleClinicalSignoff {
  readonly signerRole: string;
  /** Anything but `true` means the signature is machine translation with a name on it. */
  readonly signerReadsLocale: true;
  /** Where the nomination is recorded, so a reviewer can look it up. */
  readonly recordedIn: string;
}

/** One offerable language, and the two separate conditions it must meet. */
export interface LocaleRegistration {
  readonly code: string;
  /** The language's own name for itself — a build-time constant, never patient input. */
  readonly endonym: string;
  /** Condition one: the UI catalogue is complete against `tr`. */
  readonly uiCatalogueComplete: boolean;
  /** Condition two: HB-C19 is answered for this language, or `null`. */
  readonly clinicalSignoff: LocaleClinicalSignoff | null;
}

/** A language tag is a code, never prose — this is what keeps a sentence a
 * patient typed out of a log line or a metric label (invariant 6). */
const LOCALE_CODE = /^[a-z]{2,3}(-[A-Z][a-z]{3})?(-[A-Z]{2})?$/;

const REDACTED_CODE = "<not-a-locale-code>";

/** The only way a locale string reaches a message. Anything that is not a
 * well-formed tag is replaced wholesale, not truncated: a truncated
 * identifier is still an identifier. */
export function safeCode(value: string): string {
  if (LOCALE_CODE.test(value)) {
    return value;
  }
  return REDACTED_CODE;
}

/**
 * The registry. One entry, deliberately.
 *
 * Adding a second means HB-O5 has named the language, HB-C19 has named a
 * signing clinician who reads it, HB-L23 has said what a translated legal text
 * legally is, and HB-L24 has settled that language's instrument licences and
 * validations — four humans, none of them an agent.
 */
// Nothing invented: HB-C19's own "blocks" column reads "every locale except
// `tr` running an intake", which is the register of record saying Turkish's
// answer is already settled. The pack-level signature is the separate,
// still-open HB-C1 and the compiler's serve interlock.
const TURKISH_SIGNOFF: LocaleClinicalSignoff = {
  signerRole: "physician of record",
  signerReadsLocale: true,
  recordedIn: "HUMAN_BLOCKERS.md HB-C19",
};

export const LOCALE_REGISTRY: Readonly<Record<string, LocaleRegistration>> = Object.freeze({
  tr: {
    code: "tr",
    endonym: "Türkçe",
    uiCatalogueComplete: true,
    clinicalSignoff: TURKISH_SIGNOFF,
  },
});

export class LocaleNotOffered extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LocaleNotOffered";
  }
}

/** The registration for `code`, or a refusal that echoes nothing. */
export function registration(code: string): LocaleRegistration {
  const entry: LocaleRegistration | undefined = LOCALE_REGISTRY[code];
  if (entry === undefined) {
    throw new LocaleNotOffered(
      `locale ${safeCode(code)} is not registered; this build offers ` +
        `${Object.keys(LOCALE_REGISTRY).join(", ")} (HB-O5 names the rest, HB-C19 signs them)`,
    );
  }
  return entry;
}

type Registry = Readonly<Record<string, LocaleRegistration>>;

/**
 * Locales the chooser may offer for RENDERING the app.
 *
 * An incomplete locale is absent from this list — never present-and-patched.
 * A screen half in another language and half in Turkish reads as finished,
 * which is worse than a screen that never offered the language at all.
 */
export function offerableAppLocales(registry: Registry = LOCALE_REGISTRY): string[] {
  return Object.entries(registry)
    .filter(([, entry]) => entry.uiCatalogueComplete)
    .map(([code]) => code);
}

/**
 * Locales the chooser may offer for RUNNING AN INTAKE. Strictly narrower, and
 * it has to be: an intake speaks red-flag scripts and instrument items.
 */
export function offerableIntakeLocales(registry: Registry = LOCALE_REGISTRY): string[] {
  return Object.entries(registry)
    .filter(([, entry]) => entry.uiCatalogueComplete && entry.clinicalSignoff !== null)
    .map(([code]) => code);
}

/* ------------------------------------------------------------------ */
/* The resolver, and the fallback it does not have                     */
/* ------------------------------------------------------------------ */

export class MissingLocaleString extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MissingLocaleString";
  }
}

type Catalogues = Readonly<Record<string, Readonly<Record<string, string>>>>;

/**
 * The one string for `key` in `locale`, or a refusal.
 *
 * Three parameters and no fourth. There is no `default`, no `fallback`, no
 * `orElse` — not unused, absent — because a sentence half in another language
 * and half in Turkish is not a degraded translation, it is a sentence the
 * patient cannot parse. Raising at the missing key makes the gap a build
 * failure instead of a production sentence.
 */
export function resolveMessage(catalogues: Catalogues, locale: string, key: string): string {
  const catalogue: Readonly<Record<string, string>> | undefined = catalogues[locale];
  if (catalogue === undefined) {
    throw new MissingLocaleString(
      `no catalogue for locale ${safeCode(locale)}; there is no fallback to ` +
        `${DEFAULT_LOCALE} and there is not meant to be one`,
    );
  }
  const value: string | undefined = catalogue[key];
  if (value === undefined) {
    throw new MissingLocaleString(
      `"${key}" is missing from the ${safeCode(locale)} catalogue; a locale is offered ` +
        `only when it is complete, so this is a build defect rather than a runtime ` +
        `condition to paper over`,
    );
  }
  return value;
}

/**
 * Every reason these catalogues are not shippable.
 *
 * Invariant 5 is generalised here and never weakened: the rule was "`tr` must
 * exist" and becomes "`tr` must exist AND every other catalogue offered must
 * be complete against it". A blank value counts as missing, and is the more
 * dangerous of the two — it passes a key-parity check and renders as nothing.
 */
export function catalogueComplaints(catalogues: Catalogues): string[] {
  const complaints: string[] = [];
  const reference: Readonly<Record<string, string>> | undefined = catalogues[DEFAULT_LOCALE];
  if (reference === undefined) {
    complaints.push(
      `no ${DEFAULT_LOCALE} catalogue: ${DEFAULT_LOCALE} is the source of truth ` +
        `(invariant 5) and every other locale is measured against it`,
    );
    return complaints;
  }
  for (const [key, value] of Object.entries(reference).sort()) {
    if (value.trim() === "") {
      complaints.push(`${DEFAULT_LOCALE}["${key}"] is blank`);
    }
  }
  for (const [code, catalogue] of Object.entries(catalogues).sort()) {
    if (code === DEFAULT_LOCALE) {
      continue;
    }
    for (const key of Object.keys(reference).sort()) {
      const value: string | undefined = catalogue[key];
      if (value === undefined) {
        complaints.push(`${safeCode(code)} is missing "${key}"`);
      } else if (value.trim() === "") {
        complaints.push(`${safeCode(code)}["${key}"] is blank`);
      }
    }
    for (const key of Object.keys(catalogue).sort()) {
      if (!(key in reference)) {
        complaints.push(
          `${safeCode(code)} defines "${key}" with no ${DEFAULT_LOCALE} key: a string ` +
            `authored in another language first is the defect, not the missing mirror`,
        );
      }
    }
  }
  return complaints;
}

/* ------------------------------------------------------------------ */
/* Chosen, never inferred                                              */
/* ------------------------------------------------------------------ */

/**
 * How a session came to be in the language it is in. Three members, and the
 * absent fourth is the point: there is no member meaning "worked out from what
 * the patient said", so a locale that arrived that way is not representable.
 *
 * This is not squeamishness about a model's quality. Invariant 21 puts the
 * red-flag script on the device, fired over the data channel, because a failed
 * escalation is the one failure this product may not have — and a language
 * guess that is wrong delivers that script in a language the patient cannot
 * read.
 */
export type LocaleChoiceSource = "default" | "patient_choice" | "patient_confirmed_offer";

/** The one language a session runs in. Two fields and no third: there is
 * nowhere here for a display name or a confidence score to be carried. */
export interface SessionLocale {
  readonly code: string;
  readonly source: LocaleChoiceSource;
}

/** A proposal the patient has not yet answered. */
export interface LocaleSwitchOffer {
  readonly current: SessionLocale;
  readonly suggested: string;
}

export class RedScriptInFlight extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RedScriptInFlight";
  }
}

/** Turkish, unchosen. */
export function defaultSessionLocale(): SessionLocale {
  return { code: DEFAULT_LOCALE, source: "default" };
}

/** The patient picked `code` from the chooser. Refused unless the locale is
 * registered, complete AND signed: a language good enough to draw a settings
 * screen is not good enough to speak a triage script. */
export function chooseSessionLocale(code: string): SessionLocale {
  const entry = registration(code);
  if (entry.clinicalSignoff === null) {
    throw new LocaleNotOffered(
      `locale ${safeCode(code)} may render the app but may not run an intake: no ` +
        `clinician who reads it has signed its clinical text (HB-C19)`,
    );
  }
  return { code: entry.code, source: "patient_choice" };
}

/**
 * Propose a language change for the patient to confirm.
 *
 * The only door through which anything other than the patient's own tap may
 * influence the session language — and it does not open the door, it produces
 * a proposal that `confirmLocaleSwitch` turns into a locale if and only if the
 * patient says yes.
 *
 * `redScriptInFlight` is a required field of the argument object with no
 * default. A language prompt on top of "hold pressure, call 112" is a modal
 * dialogue between the patient and the sentence that matters most, so this
 * throws rather than returning an offer nobody may show.
 */
export function offerLocaleSwitch(request: {
  readonly current: SessionLocale;
  readonly suggested: string;
  readonly redScriptInFlight: boolean;
}): LocaleSwitchOffer {
  if (request.redScriptInFlight) {
    throw new RedScriptInFlight(
      "a red-flag script is in flight: the language offer is unreachable until it has " +
        "been delivered (invariant 21 — the RED script is pre-positioned on the device " +
        "and nothing may sit in front of it)",
    );
  }
  if (!offerableIntakeLocales().includes(request.suggested)) {
    throw new LocaleNotOffered(
      `locale ${safeCode(request.suggested)} may not be offered: this build runs an ` +
        `intake in ${offerableIntakeLocales().join(", ")}`,
    );
  }
  return { current: request.current, suggested: request.suggested };
}

/** Answer an offer. `false` leaves the session exactly as it was. */
export function confirmLocaleSwitch(
  offer: LocaleSwitchOffer,
  patientConfirmed: boolean,
): SessionLocale {
  if (!patientConfirmed) {
    return offer.current;
  }
  return { code: offer.suggested, source: "patient_confirmed_offer" };
}
