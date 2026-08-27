/**
 * Welcome (02 §4 auth flow). Real sign-in (phone verification) is INT-131;
 * in development builds this screen offers the synthetic test accounts so
 * the shell can be walked end to end. The dev block is compiled out of
 * release builds via __DEV__.
 */
import { useRouter } from "expo-router";
import { StyleSheet, View } from "react-native";

import { AppText, Card, PrimaryButton, Screen } from "@/components/Themed";
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
        <AppText role="hero">{t("app.name")}</AppText>
        <AppText role="body" color="inkSoft">
          {t("app.tagline")}
        </AppText>
      </View>
      <AppText role="body">{t("welcome.body")}</AppText>
      {__DEV__ ? (
        <Card style={styles.devCard}>
          <AppText role="label" color="inkSoft">
            {t("welcome.devSignIn")}
          </AppText>
          {testAccounts.map((account) => (
            <PrimaryButton
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
        </Card>
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
