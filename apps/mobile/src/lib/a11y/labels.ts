/**
 * Accessible-name composition (INT-144).
 *
 * Every accessible name in the app is built here, for three reasons that are
 * all conformance reasons rather than tidiness:
 *
 * 1. **One separator, not twenty.** Before this module the app assembled
 *    names inline with literal `": "`, `" · "` and `" — "` scattered across
 *    six files. A separator is punctuation, not prose, so it does not belong
 *    in the tr catalog (invariant 5 governs translatable strings); but it
 *    does belong in exactly one place, so a screen reader reads the same
 *    rhythm everywhere and `e2e/a11y.spec.ts` can prove no file invents its
 *    own.
 * 2. **Label in Name (WCAG 2.2 SC 2.5.3).** A control whose visible text is
 *    "Onaylayın" must have that text at the START of its accessible name, or
 *    a voice-control user saying "Onaylayın" cannot reach it. `withContext`
 *    puts the visible label first and the disambiguating context after.
 * 3. **The two-sided transcript.** A screen-reader user reading the voice
 *    dialogue must know who spoke each turn. `spoken` prefixes every bubble
 *    with its speaker, because visual left/right alignment carries that
 *    information for sighted users and nothing carried it otherwise.
 *
 * PolicyGuard posture: nothing here adds words. Every part passed in is
 * already on screen — these functions only join and order what the patient
 * can already read, so an accessible name can never say more than the visual
 * (and in particular can never volunteer a clinical interpretation).
 */

/** Between a label and its value: "Telefon numaranız: 0532…". */
const VALUE_SEPARATOR = ": ";

/** Between peer parts of one name: "Kardiyoloji · 3 Eylül Perşembe". */
const PART_SEPARATOR = " · ";

/** Drop empty parts so a name never reads "Kardiyoloji ·  · ". */
function present(parts: readonly (string | null | undefined)[]): string[] {
  return parts.map((part) => (part ?? "").trim()).filter((part) => part.length > 0);
}

/**
 * Join peer parts of one accessible name.
 *
 * Returns "" when nothing is present, which callers must treat as "no name"
 * rather than passing an empty `accessibilityLabel` — an empty label is
 * worse than none, because it suppresses the name the children would have
 * supplied.
 */
export function joinParts(...parts: readonly (string | null | undefined)[]): string {
  return present(parts).join(PART_SEPARATOR);
}

/**
 * "<label>: <value>" — the labelled-value form used by settings rows, note
 * sections and any control whose name is a field plus its current content.
 * With no value it degrades to the bare label rather than a dangling colon.
 */
export function labelled(label: string, value: string | null | undefined): string {
  const parts = present([label, value]);
  return parts.length > 1
    ? `${parts[0]}${VALUE_SEPARATOR}${parts.slice(1).join(PART_SEPARATOR)}`
    : (parts[0] ?? "");
}

/**
 * SC 2.5.3 Label in Name: the control's VISIBLE text first, then whatever
 * context the screen reader needs that the eye gets from position.
 *
 * `withContext("Onaylayın", "Şikâyet süresi")` → "Onaylayın · Şikâyet süresi"
 * — a voice-control user says "Onaylayın" and is understood, and a
 * screen-reader user still learns which row it belongs to.
 */
export function withContext(
  visibleLabel: string,
  ...context: readonly (string | null | undefined)[]
): string {
  return joinParts(visibleLabel, ...context);
}

/**
 * One turn of the voice dialogue, named for a screen reader.
 *
 * `speaker` is the catalog's Turkish speaker noun ("Vizite" / "Siz"); the
 * body parts are the words already rendered in the bubble. The speaker
 * always comes first because a transcript read without attribution is the
 * single largest accessibility defect the dialogue surface can have — left
 * and right alignment is not conveyed by any screen reader.
 */
export function spoken(speaker: string, ...body: readonly (string | null | undefined)[]): string {
  return labelled(speaker, joinParts(...body));
}
