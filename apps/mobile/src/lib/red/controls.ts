/**
 * The RED layer's controls and frame (INT-602; CLAUDE.md invariants 21 and the
 * RED patient-copy rule; files/02 §5.3; ADR-033 via lib/motion/red.ts;
 * docs/design/audit-2026-11 Part B R1, R2, R4, R6).
 *
 * Pure: no React Native import, so every register × scheme is node-testable,
 * and RedLayer.tsx spreads these answers instead of writing its own.
 *
 * - **The patient's control is the strongest one on the layer** (R1). The 112
 *   control, and under ON_SITE the staff control in its place, are at least the
 *   app's primary CTA: `CTA_MIN_HEIGHT` with a body-size semibold label
 *   (components/Themed.tsx `PrimaryButton`). The location answers stay 44 pt.
 * - **It has a visible edge in every register** (R2; WCAG 1.4.11). ALERT keeps
 *   the reserved emergency fill. CALM and SILENT take the neutral `cta` pill —
 *   never the emergency colour, because CALM has "no red, no alarm colour" and
 *   SILENT "no colour change" (files/02 §5.3).
 * - **Pressing it shows at once** (R6): the INT-341 opacity step. Not motion,
 *   and no haptic (ADR-033 Q2's fail-closed default: none for any register).
 * - **The layer clears every safe-area edge** (R4), with no SafeAreaView
 *   animation; with no insets the geometry is what it was before.
 */
import { MIN_TAP } from "../a11y/target";
import type { RedRegister } from "../livekit/red";
import { CTA_MIN_HEIGHT } from "../prefs/appearance";
import { motion, spacing, type ThemeColors, type TypeRole } from "../theme";

/** Re-exported so the layer types its control without importing the livekit module. */
export type { RedRegister };

/** The registers a patient is shown: DEFERRED_CLINICIAN changes nothing on screen. */
export type ShownRegister = Exclude<RedRegister, "DEFERRED_CLINICIAN">;

/** The ground a RED's body sits on. SILENT sits in the flow, on the screen's own. */
export function redWash(register: ShownRegister, colors: ThemeColors): string {
  switch (register) {
    case "ALERT":
      return colors.emergencySoft;
    case "CALM":
      return colors.amberSoft;
    case "SILENT":
      return colors.background;
  }
}

export interface RedControlLook {
  readonly minHeight: number;
  readonly labelRole: TypeRole;
  readonly labelWeight: "600";
  readonly backgroundColor: string;
  readonly borderColor: string;
  readonly borderWidth: number;
  readonly labelColor: string;
}

/**
 * The 112 control, or the staff control under ON_SITE: never weaker than the CTA.
 * ALERT is the one register with the emergency fill; every other shown register
 * takes the neutral pill. (DEFERRED_CLINICIAN renders no control at all.)
 */
export function redPrimaryControl(register: RedRegister, colors: ThemeColors): RedControlLook {
  const fill = register === "ALERT" ? colors.emergency : colors.cta;
  return {
    minHeight: CTA_MIN_HEIGHT,
    labelRole: "body",
    labelWeight: "600",
    backgroundColor: fill,
    borderColor: fill,
    borderWidth: 0,
    labelColor: register === "ALERT" ? colors.onPrimary : colors.onCta,
  };
}

/** The colour that draws the control's edge against the wash: its border, or its fill. */
export function redControlBoundary(look: RedControlLook): string {
  return look.borderWidth > 0 ? look.borderColor : look.backgroundColor;
}

/** The location answers (Evet / Hayır): a 44 pt target, below the primary control. */
export const RED_SECONDARY_CONTROL = { minHeight: MIN_TAP, labelRole: "label" } as const;

/** Pressed feedback: an instant opacity step (INT-341), never an animation. */
export function redPressedOpacity(pressed: boolean): number {
  return pressed ? motion.press.opacity : 1;
}

/**
 * Open the dialer; if it cannot open, show the number instead. `open` is the
 * caller's `Linking.openURL(tel:…)`. Nothing waits on it: the screen already
 * shows the number as selectable text, and a failure adds the fallback line.
 */
export function callOrShowNumber(open: () => Promise<unknown>, showNumber: () => void): void {
  try {
    open().catch(showNumber);
  } catch {
    showNumber();
  }
}

export interface Insets {
  readonly top: number;
  readonly right: number;
  readonly bottom: number;
  readonly left: number;
}

export interface RedLayerFrame {
  /** The register band at the top, which also covers the status bar or cutout. */
  readonly bandHeight: number;
  /** The scrolling body's padding: every edge clears its inset. */
  readonly padding: Insets;
}

/** The root layer's frame for these safe-area insets. */
export function redLayerFrame(insets: Insets): RedLayerFrame {
  return {
    bandHeight: Math.max(spacing.xl * 2, insets.top + spacing.md),
    padding: {
      top: spacing.xl,
      right: spacing.screen + insets.right,
      bottom: spacing.screen + insets.bottom,
      left: spacing.screen + insets.left,
    },
  };
}
