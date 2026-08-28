/** Visit summary card used on Bugün and Vizitlerim (02 §5.1). */
import { StyleSheet, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { SymbolView } from "expo-symbols";

import { StatusChip } from "@/components/StatusChip";
import { AppText, Card, useTheme } from "@/components/Themed";
import type { VisitFixture } from "@/lib/dev/accounts";
import { getLocale } from "@/lib/i18n";
import { radius, spacing, tracking } from "@/lib/theme";

/** tr-formatted, no truncation (Turkish hospital names are long — 00 §2). */
export function formatVisitDate(iso: string, locale: string): string {
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
        // measurement) — these cards navigate, so say so.
        <SymbolView
          name="chevron.right"
          size={14}
          tintColor={theme.inkFaint}
          style={styles.chevron}
        />
      ) : null}
      <AppText
        role="caption"
        color={hero ? "primary" : "inkSoft"}
        style={hero ? styles.heroDate : undefined}
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
    </Card>
  );
}

const styles = StyleSheet.create({
  chipRow: { marginTop: spacing.xs },
  chevron: { position: "absolute", right: spacing.lg, top: "50%" },
  hero: {
    borderRadius: radius.hero,
    padding: spacing.lg,
    borderWidth: 0,
    overflow: "hidden",
    gap: spacing.sm,
  },
  heroDate: { fontWeight: "600", letterSpacing: tracking.kicker },
});
