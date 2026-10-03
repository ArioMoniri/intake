/**
 * An empty state (INT-422, docs/design/system-refresh.md §4): the shape of
 * SwiftUI's ContentUnavailableView. One SF Symbol in the tint, the existing
 * catalogue line under it, and the one action that fills the space, centred
 * in the room the list would take. A blank screen, or a lone grey card that
 * says "nothing here", reads as broken; this reads as the next step.
 *
 * No illustration and no new copy: the glyph is a registry symbol and the
 * line is the string the screen already showed. The glyph is decorative and
 * hidden from screen readers, so the line is what VoiceOver reads.
 */
import { type ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import { Icon } from "@/components/Icon";
import { AppText, useFontScale, useTheme } from "@/components/Themed";
import type { SymbolKey } from "@/lib/symbols";
import { scaledControl, spacing } from "@/lib/theme";

interface EmptyStateProps {
  icon: SymbolKey;
  message: string;
  /** The one action that fills the space, rendered under the message. */
  children?: ReactNode;
}

export function EmptyState({ icon, message, children }: EmptyStateProps) {
  const theme = useTheme();
  const size = scaledControl(44, useFontScale());
  return (
    <View style={styles.wrap}>
      <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
        <Icon name={icon} size={size} tintColor={theme.primary} />
      </View>
      <AppText role="body" color="inkSoft" style={styles.message}>
        {message}
      </AppText>
      {children ? <View style={styles.action}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.xl,
  },
  message: { textAlign: "center" },
  action: { alignSelf: "stretch", marginTop: spacing.sm },
});
