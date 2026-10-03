/**
 * The filled field and the answer chip, as data (INT-433's rules, shared by
 * INT-462 with the chat).
 *
 * Pure: no react-native import. INT-433 wrote these rules for the typed
 * question screen (lib/intake/questionScreen.ts re-exports them). They live
 * here so the chat's composer and confirm chips can take the same rules
 * without importing the question module, which formats the "Soru N / M"
 * numerals and must stay unreachable from the spoken lane (invariant 22,
 * e2e/questionScreen.spec.ts). Nothing here formats a number.
 */
import type { ColorToken, ThemeColors } from "@/lib/theme";

/** The focus ring's width, held in every state so focusing never moves text. */
export const FOCUS_RING = 2;

export interface FieldChrome {
  readonly backgroundColor: string;
  readonly borderColor: string;
  readonly borderWidth: number;
}

/**
 * The filled field (HIG text field on a grouped ground): a `surface` fill with
 * no resting outline; a tint-coloured ring while focused; and the `border`
 * control boundary back at rest when the OS asks for Increase Contrast, the
 * same way iOS adds shapes to controls under that setting.
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
