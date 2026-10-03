/**
 * The typed question screen's presentation rules (INT-433), as data.
 *
 * Pure: no react-native import, so lib/intake/questionScreen.test.ts holds
 * every rule in node. The screen (app/(tabs)/visits/[visitId]/intake.tsx) and
 * its progress control (components/QuestionProgress.tsx) are the only
 * importers, and e2e/questionScreen.spec.ts keeps it that way: the numerals
 * this module formats are display-only and never reach the spoken lane
 * (invariant 22).
 */
/** Where the current question sits in the flow the patient is actually in. */
export interface QuestionPosition {
  /** 1-based place of the current question in the applicable list. */
  readonly position: number;
  /** The applicable count: never the pack's length (INT-136, INT-236). */
  readonly total: number;
  /** position / total, for the bar's fill; always in (0, 1]. */
  readonly fraction: number;
  /** A gate could still add steps, so the screen says more may follow. */
  readonly mayGrow: boolean;
}

/**
 * The bar and the "Soru N / M" line, from the pack layer's applicable list.
 *
 * An id outside the list (an edit reopening a question a later answer gated
 * out) sits at the first place rather than at zero, so the bar never renders
 * empty under a question that is on screen.
 */
export function questionPosition(
  applicable: readonly { readonly id: string }[],
  currentId: string,
  canGrow: boolean,
): QuestionPosition {
  const total = Math.max(applicable.length, 1);
  const index = applicable.findIndex((q) => q.id === currentId);
  const position = Math.min(Math.max(index + 1, 1), total);
  return { position, total, fraction: position / total, mayGrow: canGrow };
}

/**
 * The visible line, "Soru 3 / 9". Integers are printed as one run of digits
 * (no grouping separator), and the slash is typography, not a word.
 */
export function positionLabel(position: QuestionPosition, word: string): string {
  return `${word} ${digits(position.position)} / ${digits(position.total)}`;
}

/**
 * What a screen reader hears as the progressbar's value, "Soru 3, toplam 9":
 * worded, because a slash is read aloud as a symbol.
 */
export function positionSpoken(position: QuestionPosition, word: string, of: string): string {
  return `${word} ${digits(position.position)}, ${of} ${digits(position.total)}`;
}

function digits(n: number): string {
  return Math.trunc(n).toString(10);
}

/**
 * The filled field and the chip are the shared control rules (lib/controlChrome.ts):
 * the chat takes them too, and it must not import this module (invariant 22).
 */
export {
  FOCUS_RING,
  chipChrome,
  filledFieldChrome,
  type ChipChrome,
  type FieldChrome,
} from "@/lib/controlChrome";
