/**
 * Month calendar for the Vizitlerim takvim view (02 §4).
 *
 * Built from View/Pressable only — no native calendar module, so it loads in
 * Expo Go (the coordinator's dev client) with nothing to link. The date
 * arithmetic and the localized names live in lib/calendar.ts (pure, tested in
 * node); this file is the thin themed adapter.
 *
 * Two forms, one control, the same rule the tab rail and the segmented control
 * already follow (lib/prefs/appearance.ts): below the large-text scale the
 * month is a Monday-first seven-column grid; at or above it the grid would put
 * a doubled numeral into a phone-seventh of the width and clip, so the control
 * changes FORM (00 §2) into a vertical agenda of the month's visit days — which
 * only ever grows taller and scrolls. A calendar is the tightest horizontal box
 * in the app after the rail, so it earns the same treatment rather than a
 * clamp that would leave its numerals out of step with the body text (the
 * "navbar and sizes don't match" defect INT-260 fixed for the rail).
 *
 * Selection rests on luminance, never hue (SC 1.4.1): the chosen day is a
 * filled `cta` pill with `onCta` text, today (when not chosen) is an accent
 * ring, and a visit day carries one dot regardless of how many visits it holds
 * — the count is spoken by the day panel below the grid, never as a numeral in
 * the cell (invariant 22: no bare numeral crosses into a place a normaliser
 * would mis-read it, and no count is shown without its list).
 */
import { useMemo } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { SymbolView } from "expo-symbols";

import { AppText, Card, useFontScale, useTheme } from "@/components/Themed";
import { joinParts } from "@/lib/a11y/labels";
import { MIN_TAP } from "@/lib/a11y/target";
import {
  addMonths,
  buildCalendarGrid,
  countVisitsByDay,
  longDate,
  monthTitle,
  weekdayHeaders,
  type CalendarCell,
  type YearMonth,
} from "@/lib/calendar";
import { getLocale, t } from "@/lib/i18n";
import { isLargeText } from "@/lib/prefs/appearance";
import { motion, radius, spacing, tracking, type ThemeColors } from "@/lib/theme";

interface VisitCalendarProps {
  /** The visits to mark; a dateless visit marks no day (lib/calendar.ts). */
  visits: readonly { readonly date: string | null }[];
  /** The caller's "today", so the whole screen agrees on one date. */
  todayIso: string;
  /** The displayed month; navigation is lifted so one place owns the state. */
  viewMonth: YearMonth;
  onChangeMonth: (next: YearMonth) => void;
  /** The chosen day (its visits render below the grid), or null for none. */
  selectedIso: string | null;
  onSelectDay: (iso: string) => void;
}

export function VisitCalendar({
  visits,
  todayIso,
  viewMonth,
  onChangeMonth,
  selectedIso,
  onSelectDay,
}: VisitCalendarProps) {
  const theme = useTheme();
  const locale = getLocale();
  const large = isLargeText(useFontScale());
  const counts = useMemo(() => countVisitsByDay(visits), [visits]);
  const grid = useMemo(
    () => buildCalendarGrid(viewMonth, todayIso, counts),
    [viewMonth, todayIso, counts],
  );
  const headers = useMemo(() => weekdayHeaders(locale), [locale]);
  const agendaDays = grid.weeks.flat().filter((cell) => cell.inMonth && cell.visitCount > 0);

  return (
    <Card>
      <View style={styles.monthRow}>
        <NavButton
          label={t("visits.calendar.prevMonth")}
          glyph="chevron.left"
          tint={theme.ink}
          onPress={() => onChangeMonth(addMonths(viewMonth, -1))}
        />
        <AppText role="title" heading style={styles.monthTitle}>
          {monthTitle(viewMonth, locale)}
        </AppText>
        <NavButton
          label={t("visits.calendar.nextMonth")}
          glyph="chevron.right"
          tint={theme.ink}
          onPress={() => onChangeMonth(addMonths(viewMonth, 1))}
        />
      </View>

      {large ? (
        agendaDays.length === 0 ? (
          <AppText role="caption" color="inkFaint" style={styles.agendaEmpty}>
            {t("visits.calendar.monthEmpty")}
          </AppText>
        ) : (
          <View style={styles.agenda}>
            {agendaDays.map((cell) => (
              <AgendaRow
                key={cell.iso}
                cell={cell}
                selected={cell.iso === selectedIso}
                locale={locale}
                theme={theme}
                onSelect={onSelectDay}
              />
            ))}
          </View>
        )
      ) : (
        <View style={styles.grid}>
          <View style={styles.weekRow} accessibilityElementsHidden importantForAccessibility="no">
            {headers.map((name, index) => (
              <View key={index} style={styles.headerCell}>
                <AppText role="caption" color="inkFaint" style={styles.headerText}>
                  {name}
                </AppText>
              </View>
            ))}
          </View>
          {grid.weeks.map((week, index) => (
            <View key={index} style={styles.weekRow}>
              {week.map((cell) => (
                <DayCell
                  key={cell.iso}
                  cell={cell}
                  selected={cell.iso === selectedIso}
                  locale={locale}
                  theme={theme}
                  onSelect={onSelectDay}
                />
              ))}
            </View>
          ))}
        </View>
      )}
    </Card>
  );
}

function NavButton({
  label,
  glyph,
  tint,
  onPress,
}: {
  label: string;
  glyph: "chevron.left" | "chevron.right";
  tint: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={({ pressed }) => [
        styles.navButton,
        { opacity: pressed ? motion.press.rowOpacity : 1 },
      ]}
    >
      <SymbolView name={glyph} size={18} tintColor={tint} />
    </Pressable>
  );
}

function DayCell({
  cell,
  selected,
  locale,
  theme,
  onSelect,
}: {
  cell: CalendarCell;
  selected: boolean;
  locale: "tr" | "en";
  theme: ThemeColors;
  onSelect: (iso: string) => void;
}) {
  // Spill days (the adjacent month's edge) are shown faded for continuity but
  // are not targets — the arrows change month, so a spill day never has to.
  if (!cell.inMonth) {
    return (
      <View style={styles.cell} accessibilityElementsHidden importantForAccessibility="no">
        <View style={styles.numeralPill}>
          <AppText role="body" color="inkFaint" style={styles.numeral}>
            {cell.day}
          </AppText>
        </View>
        <View style={styles.dot} />
      </View>
    );
  }
  const showToday = cell.isToday && !selected;
  const hasVisits = cell.visitCount > 0;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={joinParts(
        longDate(cell.iso, locale),
        hasVisits ? t("visits.calendar.hasVisits") : null,
      )}
      accessibilityHint={t("a11y.visits.dayHint")}
      accessibilityState={{ selected }}
      onPress={() => onSelect(cell.iso)}
      style={({ pressed }) => [styles.cell, { opacity: pressed ? motion.press.rowOpacity : 1 }]}
    >
      <View
        style={[
          styles.numeralPill,
          selected ? { backgroundColor: theme.cta } : null,
          showToday ? { borderColor: theme.primary } : null,
        ]}
      >
        <AppText
          role="body"
          color={selected ? "onCta" : showToday ? "primary" : "ink"}
          style={styles.numeral}
        >
          {cell.day}
        </AppText>
      </View>
      <View
        style={[
          styles.dot,
          { backgroundColor: hasVisits ? (selected ? theme.onCta : theme.primary) : "transparent" },
        ]}
      />
    </Pressable>
  );
}

function AgendaRow({
  cell,
  selected,
  locale,
  theme,
  onSelect,
}: {
  cell: CalendarCell;
  selected: boolean;
  locale: "tr" | "en";
  theme: ThemeColors;
  onSelect: (iso: string) => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={joinParts(longDate(cell.iso, locale), t("visits.calendar.hasVisits"))}
      accessibilityHint={t("a11y.visits.dayHint")}
      accessibilityState={{ selected }}
      onPress={() => onSelect(cell.iso)}
      style={({ pressed }) => [
        styles.agendaRow,
        {
          backgroundColor: selected ? theme.cta : theme.surfaceRaised,
          opacity: pressed ? motion.press.opacity : 1,
        },
      ]}
    >
      <AppText role="body" color={selected ? "onCta" : "ink"} style={styles.agendaLabel}>
        {longDate(cell.iso, locale)}
      </AppText>
      <View style={[styles.dot, { backgroundColor: selected ? theme.onCta : theme.primary }]} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  monthRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    // The title flexes to fill, but if a long month name ever needs the
    // width, the next arrow drops to a new line rather than off the edge
    // (INT-295) — never a shrink that 00 §2 forbids.
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  monthTitle: { flex: 1, textAlign: "center" },
  navButton: {
    minWidth: MIN_TAP,
    minHeight: MIN_TAP,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: radius.chip,
  },
  grid: { gap: spacing.xs, marginTop: spacing.sm },
  weekRow: { flexDirection: "row" },
  headerCell: { flex: 1, alignItems: "center", paddingVertical: spacing.xs },
  headerText: { letterSpacing: tracking.kicker },
  cell: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    minHeight: MIN_TAP,
    paddingVertical: spacing.xs,
    gap: 3,
  },
  numeralPill: {
    minWidth: 30,
    paddingHorizontal: 6,
    paddingVertical: 3,
    borderRadius: radius.chip,
    borderWidth: 1,
    borderColor: "transparent",
    alignItems: "center",
    justifyContent: "center",
  },
  numeral: { fontVariant: ["tabular-nums"] },
  dot: { width: 6, height: 6, borderRadius: radius.chip },
  agenda: { gap: spacing.sm, marginTop: spacing.sm },
  agendaRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    minHeight: 56,
    borderRadius: radius.group,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  agendaLabel: { flexShrink: 1 },
  agendaEmpty: { marginTop: spacing.md },
});
