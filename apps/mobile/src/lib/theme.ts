/**
 * Vizite design tokens (INT-130; docs/design/mobile-ui.md).
 *
 * Calm dark-on-light (02 §5.2): warm paper ground, deep ink, ONE accent.
 * RED is reserved for the emergency route alone — nothing else in the app may
 * use it (02 §5.3). Motion budget: 120 ms fades, one animated element at a
 * time (02 §5.2a) — tokens carry the number so nobody re-invents it.
 *
 * Turkish rules baked in (00 §2): no text-transform anywhere (İ/ı casing
 * corrupts strings), no mid-word truncation, sentence case only.
 *
 * Pure TS module — no react-native imports, so every token and the type scale
 * are unit-testable in node.
 */

export const palette = {
  light: {
    background: "#FAF8F4", // warm paper (Pi-class calm, not clinical white)
    surface: "#FFFFFF",
    ink: "#1C1B18",
    inkSoft: "#5C594F",
    inkFaint: "#8A867A",
    border: "#E7E3DA",
    primary: "#0F7B6C", // şifa teal — the single accent
    primarySoft: "#E3F0ED",
    onPrimary: "#FFFFFF",
    amber: "#9A5B00", // YELLOW status pill only
    amberSoft: "#FBF1DF",
    success: "#1B7F4B",
    successSoft: "#E4F2EA",
    emergency: "#B3261E", // RESERVED: RED route (ALERT register) only
    emergencySoft: "#F9E5E3",
  },
  dark: {
    background: "#171613",
    surface: "#201F1B",
    ink: "#F2F0EA",
    inkSoft: "#B7B3A7",
    inkFaint: "#8A867A",
    border: "#33312B",
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

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32 } as const;
export const radius = { card: 16, control: 12, chip: 999 } as const;

/** Motion budget (02 §5.2a): fades only, and only this long. */
export const motion = { fadeMs: 120 } as const;

/** Base sizes at fontScale 1.0. Body 17 matches the platform default. */
export const typeScale = {
  hero: 28,
  title: 22,
  body: 17,
  label: 15,
  caption: 13,
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

/** Line height keeps Turkish diacritics (ğ, ş, İ) unclipped. */
export function lineHeight(role: TypeRole, fontScale: number): number {
  return Math.round(scaledSize(role, fontScale) * 1.4);
}
