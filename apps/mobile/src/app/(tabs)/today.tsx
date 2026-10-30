/**
 * Bugün (02 §5.1): one thing at a time — the next visit and its single most
 * useful action. No feed, no engagement surface. The hero card's serif
 * department line is the focal point, and the accent appears exactly once:
 * the CTA.
 *
 * INT-594: the focus comes from `todayFocus`, i.e. from the note's real state
 * (the draft on this phone and the server's confirmed delivery, INT-587).
 * The feed's `noteStatus` alone is always null for a hospital-feed visit.
 * The design-pass-5 prep gauge is gone. It printed answered ÷ the pack's
 * questions as a bare percentage, and the flow asks conditionally, so that
 * denominator counts questions the patient may never be asked. The CTA
 * carries no duration either: nobody measured one (invariant 20).
 */
import { useRouter } from "expo-router";
import { ScrollView, StyleSheet, View } from "react-native";

import { useTabBarClearance } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import { AppText, Card, PrimaryButton, RAIL_EDGES, Screen } from "@/components/Themed";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { useDeliveries } from "@/lib/intake/delivery/store";
import { useSession } from "@/lib/session";
import { todayFocus } from "@/lib/today";
import { spacing } from "@/lib/theme";

export default function Today() {
  const router = useRouter();
  const { visits, notes } = useSession();
  const deliveries = useDeliveries();
  const focus = todayFocus(visits, notes, (id) => deliveries[id]?.stage === "delivered");

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: useTabBarClearance() }]}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("tabs.today")}
        </AppText>
        {focus.kind !== "none" ? (
          <View style={styles.section}>
            <Kicker label={t("today.nextVisit")} />
            <VisitCard visit={focus.visit} statusOverride={focus.status} hero />
            <PrimaryButton
              label={t(focus.cta)}
              onPress={() => router.push(`/(tabs)/visits/${focus.visit.id}`)}
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
  content: { gap: spacing.xl },
  heroLine: { marginTop: spacing.xl },
  section: { gap: spacing.md },
});
