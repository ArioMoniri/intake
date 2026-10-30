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
import type { PurposeView } from "./consent/ledger";
import type { PurposeId } from "./consent/purposes";
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

// --- INT-591: İzinleriniz offers no consent this build cannot use ---------------------

/** The purposes only the voice lane uses. lane:linguistic reads text, not voice. */
const VOICE_ONLY_PURPOSES: ReadonlySet<PurposeId> = new Set<PurposeId>(["voice", "lane:affect"]);

/** The voice group's line where voice does not ship; null where it does. */
export function voiceGroupNoteKey(mode: BuildMode): MessageKey | null {
  return voiceShips(mode) ? null : "consent.group.voice.release";
}

export interface ConsentActions {
  /** Offer the grant action on the detail screen. */
  grant: boolean;
  /** Offer the withdraw action — never gated on the build: withdrawal must
   * always be possible (files/06 §2), including a grant made in another build. */
  withdraw: boolean;
  /** The line shown in place of a grant this build does not offer. */
  note: MessageKey | null;
}

/**
 * What the consent detail screen offers for one purpose, in this build. In a
 * release build the voice-only purposes offer no grant — granting them would
 * record special-category consent evidence for a feature that cannot run
 * (KVKK m.4) — and say why instead; a grant already standing keeps its
 * withdraw control. Every other purpose, and every purpose in a dev build, is
 * exactly the ledger's own answer.
 */
export function consentActions(view: PurposeView, mode: BuildMode): ConsentActions {
  const unusable = !voiceShips(mode) && VOICE_ONLY_PURPOSES.has(view.id);
  return {
    grant: view.grantable && !unusable,
    withdraw: view.withdrawable,
    note: unusable ? voiceGroupNoteKey(mode) : null,
  };
}
