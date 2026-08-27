/**
 * Profilim (02 §4): identity, consents, language, and the "what it learned
 * about me" ledger entry point. Consent chips toggle SESSION-LOCAL state on
 * the synthetic accounts so the consent gate is demonstrable (flip wellbeing
 * and watch the tab appear/disappear); the real product mutates consents
 * only through the versioned consent ledger (invariant 4, INT-060s).
 */
import { Link } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AppText, Card, PrimaryButton, Screen, useTheme } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { radius, spacing } from "@/lib/theme";

function ConsentRow({ label, on, onToggle }: { label: string; on: boolean; onToggle: () => void }) {
  const theme = useTheme();
  return (
    <View style={styles.consentRow}>
      <AppText role="body">{label}</AppText>
      <Pressable
        accessibilityRole="switch"
        accessibilityLabel={label}
        accessibilityState={{ checked: on }}
        onPress={onToggle}
        style={[
          styles.consentPill,
          {
            backgroundColor: on ? theme.successSoft : theme.background,
            borderColor: on ? theme.success : theme.border,
          },
        ]}
      >
        <AppText
          role="caption"
          style={{ color: on ? theme.success : theme.inkSoft, fontWeight: "600" }}
        >
          {on ? t("consent.on") : t("consent.off")}
        </AppText>
      </Pressable>
    </View>
  );
}

function LanguageRow() {
  const theme = useTheme();
  const { locale, switchLocale } = useSession();
  return (
    <View style={styles.consentRow}>
      <AppText role="body">{t("me.language")}</AppText>
      <View style={styles.langGroup}>
        {(["tr", "en"] as const).map((code) => {
          const active = locale === code;
          return (
            <Pressable
              key={code}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              onPress={() => switchLocale(code)}
              style={[
                styles.consentPill,
                {
                  backgroundColor: active ? theme.primarySoft : theme.background,
                  borderColor: active ? theme.primary : theme.border,
                },
              ]}
            >
              <AppText
                role="caption"
                style={{ color: active ? theme.primary : theme.inkSoft, fontWeight: "600" }}
              >
                {code === "tr" ? t("lang.tr") : t("lang.en")}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export default function Me() {
  const { account, consents, setConsent, signOut } = useSession();
  if (account === null || consents === null) {
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
          <ConsentRow
            label={t("consent.core")}
            on={consents.core}
            onToggle={() => setConsent("core", !consents.core)}
          />
          <ConsentRow
            label={t("consent.voice")}
            on={consents.voice}
            onToggle={() => setConsent("voice", !consents.voice)}
          />
          <ConsentRow
            label={t("consent.wellbeing")}
            on={consents.wellbeing}
            onToggle={() => setConsent("wellbeing", !consents.wellbeing)}
          />
          <ConsentRow
            label={t("consent.documents")}
            on={consents.documents}
            onToggle={() => setConsent("documents", !consents.documents)}
          />
        </Card>
        <Card>
          <LanguageRow />
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
  langGroup: { flexDirection: "row", gap: spacing.xs },
});
