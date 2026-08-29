/**
 * Bildirimler (INT-141): the patient's own opt-out and quiet window.
 *
 * Two things this screen deliberately does NOT have. There is no toggle for
 * anything other than reminders — a promotional switch would imply a consent
 * this product cannot collect and must not appear to hold. And there is no
 * pre-selected quiet window: files/10 §9 names the control, no file names an
 * hour, so the screen offers choices and starts with none of them chosen.
 *
 * The state lives on the server, not the phone: a quiet-hours setting the
 * scheduler cannot read is decoration, and one that only lives here would
 * vanish with the device.
 *
 * Design pass 5 register (the Oura settings anatomy): group headers outside
 * the groups, 56 pt rows with hairlines between, tonal state pills, and the
 * honest explanation as the group's quiet footer.
 */
import { useEffect } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, RAIL_EDGES, Screen, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import {
  QUIET_PRESETS,
  clearQuietWindow,
  isPresetSelected,
  withOptOut,
  withQuietWindow,
  type QuietPreset,
} from "@/lib/notifications/preferences";
import {
  loadNotificationPrefs,
  saveNotificationPrefs,
  useNotificationPrefs,
} from "@/lib/notifications/store";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

function TonalPill({
  label,
  context,
  active,
  hint,
  role = "button",
  checked,
  onPress,
}: {
  label: string;
  context: string;
  active: boolean;
  hint: string;
  role?: "button" | "switch";
  checked?: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  const background = active ? theme.successSoft : theme.surfaceRaised;
  const foreground = active ? theme.success : theme.inkSoft;
  return (
    <Pressable
      accessibilityRole={role}
      // Visible word first (SC 2.5.3), the subject after (INT-144).
      accessibilityLabel={withContext(label, context)}
      accessibilityHint={hint}
      accessibilityState={role === "switch" ? { checked } : { selected: active }}
      hitSlop={verticalSlop(30)}
      onPress={onPress}
      style={[styles.pill, { backgroundColor: background }]}
    >
      <AppText role="caption" style={{ color: foreground, fontWeight: "600" }}>
        {label}
      </AppText>
    </Pressable>
  );
}

export default function Notifications() {
  const { account } = useSession();
  const { prefs, pending } = useNotificationPrefs();
  const accountId = account?.id ?? null;

  useEffect(() => {
    if (accountId !== null) {
      void loadNotificationPrefs(accountId);
    }
  }, [accountId]);

  const remindersOn = !prefs.optedOut;
  const windowLabel =
    prefs.quietStart !== null && prefs.quietEnd !== null
      ? `${prefs.quietStart} – ${prefs.quietEnd}`
      : t("notifications.quietNone");

  const chooseWindow = (window: QuietPreset) => {
    const next = isPresetSelected(prefs, window)
      ? clearQuietWindow(prefs)
      : withQuietWindow(prefs, window);
    void saveNotificationPrefs(next);
  };

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("notifications.title")}
        </AppText>
        <GuidanceBlock
          accent
          icon="bell"
          kickerKey="notifications.guide.kicker"
          titleKey="notifications.guide.title"
          bodyKey="notifications.guide.body"
        />
        <ListGroup footer={t("notifications.optOutHint")}>
          <ListRow
            label={t("notifications.switchLabel")}
            trailing={
              <TonalPill
                label={remindersOn ? t("notifications.on") : t("notifications.off")}
                context={t("notifications.switchLabel")}
                hint={t("a11y.notifications.switchHint")}
                active={remindersOn}
                role="switch"
                checked={remindersOn}
                onPress={() => void saveNotificationPrefs(withOptOut(prefs, remindersOn))}
              />
            }
          />
        </ListGroup>
        <View style={styles.section}>
          <Kicker label={t("notifications.quiet")} />
          <ListGroup footer={t("notifications.quietHint")}>
            <ListRow label={t("notifications.quiet")} sublabel={windowLabel} />
            {QUIET_PRESETS.map((window) => (
              <ListRow
                key={window.start}
                label={`${window.start} – ${window.end}`}
                trailing={
                  <TonalPill
                    label={
                      isPresetSelected(prefs, window)
                        ? t("notifications.on")
                        : t("notifications.off")
                    }
                    context={`${window.start} – ${window.end}`}
                    hint={t("a11y.notifications.quietHint")}
                    active={isPresetSelected(prefs, window)}
                    role="switch"
                    checked={isPresetSelected(prefs, window)}
                    onPress={() => chooseWindow(window)}
                  />
                }
              />
            ))}
          </ListGroup>
        </View>
        <AppText role="caption" color="inkSoft">
          {t("notifications.contentFree")}
        </AppText>
        <AppText role="caption" color="inkSoft">
          {t("notifications.transactionalOnly")}
        </AppText>
        {pending ? (
          <AppText role="caption" color="inkSoft">
            {t("notifications.pending")}
          </AppText>
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  pill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
});
