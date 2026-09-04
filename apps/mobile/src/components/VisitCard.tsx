/** Visit summary card used on Bugün and Vizitlerim (02 §5.1). */
import { StyleSheet, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { SymbolView } from "expo-symbols";

import { StatusChip } from "@/components/StatusChip";
import { AppText, Card, useTheme } from "@/components/Themed";
import type { VisitFixture } from "@/lib/dev/accounts";
import { getLocale, t } from "@/lib/i18n";
import { radius, spacing, tracking } from "@/lib/theme";

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
  const status = statusOverride ?? visit.noteStatus;
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
      {chevron && !hero ? (
        // Oura list rows always carry the "›" affordance (pass 4
        // measurement) — these cards navigate, so say so. It rides an
        // absolute full-height column so it centres against a card of any
        // height, and the body reserves room on its right (bodyInset) so a
        // long Turkish department name — "Kadın Hastalıkları ve Doğum" —
        // wraps BEFORE the arrow instead of running underneath it.
        <View pointerEvents="none" style={styles.chevronWrap}>
          <SymbolView name="chevron.right" size={14} tintColor={theme.inkFaint} />
        </View>
      ) : null}
      <View style={[styles.body, chevron && !hero ? styles.bodyInset : null]}>
        {/* Design pass 5: the hero date is tracked but INK — Oura spends the
            accent once per screen, and here that moment is the CTA below.
            Pass 6: dates carry tabular figures so day numbers hold a steady
            column in stacked lists (Oura microtypography). */}
        <AppText
          role="caption"
          color="inkSoft"
          style={[styles.date, hero ? styles.heroDate : null]}
        >
          {formatVisitDate(visit.date, getLocale())}
        </AppText>
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
    </Card>
  );
}

const styles = StyleSheet.create({
  chipRow: { marginTop: spacing.xs },
  body: { gap: spacing.sm },
  // Room on the right so a wrapping department name clears the chevron
  // (right: lg + a 14 pt glyph); text wraps instead of running under it.
  bodyInset: { paddingRight: spacing.lg },
  chevronWrap: {
    position: "absolute",
    right: spacing.lg,
    top: 0,
    bottom: 0,
    justifyContent: "center",
  },
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
