/**
 * The typed intake's progress (INT-433): a thin determinate bar and a
 * "Soru N / M" line, the native treatment the owner asked for in place of a
 * row of one dot per question (Mobbin references in
 * docs/design/question-screen.md).
 *
 * - One element for assistive technology: a `progressbar` whose value is the
 *   worded "Soru 3, toplam 9". The bar's fill is the sighted cue; the value is
 *   the fact (SC 1.4.1), so nothing is carried by the hue alone.
 * - The numerals are display-only (invariant 22). They are formatted by
 *   lib/intake/questionScreen.ts and this control is mounted by the typed
 *   screen alone; the spoken lane never imports either.
 * - M is the applicable count, never the pack's length, and while a gate can
 *   still open, the growth line is shown under it, outside the progressbar so
 *   a reader hears it too.
 * - The line sits under the bar with the full content width to itself, wraps
 *   at the largest text step and is never clipped (e2e/overflow.spec.ts).
 *
 * INT-492 (behind `progressMicro`, off by default): the segmented capsule
 * (lib/intake/progressCapsule.ts). It draws inside the same progressbar, so
 * the value a reader hears is the same one string in both looks, and its
 * children are never read on their own. It swaps with the step, instantly:
 * the question's fade is the step's one animated element (ADR-033 §2). The
 * rolling digit is approval needed and runs only in a development build
 * (lib/flags.ts). The intake is capture-protected, so the capsule is solid
 * (INT-477): opaque theme fills and no material.
 */
import { useState } from "react";
import { StyleSheet, View } from "react-native";
import Animated, { LayoutAnimationConfig } from "react-native-reanimated";

import { AppText, useFontScale, useTheme } from "@/components/Themed";
import { useReducedMotion } from "@/lib/a11y/prefs";
import type { Flags } from "@/lib/flags";
import { t } from "@/lib/i18n";
import {
  capsuleChrome,
  capsuleCount,
  capsuleTrack,
  countParts,
  rollDigits,
  rollGranted,
  type CapsuleChrome,
  type CapsuleItem,
} from "@/lib/intake/progressCapsule";
import { positionLabel, positionSpoken, type QuestionPosition } from "@/lib/intake/questionScreen";
import { numberRoll, type NumberRoll } from "@/lib/motion/micro";
import { rollEntering } from "@/lib/motion/native/numberRoll";
import { radius, spacing } from "@/lib/theme";

/** The bar's height: a hairline-thin track, as in Health and Fitness setup flows. */
const TRACK = 4;

/** The redesign's capsule: what the typed screen hands over under the flag. */
export interface CapsuleProps {
  readonly flow: readonly CapsuleItem[];
  readonly flags: Flags;
}

export function QuestionProgress({
  position,
  capsule,
}: {
  position: QuestionPosition;
  capsule?: CapsuleProps;
}) {
  const theme = useTheme();
  const word = t("intake.progress.question");
  const filled = `${position.fraction * 100}%` as const;
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
        style={capsule === undefined ? styles.block : null}
      >
        {capsule === undefined ? (
          <>
            <View style={[styles.track, { backgroundColor: theme.surfaceRaised }]}>
              <View style={[styles.fill, { width: filled, backgroundColor: theme.primary }]} />
            </View>
            <AppText role="caption" color="inkSoft" style={styles.count}>
              {positionLabel(position, word)}
            </AppText>
          </>
        ) : (
          <CapsuleBody position={position} capsule={capsule} word={word} />
        )}
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
  capsule,
  word,
}: {
  position: QuestionPosition;
  capsule: CapsuleProps;
  word: string;
}) {
  const theme = useTheme();
  const reduce = useReducedMotion();
  const stacked = useFontScale() >= STACK_AT;
  const chrome = capsuleChrome(theme);
  const track = capsuleTrack(capsule.flow, position);
  const count = capsuleCount(position, word);
  const roll = numberRoll({ flags: capsule.flags, reduce, redPresented: false });
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
      {roll.kind === "none" ? (
        <StillCount count={count} chrome={chrome} />
      ) : (
        <RollingCount position={position} word={word} roll={roll} chrome={chrome} />
      )}
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
function StillCount({ count, chrome }: { count: string; chrome: CapsuleChrome }) {
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

/**
 * Approval needed (lib/flags.ts): the count as glyphs, where a digit that
 * changed is a new element and rises in on the app's one fade. Only a
 * forward step of one rolls (`rollGranted`); the first frame skips every
 * entrance. The glyphs are hidden from assistive technology and carry no
 * label of their own: the progressbar above says the one value, so a reader
 * never hears a digit or a frame.
 */
function RollingCount({
  position,
  word,
  roll,
  chrome,
}: {
  position: QuestionPosition;
  word: string;
  roll: NumberRoll;
  chrome: CapsuleChrome;
}) {
  const [seen, setSeen] = useState<{ from: QuestionPosition | null; to: QuestionPosition }>({
    from: null,
    to: position,
  });
  if (seen.to.position !== position.position || seen.to.total !== position.total) {
    setSeen({ from: seen.to, to: position });
  }
  const count = capsuleCount(position, word);
  const previous =
    seen.from !== null && rollGranted(seen.from, position) ? capsuleCount(seen.from, word) : null;
  const entering = rollEntering(roll);
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={styles.glyphs}
    >
      <LayoutAnimationConfig skipEntering>
        {rollDigits(previous, count).map((glyph) => (
          <Animated.View key={glyph.key} entering={glyph.rolls ? entering : undefined}>
            <AppText
              role="caption"
              style={[
                glyph.part < 2 ? styles.numeral : styles.numeralSoft,
                { color: glyph.part < 2 ? chrome.countInk : chrome.countSoft },
              ]}
            >
              {glyph.char}
            </AppText>
          </Animated.View>
        ))}
      </LayoutAnimationConfig>
    </View>
  );
}

const styles = StyleSheet.create({
  column: { gap: spacing.xs },
  // Stacked, not a row: the line never competes with the bar for width.
  block: {
    gap: spacing.sm,
  },
  track: {
    alignSelf: "stretch",
    height: TRACK,
    borderRadius: TRACK / 2,
    overflow: "hidden",
  },
  fill: { height: TRACK, borderRadius: TRACK / 2 },
  // Tabular figures, so the line does not reflow from one step to the next.
  count: { fontVariant: ["tabular-nums"], fontWeight: "600" },
  // INT-492: the capsule. The segments take the width the count leaves;
  // at the largest text steps the count moves under them.
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
  // Tabular figures: a new digit takes the old one's advance, so nothing shifts.
  numeral: { fontVariant: ["tabular-nums"], fontWeight: "600" },
  numeralSoft: { fontVariant: ["tabular-nums"], fontWeight: "400" },
  glyphs: { flexDirection: "row" },
});
