/**
 * The stage's shapes (ADR-039 S5, INT-466). Controls are capsules, with a
 * radius of half their height, so a control inset in another stays
 * concentric. Cards and messages are 22 pt. shape.test.ts pins both.
 */
import { MIN_TAP } from "@/lib/a11y/target";
import type { OrbState } from "@/lib/motion/orb";

export const STAGE_RADIUS = {
  card: 22,
  message: 22,
} as const;

/** The stage's control heights; each clears the 44 pt floor. */
export const STAGE_SIZE = {
  /** The composer field and its round control. */
  composer: 52,
  /** A turn action (Onaylayın, Bitirdim). */
  action: 52,
  /** An answer card. */
  answer: 52,
  /** The smallest control: a round target. */
  round: MIN_TAP,
} as const;

/** A capsule's corner radius: half its height. */
export function capsule(height: number): number {
  return height / 2;
}

const ORB_SIZE: Record<OrbState, number> = {
  listening: 116,
  speaking: 100,
  thinking: 84,
  idle: 56,
  rest: 56,
  retry: 56,
  hidden: 56,
};

/**
 * The orb's diameter on the stage: largest while the patient talks. It is
 * compact while answer cards are open or the keyboard is up, because then
 * the room belongs to the answer.
 */
export function stageOrbSize(state: OrbState, compact: boolean): number {
  return compact ? ORB_SIZE.idle : ORB_SIZE[state];
}
