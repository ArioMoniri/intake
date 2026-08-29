/**
 * Hakkımda öğrendikleri (02 §4 me/learned): the transparency ledger. Every
 * durable fact the system holds about the patient appears here with a way to
 * remove it; nothing is learned silently (00 principles). Data arrives with
 * the memory/consent services — the shell states the promise as an
 * Oura-style guidance block (design pass 3).
 */
import { ScrollView, StyleSheet } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { AppText, Card, RAIL_EDGES, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

export default function Learned() {
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
            {t("me.learnedEmpty")}
          </AppText>
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl, paddingBottom: TAB_BAR_CLEARANCE },
  heroLine: { marginTop: spacing.xl },
});
