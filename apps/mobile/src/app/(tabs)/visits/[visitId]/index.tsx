/**
 * Visit detail (02 §4): the visit, its note's place on the 02 §5.1 status
 * ladder, and the one next action — prepare (intake) or review. The
 * conversation/orb surface is INT-132+; this screen frames it.
 */
import { Stack, useLocalSearchParams, useRouter } from "expo-router";
import { ScrollView, StyleSheet } from "react-native";

import { AnnouncedText, useNews } from "@/components/Announced";
import { useTabBarClearance } from "@/components/FloatingTabBar";
import { Kicker } from "@/components/Kicker";
import { ListGroup, ListRow } from "@/components/ListRow";
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
import { useDelivery } from "@/lib/intake/delivery/store";
import { effectiveStatus } from "@/lib/intake/note";
import { useSession } from "@/lib/session";
import { visitTypeLabelKey } from "@/lib/taxonomy/labels";
import { spacing } from "@/lib/theme";

/** Pushed screens keep left/right only: the header owns the top inset. */
const HEADER_EDGES = ["left", "right"] as const;

export default function VisitDetail() {
  const router = useRouter();
  const headerOptions = useStackHeader();
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { visits, notes } = useSession();
  // Hoisted above the early return: hooks run in the same order every render.
  const tabBarClearance = useTabBarClearance();
  // INT-587: only the server's confirmation makes a sent note "Gönderildi".
  const delivered = useDelivery(visitId ?? "")?.stage === "delivered";
  const visit = visits.find((v) => v.id === visitId) ?? null;
  const status =
    visit === null ? null : effectiveStatus(visit.noteStatus, notes[visit.id], delivered);
  // INT-397 (SC 4.1.3): the note is sent from the review screen, which is in
  // front and announces it. This screen sits under it at that moment, so here
  // the line is shown, not spoken — on the way back and on every visit.
  const sentNews = useNews(status === "sent");
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
  const hasAnswers = (note?.answers.length ?? 0) > 0;
  return (
    <Screen edges={HEADER_EDGES}>
      {/* Oura framing (design pass 5): every pushed screen carries the
          centred-title bar with the "‹" affordance — nothing before this
          pass offered a visible way back. */}
      <Stack.Screen options={headerOptions(visit.department)} />
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: tabBarClearance }]}>
        <VisitCard visit={visit} statusOverride={status} />
        {visit.visitType !== null ? (
          <Card style={styles.ladderCard}>
            <Kicker label={t("visits.new.visitType")} />
            <Hairline />
            <AppText role="body">{t(visitTypeLabelKey(visit.visitType))}</AppText>
          </Card>
        ) : null}
        {/* SC 1.3.1: each rung names its own state (StatusLadder). A
            wrapping accessibilityRole="list" was tried and removed — on a
            View that is not `accessible` iOS exposes neither the role nor
            the label, and making it accessible would swallow all four
            rungs into one element. The Kicker above already names the
            group for both eye and reader. */}
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
        {/* Paylaşımlarınız (INT-139; 02 §4 "visit detail: … share centre"):
            the grants over this note, the control that stops one, and the
            access log. It appears once the note has left the patient —
            before that there is nothing to have granted, and INT-150's list
            route has no note row to hang a grant off. The row is one tap
            away and never the loudest thing on the screen, which is where a
            control the patient reaches for rarely belongs. */}
        {status !== null && status !== "draft" ? (
          <ListGroup>
            <ListRow
              icon="person.2"
              label={t("shares.title")}
              sublabel={t("shares.sub")}
              chevron
              hint={t("a11y.openHint")}
              onPress={() => router.push(`/(tabs)/visits/${visit.id}/shares`)}
            />
          </ListGroup>
        ) : null}
        {status === "sent" ? (
          <AnnouncedText
            tone="status"
            news={sentNews}
            role="caption"
            color="inkSoft"
            message={t("review.sentInfo")}
          />
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
  content: { gap: spacing.lg, paddingTop: spacing.md },
  ladderCard: { gap: spacing.md },
});
