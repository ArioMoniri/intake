/**
 * Bugün (02 §5.1): one thing at a time — the next visit and its single most
 * useful action. No feed, no engagement surface.
 */
import { useRouter } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";

import { AppText, Card, PrimaryButton, Screen } from "@/components/Themed";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Today() {
  const router = useRouter();
  const { visits } = useSession();
  
  const next = visits.find((v) => v.noteStatus === "draft" || v.noteStatus === null) ?? null;
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("tabs.today")}</AppText>
        {next ? (
          <View style={styles.section}>
            <AppText role="label" color="inkSoft">
              {t("today.nextVisit")}
            </AppText>
            <VisitCard visit={next} />
            <PrimaryButton
              label={next.noteStatus === "draft" ? t("today.continueCta") : t("today.prepareCta")}
              onPress={() => router.push(`/(tabs)/visits/${next.id}`)}
            />
          </View>
        ) : (
          <Card>
            <AppText role="body" color="inkSoft">
              {t("today.noVisit")}
            </AppText>
            <PrimaryButton
              label={t("today.addVisit")}
              onPress={() => router.push("/(tabs)/visits/new")}
            />
          </Card>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingBottom: spacing.xl },
  section: { gap: spacing.sm },
});
