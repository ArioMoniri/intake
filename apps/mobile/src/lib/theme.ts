/**
 * Önvizit design tokens (INT-130; native refresh INT-422,
 * docs/design/system-refresh.md).
 *
 * The register is Apple's own: grouped system grounds, a label hierarchy,
 * the platform face at Dynamic Type sizes, an 8-pt grid, 12-pt continuous
 * corners, and ONE restrained accent, a clinical teal. There are no
 * gradients, glows, shadows or tracked eyebrows anywhere in the palette, and
 * nothing here exists to decorate. Materials (Liquid Glass, blur) are for the
 * functional chrome only: the tab rail and the bottom bar
 * (docs/design/apple-native/spec.md §0 rule 1).
 *
 * RED is reserved for the emergency route alone, and its two colours are
 * unchanged by this refresh in every scheme and contrast mode (02 §5.3,
 * ADR-033 §5). Motion budget: 120 ms fades, one animated element at a time
 * (02 §5.2a). Tokens carry the numbers, so nobody re-invents them.
 *
 * Turkish rules baked in (00 §2): no text-transform anywhere (İ/ı casing
 * corrupts strings), no mid-word truncation, sentence case only.
 *
 * Pure TS: no react-native imports, so every token, every contrast pair and
 * the type scale are unit-testable in node. Platform resolution (the font
 * family, the Increase Contrast answer) happens in components/Themed.tsx.
 */

/**
 * The colour tokens. Every scheme and contrast mode defines exactly this set.
 *
 * Grounds follow Apple's grouped hierarchy: `background` is the page,
 * `surface` a cell or card on it, `surfaceRaised` a fill one step up (chips,
 * the segmented track, a secondary button). Text follows the label ladder:
 * `ink` (label), `inkSoft` (secondaryLabel), `inkFaint` (tertiaryLabel).
 * `border` is a CONTROL boundary, strong enough to identify an input or an
 * unselected chip on its own (SC 1.4.11); `separator` is the decorative
 * hairline between rows.
 */
export type ColorToken =
  | "background"
  | "surface"
  | "surfaceRaised"
  | "thumb"
  | "ink"
  | "inkSoft"
  | "inkFaint"
  | "border"
  | "separator"
  | "primary"
  | "primarySoft"
  | "onPrimary"
  | "cta"
  | "onCta"
  | "amber"
  | "amberSoft"
  | "success"
  | "successSoft"
  | "emergency"
  | "emergencySoft";

export type ThemeColors = Readonly<Record<ColorToken, string>>;

export type ColorScheme = "light" | "dark";

/**
 * The OS contrast request: iOS "Increase Contrast" (Darker System Colors) or
 * Android "High contrast text". Both palettes clear every floor in
 * theme.test.ts; `high` strengthens text, boundaries and the accent, and
 * leaves the grounds where they are so nothing moves.
 */
export type Contrast = "standard" | "high";

/**
 * Standard contrast: the palette nearly every patient sees. One literal, so
 * scripts/compliance/render_a11y_report.py reads the same hexes the app
 * renders. RED (`emergency`, `emergencySoft`) keeps its pre-refresh values,
 * and theme.test.ts asserts they are identical in every scheme and contrast
 * mode.
 */
export const palette = {
  light: {
    background: "#F2F2F7", // systemGroupedBackground
    surface: "#FFFFFF", // secondarySystemGroupedBackground
    surfaceRaised: "#E5E5EA", // systemGray5: chips, tracks, the gray button
    thumb: "#FFFFFF", // the selected segment
    ink: "#000000", // label
    inkSoft: "#48484A", // secondaryLabel, opaque and AAA on its grounds
    inkFaint: "#636366", // tertiaryLabel, opaque and AA on every ground
    border: "#86868B", // control boundary, 3:1 on surface and background
    separator: "#C6C6C8", // opaqueSeparator
    primary: "#0B7366", // the one accent: tint for text, glyphs, selection
    primarySoft: "#E1F0ED",
    onPrimary: "#FFFFFF",
    cta: "#0B7366", // the filled prominent button
    onCta: "#FFFFFF",
    amber: "#9A5B00", // YELLOW status only
    amberSoft: "#FBF1DF",
    success: "#146C3E",
    successSoft: "#E3F3E8",
    emergency: "#B3261E", // RESERVED: RED route (ALERT register) only
    emergencySoft: "#F9E5E3",
  },
  dark: {
    background: "#000000", // systemGroupedBackground
    surface: "#1C1C1E", // secondarySystemGroupedBackground
    surfaceRaised: "#2C2C2E", // systemGray5
    thumb: "#636366",
    ink: "#FFFFFF", // label
    inkSoft: "#AEAEB2",
    inkFaint: "#98989D",
    border: "#6A6A6F",
    separator: "#38383A", // opaqueSeparator
    primary: "#4FC3B1",
    primarySoft: "#13302B",
    onPrimary: "#06201C",
    cta: "#0E7C6E",
    onCta: "#FFFFFF",
    amber: "#E0A34E",
    amberSoft: "#332A1C",
    success: "#5CB884",
    successSoft: "#1E2E25",
    emergency: "#E5756D",
    emergencySoft: "#392320",
  },
} as const;

/**
 * Increase Contrast. The grounds and RED are the standard ones; text,
 * boundaries, separators and the accent step further from the grounds, and
 * theme.test.ts holds every pair to at least its standard ratio.
 */
export const highContrastPalette: Readonly<Record<ColorScheme, ThemeColors>> = {
  light: {
    ...palette.light,
    inkSoft: "#3A3A3C",
    inkFaint: "#48484A",
    border: "#6C6C70",
    separator: "#8E8E93",
    primary: "#06594F",
    cta: "#06594F",
    amber: "#7B4800",
    success: "#0B5A31",
  },
  dark: {
    ...palette.dark,
    inkSoft: "#D1D1D6",
    inkFaint: "#AEAEB2",
    border: "#8E8E93",
    separator: "#636366",
    primary: "#7DDCCB",
    amber: "#F0B868",
    success: "#7AD29F",
  },
};

/** The palette for a scheme and contrast mode; both modes define every token. */
export function colorsFor(scheme: ColorScheme, contrast: Contrast): ThemeColors {
  const colors: ThemeColors = contrast === "high" ? highContrastPalette[scheme] : palette[scheme];
  return colors;
}

/**
 * What each token IS on each platform: the UIKit semantic colour on iOS and
 * the Material 3 colour role on Android. `exact` marks the tokens whose
 * standard values are Apple's documented values in both schemes
 * (theme.test.ts pins them). The others keep Apple's role and move its value:
 * secondaryLabel and tertiaryLabel are translucent in UIKit and measure about
 * 3.4:1 and 1.9:1 on white, below this app's floors, so they are opaque and
 * darker here; the accent is the brand's.
 *
 * The app renders these hex values rather than `PlatformColor`, because the
 * patient's in-app theme (INT-260) can differ from the OS one and a system
 * colour would follow the OS, and because a system colour cannot be measured
 * in node, where the contrast floors are enforced.
 */
export interface SystemRole {
  readonly ios: string;
  readonly android: string;
  readonly exact: boolean;
}

export const SYSTEM_ROLES: Readonly<Record<ColorToken, SystemRole>> = {
  background: { ios: "systemGroupedBackground", android: "surfaceContainer", exact: true },
  surface: {
    ios: "secondarySystemGroupedBackground",
    android: "surfaceContainerLowest",
    exact: true,
  },
  surfaceRaised: { ios: "systemGray5", android: "surfaceContainerHighest", exact: true },
  thumb: { ios: "systemBackground (segment thumb)", android: "surfaceBright", exact: false },
  ink: { ios: "label", android: "onSurface", exact: true },
  inkSoft: { ios: "secondaryLabel", android: "onSurfaceVariant", exact: false },
  inkFaint: { ios: "tertiaryLabel", android: "onSurfaceVariant", exact: false },
  border: { ios: "opaqueSeparator (as a boundary)", android: "outline", exact: false },
  separator: { ios: "opaqueSeparator", android: "outlineVariant", exact: true },
  primary: { ios: "tintColor", android: "primary", exact: false },
  primarySoft: { ios: "tintColor (tinted fill)", android: "primaryContainer", exact: false },
  onPrimary: { ios: "white on tint", android: "onPrimary", exact: false },
  cta: { ios: "tintColor (borderedProminent)", android: "primary", exact: false },
  onCta: { ios: "white on tint", android: "onPrimary", exact: false },
  amber: { ios: "systemOrange (darkened)", android: "tertiary", exact: false },
  amberSoft: { ios: "systemOrange (tinted fill)", android: "tertiaryContainer", exact: false },
  success: { ios: "systemGreen (darkened)", android: "secondary", exact: false },
  successSoft: { ios: "systemGreen (tinted fill)", android: "secondaryContainer", exact: false },
  emergency: { ios: "systemRed (reserved)", android: "error", exact: false },
  emergencySoft: { ios: "systemRed (tinted fill)", android: "errorContainer", exact: false },
};

/**
 * The 8-pt grid. `xs` is the one half step (hairline gaps inside a control);
 * every other value is a multiple of 8. `screen` is the iPhone readable
 * margin, the same 16 an inset grouped list uses.
 */
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, screen: 16 } as const;

/**
 * Corners, drawn with `borderCurve: "continuous"` (the squircle iOS uses).
 * One 12-pt radius for every container and control, and a capsule for small
 * tags and pills. No surface is rounder than 12: the oversized 24 and 32 pt
 * corners are gone.
 */
export const radius = { card: 12, group: 12, control: 12, chip: 999 } as const;

/**
 * Motion budget (02 §5.2a): fades only, and only this long.
 *
 * `duration` is the navigators' vocabulary (INT-330, MOTION-1): `fade` for
 * every stack and tab transition, `instant` for the ones that must not move
 * at all (legal text). `fadeMs` predates it and stays as its alias, so the
 * budget is one number however it is spelled.
 *
 * INT-335 (MOTION-6) adds the two curves and the first loop period, each with
 * its first consumer:
 * - `easing.out` is every app-authored transient (lib/motion/fade.ts); no
 *   ease-in exists, because an element that starts slowly reads as late;
 * - `easing.breath` (ease-in-out sine) is for loops only: symmetric, so the
 *   turn of the loop has no visible corner;
 * - `loop` holds FULL periods. SC 2.3.1 draws the line at a 167 ms half, and
 *   theme.test.ts checks every period against it.
 *
 * INT-336 (MOTION-7) adds the presence orb's tokens, with the orb as their
 * first consumer (lib/motion/orb.ts, components/PresenceOrb.tsx):
 * - `duration.fast` is the speaking → listening shift, which starts in the
 *   same tick as the barge-in's `player.pause()`;
 * - `easing.linear` is the level following its samples, and nothing else;
 * - the three orb periods replace the dialogue pulse's `pulsePeriodMs`, which
 *   left with the pulse;
 * - `level` turns the recorder's metering into one 0…1 scalar at 10 Hz or
 *   less (attack faster than release, 0.05 steps);
 * - `orb` holds opacities only. The scale values the voice spec proposed ship
 *   only if the owner answers ADR-033 Q5 yes; until then no scale token exists.
 */
export type Bezier = readonly [number, number, number, number];

const duration = { instant: 0, fast: 90, fade: 120 } as const;

const easing = {
  out: [0.23, 1, 0.32, 1] as Bezier,
  breath: [0.37, 0, 0.63, 1] as Bezier,
  linear: [0, 0, 1, 1] as Bezier,
} as const;

const loop = { breathePeriodMs: 4000, speakPeriodMs: 1600, shimmerPeriodMs: 1400 } as const;

const level = {
  sampleMs: 100,
  floorDbfs: -50,
  ceilDbfs: -10,
  attack: 0.5,
  release: 0.2,
  step: 0.05,
} as const;

/**
 * The orb: a 40 pt disc in a 48 pt box (the box scales with the patient's
 * text size). The listening halo breathes between `haloOpacity` and
 * `haloBreathLow`; speaking dips the core to `speakOpacityLow`; thinking
 * shimmers the core between the two shimmer values; background work shows a
 * static ring at `workRingOpacity`.
 */
const orb = {
  sizePt: 40,
  boxPt: 48,
  haloOpacity: 0.35,
  haloBreathLow: 0.2,
  speakOpacityLow: 0.75,
  shimmerOpacityLow: 0.55,
  shimmerOpacityHigh: 0.9,
  workRingOpacity: 0.5,
} as const;

/**
 * Press feedback (INT-341, MOTION-12): an instant opacity step, never an
 * animation. `opacity` for buttons, pills and segments; `rowOpacity` for
 * list rows, switch rows and dialogue bubbles; `disabledOpacity` for a
 * control that cannot be pressed, and it stays below both pressed values so
 * a press never reads as the control switching off. The press-retention
 * area is left at the platform default (S-9): no Pressable sets its own.
 */
const press = { opacity: 0.85, rowOpacity: 0.7, disabledOpacity: 0.5 } as const;

export const motion = {
  fadeMs: duration.fade,
  duration,
  easing,
  loop,
  level,
  orb,
  press,
} as const;

/**
 * Row press feedback (INT-451, docs/design/interaction-patterns.md §3.1): a
 * grouped-list row and a switch row show a press by stepping their fill to
 * this token, the way a UIKit cell highlights and a Material 3 list item
 * lays its pressed state over the row. The words stay at full ink. Dimming
 * the whole row to `press.rowOpacity` dimmed the words too, and a sublabel
 * fell to about 3.1:1 while the finger was down (lib/a11y/rowPress.test.ts).
 * It is an instant state swap with no duration, so ADR-033's budget does not
 * apply to it and reduce motion has nothing to collapse.
 */
export const rowPressFill: ColorToken = "surfaceRaised";

/**
 * The platform face. `System` is SF Pro on iOS, which picks the Text or
 * Display optical size and its tracking itself; Android has no family by that
 * name and falls back to its own system sans (Roboto). No face is bundled.
 *
 * `rounded` is SF Pro Rounded, for the one numeral moment a screen may have
 * (the prep gauge), the way Apple's own health and fitness numerals use it.
 * React Native resolves `ui-rounded` to the system rounded design on iOS;
 * Android has none and takes the sans. Themed.tsx picks per platform.
 */
export const fonts = {
  sans: "System",
  rounded: { ios: "ui-rounded", default: "System" },
} as const;

/**
 * Glass fallback (Android, iOS below 26, web): a neutral wash over a real
 * BlurView, plus a separator hairline, in the grouped-background hue. It is
 * chrome only; under Reduce Transparency the surface token replaces it.
 */
export function glassFallback(scheme: ColorScheme): {
  backgroundColor: string;
  borderColor: string;
} {
  return scheme === "dark"
    ? { backgroundColor: "rgba(28, 28, 30, 0.72)", borderColor: "rgba(84, 84, 88, 0.6)" }
    : { backgroundColor: "rgba(249, 249, 249, 0.78)", borderColor: "rgba(60, 60, 67, 0.2)" };
}

/**
 * Apple's Dynamic Type ladder at the default (Large) content size, in points
 * (Human Interface Guidelines, Typography, iOS text styles).
 */
export const textStyles = {
  largeTitle: 34,
  title1: 28,
  title2: 22,
  title3: 20,
  headline: 17,
  body: 17,
  callout: 16,
  subheadline: 15,
  footnote: 13,
  caption1: 12,
  caption2: 11,
} as const;

export type TextStyleName = keyof typeof textStyles;

/**
 * The app's text roles, each one rung of Apple's ladder, and its weight.
 *
 * - `hero`: a screen's own title, Large Title bold.
 * - `question`: the one question on an intake step, Title 2 semibold. It is
 *   a rung below the Large Title on purpose: at the 2.0 cap the longest word
 *   of every question still fits the narrowest iPhone on one line
 *   (e2e/designSystem.spec.ts), where a Large Title would break it mid-word.
 * - `title`: a card or section title, Title 3 semibold.
 * - `body`, `label` (Subheadline), `caption` (Footnote), `micro` (Caption 2,
 *   chrome only: the tab rail's captions).
 * - `display` sits outside the ladder: the one big numeral a screen may
 *   have, in SF Pro Rounded.
 */
export const typeScale = {
  display: 56,
  hero: textStyles.largeTitle,
  question: textStyles.title2,
  title: textStyles.title3,
  body: textStyles.body,
  label: textStyles.subheadline,
  caption: textStyles.footnote,
  micro: textStyles.caption2,
} as const;

export type TypeRole = keyof typeof typeScale;

/**
 * Each role and the rung it takes, as pairs (theme.test.ts proves `typeScale`
 * agrees with them). Pairs rather than an object, so no role name sits beside
 * a string as if it were a prop the i18n scan should read.
 */
export const ROLE_LADDER: readonly (readonly [Exclude<TypeRole, "display">, TextStyleName])[] = [
  ["hero", "largeTitle"],
  ["question", "title2"],
  ["title", "title3"],
  ["body", "body"],
  ["label", "subheadline"],
  ["caption", "footnote"],
  ["micro", "caption2"],
];

export type FontWeight = 400 | 600 | 700;

/** A role's default weight; a caller's own `fontWeight` still wins. */
export const roleWeight: Readonly<Record<TypeRole, FontWeight>> = {
  display: 600,
  hero: 700,
  question: 600,
  title: 600,
  body: 400,
  label: 400,
  caption: 400,
  micro: 400,
};

/**
 * The roles set in SF Pro Rounded on iOS: a screen's own title and the one
 * numeral. Warmth from the face, not from decoration (INT-422).
 */
export const ROUNDED_ROLES: readonly TypeRole[] = ["display", "hero"];

/** The roles set as headings, at the tight leading. */
export const HEADING_ROLES: readonly TypeRole[] = ["display", "hero", "question", "title"];

/**
 * Dynamic type: sizes follow the user's fontScale up to 2.0 (02 §8.2 — full
 * operation at 200 %). The cap is a layout-survival bound, not a comfort
 * preference; screens that cannot survive 2.0 change FORM instead (00 §2),
 * they never clamp text harder.
 *
 * INT-260 corrected the claim that used to sit here. For four design passes
 * this comment named a collapse scale for the tab rail while
 * `FloatingTabBar` contained no scale reference at all — and the number was
 * wrong when something finally rendered against it, because the rail's
 * captions stop fitting one step earlier than it said. The thresholds now
 * live where a test can reach them, as
 * `LARGE_TEXT_SCALE` (1.6, content) and `RAIL_LABEL_MAX_SCALE` (1.2, chrome)
 * in lib/prefs/appearance.ts, and this file states no number it does not own.
 */
function clampScale(fontScale: number): number {
  return Math.max(0.5, Math.min(fontScale, 2.0));
}

export function scaledSize(role: TypeRole, fontScale: number): number {
  return Math.round(typeScale[role] * clampScale(fontScale));
}

/**
 * A CONTROL's dimension at the user's scale — a rail glyph, a switch track,
 * an icon well — under the same clamp as text (INT-260).
 *
 * It exists because of a defect the owner saw on the simulator and named
 * exactly: "navbar and sizes dont match". Every string on the screen had
 * doubled and the tab rail's icons had not, so the chrome read as a different
 * app's navbar pasted under the content. Text and chrome are dimensions in the
 * same coordinate system; they take the same multiplier, from the same clamp,
 * declared once.
 */
export function scaledControl(base: number, fontScale: number): number {
  return Math.round(base * clampScale(fontScale));
}

/**
 * Line height: heading roles sit at 1.2; reading roles keep 1.4, looser than
 * Apple's own body leading, so Turkish diacritics (ğ, ş, İ) stay unclipped
 * and a clinical paragraph keeps its air at every size.
 */
export function lineHeight(role: TypeRole, fontScale: number): number {
  const factor = HEADING_ROLES.includes(role) ? 1.2 : 1.4;
  return Math.round(scaledSize(role, fontScale) * factor);
}
