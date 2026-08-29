/**
 * Hakkımda öğrendikleri (02 §4 me/learned): the transparency ledger. Every
 * durable fact the system holds about the patient appears here with where it
 * came from; nothing is learned silently (00 principles, files/09 §3).
 *
 * INT-247 fills the shell with what the app is actually holding today — the
 * facts carried out of earlier visits, each with its provenance and the day
 * it was recorded. Whether one of them is still TRUE is a question about a
 * visit, not about the ledger, so it is answered in that visit's review step
 * (invariant 12); this screen says where, rather than offering a second,
 * competing place to answer it. Editing and deleting a learned fact are the
 * DSAR-backed operations of INT-140, on the store this screen will read.
 */
import { ScrollView, StyleSheet } from "react-native";

import { CarriedFactLedger } from "@/components/CarriedFacts";
import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { AppText, Card, RAIL_EDGES, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Learned() {
  const { account } = useSession();
  const facts = account?.carriedFacts ?? [];
  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={styles.content}>
        <AppText role="hero" heading style={styles.heroLine}>
          {t("me.learned")}
        </AppText>
        <GuidanceBlock
          accent
          icon="eye"
          kickerKey="learned.guide.kicker"
          titleKey="learned.guide.title"
          bodyKey="learned.guide.body"
        />
        <Card>
          <AppText role="body" color="inkSoft">
            {facts.length === 0 ? t("me.learnedEmpty") : t("carried.ledger.body")}
          </AppText>
        </Card>
        {facts.length === 0 ? null : (
          <Card>
            <CarriedFactLedger facts={facts} />
          </Card>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl },
});
