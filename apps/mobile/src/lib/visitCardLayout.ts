/**
 * Where the visit card's "›" sits, and the room it takes from the text
 * (INT-372).
 *
 * The chevron used to be painted at the card's right edge while the text ran
 * the full width, so a long Turkish department name ("Kadın Hastalıkları ve
 * Doğum") wrapped straight under the arrow (int-demo 01e224a2). The fix is
 * room the layout reserves: the chevron takes a column of its own beside the
 * text, and the text wraps before it.
 *
 * At the large-text scale that column costs the name the width a long word
 * needs. In the shipped title face at 2.0 on a 320 pt screen,
 * "Hastalıkları" needs 245.2 pt and the card has 246, so any column beside
 * it breaks the word as "Hastalıkla / rı", the break 00 §2 forbids. So at
 * that scale the chevron changes FORM (00 §2), as the tab rail and the
 * segmented control do: it rides the end of the date line, which is short,
 * and the department name gets the card's whole measure. The threshold is
 * the one at which the Card itself tightens its padding, so the card has
 * one idea of "large".
 *
 * Pure and node-testable. components/VisitCard.tsx renders what this says,
 * and e2e/visitCard.spec.ts measures it.
 */
import { isLargeText } from "@/lib/prefs/appearance";
import { spacing } from "@/lib/theme";

/** The glyph's box, in points. */
export const CHEVRON_SIZE = 14;

/** Air between the text and the chevron, in either placement. */
export const CHEVRON_GAP = spacing.sm;

/**
 * `beside`: a column of its own, centred against the whole card.
 * `dateLine`: the end of the date line, leaving the department name the
 * card's full width.
 */
export type ChevronPlacement = "beside" | "dateLine";

export function chevronPlacement(fontScale: number): ChevronPlacement {
  return isLargeText(fontScale) ? "dateLine" : "beside";
}
