/**
 * Welcome (02 §4 auth flow). The primary path is REAL sign-in — phone
 * verification (INT-131) at /(auth)/phone. Development builds additionally
 * offer the synthetic test accounts (INT-197 demo tier, load-bearing until
 * the OTP tier fully lands); that block is compiled out of release builds
 * via __DEV__ and renders as quiet pills so the one saturated CTA stays
 * the real sign-in (02 §5.2).
 *
 * INT-263: this screen is why that issue exists. It rendered inside a bare
 * `Screen`, so at the 2.0 rung of the INT-260 ladder the hero sat under the
 * status bar, the disclaimer was cut off, and `welcome.body` — the one line
 * that says what the app is — could not be reached by any gesture. It scrolls
 * now, and the copy is untouched: the fix is the container, not a smaller size.
 */
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

import { GlassCard } from "@/components/GlassCard";
import { Kicker } from "@/components/Kicker";
import { AppText, PrimaryButton, ScrollScreen, SecondaryButton } from "@/components/Themed";
import { testAccounts } from "@/lib/dev/accounts";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Welcome() {
  const router = useRouter();
  const { signIn } = useSession();
  return (
    <ScrollScreen contentContainerStyle={styles.content}>
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
    </ScrollScreen>
  );
}

const styles = StyleSheet.create({
  // `justifyContent` still centres the block at the sizes it fits (ScrollScreen
  // grows its content box to the viewport); above that the same content simply
  // scrolls, which is the whole change.
  content: { justifyContent: "center", gap: spacing.lg },
  hero: { gap: spacing.sm },
  devCard: { gap: spacing.sm },
  disclaimer: { textAlign: "center" },
});
