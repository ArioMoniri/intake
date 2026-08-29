/**
 * Vizitlerim (02 §4): upcoming then past, plus add. Design pass 3: kicker
 * pills over the groups, xl rhythm between them, air above the hero line.
 */
import { Link, useRouter } from "expo-router";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import { AppText, Card, RAIL_EDGES, Screen, SecondaryButton } from "@/components/Themed";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";
import { splitVisits } from "@/lib/visits";

const TODAY_FIXTURE = "2026-08-27";

export default function Visits() {
  const router = useRouter();
  const { visits } = useSession();

  // a dateless visit is upcoming, not past (INT-134) — see splitVisits
  const { upcoming, past } = splitVisits(visits, TODAY_FIXTURE);
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" style={styles.heroLine}>
          {t("visits.title")}
        </AppText>
        {visits.length === 0 ? (
          <Card>
            <AppText role="body" color="inkSoft">
              {t("visits.empty")}
            </AppText>
          </Card>
        ) : null}
        {upcoming.length > 0 ? (
          <View style={styles.section}>
            {/* Neutral like Oura's quiet group headings (design pass 5) —
                the accent budget belongs to the screen's one action. */}
            <Kicker label={t("visits.upcoming")} />
            {upcoming.map((visit) => (
              <Link key={visit.id} href={`/(tabs)/visits/${visit.id}`} asChild>
                <Pressable accessibilityRole="button">
                  <VisitCard visit={visit} chevron />
                </Pressable>
              </Link>
            ))}
          </View>
        ) : null}
        {past.length > 0 ? (
          <View style={styles.section}>
            <Kicker label={t("visits.past")} />
            {past.map((visit) => (
              <Link key={visit.id} href={`/(tabs)/visits/${visit.id}`} asChild>
                <Pressable accessibilityRole="button">
                  <VisitCard visit={visit} chevron />
                </Pressable>
              </Link>
            ))}
          </View>
        ) : null}
        {/* Adding is available, not urgent — the Oura register keeps list
            screens free of saturated CTAs (design pass 5). */}
        <SecondaryButton
          label={t("today.addVisit")}
          onPress={() => router.push("/(tabs)/visits/new")}
        />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl },
  section: { gap: spacing.md },
});
