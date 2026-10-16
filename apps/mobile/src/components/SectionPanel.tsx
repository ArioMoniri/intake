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
 * between rows only, quiet footer); state is always labelled, never colour
 * alone (02 §8.2).
 *
 * INT-473 (ADR-038 A3): the sheet is the in-tree DetentSheet, never a
 * Modal, so no presented window can cover RED.
 */
import { Pressable, StyleSheet, View } from "react-native";

import { DetentSheet } from "@/components/DetentSheet";
import { Icon } from "@/components/Icon";
import { ListGroup } from "@/components/ListRow";
import { AppText, useScheme, useTheme } from "@/components/Themed";
import { joinParts, labelled, withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import type { SectionPanelModel, SectionRow } from "@/lib/dialogue/sectionPanel";
import { t } from "@/lib/i18n";
import { optionLabelKey } from "@/lib/intake/questions";
import { motion, radius, spacing } from "@/lib/theme";

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
  /** Opens the sheet; absent while a RED stands (INT-465), so the strip opens nothing. */
  onPress?: () => void;
}

/** The collapsed strip: quiet chrome on the dialogue's glass bar. */
export function SectionStrip({ filled, total, onPress }: SectionStripProps) {
  const theme = useTheme();
  const count = `${filled} / ${total}`;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={joinParts(
        t("dialogue.noteForming"),
        `${count} ${t("dialogue.sectionsLabel")}`,
      )}
      accessibilityHint={t("a11y.dialogue.sectionsHint")}
      // The strip is 36 pt of chrome on the glass bar; slop carries it to
      // the SC 2.5.8 floor without pushing the composer off the screen.
      hitSlop={verticalSlop(36)}
      onPress={onPress}
      disabled={onPress === undefined}
      accessibilityState={{ disabled: onPress === undefined }}
      style={({ pressed }) => [styles.strip, { opacity: pressed ? motion.press.rowOpacity : 1 }]}
    >
      <View style={[styles.stripDot, { backgroundColor: theme.primary }]} />
      <AppText role="caption" color="inkSoft" style={styles.stripLabel}>
        {t("dialogue.noteForming")}
      </AppText>
      <View style={styles.stripSpacer} />
      <AppText role="caption" color="inkFaint" style={styles.stripCount}>
        {count} {t("dialogue.sectionsLabel")}
      </AppText>
      <Icon name="chevron.up" size={11} tintColor={theme.inkFaint} />
    </Pressable>
  );
}

interface SectionRowViewProps {
  row: SectionRow;
  onConfirm: (questionId: string) => void;
}

function SectionRowView({ row, onConfirm }: SectionRowViewProps) {
  const theme = useTheme();
  const dark = useScheme() === "dark";
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
          <AppText
            role="body"
            color={row.status === "suggested" || row.status === "carried" ? "inkSoft" : "ink"}
          >
            {values.length > 0 ? values : "—"}
          </AppText>
        )}
        {row.status === "suggested" ? (
          <AppText role="caption" color="primary">
            {t("voiceFirst.suggested")}
          </AppText>
        ) : null}
        {row.status === "carried" ? (
          // INT-247: an earlier visit's record, quiet and explicitly
          // unanswered — never the weight an answered row gets.
          <AppText role="caption" color="inkFaint">
            {t("carried.kicker")} · {t("carried.state.unconfirmed")}
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
        // The row's own visible chip says "Onaylayın", so that is what the
        // name starts with (SC 2.5.3); the section and the suggested value
        // follow as the context the eye takes from the row's position.
        accessibilityLabel={withContext(t("dialogue.confirm"), labelled(t(row.labelKey), values))}
        accessibilityHint={t("a11y.confirmHint")}
        onPress={() => onConfirm(row.questionId)}
        style={({ pressed }) => [styles.row, { opacity: pressed ? motion.press.rowOpacity : 1 }]}
      >
        {body}
      </Pressable>
    );
  }
  // A settled row is one fact, so it is one accessible element: section,
  // then value, then the patient's own words as provenance. Read as four
  // separate nodes it becomes four unrelated fragments in the rotor.
  return (
    <View
      accessible
      accessibilityLabel={labelled(
        t(row.labelKey),
        joinParts(row.status === "empty" ? t("dialogue.sectionEmpty") : values, row.quote),
      )}
      style={styles.row}
    >
      {body}
    </View>
  );
}

interface SectionSheetProps {
  visible: boolean;
  /** A RED stands (INT-465): the sheet leaves in 0 ms, never fading over the RED. */
  stopped?: boolean;
  model: SectionPanelModel;
  /** Where the screen's own bar ends inside the dialogue's frame. */
  top: number;
  onClose: () => void;
  onConfirmRow: (questionId: string) => void;
}

/** The expanded sheet: every section as a grouped-table row. */
export function SectionSheet({
  visible,
  stopped = false,
  model,
  top,
  onClose,
  onConfirmRow,
}: SectionSheetProps) {
  return (
    <DetentSheet
      visible={visible}
      top={top}
      onClose={onClose}
      closeLabel={t("dialogue.close")}
      closeHint={t("a11y.closeHint")}
      // INT-465: under a standing RED the sheet leaves instantly at every
      // setting (lib/motion/sheet), never fading over the RED.
      closeReason={stopped ? "red" : "patient"}
      header={
        <View style={styles.sheetHeader}>
          <AppText role="title" heading>
            {t("dialogue.sectionsTitle")}
          </AppText>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("dialogue.close")}
            hitSlop={verticalSlop(21)}
            onPress={onClose}
          >
            <AppText role="label" color="inkSoft">
              {t("dialogue.close")}
            </AppText>
          </Pressable>
        </View>
      }
    >
      <ListGroup footer={t("dialogue.sheetHint")}>
        {model.rows.map((row) => (
          <SectionRowView key={row.questionId} row={row} onConfirm={onConfirmRow} />
        ))}
      </ListGroup>
    </DetentSheet>
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
  // Wraps (INT-295): a title role and a close control at opposite ends of a
  // fixed line collide as the text grows, and the control is the one that
  // leaves.
  sheetHeader: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.sm,
    paddingHorizontal: spacing.screen,
    paddingBottom: spacing.md,
  },
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
