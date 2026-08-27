/**
 * İyilik hâli (02 §4): exists in the rail only after the wellbeing consent
 * is ON (gate lives in the tabs layout via `visibleTabs`). Content here is
 * the WHO-5-family surface — BLOCKED on licence (HB-L2), so the shell only
 * frames the space without any screening items.
 */
import { ScrollView, StyleSheet } from "react-native";

import { AppText, Card, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

export default function Wellbeing() {
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("wellbeing.title")}</AppText>
        <AppText role="body" color="inkSoft">
          {t("wellbeing.intro")}
        </AppText>
        <Card>
          <AppText role="body" color="inkSoft">
            {t("wellbeing.empty")}
          </AppText>
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingBottom: spacing.xl },
});
