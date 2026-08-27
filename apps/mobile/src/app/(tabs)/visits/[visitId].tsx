/**
 * Visit detail (02 §4): the visit's note status and, later, the conversation
 * entry point. The orb/conversation surface is INT-132+ — this screen only
 * frames it.
 */
import { useLocalSearchParams } from "expo-router";
import { ScrollView, StyleSheet } from "react-native";

import { AppText, Card, Screen } from "@/components/Themed";
import { StatusChip } from "@/components/StatusChip";
import { VisitCard } from "@/components/VisitCard";
import { t } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import { spacing } from "@/lib/theme";

export default function VisitDetail() {
  const { visitId } = useLocalSearchParams<{ visitId: string }>();
  const { account } = useSession();
  const visit = account?.visits.find((v) => v.id === visitId) ?? null;
  if (visit === null) {
    return (
      <Screen>
        <AppText role="body" color="inkSoft">
          {t("visits.empty")}
        </AppText>
      </Screen>
    );
  }
  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <VisitCard visit={visit} />
        <Card>
          <AppText role="label" color="inkSoft">
            {t("visits.detail.noteStatus")}
          </AppText>
          {visit.noteStatus === null ? (
            <AppText role="body" color="inkSoft">
              {t("visits.detail.notStarted")}
            </AppText>
          ) : (
            <StatusChip status={visit.noteStatus} />
          )}
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { gap: spacing.md, paddingBottom: spacing.xl },
});
