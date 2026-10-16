/** Visit summary card used on Bugün and Vizitlerim (02 §5.1). */
import { StyleSheet, View } from "react-native";

import { Icon } from "@/components/Icon";
import { StatusChip } from "@/components/StatusChip";
import { AppText, Card, useFontScale, useTheme } from "@/components/Themed";
import { getLocale, t } from "@/lib/i18n";
import { spacing } from "@/lib/theme";
import type { VisitFixture } from "@/lib/types/account";
import { CHEVRON_GAP, CHEVRON_SIZE, chevronPlacement } from "@/lib/visitCardLayout";

/**
 * tr-formatted, no truncation (Turkish hospital names are long — 00 §2).
 * A visit with no date says so (INT-134): the patient may have added it
 * before booking, and inventing a day would be a lie that the reminders,
 * the Doctor Link expiry and the note-staleness clock all trust (02 §2b).
 */
export function formatVisitDate(iso: string | null, locale: string): string {
  if (iso === null) {
    return t("visits.noDate", locale === "tr" ? "tr" : "en");
  }
  const date = new Date(`${iso}T00:00:00`);
  return new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", {
    day: "numeric",
    month: "long",
    weekday: "long",
  }).format(date);
}

interface VisitCardProps {
  visit: VisitFixture;
  /** Live status (local note state) wins over the fixture's ladder step. */
  statusOverride?: VisitFixture["noteStatus"];
  /**
   * The ONE card the screen is about (Bugün). It is the same grouped cell
   * as every other visit card, with no glow, gradient or larger corner
   * (INT-422); what marks it is its place under the screen's title and the
   * semibold date. One focal point per screen (02 §5.2) is the CTA below.
   */
  hero?: boolean;
  /** Show the "›" affordance — set it on cards that navigate (list rows). */
  chevron?: boolean;
}

export function VisitCard({
  visit,
  statusOverride,
  hero = false,
  chevron = false,
}: VisitCardProps) {
  const theme = useTheme();
  const fontScale = useFontScale();
  const status = statusOverride ?? visit.noteStatus;
  // Oura list rows always carry the "›" affordance (pass 4 measurement):
  // these cards navigate, so say so. It takes room in the layout, never a
  // painted spot over the text, so a long Turkish department name ("Kadın
  // Hastalıkları ve Doğum") wraps BEFORE the arrow instead of running under
  // it (INT-372). Where it sits is lib/visitCardLayout's call.
  const placement = chevron && !hero ? chevronPlacement(fontScale) : null;
  const glyph = <Icon name="chevron.right" size={CHEVRON_SIZE} tintColor={theme.inkFaint} />;
  return (
    <Card>
      <View style={styles.row}>
        <View style={styles.text}>
          <View style={placement === "dateLine" ? styles.dateLine : null}>
            {/* The date is secondary ink: the accent is spent once per
                screen, on the CTA. Tabular figures hold day numbers in a
                steady column down a stacked list. */}
            <AppText
              role="caption"
              color="inkSoft"
              style={[
                styles.date,
                hero ? styles.heroDate : null,
                placement === "dateLine" ? styles.dateFill : null,
              ]}
            >
              {formatVisitDate(visit.date, getLocale())}
            </AppText>
            {placement === "dateLine" ? <View pointerEvents="none">{glyph}</View> : null}
          </View>
          <AppText role="title">{visit.department}</AppText>
          <AppText role="body" color="inkSoft">
            {visit.hospital}
          </AppText>
          {status === null ? null : (
            <View style={styles.chipRow}>
              <StatusChip status={status} />
            </View>
          )}
        </View>
        {placement === "beside" ? (
          // A full-height column: the glyph centres against a card of any
          // height, and its width comes out of the text's measure.
          <View pointerEvents="none" style={styles.column}>
            {glyph}
          </View>
        ) : null}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  chipRow: { marginTop: spacing.xs },
  row: { flexDirection: "row" },
  // The text is the flexible part of the row; it wraps within what the
  // chevron leaves it.
  text: { flex: 1, gap: spacing.sm },
  column: { justifyContent: "center", marginLeft: CHEVRON_GAP },
  // Large text: the chevron ends the date line, and the department name
  // below keeps the card's whole measure (lib/visitCardLayout).
  dateLine: { flexDirection: "row", alignItems: "center", gap: CHEVRON_GAP },
  dateFill: { flex: 1 },
  date: { fontVariant: ["tabular-nums"] },
  heroDate: { fontWeight: "600" },
});
