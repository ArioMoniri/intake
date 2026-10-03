/**
 * Grouped list primitives: the iOS inset grouped list (INT-422,
 * docs/design/system-refresh.md). Rows of 56 pt inside ONE group on the
 * surface tone, 12-pt continuous corners, no border and no shadow, Body
 * labels, a bare tinted SF Symbol leading the row, quiet trailing values, a
 * small "›" only on rows that navigate, separators between rows (never
 * around them). Group headers are the Kicker, rendered OUTSIDE the group by
 * the host screen.
 *
 * Colour never carries meaning alone (02 §8.2): trailing state is always a
 * labelled element, and the chevron is an affordance, not a state.
 */
import { type ReactNode } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { Icon } from "@/components/Icon";
import { AppText, Hairline, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import type { SymbolKey } from "@/lib/symbols";
import { radius, rowPressFill, spacing } from "@/lib/theme";

/** Action name for the row's nested trailing control. */
const SECONDARY_ACTION = "secondary";

export function ListGroup({ children, footer }: { children: ReactNode; footer?: string }) {
  const theme = useTheme();
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
      <View style={[styles.group, { backgroundColor: theme.surface }]}>{rows}</View>
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
  /** Leading glyph (a symbol registry row), drawn bare in the tint. */
  icon?: SymbolKey;
  /** Trailing element: a value chip, pill group — rendered as-is. */
  trailing?: ReactNode;
  /** "›" affordance; set it ONLY on rows that navigate. */
  chevron?: boolean;
  /** Nested child row (INT-132 lane sub-toggles): indented text column. */
  inset?: boolean;
  onPress?: () => void;
  /**
   * What activating the row does (INT-144). A row and a switch nested in its
   * trailing slot are two different controls that used to carry the same
   * accessible name; the hint is what separates "open the consent text" from
   * "withdraw the consent" for a screen-reader user.
   */
  hint?: string;
  /**
   * Context spoken after the visible label — a date, a trailing value — for
   * rows whose label alone is ambiguous once position is gone. The visible
   * label always comes FIRST (SC 2.5.3 Label in Name).
   */
  labelContext?: string;
  /**
   * The row's SECOND action, when a control is nested in `trailing`
   * (INT-144).
   *
   * A pressable row is `accessible` by default, which merges its whole
   * subtree into one element — so a `Pressable` in the trailing slot is not
   * focusable at all on iOS and its role, state and target are inert. That
   * is how the consent switch became unreachable: a screen-reader user could
   * open a purpose's text but could not withdraw the consent.
   *
   * A custom accessibility action is the platform's answer: VoiceOver
   * surfaces it in the actions rotor and TalkBack in its local context menu,
   * so both reach the toggle without the row having to stop being one
   * element. The trailing control stays exactly as it is for pointer use.
   */
  secondaryAction?: { label: string; onPress: () => void };
}

export function ListRow({
  label,
  sublabel,
  icon,
  trailing,
  chevron = false,
  inset = false,
  onPress,
  hint,
  labelContext,
  secondaryAction,
}: ListRowProps) {
  const theme = useTheme();
  const body = (
    <>
      {icon ? (
        <View style={styles.iconSlot}>
          <Icon name={icon} size={22} tintColor={theme.primary} />
        </View>
      ) : null}
      <View style={styles.labels}>
        <AppText role="body">{label}</AppText>
        {sublabel ? (
          // Tabular figures: sublabels are mostly dates, and stacked rows
          // should hold a steady numeric column (design pass 6).
          <AppText role="caption" color="inkFaint" style={styles.sublabel}>
            {sublabel}
          </AppText>
        ) : null}
      </View>
      {trailing ?? null}
      {chevron ? <Icon name="chevron.right" size={13} tintColor={theme.inkFaint} /> : null}
    </>
  );
  if (onPress) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={withContext(label, labelContext, sublabel)}
        accessibilityHint={hint}
        accessibilityActions={
          secondaryAction ? [{ name: SECONDARY_ACTION, label: secondaryAction.label }] : undefined
        }
        onAccessibilityAction={
          secondaryAction
            ? (event) => {
                if (event.nativeEvent.actionName === SECONDARY_ACTION) {
                  secondaryAction.onPress();
                }
              }
            : undefined
        }
        onPress={onPress}
        style={({ pressed }) => [
          styles.row,
          inset ? styles.rowInset : null,
          pressed ? { backgroundColor: theme[rowPressFill] } : null,
        ]}
      >
        {body}
      </Pressable>
    );
  }
  return <View style={[styles.row, inset ? styles.rowInset : null]}>{body}</View>;
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  group: {
    borderRadius: radius.group,
    borderCurve: "continuous",
    overflow: "hidden",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    minHeight: 56,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  labels: { flex: 1, gap: 2 },
  sublabel: { fontVariant: ["tabular-nums"] },
  // Nested child rows shift the whole content column one step right.
  rowInset: { paddingLeft: spacing.md + spacing.lg },
  // Separators start at the content column, not the group edge.
  hairlineInset: { marginLeft: spacing.md },
  // A fixed column, so labels align down the group whatever the glyph's width.
  iconSlot: { width: 28, alignItems: "center", justifyContent: "center" },
  footer: { paddingHorizontal: spacing.md },
});
