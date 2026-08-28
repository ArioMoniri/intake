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
 * "branch, don't enumerate" the honest pattern; longer lists point to the
 * screen instead. Enumeration keeps forward catalog order (13 §5.4:
 * counterbalance forward/reverse — never randomise; the dev tier speaks
 * forward order only and leaves counterbalancing to the runtime).
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
 * What the agent speaks to ask one step: the tr question text, the hint
 * where the pack carries one, then option hints where the list is short
 * enough to hold — otherwise a pointer to the screen.
 */
export function questionSpeechTr(question: IntakeQuestion): string {
  const parts: string[] = [trText(question.titleKey)];
  if (question.hintKey) {
    parts.push(trText(question.hintKey));
  }
  const options = question.options ?? [];
  if (options.length > 0) {
    if (options.length <= MAX_SPOKEN_OPTION_HINTS) {
      const labels = options.map((option) => trText(option.labelKey));
      parts.push(`${trText("dialogue.optionsIntro")} ${joinLabels(labels, "dialogue.or")}.`);
    } else {
      parts.push(trText("dialogue.optionsOnScreen"));
    }
  }
  return parts.join(" ");
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
