/**
 * Agent speech composition for the spoken dialogue mode (INT-233).
 *
 * Everything the agent says is composed from catalog tr strings — the
 * question's own tr text plus fixed dialogue phrases. Never LLM output,
 * never patient words (invariant 2/10 posture): patient quotes and
 * free-text values are DISPLAYED as text, never synthesized. Turkish is
 * forced explicitly — the agent voice is Turkish regardless of UI locale.
 *
 * Option hints are enumerated only when the list fits spoken working
 * memory — files/13 §5.3: ~4 chunks (Cowan 2001) is the honest bound, and
 * "branch, don't enumerate" the honest pattern; a longer list is asked
 * openly and the extractor maps the answer. Enumeration keeps forward
 * catalog order (13 §5.4: counterbalance forward/reverse — never randomise;
 * the dev tier speaks forward order only and leaves counterbalancing to the
 * runtime).
 *
 * INT-261: what the agent says is the QUESTION and the aside that belongs to
 * asking it, and nothing else. Copy that describes a control — the chips
 * grid's "select more than one", the text field's "leave it blank", a
 * pointer at options that are not on screen — belongs to the lane that has
 * the control. `questionAsideTr` is the single composition the clip and the
 * chat bubble both render, so a silenced session loses the voice and not the
 * words.
 */
import { t } from "../i18n";
import type { IntakeQuestion } from "../intake/questions";
import { optionLabelKey } from "../intake/questions";

/** Spoken enumeration bound (files/13 §5.3, Cowan ~4 chunks). */
export const MAX_SPOKEN_OPTION_HINTS = 4;

function trText(key: Parameters<typeof t>[0]): string {
  return t(key, "tr");
}

/** "a, b veya c" / "a ve b" — list joined from catalog connectors. */
function joinLabels(labels: string[], connectorKey: "dialogue.and" | "dialogue.or"): string {
  if (labels.length === 1) {
    return labels[0];
  }
  const head = labels.slice(0, -1).join(", ");
  return `${head} ${trText(connectorKey)} ${labels[labels.length - 1]}`;
}

/**
 * Everything the agent adds to a question after asking it — today, the
 * spoken option enumeration where the list is short enough to hold. Null
 * when the question stands on its own.
 *
 * Exported because the CHAT BUBBLE renders it too (INT-261). Speech and
 * screen must carry the same words: a patient whose voice lane went silent
 * mid-conversation reads exactly what a patient who can hear the clip is
 * told, and there is nowhere for the two to drift apart.
 *
 * What is deliberately NOT here (INT-261): the pack's `hintKey`. Those are
 * the TYPED lane's control hints — "Birden fazla seçebilirsiniz" describes
 * the chips grid, "İsterseniz boş bırakabilirsiniz" describes the text
 * field — and in a spoken turn neither control exists, so both sentences
 * are false at the moment they are said. Invariant 10 requires the scripted
 * question verbatim; it does not carry the form's affordance copy along
 * with it. Nor does a question turn claim the options are on screen,
 * because they are not: chips render at `confirming`, never while the
 * question is being asked. Above the spoken bound the agent asks openly and
 * the extractor maps the answer — files/13 §5.3's "branch, don't enumerate".
 */
export function questionAsideTr(question: IntakeQuestion): string | null {
  const options = question.options ?? [];
  if (options.length === 0 || options.length > MAX_SPOKEN_OPTION_HINTS) {
    return null;
  }
  const labels = options.map((option) => trText(option.labelKey));
  return `${trText("dialogue.optionsIntro")} ${joinLabels(labels, "dialogue.or")}.`;
}

/**
 * What the agent speaks to ask one step: the tr question text, then the
 * aside where there is one. Nothing else — see `questionAsideTr`.
 */
export function questionSpeechTr(question: IntakeQuestion): string {
  const aside = questionAsideTr(question);
  const title = trText(question.titleKey);
  return aside === null ? title : `${title} ${aside}`;
}

/**
 * The short confirmation prompt for a candidate. Option questions echo the
 * catalog labels of the suggested values; free-text steps use the generic
 * catalog line because the value is the patient's own words and patient
 * words are never synthesized. Unknown option ids are dropped, never
 * spoken.
 */
export function confirmSpeechTr(question: IntakeQuestion, values: string[]): string {
  if (question.kind === "text") {
    return trText("dialogue.confirmTextGeneric");
  }
  const labels = values
    .map((value) => optionLabelKey(question.id, value))
    .filter((key): key is NonNullable<typeof key> => key !== null)
    .map((key) => trText(key));
  if (labels.length === 0) {
    return trText("dialogue.confirmAsk");
  }
  return `${trText("dialogue.confirmIntro")} ${joinLabels(labels, "dialogue.and")}. ${trText("dialogue.confirmAsk")}`;
}
