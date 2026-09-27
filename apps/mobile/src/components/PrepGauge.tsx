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
import { StyleSheet, View, useWindowDimensions } from "react-native";

import { AppText, useFontScale, useTheme } from "@/components/Themed";
import { shortSide } from "@/lib/a11y/orientation";
import { getLocale } from "@/lib/i18n";
import { scaledControl, spacing, tracking } from "@/lib/theme";

/** The arc's diameter at scale 1.0 (design pass 5 measurement). */
const BASE_SIZE = 232;
const STROKE = 3;
/** Screen gutter either side, so the arc never runs off the edge. */
const GUTTER = spacing.screen * 2;

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
  // INT-260: the arc was a fixed 232 while the numeral inside it scaled, so at
  // the largest step a 112 pt numeral sat in a 116 pt bowl and the ring read as
  // broken. The arc scales with the numeral it frames — and is capped to the
  // screen so growing it can never clip it against the edge, which is the
  // other half of the same defect.
  //
  // INT-360: capped by the window's SHORT side. The width bounded it while the
  // app was portrait-only, but in landscape the width is the long side: at the
  // largest step the arc stayed 464 × 232 pt in an 844 × 390 window, and with
  // its numeral and caption the gauge alone filled the room above the tab
  // rail. The short side makes it 350 × 175 there. In portrait the short side
  // is the width, so nothing a portrait patient sees moves.
  const fontScale = useFontScale();
  const window = useWindowDimensions();
  const size = Math.min(
    scaledControl(BASE_SIZE, fontScale),
    Math.max(120, shortSide(window) - GUTTER),
  );
  const ring = {
    width: size,
    height: size / 2,
    borderTopLeftRadius: size / 2,
    borderTopRightRadius: size / 2,
  };
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
      <View style={[styles.window, { width: size, height: size / 2 }]} pointerEvents="none">
        <View style={[styles.ring, ring, { borderColor: theme.border }]} />
        <View
          style={[
            styles.fillLayer,
            { width: size, height: size / 2 },
            { transform: [{ rotate: `${-180 + clamped * 180}deg` }] },
          ]}
        >
          <View style={[styles.ring, ring, { borderColor: theme.ink }]} />
        </View>
      </View>
      {/* The numeral overlaps INTO the bowl but lives outside the clip
          window, so at fontScale 2.0 it grows downward past the arc instead
          of being cut off (02 §8.2). */}
      <View style={[styles.numeral, { marginTop: -(size / 2 - scaledControl(44, fontScale)) }]}>
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
  // The clip window: only the top half of the rings is ever visible. Its
  // dimensions come from the scale at render.
  window: { overflow: "hidden" },
  // Half-ring: a top-semicircle outline; bottom edge open.
  ring: {
    position: "absolute",
    top: 0,
    left: 0,
    borderWidth: STROKE,
    borderBottomWidth: 0,
  },
  // Rotates around the baseline centre; at 0 progress it points straight
  // down (fully clipped), at 1 it overlaps the track exactly.
  fillLayer: {
    position: "absolute",
    top: 0,
    left: 0,
    transformOrigin: "50% 100%",
  },
  // Pulls the numeral up into the arc bowl; the overlap parks it on the
  // baseline and scales with the bowl (marginTop is set at render).
  numeral: { alignItems: "center" },
  label: { fontWeight: "600", letterSpacing: tracking.kicker },
});
