/**
 * Visit detail (02 §4): the visit, its note's place on the 02 §5.1 status
 * ladder, and the one next action — prepare (intake) or review. The
 * conversation/orb surface is INT-132+; this screen frames it.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { ScrollView, StyleSheet } from "react-native";

import { TAB_BAR_CLEARANCE } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import { StatusLadder } from "@/components/StatusLadder";
import {
  AppText,
  Card,
  Hairline,
  PrimaryButton,
  Screen,
  useStackHeader,
} from "@/components/Themed";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { effectiveStatus } from "@/lib/intake/note";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

/** Pushed screens keep left/right only: the header owns the top inset. */
const HEADER_EDGES = ["left", "right"] as const;

export default function VisitDetail() {
  const router = useRouter();
  const headerOptions = useStackHeader();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { visits, notes } = useSession();
  const visit = visits.find((v) => v.id === visitId) ?? null;
  if (visit === null) {
    return (
      <Screen>
        <Stack.Screen options={headerOptions(t("visits.title"))} />
        <AppText role="body" color="inkSoft">
          {t("visits.empty")}
        </AppText>
      </Screen>
    );
  }
  const note = notes[visit.id];
  const status = effectiveStatus(visit.noteStatus, note);
  const hasAnswers = (note?.answers.length ?? 0) > 0;
  return (
    <Screen edges={HEADER_EDGES}>
      {/* Oura framing (design pass 5): every pushed screen carries the
          centred-title bar with the "‹" affordance — nothing before this
          pass offered a visible way back. */}
      <Stack.Screen options={headerOptions(visit.department)} />
      <ScrollView contentContainerStyle={styles.content}>
        <VisitCard visit={visit} statusOverride={status} />
        <Card style={styles.ladderCard}>
          <Kicker label={t("visits.detail.noteStatus")} />
          <Hairline />
          {status === null ? (
            <AppText role="body" color="inkSoft">
              {t("visits.detail.notStarted")}
            </AppText>
          ) : (
            <StatusLadder current={status} />
          )}
        </Card>
        {status === "sent" ? (
          <AppText role="caption" color="inkSoft">
            {t("review.sentInfo")}
          </AppText>
        ) : status === null || status === "draft" ? (
          hasAnswers ? (
            <PrimaryButton
              label={t("visit.reviewNote")}
              onPress={() => router.push(`/(tabs)/visits/${visit.id}/review`)}
            />
          ) : (
            <PrimaryButton
              label={t("visit.prepare")}
              onPress={() => router.push(`/(tabs)/visits/${visit.id}/intake`)}
            />
          )
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.lg, paddingTop: spacing.md, paddingBottom: TAB_BAR_CLEARANCE },
  ladderCard: { gap: spacing.md },
});
