/**
 * Kayıtlarım (02 §4): patient-owned documents; upload flows are INT-138.
 * Design pass 3: the empty state is an Oura-style guidance block about the
 * product (what will live here, who controls sharing) instead of a lone
 * "nothing here" card; the populated list gets a kicker.
 */
import { ScrollView, StyleSheet, View } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { AppText, Card, RAIL_EDGES, Screen } from "@/components/Themed";
import { formatVisitDate } from "@/components/VisitCard";
import { getLocale, t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Records() {
  const { account } = useSession();
  const records = account?.records ?? [];
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" style={styles.heroLine}>
          {t("records.title")}
        </AppText>
        {records.length === 0 ? (
          <GuidanceBlock
            accent
            kickerKey="records.guide.kicker"
            titleKey="records.guide.title"
            bodyKey="records.guide.body"
          />
        ) : (
          <View style={styles.section}>
            <Kicker label={t("records.guide.kicker")} tone="accent" />
            {records.map((record) => (
              <Card key={record.id}>
                <AppText role="caption" color="inkSoft">
                  {formatVisitDate(record.date, getLocale())}
                </AppText>
                {/* Card hierarchy (pass 4): serif title / sans caption meta. */}
                <AppText role="title">{record.title}</AppText>
                <AppText role="caption" color="inkFaint">
                  {t("records.synthetic")}
                </AppText>
              </Card>
            ))}
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
