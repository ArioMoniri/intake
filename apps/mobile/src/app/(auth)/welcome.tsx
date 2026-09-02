/**
 * Welcome (02 §4 auth flow). The primary path is REAL sign-in — phone
 * verification (INT-131) at /(auth)/phone. Development builds additionally
 * offer the synthetic test accounts (INT-197 demo tier, load-bearing until
 * the OTP tier fully lands); that block is compiled out of release builds
 * via __DEV__ and renders as quiet pills so the one saturated CTA stays
 * the real sign-in (02 §5.2).
 *
 * INT-284: the screen SCROLLS. It used to centre its column in a `flex: 1`
 * box, which is fine until the column outgrows the box — flexbox centring does
 * not clip, it pushes the overflow out of BOTH ends, past the safe-area inset
 * the Screen just applied. At the largest text step INT-260 can now reach, the
 * title rendered under the notch and the footer was cut off at the physical
 * bottom edge, and a 400 pt swipe moved nothing: the copy explaining what this
 * screen IS was unreachable. `flexGrow: 1` on the scroll content keeps the
 * centring while it fits and hands the patient the rest when it does not.
 */
import { useRouter } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";

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
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
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
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  // `flexGrow` rather than `flex`: at the small steps the column is shorter
  // than the screen and centring is the design; at the large ones it is
  // taller, flexGrow stops applying, and the same container scrolls.
  content: { flexGrow: 1, justifyContent: "center", gap: spacing.lg },
  hero: { gap: spacing.sm },
  devCard: { gap: spacing.sm },
  disclaimer: { textAlign: "center" },
});
