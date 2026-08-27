/** Kayıtlarım (02 §4): patient-owned documents; upload flows are INT-138. */
import { ScrollView, StyleSheet } from "react-native";

import { AppText, Card, Screen } from "@/components/Themed";
import { formatVisitDate } from "@/components/VisitCard";
import { getLocale, t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Records() {
  const { account } = useSession();
  const records = account?.records ?? [];
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("records.title")}</AppText>
        {records.length === 0 ? (
          <Card>
            <AppText role="body" color="inkSoft">
              {t("records.empty")}
            </AppText>
          </Card>
        ) : (
          records.map((record) => (
            <Card key={record.id}>
              <AppText role="caption" color="inkSoft">
                {formatVisitDate(record.date, getLocale())}
              </AppText>
              <AppText role="body">{record.title}</AppText>
              <AppText role="caption" color="inkFaint">
                {t("records.synthetic")}
              </AppText>
            </Card>
          ))
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: spacing.xl },
});
