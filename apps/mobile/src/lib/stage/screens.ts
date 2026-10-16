/**
 * The still stage on the remaining screens (ADR-039 amendment, INT-499,
 * GitHub #849): the visits list, documents, the share centre and settings
 * take the stage's visual language as welcome and sign-in did (S7), with the
 * Liquid Glass split Apple asks for (docs/design/liquid-glass-research.md).
 *
 * - **Glass is for the controls.** A screen's page actions are stage
 *   capsules; they may be Liquid Glass, regular and inert. Lists, cards and
 *   rows are content and always solid.
 * - **Capture-protected screens are solid** (INT-477, owner: "solid").
 *   Documents and the share centre hold INT-131's capture protection, so they
 *   never mount glass or the wash, whatever the OS offers.
 * - **Reduce Transparency and Increase Contrast are solid.** No system glass
 *   means solid stage fills, never a blur; Increase Contrast keeps the wash
 *   (held to AA in screens.test.ts) and draws the actions solid, with the
 *   stage card's boundary.
 * - **Nothing moves.** These screens add no motion, so Reduce Motion has
 *   nothing to still.
 *
 * Pure, so the whole policy is node-testable. The device half is
 * components/stage/useStageScreen.ts and components/stage/StageSurface.tsx.
 */
import type { GlassMode } from "../a11y/glass";

import { withSolidStageBar, type SolidStageBar } from "./nav";
import type { StagePalette } from "./palette";
import { STAGE_RADIUS } from "./shape";

export type StageScreen = "visits" | "records" | "shares" | "settings";

export interface StageScreenSpec {
  /** The route, named by its path under `src/app` without the extension. */
  readonly route: string;
  /** The screen holds INT-131's capture protection, so it is solid (INT-477). */
  readonly captureProtected: boolean;
}

/**
 * The four screens. e2e/stageScreens.spec.ts checks `captureProtected`
 * against the source: it is true exactly where the route's file calls
 * `useClinicalScreenPrivacy()`.
 */
export const STAGE_SCREENS: Readonly<Record<StageScreen, StageScreenSpec>> = {
  visits: { route: "(tabs)/visits/index", captureProtected: false },
  records: { route: "(tabs)/records", captureProtected: true },
  shares: { route: "(tabs)/visits/[visitId]/shares", captureProtected: true },
  settings: { route: "(tabs)/me/index", captureProtected: false },
};

export interface StageScreenInputs {
  /** The live material answer (lib/a11y/glass `glassMode`). */
  readonly mode: GlassMode;
  readonly captureProtected: boolean;
  /** The OS Increase Contrast request. */
  readonly increasedContrast: boolean;
}

export interface StageScreenChrome {
  /** The page actions may be Liquid Glass. */
  readonly glass: boolean;
  /** The still wash is drawn behind the screen. */
  readonly backdrop: boolean;
  /** The palette resolves as Reduce Transparency resolves it: a flat base. */
  readonly flat: boolean;
}

export function stageScreenChrome({
  mode,
  captureProtected,
  increasedContrast,
}: StageScreenInputs): StageScreenChrome {
  const flat = captureProtected || mode !== "liquid";
  return { glass: !flat && !increasedContrast, backdrop: !flat, flat };
}

/** What content sits on: the solid stage card at the stage corner. */
export interface StageSurface {
  readonly card: string;
  /** ADR-039 S5: stage cards are 22 pt. */
  readonly corner: number;
  /** A card's boundary, under Increase Contrast only (ADR-039 S6). */
  readonly border: string | null;
}

export function stageSurface(palette: StagePalette): StageSurface {
  return { card: palette.card, corner: STAGE_RADIUS.card, border: palette.cardBorder };
}

const NO_SCROLL_EDGE = {
  top: "hidden",
  bottom: "hidden",
  left: "hidden",
  right: "hidden",
} as const;

export interface ProtectedStageBar extends SolidStageBar {
  readonly scrollEdgeEffects: typeof NO_SCROLL_EDGE;
}

/**
 * A capture-protected pushed screen's bar (the share centre): the sign-in
 * screens' solid stage bar, in the flat base, with only the back chevron;
 * the title is the large title in the content. INT-477 asks for no system
 * chrome material and no scroll-edge effect, so every edge is hidden.
 */
export function withProtectedStageBar<T extends object>(
  options: T,
  palette: StagePalette,
): T & ProtectedStageBar {
  return { ...withSolidStageBar(options, palette), scrollEdgeEffects: NO_SCROLL_EDGE };
}
