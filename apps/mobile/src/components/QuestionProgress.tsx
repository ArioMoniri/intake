/**
 * The typed intake's progress: the "Soru N / M" count in a solid segmented
 * capsule (INT-492; owner, 16 Oct 2026). It replaced INT-433's thin bar and
 * line, which had replaced a row of one dot per question.
 *
 * - One element for assistive technology: a `progressbar` whose value is the
 *   worded "Soru 3, toplam 9". The segments are the sighted cue; the value is
 *   the fact (SC 1.4.1), so nothing is carried by the hue alone. No part of
 *   the capsule is read on its own, and nothing in it announces itself.
 * - One segment per section of the flow, each as wide as its share of the
 *   questions (lib/intake/progressCapsule.ts), so the filled length is the
 *   old bar's fraction and a section change is the next segment becoming
 *   current.
 * - The numerals are display-only (invariant 22): one non-breaking atom with
 *   no grouping separator, formatted by lib/intake/progressCapsule.ts, and
 *   this control is mounted by the typed screen alone; the spoken lane never
 *   imports either.
 * - Nothing moves. The capsule swaps with the step, instantly: the question's
 *   120 ms fade is the step's one animated element (ADR-033 §2).
 * - Solid: the intake is capture-protected (INT-477), so the capsule is an
 *   opaque theme fill, never a material.
 * - M is the applicable count, never the pack's length, and while a gate can
 *   still open, the growth line is shown under it, outside the progressbar so
 *   a reader hears it too.
 * - The count sits beside the segments at the everyday sizes and moves under
 *   them at the largest steps, so neither is squeezed and nothing is clipped
 *   (e2e/overflow.spec.ts).
 */
import { StyleSheet, View } from "react-native";

import { AppText, useFontScale, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import {
  capsuleChrome,
  capsuleCount,
  capsuleTrack,
  countParts,
  type CapsuleChrome,
  type CapsuleItem,
} from "@/lib/intake/progressCapsule";
import { positionSpoken, type QuestionPosition } from "@/lib/intake/questionScreen";
import { radius, spacing } from "@/lib/theme";

export function QuestionProgress({
  position,
  flow,
}: {
  position: QuestionPosition;
  /** The pack layer's applicable list, the same one `position` came from. */
  flow: readonly CapsuleItem[];
}) {
  const word = t("intake.progress.question");
  return (
    <View style={styles.column}>
      <View
        accessible
        accessibilityRole="progressbar"
        accessibilityLabel={t("intake.progress.name")}
        accessibilityValue={{
          min: 1,
          max: position.total,
          now: position.position,
          text: positionSpoken(position, word, t("intake.progress.of")),
        }}
      >
        <CapsuleBody position={position} flow={flow} word={word} />
      </View>
      {position.mayGrow ? (
        <AppText role="caption" color="inkFaint">
          {t("intake.progress.grows")}
        </AppText>
      ) : null}
    </View>
  );
}

/**
 * At this text scale and above the count moves under the segments, so
 * neither is squeezed (the largest steps of Dynamic Type).
 */
const STACK_AT = 1.35;

/** A segment's height: a bar a little bolder than the old hairline. */
const SEGMENT = 6;

/** The narrowest a one-question segment draws, so it is never a sliver. */
const SEGMENT_MIN = 8;

function CapsuleBody({
  position,
  flow,
  word,
}: {
  position: QuestionPosition;
  flow: readonly CapsuleItem[];
  word: string;
}) {
  const theme = useTheme();
  const stacked = useFontScale() >= STACK_AT;
  const chrome = capsuleChrome(theme);
  const track = capsuleTrack(flow, position);
  return (
    <View
      style={[
        styles.capsule,
        stacked ? styles.capsuleStacked : null,
        { backgroundColor: chrome.ground },
      ]}
    >
      <View style={styles.segments}>
        {track.kind === "continuous" ? (
          <Segment fill={track.fraction} weight={1} chrome={chrome} />
        ) : (
          track.segments.map((segment) => (
            <Segment
              key={segment.key}
              fill={segment.fill}
              weight={segment.weight}
              chrome={chrome}
            />
          ))
        )}
      </View>
      <Count count={capsuleCount(position, word)} chrome={chrome} />
    </View>
  );
}

function Segment({
  fill,
  weight,
  chrome,
}: {
  fill: number;
  weight: number;
  chrome: CapsuleChrome;
}) {
  return (
    <View style={[styles.segment, { flexGrow: weight, backgroundColor: chrome.track }]}>
      {fill > 0 ? (
        <View
          style={[styles.segmentFill, { width: `${fill * 100}%`, backgroundColor: chrome.fill }]}
        />
      ) : null}
    </View>
  );
}

/** The count, in two weights, as one run of text that never breaks. */
function Count({ count, chrome }: { count: string; chrome: CapsuleChrome }) {
  const { head, tail } = countParts(count);
  return (
    <AppText role="caption" style={[styles.numeral, { color: chrome.countInk }]}>
      {head}
      <AppText role="caption" style={[styles.numeralSoft, { color: chrome.countSoft }]}>
        {tail}
      </AppText>
    </AppText>
  );
}

const styles = StyleSheet.create({
  column: { gap: spacing.xs },
  // The segments take the width the count leaves; at the largest text steps
  // the count moves under them.
  capsule: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    minHeight: 32,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.chip,
    borderCurve: "continuous",
  },
  capsuleStacked: {
    flexDirection: "column",
    alignItems: "stretch",
    borderRadius: radius.card,
    borderCurve: "continuous",
  },
  segments: { flexGrow: 1, flexShrink: 1, flexDirection: "row", gap: 3 },
  segment: {
    flexBasis: 0,
    minWidth: SEGMENT_MIN,
    height: SEGMENT,
    borderRadius: SEGMENT / 2,
    overflow: "hidden",
  },
  segmentFill: { height: SEGMENT, borderRadius: SEGMENT / 2 },
  // Tabular figures, so the count does not reflow from one step to the next.
  numeral: { fontVariant: ["tabular-nums"], fontWeight: "600" },
  numeralSoft: { fontVariant: ["tabular-nums"], fontWeight: "400" },
});
