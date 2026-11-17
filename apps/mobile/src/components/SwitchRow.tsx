/**
 * A labelled switch as a full list row (INT-260).
 *
 * The app had no switch primitive — the consent and notification screens each
 * hand-rolled a tonal pill, which reads as a chip rather than as a control
 * with two states. This is the real thing, and it is the whole row: the target
 * is the row's 56 pt box, so it clears SC 2.5.8 without slop, and a
 * screen-reader user gets one element with the platform's `switch` role and
 * its value rather than a button whose visible word IS the state.
 *
 * The knob moves as well as recolouring, so the state survives a patient who
 * cannot separate the two fills (BK8 / SC 1.4.1).
 *
 * Two things happen as the text grows, and both were defects the owner named
 * on the simulator ("navbar and sizes dont match"). The track and knob scale
 * with the label through `scaledControl`, so the control does not sit at its
 * base size beside doubled words. And above the large-text scale the row
 * becomes a COLUMN: at 2.0 "Ekran hareketini azaltın" needs two lines, and a
 * toggle pinned to the right of two wrapped lines reads as an afterthought
 * rather than as the control for them. Under the words is where it belongs.
 * A platform `Switch` cannot do either of these, which is the other reason
 * this is drawn rather than imported.
 *
 * Refitting the two existing hand-rolled pills onto this component is a
 * separate cleanup issue — one issue, one PR — and is listed as such.
 */
import { Pressable, StyleSheet, View } from "react-native";

import { AppText, useFontScale, useTheme } from "@/components/Themed";
import { isLargeText } from "@/lib/prefs/appearance";
import { motion, scaledControl, spacing } from "@/lib/theme";

interface SwitchRowProps {
  label: string;
  /** Quiet caption under the label. */
  sublabel?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Spoken after the name; what flipping it does. */
  hint?: string;
}

export function SwitchRow({ label, sublabel, checked, onChange, hint }: SwitchRowProps) {
  const theme = useTheme();
  const fontScale = useFontScale();
  const stacked = isLargeText(fontScale);
  const trackWidth = scaledControl(46, fontScale);
  const trackHeight = scaledControl(28, fontScale);
  const inset = scaledControl(3, fontScale);
  const knob = trackHeight - inset * 2;
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ checked }}
      onPress={() => onChange(!checked)}
      style={({ pressed }) => [
        styles.row,
        stacked ? styles.rowStacked : null,
        { opacity: pressed ? motion.press.rowOpacity : 1 },
      ]}
    >
      <View style={stacked ? styles.labelsStacked : styles.labels}>
        <AppText role="body">{label}</AppText>
        {sublabel ? (
          <AppText role="caption" color="inkFaint">
            {sublabel}
          </AppText>
        ) : null}
      </View>
      <View
        style={[
          styles.track,
          {
            width: trackWidth,
            height: trackHeight,
            borderRadius: trackHeight / 2,
            padding: inset,
            backgroundColor: checked ? theme.primary : theme.surfaceRaised,
            // Position, not only fill — the knob sitting left or right is the
            // half of the signal that survives a colour deficiency.
            alignItems: checked ? "flex-end" : "flex-start",
          },
        ]}
      >
        <View
          style={{
            width: knob,
            height: knob,
            borderRadius: knob / 2,
            backgroundColor: checked ? theme.onPrimary : theme.inkFaint,
          }}
        />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    // The row IS the target (SC 2.5.8), matching ListRow's own rhythm.
    minHeight: 56,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  // Column form: the control sits under the words it governs, left-aligned
  // with them, once those words need more than one line.
  rowStacked: { flexDirection: "column", alignItems: "flex-start", gap: spacing.sm },
  labels: { flex: 1, gap: 2 },
  labelsStacked: { alignSelf: "stretch", gap: 2 },
  // Track and knob dimensions come from the scale at render.
  track: { justifyContent: "center" },
});
