/**
 * Hakkımda öğrendikleri (02 §4 me/learned): the transparency ledger. Every
 * durable fact the system holds about the patient appears here with where it
 * came from; nothing is learned silently (00 principles, files/09 §3).
 *
 * INT-247 filled the shell with the facts this device carries out of earlier
 * visits. INT-140 makes the screen the thing files/09 §3 actually asks for:
 * the ledger reads the patient's own overlay through `/v1/me/learned`
 * (INT-170), each fact keeps its provenance, its share scope is per field,
 * and deleting one deletes it — from the record when the record holds it,
 * from this phone when this phone does.
 *
 * What the screen still does NOT do, and why: it does not answer the
 * twelve-month re-confirmation question. Answering needs the origin and the
 * observed instant of the candidate behind a fact, which the ledger does not
 * hold; minting either would be minting a provenance (invariant 12). Whether
 * a fact is still TRUE is a question about a visit, so it stays in that
 * visit's review step and the ledger says so.
 */
import { useEffect } from "react";
import { ScrollView, StyleSheet } from "react-native";

import { AnnouncedText } from "@/components/Announced";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { GuidanceBlock } from "@/components/GuidanceBlock";
import { LearnedLedger } from "@/components/LearnedLedger";
import { AppText, Card, RAIL_EDGES, Screen } from "@/components/Themed";
import { t } from "@/lib/i18n";
import {
  forgetFact,
  loadLearnedLedger,
  seedLearnedLedger,
  setFactShared,
  useLearnedLedger,
} from "@/lib/learned/store";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function Learned() {
  const { account } = useSession();
  const { facts, unsaved } = useLearnedLedger();
  const tabBarClearance = useTabBarClearance();
  const accountId = account?.id ?? null;
  const carried = account?.carriedFacts;

  useEffect(() => {
    if (accountId === null) {
      return;
    }
    seedLearnedLedger(accountId, carried ?? []);
    void loadLearnedLedger();
  }, [accountId, carried]);

  return (
    <Screen edges={RAIL_EDGES}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
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
        <LearnedLedger
          facts={facts}
          onShare={(id, shared) => void setFactShared(id, shared)}
          onForget={(id) => void forgetFact(id)}
        />
        {unsaved ? (
          // SC 3.3.1: the change the patient just made did not reach their
          // record — announced as an error on both platforms (INT-362).
          <AnnouncedText
            tone="error"
            role="caption"
            color="inkSoft"
            message={t("learned.unsaved")}
          />
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.xl },
  heroLine: { marginTop: spacing.xl },
});
