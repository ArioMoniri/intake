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

/** The line under the staff control for each phase of its press (INT-602 round 1). */
export interface StaffCallLine {
  readonly key: "red.callStaff.sending" | "red.callStaff.sent" | "red.callStaff.failed";
  readonly tone: "status" | "error";
}

/**
 * What the patient reads about their press. Never silent once pressed:
 * `sending` is neutral, `sent` exists only for a confirmed send, and `failed`
 * says to ask a staff member or go to the emergency department. `idle` shows
 * nothing, so nothing claims a notification before the patient acts.
 */
export function staffCallLine(phase: "idle" | "sending" | "sent" | "failed"): StaffCallLine | null {
  switch (phase) {
    case "idle":
      return null;
    case "sending":
      return { key: "red.callStaff.sending", tone: "status" };
    case "sent":
      return { key: "red.callStaff.sent", tone: "status" };
    case "failed":
      return { key: "red.callStaff.failed", tone: "error" };
  }
}

/**
 * The quieter control on the layer (INT-602 owner decision 1): the staff notify
 * control when "Acil Servis'e gidin" leads. A 44 pt target with a body-weight
 * label, below the primary control's 56 pt and 17 pt semibold, and a 1.5 pt
 * outline so its edge still clears 3:1 on every RED ground. Never the
 * emergency colour.
 */
export function redSecondaryControl(colors: ThemeColors): RedControlLook {
  return {
    minHeight: MIN_TAP,
    labelRole: "label",
    labelWeight: "600",
    backgroundColor: colors.surface,
    borderColor: colors.inkSoft,
    borderWidth: 1.5,
    labelColor: colors.ink,
  };
}

/** One ON_SITE control, in the order it is drawn. */
export interface OnSiteControl {
  readonly kind: "goToAcil" | "notifyStaff";
  readonly weight: "primary" | "secondary";
}

/**
 * The ON_SITE controls, top first (owner decision 1, 17 Nov 2026: "give the
 * button of acil servise gidin"). Where the pack's ON_SITE action is
 * GO_TO_IN_HOUSE_ACIL, "Acil Servis'e gidin" is the primary control and the
 * staff control follows as the secondary one. Any other ON_SITE action fails
 * closed to the staff control alone, as the primary. Nothing under REMOTE.
 */
export function redOnSiteControls(screen: {
  readonly callStaff: boolean;
  readonly goToAcil: boolean;
}): readonly OnSiteControl[] {
  if (!screen.callStaff) {
    return [];
  }
  if (screen.goToAcil) {
    return [
      { kind: "goToAcil", weight: "primary" },
      { kind: "notifyStaff", weight: "secondary" },
    ];
  }
  return [{ kind: "notifyStaff", weight: "primary" }];
}
