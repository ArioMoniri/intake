/**
 * The segmented question capsule (INT-492, GitHub #839), as data.
 *
 * Pure: no react-native import, so lib/intake/progressCapsule.test.ts holds
 * every rule in node. The progress control (components/QuestionProgress.tsx)
 * is its only importer, and e2e/progressMicro.spec.ts keeps it that way: the
 * numerals it formats are display-only and never reach the spoken lane
 * (invariant 22).
 *
 * The owner's reference was spaceui.one; the shape is the section-grouped
 * bar of the best questionnaires on Mobbin (Hers, MyFitnessPal), adapted to
 * the motion rules:
 *
 * - One segment per run of questions from one section of the flow: the HPI
 *   dimensions, medicines and allergies, the history block, the closing
 *   note. Each segment is as wide as its share of the questions, so the
 *   filled length is exactly the old bar's fraction, and a section change is
 *   the next segment becoming the current one.
 * - Done segments are full, the current one is filled up to the question on
 *   screen, upcoming ones are empty. The worded value carries the fact
 *   (SC 1.4.1), so no state is the colour alone.
 * - More sections than the capsule holds fall back to one continuous track.
 * - The count, "Soru 3 / 9", is one non-breaking atom with no grouping
 *   separator. It is only ever shown; the reader hears the worded value
 *   (lib/intake/questionScreen.ts `positionSpoken`).
 *
 * Nothing here animates and nothing here is glass: the intake is a
 * capture-protected screen, so the capsule is solid (INT-477).
 */
import type { ThemeColors } from "../theme";
import type { ProtocolSectionId } from "./questions";
import type { QuestionPosition } from "./questionScreen";

/** One question of the applicable flow, as the capsule reads it. */
export interface CapsuleItem {
  readonly id: string;
  /** The 04 §1 section owning the question; absent = the HPI dimensions. */
  readonly section?: ProtocolSectionId;
}

/** At most this many sections are drawn as segments; more become one track. */
export const MAX_SEGMENTS = 6;

export type SegmentState = "done" | "current" | "upcoming";

export interface CapsuleSegment {
  /** Stable for a flow: the run's place and its section. */
  readonly key: string;
  /** The run's question count: the segment's share of the width. */
  readonly weight: number;
  /** How much of the segment is filled, 0 to 1. */
  readonly fill: number;
  readonly state: SegmentState;
}

export type CapsuleTrack =
  | { readonly kind: "segments"; readonly segments: readonly CapsuleSegment[] }
  | { readonly kind: "continuous"; readonly fraction: number };

interface Run {
  readonly section: string;
  readonly start: number;
  readonly size: number;
}

function runsOf(flow: readonly CapsuleItem[]): Run[] {
  const runs: Run[] = [];
  flow.forEach((q, index) => {
    const section = q.section ?? "hpi";
    const last = runs[runs.length - 1];
    if (last !== undefined && last.section === section) {
      runs[runs.length - 1] = { ...last, size: last.size + 1 };
    } else {
      runs.push({ section, start: index, size: 1 });
    }
  });
  return runs;
}

/**
 * The capsule's track for the question at `position` (from
 * `questionPosition` over the same list), so the two can never disagree
 * about where the patient is.
 */
export function capsuleTrack(
  flow: readonly CapsuleItem[],
  position: QuestionPosition,
): CapsuleTrack {
  const runs = runsOf(flow);
  if (runs.length === 0 || runs.length > MAX_SEGMENTS) {
    return { kind: "continuous", fraction: position.fraction };
  }
  const here = position.position - 1;
  const segments = runs.map((run, index): CapsuleSegment => {
    const key = `${index}:${run.section}`;
    if (run.start + run.size <= here) {
      return { key, weight: run.size, fill: 1, state: "done" };
    }
    if (run.start > here) {
      return { key, weight: run.size, fill: 0, state: "upcoming" };
    }
    return { key, weight: run.size, fill: (here - run.start + 1) / run.size, state: "current" };
  });
  return { kind: "segments", segments };
}

/** U+00A0: the space that never breaks a line. */
export const NBSP = String.fromCharCode(0xa0);

/** An integer as one run of digits: no grouping separator in any locale. */
function digits(n: number): string {
  return Math.trunc(n).toString(10);
}

/** "Soru 3 / 9", one non-breaking atom. Display-only (invariant 22). */
export function capsuleCount(position: QuestionPosition, word: string): string {
  return [word, digits(position.position), "/", digits(position.total)].join(NBSP);
}

/**
 * The count in two weights: the word and the position in the label colour,
 * "/ M" in the secondary one. The cut sits before a non-breaking space, so
 * the two halves still never part.
 */
export function countParts(count: string): { readonly head: string; readonly tail: string } {
  const cut = count.lastIndexOf(`${NBSP}/${NBSP}`);
  return cut < 0
    ? { head: count, tail: "" }
    : { head: count.slice(0, cut), tail: count.slice(cut) };
}

/** The capsule's paint: opaque theme colours only, never a material. */
export interface CapsuleChrome {
  /** The capsule itself, on the screen's grouped background. */
  readonly ground: string;
  /** An upcoming segment, and the unfilled part of the current one. */
  readonly track: string;
  /** A done segment, and the filled part of the current one. */
  readonly fill: string;
  /** The ground behind the count. */
  readonly countFill: string;
  /** The word and the position. */
  readonly countInk: string;
  /** "/ M". */
  readonly countSoft: string;
}

export function capsuleChrome(colors: ThemeColors): CapsuleChrome {
  return {
    ground: colors.surface,
    track: colors.surfaceRaised,
    fill: colors.primary,
    countFill: colors.surface,
    countInk: colors.ink,
    countSoft: colors.inkSoft,
  };
}
