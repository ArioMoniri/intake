/**
 * Kicker / eyebrow (design pass 3, Oura register): a tiny dot glyph + wide-
 * tracked caption on a subtle glass-family pill, sitting ABOVE a section or
 * a guidance block where a plain label used to be. Tracking replaces the
 * case transform Oura uses — ALL-CAPS is banned (İ/ı, 00 §2), so the pill,
 * the dot and the letterSpacing carry the "small label" register instead.
 */
import { StyleSheet, View } from "react-native";

import { AppText, useTheme } from "@/components/Themed";
import { radius, spacing, tracking } from "@/lib/theme";

interface KickerProps {
  label: string;
  /** accent = the section the screen is about; neutral = everything else. */
  tone?: "accent" | "neutral";
}

export function Kicker({ label, tone = "neutral" }: KickerProps) {
  const theme = useTheme();
  const accent = tone === "accent";
  return (
    <View
      style={[
        styles.pill,
        {
          // Neutral pills carry the ground tone + hairline so they read both
          // on the ground and inset on a surface card; accent pills are the
          // soft primary wash either way.
          backgroundColor: accent ? theme.primarySoft : theme.background,
          borderColor: accent ? "transparent" : theme.border,
        },
      ]}
    >
      <View
        style={[styles.dot, { backgroundColor: accent ? theme.primary : theme.inkFaint }]}
      />
      <AppText
        role="caption"
        color={accent ? "primary" : "inkSoft"}
        style={styles.label}
      >
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: spacing.xs + 2,
    borderRadius: radius.chip,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 1,
  },
  dot: { width: 5, height: 5, borderRadius: radius.chip },
  label: { fontWeight: "600", letterSpacing: tracking.kicker },
});
