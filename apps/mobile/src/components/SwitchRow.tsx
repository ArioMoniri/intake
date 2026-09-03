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
 *
 * The form rule is TWO terms now, and it is the same rule the consent rows
 * take: `isLargeText(scale) || required > available`, evaluated by
 * lib/a11y/pairedRow.ts. The scale term is unchanged and no second scalar was
 * minted — the geometry term is what was missing. A label column with
 * `flex: 1` and no floor is free to shrink to nothing while the track holds
 * its intrinsic width (React Native gives children `flexShrink: 0` by
 * default), and that is exactly how the consent rows came down one character
 * at a time. Today's labels all fit to about 1.59, so nothing renders
 * differently now: the geometry term is the tripwire for the next label a
 * copy owner lengthens, and the column's own minimum is the repair.
 */
import { useCallback, useState } from "react";
import { Pressable, StyleSheet, View, type LayoutChangeEvent } from "react-native";

import { AppText, useFontScale, useTheme } from "@/components/Themed";
import {
  ROW_GAP,
  ROW_PADDING,
  TRAILING_SLOT_FLEX,
  labelColumnStyle,
  pairedRowMetrics,
} from "@/lib/a11y/pairedRow";
import { scaledControl, spacing } from "@/lib/theme";

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
  const [rowWidth, setRowWidth] = useState<number | null>(null);
  const onRowLayout = useCallback((event: LayoutChangeEvent) => {
    const width = Math.floor(event.nativeEvent.layout.width);
    setRowWidth((previous) => (previous === width ? previous : width));
  }, []);
  const trackWidth = scaledControl(46, fontScale);
  const trackHeight = scaledControl(28, fontScale);
  const inset = scaledControl(3, fontScale);
  const knob = trackHeight - inset * 2;
  // The track's width IS the reserve: a control's box is its target, so it
  // never gives width back to the words beside it — when they cannot both
  // hold, the row changes form instead. `rowWidth` is null on the first frame
  // and the reference device answers for it; the real measurement wins the
  // moment it arrives.
  const stacked =
    pairedRowMetrics({ label, trailingWidth: trackWidth }, fontScale, rowWidth).form === "stacked";
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ checked }}
      onLayout={onRowLayout}
      onPress={() => onChange(!checked)}
      style={({ pressed }) => [
        styles.row,
        stacked ? styles.rowStacked : null,
        { opacity: pressed ? 0.7 : 1 },
      ]}
    >
      <View
        style={[styles.labels, stacked ? styles.labelsStacked : labelColumnStyle(label, fontScale)]}
      >
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
    // Read from the module that does the fit arithmetic rather than spelled
    // again here: a row that renders a 16 pt gap while the model reserves 12
    // is two numbers free to drift, and it also put this row half a step out
    // of the ListRow rhythm the docstring above claims it matches.
    gap: ROW_GAP,
    // The row IS the target (SC 2.5.8), matching ListRow's own rhythm.
    minHeight: 56,
    paddingHorizontal: ROW_PADDING,
    paddingVertical: spacing.sm + 2,
  },
  // Column form: the control sits under the words it governs, left-aligned
  // with them, once those words need more than one line.
  rowStacked: { flexDirection: "column", alignItems: "flex-start", gap: spacing.sm },
  labels: { gap: 2 },
  labelsStacked: { alignSelf: "stretch", gap: 2 },
  // Track and knob dimensions come from the scale at render, and the track
  // never shrinks: a control that gives up width stops being a target.
  track: { ...TRAILING_SLOT_FLEX, justifyContent: "center" },
});
