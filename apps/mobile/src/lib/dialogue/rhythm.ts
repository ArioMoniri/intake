/**
 * The conversation's rhythm (INT-423, docs/design/chat-rhythm.md): how the
 * transcript groups consecutive turns and how wide a bubble may run. Pure, so
 * the rules are node-testable; components/DialogueIntake.tsx renders them.
 *
 * - Turns from one speaker in a row sit together, 4 pt apart, and only the
 *   last of the run carries the tail corner, as Messages draws a group. A
 *   change of speaker opens the full 16 pt turn gap. The grouping is the
 *   rhythm a reader sees; who spoke is still said in each bubble's own
 *   accessible name, never by position alone.
 * - A bubble takes 84 % of the transcript, so the two speakers keep their
 *   sides, and never more than 560 pt, about 70 characters of body text, so a
 *   landscape window does not stretch a line past a readable measure.
 * - From the large-text scale up, a bubble takes the whole width: at an
 *   accessibility size a long Turkish word needs every point, and breaking it
 *   inside itself is the defect 00 §2 forbids.
 */
import { isLargeText } from "@/lib/prefs/appearance";
import { spacing } from "@/lib/theme";

import type { StreamEntry } from "./stream";

export type Side = "agent" | "patient";

/** The space between two speakers' turns: the transcript's own gap. */
export const TURN_GAP = spacing.md;

/** The space between two turns from one speaker. */
export const GROUP_GAP = spacing.xs;

/** The margin that pulls a grouped bubble up from the transcript's gap. */
export const GROUPED_MARGIN = GROUP_GAP - TURN_GAP;

/** A bubble's share of the transcript's width, below the large-text scale. */
export const BUBBLE_SHARE = 0.84;

/** The longest a bubble's line may run, in points. */
export const MEASURE_MAX = 560;

export interface TurnPlacement {
  /** The turn follows one from the same speaker. */
  readonly grouped: boolean;
  /** The turn ends its speaker's run, so it carries the tail corner. */
  readonly tail: boolean;
}

export function sideOf(entry: StreamEntry): Side {
  return entry.kind === "patient" ? "patient" : "agent";
}

export function placeTurns(sides: readonly Side[]): TurnPlacement[] {
  return sides.map((side, index) => ({
    grouped: index > 0 && sides[index - 1] === side,
    tail: sides[index + 1] !== side,
  }));
}

export function bubbleMaxWidth(contentWidth: number, fontScale: number): number {
  if (isLargeText(fontScale)) {
    return contentWidth;
  }
  return Math.min(Math.round(contentWidth * BUBBLE_SHARE), MEASURE_MAX);
}
