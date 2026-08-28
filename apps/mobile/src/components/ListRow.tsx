/**
 * Grouped list primitives (design pass 5): the Oura settings/contributor
 * anatomy measured off the Mobbin captures — rows of 52+ pt inside ONE
 * rounded group (radius.group, squarer than content cards), 17 pt sans
 * labels, quiet trailing values, a small "›" only on rows that navigate,
 * hairlines between rows (never around them). Group headers are the
 * existing Kicker rendered OUTSIDE the group by the host screen.
 *
 * Colour never carries meaning alone (02 §8.2): trailing state is always a
 * labelled element, and the chevron is an affordance, not a state.
 */
import { type ReactNode } from "react";
import { Pressable, StyleSheet, View, useColorScheme } from "react-native";
import { SymbolView } from "expo-symbols";

import { AppText, Hairline, useTheme } from "@/components/Themed";
import { palette, radius, shadow, spacing } from "@/lib/theme";

export function ListGroup({ children, footer }: { children: ReactNode; footer?: string }) {
  const scheme = useColorScheme() === "dark" ? "dark" : "light";
  const theme = palette[scheme];
  const depth = shadow[scheme];
  const rows: ReactNode[] = [];
  const items = Array.isArray(children) ? children : [children];
  items
    .filter((child) => child !== null && child !== undefined && child !== false)
    .forEach((child, index) => {
      if (index > 0) {
        rows.push(<Hairline key={`hairline-${index}`} style={styles.hairlineInset} />);
      }
      rows.push(child);
    });
  return (
    <View style={styles.wrap}>
      <View
        style={[
          styles.group,
          {
            backgroundColor: theme.surface,
            borderColor: scheme === "dark" ? "transparent" : theme.border,
            shadowColor: depth.color,
            shadowOpacity: depth.opacity,
            shadowRadius: depth.radius,
            shadowOffset: { width: 0, height: depth.offsetY },
          },
        ]}
      >
        {rows}
      </View>
      {footer ? (
        <AppText role="caption" color="inkFaint" style={styles.footer}>
          {footer}
        </AppText>
      ) : null}
    </View>
  );
}

interface ListRowProps {
  label: string;
  /** Quiet caption under the label (dates, notes). */
  sublabel?: string;
  /** Leading 36 pt tonal icon well (SF Symbol name) — Oura's row anchor. */
  icon?: string;
  /** Trailing element: a value chip, pill group — rendered as-is. */
  trailing?: ReactNode;
  /** "›" affordance; set it ONLY on rows that navigate. */
  chevron?: boolean;
  onPress?: () => void;
}

export function ListRow({
  label,
  sublabel,
  icon,
  trailing,
  chevron = false,
  onPress,
}: ListRowProps) {
  const theme = useTheme();
  const body = (
    <>
      {icon ? (
        <View style={[styles.iconWell, { backgroundColor: theme.surfaceRaised }]}>
          <SymbolView name={icon as never} size={17} tintColor={theme.inkSoft} />
        </View>
      ) : null}
      <View style={styles.labels}>
        <AppText role="body">{label}</AppText>
        {sublabel ? (
          <AppText role="caption" color="inkFaint">
            {sublabel}
          </AppText>
        ) : null}
      </View>
      {trailing ?? null}
      {chevron ? <SymbolView name="chevron.right" size={13} tintColor={theme.inkFaint} /> : null}
    </>
  );
  if (onPress) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        onPress={onPress}
        style={({ pressed }) => [styles.row, { opacity: pressed ? 0.7 : 1 }]}
      >
        {body}
      </Pressable>
    );
  }
  return <View style={styles.row}>{body}</View>;
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  group: {
    borderRadius: radius.group,
    borderWidth: 1,
    overflow: "hidden",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm + 4,
    minHeight: 56,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  labels: { flex: 1, gap: 2 },
  // Oura hairlines start at the text column, not the group edge.
  hairlineInset: { marginLeft: spacing.md },
  iconWell: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  footer: { paddingHorizontal: spacing.md },
});
