/**
 * Kayıtlarım (02 §4): patient-owned documents; upload flows are INT-138.
 * Design pass 3: the empty state is an Oura-style guidance block about the
 * product. Design pass 5: the populated list is the Oura grouped-row
 * anatomy — one squarer group, 56+ pt rows with a tonal leading icon well,
 * 17 pt sans labels, hairlines between rows — instead of a stack of content
 * cards; the synthetic marker becomes the group's single quiet footer.
 */
import { ScrollView, StyleSheet, View } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
import { AppText, RAIL_EDGES, Screen } from "@/components/Themed";
import { formatVisitDate } from "@/components/VisitCard";
import { useClinicalScreenPrivacy } from "@/lib/auth/screenPrivacy";
import { getLocale, t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Records() {
  useClinicalScreenPrivacy(); // clinical screen: FLAG_SECURE-class (INT-131)
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
            icon="folder"
            kickerKey="records.guide.kicker"
            titleKey="records.guide.title"
            bodyKey="records.guide.body"
          />
        ) : (
          <View style={styles.section}>
            <Kicker label={t("records.guide.kicker")} />
            <ListGroup footer={t("records.synthetic")}>
              {records.map((record) => (
                <ListRow
                  key={record.id}
                  icon="doc.text"
                  label={record.title}
                  sublabel={formatVisitDate(record.date, getLocale())}
                />
              ))}
            </ListGroup>
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl },
  section: { gap: spacing.sm },
});
