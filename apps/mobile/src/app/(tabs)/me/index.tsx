/**
 * Profilim (02 §4): identity, consents, language, and the "what it learned
 * about me" ledger entry point. Consents live on their own layered
 * İzinleriniz screen (INT-132) — this screen carries the permanent
 * one-tap-away entry row; only the device-local health toggle (INT-208)
 * stays inline, because it never leaves the phone and mirrors no server
 * purpose.
 *
 * Design pass 5: the Oura settings anatomy — group headers OUTSIDE the
 * groups, squarer ListGroups of 56 pt rows with hairlines between, "›" on
 * the one row that navigates, and sign-out as a quiet pill instead of the
 * screen's loudest element (the saturated accent belongs to forward
 * actions, never to leaving).
 */
import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { HealthSection } from "@/components/HealthSection";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, RAIL_EDGES, Screen, SecondaryButton, useTheme } from "@/components/Themed";
import { withContext } from "@/lib/a11y/labels";
import { verticalSlop } from "@/lib/a11y/target";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

/**
 * Tonal state pill (Oura tag register: filled, borderless; the label always
 * carries the state — colour never alone, 02 §8.2).
 */
function StatePill({
  label,
  context,
  active,
  activeColor,
  onPress,
  accessibilityRole = "button",
  checked,
  hint,
}: {
  label: string;
  /**
   * What the pill governs (INT-144). Its visible word is a state — "Açık",
   * "Türkçe" — which alone names nothing; the row supplies the subject to
   * the eye, and this supplies it to a screen reader.
   */
  context?: string;
  active: boolean;
  activeColor: "success" | "primary";
  onPress: () => void;
  accessibilityRole?: "button" | "switch";
  checked?: boolean;
  hint?: string;
}) {
  const theme = useTheme();
  const bg = active
    ? activeColor === "success"
      ? theme.successSoft
      : theme.primarySoft
    : theme.surfaceRaised;
  const fg = active ? (activeColor === "success" ? theme.success : theme.primary) : theme.inkSoft;
  return (
    <Pressable
      accessibilityRole={accessibilityRole}
      // Visible word first (SC 2.5.3), subject after.
      accessibilityLabel={withContext(label, context)}
      accessibilityHint={hint}
      accessibilityState={accessibilityRole === "switch" ? { checked } : { selected: active }}
      // 30 pt by design (Oura tag register). Slop lifts the TARGET to the
      // SC 2.5.8 floor without disturbing the 56 pt row it sits in; vertical
      // only, so the tr and en pills never swallow each other.
      hitSlop={verticalSlop(30)}
      onPress={onPress}
      style={[styles.statePill, { backgroundColor: bg }]}
    >
      <AppText role="caption" style={{ color: fg, fontWeight: "600" }}>
        {label}
      </AppText>
    </Pressable>
  );
}

export default function Me() {
  const router = useRouter();
  const { account, consents, setConsent, signOut, locale, switchLocale } = useSession();
  // Hoisted above the early return: hooks run in the same order every render.
  const tabBarClearance = useTabBarClearance();
  if (account === null || consents === null) {
    // The tabs layout has already redirected to welcome by the time this
    // renders without a session; render nothing during that frame.
    return null;
  }
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("me.title")}
        </AppText>
        <ListGroup>
          <ListRow
            icon="person.crop.circle"
            label={account.name}
            sublabel={t("me.syntheticBadge")}
          />
        </ListGroup>
        {/* Görünüm (INT-260): text size, theme, motion and how a visit
            starts. Above İzinleriniz because a patient who cannot read the
            screen cannot reach anything below it either. */}
        <ListGroup>
          <ListRow
            icon="textformat.size"
            label={t("appearance.title")}
            chevron
            hint={t("a11y.appearance.entry")}
            onPress={() => router.push("/(tabs)/me/appearance")}
          />
        </ListGroup>
        {/* İzinleriniz (INT-132): the per-purpose record moved to its own
            layered screen — every 06 §2 purpose, versioned texts, one-tap
            withdrawal. This row is the permanent one-tap-away entry. */}
        <View style={styles.section}>
          <Kicker label={t("me.consents")} />
          <ListGroup>
            <ListRow
              icon="checkmark.shield"
              label={t("me.consents")}
              sublabel={t("consent.entry.sub")}
              chevron
              hint={t("a11y.openHint")}
              onPress={() => router.push("/(tabs)/me/consents")}
            />
          </ListGroup>
        </View>
        {/* Sağlık verileri (INT-208): device-local reads behind their own
            consent. The hint states the scope honestly — read on this phone
            only, nothing sent, nothing enters a note unless the patient adds
            it. Content renders only while the consent is ON; the hint is the
            group's quiet footer (Oura's under-group explanations). */}
        <View style={styles.section}>
          <Kicker label={t("me.health")} />
          <ListGroup footer={t("consent.health.hint")}>
            <ListRow
              label={t("consent.health")}
              trailing={
                <StatePill
                  label={consents.health ? t("consent.on") : t("consent.off")}
                  context={t("consent.health")}
                  hint={t("a11y.consent.switchHint")}
                  active={consents.health}
                  activeColor="success"
                  accessibilityRole="switch"
                  checked={consents.health}
                  onPress={() => setConsent("health", !consents.health)}
                />
              }
            />
          </ListGroup>
          {consents.health ? <HealthSection /> : null}
        </View>
        <ListGroup>
          <ListRow
            label={t("me.language")}
            trailing={
              <View style={styles.langGroup}>
                {(["tr", "en"] as const).map((code) => (
                  <StatePill
                    key={code}
                    label={code === "tr" ? t("lang.tr") : t("lang.en")}
                    context={t("me.language")}
                    active={locale === code}
                    activeColor="primary"
                    onPress={() => switchLocale(code)}
                  />
                ))}
              </View>
            }
          />
          {/* Bildirimler (INT-141): opt-out and quiet hours. Its own screen
              because the quiet-window choices do not fit a settings row —
              and because the honest explanation of what a reminder never
              says belongs beside the switch that governs it. */}
          <ListRow
            label={t("me.notifications")}
            sublabel={t("notifications.entry.sub")}
            chevron
            hint={t("a11y.openHint")}
            onPress={() => router.push("/(tabs)/me/notifications")}
          />
          {/* Yakınınız adına (INT-133): who is doing this sitting, and what
              that does to the note (06 §6, 13 §13). The under-18 door lives
              on that screen too, closed with its reason on it. */}
          <ListRow
            label={t("me.companion")}
            sublabel={t("companion.entry.sub")}
            chevron
            hint={t("a11y.openHint")}
            onPress={() => router.push("/(tabs)/me/companion")}
          />
          <ListRow
            label={t("me.learned")}
            chevron
            hint={t("a11y.openHint")}
            onPress={() => router.push("/(tabs)/me/learned")}
          />
          {/* Verileriniz (INT-140): the KVKK m.11 controls — a copy of the
              record, and its erasure. Last in the group and one tap away,
              which is where a right the patient rarely exercises belongs:
              always reachable, never the loudest thing on the screen. */}
          <ListRow
            label={t("me.data")}
            sublabel={t("data.entry.sub")}
            chevron
            hint={t("a11y.openHint")}
            onPress={() => router.push("/(tabs)/me/data")}
          />
        </ListGroup>
        <SecondaryButton label={t("me.signOut")} onPress={signOut} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  statePill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
  langGroup: { flexDirection: "row", gap: spacing.xs },
});
