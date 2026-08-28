/**
 * Vizite design tokens (INT-130, premium pass INT-193;
 * docs/design/mobile-ui.md).
 *
 * Calm dark-on-light (02 §5.2): warm paper ground, deep ink, ONE accent.
 * The premium register (Oura/Tiimo/ChatGPT study): serif display for hero
 * moments, deeper near-black dark mode with tonal card separation, soft
 * large radii, Liquid Glass surfaces where the system provides them.
 * RED is reserved for the emergency route alone — nothing else in the app
 * may use it (02 §5.3). Motion budget: 120 ms fades, one animated element
 * at a time (02 §5.2a) — tokens carry the number so nobody re-invents it.
 *
 * Turkish rules baked in (00 §2): no text-transform anywhere (İ/ı casing
 * corrupts strings), no mid-word truncation, sentence case only.
 *
 * Pure TS module — no react-native imports, so every token and the type
 * scale are unit-testable in node. Platform resolution (fonts, shadows)
 * happens in components/Themed.tsx.
 */

export const palette = {
  light: {
    background: "#FAF8F4", // warm paper (Pi/Tiimo-class calm, not clinical white)
    surface: "#FFFFFF",
    // One tonal step ABOVE surface (design pass 5): leading icon wells,
    // tonal chips and off-state pills — the Oura "raised" grey that replaces
    // outlines in the tag register.
    surfaceRaised: "#F1EDE4",
    ink: "#1C1B18",
    inkSoft: "#5C594F",
    inkFaint: "#8A867A",
    border: "#EAE6DD",
    primary: "#0F7B6C", // şifa teal — the single accent
    primarySoft: "#EAF5F2", // light enough that primary text on it clears AA (4.6:1)
    onPrimary: "#FFFFFF",
    amber: "#9A5B00", // YELLOW status pill only
    amberSoft: "#FBF1DF",
    success: "#1B7F4B",
    successSoft: "#E4F2EA",
    emergency: "#B3261E", // RESERVED: RED route (ALERT register) only
    emergencySoft: "#F9E5E3",
  },
  dark: {
    background: "#0F0E0C", // Oura-register near-black with warmth
    surface: "#211F1B", // a full step lighter than ground — cards must separate
    surfaceRaised: "#2B2823", // one more tonal step for chips/icon wells

    ink: "#F2F0EA",
    inkSoft: "#B7B3A7",
    inkFaint: "#8A867A",
    border: "#353128",
    primary: "#4FA79A",
    primarySoft: "#22322F",
    onPrimary: "#10201D",
    amber: "#E0A34E",
    amberSoft: "#332A1C",
    success: "#5CB884",
    successSoft: "#1E2E25",
    emergency: "#E5756D",
    emergencySoft: "#392320",
  },
} as const;

export type ColorScheme = keyof typeof palette;
export type ThemeColors = (typeof palette)[ColorScheme];

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, screen: 20 } as const;

/**
 * Softer, larger geometry; CTAs are full pills. Design pass 4 (measured
 * against Mobbin Oura captures): cards 24, hero surfaces 32 — Oura's dark
 * cards are visibly rounder than our pass-3 20/28.
 */
/**
 * `group` (design pass 5): grouped list containers — Oura's settings and
 * contributor groups sit visibly squarer (~16) than its content cards; one
 * radius for every ListGroup so rows read as a table, not a card stack.
 */
export const radius = { card: 24, control: 999, hero: 32, chip: 999, group: 16 } as const;

/** Motion budget (02 §5.2a): fades only, and only this long. */
export const motion = { fadeMs: 120 } as const;

/**
 * Display face: Newsreader (OFL 1.1 — commercially usable; loaded as an app
 * asset via @expo-google-fonts/newsreader in the root layout) for hero/title
 * lines — the Oura-register soft serif. Body stays system sans. Platform
 * serif names remain as the pre-load fallback chain.
 */
export const fonts = {
  /**
   * Design pass 5: 600 read one register heavier than the Oura headline
   * serif (a bookish regular-to-medium); 500 at display sizes matches the
   * reference weight without thinning small titles.
   */
  display: "Newsreader_500Medium",
  displayFallback: { ios: "Georgia", android: "serif", default: "serif" },
  /**
   * Body sans: Inter (OFL 1.1 — commercially usable; loaded via
   * @expo-google-fonts/inter in the root layout). Design pass 4: Oura's UI
   * sans is Inter-class — rounder apertures and a taller x-height than the
   * platform faces — so body/label/caption roles carry it explicitly.
   * Weights are separate loaded families; Themed.tsx maps fontWeight →
   * family (custom fonts on iOS do not synthesize weights reliably).
   */
  sans: "Inter_400Regular",
  sansMedium: "Inter_500Medium",
  sansSemiBold: "Inter_600SemiBold",
} as const;

/**
 * Depth: light mode floats cards on a soft, wide shadow; dark mode relies
 * on tonal separation like Oura (shadows read as mud on near-black).
 */
export const shadow = {
  light: { color: "#1C1B18", opacity: 0.07, radius: 18, offsetY: 8 },
  dark: { color: "#000000", opacity: 0, radius: 0, offsetY: 0 },
} as const;

/**
 * Glass fallback (Android, iOS < 26, web): a soft tint wash laid OVER a real
 * BlurView plus a hairline border — the closest honest approximation of the
 * system material (design pass 3: the wash alone read as flat plastic; the
 * blur underneath is what makes it glass). Alphas are low because the blur
 * carries most of the separation.
 */
export function glassFallback(scheme: ColorScheme): {
  backgroundColor: string;
  borderColor: string;
} {
  return scheme === "dark"
    ? { backgroundColor: "rgba(33, 31, 27, 0.45)", borderColor: "rgba(242, 240, 234, 0.10)" }
    : { backgroundColor: "rgba(255, 255, 255, 0.42)", borderColor: "rgba(28, 27, 24, 0.08)" };
}

/**
 * Letter tracking (design pass 3, Oura register): kickers/eyebrows breathe
 * with a wide caption; everything else stays untracked. Never pair this with
 * a case transform (İ/ı rule) — the tracking IS the emphasis. Pass 4 widened
 * 0.5 → 0.8 against the Mobbin captures: Oura's smallcaps eyebrows track
 * wider than our pass-3 pills read.
 */
export const tracking = { kicker: 0.8 } as const;

/**
 * Base sizes at fontScale 1.0. Body 17 matches the platform default.
 * `display` (design pass 5): the one big-numeral moment a screen may have —
 * Oura's score numerals sit around 64 pt; 56 keeps the register while
 * surviving fontScale 2.0. `micro` is chrome-only (tab rail captions): Oura
 * rail labels measure ~11; never use it for reading text.
 */
export const typeScale = {
  display: 56,
  hero: 34,
  title: 24,
  body: 17,
  label: 15,
  caption: 13,
  micro: 11,
} as const;

export type TypeRole = keyof typeof typeScale;

/**
 * Dynamic type: sizes follow the user's fontScale up to 2.0 (02 §8.2 — full
 * operation at 200 %). The cap is a layout-survival bound, not a comfort
 * preference; screens that cannot survive 2.0 change FORM instead (the rail
 * collapses at ≥1.6 — 00 §2), they never clamp text harder.
 */
export function scaledSize(role: TypeRole, fontScale: number): number {
  const clamped = Math.max(0.5, Math.min(fontScale, 2.0));
  return Math.round(typeScale[role] * clamped);
}

/**
 * Line height: display roles (hero/title) sit tight at 1.2 — the Oura serif
 * register collapses at book leading (design pass 3) — while body roles keep
 * 1.4 so Turkish diacritics (ğ, ş, İ) stay unclipped at reading sizes. 1.2
 * still clears the diacritics at display sizes because the glyphs are large.
 */
export function lineHeight(role: TypeRole, fontScale: number): number {
  const factor = role === "display" || role === "hero" || role === "title" ? 1.2 : 1.4;
  return Math.round(scaledSize(role, fontScale) * factor);
}
