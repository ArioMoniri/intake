/**
 * Bugün (02 §5.1): one thing at a time — the next visit and its single most
 * useful action. No feed, no engagement surface. Design pass 5: the screen
 * leads with the Oura-register focal point — a centred prep gauge (big serif
 * numeral under a thin ink arc) for the next visit's preparation — and the
 * hero card's serif department line plays the reference's headline. The
 * accent appears exactly once: the CTA.
 */
import { useRouter } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import { PrepGauge } from "@/components/PrepGauge";
import { AppText, Card, PrimaryButton, RAIL_EDGES, Screen } from "@/components/Themed";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { packForDepartment } from "@/lib/intake/questions";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Today() {
  const router = useRouter();
  const { visits, notes } = useSession();

  const next = visits.find((v) => v.noteStatus === "draft" || v.noteStatus === null) ?? null;
  const pack = next ? packForDepartment(next.department) : [];
  const answered = next
    ? (notes[next.id]?.answers.filter((a) => a.values.some((v) => v.trim().length > 0)).length ?? 0)
    : 0;
  const fraction = pack.length > 0 ? answered / pack.length : 0;

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("tabs.today")}
        </AppText>
        {next ? (
          <View style={styles.section}>
            <PrepGauge fraction={fraction} label={t("today.prep")} />
            <VisitCard visit={next} hero />
            <PrimaryButton
              label={next.noteStatus === "draft" ? t("today.continueCta") : t("today.prepareCta")}
              onPress={() => router.push(`/(tabs)/visits/${next.id}`)}
            />
          </View>
        ) : (
          <View style={styles.section}>
            <Kicker label={t("today.nextVisit")} />
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
  content: { gap: spacing.xl, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl },
  section: { gap: spacing.md },
});
