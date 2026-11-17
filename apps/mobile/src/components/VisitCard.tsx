/** Visit summary card used on Bugün and Vizitlerim (02 §5.1). */
import { StyleSheet, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";

import { Icon } from "@/components/Icon";
import { StatusChip } from "@/components/StatusChip";
import { AppText, Card, useFontScale, useTheme } from "@/components/Themed";
import { getLocale, t } from "@/lib/i18n";
import { radius, spacing, tracking } from "@/lib/theme";
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
   * Oura-register hero treatment for the ONE card the screen is about
   * (design pass 3): solid surface with a very soft STATIC accent glow
   * washing down from the top (primarySoft → transparent — the Oura scrim
   * feel), hero radius, date in the accent colour. Text still sits on the
   * solid surface underneath (02 §8.2); the glow is garnish. Everything
   * else stays a quiet surface card — one focal point per screen (02 §5.2).
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
    <Card style={hero ? styles.hero : undefined}>
      {hero ? (
        <LinearGradient
          pointerEvents="none"
          // Fade to the SAME hue at zero alpha — "transparent" is black@0 and
          // drags the wash through grey on the light surface.
          colors={[theme.primarySoft, `${theme.primarySoft}00`]}
          start={{ x: 0.5, y: 0 }}
          // Oura's card scrim dies by mid-card (design pass 4 measurement);
          // 0.85 dragged the wash under the whole card.
          end={{ x: 0.5, y: 0.55 }}
          style={StyleSheet.absoluteFill}
        />
      ) : null}
      <View style={styles.row}>
        <View style={styles.text}>
          <View style={placement === "dateLine" ? styles.dateLine : null}>
            {/* Design pass 5: the hero date is tracked but INK — Oura spends the
                accent once per screen, and here that moment is the CTA below.
                Pass 6: dates carry tabular figures so day numbers hold a steady
                column in stacked lists (Oura microtypography). */}
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
          <AppText role={hero ? "hero" : "title"}>{visit.department}</AppText>
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
  hero: {
    borderRadius: radius.hero,
    padding: spacing.lg,
    borderWidth: 0,
    overflow: "hidden",
    gap: spacing.sm,
  },
  date: { fontVariant: ["tabular-nums"] },
  heroDate: { fontWeight: "600", letterSpacing: tracking.kicker },
});
