/**
 * Semicircular prep gauge (design pass 5): the Oura home leads with a big
 * centred numeral under a thin arc — this is that focal point for the next
 * visit's preparation, in pure Views (no SVG dependency): a half-ring track
 * clipped to its top half, and a fill half-ring rotating up around the
 * baseline centre; the clip window hides whatever sits below the horizon.
 *
 * Register rules from the reference: the arc and numeral are INK, not the
 * accent (Oura's gauge is white; the accent stays reserved for the screen's
 * one CTA), the numeral is the serif display face, and the label under it is
 * the tracked kicker caption. The percent string comes from
 * Intl.NumberFormat so tr renders "%42" and en "42%" — the symbol side is a
 * locale rule, never hand-assembled (00 §2).
 */
import { StyleSheet, View } from "react-native";

import { AppText, useTheme } from "@/components/Themed";
import { getLocale } from "@/lib/i18n";
import { spacing, tracking } from "@/lib/theme";

const SIZE = 232;
const STROKE = 3;

export function formatPercent(fraction: number, locale: string): string {
  const clamped = Math.max(0, Math.min(fraction, 1));
  return new Intl.NumberFormat(locale === "tr" ? "tr-TR" : "en-GB", {
    style: "percent",
    maximumFractionDigits: 0,
    useGrouping: false,
  }).format(clamped);
}

export function PrepGauge({ fraction, label }: { fraction: number; label: string }) {
  const theme = useTheme();
  const clamped = Math.max(0, Math.min(fraction, 1));
  const value = formatPercent(clamped, getLocale());
  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      // INT-144: the value belongs in accessibilityValue, not glued into the
      // name. `text` is the locale-formatted percent the eye reads (tr "%42",
      // en "42%" — never hand-assembled, 00 §2); now/min/max let the screen
      // reader use its own progress idiom and report change on re-render.
      accessibilityValue={{ min: 0, max: 100, now: Math.round(clamped * 100), text: value }}
      style={styles.wrap}
    >
      <View style={styles.window} pointerEvents="none">
        <View style={[styles.ring, { borderColor: theme.border }]} />
        <View style={[styles.fillLayer, { transform: [{ rotate: `${-180 + clamped * 180}deg` }] }]}>
          <View style={[styles.ring, { borderColor: theme.ink }]} />
        </View>
      </View>
      {/* The numeral overlaps INTO the bowl but lives outside the clip
          window, so at fontScale 2.0 it grows downward past the arc instead
          of being cut off (02 §8.2). */}
      <View style={styles.numeral}>
        <AppText role="display">{value}</AppText>
      </View>
      <AppText role="caption" color="inkSoft" style={styles.label}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  // marginBottom nets the hero block ~24 of air over the first card, the
  // Oura headline→card rhythm (round-2 measurement).
  wrap: { alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm },
  // The clip window: only the top half of the rings is ever visible.
  window: { width: SIZE, height: SIZE / 2, overflow: "hidden" },
  // Half-ring: a top-semicircle outline; bottom edge open.
  ring: {
    position: "absolute",
    top: 0,
    left: 0,
    width: SIZE,
    height: SIZE / 2,
    borderTopLeftRadius: SIZE / 2,
    borderTopRightRadius: SIZE / 2,
    borderWidth: STROKE,
    borderBottomWidth: 0,
  },
  // Rotates around the baseline centre; at 0 progress it points straight
  // down (fully clipped), at 1 it overlaps the track exactly.
  fillLayer: {
    position: "absolute",
    top: 0,
    left: 0,
    width: SIZE,
    height: SIZE / 2,
    transformOrigin: "50% 100%",
  },
  // Pulls the numeral up into the arc bowl (the window is 116 tall; the
  // display line is 67 at scale 1.0 — the overlap parks it on the baseline).
  numeral: { marginTop: -(SIZE / 2 - 44), alignItems: "center" },
  label: { fontWeight: "600", letterSpacing: tracking.kicker },
});
