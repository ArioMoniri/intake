/**
 * How a question may be answered when the channel is a keyboard (INT-136).
 *
 * This is the app-side mirror of INT-096's
 * `services/voice-runtime/src/intake_voice_runtime/typed/affordance.py`, and
 * it is a mirror rather than a second opinion on purpose. That module already
 * decides the question — *may this slot be answered by typing?* — and answers
 * it by refusing: a numeric slot with no authored `choices_tr` raises
 * `FreeNumericEntryRefused`, because the only remaining control is a numeric
 * text field and CLAUDE.md invariant 22 forbids free numeric text entry on the
 * clinical critical path. files/00 §2 records what ignoring that costs:
 * `parseFloat("2,5")` is `2` (a Turkish-typed 2,5 mg dose read as 2 mg) and
 * `parseFloat("1.500")` is `1.5` (a Turkish-*formatted* 1500 mg read as
 * 1.5 mg), and neither leaves a diff that looks wrong.
 *
 * The UI must honour that contract rather than route around it. A screen that
 * quietly opened a decimal keypad where the runtime refuses would put the
 * hazard back on the one surface the patient actually touches — so the
 * refusal is re-stated here, in the layer that owns the input control, and
 * `e2e/typed_intake.spec.ts` pins both `SLOT_TYPES` and `NUMERIC_SLOT_TYPES`
 * against their Python sources so the two cannot drift.
 *
 * No react-native import: every rule below is testable in node.
 */
import type { IntakeQuestion } from "./questions";

/**
 * Typed slot answers, mirroring `protocols.types.SlotType`. Eight members,
 * no floats — files/03 §6 slot examples plus the GuardExpr scalar types of
 * files/13 §9.5.
 */
export const SLOT_TYPES = [
  "boolean",
  "integer",
  "decimal",
  "string",
  "code",
  "date",
  "duration",
  "quantity",
] as const;

export type SlotType = (typeof SLOT_TYPES)[number];

/**
 * Every slot type whose answer is a magnitude, mirroring
 * `typed/affordance.py NUMERIC_SLOT_TYPES`.
 *
 * `duration` and `quantity` are in the set because they are numbers — a
 * duration is typed as a count of units and a quantity is a magnitude plus a
 * unit — and leaving either out is how a gate written for `integer` and
 * `decimal` quietly stops covering the two slot types a clinical pack
 * actually uses for doses and intervals.
 */
export const NUMERIC_SLOT_TYPES: readonly SlotType[] = [
  "integer",
  "decimal",
  "duration",
  "quantity",
];

/** What the typed lane puts under the question. There is no third shape. */
export type Affordance = "choice" | "free_text";

/**
 * A numeric question offers no discrete answers, so the typed lane cannot
 * render it. Thrown rather than degraded: the alternative is a numeric text
 * field on the clinical critical path.
 */
export class FreeNumericEntryRefused extends Error {
  readonly stepId: string;

  constructor(stepId: string, slotType: SlotType) {
    super(
      `${stepId}: a ${slotType} question with no authored choices has no typed ` +
        "affordance — the only remaining control is a numeric text field, and " +
        "CLAUDE.md invariant 22 forbids free numeric text entry on the clinical " +
        "critical path. The pack must author the discrete answers (files/00 §2 " +
        "gives the dose case); that content is clinical and awaits sign-off " +
        "(HUMAN_BLOCKERS HB-C6, HB-C16).",
    );
    this.name = "FreeNumericEntryRefused";
    this.stepId = stepId;
  }
}

/** The little the input layer needs to know about one question. */
export interface SlotFacts {
  readonly stepId: string;
  readonly slotType: SlotType;
  /** Authored answer labels, verbatim. */
  readonly choicesTr: readonly string[];
}

export function isNumericSlot(slotType: SlotType): boolean {
  return NUMERIC_SLOT_TYPES.includes(slotType);
}

/**
 * The input control, or a refusal.
 *
 * Order matters, and it is INT-096's order. Discrete labels win for every
 * slot type, so a numeric question the pack gave chips to is answered by
 * tapping one; only a numeric question with no labels reaches the refusal.
 */
export function typedAffordance(facts: SlotFacts): Affordance {
  if (facts.choicesTr.length > 0) {
    return "choice";
  }
  if (isNumericSlot(facts.slotType)) {
    throw new FreeNumericEntryRefused(facts.stepId, facts.slotType);
  }
  return "free_text";
}

/**
 * One fixture question projected onto the slot facts above.
 *
 * A question that declares no `slotType` is read from its kind: an option
 * question answers a `code` slot, a free-note step answers a `string` one.
 * The declaration exists so a pack CAN say "this asks for a magnitude" and
 * be held to it — which is what makes `numericStepsWithoutChoices` a gate
 * rather than a tautology.
 */
export function slotFactsFor(question: IntakeQuestion): SlotFacts {
  const options = question.options ?? [];
  return {
    stepId: question.id,
    slotType: question.slotType ?? (question.kind === "text" ? "string" : "code"),
    choicesTr: options.map((option) => option.labelKey),
  };
}

export function affordanceForQuestion(question: IntakeQuestion): Affordance {
  return typedAffordance(slotFactsFor(question));
}

/**
 * Steps that would need a numeric text field to be answered typed.
 *
 * The gate invariant 22 asks for, in the invariant's own boundary: numeric,
 * and with no authored discrete answers. A pack that lists any is a pack the
 * typed lane cannot complete, so the emptiness of this array is a serving
 * precondition and not a style preference.
 */
export function numericStepsWithoutChoices(pack: readonly IntakeQuestion[]): string[] {
  return pack
    .map(slotFactsFor)
    .filter((facts) => isNumericSlot(facts.slotType) && facts.choicesTr.length === 0)
    .map((facts) => facts.stepId);
}
