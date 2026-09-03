/**
 * `overlay.low_literacy` on the typed surface (INT-136) — the chips half of
 * files/04 §2.3's *"chips + slow pace"*, held to what files/02 §3 promises:
 *
 *   "full operation **without reading**. Every chip label is spoken and
 *    selectable by voice; severity is **numeracy-free, using 3–4 ordinal
 *    spoken anchors** (Cowan 2010 on working-memory capacity — *not* the 7±2
 *    folklore that `13 §5.3` debunks); **no free text anywhere on the critical
 *    path**."
 *
 * Everything here is a DELIVERY rule, and that is the constraint files/04 §2.3
 * imposes on an overlay in the first place: *"may only add/tighten red flags or
 * change delivery; they never remove questions clinicians marked `must_ask`"*.
 * So no function in this file drops a step, re-scales one, or re-words one.
 * Where the pack cannot satisfy a rule, the function NAMES the step and
 * `lowLiteracyReadiness` reports the overlay as not ready — because the
 * alternative, recoding an eleven-point scale into three or four Turkish
 * anchors, is a clinical judgement and HUMAN_BLOCKERS.md rule 1 forbids taking
 * it here. `packages/protocols`' own base layer records that no anchor wording
 * for that scale is authored anywhere.
 *
 * The runtime half of the same promise already exists and is where this
 * vocabulary comes from: `tests/sim/driver.py free_text_critical_path_steps`
 * and scenario IM-10.
 *
 * **Who calls these.** The suite, and that is deliberate rather than a gap.
 * They are pack GATES in the shape `free_text_critical_path_steps` already
 * has — nothing about them belongs on a render path, and a rule that fired at
 * runtime would be telling a patient about a pack defect. `lowLiteracy.test.ts`
 * runs each over every shipped pack in both modes, with a fixture that makes it
 * fail; a pack change that breaks one reddens `make check`.
 */
import { MAX_SPOKEN_OPTION_HINTS } from "../dialogue/speech";
import { t } from "../i18n";
import { spokenPack, type IntakeQuestion } from "./questions";

/**
 * The ordinal anchor bound of files/02 §3, which cites Cowan 2010 and names
 * the number it is NOT: *"3–4 ordinal spoken anchors … not the 7±2 folklore
 * that `13 §5.3` debunks"*. These are the two ends of that range and nothing
 * else — they are not a clinical threshold, and no answer is graded by them.
 */
export const ORDINAL_ANCHOR_MIN = 3;

/**
 * The upper end, and it is not a second number: `dialogue/speech.ts` already
 * carries this bound as `MAX_SPOKEN_OPTION_HINTS` — files/13 §5.3, Cowan's ~4
 * chunks, the bound above which the spoken lane branches instead of
 * enumerating. Two constants for one published finding is how they drift, so
 * this one is derived rather than restated.
 */
export const ORDINAL_ANCHOR_MAX = MAX_SPOKEN_OPTION_HINTS;

/** Steps declared `ordinal` whose anchor set is outside the files/02 §3 bound. */
export function ordinalAnchorOffenders(pack: readonly IntakeQuestion[]): string[] {
  return pack
    .filter((question) => question.ordinal === true)
    .filter((question) => {
      const anchors = question.options?.length ?? 0;
      return anchors < ORDINAL_ANCHOR_MIN || anchors > ORDINAL_ANCHOR_MAX;
    })
    .map((question) => question.id);
}

/**
 * Steps a patient could only pass by typing.
 *
 * The mobile mirror of `free_text_critical_path_steps`, and it reads the
 * critical path the same way that function does — the set a session cannot
 * legitimately finish without. A `text` step is not in it: the typed screen
 * commits one on an empty field (its CTA carries no `disabled`), so a keyboard
 * step never blocks the flow and the patient reaches the review either way.
 *
 * What WOULD block it is an option-bearing step with no options: under an open
 * ask the grid is the fallback beneath the answer field, so an empty grid
 * leaves the keyboard as the only control. That is also the shape an instrument
 * step takes when its verbatim choices did not resolve, which is exactly the
 * degradation invariant 10 must not allow.
 */
export function typingOnlySteps(pack: readonly IntakeQuestion[]): string[] {
  return pack
    .filter((question) => question.kind === "chips" || question.kind === "single")
    .filter((question) => (question.options?.length ?? 0) === 0)
    .map((question) => question.id);
}

/**
 * Chip labels that a digit would ride into a speech model on — invariant 22's
 * *"no numeral reaches any TTS model"*, checked over the whole pack instead of
 * one call at a time.
 *
 * `dialogue/tts.ts assertSpeakableTr` already refuses a digit-bearing string
 * before any request leaves the app, and that is the guarantee. This is the
 * PRE-FLIGHT of the same rule: it fails in CI on the pack a pack author just
 * changed, rather than on a patient's device mid-turn. It reads labels and
 * never `inline` — the numeral belongs to the on-screen render beside the word,
 * and reading the wrong field here is precisely the mistake it exists to catch.
 *
 * `spokenPack` drops the `text_only` steps first, because files/13 §13 means
 * text only — *"no clip, no `speech_tr`, ever"* — so their labels are not on a
 * speech path at all and holding them to a speech rule would be theatre.
 */
export function unspeakableChipLabels(pack: readonly IntakeQuestion[]): string[] {
  return spokenPack(pack)
    .flatMap((question) =>
      (question.options ?? []).map((option) => ({ question, label: t(option.labelKey, "tr") })),
    )
    .filter(({ label }) => /\p{Nd}/u.test(label))
    .map(({ question }) => question.id);
}

/**
 * Steps whose answer is presented to the patient as a NUMERAL — an option
 * carrying an `inline` render.
 *
 * These are not unsafe and nothing here speaks them: the labels are authored
 * Turkish words and the step is `text_only`, so invariant 22 holds. What they
 * are is unreachable for the patient files/02 §3 is about, because a numeric
 * scale is the one thing that section says severity must not be.
 */
export function numeralAnchoredSteps(pack: readonly IntakeQuestion[]): string[] {
  return pack
    .filter((question) => (question.options ?? []).some((option) => option.inline !== undefined))
    .map((question) => question.id);
}

export interface LowLiteracyReadiness {
  /** True when every files/02 §3 delivery rule holds over this pack. */
  readonly ready: boolean;
  /** Each unmet rule, as `<rule>:<step id>`. Empty iff `ready`. */
  readonly unmet: readonly string[];
}

/**
 * Whether the overlay can honour files/02 §3 over this pack, and what stops it.
 *
 * It reports rather than repairs. A pack that fails is not silently narrowed —
 * an overlay may not remove a question — and no substitute wording is
 * invented; the offending step is named so the ask can be put to a clinician.
 */
export function lowLiteracyReadiness(pack: readonly IntakeQuestion[]): LowLiteracyReadiness {
  const unmet = [
    ...ordinalAnchorOffenders(pack).map((id) => `ordinal_anchors:${id}`),
    ...typingOnlySteps(pack).map((id) => `typing_only:${id}`),
    ...unspeakableChipLabels(pack).map((id) => `unspeakable_label:${id}`),
    ...numeralAnchoredSteps(pack).map((id) => `numeral_anchored:${id}`),
  ];
  return { ready: unmet.length === 0, unmet };
}
