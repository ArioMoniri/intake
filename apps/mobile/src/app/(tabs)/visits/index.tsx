/** Vizitlerim (02 §4): upcoming then past, plus add. */
import { Link, useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { AppText, Card, PrimaryButton, Screen } from "@/components/Themed";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

const TODAY_FIXTURE = "2026-08-27";

export default function Visits() {
  const router = useRouter();
  const { account } = useSession();
  const visits = account?.visits ?? [];
  const upcoming = visits.filter((v) => v.date >= TODAY_FIXTURE);
  const past = visits.filter((v) => v.date < TODAY_FIXTURE);
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero">{t("visits.title")}</AppText>
        {visits.length === 0 ? (
          <Card>
            <AppText role="body" color="inkSoft">
              {t("visits.empty")}
            </AppText>
          </Card>
        ) : null}
        {upcoming.length > 0 ? (
          <View style={styles.section}>
            <AppText role="label" color="inkSoft">
              {t("visits.upcoming")}
            </AppText>
            {upcoming.map((visit) => (
              <Link key={visit.id} href={`/(tabs)/visits/${visit.id}`} asChild>
                <Pressable accessibilityRole="button">
                  <VisitCard visit={visit} />
                </Pressable>
              </Link>
            ))}
          </View>
        ) : null}
        {past.length > 0 ? (
          <View style={styles.section}>
            <AppText role="label" color="inkSoft">
              {t("visits.past")}
            </AppText>
            {past.map((visit) => (
              <Link key={visit.id} href={`/(tabs)/visits/${visit.id}`} asChild>
                <Pressable accessibilityRole="button">
                  <VisitCard visit={visit} />
                </Pressable>
              </Link>
            ))}
          </View>
        ) : null}
        <PrimaryButton
          label={t("today.addVisit")}
          onPress={() => router.push("/(tabs)/visits/new")}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingBottom: spacing.xl },
  section: { gap: spacing.sm },
});
