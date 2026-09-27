/**
 * The skeleton (INT-342, MOTION-13; docs/design/motion/motion-verification.md
 * §1.2 P7, §4 MOTION-13): static blocks that stand in for a list on its way.
 *
 * It is on the tree from the commit that starts the wait, hidden, and steps
 * in once the plan's delay has passed (lib/motion/reveal.ts; the UI-thread
 * half is lib/motion/native/reanimated.ts). So a load that lands inside the
 * delay never shows it. Once shown it never moves: no sweep, no loop, no
 * transform, no entrance and no exit (e2e/motion.spec.ts). Its host removes
 * it in the commit that brings the content.
 *
 * For a screen reader it is one element, busy, named from the catalogue, from
 * the moment it mounts: the wait is on the tree even before the blocks are
 * drawn. Nothing is posted as a live announcement, because a load under the
 * delay would then be spoken for a skeleton nobody sees.
 *
 * The shape echoes ListGroup (radius.group, 56 pt rows) in the raised tone,
 * so the content lands where the blocks were. Two rows, whatever the data:
 * a count the patient could read as theirs would be a claim.
 */
import { StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";

import { useScheme, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { useSkeletonOpacity } from "@/lib/motion/native/reanimated";
import type { SkeletonPlan } from "@/lib/motion/reveal";
import { radius, spacing } from "@/lib/theme";

const ROWS = ["first", "second"] as const;

export function Skeleton({ plan }: { plan: SkeletonPlan }) {
  const theme = useTheme();
  const dark = useScheme() === "dark";
  const opacity = useSkeletonOpacity(plan);
  const block = { backgroundColor: theme.surfaceRaised };
  return (
    <Animated.View
      accessible
      accessibilityLabel={t("a11y.loading")}
      accessibilityState={{ busy: true }}
      style={[
        styles.group,
        { backgroundColor: theme.surface, borderColor: dark ? "transparent" : theme.border },
        opacity,
      ]}
    >
      {ROWS.map((row) => (
        <View key={row} style={styles.row}>
          <View style={[styles.well, block]} />
          <View style={styles.lines}>
            <View style={[styles.line, block]} />
            <View style={[styles.line, styles.short, block]} />
          </View>
        </View>
      ))}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  group: { borderRadius: radius.group, borderWidth: 1, overflow: "hidden" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm + 4,
    minHeight: 56,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  well: { width: 36, height: 36, borderRadius: 18 },
  lines: { flex: 1, gap: spacing.xs + 2 },
  line: { height: 12, borderRadius: radius.chip },
  short: { width: "40%" },
});
