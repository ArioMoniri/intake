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
 */
import { StyleSheet, View } from "react-native";

import { AppText, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { positionLabel, positionSpoken, type QuestionPosition } from "@/lib/intake/questionScreen";
import { spacing } from "@/lib/theme";

/** The bar's height: a hairline-thin track, as in Health and Fitness setup flows. */
const TRACK = 4;

export function QuestionProgress({ position }: { position: QuestionPosition }) {
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
        style={styles.block}
      >
        <View style={[styles.track, { backgroundColor: theme.surfaceRaised }]}>
          <View style={[styles.fill, { width: filled, backgroundColor: theme.primary }]} />
        </View>
        <AppText role="caption" color="inkSoft" style={styles.count}>
          {positionLabel(position, word)}
        </AppText>
      </View>
      {position.mayGrow ? (
        <AppText role="caption" color="inkFaint">
          {t("intake.progress.grows")}
        </AppText>
      ) : null}
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
});
