/**
 * Bugün (02 §5.1): one thing at a time — the next visit and its single most
 * useful action. No feed, no engagement surface. Design pass 3: Oura
 * framing — air above the hero line, a kicker pill instead of a plain
 * label, xl section rhythm; the hero card carries the screen's one glow.
 */
import { useRouter } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";

import { Kicker } from "@/components/Kicker";
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
        <AppText role="hero" style={styles.heroLine}>
          {t("tabs.today")}
        </AppText>
        {next ? (
          <View style={styles.section}>
            <Kicker label={t("today.nextVisit")} tone="accent" />
            <VisitCard visit={next} hero />
            <PrimaryButton
              label={next.noteStatus === "draft" ? t("today.continueCta") : t("today.prepareCta")}
              onPress={() => router.push(`/(tabs)/visits/${next.id}`)}
            />
          </View>
        ) : (
          <View style={styles.section}>
            <Kicker label={t("today.nextVisit")} tone="accent" />
            <Card>
              <AppText role="body" color="inkSoft">
                {t("today.noVisit")}
              </AppText>
            </Card>
            <PrimaryButton
              label={t("today.addVisit")}
              onPress={() => router.push("/(tabs)/visits/new")}
            />
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl, paddingBottom: spacing.xl },
  heroLine: { marginTop: spacing.lg },
  section: { gap: spacing.md },
});
