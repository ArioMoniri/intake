/**
 * Welcome (02 §4 auth flow). The primary path is REAL sign-in — phone
 * verification (INT-131) at /(auth)/phone. Development builds additionally
 * offer the synthetic test accounts (INT-197 demo tier, load-bearing until
 * the OTP tier fully lands); that block is compiled out of release builds
 * via __DEV__ and renders as quiet pills so the one saturated CTA stays
 * the real sign-in (02 §5.2).
 */
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

import { GlassCard } from "@/components/GlassCard";
import { Kicker } from "@/components/Kicker";
import { AppText, PrimaryButton, Screen, SecondaryButton } from "@/components/Themed";
import { testAccounts } from "@/lib/dev/accounts";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Welcome() {
  const router = useRouter();
  const { signIn } = useSession();
  return (
    <Screen style={styles.screen}>
      <View style={styles.hero}>
        <AppText role="hero" heading>
          {t("app.name")}
        </AppText>
        <AppText role="body" color="inkSoft">
          {t("app.tagline")}
        </AppText>
      </View>
      <AppText role="body">{t("welcome.body")}</AppText>
      <PrimaryButton label={t("welcome.phoneCta")} onPress={() => router.push("/(auth)/phone")} />
      {__DEV__ ? (
        <GlassCard style={styles.devCard}>
          <Kicker label={t("welcome.devSignIn")} />
          {testAccounts.map((account) => (
            <SecondaryButton
              key={account.id}
              label={account.name}
              onPress={() => {
                signIn(account);
                router.replace("/(tabs)/today");
              }}
            />
          ))}
          <AppText role="caption" color="inkFaint">
            {t("welcome.devNote")}
          </AppText>
        </GlassCard>
      ) : null}
      <AppText role="caption" color="inkFaint" style={styles.disclaimer}>
        {t("app.disclaimer")}
      </AppText>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: { justifyContent: "center", gap: spacing.lg },
  hero: { gap: spacing.sm },
  devCard: { gap: spacing.sm },
  disclaimer: { textAlign: "center" },
});
