/**
 * INT-588 — patient copy that is true for the build it ships in.
 *
 * Voice ships in a dev build only. intake.tsx gates the voice lane
 * (`voiceEligible`) and the dictation button on `__DEV__`, and INT-421 strips
 * the voice lanes from the production profile. So a release build — the one
 * TestFlight and the App Store carry — can neither talk to the patient nor
 * take dictation, and any line that says it can is false there.
 *
 * Two kinds of fix, chosen per line:
 *
 * - **build-aware keys**, where the dev build has a different truth worth
 *   keeping: the open-answer hint (dictation exists in dev, with the voice
 *   consent), the start-mode chooser (a voice start exists in dev) and the
 *   companion's text-only effect (a change only where questions can be
 *   spoken). The choice lives here, pure, so a test can resolve it in release
 *   mode without rendering a screen (lib/buildCopy.test.ts);
 * - **one line true in every build**, where the voice clause never had to be
 *   there: the welcome body, the integrity warning, the companion footer.
 *   Those are plain catalogue edits, and the same test reads them.
 *
 * tr is the source of truth (invariant 5); every key here has its en mirror.
 */
import type { MessageKey } from "./i18n";
import type { AttributionOutcome } from "./profile/attribution";

export const BUILD_MODES = ["dev", "release"] as const;
export type BuildMode = (typeof BUILD_MODES)[number];

/**
 * The build this bundle is. Metro folds `__DEV__` to false in a release
 * bundle; where it is not defined at all (the node test lane) the answer is
 * the stricter one, release.
 */
export function currentBuildMode(): BuildMode {
  return typeof __DEV__ !== "undefined" && __DEV__ ? "dev" : "release";
}

/** Whether any voice surface — the voice lane, dictation — exists in this build. */
export function voiceShips(mode: BuildMode): boolean {
  return mode === "dev";
}

/**
 * The open-answer hint. It names dictation only where the dictation button is
 * drawn: a dev build, with the voice consent — the same two facts intake.tsx
 * checks before rendering `VoiceNote` (e2e/releaseCopy.spec.ts holds them
 * together).
 */
export function openAnswerHintKey(mode: BuildMode, voiceConsent: boolean): MessageKey {
  return voiceShips(mode) && voiceConsent ? "intake.open.hintVoice" : "intake.open.hint";
}

/** The Görünüm start-mode chooser offers "Konuşarak"; it exists only where that start does. */
export function startModeOffered(mode: BuildMode): boolean {
  return voiceShips(mode);
}

/**
 * "Bu görüşmede neler değişir" — what the declared companion and third-party
 * facts change, in this build. Text-only for sensitive topics is a change only
 * where a question could otherwise be spoken; in a release build every
 * question is already written, so listing it would describe a change that does
 * not happen.
 */
export function companionEffectKeys(outcome: AttributionOutcome, mode: BuildMode): MessageKey[] {
  const keys: MessageKey[] = [];
  if (outcome.proxyReported) {
    keys.push("companion.effect.proxy");
  }
  if (outcome.attribution === "assisted_self_report") {
    keys.push("companion.effect.assisted");
  }
  if (outcome.sensitiveTextOnly && voiceShips(mode)) {
    keys.push("companion.effect.textOnly");
  }
  if (!outcome.safeguardingAsked) {
    keys.push("companion.effect.noSafeguarding");
  }
  return keys;
}
