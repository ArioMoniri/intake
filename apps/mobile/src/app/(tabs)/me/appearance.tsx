/**
 * Görünüm (INT-260) — the owner's ask: "also make text size and other
 * settings adjustable".
 *
 * Anatomy, top to bottom: the live PREVIEW first, then the groups. Putting the
 * preview above the control is what the reference display-settings screens do,
 * and it is the only way a size control can be honest — the patient judges the
 * size by reading real product text at it, not by reading the word "Büyük".
 *
 * The preview is real catalogue copy: one agent bubble rendering the pack's
 * own opening question, one option chip, one status line. It is NOT a
 * fabricated patient utterance — a plausible complaint would be demo clinical
 * data on a shipped screen (invariant 17).
 *
 * Four groups, and every one of them has a consumer today:
 *   Yazı boyutu       → useFontScale (Themed.tsx)
 *   Tema              → useScheme (Themed.tsx)
 *   Hareket           → useReducedMotion (lib/a11y/prefs.ts)
 *   Ziyarete başlarken → the intake shell's voice-eligibility rule
 * A "Sesli okuma" switch belongs here too and is deliberately ABSENT: its only
 * consumer is the spoken-dialogue surface, and a switch whose value nothing
 * reads is decoration with a nice pill on it. It lands with that surface.
 *
 * The screen has to survive its own largest setting — a settings screen that
 * breaks at its own maximum is the worst possible failure — so nothing here is
 * a fixed-height box, the segmented control stacks at ≥1.6, and the evidence
 * carries simulator captures at both ends of the ladder.
 */
import { ScrollView, StyleSheet, View, useWindowDimensions } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import { ListGroup } from "@/components/ListRow";
import { Segmented, type SegmentedOption } from "@/components/Segmented";
import { SwitchRow } from "@/components/SwitchRow";
import { AppText, Card, RAIL_EDGES, Screen, useTheme } from "@/components/Themed";
import { t, type MessageKey } from "@/lib/i18n";
import { nearestStep, type StartMode, type TextStep, type ThemePref } from "@/lib/prefs/appearance";
import { useAppearance } from "@/lib/prefs/AppearanceProvider";
import { radius, spacing } from "@/lib/theme";

/**
 * Option tables carry KEYS, not strings: `t()` reads a module-level catalogue
 * and a module-scope call would freeze these labels in whichever language the
 * bundle happened to import under. They resolve at render, like every other
 * option table in the app.
 */
const SIZE_KEYS: readonly { id: string; key: MessageKey }[] = [
  { id: "0", key: "appearance.size.s" },
  { id: "1", key: "appearance.size.m" },
  { id: "2", key: "appearance.size.l" },
  { id: "3", key: "appearance.size.xl" },
  { id: "4", key: "appearance.size.xxl" },
];

const THEME_KEYS: readonly { id: string; key: MessageKey }[] = [
  { id: "system", key: "appearance.theme.system" },
  { id: "light", key: "appearance.theme.light" },
  { id: "dark", key: "appearance.theme.dark" },
];

const START_KEYS: readonly { id: string; key: MessageKey }[] = [
  { id: "voice", key: "appearance.start.voice" },
  { id: "typed", key: "appearance.start.typed" },
];

function labelled(
  rows: readonly { id: string; key: MessageKey }[],
): readonly SegmentedOption[] {
  return rows.map((row) => ({ id: row.id, label: t(row.key) }));
}

/**
 * One agent bubble, one chip, one status line — rendered at whatever scale is
 * currently chosen, because every line in it goes through AppText.
 */
function Preview() {
  const theme = useTheme();
  return (
    <Card>
      <View
        accessible
        accessibilityLabel={t("a11y.appearance.preview")}
        style={styles.preview}
      >
        <View style={[styles.bubble, { backgroundColor: theme.surfaceRaised }]}>
          <AppText role="body">{t("intake.q.complaint")}</AppText>
        </View>
        <View style={styles.chipRow}>
          <View style={[styles.chip, { backgroundColor: theme.primarySoft }]}>
            <AppText role="label" color="primary">
              {t("intake.opt.pain")}
            </AppText>
          </View>
        </View>
        <AppText role="caption" color="inkSoft">
          {t("voiceFirst.listening")}
        </AppText>
      </View>
    </Card>
  );
}

export default function Appearance() {
  const { prefs, update } = useAppearance();
  // The OS value, read directly: it is what "Telefon ayarını kullanın" means,
  // and it is the anchor for the first app step when that switch goes off.
  const osFontScale = useWindowDimensions().fontScale;
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: useTabBarClearance() }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("appearance.title")}
        </AppText>

        <View style={styles.section}>
          <Kicker label={t("appearance.preview")} />
          <Preview />
        </View>

        <View style={styles.section}>
          <Kicker label={t("appearance.textSize")} />
          <Segmented
            label={t("appearance.textSize")}
            hint={t("a11y.appearance.size")}
            options={labelled(SIZE_KEYS)}
            // `null` while the phone decides: no rung is the patient's choice,
            // so none is shown as one.
            value={prefs.textStep === null ? null : String(prefs.textStep)}
            onChange={(id) => update({ textStep: Number(id) as TextStep })}
          />
          <ListGroup footer={t("appearance.overrideNote")}>
            <SwitchRow
              label={t("appearance.textSize.phone")}
              hint={t("a11y.appearance.phone")}
              checked={prefs.textStep === null}
              // Turning it OFF must not resize the screen under the finger
              // that turned it off, so the first app value is the rung nearest
              // whatever is already on screen.
              onChange={(next) =>
                update({ textStep: next ? null : nearestStep(osFontScale) })
              }
            />
          </ListGroup>
        </View>

        <View style={styles.section}>
          <Kicker label={t("appearance.theme")} />
          <Segmented
            label={t("appearance.theme")}
            hint={t("a11y.appearance.theme")}
            options={labelled(THEME_KEYS)}
            value={prefs.theme}
            onChange={(id) => update({ theme: id as ThemePref })}
          />
        </View>

        <View style={styles.section}>
          <Kicker label={t("appearance.motion")} />
          <ListGroup footer={t("appearance.motionNote")}>
            <SwitchRow
              label={t("appearance.motion")}
              hint={t("a11y.appearance.motion")}
              checked={prefs.reduceMotion}
              onChange={(next) => update({ reduceMotion: next })}
            />
          </ListGroup>
        </View>

        <View style={styles.section}>
          <Kicker label={t("appearance.start")} />
          <Segmented
            label={t("appearance.start")}
            hint={t("a11y.appearance.start")}
            options={labelled(START_KEYS)}
            value={prefs.startMode}
            onChange={(id) => update({ startMode: id as StartMode })}
          />
        </View>

        <AppText role="caption" color="inkSoft">
          {t("appearance.deviceOnly")}
        </AppText>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  preview: { gap: spacing.sm },
  bubble: {
    alignSelf: "flex-start",
    maxWidth: "92%",
    borderRadius: radius.group,
    borderBottomLeftRadius: 6,
    padding: spacing.md,
  },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
});
