/**
 * Profilim (02 §4): identity, consents at a glance, language, and the
 * "what it learned about me" ledger entry point. Consent TOGGLING is a
 * consent-ledger operation (INT-060s) — here they are read-only chips.
 */
import { Link } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AppText, Card, PrimaryButton, Screen, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

function ConsentRow({ label, on }: { label: string; on: boolean }) {
  const theme = useTheme();
  return (
    <View style={styles.consentRow}>
      <AppText role="body">{label}</AppText>
      <View
        style={[
          styles.consentPill,
          {
            backgroundColor: on ? theme.successSoft : theme.background,
            borderColor: on ? theme.successSoft : theme.border,
          },
        ]}
      >
        <AppText
          role="caption"
          style={{ color: on ? theme.success : theme.inkSoft, fontWeight: "600" }}
        >
          {on ? t("consent.on") : t("consent.off")}
        </AppText>
      </View>
    </View>
  );
}

export default function Me() {
  const { account, signOut } = useSession();
  if (account === null) {
    // The tabs layout has already redirected to welcome by the time this
    // renders without a session; render nothing during that frame.
    return null;
  }
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("me.title")}</AppText>
        <Card>
          <AppText role="title">{account.name}</AppText>
          <AppText role="caption" color="inkFaint">
            {t("me.syntheticBadge")}
          </AppText>
        </Card>
        <Card>
          <AppText role="label" color="inkSoft">
            {t("me.consents")}
          </AppText>
          <ConsentRow label={t("consent.core")} on={account.consents.core} />
          <ConsentRow label={t("consent.voice")} on={account.consents.voice} />
          <ConsentRow label={t("consent.wellbeing")} on={account.consents.wellbeing} />
          <ConsentRow label={t("consent.documents")} on={account.consents.documents} />
        </Card>
        <Link href="/(tabs)/me/learned" asChild>
          <Pressable accessibilityRole="button">
            <Card>
              <AppText role="body">{t("me.learned")}</AppText>
            </Card>
          </Pressable>
        </Link>
        <PrimaryButton label={t("me.signOut")} onPress={signOut} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: spacing.xl },
  consentRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  consentPill: {
    borderRadius: radius.chip,
    borderWidth: 1,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs,
  },
});
