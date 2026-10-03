/**
 * The stage's filled field (ADR-039 S7, INT-464): INT-433's filled rule in
 * the stage palette, for the sign-in fields.
 *
 * A field is content, not glass: a solid field fill with no resting outline.
 * Focus draws a 2 pt accent ring. Increase Contrast gives the resting field
 * its boundary back. field.test.ts holds the ring to 3:1 against the fill.
 */
import type { StagePalette } from "./palette";

export interface StageFieldChrome {
  readonly backgroundColor: string;
  readonly borderWidth: number;
  readonly borderColor: string;
}

/** The focus ring's width, in points. */
const RING = 2;

export function stageFieldChrome(
  palette: StagePalette,
  { focused }: { readonly focused: boolean },
): StageFieldChrome {
  if (focused) {
    return { backgroundColor: palette.field, borderWidth: RING, borderColor: palette.accent };
  }
  if (palette.cardBorder !== null) {
    return { backgroundColor: palette.field, borderWidth: 1, borderColor: palette.cardBorder };
  }
  return { backgroundColor: palette.field, borderWidth: 0, borderColor: "transparent" };
}
