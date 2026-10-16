/**
 * The conversation stage's palette (chat redesign prototype; owner feedback on
 * PR #792, 3 Oct 2026: "modern, dynamic, like a health app such as Oura").
 *
 * The stage is a full-bleed ambient backdrop: a calm vertical wash with a soft
 * light behind the voice orb. Text sits on it directly, so palette.test.ts
 * holds every text colour to AA against every stop of the wash. Answer cards
 * are solid: content stays on solid fills and glass is for chrome only.
 *
 * - light, "morning": a warm mist with the app's teal;
 * - dark, "night": a deep teal-ink, never pure black, with warm white text.
 *
 * Reduce Transparency flattens the wash to the base and drops the glow.
 * Increase Contrast strengthens the secondary ink and gives cards a boundary.
 */
export type StageScheme = "light" | "dark";

export interface StageModes {
  readonly reduceTransparency: boolean;
  readonly increasedContrast: boolean;
}

export interface StagePalette {
  /** The solid ground: the whole stage under Reduce Transparency. */
  readonly base: string;
  /** The backdrop's vertical wash, top → middle → bottom. */
  readonly wash: readonly [string, string, string];
  /** The soft light behind the orb; null when transparency is reduced. */
  readonly glow: string | null;
  readonly ink: string;
  readonly inkSoft: string;
  readonly accent: string;
  /** A solid answer card, its selected fill and the text on that fill. */
  readonly card: string;
  readonly cardSelected: string;
  readonly cardInkSelected: string;
  /** A card's boundary, under Increase Contrast only. */
  readonly cardBorder: string | null;
  /**
   * A text field's fill (ADR-039 S7). A field has no resting outline, so its
   * fill must stand apart from the wash; the dark answer card does not.
   */
  readonly field: string;
  /** The voice orb's angular gradient stops. */
  readonly orb: readonly [string, string, string, string, string];
  /**
   * The floor a glass control's label is held to: system regular glass is
   * modelled as this veil over the wash (palette.test.ts). Under Reduce
   * Transparency the control is the solid `card` instead.
   */
  readonly controlVeil: { readonly color: string; readonly alpha: number };
}

const LIGHT = {
  base: "#F4F1EB",
  wash: ["#E3EEEA", "#F4F1EB", "#F2ECE3"],
  glow: "#8FD3C5",
  ink: "#0E1A19",
  inkSoft: "#4A5654",
  inkSoftHigh: "#2B3634",
  accent: "#0B7366",
  card: "#FFFFFF",
  cardSelected: "#0B7366",
  cardInkSelected: "#FFFFFF",
  cardBorder: "#5F6B69",
  field: "#FFFFFF",
  orb: ["#0B7366", "#3CB8A6", "#5DAEE6", "#C3EFE6", "#0B7366"],
  controlVeil: { color: "#FFFFFF", alpha: 0.55 },
} as const;

const DARK = {
  base: "#0A1213",
  wash: ["#14302F", "#0A1213", "#05090A"],
  glow: "#2E9C8C",
  ink: "#F3EFE7",
  inkSoft: "#A9B5B3",
  inkSoftHigh: "#D3DBD9",
  accent: "#7DDCCB",
  card: "#152123",
  cardSelected: "#7DDCCB",
  cardInkSelected: "#04201C",
  cardBorder: "#8C9997",
  field: "#2C4244",
  orb: ["#1F8F80", "#7DDCCB", "#6FB4F0", "#D8F5EF", "#1F8F80"],
  controlVeil: { color: "#2C2C2E", alpha: 0.55 },
} as const;

export function stagePalette(scheme: StageScheme, modes: StageModes): StagePalette {
  const p = scheme === "dark" ? DARK : LIGHT;
  return {
    base: p.base,
    wash: modes.reduceTransparency ? [p.base, p.base, p.base] : p.wash,
    glow: modes.reduceTransparency ? null : p.glow,
    ink: p.ink,
    inkSoft: modes.increasedContrast ? p.inkSoftHigh : p.inkSoft,
    accent: p.accent,
    card: p.card,
    cardSelected: p.cardSelected,
    cardInkSelected: p.cardInkSelected,
    cardBorder: modes.increasedContrast ? p.cardBorder : null,
    field: p.field,
    orb: p.orb,
    controlVeil: p.controlVeil,
  };
}
