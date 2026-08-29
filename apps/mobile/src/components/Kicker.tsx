/**
 * Kicker / eyebrow (design pass 3; unboxed in pass 4): a tiny dot glyph +
 * wide-tracked semibold caption ABOVE a section or inside a card header.
 * Pass 4 measurement against the Mobbin Oura captures: Oura's eyebrows and
 * group headers are UNBOXED quiet labels — the pass-3 pill box read as noise
 * Oura does not have, so the dot + tracking now carry the register alone.
 * Tracking replaces the case transform Oura uses — ALL-CAPS is banned
 * (İ/ı, 00 §2).
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
    <View style={styles.row}>
      <View style={[styles.dot, { backgroundColor: accent ? theme.primary : theme.inkFaint }]} />
      <AppText role="caption" color={accent ? "primary" : "inkSoft"} style={styles.label}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: spacing.xs + 2,
  },
  dot: { width: 5, height: 5, borderRadius: radius.chip },
  label: { fontWeight: "600", letterSpacing: tracking.kicker },
});
