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
 *
 * Motion (INT-338, MOTION-9): the platform never animates the sheet, and
 * its content enters with the one fade and leaves at once, for any reason
 * it closes (lib/motion/transitions.ts `modalTransition`).
 */
import { useEffect, useRef, type Ref, type RefObject } from "react";
import { AccessibilityInfo, Modal, Pressable, ScrollView, StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";
import { SymbolView } from "expo-symbols";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { ListGroup } from "@/components/ListRow";
import { AppText, useScheme, useTheme } from "@/components/Themed";
import { joinParts, labelled, withContext } from "@/lib/a11y/labels";
import { ALL_ORIENTATIONS } from "@/lib/a11y/orientation";
import { useReducedMotion } from "@/lib/a11y/prefs";
import { MIN_TAP, verticalSlop } from "@/lib/a11y/target";
import type { SectionPanelModel, SectionRow } from "@/lib/dialogue/sectionPanel";
import { t } from "@/lib/i18n";
import { optionLabelKey } from "@/lib/intake/questions";
import { enteringFor } from "@/lib/motion/native/reanimated";
import { modalTransition } from "@/lib/motion/transitions";
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
  onPress: () => void;
  /**
   * The strip's host view: the sheet it opens hands the screen reader's
   * focus back to it on close (INT-338, SC 2.4.3).
   */
  ref?: Ref<View>;
}

/** The collapsed strip: quiet chrome on the dialogue's glass bar. */
export function SectionStrip({ filled, total, onPress, ref }: SectionStripProps) {
  const theme = useTheme();
  const count = `${filled} / ${total}`;
  return (
    <Pressable
      ref={ref}
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
  model: SectionPanelModel;
  onClose: () => void;
  onConfirmRow: (questionId: string) => void;
  /** The control that opened the sheet: focus returns to it on close. */
  opener: RefObject<View | null>;
}

/** The expanded sheet: every section as a grouped-table row. */
export function SectionSheet({ visible, model, onClose, onConfirmRow, opener }: SectionSheetProps) {
  const theme = useTheme();
  const reduceMotion = useReducedMotion();
  const transition = modalTransition({ reduce: reduceMotion });
  // INT-360: a Modal is its own window, so the Screen's safe edges do not
  // reach the sheet. In landscape the notch and the rounded corners are at
  // the SIDES, so the sheet takes the side insets itself, and the bottom one
  // for the home indicator.
  const insets = useSafeAreaInsets();
  // SC 2.4.3 (INT-338): a sheet that closes hands the screen reader's focus
  // back to the strip that opened it, in the first effect after the close
  // and with no delay. iOS's modal host restores VoiceOver's last focus on
  // dismissal by itself; Android's does not, so the app names the target on
  // both. Only a close moves it: the first mount opened nothing.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (visible) {
      wasOpen.current = true;
      return;
    }
    const target = opener.current;
    if (wasOpen.current && target !== null) {
      AccessibilityInfo.sendAccessibilityEvent(target, "focus");
    }
    wasOpen.current = false;
  }, [visible, opener]);
  return (
    <Modal
      visible={visible}
      transparent
      // INT-338: the platform never animates the sheet ("none" at every
      // setting), so every close, the privacy hide and a RED's included, is
      // gone in the commit that makes it.
      animationType={transition.animationType}
      // SC 1.3.4 (INT-360): without this list React Native presents the Modal
      // portrait-only on an iPhone, and opening the sheet in landscape would
      // turn the screen under the patient.
      supportedOrientations={ALL_ORIENTATIONS}
      onRequestClose={onClose}
    >
      {/* The dismiss backdrop and the panel are ONE animated element: they
          enter together with the one fade (none under reduce-motion) and
          carry no exit, so nothing of the sheet outlives its close. */}
      <Animated.View entering={enteringFor(transition.enter)} style={styles.backdropWrap}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("dialogue.close")}
          accessibilityHint={t("a11y.closeHint")}
          onPress={onClose}
          style={[StyleSheet.absoluteFill, styles.backdrop]}
        />
        {/* SC 2.4.3: the modal flag belongs HERE, not on <Modal>. React
            Native's Modal enumerates the props it forwards to the native
            host view (Libraries/Modal/Modal.js) and `accessibilityViewIsModal`
            is not among them — set there it type-checks and does nothing.
            On the sheet it does the real work: the dismiss backdrop and
            anything behind leave the accessibility tree, so a swipe cannot
            walk out of the sheet into content the eye cannot see. Dismissal
            stays reachable through the labelled close control below. */}
        <View
          accessibilityViewIsModal
          style={[
            styles.sheet,
            {
              backgroundColor: theme.background,
              paddingLeft: insets.left,
              paddingRight: insets.right,
              paddingBottom: insets.bottom,
            },
          ]}
        >
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
          <ScrollView contentContainerStyle={styles.sheetContent}>
            <ListGroup footer={t("dialogue.sheetHint")}>
              {model.rows.map((row) => (
                <SectionRowView key={row.questionId} row={row} onConfirm={onConfirmRow} />
              ))}
            </ListGroup>
          </ScrollView>
        </View>
      </Animated.View>
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
  // The dismiss backdrop covers the screen behind the sheet; the floor is
  // declared rather than inherited from absoluteFill (SC 2.5.8).
  backdrop: { backgroundColor: "rgba(0, 0, 0, 0.4)", minHeight: MIN_TAP },
  sheet: {
    borderTopLeftRadius: radius.card,
    borderTopRightRadius: radius.card,
    paddingTop: spacing.lg,
    maxHeight: "78%",
  },
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
