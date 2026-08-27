/** Yeni vizit (02 §4): manual add; MHRS-message import lands later. */
import { ScrollView, StyleSheet } from "react-native";

import { AppText, Card, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

export default function NewVisit() {
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("visits.new.title")}</AppText>
        <Card>
          <AppText role="label">{t("visits.new.manual")}</AppText>
          <AppText role="body" color="inkSoft">
            {t("visits.new.hint")}
          </AppText>
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingBottom: spacing.xl },
});
