/**
 * INT-301 — the language chooser, pure half.
 *
 * INT-296 landed the registry and its two conditions (a locale may RENDER the
 * app when its UI catalogue is complete, and may RUN AN INTAKE only when a
 * clinician who reads it has also signed its clinical text). This module turns
 * that offerable set into what a chooser needs:
 *
 *  - each language in its OWN name and script — its endonym from the registry,
 *    plus its writing direction, which is left-to-right for every offered
 *    locale until INT-253's RTL audit (`./direction`, owner decision
 *    2026-09-26);
 *  - the one rule that a chooser with a single option is worse than none, so a
 *    would-be one-item chooser is ABSENT (acceptance 4);
 *  - a narrowing to the pack in play, because an intake speaks that pack's
 *    signed clinical text and no other;
 *  - the sanctioned switch, which refuses while a red-flag script is in flight
 *    with the same explicit refusal barge-in uses (invariant 21).
 *
 * The registry holds exactly `tr`, so every chooser this build renders is
 * ABSENT. That is the deliverable: the mechanism, waiting for HB-O5 to name a
 * second language and HB-C19 to sign it. This module adds no locale.
 */
import { TEXT_DIRECTION, type TextDirection } from "./direction";
import {
  LOCALE_REGISTRY,
  chooseSessionLocale,
  offerableAppLocales,
  offerableIntakeLocales,
  registration,
  RedScriptInFlight,
  type LocaleRegistration,
  type SessionLocale,
} from "../i18n/locale";

/** One row a chooser draws: the code it selects, the language's own name, and
 * the direction it is laid out in. Nothing here is patient input. */
export interface LocaleChoice {
  readonly code: string;
  readonly endonym: string;
  readonly direction: TextDirection;
}

type Registry = Readonly<Record<string, LocaleRegistration>>;

/**
 * Turn registered locale codes into displayable choices.
 *
 * The endonym comes from the registry (a build-time constant), never from a
 * catalogue string and never from anything a patient typed. A code the
 * registry does not know throws rather than rendering an invented name.
 */
export function toChoices(
  codes: readonly string[],
  registry: Registry = LOCALE_REGISTRY,
): LocaleChoice[] {
  return codes.map((code) => {
    const entry = resolve(code, registry);
    return { code: entry.code, endonym: entry.endonym, direction: TEXT_DIRECTION };
  });
}

/** The registration for `code` in `registry`. A miss defers to the canonical
 * `registration()` refusal (INT-296) — which throws `LocaleNotOffered` and
 * echoes nothing a caller supplied — rather than inventing a message here.
 * The default registry path resolves identically to `registration()`. */
function resolve(code: string, registry: Registry): LocaleRegistration {
  const entry = registry[code];
  if (entry !== undefined) {
    return entry;
  }
  return registration(code);
}

/**
 * The absent-when-one rule (acceptance 4).
 *
 * A chooser with a single choice teaches a patient the feature does not work,
 * so it is worse than no chooser at all. Below two real choices, there is no
 * chooser — the caller renders nothing.
 */
export function present(choices: readonly LocaleChoice[]): LocaleChoice[] {
  return choices.length >= 2 ? [...choices] : [];
}

/**
 * The chooser for RENDERING the app: every locale whose UI catalogue is
 * complete, as choices, gated by `present`. This is the switch on the Me
 * screen and at first run — the language the surface is drawn in.
 */
export function appLocaleChooser(registry: Registry = LOCALE_REGISTRY): LocaleChoice[] {
  return present(toChoices(offerableAppLocales(registry), registry));
}

/**
 * The chooser for RUNNING AN INTAKE: complete AND signed, and narrowed to the
 * pack in play. An intake speaks red-flag scripts and instrument items, so a
 * locale is offered only when the pack that will be served carries signed
 * content for it — `packSignedLocales` is that set. Omitting it means "not yet
 * narrowed to a pack" and leaves the registry's signed set as the bound.
 */
export function intakeLocaleChooser(options?: {
  packSignedLocales?: readonly string[];
  registry?: Registry;
}): LocaleChoice[] {
  const registry = options?.registry ?? LOCALE_REGISTRY;
  const pack = options?.packSignedLocales;
  const offered = offerableIntakeLocales(registry).filter(
    (code) => pack === undefined || pack.includes(code),
  );
  return present(toChoices(offered, registry));
}

/**
 * The one sanctioned way the chooser changes a session's language.
 *
 * It refuses while a red-flag script is in flight, throwing the same
 * `RedScriptInFlight` that `offerLocaleSwitch` throws and that barge-in's
 * refusal uses: a language prompt on top of "hold pressure, call 112" sits a
 * modal between the patient and the sentence that matters most (invariant 21).
 * Otherwise it delegates to `chooseSessionLocale`, which admits only a
 * registered, complete AND signed locale — a language good enough to draw a
 * settings screen is not good enough to speak a triage script.
 */
export function chooseFromChooser(
  target: string,
  options: { readonly redScriptInFlight: boolean },
): SessionLocale {
  if (options.redScriptInFlight) {
    throw new RedScriptInFlight(
      "a red-flag script is in flight: a language switch is refused until it has been " +
        "delivered — the same refusal barge-in uses (invariant 21)",
    );
  }
  return chooseSessionLocale(target);
}
