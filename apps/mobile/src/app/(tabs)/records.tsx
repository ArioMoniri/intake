/** Kayıtlarım (02 §4): patient-owned documents; upload flows are INT-133+. */
import { ScrollView, StyleSheet } from "react-native";

import { AppText, Card, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Records() {
  const { account } = useSession();
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("records.title")}</AppText>
        <Card>
          <AppText role="body" color="inkSoft">
            {t("records.empty")}
          </AppText>
          {account ? (
            <AppText role="caption" color="inkFaint">
              {t("records.synthetic")}
            </AppText>
          ) : null}
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingBottom: spacing.xl },
});
