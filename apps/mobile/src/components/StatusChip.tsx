/**
 * Pre-visit note status chip (02 §5.1): Taslak → Gönderildi → Hekim
 * görüntüledi → Dosyaya eklendi. Colour never carries the meaning alone —
 * the label is always present (02 §8.2, colour-blind safe).
 */
import { StyleSheet, View } from "react-native";

import { AppText, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { radius, spacing } from "@/lib/theme";
import type { NoteStatus } from "@/lib/types/account";

const statusKey = {
  draft: "status.draft",
  sent: "status.sent",
  viewed: "status.viewed",
  filed: "status.filed",
} as const;

/**
 * The catalog key for a note status (INT-144). Exported so a card that
 * WRAPS this chip in a Pressable can put the same word in its accessible
 * name: a merged subtree is one element, and the status must survive the
 * merge rather than being the one thing that only the eye receives.
 */
export function statusLabelKey(status: NoteStatus): (typeof statusKey)[NoteStatus] {
  return statusKey[status];
}

export function StatusChip({ status }: { status: NoteStatus }) {
  const theme = useTheme();
  const colors = {
    // Draft is a filled tonal chip (design pass 5): Oura's tag register is
    // borderless — one raised step above the card carries the separation.
    draft: { bg: theme.surfaceRaised, fg: theme.inkSoft, border: theme.surfaceRaised },
    sent: { bg: theme.primarySoft, fg: theme.primary, border: theme.primarySoft },
    viewed: { bg: theme.primarySoft, fg: theme.primary, border: theme.primary },
    filed: { bg: theme.successSoft, fg: theme.success, border: theme.successSoft },
  }[status];
  return (
    <View style={[styles.chip, { backgroundColor: colors.bg, borderColor: colors.border }]}>
      <AppText role="caption" style={{ color: colors.fg, fontWeight: "600" }}>
        {t(statusKey[status])}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    alignSelf: "flex-start",
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
});
