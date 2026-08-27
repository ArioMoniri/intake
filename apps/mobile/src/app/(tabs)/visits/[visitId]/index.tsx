/**
 * Visit detail (02 §4): the visit, its note's place on the 02 §5.1 status
 * ladder, and the one next action — prepare (intake) or review. The
 * conversation/orb surface is INT-132+; this screen frames it.
 */
import { useLocalSearchParams, useRouter } from "expo-router";
import { ScrollView, StyleSheet } from "react-native";

import { StatusLadder } from "@/components/StatusLadder";
import { AppText, Card, PrimaryButton, Screen } from "@/components/Themed";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { effectiveStatus } from "@/lib/intake/note";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function VisitDetail() {
  const router = useRouter();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { visits, notes } = useSession();
  const visit = visits.find((v) => v.id === visitId) ?? null;
  if (visit === null) {
    return (
      <Screen>
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
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <VisitCard visit={visit} statusOverride={status} />
        <Card>
          <AppText role="label" color="inkSoft">
            {t("visits.detail.noteStatus")}
          </AppText>
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
  content: { gap: spacing.md, paddingBottom: spacing.xl },
});
