/**
 * The paired row: ONE leading label beside ONE trailing control.
 *
 * This is the shape that keeps breaking — consent rows, switch rows, settings
 * rows, any row carrying trailing state — and it breaks the same way every
 * time. The label column is told to take the leftover (`flex: 1`) and the
 * trailing control is told nothing at all; React Native defaults a child's
 * `flexShrink` to 0, so the control keeps its intrinsic width and the label
 * absorbs the entire deficit. The label did not overflow — it was SQUEEZED,
 * and squeezing a Turkish word until it breaks mid-syllable is what 00 §2
 * forbids tree-wide.
 *
 * files/00_STATE.md §2, and theme.ts after it: the 2.0 cap is a
 * layout-survival bound, not a comfort preference. A row that cannot survive
 * it CHANGES FORM. It never clamps the text harder, never hides a Turkish
 * suffix behind an ellipsis. So this module answers one question — *can the
 * label and the control still share a line?* — and when the answer is no the
 * row stops being a row and becomes a column.
 *
 * Pure TS, no react-native import, for the reason theme.ts and
 * prefs/appearance.ts are pure: vitest runs in node, so the rule lives where
 * a test can hold it rather than inside a component. (The e2e specs source-
 * scan the components themselves — `vitest.config.ts` collects
 * `e2e/**\/*.spec.ts` too — so the WIRING is provable as well, and
 * appearance.spec.ts now pins it.)
 *
 * ── Why the threshold is a FUNCTION and not a constant ──────────────────────
 *
 * `RAIL_LABEL_MAX_SCALE` could be one number because the rail carries fixed
 * captions in a fixed box. This shape cannot: the trailing word varies while
 * the leading word varies independently. Derived below at the reference width
 * for every consent row and every state its pill can carry, the scale at
 * which the row stops fitting ranges from below 0.9 to "never" — and for the
 * stale and pending states, which are not edge cases (while INT-210 leaves
 * the consent texts empty EVERY row reads "Metin hazırlanıyor"), most rows
 * are already past the boundary at 1.0, the default text size.
 *
 * So the rule is two-term, the same shape `shouldStack` already has for the
 * segmented control: the app-wide scale ceiling OR this row's own arithmetic.
 * The scale term is `isLargeText` — borrowed, not re-litigated, because
 * SwitchRow and Segmented already change form there and a settings group
 * where one row stayed beside is the same class of inconsistency as the
 * owner's "navbar and sizes dont match". No second scalar is minted, because
 * a second scalar is a second thing to be wrong.
 */
import { isLargeText } from "../prefs/appearance";
import { scaledControl, scaledSize, spacing } from "../theme";
import { MIN_TAP } from "./target";

/**
 * The narrowest row the app must survive, in dp.
 *
 * 320, because that is the floor this repo already commits to —
 * `e2e/shares.spec.ts` checks every row it adds at 320 — and because
 * `app.json` is portrait-only with `supportsTablet: false` and ships an
 * `android` block, so the reference is a small phone rather than the widest
 * one a measurement happened to be taken on. A floor derived on a wide device
 * is not a floor.
 *
 * This is the FIRST FRAME only. `pairedRowMetrics` prefers a real measured
 * width the moment `onLayout` supplies one, the way the glass bar prefers its
 * own measurement over its declared floor.
 */
export const REFERENCE_ROW_WIDTH = 320;

/** Screen gutter (Themed.Screen) plus the group's own hairline, both sides. */
const SCREEN_CHROME = spacing.screen * 2 + 2;

/** Row padding, matching components/ListRow.tsx. */
export const ROW_PADDING = spacing.md;

/** A nested sub-row shifts its content column one step right. */
export const ROW_INSET_PADDING = spacing.md + spacing.lg;

/** Space between the label column and the trailing slot. */
export const ROW_GAP = spacing.sm + 4;

/** The "›" affordance at scale 1.0. */
export const CHEVRON_BASE = 13;

/** The leading tonal icon well at scale 1.0 — Oura's row anchor. */
export const ICON_WELL_BASE = 36;

/** The SF Symbol inside that well at scale 1.0. */
export const ICON_GLYPH_BASE = 17;

/** Horizontal padding inside a trailing pill at scale 1.0, per side. */
export const TRAILING_PADDING_BASE = spacing.sm + 4;

/**
 * Glyph advance widths as a fraction of the em, in six measured bands.
 *
 * Every number below is the WIDEST advance in its band, read out of
 * `Inter_400Regular.ttf` — the face `theme.ts` names as `fonts.sans`, the one
 * the root layout loads — and rounded up to two places. A ceiling rather than
 * an average, because an estimate here is only acceptable in one direction:
 * over-reserving changes a row's form one step early, which is visible and
 * harmless, while under-reserving squeezes a word until React Native breaks it
 * mid-syllable, which is the harm this module exists to prevent.
 *
 * The three classes this started with were a guess at the face, and the guess
 * was wrong in the unsafe direction — measured against the shipped file, 610
 * of the 1383 longest-word tokens in the two catalogues reserved LESS than the
 * text needs, the worst of them by 17 %. Two of the three bands were drawn in
 * the wrong place, and the capitals had no band at all:
 *
 *   hairline ≤ 0.269  the dotted and dotless I family, `j` and `l`: a stem and
 *                     its sidebearings, nothing else (0.242; I and İ 0.269).
 *   stem     ≤ 0.377  `t` (0.327), `f` (0.370) and `r` (0.377) — called
 *                     "normal, toward safety" before and in fact the narrowest
 *                     letters after the i family — with the thin punctuation,
 *                     the bracket and solidus family and the space (0.281).
 *   slim     ≤ 0.571  the shallow-bowl lowercase: a â c ç k s ş v x y z, and
 *                     `?` (0.511), which ends a Turkish question inside the
 *                     last token rather than beside it.
 *   normal   ≤ 0.662  the round lowercase (`g`/`ğ` widest at 0.613), the
 *                     digits (`4` widest at 0.646) and the rest of the middle,
 *                     up to the arithmetic signs at 0.662. This is the DEFAULT
 *                     band, so its ceiling is the whole middle: a glyph no set
 *                     below names still cannot under-reserve.
 *   capital  ≤ 0.765  the capitals, which are NOT normal-width — `A` is 0.690,
 *                     `O` and `Ö` are 0.765, against the 0.56 they were given.
 *                     Turkish sentence case puts one at the head of nearly
 *                     every label and in a short word it decides the whole
 *                     width: "On", "No" and "Üç" were the three worst
 *                     under-reservations in the catalogues.
 *   wide     ≤ 1.000  m w M W, the ellipsis (0.864), `%` and `@` (0.982,
 *                     0.966) and the em dash (1.000). `@` is here because
 *                     BREAK_OPPORTUNITY deliberately does not break there, so
 *                     a share recipient is one token.
 *
 * The I family sits in `hairline` and M and W sit in `wide`, both ahead of the
 * capital test, because a band is a width and not a case.
 *
 * Six bands and not fewer: each one is load-bearing, and dropping any of them
 * takes a near-miss in `pairedRow.test.ts` out of the beside form — a model
 * too loose stacks a row that fits, which is the failure the near-misses
 * exist to catch. Six and not more: the remaining splits buy a dp or two and
 * every band is another thing to be wrong.
 *
 * None of this is left as an intention. `e2e/overflow.spec.ts` proves it
 * against the real `Inter_400Regular.ttf` across every APP_STEPS rung and both
 * catalogues, using the same TrueType reader the overflow gates already use —
 * and bounds the slack in the other direction, so the bias stays a bias rather
 * than becoming an always-stack in disguise. A measured `onLayout` width
 * always wins over this estimate anyway; the estimate only has to be right for
 * frame one.
 */
export const GLYPH_ADVANCE_EM = {
  hairline: 0.27,
  stem: 0.38,
  slim: 0.58,
  normal: 0.67,
  capital: 0.77,
  wide: 1.0,
} as const;

/**
 * Trailing pills render at 600, which is wider than the 400 the bands above
 * were read from. This is a whole-string allowance and NOT a per-glyph ratio —
 * Inter's 600 runs up to 1.06× its 400 on individual letters — and it holds
 * because the band ceilings absorb the difference: measured across both
 * catalogues, no string's 600 advance reaches the estimate.
 */
export const SEMIBOLD_WIDENING = 1.02;

const HAIRLINE_GLYPHS = new Set("iıIİîÎjl");
const STEM_GLYPHS = new Set("tfr.,:;!·'‘’|()[]/\\ ");
const SLIM_GLYPHS = new Set("aâcçksşvxyz?");
const WIDE_GLYPHS = new Set("mwMW…%@—");
const CAPITAL_GLYPH = /\p{Lu}/u;

/**
 * Where a line MAY break, and nowhere else.
 *
 * Whitespace, the hyphen family and the solidus are break opportunities the
 * platform text engines honour. "." and "@" are deliberately absent: a break
 * there is not reliable, and assuming one would under-reserve for a hospital
 * address or a share recipient — the unsafe direction.
 */
export const BREAK_OPPORTUNITY = /[\s\-‐-―­/]+/u;

/** The band `glyph` falls in, as a fraction of the em. */
function glyphAdvanceEm(glyph: string): number {
  if (HAIRLINE_GLYPHS.has(glyph)) {
    return GLYPH_ADVANCE_EM.hairline;
  }
  if (STEM_GLYPHS.has(glyph)) {
    return GLYPH_ADVANCE_EM.stem;
  }
  if (SLIM_GLYPHS.has(glyph)) {
    return GLYPH_ADVANCE_EM.slim;
  }
  if (WIDE_GLYPHS.has(glyph)) {
    return GLYPH_ADVANCE_EM.wide;
  }
  return CAPITAL_GLYPH.test(glyph) ? GLYPH_ADVANCE_EM.capital : GLYPH_ADVANCE_EM.normal;
}

/** Advance width of `text` at `fontSizeDp`, in dp. */
export function textWidth(text: string, fontSizeDp: number, semibold = false): number {
  let em = 0;
  for (const glyph of text) {
    em += glyphAdvanceEm(glyph);
  }
  return em * fontSizeDp * (semibold ? SEMIBOLD_WIDENING : 1);
}

/**
 * The widest run of characters in `text` that the renderer cannot split.
 *
 * This is the whole minimum-width question. A label column narrower than its
 * longest token does not wrap — it breaks a Turkish word mid-syllable, which
 * 00 §2 forbids tree-wide — so this token is the floor the column may never
 * go below.
 */
export function longestUnbreakableToken(text: string): string {
  let widest = "";
  let widestWidth = 0;
  for (const token of text.split(BREAK_OPPORTUNITY)) {
    const width = textWidth(token, 1);
    if (width > widestWidth) {
      widest = token;
      widestWidth = width;
    }
  }
  return widest;
}

/**
 * The narrowest the label column may be, in dp — derived from the label's own
 * longest word at the reading role, so a short label reserves almost nothing
 * and a long Turkish compound reserves exactly what it needs.
 *
 * This is the number missing from the rows today: they set `flex: 1` and no
 * minimum, so Yoga is free to shrink the column toward zero, and does.
 */
export function minLabelWidth(label: string, fontScale: number): number {
  return Math.ceil(textWidth(longestUnbreakableToken(label), scaledSize("body", fontScale)));
}

/**
 * How much width the trailing control needs, in dp.
 *
 * A control keeps its intrinsic width: shrinking it wraps its own word or
 * drops it under the target floor, and a target below MIN_TAP is an SC 2.5.8
 * failure traded for a layout one. So the trailing slot never shrinks, and
 * when it cannot fit, the ROW changes instead.
 *
 * The floor is a FIXED `MIN_TAP` rather than a scaled one: `scaledControl(44,
 * 0.5)` is 22, and a control must not follow the text DOWN through the floor
 * for a patient who asked for smaller type.
 */
export function trailingReserve(trailingText: string, fontScale: number): number {
  const text = Math.ceil(textWidth(trailingText, scaledSize("caption", fontScale), true));
  const box = scaledControl(TRAILING_PADDING_BASE, fontScale) * 2 + text;
  return Math.max(box, MIN_TAP);
}

/** What a paired row carries. */
export interface PairedRowShape {
  /** The leading label — the reading text, always `body`, never `micro`. */
  readonly label: string;
  /**
   * The trailing control's own visible word, when it has one ("Açık",
   * "Metin hazırlanıyor"). Omit for a control with no text — a switch track,
   * an icon — and pass `trailingWidth` instead.
   */
  readonly trailingText?: string;
  /**
   * A measured or known trailing width in dp. Wins over `trailingText`, and a
   * row can feed it from the slot's own `onLayout`.
   */
  readonly trailingWidth?: number;
  /**
   * Width already spent, before the label and the control divide the rest —
   * a LEADING fixture such as the icon well plus its gap.
   *
   * It is a separate term rather than folded into the row width because rows
   * carrying both an icon and a trailing control exist (a share row is an
   * icon, an unbounded recipient name and a state caption), and pretending
   * they do not would make the first frame optimistic on exactly the rows
   * whose label is least predictable.
   */
  readonly leading?: number;
  /** "›" affordance — only on rows that navigate. */
  readonly chevron?: boolean;
  /** Nested sub-row (the consent lane toggles): one step of extra indent. */
  readonly inset?: boolean;
}

export type PairedRowForm = "beside" | "stacked";

export interface PairedRowMetrics {
  readonly form: PairedRowForm;
  /** Why — so a test and a reviewer can tell the two causes apart. */
  readonly reason: "fits" | "large-text" | "no-room";
  /** Content width available to label + gaps + trailing + chevron, in dp. */
  readonly available: number;
  /** What those parts need at this scale, in dp. */
  readonly required: number;
  readonly minLabelWidth: number;
  readonly trailingReserve: number;
  readonly chevronSize: number;
  readonly gap: number;
}

/** The row's horizontal padding — leading side plus trailing. */
export function rowHorizontalPadding(inset = false): number {
  return (inset ? ROW_INSET_PADDING : ROW_PADDING) + ROW_PADDING;
}

/**
 * The whole decision, in one pure function.
 *
 * `measuredRowWidth` is the row's own border-box width from `onLayout`, or
 * `null` before the first layout. Measured wins; the reference device is the
 * first frame only.
 *
 * `fontScale` is the ALREADY-EFFECTIVE scale (`useFontScale()`). It is never
 * re-clamped here: every dimension below leaves through `scaledSize` or
 * `scaledControl`, which share theme.ts's one [0.5, 2.0] clamp, so the text
 * and the chrome in this row take the same multiplier from the same place.
 * That is the contract `scaledControl` was added for, and a second clamp here
 * would rebuild "navbar and sizes dont match" one level down.
 */
export function pairedRowMetrics(
  shape: PairedRowShape,
  fontScale: number,
  measuredRowWidth: number | null = null,
): PairedRowMetrics {
  const outer =
    measuredRowWidth !== null && measuredRowWidth > 0
      ? measuredRowWidth
      : REFERENCE_ROW_WIDTH - SCREEN_CHROME;
  const available = Math.max(
    0,
    outer - rowHorizontalPadding(shape.inset) - Math.max(0, shape.leading ?? 0),
  );

  const label = minLabelWidth(shape.label, fontScale);
  const trailing =
    shape.trailingWidth !== undefined && shape.trailingWidth > 0
      ? shape.trailingWidth
      : shape.trailingText !== undefined
        ? trailingReserve(shape.trailingText, fontScale)
        : 0;
  const chevron = shape.chevron === true ? scaledControl(CHEVRON_BASE, fontScale) : 0;
  const gap = ROW_GAP * ((trailing > 0 ? 1 : 0) + (chevron > 0 ? 1 : 0));
  const required = label + trailing + chevron + gap;

  // Two independent reasons, checked in the order a reviewer would ask them.
  // `large-text` first because it is the app-wide ruling rather than this
  // row's arithmetic: above it SwitchRow and Segmented already change form,
  // and a settings group where one row stayed beside is the inconsistency
  // this module exists to end.
  const reason = isLargeText(fontScale) ? "large-text" : required > available ? "no-room" : "fits";
  return {
    form: reason === "fits" ? "beside" : "stacked",
    reason,
    available,
    required,
    minLabelWidth: label,
    trailingReserve: trailing,
    chevronSize: chevron,
    gap,
  };
}

/** Does this row have to change form? */
export function pairedRowStacks(
  shape: PairedRowShape,
  fontScale: number,
  measuredRowWidth: number | null = null,
): boolean {
  return pairedRowMetrics(shape, fontScale, measuredRowWidth).form === "stacked";
}

/**
 * The flex contract, as data, so a test can hold it without a renderer.
 *
 * The label column grows into the leftover and may shrink — but never past
 * `minWidth`, which Yoga honours during shrink and which is the whole repair.
 * The trailing slot does neither: it is a control, its box is its target, and
 * a control that shrinks stops being one.
 */
export const LABEL_COLUMN_FLEX = { flexGrow: 1, flexShrink: 1, flexBasis: 0 } as const;
export const TRAILING_SLOT_FLEX = { flexGrow: 0, flexShrink: 0 } as const;

export interface LabelColumnStyle {
  readonly flexGrow: number;
  readonly flexShrink: number;
  readonly flexBasis: number;
  readonly minWidth: number;
}

/** The label column's style in the beside form. */
export function labelColumnStyle(label: string, fontScale: number): LabelColumnStyle {
  return { ...LABEL_COLUMN_FLEX, minWidth: minLabelWidth(label, fontScale) };
}
