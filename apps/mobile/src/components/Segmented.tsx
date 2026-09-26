/**
 * Segmented choice (INT-260): a small closed set, one of which is chosen.
 *
 * Deliberately discrete and deliberately not a slider. `typeScale` is seven
 * fixed integers and `scaledSize` rounds (theme.ts), so a continuous control
 * would promise precision the token system does not have — and the clinical
 * path forbids free numeric entry outright (invariant 22).
 *
 * Two forms, one component, and TWO reasons to take the second. Below the
 * large-text scale a group of two or three is a row of tonal pills on a raised
 * track (the Oura segment register). It stacks into full-width rows when the
 * text is large — and also whenever there are more than three options, at any
 * scale, because five Turkish labels do not fit a phone width: measured on the
 * simulator at OS 1.0, "Daha büyük" and "En büyük" each wrapped to two lines
 * and the pills ended up different heights. Shortening the words to fit the
 * control would have been the wrong repair; the control changes form instead
 * (00 §2), and a vertical list never has to change form again — it just gets
 * taller and scrolls.
 *
 * Accessibility is the point of this control, so it is explicit rather than
 * inferred: `radiogroup` names the question, each row is a `radio` that states
 * whether it is the chosen one, and every row reaches the target floor by BOX
 * (`minHeight: MIN_TAP`) — never by slop, which on a row of adjacent pills
 * would make a neighbour unreachable. Selection is carried by a filled pill in
 * the inline form (a luminance inversion, not a hue) and by a border plus a
 * checkmark once stacked, so it never rests on colour alone.
 */
import { Pressable, StyleSheet, View } from "react-native";
import { SymbolView } from "expo-symbols";

import { AppText, useFontScale, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { MIN_TAP } from "@/lib/a11y/target";
import { shouldStack } from "@/lib/prefs/appearance";
import { motion, radius, spacing } from "@/lib/theme";

export interface SegmentedOption {
  readonly id: string;
  readonly label: string;
}

interface SegmentedProps {
  /** What the group is asking — its accessible name, and the row's context. */
  label: string;
  options: readonly SegmentedOption[];
  /**
   * The chosen option's id, or `null` for "nothing chosen here" — which is a
   * real state, not an error: while the text size follows the phone, no rung
   * of the ladder is the patient's choice and none is shown as one.
   */
  value: string | null;
  onChange: (id: string) => void;
  /** Spoken after the name; what choosing from this group does. */
  hint?: string;
}

export function Segmented({ label, options, value, onChange, hint }: SegmentedProps) {
  const theme = useTheme();
  const stacked = shouldStack(useFontScale(), options.length);
  return (
    <View
      accessibilityRole="radiogroup"
      accessibilityLabel={label}
      style={[
        styles.group,
        stacked ? styles.groupStacked : styles.groupInline,
        stacked ? null : { backgroundColor: theme.surfaceRaised },
      ]}
    >
      {options.map((option) => {
        const selected = option.id === value;
        return (
          <Pressable
            key={option.id}
            accessibilityRole="radio"
            // The visible word first (SC 2.5.3), the group after — "Büyük" on
            // its own names nothing once position is gone.
            accessibilityLabel={withContext(option.label, label)}
            accessibilityHint={hint}
            accessibilityState={{ selected }}
            onPress={() => onChange(option.id)}
            style={({ pressed }) => [
              styles.option,
              stacked ? styles.optionStacked : styles.optionInline,
              {
                backgroundColor: stacked
                  ? theme.surface
                  : selected
                    ? theme.cta
                    : "transparent",
                borderColor: stacked && selected ? theme.ink : "transparent",
                opacity: pressed ? motion.press.opacity : 1,
              },
            ]}
          >
            <AppText
              role="label"
              color={stacked ? "ink" : selected ? "onCta" : "inkSoft"}
              style={selected ? styles.selectedLabel : undefined}
            >
              {option.label}
            </AppText>
            {stacked && selected ? (
              <SymbolView name="checkmark" size={20} tintColor={theme.ink} />
            ) : null}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  group: { gap: spacing.xs },
  groupInline: {
    flexDirection: "row",
    borderRadius: radius.chip,
    padding: spacing.xs,
  },
  groupStacked: { flexDirection: "column", gap: spacing.sm },
  option: {
    alignItems: "center",
    justifyContent: "center",
    // By box, never by slop: adjacent pills sit a few points apart and
    // overlapping targets trade one SC 2.5.8 failure for a worse one.
    minHeight: MIN_TAP,
    borderWidth: 1,
  },
  optionInline: {
    flex: 1,
    flexBasis: 0,
    borderRadius: radius.chip,
    paddingHorizontal: spacing.xs,
    paddingVertical: spacing.xs,
  },
  optionStacked: {
    flexDirection: "row",
    // Wraps (INT-295): the checkmark is pinned to the far end, and a long
    // Turkish label at the largest step would otherwise push it off the row.
    flexWrap: "wrap",
    justifyContent: "space-between",
    alignSelf: "stretch",
    borderRadius: radius.group,
    // A stacked row is a list row, and the app's list rows are 56.
    minHeight: 56,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  selectedLabel: { fontWeight: "600" },
});
