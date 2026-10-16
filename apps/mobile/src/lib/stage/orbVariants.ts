/**
 * The stage orb's body (INT-491, GitHub #838; ADR-039 amendment, owner,
 * 16 Oct 2026: "orb=lens").
 *
 * The owner asked for the orb to be explored against spaceui.one and the
 * voice orbs of Siri, ChatGPT and Gemini, and chose the refined glass lens: a
 * deep sphere lit from the top left, a darker rim, a light that travels round
 * the rim and a fainter, slower one, a crisp edge, and the clear lens over it.
 * The blob and the particle field the exploration also built are not shipped.
 *
 * Nothing here decides a state or a speed. The plan is built from the S1
 * motion (`stageOrbMotion`, ADR-039), so whatever that motion keeps still
 * (idle, rest, retry, Reduce Motion, a RED) the lens keeps still, and
 * whatever bound it keeps (breath ≤ 1.06×, swell ≤ +10 %, no breath under
 * 1.2 s, no turn under 3 s) the lens keeps too. Its two rim lights turn the
 * same way, as the sphere's layers now do, so their pattern repeats below
 * the band S1 cites from Apple.
 *
 * `classic` names the earlier sphere. Only a development or preview build
 * can name it (app.config.ts): unset, empty or unknown is the lens.
 *
 * Pure: no React Native, Expo or Reanimated import, so node tests hold it.
 * The drawing is components/stage/VoiceOrb.ios.tsx.
 */
import { STAGE_ORB_SECOND_LAYER, type StageOrbMotion } from "./orb";

export const ORB_VARIANTS = ["lens", "classic"] as const;
export type OrbVariant = (typeof ORB_VARIANTS)[number];

/** The orb ADR-039 names: the lens. */
export const ORB_VARIANT_DEFAULT = "lens" satisfies OrbVariant;

/** The flag's value as a body; anything unknown is the lens. */
export function orbVariantFrom(value: unknown): OrbVariant {
  if (typeof value !== "string") {
    return ORB_VARIANT_DEFAULT;
  }
  const name = value.trim().toLowerCase();
  return ORB_VARIANTS.find((variant) => variant === name) ?? ORB_VARIANT_DEFAULT;
}

/** One full turn of a rim light, clockwise. */
export interface Turn {
  readonly periodS: number;
}

export interface LensPlan {
  readonly visible: boolean;
  /** The light that travels round the rim; null is still. */
  readonly sweep: Turn | null;
  /** A fainter, slower light, the same way, so the rim never shows one fixed band. */
  readonly caustic: Turn | null;
  /** The crisp edge, as a fraction of the size. */
  readonly rim: number;
  /** The S1 breath, passed through; null is still. */
  readonly breathe: StageOrbMotion["breathe"];
  /** The S1 voice gain, passed through (PresenceOrb applies it). */
  readonly levelGain: number;
  readonly glowOpacity: number;
  /** The clear Liquid Glass lens: only where glass is drawn at all. */
  readonly lens: boolean;
}

function turnOf(periodS: number | null, factor: number): Turn | null {
  return periodS === null ? null : { periodS: periodS * factor };
}

/**
 * The lens for this motion. The motion is the S1 policy's answer for
 * `orbStateFor`'s state; `glass` is false under Reduce Transparency and on a
 * capture-protected screen, where nothing is glass.
 */
export function lensPlan(motion: StageOrbMotion, surface: { readonly glass: boolean }): LensPlan {
  return {
    visible: motion.visible,
    sweep: turnOf(motion.rotationPeriodS, 1),
    caustic: turnOf(motion.rotationPeriodS, STAGE_ORB_SECOND_LAYER.periodFactor),
    rim: 0.012,
    breathe: motion.breathe,
    levelGain: motion.levelGain,
    glowOpacity: motion.glowOpacity,
    lens: surface.glass,
  };
}

/** Every turning light of a plan; empty when the lens is still. */
export function lensTurns(plan: LensPlan): Turn[] {
  return [plan.sweep, plan.caustic].filter((turn): turn is Turn => turn !== null);
}
