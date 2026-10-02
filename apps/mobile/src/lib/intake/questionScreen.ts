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
import type { ColorToken, ThemeColors } from "@/lib/theme";

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

/** The focus ring's width, held in every state so focusing never moves text. */
export const FOCUS_RING = 2;

export interface FieldChrome {
  readonly backgroundColor: string;
  readonly borderColor: string;
  readonly borderWidth: number;
}

/**
 * The filled answer field (HIG text field on a grouped ground): a `surface`
 * fill with no resting outline; a tint-coloured ring while focused; and the
 * `border` control boundary back at rest when the OS asks for Increase
 * Contrast, the same way iOS adds shapes to controls under that setting.
 */
export function filledFieldChrome(
  colors: ThemeColors,
  state: { readonly focused: boolean; readonly increasedContrast: boolean },
): FieldChrome {
  const borderColor = state.focused
    ? colors.primary
    : state.increasedContrast
      ? colors.border
      : "transparent";
  return { backgroundColor: colors.surface, borderColor, borderWidth: FOCUS_RING };
}

export interface ChipChrome {
  readonly backgroundColor: string;
  readonly textColor: ColorToken;
  /** The selected chip draws a check, so its state is not carried by colour alone. */
  readonly check: boolean;
}

/** A filled capsule; the selected one is tinted, labelled in the tint and checked. */
export function chipChrome(colors: ThemeColors, selected: boolean): ChipChrome {
  return selected
    ? { backgroundColor: colors.primarySoft, textColor: "primary", check: true }
    : { backgroundColor: colors.surface, textColor: "ink", check: false };
}
