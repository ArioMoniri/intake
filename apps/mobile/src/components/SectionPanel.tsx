/**
 * Realtime section panel (INT-235): the collapsed "Not oluşuyor · x/y
 * bölüm" strip on the dialogue's glass bar, and the sheet it expands to —
 * the muayene sections filling in AS the conversation runs, each row
 * carrying the chosen option label plus the patient's verbatim quote as
 * provenance (display-only, never synthesized).
 *
 * Rows come from `sectionPanelModel` (pack-driven labels — buildNote's
 * mapping, never a hardcoded section list). A `suggested` row is an
 * UNCOMMITTED candidate (invariant 1): the labelled "Onaylayın" chip on
 * the row — or the row tap — is the patient's confirm; nothing fills the
 * note silently. The current turn's own candidate shows as suggested but
 * confirms in the turn, never from here (no double-commit path).
 *
 * Register: Oura grouped-table anatomy (ListGroup radii, hairlines
 * between rows only, quiet footer), fade-only motion (02 §5.2a); state is
 * always labelled, never colour alone (02 §8.2).
 */
import { Modal, Pressable, ScrollView, StyleSheet, View, useColorScheme } from "react-native";
import { SymbolView } from "expo-symbols";

import { ListGroup } from "@/components/ListRow";
import { AppText, useTheme } from "@/components/Themed";
import type { SectionPanelModel, SectionRow } from "@/lib/dialogue/sectionPanel";
import { t } from "@/lib/i18n";
import { optionLabelKey } from "@/lib/intake/questions";
import { radius, spacing } from "@/lib/theme";

/** Option ids → catalog labels; free text and meds lines pass through. */
function valueText(row: SectionRow): string {
  return row.values
    .map((value) => {
      const key = optionLabelKey(row.questionId, value);
      return key ? t(key) : value;
    })
    .join(", ");
}

interface SectionStripProps {
  filled: number;
  total: number;
  onPress: () => void;
}

/** The collapsed strip: quiet chrome on the dialogue's glass bar. */
export function SectionStrip({ filled, total, onPress }: SectionStripProps) {
  const theme = useTheme();
  const count = `${filled} / ${total}`;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${t("dialogue.noteForming")} · ${count} ${t("dialogue.sectionsLabel")}`}
      onPress={onPress}
      style={({ pressed }) => [styles.strip, { opacity: pressed ? 0.7 : 1 }]}
    >
      <View style={[styles.stripDot, { backgroundColor: theme.primary }]} />
      <AppText role="caption" color="inkSoft" style={styles.stripLabel}>
        {t("dialogue.noteForming")}
      </AppText>
      <View style={styles.stripSpacer} />
      <AppText role="caption" color="inkFaint" style={styles.stripCount}>
        {count} {t("dialogue.sectionsLabel")}
      </AppText>
      <SymbolView name="chevron.up" size={11} tintColor={theme.inkFaint} />
    </Pressable>
  );
}

interface SectionRowViewProps {
  row: SectionRow;
  onConfirm: (questionId: string) => void;
}

function SectionRowView({ row, onConfirm }: SectionRowViewProps) {
  const theme = useTheme();
  const dark = useColorScheme() === "dark";
  const values = valueText(row);
  const body = (
    <>
      <View style={styles.rowText}>
        <AppText role="caption" color="inkFaint">
          {t(row.labelKey)}
        </AppText>
        {row.status === "empty" ? (
          <AppText role="body" color="inkFaint">
            {t("dialogue.sectionEmpty")}
          </AppText>
        ) : (
          <AppText role="body" color={row.status === "suggested" ? "inkSoft" : "ink"}>
            {values.length > 0 ? values : "—"}
          </AppText>
        )}
        {row.status === "suggested" ? (
          <AppText role="caption" color="primary">
            {t("voiceFirst.suggested")}
          </AppText>
        ) : null}
        {row.quote.length > 0 ? (
          // Provenance, verbatim and DISPLAY-ONLY (invariant 2/10 posture).
          <AppText role="caption" color="inkFaint">
            “{row.quote}”
          </AppText>
        ) : null}
      </View>
      {row.confirmable ? (
        <View
          style={[
            styles.confirmChip,
            {
              backgroundColor: theme.primarySoft,
              borderColor: dark ? "transparent" : theme.primary,
            },
          ]}
        >
          <AppText role="label" color="primary">
            {t("dialogue.confirm")}
          </AppText>
        </View>
      ) : null}
    </>
  );
  if (row.confirmable) {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${t(row.labelKey)}: ${values} — ${t("dialogue.confirm")}`}
        onPress={() => onConfirm(row.questionId)}
        style={({ pressed }) => [styles.row, { opacity: pressed ? 0.7 : 1 }]}
      >
        {body}
      </Pressable>
    );
  }
  return <View style={styles.row}>{body}</View>;
}

interface SectionSheetProps {
  visible: boolean;
  model: SectionPanelModel;
  onClose: () => void;
  onConfirmRow: (questionId: string) => void;
}

/** The expanded sheet: every section as a grouped-table row. */
export function SectionSheet({ visible, model, onClose, onConfirmRow }: SectionSheetProps) {
  const theme = useTheme();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdropWrap}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("dialogue.close")}
          onPress={onClose}
          style={[StyleSheet.absoluteFill, styles.backdrop]}
        />
        <View style={[styles.sheet, { backgroundColor: theme.background }]}>
          <View style={styles.sheetHeader}>
            <AppText role="title">{t("dialogue.sectionsTitle")}</AppText>
            <Pressable accessibilityRole="button" onPress={onClose}>
              <AppText role="label" color="inkSoft">
                {t("dialogue.close")}
              </AppText>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={styles.sheetContent}>
            <ListGroup footer={t("dialogue.sheetHint")}>
              {model.rows.map((row) => (
                <SectionRowView key={row.questionId} row={row} onConfirm={onConfirmRow} />
              ))}
            </ListGroup>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  strip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs + 2,
    minHeight: 36,
    paddingBottom: spacing.xs,
  },
  stripDot: { width: 5, height: 5, borderRadius: radius.chip },
  stripLabel: { fontWeight: "600" },
  stripSpacer: { flex: 1 },
  // Tabular figures: the counter must not reflow as sections fill
  // (design pass 6 microtypography).
  stripCount: { fontVariant: ["tabular-nums"] },
  backdropWrap: { flex: 1, justifyContent: "flex-end" },
  backdrop: { backgroundColor: "rgba(0, 0, 0, 0.4)" },
  sheet: {
    borderTopLeftRadius: radius.card,
    borderTopRightRadius: radius.card,
    paddingTop: spacing.lg,
    maxHeight: "78%",
  },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.screen,
    paddingBottom: spacing.md,
  },
  sheetContent: { paddingHorizontal: spacing.screen, paddingBottom: spacing.xl },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm + 4,
    minHeight: 56,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  rowText: { flex: 1, gap: 2 },
  confirmChip: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    minHeight: 44,
    justifyContent: "center",
  },
});
