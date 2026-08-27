/** Visit summary card used on Bugün and Vizitlerim (02 §5.1). */
import { StyleSheet, View } from "react-native";

import { StatusChip } from "@/components/StatusChip";
import { AppText, Card } from "@/components/Themed";
import type { VisitFixture } from "@/lib/dev/accounts";
import { getLocale } from "@/lib/i18n";
import { spacing } from "@/lib/theme";

/** tr-formatted, no truncation (Turkish hospital names are long — 00 §2). */
export function formatVisitDate(iso: string, locale: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", {
    day: "numeric",
    month: "long",
    weekday: "long",
  }).format(date);
}

export function VisitCard({ visit }: { visit: VisitFixture }) {
  return (
    <Card>
      <AppText role="caption" color="inkSoft">
        {formatVisitDate(visit.date, getLocale())}
      </AppText>
      <AppText role="title">{visit.department}</AppText>
      <AppText role="body" color="inkSoft">
        {visit.hospital}
      </AppText>
      {visit.noteStatus === null ? null : (
        <View style={styles.chipRow}>
          <StatusChip status={visit.noteStatus} />
        </View>
      )}
    </Card>
  );
}

const styles = StyleSheet.create({
  chipRow: { marginTop: spacing.xs },
});
