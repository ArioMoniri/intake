/**
 * Profilim (02 §4): identity, consents, language, and the "what it learned
 * about me" ledger entry point. Consent chips toggle SESSION-LOCAL state on
 * the synthetic accounts so the consent gate is demonstrable (flip wellbeing
 * and watch the tab appear/disappear); the real product mutates consents
 * only through the versioned consent ledger (invariant 4, INT-060s).
 *
 * Design pass 5: the Oura settings anatomy — group headers OUTSIDE the
 * groups, squarer ListGroups of 56 pt rows with hairlines between, "›" on
 * the one row that navigates, and sign-out as a quiet pill instead of the
 * screen's loudest element (the saturated accent belongs to forward
 * actions, never to leaving).
 */
import { useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { HealthSection } from "@/components/HealthSection";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, RAIL_EDGES, Screen, SecondaryButton, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

/**
 * Tonal state pill (Oura tag register: filled, borderless; the label always
 * carries the state — colour never alone, 02 §8.2).
 */
function StatePill({
  label,
  active,
  activeColor,
  onPress,
  accessibilityRole = "button",
  checked,
}: {
  label: string;
  active: boolean;
  activeColor: "success" | "primary";
  onPress: () => void;
  accessibilityRole?: "button" | "switch";
  checked?: boolean;
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
      accessibilityLabel={label}
      accessibilityState={accessibilityRole === "switch" ? { checked } : { selected: active }}
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
  if (account === null || consents === null) {
    // The tabs layout has already redirected to welcome by the time this
    // renders without a session; render nothing during that frame.
    return null;
  }
  const consentRows = [
    { key: "core" as const, label: t("consent.core") },
    { key: "voice" as const, label: t("consent.voice") },
    { key: "wellbeing" as const, label: t("consent.wellbeing") },
    { key: "documents" as const, label: t("consent.documents") },
  ];
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" style={styles.heroLine}>
          {t("me.title")}
        </AppText>
        <ListGroup>
          <ListRow
            icon="person.crop.circle"
            label={account.name}
            sublabel={t("me.syntheticBadge")}
          />
        </ListGroup>
        <View style={styles.section}>
          <Kicker label={t("me.consents")} />
          <ListGroup>
            {consentRows.map((row) => (
              <ListRow
                key={row.key}
                label={row.label}
                trailing={
                  <StatePill
                    label={consents[row.key] ? t("consent.on") : t("consent.off")}
                    active={consents[row.key]}
                    activeColor="success"
                    accessibilityRole="switch"
                    checked={consents[row.key]}
                    onPress={() => setConsent(row.key, !consents[row.key])}
                  />
                }
              />
            ))}
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
                    active={locale === code}
                    activeColor="primary"
                    onPress={() => switchLocale(code)}
                  />
                ))}
              </View>
            }
          />
          <ListRow
            label={t("me.learned")}
            chevron
            onPress={() => router.push("/(tabs)/me/learned")}
          />
        </ListGroup>
        <SecondaryButton label={t("me.signOut")} onPress={signOut} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl, marginBottom: spacing.sm },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  statePill: {
    borderRadius: radius.chip,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.xs + 2,
  },
  langGroup: { flexDirection: "row", gap: spacing.xs },
});
